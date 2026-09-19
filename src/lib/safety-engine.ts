// =================================================================
// BRAHMO Clinical AI — Safety Engine
//
// Given a Patient, returns a SafetyReport with:
//   - eGFR + CKD stage
//   - CHA₂DS₂-VASc (if AF)
//   - All drug-drug interactions (incl. cross-condition)
//   - Renal dosing flags per current med
//   - HF contraindication flags
//   - Hypoglycemia risk flags (SU + elderly/CKD/beta-blocker)
//   - Hyperkalemia risk (ACEi + K-sparing + K+ level)
//   - Allergy cross-reaction flags
//   - Drug recommendations (preferred classes per profile)
//   - Drugs to avoid
//
// Architecture rule: this engine works for ALL conditions because it
// reads condition_tags + renal_dosing JSONB from the drugs table.
// Adding a 3rd condition (e.g. respiratory) needs NO changes here.
// =================================================================
import { supabase } from "./supabase";
import {
  calculateEGFR,
  ckdStage,
  getRenalDoseInstruction,
  calculateChadsVasc,
  shouldAnticoagulate,
  bmiCategory,
} from "./calculators";
import type {
  Patient,
  Drug,
  DrugInteraction,
  SafetyFlag,
  SafetyReport,
  ComputedValues,
  Medication,
} from "./types";

// =================================================================
// Condition detection — see ./conditions.ts (shared with the composer)
// =================================================================
export {
  hasCondition,
  isElderly,
  isHF,
  isAF,
  isDiabetic,
  hasHTN,
  hasStroke,
  hasVascularDisease,
  hasAllergy,
} from "./conditions";

import {
  hasCondition,
  isElderly,
  isHF,
  isAF,
  isDiabetic,
  hasHTN,
  hasStroke,
  hasVascularDisease,
  hasAllergy,
} from "./conditions";

// =================================================================
// Drug name → DB resolver
// =================================================================
function normalize(name: string): string {
  return name.toLowerCase().replace(/\s+/g, "").replace(/[^a-z0-9]/g, "");
}

async function loadAllDrugs(): Promise<Drug[]> {
  const { data, error } = await supabase.from("drugs").select("*");
  if (error) throw error;
  return data as Drug[];
}

function resolveMedications(meds: Medication[], allDrugs: Drug[]): Medication[] {
  const byNorm = new Map<string, Drug>();
  allDrugs.forEach((d) => {
    byNorm.set(normalize(d.generic_name), d);
    byNorm.set(normalize(d.generic_name_normalized), d);
  });

  return meds.map((m) => {
    const key = normalize(m.drug);
    // exact match
    let hit = byNorm.get(key);
    // fuzzy: starts-with match for "Metformin SR" → "metformin"
    if (!hit) {
      for (const [norm, drug] of byNorm.entries()) {
        if (key.startsWith(norm) || norm.startsWith(key)) {
          hit = drug;
          break;
        }
      }
    }
    return { ...m, drug_id: hit?.id };
  });
}

// =================================================================
// Individual safety checkers — each returns SafetyFlag[]
// =================================================================

/** Renal dosing — for each current med, check if safe at this eGFR */
function checkRenalDosing(
  meds: Medication[],
  allDrugs: Drug[],
  eGFR: number | null
): SafetyFlag[] {
  if (eGFR === null) return [];
  const drugById = new Map(allDrugs.map((d) => [d.id, d]));
  const flags: SafetyFlag[] = [];

  for (const m of meds) {
    if (!m.drug_id) continue;
    const drug = drugById.get(m.drug_id);
    if (!drug) continue;

    const instruction = getRenalDoseInstruction(drug.renal_dosing, eGFR);
    if (!instruction) continue;

    const upper = instruction.toUpperCase();
    let severity: SafetyFlag["severity"] = "info";
    let action: string | undefined;

    if (upper.includes("STOP") || upper.includes("AVOID")) {
      severity = "critical";
      action = "STOP";
    } else if (upper.includes("REDUCE") || upper.includes("CAUTIOUSLY") || upper.includes("CAUTION")) {
      severity = "warning";
      action = "REDUCE / CAUTION";
    } else if (upper.includes("MONITOR")) {
      severity = "caution";
      action = "MONITOR";
    } else {
      // "use", "full dose", "no dose adjustment" - informational
      continue;
    }

    flags.push({
      category: "renal",
      severity,
      title: `${drug.generic_name}: ${action} (eGFR ${eGFR})`,
      detail: `Patient eGFR ${eGFR} → ${instruction}`,
      drugs_involved: [drug.generic_name],
      action,
    });
  }

  return flags;
}

