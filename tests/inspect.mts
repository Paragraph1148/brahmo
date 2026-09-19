import "./harness/env.mjs";
import { installShim } from "./harness/db.mjs";
import { loadPatients } from "./harness/patients.mjs";
await installShim();
const { runSafetyChecks } = await import("../src/lib/safety-engine.js");
const want = new Set((process.argv.slice(2).map(Number)));
for (const c of await loadPatients()) {
  if (want.size && !want.has(c.patient.id)) continue;
  const r = await runSafetyChecks(c.patient);
  console.log(`\n=== #${c.patient.id} ${c.patient.patient_label} (${c.patient.age}${c.patient.sex}) eGFR ${r.computed.eGFR} CHA₂DS₂-VASc ${r.computed.chads_vasc}`);
  for (const f of r.flags) console.log(`  [${f.severity.toUpperCase().padEnd(8)}] ${f.title}`);
  if (r.drugs_to_avoid.length) console.log(`  AVOID: ${r.drugs_to_avoid.map(d=>d.drug).join("; ")}`);
  if (r.recommended_drug_classes.length) console.log(`  CLASSES: ${r.recommended_drug_classes.join("; ")}`);
}
