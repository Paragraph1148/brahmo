"""Metric behaviour, pinned on cases where the right answer is known by hand."""

from __future__ import annotations

import pytest

from brahmo.ir.metrics import (
    ESSENTIAL,
    USEFUL,
    dcg,
    evaluate,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    wilson,
)

JUDGED = {"a": ESSENTIAL, "b": USEFUL, "c": 0}


def test_recall_counts_only_relevant_documents() -> None:
    assert recall_at_k(["a", "b"], JUDGED, 10) == 1.0
    assert recall_at_k(["a"], JUDGED, 10) == 0.5
    assert recall_at_k(["c"], JUDGED, 10) == 0.0


def test_recall_respects_the_cutoff() -> None:
    assert recall_at_k(["c", "c", "a"], JUDGED, 2) == 0.0
    assert recall_at_k(["c", "c", "a"], JUDGED, 3) == 0.5


def test_precision_divides_by_k_not_by_what_was_returned() -> None:
    """Returning two correct documents is not precision@10 of 1.0."""
    assert precision_at_k(["a", "b"], JUDGED, 10) == pytest.approx(0.2)
    assert precision_at_k(["a", "b"], JUDGED, 2) == 1.0


def test_reciprocal_rank_finds_the_first_hit() -> None:
    assert reciprocal_rank(["a"], JUDGED) == 1.0
    assert reciprocal_rank(["c", "a"], JUDGED) == 0.5
    assert reciprocal_rank(["c"], JUDGED) == 0.0


def test_ndcg_rewards_putting_the_essential_document_first() -> None:
    """The discrimination recall cannot make."""
    leading = ndcg_at_k(["a", "b"], JUDGED, 10)
    buried = ndcg_at_k(["b", "a"], JUDGED, 10)
    assert leading == 1.0
    assert buried < leading
    assert recall_at_k(["a", "b"], JUDGED, 10) == recall_at_k(["b", "a"], JUDGED, 10)


def test_ndcg_is_bounded() -> None:
    assert ndcg_at_k([], JUDGED, 10) == 0.0
    assert 0.0 <= ndcg_at_k(["c", "b", "a"], JUDGED, 10) <= 1.0


def test_dcg_discounts_by_position() -> None:
    assert dcg([2, 0]) > dcg([0, 2])


def test_a_query_with_nothing_to_find_is_not_a_failure() -> None:
    assert recall_at_k([], {"x": 0}, 10) == 1.0
    assert ndcg_at_k([], {"x": 0}, 10) == 1.0


def test_wilson_does_not_claim_certainty_from_a_small_sample() -> None:
    """Six from six is not proof; the interval has to say so."""
    perfect = wilson(6, 6)
    assert perfect.point == 1.0
    assert perfect.low < 0.7


def test_wilson_narrows_as_n_grows() -> None:
    small = wilson(5, 6)
    large = wilson(500, 600)
    assert (large.high - large.low) < (small.high - small.low)


def test_wilson_handles_the_empty_case() -> None:
    assert wilson(0, 0).point == 0.0


def test_evaluate_skips_queries_with_no_relevant_document() -> None:
    """A vacuous query would flatter every retriever equally."""
    judgments = {"real": {"a": ESSENTIAL}, "vacuous": {"z": 0}}
    result = evaluate("t", {"real": ["a"], "vacuous": ["q"]}, judgments, k=10)
    assert [r.query_id for r in result.per_query] == ["real"]
    assert result.recall.n == 1
