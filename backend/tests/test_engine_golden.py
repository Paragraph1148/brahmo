"""The Python engine against the TypeScript engine's recorded reports.

Every flag must either appear identically in the TypeScript golden report, or
fall into one of the divergences enumerated below. Anything else fails — the
point of this test is that an unintended difference cannot hide among the
intended ones.

Each divergence has its own test under ``tests/divergence/`` stating what the
original does and why this port does otherwise.
"""

from __future__ import annotations

import pytest

from brahmo.domain.patient import Patient
from brahmo.engine import Engine
from brahmo.report import SafetyFlag

#: Rules that intentionally produce a flag the TypeScript never produces.
EXPECTED_EXTRA_RULES = frozenset(
    {
        "resolution.unknown",         # TS skips unrecognised meds silently
        "resolution.ambiguous",       # TS resolves ambiguity by row order
        "hypoglycemia.ckd.caution",   # TS fires a single critical STOP instead
        "interaction.pairwise",       # TS skips all interactions for a lone drug
    }
)

#: TypeScript flag titles this port deliberately does not reproduce.
EXPECTED_MISSING_TITLES = (
    "in CKD (eGFR",  # superseded by the graded hypoglycemia.ckd.* rules
)


def _title(flag: SafetyFlag) -> str:
    return flag.title


def test_every_patient_is_covered(golden_cases: list[dict]) -> None:
    assert len(golden_cases) == 9


def test_computed_values_match_typescript(engine: Engine, golden_cases: list[dict]) -> None:
    """eGFR, stage, CHA2DS2-VASc and BMI category agree on every real patient."""
    for case in golden_cases:
        patient = Patient.model_validate(case["patient"])
        report = engine.run(patient)
        ts = case["report"]["computed"]

        assert report.computed.egfr_display == ts["eGFR"], f"eGFR differs for #{patient.id}"
        assert report.computed.egfr_stage == ts["eGFR_stage"], f"stage differs for #{patient.id}"
        assert report.computed.chads_vasc == ts["chads_vasc"], f"score differs for #{patient.id}"
        assert report.computed.bmi_category == ts["bmi_category"], f"BMI differs for #{patient.id}"


def test_no_unintended_divergence_from_typescript(
    engine: Engine, golden_cases: list[dict]
) -> None:
    for case in golden_cases:
        patient = Patient.model_validate(case["patient"])
        report = engine.run(patient)
        ts_titles = {f["title"] for f in case["report"]["flags"]}
        py_titles = {_title(f) for f in report.flags}

        extra = py_titles - ts_titles
        for flag in report.flags:
            if _title(flag) in extra:
                assert flag.provenance.rule_id in EXPECTED_EXTRA_RULES, (
                    f"#{patient.id} raised an unexpected flag from rule "
                    f"{flag.provenance.rule_id!r}: {flag.title!r}"
                )

        missing = ts_titles - py_titles
        for title in missing:
            assert any(marker in title for marker in EXPECTED_MISSING_TITLES), (
                f"#{patient.id} lost a TypeScript flag that was not meant to go: {title!r}"
            )


def test_shared_flags_keep_their_severity(engine: Engine, golden_cases: list[dict]) -> None:
    """Where both engines raise the same flag, they must agree on how bad it is."""
    for case in golden_cases:
        patient = Patient.model_validate(case["patient"])
        report = engine.run(patient)
        ts_by_title = {f["title"]: f for f in case["report"]["flags"]}

        for flag in report.flags:
            ts_flag = ts_by_title.get(flag.title)
            if ts_flag is None:
                continue
            assert flag.severity.value == ts_flag["severity"], (
                f"#{patient.id} {flag.title!r}: severity "
                f"{flag.severity.value} vs TypeScript {ts_flag['severity']}"
            )
            assert flag.category == ts_flag["category"], f"#{patient.id} {flag.title!r}: category"


def test_flags_are_sorted_by_severity(engine: Engine, golden_cases: list[dict]) -> None:
    for case in golden_cases:
        report = engine.run(Patient.model_validate(case["patient"]))
        ranks = [f.severity.rank for f in report.flags]
        assert ranks == sorted(ranks)


def test_every_flag_states_its_provenance(engine: Engine, golden_cases: list[dict]) -> None:
    """The property the RAG contradiction check will depend on."""
    for case in golden_cases:
        report = engine.run(Patient.model_validate(case["patient"]))
        for flag in report.flags:
            assert flag.provenance.rule_id
            assert flag.provenance.inputs or flag.provenance.rule_id.startswith("recommend.")


def test_engine_is_deterministic(engine: Engine, golden_cases: list[dict]) -> None:
    for case in golden_cases:
        patient = Patient.model_validate(case["patient"])
        assert engine.run(patient).to_dict() == engine.run(patient).to_dict()


@pytest.mark.parametrize("patient_id", [2, 7])
def test_unresolvable_medications_are_reported(
    engine: Engine, golden_cases: list[dict], patient_id: int
) -> None:
    """Patients 2 and 7 carry a medication outside the formulary."""
    case = next(c for c in golden_cases if c["patient"]["id"] == patient_id)
    report = engine.run(Patient.model_validate(case["patient"]))
    assert report.unresolved_medications
    assert any(f.provenance.rule_id.startswith("resolution.") for f in report.flags)
