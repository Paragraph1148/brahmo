# BRAHMO — Python core

The deterministic safety engine, ported from `src/lib/*.ts`. The port is
verified against the TypeScript implementation rather than against a reading of
it: `tests/differential/` keeps a live `tsx` process open and runs every fuzzed
input through both, so a rule that was ported wrong fails here.

```bash
uv sync --extra dev
uv run pytest                                            # 211 tests
uv run uvicorn --factory brahmo.api:create_app --reload  # http://127.0.0.1:8000
```

Interactive API docs at `/docs`. The service needs no database and no API key:
the corpus loads from `tests/fixtures/`, exported from `schema.sql` + `seed.sql`
by `npm run fixtures` at the repository root.

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

### One report called the same patient's AF both valvular and non-valvular

`safety-engine.ts` asks "is this valvular?" three times with three different
keyword lists — three keywords at lines 458 and 470, five at line 558. A
patient charted as plain "Mitral Stenosis" satisfies the long list and not the
short one, so a single report carries both verdicts. Against the live engine:

```
conditions=["Mitral Stenosis", "Atrial Fibrillation"]
  flag:    Valvular AF → Anticoagulation INDICATED regardless of CHA₂DS₂-VASc
  flag:    Non-valvular AF: DOAC preferred over Warfarin
  classes: ["DOAC"]
```

Rheumatic mitral stenosis is routinely charted without the word "rheumatic",
and a DOAC in rheumatic MS is the exact error this project was built to
prevent — it is the headline row of the README's own comparison table. Seeded
patient #7 escapes only because their problem list also carries "RHD".

`conditions.py` has one definition and one call site. It also splits two
questions the original conflated: `is_valvular_for_retrieval` is liberal and
pulls the valve guidelines, while `doac_contraindicated` is narrow — mitral
stenosis and mechanical prostheses, the two lesions that actually make a DOAC
unsafe. Isolated aortic stenosis is valve disease but not a DOAC
contraindication, and sending such a patient to warfarin means lifelong INR
monitoring they do not need.

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

### The drug list's order depended on the server's locale

Both list sections re-sort client-side with `String.prototype.localeCompare`
and no locale argument, which resolves against whatever locale the host is in.
Locale collation is case-insensitive at the primary level and code-point order
is not, so the section breaks already fall in different places:

```
localeCompare:  ### Alpha-glucosidase inhibitor   then   ### ARB
code points:    ### ARB                           then   ### Alpha-glucosidase
```

Neither order is wrong, but the prompt handed to the model should not depend on
where the server runs. `retrieval.collate` fixes an explicit key: case-folded
first so the reading order is the natural one, then the exact string to break
the ties case-folding creates, then the id so the ordering is total.

## The composer

`composer.py` reproduces the TypeScript prompt exactly. Every section except
the safety block matches byte for byte across all nine patients, as do the
condition tags, guideline and drug counts, active sources, and the generic
contrast arm. The safety block differs only because it renders this port's
report, which raises flags the original does not.

The response-instruction block is held as data in `data/response_instructions.md`
and was extracted verbatim from the TypeScript rather than retyped, so the two
cannot drift apart silently. Nothing reads it; it is prose for the model.

One addition: a medication the engine could not check now appears in the prompt
under its own heading. A prompt that presents a safety review without saying it
skipped a drug the patient is taking is worse than one that says nothing.

## The service

`brahmo.api` exposes the deterministic layer over HTTP. Route names match the
Next.js API it replaces, so the existing frontend needs a base URL change and
nothing else.

| route | what it does |
|---|---|
| `GET /health` | status, corpus row counts, configured model |
| `GET /patients` · `GET /patients/{id}` | the seeded patients |
| `POST /safety-check` | the deterministic verdict — no model, no network |
| `POST /compose-prompt` | the prompt a model *would* get, without sending it |
| `POST /consult` | safety first, then the model |

Two properties are structural rather than documented.

