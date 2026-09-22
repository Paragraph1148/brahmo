"""The drafted questions and the labelling worksheet built from them."""

from __future__ import annotations

import json

import pytest

from brahmo.corpus import load_default
from brahmo.ir.drafts import DraftSet
from brahmo.ir.harness import Campaign
from brahmo.ir.judgments import JudgmentSet
from brahmo.ir.worksheet import build_pools, markdown, skeleton


@pytest.fixture(scope="module")
def drafts() -> DraftSet:
    return DraftSet.load()


@pytest.fixture(scope="module")
def pools():
    return build_pools(depth=8)


def test_drafts_load_with_unique_ids(drafts: DraftSet) -> None:
    assert len(drafts) == 44
    assert len({q.id for q in drafts.questions}) == len(drafts)


def test_drafts_do_not_collide_with_the_judged_set(drafts: DraftSet) -> None:
    """An id clash would silently overwrite a judged query on merge."""
    judged = {q.id for q in JudgmentSet.load().queries}
    assert not judged & {q.id for q in drafts.questions}


def test_every_draft_names_a_patient_that_exists(drafts: DraftSet) -> None:
    corpus = load_default()
    missing = [q.id for q in drafts.questions if corpus.patient(q.patient_id) is None]
    assert missing == []


def test_drafts_cover_the_held_out_patients(drafts: DraftSet) -> None:
    """Patients 7-9 were absent from the judged set entirely."""
    covered = {q.patient_id for q in drafts.questions}
    assert {7, 8, 9} <= covered


def test_drafts_probe_more_than_lexical_overlap(drafts: DraftSet) -> None:
    """A set of easy questions would measure nothing but term matching."""
    probes = {q.probes for q in drafts.questions}
    assert {"vocabulary-gap", "negative", "distractor", "multi-hop", "cost"} <= probes
    lexical = sum(1 for q in drafts.questions if q.probes == "lexical")
    assert lexical < len(drafts) / 2


def test_negative_controls_exist(drafts: DraftSet) -> None:
    """Without them no metric can see a retriever that answers confidently
    when it should return nothing."""
    assert sum(1 for q in drafts.questions if q.probes == "negative") >= 5


# -- pooling ----------------------------------------------------------------


def test_every_question_pools_some_candidates(pools) -> None:
    assert all(p.candidates for p in pools)


def test_pooling_is_smaller_than_judging_everything(pools) -> None:
    corpus_size = len(Campaign.build().store)
    pooled = sum(len(p.candidates) for p in pools)
    assert pooled < len(pools) * corpus_size * 0.75


def test_pools_are_not_merely_the_whole_corpus(pools) -> None:
    corpus_size = len(Campaign.build().store)
    assert all(len(p.candidates) < corpus_size for p in pools)


def test_the_cross_encoder_contributes_to_the_pools(pools) -> None:
    """Without it the pool is lexically biased and the vocabulary-gap
    questions would never show their answers to a reviewer."""
    contributors = {name for p in pools for names in p.found_by.values() for name in names}
    assert any(name.startswith("rerank(") for name in contributors), contributors


def test_the_vocabulary_gap_answer_reaches_the_pool(pools) -> None:
    """guideline:19 says a penicillin allergy does not contraindicate heparin.
    It is the one that matters for patient 4 and shares few terms with the
    question."""
    pool = next(p for p in pools if p.question.id == "p4-penicillin-anaphylaxis-heparin")
    assert "guideline:19" in pool.candidates


def test_pools_are_ordered_by_retriever_agreement(pools) -> None:
    for pool in pools:
        agreement = [len(pool.found_by[d]) for d in pool.candidates]
        assert agreement == sorted(agreement, reverse=True)


def test_pooling_is_deterministic() -> None:
    first = {p.question.id: p.candidates for p in build_pools(depth=8)}
    second = {p.question.id: p.candidates for p in build_pools(depth=8)}
    assert first == second


# -- the emitted artefacts --------------------------------------------------


def test_the_worksheet_renders_every_question(pools) -> None:
    text = markdown(pools)
    for pool in pools:
        assert f"`{pool.question.id}`" in text
        assert pool.question.question in text
    assert text.count("| `_` |") == sum(len(p.candidates) for p in pools)


def test_the_skeleton_is_a_loadable_judgment_set(pools) -> None:
    """It must merge into judgments.json without a schema change."""
    data = json.loads(skeleton(pools))
    loaded = JudgmentSet.from_dict(data)
    assert len(loaded) == len(pools)
    assert loaded.reviewed is False


def test_the_skeleton_starts_every_grade_at_zero(pools) -> None:
    """Pre-filled grades would be the same mistake as generating judgments."""
    data = json.loads(skeleton(pools))
    assert all(
        grade == 0 for q in data["queries"] for grade in q["judgments"].values()
    )


def test_an_unlabelled_skeleton_scores_nothing(pools) -> None:
    """Zero grades mean zero relevant documents, so the harness skips them
    rather than reporting a vacuous perfect score."""
    loaded = JudgmentSet.from_dict(json.loads(skeleton(pools)))
    assert all(q.relevant == () for q in loaded.queries)
