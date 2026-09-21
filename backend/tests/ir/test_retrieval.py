"""Retrievers, the judgment set, and the guards that keep the evaluation honest."""

from __future__ import annotations

import pytest

from brahmo.ir.documents import Document, DocumentStore, tokenize
from brahmo.ir.harness import Campaign
from brahmo.ir.judgments import JudgmentError, JudgmentSet
from brahmo.ir.retrievers import (
    BM25Retriever,
    HybridRetriever,
    Query,
    TagFilteredBM25,
    TagRetriever,
)


@pytest.fixture(scope="module")
def toy_store() -> DocumentStore:
    return DocumentStore(
        [
            Document("g:1", "guideline", "Anticoagulation in valvular AF",
                     "Warfarin only. DOACs are contraindicated in rheumatic mitral stenosis.",
                     tags=("atrial_fibrillation",)),
            Document("g:2", "guideline", "Metformin first line",
                     "Metformin is first-line therapy at diagnosis of type 2 diabetes.",
                     tags=("diabetes",)),
            Document("g:3", "guideline", "Diet in Indian practice",
                     "Prefer millets and brown rice over white rice for glycaemic control.",
                     tags=("diabetes",)),
        ]
    )


# -- tokenizing -------------------------------------------------------------


def test_tokenizer_keeps_clinical_abbreviations() -> None:
    """AF, MI, eGFR carry the signal; dropping them would be fatal here."""
    tokens = tokenize("AF with eGFR 38 post-MI")
    assert "af" in tokens and "egfr" in tokens and "mi" in tokens and "38" in tokens


def test_tokenizer_drops_only_harmless_stopwords() -> None:
    assert "not" in tokenize("DOACs are not indicated")
    assert "no" in tokenize("no anaphylaxis")
    assert "the" not in tokenize("the patient")


# -- the shipped baseline ---------------------------------------------------


def test_tag_retriever_returns_everything_sharing_a_tag(toy_store: DocumentStore) -> None:
    hits = TagRetriever(toy_store).search(Query("q", "anything", tags=("diabetes",)), 10)
    assert [h.doc_id for h in hits] == ["g:2", "g:3"]


def test_tag_retriever_ignores_the_question(toy_store: DocumentStore) -> None:
    """The baseline's defining weakness, stated as a test."""
    tag = TagRetriever(toy_store)
    about_diet = tag.search(Query("a", "what should he eat", tags=("diabetes",)), 10)
    about_drugs = tag.search(Query("b", "which drug do I start", tags=("diabetes",)), 10)
    assert [h.doc_id for h in about_diet] == [h.doc_id for h in about_drugs]


def test_tag_retriever_returns_nothing_without_tags(toy_store: DocumentStore) -> None:
    assert TagRetriever(toy_store).search(Query("q", "warfarin", tags=()), 10) == []


# -- bm25 -------------------------------------------------------------------


def test_bm25_ranks_the_document_the_question_is_about(toy_store: DocumentStore) -> None:
    hits = BM25Retriever(toy_store).search(
        Query("q", "which anticoagulant in rheumatic mitral stenosis"), 3
    )
    assert hits[0].doc_id == "g:1"


def test_bm25_reads_the_question_not_the_tags(toy_store: DocumentStore) -> None:
    bm25 = BM25Retriever(toy_store)
    diet = bm25.search(Query("a", "rice and millets in the Indian diet"), 1)
    drug = bm25.search(Query("b", "first line therapy at diagnosis"), 1)
    assert diet[0].doc_id == "g:3"
    assert drug[0].doc_id == "g:2"


def test_bm25_returns_nothing_for_an_unmatched_query(toy_store: DocumentStore) -> None:
    assert BM25Retriever(toy_store).search(Query("q", "orthopaedic fracture fixation"), 5) == []


def test_bm25_is_deterministic_under_ties(toy_store: DocumentStore) -> None:
    bm25 = BM25Retriever(toy_store)
    query = Query("q", "diabetes")
    assert [h.doc_id for h in bm25.search(query, 5)] == [
        h.doc_id for h in bm25.search(query, 5)
    ]


