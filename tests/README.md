# BRAHMO test + measurement harness

Every number quoted about this project is produced by the code in this
directory. Nothing here is hand-counted.

```bash
npm install
npm test              # 31 tests — calculators + safety engine
npm run bench         # the measurement harness (all numbers below)
npm run audit:detection   # condition-detection recall / false-positive rate
npm run audit:tags        # agreement between the engine and the composer
npm run inspect 6 7       # dump the safety report for given patient ids
```

## How it runs

`tests/harness/db.mts` boots **PGlite** — Postgres compiled to WASM — and
executes this repository's own `supabase/schema.sql` and `supabase/seed.sql`
verbatim, so the JSONB containment operators and the
`guidelines_for_condition` / `drugs_for_condition` SQL functions are really
exercised rather than reimplemented in the test.

`src/lib/safety-engine.ts` and `src/lib/prompt-composer.ts` are imported
unmodified. The only substitution is transport: `supabase.from` and
`supabase.rpc` normally speak PostgREST over HTTP; here they run the
equivalent SQL in-process.

Two things are deliberately faithful rather than convenient:

- **The network is hard-blocked.** `tests/harness/no-network.mts` replaces
  `fetch`, `http.request`, `https.request` and `net.connect` with functions
  that throw. The claim that the safety verdict is reached before any model
  is consulted is therefore checked mechanically, not asserted.
- **The only edit to the SQL** is dropping `CREATE EXTENSION pgcrypto`,
  which PGlite does not ship and which no column in this schema uses.

## What is and is not measured

Measured: the deterministic layer — calculators, safety flags, condition
detection, retrieval selection, prompt composition, latency, determinism.

**Not** measured: model response quality. That needs a `GROQ_API_KEY` and a
scored rubric over generated answers; the A/B contrast reported here is the
*context* the two prompts carry, not the answers they produce.

## The corpus

`tests/harness/phrasings.mts` holds a labelled corpus of problem-list
phrasings — 52 positives across six conditions, 20 negative comorbidities.
It was fixed **before** any detector change, so recall and false-positive
rate are measured rather than tuned.

## Reproducing the before/after

The baseline figures come from running this same harness against the
pre-fix commit:

```bash
git worktree add /tmp/baseline 1957aed
ln -s "$PWD/node_modules" /tmp/baseline/node_modules
cp -r tests /tmp/baseline/
# add `export` to the predicates in the baseline's safety-engine.ts and to
# deriveConditionTags in its prompt-composer.ts — no logic change — then:
cd /tmp/baseline && npx tsx --test tests/*.test.mts && npx tsx tests/bench.mts
```

| | before | after |
|---|---|---|
| tests passing | 21 / 31 | 31 / 31 |
| condition-detection recall | 43/52 = 82.7% | 52/52 = 100% |
| false-positive rate | 13/120 = 10.8% | 0/120 = 0% |
| engine ↔ composer disagreement | 6/90 = 6.7% | 0/90 = 0% |
| drugs with an uncovered eGFR band | 1 / 48 | 0 / 48 |
