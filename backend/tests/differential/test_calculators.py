"""Differential tests: the Python calculators against the live TypeScript ones.

Every test here runs the same input through both implementations and asserts
they agree. A failure means one of the two is wrong — and it is worth checking
which before assuming it is the port.

The strategies deliberately concentrate on band boundaries. Clinical thresholds
are where rounding, ``>=`` vs ``>`` and off-by-one errors actually change a
patient's care, and uniform random floats almost never land on them.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from brahmo.calculators import (
    RENAL_PRIORITY,
    egfr_exact,
    ChadsVascInputs,
    bmi_category,
    calculate_chads_vasc,
    calculate_egfr,
    ckd_stage,
    egfr_bucket,
    js_round,
    renal_dose_instruction,
    should_anticoagulate,
)
from tests.differential.bridge import TsBridge

# Session-scoped subprocess + function-scoped Hypothesis examples is exactly the
# pattern this health check warns about, and exactly what we want here.
DIFFERENTIAL = settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

SEXES = st.sampled_from(["M", "F", "Other"])

#: Every eGFR threshold the rules branch on, and the floats either side of it.
EGFR_EDGES = sorted(
    {
        v + delta
        for v in (0, 15, 20, 25, 30, 45, 50, 60, 90)
        for delta in (-0.5, -0.001, 0.0, 0.001, 0.5)
    }
)

egfr_values = st.one_of(
    st.sampled_from(EGFR_EDGES),
    st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    st.integers(min_value=0, max_value=200).map(float),
    st.none(),
)

creatinines = st.one_of(
    st.floats(min_value=0.1, max_value=20.0, allow_nan=False, allow_infinity=False),
    st.sampled_from([0.1, 0.5, 0.9, 1.0, 1.2, 2.0, 5.0, 11.3]),
)

ages = st.one_of(
    st.integers(min_value=1, max_value=120).map(float),
    st.floats(min_value=1.0, max_value=120.0, allow_nan=False, allow_infinity=False),
    st.sampled_from([64.0, 64.999, 65.0, 74.999, 75.0]),
)


def _creatinine_for_egfr(target: float, age: float, sex: str) -> float:
    """Invert CKD-EPI 2021 to find the creatinine that yields ``target`` eGFR.

    Uniform random creatinine essentially never produces an eGFR sitting on a
    rounding boundary, so a differential test built only on random inputs
    cannot see a half-up/half-even disagreement at all — verified by mutating
    :func:`js_round` and watching the suite stay green. Solving for the
    boundary instead of waiting for it is the difference between a test that
    could fail and one that merely does not.
    """
    is_female = sex == "F"
    kappa = 0.7 if is_female else 0.9
    alpha = -0.241 if is_female else -0.302
    sex_factor = 1.012 if is_female else 1.0
    ratio = target / (142 * (0.9938**age) * sex_factor)
    # Two branches of the piecewise formula; pick whichever is self-consistent.
    high = kappa * ratio ** (-1 / 1.2)   # scr >= kappa
    if high >= kappa:
        return high
    return kappa * ratio ** (1 / alpha)  # scr < kappa


@st.composite
def creatinine_on_rounding_boundary(draw: st.DrawFn) -> tuple[float, float, str]:
    """(creatinine, age, sex) triples whose raw eGFR lands on or beside ``x.5``."""
    half = draw(st.integers(min_value=3, max_value=140)) + 0.5
    age = draw(st.integers(min_value=18, max_value=95).map(float))
    sex = draw(SEXES)
    nudge = draw(st.sampled_from([0.0, -1e-9, 1e-9, -1e-6, 1e-6]))
    cr = _creatinine_for_egfr(half + nudge, age, sex)
    assume(0.05 < cr < 50.0 and math.isfinite(cr))
    return cr, age, sex


@given(cr=creatinines, age=ages, sex=SEXES)
@DIFFERENTIAL
def test_egfr_matches_typescript(ts: TsBridge, cr: float, age: float, sex: str) -> None:
    assert calculate_egfr(cr, age, sex) == ts.call("calculateEGFR", cr, age, sex)


@given(triple=creatinine_on_rounding_boundary())
@DIFFERENTIAL
def test_egfr_matches_typescript_on_rounding_boundaries(
    ts: TsBridge, triple: tuple[float, float, str]
) -> None:
    """The case uniform sampling cannot reach: raw eGFR sitting on ``x.5``.

    Exact agreement is asserted everywhere except the one place the two
    runtimes provably cannot agree. ``Math.pow`` is not correctly rounded in
    either language and V8 and CPython differ by an ulp, so a raw eGFR landing
    within a hair of ``x.5`` can round in opposite directions. That is allowed
    here, bounded to a single unit, and only when the value really is on the
    boundary — a two-unit gap, or a disagreement away from ``x.5``, is a bug.
    """
    cr, age, sex = triple
    py = calculate_egfr(cr, age, sex)
    js = ts.call("calculateEGFR", cr, age, sex)
    if py == js:
        return

    raw = egfr_exact(cr, age, sex)
    assert raw is not None
    distance_to_half = abs(raw - math.floor(raw) - 0.5)
    assert distance_to_half < 1e-9, (
        f"eGFR disagreement away from a rounding boundary: py={py} js={js} raw={raw!r}"
    )
    assert abs(py - js) == 1, f"boundary disagreement should be 1 unit, got py={py} js={js}"


@given(egfr=egfr_values)
@DIFFERENTIAL
def test_ckd_stage_matches_typescript(ts: TsBridge, egfr: float | None) -> None:
    assert ckd_stage(egfr) == ts.call("ckdStage", egfr)


@given(egfr=egfr_values)
@DIFFERENTIAL
def test_egfr_bucket_matches_typescript(ts: TsBridge, egfr: float | None) -> None:
    assert egfr_bucket(egfr) == ts.call("egfrBucket", egfr)


@given(
    egfr=egfr_values,
    dosing=st.dictionaries(
        keys=st.sampled_from(RENAL_PRIORITY),
        values=st.text(min_size=1, max_size=12),
        max_size=6,
    ),
)
@DIFFERENTIAL
def test_renal_dose_instruction_matches_typescript(
    ts: TsBridge, egfr: float | None, dosing: dict[str, str]
) -> None:
    assert renal_dose_instruction(dosing, egfr) == ts.call("getRenalDoseInstruction", dosing, egfr)


@given(
    has_hf=st.booleans(),
    has_htn=st.booleans(),
    age=ages,
    has_diabetes=st.booleans(),
    has_prior_stroke=st.booleans(),
    has_vascular_disease=st.booleans(),
    sex=SEXES,
)
@DIFFERENTIAL
def test_chads_vasc_matches_typescript(
    ts: TsBridge,
    has_hf: bool,
    has_htn: bool,
    age: float,
    has_diabetes: bool,
    has_prior_stroke: bool,
    has_vascular_disease: bool,
    sex: str,
) -> None:
    py = calculate_chads_vasc(
        ChadsVascInputs(
            has_hf, has_htn, age, has_diabetes, has_prior_stroke, has_vascular_disease, sex
        )
    )
    js = ts.call(
        "calculateChadsVasc",
        {
            "hasHF": has_hf,
            "hasHTN": has_htn,
            "age": age,
            "hasDiabetes": has_diabetes,
            "hasPriorStroke": has_prior_stroke,
            "hasVascularDisease": has_vascular_disease,
            "sex": sex,
        },
    )
    assert py == js


@given(score=st.integers(min_value=0, max_value=9), sex=SEXES)
@DIFFERENTIAL
def test_should_anticoagulate_matches_typescript(ts: TsBridge, score: int, sex: str) -> None:
    assert should_anticoagulate(score, sex) == ts.call("shouldAnticoagulate", score, sex)


@given(
    bmi=st.one_of(
        st.floats(min_value=10.0, max_value=60.0, allow_nan=False, allow_infinity=False),
        st.sampled_from([18.49, 18.5, 22.99, 23.0, 24.99, 25.0, 29.99, 30.0]),
    )
)
@DIFFERENTIAL
def test_bmi_category_matches_typescript(ts: TsBridge, bmi: float) -> None:
    assert bmi_category(bmi) == ts.call("bmiCategory", bmi)


# --------------------------------------------------------------------------
# Properties that should hold of the Python side regardless of the original.
# --------------------------------------------------------------------------


@given(x=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
def test_js_round_is_half_up(x: float) -> None:
    assert js_round(x) == math.floor(x + 0.5)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2.5, 3), (3.5, 4), (-2.5, -2), (0.5, 1), (-0.5, 0), (2.4, 2), (2.6, 3)],
)
def test_js_round_disagrees_with_python_round_where_it_should(value: float, expected: int) -> None:
    """Pins the exact cases where Python's banker's rounding would diverge."""
    assert js_round(value) == expected


@given(egfr=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False))
def test_every_egfr_has_a_stage(egfr: float) -> None:
    assert ckd_stage(egfr) is not None


@given(
    egfr=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    dosing=st.dictionaries(st.sampled_from(RENAL_PRIORITY), st.text(min_size=1), min_size=1),
)
def test_a_drug_listing_egfr_all_always_resolves(egfr: float, dosing: dict[str, str]) -> None:
    """No patient may fall through a drug's renal bands when a catch-all exists."""
    assume("egfr_all" in dosing)
    assert renal_dose_instruction(dosing, egfr) is not None


