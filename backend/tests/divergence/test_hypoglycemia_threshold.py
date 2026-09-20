"""The sulfonylurea renal flag cited one threshold and used another.

The original fires a single ``critical`` flag at any eGFR below 60::

    if (eGFR !== null && eGFR < 60) { ... }
        title:  "<drug> in CKD (eGFR N): high hypoglycemia risk"
        detail: "RSSDI 2022: STOP sulfonylurea when eGFR <30 ..."
        action: "STOP - switch to insulin or Linagliptin"

So a patient at eGFR 44 is told to stop a drug by a flag whose own citation
says to stop below 30. RSSDI 2022 grades it: reduce and monitor between 30 and
60, stop below 30. This port follows the guideline it cites.

The same block also applied sulfonylurea-specific wording to any drug carrying
moderate or high hypoglycemia risk, so the advice named a drug class the
patient might not be on.
"""

from __future__ import annotations

import pytest

from brahmo.engine import SU_CAUTION_EGFR, SU_STOP_EGFR
from brahmo.domain.patient import Patient
from brahmo.engine import Engine
from brahmo.report import Severity
from tests.differential.bridge import TsBridge


def _ckd_patient(creatinine: float) -> dict:
    return {
        "id": 97,
        "patient_label": "sulfonylurea probe",
        "age": 55,
        "sex": "M",
        "bmi": 26,
        "conditions": ["T2DM", "CKD"],
        "medications": [{"drug": "Glimepiride", "dose": "2mg OD"}],
        "allergies": [],
        "labs": {"Cr": creatinine},
        "vitals": {},
        "insurance": {},
        "income_context": "",
    }


def _hypo_flags(flags: list[dict]) -> list[dict]:
    return [f for f in flags if f["category"] == "hypoglycemia" and "CKD" in f["title"]]


def test_typescript_says_stop_at_an_egfr_its_own_citation_calls_safe(ts: TsBridge) -> None:
    """eGFR ~44: critical STOP, from a flag citing the rule for below 30."""
    report = ts.call("runSafetyChecks", _ckd_patient(1.8))
    assert report["computed"]["eGFR"] < 60
    assert report["computed"]["eGFR"] > SU_STOP_EGFR

    hypo = _hypo_flags(report["flags"])
    assert hypo, "expected a CKD hypoglycemia flag from the TypeScript engine"
    assert hypo[0]["severity"] == "critical", (
        "TypeScript no longer fires critical above the stop threshold — if that was "
        "fixed upstream, this divergence test should be retired."
    )
    assert "STOP" in (hypo[0]["action"] or "")
    assert "<30" in hypo[0]["detail"]


@pytest.mark.parametrize(
    ("creatinine", "expected"),
    [
        (1.8, Severity.WARNING),   # eGFR in the 30-60 band: reduce and monitor
        (3.2, Severity.CRITICAL),  # eGFR below 30: stop
    ],
)
def test_python_grades_the_response_to_the_threshold_it_cites(
    engine: Engine, creatinine: float, expected: Severity
) -> None:
    report = engine.run(Patient.model_validate(_ckd_patient(creatinine)))
    egfr = report.computed.egfr
    assert egfr is not None

    hypo = [f for f in report.flags if f.provenance.rule_id.startswith("hypoglycemia.ckd.")]
    assert len(hypo) == 1, [f.title for f in report.flags]
    assert hypo[0].severity is expected

    if expected is Severity.CRITICAL:
        assert egfr < SU_STOP_EGFR
        assert "STOP" in (hypo[0].action or "")
    else:
        assert SU_STOP_EGFR <= egfr < SU_CAUTION_EGFR
        assert "REDUCE" in (hypo[0].action or "")


def test_the_flag_names_the_drugs_actual_class(engine: Engine) -> None:
    """Advice must not assume the drug is a sulfonylurea."""
    report = engine.run(Patient.model_validate(_ckd_patient(3.2)))
    hypo = next(f for f in report.flags if f.provenance.rule_id == "hypoglycemia.ckd.stop")
    assert "Sulfonylurea" in hypo.detail
    assert "Glimepiride" in hypo.title
