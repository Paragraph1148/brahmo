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


#: Valve lesions that make a DOAC unsafe in AF. Moderate-to-severe mitral
#: stenosis (rheumatic, in Indian practice) and a mechanical prosthesis are the
#: two accepted ones; other valve disease is not. Aortic stenosis is
#: deliberately absent — it is valve disease, but a patient with isolated AS and
#: AF may have a DOAC, and sending them to warfarin means lifelong INR
#: monitoring they do not need.
DOAC_CONTRAINDICATED = (
    "rheumatic", "rhd", "mitral stenosis", "mitral valve stenosis",
    "prosthetic valve", "mechanical valve", "valve replacement", "valvular",
)

#: Broader, for retrieval only. See :func:`derive_condition_tags`.
VALVULAR_FOR_RETRIEVAL = (*DOAC_CONTRAINDICATED, "aortic stenosis")


def doac_contraindicated(patient: Patient) -> bool:
    """Is a DOAC unsafe for this patient's AF?

    The original asked this question with three different keyword lists at
    three call sites, and the shortest one — ``"rheumatic", "valvular",
    "rhd"`` — drove the drug recommendation. A patient charted as plain
    "Mitral Stenosis" therefore received, in one report, a flag reading
    "Valvular AF → Anticoagulation INDICATED" from the five-keyword list and
    "Non-valvular AF: DOAC preferred over Warfarin" from the three-keyword
    one, with ``DOAC`` in the recommended classes. Rheumatic MS is routinely
    charted without the word "rheumatic", and a DOAC in rheumatic MS is the
    exact error this project was built to prevent.

    One definition, one call site.
    """
    return has_condition(patient, *DOAC_CONTRAINDICATED)


def is_valvular_for_retrieval(patient: Patient) -> bool:
    """Any valve disease worth pulling guidelines for. Liberal by design."""
    return has_condition(patient, *VALVULAR_FOR_RETRIEVAL)


#: Diagnostic thresholds for dysglycaemia (RSSDI 2022 / WHO).
HBA1C_DIAGNOSTIC = 6.5
FPG_DIAGNOSTIC = 126.0
RANDOM_GLUCOSE_DIAGNOSTIC = 200.0


def derive_condition_tags(patient: Patient) -> list[str]:
    """Retrieval tags — deliberately more generous than the predicates above.

    A safety gate should be conservative: do not act as if a patient is
    diabetic on weak evidence. Retrieval should be liberal: withholding the
    diabetes formulary from the model cannot make an answer safer, only less
    informed. The asymmetry is the point, and it is why this is a separate
    function rather than a reuse of ``is_diabetic``.
    """
    tags: list[str] = []

    def add(tag: str) -> None:
        if tag not in tags:
            tags.append(tag)

    hba1c = patient.lab("HbA1c")
    fbs = patient.lab("FBS")
    glucose = patient.lab("Glucose")
    dysglycaemic = (
        (hba1c is not None and hba1c >= HBA1C_DIAGNOSTIC)
        or (fbs is not None and fbs >= FPG_DIAGNOSTIC)
        or (glucose is not None and glucose >= RANDOM_GLUCOSE_DIAGNOSTIC)
    )
    if is_diabetic(patient) or dysglycaemic:
        add("diabetes")

    if has_htn(patient) or has_vascular_disease(patient):
        add("cardiovascular")
    if is_hf(patient):
        add("heart_failure")
    if is_af(patient):
        add("atrial_fibrillation")
    if has_condition(patient, "ckd", "chronic kidney disease", "renal", "nephropathy", "esrd"):
        add("ckd")
    if has_condition(patient, "nafld", "fatty liver", "nash"):
        add("nafld")
    if is_valvular_for_retrieval(patient):
        add("rheumatic_heart_disease")
    if is_elderly(patient):
        add("elderly")
    if has_condition(patient, "retinopathy", "neuropathy"):
        add("diabetes_complications")

    return tags