/** Heart-failure contraindication check */
function checkHFContraindications(
  patient: Patient,
  meds: Medication[],
  allDrugs: Drug[]
): SafetyFlag[] {
  if (!isHF(patient)) return [];
  const drugById = new Map(allDrugs.map((d) => [d.id, d]));
  const flags: SafetyFlag[] = [];

  for (const m of meds) {
    if (!m.drug_id) continue;
    const drug = drugById.get(m.drug_id);
    if (!drug) continue;

    if (drug.hf_safe === false) {
      flags.push({
        category: "heart_failure",
        severity: "critical",
        title: `${drug.generic_name} CONTRAINDICATED in Heart Failure`,
        detail: drug.notes || `${drug.drug_class} not safe in HF.`,
        drugs_involved: [drug.generic_name],
        action: "STOP / DO NOT USE",
        guideline_source: "RSSDI+CSI 2022",
      });
    }
  }
  return flags;
}

/** Hypoglycemia risk — SU + (elderly | CKD | beta-blocker) */
function checkHypoglycemiaRisk(
  patient: Patient,
  meds: Medication[],
  allDrugs: Drug[],
  eGFR: number | null
): SafetyFlag[] {
  const drugById = new Map(allDrugs.map((d) => [d.id, d]));
  const flags: SafetyFlag[] = [];

  const highHypoMeds = meds
    .map((m) => (m.drug_id ? drugById.get(m.drug_id) : null))
    .filter((d): d is Drug => !!d && (d.hypoglycemia_risk === "high" || d.hypoglycemia_risk === "moderate"));

  if (highHypoMeds.length === 0) return flags;

  const betaBlockers = meds
    .map((m) => (m.drug_id ? drugById.get(m.drug_id) : null))
    .filter((d): d is Drug => !!d && d.drug_class === "Beta blocker");

  for (const su of highHypoMeds) {
    if (isElderly(patient)) {
      flags.push({
        category: "hypoglycemia",
        severity: "warning",
        title: `Hypoglycemia risk: ${su.generic_name} in elderly`,
        detail: `Patient is ${patient.age}y. RSSDI 2022 recommends DPP4i (e.g. Teneligliptin, Linagliptin) over sulfonylureas in elderly to reduce hypoglycemia risk.`,
        drugs_involved: [su.generic_name],
        action: "Consider switching to DPP4i",
        guideline_source: "RSSDI 2022",
      });
    }
    if (eGFR !== null && eGFR < 60) {
      flags.push({
        category: "hypoglycemia",
        severity: "critical",
        title: `${su.generic_name} in CKD (eGFR ${eGFR}): high hypoglycemia risk`,
        detail: "Sulfonylureas accumulate in renal impairment causing prolonged hypoglycemia. RSSDI 2022: STOP sulfonylurea when eGFR <30; use insulin or Linagliptin (no renal adjustment needed).",
        drugs_involved: [su.generic_name],
        action: "STOP - switch to insulin or Linagliptin",
        guideline_source: "RSSDI 2022",
      });
    }
    if (betaBlockers.length > 0) {
      flags.push({
        category: "hypoglycemia",
        severity: "caution",
        title: `${su.generic_name} + ${betaBlockers.map((b) => b.generic_name).join("/")}: hypoglycemia unawareness`,
        detail: "Beta blockers mask the adrenergic symptoms of hypoglycemia (tachycardia, tremor). Patient must use SMBG and recognise non-adrenergic symptoms (sweating, confusion).",
        drugs_involved: [su.generic_name, ...betaBlockers.map((b) => b.generic_name)],
        action: "Patient education + SMBG",
      });
    }
  }
  return flags;
}

