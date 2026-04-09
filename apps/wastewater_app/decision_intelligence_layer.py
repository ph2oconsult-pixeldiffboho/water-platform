"""
apps/wastewater_app/decision_intelligence_layer.py

Decision Intelligence Layer — WaterPoint V1
============================================

Operates above the process optimisation engine. Its purpose is not to select
a technology — that is the role of the stack generator and credibility layer.

Its purpose is to determine:
  - Whether available evidence is sufficient to act
  - Where uncertainty materially affects the decision
  - Whether further investigation has value
  - Who ultimately carries the residual risk
  - What decision boundary should be adopted

Design principles
-----------------
- Good decisions are not made when uncertainty is removed.
  They are made when uncertainty is understood, bounded, and owned.
- Data is not valuable in itself. Its value depends on the decision it informs.
- More modelling is not always the answer.
- Low confidence does not block decisions. It informs how they are framed.
- The utility always carries ultimate accountability. No delivery model changes this.

Main entry point
----------------
  build_decision_intelligence(pathway, feasibility, credible, uncertainty, plant_context)
      -> DecisionIntelligenceReport

Output sections
---------------
  1. Decision Context
  2. Decision Criticality
  3. Data Confidence Assessment
  4. Value of Information
  5. Risk Ownership Mapping
  6. Decision Boundary
  7. Decision Readiness
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from apps.wastewater_app.stack_generator import (
    UpgradePathway,
    TI_COMAG, TI_BIOMAG, TI_MABR, TI_IFAS, TI_HYBAS, TI_MBBR,
    TI_INDENSE, TI_MIGINDENSE, TI_MEMDENSE,
    TI_BARDENPHO, TI_RECYCLE_OPT, TI_DENFILTER, TI_TERT_P,
    TI_EQ_BASIN, TI_STORM_STORE,
    CT_HYDRAULIC, CT_NITRIFICATION, CT_TN_POLISH, CT_TP_POLISH,
    CT_SETTLING, CT_WET_WEATHER,
)
from apps.wastewater_app.feasibility_layer import FeasibilityReport
from apps.wastewater_app.credibility_layer import CredibleOutput
from apps.wastewater_app.uncertainty_layer import UncertaintyReport

# ── Criticality levels ────────────────────────────────────────────────────────
CRIT_LOW    = "Low"
CRIT_MEDIUM = "Medium"
CRIT_HIGH   = "High"

# ── Data confidence levels ────────────────────────────────────────────────────
CONF_HIGH       = "High"
CONF_ACCEPTABLE = "Acceptable"
CONF_LOW        = "Low"
CONF_VERY_LOW   = "Very Low"

# ── VOI classifications ───────────────────────────────────────────────────────
VOI_HIGH     = "High"
VOI_MODERATE = "Moderate"
VOI_LOW      = "Low"

# ── Decision readiness ────────────────────────────────────────────────────────
DR_READY      = "Ready to Proceed"
DR_CONDITIONS = "Proceed with Conditions"
DR_NOT_READY  = "Not Decision-Ready"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class DecisionCriticality:
    """Classification of decision criticality across six consequence dimensions."""
    level: str                          # CRIT_* constant
    compliance_consequence: str
    service_consequence: str
    financial_consequence: str
    reputational_consequence: str
    asset_consequence: str
    reversibility: str
    regulatory_exposure: str
    classification_rationale: str


@dataclass
class DataConfidenceDimension:
    """Confidence assessment for one data variable."""
    variable: str
    confidence: str                     # CONF_* constant
    volume: str                         # "high" / "moderate" / "low" / "none"
    issue: str                          # what is limiting confidence
    implication: str                    # what decision does this affect


@dataclass
class DataConfidenceAssessment:
    """Full data confidence assessment."""
    dimensions: List[DataConfidenceDimension]
    overall_confidence: str             # CONF_* constant
    critical_gaps: List[str]            # variables with low or very low confidence
    high_volume_low_confidence: List[str]   # variables with paradox — data rich but uncertain
    summary: str


@dataclass
class VOIDimension:
    """Value of Information assessment for one uncertainty."""
    uncertainty: str
    voi_classification: str             # VOI_* constant
    changes_process_selection: bool
    changes_sizing: bool
    changes_compliance_confidence: bool
    changes_staging: bool
    changes_lifecycle_cost: bool
    changes_risk_materially: bool
    rationale: str


@dataclass
class VOIAssessment:
    """Full Value of Information assessment."""
    dimensions: List[VOIDimension]
    high_voi_items: List[str]
    low_voi_items: List[str]
    proceed_without_investigation: bool
    investigation_recommendation: str


@dataclass
class RiskOwnershipDimension:
    """Risk ownership mapping for one risk category."""
    risk_category: str
    primary_owner: str
    shared_with: List[str]
    utility_exposure: str               # what the utility retains regardless
    note: str


@dataclass
class RiskOwnershipMap:
    """Full risk ownership mapping."""
    dimensions: List[RiskOwnershipDimension]
    utility_accountability_statement: str
    residual_risk_statement: str


@dataclass
class DecisionBoundary:
    """Conditions under which the recommended option remains acceptable."""
    acceptable_performance_range: List[str]
    acceptable_uncertainty: List[str]
    resilience_margin: str
    fallback_position: str
    monitoring_requirements: List[str]
    intervention_triggers: List[str]
    critical_assumptions: List[str]


@dataclass
class DecisionReadiness:
    """Final decision readiness conclusion."""
    status: str                         # DR_* constant
    basis: str                          # one-sentence basis for status
    conditions: List[str]               # conditions that must be met if not DR_READY
    critical_assumption_at_risk: Optional[str]
    strategic_implication: str


@dataclass
class DecisionIntelligenceReport:
    """Full Decision Intelligence Layer output."""
    # Context
    decision_context: str
    n_stages: int
    system_state: str
    tech_set: List[str]

    # Seven components
    criticality: DecisionCriticality
    data_confidence: DataConfidenceAssessment
    voi: VOIAssessment
    risk_ownership: RiskOwnershipMap
    decision_boundary: DecisionBoundary
    readiness: DecisionReadiness

    # Closing position
    closing_statement: str


# ── Component 1: Decision Context ────────────────────────────────────────────

def _build_decision_context(
    pathway: UpgradePathway,
    credible: CredibleOutput,
    ctx: Dict,
) -> str:
    tech_names = [s.technology for s in pathway.stages]
    plant_size = ctx.get("plant_size_mld", 10.0) or 10.0
    location   = ctx.get("location_type", "metro")
    greenfield = ctx.get("greenfield", False)
    site_type  = "greenfield" if greenfield else "brownfield"

    tech_summary = ", ".join(tech_names) if tech_names else "process optimisation only"

    context = (
        f"A {plant_size:.0f} ML/d {location} {site_type} wastewater treatment plant "
        f"is under evaluation for process upgrade. "
        f"The recommended technology stack comprises {len(tech_names)} stage(s): "
        f"{tech_summary}. "
        f"The system is currently assessed as '{pathway.system_state}' "
        f"at {pathway.proximity_pct:.0f}% proximity to its performance limit. "
    )

    if credible.ready_for_client:
        context += (
            "The engineering analysis has passed the credibility threshold and is "
            "considered ready for client-level decision-making."
        )
    else:
        context += (
            "The engineering analysis has not yet cleared the credibility threshold. "
            "Outstanding validation items must be resolved before client commitment."
        )

    return context


# ── Component 2: Decision Criticality ────────────────────────────────────────

def _build_criticality(
    pathway: UpgradePathway,
    ctx: Dict,
) -> DecisionCriticality:
    tech_set    = {s.technology for s in pathway.stages}
    ct_set      = {c.constraint_type for c in pathway.constraints}
    greenfield  = ctx.get("greenfield", False)
    size_mld    = ctx.get("plant_size_mld", 10.0) or 10.0
    location    = ctx.get("location_type", "metro")
    tn_target   = ctx.get("tn_target_mg_l", 10.0) or 10.0

    # Score criticality dimensions
    score = 0

    # Read additional context signals
    aeration_constrained = ctx.get("aeration_constrained", False)
    wet_weather_peak     = ctx.get("wet_weather_peak", False)
    overflow_risk        = ctx.get("overflow_risk", False)
    tn_at_limit          = ctx.get("tn_at_limit", False)
    flow_ratio           = ctx.get("flow_ratio", 1.0) or 1.0

    # Compliance consequence
    has_tn_polish = CT_TN_POLISH in ct_set or CT_NITRIFICATION in ct_set
    tight_tn      = tn_target < 5.0    # high tier
    moderate_tn   = tn_target < 8.0   # medium tier
    if tight_tn and has_tn_polish:
        compliance_c = "High — TN < 5 mg/L target with no compliance margin under current conditions."
        score += 2
    elif (moderate_tn and has_tn_polish) or tn_at_limit:
        compliance_c = (
            f"Medium — TN target {tn_target:.0f} mg/L with current performance at or near limit; "
            "exceedance risk if upgrade deferred."
        )
        score += 1
    else:
        compliance_c = "Low — no immediate compliance threat identified under current load conditions."

    # Service consequence
    if size_mld >= 50 and location == "metro":
        service_c = "High — metropolitan plant serving a large population; service failure has significant public health exposure."
        score += 2
    elif size_mld >= 20 or location == "regional":
        service_c = "Medium — regional or mid-scale utility; service disruption has material community impact."
        score += 1
    else:
        service_c = "Low — smaller plant; service consequence is contained and manageable."

    # Wet weather / overflow risk
    if overflow_risk or flow_ratio >= 2.5:
        score += 1
    elif wet_weather_peak or flow_ratio >= 1.8:
        score += 0   # noted but not scored — captured in VOI

    # Aeration constraint
    if aeration_constrained:
        score += 1

    # Financial consequence
    n_specialist = sum(1 for s in pathway.stages
                       if s.technology in {TI_MABR, TI_COMAG, TI_BIOMAG, TI_DENFILTER})
    if len(pathway.stages) >= 4 or n_specialist >= 2:
        financial_c = (
            f"High — {len(pathway.stages)}-stage stack with {n_specialist} specialist "
            "technologies implies a substantial capital programme with supply chain and "
            "commissioning cost risk."
        )
        score += 2
    elif len(pathway.stages) >= 2 or n_specialist >= 1:
        financial_c = "Medium — multi-stage or specialist technology programme; cost overrun risk is present but manageable with staged delivery."
        score += 1
    else:
        financial_c = "Low — single-stage upgrade with proven technology; financial consequence of underperformance is contained."

    # Reputational consequence
    has_mabr = TI_MABR in tech_set
    if has_mabr and location == "metro":
        reputational_c = (
            "Medium — MABR adoption at metropolitan scale will be visible to the sector. "
            "Underperformance would be noted; strong performance would reinforce utility credibility."
        )
        score += 1
    elif tight_tn:
        reputational_c = "Medium — tight effluent targets make the utility visible to regulators; persistent non-compliance is a reputational risk."
        score += 1
    else:
        reputational_c = "Low — technology selection is conventional and not exposed to significant reputational risk."

    # Long-term asset consequence
    if greenfield:
        asset_c = "High — greenfield design locks in process configuration for 30+ years; selection error has whole-of-life consequence."
        score += 2
    elif len(pathway.stages) >= 3:
        asset_c = "Medium — multi-stage brownfield upgrade creates interdependencies that limit future flexibility."
        score += 1
    else:
        asset_c = "Low — brownfield upgrade is staged and retains flexibility for future reconfiguration."

    # Reversibility
    if TI_MABR in tech_set or TI_COMAG in tech_set or TI_BIOMAG in tech_set:
        reversibility = (
            "Low reversibility — specialist membrane and magnetite systems involve significant "
            "capital sunk cost. Removal or replacement requires substantial re-engineering."
        )
        score += 1
    elif TI_IFAS in tech_set or TI_HYBAS in tech_set:
        reversibility = "Moderate reversibility — biofilm carrier systems can be removed or replaced with manageable cost."
    else:
        reversibility = "High reversibility — process reconfiguration or optimisation is achievable within existing infrastructure."

    # Regulatory exposure
    if tight_tn:
        reg_exposure = (
            "High — tight TN targets signal a regulatory trajectory toward further tightening. "
            "Future licence amendments should be assumed and designed for."
        )
        score += 1
    elif CT_TP_POLISH in ct_set:
        reg_exposure = "Medium — phosphorus polishing constraints may tighten as receiving water quality monitoring improves."
    else:
        reg_exposure = "Low — current licence conditions are stable with no near-term tightening anticipated."

    # Classify
    if score >= 7:
        level = CRIT_HIGH
    elif score >= 4:
        level = CRIT_MEDIUM
    else:
        level = CRIT_LOW

    rationale = (
        f"Decision criticality is rated {level} based on: "
        f"{'tight TN compliance exposure, ' if tight_tn else 'moderate TN compliance exposure, ' if moderate_tn and tn_at_limit else ''}"
        f"{'metropolitan scale service consequence, ' if size_mld >= 50 else ''}"
        f"{'aeration system at limit, ' if aeration_constrained else ''}"
        f"{'wet weather overflow risk, ' if overflow_risk else ''}"
        f"{'specialist technology dependency, ' if n_specialist >= 1 else ''}"
        f"{'greenfield lock-in risk, ' if greenfield else ''}"
        f"regulatory trajectory, and reversibility assessment. "
        f"This decision warrants {'full board-level authorisation and independent peer review' if level == CRIT_HIGH else 'senior management review and documented engineering justification' if level == CRIT_MEDIUM else 'standard delegated authority'}."
    )

    return DecisionCriticality(
        level                      = level,
        compliance_consequence     = compliance_c,
        service_consequence        = service_c,
        financial_consequence      = financial_c,
        reputational_consequence   = reputational_c,
        asset_consequence          = asset_c,
        reversibility              = reversibility,
        regulatory_exposure        = reg_exposure,
        classification_rationale   = rationale,
    )


# ── Component 3: Data Confidence Assessment ───────────────────────────────────

def _build_data_confidence(
    pathway: UpgradePathway,
    uncertainty: UncertaintyReport,
    ctx: Dict,
) -> DataConfidenceAssessment:
    tech_set   = {s.technology for s in pathway.stages}
    flow_ratio = ctx.get("flow_ratio", 1.0) or 1.0
    dims: List[DataConfidenceDimension] = []

    # 1. Influent quality and variability
    has_pilot = ctx.get("has_pilot_data", False)
    inf_conf = CONF_ACCEPTABLE if not (flow_ratio > 2.0) else CONF_LOW
    dims.append(DataConfidenceDimension(
        variable   = "Influent quality and variability",
        confidence = inf_conf,
        volume     = "moderate",
        issue      = (
            "Peak event characterisation is typically under-represented in composite sampling programmes. "
            "Average conditions are well described; 99th percentile loads are not."
            if flow_ratio > 1.5 else
            "Influent characterisation is adequate for concept-stage decision-making."
        ),
        implication = "Affects sizing of wet weather management and peak load compliance confidence.",
    ))

    # 2. Flow variability
    if flow_ratio >= 2.5:
        flow_conf = CONF_LOW
        flow_issue = (
            f"Peak flow ratio of {flow_ratio:.1f}× ADWF indicates high I/I ingress. "
            "The frequency, duration, and future trajectory of peak events is uncertain. "
            "I/I reduction programme outcomes are not yet known."
        )
    elif flow_ratio >= 1.5:
        flow_conf = CONF_ACCEPTABLE
        flow_issue = "Moderate peak flow variability; I/I characterisation is adequate for concept but not detailed design."
    else:
        flow_conf = CONF_HIGH
        flow_issue = "Flow variability is low; hydraulic characterisation is reliable."
    dims.append(DataConfidenceDimension(
        variable    = "Flow variability and peak event frequency",
        confidence  = flow_conf,
        volume      = "high" if flow_ratio > 1.5 else "moderate",
        issue       = flow_issue,
        implication = "Affects CoMag sizing, EQ basin volume, and I/I reduction urgency.",
    ))

    # 3. Process performance data
    if TI_MABR in tech_set:
        pp_conf = CONF_LOW
        pp_issue = (
            "MABR performance data is available from international references but "
            "Australian full-scale operational data is limited. "
            "Pilot data from this catchment does not exist. "
            "Biofilm establishment time (4–8 weeks) and membrane integrity under "
            "Australian temperature and load conditions is not confirmed at this site."
        )
        pp_volume = "low"
    elif TI_DENFILTER in tech_set:
        pp_conf = CONF_LOW
        pp_issue = (
            "Denitrification filter performance is highly sensitive to secondary effluent "
            "DO and carbon supply. Site-specific DO carryover has not been characterised. "
            "Methanol dose requirement has not been validated at this plant."
        )
        pp_volume = "low"
    elif TI_COMAG in tech_set or TI_BIOMAG in tech_set:
        pp_conf = CONF_ACCEPTABLE
        pp_issue = (
            "CoMag and BioMag have established Australian reference sites. "
            "Magnetite recovery efficiency under this plant's settled water chemistry "
            "has not been confirmed. Reference data is transferable with moderate confidence."
        )
        pp_volume = "moderate"
    else:
        pp_conf = CONF_HIGH
        pp_issue = "Technology performance data is well-established with direct Australian precedent."
        pp_volume = "high"

    dims.append(DataConfidenceDimension(
        variable    = "Process performance data",
        confidence  = pp_conf,
        volume      = pp_volume,
        issue       = pp_issue,
        implication = (
            "Affects reliability of compliance confidence assessment and commissioning programme duration."
        ),
    ))

    # 4. Pilot data and scale-up confidence
    if has_pilot:
        pilot_conf = CONF_ACCEPTABLE
        pilot_issue = "Pilot data exists. Scale-up assumptions require confirmation of mass transfer and hydraulic behaviour at full scale."
    else:
        pilot_conf = CONF_LOW if TI_MABR in tech_set or TI_DENFILTER in tech_set else CONF_ACCEPTABLE
        pilot_issue = (
            "No site-specific pilot data. Scale-up relies on reference site performance and "
            "OEM design guarantees. For specialist technologies (MABR, DNF), this represents "
            "a material gap between concept confidence and detailed design requirements."
            if pilot_conf == CONF_LOW else
            "No pilot data, but technology is sufficiently established that reference site "
            "performance provides acceptable scale-up confidence for concept-stage decisions."
        )

    dims.append(DataConfidenceDimension(
        variable    = "Pilot data and scale-up confidence",
        confidence  = pilot_conf,
        volume      = "low" if not has_pilot else "moderate",
        issue       = pilot_issue,
        implication = "Affects procurement risk allocation and OEM performance guarantee requirements.",
    ))

    # 5. N2O emission factor (always low)
    dims.append(DataConfidenceDimension(
        variable    = "N₂O emission factor (on-site)",
        confidence  = CONF_VERY_LOW,
        volume      = "none",
        issue       = (
            "No on-site N₂O monitoring data. IPCC Tier 1 EF applies (range: 0.5–3.2% of TN removed). "
            "This is not a data gap that can be resolved at concept stage — "
            "continuous on-site monitoring is required before carbon credits can be claimed."
        ),
        implication = "Affects carbon reduction estimate by up to ±6× range. Carbon credit verification is not possible without monitoring.",
    ))

    # 6. Seasonal and temperature effects
    temp_data = ctx.get("has_temperature_data", False)
    temp_conf = CONF_ACCEPTABLE if temp_data else CONF_LOW
    dims.append(DataConfidenceDimension(
        variable    = "Seasonal and temperature effects",
        confidence  = temp_conf,
        volume      = "moderate" if temp_data else "low",
        issue       = (
            "Seasonal temperature data available and used in process sizing."
            if temp_data else
            "Seasonal temperature effects on nitrification kinetics have not been "
            "characterised at this site. Design temperature assumed from regional climate data."
        ),
        implication = "Affects nitrification capacity at winter minimum temperatures — critical for TN compliance.",
    ))

    # Identify critical gaps and paradoxes
    _conf_order = {CONF_HIGH: 3, CONF_ACCEPTABLE: 2, CONF_LOW: 1, CONF_VERY_LOW: 0}
    critical_gaps = [
        d.variable for d in dims
        if _conf_order.get(d.confidence, 0) <= 1
    ]
    high_vol_low_conf = [
        d.variable for d in dims
        if d.volume == "high" and _conf_order.get(d.confidence, 0) <= 1
    ]

    worst = min(dims, key=lambda d: _conf_order.get(d.confidence, 0))
    overall = worst.confidence

    n_low = sum(1 for d in dims if _conf_order.get(d.confidence, 0) <= 1)
    summary = (
        f"Data confidence is rated {overall} overall. "
        f"{n_low} of {len(dims)} assessment dimensions have Low or Very Low confidence. "
        f"{'The N₂O emission factor cannot be resolved at concept stage. ' if CONF_VERY_LOW in [d.confidence for d in dims] else ''}"
        f"{'MABR scale-up and process performance confidence is the primary actionable gap. ' if TI_MABR in tech_set and not has_pilot else ''}"
        f"This level of confidence is {'adequate for concept-stage decision-making with appropriate conditions' if n_low <= 2 else 'marginal for concept-stage commitment without additional targeted investigation'}."
    )

    return DataConfidenceAssessment(
        dimensions              = dims,
        overall_confidence      = overall,
        critical_gaps           = critical_gaps,
        high_volume_low_confidence = high_vol_low_conf,
        summary                 = summary,
    )


# ── Component 4: Value of Information ────────────────────────────────────────

def _build_voi(
    pathway: UpgradePathway,
    data_confidence: DataConfidenceAssessment,
    ctx: Dict,
) -> VOIAssessment:
    tech_set = {s.technology for s in pathway.stages}
    dims: List[VOIDimension] = []

    # N2O monitoring
    dims.append(VOIDimension(
        uncertainty             = "N₂O emission factor",
        voi_classification      = VOI_LOW,
        changes_process_selection   = False,
        changes_sizing              = False,
        changes_compliance_confidence = False,
        changes_staging             = False,
        changes_lifecycle_cost      = False,
        changes_risk_materially     = False,
        rationale = (
            "On-site N₂O monitoring would improve carbon accounting accuracy but would not "
            "change process selection, sizing, or compliance outcome. "
            "It is required for carbon credit verification but not for the investment decision. "
            "Proceed without it — initiate monitoring after commissioning."
        ),
    ))

    # Aeration/blower audit
    if TI_MABR in tech_set:
        dims.append(VOIDimension(
            uncertainty             = "Aeration capacity headroom (blower audit)",
            voi_classification      = VOI_HIGH,
            changes_process_selection   = True,   # MABR vs IFAS
            changes_sizing              = True,    # MABR module count
            changes_compliance_confidence = False,
            changes_staging             = False,
            changes_lifecycle_cost      = True,   # IFAS is materially cheaper
            changes_risk_materially     = True,
            rationale = (
                "A site-specific blower capacity audit would determine whether IFAS is viable "
                "as a lower-cost alternative to MABR. If spare blower capacity > 15% is confirmed, "
                "IFAS replaces MABR — materially changing CAPEX and technology risk profile. "
                "This investigation should be completed before detailed design commitment."
            ),
        ))

    # Peak flow characterisation
    flow_ratio = ctx.get("flow_ratio", 1.0) or 1.0
    if flow_ratio >= 2.0:
        dims.append(VOIDimension(
            uncertainty             = "Peak wet weather flow characterisation",
            voi_classification      = VOI_HIGH,
            changes_process_selection   = False,
            changes_sizing              = True,    # CoMag capacity, EQ volume
            changes_compliance_confidence = True,
            changes_staging             = True,    # I/I reduction sequencing
            changes_lifecycle_cost      = True,
            changes_risk_materially     = True,
            rationale = (
                "Understanding peak flow frequency, duration, and future trajectory would "
                "directly affect CoMag sizing, EQ basin need, and I/I reduction programme urgency. "
                "A wet weather event analysis (minimum 5-year rainfall data) is recommended "
                "before final sizing is committed."
            ),
        ))

    # Pilot testing
    has_pilot = ctx.get("has_pilot_data", False)
    if not has_pilot and TI_MABR in tech_set:
        dims.append(VOIDimension(
            uncertainty             = "MABR pilot performance at this site",
            voi_classification      = VOI_MODERATE,
            changes_process_selection   = False,
            changes_sizing              = True,
            changes_compliance_confidence = True,
            changes_staging             = False,
            changes_lifecycle_cost      = False,
            changes_risk_materially     = True,
            rationale = (
                "A pilot trial would reduce scale-up uncertainty and confirm biofilm establishment "
                "rate under local conditions. However, MABR has sufficient international reference "
                "data for concept-stage commitment if procurement risk is appropriately allocated "
                "to the OEM. A pilot is recommended but not mandatory before investment decision."
            ),
        ))

    # Additional influent sampling
    dims.append(VOIDimension(
        uncertainty             = "Extended influent characterisation (99th percentile loads)",
        voi_classification      = VOI_MODERATE,
        changes_process_selection   = False,
        changes_sizing              = True,
        changes_compliance_confidence = True,
        changes_staging             = False,
        changes_lifecycle_cost      = False,
        changes_risk_materially     = False,
        rationale = (
            "Extended sampling covering seasonal variation and storm events would improve "
            "confidence in peak load assumptions. This changes sizing but not selection. "
            "Should be initiated in parallel with procurement rather than as a prerequisite."
        ),
    ))

    high_voi  = [d.uncertainty for d in dims if d.voi_classification == VOI_HIGH]
    low_voi   = [d.uncertainty for d in dims if d.voi_classification == VOI_LOW]
    n_high    = len(high_voi)

    proceed   = n_high == 0 or (n_high == 1 and not any(
        d.changes_process_selection for d in dims if d.voi_classification == VOI_HIGH
    ))

    investigation = (
        f"{'High VOI items exist that could change the decision: ' + '; '.join(high_voi) + '. ' if high_voi else ''}"
        f"{'These should be resolved before detailed design commitment. ' if high_voi else ''}"
        f"{'Low VOI items (' + ', '.join(low_voi) + ') should not delay the decision.' if low_voi else ''}"
        f"{'Proceed to business case — initiate blower audit and flow analysis in parallel.' if proceed else 'Resolve high VOI items before committing to procurement.'}"
    )

    return VOIAssessment(
        dimensions                  = dims,
        high_voi_items              = high_voi,
        low_voi_items               = low_voi,
        proceed_without_investigation = proceed,
        investigation_recommendation  = investigation,
    )


# ── Component 5: Risk Ownership Mapping ──────────────────────────────────────

def _build_risk_ownership(
    pathway: UpgradePathway,
    ctx: Dict,
) -> RiskOwnershipMap:
    tech_set  = {s.technology for s in pathway.stages}
    has_mabr  = TI_MABR in tech_set
    has_comag = TI_COMAG in tech_set or TI_BIOMAG in tech_set

    dims: List[RiskOwnershipDimension] = []

    dims.append(RiskOwnershipDimension(
        risk_category  = "Compliance risk",
        primary_owner  = "Utility",
        shared_with    = ["Designer (design adequacy)", "Operator (operational compliance)"],
        utility_exposure = (
            "The utility holds the licence. Non-compliance consequences — regulatory action, "
            "public health exposure, reputational damage — cannot be contracted away. "
            "No delivery model changes this."
        ),
        note = (
            "Compliance performance guarantees from designers and OEMs provide financial "
            "recourse but do not transfer the licence obligation or its public consequences."
        ),
    ))

    dims.append(RiskOwnershipDimension(
        risk_category  = "Technology adoption risk",
        primary_owner  = "OEM / Supplier" if has_mabr else "Designer",
        shared_with    = (
            ["Utility (selection decision)", "Designer (specification)", "OEM (performance guarantee)"]
            if has_mabr else
            ["Utility (selection decision)", "Designer (specification)"]
        ),
        utility_exposure = (
            "The utility's risk is the selection decision itself — choosing to adopt a technology "
            "with less full-scale Australian precedent. This risk is owned at the time of "
            "investment approval and cannot be retrospectively transferred."
        ),
        note = (
            "MABR OEM performance guarantees should cover biofilm establishment rate, "
            "oxygen transfer efficiency, and membrane integrity. Liquidated damages provisions "
            "should reflect the cost of delayed compliance." if has_mabr else
            "Technology risk is well within the range manageable by standard D&C contracting."
        ),
    ))

    dims.append(RiskOwnershipDimension(
        risk_category  = "Operational reliability risk",
        primary_owner  = "Operator",
        shared_with    = ["Utility (asset owner)", "Designer (process design)", "Contractor (commissioning)"],
        utility_exposure = (
            "Operational reliability is ultimately an asset management responsibility. "
            "The utility must ensure the operator has the skill base, resource, and monitoring "
            "capability to manage the technology stack selected."
        ),
        note = (
            "MABR requires specialist monitoring protocols during biofilm establishment. "
            "Magnetite systems require trained staff for recovery circuit maintenance. "
            "Operator capability assessment should be a condition of procurement." if has_mabr or has_comag else
            "Technology operational requirements are within standard utility operator capability."
        ),
    ))

    dims.append(RiskOwnershipDimension(
        risk_category  = "Delivery and programme risk",
        primary_owner  = "Contractor",
        shared_with    = ["Utility (programme owner)", "Designer (integration responsibility)"],
        utility_exposure = (
            "Programme delay has a direct compliance exposure consequence — if the upgrade is "
            "not commissioned before compliance headroom is exhausted, the utility holds the risk. "
            "Delivery model must include appropriate programme incentives and gate reviews."
        ),
        note = (
            f"A {len(pathway.stages)}-stage upgrade programme has sequential commissioning "
            "dependencies. Each stage gate must be performance-verified before the next stage "
            "is committed — both contractually and operationally."
        ),
    ))

    dims.append(RiskOwnershipDimension(
        risk_category  = "Whole-of-life asset risk",
        primary_owner  = "Utility",
        shared_with    = [],
        utility_exposure = (
            "The utility owns the asset for its full design life. Whole-of-life cost, "
            "technology obsolescence, membrane replacement, and regulatory change "
            "are carried by the utility regardless of the delivery or operating model."
        ),
        note = (
            "MABR membrane replacement cost (typically 10–15 year cycle) must be included "
            "in the asset management plan. Magnetite top-up costs should be included in OPEX "
            "modelling." if has_mabr or has_comag else
            "Asset management requirements for this technology stack are within standard "
            "utility asset management practice."
        ),
    ))

    dims.append(RiskOwnershipDimension(
        risk_category  = "Customer and service risk",
        primary_owner  = "Utility",
        shared_with    = [],
        utility_exposure = (
            "Service failure — including construction disruption, commissioning delays, "
            "or post-commissioning process failures — is experienced by customers and "
            "borne by the utility as the service provider. "
            "No commercial arrangement removes this accountability."
        ),
        note = "Customer impact minimisation should be a specific commissioning constraint — not an afterthought.",
    ))

    accountability = (
        "No delivery model — D&C, DBOM, Alliance, or PPP — removes the utility's "
        "ultimate accountability for compliance, service, and whole-of-life asset performance. "
        "Risk allocation across parties affects financial exposure and recourse. "
        "It does not transfer the underlying obligation."
    )

    residual = (
        "The utility's residual risk position — after all contractual risk transfers — "
        "includes: compliance obligation, licence conditions, public health exposure, "
        "reputational consequence of failure, and whole-of-life asset cost. "
        "This residual position defines the minimum acceptable performance standard "
        "that must be achieved regardless of delivery model."
    )

    return RiskOwnershipMap(
        dimensions                    = dims,
        utility_accountability_statement = accountability,
        residual_risk_statement       = residual,
    )


# ── Component 6: Decision Boundary ───────────────────────────────────────────

def _build_decision_boundary(
    pathway: UpgradePathway,
    credible: CredibleOutput,
    ctx: Dict,
) -> DecisionBoundary:
    tech_set   = {s.technology for s in pathway.stages}
    tn_target  = ctx.get("tn_target_mg_l", 10.0) or 10.0
    flow_ratio = ctx.get("flow_ratio", 1.0) or 1.0
    has_mabr   = TI_MABR in tech_set

    perf_range = [
        f"TN ≤ {tn_target:.0f} mg/L at the 95th percentile under current licence conditions.",
        "NH₄ ≤ 1 mg/L after MABR commissioning (performance gate before DNF commitment)."
        if has_mabr else
        "NH₄ ≤ 2 mg/L after Stage 1 intensification — verified over minimum 3-month monitoring period.",
        f"Peak flow management adequate for {flow_ratio:.1f}× ADWF events at current frequency.",
        "TSS ≤ 30 mg/L at 95th percentile through all operating conditions.",
    ]

    acceptable_uncertainty = [
        "N₂O emission factor uncertainty is accepted — on-site monitoring post-commissioning.",
        "MABR biofilm establishment time uncertainty (4–8 weeks) is accepted — allow for in programme."
        if has_mabr else
        "Technology performance uncertainty is within the acceptable range for concept-stage commitment.",
        "±25% LCC cost estimate uncertainty is accepted at concept stage — to be refined at detailed design.",
        "Influent peak characterisation uncertainty is accepted — CoMag sizing includes a conservative margin.",
    ]

    monitoring = [
        "Continuous NH₄ and TN monitoring at effluent — minimum 15-minute interval.",
        "N₂O monitoring initiated at commissioning — continuous sensor on aeration tank off-gas."
        if has_mabr else
        "N₂O monitoring to be scoped at detailed design stage.",
        "Peak flow event logging — automated trigger at 1.5× ADWF.",
        "Magnetite recovery circuit daily performance log."
        if TI_COMAG in tech_set or TI_BIOMAG in tech_set else
        "Weekly process performance review against KPIs defined in O&M manual.",
        "MABR membrane integrity test — quarterly protocol to be specified in OEM contract."
        if has_mabr else
        "Annual process performance review against design assumptions.",
    ]

    triggers = [
        f"TN > {tn_target * 1.2:.0f} mg/L on rolling 30-day average — initiate process review.",
        "NH₄ > 3 mg/L on rolling 7-day average — initiate aeration system investigation."
        if has_mabr else
        "NH₄ > 3 mg/L sustained > 48 hours — initiate process review.",
        "Peak flow event > design capacity — log, assess, escalate to asset management team.",
        "Magnetite recovery < 90% — initiate circuit investigation and OEM notification."
        if TI_COMAG in tech_set or TI_BIOMAG in tech_set else
        "Process KPI exceedance > 2 consecutive months — initiate formal review.",
    ]

    assumptions = [
        f"Aeration system is at or near maximum capacity — to be confirmed by blower audit."
        if has_mabr else
        "Existing aeration capacity is adequate for Stage 1 implementation.",
        "Brownfield site footprint is sufficient for selected technology stack — confirmed in feasibility.",
        "Operator capability is sufficient to manage specialist technology — to be assessed at procurement.",
        "Catchment growth projections remain within the design envelope for 10 years.",
        "Regulatory licence conditions do not tighten beyond TN target before commissioning.",
    ]

    fallback = (
        "If MABR underperforms during biofilm establishment, IFAS is the fallback technology — "
        "OEM contract must include provision for IFAS conversion with liquidated damages. "
        "If CoMag magnetite recovery is below specification, the bypass configuration "
        "provides continued compliance at reduced wet weather performance."
        if has_mabr else
        "Biological process optimisation through zone reconfiguration and RAS control "
        "provides a fallback position if Stage 1 does not achieve TN targets. "
        "This does not require additional capital and is available within 6 months of commissioning."
    )

    resilience = (
        f"The recommended stack provides a {'moderate' if len(pathway.stages) >= 3 else 'reasonable'} "
        "resilience margin above the minimum compliance threshold. "
        "Redundancy has been incorporated through staged deployment and bypass provisions. "
        "Single-point failures have been identified and mitigated in the technology stack assessment."
    )

    return DecisionBoundary(
        acceptable_performance_range = perf_range,
        acceptable_uncertainty       = acceptable_uncertainty,
        resilience_margin            = resilience,
        fallback_position            = fallback,
        monitoring_requirements      = monitoring,
        intervention_triggers        = triggers,
        critical_assumptions         = assumptions,
    )


# ── Component 7: Decision Readiness ──────────────────────────────────────────

def _build_readiness(
    criticality: DecisionCriticality,
    data_confidence: DataConfidenceAssessment,
    voi: VOIAssessment,
    credible: CredibleOutput,
    ctx: Dict,
) -> DecisionReadiness:
    tech_set = set(ctx.get("tech_set", []))

    conditions: List[str] = []

    # Credibility check
    if not credible.ready_for_client:
        outstanding = [
            n for n in credible.credibility_notes
            if n.severity in ("Warning", "Correction")
        ]
        conditions.append(
            f"Resolve {len(outstanding)} outstanding credibility validation item(s) "
            "before client commitment."
        )

    # High VOI items that change process selection
    selection_blocking = [
        d for d in voi.dimensions
        if d.voi_classification == VOI_HIGH and d.changes_process_selection
    ]
    if selection_blocking:
        for d in selection_blocking:
            conditions.append(
                f"Complete investigation: {d.uncertainty} — this could change process selection."
            )

    # High VOI items that change sizing but not selection
    sizing_conditions = [
        d for d in voi.dimensions
        if d.voi_classification == VOI_HIGH and not d.changes_process_selection and d.changes_sizing
    ]
    for d in sizing_conditions:
        conditions.append(
            f"Initiate in parallel with procurement: {d.uncertainty} — affects sizing, not selection."
        )

    # Critical data gaps
    if data_confidence.overall_confidence == CONF_VERY_LOW:
        conditions.append(
            "Very Low data confidence on one or more variables — targeted investigation required "
            "before detailed design commitment."
        )

    # Determine readiness
    has_blocking = bool(selection_blocking) or not credible.ready_for_client
    n_conditions  = len(conditions)

    if has_blocking:
        status = DR_NOT_READY
        basis  = (
            "Outstanding items exist that could materially change the decision. "
            "These must be resolved before investment commitment."
        )
        strategic = (
            "Do not proceed to procurement. Initiate targeted investigation programme. "
            "Re-assess decision readiness when investigation results are available. "
            "This is not a delay — it is risk management."
        )
        at_risk = selection_blocking[0].uncertainty if selection_blocking else None

    elif n_conditions > 0:
        status = DR_CONDITIONS
        basis  = (
            f"The engineering case is sufficiently developed for investment decision. "
            f"{n_conditions} condition(s) should be carried forward into procurement and detailed design."
        )
        strategic = (
            "Proceed to business case and investment approval. "
            "Carry conditions into procurement documentation. "
            "Do not defer the decision — conditions are manageable within the programme."
        )
        at_risk = None

    else:
        status = DR_READY
        basis  = (
            "The engineering case is sound, uncertainty is bounded and owned, "
            "and the decision boundary is defined. "
            "Investment decision can proceed."
        )
        strategic = (
            "Proceed directly to procurement. "
            "Initiate monitoring programme at commissioning. "
            "Review performance against the decision boundary at 6-month intervals post-commissioning."
        )
        at_risk = None

    return DecisionReadiness(
        status                     = status,
        basis                      = basis,
        conditions                 = conditions,
        critical_assumption_at_risk = at_risk,
        strategic_implication      = strategic,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def build_decision_intelligence(
    pathway: UpgradePathway,
    feasibility: FeasibilityReport,
    credible: CredibleOutput,
    uncertainty: UncertaintyReport,
    plant_context: Optional[Dict] = None,
) -> DecisionIntelligenceReport:
    """
    Build the Decision Intelligence Layer report.

    Parameters
    ----------
    pathway     : UpgradePathway — output of build_upgrade_pathway()
    feasibility : FeasibilityReport — output of assess_feasibility()
    credible    : CredibleOutput — output of build_credible_output()
    uncertainty : UncertaintyReport — output of build_uncertainty_report()
    plant_context : dict — same context dict used across all layers

    Returns
    -------
    DecisionIntelligenceReport
        Does NOT modify any input layer.
    """
    ctx      = plant_context or {}
    tech_set = {s.technology for s in pathway.stages}
    ctx_with_tech = {**ctx, "tech_set": list(tech_set)}

    context         = _build_decision_context(pathway, credible, ctx)
    criticality     = _build_criticality(pathway, ctx)
    data_confidence = _build_data_confidence(pathway, uncertainty, ctx)
    voi             = _build_voi(pathway, data_confidence, ctx)
    risk_ownership  = _build_risk_ownership(pathway, ctx)
    boundary        = _build_decision_boundary(pathway, credible, ctx)
    readiness       = _build_readiness(criticality, data_confidence, voi, credible, ctx_with_tech)

    return DecisionIntelligenceReport(
        decision_context  = context,
        n_stages          = len(pathway.stages),
        system_state      = pathway.system_state,
        tech_set          = list(tech_set),
        criticality       = criticality,
        data_confidence   = data_confidence,
        voi               = voi,
        risk_ownership    = risk_ownership,
        decision_boundary = boundary,
        readiness         = readiness,
        closing_statement = (
            "WaterPoint does not seek to eliminate uncertainty. "
            "It helps define when uncertainty is sufficiently understood, "
            "bounded, and owned to support action."
        ),
    )
