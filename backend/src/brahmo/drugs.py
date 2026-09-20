"""The drug formulary, and resolving a written medication to a row in it.

Two changes from the TypeScript.

**Ambiguity is not resolved by luck.** ``resolveMedications`` falls back to a
prefix match and takes the first hit while iterating a map built from
``select * from drugs`` — a query with no ``ORDER BY``, so the winner is
whatever order the rows come back in. The seed holds three insulins
(``Insulin Glargine``, ``Insulin Human 30/70``, ``Insulin Regular``), and a
medication written as plain ``Insulin`` prefix-matches all three. In practice
the determinism test passes because Postgres returns the seed rows in a stable
physical order; that is luck, not a guarantee, and the drug it picks decides
which renal band and which interactions get checked. Here a prefix match
resolves only when it is unique, and ambiguity is reported.

**An unresolved medication is reported, not skipped.** Every checker in the
TypeScript begins ``if (!m.drug_id) continue``, so a drug the resolver could
not identify is checked for nothing: no renal dosing, no HF contraindication,
no interactions. The report comes back clean and the reason it is clean is
that the engine never looked. That is the silent-failure class this project
exists to catch, so resolution failure raises a flag of its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Sequence

from brahmo.domain.patient import Medication

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def normalize(name: str) -> str:
    """Lowercase, strip everything that is not a letter or digit."""
    return _NON_ALNUM.sub("", name.lower())


@dataclass(frozen=True, slots=True)
class Drug:
    id: int
    generic_name: str
    generic_name_normalized: str
    drug_class: str
    drug_subclass: str | None
    indian_brand_name: str
    manufacturer: str
    mrp_price: Decimal | None
    nlem_status: bool
    renal_dosing: dict[str, str]
    hf_safe: bool | None
    weight_effect: str
    hypoglycemia_risk: str
    condition_tags: tuple[str, ...]
    source_url: str | None
    notes: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Drug:
        return cls(
            id=int(row["id"]),
            generic_name=row["generic_name"],
            generic_name_normalized=row.get("generic_name_normalized") or row["generic_name"],
            drug_class=row.get("drug_class") or "",
            drug_subclass=row.get("drug_subclass"),
            indian_brand_name=row.get("indian_brand_name") or "",
            manufacturer=row.get("manufacturer") or "",
            mrp_price=_as_money(row.get("mrp_price")),
            nlem_status=bool(row.get("nlem_status")),
            renal_dosing=dict(row.get("renal_dosing") or {}),
            hf_safe=row.get("hf_safe"),
            weight_effect=row.get("weight_effect") or "",
            hypoglycemia_risk=row.get("hypoglycemia_risk") or "",
            condition_tags=tuple(row.get("condition_tags") or ()),
            source_url=row.get("source_url"),
            notes=row.get("notes"),
        )


def _as_money(value: Any) -> Decimal | None:
    """Prices are money, so they are Decimal.

    The TypeScript carries ``mrp_price`` as a string and parses it with
    ``Number`` at the point of display. Binary floating point cannot represent
    most rupee amounts exactly, and this system's whole argument is about cost.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class Resolution(Enum):
    EXACT = "exact"
    PREFIX_UNIQUE = "prefix_unique"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ResolvedMedication:
    """A written medication and what, if anything, it was matched to."""

    medication: Medication
    drug: Drug | None
    resolution: Resolution
    candidates: tuple[Drug, ...] = ()

    @property
    def is_checkable(self) -> bool:
        """Can the safety checkers do anything with this medication?"""
        return self.drug is not None

    @property
    def name(self) -> str:
        return self.drug.generic_name if self.drug else self.medication.drug


class Formulary:
    """The drug table, indexed for resolution."""

    def __init__(self, drugs: Iterable[Drug]) -> None:
        self._drugs = tuple(sorted(drugs, key=lambda d: d.id))
        self._by_id = {d.id: d for d in self._drugs}
        self._exact: dict[str, set[int]] = {}
        for drug in self._drugs:
            for name in (drug.generic_name, drug.generic_name_normalized):
                self._exact.setdefault(normalize(name), set()).add(drug.id)

    @classmethod
    def from_rows(cls, rows: Iterable[dict[str, Any]]) -> Formulary:
        return cls(Drug.from_row(r) for r in rows)

    def __len__(self) -> int:
        return len(self._drugs)

    def __iter__(self):
        return iter(self._drugs)

    def by_id(self, drug_id: int) -> Drug | None:
        return self._by_id.get(drug_id)

    def resolve(self, medication: Medication) -> ResolvedMedication:
        key = normalize(medication.drug)
        if not key:
            return ResolvedMedication(medication, None, Resolution.UNKNOWN)

        exact = self._exact.get(key)
        if exact:
            # Two rows sharing a normalized name is a data problem, not a
            # resolution problem; lowest id wins and is deterministic.
            drug = self._by_id[min(exact)]
            return ResolvedMedication(medication, drug, Resolution.EXACT)

        candidate_ids: set[int] = set()
        for name, ids in self._exact.items():
            if name.startswith(key) or key.startswith(name):
                candidate_ids |= ids
        candidates = tuple(self._by_id[i] for i in sorted(candidate_ids))

        if len(candidates) == 1:
            return ResolvedMedication(
                medication, candidates[0], Resolution.PREFIX_UNIQUE, candidates
            )
        if candidates:
            return ResolvedMedication(medication, None, Resolution.AMBIGUOUS, candidates)
        return ResolvedMedication(medication, None, Resolution.UNKNOWN)

    def resolve_all(self, medications: Sequence[Medication]) -> tuple[ResolvedMedication, ...]:
        return tuple(self.resolve(m) for m in medications)
