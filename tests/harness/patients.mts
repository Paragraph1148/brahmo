// =================================================================
// The full patient set under test:
//   #1-#6  the seeded demo patients, read from the database
//   #7-#9  the held-out "surprise" patients, read from their JSON
// Questions #1-#6 are the canonical Question Set A #1 from
// outputs/patient-questions.md; #7-#9 ship with their own question.
// =================================================================
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { bootstrapDb } from "./db.mjs";
import type { Patient } from "../../src/lib/types.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

export interface Case {
  patient: Patient;
  question: string;
  origin: "seed" | "surprise";
}

const SEED_QUESTIONS: Record<number, string> = {
  1: "HbA1c is 8.4% on Metformin 2g/day. What second-line agent should I add given his ₹5K/month insurance cap?",
  2: "HbA1c is 9.2% on Metformin + Glimepiride, eGFR is 38. How should I transition this patient to insulin safely?",
  3: "Newly diagnosed T2DM. He's an auto-driver, no insurance, daily wage ₹800. What regimen?",
  4: "STEMI just walked in — chest pain 2 hrs, anterior ST elevation. What's the immediate protocol?",
  5: "Post-MI on DAPT, now new AF. CHA₂DS₂-VASc is 3 (male threshold = ≥2). How do I manage triple therapy?",
  6: "HbA1c is 8.6% with HFrEF (EF 30%) and CKD 3a. How do I optimize her diabetes regimen given her cardiac status?",
};

export async function loadPatients(): Promise<Case[]> {
  const pg = await bootstrapDb();
  const res = await pg.query<Patient>("SELECT * FROM patients ORDER BY id");
  const cases: Case[] = res.rows.map((p) => ({
    patient: { ...p, bmi: Number(p.bmi) },
    question: SEED_QUESTIONS[p.id],
    origin: "seed" as const,
  }));

  const dir = join(ROOT, "outputs", "surprise-patients");
  for (const f of readdirSync(dir).filter((f) => f.endsWith(".json")).sort()) {
    const raw = JSON.parse(readFileSync(join(dir, f), "utf8"));
    cases.push({ patient: raw.patient as Patient, question: raw.question, origin: "surprise" });
  }
  return cases;
}
