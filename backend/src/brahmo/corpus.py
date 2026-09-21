"""Loading the reference data the engine and composer run on.

The rows originate from ``supabase/schema.sql`` and ``supabase/seed.sql``,
exported through PGlite by ``npm run fixtures``. Keeping the load behind one
class means the service does not care where they came from: a Postgres-backed
loader is a second classmethod, not a change to anything downstream.

Nothing here reaches the network, and neither does anything it builds. That is
what lets :mod:`brahmo.api` assert the safety path is model-free at the service
boundary rather than in a comment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Iterable, Sequence

from brahmo import response_instructions
from brahmo.composer import Composer
from brahmo.domain.patient import Patient
from brahmo.drugs import Formulary
from brahmo.engine import Engine
from brahmo.interactions import InteractionTable
from brahmo.retrieval import GuidelineLibrary, HospitalFormulary

#: Files ``npm run fixtures`` writes, and what each one feeds.
FIXTURE_FILES = (
    "drugs.json",
    "drug_interactions.json",
    "indian_guidelines.json",
    "hospital_formulary.json",
    "patients.json",
)


class CorpusError(RuntimeError):
    """The reference data is missing or unreadable."""


@dataclass(frozen=True)
class Corpus:
    """Every row the deterministic layer needs, loaded once."""

    drugs: tuple[dict[str, Any], ...]
    interactions: tuple[dict[str, Any], ...]
    guidelines: tuple[dict[str, Any], ...]
    stock: tuple[dict[str, Any], ...]
    patients: tuple[dict[str, Any], ...]

    @classmethod
    def from_json_dir(cls, directory: str | Path) -> Corpus:
        path = Path(directory)
        missing = [f for f in FIXTURE_FILES if not (path / f).is_file()]
        if missing:
            raise CorpusError(
                f"{path} is missing {', '.join(missing)} — run `npm run fixtures` "
                "at the repository root to export them from schema.sql + seed.sql"
            )

        def rows(name: str) -> tuple[dict[str, Any], ...]:
            try:
                loaded = json.loads((path / name).read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise CorpusError(f"{path / name} is not valid JSON: {exc}") from exc
            if not isinstance(loaded, list):
                raise CorpusError(f"{path / name} should hold a list of rows")
            return tuple(loaded)

        return cls(
            drugs=rows("drugs.json"),
            interactions=rows("drug_interactions.json"),
            guidelines=rows("indian_guidelines.json"),
            stock=rows("hospital_formulary.json"),
            patients=rows("patients.json"),
        )

    @classmethod
    def from_rows(
        cls,
        *,
        drugs: Iterable[dict[str, Any]] = (),
        interactions: Iterable[dict[str, Any]] = (),
        guidelines: Iterable[dict[str, Any]] = (),
        stock: Iterable[dict[str, Any]] = (),
        patients: Iterable[dict[str, Any]] = (),
    ) -> Corpus:
        """For tests that want a corpus of exactly N rows."""
        return cls(
            drugs=tuple(drugs),
            interactions=tuple(interactions),
            guidelines=tuple(guidelines),
            stock=tuple(stock),
            patients=tuple(patients),
        )

    @cached_property
    def formulary(self) -> Formulary:
        return Formulary.from_rows(self.drugs)

    @cached_property
    def engine(self) -> Engine:
        return Engine(
            formulary=self.formulary,
            interactions=InteractionTable.from_rows(self.interactions),
        )

    @cached_property
    def composer(self) -> Composer:
        return Composer(
            formulary=self.formulary,
            guidelines=GuidelineLibrary.from_rows(self.guidelines),
            stock=HospitalFormulary(self.stock),
            instructions=response_instructions(),
        )

    @cached_property
    def seeded_patients(self) -> tuple[Patient, ...]:
        return tuple(
            Patient.model_validate(row) for row in sorted(self.patients, key=lambda r: r["id"])
        )

    def patient(self, patient_id: int) -> Patient | None:
        return next((p for p in self.seeded_patients if p.id == patient_id), None)

    def describe(self) -> dict[str, int]:
        """Row counts, for the health endpoint."""
        return {
            "drugs": len(self.drugs),
            "interactions": len(self.interactions),
            "guidelines": len(self.guidelines),
            "formulary_entries": len(self.stock),
            "seeded_patients": len(self.patients),
        }


def default_fixture_dir() -> Path:
    """``<repo>/tests/fixtures``, relative to this package."""
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def load_default(directories: Sequence[str | Path] | None = None) -> Corpus:
    """The corpus the service runs on unless told otherwise."""
    for candidate in directories or (default_fixture_dir(),):
        try:
            return Corpus.from_json_dir(candidate)
        except CorpusError:
            continue
    raise CorpusError(
        "no usable fixture directory found; set BRAHMO_FIXTURES to the directory "
        "holding drugs.json and friends"
    )
