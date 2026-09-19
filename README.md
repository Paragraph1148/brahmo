# BRAHMO — Clinical Decision Support for Indian Practice

Decision support for **Type 2 Diabetes** and **Cardiovascular Disease**, built around
two commitments: every clinical guideline it cites is Indian (RSSDI, CSI, IHRS, MoHFW
NLEM) rather than American, and **no safety decision depends on model output**.

The second commitment is the load-bearing one. Dosing limits, drug–drug interactions
and contraindications are settled by a deterministic engine before a language model is
consulted at all — and the test harness enforces that mechanically by blocking the
network, rather than asserting it in a paragraph like this one.

---

## What is measured

Everything below is produced by `npm run bench` against a real Postgres instance loaded
from this repository's own `schema.sql` and `seed.sql`. Nothing is hand-counted.

| | before | after |
|---|---|---|
| Tests passing | 21 / 31 | **31 / 31** |
| Condition-detection recall | 43/52 = 82.7 % | **52/52 = 100 %** |
| False-positive rate | 13/120 = 10.8 % | **0/120 = 0 %** |
| Engine ↔ composer disagreement | 6/90 = 6.7 % | **0/90 = 0 %** |
| Drugs with an uncovered eGFR band | 1 / 48 | **0 / 48** |

Also measured on every run: 53 safety flags raised across 9 patients (6 seeded, 3
held-out) with **zero network calls**, and byte-identical output across repeated runs.

"Before" is not a straw man — it is this repository at commit `1957aed`, the code that
was already live. `tests/README.md` has the exact worktree recipe to reproduce it.

**Not measured:** model response quality. That needs a scored rubric over generated
answers. The A/B contrast this project demonstrates is the *context* the two prompts
carry, not the quality of what comes back.

---

## The bug this found

Ten of the thirty-one tests failed on the existing code. All ten traced to a single
root cause: **substring matching over the problem list.**

```
"af"  matched inside  de[af]           →  false positive
"mi"  matched inside  [mi]tral         →  false positive
"ef"  matched inside  r[ef]lux         →  false positive
```

The dangerous failures were the silent ones. Nothing crashed, nothing logged an error,
and every patient page rendered normally:

- **"Newly detected AF"** never registered as atrial fibrillation, so that patient was
  silently never given a CHA₂DS₂-VASc stroke score.
- **"Mitral Stenosis"** was counted as vascular disease, pushing a 45-year-old woman
  past the anticoagulation threshold on a score she should not have had.
- **"no anaphylaxis"** parsed as anaphylaxis.

The fix is word-boundary matching (`/\baf\b/` rather than `text.includes("af")`). It is
a small diff. The point is not the diff — it is that a class of failure that produces no
error signal is invisible to anything except a test that knows the right answer
independently of the code under test.

The labelled corpus used to measure it — 52 positive phrasings across six conditions and
20 negative comorbidities, 72 in total — was **fixed before any detector change**, so
recall and false-positive rate are measured rather than tuned against.

---

## How the safety path is kept honest

`tests/harness/no-network.mts` replaces `fetch`, `http.request`, `https.request` and
`net.connect` with functions that throw. If any safety verdict ever reached for a model,
the suite fails — so "the deterministic layer runs before the LLM" is a property the
tests enforce, not a claim in the docs.

`tests/harness/db.mts` boots **PGlite** (Postgres compiled to WebAssembly) and executes
`supabase/schema.sql` and `supabase/seed.sql` verbatim. The JSONB containment operators
and the `drugs_for_condition` / `guidelines_for_condition` SQL functions are genuinely
exercised rather than reimplemented in TypeScript for the test's convenience. The only
edit to the SQL is dropping `CREATE EXTENSION pgcrypto`, which PGlite does not ship and
which no column in this schema uses.

`src/lib/safety-engine.ts` and `src/lib/prompt-composer.ts` are imported unmodified. The
only substitution is transport: `supabase.from` and `supabase.rpc` normally speak
PostgREST over HTTP; here the equivalent SQL runs in-process.

---

## What the India context actually buys

| A general-purpose assistant says | BRAHMO says |
|---|---|
| "Consider a DPP4 inhibitor" | Teneligliptin (Dynaglipt, Mankind Pharma, ₹84.8 / strip of 10, non-NLEM) |
| "This is affordable" | ₹160/mo retail → ₹40/mo at a Jan Aushadhi Kendra (75 % saving) |
| "Per ADA guidelines" | Per RSSDI 2022 |
| "Apixaban for AF" | Warfarin only — DOACs are **contraindicated** in rheumatic mitral stenosis |
| "Streptokinase or Tenecteplase" | Streptokinase ₹1,920 vs Tenecteplase ₹29,870 — a ₹28k gap, with NLEM status |

That last row is the one clinicians react to. A thrombolytic choice that is a coin-flip
on efficacy grounds is a fifteen-fold cost difference for the patient paying out of
pocket, and a model trained predominantly on US sources has no way to know it.

---

## Architecture — one schema, no code per condition

The structural commitment: **adding a third condition vertical requires data changes,
not code changes.** The safety engine reads `condition_tags` and `renal_dosing` from
JSONB at runtime, so `drugs_for_condition('respiratory')` works the moment the rows
exist. `docs/architecture.md` has the details.

```
src/lib/
  safety-engine.ts      8 deterministic checkers — no model call on this path
  calculators.ts        eGFR (CKD-EPI 2021), CHA₂DS₂-VASc, BMI
  prompt-composer.ts    builds the India-specific prompt from the database
  conditions.ts         shared condition-detection predicates
src/app/api/
  safety-check/         runs the deterministic engine
  compose-prompt/       inspect the composed prompt without an LLM call
  claude/               the model call (Groq Llama 3.3 70B)
supabase/
  schema.sql            5 tables, RLS policies, helper SQL functions
  seed.sql              48 drugs, 30 interactions, 29 guidelines, 6 patients
tests/
  harness/              PGlite, network block, labelled corpus, patient loader
  *.test.mts            31 tests
  bench.mts             every number in this README
```

---

## Quickstart

```bash
npm install
npm test                  # 31 tests — no database or API key needed
npm run bench             # the full measurement harness
npm run audit:detection   # recall / false-positive rate on the labelled corpus
npm run inspect 6 7       # dump the safety report for given patient ids
```

The test suite needs no Supabase project and no API key — PGlite supplies the database
in-process. To run the **application**, you need both:

```bash
cp .env.local.example .env.local   # add Supabase URL + anon key, and GROQ_API_KEY
npm run dev                        # http://localhost:3000
```

Load `supabase/schema.sql` then `supabase/seed.sql` in the Supabase SQL editor, and
verify with `SELECT COUNT(*) FROM drugs;` → 48.

---

## Limitations

- **Pregnancy is not deterministically modelled.** The engine does not catch
  teratogenicity; the model handles it from general knowledge, which is exactly the
  arrangement the rest of this project argues against. Fix is a `pregnancy` condition
  tag — no schema change.
- **Drug prices are baked into the seed**, verified against Tata 1mg at the time of
  writing. Production needs a scheduled refresh.
- **Hospital formulary and stock levels are illustrative**, not a live pharmacy feed.
- **Drug identity is fuzzy name matching.** Reliable EHR integration needs an
  RxNorm-India equivalent.
- **Llama 3.3 70B is the demo model**, chosen for its free tier. The route swap to a
  stronger model is one line.
- **Model output quality is unmeasured.** See "What is measured" above.

---

## Licence

MIT.
