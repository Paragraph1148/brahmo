"""The deterministic safety engine.

No language model is consulted anywhere in this module, and nothing here
performs I/O: the formulary and interaction table are passed in. That is what
lets the test suite assert the property mechanically rather than in prose.

Ported from ``src/lib/safety-engine.ts``. Where this diverges from the
original the reason is recorded at the point of divergence and pinned by a test
in ``tests/divergence/``.
"""

from __future__ import annotations

from dataclasses import dataclass

from brahmo.calculators import (
    ChadsVascInputs,
    bmi_category,
    calculate_chads_vasc,
    ckd_stage,
    egfr_exact,
    js_round,
    renal_dose_instruction,
    should_anticoagulate,
)
from brahmo.conditions import (
    has_htn,
    has_stroke,
    has_vascular_disease,
    is_af,
    is_diabetic,
    is_elderly,
    is_hf,
    is_valvular,
)
from brahmo.domain.patient import Patient
from brahmo.drugs import Formulary, Resolution, ResolvedMedication
from brahmo.interactions import InteractionTable
from brahmo.report import (
    AvoidEntry,
    ComputedValues,
    Provenance,
    SafetyFlag,
    SafetyReport,
    Severity,
)

ASPIRIN_KEYWORDS = ("aspirin", "salicylate", "nsaid", "ibuprofen", "diclofenac")

#: RSSDI 2022 sulfonylurea thresholds. Named rather than inlined because the
#: original's flag text cited one number while its condition used another.
SU_STOP_EGFR = 30.0
SU_CAUTION_EGFR = 60.0


@dataclass(frozen=True, slots=True)
class Engine:
    """A configured safety engine. Construct once, run per patient."""

    formulary: Formulary
    interactions: InteractionTable

    def run(self, patient: Patient) -> SafetyReport:
        egfr = self._egfr(patient)
        resolved = self.formulary.resolve_all(patient.medications)

        computed = ComputedValues(
            egfr=egfr,
            egfr_display=None if egfr is None else js_round(egfr),
            egfr_stage=ckd_stage(egfr),
            chads_vasc=self._chads_vasc(patient),
            bmi_category=bmi_category(patient.bmi) if patient.bmi else None,
        )

        flags: list[SafetyFlag] = []
        flags += _check_unresolved_medications(resolved)
        flags += _check_renal_dosing(resolved, egfr)
        flags += _check_hf_contraindications(patient, resolved)
        flags += _check_hypoglycemia_risk(patient, resolved, egfr)
        flags += _check_hyperkalemia_risk(patient, resolved, egfr)
        flags += self._check_interactions(resolved)
        flags += _check_allergies(patient, resolved)
        flags += _check_anticoagulation(patient, computed.chads_vasc)

        classes, rec_flags = _recommend_drug_classes(patient, egfr)
        flags += rec_flags

        # Stable: severity first, then the order the checkers ran, so a report
        # is reproducible and diffable rather than incidentally ordered.
        flags.sort(key=lambda f: f.severity.rank)

        return SafetyReport(
            patient_id=patient.id,
            computed=computed,
            flags=tuple(flags),
            recommended_drug_classes=tuple(classes),
            drugs_to_avoid=tuple(_list_drugs_to_avoid(patient, egfr)),
            unresolved_medications=tuple(
                r.medication.drug for r in resolved if not r.is_checkable
            ),
        )

    def _egfr(self, patient: Patient) -> float | None:
        """Unrounded, because the bands read it. See calculators.calculate_egfr."""
        if patient.creatinine is not None:
            return egfr_exact(patient.creatinine.canonical, patient.age, patient.sex)
        return patient.reported_egfr

    def _chads_vasc(self, patient: Patient) -> int | None:
        if not is_af(patient):
            return None
        return calculate_chads_vasc(
            ChadsVascInputs(
                has_hf=is_hf(patient),
                has_htn=has_htn(patient),
                age=patient.age,
                has_diabetes=is_diabetic(patient),
                has_prior_stroke=has_stroke(patient),
                has_vascular_disease=has_vascular_disease(patient),
                sex=patient.sex,
            )
        )

    def _check_interactions(self, resolved: tuple[ResolvedMedication, ...]) -> list[SafetyFlag]:
        drug_ids = frozenset(r.drug.id for r in resolved if r.drug is not None)
        flags: list[SafetyFlag] = []
        for ix in self.interactions.firing_for(drug_ids):
            names = tuple(n for n in (ix.drug_a_name, ix.drug_b_name) if n)
            flags.append(
                SafetyFlag(
                    category="interaction",
                    severity=ix.flag_severity,
                    title=f"{ix.drug_a_name} + {ix.drug_b_name}: {ix.severity.upper()}",
                    detail=f"{ix.clinical_effect}. Mechanism: {ix.mechanism}.",
                    drugs_involved=names,
                    action=ix.management,
                    provenance=Provenance(
                        rule_id="interaction.pairwise",
                        inputs=("medications",),
                        basis=f"drug_interactions#{ix.id}",
                    ),
                )
            )
        return flags


