"""Request and response shapes for the HTTP layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from brahmo.domain.patient import Patient


class PatientRef(BaseModel):
    """Either a seeded patient by id, or a whole record inline.

    Exactly one must be given. Accepting both and silently preferring one is
    how a caller ends up reading a report for a patient they did not send.
    """

    model_config = ConfigDict(extra="forbid")

    patient_id: int | None = None
    patient: dict[str, Any] | None = None

    def resolve(self, lookup) -> Patient:
        from fastapi import HTTPException

        if (self.patient_id is None) == (self.patient is None):
            raise HTTPException(
                status_code=422,
                detail="send exactly one of patient_id or patient",
            )
        if self.patient is not None:
            return Patient.model_validate(self.patient)
        found = lookup(self.patient_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"no patient {self.patient_id}")
        return found


class ComposeRequest(PatientRef):
    question: str = Field(min_length=1, max_length=4000)


class ConsultRequest(ComposeRequest):
    include_generic: bool = Field(
        default=True,
        description="Also answer the un-grounded contrast prompt, for A/B comparison.",
    )


class PatientSummary(BaseModel):
    id: int
    patient_label: str
    age: float
    sex: str
    conditions: list[str]
    medication_count: int

    @classmethod
    def of(cls, patient: Patient) -> PatientSummary:
        return cls(
            id=patient.id,
            patient_label=patient.patient_label,
            age=patient.age,
            sex=patient.sex,
            conditions=patient.conditions,
            medication_count=len(patient.medications),
        )


class Health(BaseModel):
    status: str
    corpus: dict[str, int]
    model: str
    safety_path_calls_model: bool = Field(
        default=False,
        description=(
            "Always false. The safety verdict is reached before any model is "
            "consulted; the test suite enforces it by blocking sockets."
        ),
    )
