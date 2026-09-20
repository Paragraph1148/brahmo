"""Unit tests for per-substance allergy parsing."""

from __future__ import annotations

import pytest

from brahmo.domain.allergy import AllergyEntry, AllergyList


@pytest.mark.parametrize(
    ("raw", "substance", "reaction"),
    [
        ("Aspirin (mild rash, no anaphylaxis)", "Aspirin", "mild rash, no anaphylaxis"),
        ("Penicillin (anaphylaxis)", "Penicillin", "anaphylaxis"),
        ("Sulfa drugs", "Sulfa drugs", ""),
        ("Ibuprofen - bronchospasm", "Ibuprofen", "bronchospasm"),
        ("Codeine: nausea", "Codeine", "nausea"),
        ("  Latex  ", "Latex", ""),
    ],
)
def test_entry_splits_substance_from_reaction(raw: str, substance: str, reaction: str) -> None:
    entry = AllergyEntry.parse(raw)
    assert entry.substance == substance
    assert entry.reaction == reaction


def test_severity_is_read_from_the_entrys_own_reaction() -> None:
    assert AllergyEntry.parse("Penicillin (anaphylaxis)").is_severe
    assert not AllergyEntry.parse("Aspirin (mild rash, no anaphylaxis)").is_severe
    assert not AllergyEntry.parse("Aspirin (mild rash)").is_severe


def test_an_unqualified_entry_is_not_severe() -> None:
    """A documented allergy is not a documented anaphylaxis."""
    assert not AllergyEntry.parse("Penicillin").is_severe


def test_matching_reads_the_substance_not_the_reaction() -> None:
    """A reaction mentioning another drug is not an allergy to that drug."""
    entry = AllergyEntry.parse("Penicillin (rash; tolerates aspirin)")
    assert entry.matches("penicillin")
    assert not entry.matches("aspirin")


@pytest.mark.parametrize(
    "raw",
    [
        "No known drug allergies",
        "NKDA",
        "nka",
        "None",
        "Nil",
        "no known allergies",
        "Denies allergies",
    ],
)
def test_no_allergy_sentinels_carry_no_allergy(raw: str) -> None:
    """The commonest value in the field must not read as an allergy.

    "No known drug allergies" contains the word "drug" with the negation four
    words away, so a negation guard that only looks immediately before the
    keyword does not catch it. The TypeScript engine has the same hole.
    """
    allergies = AllergyList([raw])
    assert len(allergies) == 0
    assert not allergies.has("drug")
    assert not allergies.has("allergies")


def test_a_sentinel_alongside_a_real_allergy_keeps_the_real_one() -> None:
    allergies = AllergyList(["NKDA", "Aspirin (mild rash)"])
    assert len(allergies) == 1
    assert allergies.has("aspirin")


def test_severity_does_not_leak_between_entries() -> None:
    """The defect this module exists for, stated as a property."""
    allergies = AllergyList(["Penicillin (anaphylaxis)", "Aspirin (mild rash, no anaphylaxis)"])

    assert allergies.has("aspirin", "salicylate", "nsaid")
    assert allergies.has("penicillin")

    assert allergies.is_severe_for("penicillin") is True
    assert allergies.is_severe_for("aspirin", "salicylate", "nsaid") is False


def test_severity_is_found_when_it_really_is_this_substance() -> None:
    allergies = AllergyList(["Aspirin (anaphylaxis)", "Penicillin (mild rash)"])
    assert allergies.is_severe_for("aspirin") is True
    assert allergies.is_severe_for("penicillin") is False


def test_reactions_for_reports_only_matching_entries() -> None:
    allergies = AllergyList(["Penicillin (anaphylaxis)", "Aspirin (mild rash)"])
    assert allergies.reactions_for("aspirin") == ("mild rash",)
