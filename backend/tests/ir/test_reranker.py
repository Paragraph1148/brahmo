"""Reranking: the cache, the ordering, and what a reranker cannot fix.

None of these download a model. The shipped score cache covers every judged
pair, and ``allow_compute=False`` makes a miss an error rather than a quiet
network call — a test that downloads a model is a test that fails on a plane.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from brahmo.ir.documents import Document, DocumentStore
from brahmo.ir.harness import Campaign
from brahmo.ir.reranker import (
    DEFAULT_MODEL,
    CachedScorer,
    RerankedRetriever,
    ScoreCache,
    ScoresUnavailable,
    _pair_key,
    default_cache_path,
)
from brahmo.ir.retrievers import Query, Scored


@dataclass
class FakeRetriever:
    """A first stage with a known, deliberately wrong ordering."""

    order: tuple[str, ...]
    label: str = "fake"

    @property
    def name(self) -> str:
        return self.label

    def search(self, query: Query, k: int) -> list[Scored]:
        return [Scored(d, 1.0) for d in self.order[:k]]


@dataclass
class FakeScorer:
    """Scores by a fixed table, so the expected ranking is known."""

    table: dict[str, float]
    name_: str = "fake-scorer"

    @property
    def name(self) -> str:
        return self.name_

    def score_pairs(self, pairs):
        return [self.table.get(text, 0.0) for _, text in pairs]


@pytest.fixture
def store() -> DocumentStore:
    return DocumentStore(
        [
            Document("g:1", "guideline", "one", "alpha"),
            Document("g:2", "guideline", "two", "beta"),
            Document("g:3", "guideline", "three", "gamma"),
        ]
    )


# -- the cache --------------------------------------------------------------


def test_cache_round_trips(tmp_path: Path) -> None:
    cache = ScoreCache.load(tmp_path / "scores.json")
    cache.put("k", 1.5)
    cache.save()
    assert ScoreCache.load(tmp_path / "scores.json").get("k") == 1.5


def test_editing_a_question_invalidates_its_scores() -> None:
    """Keying on the query id would silently reuse a stale score."""
    before = _pair_key(DEFAULT_MODEL, "how do I manage triple therapy", "g:1")
    after = _pair_key(DEFAULT_MODEL, "how do I manage dual therapy", "g:1")
    assert before != after


def test_the_model_name_is_part_of_the_key() -> None:
    assert _pair_key("model-a", "q", "g:1") != _pair_key("model-b", "q", "g:1")


def test_a_missing_score_is_an_error_when_computing_is_disabled(
    tmp_path: Path, store: DocumentStore
) -> None:
    scorer = CachedScorer(cache=ScoreCache.load(tmp_path / "s.json"), allow_compute=False)
    with pytest.raises(ScoresUnavailable, match="not in the score cache"):
        scorer.score("a question", list(store))


def test_cached_scores_are_reused_rather_than_recomputed(
    tmp_path: Path, store: DocumentStore
) -> None:
    cache = ScoreCache.load(tmp_path / "s.json")
    scorer = CachedScorer(
        cache=cache, compute=FakeScorer({"one\nalpha": 9.0, "two\nbeta": 1.0, "three\ngamma": 5.0})
    )
    first = scorer.score("q", list(store))
    misses_after_first = cache.misses
    second = scorer.score("q", list(store))
    assert first == second
    assert cache.misses == misses_after_first  # nothing recomputed


# -- reranking --------------------------------------------------------------


def test_the_reranker_reorders_the_first_stage(tmp_path: Path, store: DocumentStore) -> None:
    scorer = CachedScorer(
        cache=ScoreCache.load(tmp_path / "s.json"),
        compute=FakeScorer({"one\nalpha": 1.0, "two\nbeta": 9.0, "three\ngamma": 5.0}),
    )
    reranked = RerankedRetriever(
        first_stage=FakeRetriever(("g:1", "g:2", "g:3")), scorer=scorer, store=store
    )
    assert [h.doc_id for h in reranked.search(Query("q", "text"), 3)] == ["g:2", "g:3", "g:1"]


def test_a_reranker_cannot_recover_what_the_first_stage_missed(
    tmp_path: Path, store: DocumentStore
) -> None:
    """Recall is inherited. This is why --depth caps what reranking achieves."""
    scorer = CachedScorer(
        cache=ScoreCache.load(tmp_path / "s.json"),
        compute=FakeScorer({"one\nalpha": 1.0, "two\nbeta": 9.0, "three\ngamma": 99.0}),
    )
    reranked = RerankedRetriever(
        first_stage=FakeRetriever(("g:1", "g:2")), scorer=scorer, store=store, depth=2
    )
    assert "g:3" not in {h.doc_id for h in reranked.search(Query("q", "text"), 3)}


def test_reranking_an_empty_first_stage_returns_nothing(
    tmp_path: Path, store: DocumentStore
) -> None:
    scorer = CachedScorer(cache=ScoreCache.load(tmp_path / "s.json"), compute=FakeScorer({}))
    reranked = RerankedRetriever(first_stage=FakeRetriever(()), scorer=scorer, store=store)
    assert reranked.search(Query("q", "text"), 5) == []


# -- the shipped cache ------------------------------------------------------


def test_the_shipped_cache_covers_every_judged_pair() -> None:
    """The evaluation must reproduce for someone with neither torch nor a GPU."""
    campaign = Campaign.build()
    cache = ScoreCache.load(default_cache_path())
    missing = [
        (q.id, d.id)
        for q in campaign.queries
        for d in campaign.store
        if cache.scores.get(_pair_key(DEFAULT_MODEL, q.text, d.id)) is None
    ]
    assert missing == [], f"{len(missing)} pairs would need the model"


def test_reranked_configurations_run_from_cache_alone() -> None:
    campaign = Campaign.build()
    evaluations = campaign.run_reranked(k=10, allow_compute=False)
    assert not isinstance(evaluations, ScoresUnavailable)
    assert len(evaluations) == 3
    assert all(0.0 <= e.ndcg.point <= 1.0 for e in evaluations)


def test_the_cache_file_is_valid_json_with_provenance() -> None:
    data = json.loads(default_cache_path().read_text())
    assert "about" in data and "scores" in data
    assert all(isinstance(v, (int, float)) for v in data["scores"].values())


# -- what the evaluation says -----------------------------------------------


def test_reranking_helps_most_where_there_was_no_ranking() -> None:
    """The headline: the tag set is unranked, so the reranker has most to add."""
    campaign = Campaign.build()
    tag = campaign.run(campaign.reranked(depth=40)[0].first_stage, 10)
    reranked_tag = campaign.run(campaign.reranked(depth=40)[0], 10)
    assert reranked_tag.ndcg.point > tag.ndcg.point + 0.2
    assert reranked_tag.recall.point > tag.recall.point + 0.2


def test_bm25_recall_plateaus_below_the_rerankers() -> None:
    """A lexical ceiling no cutoff fixes: some relevant guidelines share no
    terms with the question."""
    campaign = Campaign.build()
    from brahmo.ir.retrievers import BM25Retriever, TagFilteredBM25

    lexical = campaign.run(TagFilteredBM25(campaign.store, BM25Retriever(campaign.store)), 29)
    reranked = campaign.run(campaign.reranked(depth=40)[0], 29)
    assert lexical.recall.point < 0.8
    assert reranked.recall.point > lexical.recall.point