# --------------------------------------------------------------------------
# Why the bands read the unrounded value.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "stage_from_exact", "stage_from_rounded"),
    [
        (44.5, "CKD 3b", "CKD 3a"),
        (29.5, "CKD 4", "CKD 3b"),
        (14.5, "CKD 5", "CKD 4"),
        (59.5, "CKD 3a", "G2"),
        (89.5, "G2", "Normal (G1)"),
    ],
)
def test_rounding_before_banding_moves_the_clinical_stage(
    raw: float, stage_from_exact: str, stage_from_rounded: str
) -> None:
    """Rounding eGFR before comparing it to a band threshold changes the answer.

    This is the defect the split between :func:`egfr_exact` and
    :func:`calculate_egfr` exists to remove. At every KDIGO threshold, a true
    eGFR half a unit below it rounds *up* across the boundary and reports a
    healthier kidney than the patient has — and at 44.5 that is the difference
    between CKD 3b and CKD 3a, which selects a different renal dosing band.
    """
    assert ckd_stage(raw) == stage_from_exact
    assert ckd_stage(js_round(raw)) == stage_from_rounded
    assert stage_from_exact != stage_from_rounded


@given(
    cr=st.floats(min_value=0.2, max_value=15.0, allow_nan=False, allow_infinity=False),
    age=st.integers(min_value=18, max_value=95).map(float),
    sex=SEXES,
)
def test_exact_egfr_bands_are_stable_under_one_ulp_of_creatinine(
    cr: float, age: float, sex: str
) -> None:
    """A one-ulp nudge to creatinine must not move the patient's CKD stage.

    The rounded path cannot promise this — an ulp is exactly what moved one
    fuzzed patient from 46 to 47 across the two runtimes. On the exact path a
    stage change needs the true value to sit within an ulp of the threshold
    itself, which this asserts does not happen for ordinary inputs.
    """
    base = egfr_exact(cr, age, sex)
    nudged = egfr_exact(math.nextafter(cr, math.inf), age, sex)
    assume(base is not None and nudged is not None)
    for threshold in (15, 30, 45, 60, 90):
        assume(abs(base - threshold) > 1e-6)
    assert ckd_stage(base) == ckd_stage(nudged)
