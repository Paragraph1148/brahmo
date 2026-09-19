// =================================================================
// Behavioural tests for src/lib/safety-engine.ts
//
// Run against a real Postgres (PGlite) loaded with the repository's
// own schema.sql and seed.sql. Nothing is stubbed except the network
// transport, and the network is hard-blocked for the whole file.
// =================================================================
import "./harness/env.mjs";
import test, { before } from "node:test";
import assert from "node:assert/strict";
import { armNetworkGuard, outboundCount } from "./harness/no-network.mjs";
import { installShim, bootstrapDb } from "./harness/db.mjs";
import { loadPatients, type Case } from "./harness/patients.mjs";
import type { SafetyReport, Drug } from "../src/lib/types.js";

armNetworkGuard();

let cases: Case[];
let reports = new Map<number, SafetyReport>();
let runSafetyChecks: (p: any) => Promise<SafetyReport>;
let getRenalDoseInstruction: any;

before(async () => {
  await installShim();
  ({ runSafetyChecks } = await import("../src/lib/safety-engine.js"));
  ({ getRenalDoseInstruction } = await import("../src/lib/calculators.js"));
  cases = await loadPatients();
  for (const c of cases) reports.set(c.patient.id, await runSafetyChecks(c.patient));
});

const by = (id: number) => reports.get(id)!;
const titles = (id: number) => by(id).flags.map((f) => f.title);
const has = (id: number, re: RegExp) => titles(id).some((t) => re.test(t));

// -----------------------------------------------------------------
// The architectural claim: the safety verdict is reached with no model
// -----------------------------------------------------------------
test("the whole safety path runs without a single outbound call", () => {
  assert.equal(outboundCount(), 0, `safety path made ${outboundCount()} outbound calls`);
  assert.equal(reports.size, 9);
});

test("safety output is deterministic across repeated runs", async () => {
  for (const c of cases) {
    const a = JSON.stringify(await runSafetyChecks(c.patient));
    const b = JSON.stringify(await runSafetyChecks(c.patient));
    assert.equal(a, b, `patient ${c.patient.id} not deterministic`);
    assert.equal(a, JSON.stringify(by(c.patient.id)), `patient ${c.patient.id} drifted from first run`);
  }
});

test("flags are ordered critical → warning → caution → info", () => {
  const rank: Record<string, number> = { critical: 0, warning: 1, caution: 2, info: 3 };
  for (const c of cases) {
    const seq = by(c.patient.id).flags.map((f) => rank[f.severity]);
    for (let i = 1; i < seq.length; i++) {
      assert.ok(seq[i] >= seq[i - 1], `patient ${c.patient.id} flags out of severity order`);
    }
  }
});

// -----------------------------------------------------------------
// Condition detection — the gate every downstream check sits behind
// -----------------------------------------------------------------
test("atrial fibrillation is detected however the clinician wrote it", async () => {
  const phrasings = [
    "Atrial Fibrillation (new)",
    "Newly detected AF",
    "AF",
    "new-onset AF",
    "Paroxysmal AF, rate controlled",
    "AFib",
    "chronic af",
  ];
  const missed: string[] = [];
  for (const text of phrasings) {
    const r = await runSafetyChecks({
      id: 900, patient_label: "probe", age: 70, sex: "M", bmi: 25,
      conditions: [text], medications: [], allergies: [], labs: { Cr: 1.0 },
      vitals: {}, insurance: {}, income_context: "",
    } as any);
    if (r.computed.chads_vasc === null) missed.push(text);
  }
  assert.deepEqual(missed, [], `AF not detected for: ${missed.join(" | ")}`);
});

test("heart failure detection does not fire on unrelated words containing 'ef'/'hf'", async () => {
  const nonHF = ["GERD with reflux", "Left knee osteoarthritis", "Iron deficiency anaemia", "Benign essential tremor"];
  const falsePositives: string[] = [];
  for (const text of nonHF) {
    const r = await runSafetyChecks({
      id: 901, patient_label: "probe", age: 55, sex: "M", bmi: 25,
      conditions: [text], medications: [{ drug: "Pioglitazone", dose: "15mg" }],
      allergies: [], labs: { Cr: 1.0 }, vitals: {}, insurance: {}, income_context: "",
    } as any);
    if (r.flags.some((f) => f.category === "heart_failure")) falsePositives.push(text);
    if (r.drugs_to_avoid.some((d) => /Pioglitazone/.test(d.drug))) falsePositives.push(`${text} (avoid-list)`);
  }
  assert.deepEqual(falsePositives, [], `false HF detection on: ${falsePositives.join(" | ")}`);
});

test("vascular disease does not fire on 'Mitral Stenosis' (substring 'mi')", async () => {
  const r = await runSafetyChecks({
    id: 902, patient_label: "probe", age: 45, sex: "F", bmi: 25,
    conditions: ["Rheumatic Heart Disease", "Mitral Stenosis (moderate)", "Atrial Fibrillation (new)"],
    medications: [], allergies: [], labs: { Cr: 0.9 }, vitals: {}, insurance: {}, income_context: "",
  } as any);
  // 45F, no HF/HTN/diabetes/stroke, no true vascular disease → sex category only.
  assert.equal(r.computed.chads_vasc, 1, "mitral stenosis was scored as vascular disease");
});

