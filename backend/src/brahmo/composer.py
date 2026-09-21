"""Builds the India-specific prompt.

Nothing here decides anything clinical. The safety report arrives already
settled by :mod:`brahmo.engine`, and this module's job is to lay it out
alongside the guidelines, formulary and cost context the model would otherwise
have no way to know. That separation is the point: if a rule ever migrated into
this file, the guarantee that safety is decided before a model is consulted
would quietly stop being true.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from brahmo.conditions import derive_condition_tags
from brahmo.domain.patient import Patient
from brahmo.drugs import Formulary
from brahmo.report import SafetyReport, Severity
from brahmo.retrieval import (
    Guideline,
    GuidelineLibrary,
    HospitalFormulary,
    StockedDrug,
    drugs_for_tags,
)

HOSPITAL_CONTACTS: Mapping[str, Any] = {
    "endocrinology": {
        "diabetes_educator": "Sister Lakshmi, ext 3345 (Hindi/Tamil/English)",
        "dietitian": "Ms. Priya Raman, ext 3350 (South Indian diet specialist)",
        "podiatrist": "Dr. Suresh, ext 3360 (Mon/Wed/Fri)",
        "ophthalmology": "Dr. Iyer, ext 4410 (retinal screening)",
        "nephrology": "Dr. Ramachandran, ext 4420",
    },
    "cardiology": {
        "interventional": "Dr. Venkat, ext 4455 (cath lab)",
        "electrophysiology": "Dr. Anand, ext 4460",
        "heart_failure_clinic": "Dr. Meena, ext 4465 (Tue/Thu)",
        "cardiac_rehab": "Sister Priya, ext 4470",
        "ccu_nurse_station": "ext 3322",
        "code_stemi": "Call 4455 + alert CCU 3322",
    },
    "blood_bank": "O-negative available (2 units standby)",
}

_SEVERITY_LABELS = {
    Severity.CRITICAL: "\U0001f534 CRITICAL (must address)",
    Severity.WARNING: "\U0001f7e0 WARNING",
    Severity.CAUTION: "\U0001f7e1 CAUTION",
    Severity.INFO: "\U0001f535 INFO / Recommendation",
}

#: Values of ``insurance.provider`` that mean "none". Compared case-folded: the
#: original tests ``provider === "NONE"`` exactly while rendering the same field
#: as "None" elsewhere, so a record written the way it is displayed would read
#: as insured and lose the affordability guidance.
_NO_INSURANCE = frozenset({"", "none", "nil", "uninsured", "n/a", "na", "-"})


def is_uninsured(patient: Patient) -> bool:
    provider = (patient.insurance.get("provider") or "").strip().casefold()
    return provider in _NO_INSURANCE


@dataclass(frozen=True, slots=True)
class PromptMeta:
    condition_tags: tuple[str, ...]
    guidelines_count: int
    drugs_count: int
    safety_flags_count: int
    active_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_tags": list(self.condition_tags),
            "guidelines_count": self.guidelines_count,
            "drugs_count": self.drugs_count,
            "safety_flags_count": self.safety_flags_count,
            "active_sources": list(self.active_sources),
        }


@dataclass(frozen=True, slots=True)
class ComposedPrompts:
    grounded: str
    generic: str
    meta: PromptMeta

    def to_dict(self) -> dict[str, Any]:
        return {"optionC": self.grounded, "generic": self.generic, "meta": self.meta.to_dict()}


def _pairs(mapping: Mapping[str, Any]) -> str:
    return ", ".join(f"{k} {v}" for k, v in mapping.items() if v is not None and v != "")


def _medications(patient: Patient) -> str:
    if not patient.medications:
        return "None"
    return ", ".join(f"{m.drug} {m.dose}".strip() for m in patient.medications)


def _price(value: Decimal | None) -> str:
    return "—" if value is None else f"{value}"


def build_patient_section(patient: Patient) -> str:
    provider = patient.insurance.get("provider") or "None"
    notes = patient.insurance.get("notes")
    return (
        "## PATIENT\n"
        f"- **{patient.patient_label}** — {patient.age:g}{patient.sex}, BMI {patient.bmi}\n"
        f"- **Conditions:** {'; '.join(patient.conditions)}\n"
        f"- **Medications:** {_medications(patient)}\n"
        f"- **Allergies:** {', '.join(patient.allergies_raw)}\n"
        f"- **Labs:** {_pairs(patient.labs)}\n"
        f"- **Vitals:** {_pairs(patient.vitals)}\n"
        f"- **Insurance:** {provider}{f' ({notes})' if notes else ''}\n"
        f"- **Income context:** {patient.income_context}"
    )


def build_safety_section(report: SafetyReport) -> str:
    egfr = report.computed.egfr_display
    head = (
        f"- eGFR: {egfr if egfr is not None else '—'} "
        f"({report.computed.egfr_stage or '—'})\n"
        f"- CHA₂DS₂-VASc: "
        f"{report.computed.chads_vasc if report.computed.chads_vasc is not None else 'N/A'}\n"
        f"- BMI category: {report.computed.bmi_category or '—'}"
    )

    if not report.flags:
        return (
            "## SAFETY ENGINE OUTPUT\n"
            f"{head}\n\n"
            "No safety alerts triggered. Patient is clinically straightforward."
        )

    out = ["## SAFETY ENGINE OUTPUT (pre-computed - YOU MUST RESPECT THESE)", head]

    for severity in (Severity.CRITICAL, Severity.WARNING, Severity.CAUTION, Severity.INFO):
        group = report.by_severity(severity)
        if not group:
            continue
        out.append(f"\n### {_SEVERITY_LABELS[severity]}")
        for flag in group:
            block = [f"- **{flag.title}**", f"  {flag.detail}"]
            if flag.action:
                block.append(f"  → Action: {flag.action}")
            if flag.guideline_source:
                block.append(f"  → Source: {flag.guideline_source}")
            out.append("\n".join(block))

    if report.unresolved_medications:
        out.append(
            "\n### MEDICATIONS THE SAFETY ENGINE COULD NOT CHECK\n"
            + "\n".join(f"- **{m}**" for m in report.unresolved_medications)
            + "\n\nThese were not matched to the formulary, so no renal, heart-failure or"
            " interaction check was run against them. Their absence from the flags above"
            " is not a finding of safety."
        )

    if report.drugs_to_avoid:
        out.append(
            "\n### DRUGS TO AVOID for this patient\n"
            + "\n".join(f"- **{d.drug}** — {d.reason}" for d in report.drugs_to_avoid)
        )

    if report.recommended_drug_classes:
        out.append(
            "\n### RECOMMENDED DRUG CLASSES\n"
            + "\n".join(f"- {c}" for c in report.recommended_drug_classes)
        )

    return "\n".join(out)


def build_guidelines_section(guidelines: Sequence[Guideline]) -> str:
    """Guidelines grouped by source, sources in order of first appearance.

    Grouping is by source across the whole list, not by runs within it: the
    rows are ordered by year descending, so one source can surface at several
    points and every one of its recommendations still belongs under a single
    heading.
    """
    if not guidelines:
        return ""
    by_source: dict[str, list[Guideline]] = {}
    for g in guidelines:
        by_source.setdefault(g.source_id, []).append(g)

    out = [
        "## RELEVANT INDIAN GUIDELINES "
        "(cite these \u2014 do NOT cite ADA, ACC/AHA, ESC, NICE)"
    ]
    for source, items in by_source.items():
        out.append(f"\n### {source}")
        for g in items:
            evidence = g.evidence_level or "\u2014"
            out.append(
                f"- **{g.section}** ({g.year}, Evidence {evidence}): {g.recommendation}"
            )
    return "\n".join(out) + "\n"


def build_drugs_section(drugs: Sequence[StockedDrug], patient: Patient) -> str:
    """The formulary the model may prescribe from, grouped by drug class."""
    if not drugs:
        return ""
    by_class: dict[str, list[StockedDrug]] = {}
    for d in drugs:
        by_class.setdefault(d.drug_class, []).append(d)

    out = ["## AVAILABLE INDIAN DRUGS (use these brands + \u20b9 prices in your response)"]
    if is_uninsured(patient):
        out.append(
            "\n\u26a0\ufe0f PATIENT IS UNINSURED \u2014 prioritize NLEM drugs and cheapest "
            "options. Mention Jan Aushadhi Kendra availability for NLEM drugs."
        )

    for drug_class, items in by_class.items():
        out.append(f"\n### {drug_class}")
        for d in items:
            tags = [
                "NLEM\u2713" if d.drug.nlem_status else None,
                f"In stock ({d.stock_level})" if d.in_stock else "Not stocked",
                "\u26a0\ufe0fUNSAFE-IN-HF" if d.drug.hf_safe is False else None,
                "\u26a0\ufe0fHIGH HYPO RISK" if d.drug.hypoglycemia_risk == "high" else None,
                {"loss": "weight loss", "gain": "weight gain"}.get(d.drug.weight_effect),
            ]
            line = (
                f"- **{d.generic_name}** ({d.drug.indian_brand_name}, "
                f"{d.drug.manufacturer}) \u2014 {d.mrp_price} "
                f"[{' | '.join(t for t in tags if t)}]"
            )
            if d.drug.notes:
                line += f" \u2014 {d.drug.notes}"
            out.append(line)
    return "\n".join(out) + "\n"


def build_cost_section(patient: Patient) -> str:
    provider = patient.insurance.get("provider") or "NONE"
    out = [
        "## COST & INSURANCE CONTEXT",
        f"- Patient income: {patient.income_context}",
        f"- Insurance: {provider}",
    ]
    notes = patient.insurance.get("notes")
    if notes:
        out.append(f"- Insurance notes: {notes}")
    if is_uninsured(patient):
        out.append(
            "- **UNINSURED** — every prescription must be affordable. Prefer NLEM "
            "drugs available at Jan Aushadhi stores (50-80% cheaper than MRP)."
        )
    return "\n".join(out)


def build_hospital_section(tags: Sequence[str]) -> str:
    endo = HOSPITAL_CONTACTS["endocrinology"]
    cardio = HOSPITAL_CONTACTS["cardiology"]
    sections: list[str] = []

    if {"diabetes", "ckd", "diabetes_complications"} & set(tags):
        sections.append(
            "**Endocrinology / Diabetes care:**\n"
            f"  - Diabetes Educator: {endo['diabetes_educator']}\n"
            f"  - Dietitian: {endo['dietitian']}\n"
            f"  - Podiatrist: {endo['podiatrist']}\n"
            f"  - Ophthalmology (retinal screening): {endo['ophthalmology']}\n"
            f"  - Nephrology: {endo['nephrology']}"
        )
    if {"cardiovascular", "heart_failure", "atrial_fibrillation"} & set(tags):
        sections.append(
            "**Cardiology:**\n"
            f"  - Interventional / Cath lab: {cardio['interventional']}\n"
            f"  - Electrophysiology: {cardio['electrophysiology']}\n"
            f"  - Heart Failure Clinic: {cardio['heart_failure_clinic']}\n"
            f"  - Cardiac Rehab: {cardio['cardiac_rehab']}\n"
            f"  - CCU: {cardio['ccu_nurse_station']}\n"
            f"  - Code STEMI protocol: {cardio['code_stemi']}\n"
            f"  - Blood bank: {HOSPITAL_CONTACTS['blood_bank']}"
        )
    if not sections:
        return ""
    return "## APOLLO CHENNAI REFERRAL CONTACTS (mention relevant ones)\n" + "\n\n".join(sections)


def build_generic_prompt(patient: Patient, question: str) -> str:
    """The contrast arm: the same patient with none of the India context."""
    return f"""You are a clinical decision support AI advising a doctor.

