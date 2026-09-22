"""Run every retriever over the judged queries and report the comparison.

    uv run python -m brahmo.ir.harness
    uv run python -m brahmo.ir.harness --k 5 --per-query
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from brahmo.conditions import derive_condition_tags
from brahmo.corpus import Corpus, load_default
from brahmo.ir.documents import DocumentStore
from brahmo.ir.judgments import JudgmentSet
from brahmo.ir.metrics import Evaluation, evaluate
from brahmo.ir.reranker import ScoresUnavailable, build_reranked
from brahmo.ir.retrievers import (
    BM25Retriever,
    Query,
    Retriever,
    TagFilteredBM25,
    TagRetriever,
    build_all,
)


@dataclass(frozen=True, slots=True)
class Campaign:
    store: DocumentStore
    judgments: JudgmentSet
    queries: tuple[Query, ...]

    @classmethod
    def build(cls, corpus: Corpus | None = None, judgments: JudgmentSet | None = None) -> Campaign:
        resolved = corpus if corpus is not None else load_default()
        judged = judgments if judgments is not None else JudgmentSet.load()

        # Guidelines only for now. Judging all 48 drug entries per question is a
        # separate labelling pass, and mixing unjudged documents into the store
        # would charge every retriever for returning them.
        store = DocumentStore.from_corpus(resolved.guidelines)

        unknown = judged.validate_against(frozenset(store.ids()))
        if unknown:
            raise SystemExit(
                "judgments reference documents not in the corpus:\n  "
                + "\n  ".join(unknown)
            )

        queries: list[Query] = []
        for jq in judged.queries:
            patient = resolved.patient(jq.patient_id) if jq.patient_id else None
            tags = tuple(derive_condition_tags(patient)) if patient else ()
            queries.append(
                Query(id=jq.id, text=jq.question, tags=tags, patient_id=jq.patient_id)
            )
        return cls(store=store, judgments=judged, queries=tuple(queries))

    def run(self, retriever: Retriever, k: int) -> Evaluation:
        rankings = {q.id: [s.doc_id for s in retriever.search(q, k)] for q in self.queries}
        return evaluate(retriever.name, rankings, self.judgments.grades(), k=k)

    def run_all(self, k: int) -> list[Evaluation]:
        return [self.run(r, k) for r in build_all(self.store)]

    def reranked(self, depth: int = 40, allow_compute: bool = False) -> tuple[Retriever, ...]:
        """Reranked configurations, from cached scores unless told otherwise.

        The tag-set rerank is first because it is the deployable one: it ranks
        and trims exactly what the system already sends, so it cannot surface a
        document the current behaviour would have withheld.
        """
        bm25 = BM25Retriever(self.store)
        stages = (
            TagRetriever(self.store),
            TagFilteredBM25(self.store, bm25),
            bm25,
        )
        return build_reranked(
            self.store, stages, allow_compute=allow_compute, depth=depth
        )

    def run_reranked(self, k: int, depth: int = 40, allow_compute: bool = False):
        try:
            return [self.run(r, k) for r in self.reranked(depth, allow_compute)]
        except ScoresUnavailable as exc:
            return exc

    def run_untruncated_baseline(self) -> Evaluation:
        """The shipped system as it actually behaves: everything, unranked.

        Scoring the tag retriever at k=10 charges it for an ordering it never
        claimed — the live system hands the model every matching guideline and
        implies no ranking. Measured at the full corpus depth it is what it is:
        near-total recall bought by sending near-everything, which is the
        trade the ranked retrievers are being asked to improve on.
        """
        depth = len(self.store)
        retriever = TagRetriever(self.store)
        rankings = {
            q.id: [s.doc_id for s in retriever.search(q, depth)] for q in self.queries
        }
        evaluation = evaluate("tag, untruncated", rankings, self.judgments.grades(), k=depth)
        return evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=10, help="cutoff for the @k metrics")
    parser.add_argument("--per-query", action="store_true", help="also break down by query")
    parser.add_argument(
        "--depth",
        type=int,
        default=40,
        help="reranker candidate depth; it caps recall, since nothing outside "
        "the first stage's top --depth can be recovered",
    )
    parser.add_argument(
        "--compute",
        action="store_true",
        help="score uncached pairs with the model (needs --extra rerank)",
    )
    args = parser.parse_args()

    campaign = Campaign.build()
    rule = "-" * 108

    print(f"corpus            {len(campaign.store)} guidelines")
    print(f"queries           {len(campaign.judgments)}")
    judged_total = sum(len(q.grades) for q in campaign.judgments.queries)
    essential = sum(len(q.essential) for q in campaign.judgments.queries)
    print(f"judgments         {judged_total} relevant ({essential} essential)")
    print(f"cutoff            k = {args.k}")
    print()
    print(campaign.judgments.caveat)
    print(rule)

    shipped = campaign.run_untruncated_baseline()
    print(
        f"{shipped.name:<22} recall {shipped.recall}   nDCG {shipped.ndcg}   "
        f"P {shipped.precision}   avg returned {shipped.mean_returned:.1f}"
    )
    print(
        "                       ^ what ships today: no ranking, no cutoff. Near-total\n"
        "                         recall bought by sending most of the corpus, which is\n"
        "                         the cost the ranked retrievers are trying to cut.\n"
    )

    evaluations = campaign.run_all(args.k)
    for evaluation in evaluations:
        print(evaluation.row())

    reranked = campaign.run_reranked(args.k, depth=args.depth, allow_compute=args.compute)
    if isinstance(reranked, ScoresUnavailable):
        print(f"\n  (reranked configurations skipped: {reranked})")
        reranked = []
    else:
        print()
        for evaluation in reranked:
            print(evaluation.row())
    print(rule)

    baseline, *rest = [*evaluations, *reranked]
    for evaluation in rest:
        delta = evaluation.ndcg.point - baseline.ndcg.point
        overlap = not (
            evaluation.ndcg.low > baseline.ndcg.high
            or baseline.ndcg.low > evaluation.ndcg.high
        )
        verdict = "intervals overlap" if overlap else "intervals separate"
        print(
            f"{evaluation.name:<22} nDCG@{args.k} {delta:+.3f} vs baseline  ({verdict})"
        )
    print()
    print(
        "Six queries cannot separate two retrievers whose intervals overlap. A\n"
        "difference reported here is a direction to investigate, not a result."
    )

    if args.per_query:
        print()
        print(rule)
        for evaluation in [*evaluations, *reranked]:
            print(f"\n{evaluation.name}")
            for result in evaluation.per_query:
                print(
                    f"  {result.query_id:<34} recall {result.recall:.2f}  "
                    f"nDCG {result.ndcg:.3f}  RR {result.reciprocal_rank:.2f}  "
                    f"returned {result.returned:>2}/{result.relevant_total} relevant"
                )


if __name__ == "__main__":
    main()
