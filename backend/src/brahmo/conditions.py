"""Condition detection — one source of truth for "does this patient have X".

Ported from ``src/lib/conditions.ts``, which already carries the fix this
project is known for: whole-word matching rather than substring, after 'af'
matched inside 'deaf', 'mi' inside 'mitral' and 'ef' inside 'reflux'. That
behaviour is held to the TypeScript by the differential suite.
"""

from __future__ import annotations

import re
from functools import lru_cache

from brahmo.domain.patient import Patient


@lru_cache(maxsize=512)
def _word_pattern(keyword: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(keyword.lower())}\b")


def has_condition(patient: Patient, *keywords: str) -> bool:
    """Whole-word match against the problem list."""
    text = " | ".join(patient.conditions).lower()
    return any(_word_pattern(k).search(text) for k in keywords)


def is_elderly(patient: Patient) -> bool:
    return patient.age >= 65


def is_hf(patient: Patient) -> bool:
    return has_condition(
        patient,
        "heart failure", "cardiac failure", "hf", "hfref", "hfpef", "chf",
        "ef", "ejection fraction", "lv dysfunction",
    )


def is_af(patient: Patient) -> bool:
    return has_condition(patient, "atrial fibrillation", "af", "afib", "a-fib")


def is_diabetic(patient: Patient) -> bool:
    return has_condition(
        patient, "t2dm", "t1dm", "dm", "diabetes", "diabetic", "diabetes mellitus"
    )


def has_htn(patient: Patient) -> bool:
    return has_condition(patient, "htn", "hypertension", "hypertensive")


def has_stroke(patient: Patient) -> bool:
    return has_condition(
        patient, "stroke", "tia", "cva", "cerebrovascular", "cerebrovascular accident"
    )


def has_vascular_disease(patient: Patient) -> bool:
    return has_condition(
        patient,
        "mi", "myocardial", "myocardial infarction", "pad", "cad", "ihd",
        "stemi", "nstemi", "angina", "acs", "peripheral arterial disease",
        "cabg", "pci", "ischaemic heart disease", "ischemic heart disease",
    )


def is_valvular(patient: Patient) -> bool:
    """Valvular or rheumatic disease — the AF pathway turns on this."""
    return has_condition(
        patient,
        "rheumatic", "valvular", "rhd", "mitral stenosis",
        "aortic stenosis", "prosthetic valve",
    )
