"""
BioPoint V1 — Compatibility, Carbon, Product, Economic, and Risk Engines.
Implements Parts 6–10 of the specification.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ===========================================================================
# PART 6 — TECHNOLOGY-FEEDSTOCK COMPATIBILITY ENGINE
# ===========================================================================

@dataclass
class CompatibilityResult:
    score: str = "Low"              # High / Moderate / Low
    score_numeric: float = 0.0      # 0-100
    explanation: str = ""
    key_constraints: list = field(default_factory=list)
    key_enablers: list = field(default_factory=list)


def run_compatibility(flowsheet) -> CompatibilityResult:
    """
    Score compatibility between feedstock and flowsheet pathway.
    Does NOT rank technologies — evaluates this feedstock with this pathway.
    """
    fs = flowsheet.inputs.feedstock
    a = flowsheet.assumptions
    ptype = flowsheet.pathway_type

    score = 0.0
    constraints = []
    enablers = []

    # --- BASELINE: always compatible ---
    if ptype == "baseline":
        return CompatibilityResult(
            score="High", score_numeric=80.0,
            explanation="Baseline disposal always feasible — no process requirements.",
            key_constraints=["No mass reduction — full disposal cost retained."],
            key_enablers=["No technology risk."],
        )

    # --- AD ---
    if ptype == "AD":
        score = 70.0
        if fs.sludge_type in ("secondary", "primary", "blended"):
            score += 10
            enablers.append("Fresh sludge feedstock — suitable for AD.")
        if fs.sludge_type in ("digested", "thp_digested"):
            score -= 30
            constraints.append("Already digested — AD adds minimal value.")
        if fs.volatile_solids_percent >= 65:
            score += 10
            enablers.append(f"VS% {fs.volatile_solids_percent:.0f}% — good biodegradable fraction.")
        if fs.feedstock_variability == "high":
            score -= 10
            constraints.append("High variability — digester stability risk.")
        if flowsheet.inputs.assets.anaerobic_digestion_present:
            score += 15
            enablers.append("AD already on site — incremental upgrade.")

    # --- DRYING ONLY ---
    elif ptype == "drying_only":
        score = 65.0
        if fs.dewatered_ds_percent < 15:
            score -= 20
            constraints.append(f"Low feed DS {fs.dewatered_ds_percent:.0f}% — high drying burden.")
        elif fs.dewatered_ds_percent >= 20:
            score += 10
            enablers.append(f"Feed DS {fs.dewatered_ds_percent:.0f}% — reasonable drying start point.")
        if fs.feedstock_variability == "low":
            score += 10
            enablers.append("Low variability — stable dryer operation.")

    # --- PYROLYSIS ---
    elif ptype == "pyrolysis":
        score = 50.0
        # DS requirement: UKWIR notes 85-90% DS typically required
        if fs.dewatered_ds_percent < 18:
            score -= 15
            constraints.append(
                f"Low feed DS {fs.dewatered_ds_percent:.0f}% — high drying duty to reach 87% DS target."
            )
        # GCV requirement: adequate energy content for near-autothermal operation
        if fs.gross_calorific_value_mj_per_kg_ds >= 14:
            score += 20
            enablers.append(f"GCV {fs.gross_calorific_value_mj_per_kg_ds:.1f} MJ/kgDS — autothermal viable.")
        elif fs.gross_calorific_value_mj_per_kg_ds >= 10:
            score += 8
            enablers.append(f"GCV {fs.gross_calorific_value_mj_per_kg_ds:.1f} MJ/kgDS — autothermal marginal.")
        else:
            score -= 15
            constraints.append(
                f"GCV {fs.gross_calorific_value_mj_per_kg_ds:.1f} MJ/kgDS — below autothermal threshold. "
                "Auxiliary fuel likely required."
            )
        # Variability
        if fs.feedstock_variability == "high":
            score -= 15
            constraints.append("High variability — pyrolysis requires consistent feed.")
        elif fs.feedstock_variability == "low":
            score += 10
            enablers.append("Low variability — consistent pyrolysis performance.")
        # PFAS
        if fs.pfas_present == "yes":
            score += 10
            enablers.append("PFAS present — pyrolysis temperatures may achieve destruction.")
        # Biochar market
        biochar_conf = flowsheet.inputs.strategic.biochar_market_confidence
        if biochar_conf == "high":
            score += 15
            enablers.append("High biochar market confidence — product value captured.")
        elif biochar_conf == "low":
            score -= 10
            constraints.append("Low biochar market confidence — product disposal fallback needed.")

    # --- GASIFICATION ---
    elif ptype == "gasification":
        score = 45.0
        if fs.dewatered_ds_percent < 18:
            score -= 20
            constraints.append(
                f"Low feed DS {fs.dewatered_ds_percent:.0f}% — very high drying burden to reach 90% DS."
            )
        if fs.gross_calorific_value_mj_per_kg_ds >= 12:
            score += 15
            enablers.append(f"GCV {fs.gross_calorific_value_mj_per_kg_ds:.1f} MJ/kgDS — gasification viable.")
        else:
            score -= 10
            constraints.append(
                f"GCV {fs.gross_calorific_value_mj_per_kg_ds:.1f} MJ/kgDS — marginal for gasification."
            )
        if fs.feedstock_variability == "high":
            score -= 20
            constraints.append("High variability — gasification requires high feed homogeneity.")
        if fs.ash_percent > 40:
            score -= 10
            constraints.append(f"High ash {fs.ash_percent:.0f}% — slag/vitrification management required.")
        if fs.pfas_present == "yes":
            score += 15
            enablers.append("PFAS present — gasification temperatures typically achieve destruction.")

    # --- HTC ---
    elif ptype in ("HTC", "HTC_sidestream"):
        score = 55.0
        enablers.append("HTC handles wet feed — no thermal pre-drying required.")
        if fs.sludge_type in ("digested", "thp_digested"):
            score += 10
            enablers.append("Digested sludge feedstock — HTC proven on digestate.")
        if fs.dewatered_ds_percent > 30:
            score -= 10
            constraints.append("High DS feed — HTC works best on wetter feed streams.")
        if fs.volatile_solids_percent < 55:
            score -= 15
            constraints.append("Low VS% — limited hydrochar yield and quality.")
        score -= 10
        constraints.append("Hydrochar market confidence typically low — product validation required.")
        constraints.append("Process liquor (filtrate) requires treatment — additional cost.")

    # --- INCINERATION ---
    elif ptype in ("incineration", "thp_incineration"):
        # Incineration is NOT penalised by default.
        # It is evaluated on its actual feedstock compatibility.
        # High robustness, tolerance to variability, and full-scale maturity are positives.
        score = 65.0
        enablers.append(
            "Established full-scale technology — proven at utility scale globally. "
            "High tolerance to feedstock variability."
        )
        # DS requirement: FBF autothermal above ~22% DS; positive energy balance above ~30% DS
        # With pre-drying to 75-85% DS, energy balance is strongly positive
        if fs.dewatered_ds_percent < 15:
            score -= 10
            constraints.append(
                f"Low feed DS {fs.dewatered_ds_percent:.0f}% — high drying burden to reach 78% DS target. "
                "Drying energy demand must be confirmed against energy recovery."
            )
        elif fs.dewatered_ds_percent >= 20:
            score += 10
            enablers.append(
                f"Feed DS {fs.dewatered_ds_percent:.0f}% — manageable drying burden. "
                "Energy balance likely positive with pre-drying to 78% DS."
            )
        # GCV: incineration is less sensitive to GCV than pyrolysis/gasification
        # but still benefits from higher energy content
        if fs.gross_calorific_value_mj_per_kg_ds >= 10:
            score += 10
            enablers.append(
                f"GCV {fs.gross_calorific_value_mj_per_kg_ds:.1f} MJ/kgDS — "
                "positive energy balance with thermal drying pre-treatment confirmed."
            )
        elif fs.gross_calorific_value_mj_per_kg_ds < 8:
            score -= 5
            constraints.append(
                f"GCV {fs.gross_calorific_value_mj_per_kg_ds:.1f} MJ/kgDS — "
                "low; autothermal operation marginal. Pre-drying energy balance must be verified."
            )
        # Variability tolerance: incineration's key advantage over pyrolysis/gasification
        if fs.feedstock_variability == "high":
            score += 15
            enablers.append(
                "High feedstock variability — incineration handles variable feed better "
                "than pyrolysis or gasification. This is a key relative advantage."
            )
        elif fs.feedstock_variability == "moderate":
            score += 8
            enablers.append("Moderate variability — within incineration operating envelope.")
        # PFAS: incineration is the preferred PFAS destruction route
        if fs.pfas_present == "yes":
            score += 20
            enablers.append(
                "PFAS present — incineration at >850°C provides verified PFAS destruction. "
                "This is the most defensible route under regulatory scrutiny."
            )
        elif fs.pfas_present == "unknown":
            score += 8
            enablers.append(
                "PFAS status unknown — incineration provides regulatory certainty "
                "regardless of PFAS outcome."
            )
        # Ash product: moderate confidence — construction/P-recovery routes exist
        score += 5
        enablers.append(
            "Ash product: inert residual — construction aggregate or P-recovery where permitted. "
            "Ash volume is small relative to incoming wet mass."
        )
        # Scale: incineration economics improve strongly at larger scale
        ds_tpd = flowsheet.inputs.feedstock.dry_solids_tpd
        if ds_tpd >= 50:
            score += 10
            enablers.append(
                f"Large scale ({ds_tpd:.0f} tDS/d) — incineration unit economics are "
                "most competitive at this scale. Mandatory benchmark pathway."
            )
        elif ds_tpd < 10:
            score -= 15
            constraints.append(
                f"Small scale ({ds_tpd:.0f} tDS/d) — incineration CAPEX per tonne is high. "
                "Consider co-incineration at regional facility rather than own-asset."
            )

    # --- CENTRALISED ---
    elif ptype == "centralised":
        score = 50.0
        enablers.append("Centralised hub achieves economy of scale in drying/conversion.")
        constraints.append("Requires multi-site coordination — logistics complexity.")
        constraints.append("Hub CAPEX spread over multiple authorities.")
        if fs.dry_solids_tpd < 2.0:
            score -= 10
            constraints.append("Low volume — centralisation benefit reduced at small scale.")
        elif fs.dry_solids_tpd > 5.0:
            score += 15
            enablers.append("High volume — centralisation delivers strong unit cost reduction.")

    # --- DECENTRALISED ---
    elif ptype == "decentralised":
        score = 55.0
        enablers.append("Site-based treatment — no transport to hub required.")
        if fs.dry_solids_tpd > 5.0:
            score -= 10
            constraints.append("High volume — decentralised approach loses economy of scale.")
        if flowsheet.inputs.assets.drying_system_present:
            score += 15
            enablers.append("Drying already on site — incremental upgrade.")

    # Clamp
    score = max(0.0, min(100.0, score))

    if score >= 65:
        label = "High"
    elif score >= 40:
        label = "Moderate"
    else:
        label = "Low"

    explanation = (
        f"{ptype.replace('_',' ').title()} pathway scored {score:.0f}/100 "
        f"for this feedstock. "
        + (f"Key enabler: {enablers[0]}" if enablers else "")
        + (f" Key constraint: {constraints[0]}" if constraints else "")
    )

    return CompatibilityResult(
        score=label,
        score_numeric=round(score, 1),
        explanation=explanation,
        key_constraints=constraints,
        key_enablers=enablers,
    )


# ===========================================================================
# PART 7 — CARBON FLOW ENGINE
# ===========================================================================

@dataclass
class CarbonBalance:
    # Inputs
    carbon_input_t_per_day: float = 0.0
    carbon_fraction_of_ds: float = 0.0

    # Fate
    carbon_to_char_t_per_day: float = 0.0           # Sequestered in biochar/hydrochar
    carbon_to_gas_t_per_day: float = 0.0            # Combusted (biogas/syngas) → CO2
    carbon_to_direct_emissions_t_per_day: float = 0.0
    carbon_sequestered_t_per_day: float = 0.0       # Durable (biochar land application)

    # CO2e
    co2e_sequestered_t_per_day: float = 0.0
    co2e_avoided_t_per_day: float = 0.0             # vs. baseline fossil reference
    co2e_emitted_t_per_day: float = 0.0

    # Carbon credits
    carbon_credit_revenue_per_day: float = 0.0
    carbon_credit_confidence: str = "low"

    # Closure
    carbon_unaccounted_pct: float = 0.0
    notes: str = ""


def run_carbon_balance(flowsheet, mb) -> CarbonBalance:
    """
    Explicit carbon fate tracking — Part 7 of spec.
    Carbon fate depends on process, conditions, and output utilisation.
    Does NOT assume 'carbon negative' — calculates from allocation factors.
    """
    fs = flowsheet.inputs.feedstock
    a = flowsheet.assumptions
    strategic = flowsheet.inputs.strategic
    ptype = flowsheet.pathway_type

    carbon_frac = fs.carbon_fraction_of_ds
    c_input_t_d = fs.dry_solids_tpd * carbon_frac

    # Carbon allocation fractions (sum to <= 1.0; remainder = unaccounted/uncertain)
    c_to_char = a.carbon_to_char_fraction
    c_to_gas = a.carbon_to_gas_fraction
    c_to_emit = a.carbon_to_emissions_fraction

    c_char_t_d = c_input_t_d * c_to_char
    c_gas_t_d = c_input_t_d * c_to_gas
    c_emit_t_d = c_input_t_d * c_to_emit
    c_unaccounted = c_input_t_d * max(0.0, 1.0 - c_to_char - c_to_gas - c_to_emit)

    # Sequestration: only biochar/hydrochar with credible land application qualifies
    # Syngas carbon is combusted → CO2 (not sequestered)
    sequestered = 0.0
    seq_confidence = "low"
    product_type = a.product_type

    if product_type == "biochar":
        # Biochar: ~80% of char carbon considered durable at 100yr horizon (IPCC)
        sequestered = c_char_t_d * 0.80
        seq_confidence = strategic.biochar_market_confidence
    elif product_type == "hydrochar":
        # Hydrochar: lower stability — ~50% durability assumed
        sequestered = c_char_t_d * 0.50
        seq_confidence = "low"

    # CO2e conversion: 1 tonne C = 44/12 = 3.667 tCO2e
    co2e_factor = 44.0 / 12.0
    co2e_seq = sequestered * co2e_factor
    co2e_emitted = (c_gas_t_d + c_emit_t_d) * co2e_factor

    # Avoided emissions: vs. baseline (landfill/land application decomposition)
    # Baseline: ~50% of VS carbon mineralises to CO2 within 10 years at land application
    baseline_c_emitted = c_input_t_d * (fs.volatile_solids_percent / 100.0) * 0.50
    co2e_avoided = max(0.0, (baseline_c_emitted - c_emit_t_d)) * co2e_factor

    # Carbon credit revenue
    ccr_per_day = co2e_seq * strategic.carbon_credit_value_per_tco2e

    # Closure check
    accounted = c_char_t_d + c_gas_t_d + c_emit_t_d
    unaccounted_pct = (c_unaccounted / c_input_t_d * 100) if c_input_t_d > 0 else 0.0

    notes = []
    if unaccounted_pct > 15:
        notes.append(f"⚠ {unaccounted_pct:.0f}% of carbon not allocated — refine process assumptions.")
    if product_type in ("syngas", "heat") and c_to_char == 0:
        notes.append("Carbon is combusted — no sequestration pathway. System is not carbon negative.")
    if seq_confidence == "low" and sequestered > 0:
        notes.append("Carbon credit revenue is sensitive to biochar/hydrochar market confidence.")

    return CarbonBalance(
        carbon_input_t_per_day=round(c_input_t_d, 4),
        carbon_fraction_of_ds=round(carbon_frac, 3),
        carbon_to_char_t_per_day=round(c_char_t_d, 4),
        carbon_to_gas_t_per_day=round(c_gas_t_d, 4),
        carbon_to_direct_emissions_t_per_day=round(c_emit_t_d, 4),
        carbon_sequestered_t_per_day=round(sequestered, 4),
        co2e_sequestered_t_per_day=round(co2e_seq, 4),
        co2e_avoided_t_per_day=round(co2e_avoided, 4),
        co2e_emitted_t_per_day=round(co2e_emitted, 4),
        carbon_credit_revenue_per_day=round(ccr_per_day, 2),
        carbon_credit_confidence=seq_confidence,
        carbon_unaccounted_pct=round(unaccounted_pct, 1),
        notes=" ".join(notes),
    )


# ===========================================================================
# PART 8 — PRODUCT PATHWAY ENGINE
# ===========================================================================

@dataclass
class ProductPathwayResult:
    product_type: str = ""
    product_quantity_tpd: float = 0.0
    product_market_confidence: str = "low"     # low/moderate/high
    reuse_route: str = ""
    disposal_fallback: str = ""
    product_value_per_day: float = 0.0         # Revenue potential $/day
    product_revenue_confidence: str = "low"
    notes: str = ""


# Product revenue assumptions ($/tonne) — conservative operational benchmarks
_PRODUCT_REVENUES = {
    "biochar":       {"low": 0,    "moderate": 150,  "high": 400},   # $/t
    "hydrochar":     {"low": 0,    "moderate": 80,   "high": 200},
    "syngas":        {"low": 0,    "moderate": 0,    "high": 50},    # Usually internal use
    "heat":          {"low": 0,    "moderate": 20,   "high": 60},    # $/MWh equivalent
    "dried_sludge":  {"low": -50,  "moderate": 0,    "high": 30},   # Often still a cost
    "ash":           {"low": -20,  "moderate": 0,    "high": 10},
    "none":          {"low": 0,    "moderate": 0,    "high": 0},
}

_REUSE_ROUTES = {
    "biochar":      "Agriculture/soil amendment; adsorbent; construction supplement",
    "hydrochar":    "Agriculture/soil amendment (validation required); co-fuel",
    "syngas":       "Internal heat/power; CHP; grid injection",
    "heat":         "Internal digester heating; district heat export (if available)",
    "dried_sludge": "Reduced-volume disposal; co-fuel at cement/energy plant",
    "ash":          "Construction material; vitrified mineral product; landfill",
    "none":         "Disposal",
}

_DISPOSAL_FALLBACKS = {
    "biochar":      "Landfill (if product fails market qualification)",
    "hydrochar":    "Landfill or co-fuel (lower value route)",
    "syngas":       "Flare (if not recovered)",
    "heat":         "Heat rejection (wasted if no export market)",
    "dried_sludge": "Disposal at higher DS% — reduced volume benefit retained",
    "ash":          "Inert landfill — typically cheaper than wet sludge",
    "none":         "Baseline disposal",
}


def run_product_pathway(flowsheet, mb) -> ProductPathwayResult:
    """
    Map flowsheet outputs to credible product pathways.
    Confidence levels are explicit — marketability is scored, not assumed.
    """
    a = flowsheet.assumptions
    strategic = flowsheet.inputs.strategic
    fs = flowsheet.inputs.feedstock
    ptype = flowsheet.pathway_type

    product = a.product_type
    conf = a.product_market_confidence

    # Override confidence if strategic inputs are more specific
    if product == "biochar":
        conf = strategic.biochar_market_confidence

    # Product quantity
    if product == "biochar":
        qty = mb.residual_ds_tpd  # Char is the solid residual
    elif product == "hydrochar":
        qty = mb.residual_ds_tpd * 1.1  # Hydrochar slightly higher mass (retained water)
    elif product == "dried_sludge":
        qty = mb.dried_mass_tpd
    elif product == "syngas":
        qty = 0.0  # Gas phase — no solid product quantity
    elif product == "heat":
        qty = 0.0  # Energy product — not tonnes
    else:
        qty = mb.residual_ds_tpd

    # Revenue
    rev_per_tonne = _PRODUCT_REVENUES.get(product, {"low": 0, "moderate": 0, "high": 0}).get(conf, 0)
    if product in ("syngas", "heat"):
        rev_per_day = 0.0  # Handled in energy balance
    elif qty > 0:
        rev_per_day = qty * rev_per_tonne
    else:
        rev_per_day = 0.0

    # PFAS impact on product confidence
    notes = []
    if fs.pfas_present == "yes" and product in ("biochar", "hydrochar", "dried_sludge"):
        if conf != "low":
            conf = "low"
            notes.append("⚠ PFAS present — product land application confidence downgraded to LOW.")
        else:
            notes.append("⚠ PFAS present — product qualification requires PFAS destruction verification.")

    if conf == "low" and rev_per_day > 0:
        notes.append(
            f"Revenue estimate ({rev_per_day:.0f} $/day) is low-confidence. "
            "Do not use in financial base case without market validation."
        )

    return ProductPathwayResult(
        product_type=product,
        product_quantity_tpd=round(qty, 3),
        product_market_confidence=conf,
        reuse_route=_REUSE_ROUTES.get(product, "Unknown"),
        disposal_fallback=_DISPOSAL_FALLBACKS.get(product, "Landfill"),
        product_value_per_day=round(max(0.0, rev_per_day), 2),
        product_revenue_confidence=conf,
        notes=" ".join(notes),
    )


# ===========================================================================
# PART 9 — ECONOMIC ENGINE
# ===========================================================================

@dataclass
class EconomicResult:
    # Avoided costs (value of not doing baseline)
    avoided_disposal_per_year: float = 0.0
    avoided_transport_per_year: float = 0.0
    total_avoided_per_year: float = 0.0

    # OPEX
    drying_energy_cost_per_year: float = 0.0
    auxiliary_fuel_cost_per_year: float = 0.0
    parasitic_power_cost_per_year: float = 0.0
    labour_cost_per_year: float = 0.0
    maintenance_cost_per_year: float = 0.0
    product_handling_cost_per_year: float = 0.0
    post_treatment_transport_per_year: float = 0.0
    total_opex_per_year: float = 0.0

    # Revenue
    energy_export_per_year: float = 0.0
    carbon_credit_per_year: float = 0.0
    product_sales_per_year: float = 0.0
    total_revenue_per_year: float = 0.0

    # CAPEX
    capex_total_m_dollars: float = 0.0
    annualised_capex_per_year: float = 0.0

    # Net position
    net_annual_value: float = 0.0
    cost_per_tds_treated: float = 0.0
    npv_sensitivity: str = ""

    # Confidence flags
    revenue_confidence: str = "low"
    revenue_dependency: str = ""
    revenue_sensitivity: str = ""
    notes: str = ""


def run_economics(flowsheet, mb, dc, eb, carbon, product) -> EconomicResult:
    """
    Full economic comparison per flowsheet — Part 9 of spec.
    Revenue lines carry confidence flags. Optimistic revenues don't dominate.
    """
    fs = flowsheet.inputs.feedstock
    assets = flowsheet.inputs.assets
    a = flowsheet.assumptions
    strategic = flowsheet.inputs.strategic
    ptype = flowsheet.pathway_type

    ds_tpd = fs.dry_solids_tpd
    ds_tyr = ds_tpd * 365

    # --- AVOIDED COSTS ---
    # Compare vs baseline: full wet sludge disposed + transported
    avoided_disposal = ds_tyr * assets.disposal_cost_per_tds
    baseline_transport = (
        fs.wet_sludge_tpd * 365
        * assets.average_transport_distance_km
        * assets.transport_cost_per_tonne_km
    )
    # Post-treatment transport (residual product)
    post_transport = (
        mb.residual_wet_mass_tpd * 365
        * assets.average_transport_distance_km
        * assets.transport_cost_per_tonne_km
    )
    avoided_transport = baseline_transport - post_transport

    # For baseline pathway: no avoided costs (it IS the baseline)
    if ptype == "baseline":
        avoided_disposal = 0.0
        avoided_transport = 0.0

    total_avoided = avoided_disposal + avoided_transport

    # --- OPEX ---
    power_price = assets.local_power_price_per_kwh
    # Fuel price conversion: $/GJ → $/kWh
    # 1 GJ = 1000 MJ = 277.78 kWh → $/GJ ÷ 277.78 = $/kWh
    fuel_price_kwh = assets.fuel_price_per_gj / 277.78

    drying_cost = dc.net_external_drying_energy_kwh_per_day * 365 * power_price
    aux_fuel_cost = eb.auxiliary_fuel_kwh_per_day * 365 * fuel_price_kwh
    parasitic_cost = eb.process_parasitic_kwh_per_day * 365 * power_price

    labour = a.labour_cost_per_year if a.labour_cost_per_year > 0 else (
        a.opex_fixed_per_year * 0.40  # Labour ~40% of fixed OPEX
    )
    maintenance = a.maintenance_fraction_of_capex * a.capex_m_dollars * 1_000_000
    product_handling = mb.residual_ds_tpd * 365 * 20  # $20/tDS for handling
    if ptype == "baseline":
        product_handling = 0.0

    total_opex = (drying_cost + aux_fuel_cost + parasitic_cost +
                  labour + maintenance + product_handling + post_transport)

    # --- REVENUE ---
    # Energy export (net electrical surplus)
    energy_export = max(0.0, eb.net_energy_kwh_per_day) * 365 * power_price
    energy_export_conf = "moderate" if eb.energy_status == "surplus" else "low"

    # Carbon credits — carry confidence
    carbon_credits = carbon.carbon_credit_revenue_per_day * 365
    cc_conf = carbon.carbon_credit_confidence

    # Product revenue — already has confidence from product engine
    product_rev = product.product_value_per_day * 365
    prod_conf = product.product_revenue_confidence

    # Revenue confidence flags
    # Overall revenue confidence = worst of its components
    conf_rank = {"high": 3, "moderate": 2, "low": 1}
    overall_conf = min(
        [energy_export_conf, cc_conf, prod_conf],
        key=lambda c: conf_rank.get(c, 1)
    )

    total_rev = energy_export + carbon_credits + product_rev

    # --- CAPEX ---
    capex_total = a.capex_m_dollars
    ann_capex = a.annualised_capex()

    # --- NET ANNUAL VALUE ---
    net = total_avoided + total_rev - total_opex - ann_capex

    cost_per_tds = (total_opex + ann_capex - total_avoided - total_rev) / ds_tyr if ds_tyr > 0 else 0.0

    # Sensitivity narrative
    notes = []
    if carbon_credits > total_rev * 0.4:
        notes.append(
            f"⚠ Carbon credits represent {carbon_credits/total_rev*100:.0f}% of revenue — "
            "high sensitivity to carbon market."
        )
    if product_rev > total_rev * 0.3 and prod_conf == "low":
        notes.append(
            f"⚠ Product revenue ({product_rev:,.0f} $/yr) carries LOW confidence — "
            "treat as upside only."
        )
    if net < 0:
        notes.append(
            f"Pathway has negative net annual value (${net:,.0f}/yr) — "
            "viable only if strategic drivers override cost."
        )

    sensitivity = (
        "Revenue sensitive to: "
        + (f"carbon price ({cc_conf} confidence); " if carbon_credits > 0 else "")
        + (f"product market ({prod_conf} confidence); " if product_rev > 0 else "")
        + (f"energy price ({energy_export_conf} confidence)." if energy_export > 0 else "")
    ).strip()

    dependency = (
        "Avoided disposal cost drives economics." if avoided_disposal > total_rev
        else "Revenue lines drive economics — validate before committing."
    )

    return EconomicResult(
        avoided_disposal_per_year=round(avoided_disposal, 0),
        avoided_transport_per_year=round(avoided_transport, 0),
        total_avoided_per_year=round(total_avoided, 0),
        drying_energy_cost_per_year=round(drying_cost, 0),
        auxiliary_fuel_cost_per_year=round(aux_fuel_cost, 0),
        parasitic_power_cost_per_year=round(parasitic_cost, 0),
        labour_cost_per_year=round(labour, 0),
        maintenance_cost_per_year=round(maintenance, 0),
        product_handling_cost_per_year=round(product_handling, 0),
        post_treatment_transport_per_year=round(post_transport, 0),
        total_opex_per_year=round(total_opex, 0),
        energy_export_per_year=round(energy_export, 0),
        carbon_credit_per_year=round(carbon_credits, 0),
        product_sales_per_year=round(product_rev, 0),
        total_revenue_per_year=round(total_rev, 0),
        capex_total_m_dollars=round(capex_total, 2),
        annualised_capex_per_year=round(ann_capex, 0),
        net_annual_value=round(net, 0),
        cost_per_tds_treated=round(cost_per_tds, 0),
        revenue_confidence=overall_conf,
        revenue_dependency=dependency,
        revenue_sensitivity=sensitivity,
        notes=" ".join(notes),
    )


# ===========================================================================
# PART 10 — RISK ENGINE
# ===========================================================================

@dataclass
class RiskProfile:
    feedstock_risk: str = "Low"
    drying_energy_closure_risk: str = "Low"
    process_operability_risk: str = "Low"
    market_risk: str = "Low"
    regulatory_risk: str = "Low"
    disposal_fallback_risk: str = "Low"
    logistics_risk: str = "Low"

    overall_risk: str = "Low"
    risk_score: float = 0.0              # 0-100 (higher = riskier)
    risk_narrative: str = ""
    key_risks: list = field(default_factory=list)


_RISK_WEIGHT = {
    "Low": 1, "Moderate": 2, "High": 3,
}


def run_risk_engine(flowsheet, mb, dc, eb, compat,
                    carbon, product, econ) -> RiskProfile:
    """
    Structured multi-category risk assessment — Part 10 of spec.
    Traffic-light output per category + overall risk score.
    """
    fs = flowsheet.inputs.feedstock
    a = flowsheet.assumptions
    assets = flowsheet.inputs.assets
    strategic = flowsheet.inputs.strategic
    ptype = flowsheet.pathway_type

    key_risks = []

    # --- FEEDSTOCK RISK ---
    var_map = {"low": "Low", "moderate": "Moderate", "high": "High"}
    feedstock_r = var_map.get(fs.feedstock_variability, "Moderate")
    if fs.pfas_present == "yes":
        feedstock_r = "High"
        key_risks.append("PFAS present — product route and regulatory approval at risk.")
    if fs.metals_risk == "high":
        feedstock_r = "High"
        key_risks.append("High metals risk — product land application precluded.")

    # --- DRYING/ENERGY CLOSURE RISK ---
    if dc.energy_closure_risk or eb.energy_closure_risk:
        energy_r = "High"
        key_risks.append("Energy closure risk flagged — auxiliary fuel dependency unresolved.")
    elif not dc.drying_required:
        energy_r = "Low"
    elif dc.net_external_drying_energy_kwh_per_day > 0:
        energy_r = "Moderate"
    else:
        energy_r = "Low"

    # --- PROCESS OPERABILITY RISK ---
    operability_map = {
        "baseline":      "Low",
        "AD":            "Low",
        "drying_only":   "Low",
        "pyrolysis":     "Moderate",
        "gasification":  "High",
        "HTC":           "Moderate",
        "HTC_sidestream": "Low",     # Sidestream treatment removes the HIGH impact from raw HTC
        "centralised":   "Moderate",
        "decentralised": "Low",
        "incineration":  "Low",
        "thp_incineration": "Low",    # THP is established; same operability as incineration technology — lower operability risk
    }
    operability_r = operability_map.get(ptype, "Moderate")
    if fs.feedstock_variability == "high" and ptype in ("pyrolysis", "gasification"):
        operability_r = "High"
        key_risks.append("High variability + thermal conversion = process stability risk.")

    # --- MARKET RISK ---
    conf_map = {"high": "Low", "moderate": "Moderate", "low": "High"}
    market_r = conf_map.get(product.product_market_confidence, "High")
    if product.product_type == "none":
        market_r = "Low"  # No product market needed
    if econ.carbon_credit_per_year > econ.total_revenue_per_year * 0.5:
        market_r = "High"
        key_risks.append("Carbon credit revenue > 50% of total — high carbon market dependency.")

    # --- REGULATORY RISK ---
    reg_map = {"low": "Low", "moderate": "Moderate", "high": "High"}
    regulatory_r = reg_map.get(strategic.regulatory_pressure, "Moderate")
    if fs.pfas_present == "yes" and ptype not in ("pyrolysis", "gasification"):
        regulatory_r = "High"
        key_risks.append("PFAS + non-thermal route — regulatory approval pathway uncertain.")

    # --- DISPOSAL FALLBACK RISK ---
    if product.disposal_fallback and "landfill" in product.disposal_fallback.lower():
        fallback_r = "Moderate"
    elif ptype == "baseline":
        fallback_r = "Low"  # Already at fallback
    else:
        fallback_r = "Low"
    if product.product_market_confidence == "low" and ptype not in ("baseline", "drying_only"):
        fallback_r = "Moderate"
        key_risks.append("Low product confidence — disposal fallback route must be confirmed.")

    # --- LOGISTICS RISK ---
    if ptype == "centralised":
        logistics_r = "Moderate"
        key_risks.append("Centralised hub — multi-site coordination and transport dependency.")
    elif mb.residual_wet_mass_tpd > fs.wet_sludge_tpd * 0.7:
        logistics_r = "Moderate"
    else:
        logistics_r = "Low"

    # --- OVERALL ---
    categories = [feedstock_r, energy_r, operability_r, market_r,
                  regulatory_r, fallback_r, logistics_r]
    risk_score = sum(_RISK_WEIGHT.get(r, 1) for r in categories) / (3 * len(categories)) * 100
    if risk_score >= 67:
        overall = "High"
    elif risk_score >= 40:
        overall = "Moderate"
    else:
        overall = "Low"

    narrative = (
        f"Overall risk: {overall} ({risk_score:.0f}/100). "
        + (f"Key risk: {key_risks[0]}" if key_risks else "No critical risks identified.")
    )

    return RiskProfile(
        feedstock_risk=feedstock_r,
        drying_energy_closure_risk=energy_r,
        process_operability_risk=operability_r,
        market_risk=market_r,
        regulatory_risk=regulatory_r,
        disposal_fallback_risk=fallback_r,
        logistics_risk=logistics_r,
        overall_risk=overall,
        risk_score=round(risk_score, 1),
        risk_narrative=narrative,
        key_risks=key_risks,
    )
