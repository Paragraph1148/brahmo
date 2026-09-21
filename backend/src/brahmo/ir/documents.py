"""The retrievable units.

This corpus arrives pre-chunked and it would be a mistake to re-chunk it. A
guideline row is already one graded recommendation with its section heading,
source and year attached; a drug row is already one formulary entry. Splitting
either on a token budget would cut a recommendation away from the evidence
grade that qualifies it, which is the part a clinician reads first.

So the chunking decision here is to respect the structure that exists rather
than impose one. Where a longer source is added later — a full guideline PDF —
it should be split on its own recommendation boundaries for the same reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

#: Clinical text is full of abbreviations that matter (AF, MI, HF, eGFR) and
#: punctuation that does not. Keep alphanumerics, fold case, drop the rest.
_TOKEN = re.compile(r"[a-z0-9]+")

#: Words carrying no discriminative power in a corpus that is entirely about
#: Indian clinical practice. Kept deliberately short: aggressive stoplists
#: remove terms that turn out to matter ("no", "not" flip a recommendation).
_STOPWORDS = frozenset(
    """a an and are as at be by for from in into is it its of on or that the
    to with which while when if then than this these those""".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens, stopwords removed."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


@dataclass(frozen=True, slots=True)
class Document:
    """One retrievable item, with everything needed to cite it."""

    id: str
    kind: str
    title: str
    text: str
    tags: tuple[str, ...] = ()
    source: str | None = None
    year: int | None = None

    @property
    def indexed_text(self) -> str:
        """What a lexical retriever matches against.

        The title is included because a section heading like "AF
        anticoagulation choice" carries most of the topical signal in one line,
        and a body that never repeats those words would otherwise be
        unreachable by a query that uses them.
        """
        return f"{self.title}\n{self.text}"

    @property
    def citation(self) -> str:
        if self.source and self.year:
            return f"{self.source} {self.year} — {self.title}"
        return self.title


def guideline_document(row: dict[str, Any]) -> Document:
    return Document(
        id=f"guideline:{row['id']}",
        kind="guideline",
        title=row.get("section") or "",
        text=row.get("recommendation") or "",
        tags=tuple(row.get("condition_tags") or ()),
        source=row.get("source_id"),
        year=int(row["year"]) if row.get("year") else None,
    )


def drug_document(row: dict[str, Any]) -> Document:
    """A formulary entry as retrievable text.

    Brand and manufacturer are indexed because Indian practice names drugs that
    way — a clinician asking about Dynaglipt is asking about teneligliptin, and
    a retriever that only knows generic names cannot follow.
    """
    parts = [
        row.get("generic_name") or "",
        row.get("indian_brand_name") or "",
        row.get("manufacturer") or "",
        row.get("drug_class") or "",
        row.get("drug_subclass") or "",
        row.get("notes") or "",
    ]
    if row.get("nlem_status"):
        parts.append("NLEM essential medicine")
    return Document(
        id=f"drug:{row['id']}",
        kind="drug",
        title=row.get("generic_name") or "",
        text=" — ".join(p for p in parts[1:] if p),
        tags=tuple(row.get("condition_tags") or ()),
        source=None,
        year=None,
    )


class DocumentStore:
    """Every retrievable document, addressable by id."""

    def __init__(self, documents: Iterable[Document]) -> None:
        self._docs = tuple(sorted(documents, key=lambda d: d.id))
        self._by_id = {d.id: d for d in self._docs}
        if len(self._by_id) != len(self._docs):
            raise ValueError("duplicate document ids in the store")

    @classmethod
    def from_corpus(
        cls,
        guidelines: Sequence[dict[str, Any]],
        drugs: Sequence[dict[str, Any]] = (),
    ) -> DocumentStore:
        docs = [guideline_document(r) for r in guidelines]
        docs += [drug_document(r) for r in drugs]
        return cls(docs)

    def __len__(self) -> int:
        return len(self._docs)

    def __iter__(self):
        return iter(self._docs)

    def __contains__(self, doc_id: object) -> bool:
        return doc_id in self._by_id

    def get(self, doc_id: str) -> Document | None:
        return self._by_id.get(doc_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(d.id for d in self._docs)

    def of_kind(self, kind: str) -> tuple[Document, ...]:
        return tuple(d for d in self._docs if d.kind == kind)
