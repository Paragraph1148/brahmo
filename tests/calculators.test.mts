// =================================================================
// Unit + property tests for src/lib/calculators.ts
//
// The calculators are the part of the system a clinician is entitled
// to treat as arithmetic rather than opinion, so they are tested
// against the published equations rather than against themselves.
// =================================================================
import test from "node:test";
import assert from "node:assert/strict";
import {
  calculateEGFR,
  ckdStage,
  calculateChadsVasc,
  shouldAnticoagulate,
  bmiCategory,
  getRenalDoseInstruction,
} from "../src/lib/calculators.js";

// -----------------------------------------------------------------
// CKD-EPI 2021 (Inker LA et al. NEJM 2021;385:1737-1749)
//
// Reference implementation transcribed independently from the paper,
// then swept over a clinical grid. This catches transcription drift
// (swapped κ/α, missing sex factor, wrong exponent sign).
// -----------------------------------------------------------------
function referenceEGFR(scr: number, age: number, female: boolean): number {
  const k = female ? 0.7 : 0.9;
  const a = female ? -0.241 : -0.302;
  const r = scr / k;
  return (
    142 *
    Math.pow(Math.min(r, 1), a) *
    Math.pow(Math.max(r, 1), -1.2) *
    Math.pow(0.9938, age) *
    (female ? 1.012 : 1)
  );
}

test("CKD-EPI 2021 matches the published equation across a clinical grid", () => {
  let n = 0;
  for (let age = 18; age <= 95; age += 1) {
    for (const scr of [0.4, 0.6, 0.8, 0.9, 1.0, 1.2, 1.5, 1.8, 2.4, 3.0, 4.5, 6.0]) {
      for (const sex of ["M", "F"] as const) {
        const got = calculateEGFR(scr, age, sex);
        const want = Math.round(referenceEGFR(scr, age, sex === "F"));
        assert.equal(got, want, `eGFR mismatch at Scr=${scr} age=${age} sex=${sex}`);
        n++;
      }
    }
  }
  console.log(`    ↳ ${n} eGFR grid points checked against the published equation`);
});

test("CKD-EPI 2021: known clinical anchors", () => {
  // Healthy 30y male, Scr 0.9 (Scr/κ == 1, so only the age term applies):
  // 142 × 0.9938^30 = 117.7 → 118
  assert.equal(calculateEGFR(0.9, 30, "M"), 118);
  // Same patient as a female at her own κ (Scr 0.7): 142 × 0.9938^30 × 1.012 = 119.1 → 119
  assert.equal(calculateEGFR(0.7, 30, "F"), 119);
});

test("CKD-EPI 2021: monotonic in creatinine and in age", () => {
  for (const sex of ["M", "F"] as const) {
    let prev = Infinity;
    for (let scr = 0.4; scr <= 6; scr += 0.1) {
      const v = calculateEGFR(scr, 55, sex)!;
      assert.ok(v <= prev, `eGFR rose with creatinine at ${scr.toFixed(1)} (${sex})`);
      prev = v;
    }
    prev = Infinity;
    for (let age = 18; age <= 95; age++) {
      const v = calculateEGFR(1.1, age, sex)!;
      assert.ok(v <= prev, `eGFR rose with age at ${age} (${sex})`);
      prev = v;
    }
  }
});

test("CKD-EPI 2021: invalid inputs return null rather than NaN/Infinity", () => {
  for (const bad of [0, -1, undefined, NaN]) {
    assert.equal(calculateEGFR(bad as any, 50, "M"), null, `Scr=${bad}`);
  }
  assert.equal(calculateEGFR(1.0, 0, "M"), null);
  assert.equal(calculateEGFR(1.0, -5, "M"), null);
});

test("'Other' sex is scored on the male equation (documented consequence)", () => {
  // Not a defect, but a real clinical caveat: the CKD-EPI 2021 equation has
  // only two sex coefficients, and the code routes anything that is not "F"
  // through the male branch. Pinned so the behaviour cannot change silently.
  assert.equal(calculateEGFR(1.2, 60, "Other"), calculateEGFR(1.2, 60, "M"));
});

