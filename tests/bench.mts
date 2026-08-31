// =================================================================
// BRAHMO measurement harness.
//
// Every number quoted about this project comes from running this file.
// It runs the real safety engine and the real prompt composer over all
// nine patients against a real Postgres loaded from supabase/schema.sql
// and supabase/seed.sql, with the network hard-blocked.
//
//   npx tsx tests/bench.mts
// =================================================================
import "./harness/env.mjs";
import { armNetworkGuard, outboundCount } from "./harness/no-network.mjs";
import { installShim, bootstrapDb } from "./harness/db.mjs";
import { loadPatients } from "./harness/patients.mjs";
import { POSITIVES, NEGATIVES, probe, type Cat } from "./harness/phrasings.mjs";

armNetworkGuard();
await installShim();

const dbmod = await import("./harness/db.mjs");
const { runSafetyChecks } = await import("../src/lib/safety-engine.js");
const { composePrompt } = await import("../src/lib/prompt-composer.js");
const E = await import("../src/lib/safety-engine.js");

const cases = await loadPatients();
const pg = await bootstrapDb();

const line = (s = "") => console.log(s);
const rule = (t: string) => { line(); line(`── ${t} ${"─".repeat(Math.max(0, 66 - t.length))}`); };

// -----------------------------------------------------------------
rule("CORPUS");
for (const t of ["drugs", "drug_interactions", "indian_guidelines", "hospital_formulary"]) {
  const r = await pg.query<{ n: number }>(`SELECT COUNT(*)::int AS n FROM ${t}`);
  line(`  ${t.padEnd(22)} ${String(r.rows[0].n).padStart(4)} rows`);
}
const nlem = await pg.query<{ n: number }>(`SELECT COUNT(*)::int AS n FROM drugs WHERE nlem_status`);
line(`  ${"of which NLEM".padEnd(22)} ${String(nlem.rows[0].n).padStart(4)} drugs`);
line(`  ${"patients under test".padEnd(22)} ${String(cases.length).padStart(4)} (6 seeded + 3 held-out)`);

// -----------------------------------------------------------------
rule("SAFETY OUTPUT PER PATIENT");
const reports = new Map<number, any>();
const sev = { critical: 0, warning: 0, caution: 0, info: 0 } as Record<string, number>;
const cats: Record<string, number> = {};
line("   #  patient                              eGFR stage      CHA₂DS₂  crit warn caut info  avoid");
for (const c of cases) {
  const r = await runSafetyChecks(c.patient);
  reports.set(c.patient.id, r);
  const s: Record<string, number> = { critical: 0, warning: 0, caution: 0, info: 0 };
  for (const f of r.flags) { s[f.severity]++; sev[f.severity]++; cats[f.category] = (cats[f.category] ?? 0) + 1; }
  line(
    `  ${String(c.patient.id).padStart(2)}  ${c.patient.patient_label.slice(0, 34).padEnd(36)}` +
    `${String(r.computed.eGFR ?? "—").padStart(4)} ${String(r.computed.eGFR_stage ?? "—").padEnd(11)}` +
    `${String(r.computed.chads_vasc ?? "—").padStart(5)}   ` +
    `${String(s.critical).padStart(4)} ${String(s.warning).padStart(4)} ${String(s.caution).padStart(4)} ${String(s.info).padStart(4)}` +
    `${String(r.drugs_to_avoid.length).padStart(7)}`
  );
}
const totalFlags = Object.values(sev).reduce((a, b) => a + b, 0);
line(`  ${"TOTAL".padEnd(38)}${" ".repeat(21)}${String(sev.critical).padStart(4)} ${String(sev.warning).padStart(4)} ${String(sev.caution).padStart(4)} ${String(sev.info).padStart(4)}`);
line(`  ${totalFlags} flags across ${cases.length} patients; ${sev.critical} critical, ${sev.warning} warning`);
line(`  by category: ${Object.entries(cats).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(", ")}`);