**The safety path cannot reach a model.** `/safety-check` and `/compose-prompt`
import nothing from `brahmo.model`. `tests/api/test_no_network.py` severs
`socket.connect`, `create_connection`, `getaddrinfo` and
`SSLContext.wrap_socket` for the whole process, drives every deterministic
route through including all six seeded patients, and checks that the guard
itself bites — a test that cannot fail proves nothing. This catches what the
library-level harness cannot: a route handler enriching a response with a model
call before returning it, leaving the engine untouched and the guarantee
quietly false.

**The model cannot change the clinical content.** `/consult` settles the report
and composes the prompt before the model is touched. With none configured it
still returns the verdict and the prompts, with `answers.error` saying why
nothing was generated — and a test asserts the report is byte-identical whether
or not a model answered.

`PatientRef` takes either `patient_id` or an inline `patient`, and rejects both
or neither with a 422. Accepting both and silently preferring one is how a
caller ends up reading a report for a patient they did not send.

Every response carries `Server-Timing`. That is the seam the roadmap's query
telemetry hangs off: one place that already knows the route and the wall-clock
cost, so shipping those to a time-series store is a sink swap rather than a
refactor.

## Retrieval evaluation

`brahmo.ir` measures what the prompt's guideline selection actually retrieves.

```bash
uv run python -m brahmo.ir.harness
uv run python -m brahmo.ir.harness --k 5 --per-query
```

### The problem, measured

Guideline selection is `condition_tags ? tag` — a boolean test against the
patient's conditions. It never reads the clinician's question, so every
question about a given patient retrieves the same set. And because the tags are
derived generously, a multi-condition patient matches most of the corpus:

| patient | tags | guidelines | drugs |
|---|---|---|---|
| Failing Metformin | diabetes, cardiovascular | 29/29 (100%) | 48/48 (100%) |
| Complex with CKD | + ckd, complications | 29/29 (100%) | 48/48 (100%) |
| Auto-Driver | diabetes, nafld | 17/29 (59%) | 22/48 (46%) |
| Acute STEMI | cardiovascular | 14/29 (48%) | 31/48 (65%) |
| Post-MI + New AF | + atrial_fibrillation | 29/29 (100%) | 48/48 (100%) |
| Diabetes + Heart Failure | + heart_failure, ckd | 29/29 (100%) | 48/48 (100%) |

Four of six get the entire corpus. That is not retrieval; it is sending
everything and letting the model sort it out.

### Results — k = 10, guideline corpus (29 documents), 6 judged queries

**Provisional.** The judgments have not been reviewed by a clinician.

| retriever | recall | nDCG | MRR | precision | avg returned |
|---|---|---|---|---|---|
| tag, untruncated *(ships today)* | **1.000** [0.610, 1.000] | 0.531 | — | 0.224 | 24.5 |
| tag @10 | 0.332 | 0.275 | 0.302 | 0.250 | 10.0 |
| bm25 | 0.650 | 0.618 | 0.889 | 0.417 | 9.0 |
| bm25 within tags | 0.650 | **0.628** | **0.917** | 0.417 | 8.5 |
| hybrid (tag + bm25, RRF) | 0.687 | 0.495 | 0.408 | 0.450 | 10.0 |

Three things this says.

**The shipped system buys perfect recall with precision of 0.224.** It finds
every relevant guideline by sending 24.5 of 29. The ranked retrievers reach
about two thirds of the relevant set while sending a third as much, and put the
first relevant document at rank ~1.1 (MRR 0.917).

**Fusing an unranked retriever hurts.** The hybrid has the best recall and the
second-worst MRR. Tag containment is boolean, so its "ranking" is document-id
order, and reciprocal rank fusion treats that arbitrary order as signal. An
unranked retriever belongs in a filter, not a fusion — which is what
`bm25 within tags` is, and it scores best on both ranking metrics.

**Six queries cannot separate any of these.** Every interval overlaps the
baseline's. The harness says so on every run rather than leaving the reader to
notice.

### Reranking

```bash
uv run --extra rerank python -m brahmo.ir.rerank_cache   # once, fills the cache
uv run python -m brahmo.ir.harness                        # runs from cache, no torch
```

A cross-encoder (`ms-marco-MiniLM-L-6-v2`) reads the query and document
together, so it can match a question about rheumatic mitral stenosis to a
recommendation that never uses the word "rheumatic". All 174 judged pairs are
cached in `ir/data/rerank_scores.json`, so the numbers reproduce for someone
with neither torch nor a GPU — the test suite runs entirely from it.

