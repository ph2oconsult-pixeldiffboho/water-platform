"""
BioPoint V1 — Drying Dominance & Feedstock Reality Engine (v24Z81).

Thermal sludge systems are drying-limited. No recommendation is valid
unless drying feasibility is confirmed.

This module extends the existing energy_system layer with:

  1. Explicit latent heat calculation (kJ/kg and kWh/tonne water removed)
  2. Drying energy as % of feedstock energy — the critical dominance ratio
  3. DS% at energy neutrality for ALL thermal pathways (not just incineration)
  4. Feedstock handling risk assessment (stickiness, odour, variability)
  5. Drying feasibility gate — NON-VIABLE pathways cannot rank as Preferred
  6. Scoring penalty proportional to energy deficit magnitude

Fail condition (per spec):
  If drying feasibility is not demonstrated → pathway cannot rank as Preferred.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ---------------------------------------------------------------------------
# PHYSICS CONSTANTS
# ---------------------------------------------------------------------------

# Latent heat of vaporisation of water
# At 100°C (standard evaporation): 2,257 kJ/kg
# At typical indirect dryer operating temp (~80-120°C): 2,270 kJ/kg effective
# At direct dryer (ambient to exhaust): slightly higher due to sensible heat
LATENT_HEAT_KJ_PER_KG = 2_270.0        # kJ/kg water evaporated
LATENT_HEAT_KWH_PER_TONNE = 2_270.0 / 3.6  # kWh/tonne water = 630.6 kWh/t

# Dryer efficiency factors
DRYER_EFFICIENCY = {
    "indirect": 0.75,   # Heat transfer losses ~25%
    "direct":   0.55,   # Exhaust gas carries significant latent heat
    "belt":     0.72,
    "solar":    0.40,   # High losses; weather-dependent
    "none":     1.00,   # No dryer
}

# Specific energy consumption (kWh/kg water removed) by dryer type
# This is THEORETICAL minimum (latent heat / efficiency)
# Latent heat: 0.630 kWh/kg → at 75% efficiency = 0.840 kWh/kg
SPECIFIC_ENERGY_KWH_PER_KG = {
    "indirect": 0.80,   # Conservative mid-range (0.65-0.95 operational range)
    "direct":   1.00,   # Higher due to exhaust losses
    "belt":     0.78,
    "solar":    1.60,   # Per kWh thermal input (large footprint, slow)
    "none":     0.00,
}

# Process heat recovery fractions (what fraction of feedstock energy is recoverable
# as usable heat for the drying loop — separate from electrical output)
PROCESS_HEAT_FOR_DRYING = {
    "pyrolysis":       0.30,   # Process gas combustion → dryer heat
    "gasification":    0.25,   # Syngas combustion
    "incineration":    0.40,   # Flue gas / steam extraction
    "thp_incineration":0.40,
    "drying_only":     0.00,   # No thermal conversion
    "HTC":             0.00,   # Not applicable (wet process)
    "HTC_sidestream":  0.00,
    "AD":              0.00,   # CHP heat available but not for drying here
    "baseline":        0.00,
    "centralised":     0.30,
    "decentralised":   0.00,
}

# DS% thresholds (engineering references)
DS_THRESHOLD_FBF_AUTOTHERMAL = 22.0     # FBF minimum for wet-feed combustion
DS_THRESHOLD_ENERGY_NEUTRALITY = 28.0  # Approx DS% at which incineration self-supplies drying
DS_THRESHOLD_PYROLYSIS_MIN    = 75.0   # Minimum feed DS% for reliable pyrolysis
DS_THRESHOLD_GASIFICATION_MIN = 85.0   # Minimum feed DS% for gasification
DS_THRESHOLD_INCINERATION_DRY = 70.0   # Below this, pre-drying is mandatory

# Scoring penalties for energy deficit (applied to flowsheet.score)
DEFICIT_PENALTY = {
    # (deficit_as_pct_feedstock) -> score penalty
    "mild":     ( 10,  30,  -3.0),   # 10-30% of feedstock energy: -3 points
    "moderate": ( 30,  70, -10.0),   # 30-70%: -10 points
    "severe":   ( 70, 120, -18.0),   # 70-120%: -18 points
    "extreme":  (120, 999, -25.0),   # >120%: -25 points (drying > feedstock energy)
}


# ---------------------------------------------------------------------------
# FEEDSTOCK HANDLING RISK
# ---------------------------------------------------------------------------

@dataclass
class FeedstockHandlingRisk:
    """Physical handling characteristics of the dewatered sludge."""
    sludge_type: str = ""
    dewatered_ds_pct: float = 0.0
    variability: str = "moderate"

    # Individual risk factors
    stickiness_risk: str = "Low"     # Low / Medium / High
    odour_risk: str = "Low"
    variability_risk: str = "Low"
    drying_sensitivity: str = "Low"  # How sensitive is the drying step to feed variation

    # Handling requirements
    grinding_required: bool = False
    homogenisation_required: bool = False
    pre_screening_required: bool = False

    # Overall
    handling_risk: str = "LOW"       # LOW / MEDIUM / HIGH
    handling_narrative: str = ""
    handling_implications: list = field(default_factory=list)


def assess_feedstock_handling(feedstock_inputs, pathway_type: str) -> FeedstockHandlingRisk:
    """
    Assess feedstock physical handling risk for a thermal pathway.
    Based on sludge type, DS%, variability, and pathway requirements.
    """
    fs = feedstock_inputs
    ds_pct = fs.dewatered_ds_percent
    stype  = fs.sludge_type
    var    = fs.feedstock_variability
    vs_pct = fs.volatile_solids_percent

    risk = FeedstockHandlingRisk(
        sludge_type=stype,
        dewatered_ds_pct=ds_pct,
        variability=var,
    )

    implications = []

    # --- STICKINESS ---
    # Sludge in the 45-65% DS range becomes highly sticky / plastic
    # Below 30% DS: pumpable paste. Above 65% DS: granular/crumbly.
    # The sticky zone (45-65% DS) creates major handling problems for screw conveyors,
    # belt dryers, and rotary dryers.
    if 45 <= ds_pct <= 65:
        risk.stickiness_risk = "High"
        implications.append(
            f"Feed DS {ds_pct:.0f}% is in the sticky zone (45-65% DS) — "
            "highly plastic sludge adheres to dryer surfaces, plugs conveyors, "
            "and causes bridging. Vendor dryer design must explicitly address this."
        )
    elif 30 <= ds_pct < 45:
        risk.stickiness_risk = "Medium"
        implications.append(
            f"Feed DS {ds_pct:.0f}% is below the worst sticky zone but still plastic. "
            "Conveyor design and dryer surface coatings are important."
        )
    elif ds_pct > 65:
        risk.stickiness_risk = "Low"
        implications.append(
            f"Feed DS {ds_pct:.0f}% is above the sticky zone — granular/crumbly. "
            "Easier conveying but dust generation increases."
        )
    else:
        risk.stickiness_risk = "Low"   # <30% DS — pumpable

    # --- ODOUR ---
    # Digested sludge: lower odour than raw. High VS = more odour potential.
    if stype in ("secondary", "raw", "blended") and ds_pct < 30:
        risk.odour_risk = "High"
        implications.append(
            "Undigested or partially digested sludge at low DS%: high odour potential "
            "during handling and drying. Enclosed dryer and odour control essential."
        )
    elif stype in ("digested", "thp_digested"):
        risk.odour_risk = "Medium"
        implications.append(
            "Digested sludge: moderate odour during drying (ammonia stripping). "
            "Odour extraction and scrubbing recommended."
        )
    else:
        risk.odour_risk = "Low" if ds_pct > 50 else "Medium"

    # --- VARIABILITY ---
    var_map = {"low": "Low", "moderate": "Medium", "high": "High"}
    risk.variability_risk = var_map.get(var, "Medium")

    # Thermal pathway sensitivity to feed variation
    if pathway_type in ("pyrolysis", "gasification"):
        risk.drying_sensitivity = "High"
        if var == "high":
            implications.append(
                "HIGH variability + thermal conversion: pyrolysis/gasification requires "
                "consistent feed DS% and GCV. Feed variation causes: unstable reactor "
                "temperatures, inconsistent product quality, frequent shutdowns. "
                "Homogenisation and buffer storage are essential at this variability."
            )
            risk.homogenisation_required = True
        elif var == "moderate":
            implications.append(
                "Moderate variability: consider buffer silo upstream of dryer "
                "to blend feed and smooth DS% variation."
            )
    elif pathway_type == "incineration":
        risk.drying_sensitivity = "Low"   # FBF tolerant of variability
        implications.append(
            "Incineration (FBF): high tolerance to feed variability. "
            "This is a genuine operational advantage over pyrolysis/gasification."
        )
    elif pathway_type in ("HTC", "HTC_sidestream"):
        risk.drying_sensitivity = "Low"
        implications.append(
            "HTC: wet-feed process tolerates variability. No drying means "
            "DS% variation does not affect process stability."
        )

    # --- GRINDING / SCREENING ---
    if pathway_type in ("pyrolysis", "gasification") and ds_pct > 70:
        risk.grinding_required = True
        implications.append(
            f"At {ds_pct:.0f}% DS, dried sludge forms hard granules/lumps. "
            "Grinding or milling to uniform particle size is required before "
            "pyrolysis/gasification reactor entry."
        )

    # --- OVERALL RISK ---
    risk_scores = {
        "Low": 1, "Medium": 2, "High": 3
    }
    total = (risk_scores.get(risk.stickiness_risk, 1) +
             risk_scores.get(risk.odour_risk, 1) +
             risk_scores.get(risk.variability_risk, 1) +
             risk_scores.get(risk.drying_sensitivity, 1))

    if total >= 9:
        risk.handling_risk = "HIGH"
    elif total >= 6:
        risk.handling_risk = "MEDIUM"
    else:
        risk.handling_risk = "LOW"

    risk.handling_implications = implications
    risk.handling_narrative = (
        f"Feed DS {ds_pct:.0f}% | {stype} | variability {var}. "
        f"Stickiness: {risk.stickiness_risk}. "
        f"Odour: {risk.odour_risk}. "
        f"Pathway sensitivity: {risk.drying_sensitivity}. "
        f"Overall handling risk: {risk.handling_risk}."
    )
    return risk


# ---------------------------------------------------------------------------
# DRYING DOMINANCE RESULT
# ---------------------------------------------------------------------------

@dataclass
class DryingDominanceResult:
    """
    Full drying dominance assessment for one flowsheet.
    Extends energy_system with explicit physics and the fail gate.
    """
    flowsheet_id: str = ""
    pathway_type: str = ""
    pathway_name: str = ""

    # --- FEEDSTOCK STATE ---
    feed_ds_pct: float = 0.0
    target_ds_pct: float = 0.0
    ds_uplift_required_pct_points: float = 0.0   # How many %DS points to gain
    wet_feed_t_d: float = 0.0
    dry_solids_t_d: float = 0.0
    water_to_remove_t_d: float = 0.0
    water_to_remove_kg_d: float = 0.0
    drying_required: bool = False

    # --- LATENT HEAT (EXPLICIT) ---
    latent_heat_kj_per_kg: float = LATENT_HEAT_KJ_PER_KG
    latent_heat_kwh_per_tonne_water: float = LATENT_HEAT_KWH_PER_TONNE
    theoretical_min_drying_kwh_d: float = 0.0     # Latent heat × water mass only
    specific_energy_kwh_per_kg: float = 0.0        # Including dryer efficiency
    gross_drying_energy_kwh_d: float = 0.0         # Actual dryer demand

    # --- ENERGY BUDGET ---
    feedstock_energy_kwh_d: float = 0.0
    process_heat_recoverable_kwh_d: float = 0.0    # Usable for drying
    site_waste_heat_kwh_d: float = 0.0
    total_internal_heat_kwh_d: float = 0.0
    external_energy_required_kwh_d: float = 0.0
    external_energy_kwh_per_tds: float = 0.0

    # --- DOMINANCE RATIOS ---
    drying_as_pct_of_feedstock_energy: float = 0.0  # THE critical ratio
    drying_dominance_label: str = ""   # "Marginal" / "Significant" / "Dominant" / "Extreme"
    internal_coverage_pct: float = 0.0

    # --- ENERGY NEUTRALITY ---
    ds_for_energy_neutrality_pct: Optional[float] = None  # For this pathway
    neutrality_achievable: bool = False
    neutrality_note: str = ""

    # --- VIABILITY ---
    energy_viability_flag: str = ""
    can_rank_as_preferred: bool = True   # THE GATE: False if NON-VIABLE

    # --- SCORE ADJUSTMENT ---
    score_penalty: float = 0.0
    score_penalty_reason: str = ""

    # --- HANDLING ---
    handling_risk: Optional[FeedstockHandlingRisk] = None

    # --- DISPLAY SUMMARY ---
    drying_summary: str = ""

    # --- v25A30: DS% VIABILITY THRESHOLD LABELS (P4) ---
    # Named labels for pyrolysis/thermal pathway viability at current DS%:
    #   NOT VIABLE      DS < 30%  (gate FAIL for all thermal pyrolysis)
    #   MARGINAL        DS 30-38% (gate FAIL for pyrolysis; PASS for incineration)
    #   APPROACHING     DS 38-48% (pyrolysis approaching energy neutral; <10% DS gap)
    #   ENERGY-NEUTRAL  DS ≥ neutrality threshold for this pathway
    #   NOT APPLICABLE  Wet-feed pathways (HTC, AD, baseline)
    ds_viability_label: str = ""

    # --- v25A30: WATER-REMOVAL CONSTRAINT FLAG (P1) ---
    # True when feed DS% < 20% — system is water-removal constrained
    system_water_constrained: bool = False
    system_water_constrained_label: str = ""


# ---------------------------------------------------------------------------
# DS% FOR ENERGY NEUTRALITY — ALL THERMAL PATHWAYS
# ---------------------------------------------------------------------------

def calculate_ds_for_neutrality(pathway_type: str, ds_tpd: float,
                                  gcv_mj_per_kg_ds: float,
                                  dryer_type: str = "indirect",
                                  specific_energy: float = 0.80,
                                  dryer_eff: float = 0.75) -> Optional[float]:
    """
    For a given thermal pathway, calculate the minimum feed DS% at which
    the pathway's internal heat can fully cover drying energy demand.

    Solves:  process_heat(DS%) = drying_energy(DS%)
    Where:   process_heat = feedstock_energy × process_heat_fraction
             drying_energy = water_removed(DS%) × spec_energy / efficiency

    Returns DS% or None if not achievable below 50% DS.
    """
    heat_fraction = PROCESS_HEAT_FOR_DRYING.get(pathway_type, 0.0)
    if heat_fraction <= 0 or dryer_type == "none":
        return None  # No recoverable process heat or no drying needed

    # feedstock_energy = ds_tpd × 1000 × gcv / 3.6  (kWh/d)
    feedstock_kwh_d = ds_tpd * 1000 * gcv_mj_per_kg_ds / 3.6
    process_heat = feedstock_kwh_d * heat_fraction

    # For target DS% = pathway target (we use a conservative target of 80%)
    # water_removed(feed_ds) = ds_tpd/feed_ds - ds_tpd/0.80
    # drying_kwh = water_removed × 1000 × spec_energy / dryer_eff

    # Solve numerically: find feed_ds where process_heat = drying_kwh
    # process_heat >= drying_kwh
    # feedstock_kwh × heat_fraction >= (ds_tpd/feed_ds - ds_tpd/0.80) × 1000 × spec/eff
    # Rearrange for feed_ds:
    # ds_tpd/feed_ds = ds_tpd/0.80 + process_heat × eff / (1000 × spec)
    # feed_ds = ds_tpd / (ds_tpd/0.80 + process_heat × eff / (1000 × spec))

    denom_add = process_heat * dryer_eff / (1000 * specific_energy)
    denominator = ds_tpd / 0.80 + denom_add
    if denominator <= 0:
        return None

    feed_ds_needed = ds_tpd / denominator
    feed_ds_pct = feed_ds_needed * 100.0

    if feed_ds_pct > 50.0:
        return None   # Not achievable at realistic DS%
    if feed_ds_pct < 0.5:
        return None   # Essentially always viable

    return round(feed_ds_pct, 1)


# ---------------------------------------------------------------------------
# DRYING DOMINANCE CALCULATOR
# ---------------------------------------------------------------------------

def run_drying_dominance(flowsheet, feedstock_inputs) -> DryingDominanceResult:
    """
    Full drying dominance assessment for one flowsheet.
    Draws on drying_calc and energy_system already computed by the runner.
    Adds explicit latent heat, ratios, neutrality DS%, handling risk, and fail gate.
    """
    fs_in    = feedstock_inputs
    a        = flowsheet.assumptions
    dc       = flowsheet.drying_calc
    esys     = flowsheet.energy_system
    ptype    = flowsheet.pathway_type

    ds_tpd       = fs_in.dry_solids_tpd
    feed_ds_pct  = fs_in.dewatered_ds_percent
    gcv          = fs_in.gross_calorific_value_mj_per_kg_ds
    feedstock_kwh_d = ds_tpd * 1000 * gcv / 3.6

    target_ds_pct = a.target_ds_percent if a else feed_ds_pct
    wet_feed_t_d  = ds_tpd / (feed_ds_pct / 100.0)

    r = DryingDominanceResult(
        flowsheet_id=flowsheet.flowsheet_id,
        pathway_type=ptype,
        pathway_name=flowsheet.name,
        feed_ds_pct=feed_ds_pct,
        target_ds_pct=target_ds_pct,
        ds_uplift_required_pct_points=max(0.0, target_ds_pct - feed_ds_pct),
        wet_feed_t_d=round(wet_feed_t_d, 1),
        dry_solids_t_d=round(ds_tpd, 1),
        feedstock_energy_kwh_d=round(feedstock_kwh_d, 0),
        energy_viability_flag=esys.energy_viability_flag if esys else "UNKNOWN",
    )

    drying_required = dc.drying_required if dc else False
    r.drying_required = drying_required

    if not drying_required:
        r.water_to_remove_t_d   = 0.0
        r.water_to_remove_kg_d  = 0.0
        r.theoretical_min_drying_kwh_d = 0.0
        r.gross_drying_energy_kwh_d    = 0.0
        r.drying_as_pct_of_feedstock_energy = 0.0
        r.drying_dominance_label = "None — wet feed pathway"
        r.internal_coverage_pct  = 100.0
        r.external_energy_required_kwh_d = 0.0
        r.external_energy_kwh_per_tds   = 0.0
        r.can_rank_as_preferred  = True
        r.score_penalty = 0.0
        r.drying_summary = (
            f"No pre-drying required. Wet-feed process ({ptype}). "
            "Drying energy constraint does not apply."
        )
        r.handling_risk = assess_feedstock_handling(fs_in, ptype)
        return r

    # --- EXPLICIT LATENT HEAT ---
    water_t_d  = dc.water_removed_tpd
    water_kg_d = water_t_d * 1000.0
    r.water_to_remove_t_d  = round(water_t_d, 1)
    r.water_to_remove_kg_d = round(water_kg_d, 0)

    # Theoretical minimum: latent heat only (no efficiency losses)
    theoretical_min = water_kg_d * (LATENT_HEAT_KJ_PER_KG / 3600)  # kWh/d
    r.theoretical_min_drying_kwh_d = round(theoretical_min, 0)
    r.latent_heat_kj_per_kg        = LATENT_HEAT_KJ_PER_KG
    r.latent_heat_kwh_per_tonne_water = LATENT_HEAT_KWH_PER_TONNE

    # Actual dryer demand (with efficiency)
    dryer_type = a.dryer_type if a else "indirect"
    spec_energy = a.drying_specific_energy_kwh_per_kg_water if a else 0.80
    dryer_eff   = a.dryer_efficiency if (a and a.dryer_efficiency > 0) else 0.75
    gross_kwh_d = dc.drying_energy_actual_kwh_per_day
    r.specific_energy_kwh_per_kg = spec_energy
    r.gross_drying_energy_kwh_d  = round(gross_kwh_d, 0)

    # --- ENERGY BUDGET ---
    process_heat_frac = PROCESS_HEAT_FOR_DRYING.get(ptype, 0.0)
    process_heat_kwh_d = feedstock_kwh_d * process_heat_frac
    site_waste_heat    = flowsheet.inputs.assets.waste_heat_available_kwh_per_day if flowsheet.inputs else 0.0

    total_internal = min(
        gross_kwh_d,
        process_heat_kwh_d + site_waste_heat
    )
    external_kwh_d = max(0.0, gross_kwh_d - total_internal)

    r.process_heat_recoverable_kwh_d = round(process_heat_kwh_d, 0)
    r.site_waste_heat_kwh_d          = round(site_waste_heat, 0)
    r.total_internal_heat_kwh_d      = round(total_internal, 0)
    r.external_energy_required_kwh_d = round(external_kwh_d, 0)
    r.external_energy_kwh_per_tds    = round(external_kwh_d / ds_tpd, 0) if ds_tpd > 0 else 0
    r.internal_coverage_pct          = round(total_internal / gross_kwh_d * 100, 1) if gross_kwh_d > 0 else 0

    # --- DOMINANCE RATIO (the critical output) ---
    ratio = gross_kwh_d / feedstock_kwh_d * 100 if feedstock_kwh_d > 0 else 0
    r.drying_as_pct_of_feedstock_energy = round(ratio, 1)

    if ratio < 30:
        r.drying_dominance_label = "Marginal"
    elif ratio < 70:
        r.drying_dominance_label = "Significant"
    elif ratio < 100:
        r.drying_dominance_label = "Dominant"
    else:
        r.drying_dominance_label = "Extreme — drying exceeds feedstock energy"

    # --- ENERGY NEUTRALITY DS% ---
    ds_neutral = calculate_ds_for_neutrality(
        ptype, ds_tpd, gcv, dryer_type, spec_energy, dryer_eff
    )
    r.ds_for_energy_neutrality_pct = ds_neutral
    if ds_neutral is not None:
        r.neutrality_achievable = ds_neutral <= 45.0
        if r.neutrality_achievable:
            r.neutrality_note = (
                f"Energy neutrality achievable at feed DS% ≥ {ds_neutral:.0f}% "
                f"(current: {feed_ds_pct:.0f}%). "
                f"Gap: {max(0, ds_neutral - feed_ds_pct):.0f} %DS points. "
                f"Upstream preconditioning (THP or filter press) may close this gap."
            )
        else:
            r.neutrality_note = (
                f"Energy neutrality would require DS% ≥ {ds_neutral:.0f}% — "
                f"not achievable through standard preconditioning. "
                f"External energy is structurally required for this pathway."
            )
    else:
        if ptype in ("HTC", "HTC_sidestream", "baseline", "AD"):
            r.neutrality_note = "Not applicable — no drying required."
        else:
            r.neutrality_note = (
                "Insufficient process heat recovery to achieve energy neutrality. "
                "External energy structurally required."
            )

    # --- FAIL GATE (per spec) ---
    viability = esys.energy_viability_flag if esys else "UNKNOWN"
    can_prefer = viability != "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT"
    r.can_rank_as_preferred = can_prefer

    # --- SCORE PENALTY ---
    deficit_ratio = (external_kwh_d / feedstock_kwh_d * 100) if feedstock_kwh_d > 0 else 0
    penalty = 0.0
    penalty_reason = ""
    for label, (low, high, pen) in DEFICIT_PENALTY.items():
        if low <= deficit_ratio < high:
            penalty = pen
            penalty_reason = (
                f"{label.title()} energy deficit: external drying = "
                f"{deficit_ratio:.0f}% of feedstock energy ({external_kwh_d:,.0f} kWh/d). "
                f"Score penalty: {pen:.0f} points."
            )
            break
    if not can_prefer and penalty == 0.0:
        penalty = -10.0
        penalty_reason = "NON-VIABLE without external input — additional penalty applied."

    r.score_penalty = round(penalty, 1)
    r.score_penalty_reason = penalty_reason

    # --- v25A30: DS% VIABILITY THRESHOLD LABELS (P4) ---
    if ptype in ("HTC", "HTC_sidestream", "AD", "baseline", "decentralised"):
        r.ds_viability_label = "NOT APPLICABLE — wet-feed or no-drying pathway"
    elif ptype == "drying_only":
        r.ds_viability_label = "NOT APPLICABLE — no thermal conversion"
    else:
        # Thermal pathways: assign named label based on DS% and neutrality threshold
        nd = r.ds_for_energy_neutrality_pct
        if feed_ds_pct < 30.0:
            r.ds_viability_label = (
                f"NOT VIABLE — DS {feed_ds_pct:.0f}% is below the 30% minimum for "
                "credible thermal pathway operation. Mechanical dewatering to ≥30% DS required."
            )
        elif feed_ds_pct < 38.0:
            neutrality_gap = f" (neutrality requires {nd:.0f}% DS — gap {nd - feed_ds_pct:.0f}%DS)" if nd else ""
            r.ds_viability_label = (
                f"MARGINAL — DS {feed_ds_pct:.0f}% enables incineration but pyrolysis "
                "remains energy non-viable. THP + filter press to reach 38%+ DS "
                f"required to unlock pyrolysis{neutrality_gap}."
            )
        elif nd and feed_ds_pct < nd:
            gap = nd - feed_ds_pct
            r.ds_viability_label = (
                f"APPROACHING ENERGY-NEUTRAL — DS {feed_ds_pct:.0f}% is {gap:.0f}%DS "
                f"below energy neutrality ({nd:.0f}% DS). External energy required "
                "but substantially reduced. Advanced preconditioning (THP + filter press) "
                "may close this gap."
            )
        else:
            r.ds_viability_label = (
                f"ENERGY-NEUTRAL — DS {feed_ds_pct:.0f}% meets or exceeds the "
                f"energy neutrality threshold for this pathway "
                + (f"({nd:.0f}% DS)." if nd else "(pathway self-supplies drying).")
            )

    # --- v25A30: WATER-REMOVAL CONSTRAINT FLAG (P1) ---
    if feed_ds_pct < 20.0:
        r.system_water_constrained = True
        r.system_water_constrained_label = (
            f"WATER-REMOVAL CONSTRAINED — feed DS {feed_ds_pct:.0f}% is below 20%. "
            "All thermal pathways are blocked until mechanical dewatering is installed. "
            "Drying energy at this DS% is unachievable without massive external energy input. "
            "The primary engineering priority is dewatering, not technology selection."
        )
    else:
        r.system_water_constrained = False
        r.system_water_constrained_label = ""

    # --- HANDLING RISK ---
    r.handling_risk = assess_feedstock_handling(fs_in, ptype)

    # --- DISPLAY SUMMARY ---
    r.drying_summary = (
        f"Drying: {water_t_d:.0f} t/d water removed | "
        f"{feed_ds_pct:.0f}% → {target_ds_pct:.0f}% DS | "
        f"Gross {gross_kwh_d:,.0f} kWh/d = "
        f"{ratio:.0f}% of feedstock energy ({r.drying_dominance_label.lower()}). "
        f"Internal covers {r.internal_coverage_pct:.0f}% | "
        f"External: {external_kwh_d:,.0f} kWh/d ({r.external_energy_kwh_per_tds:.0f} kWh/tDS). "
        f"Neutrality DS%: {ds_neutral:.0f}% " if ds_neutral else ""
        f"Gate: {'PASS' if can_prefer else 'FAIL — cannot rank as Preferred'}."
    )

    return r


# ---------------------------------------------------------------------------
# SYSTEM-LEVEL RUNNER
# ---------------------------------------------------------------------------

@dataclass
class DryingDominanceSystem:
    """System-level drying dominance assessment across all flowsheets."""
    results: dict = field(default_factory=dict)    # flowsheet_id -> DryingDominanceResult
    score_adjustments: dict = field(default_factory=dict)  # flowsheet_id -> penalty

    # Summary
    n_non_viable: int = 0
    n_viable: int = 0
    drying_limited_pathways: list = field(default_factory=list)
    gate_failed_pathways: list = field(default_factory=list)
    gate_passed_pathways: list = field(default_factory=list)

    primary_constraint_is_drying: bool = False
    drying_dominance_narrative: str = ""

    # v25A30: P1 system water constraint
    system_water_constrained: bool = False
    system_water_constrained_label: str = ""
    feed_ds_pct: float = 0.0


def run_drying_dominance_system(flowsheets: list,
                                  feedstock_inputs) -> DryingDominanceSystem:
    """
    Run drying dominance assessment across all flowsheets.
    Attaches DryingDominanceResult to each flowsheet as fs.drying_dominance.
    Returns system-level summary.
    """
    results = {}
    adjustments = {}
    gate_failed = []
    gate_passed = []
    drying_limited = []
    non_viable = 0
    viable = 0

    for fs in flowsheets:
        ddr = run_drying_dominance(fs, feedstock_inputs)
        results[fs.flowsheet_id] = ddr
        fs.drying_dominance = ddr  # Attach to flowsheet

        adjustments[fs.flowsheet_id] = ddr.score_penalty

        if not ddr.can_rank_as_preferred:
            gate_failed.append(fs.name)
            non_viable += 1
        else:
            gate_passed.append(fs.name)
            viable += 1

        if ddr.drying_required and ddr.drying_as_pct_of_feedstock_energy >= 70:
            drying_limited.append(fs.name)

    primary_constraint = len(drying_limited) >= 3

    # Apply score adjustments
    for fs in flowsheets:
        ddr = fs.drying_dominance
        if ddr.score_penalty != 0.0:
            fs.score = max(0.0, fs.score + ddr.score_penalty)

    feed_ds_pct = feedstock_inputs.dewatered_ds_percent
    water_constrained = feed_ds_pct < 20.0
    water_constrained_label = ""
    if water_constrained:
        water_constrained_label = (
            f"WATER-REMOVAL CONSTRAINED — feed DS {feed_ds_pct:.0f}% is below 20%. "
            "All thermal pathways are blocked until mechanical dewatering is installed. "
            "This is a water-removal engineering problem, not a technology selection problem."
        )

    narrative = _system_narrative(gate_failed, gate_passed, drying_limited,
                                   feed_ds_pct,
                                   feedstock_inputs.gross_calorific_value_mj_per_kg_ds,
                                   water_constrained)

    return DryingDominanceSystem(
        results=results,
        score_adjustments=adjustments,
        n_non_viable=non_viable,
        n_viable=viable,
        drying_limited_pathways=drying_limited,
        gate_failed_pathways=gate_failed,
        gate_passed_pathways=gate_passed,
        primary_constraint_is_drying=primary_constraint,
        drying_dominance_narrative=narrative,
        system_water_constrained=water_constrained,
        system_water_constrained_label=water_constrained_label,
        feed_ds_pct=feed_ds_pct,
    )


def _system_narrative(gate_failed, gate_passed, drying_limited, feed_ds, gcv,
                       water_constrained: bool = False) -> str:
    parts = []
    if water_constrained:
        parts.append(
            f"WATER-REMOVAL CONSTRAINED at {feed_ds:.0f}% DS. "
            "All thermal pathways are BLOCKED. "
            "The primary engineering priority is mechanical dewatering — "
            "this is a water-removal problem, not a technology selection problem."
        )
    parts.append(
        f"Feed: {feed_ds:.0f}% DS, GCV {gcv:.1f} MJ/kgDS. "
        f"Drying gate: {len(gate_passed)} pathways PASS, {len(gate_failed)} FAIL."
    )
    if gate_failed:
        parts.append(
            f"Cannot rank as Preferred: {', '.join(gate_failed[:4])}. "
            "These pathways require confirmed external energy source before selection."
        )
    if drying_limited:
        parts.append(
            f"Drying-dominated (drying >70% of feedstock energy): "
            f"{', '.join(drying_limited[:4])}. "
            "Drying is the primary cost and engineering constraint for these pathways."
        )
    if len(gate_failed) >= 5:
        parts.append(
            f"SYSTEM FINDING: Drying is the dominant constraint at {feed_ds:.0f}% DS. "
            "Only wet-pathway (HTC, AD) or baseline options satisfy the drying feasibility gate. "
            "Upstream preconditioning to higher DS% is required to unlock thermal pathways."
        )
    return " ".join(parts)
