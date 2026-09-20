# BRAHMO — Python core

The deterministic safety engine, ported from `src/lib/*.ts`. The port is
verified against the TypeScript implementation rather than against a reading of
it: `tests/differential/` keeps a live `tsx` process open and runs every fuzzed
input through both, so a rule that was ported wrong fails here.

```bash
uv sync --extra dev
uv run pytest            # 68 tests
```

The TypeScript side must be installed (`npm install` at the repo root); the
differential tests skip with a message if it is not.

## How the oracle works

`npm run golden` freezes the TypeScript engine's full `SafetyReport` for all
nine patients into `tests/golden/*.json`, with sorted keys so the files are
diffable. `npm run golden -- check` fails if the TypeScript engine drifts from
what was recorded. The Python port is then held to those same reports.

For the pure functions, `tests/bridge.mts` exposes the TypeScript calculators
over line-delimited JSON on stdin/stdout. One process serves a whole Hypothesis
run, so fuzzing against the real implementation costs about 2 ms per example
instead of a process spawn.

## What the differential found

Random inputs never land on a rounding boundary, so the first version of these
tests could not fail: mutating `js_round` to Python's banker's rounding left the
suite green. `creatinine_on_rounding_boundary` fixes that by inverting CKD-EPI
to solve for the creatinine that yields a target `x.5` eGFR.

With boundaries reachable, the suite immediately found a disagreement that is
not a porting mistake. `Math.pow` is not correctly rounded in either language,
and V8 and CPython differ by one ulp:

```
Math.pow(2.332552743738428, -1.2)
  V8       0.36191137440250265023
  CPython  0.36191137440250259472
```

Propagated through the formula, one fuzzed patient's raw eGFR is exactly
`46.5` in JavaScript and `46.49999999999999` in Python — 47 against 46.

That one is harmless, since both sit inside CKD 3a. The reason it matters is
what it reveals about the original design: it rounds eGFR to an integer and
then compares the *rounded* value against KDIGO band thresholds. At a true eGFR
of 44.5 that reports CKD 3a instead of CKD 3b, and the renal dosing band that
follows changes with it. The same holds at every threshold:

| true eGFR | band from exact value | band after rounding |
|---|---|---|
| 89.5 | G2 | Normal (G1) |
| 59.5 | CKD 3a | G2 |
| 44.5 | CKD 3b | CKD 3a |
| 29.5 | CKD 4 | CKD 3b |
| 14.5 | CKD 5 | CKD 4 |

In each row rounding reports a healthier kidney than the patient has.

So the Python core splits the two: `egfr_exact` returns the unrounded value and
is what every band comparison reads, while `calculate_egfr` rounds for display
and for parity with the original. `test_rounding_before_banding_moves_the_clinical_stage`
pins the table above, and
`test_exact_egfr_bands_are_stable_under_one_ulp_of_creatinine` asserts the
property the rounded path cannot offer.

## What the divergence suite found

`tests/divergence/` holds the places this port deliberately disagrees with the
TypeScript engine. Each test asserts both sides: what TypeScript does today,
read live over the bridge, and what this port does instead. If the original is
ever fixed, the test fails and says to retire it.

### Reaction severity was read across allergy entries

`hasAllergy(patient, "anaphylaxis", ...)` searches the entire allergy list
joined into one string. So the severity of *one* substance's reaction is
decided by whatever word appears anywhere in the list. Against the live engine:

```
["Aspirin (mild rash, no anaphylaxis)"]
  -> aspirin flag: warning                         correct
["Penicillin (anaphylaxis)", "Aspirin (mild rash, no anaphylaxis)"]
  -> aspirin flag: critical, "DO NOT give aspirin" wrong
```

The aspirin entry says "no anaphylaxis" in as many words and is overruled by
the penicillin line. In a STEMI pathway that withholds aspirin from a patient
who can safely take it — a harm, not a conservative default. It is the same
cross-attribution family as the substring bug the project already fixed: a
property belonging to one record applied to another.

