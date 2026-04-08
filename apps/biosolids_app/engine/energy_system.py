"""
BioPoint V1 — Energy System Integration Layer.
Evaluates all biosolids pathways as integrated energy systems.

For every flowsheet computes:
  1. Biogas production (VS destruction basis)
  2. Methane content and energy yield
  3. CHP electrical + thermal efficiency split
  4. Waste heat available for drying
  5. Drying energy requirement
  6. Net energy balance after drying
  7. Internal energy sufficiency verdict
  8. AD trade-off: GCV reduction vs biogas gain

Flags pathway "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT" when
drying energy exceeds all available internal energy sources.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

CH4_LHV_MJ_M3   = 35.8     # Lower heating value methane MJ/m³
CH4_LHV_KWH_M3  = CH4_LHV_MJ_M3 / 3.6
CH4_DENSITY_KG_M3 = 0.717  # kg/m³ at STP

# Biogas yield reference values (m³/kgVS destroyed) — recalibrated operational data
BIOGAS_YIELD_BY_SLUDGE_TYPE = {
    "raw":         0.60,    # Raw unsettled — not normally digested alone
    "primary":     0.63,    # PS operational mid (315–400 Nm³/tODM ref)
    "secondary":   0.48,    # WAS operational mid (190–240 Nm³/tODM ref)
    "digested":    0.15,    # Already digested — residual only
    "thp_digested":0.10,    # THP + digested — minimal residual
    "ags":         0.48,    # AGS — similar to WAS basis
    "blended":     0.55,    # PS+WAS blend mid
}

CH4_CONTENT_BY_SLUDGE_TYPE = {
    "raw":         0.63,
    "primary":     0.67,
    "secondary":   0.62,
    "digested":    0.60,
    "thp_digested":0.60,
    "ags":         0.62,
    "blended":     0.64,
}

# CHP reference efficiencies (gas engine)
CHP_ELECTRICAL_EFF = 0.35
CHP_THERMAL_EFF    = 0.45   # Jacket + exhaust combined
CHP_RUNTIME_H_D    = 22.0   # Allow 2h/d maintenance

# Incineration steam cycle efficiencies
INCIN_ELECTRICAL_EFF = 0.18   # Condensing steam turbine (lower — steam extracted for drying)
INCIN_THERMAL_EFF    = 0.40   # Steam available for drying from combustion gases

# Pyrolysis / gasification — energy recovery fractions
PYROLYSIS_THERMAL_RECOVERY  = 0.30   # Gross thermal from char + gas combustion
GASIFICATION_THERMAL_RECOVERY = 0.25  # Syngas lower heating value recovery


# ---------------------------------------------------------------------------
# ENERGY SYSTEM DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class EnergySystemResult:
    """
    Full integrated energy system output for one flowsheet.
    All values are per day unless noted.
    """
    pathway_type: str = ""
    pathway_name: str = ""

    # --- FEEDSTOCK ENERGY ---
    feedstock_gcv_mj_per_kg_ds: float = 0.0
    feedstock_energy_mj_d: float = 0.0
    feedstock_energy_kwh_d: float = 0.0

    # --- AD INTERACTION (where AD is present) ---
    ad_present: bool = False
    vs_destruction_fraction: float = 0.0
    vs_destroyed_kg_d: float = 0.0

    # Biogas
    biogas_yield_m3_per_kgVSd: float = 0.0
    biogas_total_m3_d: float = 0.0
    methane_content_pct: float = 0.0
    methane_m3_d: float = 0.0
    biogas_energy_mj_d: float = 0.0
    biogas_energy_kwh_d: float = 0.0

    # CHP
    chp_capacity_kwe: float = 0.0
    chp_electrical_kwh_d: float = 0.0
    chp_thermal_kwh_d: float = 0.0
    chp_total_energy_kwh_d: float = 0.0

    # AD trade-off: does digestion help or hurt the downstream thermal case?
    ad_gcv_reduction_pct: float = 0.0     # How much GCV drops post-digestion (VS removed)
    ad_biogas_gain_kwh_d: float = 0.0     # What biogas CHP recovers
    ad_net_energy_benefit_kwh_d: float = 0.0   # biogas gain - lost calorific value
    ad_trade_off_verdict: str = ""         # "POSITIVE" / "NEUTRAL" / "NEGATIVE"
    ad_trade_off_narrative: str = ""

    # --- DRYING ENERGY SYSTEM ---
    drying_required: bool = False
    drying_target_ds_pct: float = 0.0
    water_removed_t_d: float = 0.0
    drying_energy_gross_kwh_d: float = 0.0    # Before any offset
    drying_energy_net_kwh_d: float = 0.0      # After waste heat offset

    # Available internal energy for drying
    waste_heat_site_kwh_d: float = 0.0       # From site assets (existing CHP etc.)
    chp_heat_available_for_drying_kwh_d: float = 0.0   # From this pathway's CHP
    incin_heat_for_drying_kwh_d: float = 0.0           # From incineration combustion
    total_internal_heat_kwh_d: float = 0.0             # All internal sources combined

    # Drying sufficiency
    drying_covered_by_internal_pct: float = 0.0        # % of drying met internally
    external_drying_energy_kwh_d: float = 0.0          # What must come from outside
    external_energy_kwh_per_t_ds: float = 0.0          # Per tonne DS treated
    drying_self_sufficient: bool = False

    # --- NET ENERGY BALANCE ---
    total_energy_in_kwh_d: float = 0.0       # All recovery: CHP elec + exports
    total_energy_demand_kwh_d: float = 0.0   # Drying net + parasitic + process
    net_energy_kwh_d: float = 0.0
    net_energy_kwh_per_t_ds: float = 0.0

    # --- VERDICT ---
    energy_status: str = ""               # "surplus" / "near-neutral" / "deficit"
    can_drying_be_internally_supported: bool = False
    energy_viability_flag: str = ""       # "VIABLE" / "VIABLE WITH WASTE HEAT" /
                                           # "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT"
    energy_viability_narrative: str = ""

    # Sensitivities
    ds_for_energy_neutrality_pct: Optional[float] = None   # Feed DS% at which balance closes
    notes: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_energy_system(flowsheet, mb) -> EnergySystemResult:
    """
    Full integrated energy system evaluation for one flowsheet.
    Replaces the scattered energy logic in run_energy_balance_v2
    with a single, explicit, traceable calculation chain.
    """
    fs = flowsheet.inputs.feedstock
    assets = flowsheet.inputs.assets
    a = flowsheet.assumptions
    ptype = flowsheet.pathway_type

    ds_tpd = fs.dry_solids_tpd
    vs_tpd = fs.vs_tpd
    gcv = fs.gross_calorific_value_mj_per_kg_ds
    sludge_type = fs.sludge_type

    notes = []

    # -----------------------------------------------------------------------
    # 1. FEEDSTOCK ENERGY
    # -----------------------------------------------------------------------
    feedstock_mj_d  = ds_tpd * 1000 * gcv
    feedstock_kwh_d = feedstock_mj_d / 3.6

    # -----------------------------------------------------------------------
    # 2. AD BIOGAS SYSTEM
    # -----------------------------------------------------------------------
    ad_present = (ptype == "AD" or assets.anaerobic_digestion_present or
                  ptype in ("incineration", "thp_incineration", "pyrolysis", "gasification", "HTC", "HTC_sidestream",
                             "centralised", "decentralised", "drying_only"))
    # For non-AD pathways where AD is an existing upstream asset,
    # the feedstock is already post-AD (sludge_type == "digested")
    # For the AD pathway itself, we calculate biogas production

    vs_destruction = a.mass_reduction_factor if ptype == "AD" else 0.0
    vs_destroyed_kg_d = vs_tpd * vs_destruction * 1000

    # Biogas yield — by sludge type, from recalibrated operational data
    biogas_yield = BIOGAS_YIELD_BY_SLUDGE_TYPE.get(sludge_type,
                   BIOGAS_YIELD_BY_SLUDGE_TYPE["blended"])
    ch4_pct = CH4_CONTENT_BY_SLUDGE_TYPE.get(sludge_type,
              CH4_CONTENT_BY_SLUDGE_TYPE["blended"])

    if ptype == "AD" and vs_destroyed_kg_d > 0:
        biogas_m3_d = vs_destroyed_kg_d * biogas_yield
        ch4_m3_d    = biogas_m3_d * ch4_pct
        biogas_mj_d = ch4_m3_d * CH4_LHV_MJ_M3
        biogas_kwh_d = biogas_mj_d / 3.6

        # CHP sizing and output
        ch4_m3_h = ch4_m3_d / 24.0
        chp_kwe = (ch4_m3_h * CH4_LHV_MJ_M3 * CHP_ELECTRICAL_EFF) / 3.6
        chp_elec_kwh_d  = chp_kwe * CHP_RUNTIME_H_D
        chp_therm_kwh_d = chp_elec_kwh_d * (CHP_THERMAL_EFF / CHP_ELECTRICAL_EFF)

        notes.append(
            f"AD biogas: {vs_destroyed_kg_d:,.0f} kgVS/d destroyed "
            f"× {biogas_yield:.2f} m³/kgVSd = {biogas_m3_d:,.0f} m³/d "
            f"({ch4_pct*100:.0f}% CH₄). "
            f"CHP: {chp_kwe:.0f} kWe electrical, "
            f"{chp_therm_kwh_d:,.0f} kWh/d thermal recovery."
        )
    else:
        biogas_m3_d = 0.0
        ch4_m3_d = 0.0
        biogas_mj_d = 0.0
        biogas_kwh_d = 0.0
        chp_kwe = 0.0
        chp_elec_kwh_d = 0.0
        chp_therm_kwh_d = 0.0

    # -----------------------------------------------------------------------
    # 3. AD TRADE-OFF: GCV REDUCTION vs BIOGAS GAIN
    # -----------------------------------------------------------------------
    if ptype == "AD" and vs_destroyed_kg_d > 0:
        # VS removed reduces downstream GCV proportionally
        vs_frac_removed = vs_destruction * (vs_tpd / ds_tpd)  # fraction of DS that was VS, now gone
        # Post-AD feedstock calorific value per kg remaining DS:
        # GCV of VS ≈ total GCV (ash has ~0 calorific value)
        # After digestion: remaining VS is reduced, so GCV/kgDS falls
        post_ad_vs_frac = (vs_tpd * (1 - vs_destruction)) / (ds_tpd * (1 - vs_destruction * vs_tpd/ds_tpd + 1e-9))
        # Simpler model: GCV scales with VS/TS ratio
        original_vs_ts = vs_tpd / ds_tpd
        post_ad_vs_ts = (vs_tpd * (1 - vs_destruction)) / (ds_tpd - vs_destroyed_kg_d/1000)
        gcv_reduction_pct = (original_vs_ts - post_ad_vs_ts) / original_vs_ts * 100
        gcv_reduction_pct = max(0.0, min(gcv_reduction_pct, 60.0))

        # Lost calorific value in the remaining cake (vs what it would have been pre-AD)
        # Original cake energy = ds_tpd × 1000 × gcv
        # Post-AD remaining DS = ds_tpd - vs_destroyed/1000
        remaining_ds_tpd = ds_tpd - vs_destroyed_kg_d / 1000
        lost_gcv_kwh_d = (ds_tpd - remaining_ds_tpd) * 1000 * gcv / 3.6  # energy in destroyed VS

        # Net benefit: biogas recovered vs calorific value lost
        ad_net_kwh_d = biogas_kwh_d - lost_gcv_kwh_d

        if ad_net_kwh_d > feedstock_kwh_d * 0.05:
            trade_off = "POSITIVE"
            to_narrative = (
                f"AD is energetically beneficial: biogas CHP recovers {biogas_kwh_d:,.0f} kWh/d "
                f"vs {lost_gcv_kwh_d:,.0f} kWh/d calorific value lost in VS destruction "
                f"(net gain {ad_net_kwh_d:+,.0f} kWh/d). "
                f"GCV of cake falls by ~{gcv_reduction_pct:.0f}% post-digestion — "
                f"note this reduces downstream thermal conversion efficiency."
            )
        elif ad_net_kwh_d > -feedstock_kwh_d * 0.05:
            trade_off = "NEUTRAL"
            to_narrative = (
                f"AD trade-off is approximately neutral: biogas gain "
                f"({biogas_kwh_d:,.0f} kWh/d) ≈ calorific value lost "
                f"({lost_gcv_kwh_d:,.0f} kWh/d). "
                f"Post-AD GCV is reduced ~{gcv_reduction_pct:.0f}% — "
                f"thermal conversion efficiency falls accordingly."
            )
        else:
            trade_off = "NEGATIVE"
            to_narrative = (
                f"AD trade-off is NEGATIVE for downstream thermal: calorific value lost "
                f"({lost_gcv_kwh_d:,.0f} kWh/d) exceeds biogas CHP recovery "
                f"({biogas_kwh_d:,.0f} kWh/d). "
                f"Reduced AD or direct-to-thermal may preserve fuel quality for better "
                f"thermal conversion. GCV falls ~{gcv_reduction_pct:.0f}% post-digestion."
            )

        notes.append(to_narrative)
    else:
        gcv_reduction_pct = 0.0
        lost_gcv_kwh_d = 0.0
        ad_net_kwh_d = 0.0
        trade_off = "NEUTRAL"
        to_narrative = "AD not active in this pathway — no biogas/GCV trade-off to evaluate."

    # -----------------------------------------------------------------------
    # 4. DRYING ENERGY SYSTEM
    # -----------------------------------------------------------------------
    drying_required = mb.water_removed_tpd > 0.01
    target_ds = a.target_ds_percent
    water_removed_t_d = mb.water_removed_tpd

    if drying_required:
        specific_energy = a.drying_specific_energy_kwh_per_kg_water
        dryer_eff = a.dryer_efficiency if a.dryer_efficiency > 0 else 0.75
        drying_gross_kwh_d = water_removed_t_d * 1000 * specific_energy / dryer_eff
    else:
        drying_gross_kwh_d = 0.0

    # Internal heat sources available for drying:

    # A) Waste heat from site (existing CHP, process heat)
    waste_heat_site = assets.waste_heat_available_kwh_per_day

    # B) CHP thermal from this pathway (AD pathway)
    chp_heat_for_drying = chp_therm_kwh_d if ptype == "AD" else 0.0

    # C) Incineration combustion heat
    incin_heat = 0.0
    if ptype in ("incineration", "thp_incineration") and drying_required:
        gross_therm = feedstock_kwh_d * INCIN_THERMAL_EFF
        incin_heat = min(gross_therm, drying_gross_kwh_d)

    # D) Pyrolysis/gasification process heat (if autothermal)
    pyro_gas_heat = 0.0
    if ptype in ("pyrolysis", "gasification") and a.autothermal:
        process_heat = feedstock_kwh_d * a.energy_recovery_efficiency
        pyro_gas_heat = min(process_heat, drying_gross_kwh_d)

    # Total internal heat available for drying
    total_internal_heat = min(
        drying_gross_kwh_d,
        waste_heat_site + chp_heat_for_drying + incin_heat + pyro_gas_heat
    )

    # Net external drying energy required
    external_drying_kwh_d = max(0.0, drying_gross_kwh_d - total_internal_heat)
    coverage_pct = (total_internal_heat / drying_gross_kwh_d * 100
                    if drying_gross_kwh_d > 0 else 100.0)
    self_sufficient = external_drying_kwh_d < drying_gross_kwh_d * 0.05

    external_per_tds = external_drying_kwh_d / ds_tpd if ds_tpd > 0 else 0.0

    if drying_required:
        notes.append(
            f"Drying to {target_ds:.0f}% DS: {water_removed_t_d:.0f} t/d water removed. "
            f"Gross drying energy {drying_gross_kwh_d:,.0f} kWh/d. "
            f"Internal heat covers {coverage_pct:.0f}% "
            f"({total_internal_heat:,.0f} kWh/d from: "
            f"site waste heat {waste_heat_site:,.0f} + "
            f"CHP heat {chp_heat_for_drying:,.0f} + "
            f"process heat {incin_heat + pyro_gas_heat:,.0f}). "
            f"External energy required: {external_drying_kwh_d:,.0f} kWh/d "
            f"({external_per_tds:.0f} kWh/tDS)."
        )

    # -----------------------------------------------------------------------
    # 5. NET ENERGY BALANCE
    # -----------------------------------------------------------------------
    parasitic_kwh_d = a.parasitic_power_kwh_per_tds * ds_tpd

    # Energy recovered (usable output — electrical)
    if ptype == "AD":
        energy_in_kwh_d = chp_elec_kwh_d
    elif ptype in ("incineration", "thp_incineration"):
        energy_in_kwh_d = feedstock_kwh_d * INCIN_ELECTRICAL_EFF
    elif ptype in ("pyrolysis", "gasification"):
        gross = feedstock_kwh_d * a.energy_recovery_efficiency
        energy_in_kwh_d = max(0.0, gross - (incin_heat + pyro_gas_heat))
    else:
        energy_in_kwh_d = 0.0

    total_demand_kwh_d = external_drying_kwh_d + parasitic_kwh_d
    net_kwh_d = energy_in_kwh_d - total_demand_kwh_d
    net_per_tds = net_kwh_d / ds_tpd if ds_tpd > 0 else 0.0

    if net_kwh_d > total_demand_kwh_d * 0.10:
        status = "surplus"
    elif net_kwh_d > -total_demand_kwh_d * 0.10:
        status = "near-neutral"
    else:
        status = "deficit"

    # -----------------------------------------------------------------------
    # 6. ENERGY VIABILITY VERDICT
    # -----------------------------------------------------------------------
    can_drying_be_supported = self_sufficient or (coverage_pct >= 80.0)

    if not drying_required:
        flag = "VIABLE"
        flag_narrative = (
            "No thermal pre-drying required — pathway bypasses the drying energy constraint. "
            f"Net energy: {net_kwh_d:+,.0f} kWh/d ({status})."
        )
    elif self_sufficient:
        flag = "VIABLE"
        flag_narrative = (
            f"Internal energy self-sufficient for drying. "
            f"Drying demand ({drying_gross_kwh_d:,.0f} kWh/d) fully covered by "
            f"internal heat ({total_internal_heat:,.0f} kWh/d). "
            f"Net energy: {net_kwh_d:+,.0f} kWh/d ({status})."
        )
    elif coverage_pct >= 50.0:
        flag = "VIABLE WITH WASTE HEAT"
        flag_narrative = (
            f"Partial internal energy coverage ({coverage_pct:.0f}%). "
            f"External energy required: {external_drying_kwh_d:,.0f} kWh/d "
            f"({external_per_tds:.0f} kWh/tDS). "
            f"Pathway viable if waste heat or low-cost energy source is confirmed. "
            f"Net energy: {net_kwh_d:+,.0f} kWh/d ({status})."
        )
    else:
        flag = "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT"
        flag_narrative = (
            f"Drying energy demand ({drying_gross_kwh_d:,.0f} kWh/d) far exceeds "
            f"available internal energy ({total_internal_heat:,.0f} kWh/d — "
            f"{coverage_pct:.0f}% coverage). "
            f"External energy required: {external_drying_kwh_d:,.0f} kWh/d "
            f"({external_per_tds:.0f} kWh/tDS). "
            f"Pathway requires confirmed low-cost heat source or feed DS% increase. "
            f"Net energy: {net_kwh_d:+,.0f} kWh/d ({status})."
        )

    # -----------------------------------------------------------------------
    # 7. DS% FOR ENERGY NEUTRALITY (for drying pathways)
    # -----------------------------------------------------------------------
    ds_for_neutral = None
    if drying_required and not self_sufficient and ptype in ("incineration", "thp_incineration"):
        # At what DS% does incineration thermal cover its own drying?
        # thermal = feedstock_kwh × 0.40
        # drying = water_removed × 1000 × spec_energy / eff
        # water_removed = ds_in/ds_pct_in - ds_in/target_ds
        # We need thermal >= drying
        # feedstock_kwh × 0.40 >= (ds_in/ds_pct_in - ds_in/target_ds) × 1000 × spec / eff
        # Feedstock energy ~ constant (DS doesn't change the energy content per kgDS)
        # Solve for ds_pct_in that closes:
        thermal_avail = feedstock_kwh_d * INCIN_THERMAL_EFF
        spec = a.drying_specific_energy_kwh_per_kg_water
        eff = a.dryer_efficiency if a.dryer_efficiency > 0 else 0.75
        # thermal_avail = (ds_tpd/x - ds_tpd/target_ds) × 1000 × spec / eff
        # ds_tpd/x = thermal_avail × eff / (1000 × spec) + ds_tpd/target_ds
        denominator = (thermal_avail * eff / (1000 * spec) + ds_tpd / (target_ds / 100))
        if denominator > 0:
            ds_for_neutral_frac = ds_tpd / denominator
            ds_for_neutral = round(ds_for_neutral_frac * 100, 1)
            if ds_for_neutral > 50:
                ds_for_neutral = None  # Physically unreachable
            else:
                notes.append(
                    f"Energy neutrality for incineration drying loop: "
                    f"feed DS% must reach ~{ds_for_neutral:.0f}% "
                    f"(current {fs.dewatered_ds_percent:.0f}%) "
                    f"for combustion heat to self-supply the dryer."
                )

    return EnergySystemResult(
        pathway_type=ptype,
        pathway_name=flowsheet.name,

        feedstock_gcv_mj_per_kg_ds=gcv,
        feedstock_energy_mj_d=round(feedstock_mj_d, 0),
        feedstock_energy_kwh_d=round(feedstock_kwh_d, 0),

        ad_present=ad_present,
        vs_destruction_fraction=vs_destruction,
        vs_destroyed_kg_d=round(vs_destroyed_kg_d, 0),

        biogas_yield_m3_per_kgVSd=biogas_yield,
        biogas_total_m3_d=round(biogas_m3_d, 0),
        methane_content_pct=round(ch4_pct * 100, 1),
        methane_m3_d=round(ch4_m3_d, 0),
        biogas_energy_mj_d=round(biogas_mj_d, 0),
        biogas_energy_kwh_d=round(biogas_kwh_d, 0),

        chp_capacity_kwe=round(chp_kwe, 1),
        chp_electrical_kwh_d=round(chp_elec_kwh_d, 0),
        chp_thermal_kwh_d=round(chp_therm_kwh_d, 0),
        chp_total_energy_kwh_d=round(chp_elec_kwh_d + chp_therm_kwh_d, 0),

        ad_gcv_reduction_pct=round(gcv_reduction_pct, 1),
        ad_biogas_gain_kwh_d=round(biogas_kwh_d, 0),
        ad_net_energy_benefit_kwh_d=round(ad_net_kwh_d, 0),
        ad_trade_off_verdict=trade_off,
        ad_trade_off_narrative=to_narrative,

        drying_required=drying_required,
        drying_target_ds_pct=target_ds,
        water_removed_t_d=round(water_removed_t_d, 1),
        drying_energy_gross_kwh_d=round(drying_gross_kwh_d, 0),
        drying_energy_net_kwh_d=round(external_drying_kwh_d, 0),

        waste_heat_site_kwh_d=round(waste_heat_site, 0),
        chp_heat_available_for_drying_kwh_d=round(chp_heat_for_drying, 0),
        incin_heat_for_drying_kwh_d=round(incin_heat, 0),
        total_internal_heat_kwh_d=round(total_internal_heat, 0),

        drying_covered_by_internal_pct=round(coverage_pct, 1),
        external_drying_energy_kwh_d=round(external_drying_kwh_d, 0),
        external_energy_kwh_per_t_ds=round(external_per_tds, 0),
        drying_self_sufficient=self_sufficient,

        total_energy_in_kwh_d=round(energy_in_kwh_d, 0),
        total_energy_demand_kwh_d=round(total_demand_kwh_d, 0),
        net_energy_kwh_d=round(net_kwh_d, 0),
        net_energy_kwh_per_t_ds=round(net_per_tds, 0),

        energy_status=status,
        can_drying_be_internally_supported=can_drying_be_supported,
        energy_viability_flag=flag,
        energy_viability_narrative=flag_narrative,
        ds_for_energy_neutrality_pct=ds_for_neutral,
        notes=notes,
    )
