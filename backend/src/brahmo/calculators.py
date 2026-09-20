"""Clinical calculators — pure functions, no I/O.

Ported from ``src/lib/calculators.ts``. Numerically faithful to it: the
differential suite asserts these agree with the TypeScript originals across
fuzzed inputs, so any deliberate divergence has to be argued for here rather
than discovered later.

The one place the two languages disagree by default is rounding. JavaScript's
``Math.round`` is half-up toward positive infinity; Python's builtin ``round``
is banker's rounding, so ``round(2.5) == 2`` where ``Math.round(2.5) === 3``.
An eGFR landing exactly on .5 is not rare across a fuzzed range, and silently
reporting 44 instead of 45 moves a patient across the CKD 3a/3b boundary and
changes which renal dosing band applies. Hence :func:`js_round`.
"""

from __future__ import annotations

import math
from typing import Literal, NamedTuple

from brahmo.domain.quantity import Dimension, Quantity

Sex = Literal["M", "F", "Other"]


def js_round(x: float) -> int:
    """JavaScript ``Math.round`` semantics: halves go toward positive infinity.

    ``js_round(2.5) == 3`` and ``js_round(-2.5) == -2``, matching JS, where
    Python's ``round`` would give 2 and -2.
    """
    if math.isnan(x) or math.isinf(x):
        raise ValueError(f"cannot round {x}")
    return math.floor(x + 0.5)


def egfr_exact(creatinine_mg_dl: float | None, age: float, sex: Sex) -> float | None:
    """eGFR by CKD-EPI 2021 (race-free), unrounded.

    Inker LA et al. NEJM 2021;385:1737-1749::

        eGFR = 142 * min(Scr/k, 1)^a * max(Scr/k, 1)^-1.200 * 0.9938^age * (1.012 if female)

    This is the value every downstream band comparison uses. See
    :func:`calculate_egfr` for why the rounded one is display-only.
    """
    if creatinine_mg_dl is None or age is None:
        return None
    if math.isnan(creatinine_mg_dl) or math.isnan(age):
        return None
    if creatinine_mg_dl <= 0 or age <= 0:
        return None

    is_female = sex == "F"
    kappa = 0.7 if is_female else 0.9
    alpha = -0.241 if is_female else -0.302
    sex_factor = 1.012 if is_female else 1.0

    scr_ratio = creatinine_mg_dl / kappa
    min_term = min(scr_ratio, 1.0) ** alpha
    max_term = max(scr_ratio, 1.0) ** -1.2
    age_factor = 0.9938**age

    egfr = 142 * min_term * max_term * age_factor * sex_factor
    if math.isinf(egfr) or math.isnan(egfr):
        return None
    return egfr


def calculate_egfr(creatinine_mg_dl: float | None, age: float, sex: Sex) -> int | None:
    """eGFR rounded to an integer, **for display and for parity with the original only**.

    The TypeScript implementation rounds here and then feeds the *rounded*
    value to :func:`ckd_stage` and :func:`egfr_bucket`. That makes a clinical
    band depend on the last bit of a transcendental function, and the two
    runtimes do not agree on that bit: ``Math.pow(2.332552743738428, -1.2)`` is
    ``0.36191137440250265`` in V8 and ``0.3619113744025026`` in CPython, one ulp
    apart. Neither language promises a correctly-rounded ``pow``, so this is not
    something a careful port can eliminate.

    Propagated, that ulp put one fuzzed patient's raw eGFR at exactly 46.5 in
    JavaScript and 46.49999999999999 in Python — 47 against 46. Harmless there,
    because both sit inside CKD 3a. At a true eGFR near 44.5 the same ulp
    decides CKD 3a against CKD 3b, and with it which renal dosing band applies.

    So nothing downstream may consume this number. Bands read
    :func:`egfr_exact`; this exists to render "eGFR 46" on a screen and to let
    the differential suite compare like with like.
    """
    egfr = egfr_exact(creatinine_mg_dl, age, sex)
    return None if egfr is None else js_round(egfr)


def egfr_from_quantity(creatinine: Quantity | None, age: float, sex: Sex) -> float | None:
    """Typed entry point: accepts creatinine in any mass-concentration unit.

    Returns the unrounded value, because that is what the bands must read.
    """
    if creatinine is None:
        return None
    if creatinine.dimension is not Dimension.CONCENTRATION_MASS:
        raise TypeError(f"creatinine must be a mass concentration, got {creatinine.unit.symbol}")
    return egfr_exact(creatinine.canonical, age, sex)


