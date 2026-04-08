"""
Heat balance engine.
Calculates digester heat demand (feed heating + cover/wall/floor losses)
vs CHP thermal recovery (jacket water + exhaust gas).
Auto-sizes digester geometry from VS loading.
Applies climate zone adjustments.

ph2o Consulting — BioPoint v1
"""

import math
from engine.dataclasses import (
    BioPointInputs, FeedstockProfile, MADOutputs, EnergyBalance, HeatBalance
)
from data.feedstock_defaults import (
    DIGESTER_HEAT_LOSS, DIGESTER_GEOMETRY, CLIMATE_ZONES, CHP_DEFAULTS
)


def run_heat_balance(inputs: BioPointInputs, profile: FeedstockProfile,
                     mad: MADOutputs, energy: EnergyBalance,
                     thp_steam_MJ_d: float = 0.0) -> HeatBalance:
    """
    Full digester heat balance.
    energy: EnergyBalance must be pre-computed (provides CHP heat outputs).
    """
    climate = CLIMATE_ZONES[inputs.context.climate_zone]
    ambient_C = climate["ambient_C"]
    ground_C = climate["ground_C"]
    dig_temp_C = inputs.stabilisation.digester_temp_C

    # --- DIGESTER GEOMETRY (auto-sized from VS load) ---
    geom = _auto_size_digester(mad.hrt_days, profile.vs_load_kg_d)
    wall_area = geom["wall_area_m2"]
    floor_area = geom["floor_area_m2"]
    cover_area = geom["cover_area_m2"]
    vol = geom["volume_m3"]

    # --- HEAT LOSS ---
    dl = DIGESTER_HEAT_LOSS
    seconds_per_day = 86400.0

    # W/m²·K → MJ/d:  Q = U × A × ΔT × 86400 / 1e6
    wall_loss = dl["wall_U"] * wall_area * (dig_temp_C - ambient_C) * seconds_per_day / 1e6
    floor_loss = dl["floor_U"] * floor_area * (dig_temp_C - ground_C) * seconds_per_day / 1e6
    cover_loss = dl["cover_U"] * cover_area * (dig_temp_C - ambient_C) * seconds_per_day / 1e6

    # --- FEED HEATING ---
    # Q = m_dot × Cp × ΔT
    # Feed volume m³/d → mass kg/d → MJ/d
    feed_mass_kg_d = profile.sludge_volume_m3_d * profile.density_kg_m3
    cp_kJ_kgK = 4.18
    delta_T = dig_temp_C - ambient_C                      # Conservative: feed at ambient
    feed_heat_MJ_d = feed_mass_kg_d * cp_kJ_kgK * delta_T / 1000.0  # kJ → MJ

    # --- TOTAL HEAT DEMAND ---
    total_demand = feed_heat_MJ_d + wall_loss + floor_loss + cover_loss + thp_steam_MJ_d

    # --- CHP HEAT SUPPLY (from pre-computed energy balance) ---
    jacket_MJ_d = energy.jacket_heat_kWh_d * 3.6
    exhaust_MJ_d = energy.exhaust_heat_kWh_d * 3.6
    total_heat_recovered = jacket_MJ_d + exhaust_MJ_d

    # --- BALANCE ---
    surplus_deficit = total_heat_recovered - total_demand
    self_sufficient = surplus_deficit >= 0.0
    aux_heat = max(0.0, -surplus_deficit)

    return HeatBalance(
        feed_heating_MJ_d=round(feed_heat_MJ_d, 1),
        digester_wall_loss_MJ_d=round(wall_loss, 1),
        digester_floor_loss_MJ_d=round(floor_loss, 1),
        digester_cover_loss_MJ_d=round(cover_loss, 1),
        thp_steam_demand_MJ_d=round(thp_steam_MJ_d, 1),
        total_heat_demand_MJ_d=round(total_demand, 1),
        chp_jacket_heat_MJ_d=round(jacket_MJ_d, 1),
        chp_exhaust_heat_MJ_d=round(exhaust_MJ_d, 1),
        total_heat_recovered_MJ_d=round(total_heat_recovered, 1),
        heat_surplus_deficit_MJ_d=round(surplus_deficit, 1),
        heat_self_sufficient=self_sufficient,
        auxiliary_heat_required_MJ_d=round(aux_heat, 1),
        digester_volume_m3=round(vol, 1),
        digester_diameter_m=round(geom["diameter_m"], 2),
        digester_height_m=round(geom["height_m"], 2),
        wall_area_m2=round(wall_area, 1),
        floor_area_m2=round(floor_area, 1),
        cover_area_m2=round(cover_area, 1),
    )


# ---------------------------------------------------------------------------
# DIGESTER AUTO-SIZING
# ---------------------------------------------------------------------------

def _auto_size_digester(hrt_days: float, vs_load_kg_d: float) -> dict:
    """
    Auto-size digester volume from HRT × VS loading.
    Geometry: cylindrical, H/D ratio from defaults.
    """
    g = DIGESTER_GEOMETRY
    h_d = g["height_diameter_ratio"]

    # Volume: V = HRT × flow_rate
    # Use VS loading as proxy for active volume demand
    # At 30d HRT, ~33 kgVS/m³/d loading rate
    loading_rate_kgVS_m3_d = 1000.0 / (hrt_days * g["volume_per_kgVSd_m3"] * 1000.0 / 30.0)
    # Simpler: V = VS_load / loading_rate; loading_rate scales with HRT
    base_loading = 33.0  # kgVS/m³·d at 30d HRT
    loading_rate = base_loading * (30.0 / hrt_days)     # Longer HRT → lower loading
    vol = vs_load_kg_d / loading_rate if loading_rate > 0 else 0.0
    vol += vol * 0.10                                    # 10% freeboard allowance

    # Geometry from volume
    # V = π/4 × D² × H;  H = h_d × D → V = π/4 × D² × h_d × D = π/4 × h_d × D³
    if vol > 0:
        diam = (vol / (math.pi / 4.0 * h_d)) ** (1.0 / 3.0)
    else:
        diam = 0.0
    height = h_d * diam

    wall_area = math.pi * diam * height
    floor_area = math.pi / 4.0 * diam ** 2
    cover_area = floor_area

    return {
        "volume_m3": vol,
        "diameter_m": diam,
        "height_m": height,
        "wall_area_m2": wall_area,
        "floor_area_m2": floor_area,
        "cover_area_m2": cover_area,
    }