/** Hyperkalemia risk — ACEi/ARB + K-sparing diuretic + (CKD or K+ ≥5.0) */
function checkHyperkalemiaRisk(
  patient: Patient,
  meds: Medication[],
  allDrugs: Drug[],
  eGFR: number | null
): SafetyFlag[] {
  const drugById = new Map(allDrugs.map((d) => [d.id, d]));
  const drugsInUse = meds
    .map((m) => (m.drug_id ? drugById.get(m.drug_id) : null))
    .filter((d): d is Drug => !!d);

  const aceiArb = drugsInUse.filter((d) => d.drug_class === "ACE inhibitor" || d.drug_class === "ARB");
  const ksparing = drugsInUse.filter((d) => d.drug_class === "K-sparing diuretic");
  const k = patient.labs.K;

  if (aceiArb.length === 0 || ksparing.length === 0) return [];

  const flags: SafetyFlag[] = [];
  const isHighRisk = (k !== undefined && k >= 5.0) || (eGFR !== null && eGFR < 60);

  flags.push({
    category: "hyperkalemia",
    severity: isHighRisk ? "critical" : "warning",
    title: `Hyperkalemia risk: ${aceiArb[0].generic_name} + ${ksparing[0].generic_name}`,
    detail:
      `Dual RAAS blockade + K-sparing diuretic significantly raises hyperkalemia risk.` +
      (k !== undefined ? ` Current K+ is ${k} mEq/L.` : "") +
      (eGFR !== null && eGFR < 60 ? ` CKD (eGFR ${eGFR}) compounds the risk.` : "") +
      ` RSSDI+CSI: hold spironolactone if K+ >5.5. Adding SGLT2i mitigates risk.`,
    drugs_involved: [aceiArb[0].generic_name, ksparing[0].generic_name],
    action: k !== undefined && k > 5.5 ? "HOLD K-sparing diuretic" : "Monitor K+ at baseline, 1 wk, monthly",
    guideline_source: "RSSDI+CSI 2022",
  });

  return flags;
}

/** Drug-drug interactions — pairwise lookup against drug_interactions table */
async function checkInteractions(meds: Medication[]): Promise<SafetyFlag[]> {
  const drugIds = meds.map((m) => m.drug_id).filter((id): id is number => !!id);
  if (drugIds.length < 2) return [];

  // Pull all interactions involving any patient drug, INCLUDING those where the other side
  // is a non-DB substance (NULL id, e.g. Alcohol, NSAIDs, IV contrast).
  const drugIdList = drugIds.join(",");
  const { data, error } = await supabase
    .from("drug_interactions")
    .select("*")
    .or(`drug_a_id.in.(${drugIdList}),drug_b_id.in.(${drugIdList})`);
  if (error) throw error;

  const allInteractions = (data as DrugInteraction[]) || [];
  const flags: SafetyFlag[] = [];
  const seen = new Set<number>();
  const idSet = new Set(drugIds);

  for (const ix of allInteractions) {
    if (seen.has(ix.id)) continue;
    // Each end is either: (a) in patient's drug list, or (b) a non-DB substance (id NULL, name like "Alcohol")
    const aMatches = ix.drug_a_id === null ? false : idSet.has(ix.drug_a_id);
    const bMatches = ix.drug_b_id === null ? false : idSet.has(ix.drug_b_id);
    // Fire if BOTH are DB drugs in the patient's list,
    // OR one is a patient drug and the other is a generic substance (NULL id).
    // We don't fire for substance-substance pairs (both NULL) — those don't exist in our data anyway.
    const aNullKnown = ix.drug_a_id === null && ix.drug_a_name;
    const bNullKnown = ix.drug_b_id === null && ix.drug_b_name;
    const shouldFire =
      (aMatches && bMatches) ||
      (aMatches && bNullKnown) ||
      (bMatches && aNullKnown);
    if (!shouldFire) continue;

    seen.add(ix.id);
    const sevMap: Record<DrugInteraction["severity"], SafetyFlag["severity"]> = {
      minor: "info",
      moderate: "caution",
      severe: "warning",
      contraindicated: "critical",
    };

    flags.push({
      category: "interaction",
      severity: sevMap[ix.severity],
      title: `${ix.drug_a_name} + ${ix.drug_b_name}: ${ix.severity.toUpperCase()}`,
      detail: `${ix.clinical_effect}. Mechanism: ${ix.mechanism}.`,
      drugs_involved: [ix.drug_a_name || "", ix.drug_b_name || ""].filter(Boolean),
      action: ix.management,
    });
  }

  return flags;
}

