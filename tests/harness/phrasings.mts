// =================================================================
// A labelled corpus of problem-list phrasings.
//
// Positives are how the condition is actually written in this repo's
// own seed/demo data plus standard clinical shorthand. Negatives are
// ordinary comorbidities from an Indian outpatient problem list that
// carry none of the target conditions. The corpus is fixed in advance
// of any fix so recall and precision are measured, not tuned.
// =================================================================
export type Cat = "HF" | "AF" | "DM" | "HTN" | "STROKE" | "VASC";

export const POSITIVES: Record<Cat, string[]> = {
  HF: [
    "Heart Failure (EF 30%)", "HFrEF", "HFpEF", "CHF",
    "Congestive cardiac failure", "Decompensated heart failure",
    "LV dysfunction, EF 35%", "NYHA III heart failure",
    "Heart failure with reduced ejection fraction", "Chronic HF on GDMT",
  ],
  AF: [
    "Atrial Fibrillation (new)", "Newly detected AF", "AF", "AFib",
    "new-onset AF", "Paroxysmal AF, rate controlled", "chronic af",
    "Persistent atrial fibrillation", "AF with RVR", "Permanent AF",
  ],
  DM: [
    "T2DM (3yr)", "T2DM", "Type 2 Diabetes Mellitus", "diabetes",
    "Diabetic nephropathy", "T1DM", "DM type 2", "Newly diagnosed diabetes",
    "Type 2 DM", "Diabetes mellitus, poorly controlled",
  ],
  HTN: [
    "HTN (1yr)", "Hypertension", "Essential HTN", "Systemic hypertension",
    "Hypertension, newly diagnosed", "Uncontrolled HTN",
  ],
  STROKE: [
    "Prior CVA", "Old stroke", "TIA 2019", "Ischaemic stroke",
    "Cerebrovascular accident", "Prior stroke with residual weakness",
  ],
  VASC: [
    "Anterior MI (3mo ago, DES to LAD)", "STEMI", "NSTEMI", "CAD",
    "IHD", "Peripheral arterial disease (PAD)", "Stable angina",
    "Prior myocardial infarction", "Triple vessel CAD", "Post-CABG, CAD",
  ],
};

/** Ordinary comorbidities carrying none of the six target conditions. */
export const NEGATIVES: string[] = [
  "GERD with reflux",
  "Left knee osteoarthritis",
  "Iron deficiency anaemia",
  "Hypothyroidism on thyroxine",
  "Benign prostatic hyperplasia",
  "Vitamin B12 deficiency",
  "Migraine without aura",
  "Mild cognitive impairment",
  "Deaf in right ear",
  "Chronic obstructive pulmonary disease",
  "Rheumatoid arthritis",
  "Allergic rhinitis",
  "Cataract, left eye",
  "Refractive error",
  "Gallstones, asymptomatic",
  "Mitral Stenosis (moderate)",
  "Psoriasis vulgaris",
  "Lumbar spondylosis",
  "Generalised anxiety disorder",
  "Deferred hernia repair",
];

export function probe(conditions: string[], age = 55) {
  return {
    id: 999, patient_label: "probe", age, sex: "M" as const, bmi: 25,
    conditions, medications: [], allergies: [], labs: { Cr: 1.0 },
    vitals: {}, insurance: {}, income_context: "",
  };
}