def _check_unresolved_medications(
    resolved: tuple[ResolvedMedication, ...],
) -> list[SafetyFlag]:
    """A medication the engine could not identify is checked for nothing.

    The TypeScript opens every checker with ``if (!m.drug_id) continue``, so an
    unrecognised drug produces no renal flag, no HF flag and no interaction —
    and the report comes back clean because nothing was looked at. Saying so is
    the whole point.
    """
    flags: list[SafetyFlag] = []
    for r in resolved:
        if r.is_checkable:
            continue
        if r.resolution is Resolution.AMBIGUOUS:
            options = ", ".join(d.generic_name for d in r.candidates)
            flags.append(
                SafetyFlag(
                    category="contraindication",
                    severity=Severity.WARNING,
                    title=f'"{r.medication.drug}" matches more than one formulary drug',
                    detail=(
                        f"Could be any of: {options}. No renal dosing, heart-failure or "
                        "interaction check has been run for this medication. Record the "
                        "specific preparation."
                    ),
                    drugs_involved=(r.medication.drug,),
                    action="Clarify which preparation is prescribed",
                    provenance=Provenance(
                        rule_id="resolution.ambiguous",
                        inputs=("medications",),
                        basis=None,
                    ),
                )
            )
        else:
            flags.append(
                SafetyFlag(
                    category="contraindication",
                    severity=Severity.CAUTION,
                    title=f'"{r.medication.drug}" is not in the formulary',
                    detail=(
                        "No renal dosing, heart-failure or interaction check has been run "
                        "for this medication. Its absence from the flags below is not a "
                        "finding of safety."
                    ),
                    drugs_involved=(r.medication.drug,),
                    action="Check manually",
                    provenance=Provenance(
                        rule_id="resolution.unknown", inputs=("medications",), basis=None
                    ),
                )
            )
    return flags


def _check_renal_dosing(
    resolved: tuple[ResolvedMedication, ...], egfr: float | None
) -> list[SafetyFlag]:
    if egfr is None:
        return []
    display = js_round(egfr)
    flags: list[SafetyFlag] = []

    for r in resolved:
        if r.drug is None:
            continue
        instruction = renal_dose_instruction(r.drug.renal_dosing, egfr)
        if not instruction:
            continue

        upper = instruction.upper()
        if "STOP" in upper or "AVOID" in upper:
            severity, action = Severity.CRITICAL, "STOP"
        elif "REDUCE" in upper or "CAUTIOUSLY" in upper or "CAUTION" in upper:
            severity, action = Severity.WARNING, "REDUCE / CAUTION"
        elif "MONITOR" in upper:
            severity, action = Severity.CAUTION, "MONITOR"
        else:
            continue

        flags.append(
            SafetyFlag(
                category="renal",
                severity=severity,
                title=f"{r.drug.generic_name}: {action} (eGFR {display})",
                detail=f"Patient eGFR {display} → {instruction}",
                drugs_involved=(r.drug.generic_name,),
                action=action,
                provenance=Provenance(
                    rule_id="renal.dosing",
                    inputs=("labs.Cr", "age", "sex", "medications"),
                    basis=f"drugs#{r.drug.id}.renal_dosing",
                ),
            )
        )
    return flags


