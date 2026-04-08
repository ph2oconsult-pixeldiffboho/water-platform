"""
Logistics layer.
Quantifies transport burden, storage requirement, and handling complexity
from dewatered cake properties.

ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class LogisticsInputs:
    haul_distance_km: float = 50.0          # One-way haul distance km
    truck_payload_t: float = 20.0           # Wet payload per truck tonne
    storage_days: float = 7.0              # Required storage buffer days
    disposal_unit_cost_per_t_DS: Optional[float] = None  # $/t DS if known


@dataclass
class LogisticsResult:
    # --- CAKE PROPERTIES ---
    cake_ds_pct: float = 0.0
    cake_wet_mass_kg_d: float = 0.0
    cake_ts_kg_d: float = 0.0
    cake_ts_t_yr: float = 0.0
    cake_volume_m3_d: float = 0.0

    # --- TRANSPORT ---
    truck_loads_per_day: float = 0.0
    truck_loads_per_year: float = 0.0
    truck_payload_t: float = 20.0
    haul_distance_km: float = 50.0
    haul_km_per_year: float = 0.0           # Total truck-km/year (one-way)

    # --- STORAGE ---
    storage_days: float = 7.0
    storage_volume_m3: float = 0.0          # Required storage volume

    # --- COMPLEXITY ---
    handling_complexity: str = ""           # "LOW" | "MODERATE" | "HIGH"
    complexity_drivers: list = field(default_factory=list)

    # --- DISPOSAL COST (bands) ---
    disposal_cost_band: str = ""            # "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH"
    disposal_unit_cost_per_t_DS: Optional[float] = None
    disposal_cost_t_yr: Optional[float] = None   # Total $/year if unit cost provided
    disposal_route: str = ""

    # --- FUTURE BURDEN (at growth horizon) ---
    future_truck_loads_per_day: float = 0.0
    future_cake_ts_t_yr: float = 0.0
    growth_factor: float = 1.0


# ---------------------------------------------------------------------------
# DISPOSAL COST BANDS
# Reference: industry benchmarks — qualitative, no $ figures published
# Bands: relative cost ranking only
# ---------------------------------------------------------------------------

DISPOSAL_COST_BANDS = {
    "LAND_APPLICATION":     ("LOW",       "Land application — lowest cost, highest regulatory exposure."),
    "COMPOSTING":           ("MEDIUM",    "Composting — moderate cost, market-dependent."),
    "LANDFILL":             ("HIGH",      "Landfill — high and rising; regulatory risk increasing."),
    "INCINERATION":         ("VERY_HIGH", "Incineration — very high CAPEX and OPEX; PFAS-preferred."),
    "GASIFICATION":         ("HIGH",      "Gasification — high capital; emerging at utility scale."),
    "PYROLYSIS":            ("HIGH",      "Pyrolysis — high capital; biochar market uncertain."),
    "NONE":                 ("MEDIUM",    "No disposal route selected."),
}


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_logistics(
    cake_ds_pct: float,
    cake_ts_kg_d: float,
    disposal_route: str,
    logistics_inputs: LogisticsInputs,
    growth_factor: float = 1.0,
) -> LogisticsResult:
    """
    Compute full logistics burden from dewatered cake properties.
    """
    # --- CAKE WET MASS ---
    cake_wet_kg_d = cake_ts_kg_d / (cake_ds_pct / 100.0) if cake_ds_pct > 0 else 0.0
    cake_wet_t_d = cake_wet_kg_d / 1000.0
    cake_ts_t_yr = cake_ts_kg_d * 365 / 1000.0
    cake_vol_m3_d = cake_wet_kg_d / 1050.0      # Cake density ~1050 kg/m³

    # --- TRANSPORT ---
    loads_per_day = cake_wet_t_d / logistics_inputs.truck_payload_t
    loads_per_year = loads_per_day * 365
    haul_km_yr = loads_per_year * logistics_inputs.haul_distance_km

    # --- STORAGE ---
    storage_vol = cake_vol_m3_d * logistics_inputs.storage_days

    # --- HANDLING COMPLEXITY ---
    complexity, drivers = _assess_complexity(cake_ds_pct, loads_per_day, disposal_route)

    # --- DISPOSAL COST BAND ---
    route_key = disposal_route.upper().replace(" ", "_")
    band_info = DISPOSAL_COST_BANDS.get(route_key, DISPOSAL_COST_BANDS["NONE"])
    cost_band = band_info[0]
    cost_note = band_info[1]

    # Total cost if unit cost provided
    total_cost = None
    if logistics_inputs.disposal_unit_cost_per_t_DS:
        total_cost = logistics_inputs.disposal_unit_cost_per_t_DS * cake_ts_t_yr

    # --- FUTURE BURDEN ---
    future_wet_t_d = cake_wet_t_d * growth_factor
    future_loads = future_wet_t_d / logistics_inputs.truck_payload_t
    future_ts_t_yr = cake_ts_t_yr * growth_factor

    return LogisticsResult(
        cake_ds_pct=cake_ds_pct,
        cake_wet_mass_kg_d=round(cake_wet_kg_d, 0),
        cake_ts_kg_d=round(cake_ts_kg_d, 0),
        cake_ts_t_yr=round(cake_ts_t_yr, 0),
        cake_volume_m3_d=round(cake_vol_m3_d, 1),
        truck_loads_per_day=round(loads_per_day, 2),
        truck_loads_per_year=round(loads_per_year, 0),
        truck_payload_t=logistics_inputs.truck_payload_t,
        haul_distance_km=logistics_inputs.haul_distance_km,
        haul_km_per_year=round(haul_km_yr, 0),
        storage_days=logistics_inputs.storage_days,
        storage_volume_m3=round(storage_vol, 0),
        handling_complexity=complexity,
        complexity_drivers=drivers,
        disposal_cost_band=cost_band,
        disposal_unit_cost_per_t_DS=logistics_inputs.disposal_unit_cost_per_t_DS,
        disposal_cost_t_yr=round(total_cost, 0) if total_cost else None,
        disposal_route=disposal_route,
        future_truck_loads_per_day=round(future_loads, 2),
        future_cake_ts_t_yr=round(future_ts_t_yr, 0),
        growth_factor=growth_factor,
    )


def _assess_complexity(cake_ds_pct: float, loads_per_day: float,
                        disposal_route: str) -> tuple:
    """Classify handling complexity and identify drivers."""
    drivers = []
    score = 0

    if cake_ds_pct < 18:
        score += 2
        drivers.append(f"Low cake DS ({cake_ds_pct:.0f}%) — difficult to handle, high pump wear")
    elif cake_ds_pct < 25:
        score += 1
        drivers.append(f"Moderate cake DS ({cake_ds_pct:.0f}%) — conveyable but sticky")

    if loads_per_day > 5:
        score += 2
        drivers.append(f"High transport frequency ({loads_per_day:.1f} loads/day)")
    elif loads_per_day > 2:
        score += 1
        drivers.append(f"Moderate transport frequency ({loads_per_day:.1f} loads/day)")

    if disposal_route in ["INCINERATION", "GASIFICATION", "PYROLYSIS"]:
        score += 1
        drivers.append("Thermal route requires consistent feedstock quality")

    if disposal_route == "LAND_APPLICATION":
        score += 1
        drivers.append("Land application — seasonal constraint on offtake")

    if score >= 4:
        return "HIGH", drivers
    elif score >= 2:
        return "MODERATE", drivers
    else:
        return "LOW", drivers
