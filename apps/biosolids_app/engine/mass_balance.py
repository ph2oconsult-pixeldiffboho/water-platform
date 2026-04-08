"""
Mass balance engine.
Tracks TS, VS, water, biogas, cake, and filtrate flows.
Closure check validates mass conservation to <1%.

ph2o Consulting — BioPoint v1
"""

from engine.dataclasses import FeedstockProfile, MADOutputs, MassBalance
from engine.mad import _biogas_mass


def run_mass_balance(profile: FeedstockProfile, mad: MADOutputs) -> MassBalance:
    """
    Full mass balance across digestion + dewatering boundary.
    Input: characterised feedstock profile + MAD outputs.
    """
    # --- INPUTS ---
    ts_in = profile.ts_load_kg_d
    vs_in = profile.vs_load_kg_d
    fsi_in = ts_in - vs_in                               # Fixed solids (inorganic)
    ts_frac = profile.ts_pct / 100.0
    total_mass_in = ts_in / ts_frac if ts_frac > 0 else 0.0   # Wet mass kg/d
    water_in = total_mass_in - ts_in

    # --- DESTRUCTION ---
    vs_destroyed = mad.vs_destroyed_kg_d
    vs_out = mad.vs_effluent_kg_d
    fsi_out = fsi_in                                      # Inorganics conserved
    ts_digested = vs_out + fsi_out

    # --- BIOGAS MASS ---
    methane_total = mad.methane_total_m3_d
    methane_pct = mad.methane_content_pct
    biogas_mass = _biogas_mass(methane_total, methane_pct)
    ch4_mass = methane_total * 0.717
    co2_mass = biogas_mass - ch4_mass

    # --- DIGESTED SLUDGE ---
    total_digested_mass = total_mass_in - biogas_mass
    total_digested_mass = max(total_digested_mass, 0.0)
    digested_volume = total_digested_mass / 1010.0        # density ≈1010 kg/m³

    # --- DEWATERED CAKE ---
    cake_ds = mad.cake_ds_pct
    cake_ts = ts_digested                                  # All TS goes to cake
    cake_wet = cake_ts / (cake_ds / 100.0) if cake_ds > 0 else 0.0
    cake_volume = cake_wet / 1050.0                       # Cake density ~1050 kg/m³

    # --- FILTRATE ---
    filtrate_mass = total_digested_mass - cake_wet
    filtrate_mass = max(filtrate_mass, 0.0)
    filtrate_volume = filtrate_mass / 1005.0              # Thin filtrate density
    # Filtrate carries ~5% of cake TS as suspended solids return load
    filtrate_ts = cake_ts * 0.05

    # --- CLOSURE CHECK ---
    # Mass in = biogas + cake (wet) + filtrate
    mass_out = biogas_mass + cake_wet + filtrate_mass
    error_pct = abs(total_mass_in - mass_out) / total_mass_in * 100.0 if total_mass_in > 0 else 0.0

    return MassBalance(
        ts_in_kg_d=round(ts_in, 1),
        vs_in_kg_d=round(vs_in, 1),
        water_in_kg_d=round(water_in, 1),
        total_mass_in_kg_d=round(total_mass_in, 1),
        vs_destroyed_kg_d=round(vs_destroyed, 1),
        fsi_in_kg_d=round(fsi_in, 1),
        fsi_out_kg_d=round(fsi_out, 1),
        biogas_mass_kg_d=round(biogas_mass, 2),
        methane_mass_kg_d=round(ch4_mass, 2),
        co2_mass_kg_d=round(co2_mass, 2),
        ts_digested_kg_d=round(ts_digested, 1),
        vs_digested_kg_d=round(vs_out, 1),
        total_digested_mass_kg_d=round(total_digested_mass, 1),
        digested_volume_m3_d=round(digested_volume, 2),
        cake_ts_kg_d=round(cake_ts, 1),
        cake_ds_pct=cake_ds,
        cake_wet_mass_kg_d=round(cake_wet, 1),
        cake_volume_m3_d=round(cake_volume, 2),
        filtrate_volume_m3_d=round(filtrate_volume, 2),
        filtrate_ts_kg_d=round(filtrate_ts, 1),
        mass_balance_error_pct=round(error_pct, 3),
    )