// -----------------------------------------------------------------
rule("CONDITION DETECTION (labelled corpus, fixed before any fix)");
const DETECT: Record<Cat, (p: any) => boolean> = {
  HF: E.isHF, AF: E.isAF, DM: E.isDiabetic, HTN: E.hasHTN, STROKE: E.hasStroke, VASC: E.hasVascularDisease,
};
let tp = 0, fnN = 0, fp = 0, tn = 0;
for (const cat of Object.keys(DETECT) as Cat[]) {
  for (const t of POSITIVES[cat]) (DETECT[cat](probe([t]) as any) ? tp++ : fnN++);
  for (const t of NEGATIVES) (DETECT[cat](probe([t]) as any) ? fp++ : tn++);
}
line(`  recall              ${tp}/${tp + fnN} = ${((tp / (tp + fnN)) * 100).toFixed(1)}%`);
line(`  false-positive rate ${fp}/${fp + tn} = ${((fp / (fp + tn)) * 100).toFixed(1)}%`);

// -----------------------------------------------------------------
rule("LLM INDEPENDENCE");
dbmod.resetQueryCount();
for (const c of cases) await runSafetyChecks(c.patient);
line(`  outbound network calls made by the safety path : ${outboundCount()}`);
line(`  DB round-trips for ${cases.length} full safety reports    : ${dbmod.queryCount}`);
line(`  → every flag, dose and score above is produced before any model is called.`);

// -----------------------------------------------------------------
rule("DETERMINISM");
let identical = 0;
const REPEATS = 20;
for (const c of cases) {
  const first = JSON.stringify(await runSafetyChecks(c.patient));
  let same = true;
  for (let i = 1; i < REPEATS; i++) {
    if (JSON.stringify(await runSafetyChecks(c.patient)) !== first) same = false;
  }
  if (same) identical++;
}
line(`  ${identical}/${cases.length} patients byte-identical over ${REPEATS} repeated runs (${cases.length * REPEATS} total runs)`);

// -----------------------------------------------------------------
rule("LATENCY — full safety report + prompt composition");
line("  (in-process Postgres; a hosted Supabase adds network RTT per round-trip)");
const ITER = 30;
const safetyMs: number[] = [];
const composeMs: number[] = [];
for (let i = 0; i < ITER; i++) {
  for (const c of cases) {
    let t = performance.now();
    const r = await runSafetyChecks(c.patient);
    safetyMs.push(performance.now() - t);
    t = performance.now();
    await composePrompt(c.patient, r, c.question);
    composeMs.push(performance.now() - t);
  }
}
const pct = (a: number[], p: number) => {
  const s = [...a].sort((x, y) => x - y);
  return s[Math.min(s.length - 1, Math.floor((p / 100) * s.length))];
};
for (const [name, arr] of [["safety engine", safetyMs], ["prompt composition", composeMs]] as const) {
  line(`  ${name.padEnd(20)} p50 ${pct(arr, 50).toFixed(1)} ms   p95 ${pct(arr, 95).toFixed(1)} ms   max ${Math.max(...arr).toFixed(1)} ms   (n=${arr.length})`);
}
const combined = safetyMs.map((v, i) => v + composeMs[i]);
line(`  ${"end-to-end".padEnd(20)} p50 ${pct(combined, 50).toFixed(1)} ms   p95 ${pct(combined, 95).toFixed(1)} ms   max ${Math.max(...combined).toFixed(1)} ms`);

// -----------------------------------------------------------------
rule("RETRIEVAL + PROMPT CONTEXT");
line("   #  patient                          tags gl/29 drugs/48   generic  option-C  ratio");
let gSum = 0, cSum = 0;
for (const c of cases) {
  const r = reports.get(c.patient.id);
  const p = await composePrompt(c.patient, r, c.question);
  gSum += p.generic.length; cSum += p.optionC.length;
  line(
    `  ${String(c.patient.id).padStart(2)}  ${c.patient.patient_label.slice(0, 30).padEnd(32)}` +
    `${String(p.meta.condition_tags.length).padStart(3)} ${String(p.meta.guidelines_count).padStart(5)} ${String(p.meta.drugs_count).padStart(6)}   ` +
    `${String(p.generic.length).padStart(7)} ${String(p.optionC.length).padStart(9)}   ${(p.optionC.length / p.generic.length).toFixed(1)}×`
  );
}
line(`  mean generic prompt ${Math.round(gSum / cases.length)} chars → mean India-context prompt ${Math.round(cSum / cases.length)} chars (${(cSum / gSum).toFixed(1)}× more context)`);
line(`  ≈ ${Math.round(gSum / cases.length / 4)} → ${Math.round(cSum / cases.length / 4)} tokens at ~4 chars/token`);

rule("");
line(`  outbound network calls for the entire run: ${outboundCount()}`);