# -- composition ------------------------------------------------------------


def test_tag_filtered_bm25_cannot_surface_what_tags_exclude(toy_store: DocumentStore) -> None:
    """The conservative option: it may reorder and trim, never introduce."""
    retriever = TagFilteredBM25(toy_store, BM25Retriever(toy_store))
    hits = retriever.search(
        Query("q", "warfarin in rheumatic mitral stenosis", tags=("diabetes",)), 10
    )
    assert "g:1" not in [h.doc_id for h in hits]


def test_hybrid_fuses_both_component_orderings(toy_store: DocumentStore) -> None:
    store = toy_store
    hybrid = HybridRetriever(components=(TagRetriever(store), BM25Retriever(store)))
    hits = hybrid.search(
        Query("q", "rheumatic mitral stenosis", tags=("diabetes",)), 10
    )
    found = {h.doc_id for h in hits}
    assert "g:1" in found  # only bm25 could reach it
    assert "g:2" in found  # only the tag side could reach it


# -- the judgment set -------------------------------------------------------


def test_the_shipped_judgments_load() -> None:
    judged = JudgmentSet.load()
    assert len(judged) == 6
    assert all(q.relevant for q in judged.queries)


def test_unreviewed_judgments_carry_the_caveat() -> None:
    judged = JudgmentSet.load()
    if not judged.reviewed:
        assert "PROVISIONAL" in judged.caveat


def test_every_judged_document_exists_in_the_corpus() -> None:
    """A typo'd id is an unreachable relevant document, indistinguishable
    from a retriever failure."""
    campaign = Campaign.build()
    assert campaign.judgments.validate_against(frozenset(campaign.store.ids())) == []


def test_a_bad_grade_is_rejected() -> None:
    with pytest.raises(JudgmentError, match="grade must be"):
        JudgmentSet.from_dict(
            {"schema": 1, "queries": [{"id": "q", "judgments": {"g:1": 7}}]}
        )


def test_a_duplicate_query_id_is_rejected() -> None:
    with pytest.raises(JudgmentError, match="duplicate"):
        JudgmentSet.from_dict(
            {
                "schema": 1,
                "queries": [
                    {"id": "q", "judgments": {"g:1": 2}},
                    {"id": "q", "judgments": {"g:2": 2}},
                ],
            }
        )


def test_an_unknown_schema_is_rejected() -> None:
    with pytest.raises(JudgmentError, match="schema"):
        JudgmentSet.from_dict({"schema": 99, "queries": []})


# -- the circularity guard --------------------------------------------------


def test_the_judgments_are_not_a_restatement_of_the_tags() -> None:
    """The methodological trap this evaluation exists to avoid.

    If relevance had been derived from ``condition_tags``, the shipped tag
    retriever would score near-perfectly by construction and the comparison
    would measure nothing. It does not, which is evidence the labels carry
    information the tags do not.
    """
    campaign = Campaign.build()
    shipped = campaign.run_untruncated_baseline()
    assert shipped.precision.point < 0.5, (
        "tag retrieval is too precise against these judgments — check they were "
        "not derived from condition_tags"
    )


def test_tag_retrieval_returns_most_of_the_corpus() -> None:
    """The motivating problem, measured rather than asserted."""
    campaign = Campaign.build()
    shipped = campaign.run_untruncated_baseline()
    assert shipped.mean_returned > 0.7 * len(campaign.store)
    assert shipped.recall.point > 0.9  # it finds everything, by sending everything


def test_the_harness_runs_every_retriever() -> None:
    evaluations = Campaign.build().run_all(k=10)
    assert [e.name for e in evaluations][0] == "tag (shipped)"
    assert len(evaluations) == 4
    assert all(0.0 <= e.ndcg.point <= 1.0 for e in evaluations)


def test_results_are_reproducible() -> None:
    first = {e.name: e.ndcg.point for e in Campaign.build().run_all(k=10)}
    second = {e.name: e.ndcg.point for e in Campaign.build().run_all(k=10)}
    assert first == second
