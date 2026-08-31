import "./harness/env.mjs";
import { installShim } from "./harness/db.mjs";
import { POSITIVES, NEGATIVES, probe, type Cat } from "./harness/phrasings.mjs";

await installShim();
const E = await import("../src/lib/safety-engine.js");

const DETECT: Record<Cat, (p: any) => boolean> = {
  HF: E.isHF, AF: E.isAF, DM: E.isDiabetic,
  HTN: E.hasHTN, STROKE: E.hasStroke, VASC: E.hasVascularDisease,
};

let tp = 0, fn = 0, fp = 0, tn = 0;
const missed: string[] = [];
const spurious: string[] = [];

console.log("category  recall            precision(vs negatives)");
for (const cat of Object.keys(DETECT) as Cat[]) {
  const det = DETECT[cat];
  let hit = 0;
  for (const text of POSITIVES[cat]) {
    if (det(probe([text]) as any)) hit++;
    else missed.push(`${cat}: "${text}"`);
  }
  let falsePos = 0;
  for (const text of NEGATIVES) {
    if (det(probe([text]) as any)) { falsePos++; spurious.push(`${cat}: "${text}"`); }
  }
  tp += hit; fn += POSITIVES[cat].length - hit;
  fp += falsePos; tn += NEGATIVES.length - falsePos;
  const n = POSITIVES[cat].length;
  console.log(
    `${cat.padEnd(9)} ${String(hit).padStart(2)}/${n}  ${((hit / n) * 100).toFixed(0).padStart(3)}%      ` +
    `${falsePos} false positive(s) out of ${NEGATIVES.length}`
  );
}

const n = tp + fn;
console.log(`\nOVERALL   recall ${tp}/${n} = ${((tp / n) * 100).toFixed(1)}%   ` +
            `false-positive rate ${fp}/${fp + tn} = ${((fp / (fp + tn)) * 100).toFixed(1)}%`);
console.log(`\nMISSED (${missed.length}):`);
missed.forEach((m) => console.log("  " + m));
console.log(`\nSPURIOUS (${spurious.length}):`);
spurious.forEach((m) => console.log("  " + m));
