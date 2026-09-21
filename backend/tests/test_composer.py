"""The composed prompt against the TypeScript composer.

Every section except the safety block must match byte for byte. The safety
block is excluded because it renders this port's report, which carries flags
the original does not raise — those differences are the subject of
``tests/divergence/`` and are not the composer's doing.
"""

from __future__ import annotations

import re

import pytest

from brahmo.composer import Composer, is_uninsured
from brahmo.conditions import derive_condition_tags
from brahmo.domain.patient import Patient
from brahmo.engine import Engine
from brahmo.retrieval import collate
from tests.differential.bridge import TsBridge

SECTION = re.compile(r"\n\n(?=#{1,2} )")


def _sections(prompt: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in SECTION.split(prompt):
        out[block.splitlines()[0].strip()] = block
    return out


def _compose_both(ts: TsBridge, composer: Composer, engine: Engine, case: dict):
    question = case["question"] or "What is the next step?"
    patient = Patient.model_validate(case["patient"])
    return (
        ts.call("composePrompt", case["patient"], question),
        composer.compose(patient, engine.run(patient), question),
    )


def test_every_non_safety_section_matches_typescript(
    ts: TsBridge, composer: Composer, engine: Engine, golden_cases: list[dict]
) -> None:
    for case in golden_cases:
        ts_out, py_out = _compose_both(ts, composer, engine, case)
        ts_sections = _sections(ts_out["optionC"])
        py_sections = _sections(py_out.grounded)
        pid = case["patient"]["id"]

        for heading, body in ts_sections.items():
            if heading.startswith("## SAFETY"):
                continue
            assert heading in py_sections, f"#{pid} missing section {heading!r}"
            assert py_sections[heading] == body, f"#{pid} section {heading!r} differs"

        unexpected = set(py_sections) - set(ts_sections)
        assert not {h for h in unexpected if not h.startswith("## SAFETY")}, (
            f"#{pid} produced unexpected sections: {unexpected}"
        )


def test_retrieval_metadata_matches_typescript(
    ts: TsBridge, composer: Composer, engine: Engine, golden_cases: list[dict]
) -> None:
    """Same tags in, same guidelines and drugs out."""
    for case in golden_cases:
        ts_out, py_out = _compose_both(ts, composer, engine, case)
        ts_meta, py_meta = ts_out["meta"], py_out.meta
        pid = case["patient"]["id"]

        assert list(py_meta.condition_tags) == ts_meta["condition_tags"], f"#{pid} tags"
        assert py_meta.guidelines_count == ts_meta["guidelines_count"], f"#{pid} guidelines"
        assert py_meta.drugs_count == ts_meta["drugs_count"], f"#{pid} drugs"
        assert list(py_meta.active_sources) == ts_meta["active_sources"], f"#{pid} sources"


def test_generic_arm_matches_typescript(
    ts: TsBridge, composer: Composer, engine: Engine, golden_cases: list[dict]
) -> None:
    """The contrast arm must be untouched, or the A/B comparison means nothing."""
    for case in golden_cases:
        ts_out, py_out = _compose_both(ts, composer, engine, case)
        assert py_out.generic == ts_out["generic"], f"#{case['patient']['id']} generic arm"


def test_condition_tags_match_typescript(
    ts: TsBridge, golden_cases: list[dict]
) -> None:
    for case in golden_cases:
        patient = Patient.model_validate(case["patient"])
        assert derive_condition_tags(patient) == ts.call(
            "deriveConditionTags", case["patient"]
        ), f"#{patient.id} condition tags"


def test_composition_is_deterministic(
    composer: Composer, engine: Engine, golden_cases: list[dict]
) -> None:
    for case in golden_cases:
        patient = Patient.model_validate(case["patient"])
        report = engine.run(patient)
        first = composer.compose(patient, report, "q").grounded
        second = composer.compose(patient, report, "q").grounded
        assert first == second


def test_unresolved_medications_reach_the_prompt(
    composer: Composer, engine: Engine, golden_cases: list[dict]
) -> None:
    """A medication the engine could not check must be said out loud to the model.

    Otherwise the prompt asserts a safety review that did not cover everything
    the patient is taking, which is worse than saying nothing.
    """
    case = next(c for c in golden_cases if c["patient"]["id"] == 2)
    patient = Patient.model_validate(case["patient"])
    prompt = composer.compose(patient, engine.run(patient), "q").grounded
    assert "COULD NOT CHECK" in prompt
    assert "Pregabalin" in prompt


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("NONE", True), ("None", True), ("none", True), ("", True),
        ("  ", True), ("nil", True), ("Uninsured", True),
        ("CGHS", False), ("Star Health", False), ("ESI", False),
    ],
)
def test_uninsured_detection_is_case_insensitive(provider: str, expected: bool) -> None:
    """The original compares to "NONE" exactly while rendering the field "None".

    A record written the way the prompt displays it would read as insured and
    lose the affordability guidance the uninsured path adds.
    """
    patient = Patient.model_validate(
        {
            "id": 1, "age": 50, "sex": "M", "conditions": [], "medications": [],
            "allergies": [], "labs": {}, "vitals": {},
            "insurance": {"provider": provider}, "income_context": "",
        }
    )
    assert is_uninsured(patient) is expected


def test_collation_is_locale_independent_and_reads_naturally() -> None:
    classes = ["ARB", "Alpha-glucosidase inhibitor", "Biguanide", "arb duplicate"]
    assert sorted(classes, key=collate) == [
        "Alpha-glucosidase inhibitor",
        "ARB",
        "arb duplicate",
        "Biguanide",
    ]


def test_collation_is_total() -> None:
    """Entries differing only in case still order stably."""
    assert collate("ARB") != collate("arb")
    assert sorted(["arb", "ARB"], key=collate) == ["ARB", "arb"]
