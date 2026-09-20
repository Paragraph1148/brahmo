"""Allergy entries, parsed per substance.

The TypeScript engine keeps allergies as a flat list of strings and answers
"is there an anaphylaxis on file?" by searching the whole list joined together.
That conflates two different questions -- *which substance* the patient reacts
to, and *how badly they reacted to that substance* -- and the second one is
read off whichever entry happens to contain the word.

Observed on the live engine::

    ["Aspirin (mild rash, no anaphylaxis)"]
        -> aspirin flag: warning                      correct
    ["Penicillin (anaphylaxis)", "Aspirin (mild rash, no anaphylaxis)"]
        -> aspirin flag: critical, "DO NOT USE"       wrong

The penicillin reaction escalated the aspirin flag, on a patient whose aspirin
entry says "no anaphylaxis" in as many words. In a STEMI pathway that withholds
aspirin from someone who can safely take it, which is a harm in its own right.

So an allergy here is a record with a substance and its own reaction, and
severity is only ever read from the entry that matched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

#: A negation immediately before a keyword cancels it: "no anaphylaxis",
#: "denies penicillin allergy". Kept in step with conditions.hasAllergy.
_NEGATION = re.compile(r"\b(no|not|non|without|denies|denied|negative for|nil|neg)\b[\s,\-]*$")

#: Words that mark a reaction as life-threatening rather than merely documented.
_SEVERE_REACTION = (
    "anaphylaxis",
    "anaphylactic",
    "angioedema",
    "bronchospasm",
    "stevens-johnson",
    "sjs",
    "toxic epidermal necrolysis",
    "ten",
    "shock",
)

#: "Aspirin (mild rash)" / "Aspirin - mild rash" / "Aspirin: mild rash"
_SPLIT = re.compile(r"\s*[(\[:;—-]\s*|\s+-\s+")

#: How an empty allergy field is actually written. This is the most common
#: value in the field, and read literally "No known drug allergies" parses as
#: an allergy to drugs -- the negation guard does not catch it, because the
#: negation is not adjacent to the keyword. Both implementations had this hole;
#: here such an entry is recognised and carries no allergy at all.
_NO_ALLERGY = re.compile(
    r"^\s*(nkda|nka|none|nil"
    r"|no\s+known\s+(drug\s+)?(allerg\w*|reactions?)"
    r"|no\s+allerg\w*|denies\s+(any\s+)?allerg\w*|not\s+known\s+allerg\w*)"
    r"\s*\.?\s*$",
    re.IGNORECASE,
)


def is_no_allergy_sentinel(raw: str) -> bool:
    """Is this line the clerk saying there are no allergies?"""
    return bool(_NO_ALLERGY.match(raw.strip()))



def _word_present(text: str, keyword: str) -> bool:
    """Whole-word keyword match that a preceding negation cancels."""
    pattern = re.compile(rf"\b{re.escape(keyword.lower())}\b")
    for match in pattern.finditer(text.lower()):
        window = text.lower()[max(0, match.start() - 24) : match.start()]
        if not _NEGATION.search(window):
            return True
    return False


@dataclass(frozen=True, slots=True)
class AllergyEntry:
    """One line of the allergy list, split into what and how bad."""

    raw: str
    substance: str
    reaction: str

    @classmethod
    def parse(cls, raw: str) -> AllergyEntry:
        cleaned = raw.strip().rstrip(")]")
        parts = _SPLIT.split(cleaned, maxsplit=1)
        substance = parts[0].strip()
        reaction = parts[1].strip() if len(parts) > 1 else ""
        return cls(raw=raw, substance=substance, reaction=reaction)

    def matches(self, *keywords: str) -> bool:
        """Does this entry name one of these substances?

        Matched against the substance only. A reaction description mentioning
        another drug must not make this entry an allergy to that drug.
        """
        return any(_word_present(self.substance, k) for k in keywords)

    @property
    def is_severe(self) -> bool:
        """Was *this* substance's reaction life-threatening?

        Read from this entry's own reaction text. When no reaction is recorded
        the answer is no: an unqualified entry is a documented allergy, not a
        documented anaphylaxis, and inventing severity is how a rash becomes an
        absolute contraindication.
        """
        haystack = self.reaction or ""
        return any(_word_present(haystack, k) for k in _SEVERE_REACTION)


class AllergyList:
    """The patient's allergies, addressable by substance."""

    def __init__(self, raw: Iterable[str]) -> None:
        self._entries = tuple(
            AllergyEntry.parse(r)
            for r in raw
            if r and r.strip() and not is_no_allergy_sentinel(r)
        )

    def __iter__(self):
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"AllergyList({[e.raw for e in self._entries]!r})"

    def matching(self, *keywords: str) -> tuple[AllergyEntry, ...]:
        """Every entry naming one of these substances."""
        return tuple(e for e in self._entries if e.matches(*keywords))

    def has(self, *keywords: str) -> bool:
        """Is any of these substances on file?"""
        return bool(self.matching(*keywords))

    def is_severe_for(self, *keywords: str) -> bool:
        """Did the patient react severely **to one of these substances**?

        This is the question the TypeScript engine could not ask. It could only
        ask whether a severe reaction appeared anywhere in the list.
        """
        return any(e.is_severe for e in self.matching(*keywords))

    def reactions_for(self, *keywords: str) -> tuple[str, ...]:
        """Recorded reaction text for these substances, for flag provenance."""
        return tuple(e.reaction for e in self.matching(*keywords) if e.reaction)
