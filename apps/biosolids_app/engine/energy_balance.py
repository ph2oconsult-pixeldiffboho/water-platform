"""
Energy balance engine.
Auto-sizes CHP to biogas supply. Calculates gross/net electrical output,
thermal recovery (jacket + exhaust), and net energy position vs plant demand.

ph2o Consulting — BioPoint v1
"""

import math
from engine.dataclasses import BioPointInputs, FeedstockProfile, MADOutputs, EnergyBalance
from data.feedstock_defaults import CHP_DEFAULTS


def run_energy_balance(inputs: BioPointInputs, profile: FeedstockProfile,
                       mad: MADOutputs) -> EnergyBalance:
    """
    Auto-size CHP and compute full energy balance.
    Plant demand estimated from VS loading (simplified parasitic model).
    """
    chp_cfg = inputs.chp
    ref = CHP_DEFAULTS

    # --- BIOGAS ENERGY ---
    biogas_m3_d = mad.biogas_total_m3_d
    methane_m3_d = mad.methane_total_m3_d
    ch4_lhv = ref["methane_lhv_MJ_m3"]
    biogas_energy_MJ_d = methane_m3_d * ch4_lhv
    biogas_energy_kWh_d = biogas_energy_MJ_d / 3.6

    # --- CHP AUTO-SIZING ---
    # Size CHP to consume available biogas over runtime hours
    runtime_h_d = 22.0                                    # 2h/d maintenance allowance
    # Instantaneous biogas flow rate available for CHP
    biogas_m3_h = biogas_m3_d / 24.0
    methane_m3_h = methane_m3_d / 24.0
    # Electrical output = methane_flow × LHV × electrical_efficiency / 3.6
    # kW = (m³/h × MJ/m³ × eff) / 3.6
    chp_kWe = (methane_m3_h * ch4_lhv * chp_cfg.electrical_efficiency) / 3.6

    # --- ELECTRICAL OUTPUTS ---
    gross_elec_kWh_d = chp_kWe * runtime_h_d
    parasitic_chp_kWh_d = gross_elec_kWh_d * chp_cfg.parasitic_fraction
    net_elec_kWh_d = gross_elec_kWh_d - parasitic_chp_kWh_d

    # --- THERMAL OUTPUTS ---
    # Thermal from biogas energy (proportional to runtime)
    biogas_energy_runtime_kWh_d = biogas_energy_kWh_d * (runtime_h_d / 24.0)
    jacket_kWh_d = biogas_energy_runtime_kWh_d * chp_cfg.thermal_efficiency_jacket
    exhaust_kWh_d = biogas_energy_runtime_kWh_d * chp_cfg.thermal_efficiency_exhaust
    total_heat_kWh_d = jacket_kWh_d + exhaust_kWh_d

    # --- PLANT PARASITIC LOAD ESTIMATION ---
    # Simplified: digester mixing + dewatering + ancillaries
    # Based on VS loading — conservative estimates for medium-sized plant
    vs_t_d = profile.vs_load_kg_d / 1000.0               # tVS/d
    ts_t_d = profile.ts_load_kg_d / 1000.0               # tTS/d

    digester_mixing_kWh_d = _mixing_energy(mad)
    dewatering_kWh_d = ts_t_d * 35.0                     # ~35 kWh/tTS (centrifuge reference)
    ancillaries_kWh_d = net_elec_kWh_d * 0.05            # Pumping, lighting, SCADA ~5%
    total_parasitic_kWh_d = digester_mixing_kWh_d + dewatering_kWh_d + ancillaries_kWh_d

    # Note: aeration excluded — this is solids-side only
    # Full plant aeration demand is a WaterPoint output (bridge)
    estimated_plant_demand_kWh_d = total_parasitic_kWh_d

    # --- NET POSITION ---
    net_export_kWh_d = net_elec_kWh_d - estimated_plant_demand_kWh_d
    self_sufficiency = (
        min(net_elec_kWh_d / estimated_plant_demand_kWh_d * 100.0, 100.0)
        if estimated_plant_demand_kWh_d > 0 else 100.0
    )
    self_sufficient = net_export_kWh_d >= 0.0

    return EnergyBalance(
        biogas_total_m3_d=round(biogas_m3_d, 1),
        methane_total_m3_d=round(methane_m3_d, 1),
        biogas_energy_MJ_d=round(biogas_energy_MJ_d, 1),
        biogas_energy_kWh_d=round(biogas_energy_kWh_d, 1),
        chp_capacity_kWe=round(chp_kWe, 1),
        chp_runtime_h_d=runtime_h_d,
        gross_electrical_kWh_d=round(gross_elec_kWh_d, 1),
        parasitic_kWh_d=round(parasitic_chp_kWh_d, 1),
        net_electrical_kWh_d=round(net_elec_kWh_d, 1),
        jacket_heat_kWh_d=round(jacket_kWh_d, 1),
        exhaust_heat_kWh_d=round(exhaust_kWh_d, 1),
        total_heat_kWh_d=round(total_heat_kWh_d, 1),
        estimated_plant_demand_kWh_d=round(estimated_plant_demand_kWh_d, 1),
        digester_mixing_kWh_d=round(digester_mixing_kWh_d, 1),
        dewatering_kWh_d=round(dewatering_kWh_d, 1),
        total_parasitic_process_kWh_d=round(total_parasitic_kWh_d, 1),
        net_electrical_export_kWh_d=round(net_export_kWh_d, 1),
        electrical_self_sufficiency_pct=round(self_sufficiency, 1),
        energy_self_sufficient=self_sufficient,
        electrical_efficiency=chp_cfg.electrical_efficiency,
        thermal_efficiency=chp_cfg.thermal_efficiency_jacket + chp_cfg.thermal_efficiency_exhaust,
        overall_efficiency=chp_cfg.electrical_efficiency
            + chp_cfg.thermal_efficiency_jacket
            + chp_cfg.thermal_efficiency_exhaust,
    )


# ---------------------------------------------------------------------------
# DIGESTER MIXING ENERGY
# ---------------------------------------------------------------------------

def _mixing_energy(mad: MADOutputs) -> float:
    """
    Estimate digester mixing energy.
    Gas mixing reference: ~5–8 W/m³ digester volume.
    Digester volume back-calculated from HRT and flow.
    """
    # We don't carry digester volume here — use biogas proxy
    # ~6 W/m³ × volume; approximate volume from biogas production
    # Use simplified 4 kWh/MJ biogas as proxy (industry heuristic)
    biogas_proxy_kWh_d = mad.biogas_total_m3_d * 0.15   # ~0.15 kWh/m³ biogas for mixing
    return max(biogas_proxy_kWh_d, 20.0)                 # Floor 20 kWh/d
