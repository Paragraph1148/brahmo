"""Intentional divergences from the TypeScript engine.

Every test here asserts two things: what the TypeScript implementation does
today, read from the live engine over the bridge, and what this port does
instead. Both halves matter. Pinning the original's behaviour means that if
someone fixes it upstream, this test fails and says so, rather than quietly
becoming a description of something that is no longer true.

These are the only places the two implementations are allowed to disagree.
Everywhere else, ``tests/differential/`` requires them to match.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from brahmo.domain.allergy import AllergyList
from tests.differential.bridge import TsBridge

DIVERGENCE = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

ASPIRIN_KEYWORDS = ("aspirin", "salicylate", "nsaid", "ibuprofen", "diclofenac")


def _stemi_patient(allergies: list[str]) -> dict:
    """A STEMI patient, because that is where the aspirin decision bites."""
    return {
        "id": 99,
        "patient_label": "divergence probe",
        "age": 60,
        "sex": "M",
        "bmi": 25,
        "conditions": ["STEMI"],
        "medications": [],
        "allergies": allergies,
        "labs": {},
        "vitals": {},
        "insurance": {},
        "income_context": "",
    }


def _aspirin_flag(report: dict) -> dict | None:
    for flag in report["flags"]:
        if "Aspirin" in (flag.get("drugs_involved") or []):
            return flag
    return None


ASPIRIN_MILD = "Aspirin (mild rash, no anaphylaxis)"
PENICILLIN_SEVERE = "Penicillin (anaphylaxis)"


def test_typescript_escalates_aspirin_on_an_unrelated_anaphylaxis(ts: TsBridge) -> None:
    """The bug, pinned against the live TypeScript engine.

    ``hasAllergy(patient, "anaphylaxis", ...)`` searches the whole allergy list
    joined into one string, so a penicillin anaphylaxis satisfies the severity
    test for aspirin. The aspirin entry says "no anaphylaxis" explicitly and is
    overruled by a different line.
    """
    alone = _aspirin_flag(ts.call("runSafetyChecks", _stemi_patient([ASPIRIN_MILD])))
    with_penicillin = _aspirin_flag(
        ts.call("runSafetyChecks", _stemi_patient([PENICILLIN_SEVERE, ASPIRIN_MILD]))
    )

    assert alone is not None and with_penicillin is not None
    assert alone["severity"] == "warning"
    assert with_penicillin["severity"] == "critical", (
        "TypeScript no longer escalates across allergy entries — if that was fixed "
        "upstream, this divergence test should be retired."
    )
    assert "DO NOT give aspirin" in with_penicillin["title"]


def test_python_keeps_the_aspirin_reaction_with_aspirin() -> None:
    """The same two patients, decided per substance."""
    alone = AllergyList([ASPIRIN_MILD])
    with_penicillin = AllergyList([PENICILLIN_SEVERE, ASPIRIN_MILD])

    assert alone.is_severe_for(*ASPIRIN_KEYWORDS) is False
    assert with_penicillin.is_severe_for(*ASPIRIN_KEYWORDS) is False
    assert with_penicillin.is_severe_for("penicillin") is True


@given(
    other=st.sampled_from(
        [
            "Penicillin (anaphylaxis)",
            "Amoxicillin (angioedema)",
            "Latex (bronchospasm)",
            "Sulfa drugs (Stevens-Johnson)",
        ]
    )
)
@DIVERGENCE
def test_no_unrelated_allergy_can_escalate_aspirin(other: str) -> None:
    """Severity never crosses entries, whatever else is on the list."""
    assert AllergyList([other, ASPIRIN_MILD]).is_severe_for(*ASPIRIN_KEYWORDS) is False


@pytest.mark.parametrize(
    "allergies",
    [
        [ASPIRIN_MILD],
        [PENICILLIN_SEVERE, ASPIRIN_MILD],
        ["Aspirin (anaphylaxis)"],
        ["Aspirin (anaphylaxis)", "Penicillin (mild rash)"],
    ],
)
def test_aspirin_severity_depends_only_on_the_aspirin_entry(allergies: list[str]) -> None:
    """Dropping every non-aspirin entry must not change the aspirin verdict."""
    full = AllergyList(allergies)
    aspirin_only = AllergyList([a for a in allergies if AllergyList([a]).has(*ASPIRIN_KEYWORDS)])
    assert full.is_severe_for(*ASPIRIN_KEYWORDS) == aspirin_only.is_severe_for(*ASPIRIN_KEYWORDS)
