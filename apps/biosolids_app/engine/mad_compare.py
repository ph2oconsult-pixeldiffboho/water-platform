"""
engine/mad_compare.py

BioPoint V1 — MAD Configuration Comparison Engine.

Runs up to four digestion configurations against the same site inputs
and scores each against eight project drivers. Pure Python — no Streamlit.

Configurations:
  base          Conventional mesophilic AD (no THP, no recup thickening upgrade)
  recup         Recuperative thickening (higher feed TS via centrifuge recirculation)
  pre_thp       Pre-digestion THP (cell disintegration before digesters)
  solidstream   SolidStream post-digestion THP (retrofit of existing digesters)

Eight project drivers (fixed set, user-weighted):
  energy        Biogas / electricity production
  biosolids     Biosolids quality (Class A vs B, pathogen kill)
  dewatering    Cake DS%, wet cake volume reduction
  return_load   NH4-N returned to liquid treatment (lower = better)
  carbon        Net GHG (Scope 1 + 2 + 3, lower = better)
  opex          Operating cost (lower = better)
  capex         Capital cost (lower = better, qualitative)
  headroom      Digester throughput headroom / flexibility

Entry point:
    result = run_comparison(site_inputs, driver_weights, configs_to_run)

ph2o Consulting — BioPoint V1 — v25B02
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal

# ── Configuration identifiers ──────────────────────────────────────────────
ConfigID = Literal["base", "recup", "pre_thp", "solidstream"]

ALL_CONFIGS: List[ConfigID] = ["base", "recup", "pre_thp", "solidstream"]

CONFIG_LABELS = {
    "base":        "Base Case\n(Conventional AD)",
    "recup":       "Recuperative\nThickening",
    "pre_thp":     "Pre-digestion\nTHP",
    "solidstream": "SolidStream\n(Post-THP)",
}

CONFIG_LABELS_SHORT = {
    "base":        "Base Case",
    "recup":       "Recup. Thickening",
    "pre_thp":     "Pre-THP",
    "solidstream": "SolidStream",
}

# ── Driver definitions ─────────────────────────────────────────────────────
DRIVER_IDS = ["energy", "biosolids", "dewatering", "return_load",
              "carbon", "opex", "capex", "headroom"]

DRIVER_LABELS = {
    "energy":      "Energy Recovery",
    "biosolids":   "Biosolids Quality",
    "dewatering":  "Dewatering Performance",
    "return_load": "Return Load (NH4)",   # plain ASCII — sub tag applied in report
    "carbon":      "GHG / Carbon Footprint",
    "opex":        "Operating Cost (OPEX)",
    "capex":       "Capital Cost (CAPEX)",
    "headroom":    "Digester Headroom",
}

DRIVER_DESCRIPTIONS = {
    "energy":      "Biogas production (m³/day) and net electricity output (kW). Higher = better.",
    "biosolids":   "Pathogen classification (Class A / B), regulatory compliance, product marketability.",
    "dewatering":  "Dewatered cake DS%, wet cake volume (t/day), truck movements. Drier = better.",
    "return_load": "NH4-N returned to liquid treatment train (kg/day). Lower = better.",
    "carbon":      "Net GHG kg CO2e/day. Scope 1 (fugitive CH4, N2O) + Scope 2 (grid) + Scope 3 (transport).",
    "opex":        "Annual operating cost: polymer, energy, disposal, sidestream treatment.",
    "capex":       "Capital cost indicator (order-of-magnitude, ±30%). New THP = higher CAPEX.",
    "headroom":    "Digester hydraulic headroom — capacity available for throughput growth.",
}

# Higher score = better for all drivers (scores are normalised 1–4 within comparison)
DRIVER_HIGHER_IS_BETTER = {
    "energy":      True,
    "biosolids":   True,
    "dewatering":  True,
    "return_load": False,   # Lower NH4 return = better → invert
    "carbon":      False,   # Lower GHG = better → invert
    "opex":        False,   # Lower cost = better → invert
    "capex":       False,   # Lower CAPEX = better → invert
    "headroom":    True,
}

DEFAULT_WEIGHTS = {
    "energy":      3,
    "biosolids":   4,
    "dewatering":  3,
    "return_load": 3,
    "carbon":      3,
    "opex":        4,
    "capex":       2,
    "headroom":    2,
}


# ── Site inputs ────────────────────────────────────────────────────────────
@dataclass
class ComparisonSiteInputs:
    """
    Shared site inputs for all four configurations.
    The comparison engine modifies these per config — does not mutate this object.
    """
    # Feed (base case — before any upgrade)
    ps_ds_tpd:   float = 6.0      # PS dry solids, tDS/day
    was_ds_tpd:  float = 4.0      # WAS dry solids, tDS/day
    ps_ts_pct:   float = 4.0      # PS feed TS%, base case (after primary thickening)
    was_ts_pct:  float = 4.0      # WAS feed TS%, base case (after secondary thickening)
    ps_vs_pct:   float = 75.0     # PS volatile solids % of DS
    was_vs_pct:  float = 70.0     # WAS volatile solids % of DS
    ps_n_pct:    float = 3.0      # PS nitrogen % of DS
    was_n_pct:   float = 8.5      # WAS nitrogen % of DS

    # Digester geometry (existing)
    ps_volume_m3:  float = 3000.0
    was_volume_m3: float = 1200.0

    # Recuperative thickening — achievable TS% with centrifuge recirculation
    recup_ps_ts_pct:  float = 6.0   # PS TS% after recup thickening upgrade
    recup_was_ts_pct: float = 5.5   # WAS TS% after recup thickening upgrade
    recup_beta_ps:    float = 2.0   # Recirculation ratio PS
    recup_beta_was:   float = 3.0   # Recirculation ratio WAS

    # Mixing
    mixing_type:  str   = "mechanical"
    mixing_power: float = 15.0     # W/m³

    # Chemistry
    digester_ph:  float = 7.25
    ph_control:   str   = "off"
    nh3_mode:     str   = "acclimated"

    # Recup loop (base case)
    ps_cap:  float = 85.0
    was_cap: float = 85.0
    ps_beta: float = 1.5
    was_beta: float = 2.5

    # CHP
    chp_eff_pct:   float = 40.0
    chp_avail_pct: float = 88.0
    final_dew_cap: float = 92.0

    # Economics
    electricity_buy_per_kwh:  float = 0.18   # $/kWh purchased
    electricity_sell_per_kwh: float = 0.10   # $/kWh exported
    disposal_cost_per_t_wet:  float = 80.0   # $/wet tonne cake
    polymer_cost_per_kg:      float = 3.50   # $/kg polymer
    polymer_dose_kg_per_tds:  float = 8.0    # kg/tDS — dewatering polymer
    transport_km:             float = 50.0   # km to disposal
    transport_cost_per_t_km:  float = 0.25   # $/t·km

    # GHG
    grid_intensity_kg_co2e_per_kwh: float = 0.55   # kg CO2e/kWh (VIC default)

    # Plant context
    plant_tkn_kg_per_d: float = 500.0   # Total plant TKN load (for % return calc)
    project_name:       str   = "BioPoint Analysis"
    # Sidestream OPEX parameters
    aeration_kwh_per_kg_o2:    float = 2.0    # kWh per kg O2 delivered
    o2_per_kg_n_nitrified:     float = 4.6    # kg O2 per kg NH4-N nitrified
    lime_cost_per_kg:          float = 0.15   # $/kg CaCO3 (lime equivalent)
    alk_per_kg_n:              float = 7.14   # kg CaCO3 per kg NH4-N nitrified
    prepared_by:        str   = "ph2o Consulting"


# ── Per-configuration result ───────────────────────────────────────────────
@dataclass
class ConfigResult:
    config_id:    ConfigID = "base"
    config_label: str = "Base Case"
    included:     bool = True

    # ── Energy ──────────────────────────────────────────────────────────────
    biogas_m3_per_d:    float = 0.0
    biogas_gj_per_d:    float = 0.0
    elec_gross_kw:      float = 0.0
    elec_net_kw:        float = 0.0
    elec_annual_mwh:    float = 0.0
    biogas_uplift_pct:  float = 0.0   # vs base case

    # ── Biosolids quality ────────────────────────────────────────────────────
    pathogen_class:     str   = "Class B"   # "Class A" / "Class B"
    class_a_achieved:   bool  = False
    hygienisation_note: str   = ""

    # ── Dewatering ──────────────────────────────────────────────────────────
    cake_ds_pct:            float = 20.0
    wet_cake_t_per_day:     float = 0.0
    wet_cake_t_per_year:    float = 0.0
    trucks_per_day:         float = 0.0
    cake_vol_reduction_pct: float = 0.0   # vs base case
    vsr_pct:                float = 57.5

    # ── Return load ─────────────────────────────────────────────────────────
    centrate_nh4_kg_per_d:     float = 0.0
    centrate_pct_of_plant_tkn: float = 0.0
    sidestream_treatment_reqd: bool  = False

    # ── GHG (Scope 1 / 2 / 3) ────────────────────────────────────────────────
    scope1_kg_co2e_per_d:         float = 0.0
    scope1_ch4_kg_co2e_per_d:     float = 0.0   # Fugitive CH4 only
    scope1_n2o_kg_co2e_per_d:     float = 0.0   # N2O from land application
    scope2_kg_co2e_per_d:         float = 0.0   # Grid electricity net
    scope3_kg_co2e_per_d:         float = 0.0
    scope3_transport_kg_co2e_per_d:  float = 0.0  # Cake transport
    scope3_polymer_kg_co2e_per_d:    float = 0.0  # Polymer upstream
    scope3_gas_upstream_kg_co2e_per_d: float = 0.0  # Supplementary boiler gas
    scope1_boiler_kg_co2e_per_d:     float = 0.0  # Supplementary boiler combustion
    heat_self_sufficient:            bool  = True
    heat_surplus_kw:                 float = 0.0
    thp_steam_demand_kw:             float = 0.0
    net_ghg_kg_co2e_per_d:           float = 0.0
    net_ghg_t_co2e_per_yr:           float = 0.0

    # ── OPEX ($/year) ────────────────────────────────────────────────────────
    opex_polymer_per_yr:                 float = 0.0
    opex_energy_net_per_yr:              float = 0.0   # + = cost, - = revenue
    opex_disposal_per_yr:                float = 0.0
    opex_sidestream_per_yr:              float = 0.0   # dedicated PN/A treatment
    opex_sidestream_aeration_per_yr:     float = 0.0   # extra mainstream aeration
    opex_sidestream_alkalinity_per_yr:   float = 0.0   # extra alkalinity dosing
    opex_sidestream_total_impact_per_yr: float = 0.0   # sum of all sidestream impacts
    opex_thp_maintenance_per_yr:         float = 0.0
    opex_total_per_yr:                   float = 0.0
    opex_delta_vs_base_per_yr:           float = 0.0   # vs base (- = saving)
    opex_delta_whole_plant_per_yr:       float = 0.0   # incl. sidestream impacts

    # ── CAPEX — equipment scope only (no dollar estimates) ──────────────────
    capex_low_m:     float = 0.0   # retained for scoring only — not shown in report
    capex_high_m:    float = 0.0   # retained for scoring only — not shown in report
    capex_mid_m:     float = 0.0   # retained for scoring only — not shown in report
    equipment_list:  List[str] = field(default_factory=list)
    capex_scope_summary: str = ""   # one-line scope description
    capex_note:      str = ""

    # ── Headroom ─────────────────────────────────────────────────────────────
    hrt_ps_d:              float = 0.0
    hrt_was_d:             float = 0.0
    min_stable_srt_d:      float = 6.0
    ps_srt_headroom_d:     float = 0.0   # achievable - minimum
    was_srt_headroom_d:    float = 0.0
    throughput_uplift_pct: float = 0.0   # additional DS% that could be accepted

    # ── Driver raw scores (before normalisation) ─────────────────────────────
    driver_raw: Dict[str, float] = field(default_factory=dict)

    # ── Normalised rank scores (1 = worst, 4 = best among included configs) ──
    driver_scores: Dict[str, int] = field(default_factory=dict)

    # ── Weighted total ────────────────────────────────────────────────────────
    weighted_score: float = 0.0

    # ── MAD engine result (for detailed view) ────────────────────────────────
    mad_result: object = None
    mad_status: str = "SAFE"

    # ── Narrative ─────────────────────────────────────────────────────────────
    recommendation_text: str = ""
    key_risks: List[str] = field(default_factory=list)
    key_benefits: List[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    configs:        Dict[ConfigID, ConfigResult] = field(default_factory=dict)
    included_ids:   List[ConfigID] = field(default_factory=list)
    driver_weights: Dict[str, int] = field(default_factory=dict)
    winner_id:      Optional[ConfigID] = None
    winner_label:   str = ""
    is_tie:         bool = False
    tie_ids:        List[str] = field(default_factory=list)
    executive_summary: str = ""
    site: Optional[ComparisonSiteInputs] = None


# ── CAPEX reference data ───────────────────────────────────────────────────
CAPEX_DATA = {
    "base": {
        "low": 0.0, "high": 0.0, "mid": 0.0,
        "scope_summary": "No new capital — existing plant optimisation only.",
        "note": "No new capital — existing plant, operational optimisation only.",
        "equipment": [
            "No new major equipment required",
            "Possible polymer system optimisation",
            "Possible mixing system audit/upgrade",
        ],
    },
    "recup": {
        "low": 0.5, "high": 2.0, "mid": 1.0,
        "scope_summary": "Centrifuge upgrade, polymer system, recirculation pipework.",
        "note": (
            "Recuperative thickening upgrade: centrifuge(s), polymer station, "
            "pipework, instrumentation. Cost scales with throughput. "
            "±30% order-of-magnitude. Source: WEF MOP 8, vendor budgets."
        ),
        "equipment": [
            "High-performance centrifuge(s) — duty + standby",
            "Polymer preparation and dosing system",
            "Thickened sludge pumps and pipework",
            "Recirculation loop instrumentation",
            "Sludge storage/buffer tank (optional)",
        ],
    },
    "pre_thp": {
        "low": 4.0, "high": 12.0, "mid": 7.0,
        "scope_summary": "THP reactors, steam boiler, pre-dewatering centrifuge, civil works. New building likely required.",
        "note": (
            "Pre-digestion THP: B6–B12 module(s), steam boiler or composite boiler, "
            "pre-dewatering centrifuge, pulper, flash tank, pipework, civil works. "
            "Cost highly scale-dependent. ±30%. "
            "Source: PYREG/Cambi/Veolia vendor data; WEF MOP 8."
        ),
        "equipment": [
            "CambiTHP or equivalent — B6/B8/B12 hydrolysis reactors",
            "Pulper and flash tank",
            "Steam boiler (composite or dedicated)",
            "Pre-dewatering centrifuge (duty + standby)",
            "Polymer preparation and dosing — pre-dewatering",
            "Sludge storage silo and feed pumps",
            "Heat recovery system",
            "Instrumentation and control upgrades",
            "Civil/structural works — new building or extension",
        ],
    },
    "solidstream": {
        "low": 3.0, "high": 9.0, "mid": 5.5,
        "scope_summary": "THP reactors, composite boiler, pre- and post-dewatering centrifuges, coolveyor, cake storage.",
        "note": (
            "SolidStream (post-THP): hydrolysis reactors, composite steam boiler, "
            "pre-dewatering centrifuge, final dewatering centrifuge, coolveyor, "
            "polymer station, pipework. Lower CAPEX than pre-THP as existing digesters "
            "are retained at full volume. ±30%. "
            "Source: Cambi Melbourne ETP memo 20.05.2026; Antwerp Schijnpoort 2025."
        ),
        "equipment": [
            "CambiTHP SolidStream — B6/B8 hydrolysis reactors (post-digestion)",
            "Composite steam boiler (exhaust gas + biogas burner)",
            "Pre-dewatering centrifuge — duty + standby",
            "Final dewatering centrifuge (hot, 80–90°C) — duty + standby",
            "Coolveyor/air-cooled screw conveyor",
            "Polymer preparation and dosing — final dewatering",
            "Centrate recycle pumps and pipework",
            "Foul air scrubber",
            "Dry cake storage silo",
            "Instrumentation and control upgrades",
        ],
    },
}

# OPEX reference rates ($/unit/year, per tDS/day capacity)
OPEX_THP_MAINTENANCE_PER_TDS_PER_YR = 25000.0   # $/tDS/day/yr for THP O&M
OPEX_RECUP_MAINTENANCE_PER_TDS_PER_YR = 8000.0  # $/tDS/day/yr for recup centrifuge O&M

# ── Heat recovery constants ────────────────────────────────────────────────
# CHP heat recovery: jacket water + exhaust HRSG
# Typical gas engine: 40% electrical, 45% heat recovery, 15% radiated losses
CHP_HEAT_RECOVERY_FRAC  = 0.45   # fraction of fuel input recoverable as useful heat
# THP steam demand per tDS/day feed (from Cambi Melbourne memo, scaled)
# Scenario 1: 6,215 kg/h steam for 219.5 tDS/day = 28.3 kg steam/tDS
# At 2,700 kJ/kg: 28.3 × 2700 / 3600 = 21.2 kW thermal per tDS/day
THP_STEAM_KW_PER_TDS_PER_DAY = 21.2
# Digester heating: Q = m_dot × Cp × ΔT
# Feed at 4%TS: 1 tDS/day → 25 m³/day feed → at 22°C rise → 26.7 kW/tDS/day
DIGESTER_HEAT_KW_PER_TDS_PER_DAY = 26.7
# SolidStream hot centrate recycle heat credit
# Hot centrate ~77°C at ~1,200/219.5 = 5.47 m³/tDS/day → at 40°C rise → 10.5 kW/tDS/day
SOLIDSTREAM_CENTRATE_HEAT_CREDIT_KW_PER_TDS = 10.5
# Natural gas upstream emission factor (for supplementary boiler if needed)
# IPCC / Ecoinvent: ~0.20 kg CO2e / kWh (LHV) upstream extraction + transport
NG_UPSTREAM_EF_KG_CO2E_PER_KWH = 0.20
# Natural gas combustion EF (Scope 1 direct): 0.202 kg CO2e/kWh LHV
NG_COMBUSTION_EF_KG_CO2E_PER_KWH = 0.202

# GHG constants
GWP_CH4 = 28.0         # AR5
CH4_FUGITIVE_FRAC = 0.015
CH4_DENSITY = 0.717    # kg/m³
CH4_FRACTION_BIOGAS = 0.64
N2O_EF_LAND = 0.01
GWP_N2O = 265.0
N2O_MW_RATIO = 44.0/28.0
TRANSPORT_EF = 0.10    # kg CO2e / t·km
POLYMER_EF = 3.5       # kg CO2e / kg polymer
BIOGAS_LHV_MJ_M3 = 35.8 * CH4_FRACTION_BIOGAS   # CH4 fraction only


# ── Physics helpers ────────────────────────────────────────────────────────

def _run_mad_config(site: ComparisonSiteInputs, config_id: ConfigID):
    """Run MAD engine for a given config. Returns MADResult or None."""
    try:
        from engine.mad import MADInputs, run_mad

        # Build MADInputs per config
        if config_id == "base":
            inp = MADInputs(
                psV=site.ps_volume_m3, wasV=site.was_volume_m3,
                psDS=site.ps_ds_tpd,  wasDS=site.was_ds_tpd,
                psTS=site.ps_ts_pct,  wasTS=site.was_ts_pct,
                psVS=site.ps_vs_pct,  wasVS=site.was_vs_pct,
                psN=site.ps_n_pct,    wasN=site.was_n_pct,
                psCap=site.ps_cap, wasCap=site.was_cap,
                psBeta=site.ps_beta, wasBeta=site.was_beta,
                mixingSystemType=site.mixing_type,
                mixingPower=site.mixing_power,
                digester_pH=site.digester_ph,
                pHControl=site.ph_control,
                nh3Mode=site.nh3_mode,
                pretreatment="none",
                finalDewateringCap=site.final_dew_cap,
                chpE=site.chp_eff_pct, chpAvail=site.chp_avail_pct,
            )

        elif config_id == "recup":
            inp = MADInputs(
                psV=site.ps_volume_m3, wasV=site.was_volume_m3,
                psDS=site.ps_ds_tpd,  wasDS=site.was_ds_tpd,
                psTS=site.recup_ps_ts_pct,  wasTS=site.recup_was_ts_pct,
                psVS=site.ps_vs_pct,  wasVS=site.was_vs_pct,
                psN=site.ps_n_pct,    wasN=site.was_n_pct,
                psCap=site.ps_cap, wasCap=site.was_cap,
                psBeta=site.recup_beta_ps, wasBeta=site.recup_beta_was,
                mixingSystemType=site.mixing_type,
                mixingPower=site.mixing_power,
                digester_pH=site.digester_ph,
                pHControl=site.ph_control,
                nh3Mode=site.nh3_mode,
                pretreatment="none",
                finalDewateringCap=site.final_dew_cap,
                chpE=site.chp_eff_pct, chpAvail=site.chp_avail_pct,
            )

        elif config_id == "pre_thp":
            inp = MADInputs(
                psV=site.ps_volume_m3, wasV=site.was_volume_m3,
                psDS=site.ps_ds_tpd,  wasDS=site.was_ds_tpd,
                psTS=site.ps_ts_pct,  wasTS=site.was_ts_pct,
                psVS=site.ps_vs_pct,  wasVS=site.was_vs_pct,
                psN=site.ps_n_pct,    wasN=site.was_n_pct,
                psCap=site.ps_cap, wasCap=site.was_cap,
                psBeta=site.ps_beta, wasBeta=site.was_beta,
                mixingSystemType=site.mixing_type,
                mixingPower=site.mixing_power,
                digester_pH=site.digester_ph,
                pHControl=site.ph_control,
                nh3Mode="thp",   # THP acclimated community
                pretreatment="thp",
                finalDewateringCap=site.final_dew_cap,
                chpE=site.chp_eff_pct, chpAvail=site.chp_avail_pct,
            )

        else:  # solidstream
            inp = MADInputs(
                psV=site.ps_volume_m3, wasV=site.was_volume_m3,
                psDS=site.ps_ds_tpd,  wasDS=site.was_ds_tpd,
                psTS=site.ps_ts_pct,  wasTS=site.was_ts_pct,
                psVS=site.ps_vs_pct,  wasVS=site.was_vs_pct,
                psN=site.ps_n_pct,    wasN=site.was_n_pct,
                psCap=site.ps_cap, wasCap=site.was_cap,
                psBeta=site.ps_beta, wasBeta=site.was_beta,
                mixingSystemType=site.mixing_type,
                mixingPower=site.mixing_power,
                digester_pH=site.digester_ph,
                pHControl=site.ph_control,
                nh3Mode="thp",
                pretreatment="solidstream",
                finalDewateringCap=site.final_dew_cap,
                chpE=site.chp_eff_pct, chpAvail=site.chp_avail_pct,
            )

        return run_mad(inp), inp

    except Exception:
        return None, None


def _cake_properties(config_id: ConfigID, vsr_pct: float,
                     ds_tpd: float, base_cake_ds_pct: float = 20.0):
    """
    Compute dewatered cake DS%, wet cake volume, and trucks/day.
    SolidStream achieves 38% DS (Cambi Melbourne memo).
    Pre-THP achieves ~30–35% DS (higher VSR but conventional dewatering).
    Recup: marginally better dewatering ~24–26% DS (higher feed TS).
    Base: 20–22% DS typical.
    """
    cake_ds = {
        "base":        base_cake_ds_pct,
        "recup":       base_cake_ds_pct + 3.0,   # marginal improvement
        "pre_thp":     base_cake_ds_pct + 12.0,  # improved rheology
        "solidstream": 38.0,                      # SolidStream guarantee
    }[config_id]

    # VS destroyed → DS remaining in cake
    # DS_feed × (1 - VSR × VS_fraction) = DS remaining
    # Simplified: VS fraction of feed ≈ 0.72 (site-specific, use avg)
    vs_fraction = 0.72
    ds_remaining_frac = 1.0 - (vsr_pct / 100.0) * vs_fraction
    ds_remaining_tpd = ds_tpd * ds_remaining_frac

    # Wet cake = DS_remaining / (cake_DS% / 100)
    wet_cake_tpd = ds_remaining_tpd / (cake_ds / 100.0)
    wet_cake_tpy = wet_cake_tpd * 365
    trucks_per_day = wet_cake_tpd / 40.0  # 40t per truck

    return cake_ds, wet_cake_tpd, wet_cake_tpy, trucks_per_day


def _heat_balance(config_id: str, elec_gross_kw: float,
                    ds_total: float, site) -> dict:
    """
    Compute CHP waste heat available vs THP steam + digester heating demand.
    Returns dict with heat budget components in kW.

    Physics:
    - CHP fuel input = elec_gross_kw / (chp_eff/100)
    - CHP heat available = fuel_input × CHP_HEAT_RECOVERY_FRAC
    - THP steam demand = ds_total × THP_STEAM_KW_PER_TDS_PER_DAY (pre_thp/solidstream only)
    - Digester heat demand = ds_total × DIGESTER_HEAT_KW_PER_TDS_PER_DAY
    - SolidStream: hot centrate recycle reduces digester demand
    - If CHP heat >= (steam + digester): self-sufficient, no gas boiler
    - If deficit: supplementary boiler required → Scope 1 + Scope 3 gas emissions

    Source: Cambi Melbourne ETP memo 20.05.2026; typical CHP heat recovery literature.
    """
    chp_eff_frac = site.chp_eff_pct / 100.0
    fuel_input_kw = elec_gross_kw / max(chp_eff_frac, 0.01)
    heat_available_kw = fuel_input_kw * CHP_HEAT_RECOVERY_FRAC

    # THP steam demand (only for THP configurations)
    thp_steam_kw = 0.0
    if config_id in ("pre_thp", "solidstream"):
        thp_steam_kw = ds_total * THP_STEAM_KW_PER_TDS_PER_DAY

    # Digester heating demand (all configs)
    digester_heat_gross_kw = ds_total * DIGESTER_HEAT_KW_PER_TDS_PER_DAY

    # SolidStream hot centrate recycle reduces digester heating demand
    centrate_heat_credit_kw = 0.0
    if config_id == "solidstream":
        centrate_heat_credit_kw = ds_total * SOLIDSTREAM_CENTRATE_HEAT_CREDIT_KW_PER_TDS

    digester_heat_net_kw = max(0.0, digester_heat_gross_kw - centrate_heat_credit_kw)

    total_heat_demand_kw = thp_steam_kw + digester_heat_net_kw
    heat_surplus_kw = heat_available_kw - total_heat_demand_kw
    supplementary_boiler_kw = max(0.0, -heat_surplus_kw)
    heat_self_sufficient = heat_surplus_kw >= 0

    return {
        "fuel_input_kw":           fuel_input_kw,
        "heat_available_kw":       heat_available_kw,
        "thp_steam_kw":            thp_steam_kw,
        "digester_heat_gross_kw":  digester_heat_gross_kw,
        "digester_heat_net_kw":    digester_heat_net_kw,
        "centrate_heat_credit_kw": centrate_heat_credit_kw,
        "total_heat_demand_kw":    total_heat_demand_kw,
        "heat_surplus_kw":         heat_surplus_kw,
        "supplementary_boiler_kw": supplementary_boiler_kw,
        "heat_self_sufficient":    heat_self_sufficient,
    }


def _ghg(config_id, biogas_m3_d, elec_net_kw, wet_cake_tpd,
         centrate_n_kg_d, site: ComparisonSiteInputs,
         elec_gross_kw: float = 0.0):
    """Scope 1/2/3 GHG calculation including heat recovery assessment."""
    # Scope 1: fugitive CH4
    ch4_fugitive_kg_d = (biogas_m3_d * CH4_FRACTION_BIOGAS
                         * CH4_FUGITIVE_FRAC * CH4_DENSITY)
    s1_ch4 = ch4_fugitive_kg_d * GWP_CH4

    # Scope 1: N2O from land application (if Class B → land applied)
    cake_ds_pct = {"base": 20, "recup": 23, "pre_thp": 32, "solidstream": 38}[config_id]
    ds_remaining = site.ps_ds_tpd + site.was_ds_tpd  # simplified
    n_applied_kg_d = ds_remaining * (site.ps_n_pct / 100.0 + site.was_n_pct / 100.0) / 2.0
    n2o_n = n_applied_kg_d * N2O_EF_LAND
    n2o_kg = n2o_n * N2O_MW_RATIO
    s1_n2o = n2o_kg * GWP_N2O

    scope1 = s1_ch4 + s1_n2o

    # Scope 2: grid electricity — CHP availability applied, result in kg CO2e/day
    # elec_net_kw > 0 = net export (credit = negative), < 0 = net import (cost = positive)
    chp_avail_frac = site.chp_avail_pct / 100.0
    if elec_net_kw > 0:
        scope2 = -(elec_net_kw * 24 * chp_avail_frac / 1000
                   * site.grid_intensity_kg_co2e_per_kwh)   # credit
    else:
        scope2 = (abs(elec_net_kw) * 24 * chp_avail_frac / 1000
                  * site.grid_intensity_kg_co2e_per_kwh)

    # Scope 3: transport — scales with actual wet cake volume per config
    transport_t_km = wet_cake_tpd * site.transport_km
    s3_transport = transport_t_km * TRANSPORT_EF

    # Scope 3: polymer upstream — scales with DS load + dewatering type
    poly_kg_d = (site.ps_ds_tpd + site.was_ds_tpd) * site.polymer_dose_kg_per_tds
    if config_id == "solidstream":
        poly_kg_d *= 1.5   # higher polymer for hot centrifuge dewatering
    elif config_id == "pre_thp":
        poly_kg_d *= 1.2   # pre-dewatering + final dewatering — two centrifuge stages
    s3_polymer = poly_kg_d * POLYMER_EF

    # Scope 3c: supplementary boiler gas — only if CHP waste heat insufficient
    # Heat balance determines if a gas boiler is needed beyond CHP exhaust recovery
    ds_total = site.ps_ds_tpd + site.was_ds_tpd
    heat = _heat_balance(config_id, elec_gross_kw, ds_total, site)
    supp_kw = heat["supplementary_boiler_kw"]
    # Upstream gas extraction + transport (Scope 3)
    s3_gas_upstream  = supp_kw * 24 / 1000 * NG_UPSTREAM_EF_KG_CO2E_PER_KWH
    # Supplementary boiler combustion (Scope 1 — direct on-site)
    s1_boiler = supp_kw * 24 / 1000 * NG_COMBUSTION_EF_KG_CO2E_PER_KWH
    # Add boiler combustion to Scope 1
    scope1 = scope1 + s1_boiler
    scope3 = s3_transport + s3_polymer + s3_gas_upstream
    # Store breakdown for report use
    _ghg_s3_transport = s3_transport
    _ghg_s3_polymer   = s3_polymer
    net = scope1 + scope2 + scope3

    return (scope1, scope2, scope3, net, s1_ch4, s1_n2o, s3_transport, s3_polymer,
            s3_gas_upstream, s1_boiler, heat)


def _opex(config_id, elec_net_kw, wet_cake_tpy,
          centrate_n_kg_d, ds_total, site: ComparisonSiteInputs,
          base_centrate_n_kg_d: float = 0.0):
    """Annual OPEX breakdown."""
    # Polymer
    poly_dose = site.polymer_dose_kg_per_tds
    if config_id == "solidstream":
        poly_dose *= 1.5
    poly_cost = ds_total * 365 * poly_dose * site.polymer_cost_per_kg

    # Energy net (positive = cost, negative = revenue)
    if elec_net_kw > 0:
        energy_cost = -elec_net_kw * 8760 * (site.chp_avail_pct/100) * site.electricity_sell_per_kwh
    else:
        energy_cost = abs(elec_net_kw) * 8760 * (site.chp_avail_pct/100) * site.electricity_buy_per_kwh

    # Disposal
    disposal_cost = wet_cake_tpy * site.disposal_cost_per_t_wet

    # Transport (included in disposal assumption above — or separate)
    transport_cost = wet_cake_tpy / 365 * site.transport_km * site.transport_cost_per_t_km * 365

    # Sidestream nitrogen impacts
    # Every THP configuration increases centrate NH4-N vs conventional AD.
    # This creates two unavoidable mainstream costs:
    # (1) Extra aeration: delta_N × O2_per_N × kWh_per_O2 × electricity_price
    # (2) Extra alkalinity: delta_N × alk_per_N × lime_cost
    # These are ALWAYS incurred regardless of whether dedicated sidestream
    # treatment is installed. They are currently excluded from most THP
    # screening assessments, leading to overstatement of OPEX savings.
    sidestream_cost = 0.0
    aeration_extra_cost = 0.0
    alkalinity_extra_cost = 0.0

    if config_id in ("pre_thp", "solidstream", "recup"):
        delta_n = max(0.0, centrate_n_kg_d - base_centrate_n_kg_d)
        # ss_pct: is THP-caused N increase large enough to warrant dedicated treatment?
        ss_pct = delta_n / max(site.plant_tkn_kg_per_d, 1) * 100
        aeration_extra_cost = (
            delta_n * 365
            * site.o2_per_kg_n_nitrified
            * site.aeration_kwh_per_kg_o2
            * site.electricity_buy_per_kwh
        )
        alkalinity_extra_cost = (
            delta_n * 365
            * site.alk_per_kg_n
            * site.lime_cost_per_kg
        )

    # Dedicated sidestream treatment: only warranted when THP-caused NH4-N
    # increase exceeds ~500 kg/day — below this, mainstream plant absorbs it
    # (industry rule: dedicated SHARON/ANAMMOX economic above ~500 kg NH4-N/day)
    SIDESTREAM_DEDICATED_THRESHOLD_KG_D = 500.0
    if config_id in ("pre_thp", "solidstream"):
        delta_n_pna = max(0.0, centrate_n_kg_d - base_centrate_n_kg_d)
        if delta_n_pna > SIDESTREAM_DEDICATED_THRESHOLD_KG_D:
            # THP increases centrate N enough for dedicated PN/A to be economic
            sidestream_cost = delta_n_pna * 365 * 4.0
            # Dedicated treatment handles the sidestream fraction
            # Mainstream still handles residual N; costs mostly replaced by sidestream_cost
            aeration_extra_cost   *= 0.20
            alkalinity_extra_cost *= 0.20

    # THP maintenance
    thp_maint = 0.0
    if config_id in ("pre_thp", "solidstream"):
        thp_maint = ds_total * OPEX_THP_MAINTENANCE_PER_TDS_PER_YR
    elif config_id == "recup":
        thp_maint = ds_total * OPEX_RECUP_MAINTENANCE_PER_TDS_PER_YR

    total = poly_cost + energy_cost + disposal_cost + transport_cost + sidestream_cost + thp_maint

    sidestream_total = sidestream_cost + aeration_extra_cost + alkalinity_extra_cost
    total = poly_cost + energy_cost + disposal_cost + transport_cost + sidestream_total + thp_maint

    return {
        "polymer":              poly_cost,
        "energy":               energy_cost,
        "disposal":             disposal_cost + transport_cost,
        "sidestream":           sidestream_cost,
        "aeration_extra":       aeration_extra_cost,
        "alkalinity_extra":     alkalinity_extra_cost,
        "sidestream_total":     sidestream_total,
        "thp_maint":            thp_maint,
        "total":                total,
    }


def _narratives(config_id: ConfigID, cr: ConfigResult,
                base: ConfigResult, site: ComparisonSiteInputs):
    """Plain-language benefits, risks, and recommendation text."""
    benefits, risks = [], []

    if config_id == "base":
        benefits = ["No capital expenditure required",
                    "Lowest operational complexity",
                    "Established, proven operation"]
        risks    = ["No biosolids quality upgrade — Class B only",
                    "Highest wet cake volume and disposal cost",
                    "No resilience against tightening land application regulations",
                    "Lowest energy recovery of all options"]

    elif config_id == "recup":
        uplift = cr.biogas_uplift_pct
        benefits = [f"Biogas uplift ~{uplift:.0f}% vs base case through improved VS loading",
                    "Improved dewatering — marginally drier cake",
                    "Moderate CAPEX compared to THP options",
                    "No change to digester hydraulics"]
        risks    = ["Class B biosolids only — no pathogen upgrade",
                    "Limited VS destruction improvement vs pre-THP or SolidStream",
                    "Higher TS% increases diffusion limitations at TS > 5–6%",
                    "NH3 inhibition risk increases with higher feed TS%"]

    elif config_id == "pre_thp":
        uplift = cr.biogas_uplift_pct
        # Flag if uplift is unexpectedly low — indicates VSmax saturation at this scale
        if uplift < 25:
            uplift_note = (
                f"~{uplift:.0f}% vs base case at this digester scale "
                f"(note: VS destruction near VSmax ceiling — actual uplift at larger "
                f"scale typically 40–50% per literature)"
            )
        else:
            uplift_note = f"~{uplift:.0f}% vs base case (consistent with THP literature)"
        benefits = [f"Highest biogas uplift of all options — {uplift_note}",
                    "Class A pathogen classification — expands market options",
                    "Improved dewatering (~30–35% DS)",
                    "Enables digester volume reduction for same throughput",
                    "Removes stockpiling requirement for Class A compliance"]
        risks    = ["Highest CAPEX of all options",
                    "Higher N mineralisation → larger centrate return load",
                    "Requires sidestream N treatment if plant TKN headroom is limited",
                    "Greater operational complexity — steam system, high-pressure vessels",
                    "Longer construction programme"]

    else:  # solidstream
        benefits = ["Class A equivalent pathogen kill without thermal drying",
                    f"Dewatered cake ≥38% DS — eliminates or greatly reduces drying",
                    f"~{cr.cake_vol_reduction_pct:.0f}% reduction in wet cake volume vs base",
                    f"~{cr.biogas_uplift_pct:.0f}% biogas uplift from COD centrate recycle",
                    "Retrofit of existing digesters — no new digester volume required",
                    "Eliminates 3-year stockpiling requirement (EPA Victoria)"]
        risks    = ["Minimum 15d HRT required — check digester volume adequacy",
                    "Performance is vendor-estimated (pre-contract) — verify at detailed design",
                    "Higher centrate N load than base case",
                    "Hot centrate (77°C) recycle requires careful process control",
                    "CAPEX lower than pre-THP but still significant"]

    # Recommendation text
    score = cr.weighted_score
    rank  = sorted([c.weighted_score for c in [cr]], reverse=True)
    rec = (
        f"{cr.config_label} achieves a weighted driver score of "
        f"{score:.1f}. "
    )
    if config_id == "base":
        rec += ("The base case is the lowest-risk, lowest-cost option but provides no "
                "pathway to improved biosolids quality or regulatory resilience.")
    elif config_id == "recup":
        rec += ("Recuperative thickening is a moderate-cost upgrade that improves "
                "biogas yield and dewatering without THP capital. Best suited to "
                "plants where biogas uplift is the primary driver and Class B "
                "biosolids remain acceptable.")
    elif config_id == "pre_thp":
        rec += ("Pre-digestion THP delivers the highest energy uplift and Class A "
                "biosolids. Recommended where land application regulation is tightening "
                "or where new digester capacity is planned and THP can be sized in.")
    else:
        rec += ("SolidStream is the recommended retrofit pathway for existing AD plants "
                "where dewatering performance and pathogen compliance are primary drivers "
                "and the existing digester volume is adequate (HRT ≥15d). "
                "Vendor performance guarantee required before financial commitment.")

    cr.key_benefits = benefits
    cr.key_risks    = risks
    cr.recommendation_text = rec
    return cr


# ── Raw score computation ──────────────────────────────────────────────────

def _raw_scores(configs: Dict[ConfigID, ConfigResult]) -> Dict[ConfigID, ConfigResult]:
    """
    Assign raw scores for each driver — higher always means better performance.
    Scores are 1–4 based on rank among included configs.
    """
    included = {k: v for k, v in configs.items() if v.included}
    n = len(included)

    # For each driver, collect raw metric values, rank them
    driver_metrics = {
        "energy":      {k: v.biogas_m3_per_d for k, v in included.items()},
        "biosolids":   {k: 4 if v.class_a_achieved else 1 for k, v in included.items()},
        "dewatering":  {k: v.cake_ds_pct for k, v in included.items()},
        "return_load": {k: v.centrate_nh4_kg_per_d for k, v in included.items()},
        "carbon":      {k: v.net_ghg_kg_co2e_per_d for k, v in included.items()},
        "opex":        {k: v.opex_total_per_yr for k, v in included.items()},
        "capex":       {k: v.capex_mid_m for k, v in included.items()},
        "headroom":    {k: v.ps_srt_headroom_d + v.was_srt_headroom_d
                       for k, v in included.items()},
    }

    for driver, metrics in driver_metrics.items():
        higher_better = DRIVER_HIGHER_IS_BETTER[driver]
        sorted_ids = sorted(metrics.keys(),
                            key=lambda k: metrics[k],
                            reverse=higher_better)
        for rank, cfg_id in enumerate(sorted_ids, 1):
            # rank 1 = best (highest score), rank n = worst
            score = n - rank + 1   # n for best, 1 for worst
            included[cfg_id].driver_scores[driver] = score
            included[cfg_id].driver_raw[driver] = metrics[cfg_id]

    return configs


def _weighted_totals(configs: Dict[ConfigID, ConfigResult],
                     weights: Dict[str, int]) -> Dict[ConfigID, ConfigResult]:
    """Compute weighted total score for each config."""
    included = {k: v for k, v in configs.items() if v.included}
    total_weight = sum(weights.values())

    for cfg_id, cr in included.items():
        wt = sum(cr.driver_scores.get(d, 1) * weights.get(d, 1)
                 for d in DRIVER_IDS)
        cr.weighted_score = round(wt / (total_weight * 4) * 100, 1)   # scale 0–100 (rank 1-4, max = 4×Σweights)

    return configs


# ── Main entry point ────────────────────────────────────────────────────────

def run_comparison(
    site: ComparisonSiteInputs,
    driver_weights: Dict[str, int] = None,
    configs_to_run: List[ConfigID] = None,
) -> ComparisonResult:
    """
    Run the four-configuration comparison.

    Parameters
    ----------
    site           : ComparisonSiteInputs
    driver_weights : dict of driver_id → weight (1–5). Defaults to DEFAULT_WEIGHTS.
    configs_to_run : list of ConfigIDs to include. Defaults to all four.

    Returns
    -------
    ComparisonResult
    """
    if driver_weights is None:
        driver_weights = DEFAULT_WEIGHTS.copy()
    if configs_to_run is None:
        configs_to_run = ALL_CONFIGS.copy()

    configs: Dict[ConfigID, ConfigResult] = {}
    base_result = None   # keep reference for delta calculations

    for config_id in ALL_CONFIGS:
        included = config_id in configs_to_run
        cr = ConfigResult(
            config_id=config_id,
            config_label=CONFIG_LABELS_SHORT[config_id],
            included=included,
        )

        if not included:
            configs[config_id] = cr
            continue

        # ── Run MAD engine ──────────────────────────────────────────────────
        mad_result, mad_inputs = _run_mad_config(site, config_id)
        cr.mad_result = mad_result
        cr.mad_status = mad_result.status if mad_result else "ERROR"

        if mad_result:
            cr.biogas_m3_per_d = mad_result.biogas_m3_per_d
            cr.biogas_gj_per_d = mad_result.biogas_GJ_per_d
            cr.elec_gross_kw   = mad_result.elecGross_kW
            cr.elec_net_kw     = mad_result.netElec_kW
            cr.elec_annual_mwh = (mad_result.netElec_kW * 8760
                                  * site.chp_avail_pct / 100 / 1000)
            cr.centrate_nh4_kg_per_d = mad_result.centrate_N_kg_per_d
            cr.centrate_pct_of_plant_tkn = (
                mad_result.centrate_N_kg_per_d
                / max(site.plant_tkn_kg_per_d, 1) * 100)
            cr.sidestream_treatment_reqd = cr.centrate_pct_of_plant_tkn > 10.0

            # VSR — weighted average of PS and WAS
            cr.vsr_pct = (
                mad_result.ps.VS_destruction_pct * 0.55
                + mad_result.was.VS_destruction_pct * 0.45
            )

            # HRT/SRT headroom
            cr.hrt_ps_d  = mad_result.ps.HRT_nominal_d
            cr.hrt_was_d = mad_result.was.HRT_nominal_d
            cr.ps_srt_headroom_d  = max(0, mad_result.ps.SRT_eff_d
                                        - mad_result.feasibility.minStableSRT_d)
            cr.was_srt_headroom_d = max(0, mad_result.was.SRT_eff_d
                                        - mad_result.feasibility.minStableSRT_d)
            cr.throughput_uplift_pct = min(
                cr.ps_srt_headroom_d / max(cr.hrt_ps_d, 1) * 100, 30.0)

        # ── Dewatering / cake ──────────────────────────────────────────────
        ds_total = site.ps_ds_tpd + site.was_ds_tpd
        cake_ds, wet_tpd, wet_tpy, trucks = _cake_properties(
            config_id, cr.vsr_pct, ds_total)
        cr.cake_ds_pct         = cake_ds
        cr.wet_cake_t_per_day  = wet_tpd
        cr.wet_cake_t_per_year = wet_tpy
        cr.trucks_per_day      = trucks

        # ── Pathogen class ─────────────────────────────────────────────────
        if config_id in ("pre_thp", "solidstream"):
            cr.pathogen_class   = "Class A"
            cr.class_a_achieved = True
            cr.hygienisation_note = (
                "THP operates at 150–165°C for ≥20 min (pre-THP) or "
                "145–165°C / 6 bar for 40 min (SolidStream). "
                "Sterilisation-level pathogen kill — Class A equivalent. "
                "Jurisdiction-specific regulatory acceptance required."
            )
        else:
            cr.pathogen_class   = "Class B"
            cr.class_a_achieved = False
            cr.hygienisation_note = (
                "Conventional mesophilic digestion (35–37°C) achieves "
                "Class B pathogen reduction only."
            )

        # ── GHG ───────────────────────────────────────────────────────────
        (s1, s2, s3, net, s1_ch4, s1_n2o, s3_transport, s3_polymer,
         s3_gas_upstream, s1_boiler, heat_bal) = _ghg(
            config_id, cr.biogas_m3_per_d, cr.elec_net_kw,
            cr.wet_cake_t_per_day, cr.centrate_nh4_kg_per_d, site,
            elec_gross_kw=cr.elec_gross_kw)
        cr.scope1_kg_co2e_per_d  = s1
        cr.scope1_ch4_kg_co2e_per_d = s1_ch4
        cr.scope1_n2o_kg_co2e_per_d = s1_n2o
        cr.scope2_kg_co2e_per_d  = s2
        cr.scope3_kg_co2e_per_d  = s3
        cr.scope3_transport_kg_co2e_per_d    = s3_transport
        cr.scope3_polymer_kg_co2e_per_d      = s3_polymer
        cr.scope3_gas_upstream_kg_co2e_per_d = s3_gas_upstream
        cr.scope1_boiler_kg_co2e_per_d       = s1_boiler
        cr.heat_self_sufficient = heat_bal['heat_self_sufficient']
        cr.heat_surplus_kw      = heat_bal['heat_surplus_kw']
        cr.thp_steam_demand_kw  = heat_bal['thp_steam_kw']
        cr.net_ghg_kg_co2e_per_d = net
        cr.net_ghg_t_co2e_per_yr = net * 365 / 1000

        # ── OPEX ──────────────────────────────────────────────────────────
        _base_centrate = base_result.centrate_nh4_kg_per_d if base_result else 0.0
        opex = _opex(config_id, cr.elec_net_kw, cr.wet_cake_t_per_year,
                     cr.centrate_nh4_kg_per_d, ds_total, site,
                     base_centrate_n_kg_d=_base_centrate)
        cr.opex_polymer_per_yr                = opex["polymer"]
        cr.opex_energy_net_per_yr             = opex["energy"]
        cr.opex_disposal_per_yr               = opex["disposal"]
        cr.opex_sidestream_per_yr             = opex["sidestream"]
        cr.opex_sidestream_aeration_per_yr    = opex["aeration_extra"]
        cr.opex_sidestream_alkalinity_per_yr  = opex["alkalinity_extra"]
        cr.opex_sidestream_total_impact_per_yr= opex["sidestream_total"]
        cr.opex_thp_maintenance_per_yr        = opex["thp_maint"]
        cr.opex_total_per_yr                  = opex["total"]

        # ── CAPEX ─────────────────────────────────────────────────────────
        capex_ref = CAPEX_DATA[config_id]
        tds = ds_total
        cr.capex_low_m          = capex_ref["low"]
        cr.capex_high_m         = capex_ref["high"]
        cr.capex_mid_m          = capex_ref["mid"]
        cr.capex_note           = capex_ref["note"]
        cr.capex_scope_summary  = capex_ref.get("scope_summary", "")
        cr.equipment_list       = capex_ref["equipment"]

        configs[config_id] = cr

        if config_id == "base":
            base_result = cr

    # ── Biogas uplift vs base ──────────────────────────────────────────────
    base_biogas = configs.get("base", ConfigResult()).biogas_m3_per_d or 1.0
    base_cake   = configs.get("base", ConfigResult()).wet_cake_t_per_day or 1.0
    for cfg_id, cr in configs.items():
        if cr.included and base_result:
            cr.biogas_uplift_pct = (cr.biogas_m3_per_d - base_biogas) / base_biogas * 100
            cr.cake_vol_reduction_pct = (base_cake - cr.wet_cake_t_per_day) / base_cake * 100
            cr.opex_delta_vs_base_per_yr = (
                cr.opex_total_per_yr - base_result.opex_total_per_yr)
        # Whole-plant delta: subtract the BASE sidestream impacts
        # (base already includes its own aeration/alkalinity cost)
        # then add back THIS config's sidestream impacts vs base
        base_ss_impact = base_result.opex_sidestream_total_impact_per_yr
        cr.opex_delta_whole_plant_per_yr = (
            cr.opex_total_per_yr - base_result.opex_total_per_yr
            # The sidestream costs are already included in opex_total;
            # delta_whole_plant IS the true net saving including sidestream
        )

    # ── Scoring ────────────────────────────────────────────────────────────
    configs = _raw_scores(configs)
    configs = _weighted_totals(configs, driver_weights)

    # ── Narratives ─────────────────────────────────────────────────────────
    base_cr = configs.get("base", ConfigResult())
    for cfg_id, cr in configs.items():
        if cr.included:
            configs[cfg_id] = _narratives(cfg_id, cr, base_cr, site)

    # ── Winner — with tie detection ─────────────────────────────────────────
    included_scored = [(k, v.weighted_score) for k, v in configs.items() if v.included]
    if not included_scored:
        winner_id    = None
        winner_label = ""
        is_tie       = False
        tie_ids      = []
    else:
        top_score  = max(s for _, s in included_scored)
        # Tie threshold: within 2 points (out of 100) — effectively same score
        tie_ids    = [k for k, s in included_scored if abs(s - top_score) <= 2.0]
        is_tie     = len(tie_ids) > 1
        winner_id  = tie_ids[0]   # first alphabetically among tied; report flags tie
        winner_label = CONFIG_LABELS_SHORT.get(winner_id, "") if winner_id else ""

    # Store tie info on result for report use
    # (attached to ComparisonResult below)

    # ── Executive summary ──────────────────────────────────────────────────
    if winner_id:
        wc = configs[winner_id]
        if is_tie:
            tie_labels = " and ".join(CONFIG_LABELS_SHORT.get(k,"") for k in tie_ids)
            exec_summary = (
                f"<b>Effectively tied:</b> {tie_labels} both achieve a weighted score of "
                f"<b>{top_score:.0f}/100</b> under the current driver weightings. "
                "A change in any single driver weighting could shift the recommendation. "
                "The configurations are differentiated below — review the key risks and benefits "
                "for each before making a decision, and consider adjusting driver weightings "
                "to reflect your specific project priorities."
            )
        elif winner_id == "solidstream":
            exec_summary = (
                f"Based on the configured driver weightings, "
                f"<b>{winner_label}</b> achieves the highest weighted score "
                f"({wc.weighted_score:.0f}/100). "
                "SolidStream delivers the best overall balance of dewatering "
                "performance, biosolids quality, and operating cost reduction. "
                "The minimum 15d HRT requirement should be confirmed before "
                "proceeding to detailed design."
            )
        elif winner_id == "pre_thp":
            exec_summary = (
                f"Based on the configured driver weightings, "
                f"<b>{winner_label}</b> achieves the highest weighted score "
                f"({wc.weighted_score:.0f}/100). "
                "Pre-digestion THP delivers the highest energy uplift and "
                "Class A biosolids. Recommended where land application regulation "
                "is tightening or where new digester capacity is planned."
            )
        elif winner_id == "recup":
            exec_summary = (
                f"Based on the configured driver weightings, "
                f"<b>{winner_label}</b> achieves the highest weighted score "
                f"({wc.weighted_score:.0f}/100). "
                "Recuperative thickening offers the best risk-adjusted outcome "
                "at this site — meaningful biogas uplift at moderate CAPEX "
                "without the complexity of THP."
            )
        else:
            exec_summary = (
                f"Based on the configured driver weightings, "
                f"<b>{winner_label}</b> (Base Case) achieves the highest weighted score "
                f"({wc.weighted_score:.0f}/100). "
                "The base case performs best against the current driver mix. "
                "Review driver weightings if regulatory or quality drivers "
                "are expected to tighten."
            )
    else:
        exec_summary = "No configurations included — check selection."
        is_tie = False
        tie_ids = []

    return ComparisonResult(
        configs=configs,
        included_ids=[k for k, v in configs.items() if v.included],
        driver_weights=driver_weights,
        winner_id=winner_id,
        winner_label=winner_label,
        is_tie=is_tie,
        tie_ids=tie_ids,
        executive_summary=exec_summary,
        site=site,
    )
