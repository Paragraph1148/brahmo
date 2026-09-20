// =================================================================
// Freeze the TypeScript safety engine's output for every patient.
// This file is the oracle the Python port is verified against: it is
// written once from the implementation that is known-good, and from
// then on a difference is a bug in the port (or, occasionally, a bug
// here that the port found).
//
//   npm run golden          # write tests/golden/*.json
//   npm run golden -- check # fail if the current engine has drifted
// =================================================================
import "./harness/env.mjs";
import { installShim } from "./harness/db.mjs";
import { loadPatients } from "./harness/patients.mjs";
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "golden");
const check = process.argv.includes("check");

await installShim();
const { runSafetyChecks } = await import("../src/lib/safety-engine.js");

// Stable key order so the JSON is diffable and hashable.
const sortKeys = (v: unknown): unknown =>
  Array.isArray(v)
    ? v.map(sortKeys)
    : v && typeof v === "object"
      ? Object.fromEntries(Object.keys(v as object).sort().map((k) => [k, sortKeys((v as Record<string, unknown>)[k])]))
      : v;

mkdirSync(OUT, { recursive: true });
let drift = 0;

for (const c of await loadPatients()) {
  const report = await runSafetyChecks(c.patient);
  const body = JSON.stringify(
    { patient: sortKeys(c.patient), question: c.question, origin: c.origin, report: sortKeys(report) },
    null,
    2,
  ) + "\n";
  const path = join(OUT, `patient-${String(c.patient.id).padStart(2, "0")}.json`);

  if (check) {
    if (!existsSync(path)) { console.error(`MISSING  ${path}`); drift++; continue; }
    const have = readFileSync(path, "utf8");
    if (have !== body) { console.error(`DRIFTED  #${c.patient.id} ${c.patient.patient_label}`); drift++; }
    else console.log(`ok       #${c.patient.id} ${c.patient.patient_label}`);
  } else {
    writeFileSync(path, body);
    console.log(`wrote    #${String(c.patient.id).padStart(2)} ${c.patient.patient_label.padEnd(38)} ${report.flags.length} flags`);
  }
}

if (check && drift) { console.error(`\n${drift} patient(s) drifted from the recorded golden output.`); process.exit(1); }
if (check) console.log("\nno drift.");
