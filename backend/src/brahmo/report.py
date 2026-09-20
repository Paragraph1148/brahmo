"""The safety report, and the provenance every flag carries.

The TypeScript flag says *what*. It does not say why, beyond prose, and there
is no machine-readable record of which rule fired or which patient fields it
read. That is the gap that makes "check the retrieval layer never contradicts a
deterministic flag" impossible to implement: you cannot check a verdict against
a basis it does not state.

So a flag here names its rule, the inputs it read, and the guideline it rests
on. It also makes the report auditable in the plain sense — a clinician can ask
why a flag fired and get an answer that is not a paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    CAUTION = "caution"
    INFO = "info"

    @property
    def rank(self) -> int:
        return _SEVERITY_ORDER[self]


_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.WARNING: 1,
    Severity.CAUTION: 2,
    Severity.INFO: 3,
}


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a flag came from."""

    rule_id: str
    inputs: tuple[str, ...] = ()
    basis: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "inputs": list(self.inputs), "basis": self.basis}


@dataclass(frozen=True, slots=True)
class SafetyFlag:
    category: str
    severity: Severity
    title: str
    detail: str
    provenance: Provenance
    drugs_involved: tuple[str, ...] = ()
    action: str | None = None
    guideline_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity.value,
            "title": self.title,
            "detail": self.detail,
            "drugs_involved": list(self.drugs_involved),
            "action": self.action,
            "guideline_source": self.guideline_source,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ComputedValues:
    egfr: float | None
    egfr_display: int | None
    egfr_stage: str | None
    chads_vasc: int | None
    bmi_category: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eGFR": self.egfr_display,
            "eGFR_exact": self.egfr,
            "eGFR_stage": self.egfr_stage,
            "chads_vasc": self.chads_vasc,
            "bmi_category": self.bmi_category,
        }


@dataclass(frozen=True, slots=True)
class AvoidEntry:
    drug: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"drug": self.drug, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class SafetyReport:
    patient_id: int
    computed: ComputedValues
    flags: tuple[SafetyFlag, ...] = ()
    recommended_drug_classes: tuple[str, ...] = ()
    drugs_to_avoid: tuple[AvoidEntry, ...] = ()
    unresolved_medications: tuple[str, ...] = field(default=())

    def by_severity(self, severity: Severity) -> tuple[SafetyFlag, ...]:
        return tuple(f for f in self.flags if f.severity is severity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "computed": self.computed.to_dict(),
            "flags": [f.to_dict() for f in self.flags],
            "recommended_drug_classes": list(self.recommended_drug_classes),
            "drugs_to_avoid": [d.to_dict() for d in self.drugs_to_avoid],
            "unresolved_medications": list(self.unresolved_medications),
        }
