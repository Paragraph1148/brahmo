"""Build a labelling worksheet for the drafted questions.

    uv run python -m brahmo.ir.worksheet            # markdown, for reading
    uv run python -m brahmo.ir.worksheet --json     # skeleton, for pasting back

Judging 44 questions against 29 guidelines is 1,276 decisions. Pooling cuts
that to the documents some retriever actually surfaced, which is how TREC
collections are built.

The bias pooling carries is that a document no retriever found is never judged,
so recall against the finished set is optimistic. Two things limit it here: the
corpus is 29 documents, and the pool includes the cross-encoder, so a guideline
that answers a question in words the question never uses still reaches the
reviewer. The worksheet prints what fraction of the corpus each pool covers so
the reader can judge for themselves.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from brahmo.conditions import derive_condition_tags
from brahmo.corpus import load_default
from brahmo.ir.drafts import DraftQuestion, DraftSet
from brahmo.ir.harness import Campaign
from brahmo.ir.retrievers import Query


@dataclass(frozen=True, slots=True)
class Pool:
    question: DraftQuestion
    candidates: tuple[str, ...]
    found_by: dict[str, tuple[str, ...]]


def build_pools(depth: int = 8) -> tuple[Pool, ...]:
    campaign = Campaign.build()
    corpus = load_default()
    drafts = DraftSet.load()

    retrievers = list(campaign.reranked(depth=40, allow_compute=False))
    from brahmo.ir.retrievers import build_all

    retrievers += list(build_all(campaign.store))

    pools: list[Pool] = []
    for draft in drafts.questions:
        patient = corpus.patient(draft.patient_id) if draft.patient_id else None
        tags = tuple(derive_condition_tags(patient)) if patient else ()
        query = Query(id=draft.id, text=draft.question, tags=tags, patient_id=draft.patient_id)

        found_by: dict[str, list[str]] = {}
        for retriever in retrievers:
            for hit in retriever.search(query, depth):
                found_by.setdefault(hit.doc_id, []).append(retriever.name)

        # Ordered by how many retrievers agreed, then id: the ones every
        # retriever found are the easy calls, and putting them first means a
        # reviewer warms up before reaching the contested ones.
        ordered = sorted(found_by, key=lambda d: (-len(found_by[d]), d))
        pools.append(
            Pool(
                question=draft,
                candidates=tuple(ordered),
                found_by={d: tuple(v) for d, v in found_by.items()},
            )
        )
    return tuple(pools)


def markdown(pools: tuple[Pool, ...]) -> str:
    campaign = Campaign.build()
    store = campaign.store
    total = len(store)
    sizes = [len(p.candidates) for p in pools]

    out = [
        "# Relevance judgment worksheet",
        "",
        f"{len(pools)} drafted questions · {total} guidelines · "
        f"pools average {sum(sizes) / len(sizes):.1f} candidates "
        f"({100 * sum(sizes) / (len(sizes) * total):.0f}% of the corpus)",
        "",
        "## How to fill this in",
        "",
        "Replace each `_` with a grade:",
        "",
        "- **2 — essential.** Omitting it would leave the answer wrong or unsafe.",
        "- **1 — useful.** Real supporting context; its absence weakens the answer.",
        "- **0 — irrelevant.** Leave as is, or write 0.",
        "",
        "Judge the question as a clinician seeing *this patient*, not the topic in",
        "the abstract. The same guideline can be essential for one patient and",
        "irrelevant for another.",
        "",
        "Questions marked `probes: negative` are expected to have **no** relevant",
        "document. If you find one, that is a finding — say so, it means the",
        "corpus covers more than we thought.",
        "",
        "A pool is not the whole corpus. If you know of a guideline that belongs",
        "and is not listed, add it by id — that is exactly the pooling bias this",
        "worksheet cannot fix by itself.",
        "",
        "---",
        "",
    ]

    for pool in pools:
        q = pool.question
        out += [
            f"### `{q.id}`",
            "",
            f"**Patient {q.patient_id}** · probes: *{q.probes}* · "
            f"{len(pool.candidates)}/{total} pooled",
            "",
            f"> {q.question}",
            "",
            "| grade | id | source | guideline |",
            "|:---:|---|---|---|",
        ]
        for doc_id in pool.candidates:
            doc = store.get(doc_id)
            if doc is None:
                continue
            source = f"{doc.source} {doc.year}" if doc.source else "—"
            body = doc.text.replace("|", "\\|")
            body = body if len(body) <= 210 else body[:207] + "..."
            out.append(f"| `_` | {doc_id} | {source} | **{doc.title}** — {body} |")
        out += ["", ""]

    return "\n".join(out)


def skeleton(pools: tuple[Pool, ...]) -> str:
    """A judgments-file skeleton with every pooled grade set to 0."""
    return json.dumps(
        {
            "schema": 1,
            "corpus": "guidelines",
            "reviewed": False,
            "about": [
                "Generated skeleton — fill in the grades, then merge into",
                "judgments.json. Every pooled candidate starts at 0; raise the",
                "ones that matter to 1 or 2. Grades of 0 are dropped on load.",
            ],
            "queries": [
                {
                    "id": p.question.id,
                    "patient_id": p.question.patient_id,
                    "question": p.question.question,
                    "probes": p.question.probes,
                    "rationale": "",
                    "judgments": {doc_id: 0 for doc_id in p.candidates},
                }
                for p in pools
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth", type=int, default=8, help="top-N per retriever in the pool")
    parser.add_argument("--json", action="store_true", help="emit the skeleton instead")
    parser.add_argument("-o", "--out", help="write to a file instead of stdout")
    args = parser.parse_args()

    pools = build_pools(args.depth)
    text = skeleton(pools) if args.json else markdown(pools)

    if args.out:
        from pathlib import Path

        Path(args.out).write_text(text + "\n", encoding="utf-8")
        sizes = [len(p.candidates) for p in pools]
        print(f"wrote {args.out}")
        print(f"  {len(pools)} questions, {sum(sizes)} pooled pairs to judge")
        print(f"  (vs {len(pools) * len(Campaign.build().store)} without pooling)")
    else:
        print(text)


if __name__ == "__main__":
    main()
