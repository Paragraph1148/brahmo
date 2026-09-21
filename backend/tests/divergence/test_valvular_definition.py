"""One report said the same patient had valvular AF and non-valvular AF.

``safety-engine.ts`` asks "is this valvular?" three times with three different
keyword lists::

    458:  !hasCondition(patient, "rheumatic", "valvular", "rhd")          -> DOAC
    470:   hasCondition(patient, "rheumatic", "valvular", "rhd")          -> Warfarin
    558:   hasCondition(patient, "rheumatic", "valvular", "rhd",
                                 "mitral stenosis", "prosthetic valve")   -> AF flag

A patient charted as plain "Mitral Stenosis" satisfies the five-keyword list
and not the three-keyword one, so a single report contains both verdicts.
Confirmed against the live engine::

    conditions=["Mitral Stenosis", "Atrial Fibrillation"]
      flag:    Valvular AF -> Anticoagulation INDICATED regardless of CHA2DS2-VASc
      flag:    Non-valvular AF: DOAC preferred over Warfarin
      classes: ["DOAC"]

Rheumatic mitral stenosis is routinely charted without the word "rheumatic",
and a DOAC in rheumatic MS is the specific error this project exists to
prevent — it is the headline row of the README's comparison table. Seeded
patient #7 escapes it only because their problem list also carries "RHD".
"""

from __future__ import annotations

import pytest

from brahmo.conditions import doac_contraindicated, is_valvular_for_retrieval
from brahmo.domain.patient import Patient
from brahmo.engine import Engine
from tests.differential.bridge import TsBridge

AF = "Atrial Fibrillation"


def _patient(conditions: list[str]) -> dict:
    return {
        "id": 96,
        "patient_label": "valvular probe",
        "age": 50,
        "sex": "M",
        "bmi": 24,
        "conditions": conditions,
        "medications": [],
        "allergies": [],
        "labs": {},
        "vitals": {},
        "insurance": {},
        "income_context": "",
    }


def test_typescript_contradicts_itself_on_plain_mitral_stenosis(ts: TsBridge) -> None:
    report = ts.call("runSafetyChecks", _patient(["Mitral Stenosis", AF]))
    titles = [f["title"] for f in report["flags"]]

    assert any("Valvular AF" in t for t in titles), titles
    assert any("Non-valvular AF" in t for t in titles), (
        "TypeScript no longer calls plain mitral stenosis non-valvular — if that was "
        "fixed upstream, this divergence test should be retired."
    )
    assert "DOAC" in report["recommended_drug_classes"]


@pytest.mark.parametrize(
    "conditions",
    [
        ["Rheumatic Heart Disease", AF],
        ["Mitral Stenosis", AF],
        ["Severe MS", AF],
        ["Prosthetic Valve", AF],
        ["Mechanical valve replacement", AF],
    ],
)
def test_python_reaches_one_verdict(engine: Engine, conditions: list[str]) -> None:
    """Whatever the charting, the flags and the recommendation must agree."""
    report = engine.run(Patient.model_validate(_patient(conditions)))
    titles = [f.title for f in report.flags]
    classes = list(report.recommended_drug_classes)

    if doac_contraindicated(Patient.model_validate(_patient(conditions))):
        assert any("Valvular AF" in t for t in titles), titles
        assert not any("Non-valvular AF" in t for t in titles), titles
        assert "DOAC" not in classes, classes
        assert any("Warfarin" in c for c in classes), classes


def test_no_report_ever_asserts_both(engine: Engine) -> None:
    """The property, over every way a valve lesion might be written."""
    phrasings = [
        "Rheumatic Heart Disease", "RHD", "Mitral Stenosis", "Severe MS",
        "mitral valve stenosis", "Prosthetic Valve", "Mechanical valve",
        "Valvular heart disease", "Aortic Stenosis", "Hypertension",
    ]
    for phrasing in phrasings:
        report = engine.run(Patient.model_validate(_patient([phrasing, AF])))
        titles = [f.title for f in report.flags]
        valvular = any("Valvular AF" in t for t in titles)
        non_valvular = any("Non-valvular AF" in t for t in titles)
        assert valvular != non_valvular, f"{phrasing!r}: valvular={valvular} non={non_valvular}"

        classes = list(report.recommended_drug_classes)
        if valvular:
            assert "DOAC" not in classes, f"{phrasing!r} got a DOAC with valvular AF"


def test_isolated_aortic_stenosis_is_not_a_doac_contraindication() -> None:
    """Retrieval is liberal; the anticoagulation gate is not.

    Aortic stenosis is valve disease and should pull the valve guidelines, but
    it is not one of the two lesions that make a DOAC unsafe. Sending such a
    patient to warfarin means lifelong INR monitoring they do not need.
    """
    patient = Patient.model_validate(_patient(["Severe Aortic Stenosis", AF]))
    assert is_valvular_for_retrieval(patient) is True
    assert doac_contraindicated(patient) is False


def test_mitral_stenosis_is_both() -> None:
    patient = Patient.model_validate(_patient(["Mitral Stenosis", AF]))
    assert is_valvular_for_retrieval(patient) is True
    assert doac_contraindicated(patient) is True
