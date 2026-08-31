// =================================================================
// BRAHMO Clinical AI — Prompt Composer
//
// Builds the India-specific prompt that gets injected into Claude.
// Pulls from:
//   - Patient record (conditions, meds, allergies, labs, insurance, income)
//   - Safety engine output (precomputed flags)
//   - Relevant guidelines (filtered by condition_tags from patient.conditions)
//   - Relevant drugs (filtered by condition_tags, with formulary stock)
//   - Hospital contacts (Apollo Chennai)
//
// ARCHITECTURE NOTE: the composer never hard-codes "diabetes" or
// "cardiovascular" — it derives condition tags dynamically from the
// patient's conditions, so adding respiratory/gastro/etc. requires
// zero changes here.
// =================================================================
import { supabase } from "./supabase";
import type {
  Patient,
  SafetyReport,
  Drug,
  Guideline,
  SafetyFlag,
} from "./types";

// =================================================================
// Apollo Chennai hospital contacts (from assessment Setup Guide)
// =================================================================
const HOSPITAL_CONTACTS = {
  endocrinology: {
    diabetes_educator: "Sister Lakshmi, ext 3345 (Hindi/Tamil/English)",
    dietitian: "Ms. Priya Raman, ext 3350 (South Indian diet specialist)",
    podiatrist: "Dr. Suresh, ext 3360 (Mon/Wed/Fri)",
    ophthalmology: "Dr. Iyer, ext 4410 (retinal screening)",
    nephrology: "Dr. Ramachandran, ext 4420",
  },
  cardiology: {
    interventional: "Dr. Venkat, ext 4455 (cath lab)",
    electrophysiology: "Dr. Anand, ext 4460",
    heart_failure_clinic: "Dr. Meena, ext 4465 (Tue/Thu)",
    cardiac_rehab: "Sister Priya, ext 4470",
    ccu_nurse_station: "ext 3322",
    code_stemi: "Call 4455 + alert CCU 3322",
  },
  blood_bank: "O-negative available (2 units standby)",
};

// =================================================================
// Condition-tag derivation — see ./conditions.ts (shared with the engine)
// =================================================================
import { deriveConditionTags } from "./conditions";

// =================================================================
// Data pulls
// =================================================================
async function loadRelevantGuidelines(tags: string[]): Promise<Guideline[]> {
  if (tags.length === 0) return [];
  // Use the SQL helper function defined in schema.sql which handles JSONB containment cleanly.
  // We call it once per tag and merge the results client-side, deduplicating by guideline id.
  const allResults: Guideline[] = [];
  const seen = new Set<number>();

  for (const tag of tags) {
    const { data, error } = await supabase.rpc("guidelines_for_condition", { p_tag: tag });
    if (error) throw error;
    for (const g of (data as Guideline[]) || []) {
      if (!seen.has(g.id)) {
        seen.add(g.id);
        allResults.push(g);
      }
    }
  }

  // Sort by year desc, source, id
  allResults.sort((a, b) => {
    if (b.year !== a.year) return b.year - a.year;
    if (a.source_id !== b.source_id) return a.source_id.localeCompare(b.source_id);
    return a.id - b.id;
  });

  return allResults;
}

async function loadRelevantDrugsWithFormulary(
  tags: string[]
): Promise<Array<Drug & { in_stock: boolean; stock_level: string | null; pharmacy_notes: string | null }>> {
  if (tags.length === 0) return [];

  // Pull drugs via the SQL helper function, once per tag, deduplicate by id
  const drugById = new Map<number, Drug>();
  for (const tag of tags) {
    const { data, error } = await supabase.rpc("drugs_for_condition", { p_tag: tag });
    if (error) throw error;
    for (const d of (data as Drug[]) || []) {
      drugById.set(d.id, d);
    }
  }
  const allDrugs = Array.from(drugById.values());
  if (allDrugs.length === 0) return [];

  // Pull formulary entries for these drugs and join client-side
  const drugIds = allDrugs.map((d) => d.id);
  const { data: formularyData, error: fmError } = await supabase
    .from("hospital_formulary")
    .select("*")
    .in("drug_id", drugIds);
  if (fmError) throw fmError;

  const formularyById = new Map<number, any>();
  for (const f of (formularyData as any[]) || []) {
    formularyById.set(f.drug_id, f);
  }

  const merged = allDrugs.map((d) => {
    const f = formularyById.get(d.id);
    return {
      ...d,
      in_stock: f?.in_stock ?? false,
      stock_level: f?.stock_level ?? null,
      pharmacy_notes: f?.pharmacy_notes ?? null,
    };
  });

  // Sort by drug_class then generic_name
  merged.sort((a, b) => {
    if (a.drug_class !== b.drug_class) return a.drug_class.localeCompare(b.drug_class);
    return a.generic_name.localeCompare(b.generic_name);
  });

  return merged;
}