/** Allergy cross-reaction — Sulfonamide → Glimepiride/Glibenclamide; Penicillin → antibiotic flags */
function checkAllergies(patient: Patient, meds: Medication[], allDrugs: Drug[]): SafetyFlag[] {
  const drugById = new Map(allDrugs.map((d) => [d.id, d]));
  const flags: SafetyFlag[] = [];

  // Sulfonamide allergy → sulfonylureas (cross-reactivity minor but documented)
  if (hasAllergy(patient, "sulfonamide", "sulfa")) {
    for (const m of meds) {
      const drug = m.drug_id ? drugById.get(m.drug_id) : null;
      if (!drug) continue;
      if (drug.drug_class === "Sulfonylurea") {
        flags.push({
          category: "allergy",
          severity: "warning",
          title: `${drug.generic_name}: potential cross-reactivity with sulfonamide allergy`,
          detail: "Sulfonylureas share sulfonamide structure. Cross-reactivity is uncommon but documented (especially severe sulfa reactions). Consider non-SU alternative (DPP4i, SGLT2i).",
          drugs_involved: [drug.generic_name],
          action: "Consider switching to non-sulfonylurea agent",
        });
      }
    }
  }

  // Aspirin / NSAID allergy.
  //
  // Aspirin is the one drug every ACS pathway in this formulary starts with,
  // so an allergy to it has to be surfaced before any recommendation is made.
  // Severity follows the reaction on file: a documented rash is a caution
  // (aspirin is often still given, or the patient desensitised), anaphylaxis
  // or bronchospasm is an absolute stop.
  if (hasAllergy(patient, "aspirin", "salicylate", "nsaid", "ibuprofen", "diclofenac")) {
    const severe = hasAllergy(patient, "anaphylaxis", "angioedema", "bronchospasm", "asthma");
    flags.push({
      category: "allergy",
      severity: severe ? "critical" : "warning",
      title: severe
        ? "Aspirin/NSAID allergy with a severe reaction on file — DO NOT give aspirin"
        : "Aspirin/NSAID allergy on file — review before antiplatelet loading",
      detail: severe
        ? "Severe reaction documented. Do not load aspirin. Use Clopidogrel 300-600mg or Ticagrelor 180mg as single-agent P2Y12 loading and involve cardiology; aspirin desensitisation only in a monitored setting."
        : `Documented reaction: ${patient.allergies.join(", ")}. A mild cutaneous reaction is not an absolute contraindication — confirm the reaction history before loading aspirin. If aspirin is withheld, Clopidogrel (Plavix, NLEM) is the substitute P2Y12 loading agent.`,
      drugs_involved: ["Aspirin"],
      action: severe ? "DO NOT USE aspirin — load a P2Y12 inhibitor instead" : "Confirm reaction history before aspirin loading",
      guideline_source: "CSI 2017",
    });
  }

  // Penicillin allergy — flag for downstream antibiotic prescribing (informational; doesn't restrict cardiac drugs)
  if (hasAllergy(patient, "penicillin")) {
    flags.push({
      category: "allergy",
      severity: "caution",
      title: "Penicillin allergy on file",
      detail: hasAllergy(patient, "anaphylaxis")
        ? "ANAPHYLAXIS documented. Avoid all penicillins and cephalosporins. Use alternative antibiotic class (macrolide, fluoroquinolone, glycopeptide) if antibiotics needed during admission. Note: aspirin, clopidogrel, ticagrelor, heparin, and fibrinolytics are SAFE."
        : "Avoid penicillins. Use alternative class if antibiotics required.",
      action: "Document; avoid β-lactams",
    });
  }

  return flags;
}

