"""Retrieval metrics.

Rates carry a Wilson interval rather than being reported bare. Six patients is
a small evaluation set and a point estimate off six queries invites a
confidence it does not support — the interval is what stops "0.83 recall" being
read as a fact about the system rather than about six questions.

Relevance is graded, not binary. A guideline can be the one a clinician needs,
or merely reasonable background, and a metric that cannot tell those apart
rewards a retriever for burying the first under the second. Binary metrics
(recall, precision, MRR) treat any positive grade as relevant; nDCG uses the
grades.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

#: Relevance grades. The names matter more than the numbers: a judgment is a
#: clinical claim about whether a clinician needed this document for this
#: question, and "would have been useful" is not "would have been wrong to omit".
ESSENTIAL = 2
USEFUL = 1
IRRELEVANT = 0


@dataclass(frozen=True, slots=True)
class Interval:
    """A Wilson score interval on a proportion."""

    point: float
    low: float
    high: float
    n: int

    def __str__(self) -> str:
        return f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}]"


def wilson(successes: float, n: int, z: float = 1.96) -> Interval:
    """Wilson score interval, which behaves at the extremes where normal does not.

    Accepts a fractional numerator so a mean of per-query scores (nDCG, say)
    can carry an interval on the same footing as a count of hits.
    """
    if n <= 0:
        return Interval(0.0, 0.0, 0.0, 0)
    p = successes / n
    p = min(max(p, 0.0), 1.0)
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    return Interval(p, max(0.0, centre - margin), min(1.0, centre + margin), n)


def _relevant_ids(judgments: Mapping[str, int]) -> set[str]:
    return {doc_id for doc_id, grade in judgments.items() if grade > IRRELEVANT}


def recall_at_k(ranked: Sequence[str], judgments: Mapping[str, int], k: int) -> float:
    """Fraction of relevant documents that appear in the top k.

    Undefined with no relevant documents; returns 1.0, on the reading that a
    query with nothing to find cannot have failed to find it. Such queries are
    excluded from the aggregate by :func:`evaluate`.
    """
    relevant = _relevant_ids(judgments)
    if not relevant:
        return 1.0
    return len(relevant & set(ranked[:k])) / len(relevant)


def precision_at_k(ranked: Sequence[str], judgments: Mapping[str, int], k: int) -> float:
    """Fraction of the top k that is relevant.

    The denominator is k, not the number returned. A retriever that returns two
    documents and gets both right has not achieved precision@10 of 1.0 — it has
    returned two documents.
    """
    if k <= 0:
        return 0.0
    relevant = _relevant_ids(judgments)
    return len(relevant & set(ranked[:k])) / k


def reciprocal_rank(ranked: Sequence[str], judgments: Mapping[str, int]) -> float:
    """1/rank of the first relevant document, or 0 if none is retrieved."""
    relevant = _relevant_ids(judgments)
    for position, doc_id in enumerate(ranked, start=1):
        if doc_id in relevant:
            return 1.0 / position
    return 0.0


def dcg(grades: Sequence[int]) -> float:
    return sum(g / math.log2(i + 1) for i, g in enumerate(grades, start=1) if g > 0)


def ndcg_at_k(ranked: Sequence[str], judgments: Mapping[str, int], k: int) -> float:
    """Discounted cumulative gain against the best possible ordering.

    Uses the graded relevance, so a retriever that puts the essential guideline
    below three merely useful ones is scored lower than one that leads with it,
    even though both "found" the same documents.
    """
    ideal = sorted((g for g in judgments.values() if g > 0), reverse=True)[:k]
    if not ideal:
        return 1.0
    got = [judgments.get(doc_id, IRRELEVANT) for doc_id in ranked[:k]]
    best = dcg(ideal)
    return dcg(got) / best if best else 0.0


@dataclass(frozen=True, slots=True)
class QueryResult:
    query_id: str
    recall: float
    precision: float
    reciprocal_rank: float
    ndcg: float
    returned: int
    relevant_total: int


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Aggregate scores for one retriever over one query set."""

    name: str
    k: int
    per_query: tuple[QueryResult, ...]
    recall: Interval
    precision: Interval
    mrr: Interval
    ndcg: Interval
    mean_returned: float

    def row(self) -> str:
        return (
            f"{self.name:<22} recall@{self.k} {self.recall}   "
            f"nDCG@{self.k} {self.ndcg}   MRR {self.mrr}   "
            f"P@{self.k} {self.precision}   avg returned {self.mean_returned:.1f}"
        )


def evaluate(
    name: str,
    rankings: Mapping[str, Sequence[str]],
    judgments: Mapping[str, Mapping[str, int]],
    k: int = 10,
) -> Evaluation:
    """Score one retriever's rankings against the judgments.

    Queries with no relevant document recorded are skipped rather than scored:
    they say nothing about a retriever, and averaging their vacuous 1.0 into the
    result would flatter every system equally.
    """
    results: list[QueryResult] = []
    for query_id, judged in judgments.items():
        if not _relevant_ids(judged):
            continue
        ranked = list(rankings.get(query_id, ()))
        results.append(
            QueryResult(
                query_id=query_id,
                recall=recall_at_k(ranked, judged, k),
                precision=precision_at_k(ranked, judged, k),
                reciprocal_rank=reciprocal_rank(ranked, judged),
                ndcg=ndcg_at_k(ranked, judged, k),
                returned=len(ranked),
                relevant_total=len(_relevant_ids(judged)),
            )
        )

    n = len(results)
    mean = lambda values: sum(values) / n if n else 0.0  # noqa: E731
    return Evaluation(
        name=name,
        k=k,
        per_query=tuple(results),
        recall=wilson(sum(r.recall for r in results), n),
        precision=wilson(sum(r.precision for r in results), n),
        mrr=wilson(sum(r.reciprocal_rank for r in results), n),
        ndcg=wilson(sum(r.ndcg for r in results), n),
        mean_returned=mean([r.returned for r in results]),
    )
