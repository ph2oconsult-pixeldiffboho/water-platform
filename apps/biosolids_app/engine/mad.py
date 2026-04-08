"""
Mesophilic anaerobic digestion (MAD) performance model.
HRT-dependent VSR via interpolation from M&E Table 13-20 reference table.
Biogas yield and methane content are blend-weighted from feedstock profile.

ph2o Consulting — BioPoint v1
"""

import math
from engine.dataclasses import BioPointInputs, FeedstockProfile, MADOutputs
from data.feedstock_defaults import HRT_VSR_TABLE, CHP_DEFAULTS


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def run_mad(inputs: BioPointInputs, profile: FeedstockProfile,
            thp_applied: bool = False,
            effective_hrt: float = None) -> MADOutputs:
    """
    Run the MAD model for given inputs and feedstock profile.

    Parameters
    ----------
    inputs        : BioPointInputs
    profile       : FeedstockProfile — characterised feedstock
    thp_applied   : bool — if True, uses THP-adjusted HRT and biogas uplift
    effective_hrt : float — override HRT (days); used by THP module
    """
    stab = inputs.stabilisation
    hrt = effective_hrt if effective_hrt is not None else stab.hrt_days

    # --- HRT-dependent VSR ---
    vsr_pct = _interpolate_vsr(hrt, profile.blend_ratio_ps)

    # --- VS mass flows ---
    vs_in = profile.vs_load_kg_d
    vs_destroyed = vs_in * (vsr_pct / 100.0)
    vs_effluent = vs_in - vs_destroyed

    # --- Biogas ---
    biogas_yield = profile.biogas_yield_m3_per_kgVSd     # m³/kgVS destroyed
    biogas_total = vs_destroyed * biogas_yield            # m³/d
    methane_pct = profile.methane_content_pct
    methane_total = biogas_total * (methane_pct / 100.0)  # m³ CH₄/d

    # Biogas energy (LHV basis)
    ch4_lhv = CHP_DEFAULTS["methane_lhv_MJ_m3"]
    biogas_energy_MJ_d = methane_total * ch4_lhv

    # --- Digested solids ---
    fsi_in = profile.ts_load_kg_d * (1.0 - profile.vs_ts_ratio)  # Fixed solids conserved
    vs_out = vs_effluent
    ts_digested = vs_out + fsi_in                          # kg TS/d remaining

    # --- Cake DS after dewatering ---
    # THP significantly improves dewaterability (handled in thp.py delta)
    # Base cake DS from feedstock profile (polymer-assisted centrifuge reference)
    cake_ds_pct = profile.cake_ds_pct_baseline

    # Cake wet mass: TS_cake / (DS% / 100)
    cake_wet_mass = ts_digested / (cake_ds_pct / 100.0) if cake_ds_pct > 0 else 0.0

    # Filtrate = digested sludge volume minus cake water
    # Digested sludge mass ≈ (original mass - biogas mass equivalent)
    biogas_mass_kg_d = _biogas_mass(methane_total, methane_pct)
    total_digested_mass = (profile.ts_load_kg_d / (profile.ts_pct / 100.0)) - biogas_mass_kg_d
    total_digested_mass = max(total_digested_mass, ts_digested / 0.03)  # sanity floor ~3% TS
    digested_volume_m3_d = total_digested_mass / 1010.0   # density ~1010 kg/m³

    cake_water_kg_d = cake_wet_mass * (1.0 - cake_ds_pct / 100.0)
    cake_ts_water = ts_digested / (cake_ds_pct / 100.0) - ts_digested  # water in cake
    filtrate_volume = max(0.0, digested_volume_m3_d - cake_wet_mass / 1010.0)

    return MADOutputs(
        hrt_days=hrt,
        digester_temp_C=stab.digester_temp_C,
        thp_applied=thp_applied,
        vsr_pct=vsr_pct,
        vs_destroyed_kg_d=vs_destroyed,
        vs_effluent_kg_d=vs_effluent,
        biogas_yield_m3_per_kgVSd=biogas_yield,
        methane_content_pct=methane_pct,
        biogas_total_m3_d=biogas_total,
        methane_total_m3_d=methane_total,
        biogas_energy_MJ_d=biogas_energy_MJ_d,
        ts_digested_kg_d=ts_digested,
        cake_ds_pct=cake_ds_pct,
        cake_mass_kg_d=cake_wet_mass,
        filtrate_volume_m3_d=filtrate_volume,
    )


# ---------------------------------------------------------------------------
# HRT → VSR INTERPOLATION
# ---------------------------------------------------------------------------

def _interpolate_vsr(hrt_days: float, blend_ratio_ps: float) -> float:
    """
    Interpolate VSR from M&E HRT_VSR_TABLE for blend.
    blend_ratio_ps: 0 = pure WAS, 1 = pure PS.
    Linear interpolation between table entries; clamped at extremes.
    """
    hrts = sorted(HRT_VSR_TABLE.keys())

    # Clamp to table range
    if hrt_days <= hrts[0]:
        ps_vsr, was_vsr = HRT_VSR_TABLE[hrts[0]]
    elif hrt_days >= hrts[-1]:
        ps_vsr, was_vsr = HRT_VSR_TABLE[hrts[-1]]
    else:
        # Find bracketing HRTs
        lower = max(h for h in hrts if h <= hrt_days)
        upper = min(h for h in hrts if h >= hrt_days)
        if lower == upper:
            ps_vsr, was_vsr = HRT_VSR_TABLE[lower]
        else:
            frac = (hrt_days - lower) / (upper - lower)
            ps_lo, was_lo = HRT_VSR_TABLE[lower]
            ps_hi, was_hi = HRT_VSR_TABLE[upper]
            ps_vsr = ps_lo + frac * (ps_hi - ps_lo)
            was_vsr = was_lo + frac * (was_hi - was_lo)

    # Blend-weight VSR
    vsr = ps_vsr * blend_ratio_ps + was_vsr * (1.0 - blend_ratio_ps)
    return round(vsr, 2)


# ---------------------------------------------------------------------------
# BIOGAS MASS EQUIVALENT
# ---------------------------------------------------------------------------

def _biogas_mass(methane_m3_d: float, methane_pct: float) -> float:
    """
    Approximate mass of biogas produced (kg/d).
    Used for mass balance closure check.
    CH₄ density ~0.717 kg/m³, CO₂ ~1.977 kg/m³ at STP.
    """
    co2_pct = 100.0 - methane_pct
    total_biogas_m3 = methane_m3_d / (methane_pct / 100.0) if methane_pct > 0 else 0.0
    co2_m3 = total_biogas_m3 * (co2_pct / 100.0)
    mass = methane_m3_d * 0.717 + co2_m3 * 1.977
    return mass