def _check_hf_contraindications(
    patient: Patient, resolved: tuple[ResolvedMedication, ...]
) -> list[SafetyFlag]:
    if not is_hf(patient):
        return []
    flags: list[SafetyFlag] = []
    for r in resolved:
        # `is False` rather than falsy: a null hf_safe means unknown, not unsafe.
        if r.drug is not None and r.drug.hf_safe is False:
            flags.append(
                SafetyFlag(
                    category="heart_failure",
                    severity=Severity.CRITICAL,
                    title=f"{r.drug.generic_name} CONTRAINDICATED in Heart Failure",
                    detail=r.drug.notes or f"{r.drug.drug_class} not safe in HF.",
                    drugs_involved=(r.drug.generic_name,),
                    action="STOP / DO NOT USE",
                    guideline_source="RSSDI+CSI 2022",
                    provenance=Provenance(
                        rule_id="hf.contraindication",
                        inputs=("conditions", "medications"),
                        basis=f"drugs#{r.drug.id}.hf_safe",
                    ),
                )
            )
    return flags


def _check_hypoglycemia_risk(
    patient: Patient, resolved: tuple[ResolvedMedication, ...], egfr: float | None
) -> list[SafetyFlag]:
    """Hypoglycemia risk from agents that can cause it.

    Two corrections to the original.

    It fired a single critical "STOP the sulfonylurea" at any eGFR below 60
    while quoting RSSDI's rule for below 30. The advice and the trigger now
    agree: below 30 is a stop, 30-60 is a dose reduction with monitoring.

    It also applied sulfonylurea-specific wording to any drug carrying moderate
    or high hypoglycemia risk, so a patient on repaglinide was told to stop
    their sulfonylurea. The text now names the drug and its class.
    """
    at_risk = [
        r
        for r in resolved
        if r.drug is not None and r.drug.hypoglycemia_risk in ("high", "moderate")
    ]
    if not at_risk:
        return []

    beta_blockers = [
        r for r in resolved if r.drug is not None and r.drug.drug_class == "Beta blocker"
    ]
    flags: list[SafetyFlag] = []

    for r in at_risk:
        drug = r.drug
        assert drug is not None
        is_su = drug.drug_class == "Sulfonylurea"
        alternative = (
            "insulin or Linagliptin (no renal adjustment needed)"
            if is_su
            else "an agent without hypoglycemia risk"
        )

        if is_elderly(patient):
            flags.append(
                SafetyFlag(
                    category="hypoglycemia",
                    severity=Severity.WARNING,
                    title=f"Hypoglycemia risk: {drug.generic_name} in elderly",
                    detail=(
                        f"Patient is {patient.age:g}y. RSSDI 2022 recommends DPP4i "
                        "(e.g. Teneligliptin, Linagliptin) over agents with hypoglycemia "
                        "risk in the elderly."
                    ),
                    drugs_involved=(drug.generic_name,),
                    action="Consider switching to DPP4i",
                    guideline_source="RSSDI 2022",
                    provenance=Provenance(
                        rule_id="hypoglycemia.elderly",
                        inputs=("age", "medications"),
                        basis="RSSDI 2022",
                    ),
                )
            )

        if egfr is not None and egfr < SU_STOP_EGFR:
            flags.append(
                SafetyFlag(
                    category="hypoglycemia",
                    severity=Severity.CRITICAL,
                    title=(
                        f"{drug.generic_name} at eGFR {js_round(egfr)}: "
                        "STOP (advanced renal impairment)"
                    ),
                    detail=(
                        f"{drug.drug_class} accumulates in renal impairment and causes "
                        f"prolonged hypoglycemia. RSSDI 2022: stop below eGFR "
                        f"{SU_STOP_EGFR:g}. Use {alternative}."
                    ),
                    drugs_involved=(drug.generic_name,),
                    action=f"STOP - switch to {alternative}",
                    guideline_source="RSSDI 2022",
                    provenance=Provenance(
                        rule_id="hypoglycemia.ckd.stop",
                        inputs=("labs.Cr", "age", "sex", "medications"),
                        basis="RSSDI 2022",
                    ),
                )
            )
        elif egfr is not None and egfr < SU_CAUTION_EGFR:
            flags.append(
                SafetyFlag(
                    category="hypoglycemia",
                    severity=Severity.WARNING,
                    title=(
                        f"{drug.generic_name} at eGFR {js_round(egfr)}: "
                        "reduce dose and monitor"
                    ),
                    detail=(
                        f"{drug.drug_class} clearance falls with eGFR, raising hypoglycemia "
                        f"risk. RSSDI 2022: reduce dose and monitor between eGFR "
                        f"{SU_STOP_EGFR:g} and {SU_CAUTION_EGFR:g}; stop below "
                        f"{SU_STOP_EGFR:g}. Consider {alternative}."
                    ),
                    drugs_involved=(drug.generic_name,),
                    action="REDUCE DOSE / MONITOR",
                    guideline_source="RSSDI 2022",
                    provenance=Provenance(
                        rule_id="hypoglycemia.ckd.caution",
                        inputs=("labs.Cr", "age", "sex", "medications"),
                        basis="RSSDI 2022",
                    ),
                )
            )

        if beta_blockers:
            names = "/".join(b.name for b in beta_blockers)
            flags.append(
                SafetyFlag(
                    category="hypoglycemia",
                    severity=Severity.CAUTION,
                    title=f"{drug.generic_name} + {names}: hypoglycemia unawareness",
                    detail=(
                        "Beta blockers mask the adrenergic symptoms of hypoglycemia "
                        "(tachycardia, tremor). Patient must use SMBG and recognise "
                        "non-adrenergic symptoms (sweating, confusion)."
                    ),
                    drugs_involved=(drug.generic_name, *(b.name for b in beta_blockers)),
                    action="Patient education + SMBG",
                    provenance=Provenance(
                        rule_id="hypoglycemia.beta_blocker_masking",
                        inputs=("medications",),
                        basis=None,
                    ),
                )
            )
    return flags


