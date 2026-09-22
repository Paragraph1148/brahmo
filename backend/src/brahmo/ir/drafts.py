"""Drafted questions that have no judgments yet.

Kept apart from :mod:`brahmo.ir.judgments` on purpose. A question with no
grades cannot be scored, and letting the two share a file invites a run that
silently evaluates over whichever subset happens to be labelled.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DraftQuestion:
    id: str
    question: str
    patient_id: int | None
    probes: str = ""


@dataclass(frozen=True, slots=True)
class DraftSet:
    status: str
    questions: tuple[DraftQuestion, ...]

    def __len__(self) -> int:
        return len(self.questions)

    @classmethod
    def load(cls, path: str | Path | None = None) -> DraftSet:
        if path is None:
            text = (
                resources.files("brahmo.ir") / "data" / "questions_draft.json"
            ).read_text(encoding="utf-8")
        else:
            text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text)
        seen: set[str] = set()
        questions: list[DraftQuestion] = []
        for raw in data.get("questions", ()):
            if raw["id"] in seen:
                raise ValueError(f"duplicate draft id {raw['id']!r}")
            seen.add(raw["id"])
            questions.append(
                DraftQuestion(
                    id=raw["id"],
                    question=raw["question"],
                    patient_id=raw.get("patient_id"),
                    probes=raw.get("probes", ""),
                )
            )
        return cls(status=data.get("status", "needs_labels"), questions=tuple(questions))
