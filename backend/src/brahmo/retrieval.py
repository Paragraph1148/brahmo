"""Selecting the guidelines and drugs a patient's prompt should carry.

Mirrors the ``guidelines_for_condition`` / ``drugs_for_condition`` SQL helpers,
which filter on JSONB key containment (``condition_tags ? tag``) and are called
once per derived tag with the results merged.

Ordering is explicit and locale-independent. The TypeScript re-sorts the merged
rows client-side with ``String.prototype.localeCompare`` and no locale
argument, which resolves against whatever locale the host happens to be in. It
is not a hypothetical hazard: locale collation is case-insensitive at the
primary level and code-point order is not, so the drug list already differs by
where the section breaks fall::

    localeCompare:  ### Alpha-glucosidase inhibitor  then  ### ARB
    code points:    ### ARB                          then  ### Alpha-glucosidase

Neither is wrong, but the prompt handed to the model should not depend on the
server's locale. :func:`collate` fixes an explicit key — case-folded first, so
the reading order matches what a clinician expects, then the exact string to
break ties that case-folding creates, then the id so the result is total.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Sequence

from brahmo.drugs import Drug, Formulary


def collate(text: str) -> tuple[str, str]:
    """A deterministic, locale-independent sort key that reads naturally.

    Case-folded first so "Alpha-glucosidase inhibitor" precedes "ARB" as a
    reader would expect, then the raw string so two entries differing only in
    case still have a stable order.
    """
    return (text.casefold(), text)


@dataclass(frozen=True, slots=True)
class Guideline:
    id: int
    source_id: str
    year: int
    condition: str
    section: str
    recommendation: str
    evidence_level: str | None
    condition_tags: tuple[str, ...]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Guideline:
        return cls(
            id=int(row["id"]),
            source_id=row.get("source_id") or "",
            year=int(row.get("year") or 0),
            condition=row.get("condition") or "",
            section=row.get("section") or "",
            recommendation=row.get("recommendation") or "",
            evidence_level=row.get("evidence_level"),
            condition_tags=tuple(row.get("condition_tags") or ()),
        )

    @property
    def source_label(self) -> str:
        return f"{self.source_id} {self.year}"


@dataclass(frozen=True, slots=True)
class StockedDrug:
    """A formulary drug with this hospital's stock position attached."""

    drug: Drug
    in_stock: bool
    stock_level: str | None
    pharmacy_notes: str | None

    @property
    def id(self) -> int:
        return self.drug.id

    @property
    def generic_name(self) -> str:
        return self.drug.generic_name

    @property
    def drug_class(self) -> str:
        return self.drug.drug_class

    @property
    def mrp_price(self) -> str:
        return self.drug.mrp_price


class GuidelineLibrary:
    def __init__(self, guidelines: Iterable[Guideline]) -> None:
        self._rows = tuple(guidelines)

    @classmethod
    def from_rows(cls, rows: Iterable[dict[str, Any]]) -> GuidelineLibrary:
        return cls(Guideline.from_row(r) for r in rows)

    def __len__(self) -> int:
        return len(self._rows)

    def for_tags(self, tags: Sequence[str]) -> tuple[Guideline, ...]:
        """Guidelines carrying any of these tags, newest source first.

        Sorted by year descending, then source id, then id — the same key the
        SQL helper uses, applied once over the merged set rather than per tag.
        """
        if not tags:
            return ()
        wanted = set(tags)
        hits = [g for g in self._rows if wanted & set(g.condition_tags)]
        hits.sort(key=lambda g: (-g.year, collate(g.source_id), g.id))
        return tuple(hits)


class HospitalFormulary:
    """Stock positions, keyed by drug id."""

    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        self._by_drug: dict[int, dict[str, Any]] = {}
        for row in rows:
            drug_id = row.get("drug_id")
            if drug_id is not None:
                self._by_drug[int(drug_id)] = row

    def attach(self, drug: Drug) -> StockedDrug:
        row = self._by_drug.get(drug.id)
        return StockedDrug(
            drug=drug,
            in_stock=bool(row.get("in_stock")) if row else False,
            stock_level=row.get("stock_level") if row else None,
            pharmacy_notes=row.get("pharmacy_notes") if row else None,
        )


def drugs_for_tags(
    formulary: Formulary, stock: HospitalFormulary, tags: Sequence[str]
) -> tuple[StockedDrug, ...]:
    """Formulary drugs carrying any of these tags, by class then generic name."""
    if not tags:
        return ()
    wanted = set(tags)
    hits = [d for d in formulary if wanted & set(d.condition_tags)]
    hits.sort(key=lambda d: (collate(d.drug_class), collate(d.generic_name), d.id))
    return tuple(stock.attach(d) for d in hits)
