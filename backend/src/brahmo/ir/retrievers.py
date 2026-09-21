"""Retrievers, and the baseline they have to beat.

The baseline is not a straw man: :class:`TagRetriever` is what the system ships
today, reproducing ``condition_tags ? tag`` exactly. Measuring against it is
the only way to know whether anything here is an improvement or just newer.

Its weakness is structural rather than a tuning problem. It selects on the
patient's conditions and never reads the question, so every question about a
given patient retrieves the same set; and because the tags are derived
generously, a patient with several conditions matches most of the corpus. Four
of the six seeded patients retrieve 100% of it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Protocol, Sequence

from brahmo.ir.documents import Document, DocumentStore, tokenize


@dataclass(frozen=True, slots=True)
class Query:
    """What a retriever gets to see.

    Both halves are here on purpose. The live system has a patient *and* a
    question; a retriever that ignores either is leaving signal on the table,
    and being able to show that is half the point of the comparison.
    """

    id: str
    text: str
    tags: tuple[str, ...] = ()
    patient_id: int | None = None


@dataclass(frozen=True, slots=True)
class Scored:
    doc_id: str
    score: float

    def __str__(self) -> str:
        return f"{self.doc_id}({self.score:.3f})"


class Retriever(Protocol):
    @property
    def name(self) -> str: ...

    def search(self, query: Query, k: int) -> list[Scored]: ...


def _stable_order(scored: Iterable[Scored]) -> list[Scored]:
    """Highest score first, document id breaking ties.

    Ties are common in a corpus this small, and leaving their order to sort
    stability would make the metrics depend on insertion order.
    """
    return sorted(scored, key=lambda s: (-s.score, s.doc_id))


@dataclass(frozen=True, slots=True)
class TagRetriever:
    """The shipped behaviour: every document sharing a tag with the patient.

    Unranked by construction — tag containment is a boolean test — so ordering
    falls back to document id. That is a real property of the baseline and not
    a handicap imposed on it: the live system hands the model the whole set and
    no ordering is implied.
    """

    store: DocumentStore

    @property
    def name(self) -> str:
        return "tag (shipped)"

    def search(self, query: Query, k: int) -> list[Scored]:
        wanted = set(query.tags)
        if not wanted:
            return []
        hits = [d for d in self.store if wanted & set(d.tags)]
        return [Scored(d.id, 1.0) for d in sorted(hits, key=lambda d: d.id)][:k]


class BM25Retriever:
    """Okapi BM25 over the question text.

    Written out rather than pulled in: the corpus is 77 documents, the formula
    is six lines, and being able to read exactly what the baseline is being
    compared against matters more here than the dependency would save.
    """

    def __init__(self, store: DocumentStore, k1: float = 1.2, b: float = 0.75) -> None:
        self.store = store
        self.k1 = k1
        self.b = b

        self._tokens: dict[str, list[str]] = {
            d.id: tokenize(d.indexed_text) for d in store
        }
        self._length = {doc_id: len(t) for doc_id, t in self._tokens.items()}
        self._avg_length = (
            sum(self._length.values()) / len(self._length) if self._length else 0.0
        )

        self._freq: dict[str, dict[str, int]] = {}
        postings: dict[str, set[str]] = defaultdict(set)
        for doc_id, tokens in self._tokens.items():
            counts: dict[str, int] = defaultdict(int)
            for token in tokens:
                counts[token] += 1
                postings[token].add(doc_id)
            self._freq[doc_id] = dict(counts)

        total = len(self._tokens)
        # Lucene's BM25 idf: always positive, so a term in most documents
        # contributes a little rather than subtracting.
        self._idf = {
            term: math.log(1 + (total - len(docs) + 0.5) / (len(docs) + 0.5))
            for term, docs in postings.items()
        }
        self._postings = {t: frozenset(d) for t, d in postings.items()}

    @property
    def name(self) -> str:
        return "bm25"

    def score(self, terms: Sequence[str], doc_id: str) -> float:
        freqs = self._freq.get(doc_id, {})
        length = self._length.get(doc_id, 0)
        norm = self.k1 * (1 - self.b + self.b * length / (self._avg_length or 1))
        total = 0.0
        for term in terms:
            tf = freqs.get(term, 0)
            if not tf:
                continue
            total += self._idf.get(term, 0.0) * (tf * (self.k1 + 1)) / (tf + norm)
        return total

    def search(self, query: Query, k: int) -> list[Scored]:
        terms = tokenize(query.text)
        if not terms:
            return []
        candidates: set[str] = set()
        for term in terms:
            candidates |= self._postings.get(term, frozenset())
        scored = (Scored(doc_id, self.score(terms, doc_id)) for doc_id in candidates)
        return [s for s in _stable_order(scored) if s.score > 0][:k]


@dataclass
class HybridRetriever:
    """Reciprocal rank fusion over several retrievers.

    RRF rather than a weighted score sum because the components are not on a
    comparable scale — BM25 scores are unbounded and the tag retriever emits a
    constant — and normalising them would invent a relationship that is not
    there. RRF only needs the orderings.

    ``rrf_k`` damps the contribution of top ranks; 60 is the value from the
    original paper and is left alone rather than tuned on an evaluation set
    this small, where tuning it would mean fitting six queries.
    """

    components: tuple[Retriever, ...]
    rrf_k: int = 60
    label: str = "hybrid (tag + bm25, RRF)"
    depth: int = 50
    weights: Mapping[str, float] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.label

    def search(self, query: Query, k: int) -> list[Scored]:
        fused: dict[str, float] = defaultdict(float)
        for retriever in self.components:
            weight = self.weights.get(retriever.name, 1.0)
            for rank, scored in enumerate(retriever.search(query, self.depth), start=1):
                fused[scored.doc_id] += weight / (self.rrf_k + rank)
        return _stable_order(Scored(d, s) for d, s in fused.items())[:k]


@dataclass(frozen=True, slots=True)
class TagFilteredBM25:
    """BM25, restricted to what the patient's tags admit.

    The clinically conservative option: it cannot surface a document the
    shipped system would have withheld, so it can only reorder and trim, never
    introduce. Worth measuring separately from the fusion because "rank what we
    already send" is a change a cautious reviewer would accept on its own.
    """

    store: DocumentStore
    bm25: BM25Retriever

    @property
    def name(self) -> str:
        return "bm25 within tags"

    def search(self, query: Query, k: int) -> list[Scored]:
        wanted = set(query.tags)
        if not wanted:
            return []
        allowed = {d.id for d in self.store if wanted & set(d.tags)}
        terms = tokenize(query.text)
        if not terms:
            return []
        scored = (Scored(doc_id, self.bm25.score(terms, doc_id)) for doc_id in allowed)
        return [s for s in _stable_order(scored) if s.score > 0][:k]


def build_all(store: DocumentStore) -> tuple[Retriever, ...]:
    """The retrievers the harness compares, baseline first."""
    tag = TagRetriever(store)
    bm25 = BM25Retriever(store)
    return (
        tag,
        bm25,
        TagFilteredBM25(store, bm25),
        HybridRetriever(components=(tag, bm25)),
    )