/** Profile-based drug recommendations (what the patient SHOULD be on) */
function recommendDrugClasses(patient: Patient, eGFR: number | null): {
  classes: string[];
  flags: SafetyFlag[];
} {
  const classes: string[] = [];
  const flags: SafetyFlag[] = [];

  // Diabetes + HF → SGLT2i
  if (isDiabetic(patient) && isHF(patient)) {
    classes.push("SGLT2 inhibitor");
    flags.push({
      category: "recommendation",
      severity: "info",
      title: "First-line: SGLT2 inhibitor for diabetes + HF",
      detail: "Empagliflozin (EMPEROR-Reduced) or Dapagliflozin (DAPA-HF) provides dual benefit: glycemia + HF outcomes. RSSDI+CSI 2022 recommend regardless of HbA1c if T2DM + HFrEF.",
      action: "ADD SGLT2i",
      guideline_source: "RSSDI+CSI 2022",
    });
  }

  // Diabetes + CKD → SGLT2i (if eGFR allows) or Linagliptin
  if (isDiabetic(patient) && eGFR !== null && eGFR < 60) {
    if (eGFR >= 25) {
      classes.push("SGLT2 inhibitor");
      flags.push({
        category: "recommendation",
        severity: "info",
        title: "Consider SGLT2 inhibitor for diabetic kidney disease",
        detail: "Dapagliflozin (DAPA-CKD) provides renoprotection at eGFR ≥25. ACEi/ARB mandatory if albuminuria.",
        action: "Consider adding SGLT2i",
        guideline_source: "RSSDI 2022",
      });
    } else {
      classes.push("DPP4 inhibitor (Linagliptin)");
      flags.push({
        category: "recommendation",
        severity: "info",
        title: "Linagliptin: best DPP4i in advanced CKD",
        detail: "Linagliptin has no renal dose adjustment requirement (hepatic clearance). Preferred when eGFR <30.",
        action: "Use Linagliptin if DPP4i needed",
        guideline_source: "RSSDI 2022",
      });
    }
  }

  // Diabetes + elderly + hypoglycemia risk → DPP4i over SU
  if (isDiabetic(patient) && isElderly(patient)) {
    flags.push({
      category: "recommendation",
      severity: "info",
      title: "Elderly diabetic: relaxed HbA1c target 7.5-8%",
      detail: "RSSDI 2022 recommends relaxed glycemic target in elderly with comorbidities to minimize hypoglycemia risk. Prefer DPP4i over sulfonylureas.",
      guideline_source: "RSSDI 2022",
    });
  }

  // AF + non-valvular → DOAC
  if (isAF(patient) && !hasCondition(patient, "rheumatic", "valvular", "rhd")) {
    classes.push("DOAC");
    flags.push({
      category: "recommendation",
      severity: "info",
      title: "Non-valvular AF: DOAC preferred over Warfarin",
      detail: "IHRS/CSI 2018: Apixaban / Rivaroxaban / Dabigatran preferred. Apixaban has lowest bleeding risk.",
      guideline_source: "IHRS/CSI 2018",
    });
  }

  // AF + rheumatic/valvular → Warfarin only
  if (isAF(patient) && hasCondition(patient, "rheumatic", "valvular", "rhd")) {
    classes.push("Warfarin (RHD/valvular AF)");
    flags.push({
      category: "recommendation",
      severity: "warning",
      title: "Valvular/Rheumatic AF: Warfarin ONLY (DOACs contraindicated)",
      detail: "RHD is common in India (rare in West). DOACs are contraindicated in rheumatic mitral stenosis. INR target 2-3.",
      guideline_source: "IHRS/CSI 2018",
    });
  }

  return { classes, flags };
}

/** Drugs to avoid (proactive list) */
function listDrugsToAvoid(patient: Patient, eGFR: number | null): { drug: string; reason: string }[] {
  const avoid: { drug: string; reason: string }[] = [];

  if (isHF(patient)) {
    avoid.push({ drug: "Pioglitazone", reason: "Fluid retention worsens HF (contraindicated)" });
    avoid.push({ drug: "Saxagliptin", reason: "FDA black box - increased HF hospitalization (SAVOR-TIMI)" });
  }
  if (eGFR !== null && eGFR < 30) {
    avoid.push({ drug: "Metformin", reason: `eGFR ${eGFR} < 30 (lactic acidosis risk)` });
    avoid.push({ drug: "Glimepiride / Glibenclamide", reason: "Prolonged hypoglycemia in advanced CKD" });
    avoid.push({ drug: "NSAIDs", reason: "Nephrotoxic in CKD" });
  }
  if (hasAllergy(patient, "sulfonamide")) {
    avoid.push({ drug: "Sulfonylureas", reason: "Potential sulfonamide cross-reactivity" });
  }
  if (hasAllergy(patient, "penicillin", "beta-lactam", "amoxicillin")) {
    avoid.push({
      drug: "Penicillins, Cephalosporins",
      reason: hasAllergy(patient, "anaphylaxis") ? "Anaphylaxis history" : "Penicillin allergy on file",
    });
  }
  if (hasAllergy(patient, "aspirin", "salicylate", "nsaid")) {
    avoid.push({
      drug: "Aspirin",
      reason: hasAllergy(patient, "anaphylaxis", "angioedema", "bronchospasm")
        ? "Severe aspirin/NSAID reaction documented"
        : "Aspirin/NSAID allergy on file — confirm reaction before use",
    });
  }
  return avoid;
}

