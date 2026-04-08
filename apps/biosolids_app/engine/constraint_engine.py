"""
Primary Constraint Engine.
Classifies the biosolids system into one of four constraint types:
  1. MASS       — production volume is the binding driver
  2. DISPOSAL   — route availability / regulatory risk is binding
  3. LOGISTICS  — transport cost and handling complexity is binding
  4. COST       — OPEX trajectory is the binding driver

Scores each driver independently, ranks Primary / Secondary / Tertiary,
and enforces decision alignment rules:
  - Thermal only recommended if DISPOSAL or MASS is top driver
  - Centralisation only recommended if LOGISTICS is top-2 driver

References: WaterPoint design pattern; BioPoint session brief.
ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class ConstraintScore:
    """Raw score and evidence for a single constraint type."""
    constraint_type: str = ""       # "MASS" | "DISPOSAL" | "LOGISTICS" | "COST"
    score: float = 0.0              # 0–100 composite score
    evidence: list = field(default_factory=list)   # Human-readable drivers
    severity: str = ""              # "LOW" | "MODERATE" | "HIGH" | "CRITICAL"


@dataclass
class ConstraintClassification:
    """Full ranked constraint output — primary / secondary / tertiary."""

    # --- RANKED DRIVERS ---
    primary: ConstraintScore = field(default_factory=ConstraintScore)
    secondary: ConstraintScore = field(default_factory=ConstraintScore)
    tertiary: ConstraintScore = field(default_factory=ConstraintScore)

    # --- SYSTEM TYPE LABEL ---
    system_type: str = ""           # e.g. "Mass-driven system"
    system_type_description: str = ""

    # --- DECISION ALIGNMENT ---
    aligned_recommendations: list = field(default_factory=list)
    excluded_recommendations: list = field(default_factory=list)

    # --- PANEL OUTPUT ---
    primary_label: str = ""         # Short label for UI
    secondary_label: str = ""
    tertiary_label: str = ""
    primary_narrative: str = ""     # One-sentence explanation
    secondary_narrative: str = ""


# ---------------------------------------------------------------------------
# SCORING WEIGHTS
# ---------------------------------------------------------------------------

# Maximum possible score per driver sub-component
# Scores are additive — each sub-component contributes independently.

MASS_MAX    = 100.0
DISPOSAL_MAX = 100.0
LOGISTICS_MAX = 100.0
COST_MAX    = 100.0


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def classify_constraints(
    pathway_result,       # PathwayResult
    production_result,    # ProductionResult
    logistics_result,     # LogisticsResult
) -> ConstraintClassification:
    """
    Score all four constraint types and return ranked classification.
    """
    mass_score    = _score_mass(pathway_result, production_result)
    disposal_score = _score_disposal(pathway_result, logistics_result)
    logistics_score = _score_logistics(logistics_result, production_result)
    cost_score    = _score_cost(pathway_result, logistics_result, production_result)

    # Rank all four
    all_scores = [mass_score, disposal_score, logistics_score, cost_score]
    ranked = sorted(all_scores, key=lambda s: s.score, reverse=True)

    primary   = ranked[0]
    secondary = ranked[1]
    tertiary  = ranked[2]

    # System type label
    system_type, system_desc = _system_type_label(primary, secondary)

    # Decision alignment rules
    aligned, excluded = _alignment_rules(primary, secondary)

    # Short labels for UI
    primary_label   = _constraint_label(primary.constraint_type)
    secondary_label = _constraint_label(secondary.constraint_type)
    tertiary_label  = _constraint_label(tertiary.constraint_type)

    primary_narrative   = _primary_narrative(primary, pathway_result, production_result, logistics_result)
    secondary_narrative = _secondary_narrative(secondary, pathway_result, logistics_result)

    return ConstraintClassification(
        primary=primary,
        secondary=secondary,
        tertiary=tertiary,
        system_type=system_type,
        system_type_description=system_desc,
        aligned_recommendations=aligned,
        excluded_recommendations=excluded,
        primary_label=primary_label,
        secondary_label=secondary_label,
        tertiary_label=tertiary_label,
        primary_narrative=primary_narrative,
        secondary_narrative=secondary_narrative,
    )


# ---------------------------------------------------------------------------
# MASS CONSTRAINT SCORER
# Driven by: growth pressure, low VSR, high raw solids volume, no stabilisation
# ---------------------------------------------------------------------------

def _score_mass(pathway_result, prod) -> ConstraintScore:
    score = 0.0
    evidence = []
    mad = pathway_result.mad_outputs
    fp  = pathway_result.feedstock_profile
    stab = pathway_result.inputs.stabilisation.stabilisation if pathway_result.inputs else "NONE"

    # Sub-component 1: Growth pressure (0–35)
    pressure_scores = {"LOW": 5, "MODERATE": 15, "HIGH": 28, "CRITICAL": 35}
    if prod:
        ps = pressure_scores.get(prod.growth_pressure, 0)
        score += ps
        if ps >= 15:
            evidence.append(
                f"Solids growing at {prod.growth_rate_pct_yr:.1f}%/yr "
                f"({prod.growth_pressure} pressure) — "
                f"reaching {prod.future_ts_t_yr:,.0f} t DS/yr in {prod.projection_years} years."
            )

    # Sub-component 2: No stabilisation or low VSR (0–35)
    if stab == "NONE":
        score += 35
        evidence.append("No stabilisation — full raw sludge mass to disposal.")
    elif mad:
        if mad.vsr_pct < 35:
            score += 30
            evidence.append(f"VSR of {mad.vsr_pct:.0f}% is critically low — minimal mass reduction.")
        elif mad.vsr_pct < 45:
            score += 20
            evidence.append(f"VSR of {mad.vsr_pct:.0f}% is below the 45% benchmark.")
        elif mad.vsr_pct < 55:
            score += 10
            evidence.append(f"VSR of {mad.vsr_pct:.0f}% — moderate mass reduction.")
        else:
            score += 3

    # Sub-component 3: Absolute volume (0–30)
    if prod:
        t_yr = prod.current_ts_t_yr
        if t_yr > 5000:
            score += 30
            evidence.append(f"Very high solids production: {t_yr:,.0f} t DS/yr.")
        elif t_yr > 1000:
            score += 18
            evidence.append(f"Significant solids production: {t_yr:,.0f} t DS/yr.")
        elif t_yr > 200:
            score += 8
        else:
            score += 2

    severity = _severity(score, MASS_MAX)
    return ConstraintScore("MASS", round(score, 1), evidence, severity)


# ---------------------------------------------------------------------------
# DISPOSAL CONSTRAINT SCORER
# Driven by: PFAS closure, thermal route viability gap, land app risk, cost band
# ---------------------------------------------------------------------------

def _score_disposal(pathway_result, logistics_result) -> ConstraintScore:
    score = 0.0
    evidence = []
    pfas = pathway_result.pfas_constraint
    thermal = pathway_result.thermal_result
    ctx = pathway_result.inputs.context if pathway_result.inputs else None
    stab = pathway_result.inputs.stabilisation.stabilisation if pathway_result.inputs else "NONE"

    # Sub-component 1: PFAS status (0–40)
    if pfas:
        if pfas.route_status == "CLOSED":
            score += 40
            evidence.append("PFAS has CLOSED land application — disposal route is binding constraint.")
        elif pfas.route_status == "CONSTRAINED":
            score += 22
            evidence.append("PFAS constrains land application — enhanced monitoring and route risk.")
        elif pfas.flagged:
            score += 10
            evidence.append("PFAS flagged at LOW risk — monitor closely.")

    # Sub-component 2: Thermal route DS gap (0–30)
    if thermal and not thermal.ds_adequate:
        gap = thermal.ds_gap_pp
        gap_score = min(30, gap * 0.5)    # Each pp of DS gap = 0.5 points, max 30
        score += gap_score
        evidence.append(
            f"{thermal.route} requires {thermal.min_ds_pct_required:.0f}% DS — "
            f"current cake is {thermal.cake_ds_in_pct:.0f}% DS "
            f"({gap:.0f}pp gap). Route not yet operable."
        )
    elif thermal and thermal.route_viable and ctx and ctx.thermal_route != "NONE":
        score += 5    # Thermal selected and viable — disposal being actively managed

    # Sub-component 3: No stabilisation → no land app (0–20)
    if stab == "NONE":
        score += 20
        evidence.append("No stabilisation — Class B minimum not met, land application precluded.")

    # Sub-component 4: Disposal cost band (0–10)
    if logistics_result:
        band_scores = {"VERY_HIGH": 10, "HIGH": 7, "MEDIUM": 4, "LOW": 1}
        bs = band_scores.get(logistics_result.disposal_cost_band, 0)
        score += bs
        if bs >= 7:
            evidence.append(
                f"Disposal cost band {logistics_result.disposal_cost_band} — "
                f"route is expensive and has limited resilience."
            )

    severity = _severity(score, DISPOSAL_MAX)
    return ConstraintScore("DISPOSAL", round(score, 1), evidence, severity)


# ---------------------------------------------------------------------------
# LOGISTICS CONSTRAINT SCORER
# Driven by: loads/day, handling complexity, transport intensity, storage pressure
# ---------------------------------------------------------------------------

def _score_logistics(logistics_result, prod) -> ConstraintScore:
    score = 0.0
    evidence = []

    if not logistics_result:
        return ConstraintScore("LOGISTICS", 0.0, [], "LOW")

    lg = logistics_result

    # Sub-component 1: Transport frequency (0–35)
    loads = lg.truck_loads_per_day
    if loads > 10:
        score += 35
        evidence.append(f"Very high transport frequency: {loads:.1f} loads/day — operationally intensive.")
    elif loads > 5:
        score += 25
        evidence.append(f"High transport frequency: {loads:.1f} loads/day.")
    elif loads > 2:
        score += 15
        evidence.append(f"Moderate transport frequency: {loads:.1f} loads/day.")
    elif loads > 0.5:
        score += 6
    else:
        score += 1    # Very small plant

    # Sub-component 2: Handling complexity (0–25)
    complexity_scores = {"HIGH": 25, "MODERATE": 12, "LOW": 3}
    cs = complexity_scores.get(lg.handling_complexity, 0)
    score += cs
    if cs >= 12:
        evidence.append(
            f"Handling complexity: {lg.handling_complexity}. "
            f"Drivers: {'; '.join(lg.complexity_drivers[:2])}."
        )

    # Sub-component 3: Haul distance intensity (0–20)
    haul = lg.haul_distance_km
    if haul > 200:
        score += 20
        evidence.append(f"Long haul: {haul:.0f} km one-way — significant transport cost exposure.")
    elif haul > 100:
        score += 13
        evidence.append(f"Extended haul distance: {haul:.0f} km.")
    elif haul > 50:
        score += 7
    else:
        score += 2

    # Sub-component 4: Future load growth (0–20)
    if prod and loads > 0.1 and lg.future_truck_loads_per_day > loads * 1.3:
        growth_load_score = min(20, (lg.future_truck_loads_per_day - loads) / loads * 40)
        score += growth_load_score
        evidence.append(
            f"Transport burden grows from {loads:.1f} to "
            f"{lg.future_truck_loads_per_day:.1f} loads/day — logistics pressure increasing."
        )

    severity = _severity(score, LOGISTICS_MAX)
    return ConstraintScore("LOGISTICS", round(score, 1), evidence, severity)


# ---------------------------------------------------------------------------
# COST CONSTRAINT SCORER
# Driven by: heat shortfall (aux boiler OPEX), energy deficit, disposal cost trend
# ---------------------------------------------------------------------------

def _score_cost(pathway_result, logistics_result, prod) -> ConstraintScore:
    score = 0.0
    evidence = []
    hb = pathway_result.heat_balance
    eb = pathway_result.energy_balance
    mad = pathway_result.mad_outputs

    # Sub-component 1: Heat shortfall → aux boiler OPEX (0–30)
    if hb and not hb.heat_self_sufficient:
        shortfall = abs(hb.heat_surplus_deficit_MJ_d)
        # Normalise: 5000 MJ/d shortfall = max score
        heat_score = min(30, shortfall / 5000 * 30)
        score += heat_score
        demand = hb.total_heat_demand_MJ_d
        coverage_pct = (
            hb.total_heat_recovered_MJ_d / demand * 100
            if demand > 0 else 0.0
        )
        evidence.append(
            f"Heat shortfall {shortfall:,.0f} MJ/d — auxiliary boiler adds ongoing OPEX. "
            f"CHP recovery covers only {coverage_pct:.0f}% of demand."
        )

    # Sub-component 2: Energy deficit → grid import cost (0–25)
    if eb and not eb.energy_self_sufficient:
        deficit = abs(eb.net_electrical_export_kWh_d)
        energy_score = min(25, deficit / 500 * 25)
        score += energy_score
        evidence.append(
            f"Energy deficit {deficit:,.0f} kWh/d — grid import cost ongoing. "
            f"Self-sufficiency: {eb.electrical_self_sufficiency_pct:.0f}%."
        )
    elif eb and eb.energy_self_sufficient:
        score += 0   # Energy positive — not a cost driver

    # Sub-component 3: Disposal cost trend (0–25)
    if logistics_result and prod:
        band = logistics_result.disposal_cost_band
        gf = prod.growth_factor
        # High cost band + high growth = strong cost driver
        band_base = {"VERY_HIGH": 20, "HIGH": 14, "MEDIUM": 8, "LOW": 3}.get(band, 0)
        growth_multiplier = min(1.5, gf / 1.2)    # Growth amplifies cost pressure
        cost_score = min(25, band_base * growth_multiplier)
        score += cost_score
        if band in ["HIGH", "VERY_HIGH"] and gf > 1.2:
            evidence.append(
                f"Disposal cost band {band} × {gf:.1f}× volume growth = rising cost trajectory."
            )

    # Sub-component 4: No biogas (missed energy offset) (0–20)
    if not mad or mad.biogas_total_m3_d == 0:
        score += 20
        evidence.append("No biogas production — no energy offset against plant demand.")
    elif eb and eb.biogas_energy_kWh_d < 200:
        score += 10
        evidence.append("Low biogas yield — limited energy offset.")

    severity = _severity(score, COST_MAX)
    return ConstraintScore("COST", round(score, 1), evidence, severity)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _severity(score: float, max_score: float) -> str:
    pct = score / max_score * 100
    if pct >= 65:
        return "CRITICAL"
    elif pct >= 40:
        return "HIGH"
    elif pct >= 20:
        return "MODERATE"
    else:
        return "LOW"


def _constraint_label(ct: str) -> str:
    return {
        "MASS":      "Mass",
        "DISPOSAL":  "Disposal",
        "LOGISTICS": "Logistics",
        "COST":      "Cost",
    }.get(ct, ct)


def _system_type_label(primary: ConstraintScore, secondary: ConstraintScore) -> tuple:
    combos = {
        ("MASS",      "DISPOSAL"):  ("Mass-driven system",      "Volume growth is overwhelming disposal capacity. Stabilisation and mass reduction are the priority."),
        ("MASS",      "LOGISTICS"): ("Mass-volume system",       "High solids production creates both treatment and transport pressure."),
        ("MASS",      "COST"):      ("Mass-cost system",         "Solids volume is driving OPEX upward. Mass reduction delivers both operational and financial relief."),
        ("DISPOSAL",  "MASS"):      ("Disposal-constrained system", "Route availability is binding. Mass reduction helps but route change is unavoidable."),
        ("DISPOSAL",  "LOGISTICS"): ("Disposal-logistics system",  "Route closure and transport burden are co-drivers. Thermal route reduces both."),
        ("DISPOSAL",  "COST"):      ("Disposal-cost system",       "Route risk is translating directly into cost exposure. Route change needed."),
        ("LOGISTICS", "MASS"):      ("Logistics-mass system",      "Transport burden is the immediate constraint, driven by volume. Centralisation and DS improvement are key."),
        ("LOGISTICS", "DISPOSAL"):  ("Logistics-disposal system",  "Transport cost and route risk are co-constraints. Consolidation and route clarity needed."),
        ("LOGISTICS", "COST"):      ("Logistics-cost system",      "Transport intensity is the primary OPEX driver. Increasing cake DS directly reduces cost."),
        ("COST",      "MASS"):      ("Cost-mass system",           "OPEX is the binding constraint, driven by volume. Biogas recovery and mass reduction are priority."),
        ("COST",      "DISPOSAL"):  ("Cost-disposal system",       "Disposal cost is the primary driver. Route change or stabilisation class uplift reduces exposure."),
        ("COST",      "LOGISTICS"): ("Cost-logistics system",      "Operating cost and transport intensity are co-drivers. DS improvement and haul reduction are levers."),
    }
    key = (primary.constraint_type, secondary.constraint_type)
    label, desc = combos.get(key, (
        f"{_constraint_label(primary.constraint_type)}-driven system",
        f"{primary.constraint_type} is the primary system constraint."
    ))
    return label, desc


def _alignment_rules(primary: ConstraintScore,
                     secondary: ConstraintScore) -> tuple:
    """
    Returns (aligned_recommendations, excluded_recommendations).
    Enforces the decision alignment rules from the brief.
    """
    aligned = []
    excluded = []
    p = primary.constraint_type
    s = secondary.constraint_type

    if p == "MASS":
        aligned += [
            "Implement or upgrade anaerobic digestion",
            "Add THP to improve VSR and cake DS",
            "Thermal drying to reduce final volume",
        ]
        if s != "LOGISTICS":
            excluded.append("Centralisation — not indicated unless logistics is a top-2 driver")
        # Thermal only if mass is so severe it overwhelms all routes
        if primary.severity not in ["HIGH", "CRITICAL"]:
            excluded.append("Thermal disposal — not indicated as primary recommendation for mass constraint")

    elif p == "DISPOSAL":
        aligned += [
            "Thermal disposal route (incineration preferred for PFAS)",
            "Stabilisation class uplift to expand land application eligibility",
            "Alternative beneficial reuse pathways (compost, soil amendment)",
        ]
        if s != "LOGISTICS":
            excluded.append("Centralisation — not indicated unless logistics is a top-2 driver")

    elif p == "LOGISTICS":
        aligned += [
            "Increase cake DS to reduce wet mass and truck movements",
            "Thermal drying as a volume reduction step",
            "Centralisation of biosolids management (co-digestion hub)",
            "Regional transport optimisation",
        ]
        # Thermal only if logistics is primary AND disposal is secondary
        if s not in ["DISPOSAL", "MASS"]:
            excluded.append(
                "Thermal disposal — not indicated unless disposal or mass is also a top driver"
            )

    elif p == "COST":
        aligned += [
            "Biogas recovery to reduce energy import cost",
            "THP to improve CHP heat coverage and reduce auxiliary boiler demand",
            "DS improvement to reduce disposal unit cost",
            "Review disposal route for lower-cost alternatives",
        ]
        if s != "LOGISTICS":
            excluded.append("Centralisation — not indicated unless logistics is a top-2 driver")
        if s not in ["DISPOSAL", "MASS"]:
            excluded.append(
                "Thermal disposal — not indicated as primary cost lever unless route risk is present"
            )

    return aligned, excluded


def _primary_narrative(primary: ConstraintScore, pathway_result,
                        prod, logistics_result) -> str:
    ct = primary.constraint_type
    mad = pathway_result.mad_outputs
    fp  = pathway_result.feedstock_profile

    if ct == "MASS":
        vsr_str = f"VSR is {mad.vsr_pct:.0f}%" if mad else "no stabilisation in place"
        t_yr = prod.current_ts_t_yr if prod else 0
        future = prod.future_ts_t_yr if prod else 0
        return (
            f"Solids production ({t_yr:,.0f} t DS/yr, growing to {future:,.0f} t DS/yr) "
            f"is the primary system driver — {vsr_str}. "
            f"Mass reduction is the highest-value intervention."
        )
    elif ct == "DISPOSAL":
        pfas = pathway_result.pfas_constraint
        if pfas and pfas.route_status == "CLOSED":
            return (
                "PFAS has closed the land application route — disposal is the binding constraint. "
                "No recommendation is valid without first resolving the disposal route."
            )
        return (
            "Disposal route availability or regulatory risk is the binding constraint. "
            "Recommendations must address route security before optimising treatment."
        )
    elif ct == "LOGISTICS":
        lg = logistics_result
        loads = lg.truck_loads_per_day if lg else 0
        return (
            f"Transport burden ({loads:.1f} loads/day, {lg.handling_complexity} complexity) "
            f"is the primary cost and operational driver. "
            f"Cake DS improvement is the highest-leverage intervention."
        )
    else:  # COST
        hb = pathway_result.heat_balance
        eb = pathway_result.energy_balance
        parts = []
        if hb and not hb.heat_self_sufficient:
            parts.append(f"heat shortfall ({abs(hb.heat_surplus_deficit_MJ_d):,.0f} MJ/d aux boiler)")
        if eb and not eb.energy_self_sufficient:
            parts.append(f"energy import ({abs(eb.net_electrical_export_kWh_d):,.0f} kWh/d)")
        driver_str = " and ".join(parts) if parts else "disposal cost trajectory"
        return (
            f"OPEX is the binding constraint, driven by {driver_str}. "
            f"Biogas recovery and heat integration improvements deliver fastest payback."
        )


def _secondary_narrative(secondary: ConstraintScore, pathway_result,
                          logistics_result) -> str:
    ct = secondary.constraint_type
    if ct == "MASS":
        mad = pathway_result.mad_outputs
        return (f"Mass reduction is a secondary driver — "
                f"VSR improvement would provide additional relief." if mad else
                "Mass reduction is secondary — stabilisation would reduce volume and cost.")
    elif ct == "DISPOSAL":
        return ("Disposal route risk is a secondary driver — "
                "monitor regulatory developments and PFAS status.")
    elif ct == "LOGISTICS":
        lg = logistics_result
        loads = lg.truck_loads_per_day if lg else 0
        return (f"Logistics burden ({loads:.1f} loads/day) is a secondary driver — "
                f"DS improvement would reduce transport cost.")
    else:
        return ("Cost trajectory is a secondary driver — "
                "energy and disposal cost optimisation should be evaluated alongside primary actions.")
