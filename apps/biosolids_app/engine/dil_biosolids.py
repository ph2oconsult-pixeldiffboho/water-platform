"""
apps/biosolids_app/engine/dil_biosolids.py

BioPoint — Decision Intelligence Layer
=======================================

Applies the WaterPoint DIL framework to biosolids pathway selection decisions.

The biosolids decision domain is materially different from the liquid phase:
  - Pathway selection (AD / HTC / pyrolysis / incineration / drying / hub)
    has 20–30 year whole-of-life consequence
  - PFAS status can veto entire pathway classes
  - Drying energy is a hard physical constraint, not a performance parameter
  - Product markets (biochar, compost, energy) are uncertain and illiquid
  - Disposal reliability is declining — land application is not a stable base case
  - Regulatory trajectory is one-directional: tightening

Design principles (same as WaterPoint DIL):
  - Good decisions are not made when uncertainty is removed.
    They are made when uncertainty is understood, bounded, and owned.
  - Data is not valuable in itself. Its value depends on the decision it informs.
  - Low confidence does not block decisions. It informs how they are framed.
  - The utility always carries ultimate accountability.

Main entry point
----------------
  build_biosolids_dil(inputs, results) -> BiosolidsDILReport

Where:
  inputs  : BioPointV1Inputs
  results : dict returned by run_biopoint_v1()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── Level constants (mirrored from WaterPoint DIL) ────────────────────────────
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

# ── Pathway type groupings ────────────────────────────────────────────────────
_THERMAL_ADVANCED   = {"pyrolysis", "gasification", "incineration"}
_THERMAL_ANY        = {"pyrolysis", "gasification", "incineration", "htc"}
_PRODUCT_PATHWAYS   = {"pyrolysis", "gasification", "htc"}
_DRYING_DEPENDENT   = {"pyrolysis", "gasification", "drying"}
_HUB_PATHWAYS       = {"centralised", "decentralised"}


# ── Dataclasses (mirrored structure) ─────────────────────────────────────────

@dataclass
class BPDecisionCriticality:
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
class BPDataConfidenceDimension:
    variable: str
    confidence: str
    volume: str
    issue: str
    implication: str


@dataclass
class BPDataConfidenceAssessment:
    dimensions: List[BPDataConfidenceDimension]
    overall_confidence: str
    critical_gaps: List[str]
    high_volume_low_confidence: List[str]
    summary: str


@dataclass
class BPVOIDimension:
    uncertainty: str
    voi_classification: str
    changes_pathway_selection: bool
    changes_sizing: bool
    changes_compliance_confidence: bool
    changes_product_viability: bool
    changes_lifecycle_cost: bool
    changes_risk_materially: bool
    rationale: str


@dataclass
class BPVOIAssessment:
    dimensions: List[BPVOIDimension]
    high_voi_items: List[str]
    low_voi_items: List[str]
    proceed_without_investigation: bool
    investigation_recommendation: str


@dataclass
class BPRiskOwnershipDimension:
    risk_category: str
    primary_owner: str
    shared_with: List[str]
    utility_exposure: str
    note: str


@dataclass
class BPRiskOwnershipMap:
    dimensions: List[BPRiskOwnershipDimension]
    utility_accountability_statement: str
    residual_risk_statement: str


@dataclass
class BPDecisionBoundary:
    acceptable_performance_range: List[str]
    acceptable_uncertainty: List[str]
    resilience_margin: str
    fallback_position: str
    monitoring_requirements: List[str]
    intervention_triggers: List[str]
    critical_assumptions: List[str]


@dataclass
class BPDecisionReadiness:
    status: str
    basis: str
    conditions: List[str]
    critical_assumption_at_risk: Optional[str]
    strategic_implication: str


@dataclass
class BiosolidsDILReport:
    # Context
    decision_context: str
    recommended_pathway: str
    second_pathway: str
    pathway_count: int

    # Seven components
    criticality: BPDecisionCriticality
    data_confidence: BPDataConfidenceAssessment
    voi: BPVOIAssessment
    risk_ownership: BPRiskOwnershipMap
    decision_boundary: BPDecisionBoundary
    readiness: BPDecisionReadiness

    # Closing
    closing_statement: str


# ── Helper: extract biosolids context dict from inputs + results ───────────────

def _extract_context(inputs, results: dict) -> dict:
    """
    Flatten the BioPointV1Inputs + run_biopoint_v1() results into a flat
    context dict that the DIL components can read cleanly.
    """
    feed   = inputs.feedstock
    assets = inputs.assets
    strat  = inputs.strategic

    flowsheets   = results.get("flowsheets", [])
    board        = results.get("board_output")
    its_assess   = results.get("its_assessment")
    drying_sys   = results.get("drying_dominance_system")
    sys_trans    = results.get("system_transition")

    # Top two pathways
    ranked = [fs for fs in flowsheets if hasattr(fs, "rank") and fs.rank > 0]
    ranked.sort(key=lambda fs: fs.rank)
    top    = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) >= 2 else None

    # ITS level of top pathway
    top_its_level = 1
    if its_assess and top:
        itsc = its_assess.get_by_flowsheet_id(top.flowsheet_id)
        if itsc:
            top_its_level = itsc.its_level

    # Drying viability of top pathway
    top_drying_viable = True
    top_ds_viability_label = "NOT APPLICABLE"
    top_drying_dominance = ""
    if drying_sys and top:
        for dr in getattr(drying_sys, "results", []):
            if dr.flowsheet_id == top.flowsheet_id:
                top_drying_viable = dr.can_rank_as_preferred
                top_ds_viability_label = dr.ds_viability_label
                top_drying_dominance = dr.drying_dominance_label
                break

    return {
        # Feedstock
        "dry_solids_tpd"       : feed.dry_solids_tpd,
        "dewatered_ds_pct"     : feed.dewatered_ds_percent,
        "vs_pct"               : feed.volatile_solids_percent,
        "gcv_mj_kg"            : feed.gross_calorific_value_mj_per_kg_ds,
        "pfas_status"          : feed.pfas_present,        # yes/no/unknown
        "metals_risk"          : feed.metals_risk,
        "feed_variability"     : feed.feedstock_variability,
        "sludge_type"          : feed.sludge_type,

        # Asset
        "ad_present"           : assets.anaerobic_digestion_present,
        "thp_present"          : assets.thp_present,
        "chp_present"          : assets.chp_present,
        "drying_present"       : assets.drying_system_present,
        "disposal_cost_tds"    : assets.disposal_cost_per_tds,
        "transport_dist_km"    : assets.average_transport_distance_km,
        "electricity_price"    : assets.local_power_price_per_kwh,

        # Strategic
        "regulatory_pressure"  : strat.regulatory_pressure,
        "optimisation_priority": strat.optimisation_priority,
        "biochar_confidence"   : strat.biochar_market_confidence,
        "land_constraint"      : strat.land_constraint,
        "social_licence"       : strat.social_licence_pressure,

        # Pathway results
        "top_pathway_type"     : top.pathway_type if top else "baseline",
        "top_pathway_name"     : top.name if top else "Baseline",
        "top_pathway_score"    : top.score if top else 0.0,
        "top_risk_level"       : top.risk.overall_risk if top and top.risk else "Unknown",
        "top_key_risks"        : top.risk.key_risks if top and top.risk else [],
        "top_energy_status"    : top.energy_balance.energy_status if top and top.energy_balance else "",
        "top_net_annual_value" : top.economics.net_annual_value if top and top.economics else 0.0,
        "top_cost_per_tds"     : top.economics.cost_per_tds_treated if top and top.economics else 0.0,
        "top_product_type"     : top.product_pathway.product_type if top and top.product_pathway else "none",
        "top_product_confidence": top.product_pathway.product_market_confidence if top and top.product_pathway else "low",
        "top_mass_reduction_pct": top.mass_balance.total_mass_reduction_pct if top and top.mass_balance else 0.0,

        "second_pathway_type"  : second.pathway_type if second else "",
        "second_pathway_name"  : second.name if second else "",

        # ITS / PFAS
        "top_its_level"        : top_its_level,
        "its_acceptable_pathways": getattr(its_assess, "acceptable_pathways", []),
        "its_excluded_pathways": getattr(its_assess, "pfas_excluded_pathways", []),

        # Drying
        "top_drying_viable"    : top_drying_viable,
        "top_ds_viability_label": top_ds_viability_label,
        "top_drying_dominance" : top_drying_dominance,

        # System transition
        "end_state_declaration": getattr(sys_trans, "end_state_declaration", ""),
        "role_shift_applies"   : getattr(sys_trans, "plant_role_shift_applies", False),

        # Board
        "board_headline"       : getattr(board, "headline_statement", ""),
        "board_conditions"     : getattr(board, "what_must_be_true", []),
        "board_validate_next"  : getattr(board, "what_to_validate_next", []),
    }


# ── Component 1: Decision Context ─────────────────────────────────────────────

def _build_context(ctx: dict) -> str:
    ptype = ctx["top_pathway_type"]
    pname = ctx["top_pathway_name"]
    ds    = ctx["dewatered_ds_pct"]
    tds   = ctx["dry_solids_tpd"]
    pfas  = ctx["pfas_status"]
    score = ctx["top_pathway_score"]

    pfas_note = {
        "yes":     "PFAS is confirmed present — pathway selection is constrained to ITS Level 3 or 4.",
        "no":      "PFAS has been confirmed absent — pathway selection is not constrained by PFAS.",
        "unknown": "PFAS status is unknown — regulatory trajectory must be assumed toward confirmation.",
    }.get(pfas, "PFAS status is not characterised.")

    return (
        f"A biosolids system processing {tds:.0f} tDS/day at {ds:.0f}% dewatered DS "
        f"is under evaluation for pathway selection. "
        f"The recommended pathway is {pname} (score {score:.0f}/100), "
        f"selected under the '{ctx['optimisation_priority'].replace('_', ' ')}' optimisation objective. "
        f"Mass reduction achieved: {ctx['top_mass_reduction_pct']:.0f}%. "
        f"Net annual economics: ${ctx['top_net_annual_value']:,.0f}/year. "
        f"{pfas_note} "
        f"Regulatory pressure is classified as {ctx['regulatory_pressure']}. "
        + (f"System end-state declaration: {ctx['end_state_declaration']} " if ctx['end_state_declaration'] else "")
    )


# ── Component 2: Decision Criticality ─────────────────────────────────────────

def _build_criticality(ctx: dict) -> BPDecisionCriticality:
    score      = 0
    ptype      = ctx["top_pathway_type"]
    pfas       = ctx["pfas_status"]
    reg        = ctx["regulatory_pressure"]
    ds         = ctx["dewatered_ds_pct"]
    tds        = ctx["dry_solids_tpd"]
    disposal   = ctx["disposal_cost_tds"]
    social     = ctx["social_licence"]
    land       = ctx["land_constraint"]
    ad_present = ctx["ad_present"]

    # Compliance consequence
    if pfas == "yes":
        compliance_c = (
            "High — PFAS confirmed present. Pathway selection directly determines regulatory "
            "compliance with emerging PFAS disposal and land application restrictions. "
            "ITS Level 3 or 4 is mandatory."
        )
        score += 2
    elif pfas == "unknown":
        compliance_c = (
            "Medium — PFAS status unknown. Regulatory trajectory is toward mandatory "
            "characterisation and increasingly restrictive land application conditions. "
            "Decision must be PFAS-ready regardless of current status."
        )
        score += 1
    else:
        compliance_c = (
            "Low — PFAS confirmed absent. Compliance consequence is manageable within "
            "standard biosolids regulatory framework."
        )

    # Service consequence
    if tds >= 100:
        service_c = (
            f"High — {tds:.0f} tDS/day represents a utility-scale solids stream. "
            "Pathway failure or disposal route collapse has immediate service and "
            "public health consequence. No single-pathway dependency is acceptable."
        )
        score += 2
    elif tds >= 30:
        service_c = (
            f"Medium — {tds:.0f} tDS/day. Pathway disruption has significant operational "
            "consequence but can be managed through contingency disposal routes."
        )
        score += 1
    else:
        service_c = (
            f"Low — {tds:.0f} tDS/day. Service consequence of pathway disruption "
            "is contained and manageable."
        )

    # Financial consequence
    if ptype in _THERMAL_ADVANCED:
        financial_c = (
            f"High — {ptype.title()} is a capital-intensive thermal pathway. "
            "CAPEX commitment is large, technology risk is real, and revenue assumptions "
            "(product, carbon, energy) carry market uncertainty that can materially "
            "shift the economics."
        )
        score += 2
    elif ptype in _THERMAL_ANY or ptype in _HUB_PATHWAYS:
        financial_c = (
            "Medium — pathway involves significant capital commitment and/or "
            "multi-party coordination. Cost overrun and revenue shortfall risk "
            "are manageable but material."
        )
        score += 1
    else:
        financial_c = (
            "Low — pathway is incremental and within standard utility capital "
            "programme risk tolerance."
        )

    # Reputational consequence
    if social in ("high", "moderate") or land in ("high", "moderate"):
        reputational_c = (
            "Medium — elevated social licence pressure or land constraint makes "
            "the biosolids pathway visible to the community. Odour, transport, "
            "and product application decisions will be scrutinised."
        )
        score += 1
    else:
        reputational_c = (
            "Low — community sensitivity is within manageable range for this pathway."
        )

    # Asset consequence
    if ptype in _THERMAL_ADVANCED:
        asset_c = (
            f"High — {ptype.title()} infrastructure locks in a technology and "
            "product market commitment for 20+ years. Stranded asset risk is real "
            "if regulatory conditions or product markets shift."
        )
        score += 2
    elif not ad_present and ptype == "AD":
        asset_c = (
            "High — greenfield anaerobic digestion infrastructure represents a "
            "foundational capital decision. Design must anticipate future thermal "
            "pathway integration."
        )
        score += 1
    else:
        asset_c = (
            "Medium — pathway builds on existing infrastructure. Future flexibility "
            "is retained but not unlimited."
        )
        score += 1

    # DS% constraint — hard physical signal regardless of scale
    if ds < 18:
        score += 2   # system is water-removal constrained — any pathway commitment is premature
    elif ds < 22:
        score += 1   # marginal — dewatering improvement trajectory must be confirmed

    # Reversibility
    if ptype in _THERMAL_ADVANCED:
        reversibility = (
            f"Low reversibility — {ptype.title()} plant represents committed capital "
            "with no practical exit. Once built, the utility is locked into operating "
            "this pathway for its full asset life."
        )
        score += 1
    elif ptype in _HUB_PATHWAYS:
        reversibility = (
            "Moderate reversibility — centralised hub arrangements can be renegotiated "
            "but involve contractual lock-in with other utilities or private operators."
        )
    else:
        reversibility = (
            "High reversibility — this pathway retains significant operational flexibility "
            "and can be modified or supplemented without stranding capital."
        )

    # Regulatory exposure
    if reg == "high" or pfas in ("yes", "unknown"):
        regulatory_c = (
            "High — regulatory trajectory for biosolids is one-directional: tightening. "
            "PFAS, microplastics, and land application restrictions are converging. "
            "The selected pathway must be designed for the regulatory endpoint, "
            "not the current baseline."
        )
        score += 1
    elif reg == "moderate":
        regulatory_c = (
            "Medium — moderate regulatory pressure with clear trajectory toward "
            "tighter land application and disposal controls. "
            "Pathway must be designed with regulatory headroom."
        )
    else:
        regulatory_c = (
            "Low — current regulatory framework is stable with low near-term "
            "tightening anticipated."
        )

    # Disposal cost trajectory
    if disposal >= 250:
        score += 1   # high disposal cost = declining reliability = material risk

    # Classify — BioPoint thresholds (lower than WaterPoint: whole-of-life decisions)
    if score >= 8:
        level = CRIT_HIGH
    elif score >= 4:
        level = CRIT_MEDIUM
    else:
        level = CRIT_LOW

    rationale = (
        f"Decision criticality is rated {level} based on: "
        f"{'PFAS confirmed present, ' if pfas == 'yes' else 'PFAS status unknown — regulatory exposure, ' if pfas == 'unknown' else ''}"
        f"{'utility-scale solids stream, ' if tds >= 100 else ''}"
        f"{'advanced thermal capital commitment, ' if ptype in _THERMAL_ADVANCED else ''}"
        f"{'social licence pressure, ' if social in ('high','moderate') else ''}"
        f"{'asset lock-in risk, ' if ptype in _THERMAL_ADVANCED else ''}"
        f"regulatory trajectory, and reversibility. "
        f"This decision warrants "
        f"{'full board-level authorisation and independent peer review' if level == CRIT_HIGH else 'senior management review and documented engineering justification' if level == CRIT_MEDIUM else 'standard delegated authority'}."
    )

    return BPDecisionCriticality(
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

def _build_data_confidence(ctx: dict) -> BPDataConfidenceAssessment:
    ptype    = ctx["top_pathway_type"]
    pfas     = ctx["pfas_status"]
    ds       = ctx["dewatered_ds_pct"]
    variab   = ctx["feed_variability"]
    gcv      = ctx["gcv_mj_kg"]
    product  = ctx["top_product_type"]
    prod_conf= ctx["top_product_confidence"]
    drying_dom = ctx["top_drying_dominance"]

    dims: List[BPDataConfidenceDimension] = []
    _conf_order = {CONF_HIGH: 3, CONF_ACCEPTABLE: 2, CONF_LOW: 1, CONF_VERY_LOW: 0}

    # 1. PFAS characterisation
    if pfas == "yes":
        pfas_conf, pfas_vol = CONF_HIGH, "confirmed"
        pfas_issue = "PFAS confirmed present. ITS classification is the governing constraint."
    elif pfas == "unknown":
        pfas_conf, pfas_vol = CONF_VERY_LOW, "none"
        pfas_issue = (
            "PFAS status is uncharacterised. This is not a data gap that can be deferred — "
            "it materially affects which pathways are permissible under current and future "
            "regulation. Characterisation must precede pathway commitment."
        )
    else:
        pfas_conf, pfas_vol = CONF_HIGH, "confirmed"
        pfas_issue = "PFAS confirmed absent. Pathway selection is not constrained by PFAS."
    dims.append(BPDataConfidenceDimension(
        variable   = "PFAS characterisation",
        confidence = pfas_conf,
        volume     = pfas_vol,
        issue      = pfas_issue,
        implication= "Determines which pathway classes are permissible under current and future regulation.",
    ))

    # 2. Feed dewaterability and DS%
    if ds < 18:
        dw_conf = CONF_LOW
        dw_issue = (
            f"Feed at {ds:.0f}% DS is below the minimum viable threshold for thermal pathways. "
            "Dewatering performance is the primary system constraint. "
            "Mechanical dewatering improvement is required before any thermal pathway is viable."
        )
    elif ds < 22:
        dw_conf = CONF_LOW
        dw_issue = (
            f"Feed at {ds:.0f}% DS is marginal for thermal pathways. "
            "Small improvements in dewatering performance would materially change pathway viability. "
            "Dewatering characterisation under operating conditions is required."
        )
    elif ds < 28:
        dw_conf = CONF_ACCEPTABLE
        dw_issue = (
            f"Feed at {ds:.0f}% DS is within the operational range but below energy neutrality "
            "for most thermal pathways. Dewatering improvement trajectory should be confirmed."
        )
    else:
        dw_conf = CONF_HIGH
        dw_issue = f"Feed at {ds:.0f}% DS is adequate for the recommended pathway."
    dims.append(BPDataConfidenceDimension(
        variable   = "Feed dewaterability and DS%",
        confidence = dw_conf,
        volume     = "moderate",
        issue      = dw_issue,
        implication= "Directly controls drying energy demand, thermal pathway viability, and operating cost.",
    ))

    # 3. Feedstock variability and GCV
    if variab == "high":
        gcv_conf = CONF_LOW
        gcv_issue = (
            f"High feed variability at GCV {gcv:.1f} MJ/kgDS creates thermal process stability risk. "
            "Thermal conversion processes are sensitive to GCV variation — "
            "±15% GCV swing can move a pyrolysis system from energy-positive to energy-deficit. "
            "Feed conditioning or blending strategy must be defined."
        )
    elif variab == "moderate":
        gcv_conf = CONF_ACCEPTABLE
        gcv_issue = (
            f"Moderate feed variability at GCV {gcv:.1f} MJ/kgDS. "
            "Design should include ±20% GCV tolerance in thermal sizing. "
            "Acceptable for concept-stage commitment."
        )
    else:
        gcv_conf = CONF_HIGH
        gcv_issue = f"Low feed variability at GCV {gcv:.1f} MJ/kgDS. Process sizing confidence is high."
    dims.append(BPDataConfidenceDimension(
        variable   = "Feedstock variability and GCV",
        confidence = gcv_conf,
        volume     = "moderate",
        issue      = gcv_issue,
        implication= "Affects thermal process stability, energy balance reliability, and product consistency.",
    ))

    # 4. Product market confidence
    if product in ("biochar", "syngas", "synfuel") and prod_conf == "low":
        prod_conf_rating = CONF_LOW
        prod_issue = (
            f"The recommended pathway produces {product} with low market confidence. "
            "Revenue projections are sensitive to market development that has not occurred. "
            "The decision must remain viable under a zero-revenue product scenario."
        )
    elif product in ("biochar", "syngas", "synfuel") and prod_conf == "moderate":
        prod_conf_rating = CONF_ACCEPTABLE
        prod_issue = (
            f"Moderate market confidence for {product}. "
            "Revenue projections carry material uncertainty — "
            "sensitivity testing against zero-revenue scenario is recommended."
        )
    elif product == "none":
        prod_conf_rating = CONF_HIGH
        prod_issue = "No product revenue dependency. Economics are cost-based only."
    else:
        prod_conf_rating = CONF_ACCEPTABLE
        prod_issue = f"Product market confidence is {prod_conf} for {product}."
    dims.append(BPDataConfidenceDimension(
        variable   = f"Product market confidence ({product})",
        confidence = prod_conf_rating,
        volume     = "low" if prod_conf == "low" else "moderate",
        issue      = prod_issue,
        implication= "Affects net annual economics and long-term financial viability of the pathway.",
    ))

    # 5. Drying energy — thermal pathways only
    if ptype in _DRYING_DEPENDENT:
        if drying_dom in ("Dominant", "Extreme"):
            dry_conf = CONF_LOW
            dry_issue = (
                f"Drying energy is '{drying_dom}' relative to feedstock energy. "
                "External energy supply is required and has not been confirmed. "
                "This is a hard physical constraint — not an uncertainty that resolves "
                "through further modelling."
            )
        elif drying_dom == "Significant":
            dry_conf = CONF_ACCEPTABLE
            dry_issue = (
                "Drying energy is 'Significant' relative to feedstock energy. "
                "Internal energy coverage is partial. External energy source must be "
                "identified and costed before pathway commitment."
            )
        else:
            dry_conf = CONF_HIGH
            dry_issue = "Drying energy is within feedstock energy budget. No external supply required."
        dims.append(BPDataConfidenceDimension(
            variable   = "Drying energy supply and viability",
            confidence = dry_conf,
            volume     = "moderate",
            issue      = dry_issue,
            implication= "Determines whether thermal pathway is energy-viable at current DS%.",
        ))

    # 6. Disposal route reliability
    disposal = ctx["disposal_cost_tds"]
    if disposal >= 250:
        disp_conf = CONF_LOW
        disp_issue = (
            f"Disposal cost at ${disposal:.0f}/tDS indicates a constrained or declining disposal market. "
            "Land application reliability is not confirmed. A pathway that retains disposal dependency "
            "is exposed to further cost escalation and regulatory restriction."
        )
    elif disposal >= 150:
        disp_conf = CONF_ACCEPTABLE
        disp_issue = (
            f"Disposal cost at ${disposal:.0f}/tDS is within current market range but trending upward. "
            "Pathway should reduce disposal dependence over its operating life."
        )
    else:
        disp_conf = CONF_HIGH
        disp_issue = f"Disposal cost at ${disposal:.0f}/tDS is within a stable range."
    dims.append(BPDataConfidenceDimension(
        variable   = "Disposal route reliability and cost trajectory",
        confidence = disp_conf,
        volume     = "moderate",
        issue      = disp_issue,
        implication= "Affects whole-of-life cost and pathway resilience to regulatory tightening.",
    ))

    # Summary
    worst_conf = min(dims, key=lambda d: _conf_order.get(d.confidence, 0)).confidence
    n_low = sum(1 for d in dims if _conf_order.get(d.confidence, 0) <= 1)
    critical_gaps = [d.variable for d in dims if _conf_order.get(d.confidence, 0) <= 1]
    high_vol_low = [d.variable for d in dims if d.volume == "high" and _conf_order.get(d.confidence, 0) <= 1]

    summary = (
        f"Data confidence is rated {worst_conf} overall. "
        f"{n_low} of {len(dims)} assessment dimensions have Low or Very Low confidence. "
        + (f"PFAS characterisation is unresolved — this must be addressed before pathway commitment. " if pfas == "unknown" else "")
        + (f"Drying energy is a hard physical constraint that cannot be resolved by modelling alone. " if ptype in _DRYING_DEPENDENT and drying_dom in ("Dominant", "Extreme") else "")
        + f"This confidence level is {'adequate for concept-stage commitment with conditions' if n_low <= 2 else 'insufficient for concept-stage commitment without targeted investigation'}."
    )

    return BPDataConfidenceAssessment(
        dimensions              = dims,
        overall_confidence      = worst_conf,
        critical_gaps           = critical_gaps,
        high_volume_low_confidence = high_vol_low,
        summary                 = summary,
    )


# ── Component 4: Value of Information ─────────────────────────────────────────

def _build_voi(ctx: dict, data_conf: BPDataConfidenceAssessment) -> BPVOIAssessment:
    ptype    = ctx["top_pathway_type"]
    pfas     = ctx["pfas_status"]
    ds       = ctx["dewatered_ds_pct"]
    product  = ctx["top_product_type"]
    prod_conf= ctx["top_product_confidence"]
    variab   = ctx["feed_variability"]
    drying_dom = ctx["top_drying_dominance"]

    dims: List[BPVOIDimension] = []

    # 1. PFAS characterisation
    if pfas == "unknown":
        dims.append(BPVOIDimension(
            uncertainty              = "PFAS characterisation",
            voi_classification       = VOI_HIGH,
            changes_pathway_selection= True,
            changes_sizing           = False,
            changes_compliance_confidence= True,
            changes_product_viability= True,
            changes_lifecycle_cost   = True,
            changes_risk_materially  = True,
            rationale=(
                "PFAS status is the single most consequential unresolved uncertainty in this assessment. "
                "Confirmation of PFAS presence would constrain pathway selection to ITS Level 3 or 4, "
                "potentially eliminating the recommended pathway entirely. "
                "This investigation must be completed before pathway commitment — it is not optional."
            ),
        ))

    # 2. Dewatering improvement potential
    if ds < 22:
        dims.append(BPVOIDimension(
            uncertainty              = "Dewatering improvement potential",
            voi_classification       = VOI_HIGH,
            changes_pathway_selection= True,
            changes_sizing           = True,
            changes_compliance_confidence= False,
            changes_product_viability= True,
            changes_lifecycle_cost   = True,
            changes_risk_materially  = True,
            rationale=(
                f"Feed at {ds:.0f}% DS is below the threshold for thermal pathway viability. "
                "A dewatering improvement programme (polymer optimisation, mechanical upgrade, "
                "or THP pre-treatment) could materially change which pathways are viable. "
                "This investigation should run in parallel with pathway concept design — "
                "it directly determines the scope of viable options."
            ),
        ))

    # 3. Product market development
    if product in ("biochar", "syngas") and prod_conf == "low":
        dims.append(BPVOIDimension(
            uncertainty              = f"{product.title()} market development",
            voi_classification       = VOI_HIGH,
            changes_pathway_selection= True,
            changes_sizing           = False,
            changes_compliance_confidence= False,
            changes_product_viability= True,
            changes_lifecycle_cost   = True,
            changes_risk_materially  = True,
            rationale=(
                f"The recommended pathway's economics depend on {product} market revenue "
                "that does not currently exist at the required scale. "
                "Market development investigation — including offtake negotiations and "
                "regulatory approval for product use — should be treated as a critical path item. "
                "The investment decision must remain viable if this revenue does not materialise."
            ),
        ))

    # 4. GCV and feed consistency
    if variab == "high" and ptype in _THERMAL_ADVANCED:
        dims.append(BPVOIDimension(
            uncertainty              = "Feed GCV consistency under operating conditions",
            voi_classification       = VOI_MODERATE,
            changes_pathway_selection= False,
            changes_sizing           = True,
            changes_compliance_confidence= False,
            changes_product_viability= True,
            changes_lifecycle_cost   = False,
            changes_risk_materially  = True,
            rationale=(
                "High feed variability creates thermal process stability risk. "
                "An extended feed characterisation programme — minimum 6 months of "
                "representative sampling — would reduce sizing uncertainty and confirm "
                "that feed conditioning requirements are within the design envelope. "
                "This does not change pathway selection but affects process stability confidence."
            ),
        ))

    # 5. Drying energy supply
    if ptype in _DRYING_DEPENDENT and drying_dom in ("Dominant", "Extreme"):
        dims.append(BPVOIDimension(
            uncertainty              = "External drying energy supply confirmation",
            voi_classification       = VOI_HIGH,
            changes_pathway_selection= True,
            changes_sizing           = True,
            changes_compliance_confidence= False,
            changes_product_viability= False,
            changes_lifecycle_cost   = True,
            changes_risk_materially  = True,
            rationale=(
                f"Drying energy is '{drying_dom}' relative to feedstock energy. "
                "External energy supply is required and has not been confirmed. "
                "Without a confirmed and costed energy source, this pathway cannot proceed. "
                "If external energy cannot be secured, pathway selection must revert to "
                "a non-drying-dependent option."
            ),
        ))

    # 6. Carbon credit market
    carbon_dep = ctx.get("top_net_annual_value", 0) > 0
    dims.append(BPVOIDimension(
        uncertainty              = "Carbon credit market access and price",
        voi_classification       = VOI_LOW,
        changes_pathway_selection= False,
        changes_sizing           = False,
        changes_compliance_confidence= False,
        changes_product_viability= False,
        changes_lifecycle_cost   = False,
        changes_risk_materially  = False,
        rationale=(
            "Carbon credit revenue improves pathway economics but is not the primary "
            "driver of pathway selection. Market access and price uncertainty is accepted "
            "at concept stage. Carbon accounting should be verified post-commissioning. "
            "Proceed without resolving this uncertainty."
        ),
    ))

    high_voi = [d.uncertainty for d in dims if d.voi_classification == VOI_HIGH]
    low_voi  = [d.uncertainty for d in dims if d.voi_classification == VOI_LOW]
    n_selection_blocking = sum(1 for d in dims if d.voi_classification == VOI_HIGH and d.changes_pathway_selection)

    proceed = n_selection_blocking == 0

    recommendation = (
        (f"HIGH VOI items that could change pathway selection: {'; '.join(h for h in high_voi if any(d.changes_pathway_selection for d in dims if d.uncertainty == h))}. "
         "These must be resolved before pathway commitment. " if any(d.changes_pathway_selection for d in dims if d.voi_classification == VOI_HIGH) else "")
        + (f"HIGH VOI items affecting sizing or economics (not selection): "
           f"{'; '.join(h for h in high_voi if not any(d.changes_pathway_selection for d in dims if d.uncertainty == h))}. "
           "Resolve in parallel with concept design. " if any(not d.changes_pathway_selection for d in dims if d.voi_classification == VOI_HIGH) else "")
        + (f"Low VOI items ({', '.join(low_voi)}) should not delay the decision. " if low_voi else "")
        + ("Do not proceed to pathway commitment until selection-blocking investigations are complete."
           if not proceed else
           "Proceed to concept design — carry conditions into procurement documentation.")
    )

    return BPVOIAssessment(
        dimensions                    = dims,
        high_voi_items                = high_voi,
        low_voi_items                 = low_voi,
        proceed_without_investigation = proceed,
        investigation_recommendation  = recommendation,
    )


# ── Component 5: Risk Ownership Mapping ───────────────────────────────────────

def _build_risk_ownership(ctx: dict) -> BPRiskOwnershipMap:
    ptype  = ctx["top_pathway_type"]
    pfas   = ctx["pfas_status"]
    tds    = ctx["dry_solids_tpd"]
    is_hub = ptype in _HUB_PATHWAYS

    dims: List[BPRiskOwnershipDimension] = []

    dims.append(BPRiskOwnershipDimension(
        risk_category  = "Regulatory and compliance risk",
        primary_owner  = "Utility",
        shared_with    = ["Designer (pathway adequacy)", "Operator (operational compliance)"],
        utility_exposure=(
            "The utility holds the environmental licence and the ultimate disposal obligation. "
            "PFAS regulation, land application restrictions, and product approval conditions "
            "cannot be contracted away. No delivery model transfers these obligations."
        ),
        note=(
            "PFAS characterisation is the utility's risk to resolve — not the designer's. "
            "If PFAS is later confirmed after pathway commitment, the utility bears the "
            "consequence of pathway misalignment."
            if pfas == "unknown" else
            "Compliance performance specifications in the contract provide financial recourse "
            "but do not transfer the regulatory obligation."
        ),
    ))

    dims.append(BPRiskOwnershipDimension(
        risk_category  = "Technology performance risk",
        primary_owner  = "OEM / Supplier" if ptype in _THERMAL_ADVANCED else "Designer",
        shared_with    = ["Utility (selection decision)", "Designer (specification)", "OEM (performance guarantee)"],
        utility_exposure=(
            "The utility's risk is the selection decision — committing to a pathway "
            "at concept stage before full-scale Australian precedent exists. "
            "This risk is owned at investment approval and cannot be retrospectively transferred."
        ),
        note=(
            f"{ptype.title()} technology performance guarantees should cover feedstock "
            "DS% tolerance, throughput, energy balance, and product specification. "
            "Liquidated damages provisions should reflect the cost of pathway failure."
            if ptype in _THERMAL_ADVANCED else
            "Technology risk is within the range manageable by standard D&C contracting."
        ),
    ))

    dims.append(BPRiskOwnershipDimension(
        risk_category  = "Disposal and product market risk",
        primary_owner  = "Utility",
        shared_with    = ["Operator (route management)", "Offtaker (if product pathway)"],
        utility_exposure=(
            "The utility is the last-resort disposal owner. If product markets fail, "
            "if land application is restricted, or if hub arrangements collapse, "
            "the utility must have a confirmed fallback disposal route. "
            f"At {tds:.0f} tDS/day, there is no tolerance for unplanned disposal failure."
        ),
        note=(
            "Product offtake agreements should be in place — or fallback costs modelled — "
            "before final investment decision. Disposal cost escalation risk is carried "
            "by the utility regardless of contract terms."
        ),
    ))

    dims.append(BPRiskOwnershipDimension(
        risk_category  = "Operational reliability risk",
        primary_owner  = "Operator",
        shared_with    = ["Utility (asset owner)", "Designer (process design)", "Contractor (commissioning)"],
        utility_exposure=(
            "Biosolids system failure has immediate upstream consequence — "
            "sludge accumulation affects liquid train performance and plant capacity. "
            "Operator capability for the selected pathway must be assessed and confirmed "
            "before procurement."
        ),
        note=(
            f"{'Thermal systems require specialist operator capability — pyrolysis/gasification control, ' if ptype in _THERMAL_ADVANCED else ''}"
            f"{'temperature management, and product handling are not standard utility skills. ' if ptype in _THERMAL_ADVANCED else ''}"
            "Operator training and staffing plan should be a procurement condition."
        ),
    ))

    if is_hub:
        dims.append(BPRiskOwnershipDimension(
            risk_category  = "Multi-party coordination risk",
            primary_owner  = "Hub operator",
            shared_with    = ["Utility (contributing party)", "Other contributing utilities"],
            utility_exposure=(
                "Centralised hub arrangements create dependency on other parties' "
                "sludge quality, volume, and timing. The utility cannot unilaterally "
                "control hub performance. Exit provisions and minimum service guarantees "
                "must be defined in the hub agreement."
            ),
            note=(
                "Hub arrangements reduce capital exposure but introduce counterparty risk. "
                "The utility remains the responsible party for its own sludge — "
                "hub failure does not transfer disposal liability."
            ),
        ))

    dims.append(BPRiskOwnershipDimension(
        risk_category  = "Whole-of-life asset risk",
        primary_owner  = "Utility",
        shared_with    = [],
        utility_exposure=(
            "The utility owns the asset for its full design life. "
            "Technology obsolescence, regulatory change, product market collapse, "
            "and PFAS reclassification are all carried by the utility regardless "
            "of the delivery or operating model."
        ),
        note=(
            "Asset life for thermal infrastructure is 20–25 years. "
            "Regulatory and market conditions will change materially in this period. "
            "The pathway must be designed for the regulatory endpoint, not the current baseline."
        ),
    ))

    accountability = (
        "No delivery model — D&C, DBOM, Alliance, or PPP — removes the utility's "
        "ultimate accountability for biosolids management, regulatory compliance, "
        "and whole-of-life asset performance. Risk allocation affects financial exposure "
        "and recourse. It does not transfer the underlying obligation."
    )

    residual = (
        "The utility's residual risk position — after all contractual risk transfers — "
        "includes: disposal obligation, licence conditions, PFAS regulatory exposure, "
        "product market dependency, and whole-of-life asset cost. "
        "This position defines the minimum acceptable pathway performance standard."
    )

    return BPRiskOwnershipMap(
        dimensions                    = dims,
        utility_accountability_statement = accountability,
        residual_risk_statement       = residual,
    )


# ── Component 6: Decision Boundary ────────────────────────────────────────────

def _build_decision_boundary(ctx: dict) -> BPDecisionBoundary:
    ptype    = ctx["top_pathway_type"]
    pname    = ctx["top_pathway_name"]
    ds       = ctx["dewatered_ds_pct"]
    tds      = ctx["dry_solids_tpd"]
    pfas     = ctx["pfas_status"]
    product  = ctx["top_product_type"]
    its_lvl  = ctx["top_its_level"]
    disp_cost= ctx["disposal_cost_tds"]
    board_cond = ctx["board_conditions"]

    # Performance range
    perf = [
        f"Mass reduction: ≥ {ctx['top_mass_reduction_pct']:.0f}% under design feedstock conditions.",
        f"Net annual economics: within ±25% of concept estimate at detailed design stage.",
        f"DS% feed to thermal process: ≥ {max(ds, 22):.0f}% — verified by dewatering performance monitoring.",
        f"Disposal reliability: fallback disposal route confirmed and costed at ≤ ${disp_cost * 1.3:.0f}/tDS.",
    ]
    if ptype in _THERMAL_ADVANCED:
        perf.append(f"Thermal process availability: ≥ 90% on annual basis — specified in OEM performance guarantee.")
    if pfas in ("yes", "unknown"):
        perf.append(f"ITS classification: Level ≥ 3 maintained for all active pathways — no regulatory reclassification.")

    # Acceptable uncertainty
    uncertain = [
        "±40% CAPEX estimate uncertainty is accepted at concept stage — to be refined at detailed design.",
        "Carbon credit revenue uncertainty is accepted — economics must be viable without it.",
        f"{'Product market development uncertainty is accepted — pathway must be viable under zero-revenue scenario.' if product in ('biochar','syngas') else 'No product market uncertainty — economics are cost-based.'}",
        "Transport cost escalation of up to +30% over asset life is accepted in whole-of-life modelling.",
    ]

    # Resilience margin
    resilience = (
        f"The {pname} pathway provides "
        f"{'high' if ctx['top_mass_reduction_pct'] > 80 else 'moderate'} "
        f"resilience through mass reduction, reducing exposure to disposal route disruption. "
        f"{'Fallback to baseline disposal is available but at significantly higher cost.' if ptype != 'baseline' else ''}"
    )

    # Fallback
    if ptype in _THERMAL_ADVANCED:
        fallback = (
            f"If {ptype} underperforms during commissioning, reversion to the dewatered sludge "
            f"disposal pathway ({ctx['second_pathway_name']}) provides a managed fallback. "
            "OEM contract must include performance gate provisions with liquidated damages "
            "calibrated to the cost of fallback operation."
        )
    elif ptype in _HUB_PATHWAYS:
        fallback = (
            "If the hub arrangement does not proceed or underperforms, on-site dewatering "
            "and land application disposal provides the fallback. Hub agreement must include "
            "exit provisions and minimum service guarantees."
        )
    else:
        fallback = (
            f"Reversion to baseline disposal (land application or contracted disposal) "
            f"at ${disp_cost:.0f}/tDS provides the fallback if the selected pathway "
            "does not meet performance gates."
        )

    # Monitoring
    monitoring = [
        "Weekly feedstock DS% measurement — minimum 3 samples per week.",
        "Monthly GCV verification — representative composite sampling.",
        "Quarterly product quality analysis (if applicable) against specification.",
        "Annual whole-of-life cost review against concept estimate.",
        "Regulatory monitoring programme — aligned with licence conditions and PFAS trajectory.",
    ]
    if ptype in _THERMAL_ADVANCED:
        monitoring.append("Continuous process temperature and residence time logging — thermal performance gate.")

    # Triggers
    triggers = [
        f"DS% below {max(ds - 3, 15):.0f}% for > 30 consecutive days — initiate dewatering investigation.",
        "Disposal route unavailable or cost exceeds 130% of base assumption — escalate to asset management.",
        "Product market unavailable for > 90 days — initiate alternative disposal pathway.",
    ]
    if pfas in ("yes", "unknown"):
        triggers.append("PFAS regulatory reclassification — immediate pathway review and ITS reassessment.")
    if ptype in _THERMAL_ADVANCED:
        triggers.append("Thermal process availability < 85% on rolling 90-day basis — invoke OEM performance clause.")

    # Critical assumptions
    assumptions = [
        f"Dewatering performance maintains feed at ≥ {max(ds, 20):.0f}% DS under all operating conditions.",
        "Disposal fallback route is available and costed before final investment decision.",
        f"{'PFAS characterisation completed before pathway commitment — no assumption of absence.' if pfas == 'unknown' else 'PFAS status remains as characterised throughout asset life.'}",
        "Regulatory framework does not impose ITS Level 4 as the minimum standard before commissioning.",
        f"Catchment sludge production remains within ±20% of {tds:.0f} tDS/day for 10 years.",
    ]
    if board_cond:
        assumptions.extend(board_cond[:2])  # Include top board conditions as critical assumptions

    return BPDecisionBoundary(
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
    criticality: BPDecisionCriticality,
    data_conf: BPDataConfidenceAssessment,
    voi: BPVOIAssessment,
) -> BPDecisionReadiness:
    pfas    = ctx["pfas_status"]
    ds      = ctx["dewatered_ds_pct"]
    drying_dom = ctx["top_drying_dominance"]
    ptype   = ctx["top_pathway_type"]

    conditions: List[str] = []

    # Selection-blocking High VOI items (includes PFAS if unknown)
    for d in voi.dimensions:
        if d.voi_classification == VOI_HIGH and d.changes_pathway_selection:
            conditions.append(
                f"Resolve before pathway commitment: {d.uncertainty} — "
                "this could change which pathways are permissible."
            )

    # Drying energy unresolved for drying-dependent pathway
    if ptype in _DRYING_DEPENDENT and drying_dom in ("Dominant", "Extreme"):
        conditions.append(
            "External drying energy source must be confirmed and costed before "
            "concept design commitment. The pathway is not viable without it."
        )

    # Sizing-only High VOI (not blocking, carry forward)
    sizing_voi = [
        d for d in voi.dimensions
        if d.voi_classification == VOI_HIGH and not d.changes_pathway_selection
    ]
    for d in sizing_voi:
        conditions.append(
            f"Initiate in parallel with concept design: {d.uncertainty} — "
            "affects sizing and economics, not pathway selection."
        )

    # DS% marginal — carry as condition
    if ds < 22 and pfas != "unknown":  # not double-counted with PFAS
        conditions.append(
            f"Feed dewatering improvement programme should be initiated immediately — "
            f"current {ds:.0f}% DS is marginal for the recommended pathway."
        )

    has_blocking = any(
        d.voi_classification == VOI_HIGH and d.changes_pathway_selection
        for d in voi.dimensions
    ) or (ptype in _DRYING_DEPENDENT and drying_dom in ("Dominant", "Extreme"))

    if has_blocking:
        status = DR_NOT_READY
        basis  = (
            "Outstanding items exist that must be resolved before pathway commitment. "
            "These are not conditions — they are prerequisites. "
            "Committing to a pathway before these are resolved creates a stranded asset risk."
        )
        strategic = (
            "Do not proceed to pathway commitment. "
            "Initiate targeted investigation programme immediately. "
            "Re-assess decision readiness when results are available. "
            "This is not a delay — it is risk management at utility scale."
        )
        at_risk = conditions[0] if conditions else None

    elif conditions:
        status = DR_CONDITIONS
        basis  = (
            f"The pathway case is sufficiently developed for concept design. "
            f"{len(conditions)} condition(s) must be carried forward into "
            "detailed design and procurement."
        )
        strategic = (
            "Proceed to concept design and business case. "
            "Carry conditions into detailed design documentation. "
            "Do not allow conditions to stall the programme — "
            "manage them in parallel with design development."
        )
        at_risk = None

    else:
        status = DR_READY
        basis  = (
            "The engineering case is sound, uncertainty is bounded and owned, "
            "and the decision boundary is defined. "
            "Pathway commitment can proceed."
        )
        strategic = (
            "Proceed to detailed design and procurement. "
            "Initiate monitoring programme at commissioning. "
            "Review performance against the decision boundary at 12-month intervals."
        )
        at_risk = None

    return BPDecisionReadiness(
        status                      = status,
        basis                       = basis,
        conditions                  = conditions,
        critical_assumption_at_risk = at_risk,
        strategic_implication       = strategic,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def build_biosolids_dil(
    inputs,
    results: dict,
) -> BiosolidsDILReport:
    """
    Build the Decision Intelligence Layer report for a BioPoint assessment.

    Parameters
    ----------
    inputs  : BioPointV1Inputs — fully resolved inputs passed to run_biopoint_v1()
    results : dict — return value of run_biopoint_v1()

    Returns
    -------
    BiosolidsDILReport
        Does NOT modify any input or result.
    """
    ctx = _extract_context(inputs, results)

    context     = _build_context(ctx)
    criticality = _build_criticality(ctx)
    data_conf   = _build_data_confidence(ctx)
    voi         = _build_voi(ctx, data_conf)
    risk_own    = _build_risk_ownership(ctx)
    boundary    = _build_decision_boundary(ctx)
    readiness   = _build_readiness(ctx, criticality, data_conf, voi)

    return BiosolidsDILReport(
        decision_context   = context,
        recommended_pathway= ctx["top_pathway_name"],
        second_pathway     = ctx["second_pathway_name"],
        pathway_count      = len(results.get("flowsheets", [])),
        criticality        = criticality,
        data_confidence    = data_conf,
        voi                = voi,
        risk_ownership     = risk_own,
        decision_boundary  = boundary,
        readiness          = readiness,
        closing_statement  = (
            "WaterPoint does not seek to eliminate uncertainty. "
            "It helps define when uncertainty is sufficiently understood, "
            "bounded, and owned to support action."
        ),
    )
