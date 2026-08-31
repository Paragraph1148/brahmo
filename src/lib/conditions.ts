// =================================================================
// BRAHMO Clinical AI — Condition detection
//
// Single source of truth for "does this patient have condition X".
//
// Both consumers read from here:
//   safety-engine.ts   — decides which safety checks run
//   prompt-composer.ts — decides which guidelines and drugs the model sees
//
// These used to be two separate implementations. They disagreed on 6.7%
// of the phrasing corpus in tests/harness/phrasings.mts, which meant a
// patient could be treated as being in heart failure by the safety checks
// while the retrieval layer withheld the heart-failure guidelines from
// the model. One detector, two consumers, no drift.
// =================================================================
import type { Patient } from "./types";

/**
 * Matches a keyword against the problem list on whole-word boundaries.
 *
 * Bare substring matching is not safe here: the abbreviations clinicians
 * use for these conditions are short and common as fragments of unrelated
 * words. "ef" appears in "reflux", "left" and "deficiency"; "mi" in
 * "mitral", "migraine" and "vitamin"; "af" in "deaf". Each of those was
 * observed firing a contraindication on a patient who did not have the
 * condition. Anchoring to \b keeps the abbreviations usable without
 * matching inside longer words.
 */
export function hasCondition(patient: Patient, ...keywords: string[]): boolean {
  const text = patient.conditions.join(" | ").toLowerCase();
  return keywords.some((k) => {
    const escaped = k.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`\\b${escaped}\\b`).test(text);
  });
}

export function isElderly(patient: Patient): boolean {
  return patient.age >= 65;
}

export function isHF(patient: Patient): boolean {
  return hasCondition(
    patient,
    "heart failure", "cardiac failure", "hf", "hfref", "hfpef", "chf",
    "ef", "ejection fraction", "lv dysfunction"
  );
}

export function isAF(patient: Patient): boolean {
  return hasCondition(patient, "atrial fibrillation", "af", "afib", "a-fib");
}

export function isDiabetic(patient: Patient): boolean {
  return hasCondition(patient, "t2dm", "t1dm", "dm", "diabetes", "diabetic", "diabetes mellitus");
}

export function hasHTN(patient: Patient): boolean {
  return hasCondition(patient, "htn", "hypertension", "hypertensive");
}

export function hasStroke(patient: Patient): boolean {
  return hasCondition(patient, "stroke", "tia", "cva", "cerebrovascular", "cerebrovascular accident");
}

export function hasVascularDisease(patient: Patient): boolean {
  return hasCondition(
    patient,
    "mi", "myocardial", "myocardial infarction", "pad", "cad", "ihd",
    "stemi", "nstemi", "angina", "acs", "peripheral arterial disease",
    "cabg", "pci", "ischaemic heart disease", "ischemic heart disease"
  );
}

/**
 * Matches an allergy keyword, on word boundaries and respecting negation.
 *
 * Allergy fields are written as prose by whoever clerked the patient, and
 * they routinely record what the reaction was NOT: "Aspirin (mild rash, no
 * anaphylaxis)". A plain substring test reads "anaphylaxis" out of that and
 * escalates a rash into an absolute contraindication — and, where the
 * keyword list is an OR, attributes it to an unrelated drug. Both were
 * observed on patient 9. A keyword directly preceded by a negation does
 * not count as present.
 */
export function hasAllergy(patient: Patient, ...keywords: string[]): boolean {
  const text = patient.allergies.join(" | ").toLowerCase();
  const NEGATION = /\b(no|not|non|without|denies|denied|negative for|nil|neg)\b[\s,\-]*$/;

  return keywords.some((k) => {
    const escaped = k.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`\\b${escaped}\\b`, "g");
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      if (!NEGATION.test(text.slice(Math.max(0, m.index - 24), m.index))) return true;
    }
    return false;
  });
}

// =================================================================
// Retrieval tags
//
// Deliberately more generous than the diagnostic predicates above.
// A safety gate should be conservative — do not act as if a patient is
// diabetic on weak evidence. Retrieval should be liberal — withholding
// the diabetes formulary from the model cannot make an answer safer, it
// can only make it less informed.
// =================================================================
export function deriveConditionTags(patient: Patient): string[] {
  const tags = new Set<string>();

  // Diagnosed, or meeting a diagnostic lab threshold (RSSDI 2022 / WHO:
  // HbA1c >= 6.5%, FPG >= 126 mg/dL, random glucose >= 200 mg/dL).
  const hba1c = Number(patient.labs?.HbA1c);
  const fbs = Number(patient.labs?.FBS);
  const glucose = Number(patient.labs?.Glucose);
  const dysglycaemic = hba1c >= 6.5 || fbs >= 126 || glucose >= 200;
  if (isDiabetic(patient) || dysglycaemic) tags.add("diabetes");

  if (hasHTN(patient) || hasVascularDisease(patient)) tags.add("cardiovascular");
  if (isHF(patient)) tags.add("heart_failure");
  if (isAF(patient)) tags.add("atrial_fibrillation");
  if (hasCondition(patient, "ckd", "chronic kidney disease", "renal", "nephropathy", "esrd"))
    tags.add("ckd");
  if (hasCondition(patient, "nafld", "fatty liver", "nash")) tags.add("nafld");
  if (hasCondition(patient, "rheumatic", "rhd", "valvular", "mitral stenosis", "aortic stenosis", "prosthetic valve"))
    tags.add("rheumatic_heart_disease");
  if (isElderly(patient)) tags.add("elderly");
  if (hasCondition(patient, "retinopathy", "neuropathy")) tags.add("diabetes_complications");

  return Array.from(tags);
}