// =================================================================
// Main entry: runSafetyChecks(patient) → SafetyReport
// =================================================================
export async function runSafetyChecks(patient: Patient): Promise<SafetyReport> {
  // 1. Compute clinical values
  const eGFR = patient.labs.Cr
    ? calculateEGFR(patient.labs.Cr, patient.age, patient.sex)
    : patient.labs.eGFR ?? null;

  const computed: ComputedValues = {
    eGFR,
    eGFR_stage: ckdStage(eGFR),
    chads_vasc: isAF(patient)
      ? calculateChadsVasc({
          hasHF: isHF(patient),
          hasHTN: hasHTN(patient),
          age: patient.age,
          hasDiabetes: isDiabetic(patient),
          hasPriorStroke: hasStroke(patient),
          hasVascularDisease: hasVascularDisease(patient),
          sex: patient.sex,
        })
      : null,
    bmi_category: patient.bmi ? bmiCategory(patient.bmi) : null,
  };

  // 2. Resolve medications to DB drug ids
  const allDrugs = await loadAllDrugs();
  const resolvedMeds = resolveMedications(patient.medications, allDrugs);

  // 3. Run all checks
  const flags: SafetyFlag[] = [];
  flags.push(...checkRenalDosing(resolvedMeds, allDrugs, eGFR));
  flags.push(...checkHFContraindications(patient, resolvedMeds, allDrugs));
  flags.push(...checkHypoglycemiaRisk(patient, resolvedMeds, allDrugs, eGFR));
  flags.push(...checkHyperkalemiaRisk(patient, resolvedMeds, allDrugs, eGFR));
  flags.push(...(await checkInteractions(resolvedMeds)));
  flags.push(...checkAllergies(patient, resolvedMeds, allDrugs));

  // AF-specific anticoagulation flag
  if (computed.chads_vasc !== null) {
    const valvular = hasCondition(patient, "rheumatic", "valvular", "rhd", "mitral stenosis", "prosthetic valve");
    const indicated = valvular || shouldAnticoagulate(computed.chads_vasc, patient.sex);
    flags.push({
      category: "recommendation",
      severity: indicated ? "warning" : "info",
      title: valvular
        ? `Valvular AF → Anticoagulation INDICATED regardless of CHA₂DS₂-VASc (score ${computed.chads_vasc})`
        : `CHA₂DS₂-VASc = ${computed.chads_vasc} → ${indicated ? "Anticoagulation INDICATED" : "Anticoagulation optional"}`,
      detail: valvular
        ? `CHA₂DS₂-VASc was derived and validated in NON-valvular AF and does not govern this decision. AF with rheumatic mitral stenosis or a prosthetic valve is an anticoagulation indication in its own right — the score is shown for completeness only. Warfarin, INR 2-3.`
        : indicated
        ? `Threshold met (${patient.sex === "F" ? "≥3 for women" : "≥2 for men"}). Recommend OAC unless contraindicated.`
        : "Below threshold. Consider patient preference + bleeding risk.",
      guideline_source: "IHRS/CSI 2018",
    });
  }

  // 4. Recommendations
  const { classes, flags: recFlags } = recommendDrugClasses(patient, eGFR);
  flags.push(...recFlags);

  // 5. Sort flags: critical → warning → caution → info
  const order: Record<string, number> = { critical: 0, warning: 1, caution: 2, info: 3 };
  flags.sort((a, b) => order[a.severity] - order[b.severity]);

  return {
    patient_id: patient.id,
    computed,
    flags,
    recommended_drug_classes: classes,
    drugs_to_avoid: listDrugsToAvoid(patient, eGFR),
  };
}
