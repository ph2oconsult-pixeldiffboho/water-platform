"""
Feedstock characterisation engine.
Resolves blend-weighted properties from M&E defaults + user overrides.
Handles both sizing modes (volume-based and VS-load-based).

ph2o Consulting — BioPoint v1
"""

import math
from engine.dataclasses import (
    BioPointInputs, FeedstockProfile, PlantSizingInputs
)
from data.feedstock_defaults import PS_DEFAULTS, WAS_DEFAULTS


def characterise_feedstock(inputs: BioPointInputs) -> FeedstockProfile:
    """
    Main entry point. Returns a fully resolved FeedstockProfile.
    Blend weighting is by mass fraction PS (blend_ratio_ps).
    """
    fs = inputs.feedstock
    sz = inputs.sizing

    blend_ps = _resolve_blend_ratio(fs.feedstock_type, fs.blend_ratio_ps)
    blend_was = 1.0 - blend_ps

    # --- resolve defaults by feedstock type ---
    ps_ref = PS_DEFAULTS
    was_ref = WAS_DEFAULTS

    # TS %
    ts_pct = _blend(
        ps_ref["ts_pct_mid"], was_ref["ts_pct_mid"], blend_ps,
        override=fs.ts_pct_override
    )

    # VS/TS ratio
    vs_ts = _blend(
        ps_ref["vs_ts_ratio_mid"], was_ref["vs_ts_ratio_mid"], blend_ps,
        override=fs.vs_ts_ratio_override
    )

    vs_pct = ts_pct * vs_ts  # VS as % of wet mass

    # Biogas yield (m³/kgVS destroyed) — blend weighted
    biogas_yield = _blend(
        ps_ref["biogas_yield_m3_per_kgVSd"],
        was_ref["biogas_yield_m3_per_kgVSd"],
        blend_ps
    )

    # Methane content %
    methane_pct = _blend(
        ps_ref["methane_content_pct"],
        was_ref["methane_content_pct"],
        blend_ps
    )

    # Cake DS baseline (pre-digestion reference — dewatered raw sludge)
    cake_ds = _blend(
        ps_ref["cake_ds_pct_polymer"],
        was_ref["cake_ds_pct_polymer"],
        blend_ps
    )

    # PFAS — worst-case if any WAS fraction present
    if blend_was > 0.0:
        pfas_tier = "HIGH" if blend_was >= 0.3 else "MEDIUM"
    else:
        pfas_tier = "LOW"

    # Density (blend weighted)
    density = _blend(
        ps_ref["density_kg_m3"], was_ref["density_kg_m3"], blend_ps
    )

    # --- resolve sizing ---
    sizing = _resolve_sizing(sz, ts_pct, vs_ts, density)

    profile = FeedstockProfile(
        feedstock_type=fs.feedstock_type,
        blend_ratio_ps=blend_ps,
        ts_pct=ts_pct,
        vs_ts_ratio=vs_ts,
        vs_pct=vs_pct,
        vs_load_kg_d=sizing["vs_load_kg_d"],
        ts_load_kg_d=sizing["ts_load_kg_d"],
        sludge_volume_m3_d=sizing["sludge_volume_m3_d"],
        methane_content_pct=methane_pct,
        biogas_yield_m3_per_kgVSd=biogas_yield,
        cake_ds_pct_baseline=cake_ds,
        pfas_risk_tier=pfas_tier,
        pathogen_class_raw="CLASS_B_CANDIDATE",
        density_kg_m3=density,
    )

    return profile


# ---------------------------------------------------------------------------
# SIZING RESOLUTION
# ---------------------------------------------------------------------------

def _resolve_sizing(sz: PlantSizingInputs, ts_pct: float,
                    vs_ts: float, density: float) -> dict:
    """
    Dual-mode sizing resolver.
    Returns dict with vs_load_kg_d, ts_load_kg_d, sludge_volume_m3_d.
    """
    if sz.sizing_mode == "VOLUME":
        # Volume-based: user supplies m³/d + TS%
        vol = sz.sludge_volume_m3_d or 0.0
        # ts_feed_pct is the field name on PlantSizingInputs; fall back to M&E default
        user_ts = getattr(sz, 'ts_feed_pct', None) or getattr(sz, 'ts_pct', None)
        ts = (user_ts if user_ts is not None else ts_pct) / 100.0
        vs = vs_ts
        mass_kg_d = vol * density           # Total wet mass kg/d
        ts_kg_d = mass_kg_d * ts
        vs_kg_d = ts_kg_d * vs
        return {
            "sludge_volume_m3_d": vol,
            "ts_load_kg_d": ts_kg_d,
            "vs_load_kg_d": vs_kg_d,
        }

    elif sz.sizing_mode == "VS_LOAD":
        # VS-load-based: user supplies kg VS/d directly
        vs_kg_d = sz.vs_load_kg_d or 0.0
        ts_kg_d = vs_kg_d / vs_ts if vs_ts > 0 else 0.0
        ts_frac = ts_pct / 100.0
        mass_kg_d = ts_kg_d / ts_frac if ts_frac > 0 else 0.0
        vol = mass_kg_d / density if density > 0 else 0.0
        return {
            "sludge_volume_m3_d": vol,
            "ts_load_kg_d": ts_kg_d,
            "vs_load_kg_d": vs_kg_d,
        }

    else:
        raise ValueError(f"Unknown sizing_mode: {sz.sizing_mode}")


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _resolve_blend_ratio(feedstock_type: str, blend_ratio_ps: float) -> float:
    """Return PS mass fraction — clamped for single-type feedstocks."""
    if feedstock_type == "PS":
        return 1.0
    elif feedstock_type == "WAS":
        return 0.0
    else:  # PS_WAS blend
        return max(0.0, min(1.0, blend_ratio_ps))


def _blend(ps_val: float, was_val: float, blend_ps: float,
           override: float = None) -> float:
    """Linear blend by PS mass fraction, with optional user override."""
    if override is not None:
        return override
    return ps_val * blend_ps + was_val * (1.0 - blend_ps)
