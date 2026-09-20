"""Typed clinical quantities.

The TypeScript implementation carries lab values as bare ``number`` with the
unit implied by the field name (``Cr`` is mg/dL because we say so). That is the
failure mode this project already knows well: it is silent. A creatinine of 88
is a normal value in umol/L and catastrophic in mg/dL, and nothing in a float
distinguishes them.

Here a lab value knows its unit, conversion is explicit, and a comparison
across incompatible dimensions raises rather than quietly producing a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class Dimension(Enum):
    """What a unit measures. Comparisons only make sense within a dimension."""

    CONCENTRATION_MASS = "concentration_mass"
    GLUCOSE = "glucose"
    HBA1C = "hba1c"
    ELECTROLYTE = "electrolyte"
    GFR = "gfr"
    RATIO = "ratio"
    DIMENSIONLESS = "dimensionless"


class Unit(Enum):
    """Units this system actually handles. Deliberately not a general unit library."""

    MG_DL = ("mg/dL", Dimension.CONCENTRATION_MASS)
    UMOL_L = ("umol/L", Dimension.CONCENTRATION_MASS)

    GLUCOSE_MG_DL = ("mg/dL (glucose)", Dimension.GLUCOSE)
    GLUCOSE_MMOL_L = ("mmol/L (glucose)", Dimension.GLUCOSE)

    HBA1C_PERCENT = ("% (DCCT)", Dimension.HBA1C)
    HBA1C_MMOL_MOL = ("mmol/mol (IFCC)", Dimension.HBA1C)

    MEQ_L = ("mEq/L", Dimension.ELECTROLYTE)
    MMOL_L = ("mmol/L", Dimension.ELECTROLYTE)

    ML_MIN_1_73 = ("mL/min/1.73m2", Dimension.GFR)
    MG_G = ("mg/g", Dimension.RATIO)
    COUNT = ("", Dimension.DIMENSIONLESS)

    def __init__(self, symbol: str, dimension: Dimension) -> None:
        self.symbol = symbol
        self.dimension = dimension


# Factors to each dimension's canonical unit. Canonical is the unit Indian labs
# report in, so the common path is a multiply by 1.0 and the values that reach
# the rules are bit-identical to the TypeScript implementation's.
_TO_CANONICAL: Final[dict[Unit, float]] = {
    Unit.MG_DL: 1.0,
    Unit.UMOL_L: 1.0 / 88.4,            # creatinine umol/L -> mg/dL
    Unit.GLUCOSE_MG_DL: 1.0,
    Unit.GLUCOSE_MMOL_L: 18.0182,       # mmol/L -> mg/dL
    Unit.HBA1C_PERCENT: 1.0,
    Unit.HBA1C_MMOL_MOL: 0.0,           # affine, handled in _convert
    Unit.MEQ_L: 1.0,
    Unit.MMOL_L: 1.0,                   # monovalent ions: 1 mEq/L == 1 mmol/L
    Unit.ML_MIN_1_73: 1.0,
    Unit.MG_G: 1.0,
    Unit.COUNT: 1.0,
}

_CANONICAL: Final[dict[Dimension, Unit]] = {
    Dimension.CONCENTRATION_MASS: Unit.MG_DL,
    Dimension.GLUCOSE: Unit.GLUCOSE_MG_DL,
    Dimension.HBA1C: Unit.HBA1C_PERCENT,
    Dimension.ELECTROLYTE: Unit.MEQ_L,
    Dimension.GFR: Unit.ML_MIN_1_73,
    Dimension.RATIO: Unit.MG_G,
    Dimension.DIMENSIONLESS: Unit.COUNT,
}


class DimensionMismatch(TypeError):
    """Raised when two quantities measuring different things are compared."""


@dataclass(frozen=True, slots=True)
class Quantity:
    """A value that knows what it measures and in what unit."""

    value: float
    unit: Unit

    def __post_init__(self) -> None:
        if self.value != self.value:  # NaN
            raise ValueError("quantity value is NaN")

    @property
    def dimension(self) -> Dimension:
        return self.unit.dimension

    def to(self, unit: Unit) -> Quantity:
        if unit.dimension is not self.unit.dimension:
            raise DimensionMismatch(
                f"cannot convert {self.unit.symbol} ({self.unit.dimension.value}) "
                f"to {unit.symbol} ({unit.dimension.value})"
            )
        if unit is self.unit:
            return self
        canonical = _to_canonical_value(self)
        return Quantity(_from_canonical_value(canonical, unit), unit)

    @property
    def canonical(self) -> float:
        """The value in this dimension's canonical unit, for rule evaluation."""
        return _to_canonical_value(self)

    def _cmp_operand(self, other: Quantity) -> float:
        if not isinstance(other, Quantity):
            raise DimensionMismatch(f"cannot compare Quantity with {type(other).__name__}")
        if other.dimension is not self.dimension:
            raise DimensionMismatch(
                f"cannot compare {self.unit.dimension.value} with {other.dimension.value}"
            )
        return other.canonical

    def __lt__(self, other: Quantity) -> bool:
        return self.canonical < self._cmp_operand(other)

    def __le__(self, other: Quantity) -> bool:
        return self.canonical <= self._cmp_operand(other)

    def __gt__(self, other: Quantity) -> bool:
        return self.canonical > self._cmp_operand(other)

    def __ge__(self, other: Quantity) -> bool:
        return self.canonical >= self._cmp_operand(other)

    def __str__(self) -> str:
        return f"{self.value:g} {self.unit.symbol}".strip()


def _to_canonical_value(q: Quantity) -> float:
    if q.unit is Unit.HBA1C_MMOL_MOL:
        return q.value / 10.929 + 2.15          # IFCC -> DCCT %
    return q.value * _TO_CANONICAL[q.unit]


def _from_canonical_value(value: float, unit: Unit) -> float:
    if unit is Unit.HBA1C_MMOL_MOL:
        return (value - 2.15) * 10.929
    return value / _TO_CANONICAL[unit]


def canonical_unit(dimension: Dimension) -> Unit:
    return _CANONICAL[dimension]
