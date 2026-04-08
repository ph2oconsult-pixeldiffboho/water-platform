"""
Decision spine.
Synthesises all 5 layers into:
  - System signal (what is happening)
  - Primary constraint (what is blocking)
  - Decision (what to do)
  - Urgency (how soon)
  - Deferral consequences (0-2yr / 2-5yr / 5-10yr)
  - 3-option pathway comparison

This is the credibility and board-level output layer.
ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional
from engine.constraint_engine import classify_constraints


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class DeferralWindow:
    horizon: str = ""           # "0–2 years" | "2–5 years" | "5–10 years"
    consequence: str = ""
    cost_pressure: str = ""     # "LOW" | "MODERATE" | "HIGH" | "CRITICAL"
    reversible: bool = True


@dataclass
class PathwayOption:
    label: str = ""             # e.g. "Improve digestion", "Thermal pathway", "Status quo"
    description: str = ""
    mass_reduction_pct: float = 0.0
    energy_position: str = ""   # "SURPLUS" | "NEUTRAL" | "DEFICIT"
    logistics_burden: str = ""  # "LOW" | "MODERATE" | "HIGH"
    disposal_cost_band: str = ""
    capex_band: str = ""
    risk_level: str = ""        # "LOW" | "MODERATE" | "HIGH"
    recommended: bool = False
    trade_offs: list = field(default_factory=list)


@dataclass
class DecisionSpine:
    # --- 5-SECOND SUMMARY ---
    system_signal: str = ""         # One sentence: what is happening
    primary_constraint: str = ""    # One sentence: what is the binding constraint
    decision: str = ""              # One sentence: what to do
    urgency: str = ""               # "IMMEDIATE" | "NEAR-TERM" | "PLANNED" | "MONITOR"
    urgency_rationale: str = ""
    if_you_do_nothing: str = ""     # One sentence: consequence of inaction

    # --- DEFERRAL ENGINE ---
    deferral_0_2yr: Optional[DeferralWindow] = None
    deferral_2_5yr: Optional[DeferralWindow] = None
    deferral_5_10yr: Optional[DeferralWindow] = None

    # --- PATHWAY OPTIONS ---
    option_a: Optional[PathwayOption] = None    # Improve current
    option_b: Optional[PathwayOption] = None    # Thermal / advanced
    option_c: Optional[PathwayOption] = None    # Status quo

    # --- CREDIBILITY LAYER ---
    input_confidence: str = ""      # "HIGH" | "MEDIUM" | "LOW"
    assumptions: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    confidence_note: str = ""

    # --- PRIMARY CONSTRAINT CLASSIFICATION ---
    constraint_classification: Optional[object] = None  # ConstraintClassification

    # --- KEY FLAGS ---
    flags: list = field(default_factory=list)   # Critical items requiring attention


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def build_decision_spine(
    pathway_result,         # PathwayResult
    production_result,      # ProductionResult
    logistics_result,       # LogisticsResult
) -> DecisionSpine:
    """
    Synthesise all engine outputs into the decision spine.
    """
    mad = pathway_result.mad_outputs
    eb = pathway_result.energy_balance
    hb = pathway_result.heat_balance
    fp = pathway_result.feedstock_profile
    pfas = pathway_result.pfas_constraint
    thp = pathway_result.thp_delta
    thermal = pathway_result.thermal_result
    drying = pathway_result.drying_result
    inputs = pathway_result.inputs
    stab = inputs.stabilisation.stabilisation if inputs else "NONE"
    ctx = inputs.context if inputs else None

    flags = []

    # -----------------------------------------------------------------------
    # SYSTEM SIGNAL
    # -----------------------------------------------------------------------
    system_signal = _build_system_signal(
        fp, mad, production_result, logistics_result, pfas, flags
    )

    # -----------------------------------------------------------------------
    # PRIMARY CONSTRAINT
    # -----------------------------------------------------------------------
    primary_constraint = _identify_primary_constraint(
        mad, eb, hb, logistics_result, pfas, thermal, flags
    )

    # -----------------------------------------------------------------------
    # DECISION
    # -----------------------------------------------------------------------
    decision, urgency, urgency_rationale = _derive_decision(
        stab, mad, eb, hb, logistics_result, pfas, thermal,
        production_result, flags
    )

    # -----------------------------------------------------------------------
    # IF YOU DO NOTHING
    # -----------------------------------------------------------------------
    if_nothing = _if_you_do_nothing(
        stab, logistics_result, pfas, production_result, thermal
    )

    # -----------------------------------------------------------------------
    # DEFERRAL WINDOWS
    # -----------------------------------------------------------------------
    d0, d2, d5 = _build_deferral_windows(
        stab, logistics_result, pfas, production_result, eb, thermal
    )

    # -----------------------------------------------------------------------
    # PATHWAY OPTIONS
    # -----------------------------------------------------------------------
    opt_a, opt_b, opt_c = _build_pathway_options(
        stab, mad, thp, eb, hb, logistics_result, pfas, ctx, thermal, drying
    )

    # -----------------------------------------------------------------------
    # CREDIBILITY LAYER
    # -----------------------------------------------------------------------
    confidence, assumptions, dependencies, conf_note = _build_credibility(
        inputs, production_result, fp, pfas
    )

    # -----------------------------------------------------------------------
    # PRIMARY CONSTRAINT CLASSIFICATION
    # -----------------------------------------------------------------------
    constraint_class = classify_constraints(pathway_result, production_result, logistics_result)

    # Override primary_constraint narrative with constraint engine output
    # for consistency — the scored engine is authoritative
    primary_constraint = constraint_class.primary_narrative

    return DecisionSpine(
        system_signal=system_signal,
        primary_constraint=primary_constraint,
        decision=decision,
        urgency=urgency,
        urgency_rationale=urgency_rationale,
        if_you_do_nothing=if_nothing,
        deferral_0_2yr=d0,
        deferral_2_5yr=d2,
        deferral_5_10yr=d5,
        option_a=opt_a,
        option_b=opt_b,
        option_c=opt_c,
        input_confidence=confidence,
        assumptions=assumptions,
        dependencies=dependencies,
        confidence_note=conf_note,
        flags=flags,
        constraint_classification=constraint_class,
    )


# ---------------------------------------------------------------------------
# SIGNAL BUILDER
# ---------------------------------------------------------------------------

def _build_system_signal(fp, mad, prod, logistics, pfas, flags) -> str:
    parts = []

    ts_t_yr = prod.current_ts_t_yr if prod else 0
    future_t_yr = prod.future_ts_t_yr if prod else 0

    if ts_t_yr > 0:
        parts.append(
            f"Plant is producing {ts_t_yr:,.0f} t DS/year, "
            f"projected to reach {future_t_yr:,.0f} t DS/year "
            f"over {prod.projection_years} years "
            f"({prod.growth_pressure} growth pressure)."
        )

    if mad:
        parts.append(
            f"Current stabilisation achieves {mad.vsr_pct:.0f}% VSR "
            f"with a {mad.cake_ds_pct:.0f}% DS dewatered cake."
        )
    else:
        parts.append("No stabilisation in place — raw sludge to disposal.")
        flags.append("No stabilisation — Class B minimum not met.")

    if logistics:
        parts.append(
            f"Disposal burden: {logistics.truck_loads_per_day:.1f} loads/day "
            f"({logistics.handling_complexity} handling complexity)."
        )

    if pfas and pfas.flagged:
        flags.append(f"PFAS flagged — {pfas.route_status} on land application.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# CONSTRAINT IDENTIFIER
# ---------------------------------------------------------------------------

def _identify_primary_constraint(mad, eb, hb, logistics, pfas, thermal, flags) -> str:
    # Priority order: PFAS > thermal DS gap > heat shortfall > logistics > energy

    if pfas and pfas.route_status == "CLOSED":
        return (
            "PFAS constraint is binding — land application is closed. "
            "Thermal destruction is the only compliant disposal route."
        )

    if thermal and not thermal.ds_adequate:
        flags.append(
            f"Thermal route requires {thermal.min_ds_pct_required:.0f}% DS — "
            f"current cake is {thermal.cake_ds_in_pct:.0f}% DS. "
            f"Thermal drying required."
        )
        return (
            f"Cake DS ({thermal.cake_ds_in_pct:.0f}%) is below the minimum required for "
            f"{thermal.route} ({thermal.min_ds_pct_required:.0f}%). "
            f"Thermal drying must be added before this route is viable."
        )

    if hb and not hb.heat_self_sufficient:
        shortfall_MJ = abs(hb.heat_surplus_deficit_MJ_d)
        return (
            f"Heat shortfall of {shortfall_MJ:,.0f} MJ/d — CHP recovery is insufficient "
            f"to meet digester demand. Auxiliary boiler or feed thickening required."
        )

    if logistics and logistics.handling_complexity == "HIGH":
        return (
            f"Logistics burden is high: {logistics.truck_loads_per_day:.1f} loads/day "
            f"at {logistics.cake_ds_pct:.0f}% DS. "
            f"Increasing cake DS would directly reduce transport cost and volume."
        )

    if eb and not eb.energy_self_sufficient:
        deficit = abs(eb.net_electrical_export_kWh_d)
        return (
            f"Energy deficit of {deficit:,.0f} kWh/d — biogas production insufficient "
            f"to cover process parasitic load. Increasing VS destruction would improve position."
        )

    if mad and mad.vsr_pct < 40:
        return (
            f"VSR of {mad.vsr_pct:.0f}% is below the 40% threshold for reliable stabilisation. "
            f"Consider THP pre-treatment or HRT extension."
        )

    return (
        "No single binding constraint identified. "
        "Optimise for disposal cost and logistics efficiency."
    )


# ---------------------------------------------------------------------------
# DECISION + URGENCY
# ---------------------------------------------------------------------------

def _derive_decision(stab, mad, eb, hb, logistics, pfas, thermal,
                     prod, flags) -> tuple:

    if pfas and pfas.route_status == "CLOSED" and (not thermal or thermal.route == "NONE"):
        return (
            "Commission thermal disposal route immediately — PFAS has closed land application.",
            "IMMEDIATE",
            "Regulatory exposure is current, not future.",
        )

    if pfas and pfas.route_status == "CLOSED":
        return (
            "Proceed with thermal disposal route — PFAS has closed land application. "
            "Ensure thermal drying achieves required DS before commissioning.",
            "NEAR-TERM",
            "PFAS regulatory exposure is active. Land application carries enforcement risk.",
        )

    if stab == "NONE":
        return (
            "Implement anaerobic digestion — no stabilisation means Class B minimum is not met "
            "and disposal options are severely limited.",
            "IMMEDIATE",
            "Raw sludge disposal is unsustainable at any scale.",
        )

    if thermal and not thermal.ds_adequate:
        return (
            f"Add thermal drying before {thermal.route} — cake DS gap of "
            f"{thermal.ds_gap_pp:.0f}pp must be closed for viable thermal operation.",
            "NEAR-TERM",
            "Thermal route is selected but not yet operable at current DS.",
        )

    if hb and not hb.heat_self_sufficient and mad:
        if mad.thp_applied:
            return (
                "Investigate feed thickening to reduce heat demand — THP steam load "
                "exceeds CHP recovery. Thickening to higher TS% reduces feed heating requirement.",
                "NEAR-TERM",
                "Auxiliary boiler increases OPEX and reduces energy recovery value.",
            )
        else:
            return (
                "Evaluate THP addition — it increases biogas and CHP heat output while "
                "reducing digester volume, which may close the heat shortfall.",
                "PLANNED",
                "Heat shortfall is manageable but creates ongoing auxiliary fuel cost.",
            )

    if prod and prod.growth_pressure in ["HIGH", "CRITICAL"]:
        return (
            f"Plan capacity uplift now — {prod.growth_pressure.lower()} growth pressure "
            f"({prod.growth_rate_pct_yr:.1f}%/yr) will exceed current system capacity "
            f"within the planning horizon.",
            "NEAR-TERM",
            f"Solids load reaches {prod.future_ts_t_yr:,.0f} t DS/year in {prod.projection_years} years.",
        )

    if logistics and logistics.disposal_cost_band in ["HIGH", "VERY_HIGH"]:
        return (
            "Review disposal route — current route is in the high cost band. "
            "Improving stabilisation class or increasing cake DS would reduce cost.",
            "PLANNED",
            "Disposal cost trajectory is upward without pathway improvement.",
        )

    return (
        "Current pathway is functional — monitor growth pressure and disposal market. "
        "Review stabilisation class uplift (THP) if disposal costs increase.",
        "MONITOR",
        "No immediate action required but proactive review recommended.",
    )


# ---------------------------------------------------------------------------
# IF YOU DO NOTHING
# ---------------------------------------------------------------------------

def _if_you_do_nothing(stab, logistics, pfas, prod, thermal) -> str:
    parts = []

    if stab == "NONE":
        parts.append(
            "Without stabilisation, land application is precluded and disposal cost "
            "remains at maximum. Regulatory exposure increases with each year of inaction."
        )
    elif pfas and pfas.route_status == "CLOSED":
        parts.append(
            "PFAS exposure will force regulatory intervention. "
            "Continuing land application risks enforcement action and liability."
        )
    else:
        if logistics:
            future_loads = logistics.future_truck_loads_per_day
            parts.append(
                f"Transport burden grows from {logistics.truck_loads_per_day:.1f} to "
                f"{future_loads:.1f} loads/day as production increases."
            )
        if prod and prod.growth_pressure in ["HIGH", "CRITICAL"]:
            parts.append(
                f"Solids load reaches {prod.future_ts_t_yr:,.0f} t DS/year — "
                f"current infrastructure will be overwhelmed."
            )
        parts.append(
            "Disposal costs rise with volume. Early capital investment in stabilisation "
            "improvement consistently delivers lower lifecycle cost than deferred action."
        )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# DEFERRAL WINDOWS
# ---------------------------------------------------------------------------

def _build_deferral_windows(stab, logistics, pfas, prod, eb, thermal):
    is_thermal = thermal is not None and thermal.route != "NONE"
    has_pfas = pfas and pfas.flagged

    d0 = DeferralWindow(
        horizon="0–2 years",
        consequence=(
            "Rising disposal cost as volume grows. "
            + ("PFAS regulatory scrutiny increases. " if has_pfas else "")
            + ("Transport frequency increases week on week. " if logistics and logistics.truck_loads_per_day > 2 else "")
            + "Opportunity cost of delayed energy recovery."
        ),
        cost_pressure="MODERATE" if stab != "NONE" else "HIGH",
        reversible=True,
    )

    d2 = DeferralWindow(
        horizon="2–5 years",
        consequence=(
            "Disposal route capacity may be reached. "
            + ("PFAS legislation likely to tighten — land application window closing. " if has_pfas else "")
            + ("Digester capacity constraint if growth continues at current rate. " if prod and prod.growth_pressure == "HIGH" else "")
            + "Equipment condition deteriorates — major maintenance or replacement triggered."
        ),
        cost_pressure="HIGH",
        reversible=True,
    )

    d5 = DeferralWindow(
        horizon="5–10 years",
        consequence=(
            "Major upgrade unavoidable — but now driven by crisis, not planning. "
            + ("PFAS regulatory enforcement likely — significant liability exposure. " if has_pfas else "")
            + (f"Solids load reaches {prod.future_ts_t_yr:,.0f} t DS/year — "
               f"infrastructure overwhelmed. " if prod else "")
            + "Capital cost of reactive upgrade typically 30–50% higher than planned investment."
        ),
        cost_pressure="CRITICAL",
        reversible=False,
    )

    return d0, d2, d5


# ---------------------------------------------------------------------------
# PATHWAY OPTIONS
# ---------------------------------------------------------------------------

def _build_pathway_options(stab, mad, thp, eb, hb, logistics, pfas, ctx, thermal, drying):
    has_thp = thp and thp.applied
    has_thermal = thermal and thermal.route_viable
    energy_ok = eb and eb.energy_self_sufficient
    heat_ok = hb and hb.heat_self_sufficient
    pfas_closed = pfas and pfas.route_status == "CLOSED"

    # Option A — Improve current stabilisation
    if stab == "NONE":
        opt_a = PathwayOption(
            label="Implement MAD",
            description="Install mesophilic anaerobic digestion at 30-day HRT. "
                        "Delivers Class B stabilisation, biogas for energy, and "
                        "significant mass reduction.",
            mass_reduction_pct=45.0,
            energy_position="SURPLUS",
            logistics_burden="MODERATE",
            disposal_cost_band="LOW",
            capex_band="HIGH",
            risk_level="LOW",
            recommended=not pfas_closed,
            trade_offs=[
                "High upfront capital",
                "Proven technology — low operational risk",
                "Enables land application (if no PFAS)",
            ],
        )
    elif stab == "MAD" and not has_thp:
        vsr = mad.vsr_pct if mad else 45.0
        opt_a = PathwayOption(
            label="Add THP to existing MAD",
            description="THP pre-treatment upstream of existing digester. "
                        "Increases VSR, biogas yield, and cake DS. "
                        "Reduces digester volume requirement.",
            mass_reduction_pct=vsr + 10,
            energy_position="SURPLUS",
            logistics_burden="LOW" if logistics and logistics.cake_ds_pct > 28 else "MODERATE",
            disposal_cost_band="LOW",
            capex_band="HIGH",
            risk_level="LOW",
            recommended=not pfas_closed,
            trade_offs=[
                "Significant VSR and biogas uplift",
                "Cake DS improvement reduces transport burden",
                "HRT reduction may allow digester capacity uplift without new tanks",
            ],
        )
    else:
        vsr = mad.vsr_pct if mad else 55.0
        opt_a = PathwayOption(
            label="Optimise existing MAD+THP",
            description="Review HRT, thickening, and CHP utilisation. "
                        "Close heat shortfall through feed thickening or auxiliary boiler.",
            mass_reduction_pct=vsr,
            energy_position="SURPLUS" if energy_ok else "DEFICIT",
            logistics_burden=logistics.handling_complexity if logistics else "MODERATE",
            disposal_cost_band="LOW",
            capex_band="LOW",
            risk_level="LOW",
            recommended=False,
            trade_offs=[
                "Low capital — operational optimisation only",
                "Limited headroom for further improvement",
                "Does not address long-term disposal route risk",
            ],
        )

    # Option B — Thermal pathway
    thermal_route = ctx.thermal_route if ctx else "INCINERATION"
    if thermal_route == "NONE":
        thermal_route = "INCINERATION"

    opt_b = PathwayOption(
        label=f"Thermal pathway ({thermal_route.title()})",
        description=(
            f"Add thermal drying to achieve >75% DS, then route to {thermal_route.lower()}. "
            f"Eliminates disposal market dependency. "
            + ("Preferred route given PFAS closure. " if pfas_closed else "")
        ),
        mass_reduction_pct=85.0,
        energy_position="SURPLUS",
        logistics_burden="LOW",
        disposal_cost_band="VERY_HIGH" if thermal_route == "INCINERATION" else "HIGH",
        capex_band="VERY_HIGH",
        risk_level="MEDIUM",
        recommended=pfas_closed,
        trade_offs=[
            "Eliminates land application dependency and PFAS risk",
            "Highest capital cost — requires long-term offtake or own-asset model",
            "Net energy positive at scale with pre-drying",
            "Regulatory permitting pathway required",
        ],
    )

    # Option C — Status quo
    mass_red = mad.vsr_pct if mad else 0.0
    opt_c = PathwayOption(
        label="Status quo",
        description=(
            "Continue current operations without capital investment. "
            "Disposal volume grows with production. "
            + ("PFAS regulatory exposure unresolved. " if pfas_closed else "")
        ),
        mass_reduction_pct=mass_red,
        energy_position="SURPLUS" if energy_ok else ("NEUTRAL" if stab != "NONE" else "DEFICIT"),
        logistics_burden=logistics.handling_complexity if logistics else "HIGH",
        disposal_cost_band="HIGH",
        capex_band="NONE",
        risk_level="HIGH",
        recommended=False,
        trade_offs=[
            "No capital required in short term",
            "Disposal cost rises with volume — no mitigation",
            "Regulatory and market risk unaddressed",
            "Crisis-driven investment ultimately more expensive",
        ],
    )

    return opt_a, opt_b, opt_c


# ---------------------------------------------------------------------------
# CREDIBILITY LAYER
# ---------------------------------------------------------------------------

def _build_credibility(inputs, prod, fp, pfas):
    assumptions = []
    dependencies = []

    if prod and prod.cod_derived:
        assumptions.append(
            f"Sludge production estimated from COD load — validate against plant records."
        )
    assumptions.append(
        f"VS/TS ratio: {fp.vs_ts_ratio:.2f} (M&E midpoint for {fp.feedstock_type})."
    )
    assumptions.append(
        f"CHP efficiencies: electrical {inputs.chp.electrical_efficiency*100:.0f}%, "
        f"thermal {(inputs.chp.thermal_efficiency_jacket + inputs.chp.thermal_efficiency_exhaust)*100:.0f}%."
    )
    assumptions.append(
        "Digester U-values from M&E Table 13-15 — site-specific insulation may differ."
    )
    if inputs.stabilisation.stabilisation == "MAD_THP":
        assumptions.append(
            "THP performance (delta VSR, steam demand) from published Cambi/M&E data — "
            "confirm with vendor for site-specific design."
        )

    dependencies.append("Disposal route availability and regulatory acceptance.")
    dependencies.append("Land application: agronomic offtake availability and seasonal capacity.")
    if pfas and pfas.flagged:
        dependencies.append(
            "PFAS: regulatory framework evolving — constraints may tighten before project delivery."
        )
    dependencies.append("Biogas energy offset depends on plant electrical tariff.")

    confidence = prod.input_confidence if prod else "MEDIUM"
    note = prod.confidence_note if prod else "Input confidence not assessed."

    return confidence, assumptions, dependencies, note
