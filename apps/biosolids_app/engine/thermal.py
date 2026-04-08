"""
Thermal route module.
Incineration / gasification / pyrolysis — mass and energy balance stubs.
Qualitative band outputs (cost, suitability) for v1 decision support.
Detailed process modelling deferred to v2.

References: M&E 5th ed. Ch.15; IEA Bioenergy; USEPA / EA guidance.
ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# THERMAL OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class ThermalResult:
    route: str = ""                      # "INCINERATION"|"GASIFICATION"|"PYROLYSIS"

    # Inputs
    cake_ds_in_pct: float = 0.0
    cake_ts_in_kg_d: float = 0.0
    cake_wet_in_kg_d: float = 0.0

    # Mass outputs
    ash_kg_d: float = 0.0               # Residue / bottom ash
    ash_pct_of_ts: float = 0.0         # Ash yield % of TS in
    syngas_m3_d: float = 0.0           # Gasification / pyrolysis gas
    bio_oil_kg_d: float = 0.0          # Pyrolysis oil
    biochar_kg_d: float = 0.0          # Pyrolysis char

    # Energy
    gross_energy_MJ_d: float = 0.0     # Gross thermal energy recovered
    net_energy_MJ_d: float = 0.0       # Net after parasitic thermal demand
    net_energy_kWh_d: float = 0.0

    # Suitability
    min_ds_pct_required: float = 0.0   # Minimum DS% for autothermal / viable operation
    ds_adequate: bool = False
    ds_gap_pp: float = 0.0             # Shortfall in DS% (0 if adequate)

    # Qualitative bands (v1 — no $ figures)
    capex_band: str = ""               # "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH"
    opex_band: str = ""
    complexity_band: str = ""

    # PFAS destruction
    pfas_destruction_efficiency: str = ""  # "HIGH" | "PARTIAL" | "UNCONFIRMED"

    # Regulatory / pathway notes
    notes: str = ""
    route_viable: bool = True
    viability_reason: str = ""


# ---------------------------------------------------------------------------
# ROUTE MODELS
# ---------------------------------------------------------------------------

def run_incineration(
    cake_ds_in_pct: float,
    cake_ts_kg_d: float,
    pfas_flagged: bool = False,
) -> ThermalResult:
    """
    Multiple hearth or fluidised bed incineration.
    Autothermal above ~22% DS (pre-dried cake typically 90%+ DS).
    Reference: M&E Table 15-7.
    """
    min_ds = 22.0   # Minimum for autothermal operation (FBF with auxiliary fuel assist)
    ds_adequate = cake_ds_in_pct >= min_ds
    ds_gap = max(0.0, min_ds - cake_ds_in_pct)

    cake_wet_in = cake_ts_kg_d / (cake_ds_in_pct / 100.0) if cake_ds_in_pct > 0 else 0.0

    # Ash yield: inorganic fraction = (1 - VS/TS) × TS + partial VS residual
    # Typical: ~25–35% of TS as ash
    ash_pct = 30.0
    ash_kg_d = cake_ts_kg_d * ash_pct / 100.0

    # Energy recovery: ~8–12 MJ/kg TS destroyed (net, after drying duty)
    # At 90% DS pellet: ~10 MJ/kg TS gross
    gross_energy = cake_ts_kg_d * 10.0 * (cake_ds_in_pct / 100.0)   # Scale by DS
    parasitic = gross_energy * 0.25       # ~25% parasitic for FBF + scrubbing
    net_energy = max(0.0, gross_energy - parasitic)
    net_energy_kwh = net_energy / 3.6

    return ThermalResult(
        route="INCINERATION",
        cake_ds_in_pct=cake_ds_in_pct,
        cake_ts_in_kg_d=cake_ts_kg_d,
        cake_wet_in_kg_d=round(cake_wet_in, 1),
        ash_kg_d=round(ash_kg_d, 1),
        ash_pct_of_ts=ash_pct,
        gross_energy_MJ_d=round(gross_energy, 1),
        net_energy_MJ_d=round(net_energy, 1),
        net_energy_kWh_d=round(net_energy_kwh, 1),
        min_ds_pct_required=min_ds,
        ds_adequate=ds_adequate,
        ds_gap_pp=round(ds_gap, 1),
        capex_band="VERY_HIGH",
        opex_band="HIGH",
        complexity_band="HIGH",
        pfas_destruction_efficiency="HIGH",     # >99.99% at >850°C
        notes=(
            "Fluidised bed incineration. Autothermal above 22% DS; "
            "pre-drying to 90%+ DS recommended for energy recovery. "
            "Emission controls (scrubbing, bag filter) required. "
            "PFAS destruction confirmed at operating temperatures."
            + (" ⚠ DS below autothermal threshold — auxiliary fuel required."
               if not ds_adequate else "")
        ),
        route_viable=True,
        viability_reason="Viable — preferred PFAS destruction route." if pfas_flagged
            else "Viable — review vs landfill and gasification on lifecycle cost.",
    )


def run_gasification(
    cake_ds_in_pct: float,
    cake_ts_kg_d: float,
    pfas_flagged: bool = False,
) -> ThermalResult:
    """
    Fixed-bed or fluidised bed gasification.
    Syngas (H₂ + CO + CH₄) → engine or boiler.
    Requires DS > 75% for stable operation.
    Reference: IEA Bioenergy Task 33; WEF MOP 8.
    """
    min_ds = 75.0
    ds_adequate = cake_ds_in_pct >= min_ds
    ds_gap = max(0.0, min_ds - cake_ds_in_pct)

    cake_wet_in = cake_ts_kg_d / (cake_ds_in_pct / 100.0) if cake_ds_in_pct > 0 else 0.0

    # Syngas yield: ~1.0–1.5 Nm³/kg TS at DS > 75%
    syngas_m3_d = cake_ts_kg_d * 1.2 * (cake_ds_in_pct / 100.0)

    # Ash (char residual): ~15–25% TS
    ash_pct = 20.0
    ash_kg_d = cake_ts_kg_d * ash_pct / 100.0

    # Energy: syngas LHV ~4–6 MJ/Nm³; net recovery ~6–8 MJ/kgTS (at high DS)
    gross_energy = cake_ts_kg_d * 7.0 * (cake_ds_in_pct / 100.0)
    parasitic = gross_energy * 0.20
    net_energy = max(0.0, gross_energy - parasitic)
    net_energy_kwh = net_energy / 3.6

    viable = ds_adequate
    viability_reason = (
        "Viable — syngas energy recovery with lower emissions than incineration."
        if ds_adequate else
        f"NOT VIABLE at current DS {cake_ds_in_pct:.0f}%. "
        f"Requires {min_ds:.0f}% DS minimum — thermal pre-drying required."
    )

    return ThermalResult(
        route="GASIFICATION",
        cake_ds_in_pct=cake_ds_in_pct,
        cake_ts_in_kg_d=cake_ts_kg_d,
        cake_wet_in_kg_d=round(cake_wet_in, 1),
        ash_kg_d=round(ash_kg_d, 1),
        ash_pct_of_ts=ash_pct,
        syngas_m3_d=round(syngas_m3_d, 1),
        gross_energy_MJ_d=round(gross_energy, 1),
        net_energy_MJ_d=round(net_energy, 1),
        net_energy_kWh_d=round(net_energy_kwh, 1),
        min_ds_pct_required=min_ds,
        ds_adequate=ds_adequate,
        ds_gap_pp=round(ds_gap, 1),
        capex_band="HIGH",
        opex_band="HIGH",
        complexity_band="HIGH",
        pfas_destruction_efficiency="PARTIAL",   # Depends on temperature; confirm >1000°C
        notes=(
            "Gasification — syngas to engine/boiler. Requires DS > 75%. "
            "PFAS destruction efficiency PFAS-compound dependent — confirm destruction "
            "temperature with vendor. Emerging technology — limited full-scale references "
            "in Australian biosolids context."
        ),
        route_viable=viable,
        viability_reason=viability_reason,
    )


def run_pyrolysis(
    cake_ds_in_pct: float,
    cake_ts_kg_d: float,
    pfas_flagged: bool = False,
) -> ThermalResult:
    """
    Slow / intermediate pyrolysis producing biochar + bio-oil + syngas.
    Requires DS > 70% for viable product quality.
    Reference: IEA Bioenergy; CSIRO biochar work.
    """
    min_ds = 70.0
    ds_adequate = cake_ds_in_pct >= min_ds
    ds_gap = max(0.0, min_ds - cake_ds_in_pct)

    cake_wet_in = cake_ts_kg_d / (cake_ds_in_pct / 100.0) if cake_ds_in_pct > 0 else 0.0

    # Product yields (slow pyrolysis, ~500°C):
    # Biochar: ~30–40% of TS; bio-oil: ~30–40%; syngas: ~20–30%
    biochar_pct = 35.0
    bio_oil_pct = 35.0
    biochar_kg_d = cake_ts_kg_d * biochar_pct / 100.0 * (cake_ds_in_pct / 100.0)
    bio_oil_kg_d = cake_ts_kg_d * bio_oil_pct / 100.0 * (cake_ds_in_pct / 100.0)
    syngas_m3_d = cake_ts_kg_d * 0.5 * (cake_ds_in_pct / 100.0)

    # Ash (in biochar)
    ash_pct = biochar_pct * 0.5   # Roughly half of biochar is ash/inorganic
    ash_kg_d = biochar_kg_d * 0.5

    # Energy: bio-oil LHV ~18–22 MJ/kg; biochar ~22–28 MJ/kg
    gross_energy = (bio_oil_kg_d * 20.0 + biochar_kg_d * 22.0)
    parasitic = gross_energy * 0.30   # Higher parasitic — drying + process heat
    net_energy = max(0.0, gross_energy - parasitic)
    net_energy_kwh = net_energy / 3.6

    viable = ds_adequate
    viability_reason = (
        "Viable — biochar product may qualify as soil amendment (confirm PFAS limits)."
        if ds_adequate and not pfas_flagged else
        ("PFAS-flagged: biochar land application PRECLUDED — review destruction route."
         if pfas_flagged else
         f"NOT VIABLE at current DS {cake_ds_in_pct:.0f}%. "
         f"Requires {min_ds:.0f}% DS minimum.")
    )

    return ThermalResult(
        route="PYROLYSIS",
        cake_ds_in_pct=cake_ds_in_pct,
        cake_ts_in_kg_d=cake_ts_kg_d,
        cake_wet_in_kg_d=round(cake_wet_in, 1),
        ash_kg_d=round(ash_kg_d, 1),
        ash_pct_of_ts=ash_pct,
        syngas_m3_d=round(syngas_m3_d, 1),
        bio_oil_kg_d=round(bio_oil_kg_d, 1),
        biochar_kg_d=round(biochar_kg_d, 1),
        gross_energy_MJ_d=round(gross_energy, 1),
        net_energy_MJ_d=round(net_energy, 1),
        net_energy_kWh_d=round(net_energy_kwh, 1),
        min_ds_pct_required=min_ds,
        ds_adequate=ds_adequate,
        ds_gap_pp=round(ds_gap, 1),
        capex_band="HIGH",
        opex_band="MEDIUM",
        complexity_band="HIGH",
        pfas_destruction_efficiency="UNCONFIRMED",
        notes=(
            "Pyrolysis — biochar / bio-oil / syngas products. "
            "Biochar as soil amendment: confirm heavy metal and PFAS limits under "
            "applicable biosolids guidelines. Technology still emerging at utility scale "
            "in Australia. PFAS destruction efficiency requires confirmation per compound."
        ),
        route_viable=viable,
        viability_reason=viability_reason,
    )


# ---------------------------------------------------------------------------
# DISPATCHER
# ---------------------------------------------------------------------------

def run_thermal_route(
    thermal_route: str,
    cake_ds_in_pct: float,
    cake_ts_kg_d: float,
    pfas_flagged: bool = False,
) -> Optional[ThermalResult]:
    """
    Dispatch to appropriate thermal route model.
    Returns None if thermal_route == "NONE".
    """
    if thermal_route == "NONE" or cake_ts_kg_d <= 0:
        return None
    if thermal_route == "INCINERATION":
        return run_incineration(cake_ds_in_pct, cake_ts_kg_d, pfas_flagged)
    elif thermal_route == "GASIFICATION":
        return run_gasification(cake_ds_in_pct, cake_ts_kg_d, pfas_flagged)
    elif thermal_route == "PYROLYSIS":
        return run_pyrolysis(cake_ds_in_pct, cake_ts_kg_d, pfas_flagged)
    else:
        raise ValueError(f"Unknown thermal_route: {thermal_route}")
