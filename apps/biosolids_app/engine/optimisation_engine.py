"""
BioPoint V1 — Optimisation Engine, Output Cards, and Board Mode.
Implements Parts 11, 12, and 13 of the specification.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional, List


# ===========================================================================
# PART 11 — OPTIMISATION ENGINE
# ===========================================================================

# Scoring dimensions and default weights per optimisation priority
_DIMENSION_WEIGHTS = {
    "lowest_cost": {
        "cost":               0.40,
        "carbon":             0.05,
        "resilience":         0.15,
        "operability":        0.20,
        "market_dependence":  0.10,
        "strategic_fit":      0.10,
    },
    "lowest_carbon": {
        "cost":               0.10,
        "carbon":             0.40,
        "resilience":         0.15,
        "operability":        0.15,
        "market_dependence":  0.10,
        "strategic_fit":      0.10,
    },
    "highest_resilience": {
        "cost":               0.15,
        "carbon":             0.10,
        "resilience":         0.35,
        "operability":        0.20,
        "market_dependence":  0.15,
        "strategic_fit":      0.05,
    },
    "lowest_disposal_dependency": {
        "cost":               0.15,
        "carbon":             0.10,
        "resilience":         0.25,
        "operability":        0.20,
        "market_dependence":  0.20,
        "strategic_fit":      0.10,
    },
    "balanced": {
        "cost":               0.20,
        "carbon":             0.20,
        "resilience":         0.20,
        "operability":        0.20,
        "market_dependence":  0.10,
        "strategic_fit":      0.10,
    },
}


def score_flowsheet(flowsheet, all_flowsheets: list,
                    optimisation_priority: str) -> dict:
    """
    Calculate weighted total score for a single flowsheet.
    Scores are relative across the candidate set.
    Returns score_breakdown dict and total score 0-100.
    """
    econ = flowsheet.economics
    eb = flowsheet.energy_balance
    carbon = flowsheet.carbon_balance
    risk = flowsheet.risk
    compat = flowsheet.compatibility
    mb = flowsheet.mass_balance
    product = flowsheet.product_pathway

    weights = _DIMENSION_WEIGHTS.get(optimisation_priority,
                                      _DIMENSION_WEIGHTS["balanced"])

    # --- COST SCORE (0-100, higher = lower cost) ---
    # Net annual value — normalise across candidates
    net_values = [
        fs.economics.net_annual_value
        for fs in all_flowsheets
        if fs.economics
    ]
    if net_values:
        min_nv = min(net_values)
        max_nv = max(net_values)
        if max_nv > min_nv:
            cost_score = (econ.net_annual_value - min_nv) / (max_nv - min_nv) * 100
        else:
            cost_score = 50.0
    else:
        cost_score = 50.0

    # --- CARBON SCORE (0-100, higher = more carbon benefit) ---
    # Sequestration + avoidance minus emissions
    net_co2e = carbon.co2e_sequestered_t_per_day + carbon.co2e_avoided_t_per_day - carbon.co2e_emitted_t_per_day
    all_net_co2e = [
        (fs.carbon_balance.co2e_sequestered_t_per_day +
         fs.carbon_balance.co2e_avoided_t_per_day -
         fs.carbon_balance.co2e_emitted_t_per_day)
        for fs in all_flowsheets if fs.carbon_balance
    ]
    if all_net_co2e:
        min_c = min(all_net_co2e)
        max_c = max(all_net_co2e)
        carbon_score = (net_co2e - min_c) / (max_c - min_c) * 100 if max_c > min_c else 50.0
    else:
        carbon_score = 50.0

    # --- RESILIENCE SCORE (0-100, higher = more resilient) ---
    # Mass reduction + low disposal dependency + disposal fallback quality
    mass_red = mb.total_mass_reduction_pct / 100.0
    disposal_dep = 1.0 - (mb.residual_wet_mass_tpd / mb.wet_sludge_in_tpd) if mb.wet_sludge_in_tpd > 0 else 0
    resilience_score = (mass_red * 50 + disposal_dep * 50)

    # --- OPERABILITY SCORE (0-100) ---
    # Inverse of risk score + compatibility
    risk_score = risk.risk_score          # 0-100 (higher = riskier)
    compat_score = compat.score_numeric   # 0-100 (higher = better)
    operability_score = (1 - risk_score / 100) * 60 + compat_score * 0.40

    # --- MARKET DEPENDENCE SCORE (0-100, higher = LESS market dependent) ---
    # Revenue confidence and dependency
    conf_map = {"high": 100, "moderate": 60, "low": 20}
    rev_conf_val = conf_map.get(econ.revenue_confidence, 20)
    # Penalty if product revenue is dominant
    if econ.total_revenue_per_year > 0:
        product_rev_frac = econ.product_sales_per_year / econ.total_revenue_per_year
        carbon_rev_frac = econ.carbon_credit_per_year / econ.total_revenue_per_year
    else:
        product_rev_frac = 0.0
        carbon_rev_frac = 0.0
    market_dep_score = rev_conf_val * (1 - product_rev_frac * 0.5 - carbon_rev_frac * 0.3)
    market_dep_score = max(0.0, min(100.0, market_dep_score))

    # --- STRATEGIC FIT SCORE (0-100) ---
    # Alignment with regulatory pressure and land constraints
    strategic = flowsheet.inputs.strategic
    reg_map = {"high": 30, "moderate": 15, "low": 0}
    reg_bonus = reg_map.get(strategic.regulatory_pressure, 0)
    # Thermal pathways score better under high regulatory pressure
    ptype = flowsheet.pathway_type
    if strategic.regulatory_pressure == "high" and ptype in ("pyrolysis", "gasification"):
        strategic_score = 80 + reg_bonus
    elif strategic.regulatory_pressure == "low" and ptype == "baseline":
        strategic_score = 70
    elif ptype == "AD" and strategic.regulatory_pressure in ("moderate", "high"):
        strategic_score = 65 + reg_bonus
    else:
        strategic_score = 50

    strategic_score = min(100.0, strategic_score)

    # --- WEIGHTED TOTAL ---
    breakdown = {
        "cost":              round(cost_score, 1),
        "carbon":            round(carbon_score, 1),
        "resilience":        round(resilience_score, 1),
        "operability":       round(operability_score, 1),
        "market_dependence": round(market_dep_score, 1),
        "strategic_fit":     round(strategic_score, 1),
    }

    total = sum(breakdown[dim] * weights[dim] for dim in breakdown)

    return {"total": round(total, 1), "breakdown": breakdown, "weights": weights}


# ===========================================================================
# PART 12 — OUTPUT CARD
# ===========================================================================

@dataclass
class FlowsheetOutputCard:
    """Structured output card for a single evaluated flowsheet — Part 12."""

    flowsheet_id: str = ""
    flowsheet_name: str = ""

    # 1. Summary
    summary_logic: str = ""

    # 2. Mass balance summary
    wet_in_tpd: float = 0.0
    ds_in_tpd: float = 0.0
    water_removed_tpd: float = 0.0
    residual_wet_tpd: float = 0.0
    mass_reduction_pct: float = 0.0

    # 3. Drying
    drying_required: bool = False
    target_ds_pct: float = 0.0
    net_external_drying_energy_kwh_d: float = 0.0

    # 4. Energy balance
    energy_status: str = ""
    net_energy_kwh_d: float = 0.0
    energy_closure_risk: bool = False

    # 5. Carbon
    co2e_sequestered_t_yr: float = 0.0
    co2e_avoided_t_yr: float = 0.0
    carbon_credit_revenue_yr: float = 0.0
    carbon_credit_confidence: str = ""

    # 6. Product
    product_type: str = ""
    product_quantity_tpd: float = 0.0
    product_market_confidence: str = ""
    product_revenue_yr: float = 0.0

    # 7. Economics
    net_annual_value: float = 0.0
    cost_per_tds: float = 0.0
    annualised_capex_yr: float = 0.0
    revenue_confidence: str = ""

    # 8. Risks
    overall_risk: str = ""
    key_risks: list = field(default_factory=list)

    # 9. Score
    total_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)

    # 10. Decision
    decision_status: str = ""
    rank: int = 0


def build_output_card(flowsheet) -> FlowsheetOutputCard:
    """Assemble the structured output card from all engine results."""
    mb = flowsheet.mass_balance
    dc = flowsheet.drying_calc
    eb = flowsheet.energy_balance
    carbon = flowsheet.carbon_balance
    product = flowsheet.product_pathway
    econ = flowsheet.economics
    risk = flowsheet.risk

    summary = (
        f"{flowsheet.name}: {flowsheet.description} "
        f"Mass reduction {mb.total_mass_reduction_pct:.0f}%. "
        f"Energy {eb.energy_status}. "
        f"Net annual value ${econ.net_annual_value:,.0f}. "
        f"Overall risk: {risk.overall_risk}."
    )

    return FlowsheetOutputCard(
        flowsheet_id=flowsheet.flowsheet_id,
        flowsheet_name=flowsheet.name,
        summary_logic=summary,
        wet_in_tpd=mb.wet_sludge_in_tpd,
        ds_in_tpd=mb.ds_in_tpd,
        water_removed_tpd=mb.water_removed_tpd,
        residual_wet_tpd=mb.residual_wet_mass_tpd,
        mass_reduction_pct=mb.total_mass_reduction_pct,
        drying_required=dc.drying_required,
        target_ds_pct=dc.target_ds_pct,
        net_external_drying_energy_kwh_d=dc.net_external_drying_energy_kwh_per_day,
        energy_status=eb.energy_status,
        net_energy_kwh_d=eb.net_energy_kwh_per_day,
        energy_closure_risk=eb.energy_closure_risk,
        co2e_sequestered_t_yr=carbon.co2e_sequestered_t_per_day * 365,
        co2e_avoided_t_yr=carbon.co2e_avoided_t_per_day * 365,
        carbon_credit_revenue_yr=carbon.carbon_credit_revenue_per_day * 365,
        carbon_credit_confidence=carbon.carbon_credit_confidence,
        product_type=product.product_type,
        product_quantity_tpd=product.product_quantity_tpd,
        product_market_confidence=product.product_market_confidence,
        product_revenue_yr=product.product_value_per_day * 365,
        net_annual_value=econ.net_annual_value,
        cost_per_tds=econ.cost_per_tds_treated,
        annualised_capex_yr=econ.annualised_capex_per_year,
        revenue_confidence=econ.revenue_confidence,
        overall_risk=risk.overall_risk,
        key_risks=risk.key_risks,
        total_score=flowsheet.score,
        score_breakdown=flowsheet.score_breakdown,
        decision_status=flowsheet.decision_status,
        rank=flowsheet.rank,
    )


# ===========================================================================
# PART 13 — BOARD MODE
# ===========================================================================

@dataclass
class BoardOutput:
    """
    Board-level condensed output — Part 13 of spec.
    Decisive but not absolute language. One page.
    """
    recommended_pathway: str = ""
    why_this_pathway: str = ""
    what_must_be_true: list = field(default_factory=list)
    main_risk_if_wrong: str = ""
    what_to_validate_next: list = field(default_factory=list)
    second_best_pathway: str = ""
    why_others_lose: list = field(default_factory=list)
    headline_statement: str = ""


def build_board_output(ranked_flowsheets: list) -> BoardOutput:
    """
    Synthesise ranked flowsheets into board-level output.
    Uses decisive but not absolute language per spec.
    """
    if not ranked_flowsheets:
        return BoardOutput(headline_statement="No flowsheets evaluated.")

    best = ranked_flowsheets[0]
    second = ranked_flowsheets[1] if len(ranked_flowsheets) > 1 else None

    mb = best.mass_balance
    eb = best.energy_balance
    econ = best.economics
    risk = best.risk
    carbon = best.carbon_balance
    product = best.product_pathway
    compat = best.compatibility

    # Headline
    headline = (
        f"Preferred pathway is {best.name.lower()} — "
        f"it delivers {mb.total_mass_reduction_pct:.0f}% mass reduction, "
        f"{'positive' if econ.net_annual_value >= 0 else 'negative'} net annual economics "
        f"(${econ.net_annual_value:,.0f}/yr), and {risk.overall_risk.lower()} overall risk — "
        f"but viability remains sensitive to "
        f"{_key_sensitivity(best)}."
    )

    # Why this pathway
    why = (
        f"{best.name} scores highest under the {best.inputs.strategic.optimisation_priority.replace('_',' ')} "
        f"optimisation objective (score {best.score:.0f}/100). "
        f"Mass reduction of {mb.total_mass_reduction_pct:.0f}% materially reduces disposal dependence. "
        + (f"Energy balance is {eb.energy_status}. " if eb.energy_status else "")
        + (f"Compatibility with feedstock is {compat.score}." if compat else "")
    )

    # What must be true
    conditions = []
    if best.pathway_type in ("pyrolysis", "gasification"):
        conditions.append(
            f"Feed must reliably reach {best.assumptions.target_ds_percent:.0f}% DS — "
            "validate dryer capacity and energy supply."
        )
        conditions.append(
            f"GCV must be ≥ {best.inputs.feedstock.gross_calorific_value_mj_per_kg_ds:.1f} MJ/kgDS "
            "at operating conditions — confirm with feed sampling."
        )
    if product.product_type not in ("none",) and product.product_market_confidence == "low":
        conditions.append(
            f"A credible {product.product_type} market or disposal route must be confirmed "
            "before financial commitment."
        )
    if carbon.carbon_credit_confidence == "low" and carbon.carbon_credit_revenue_per_day > 0:
        conditions.append(
            "Carbon credit revenue assumed but unvalidated — treat as upside, not base case."
        )
    if eb.energy_closure_risk:
        conditions.append(
            "Energy closure risk must be resolved — confirm auxiliary heat source or "
            "adjust dryer configuration."
        )
    if not conditions:
        conditions.append(
            "Feedstock characterisation (GCV, DS%, variability) must be validated against "
            "operating data before detailed design."
        )

    # Main risk
    main_risk = risk.key_risks[0] if risk.key_risks else (
        f"Process operability at {risk.process_operability_risk} risk — "
        "technology maturity and local vendor support should be confirmed."
    )

    # What to validate next
    validate = [
        f"Confirm GCV and DS% with representative sampling programme (minimum 3-month dataset).",
    ]
    if product.product_type not in ("none",):
        validate.append(
            f"Assess {product.product_type} market outlet — identify offtake partner or disposal fallback."
        )
    validate += [
        f"Commission drying energy balance with vendor data at this feed composition.",
        f"Confirm regulatory pathway for product classification in jurisdiction.",
    ]
    if best.inputs.feedstock.pfas_present != "no":
        validate.append("Characterise PFAS concentrations — results determine product eligibility.")

    # Why others lose
    others_lose = []
    for fs in ranked_flowsheets[1:4]:
        econ_other = fs.economics
        mb_other = fs.mass_balance
        risk_other = fs.risk
        reason = (
            f"{fs.name}: score {fs.score:.0f}/100 — "
        )
        if econ_other.net_annual_value < econ.net_annual_value:
            reason += f"weaker economics (${econ_other.net_annual_value:,.0f}/yr); "
        if mb_other.total_mass_reduction_pct < mb.total_mass_reduction_pct:
            reason += f"lower mass reduction ({mb_other.total_mass_reduction_pct:.0f}%); "
        if risk_other.overall_risk == "High" and risk.overall_risk != "High":
            reason += "higher overall risk."
        others_lose.append(reason.strip().rstrip(";"))

    second_name = second.name if second else "No second option evaluated."

    return BoardOutput(
        recommended_pathway=best.name,
        why_this_pathway=why,
        what_must_be_true=conditions,
        main_risk_if_wrong=main_risk,
        what_to_validate_next=validate,
        second_best_pathway=second_name,
        why_others_lose=others_lose,
        headline_statement=headline,
    )


def _key_sensitivity(flowsheet) -> str:
    """Return the most significant sensitivity for the headline statement."""
    econ = flowsheet.economics
    eb = flowsheet.energy_balance
    product = flowsheet.product_pathway
    carbon = flowsheet.carbon_balance

    if eb.energy_closure_risk:
        return "drying energy demand and auxiliary fuel cost"
    if product.product_market_confidence == "low":
        return f"{product.product_type} market confidence and real sludge calorific value"
    if carbon.carbon_credit_confidence == "low" and carbon.carbon_credit_revenue_per_day > 0:
        return "carbon credit market and sequestration permanence"
    return "feedstock characterisation and process vendor performance data"
