"""
engine/mad_adapter.py

BioPoint integration adapter for the MAD engine.

Responsibilities:
  1. build_mad_inputs()   — maps FeedstockInputsV2 + AssetInputs → MADInputs
  2. inject_mad_result()  — writes MADResult fields into the FS02 flowsheet object
                            and overrides energy_system values where MAD wins

Called from biopoint_v1_runner.py after the main engine run, for any AD-containing
flowsheet (FS02 AD-led, FS09 AD+incin, FS10 AD+THP+incin).

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional

from engine.mad import MADInputs, MADResult


# ============================================================
# DEFAULTS — used when BioPoint inputs don't yet have MAD fields
# These are safe screening-grade defaults; override via AssetInputs
# when site-specific data is available.
# ============================================================

MAD_FIELD_DEFAULTS = {
    # Digester geometry — MUST be overridden for meaningful results.
    # Defaults produce a notional 10 tDS/d metro plant.
    "psV_m3":                  3000.0,   # PS digester volume, m³
    "wasV_m3":                 1200.0,   # WAS digester volume, m³

    # Recup
    "ps_beta":                 1.5,
    "was_beta":                2.5,

    # Mixing
    "mixing_system_type":      "mechanical",
    "mixing_power_W_per_m3":   15.0,
    "mixing_scale":            1.00,

    # Chemistry
    "digester_pH":             7.25,
    "ph_control":              "off",
    "nh3_mode":                "acclimated",

    # Final dewatering (separate from recup-loop capture)
    "final_dewatering_cap_pct": 92.0,

    # CHP (overridden from energy_system if present)
    "chp_efficiency_pct":      40.0,
    "chp_availability_pct":    88.0,

    # Recup capture — aligned with preconditioning scenarios
    "ps_cap_pct":              85.0,
    "was_cap_pct":             85.0,

    # Trade waste
    "trade_waste":             "normal",
}


# ============================================================
# BUILD MAD INPUTS
# ============================================================

def build_mad_inputs(feedstock, assets, strategic=None) -> Optional[MADInputs]:
    """
    Map BioPoint input objects to MADInputs.

    Parameters
    ----------
    feedstock : FeedstockInputsV2
    assets    : AssetInputs
    strategic : StrategicInputs (optional — for THP flag)

    Returns None if the feedstock is not suitable for MAD
    (e.g. thermophilic, non-municipal, or insufficient data).
    """
    ds_tpd = feedstock.dry_solids_tpd
    vs_pct = feedstock.volatile_solids_percent
    gcv    = feedstock.gross_calorific_value_mj_per_kg_ds

    # Guard: MAD is calibrated for mesophilic municipal sludge only
    sludge_type = getattr(feedstock, "sludge_type", "blended")
    if sludge_type not in ("blended", "primary", "secondary", "digested", "thp_digested"):
        return None

    # --- Split DS load into PS and WAS fractions ---
    # Default split: 60% PS / 40% WAS for blended sludge
    # If sludge_type is explicit, adjust split
    if sludge_type == "primary":
        ps_frac, was_frac = 1.0, 0.0
    elif sludge_type == "secondary":
        ps_frac, was_frac = 0.0, 1.0
    else:
        ps_frac, was_frac = 0.60, 0.40

    psDS = ds_tpd * ps_frac
    wasDS = ds_tpd * was_frac

    # Guard: pure PS or pure WAS feeds need at least 0.1 tDS/d on each stream
    # to avoid divide-by-zero; skip MAD if either stream is trivial
    if psDS < 0.1 or wasDS < 0.1:
        return None

    # --- Feed quality ---
    psTS  = getattr(feedstock, "dewatered_ds_percent", 4.0)   # Use feed DS% as TS proxy
    wasTS = psTS                                               # Same until separate data available
    psVS  = vs_pct
    wasVS = vs_pct * 0.93                                      # WAS typically slightly lower VS than PS
    psN   = getattr(feedstock, "ps_n_pct_ds",  3.0)           # new field (default 3%)
    wasN  = getattr(feedstock, "was_n_pct_ds", 8.5)           # new field (default 8.5%)

    pfas_present  = getattr(feedstock, "pfas_present",  "unknown")
    trade_waste   = getattr(feedstock, "trade_waste_classification", "normal")

    # --- Asset geometry ---
    psV  = getattr(assets, "ps_digester_volume_m3",  MAD_FIELD_DEFAULTS["psV_m3"])
    wasV = getattr(assets, "was_digester_volume_m3", MAD_FIELD_DEFAULTS["wasV_m3"])

    # --- Recup ---
    ps_cap  = getattr(assets, "ps_recup_cap_pct",  MAD_FIELD_DEFAULTS["ps_cap_pct"])
    was_cap = getattr(assets, "was_recup_cap_pct", MAD_FIELD_DEFAULTS["was_cap_pct"])
    ps_beta  = getattr(assets, "ps_beta",  MAD_FIELD_DEFAULTS["ps_beta"])
    was_beta = getattr(assets, "was_beta", MAD_FIELD_DEFAULTS["was_beta"])
    final_cap = getattr(assets, "final_dewatering_cap_pct",
                        MAD_FIELD_DEFAULTS["final_dewatering_cap_pct"])

    # --- Mixing ---
    mixing_sys   = getattr(assets, "mixing_system_type",
                           MAD_FIELD_DEFAULTS["mixing_system_type"])
    mixing_power = getattr(assets, "mixing_power_W_per_m3",
                           MAD_FIELD_DEFAULTS["mixing_power_W_per_m3"])
    mixing_scale = getattr(assets, "mixing_scale",
                           MAD_FIELD_DEFAULTS["mixing_scale"])

    # --- Chemistry ---
    digester_pH = getattr(assets, "digester_pH",
                          MAD_FIELD_DEFAULTS["digester_pH"])
    ph_control  = getattr(assets, "ph_control",
                          MAD_FIELD_DEFAULTS["ph_control"])
    nh3_mode    = getattr(assets, "nh3_mode",
                          MAD_FIELD_DEFAULTS["nh3_mode"])

    # --- Pretreatment ---
    thp_present  = getattr(assets, "thp_present", False)
    pretreatment = "thp" if thp_present else "none"
    if pretreatment == "thp":
        nh3_mode = "thp"

    # --- Energy ---
    chp_eff   = getattr(assets, "chp_efficiency_pct",
                        MAD_FIELD_DEFAULTS["chp_efficiency_pct"])
    chp_avail = getattr(assets, "chp_availability_pct",
                        MAD_FIELD_DEFAULTS["chp_availability_pct"])

    # --- Reactor type ---
    reactor_type = getattr(assets, "reactor_type", "conventional")

    return MADInputs(
        psV=psV, wasV=wasV,
        psDS=psDS, wasDS=wasDS,
        psTS=psTS, wasTS=wasTS,
        psVS=psVS, wasVS=wasVS,
        psN=psN, wasN=wasN,
        mode="separate",
        sepBenefit=1.10,
        pretreatment=pretreatment,
        reactorType=reactor_type,
        recup=True,
        psCap=ps_cap, wasCap=was_cap,
        psBeta=ps_beta, wasBeta=was_beta,
        finalDewateringCap=final_cap,
        mixingSystemType=mixing_sys,
        mixingPower=mixing_power,
        mixingScale=mixing_scale,
        digester_pH=digester_pH,
        pHControl=ph_control,
        nh3Mode=nh3_mode,
        tradeWaste=trade_waste,
        chpE=chp_eff,
        chpAvail=chp_avail,
    )


# ============================================================
# INJECT MAD RESULT INTO FLOWSHEET
# ============================================================

def inject_mad_result(flowsheet, mad_result: MADResult, warnings: list) -> None:
    """
    Write MADResult fields into the flowsheet object and append
    any diagnostic warnings to the global warnings list.

    The flowsheet object is mutated in place.
    MAD overrides energy_system outputs where it has better data.
    """
    # Attach the full result for page rendering
    flowsheet.mad_detail = mad_result

    # --- Energy system override ---
    # MAD wins over energy_system.py defaults for any AD flowsheet
    es = getattr(flowsheet, "energy_system", None)
    if es is not None:
        try:
            es.biogas_volume_m3_per_d   = mad_result.biogas_m3_per_d
            es.biogas_energy_GJ_per_d   = mad_result.biogas_GJ_per_d
            es.CHP_gross_kW             = mad_result.elecGross_kW
            es.AD_net_electrical_kW     = mad_result.netElec_kW
            es.AD_mixing_parasitic_kW   = mad_result.mixingParasitic_kW
        except AttributeError:
            pass  # energy_system may not have all fields — safe to skip

    # --- Centrate N load (for BNR sidestream assessment) ---
    if hasattr(flowsheet, "mainstream_coupling"):
        mc = flowsheet.mainstream_coupling
        if mc is not None:
            try:
                mc.mad_centrate_N_kg_per_d = mad_result.centrate_N_kg_per_d
            except AttributeError:
                pass

    # --- Warnings ---
    flags = mad_result.diagnostic_flags

    if mad_result.feasibility_warning:
        warnings.append(
            f"MAD GEOMETRIC INFEASIBILITY: Digester volume is insufficient to reach "
            f"stable SRT ≥ {mad_result.feasibility.minStableSRT_d:.0f}d under typical "
            f"operating conditions (cap 85%, β 2.0). Review digester sizing — WAS "
            f"max achievable SRT = {mad_result.feasibility.maxAchievableWasSRT_d:.1f}d."
        )

    if mad_result.status == "FAILURE":
        warnings.append(
            f"MAD STATUS FAILURE: AD operating point is outside viable range. "
            f"Primary constraint: {mad_result.primary_constraint}. "
            f"WAS f_eff = {mad_result.was.f_eff:.2f}, "
            f"inhibition = {mad_result.was.inhibition_pct:.1f}%, "
            f"SRT_eff = {mad_result.was.SRT_eff_d:.1f}d."
        )
    elif mad_result.status == "LIMITING":
        warnings.append(
            f"MAD STATUS LIMITING: AD operating point approaching constraint boundary. "
            f"Primary constraint: {mad_result.primary_constraint}. "
            f"Monitor closely — disturbances may push to FAILURE."
        )

    if flags.get("biogas_blind_warning"):
        warnings.append(
            f"MAD BIOGAS BLIND ZONE: WAS SRT > 30d — biogas yield response to NH4 "
            f"and pH is below daily plant variability. Use NH4 + pH as primary "
            f"performance indicators, not biogas flow."
        )

    if flags.get("geometric_marginal"):
        warnings.append(
            f"MAD GEOMETRY MARGINAL: Digester volume is marginal for stable SRT. "
            f"Operating window is narrow — confirm recup capture and β at design."
        )

    if flags.get("industrial_trade_waste"):
        warnings.append(
            f"MAD INDUSTRIAL CATCHMENT: WAS N% elevated to industrial baseline (≥11%). "
            f"Confirm actual WAS N content — industrial trade waste can push "
            f"FAN inhibition into LIMITING/FAILURE zone."
        )