def _check_hyperkalemia_risk(
    patient: Patient, resolved: tuple[ResolvedMedication, ...], egfr: float | None
) -> list[SafetyFlag]:
    drugs = [r.drug for r in resolved if r.drug is not None]
    acei_arb = [d for d in drugs if d.drug_class in ("ACE inhibitor", "ARB")]
    ksparing = [d for d in drugs if d.drug_class == "K-sparing diuretic"]
    if not acei_arb or not ksparing:
        return []

    potassium = patient.potassium
    k = None if potassium is None else potassium.canonical
    high_risk = (k is not None and k >= 5.0) or (egfr is not None and egfr < 60)

    detail = "Dual RAAS blockade + K-sparing diuretic significantly raises hyperkalemia risk."
    if k is not None:
        detail += f" Current K+ is {k:g} mEq/L."
    if egfr is not None and egfr < 60:
        detail += f" CKD (eGFR {js_round(egfr)}) compounds the risk."
    detail += " RSSDI+CSI: hold spironolactone if K+ >5.5. Adding SGLT2i mitigates risk."

    return [
        SafetyFlag(
            category="hyperkalemia",
            severity=Severity.CRITICAL if high_risk else Severity.WARNING,
            title=(
                f"Hyperkalemia risk: {acei_arb[0].generic_name} + {ksparing[0].generic_name}"
            ),
            detail=detail,
            drugs_involved=(acei_arb[0].generic_name, ksparing[0].generic_name),
            action=(
                "HOLD K-sparing diuretic"
                if k is not None and k > 5.5
                else "Monitor K+ at baseline, 1 wk, monthly"
            ),
            guideline_source="RSSDI+CSI 2022",
            provenance=Provenance(
                rule_id="hyperkalemia.dual_raas",
                inputs=("medications", "labs.K", "labs.Cr"),
                basis="RSSDI+CSI 2022",
            ),
        )
    ]


