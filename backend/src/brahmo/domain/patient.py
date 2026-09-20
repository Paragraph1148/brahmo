"""The patient record.

Labs arrive as a loose JSONB bag, so the raw mapping is preserved as-is and
the values the rules actually branch on are exposed as typed
:class:`~brahmo.domain.quantity.Quantity` accessors. A rule that reads
``patient.creatinine`` cannot silently compare mg/dL against umol/L; one that
reaches into ``patient.labs`` directly is opting out, and should say why.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from brahmo.domain.allergy import AllergyList
from brahmo.domain.quantity import Quantity, Unit

Sex = Literal["M", "F", "Other"]


class Medication(BaseModel):
    model_config = ConfigDict(frozen=True)

    drug: str
    dose: str = ""
    drug_id: int | None = None


def _as_float(value: Any) -> float | None:
    """Labs come from JSONB and a number may arrive as a string."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if parsed != parsed else parsed


class Patient(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    patient_label: str = ""
    age: float
    sex: Sex = "Other"
    bmi: float | None = None
    conditions: list[str] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    allergies_raw: list[str] = Field(default_factory=list, alias="allergies")
    labs: dict[str, Any] = Field(default_factory=dict)
    vitals: dict[str, Any] = Field(default_factory=dict)
    insurance: dict[str, Any] = Field(default_factory=dict)
    income_context: str = ""

    @field_validator("bmi", mode="before")
    @classmethod
    def _coerce_bmi(cls, v: Any) -> Any:
        return _as_float(v)

    @property
    def allergies(self) -> AllergyList:
        """Allergies as addressable records. See :mod:`brahmo.domain.allergy`."""
        return AllergyList(self.allergies_raw)

    # -- typed lab accessors ------------------------------------------------

    @property
    def creatinine(self) -> Quantity | None:
        value = _as_float(self.labs.get("Cr"))
        return None if value is None else Quantity(value, Unit.MG_DL)

    @property
    def potassium(self) -> Quantity | None:
        value = _as_float(self.labs.get("K"))
        return None if value is None else Quantity(value, Unit.MEQ_L)

    @property
    def hba1c(self) -> Quantity | None:
        value = _as_float(self.labs.get("HbA1c"))
        return None if value is None else Quantity(value, Unit.HBA1C_PERCENT)

    @property
    def reported_egfr(self) -> float | None:
        """A pre-computed eGFR from the lab, used only when creatinine is absent."""
        return _as_float(self.labs.get("eGFR"))

    def lab(self, key: str) -> float | None:
        """Any other lab, as a number when it parses as one."""
        return _as_float(self.labs.get(key))