| retriever | recall | nDCG | MRR | precision |
|---|---|---|---|---|
| tag @10 | 0.332 | 0.275 | 0.302 | 0.250 |
| bm25 within tags | 0.650 | 0.628 | **0.917** | 0.417 |
| **rerank(tag)** | **0.792** | **0.665** | 0.867 | **0.517** |
| rerank(bm25 within tags) | 0.683 | 0.604 | 0.867 | 0.433 |

**Reranking helps where there was no ranking, and not otherwise.** On the tag
set — unranked by construction — it lifts nDCG by 0.390 and more than doubles
recall@10. On BM25, which already ranks well, it makes things slightly *worse*
(nDCG 0.628 → 0.604). A general-purpose MS MARCO reranker has nothing to add
to lexical matching that already works on a corpus this small and this
term-dense; it only has something to add where no ordering existed.

That is the argument for a domain-tuned reranker rather than against reranking.
See the next section for why that is not done here.

**BM25 has a recall ceiling the reranker does not.** Sweeping the cutoff:

| k | rerank(tag) recall | bm25-in-tags recall |
|---|---|---|
| 10 | 0.792 | 0.650 |
| 15 | 0.891 | 0.683 |
| 20 | 0.972 | 0.683 |
| 29 | 1.000 | **0.683 — plateau** |

BM25 cannot reach the last third at any cutoff: those guidelines share no terms
with the question. The cross-encoder reaches all of them.

**The deployable change.** Reranking the tag set and cutting at 15 keeps 89% of
the relevant guidelines while sending 15 documents instead of 24.5 — a 39%
smaller guideline payload. It cannot surface anything the current system would
have withheld, because it only ranks and trims what tags already admit.

`--depth` caps all of this: nothing outside the first stage's top *depth* can be
recovered, so recall is inherited. Raising it from 25 to 40 moved rerank(tag)
recall@10 from 0.701 to 0.792 — worth knowing before reading any of these
numbers as a property of the reranker rather than of the pipeline.

### Why there is no fine-tuned reranker here

The plan for this phase was to mine hard negatives from the retrieval failures
and LoRA-fine-tune the cross-encoder on them. That is not defensible at this
data scale, and doing it anyway would produce a number that means nothing.

The arithmetic: 6 queries × 29 documents is 174 query-document pairs, 39 of them
positive. Reranker fine-tuning normally uses five or six orders of magnitude
more. Worse, there is no held-out split worth the name — partitioning 6 queries
gives 4 to train and 2 to test, and a "lift" measured that way is a measurement
of memorisation.

What would make it viable is more judged queries, not more model. Roughly 50
would support a held-out half for evaluation; training a reranker needs
hundreds. Expanding the judged set is the prerequisite, and it is a labelling
job, not a modelling one.

### Expanding the judged set

44 more questions are drafted in `ir/data/questions_draft.json`, awaiting
grades. With the existing 6 that is 50 — roughly what a held-out half needs to
be worth reporting.

They carry **no grades**. Adding them would repeat the existing set's problem —
one non-clinician's reading standing in for a clinical one — at seven times the
scale.

Each names the retrieval failure it is built to expose, because a set made only
of questions whose words appear in their answer measures lexical overlap and
nothing else:

| probes | n | what it catches |
|---|---|---|
| lexical | 18 | the easy case, for contrast |
| vocabulary-gap | 7 | the answer uses different words than the question |
| negative | 7 | nothing in the corpus answers it |
| cost | 5 | affordability, often with no clinical vocabulary at all |
| multi-hop | 4 | needs two guidelines combined |
| distractor | 3 | an obvious keyword points at the wrong guideline |

The negative controls matter most. Without them, no metric can see a retriever
that answers confidently when it should return nothing — and the pool for
*"which of her drugs are teratogenic"* leads with **Diabetes + HF — drugs to
AVOID**, which is exactly that failure.

They also cover patients 7–9, which the judged set omitted entirely.

#### Two tiers, and who can set each

A relevance judgment here is two questions wearing one label, and only one of
them needs a clinician.