// -----------------------------------------------------------------
// Per-patient clinical expectations
// -----------------------------------------------------------------
test("P2 (62F, CKD 3b, on Metformin + Glimepiride): the CKD sulfonylurea stop fires", () => {
  assert.equal(by(2).computed.eGFR, 31);
  assert.equal(by(2).computed.eGFR_stage, "CKD 3b");
  assert.ok(has(2, /Glimepiride in CKD/), "no sulfonylurea-in-CKD critical flag");
  assert.ok(has(2, /Metformin: REDUCE/), "no metformin renal-dose flag");
  // She is 62, and isElderly() is age >= 65, so the elderly-specific
  // hypoglycemia flag correctly does NOT fire here. Note that
  // outputs/patient-questions.md describes this same patient as "elderly"
  // — the doc and the code use different cutoffs; the code follows the
  // conventional >=65.
  assert.ok(
    !by(2).flags.some((f) => /in elderly/.test(f.title)),
    "elderly flag fired for a 62-year-old"
  );
});

test("the elderly hypoglycemia flag turns on exactly at 65", async () => {
  const at = async (age: number) => {
    const r = await runSafetyChecks({
      id: 903, patient_label: "probe", age, sex: "F", bmi: 25,
      conditions: ["T2DM"], medications: [{ drug: "Glimepiride", dose: "2mg OD" }],
      allergies: [], labs: { Cr: 0.8 }, vitals: {}, insurance: {}, income_context: "",
    } as any);
    return r.flags.some((f) => /in elderly/.test(f.title));
  };
  assert.equal(await at(64), false);
  assert.equal(await at(65), true);
});

test("P2 sulfonamide-allergic patients are not steered onto sulfonylureas", () => {
  // P1 carries 'Sulfonamide (rash)'; the cross-reactivity check must fire on
  // any sulfonylurea in the list.
  const p1 = by(1);
  assert.ok(p1.drugs_to_avoid.some((d) => /Sulfonylurea/i.test(d.drug)), "sulfa allergy did not reach avoid-list");
});

test("P5 (66M post-MI with new AF): CHA₂DS₂-VASc is scored and OAC is addressed", () => {
  assert.notEqual(by(5).computed.chads_vasc, null, "CHA₂DS₂-VASc not computed for a patient in AF");
  // 66M: age 65-74 (+1), diabetes (+1), HTN (+1), vascular disease/MI (+1) = 4
  assert.equal(by(5).computed.chads_vasc, 4);
  assert.ok(has(5, /Anticoagulation INDICATED/), "no anticoagulation recommendation");
  assert.ok(has(5, /DOAC preferred/), "non-valvular AF did not get the DOAC recommendation");
});

test("P6 (58F, T2DM + HFrEF + CKD 3a): HF, hyperkalemia and SGLT2i all fire", () => {
  assert.equal(by(6).computed.eGFR, 44);
  assert.ok(has(6, /Gliclazide|Glimepiride/), "no sulfonylurea flag in CKD");
  assert.ok(has(6, /Hyperkalemia risk/), "ACEi + spironolactone with K+ 5.1 did not flag");
  assert.ok(has(6, /SGLT2 inhibitor for diabetes \+ HF/), "no SGLT2i recommendation for T2DM + HFrEF");
  assert.ok(by(6).drugs_to_avoid.some((d) => /Pioglitazone/.test(d.drug)), "Pioglitazone not on the HF avoid-list");
});

test("P7 (45F RHD + mitral stenosis + AF): warfarin only, DOACs excluded", () => {
  assert.ok(has(7, /Warfarin ONLY/), "valvular AF did not get the warfarin-only flag");
  assert.ok(!has(7, /DOAC preferred/), "a DOAC was recommended in rheumatic valvular AF");
});

test("P9 (60M inferior STEMI, aspirin allergy, HbA1c 9.8): the allergy is flagged", () => {
  assert.ok(
    by(9).flags.some((f) => f.category === "allergy" && /aspirin/i.test(f.title + f.detail)),
    "documented aspirin allergy produced no flag in an ACS patient whose first-line drug is aspirin"
  );
});

// -----------------------------------------------------------------
// Renal dosing, as a property over every drug in the formulary
// -----------------------------------------------------------------
interface Interval { lo: number; hi: number }
function parseBucket(key: string): Interval | null {
  if (key === "egfr_all") return { lo: -Infinity, hi: Infinity };
  let m = key.match(/^egfr_(\d+)_plus$/);
  if (m) return { lo: +m[1], hi: Infinity };
  m = key.match(/^egfr_below_(\d+)$/);
  if (m) return { lo: -Infinity, hi: +m[1] };
  m = key.match(/^egfr_(\d+)_(\d+)$/);
  if (m) return { lo: +m[1], hi: +m[2] };
  return null;
}