def _check_allergies(
    patient: Patient, resolved: tuple[ResolvedMedication, ...]
) -> list[SafetyFlag]:
    """Allergy flags, with severity read from the matching substance only.

    See :mod:`brahmo.domain.allergy`: the original decided how badly a patient
    reacted to one drug by searching the whole allergy list, so a penicillin
    anaphylaxis escalated an aspirin rash into an absolute contraindication.
    """
    allergies = patient.allergies
    flags: list[SafetyFlag] = []

    if allergies.has("sulfonamide", "sulfa"):
        for r in resolved:
            if r.drug is not None and r.drug.drug_class == "Sulfonylurea":
                flags.append(
                    SafetyFlag(
                        category="allergy",
                        severity=Severity.WARNING,
                        title=(
                            f"{r.drug.generic_name}: potential cross-reactivity with "
                            "sulfonamide allergy"
                        ),
                        detail=(
                            "Sulfonylureas share sulfonamide structure. Cross-reactivity is "
                            "uncommon but documented (especially severe sulfa reactions). "
                            "Consider non-SU alternative (DPP4i, SGLT2i)."
                        ),
                        drugs_involved=(r.drug.generic_name,),
                        action="Consider switching to non-sulfonylurea agent",
                        provenance=Provenance(
                            rule_id="allergy.sulfonamide_cross_reactivity",
                            inputs=("allergies", "medications"),
                            basis=None,
                        ),
                    )
                )

    if allergies.has(*ASPIRIN_KEYWORDS):
        severe = allergies.is_severe_for(*ASPIRIN_KEYWORDS)
        reactions = ", ".join(allergies.reactions_for(*ASPIRIN_KEYWORDS)) or "not recorded"
        flags.append(
            SafetyFlag(
                category="allergy",
                severity=Severity.CRITICAL if severe else Severity.WARNING,
                title=(
                    "Aspirin/NSAID allergy with a severe reaction on file — DO NOT give aspirin"
                    if severe
                    else "Aspirin/NSAID allergy on file — review before antiplatelet loading"
                ),
                detail=(
                    "Severe reaction documented against this substance. Do not load aspirin. "
                    "Use Clopidogrel 300-600mg or Ticagrelor 180mg as single-agent P2Y12 "
                    "loading and involve cardiology; aspirin desensitisation only in a "
                    "monitored setting."
                    if severe
                    else (
                        f"Recorded reaction to this substance: {reactions}. A mild cutaneous "
                        "reaction is not an absolute contraindication — confirm the reaction "
                        "history before loading aspirin. If aspirin is withheld, Clopidogrel "
                        "(Plavix, NLEM) is the substitute P2Y12 loading agent."
                    )
                ),
                drugs_involved=("Aspirin",),
                action=(
                    "DO NOT USE aspirin — load a P2Y12 inhibitor instead"
                    if severe
                    else "Confirm reaction history before aspirin loading"
                ),
                guideline_source="CSI 2017",
                provenance=Provenance(
                    rule_id="allergy.aspirin",
                    inputs=("allergies",),
                    basis="CSI 2017",
                ),
            )
        )

    if allergies.has("penicillin"):
        severe = allergies.is_severe_for("penicillin")
        flags.append(
            SafetyFlag(
                category="allergy",
                severity=Severity.CAUTION,
                title="Penicillin allergy on file",
                detail=(
                    "ANAPHYLAXIS documented against penicillin. Avoid all penicillins and "
                    "cephalosporins. Use alternative antibiotic class (macrolide, "
                    "fluoroquinolone, glycopeptide) if antibiotics needed during admission. "
                    "Note: aspirin, clopidogrel, ticagrelor, heparin, and fibrinolytics "
                    "are SAFE."
                    if severe
                    else "Avoid penicillins. Use alternative class if antibiotics required."
                ),
                action="Document; avoid β-lactams",
                provenance=Provenance(
                    rule_id="allergy.penicillin", inputs=("allergies",), basis=None
                ),
            )
        )
    return flags


