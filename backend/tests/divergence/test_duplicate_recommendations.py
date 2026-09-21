"""The same drug class was recommended twice to the same patient.

Several rules can reach one class. A patient with diabetes, heart failure and
CKD 3a satisfies both the HF branch and the CKD branch, and both recommend an
SGLT2 inhibitor. ``recommendDrugClasses`` appends unconditionally, so seeded
patient #6's report carries::

    recommended_drug_classes: ["SGLT2 inhibitor", "SGLT2 inhibitor"]

which the composer renders as two identical bullets under RECOMMENDED DRUG
CLASSES, and which the UI shows as a repeated row. Repetition is not emphasis
in a prompt built to be precise.

The flags stay separate — two rules reaching the same class for different
reasons is worth showing, and each states its own reasoning. Only the class
list is deduplicated.
"""

from __future__ import annotations

from brahmo.domain.patient import Patient
from brahmo.engine import Engine


def test_typescript_recommends_the_same_class_twice(golden_cases: list[dict]) -> None:
    """Pinned from the recorded TypeScript report rather than described."""
    case = next(c for c in golden_cases if c["patient"]["id"] == 6)
    classes = case["report"]["recommended_drug_classes"]
    assert classes.count("SGLT2 inhibitor") == 2, (
        "TypeScript no longer duplicates the class — if that was fixed upstream, "
        "this divergence test should be retired."
    )


def test_python_names_each_class_once(engine: Engine, golden_cases: list[dict]) -> None:
    for case in golden_cases:
        report = engine.run(Patient.model_validate(case["patient"]))
        classes = list(report.recommended_drug_classes)
        assert len(classes) == len(set(classes)), f"#{case['patient']['id']}: {classes}"


def test_the_deduplicated_set_is_unchanged(engine: Engine, golden_cases: list[dict]) -> None:
    """Dropping duplicates must not drop a recommendation."""
    for case in golden_cases:
        report = engine.run(Patient.model_validate(case["patient"]))
        ts_classes = set(case["report"]["recommended_drug_classes"])
        assert set(report.recommended_drug_classes) == ts_classes, case["patient"]["id"]


def test_both_rules_still_explain_themselves(engine: Engine, golden_cases: list[dict]) -> None:
    """Patient #6 should still carry the HF reason and the CKD reason."""
    case = next(c for c in golden_cases if c["patient"]["id"] == 6)
    report = engine.run(Patient.model_validate(case["patient"]))
    rules = {f.provenance.rule_id for f in report.flags}
    assert "recommend.sglt2_hf" in rules
    assert "recommend.sglt2_ckd" in rules
    assert list(report.recommended_drug_classes).count("SGLT2 inhibitor") == 1
