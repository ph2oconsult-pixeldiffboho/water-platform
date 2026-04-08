"""
THP (thermal hydrolysis process) benefit model.
Computes incremental gains over base MAD — delta VSR, biogas uplift,
cake DS improvement, HRT reduction, and steam energy demand.

ph2o Consulting — BioPoint v1
"""

from engine.dataclasses import (
    BioPointInputs, FeedstockProfile, MADOutputs, THPDelta
)
from data.feedstock_defaults import THP_DELTAS


def run_thp(inputs: BioPointInputs, profile: FeedstockProfile,
            mad_base: MADOutputs) -> THPDelta:
    """
    Compute THP delta over the provided base MAD result.
    Returns THPDelta — incremental benefit, not absolute values.
    Absolute post-THP values are resolved in the pathway assembler
    by re-running MAD with thp_applied=True and adjusted HRT.
    """
    if inputs.stabilisation.stabilisation != "MAD_THP":
        return THPDelta(applied=False)

    ref = THP_DELTAS
    blend_ps = profile.blend_ratio_ps
    blend_was = 1.0 - blend_ps

    # --- HRT reduction ---
    base_hrt = mad_base.hrt_days
    auto_hrt = base_hrt * ref["hrt_reduction_factor"]
    auto_hrt = max(auto_hrt, ref["hrt_min_post_thp_days"])

    # User override takes precedence
    if inputs.stabilisation.thp_hrt_override is not None:
        post_thp_hrt = max(
            inputs.stabilisation.thp_hrt_override,
            ref["hrt_min_post_thp_days"]
        )
    else:
        post_thp_hrt = auto_hrt

    hrt_reduction_pct = (base_hrt - post_thp_hrt) / base_hrt * 100.0

    # --- Delta VSR --- blend-weighted
    delta_vsr = (
        ref["delta_vsr_ps_pct"] * blend_ps
        + ref["delta_vsr_was_pct"] * blend_was
    )
    vsr_with_thp = mad_base.vsr_pct + delta_vsr

    # THP allows higher VSR even at reduced HRT — the re-run MAD with
    # post_thp_hrt will yield lower VSR than base, but THP delta MORE than
    # compensates. Net VSR is validated in pathway.py.

    # --- Delta biogas --- proportional to delta VSR over base VSR
    delta_biogas_pct = (delta_vsr / mad_base.vsr_pct * 100.0) if mad_base.vsr_pct > 0 else 0.0

    # --- Delta methane content ---
    delta_ch4 = ref["delta_methane_content_pct"]

    # --- Delta cake DS --- blend-weighted
    delta_cake_ds = (
        ref["delta_cake_ds_ps_pct"] * blend_ps
        + ref["delta_cake_ds_was_pct"] * blend_was
    )

    # --- THP steam demand ---
    ts_feed_kg_d = profile.ts_load_kg_d
    steam_demand_MJ_d = ts_feed_kg_d * ref["steam_demand_kJ_per_tTS"] / 1000.0  # kJ→MJ, per tTS
    # Correction: ref is per tonne TS, ts_feed is in kg/d → divide by 1000
    steam_demand_MJ_d = ts_feed_kg_d / 1000.0 * (ref["steam_demand_kJ_per_tTS"] / 1000.0)
    steam_demand_kWh_d = steam_demand_MJ_d / 3.6

    return THPDelta(
        applied=True,
        hrt_base_days=base_hrt,
        hrt_post_thp_days=post_thp_hrt,
        hrt_reduction_pct=hrt_reduction_pct,
        delta_vsr_pct=round(delta_vsr, 2),
        vsr_with_thp_pct=round(vsr_with_thp, 2),
        delta_biogas_pct=round(delta_biogas_pct, 2),
        delta_methane_content_pct=delta_ch4,
        delta_cake_ds_pct=round(delta_cake_ds, 2),
        steam_demand_MJ_d=round(steam_demand_MJ_d, 1),
        steam_demand_kWh_d=round(steam_demand_kWh_d, 1),
    )
