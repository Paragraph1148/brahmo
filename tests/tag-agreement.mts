// Two independent condition detectors ship in this codebase:
//   src/lib/safety-engine.ts   → decides which safety checks run
//   src/lib/prompt-composer.ts → decides which guidelines/drugs the model sees
// They are written separately and never cross-checked. This measures how
// often they disagree about the same patient.
import "./harness/env.mjs";
import { installShim } from "./harness/db.mjs";
import { POSITIVES, NEGATIVES, probe, type Cat } from "./harness/phrasings.mjs";
import { loadPatients } from "./harness/patients.mjs";

await installShim();
const E = await import("../src/lib/safety-engine.js");
const C = await import("../src/lib/conditions.js");
const deriveConditionTags: (p: any) => string[] = (C as any).deriveConditionTags;

const PAIRS: [Cat, (p: any) => boolean, string][] = [
  ["HF", E.isHF, "heart_failure"],
  ["AF", E.isAF, "atrial_fibrillation"],
  ["DM", E.isDiabetic, "diabetes"],
];

let disagree = 0, total = 0;
const rows: string[] = [];
for (const [cat, det, tag] of PAIRS) {
  for (const text of [...POSITIVES[cat], ...NEGATIVES]) {
    const p = probe([text]) as any;
    const engine = det(p);
    const composer = deriveConditionTags(p).includes(tag);
    total++;
    if (engine !== composer) {
      disagree++;
      rows.push(`  ${cat}  engine=${String(engine).padEnd(5)} composer=${String(composer).padEnd(5)}  "${text}"`);
    }
  }
}
console.log(`phrasings where the two detectors disagree: ${disagree}/${total} = ${((disagree/total)*100).toFixed(1)}%`);
rows.forEach((r) => console.log(r));

console.log("\nreal patients — tags the composer derives:");
for (const c of await loadPatients()) {
  const tags = deriveConditionTags(c.patient);
  const engine = [E.isHF(c.patient) && "heart_failure", E.isAF(c.patient) && "atrial_fibrillation", E.isDiabetic(c.patient) && "diabetes"].filter(Boolean);
  const missing = (engine as string[]).filter((t) => !tags.includes(t));
  console.log(`  #${c.patient.id} ${c.patient.patient_label.padEnd(36)} tags=[${tags.join(", ")}]${missing.length ? `  ← engine also says: ${missing.join(", ")}` : ""}`);
}
