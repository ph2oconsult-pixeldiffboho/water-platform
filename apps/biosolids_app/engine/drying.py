"""
Drying module.
Models solar drying and thermal drying as:
  - standalone endpoints (final product)
  - staging steps before thermal routes

Solar drying: climate-zone dependent, area-based, passive.
Thermal drying: energy-intensive, produces high-DS cake for thermal routes.

References: M&E 5th ed. Sections 14-9, 14-10; WEF MOP 8.
ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional
from data.feedstock_defaults import CLIMATE_ZONES


# ---------------------------------------------------------------------------
# DRYING OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class DryingResult:
    drying_route: str = "NONE"           # "SOLAR" | "THERMAL" | "NONE"
    role: str = "ENDPOINT"               # "ENDPOINT" | "STAGING"

    # Input cake characteristics
    cake_ds_in_pct: float = 0.0          # DS% entering dryer
    cake_mass_in_kg_d: float = 0.0       # Wet mass kg/d entering
    cake_ts_in_kg_d: float = 0.0         # TS kg/d entering

    # Output cake characteristics
    cake_ds_out_pct: float = 0.0         # DS% leaving dryer
    cake_mass_out_kg_d: float = 0.0      # Wet mass kg/d leaving
    cake_volume_out_m3_d: float = 0.0    # Volume m³/d

    # Water removal
    water_evaporated_kg_d: float = 0.0

    # Solar drying specifics
    drying_area_m2: float = 0.0          # Greenhouse / open bed area required
    solar_drying_factor: float = 1.0     # Climate zone modifier
    drying_time_days: float = 0.0        # Indicative days to target DS

    # Thermal drying specifics
    thermal_energy_demand_MJ_d: float = 0.0
    thermal_energy_demand_kWh_d: float = 0.0
    thermal_energy_source: str = ""      # "CHP_EXHAUST" | "AUXILIARY" | "MIXED"
    chp_heat_offset_MJ_d: float = 0.0   # How much CHP heat covers dryer demand
    auxiliary_heat_MJ_d: float = 0.0    # Shortfall requiring external source

    # Product classification
    product_class: str = ""             # "GRANULE" | "PELLET" | "CAKE" | "DRY_SOLID"
    suitable_for_thermal_route: bool = False
    notes: str = ""


# ---------------------------------------------------------------------------
# SOLAR DRYING
# ---------------------------------------------------------------------------

def run_solar_drying(
    cake_ds_in_pct: float,
    cake_ts_kg_d: float,
    climate_zone: str,
    target_ds_pct: float = 65.0,        # Typical solar drying target
    role: str = "ENDPOINT",
    chp_surplus_heat_MJ_d: float = 0.0,
) -> DryingResult:
    """
    Solar drying model.
    Climate zone adjusts achievable DS and area requirement.
    Reference: M&E Table 14-17 — solar drying bed loading rates.
    """
    climate = CLIMATE_ZONES.get(climate_zone, CLIMATE_ZONES["TEMPERATE"])
    solar_factor = climate["solar_drying_factor"]

    # Achievable DS — climate limited
    # Tropical: 65–75%; Temperate: 45–55%; Cool temperate: 30–40%
    achievable_ds = {
        "TROPICAL":       75.0,
        "SUBTROPICAL":    65.0,
        "TEMPERATE":      55.0,
        "COOL_TEMPERATE": 38.0,
    }.get(climate_zone, 55.0)

    target_ds_actual = min(target_ds_pct, achievable_ds)

    # Wet mass in
    cake_wet_in = cake_ts_kg_d / (cake_ds_in_pct / 100.0) if cake_ds_in_pct > 0 else 0.0

    # Water to evaporate: mass_in × (1 - DS_in%) - mass_ts × (1 - DS_out%)/DS_out%
    # = cake_ts × (1/DS_in - 1/DS_out)
    if target_ds_actual > cake_ds_in_pct:
        water_evap = cake_ts_kg_d * (
            100.0 / cake_ds_in_pct - 100.0 / target_ds_actual
        )
    else:
        water_evap = 0.0
        target_ds_actual = cake_ds_in_pct

    cake_wet_out = cake_wet_in - water_evap
    cake_vol_out = cake_wet_out / 950.0  # Dry cake density ~950 kg/m³

    # Solar drying area
    # Reference loading rate: ~75 kg water evaporated / m²·year in temperate
    # = 75/365 = 0.205 kg/m²·d, adjusted for climate
    base_evap_rate_kg_m2_d = 0.205 * solar_factor   # kg water / m² / day
    drying_area = water_evap / base_evap_rate_kg_m2_d if base_evap_rate_kg_m2_d > 0 else 0.0

    # Indicative drying time (bed depth ~200mm, turn frequency)
    drying_days = {
        "TROPICAL": 7, "SUBTROPICAL": 10,
        "TEMPERATE": 21, "COOL_TEMPERATE": 45,
    }.get(climate_zone, 21)

    # Product classification
    if target_ds_actual >= 70:
        product = "DRY_SOLID"
        thermal_suitable = True
    elif target_ds_actual >= 55:
        product = "GRANULE"
        thermal_suitable = True
    elif target_ds_actual >= 40:
        product = "CAKE"
        thermal_suitable = False
    else:
        product = "CAKE"
        thermal_suitable = False

    note = ""
    if target_ds_actual < target_ds_pct:
        note = (
            f"Target DS {target_ds_pct:.0f}% not achievable in {climate_zone} climate. "
            f"Achievable DS capped at {achievable_ds:.0f}%."
        )

    return DryingResult(
        drying_route="SOLAR",
        role=role,
        cake_ds_in_pct=cake_ds_in_pct,
        cake_mass_in_kg_d=round(cake_wet_in, 1),
        cake_ts_in_kg_d=round(cake_ts_kg_d, 1),
        cake_ds_out_pct=round(target_ds_actual, 1),
        cake_mass_out_kg_d=round(cake_wet_out, 1),
        cake_volume_out_m3_d=round(cake_vol_out, 2),
        water_evaporated_kg_d=round(water_evap, 1),
        drying_area_m2=round(drying_area, 0),
        solar_drying_factor=solar_factor,
        drying_time_days=drying_days,
        thermal_energy_demand_MJ_d=0.0,
        thermal_energy_demand_kWh_d=0.0,
        thermal_energy_source="PASSIVE",
        product_class=product,
        suitable_for_thermal_route=thermal_suitable,
        notes=note,
    )


# ---------------------------------------------------------------------------
# THERMAL DRYING
# ---------------------------------------------------------------------------

def run_thermal_drying(
    cake_ds_in_pct: float,
    cake_ts_kg_d: float,
    target_ds_pct: float = 90.0,        # Pelletisation / incineration target
    role: str = "ENDPOINT",
    chp_surplus_heat_MJ_d: float = 0.0,
    dryer_type: str = "INDIRECT",       # "INDIRECT" | "DIRECT"
) -> DryingResult:
    """
    Thermal drying model.
    Target DS typically 90%+ for granules/pellets.
    Reference: M&E Table 14-18; specific evaporation energy ~900–1100 kJ/kg water.
    """
    target_ds_pct = max(target_ds_pct, cake_ds_in_pct)

    # Wet mass in
    cake_wet_in = cake_ts_kg_d / (cake_ds_in_pct / 100.0) if cake_ds_in_pct > 0 else 0.0

    # Water to evaporate
    water_evap = cake_ts_kg_d * (100.0 / cake_ds_in_pct - 100.0 / target_ds_pct)
    water_evap = max(water_evap, 0.0)

    cake_wet_out = cake_wet_in - water_evap
    cake_vol_out = cake_wet_out / 600.0  # Pellet/granule density ~600 kg/m³

    # Energy demand
    # Indirect dryer (drum/disc): ~900–1000 kJ/kg water evaporated
    # Direct dryer (rotary): ~1100–1300 kJ/kg water evaporated (includes exhaust losses)
    specific_energy_kJ_kg = 950.0 if dryer_type == "INDIRECT" else 1200.0
    thermal_energy_MJ_d = water_evap * specific_energy_kJ_kg / 1000.0
    thermal_energy_kWh_d = thermal_energy_MJ_d / 3.6

    # CHP heat offset
    chp_offset = min(chp_surplus_heat_MJ_d, thermal_energy_MJ_d)
    aux_heat = max(0.0, thermal_energy_MJ_d - chp_offset)

    if chp_offset >= thermal_energy_MJ_d:
        source = "CHP_EXHAUST"
    elif chp_offset > 0:
        source = "MIXED"
    else:
        source = "AUXILIARY"

    # Product
    if target_ds_pct >= 90:
        product = "PELLET"
        thermal_suitable = True
    elif target_ds_pct >= 75:
        product = "GRANULE"
        thermal_suitable = True
    else:
        product = "CAKE"
        thermal_suitable = False

    return DryingResult(
        drying_route="THERMAL",
        role=role,
        cake_ds_in_pct=cake_ds_in_pct,
        cake_mass_in_kg_d=round(cake_wet_in, 1),
        cake_ts_in_kg_d=round(cake_ts_kg_d, 1),
        cake_ds_out_pct=round(target_ds_pct, 1),
        cake_mass_out_kg_d=round(cake_wet_out, 1),
        cake_volume_out_m3_d=round(cake_vol_out, 2),
        water_evaporated_kg_d=round(water_evap, 1),
        thermal_energy_demand_MJ_d=round(thermal_energy_MJ_d, 1),
        thermal_energy_demand_kWh_d=round(thermal_energy_kWh_d, 1),
        thermal_energy_source=source,
        chp_heat_offset_MJ_d=round(chp_offset, 1),
        auxiliary_heat_MJ_d=round(aux_heat, 1),
        product_class=product,
        suitable_for_thermal_route=thermal_suitable,
        notes=f"{dryer_type.title()} dryer. Specific energy: {specific_energy_kJ_kg:.0f} kJ/kg water.",
    )


# ---------------------------------------------------------------------------
# DISPATCHER
# ---------------------------------------------------------------------------

def run_drying(
    drying_route: str,
    cake_ds_in_pct: float,
    cake_ts_kg_d: float,
    climate_zone: str = "TEMPERATE",
    target_ds_pct: Optional[float] = None,
    role: str = "ENDPOINT",
    chp_surplus_heat_MJ_d: float = 0.0,
) -> Optional[DryingResult]:
    """
    Dispatch to solar or thermal drying model.
    Returns None if drying_route == "NONE".
    """
    if drying_route == "NONE" or cake_ts_kg_d <= 0:
        return None

    if drying_route == "SOLAR":
        target = target_ds_pct or 65.0
        return run_solar_drying(
            cake_ds_in_pct, cake_ts_kg_d, climate_zone,
            target_ds_pct=target, role=role,
            chp_surplus_heat_MJ_d=chp_surplus_heat_MJ_d,
        )
    elif drying_route == "THERMAL":
        target = target_ds_pct or 90.0
        return run_thermal_drying(
            cake_ds_in_pct, cake_ts_kg_d,
            target_ds_pct=target, role=role,
            chp_surplus_heat_MJ_d=chp_surplus_heat_MJ_d,
        )
    else:
        raise ValueError(f"Unknown drying_route: {drying_route}")
