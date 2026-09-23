"""Loading the relevance judgments.

The file is data, hand-edited, and deliberately not generated. A judgment is a
clinical claim — "a clinician needed this guideline to answer this question" —
and deriving it from the same signal a retriever uses would make the evaluation
circular: grade tag retrieval by tag overlap and the baseline wins by
construction while measuring nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Mapping


class JudgmentError(ValueError):
    """The judgment file is malformed."""


@dataclass(frozen=True, slots=True)
class JudgedQuery:
    id: str
    question: str
    patient_id: int | None
    grades: Mapping[str, int]
    rationale: str = ""

    @property
    def essential(self) -> tuple[str, ...]:
        return tuple(sorted(d for d, g in self.grades.items() if g >= 2))

    @property
    def relevant(self) -> tuple[str, ...]:
        return tuple(sorted(d for d, g in self.grades.items() if g > 0))


@dataclass(frozen=True, slots=True)
class JudgmentSet:
    corpus: str
    reviewed: bool
    queries: tuple[JudgedQuery, ...]
    #: Has someone read every pooled candidate against its question? This is a
    #: reading-comprehension pass and needs no clinical training, so it can be
    #: true while ``reviewed`` is false.
    reading_pass_complete: bool = False

    def __len__(self) -> int:
        return len(self.queries)

    def grades(self) -> dict[str, Mapping[str, int]]:
        return {q.id: q.grades for q in self.queries}

    @property
    def caveat(self) -> str:
        """What must be printed beside any number computed from this set.

        The two tiers do not fall together. Recall, precision and MRR only ask
        whether a document is relevant at all, so they rest on the reading
        pass. nDCG weights by grade, so it rests on the clinical one.
        """
        if self.reviewed:
            return "Judgments reviewed by a clinician."
        if self.reading_pass_complete:
            return (
                "Reading pass complete, clinical review outstanding.\n"
                "  recall / precision / MRR  rest on 'does this text answer the "
                "question', which the reading pass settles.\n"
                "  nDCG                      weights by the essential/useful "
                "grade, which only a clinician can set. Still provisional."
            )
        return (
            "PROVISIONAL — no reading pass and no clinical review. "
            "Treat every figure below as indicative, not established."
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JudgmentSet:
        if data.get("schema") != 1:
            raise JudgmentError(f"unsupported judgment schema {data.get('schema')!r}")
        queries: list[JudgedQuery] = []
        seen: set[str] = set()
        for raw in data.get("queries", ()):
            query_id = raw.get("id")
            if not query_id:
                raise JudgmentError("every query needs an id")
            if query_id in seen:
                raise JudgmentError(f"duplicate query id {query_id!r}")
            seen.add(query_id)

            grades: dict[str, int] = {}
            for doc_id, grade in (raw.get("judgments") or {}).items():
                if not isinstance(grade, int) or not 0 <= grade <= 2:
                    raise JudgmentError(
                        f"{query_id}/{doc_id}: grade must be 0, 1 or 2, got {grade!r}"
                    )
                if grade:
                    grades[doc_id] = grade
            queries.append(
                JudgedQuery(
                    id=query_id,
                    question=raw.get("question", ""),
                    patient_id=raw.get("patient_id"),
                    grades=grades,
                    rationale=raw.get("rationale", ""),
                )
            )
        if not queries:
            raise JudgmentError("the judgment set is empty")
        return cls(
            corpus=data.get("corpus", "guidelines"),
            reviewed=bool(data.get("reviewed")),
            queries=tuple(queries),
            reading_pass_complete=bool(data.get("reading_pass_complete")),
        )

    @classmethod
    def load(cls, path: str | Path | None = None) -> JudgmentSet:
        if path is None:
            text = (
                resources.files("brahmo.ir") / "data" / "judgments.json"
            ).read_text(encoding="utf-8")
        else:
            text = Path(path).read_text(encoding="utf-8")
        return cls.from_dict(json.loads(text))

    def validate_against(self, known_ids: frozenset[str]) -> list[str]:
        """Judgments naming a document that is not in the corpus.

        A typo in a document id silently becomes an unreachable relevant
        document, which looks exactly like a retriever failure.
        """
        return sorted(
            f"{q.id} -> {doc_id}"
            for q in self.queries
            for doc_id in q.grades
            if doc_id not in known_ids
        )