| grade | the question | who can answer it |
|---|---|---|
| **1 — answers it** | Does this text contain information that directly addresses what was asked? | Anyone reading carefully |
| **2 — essential** | Would omitting it leave the answer *wrong or unsafe*? | A clinician |

Recall, precision and MRR only ask whether a document is relevant at all, so
they rest entirely on tier 1 and stop being provisional the moment the reading
pass is done. nDCG weights by grade, so it rests on tier 2 and stays
provisional until a clinician has been through it. `JudgmentSet.caveat` prints
which of the two any given run depends on, and the harness prints it above
every table.

A tier-2 grade set by a non-clinician is an upgrade *proposed*, not confirmed,
and both the file and the export say so. This is not a formality: getting it
wrong in the safe-looking direction — marking something essential that is not —
inflates nDCG for whichever retriever happens to rank it highly.

#### Labelling

```bash
uv run python -m brahmo.ir.labeller -o ../docs/label.html   # then open it
uv run python -m brahmo.ir.worksheet -o ../docs/judgment-worksheet.md
uv run python -m brahmo.ir.worksheet --json -o ../docs/judgment-skeleton.json
```

Two pages, same pooled set, differing only in where the grades live.

`brahmo.ir.online` publishes an Artifact whose grades go to its shared
database, so the pass can be done on a phone in spare moments and read back
here with `ArtifactData` to commit. It writes one document per question,
`grades/<question-id>`, flushed after a pause rather than on every tap — 631
writes would be a burst the store is right to throttle, and 44 documents on a
lull is the same information at a hundredth of the traffic. The store wins over
local state where the two disagree, so a stale phone cannot undo a laptop.

`brahmo.ir.labeller` writes `docs/label.html`, which keeps everything in the
browser and exports JSON. No server, no network, nothing uploaded. Use it to
work offline, or if the data should not leave the machine.

Either way it is one question and one candidate at a time, graded `y` / `n` /
`e`, resumable, about an hour for 631. The markdown worksheet is the same
content for anyone who would rather read on paper.

Judging 44 questions against 29 guidelines is 1,276 decisions. Pooling — taking
the union of each retriever's top 8 — cuts it to **631**, averaging 14 candidates
per question. This is how TREC collections are built.

Pooling's bias is that a document no retriever surfaced is never judged, so
recall against the finished set is optimistic. Two things limit it here: the
corpus is 29 documents, and the pool includes the cross-encoder, so a guideline
answering a question in words it never uses still reaches the reviewer.
`test_the_vocabulary_gap_answer_reaches_the_pool` pins that on the case where it
matters — the penicillin-allergy guideline for patient 4. The worksheet prints
each pool's coverage so a reader can judge the bias themselves.

### Keeping the evaluation honest

`ir/data/judgments.json` holds 39 relevance judgments across 6 queries, graded
essential / useful, each with a written rationale. They were made by reading
each guideline against each question — **not** derived from `condition_tags`,
because grading tag retrieval by tag overlap would hand the baseline a perfect
score while measuring nothing. `test_the_judgments_are_not_a_restatement_of_the_tags`
asserts that the baseline's precision stays below 0.5, which is evidence the
labels carry information the tags do not.

Labels are fixed before a retriever is scored, the same rule
`tests/harness/phrasings.mts` follows. A judgment that turns out to be wrong
gets changed in a commit that says so, never quietly.

Scoped to guidelines. Judging all 48 drug entries per question is a separate
labelling pass, and mixing unjudged documents into the store would charge every
retriever for returning them.

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
- **Prices keep their text and gain a parsed amount.** `mrp_price` is
  `TEXT NOT NULL` holding a rendered string — `₹84.8/strip of 10 (20mg)` —
  with amount, pack size and strength in one field. The raw text is kept for
  display, and `mrp_amount` parses the rupee figure out beside it as a
  `Decimal` for anything that computes with it. An unparseable price is `None`
  rather than zero, so a missing amount is visible instead of looking free.
- **`drug_id is None`, not falsy.** `!!id` and `!m.drug_id` also discard id 0.
  Nothing is lost against a Postgres serial; a formulary loaded from anywhere
  else would lose a drug silently.