// -----------------------------------------------------------------
// KDIGO 2012 staging boundaries
// -----------------------------------------------------------------
test("KDIGO staging is correct on both sides of every boundary", () => {
  const cases: [number, string][] = [
    [120, "Normal (G1)"], [90, "Normal (G1)"], [89, "G2"], [60, "G2"],
    [59, "CKD 3a"], [45, "CKD 3a"], [44, "CKD 3b"], [30, "CKD 3b"],
    [29, "CKD 4"], [15, "CKD 4"], [14, "CKD 5"], [0, "CKD 5"],
  ];
  for (const [egfr, stage] of cases) assert.equal(ckdStage(egfr), stage, `eGFR ${egfr}`);
  assert.equal(ckdStage(null), null);
});

// -----------------------------------------------------------------
// CHA₂DS₂-VASc — scored against the published rule, component by component
// -----------------------------------------------------------------
const BASE = {
  hasHF: false, hasHTN: false, age: 50, hasDiabetes: false,
  hasPriorStroke: false, hasVascularDisease: false, sex: "M" as const,
};

test("CHA₂DS₂-VASc: each component contributes its published weight", () => {
  assert.equal(calculateChadsVasc(BASE), 0);
  assert.equal(calculateChadsVasc({ ...BASE, hasHF: true }), 1);
  assert.equal(calculateChadsVasc({ ...BASE, hasHTN: true }), 1);
  assert.equal(calculateChadsVasc({ ...BASE, hasDiabetes: true }), 1);
  assert.equal(calculateChadsVasc({ ...BASE, hasVascularDisease: true }), 1);
  assert.equal(calculateChadsVasc({ ...BASE, sex: "F" }), 1);
  assert.equal(calculateChadsVasc({ ...BASE, hasPriorStroke: true }), 2, "stroke is worth 2");
  assert.equal(calculateChadsVasc({ ...BASE, age: 75 }), 2, "age ≥75 is worth 2");
  assert.equal(calculateChadsVasc({ ...BASE, age: 65 }), 1, "age 65-74 is worth 1");
  assert.equal(calculateChadsVasc({ ...BASE, age: 74 }), 1);
  assert.equal(calculateChadsVasc({ ...BASE, age: 64 }), 0);
  // Age bands must not stack.
  assert.equal(calculateChadsVasc({ ...BASE, age: 80 }), 2);
  // Maximum attainable score is 9.
  assert.equal(
    calculateChadsVasc({
      hasHF: true, hasHTN: true, age: 80, hasDiabetes: true,
      hasPriorStroke: true, hasVascularDisease: true, sex: "F",
    }),
    9
  );
});

test("Anticoagulation threshold: ≥2 men, ≥3 women (IHRS/CSI 2018)", () => {
  assert.equal(shouldAnticoagulate(1, "M"), false);
  assert.equal(shouldAnticoagulate(2, "M"), true);
  assert.equal(shouldAnticoagulate(2, "F"), false);
  assert.equal(shouldAnticoagulate(3, "F"), true);
});

// -----------------------------------------------------------------
// WHO Asian-Pacific BMI cutoffs (Lancet 2004;363:157-163)
// -----------------------------------------------------------------
test("BMI categories use Asian-Pacific cutoffs, not Caucasian ones", () => {
  assert.equal(bmiCategory(18.4), "Underweight");
  assert.equal(bmiCategory(18.5), "Normal");
  assert.equal(bmiCategory(22.9), "Normal");
  assert.equal(bmiCategory(23.0), "Overweight (Asian)");
  assert.equal(bmiCategory(24.9), "Overweight (Asian)");
  assert.equal(bmiCategory(25.0), "Obese I (Asian)");
  assert.equal(bmiCategory(29.9), "Obese I (Asian)");
  assert.equal(bmiCategory(30.0), "Obese II (Asian)");
});

// -----------------------------------------------------------------
// Renal-dose bucket resolution, tested as a property rather than by example
// -----------------------------------------------------------------
test("renal dose lookup falls back to egfr_all and tolerates empty dosing", () => {
  assert.equal(getRenalDoseInstruction({}, 50), null);
  assert.equal(getRenalDoseInstruction({ egfr_all: "use" }, 50), "use");
  assert.equal(getRenalDoseInstruction({ egfr_all: "use" }, null), "use");
  // No matching bucket and no egfr_all → null, not a wrong instruction.
  assert.equal(getRenalDoseInstruction({ egfr_below_15: "avoid" }, 90), null);
});