def _check_anticoagulation(patient: Patient, chads_vasc: int | None) -> list[SafetyFlag]:
    if chads_vasc is None:
        return []
    valvular = is_valvular(patient)
    indicated = valvular or should_anticoagulate(chads_vasc, patient.sex)
    threshold = "≥3 for women" if patient.sex == "F" else "≥2 for men"

    return [
        SafetyFlag(
            category="recommendation",
            severity=Severity.WARNING if indicated else Severity.INFO,
            title=(
                f"Valvular AF → Anticoagulation INDICATED regardless of CHA₂DS₂-VASc "
                f"(score {chads_vasc})"
                if valvular
                else (
                    f"CHA₂DS₂-VASc = {chads_vasc} → "
                    f"{'Anticoagulation INDICATED' if indicated else 'Anticoagulation optional'}"
                )
            ),
            detail=(
                "CHA₂DS₂-VASc was derived and validated in NON-valvular AF and does not "
                "govern this decision. AF with rheumatic mitral stenosis or a prosthetic "
                "valve is an anticoagulation indication in its own right — the score is "
                "shown for completeness only. Warfarin, INR 2-3."
                if valvular
                else (
                    f"Threshold met ({threshold}). Recommend OAC unless contraindicated."
                    if indicated
                    else "Below threshold. Consider patient preference + bleeding risk."
                )
            ),
            guideline_source="IHRS/CSI 2018",
            provenance=Provenance(
                rule_id="af.anticoagulation",
                inputs=("conditions", "age", "sex"),
                basis="IHRS/CSI 2018",
            ),
        )
    ]