PATIENT
- {patient.age:g}{patient.sex}, BMI {patient.bmi}
- Conditions: {'; '.join(patient.conditions)}
- Medications: {_medications(patient)}
- Allergies: {', '.join(patient.allergies_raw)}
- Labs: {_pairs(patient.labs)}
- Vitals: {_pairs(patient.vitals)}
- Insurance: {patient.insurance.get('provider') or 'None'}
- Income: {patient.income_context}

QUESTION
{question}

Provide a structured clinical recommendation including:
1. Immediate action
2. Drug recommendation with specific drug names and approximate cost
3. Why this drug over alternatives
4. Monitoring plan
5. Referrals
6. Patient education

Be concise — the doctor is your peer."""


@dataclass(frozen=True, slots=True)
class Composer:
    """Assembles prompts from the patient, the settled report and the corpus."""

    formulary: Formulary
    guidelines: GuidelineLibrary
    stock: HospitalFormulary
    instructions: str

    def compose(self, patient: Patient, report: SafetyReport, question: str) -> ComposedPrompts:
        tags = derive_condition_tags(patient)
        guidelines = self.guidelines.for_tags(tags)
        drugs = drugs_for_tags(self.formulary, self.stock, tags)

        sections = [
            "# CLINICAL CONSULT — Apollo Hospitals, Chennai",
            build_patient_section(patient),
            build_safety_section(report),
            build_guidelines_section(guidelines),
            build_drugs_section(drugs, patient),
            build_cost_section(patient),
            build_hospital_section(tags),
            self.instructions,
            f"## CLINICIAN QUESTION\n{question}",
        ]

        return ComposedPrompts(
            grounded="\n\n".join(s for s in sections if s),
            generic=build_generic_prompt(patient, question),
            meta=PromptMeta(
                condition_tags=tuple(tags),
                guidelines_count=len(guidelines),
                drugs_count=len(drugs),
                safety_flags_count=len(report.flags),
                active_sources=tuple(sorted({g.source_label for g in guidelines})),
            ),
        )