def ckd_stage(egfr: int | float | None) -> str | None:
    """KDIGO 2012 stage from eGFR."""
    if egfr is None:
        return None
    if egfr >= 90:
        return "Normal (G1)"
    if egfr >= 60:
        return "G2"
    if egfr >= 45:
        return "CKD 3a"
    if egfr >= 30:
        return "CKD 3b"
    if egfr >= 15:
        return "CKD 4"
    return "CKD 5"


def egfr_bucket(egfr: int | float | None) -> list[str]:
    """Every ``renal_dosing`` JSONB key whose band contains this eGFR.

    Order is preserved from the TypeScript for faithfulness, but only
    membership is load-bearing — :func:`renal_dose_instruction` imposes its own
    precedence.
    """
    if egfr is None:
        return ["egfr_all"]
    buckets = ["egfr_all"]
    for threshold, key in (
        (60, "egfr_60_plus"),
        (50, "egfr_50_plus"),
        (45, "egfr_45_plus"),
        (30, "egfr_30_plus"),
        (25, "egfr_25_plus"),
        (20, "egfr_20_plus"),
        (15, "egfr_15_plus"),
    ):
        if egfr >= threshold:
            buckets.append(key)
    for lo, hi, key in (
        (30, 60, "egfr_30_60"),
        (30, 45, "egfr_30_45"),
        (15, 50, "egfr_15_50"),
        (45, 60, "egfr_45_60"),
    ):
        if lo <= egfr < hi:
            buckets.append(key)
    for threshold, key in (
        (60, "egfr_below_60"),
        (50, "egfr_below_50"),
        (45, "egfr_below_45"),
        (30, "egfr_below_30"),
        (25, "egfr_below_25"),
        (20, "egfr_below_20"),
        (15, "egfr_below_15"),
    ):
        if egfr < threshold:
            buckets.append(key)
    return buckets


#: Narrowest band first. A drug listing both ``egfr_below_30`` and ``egfr_all``
#: means the former for a patient at 28, and the fallback only for everyone else.
RENAL_PRIORITY: tuple[str, ...] = (
    "egfr_below_15",
    "egfr_below_20",
    "egfr_below_25",
    "egfr_below_30",
    "egfr_below_45",
    "egfr_below_50",
    "egfr_below_60",
    "egfr_15_50",
    "egfr_30_45",
    "egfr_30_60",
    "egfr_45_60",
    "egfr_15_plus",
    "egfr_20_plus",
    "egfr_25_plus",
    "egfr_30_plus",
    "egfr_45_plus",
    "egfr_50_plus",
    "egfr_60_plus",
    "egfr_all",
)


def renal_dose_instruction(
    renal_dosing: dict[str, str] | None, egfr: int | float | None
) -> str | None:
    """Renal dosing text for this eGFR, narrowest matching band winning."""
    if not renal_dosing:
        return None
    buckets = set(egfr_bucket(egfr))
    for key in RENAL_PRIORITY:
        if key in buckets and key in renal_dosing:
            return renal_dosing[key]
    return renal_dosing.get("egfr_all")


class ChadsVascInputs(NamedTuple):
    has_hf: bool
    has_htn: bool
    age: float
    has_diabetes: bool
    has_prior_stroke: bool
    has_vascular_disease: bool
    sex: Sex


def calculate_chads_vasc(i: ChadsVascInputs) -> int:
    """CHA2DS2-VASc stroke risk score for atrial fibrillation."""
    score = 0
    if i.has_hf:
        score += 1
    if i.has_htn:
        score += 1
    if i.age >= 75:
        score += 2
    elif i.age >= 65:
        score += 1
    if i.has_diabetes:
        score += 1
    if i.has_prior_stroke:
        score += 2
    if i.has_vascular_disease:
        score += 1
    if i.sex == "F":
        score += 1
    return score


def should_anticoagulate(score: int, sex: Sex) -> bool:
    """IHRS/CSI 2018: OAC indicated at >=2 in men, >=3 in women."""
    return score >= 3 if sex == "F" else score >= 2


def bmi_category(bmi: float) -> str:
    """WHO Asian-Pacific cutoffs. Lancet 2004;363:157-163."""
    if bmi < 18.5:
        return "Underweight"
    if bmi < 23.0:
        return "Normal"
    if bmi < 25.0:
        return "Overweight (Asian)"
    if bmi < 30.0:
        return "Obese I (Asian)"
    return "Obese II (Asian)"