def _recommend_drug_classes(
    patient: Patient, egfr: float | None
) -> tuple[list[str], list[SafetyFlag]]:
    classes: list[str] = []
    flags: list[SafetyFlag] = []

    def rec(rule_id: str, title: str, detail: str, **kw: object) -> None:
        flags.append(
            SafetyFlag(
                category="recommendation",
                severity=Severity.INFO,
                title=title,
                detail=detail,
                provenance=Provenance(rule_id=rule_id, inputs=("conditions",), basis=None),
                **kw,  # type: ignore[arg-type]
            )
        )

    if is_diabetic(patient) and is_hf(patient):
        classes.append("SGLT2 inhibitor")
        rec(
            "recommend.sglt2_hf",
            "First-line: SGLT2 inhibitor for diabetes + HF",
            "Empagliflozin (EMPEROR-Reduced) or Dapagliflozin (DAPA-HF) provides dual "
            "benefit: glycemia + HF outcomes. RSSDI+CSI 2022 recommend regardless of "
            "HbA1c if T2DM + HFrEF.",
            action="ADD SGLT2i",
            guideline_source="RSSDI+CSI 2022",
        )

    if is_diabetic(patient) and egfr is not None and egfr < 60:
        if egfr >= 25:
            classes.append("SGLT2 inhibitor")
            rec(
                "recommend.sglt2_ckd",
                "Consider SGLT2 inhibitor for diabetic kidney disease",
                "Dapagliflozin (DAPA-CKD) provides renoprotection at eGFR ≥25. "
                "ACEi/ARB mandatory if albuminuria.",
                action="Consider adding SGLT2i",
                guideline_source="RSSDI 2022",
            )
        else:
            classes.append("DPP4 inhibitor (Linagliptin)")
            rec(
                "recommend.linagliptin_advanced_ckd",
                "Linagliptin: best DPP4i in advanced CKD",
                "Linagliptin has no renal dose adjustment requirement (hepatic clearance). "
                "Preferred when eGFR <30.",
                action="Use Linagliptin if DPP4i needed",
                guideline_source="RSSDI 2022",
            )

    if is_diabetic(patient) and is_elderly(patient):
        rec(
            "recommend.elderly_relaxed_target",
            "Elderly diabetic: relaxed HbA1c target 7.5-8%",
            "RSSDI 2022 recommends relaxed glycemic target in elderly with comorbidities "
            "to minimize hypoglycemia risk. Prefer DPP4i over sulfonylureas.",
            guideline_source="RSSDI 2022",
        )

    if is_af(patient):
        if is_valvular(patient):
            classes.append("Warfarin (RHD/valvular AF)")
            flags.append(
                SafetyFlag(
                    category="recommendation",
                    severity=Severity.WARNING,
                    title="Valvular/Rheumatic AF: Warfarin ONLY (DOACs contraindicated)",
                    detail=(
                        "RHD is common in India (rare in West). DOACs are contraindicated "
                        "in rheumatic mitral stenosis. INR target 2-3."
                    ),
                    guideline_source="IHRS/CSI 2018",
                    provenance=Provenance(
                        rule_id="recommend.warfarin_valvular_af",
                        inputs=("conditions",),
                        basis="IHRS/CSI 2018",
                    ),
                )
            )
        else:
            classes.append("DOAC")
            rec(
                "recommend.doac_nonvalvular_af",
                "Non-valvular AF: DOAC preferred over Warfarin",
                "IHRS/CSI 2018: Apixaban / Rivaroxaban / Dabigatran preferred. "
                "Apixaban has lowest bleeding risk.",
                guideline_source="IHRS/CSI 2018",
            )

    return classes, flags


def _list_drugs_to_avoid(patient: Patient, egfr: float | None) -> list[AvoidEntry]:
    avoid: list[AvoidEntry] = []
    allergies = patient.allergies

    if is_hf(patient):
        avoid.append(
            AvoidEntry("Pioglitazone", "Fluid retention worsens HF (contraindicated)")
        )
        avoid.append(
            AvoidEntry(
                "Saxagliptin",
                "FDA black box - increased HF hospitalization (SAVOR-TIMI)",
            )
        )
    if egfr is not None and egfr < 30:
        avoid.append(
            AvoidEntry("Metformin", f"eGFR {js_round(egfr)} < 30 (lactic acidosis risk)")
        )
        avoid.append(
            AvoidEntry(
                "Glimepiride / Glibenclamide",
                "Prolonged hypoglycemia in advanced CKD",
            )
        )
        avoid.append(AvoidEntry("NSAIDs", "Nephrotoxic in CKD"))
    if allergies.has("sulfonamide"):
        avoid.append(AvoidEntry("Sulfonylureas", "Potential sulfonamide cross-reactivity"))
    if allergies.has("penicillin", "beta-lactam", "amoxicillin"):
        avoid.append(
            AvoidEntry(
                "Penicillins, Cephalosporins",
                "Anaphylaxis history"
                if allergies.is_severe_for("penicillin", "beta-lactam", "amoxicillin")
                else "Penicillin allergy on file",
            )
        )
    if allergies.has("aspirin", "salicylate", "nsaid"):
        avoid.append(
            AvoidEntry(
                "Aspirin",
                "Severe aspirin/NSAID reaction documented"
                if allergies.is_severe_for("aspirin", "salicylate", "nsaid")
                else "Aspirin/NSAID allergy on file — confirm reaction before use",
            )
        )
    return avoid
