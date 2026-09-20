"""Drug-drug interactions.

An interaction may have a non-formulary substance on one side — alcohol,
NSAIDs, IV contrast — recorded as a name with a null id. Those fire against a
single patient drug; formulary-to-formulary pairs need both ends present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from brahmo.report import Severity

#: Interaction severity as recorded in the table, mapped onto flag severity.
_SEVERITY = {
    "minor": Severity.INFO,
    "moderate": Severity.CAUTION,
    "severe": Severity.WARNING,
    "contraindicated": Severity.CRITICAL,
}


@dataclass(frozen=True, slots=True)
class DrugInteraction:
    id: int
    drug_a_id: int | None
    drug_a_name: str | None
    drug_b_id: int | None
    drug_b_name: str | None
    severity: str
    mechanism: str
    clinical_effect: str
    management: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DrugInteraction:
        return cls(
            id=int(row["id"]),
            drug_a_id=None if row.get("drug_a_id") is None else int(row["drug_a_id"]),
            drug_a_name=row.get("drug_a_name"),
            drug_b_id=None if row.get("drug_b_id") is None else int(row["drug_b_id"]),
            drug_b_name=row.get("drug_b_name"),
            severity=row.get("severity") or "moderate",
            mechanism=row.get("mechanism") or "",
            clinical_effect=row.get("clinical_effect") or "",
            management=row.get("management") or "",
        )

    @property
    def flag_severity(self) -> Severity:
        return _SEVERITY.get(self.severity, Severity.CAUTION)

    def fires_for(self, drug_ids: frozenset[int]) -> bool:
        """Does this interaction apply to a patient on these formulary drugs?

        ``drug_id is None`` rather than a falsy test throughout: the TypeScript
        filters ids with ``!!id`` and ``!m.drug_id``, which also discards id 0.
        Postgres serials start at 1 so nothing is lost today, but a formulary
        loaded from anywhere else would lose a drug silently.
        """
        a_present = self.drug_a_id is not None and self.drug_a_id in drug_ids
        b_present = self.drug_b_id is not None and self.drug_b_id in drug_ids
        a_substance = self.drug_a_id is None and bool(self.drug_a_name)
        b_substance = self.drug_b_id is None and bool(self.drug_b_name)
        return (a_present and b_present) or (a_present and b_substance) or (b_present and a_substance)


class InteractionTable:
    def __init__(self, interactions: Iterable[DrugInteraction]) -> None:
        self._rows = tuple(sorted(interactions, key=lambda i: i.id))

    @classmethod
    def from_rows(cls, rows: Iterable[dict[str, Any]]) -> InteractionTable:
        return cls(DrugInteraction.from_row(r) for r in rows)

    def __len__(self) -> int:
        return len(self._rows)

    def firing_for(self, drug_ids: frozenset[int]) -> tuple[DrugInteraction, ...]:
        """Interactions applying to this drug set, in stable id order."""
        if len(drug_ids) < 1:
            return ()
        return tuple(i for i in self._rows if i.fires_for(drug_ids))
