// =================================================================
// Line-delimited JSON bridge to the TypeScript implementation.
//
// The Python port is verified against this process. One request per line on
// stdin, one response per line on stdout, so the Python side can keep a single
// node process alive for a whole Hypothesis run instead of paying process
// startup per example.
//
//   {"fn":"calculateEGFR","args":[1.2,55,"M"]}  ->  {"ok":true,"value":62}
// =================================================================
import { createInterface } from "node:readline";
import "./harness/env.mjs";
import { installShim } from "./harness/db.mjs";
import * as calc from "../src/lib/calculators.js";

// The safety engine talks to the database, so the PGlite shim has to be in
// place before it is imported. Calculators are pure and need none of this.
await installShim();
const engine = await import("../src/lib/safety-engine.js");
const composer = await import("../src/lib/prompt-composer.js");

type Handler = (args: unknown[]) => unknown;

const FNS: Record<string, Handler> = {
  calculateEGFR: ([cr, age, sex]) =>
    calc.calculateEGFR(cr as number, age as number, sex as "M" | "F" | "Other"),
  ckdStage: ([e]) => calc.ckdStage(e as number | null),
  egfrBucket: ([e]) => calc.egfrBucket(e as number | null),
  getRenalDoseInstruction: ([rd, e]) =>
    calc.getRenalDoseInstruction(rd as Record<string, string>, e as number | null),
  calculateChadsVasc: ([i]) => calc.calculateChadsVasc(i as calc.ChadsVascInputs),
  shouldAnticoagulate: ([s, sex]) =>
    calc.shouldAnticoagulate(s as number, sex as "M" | "F" | "Other"),
  bmiCategory: ([b]) => calc.bmiCategory(b as number),
};

// Async handlers are kept separate: the safety engine hits the database.
const ASYNC_FNS: Record<string, (args: unknown[]) => Promise<unknown>> = {
  runSafetyChecks: async ([patient]) => engine.runSafetyChecks(patient as never),
  composePrompt: async ([patient, question]) => {
    const report = await engine.runSafetyChecks(patient as never);
    return composer.composePrompt(patient as never, report, question as string);
  },
  deriveConditionTags: async ([patient]) => {
    const { deriveConditionTags } = await import("../src/lib/conditions.js");
    return deriveConditionTags(patient as never);
  },
};

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  if (!line.trim()) continue;
  let out: unknown;
  try {
    const { fn, args } = JSON.parse(line) as { fn: string; args: unknown[] };
    const asyncHandler = ASYNC_FNS[fn];
    const handler = FNS[fn];
    if (!asyncHandler && !handler) throw new Error(`unknown fn: ${fn}`);
    const value = asyncHandler ? await asyncHandler(args) : handler(args);
    // JSON has no -0; normalise so it cannot masquerade as a difference.
    out = { ok: true, value: Object.is(value, -0) ? 0 : value };
  } catch (e) {
    out = { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
  process.stdout.write(JSON.stringify(out) + "\n");
}