test("every renal_dosing key in the seed is a parseable eGFR band", async () => {
  const pg = await bootstrapDb();
  const { rows } = await pg.query<Drug>("SELECT * FROM drugs");
  const bad: string[] = [];
  for (const d of rows) {
    for (const k of Object.keys(d.renal_dosing)) {
      if (!parseBucket(k)) bad.push(`${d.generic_name}: ${k}`);
    }
  }
  assert.deepEqual(bad, [], `unparseable renal dosing keys: ${bad.join(", ")}`);
});

test("renal dose lookup returns the narrowest band containing the patient's eGFR", async () => {
  const pg = await bootstrapDb();
  const { rows } = await pg.query<Drug>("SELECT * FROM drugs");
  const failures: string[] = [];
  let checks = 0;

  for (const d of rows) {
    const bands = Object.keys(d.renal_dosing)
      .map((k) => ({ k, iv: parseBucket(k)! }))
      .filter((b) => b.iv);
    for (let egfr = 1; egfr <= 130; egfr++) {
      checks++;
      const containing = bands.filter((b) => egfr >= b.iv.lo && egfr < b.iv.hi);
      const got = getRenalDoseInstruction(d.renal_dosing, egfr);
      if (containing.length === 0) continue;
      const width = (b: Interval) => b.hi - b.lo;
      const narrowest = containing.reduce((a, b) => (width(a.iv) <= width(b.iv) ? a : b));
      if (got !== d.renal_dosing[narrowest.k]) {
        const chosen = Object.entries(d.renal_dosing).find(([, v]) => v === got)?.[0] ?? "NONE";
        failures.push(
          `${d.generic_name} @ eGFR ${egfr}: chose "${chosen}" but "${narrowest.k}" is the narrowest match`
        );
      }
    }
  }
  console.log(`    ↳ ${checks} drug × eGFR renal-dose lookups checked`);
  assert.deepEqual(failures.slice(0, 12), [], `${failures.length} wrong renal-dose selections`);
});

test("no drug leaves a gap where a patient's eGFR matches no band at all", async () => {
  const pg = await bootstrapDb();
  const { rows } = await pg.query<Drug>("SELECT * FROM drugs");
  const gaps: string[] = [];
  for (const d of rows) {
    const bands = Object.keys(d.renal_dosing).map(parseBucket).filter(Boolean) as Interval[];
    if (bands.length === 0) continue;
    for (let egfr = 5; egfr <= 120; egfr++) {
      if (!bands.some((b) => egfr >= b.lo && egfr < b.hi)) gaps.push(`${d.generic_name} @ ${egfr}`);
    }
  }
  assert.deepEqual(gaps.slice(0, 10), [], `${gaps.length} eGFR values fall through every band`);
});

// -----------------------------------------------------------------
// Allergy prose: negation, and attribution to the right drug
// -----------------------------------------------------------------
test("'no anaphylaxis' is not read as anaphylaxis (P9)", () => {
  const aspirin = by(9).flags.find((f) => /aspirin/i.test(f.title));
  assert.ok(aspirin, "no aspirin allergy flag");
  assert.equal(aspirin!.severity, "warning", "a mild rash was escalated to a critical contraindication");
});

test("an aspirin allergy does not put penicillins on the avoid list (P9)", () => {
  assert.ok(
    !by(9).drugs_to_avoid.some((d) => /Penicillin/i.test(d.drug)),
    "penicillins were avoided for a patient with no penicillin allergy"
  );
  assert.ok(by(9).drugs_to_avoid.some((d) => /Aspirin/i.test(d.drug)), "aspirin missing from avoid list");
});

test("a real penicillin anaphylaxis is still absolute (P4)", () => {
  assert.ok(by(4).drugs_to_avoid.some((d) => /Penicillin/i.test(d.drug)), "penicillin anaphylaxis not on avoid list");
  assert.ok(has(4, /Penicillin allergy on file/), "no penicillin allergy flag");
});

test("a severe aspirin reaction is critical, a mild one is not", async () => {
  const mk = async (allergy: string) => {
    const r = await runSafetyChecks({
      id: 904, patient_label: "probe", age: 60, sex: "M", bmi: 26,
      conditions: ["STEMI"], medications: [], allergies: [allergy],
      labs: { Cr: 1.0 }, vitals: {}, insurance: {}, income_context: "",
    } as any);
    return r.flags.find((f) => /aspirin/i.test(f.title))?.severity;
  };
  assert.equal(await mk("Aspirin (mild rash, no anaphylaxis)"), "warning");
  assert.equal(await mk("Aspirin — ANAPHYLAXIS 2019"), "critical");
  assert.equal(await mk("Aspirin-induced bronchospasm"), "critical");
});

test("valvular AF is anticoagulated regardless of CHA₂DS₂-VASc (P7)", () => {
  // 45F with rheumatic MS scores 2, below the female threshold of 3, but
  // mitral stenosis with AF is an indication in its own right.
  assert.equal(by(7).computed.chads_vasc, 2);
  assert.ok(has(7, /Valvular AF → Anticoagulation INDICATED/), "valvular AF was left as 'optional'");
  assert.ok(!has(7, /Anticoagulation optional/), "valvular AF told the clinician OAC was optional");
});