`domain/allergy.py` parses each line into a substance and its own reaction, and
severity is only ever read from the entry that matched. The property is pinned
directly: dropping every non-aspirin entry must not change the aspirin verdict.

### A patient on one drug got no interaction check at all

`checkInteractions` opens with `if (drugIds.length < 2) return []`. The guard
reads as common sense — an interaction needs two drugs — but the table holds
interactions whose other side is a non-formulary substance with a null id:
alcohol, IV contrast, steroids. Those need exactly one patient drug, and the
early return discards every one of them. Against the live engine:

```
meds=[Metformin]                 -> 0 interaction flags
meds=[Metformin, Atorvastatin]   -> 4, three of them Metformin's own:
                                    IV contrast (severe), alcohol, steroids
```

The same prescription is checked or not depending on what sits beside it.
Metformin with IV contrast is a hold-before-imaging contraindication, and
seeded patient #3 — an auto-driver on metformin alone, no insurance — comes
back with an empty report on all three. That is the whole golden report for
that patient: zero flags.

### The sulfonylurea renal flag cited one threshold and used another

It fires a single `critical` "STOP" at any eGFR below 60, in a flag whose own
detail text reads *"RSSDI 2022: STOP sulfonylurea when eGFR <30"*. A patient at
eGFR 44 is told to stop a drug by a citation that says to continue it. RSSDI
grades the response — reduce and monitor between 30 and 60, stop below 30 — and
this port follows the guideline it cites. The same block also applied
sulfonylurea-specific wording to any drug with moderate or high hypoglycemia
risk, so the advice could name a class the patient was not on.

### An unidentified medication was checked for nothing

Every checker begins `if (!m.drug_id) continue`. A drug the resolver cannot
match produces no renal flag, no heart-failure flag and no interaction — and
the report comes back clean because nothing was looked at. Seeded patients 2
and 7 each carry one (`Pregabalin`, `Penicillin V`). Resolution failure is now
a flag in its own right.

Related: resolution fell back to the first prefix match while iterating rows
from `select * from drugs`, a query with no `ORDER BY`. The seed holds three
insulins, so a medication written as plain `Insulin` matched whichever row came
back first. The determinism test passes because Postgres returns seed rows in a
stable physical order — luck, not a guarantee. A prefix match now resolves only
when it is unique, and ambiguity is reported.

### "No known drug allergies" parsed as an allergy to drugs

Found by a unit test written against the new parser, and present in the
TypeScript too. The negation guard only looks immediately before the keyword,
and in `No known drug allergies` the negation is four words away from `drug`.
The commonest value in the field read as a positive finding. `AllergyList` now
recognises the no-allergy sentinels (`NKDA`, `NKA`, `none`, `nil`, `no known
drug allergies`, `denies allergies`) and carries no entry for them.

## Design changes from the TypeScript

- **eGFR is not rounded before banding.** Above.
- **Lab values carry units.** `domain/quantity.py` — a creatinine of 88 is
  normal in umol/L and catastrophic in mg/dL, and a bare `float` cannot tell
  them apart. Comparing across dimensions raises instead of returning a number.
- **`js_round` is explicit.** Python's `round` is banker's rounding, so a
  transcribed `Math.round` silently disagrees on every half. Pinned by test.
- **Allergies are records, not strings.** A substance and its own reaction, so
  severity cannot cross entries. Above.
- **Every flag carries provenance.** Which rule fired, which patient fields it
  read, which guideline it rests on. Without that, "check the retrieval layer
  never contradicts a deterministic flag" cannot be implemented: there is no
  stated basis to check against.
- **Prices are `Decimal`.** The TypeScript carries `mrp_price` as a string and
  parses it with `Number` at the point of display. Binary floating point cannot
  represent most rupee amounts exactly, in a system whose argument is cost.
- **`drug_id is None`, not falsy.** `!!id` and `!m.drug_id` also discard id 0.
  Nothing is lost against a Postgres serial; a formulary loaded from anywhere
  else would lose a drug silently.
