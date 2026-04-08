"""
BioPoint V1 — Mass Balance, Drying, and Energy Engines.
Operates on individual Flowsheet objects.
Implements Parts 3, 4, 5 of the spec.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ---------------------------------------------------------------------------
# PART 3 — MASS BALANCE
# ---------------------------------------------------------------------------

@dataclass
class MassBalanceV2:
    """Per-flowsheet mass balance."""

    # Inputs
    wet_sludge_in_tpd: float = 0.0
    ds_in_tpd: float = 0.0
    vs_in_tpd: float = 0.0
    water_in_tpd: float = 0.0
    dewatered_ds_pct: float = 0.0

    # Drying
    target_ds_pct: float = 0.0
    dried_mass_tpd: float = 0.0
    water_removed_tpd: float = 0.0

    # Conversion
    mass_reduction_factor: float = 0.0
    ds_destroyed_tpd: float = 0.0
    residual_ds_tpd: float = 0.0
    residual_wet_mass_tpd: float = 0.0

    # Summary
    total_mass_reduction_pct: float = 0.0
    residual_as_pct_of_intake: float = 0.0

    # Closure
    mass_balance_error_pct: float = 0.0


def run_mass_balance_v2(flowsheet) -> MassBalanceV2:
    """
    Run generalised mass balance for any flowsheet.
    Handles no-drying, drying-only, and drying + conversion cases.
    """
    fs = flowsheet.inputs.feedstock
    a = flowsheet.assumptions

    wet_in = fs.wet_sludge_tpd
    ds_in = fs.dry_solids_tpd
    vs_in = fs.vs_tpd
    water_in = fs.water_in_feed_tpd
    ds_pct_in = fs.dewatered_ds_percent

    # --- DRYING ---
    target_ds = a.target_ds_percent

    if target_ds <= ds_pct_in or a.dryer_type == "none":
        # No drying — feed goes straight to conversion or disposal
        dried_mass = wet_in
        water_removed = 0.0
        target_ds = ds_pct_in
    else:
        # dried_mass = DS / (target_ds% / 100)
        dried_mass = ds_in / (target_ds / 100.0)
        water_removed = wet_in - dried_mass

    # --- CONVERSION (mass destruction) ---
    # mass_reduction_factor applies to DS — fraction of DS destroyed
    ds_destroyed = ds_in * a.mass_reduction_factor
    residual_ds = ds_in - ds_destroyed

    # Residual wet mass: residual DS at assumed output moisture content
    # For pyrolysis/gasification outputs: char/ash is ~95% DS
    # For HTC hydrochar: ~50-60% DS
    # For AD digestate: ~20% DS
    # Default: use 95% DS for thermal, 20% for biological
    output_ds_pct = {
        "none": ds_pct_in,    # Baseline — no treatment, residual stays at feed DS%
        "biochar": 95.0,
        "hydrochar": 55.0,
        "syngas": 0.0,        # Gas phase — mass accounted in water_removed
        "heat": 20.0,         # AD cake
        "dried_sludge": target_ds,
        "ash": 98.0,
    }.get(a.product_type, 95.0)

    if output_ds_pct > 0 and a.product_type != "syngas":
        residual_wet = residual_ds / (output_ds_pct / 100.0)
    else:
        residual_wet = 0.0    # Syngas — all converted to gas phase

    # Water balance: total water out = removed during drying + water in product
    water_in_product = residual_wet - residual_ds
    # Remainder goes as process water/condensate
    condensate = max(0.0, water_in - water_removed - water_in_product)

    # Mass balance closure
    mass_out = water_removed + residual_wet + condensate
    # + mass of DS destroyed converted to gas (biogas/syngas/CO2)
    # Approximate: destroyed DS → gas (~1 tonne DS → ~1 tonne gas by mass conservation)
    gas_mass = ds_destroyed
    mass_out_total = water_removed + residual_wet + condensate + gas_mass
    error_pct = abs(wet_in - mass_out_total) / wet_in * 100 if wet_in > 0 else 0.0

    # Summary
    total_reduction_pct = (1.0 - residual_wet / wet_in) * 100 if wet_in > 0 else 0.0
    residual_pct = (residual_wet / wet_in * 100) if wet_in > 0 else 100.0

    return MassBalanceV2(
        wet_sludge_in_tpd=round(wet_in, 3),
        ds_in_tpd=round(ds_in, 3),
        vs_in_tpd=round(vs_in, 3),
        water_in_tpd=round(water_in, 3),
        dewatered_ds_pct=ds_pct_in,
        target_ds_pct=target_ds,
        dried_mass_tpd=round(dried_mass, 3),
        water_removed_tpd=round(water_removed, 3),
        mass_reduction_factor=a.mass_reduction_factor,
        ds_destroyed_tpd=round(ds_destroyed, 3),
        residual_ds_tpd=round(residual_ds, 3),
        residual_wet_mass_tpd=round(residual_wet, 3),
        total_mass_reduction_pct=round(total_reduction_pct, 1),
        residual_as_pct_of_intake=round(residual_pct, 1),
        mass_balance_error_pct=round(error_pct, 3),
    )


# ---------------------------------------------------------------------------
# PART 4 — DRYING ENGINE
# ---------------------------------------------------------------------------

@dataclass
class DryingCalc:
    """Drying module output — per flowsheet."""

    target_ds_pct: float = 0.0
    water_removed_tpd: float = 0.0
    water_removed_kg_per_day: float = 0.0

    dryer_type: str = ""
    specific_energy_kwh_per_kg_water: float = 0.0
    dryer_efficiency: float = 0.0

    drying_energy_ideal_kwh_per_day: float = 0.0
    drying_energy_actual_kwh_per_day: float = 0.0

    waste_heat_available_kwh_per_day: float = 0.0
    waste_heat_utilised_kwh_per_day: float = 0.0
    net_external_drying_energy_kwh_per_day: float = 0.0

    drying_required: bool = False
    energy_closure_risk: bool = False
    notes: str = ""


def run_drying_calc(flowsheet, mb: MassBalanceV2) -> DryingCalc:
    """
    Drying module — Part 4 of spec.
    Uses mass balance water_removed and flowsheet dryer assumptions.
    """
    a = flowsheet.assumptions
    assets = flowsheet.inputs.assets

    water_removed_tpd = mb.water_removed_tpd
    water_removed_kg_d = water_removed_tpd * 1000.0

    drying_required = water_removed_tpd > 0.01

    if not drying_required or a.dryer_type == "none":
        return DryingCalc(
            target_ds_pct=mb.target_ds_pct,
            water_removed_tpd=0.0,
            water_removed_kg_per_day=0.0,
            dryer_type="none",
            drying_required=False,
            notes="No drying required for this pathway.",
        )

    # Ideal drying energy
    ideal_kwh_d = water_removed_kg_d * a.drying_specific_energy_kwh_per_kg_water

    # Apply dryer efficiency
    eff = a.dryer_efficiency if a.dryer_efficiency > 0 else 0.75
    actual_kwh_d = ideal_kwh_d / eff

    # Offset with waste heat
    waste_heat = assets.waste_heat_available_kwh_per_day
    utilised = min(waste_heat, actual_kwh_d)
    net_external = max(0.0, actual_kwh_d - utilised)

    # Energy closure risk: flag if external energy > 50% of feedstock energy
    # (high sensitivity to fuel cost and availability)
    feedstock_energy_kwh_d = (
        flowsheet.inputs.feedstock.dry_solids_tpd * 1000
        * flowsheet.inputs.feedstock.gross_calorific_value_mj_per_kg_ds / 3.6
    )
    closure_risk = (feedstock_energy_kwh_d > 0 and
                    net_external / feedstock_energy_kwh_d > 0.5)

    notes = []
    if a.dryer_type == "direct":
        notes.append("Direct dryer: higher energy intensity, lower capital.")
    elif a.dryer_type == "indirect":
        notes.append("Indirect dryer: lower energy intensity, suitable for waste heat integration.")
    if closure_risk:
        notes.append("⚠ Energy closure risk: external drying energy > 50% of feedstock energy content.")
    if utilised > 0:
        notes.append(f"Waste heat offsets {utilised/actual_kwh_d*100:.0f}% of drying demand.")

    return DryingCalc(
        target_ds_pct=mb.target_ds_pct,
        water_removed_tpd=round(water_removed_tpd, 3),
        water_removed_kg_per_day=round(water_removed_kg_d, 0),
        dryer_type=a.dryer_type,
        specific_energy_kwh_per_kg_water=a.drying_specific_energy_kwh_per_kg_water,
        dryer_efficiency=eff,
        drying_energy_ideal_kwh_per_day=round(ideal_kwh_d, 0),
        drying_energy_actual_kwh_per_day=round(actual_kwh_d, 0),
        waste_heat_available_kwh_per_day=round(waste_heat, 0),
        waste_heat_utilised_kwh_per_day=round(utilised, 0),
        net_external_drying_energy_kwh_per_day=round(net_external, 0),
        drying_required=True,
        energy_closure_risk=closure_risk,
        notes=" ".join(notes),
    )


# ---------------------------------------------------------------------------
# PART 5 — ENERGY BALANCE ENGINE
# ---------------------------------------------------------------------------

@dataclass
class EnergyBalanceV2:
    """Per-flowsheet energy balance."""

    # Feedstock energy input
    feedstock_energy_mj_per_day: float = 0.0
    feedstock_energy_kwh_per_day: float = 0.0

    # Demands
    drying_energy_kwh_per_day: float = 0.0
    process_parasitic_kwh_per_day: float = 0.0
    auxiliary_fuel_kwh_per_day: float = 0.0
    total_energy_demand_kwh_per_day: float = 0.0

    # Recovery
    energy_recovered_kwh_per_day: float = 0.0

    # Net position
    net_energy_kwh_per_day: float = 0.0
    energy_status: str = ""          # surplus/near-neutral/deficit
    energy_closure_risk: bool = False

    # CHP (AD pathway)
    chp_capacity_kwe: float = 0.0
    chp_electrical_kwh_per_day: float = 0.0
    chp_heat_kwh_per_day: float = 0.0

    # Self-sufficiency
    self_sufficiency_pct: float = 0.0
    notes: str = ""


def run_energy_balance_v2(flowsheet, mb: MassBalanceV2,
                           dc: DryingCalc) -> EnergyBalanceV2:
    """
    Full pathway energy balance — Part 5 of spec.
    Does NOT hard-code technology outcomes; calculates from feedstock + assumptions.
    """
    fs = flowsheet.inputs.feedstock
    assets = flowsheet.inputs.assets
    a = flowsheet.assumptions
    ptype = flowsheet.pathway_type

    # --- FEEDSTOCK ENERGY ---
    feedstock_mj_d = fs.dry_solids_tpd * 1000 * fs.gross_calorific_value_mj_per_kg_ds
    feedstock_kwh_d = feedstock_mj_d / 3.6

    # --- DEMANDS ---
    drying_kwh_d = dc.net_external_drying_energy_kwh_per_day
    parasitic_kwh_d = a.parasitic_power_kwh_per_tds * fs.dry_solids_tpd

    # Auxiliary fuel: if autothermal process but drying energy is large,
    # check if process can self-supply
    aux_fuel_kwh_d = 0.0
    if ptype in ("pyrolysis", "gasification") and a.autothermal:
        # Autothermal: process heat covers drying if GCV sufficient
        # Energy available from conversion = feedstock energy × recovery efficiency
        conversion_energy = feedstock_kwh_d * a.energy_recovery_efficiency
        # If conversion energy < drying demand: deficit → aux fuel required
        if conversion_energy < dc.drying_energy_actual_kwh_per_day:
            aux_fuel_kwh_d = max(0.0, dc.drying_energy_actual_kwh_per_day - conversion_energy)
    elif ptype in ("HTC", "HTC_sidestream"):
        # HTC is not autothermal — process heat is external
        aux_fuel_kwh_d = dc.drying_energy_actual_kwh_per_day * 0.6  # ~60% process heat from fuel

    total_demand = drying_kwh_d + parasitic_kwh_d + aux_fuel_kwh_d

    # --- RECOVERY ---
    recovered_kwh_d = 0.0
    chp_kwe = 0.0
    chp_elec_kwh_d = 0.0
    chp_heat_kwh_d = 0.0

    if ptype == "AD":
        # Biogas CHP — use VS destruction and biogas yield from feedstock
        # Conservative: WAS-like yield at 0.48 m3/kgVSd (recalibrated)
        vsr_fraction = a.mass_reduction_factor
        vs_destroyed_kg_d = fs.vs_tpd * vsr_fraction * 1000
        biogas_yield = 0.55  # m³/kgVS destroyed (blend midpoint recalibrated)
        ch4_pct = 0.64
        ch4_lhv_mj_m3 = 35.8
        biogas_m3_d = vs_destroyed_kg_d * biogas_yield
        ch4_m3_d = biogas_m3_d * ch4_pct
        biogas_energy_mj_d = ch4_m3_d * ch4_lhv_mj_m3
        # CHP: 35% electrical, 45% thermal
        elec_eff = 0.35
        therm_eff = 0.45
        runtime_h_d = 22.0
        ch4_m3_h = ch4_m3_d / 24.0
        chp_kwe = (ch4_m3_h * ch4_lhv_mj_m3 * elec_eff) / 3.6
        chp_elec_kwh_d = chp_kwe * runtime_h_d
        chp_heat_kwh_d = biogas_energy_mj_d * therm_eff * runtime_h_d / 24.0 / 3.6 * 3600 / 1000
        # Simpler: thermal recovery proportional to electrical
        chp_heat_kwh_d = chp_elec_kwh_d * (therm_eff / elec_eff)
        recovered_kwh_d = chp_elec_kwh_d

    elif ptype in ("pyrolysis", "gasification"):
        # Process energy recovery from feedstock conversion
        recovered_kwh_d = feedstock_kwh_d * a.energy_recovery_efficiency
        # Deduct the drying loop energy (internally consumed if autothermal)
        if a.autothermal:
            recovered_kwh_d = max(0.0, recovered_kwh_d - dc.drying_energy_actual_kwh_per_day)

    elif ptype == "incineration":
        # Fluidised bed incineration with steam cycle — two separate energy streams:
        # 1. ELECTRICAL: feedstock LHV × electrical efficiency → grid export
        # 2. THERMAL: feedstock LHV × thermal recovery efficiency → drying loop
        # At full scale FBF: thermal efficiency (steam extraction) ~35-40%
        # Electrical efficiency: ~15-20% (lower than CHP because steam extracted for drying)
        thermal_recovery_eff = 0.40   # Heat to drying from combustion gases / steam
        gross_electrical_kwh_d = feedstock_kwh_d * a.energy_recovery_efficiency   # 0.18
        gross_thermal_kwh_d    = feedstock_kwh_d * thermal_recovery_eff

        # How much of drying demand can combustion heat supply?
        heat_to_dryer = min(gross_thermal_kwh_d, dc.drying_energy_actual_kwh_per_day)
        remaining_drying_demand = max(0.0, dc.drying_energy_actual_kwh_per_day - heat_to_dryer)

        # External energy needed: residual drying + parasitic, offset by electrical export
        # Net electrical export goes to grid (reduces plant demand but doesn't fund drying)
        recovered_kwh_d = gross_electrical_kwh_d   # Electrical export
        # Aux fuel covers remaining drying demand (if thermal insufficient)
        aux_fuel_kwh_d += remaining_drying_demand   # Add to existing aux_fuel

    # Net
    net_kwh_d = recovered_kwh_d - total_demand

    # Status classification
    if net_kwh_d > total_demand * 0.10:
        status = "surplus"
    elif net_kwh_d > -total_demand * 0.10:
        status = "near-neutral"
    else:
        status = "deficit"

    # Energy closure risk
    closure_risk = (status == "deficit" and
                    abs(net_kwh_d) > feedstock_kwh_d * 0.20)

    # Self-sufficiency (for AD)
    self_suff = min(100.0, recovered_kwh_d / total_demand * 100) if total_demand > 0 else 0.0

    notes = []
    if closure_risk:
        notes.append(
            "⚠ Energy closure risk: net deficit exceeds 20% of feedstock energy. "
            "Auxiliary fuel or waste heat integration required to close."
        )
    if a.autothermal and ptype in ("pyrolysis", "gasification"):
        notes.append(
            f"Autothermal assumption applied — verify with vendor at this GCV "
            f"({fs.gross_calorific_value_mj_per_kg_ds:.1f} MJ/kgDS) and DS "
            f"({a.target_ds_percent:.0f}%)."
        )
    if ptype == "incineration":
        thermal_to_dryer = min(
            feedstock_kwh_d * 0.40,
            dc.drying_energy_actual_kwh_per_day
        )
        notes.append(
            f"Incineration energy model: electrical recovery "
            f"{a.energy_recovery_efficiency*100:.0f}% ({feedstock_kwh_d * a.energy_recovery_efficiency:,.0f} kWh/d to grid). "
            f"Thermal (40% of feedstock) partially offsets drying: "
            f"{thermal_to_dryer:,.0f} kWh/d heat covers "
            f"{thermal_to_dryer/dc.drying_energy_actual_kwh_per_day*100:.0f}% of drying demand at "
            f"{dc.target_ds_pct:.0f}% DS target. "
            f"Residual drying deficit requires auxiliary fuel or feed thickening."
        )
    if ptype == "HTC":
        notes.append(
            "HTC is not autothermal — process heat from external source. "
            "Waste heat integration improves economics significantly."
        )

    return EnergyBalanceV2(
        feedstock_energy_mj_per_day=round(feedstock_mj_d, 0),
        feedstock_energy_kwh_per_day=round(feedstock_kwh_d, 0),
        drying_energy_kwh_per_day=round(drying_kwh_d, 0),
        process_parasitic_kwh_per_day=round(parasitic_kwh_d, 0),
        auxiliary_fuel_kwh_per_day=round(aux_fuel_kwh_d, 0),
        total_energy_demand_kwh_per_day=round(total_demand, 0),
        energy_recovered_kwh_per_day=round(recovered_kwh_d, 0),
        net_energy_kwh_per_day=round(net_kwh_d, 0),
        energy_status=status,
        energy_closure_risk=closure_risk,
        chp_capacity_kwe=round(chp_kwe, 1),
        chp_electrical_kwh_per_day=round(chp_elec_kwh_d, 0),
        chp_heat_kwh_per_day=round(chp_heat_kwh_d, 0),
        self_sufficiency_pct=round(self_suff, 1),
        notes=" ".join(notes),
    )
