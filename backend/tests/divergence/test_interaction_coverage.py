"""A patient on one drug got no interaction check at all.

``checkInteractions`` opens with ``if (drugIds.length < 2) return []``. The
guard reads as common sense -- an interaction needs two drugs -- but the table
holds interactions whose other side is a non-formulary substance recorded with
a null id: alcohol, IV contrast, steroids. Those need exactly one patient drug,
and the early return discards every one of them.

The effect is that the same prescription is checked or not depending on what
else happens to be beside it. Confirmed against the live engine::

    meds=[Metformin]                 -> 0 interaction flags
    meds=[Metformin, Atorvastatin]   -> 4, three of them Metformin's own:
                                        IV contrast (severe), alcohol,
                                        steroids

Metformin with IV contrast is a hold-before-imaging contraindication. Patient
#3 in the seed -- an auto-driver on metformin alone, no insurance -- comes back
with a clean report on all three.
"""

from __future__ import annotations

import pytest

from brahmo.domain.patient import Patient
from brahmo.engine import Engine
from tests.differential.bridge import TsBridge

METFORMIN = {"drug": "Metformin", "dose": "1g BD"}
ATORVASTATIN = {"drug": "Atorvastatin", "dose": "20mg OD"}


def _patient(medications: list[dict]) -> dict:
    return {
        "id": 98,
        "patient_label": "interaction probe",
        "age": 40,
        "sex": "M",
        "bmi": 24,
        "conditions": ["T2DM"],
        "medications": medications,
        "allergies": [],
        "labs": {},
        "vitals": {},
        "insurance": {},
        "income_context": "",
    }


def _interaction_titles(flags: list) -> set[str]:
    return {f["title"] for f in flags if f["category"] == "interaction"}


def test_typescript_drops_every_interaction_for_a_single_drug(ts: TsBridge) -> None:
    """The bug, pinned against the live engine."""
    alone = _interaction_titles(ts.call("runSafetyChecks", _patient([METFORMIN]))["flags"])
    with_statin = _interaction_titles(
        ts.call("runSafetyChecks", _patient([METFORMIN, ATORVASTATIN]))["flags"]
    )

    assert alone == set(), (
        "TypeScript now checks interactions for a lone drug — if that was fixed "
        "upstream, this divergence test should be retired."
    )
    metformin_only = {t for t in with_statin if t.startswith("Metformin +")}
    assert len(metformin_only) >= 3, "expected Metformin's substance interactions to appear"


def test_python_checks_a_lone_drug_against_substance_interactions(engine: Engine) -> None:
    alone = engine.run(Patient.model_validate(_patient([METFORMIN])))
    titles = {f.title for f in alone.flags if f.category == "interaction"}
    assert any("IV contrast" in t for t in titles), titles
    assert any("Alcohol" in t for t in titles), titles


def test_an_unrelated_drug_cannot_change_metformins_own_interactions(engine: Engine) -> None:
    """The property the guard violated: a drug's interactions are its own."""
    alone = engine.run(Patient.model_validate(_patient([METFORMIN])))
    together = engine.run(Patient.model_validate(_patient([METFORMIN, ATORVASTATIN])))

    def metformin_flags(report) -> set[str]:
        return {
            f.title
            for f in report.flags
            if f.category == "interaction" and f.title.startswith("Metformin +")
        }

    assert metformin_flags(alone) == metformin_flags(together)


@pytest.mark.parametrize("patient_id", [3])
def test_the_seeded_auto_driver_is_no_longer_silently_clean(
    engine: Engine, golden_cases: list[dict], patient_id: int
) -> None:
    case = next(c for c in golden_cases if c["patient"]["id"] == patient_id)
    assert case["report"]["flags"] == [], "golden #3 should be the clean-report case"

    report = engine.run(Patient.model_validate(case["patient"]))
    interactions = [f for f in report.flags if f.category == "interaction"]
    assert len(interactions) >= 3, [f.title for f in report.flags]
