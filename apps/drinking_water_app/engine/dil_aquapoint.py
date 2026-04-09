"""
apps/drinking_water_app/engine/dil_aquapoint.py

AquaPoint — Decision Intelligence Layer
========================================

Applies the WaterPoint DIL framework to drinking water treatment decisions.

The drinking water treatment decision domain differs fundamentally from
wastewater and biosolids:

  - The governing constraint is public health protection, not process optimisation
  - LRV (Log Reduction Value) gap is the primary compliance signal — not TN
  - Single-barrier dependence is the highest-criticality flag in any treatment system
  - Residuals handling can create classified waste streams (PFAS concentrate,
    arsenic-bearing media) that materially affect the decision
  - Remote operation and catchment risk are primary data confidence drivers
  - Regulatory trajectory is toward higher LRV requirements, not lower

Design principles (same as WaterPoint and BioPoint DIL):
  - Good decisions are not made when uncertainty is removed.
    They are made when uncertainty is understood, bounded, and owned.
  - Data is not valuable in itself. Its value depends on the decision it informs.
  - Low confidence does not block decisions. It informs how they are framed.
  - The utility always carries ultimate accountability.

Main entry point
----------------
  build_aquapoint_dil(inputs, reasoning_output) -> AquaPointDILReport

Where:
  inputs           : SourceWaterInputs
  reasoning_output : AquaPointReasoningOutput returned by run_reasoning_engine()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── Level constants ───────────────────────────────────────────────────────────
CRIT_LOW    = "Low"
CRIT_MEDIUM = "Medium"
CRIT_HIGH   = "High"

CONF_HIGH       = "High"
CONF_ACCEPTABLE = "Acceptable"
CONF_LOW        = "Low"
CONF_VERY_LOW   = "Very Low"

VOI_HIGH     = "High"
VOI_MODERATE = "Moderate"
VOI_LOW      = "Low"

DR_READY      = "Ready to Proceed"
DR_CONDITIONS = "Proceed with Conditions"
DR_NOT_READY  = "Not Decision-Ready"

# ── Archetype labels ──────────────────────────────────────────────────────────
_ARCHETYPE_LABELS = {
    "A": "Direct Filtration",
    "B": "Conventional (Coag-Sed-Filt)",
    "C": "Compact Clarification",
    "D": "DAF + Filtration",
    "E": "Conventional + GAC/BAC",
    "F": "Softening",
    "G": "Ozone + Biological Filtration",
    "H": "Membrane (MF/UF + RO)",
    "I": "Contaminant-Specific",
}

# ── High-complexity residuals ─────────────────────────────────────────────────
_COMPLEX_RESIDUALS = {
    "membrane_concentrate_ro",
    "pfas_concentrate",
    "spent_ix_resin",
    "arsenic_bearing_media",
    "lime_sludge",
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class AQDecisionCriticality:
    level: str
    compliance_consequence: str
    service_consequence: str
    financial_consequence: str
    reputational_consequence: str
    asset_consequence: str
    reversibility: str
    regulatory_exposure: str
    classification_rationale: str


@dataclass
class AQDataConfidenceDimension:
    variable: str
    confidence: str
    volume: str
    issue: str
    implication: str


@dataclass
class AQDataConfidenceAssessment:
    dimensions: List[AQDataConfidenceDimension]
    overall_confidence: str
    critical_gaps: List[str]
    high_volume_low_confidence: List[str]
    summary: str


@dataclass
class AQVOIDimension:
    uncertainty: str
    voi_classification: str
    changes_archetype_selection: bool
    changes_lrv_adequacy: bool
    changes_sizing: bool
    changes_residuals_classification: bool
    changes_lifecycle_cost: bool
    changes_risk_materially: bool
    rationale: str


@dataclass
class AQVOIAssessment:
    dimensions: List[AQVOIDimension]
    high_voi_items: List[str]
    low_voi_items: List[str]
    proceed_without_investigation: bool
    investigation_recommendation: str


@dataclass
class AQRiskOwnershipDimension:
    risk_category: str
    primary_owner: str
    shared_with: List[str]
    utility_exposure: str
    note: str


@dataclass
class AQRiskOwnershipMap:
    dimensions: List[AQRiskOwnershipDimension]
    utility_accountability_statement: str
    residual_risk_statement: str


@dataclass
class AQDecisionBoundary:
    acceptable_performance_range: List[str]
    acceptable_uncertainty: List[str]
    resilience_margin: str
    fallback_position: str
    monitoring_requirements: List[str]
    intervention_triggers: List[str]
    critical_assumptions: List[str]


@dataclass
class AQDecisionReadiness:
    status: str
    basis: str
    conditions: List[str]
    critical_assumption_at_risk: Optional[str]
    strategic_implication: str


@dataclass
class AquaPointDILReport:
    # Context
    decision_context: str
    preferred_archetype: str
    preferred_archetype_label: str
    n_viable_archetypes: int

    # Seven components
    criticality: AQDecisionCriticality
    data_confidence: AQDataConfidenceAssessment
    voi: AQVOIAssessment
    risk_ownership: AQRiskOwnershipMap
    decision_boundary: AQDecisionBoundary
    readiness: AQDecisionReadiness

    # Closing
    closing_statement: str


# ── Helper: extract flat context from inputs + reasoning output ───────────────

def _extract_context(inputs, reasoning) -> dict:
    """
    Flatten SourceWaterInputs + AquaPointReasoningOutput into a context dict.
    All DIL components read from this dict — not directly from the objects.
    """
    # Preferred archetype
    pref_key   = getattr(reasoning, "preferred_archetype_key", "") or ""
    pref_label = _ARCHETYPE_LABELS.get(pref_key, pref_key)

    # Viable archetypes
    arch_sel = getattr(reasoning, "archetype_selection", None)
    viable   = getattr(arch_sel, "viable_archetypes", []) if arch_sel else []
    requires_membrane  = getattr(arch_sel, "requires_membrane", False) if arch_sel else False
    requires_advanced  = getattr(arch_sel, "requires_advanced_treatment", False) if arch_sel else False
    ozone_viable       = getattr(arch_sel, "ozone_viable", True) if arch_sel else True

    # Tier 1 pass/fail for preferred archetype
    tier1_pass   = True
    tier1_issues = []
    top_score    = None
    for sc in getattr(reasoning, "scores", []):
        if sc.archetype_key == pref_key:
            tier1_pass   = sc.tier1_pass
            tier1_issues = sc.tier1_issues
            top_score    = sc
            break

    # LRV for preferred archetype
    lrv_result = None
    for k, v in getattr(reasoning, "lrv_by_archetype", {}).items():
        if k == pref_key:
            lrv_result = v
            break

    lrv_gap_any    = False
    lrv_gap_protozoa = False
    single_barrier = []
    lrv_key_risks  = []
    if lrv_result:
        lrv_gap_any      = any(v > 0 for v in lrv_result.gap_high.values())
        lrv_gap_protozoa = lrv_result.gap_high.get("protozoa", 0) > 0
        single_barrier   = lrv_result.single_barrier_dependence
        lrv_key_risks    = lrv_result.key_risks

    # Residuals
    residuals_obj = getattr(reasoning, "residuals", None)
    pref_residuals_result = None
    problem_transfer = []
    classified_waste = []
    biopoint_handoff = False
    residuals_complexity = "low"
    if residuals_obj and hasattr(residuals_obj, "archetype_assessments"):
        pref_residuals_result = residuals_obj.archetype_assessments.get(pref_key)
    if pref_residuals_result:
        problem_transfer    = pref_residuals_result.problem_transfer_flags
        classified_waste    = pref_residuals_result.classified_waste_streams
        biopoint_handoff    = pref_residuals_result.biopoint_handoff_required
        residuals_complexity= pref_residuals_result.complexity_rating

    # Contaminant modules required
    classification = getattr(reasoning, "classification", None)
    contaminant_modules = getattr(classification, "contaminant_modules_required", []) if classification else []
    primary_constraint  = getattr(classification, "primary_constraint", "") if classification else ""

    return {
        # Archetype
        "pref_key"              : pref_key,
        "pref_label"            : pref_label,
        "n_viable"              : len(viable),
        "requires_membrane"     : requires_membrane,
        "requires_advanced"     : requires_advanced,
        "ozone_viable"          : ozone_viable,

        # Tier 1
        "tier1_pass"            : tier1_pass,
        "tier1_issues"          : tier1_issues,

        # LRV
        "lrv_gap_any"           : lrv_gap_any,
        "lrv_gap_protozoa"      : lrv_gap_protozoa,
        "single_barrier"        : single_barrier,
        "lrv_key_risks"         : lrv_key_risks,
        "lrv_result"            : lrv_result,

        # Source water
        "source_type"           : inputs.source_type,
        "catchment_risk"        : inputs.catchment_risk,
        "variability_class"     : inputs.variability_class,
        "turbidity_p99"         : inputs.turbidity_p99_ntu,
        "toc_median"            : inputs.toc_median_mg_l,
        "toc_p95"               : inputs.toc_p95_mg_l,
        "pfas_detected"         : inputs.pfas_detected,
        "pfas_ng_l"             : inputs.pfas_concentration_ng_l,
        "arsenic_ug_l"          : inputs.arsenic_ug_l,
        "cyanobacteria"         : inputs.cyanobacteria_confirmed,
        "cyanotoxin"            : inputs.cyanotoxin_detected,
        "troc_concern"          : inputs.troc_concern,
        "tds_median"            : inputs.tds_median_mg_l,
        "hardness_median"       : inputs.hardness_median_mg_l,
        "iron_median"           : inputs.iron_median_mg_l,
        "manganese_median"      : inputs.manganese_median_mg_l,

        # Operational
        "design_flow"           : inputs.design_flow_ML_d,
        "is_retrofit"           : inputs.is_retrofit,
        "land_constrained"      : inputs.land_constrained,
        "remote_operation"      : inputs.remote_operation,
        "treatment_objective"   : inputs.treatment_objective,

        # LRV targets
        "lrv_required_protozoa" : inputs.pathogen_lrv_required_protozoa,
        "lrv_required_bacteria" : inputs.pathogen_lrv_required_bacteria,
        "lrv_required_virus"    : inputs.pathogen_lrv_required_virus,

        # Classification
        "primary_constraint"    : primary_constraint,
        "contaminant_modules"   : contaminant_modules,

        # Residuals
        "problem_transfer"      : problem_transfer,
        "classified_waste"      : classified_waste,
        "biopoint_handoff"      : biopoint_handoff,
        "residuals_complexity"  : residuals_complexity,

        # Reasoning outputs
        "critical_uncertainties": getattr(reasoning, "critical_uncertainties", []),
        "key_warnings"          : getattr(reasoning, "key_warnings", []),
        "next_steps"            : getattr(reasoning, "next_steps", []),
        "executive_summary"     : getattr(reasoning, "executive_summary", ""),
    }


# ── Component 1: Decision Context ─────────────────────────────────────────────

def _build_context(ctx: dict) -> str:
    flow        = ctx["design_flow"]
    source      = ctx["source_type"].replace("_", " ")
    pref        = ctx["pref_label"]
    pref_key    = ctx["pref_key"]
    catchment   = ctx["catchment_risk"]
    objective   = ctx["treatment_objective"]
    n_viable    = ctx["n_viable"]
    pfas        = ctx["pfas_detected"]
    lrv_gap     = ctx["lrv_gap_any"]
    tier1       = ctx["tier1_pass"]

    pfas_note = (
        " PFAS has been detected in source water — treatment train selection and "
        "residuals handling are constrained by PFAS management requirements."
        if pfas else ""
    )

    lrv_note = (
        " The preferred archetype has a confirmed LRV gap against the required "
        "pathogen reduction targets — this is a Tier 1 safety failure and must "
        "be resolved before the archetype can be recommended."
        if lrv_gap or not tier1 else
        " The preferred archetype meets LRV targets at the high credit estimate."
    )

    return (
        f"A {flow:.0f} ML/d drinking water treatment plant drawing from a {source} source "
        f"with {catchment} catchment risk is under evaluation for treatment selection. "
        f"Treatment objective: {objective}. "
        f"The reasoning engine has assessed {n_viable} viable treatment archetype(s). "
        f"The preferred archetype is {pref} (Archetype {pref_key})."
        f"{pfas_note}{lrv_note} "
        f"Primary source constraint: {ctx['primary_constraint'] or 'not characterised'}."
    )


# ── Component 2: Decision Criticality ─────────────────────────────────────────

def _build_criticality(ctx: dict) -> AQDecisionCriticality:
    score = 0

    flow         = ctx["design_flow"]
    catchment    = ctx["catchment_risk"]
    single_b     = ctx["single_barrier"]
    lrv_gap      = ctx["lrv_gap_any"]
    lrv_gap_prot = ctx["lrv_gap_protozoa"]
    pfas         = ctx["pfas_detected"]
    cyanotoxin   = ctx["cyanotoxin"]
    arsenic      = ctx["arsenic_ug_l"]
    objective    = ctx["treatment_objective"]
    remote       = ctx["remote_operation"]
    retrofit     = ctx["is_retrofit"]
    requires_mem = ctx["requires_membrane"]
    requires_adv = ctx["requires_advanced"]
    classified_w = ctx["classified_waste"]
    tier1        = ctx["tier1_pass"]
    variability  = ctx["variability_class"]
    contaminants = ctx["contaminant_modules"]
    residuals_cx = ctx["residuals_complexity"]

    # Compliance consequence — LRV gap is the primary drinking water compliance signal
    if not tier1 or lrv_gap_prot:
        compliance_c = (
            "High — the preferred treatment archetype has a confirmed LRV deficit for "
            "protozoa (Cryptosporidium/Giardia). This is a Tier 1 safety failure. "
            "No archetype with a protozoan LRV gap is acceptable for potable supply."
        )
        score += 3
    elif lrv_gap:
        compliance_c = (
            "High — LRV gap exists for one or more pathogen classes. "
            "The treatment train does not meet the required log reduction targets "
            "under conservative barrier credit assumptions."
        )
        score += 2
    elif single_b:
        compliance_c = (
            "Medium — LRV targets are met but single-barrier dependence is present. "
            "Loss of one barrier creates a compliance breach. "
            "Redundancy improvement is required for robust compliance."
        )
        score += 1
    else:
        compliance_c = (
            "Low — LRV targets are met with acceptable barrier redundancy. "
            "No immediate compliance gap identified."
        )

    # Service consequence
    if flow >= 100:
        service_c = (
            f"High — {flow:.0f} ML/d plant serving a large population. "
            "Treatment failure has immediate public health consequence at scale. "
            "No operational tolerance for barrier loss."
        )
        score += 2
    elif flow >= 20:
        service_c = (
            f"Medium — {flow:.0f} ML/d plant. Service disruption has material "
            "community health impact. Backup supply capacity must be confirmed."
        )
        score += 1
    else:
        service_c = (
            f"Low — {flow:.0f} ML/d plant. Service consequence is contained "
            "and manageable with emergency supply arrangements."
        )

    # Catchment risk
    if catchment in ("high", "very_high"):
        score += 2
    elif catchment == "moderate":
        score += 1

    # Financial consequence
    if requires_mem or requires_adv:
        financial_c = (
            "High — membrane or advanced treatment is required. "
            "Capital commitment is substantial with significant technology risk, "
            "membrane replacement cycles, and energy cost dependency."
        )
        score += 2
    elif len(contaminants) >= 2:
        financial_c = (
            f"Medium — {len(contaminants)} contaminant-specific treatment modules required. "
            "Multi-module systems carry cost overrun and integration risk."
        )
        score += 1
    else:
        financial_c = (
            "Low — treatment selection is within the established technology range "
            "with predictable capital and operating costs."
        )

    # Reputational consequence
    if pfas or cyanotoxin or (arsenic > 10):
        reputational_c = (
            "High — treatment decision involves a publicly visible contaminant "
            "(PFAS, cyanotoxins, or arsenic). Community and media scrutiny is elevated. "
            "Treatment failure or contaminant exceedance creates significant reputational exposure."
        )
        score += 2
    elif catchment in ("high", "very_high") or objective == "recycled":
        reputational_c = (
            "Medium — high catchment risk or recycled water objective creates "
            "elevated public visibility. Treatment adequacy will be scrutinised."
        )
        score += 1
    else:
        reputational_c = (
            "Low — treatment selection is within the expected range for source type "
            "and public scrutiny is not elevated."
        )

    # Asset consequence
    if retrofit:
        asset_c = (
            "Medium — retrofit scenario constrains future configuration options. "
            "Technology selection must be compatible with existing infrastructure "
            "for the full asset life."
        )
        score += 1
    elif requires_mem:
        asset_c = (
            "High — membrane system locks in a technology with regular replacement "
            "cycles (5–10 years) and energy dependency for the full plant life. "
            "Stranded asset risk if membrane technology advances significantly."
        )
        score += 1
    else:
        asset_c = (
            "Low — conventional treatment train retains operational flexibility "
            "and can be modified or supplemented without stranding capital."
        )

    # Reversibility
    if requires_mem or residuals_cx in ("high", "very_high"):
        reversibility = (
            "Low reversibility — membrane infrastructure or complex residuals systems "
            "represent committed capital with significant retrofit cost to change. "
            "Technology selection must be right at concept stage."
        )
        score += 1
    elif len(classified_w) > 0:
        reversibility = (
            "Moderate reversibility — classified waste streams (PFAS, arsenic) create "
            "operational commitments that are difficult to exit once treatment is operational."
        )
    else:
        reversibility = (
            "High reversibility — conventional treatment allows operational "
            "flexibility and incremental upgrade without stranding capital."
        )

    # Regulatory exposure
    if pfas or (arsenic > 10):
        regulatory_c = (
            "High — PFAS and arsenic are under active regulatory review in Australia. "
            "Health-based guideline values are tightening. "
            "The treatment system must be designed for the regulatory endpoint, "
            "not the current guideline value."
        )
        score += 2
    elif catchment in ("high", "very_high") or objective in ("recycled",):
        regulatory_c = (
            "Medium — regulatory trajectory for catchment risk and recycled water "
            "objectives is toward higher LRV requirements and more rigorous validation. "
            "Design should include headroom above current minimum requirements."
        )
        score += 1
    else:
        regulatory_c = (
            "Low — current regulatory framework is stable with no near-term "
            "major changes anticipated for this source type and treatment objective."
        )

    # Remote operation floor — any remote potable supply is at least Medium criticality
    if remote and score < 5:
        score = 5   # floor to Medium — remote operation raises all consequence dimensions

    # Classify — drinking water thresholds (public health primacy)
    if score >= 9:
        level = CRIT_HIGH
    elif score >= 5:
        level = CRIT_MEDIUM
    else:
        level = CRIT_LOW

    rationale = (
        f"Decision criticality is rated {level} based on: "
        f"{'protozoan LRV gap — Tier 1 safety failure, ' if not tier1 or lrv_gap_prot else ''}"
        f"{'confirmed LRV deficit for one or more pathogen classes, ' if lrv_gap and not lrv_gap_prot else ''}"
        f"{'single-barrier dependence present, ' if single_b else ''}"
        f"{'large population served, ' if flow >= 100 else ''}"
        f"{'high or very high catchment risk, ' if catchment in ('high','very_high') else ''}"
        f"{'PFAS/arsenic regulatory exposure, ' if pfas or arsenic > 10 else ''}"
        f"{'membrane system capital commitment, ' if requires_mem else ''}"
        f"{'remote operation, ' if remote else ''}"
        f"and regulatory trajectory. "
        f"This decision warrants "
        f"{'full board-level authorisation, independent peer review, and regulator pre-consultation' if level == CRIT_HIGH else 'senior management review and documented engineering justification' if level == CRIT_MEDIUM else 'standard delegated authority'}."
    )

    return AQDecisionCriticality(
        level                    = level,
        compliance_consequence   = compliance_c,
        service_consequence      = service_c,
        financial_consequence    = financial_c,
        reputational_consequence = reputational_c,
        asset_consequence        = asset_c,
        reversibility            = reversibility,
        regulatory_exposure      = regulatory_c,
        classification_rationale = rationale,
    )


# ── Component 3: Data Confidence Assessment ───────────────────────────────────

def _build_data_confidence(ctx: dict) -> AQDataConfidenceAssessment:
    _conf_order = {CONF_HIGH: 3, CONF_ACCEPTABLE: 2, CONF_LOW: 1, CONF_VERY_LOW: 0}
    dims: List[AQDataConfidenceDimension] = []

    variability = ctx["variability_class"]
    catchment   = ctx["catchment_risk"]
    turb_p99    = ctx["turbidity_p99"]
    toc_p95     = ctx["toc_p95"]
    remote      = ctx["remote_operation"]
    pfas        = ctx["pfas_detected"]
    pfas_ng_l   = ctx["pfas_ng_l"]
    arsenic     = ctx["arsenic_ug_l"]
    cyanobact   = ctx["cyanobacteria"]
    flow        = ctx["design_flow"]
    retrofit    = ctx["is_retrofit"]
    single_b    = ctx["single_barrier"]
    lrv_result  = ctx["lrv_result"]

    # 1. Source water variability and event characterisation
    if variability in ("high", "extreme"):
        var_conf = CONF_LOW
        var_issue = (
            f"Source water variability is classified as '{variability}'. "
            f"P99 turbidity of {turb_p99:.0f} NTU indicates significant event-driven "
            f"loading. Treatment train must be designed for the worst observed conditions, "
            f"not average or P95 values. Event characterisation is the critical data gap."
        )
    elif variability == "moderate":
        var_conf = CONF_ACCEPTABLE
        var_issue = (
            f"Moderate variability with P99 turbidity {turb_p99:.0f} NTU. "
            "Acceptable for concept-stage treatment selection. "
            "Detailed design should use extended event records."
        )
    else:
        var_conf = CONF_HIGH
        var_issue = (
            f"Low variability source. P99 turbidity {turb_p99:.0f} NTU. "
            "Source water quality is reliable and well-characterised."
        )
    dims.append(AQDataConfidenceDimension(
        variable   = "Source water variability and event characterisation",
        confidence = var_conf,
        volume     = "moderate" if variability in ("moderate",) else "low" if variability in ("high","extreme") else "high",
        issue      = var_issue,
        implication= "Governs treatment train robustness and coagulation system sizing.",
    ))

    # 2. Catchment risk and pathogen loading
    if catchment in ("high", "very_high"):
        catch_conf = CONF_LOW
        catch_issue = (
            f"Catchment risk is '{catchment}'. Pathogen loading characterisation "
            "at high risk levels requires site-specific QMRA, not generic LRV targets. "
            "Default LRV requirements may not be conservative enough for this catchment."
        )
    elif catchment == "moderate":
        catch_conf = CONF_ACCEPTABLE
        catch_issue = (
            "Moderate catchment risk. Default LRV targets are appropriate for concept stage. "
            "Detailed QMRA is recommended before detailed design."
        )
    else:
        catch_conf = CONF_HIGH
        catch_issue = "Low catchment risk. Standard LRV targets are conservative for this source."
    dims.append(AQDataConfidenceDimension(
        variable   = "Catchment risk and pathogen loading",
        confidence = catch_conf,
        volume     = "moderate",
        issue      = catch_issue,
        implication= "Determines whether default LRV targets are adequate or site-specific QMRA is required.",
    ))

    # 3. NOM / TOC and disinfection by-product formation
    if toc_p95 > 10 or (toc_p95 > 5 and variability in ("high","extreme")):
        nom_conf = CONF_LOW
        nom_issue = (
            f"P95 TOC of {toc_p95:.1f} mg/L presents DBP formation risk. "
            "Coagulation performance under high NOM loading has not been confirmed. "
            "TOC treatability testing (jar testing at P95 conditions) is required "
            "before coagulant type and dose can be confirmed."
        )
    elif toc_p95 > 5:
        nom_conf = CONF_ACCEPTABLE
        nom_issue = (
            f"P95 TOC of {toc_p95:.1f} mg/L is moderate. DBP risk is manageable "
            "with conventional coagulation. Treatability is assumed from published data."
        )
    else:
        nom_conf = CONF_HIGH
        nom_issue = f"Low TOC (P95: {toc_p95:.1f} mg/L). DBP risk is low. Coagulation performance is predictable."
    dims.append(AQDataConfidenceDimension(
        variable   = "NOM/TOC characterisation and DBP formation potential",
        confidence = nom_conf,
        volume     = "moderate",
        issue      = nom_issue,
        implication= "Affects coagulant selection, ozone viability, and DBP compliance confidence.",
    ))

    # 4. LRV barrier performance validation
    if single_b:
        lrv_conf = CONF_LOW
        lrv_issue = (
            "Single-barrier dependence is present — one barrier provides >50% of "
            "required LRV for at least one pathogen class. "
            "Performance validation of this barrier under operating conditions "
            "has not been confirmed at this site. "
            "Barrier failure would create an immediate compliance breach."
        )
    elif lrv_result and any(v > 0 for v in lrv_result.gap_low.values()):
        lrv_conf = CONF_ACCEPTABLE
        lrv_issue = (
            "LRV targets are met under high credit assumptions but not under "
            "conservative (low) credit assumptions. Barrier performance under "
            "stressed conditions has not been validated at this site."
        )
    else:
        lrv_conf = CONF_HIGH
        lrv_issue = (
            "LRV targets are met under both conservative and optimistic credit assumptions. "
            "Barrier redundancy is adequate."
        )
    dims.append(AQDataConfidenceDimension(
        variable   = "LRV barrier performance validation",
        confidence = lrv_conf,
        volume     = "moderate",
        issue      = lrv_issue,
        implication= "Directly determines whether the treatment train is safe for potable supply.",
    ))

    # 5. PFAS / contaminant characterisation
    if pfas and pfas_ng_l > 0:
        pfas_conf = CONF_ACCEPTABLE
        pfas_issue = (
            f"PFAS detected at {pfas_ng_l:.0f} ng/L. Concentration is characterised. "
            "Treatment selection must account for PFAS removal and residuals management. "
            "PFAS speciation (PFOS, PFOA, PFAS sum) should be confirmed before "
            "selecting treatment technology."
        )
    elif pfas:
        pfas_conf = CONF_LOW
        pfas_issue = (
            "PFAS detected but concentration not characterised. "
            "Treatment technology selection cannot be finalised without confirmed "
            "PFAS speciation and concentration. PFAS health guideline compliance "
            "cannot be assessed without this data."
        )
    elif arsenic > 10:
        pfas_conf = CONF_ACCEPTABLE
        pfas_issue = (
            f"Arsenic at {arsenic:.0f} µg/L exceeds the ADWG guideline of 10 µg/L. "
            "Arsenic-specific treatment is required. Speciation (As(III) vs As(V)) "
            "affects removal efficiency and has not been confirmed."
        )
    elif ctx["troc_concern"]:
        pfas_conf = CONF_LOW
        pfas_issue = (
            "Trace organic contaminant (TrOC) concern flagged. "
            "TrOC identity, concentration, and health relevance have not been characterised. "
            "This gap must be closed before advanced treatment selection is finalised."
        )
    else:
        pfas_conf = CONF_HIGH
        pfas_issue = "No PFAS, arsenic, or TrOC concerns flagged. Contaminant baseline is adequate."
    dims.append(AQDataConfidenceDimension(
        variable   = "PFAS / contaminant characterisation",
        confidence = pfas_conf,
        volume     = "low" if (pfas and pfas_ng_l == 0) else "moderate",
        issue      = pfas_issue,
        implication= "Determines whether contaminant-specific treatment is required and which residuals are generated.",
    ))

    # 6. Operational context and operator capability
    if remote:
        ops_conf = CONF_LOW
        ops_issue = (
            "Remote operation context. Operator attendance is limited and response "
            "to process upsets is delayed. Treatment train complexity must be matched "
            "to available operator capability. Advanced or membrane-based systems "
            "may not be suitable without confirmed remote monitoring capability."
        )
    elif retrofit:
        ops_conf = CONF_ACCEPTABLE
        ops_issue = (
            "Retrofit context. Existing operator familiarity is an asset, but "
            "new technology integration requires confirmed training and support. "
            "Operational compatibility with existing infrastructure should be verified."
        )
    else:
        ops_conf = CONF_HIGH
        ops_issue = "Standard operational context. Operator capability assumed adequate for the selected archetype."
    dims.append(AQDataConfidenceDimension(
        variable   = "Operational context and operator capability",
        confidence = ops_conf,
        volume     = "low" if remote else "moderate",
        issue      = ops_issue,
        implication= "Affects technology selection, monitoring requirements, and commissioning programme.",
    ))

    # Summary
    worst = min(dims, key=lambda d: _conf_order.get(d.confidence, 0))
    n_low = sum(1 for d in dims if _conf_order.get(d.confidence, 0) <= 1)
    critical_gaps = [d.variable for d in dims if _conf_order.get(d.confidence, 0) <= 1]
    high_vol_low  = [d.variable for d in dims if d.volume == "high" and _conf_order.get(d.confidence, 0) <= 1]

    summary = (
        f"Data confidence is rated {worst.confidence} overall. "
        f"{n_low} of {len(dims)} assessment dimensions have Low or Very Low confidence. "
        + (f"Single-barrier dependence is the primary actionable gap — barrier redundancy must be addressed. " if single_b else "")
        + (f"PFAS characterisation is incomplete — this must be resolved before treatment commitment. " if pfas and pfas_ng_l == 0 else "")
        + f"This confidence level is {'adequate for concept-stage treatment selection with conditions' if n_low <= 2 else 'marginal for concept-stage commitment without targeted investigation'}."
    )

    return AQDataConfidenceAssessment(
        dimensions              = dims,
        overall_confidence      = worst.confidence,
        critical_gaps           = critical_gaps,
        high_volume_low_confidence = high_vol_low,
        summary                 = summary,
    )


# ── Component 4: Value of Information ─────────────────────────────────────────

def _build_voi(ctx: dict, data_conf: AQDataConfidenceAssessment) -> AQVOIAssessment:
    dims: List[AQVOIDimension] = []

    single_b    = ctx["single_barrier"]
    lrv_gap     = ctx["lrv_gap_any"]
    pfas        = ctx["pfas_detected"]
    pfas_ng_l   = ctx["pfas_ng_l"]
    arsenic     = ctx["arsenic_ug_l"]
    catchment   = ctx["catchment_risk"]
    variability = ctx["variability_class"]
    toc_p95     = ctx["toc_p95"]
    remote      = ctx["remote_operation"]
    requires_mem= ctx["requires_membrane"]
    contaminants= ctx["contaminant_modules"]
    problem_xfr = ctx["problem_transfer"]
    classified_w= ctx["classified_waste"]
    pref_key    = ctx["pref_key"]

    # 1. PFAS characterisation (if detected but unquantified)
    if pfas and pfas_ng_l == 0:
        dims.append(AQVOIDimension(
            uncertainty                 = "PFAS speciation and concentration",
            voi_classification          = VOI_HIGH,
            changes_archetype_selection = True,
            changes_lrv_adequacy        = False,
            changes_sizing              = True,
            changes_residuals_classification = True,
            changes_lifecycle_cost      = True,
            changes_risk_materially     = True,
            rationale=(
                "PFAS is detected but concentration and speciation are not characterised. "
                "PFAS concentration determines whether activated carbon, ion exchange, "
                "or membrane treatment is required — these are materially different archetypes "
                "with different capital cost, energy, and residuals profiles. "
                "Treatment selection cannot be finalised without this data."
            ),
        ))

    # 2. Catchment QMRA (high or very high risk)
    if catchment in ("high", "very_high"):
        dims.append(AQVOIDimension(
            uncertainty                 = "Site-specific QMRA (catchment pathogen loading)",
            voi_classification          = VOI_HIGH,
            changes_archetype_selection = False,
            changes_lrv_adequacy        = True,
            changes_sizing              = True,
            changes_residuals_classification = False,
            changes_lifecycle_cost      = False,
            changes_risk_materially     = True,
            rationale=(
                f"Catchment risk is '{catchment}'. Default LRV targets may understate the "
                "required pathogen reduction for this specific catchment. "
                "A site-specific QMRA would confirm whether additional barriers are required "
                "and would validate the LRV adequacy of the preferred archetype. "
                "This does not change the archetype type but may change the number of barriers required."
            ),
        ))

    # 3. Source variability event characterisation
    if variability in ("high", "extreme"):
        dims.append(AQVOIDimension(
            uncertainty                 = "Event-based source water characterisation (P99+ conditions)",
            voi_classification          = VOI_HIGH,
            changes_archetype_selection = True,
            changes_lrv_adequacy        = True,
            changes_sizing              = True,
            changes_residuals_classification = False,
            changes_lifecycle_cost      = True,
            changes_risk_materially     = True,
            rationale=(
                f"Source variability is '{variability}' with P99 turbidity {ctx['turbidity_p99']:.0f} NTU. "
                "Treatment train performance under extreme events has not been characterised. "
                "Extreme events may require a more robust archetype (e.g. DAF instead of conventional "
                "sedimentation, or membrane instead of granular media filtration). "
                "Extended event monitoring (minimum 12 months, ideally 5 years) should be completed "
                "before detailed design commitment."
            ),
        ))

    # 4. LRV barrier redundancy improvement
    if single_b and not lrv_gap:
        dims.append(AQVOIDimension(
            uncertainty                 = "LRV barrier redundancy — single-barrier dependence",
            voi_classification          = VOI_HIGH,
            changes_archetype_selection = False,
            changes_lrv_adequacy        = True,
            changes_sizing              = True,
            changes_residuals_classification = False,
            changes_lifecycle_cost      = True,
            changes_risk_materially     = True,
            rationale=(
                "Single-barrier dependence is present. An additional validated barrier would "
                "eliminate this vulnerability and potentially change the archetype recommendation "
                "to one with inherently higher redundancy. "
                "This investigation changes the treatment train configuration and should be "
                "resolved before detailed design commitment."
            ),
        ))

    # 5. NOM treatability at P95 conditions
    if toc_p95 > 8:
        dims.append(AQVOIDimension(
            uncertainty                 = "NOM treatability jar testing at P95 TOC conditions",
            voi_classification          = VOI_MODERATE,
            changes_archetype_selection = False,
            changes_lrv_adequacy        = False,
            changes_sizing              = True,
            changes_residuals_classification = False,
            changes_lifecycle_cost      = False,
            changes_risk_materially     = False,
            rationale=(
                f"P95 TOC of {toc_p95:.1f} mg/L is elevated. Jar testing at P95 conditions "
                "would confirm coagulant type, dose, and achievable TOC removal. "
                "This changes coagulation system sizing but not archetype selection. "
                "Should be initiated in parallel with concept design rather than as a prerequisite."
            ),
        ))

    # 6. Residuals disposal pathway (if complex)
    if len(classified_w) > 0 or problem_xfr:
        dims.append(AQVOIDimension(
            uncertainty                 = "Residuals classification and disposal pathway confirmation",
            voi_classification          = VOI_HIGH,
            changes_archetype_selection = False,
            changes_lrv_adequacy        = False,
            changes_sizing              = False,
            changes_residuals_classification = True,
            changes_lifecycle_cost      = True,
            changes_risk_materially     = True,
            rationale=(
                "The preferred archetype generates classified waste streams "
                f"({'; '.join(classified_w[:2]) if classified_w else 'complex residuals'}). "
                "Residuals disposal pathway must be confirmed before treatment selection is finalised — "
                "if a viable disposal route does not exist, the archetype is not viable regardless of "
                "its treatment performance. The problem-transfer test has identified at least one "
                "residual stream that concentrates the source contaminant rather than destroying it."
            ),
        ))

    # 7. Remote monitoring capability (if remote)
    if remote and requires_mem:
        dims.append(AQVOIDimension(
            uncertainty                 = "Remote monitoring and control capability for membrane system",
            voi_classification          = VOI_HIGH,
            changes_archetype_selection = True,
            changes_lrv_adequacy        = False,
            changes_sizing              = False,
            changes_residuals_classification = False,
            changes_lifecycle_cost      = True,
            changes_risk_materially     = True,
            rationale=(
                "Remote operation context with membrane treatment selected. "
                "Membrane systems require continuous monitoring and prompt response to "
                "integrity failures and fouling events. "
                "If remote monitoring and control capability cannot be confirmed, "
                "a simpler and more robust archetype (e.g. slow sand filtration + UV) "
                "may be preferred. This investigation could change archetype selection."
            ),
        ))

    # 8. DBP compliance (always moderate — required post-commissioning)
    dims.append(AQVOIDimension(
        uncertainty                 = "Disinfection by-product (DBP) formation monitoring",
        voi_classification          = VOI_LOW,
        changes_archetype_selection = False,
        changes_lrv_adequacy        = False,
        changes_sizing              = False,
        changes_residuals_classification = False,
        changes_lifecycle_cost      = False,
        changes_risk_materially     = False,
        rationale=(
            "DBP formation potential is a post-commissioning monitoring requirement, "
            "not a concept-stage decision input. DBP compliance is managed through "
            "chlorination control, not archetype change. "
            "Proceed without resolving this at concept stage — "
            "include DBP monitoring in the commissioning programme."
        ),
    ))

    high_voi = [d.uncertainty for d in dims if d.voi_classification == VOI_HIGH]
    low_voi  = [d.uncertainty for d in dims if d.voi_classification == VOI_LOW]
    n_selection_blocking = sum(
        1 for d in dims
        if d.voi_classification == VOI_HIGH and d.changes_archetype_selection
    )

    proceed = n_selection_blocking == 0

    recommendation = (
        (
            f"High VOI items that could change archetype selection: "
            f"{'; '.join(h for h in high_voi if any(d.changes_archetype_selection for d in dims if d.uncertainty == h))}. "
            "These must be resolved before treatment selection is finalised. "
            if any(d.changes_archetype_selection for d in dims if d.voi_classification == VOI_HIGH)
            else ""
        )
        + (
            f"High VOI items affecting LRV or sizing (not selection): "
            f"{'; '.join(h for h in high_voi if not any(d.changes_archetype_selection for d in dims if d.uncertainty == h))}. "
            "Resolve in parallel with detailed design. "
            if any(not d.changes_archetype_selection for d in dims if d.voi_classification == VOI_HIGH)
            else ""
        )
        + (f"Low VOI items ({', '.join(low_voi)}) — proceed without investigation. " if low_voi else "")
        + (
            "Do not finalise treatment selection until selection-blocking investigations are complete."
            if not proceed else
            "Proceed to detailed design — carry conditions into procurement documentation."
        )
    )

    return AQVOIAssessment(
        dimensions                    = dims,
        high_voi_items                = high_voi,
        low_voi_items                 = low_voi,
        proceed_without_investigation = proceed,
        investigation_recommendation  = recommendation,
    )


# ── Component 5: Risk Ownership Mapping ───────────────────────────────────────

def _build_risk_ownership(ctx: dict) -> AQRiskOwnershipMap:
    pfas        = ctx["pfas_detected"]
    arsenic     = ctx["arsenic_ug_l"]
    remote      = ctx["remote_operation"]
    requires_mem= ctx["requires_membrane"]
    classified_w= ctx["classified_waste"]
    flow        = ctx["design_flow"]
    single_b    = ctx["single_barrier"]
    catchment   = ctx["catchment_risk"]
    contaminants= ctx["contaminant_modules"]

    dims: List[AQRiskOwnershipDimension] = []

    dims.append(AQRiskOwnershipDimension(
        risk_category  = "Public health and regulatory compliance",
        primary_owner  = "Utility",
        shared_with    = ["Designer (treatment adequacy)", "Regulator (licence conditions)"],
        utility_exposure=(
            "The utility holds the drinking water licence and the duty of care for "
            "public health protection. LRV adequacy, ADWG compliance, and outbreak "
            "prevention are the utility's obligation — not the designer's or supplier's. "
            "No contract transfers this accountability."
        ),
        note=(
            "Single-barrier dependence means the utility's public health risk is "
            "dependent on one process operating correctly at all times. "
            "This must be resolved in the treatment design, not managed operationally."
            if single_b else
            "Treatment performance guarantees from designers and suppliers provide "
            "financial recourse but do not transfer the public health obligation."
        ),
    ))

    dims.append(AQRiskOwnershipDimension(
        risk_category  = "Source water quality and catchment risk",
        primary_owner  = "Utility",
        shared_with    = ["Catchment manager (land use control)", "Regulator (catchment protection)"],
        utility_exposure=(
            "Source water quality is a shared responsibility but the utility carries "
            "the treatment obligation regardless of catchment management outcomes. "
            f"{'High catchment risk means the utility must design for the worst plausible source conditions, not the average. ' if catchment in ('high','very_high') else ''}"
            "A deteriorating source does not reduce the duty to supply safe water."
        ),
        note=(
            "Catchment risk management agreements do not transfer the utility's "
            "treatment responsibility. If catchment conditions deteriorate, "
            "the utility must upgrade treatment — not reduce supply."
        ),
    ))

    dims.append(AQRiskOwnershipDimension(
        risk_category  = "Technology performance risk",
        primary_owner  = "OEM / Supplier" if requires_mem else "Designer",
        shared_with    = ["Utility (selection decision)", "Designer (specification)"],
        utility_exposure=(
            "The utility's risk is the selection decision — committing to a treatment "
            "archetype at concept stage. This risk is owned at investment approval "
            "and cannot be retrospectively transferred."
        ),
        note=(
            "Membrane supplier performance guarantees should cover integrity, "
            "flux, recovery, and LRV validation under site-specific water quality. "
            "Liquidated damages should reflect the cost of supply interruption."
            if requires_mem else
            "Technology risk is within the range manageable by standard "
            "design-and-construct contracting."
        ),
    ))

    dims.append(AQRiskOwnershipDimension(
        risk_category  = "Contaminant management and residuals",
        primary_owner  = "Utility",
        shared_with    = ["Disposal contractor (residuals handling)"] if classified_w else [],
        utility_exposure=(
            "The utility generates the residual stream and retains ultimate "
            "responsibility for its management and disposal, regardless of "
            "contractor arrangements. "
            + (
                f"Classified waste streams ({'; '.join(classified_w[:2])}) "
                "cannot be treated as a secondary consideration — "
                "they are a primary cost and liability."
                if classified_w else
                "Residuals management is an ongoing operational and cost obligation."
            )
        ),
        note=(
            "PFAS removal does not destroy PFAS — it transfers it to a concentrated "
            "residual that requires specialist disposal or incineration. "
            "The utility owns this residual for its operational life."
            if pfas else
            "Residuals disposal pathway should be confirmed and costed before "
            "treatment selection is finalised."
        ),
    ))

    dims.append(AQRiskOwnershipDimension(
        risk_category  = "Operational reliability",
        primary_owner  = "Operator",
        shared_with    = ["Utility (asset owner)", "Designer (process design)"],
        utility_exposure=(
            "Drinking water treatment reliability is an asset management responsibility. "
            f"{'At {flow:.0f} ML/d, operational failure has immediate public health consequence. ' if flow >= 20 else ''}"
            "The utility must ensure operator capability, maintenance programme, "
            "and monitoring systems are adequate for the selected treatment train."
        ),
        note=(
            "Remote operation requires automated alarms, remote SCADA access, "
            "and a defined emergency response protocol before the plant is commissioned."
            if remote else
            "Operator training programme for any new treatment processes should "
            "be a procurement condition, not an afterthought."
        ),
    ))

    dims.append(AQRiskOwnershipDimension(
        risk_category  = "Whole-of-life asset and regulatory change",
        primary_owner  = "Utility",
        shared_with    = [],
        utility_exposure=(
            "The utility owns the treatment infrastructure for its full design life. "
            "Technology obsolescence, membrane replacement cycles, guideline value "
            "changes (particularly PFAS and emerging contaminants), and catchment "
            "quality deterioration are all carried by the utility."
        ),
        note=(
            "PFAS health guideline values are actively under review in Australia. "
            "The treatment system must be designed with headroom above current values — "
            "not optimised to the current limit."
            if pfas or arsenic > 10 else
            "Regulatory change risk for this source type and contaminant profile "
            "is within the normal range for long-term infrastructure planning."
        ),
    ))

    accountability = (
        "No delivery model — D&C, DBOM, Alliance, or PPP — removes the utility's "
        "ultimate accountability for public health protection, regulatory compliance, "
        "and whole-of-life asset management. Risk allocation affects financial exposure "
        "and recourse. It does not transfer the duty of care."
    )

    residual = (
        "The utility's residual risk position — after all contractual risk transfers — "
        "includes: public health duty of care, drinking water licence obligation, "
        "LRV adequacy for all pathogen classes, contaminant guideline compliance, "
        "residuals classification and disposal, and whole-of-life asset cost. "
        "This position defines the minimum acceptable treatment performance."
    )

    return AQRiskOwnershipMap(
        dimensions                       = dims,
        utility_accountability_statement = accountability,
        residual_risk_statement          = residual,
    )


# ── Component 6: Decision Boundary ────────────────────────────────────────────

def _build_decision_boundary(ctx: dict) -> AQDecisionBoundary:
    pref_label  = ctx["pref_label"]
    lrv_prot    = ctx["lrv_required_protozoa"]
    lrv_bact    = ctx["lrv_required_bacteria"]
    lrv_viru    = ctx["lrv_required_virus"]
    single_b    = ctx["single_barrier"]
    pfas        = ctx["pfas_detected"]
    arsenic     = ctx["arsenic_ug_l"]
    remote      = ctx["remote_operation"]
    requires_mem= ctx["requires_membrane"]
    variability = ctx["variability_class"]
    turb_p99    = ctx["turbidity_p99"]
    flow        = ctx["design_flow"]
    classified_w= ctx["classified_waste"]
    problem_xfr = ctx["problem_transfer"]
    contaminants= ctx["contaminant_modules"]
    lrv_result  = ctx["lrv_result"]
    catchment   = ctx["catchment_risk"]

    # Performance range
    perf = [
        f"Protozoa LRV ≥ {lrv_prot:.0f} log — validated against worst-case source conditions, not average.",
        f"Bacteria LRV ≥ {lrv_bact:.0f} log — including primary disinfection and secondary residual.",
        f"Virus LRV ≥ {lrv_viru:.0f} log — confirmed across all treatment barriers.",
        "Effluent turbidity ≤ 0.1 NTU (95th percentile) — prerequisite for UV disinfection credit.",
        "Primary disinfection residual maintained at all times — no supply without confirmed disinfection.",
    ]
    if pfas:
        perf.append("PFAS concentration in product water ≤ applicable ADWG health guideline value.")
    if arsenic > 10:
        perf.append(f"Arsenic in product water ≤ 10 µg/L (ADWG) — verified by monthly sampling.")
    if requires_mem:
        perf.append("Membrane integrity verified — daily pressure hold test, annual LRV validation test.")

    # Acceptable uncertainty
    uncertain = [
        "±30% CAPEX estimate uncertainty is accepted at concept stage — to be refined at detailed design.",
        "DBP formation potential uncertainty is accepted — manage through chlorination control post-commissioning.",
        "NOM variability uncertainty is accepted with coagulation system sized to P95 conditions.",
        "N₂O equivalent is not applicable to drinking water — no carbon accounting uncertainty to accept.",
    ]
    if not pfas:
        uncertain.append("PFAS absence is accepted based on current monitoring — ongoing monitoring required.")

    # Resilience margin
    if single_b:
        resilience = (
            "Resilience margin is LOW — single-barrier dependence is present. "
            "Loss of one barrier creates an immediate public health risk. "
            "Additional barrier redundancy must be incorporated before detailed design."
        )
    elif requires_mem:
        resilience = (
            "Resilience margin is MODERATE — membrane system provides high LRV but "
            "is sensitive to integrity failures. Redundant membrane capacity and "
            "bypass chlorination provide limited resilience during maintenance."
        )
    else:
        resilience = (
            "Resilience margin is ADEQUATE — multiple independent barriers provide "
            "treatment redundancy above the minimum LRV requirement. "
            "Bypass provisions should be incorporated at detailed design."
        )

    # Fallback position
    if requires_mem:
        fallback = (
            "If membrane system is offline for maintenance or integrity failure, "
            "chlorination-only bypass provides temporary supply — with reduced pathogen "
            "protection. Duration must be minimised and regulator notified. "
            "OEM contract must include response time obligations for integrity failures."
        )
    else:
        fallback = (
            "If a primary treatment stage is offline, increased disinfection dose "
            "and regulator notification provides a managed response. "
            "Duration of single-stage bypass must be defined and minimised. "
            "Emergency supply arrangements should be defined before commissioning."
        )

    # Monitoring
    monitoring = [
        "Continuous turbidity monitoring at filter effluent — 1-minute logging, alarm at 0.2 NTU.",
        "Continuous disinfectant residual monitoring at plant outlet and distribution entry points.",
        "Daily sampling for ADWG compliance parameters — turbidity, E. coli, disinfectant residual.",
        "Monthly ADWG full compliance monitoring — chemical, microbiological, and physical parameters.",
        "Annual LRV validation testing — confirm barrier credits against actual performance data.",
    ]
    if requires_mem:
        monitoring.append("Daily membrane integrity pressure test — alarm if pressure decay exceeds threshold.")
    if pfas:
        monitoring.append("Quarterly PFAS monitoring in product water and residuals — confirm continued guideline compliance.")
    if arsenic > 10:
        monitoring.append("Monthly arsenic monitoring in product water — verify removal performance.")

    # Triggers
    triggers = [
        "Turbidity > 0.5 NTU at filter effluent — isolate filter, investigate, do not restore until <0.1 NTU.",
        "E. coli detected in product water — immediate boil-water notice, regulator notification, investigation.",
        "Disinfectant residual below minimum for > 30 minutes — escalate to emergency response plan.",
        f"{'Membrane pressure decay test failure — take unit offline, perform integrity repair before return to service.' if requires_mem else 'Filter run time > design maximum — backwash or investigate if backwash ineffective.'}",
    ]
    if pfas:
        triggers.append("PFAS product water result > 50% of ADWG guideline — initiate treatment review.")

    # Critical assumptions
    assumptions = [
        f"Source water quality remains within the characterised range — P99 turbidity ≤ {turb_p99 * 1.5:.0f} NTU.",
        "Catchment risk classification remains stable — no major land use change or contamination event.",
        "LRV credits assigned to barriers are achievable under site-specific water quality conditions.",
        "Disinfection Ct values are achievable at design flow and minimum temperature.",
        f"{'Membrane supplier can supply replacement membranes within the specified lead time throughout asset life.' if requires_mem else 'Chemical supplier can maintain reagent supply — no single-source dependency.'}",
        "Residuals disposal pathway remains viable and affordable over the asset life.",
    ]
    if remote:
        assumptions.append("Remote SCADA and alarm system operates reliably — confirmed by annual testing.")

    return AQDecisionBoundary(
        acceptable_performance_range = perf,
        acceptable_uncertainty       = uncertain,
        resilience_margin            = resilience,
        fallback_position            = fallback,
        monitoring_requirements      = monitoring,
        intervention_triggers        = triggers,
        critical_assumptions         = assumptions,
    )


# ── Component 7: Decision Readiness ───────────────────────────────────────────

def _build_readiness(
    ctx: dict,
    criticality: AQDecisionCriticality,
    data_conf: AQDataConfidenceAssessment,
    voi: AQVOIAssessment,
) -> AQDecisionReadiness:
    tier1       = ctx["tier1_pass"]
    lrv_gap     = ctx["lrv_gap_any"]
    single_b    = ctx["single_barrier"]
    pfas        = ctx["pfas_detected"]
    pfas_ng_l   = ctx["pfas_ng_l"]
    problem_xfr = ctx["problem_transfer"]
    classified_w= ctx["classified_waste"]

    conditions: List[str] = []

    # Tier 1 failure is always blocking
    if not tier1 or lrv_gap:
        conditions.append(
            "Tier 1 safety gate: the preferred archetype does not meet LRV targets. "
            "A treatment train with an LRV gap is not acceptable for potable supply. "
            "Select an alternative archetype or add validated barriers before proceeding."
        )

    # Selection-blocking High VOI items
    for d in voi.dimensions:
        if d.voi_classification == VOI_HIGH and d.changes_archetype_selection:
            conditions.append(
                f"Resolve before treatment selection is finalised: {d.uncertainty} — "
                "this could change which archetype is appropriate."
            )

    # Single-barrier dependence — not blocking but must be carried as condition
    if single_b and tier1 and not lrv_gap:
        conditions.append(
            "Single-barrier dependence must be resolved at detailed design stage — "
            "an additional validated barrier is required for robust public health protection. "
            "This is a condition on the concept selection, not a blocker to investment decision."
        )

    # Residuals problem transfer — carry as condition if not already blocking
    if problem_xfr and not any("residuals" in c.lower() for c in conditions):
        conditions.append(
            "Residuals disposal pathway must be confirmed and costed before "
            "treatment selection is finalised — problem-transfer risk is present."
        )

    # Blocking determination — only Tier 1 / LRV gap and selection-blocking VOI
    has_blocking = (
        (not tier1 or lrv_gap) or
        any(
            d.voi_classification == VOI_HIGH and d.changes_archetype_selection
            for d in voi.dimensions
            if d.uncertainty != "LRV barrier redundancy — single-barrier dependence"
        )
    )

    if has_blocking:
        status = DR_NOT_READY
        basis  = (
            "Outstanding items exist that must be resolved before treatment selection "
            "can be confirmed. A treatment train with an LRV gap or unresolved "
            "selection-blocking uncertainty is not suitable for potable supply commitment."
        )
        strategic = (
            "Do not proceed to detailed design or procurement. "
            "Resolve LRV gaps and selection-blocking investigations first. "
            "Re-assess readiness when results are available. "
            "Public health protection cannot be deferred."
        )
        at_risk = conditions[0] if conditions else None

    elif conditions:
        status = DR_CONDITIONS
        basis  = (
            f"The treatment selection case is sufficiently developed for investment decision. "
            f"{len(conditions)} condition(s) must be carried into detailed design and procurement."
        )
        strategic = (
            "Proceed to detailed design and business case. "
            "Carry conditions into the detailed design brief. "
            "Do not defer the investment decision — conditions are manageable within the programme."
        )
        at_risk = None

    else:
        status = DR_READY
        basis  = (
            "The engineering case is sound — LRV targets are met with adequate "
            "barrier redundancy, uncertainty is bounded, and the decision boundary "
            "is defined. Treatment selection can proceed to detailed design."
        )
        strategic = (
            "Proceed directly to detailed design and procurement. "
            "Initiate monitoring programme at commissioning. "
            "Review performance against decision boundary at 12-month intervals."
        )
        at_risk = None

    return AQDecisionReadiness(
        status                      = status,
        basis                       = basis,
        conditions                  = conditions,
        critical_assumption_at_risk = at_risk,
        strategic_implication       = strategic,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def build_aquapoint_dil(inputs, reasoning_output) -> AquaPointDILReport:
    """
    Build the Decision Intelligence Layer report for an AquaPoint assessment.

    Parameters
    ----------
    inputs           : SourceWaterInputs — inputs passed to run_reasoning_engine()
    reasoning_output : AquaPointReasoningOutput — return value of run_reasoning_engine()

    Returns
    -------
    AquaPointDILReport
        Does NOT modify any input or result.
    """
    ctx = _extract_context(inputs, reasoning_output)

    context     = _build_context(ctx)
    criticality = _build_criticality(ctx)
    data_conf   = _build_data_confidence(ctx)
    voi         = _build_voi(ctx, data_conf)
    risk_own    = _build_risk_ownership(ctx)
    boundary    = _build_decision_boundary(ctx)
    readiness   = _build_readiness(ctx, criticality, data_conf, voi)

    return AquaPointDILReport(
        decision_context         = context,
        preferred_archetype      = ctx["pref_key"],
        preferred_archetype_label= ctx["pref_label"],
        n_viable_archetypes      = ctx["n_viable"],
        criticality              = criticality,
        data_confidence          = data_conf,
        voi                      = voi,
        risk_ownership           = risk_own,
        decision_boundary        = boundary,
        readiness                = readiness,
        closing_statement=(
            "WaterPoint does not seek to eliminate uncertainty. "
            "It helps define when uncertainty is sufficiently understood, "
            "bounded, and owned to support action."
        ),
    )