// =================================================================
// Section builders
// =================================================================
function buildPatientSection(patient: Patient): string {
  const meds = patient.medications.length === 0
    ? "None"
    : patient.medications.map((m) => `${m.drug} ${m.dose}`).join(", ");

  const labs = Object.entries(patient.labs)
    .filter(([_, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${k} ${v}`)
    .join(", ");

  const vitals = Object.entries(patient.vitals)
    .filter(([_, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${k} ${v}`)
    .join(", ");

  return `## PATIENT
- **${patient.patient_label}** — ${patient.age}${patient.sex}, BMI ${patient.bmi}
- **Conditions:** ${patient.conditions.join("; ")}
- **Medications:** ${meds}
- **Allergies:** ${patient.allergies.join(", ")}
- **Labs:** ${labs}
- **Vitals:** ${vitals}
- **Insurance:** ${patient.insurance.provider || "None"}${patient.insurance.notes ? ` (${patient.insurance.notes})` : ""}
- **Income context:** ${patient.income_context}`;
}

function buildSafetySection(report: SafetyReport): string {
  if (report.flags.length === 0) {
    return `## SAFETY ENGINE OUTPUT
- eGFR: ${report.computed.eGFR ?? "—"} (${report.computed.eGFR_stage ?? "—"})
- CHA₂DS₂-VASc: ${report.computed.chads_vasc ?? "N/A"}
- BMI category: ${report.computed.bmi_category ?? "—"}

No safety alerts triggered. Patient is clinically straightforward.`;
  }

  const grouped: Record<string, SafetyFlag[]> = {
    critical: [],
    warning: [],
    caution: [],
    info: [],
  };
  report.flags.forEach((f) => grouped[f.severity].push(f));

  let out = `## SAFETY ENGINE OUTPUT (pre-computed - YOU MUST RESPECT THESE)
- eGFR: ${report.computed.eGFR ?? "—"} (${report.computed.eGFR_stage ?? "—"})
- CHA₂DS₂-VASc: ${report.computed.chads_vasc ?? "N/A"}
- BMI category: ${report.computed.bmi_category ?? "—"}\n`;

  const labels: Record<string, string> = {
    critical: "🔴 CRITICAL (must address)",
    warning: "🟠 WARNING",
    caution: "🟡 CAUTION",
    info: "🔵 INFO / Recommendation",
  };

  for (const sev of ["critical", "warning", "caution", "info"] as const) {
    if (grouped[sev].length === 0) continue;
    out += `\n### ${labels[sev]}\n`;
    grouped[sev].forEach((f) => {
      out += `- **${f.title}**\n  ${f.detail}\n`;
      if (f.action) out += `  → Action: ${f.action}\n`;
      if (f.guideline_source) out += `  → Source: ${f.guideline_source}\n`;
    });
  }

  if (report.drugs_to_avoid.length > 0) {
    out += `\n### DRUGS TO AVOID for this patient\n`;
    report.drugs_to_avoid.forEach((d) => {
      out += `- **${d.drug}** — ${d.reason}\n`;
    });
  }

  if (report.recommended_drug_classes.length > 0) {
    out += `\n### RECOMMENDED DRUG CLASSES\n`;
    report.recommended_drug_classes.forEach((c) => {
      out += `- ${c}\n`;
    });
  }

  return out;
}

function buildGuidelinesSection(guidelines: Guideline[]): string {
  if (guidelines.length === 0) return "";

  const bySource: Record<string, Guideline[]> = {};
  guidelines.forEach((g) => {
    if (!bySource[g.source_id]) bySource[g.source_id] = [];
    bySource[g.source_id].push(g);
  });

  let out = `## RELEVANT INDIAN GUIDELINES (cite these — do NOT cite ADA, ACC/AHA, ESC, NICE)\n`;
  Object.entries(bySource).forEach(([source, items]) => {
    out += `\n### ${source}\n`;
    items.forEach((g) => {
      out += `- **${g.section}** (${g.year}, Evidence ${g.evidence_level || "—"}): ${g.recommendation}\n`;
    });
  });
  return out;
}

function buildDrugsSection(
  drugs: Array<Drug & { in_stock: boolean; stock_level: string | null; pharmacy_notes: string | null }>,
  patient: Patient
): string {
  if (drugs.length === 0) return "";

  const byClass: Record<string, typeof drugs> = {};
  drugs.forEach((d) => {
    if (!byClass[d.drug_class]) byClass[d.drug_class] = [];
    byClass[d.drug_class].push(d);
  });

  const isUninsured = !patient.insurance.provider || patient.insurance.provider === "NONE";

  let out = `## AVAILABLE INDIAN DRUGS (use these brands + ₹ prices in your response)\n`;
  if (isUninsured) {
    out += `\n⚠️ PATIENT IS UNINSURED — prioritize NLEM drugs and cheapest options. Mention Jan Aushadhi Kendra availability for NLEM drugs.\n`;
  }

  Object.entries(byClass).forEach(([cls, items]) => {
    out += `\n### ${cls}\n`;
    items.forEach((d) => {
      const tags = [
        d.nlem_status ? "NLEM✓" : null,
        d.in_stock ? `In stock (${d.stock_level})` : "Not stocked",
        d.hf_safe === false ? "⚠️UNSAFE-IN-HF" : null,
        d.hypoglycemia_risk === "high" ? "⚠️HIGH HYPO RISK" : null,
        d.weight_effect === "loss" ? "weight loss" : d.weight_effect === "gain" ? "weight gain" : null,
      ].filter(Boolean).join(" | ");
      out += `- **${d.generic_name}** (${d.indian_brand_name}, ${d.manufacturer}) — ${d.mrp_price} [${tags}]`;
      if (d.notes) out += ` — ${d.notes}`;
      out += `\n`;
    });
  });
  return out;
}

function buildCostSection(patient: Patient): string {
  const isUninsured = !patient.insurance.provider || patient.insurance.provider === "NONE";
  let out = `## COST & INSURANCE CONTEXT
- Patient income: ${patient.income_context}
- Insurance: ${patient.insurance.provider || "NONE"}`;
  if (patient.insurance.notes) out += `\n- Insurance notes: ${patient.insurance.notes}`;
  if (isUninsured) {
    out += `\n- **UNINSURED** — every prescription must be affordable. Prefer NLEM drugs available at Jan Aushadhi stores (50-80% cheaper than MRP).`;
  }
  return out;
}

function buildHospitalSection(tags: string[]): string {
  const sections: string[] = [];

  if (tags.includes("diabetes") || tags.includes("ckd") || tags.includes("diabetes_complications")) {
    sections.push(`**Endocrinology / Diabetes care:**
  - Diabetes Educator: ${HOSPITAL_CONTACTS.endocrinology.diabetes_educator}
  - Dietitian: ${HOSPITAL_CONTACTS.endocrinology.dietitian}
  - Podiatrist: ${HOSPITAL_CONTACTS.endocrinology.podiatrist}
  - Ophthalmology (retinal screening): ${HOSPITAL_CONTACTS.endocrinology.ophthalmology}
  - Nephrology: ${HOSPITAL_CONTACTS.endocrinology.nephrology}`);
  }

  if (
    tags.includes("cardiovascular") ||
    tags.includes("heart_failure") ||
    tags.includes("atrial_fibrillation")
  ) {
    sections.push(`**Cardiology:**
  - Interventional / Cath lab: ${HOSPITAL_CONTACTS.cardiology.interventional}
  - Electrophysiology: ${HOSPITAL_CONTACTS.cardiology.electrophysiology}
  - Heart Failure Clinic: ${HOSPITAL_CONTACTS.cardiology.heart_failure_clinic}
  - Cardiac Rehab: ${HOSPITAL_CONTACTS.cardiology.cardiac_rehab}
  - CCU: ${HOSPITAL_CONTACTS.cardiology.ccu_nurse_station}
  - Code STEMI protocol: ${HOSPITAL_CONTACTS.cardiology.code_stemi}
  - Blood bank: ${HOSPITAL_CONTACTS.blood_bank}`);
  }

  if (sections.length === 0) return "";

  return `## APOLLO CHENNAI REFERRAL CONTACTS (mention relevant ones)\n${sections.join("\n\n")}`;
}

function buildInstructionsSection(): string {
  return `## RESPONSE INSTRUCTIONS — read carefully

You are advising a clinician at Apollo Hospitals, Chennai. The clinician already knows medicine; what they need is **Indian-specific decision support that generic AI cannot provide**. Your response MUST:

### Hard rules (failing any of these = useless response)

1. **CITE INDIAN GUIDELINES BY NAME** in your response text — not just at the end. Write "RSSDI 2022 recommends..." or "Per CSI 2017...". NEVER cite ADA, ACC/AHA, ESC, or NICE as the primary authority.

2. **EVERY drug recommendation MUST include**: generic name + Indian brand (from the drugs list above) + exact ₹ price + NLEM status. Example format:
   - ✅ "Teneligliptin 20mg (Dynaglipt, Mankind Pharma, ₹84.8/strip of 10, non-NLEM)"
   - ❌ "DPP-4 inhibitor" or "Teneligliptin (cheaper option)" — vague, useless

3. **DO A SIDE-BY-SIDE COST COMPARISON** when multiple drugs are options. Show the math:
   - "Metformin SR ~₹160/month (NLEM, ₹40/mo at Jan Aushadhi)"
   - "Teneligliptin ~₹254/month (non-NLEM, full retail only)"
   - "Empagliflozin ~₹350/month (non-NLEM, branded only)"
   The clinician needs to see the numbers to counsel the patient.

4. **ADDRESS THE PATIENT'S OCCUPATION + INCOME EXPLICITLY**. If patient drives commercially (auto-driver, truck, taxi) → flag sulfonylureas/insulin as **occupational hypoglycemia hazard** (a hypo while driving can kill). If uninsured + low daily wage → calculate what % of daily income the regimen costs. If insured with caps → check if total monthly cost stays under cap.

5. **NLEM + JAN AUSHADHI MATH**. For uninsured patients, for each NLEM drug you recommend, mention: (a) NLEM status, (b) approximate Jan Aushadhi Kendra price (typically 50-80% off MRP), (c) the nearest Jan Aushadhi store concept. Don't just say "available at Jan Aushadhi" — say "₹160/mo retail vs ~₹40/mo at Jan Aushadhi = 75% savings."

6. **RESPECT EVERY SAFETY FLAG ABOVE**. Do NOT recommend any drug in the "DRUGS TO AVOID" list. Address each CRITICAL flag explicitly in your response (don't just ignore them).

7. **MENTION RELEVANT HOSPITAL CONTACTS BY NAME + EXTENSION** from the list above. For new T2DM diagnosis → name the dietitian. For STEMI → name the interventional cardiologist + CCU extension + the Code STEMI protocol. For CKD progression → name the nephrologist.

### India-specific things to mention when relevant

- **South Indian diet context**: rice (white rice GI 73), idli, dosa, sambar carb load. RSSDI recommends millets/brown rice substitution.
- **FDCs (Fixed-Dose Combinations)**: huge in India. Glycomet-GP, Galvus Met, Zita Met — mention when adding two agents.
- **Streptokinase vs Tenecteplase for STEMI**: ₹5-8K vs ₹25-35K — this cost comparison is uniquely Indian. Always surface in STEMI cases.
- **Rheumatic Heart Disease + AF**: common in India (rare in West). Warfarin only — DOACs contraindicated. Always check for valvular involvement.
- **Festival/Ramadan fasting**: relevant for diabetic medication timing in Indian context.
- **ESI / CGHS / Star Health caps**: name the specific insurance and how it affects choice.

### Response structure

Use these headings, in this order:
1. **Immediate Action** (1-3 lines — what to do RIGHT NOW)
2. **Drug Recommendation** (with brand + ₹ + NLEM status for every drug)
3. **Cost Analysis** (side-by-side numbers, % of patient income/cap)
4. **Why these drugs and not others** (cite RSSDI/CSI explicitly, reference safety flags)
5. **Monitoring Plan** (labs + frequency)
6. **Referrals** (named contacts + extensions from the list above)
7. **Patient Education** (1-2 India-specific points)

### Tone

- Concise. The clinician is your peer, not a layperson. No "consult your doctor" disclaimers.
- Numbers > adjectives. "₹254/mo" not "affordable". "8% of daily wage" not "manageable".
- Direct. "Avoid sulfonylureas — hypoglycemia while driving is dangerous" not "consider risk-benefit".`;
}

// =================================================================
// Main entry: composePrompt(patient, safetyReport, question)
// =================================================================
export interface ComposedPrompts {
  optionC: string;
  generic: string;
  meta: {
    condition_tags: string[];
    guidelines_count: number;
    drugs_count: number;
    safety_flags_count: number;
    active_sources: string[];
  };
}

export async function composePrompt(
  patient: Patient,
  report: SafetyReport,
  question: string
): Promise<ComposedPrompts> {
  const tags = deriveConditionTags(patient);

  const [guidelines, drugs] = await Promise.all([
    loadRelevantGuidelines(tags),
    loadRelevantDrugsWithFormulary(tags),
  ]);

  const sections = [
    `# CLINICAL CONSULT — Apollo Hospitals, Chennai`,
    buildPatientSection(patient),
    buildSafetySection(report),
    buildGuidelinesSection(guidelines),
    buildDrugsSection(drugs, patient),
    buildCostSection(patient),
    buildHospitalSection(tags),
    buildInstructionsSection(),
    `## CLINICIAN QUESTION\n${question}`,
  ].filter(Boolean);

  const optionC = sections.join("\n\n");

  const generic = `You are a clinical decision support AI advising a doctor.

PATIENT
- ${patient.age}${patient.sex}, BMI ${patient.bmi}
- Conditions: ${patient.conditions.join("; ")}
- Medications: ${patient.medications.map((m) => `${m.drug} ${m.dose}`).join(", ") || "None"}
- Allergies: ${patient.allergies.join(", ")}
- Labs: ${Object.entries(patient.labs).filter(([_, v]) => v !== undefined && v !== null).map(([k, v]) => `${k} ${v}`).join(", ")}
- Vitals: ${Object.entries(patient.vitals).filter(([_, v]) => v !== undefined && v !== null).map(([k, v]) => `${k} ${v}`).join(", ")}
- Insurance: ${patient.insurance.provider || "None"}
- Income: ${patient.income_context}

QUESTION
${question}

Provide a structured clinical recommendation including:
1. Immediate action
2. Drug recommendation with specific drug names and approximate cost
3. Why this drug over alternatives
4. Monitoring plan
5. Referrals
6. Patient education

Be concise — the doctor is your peer.`;

  const sourceSet = new Set(guidelines.map((g) => `${g.source_id} ${g.year}`));
  const activeSources = Array.from(sourceSet).sort();

  return {
    optionC,
    generic,
    meta: {
      condition_tags: tags,
      guidelines_count: guidelines.length,
      drugs_count: drugs.length,
      safety_flags_count: report.flags.length,
      active_sources: activeSources,
    },
  };
}
