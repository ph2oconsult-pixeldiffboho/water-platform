"""
mad_v2.py — BioPoint Digestion Engine v2
=========================================
Physics-based mesophilic anaerobic digestion model.

Architecture
------------
feedstock_composition
  → hydrolysis_state
  → digestion_kinetics (stream-specific, HRT + OLR constrained)
  → methane_yield (sludge-type + hydrolysis + severity adjusted)
  → energy_balance
  → dewatering_prediction
  → system_diagnostics (constraint identification)

Design principles
-----------------
- Hydrolysis is a state variable, not an assumption
- VSR = f(HRT, hydrolysis_factor, sludge_type, temperature, OLR)
- Time-constant kinetics (τ formulation): VSR = VSRmax * (1 - exp(-HRT/τ))
- COD/VS varies by sludge type
- CH4 yield adjusted by sludge type, hydrolysis factor, THP severity
- OLR constraint evaluated alongside HRT constraint
- Every output carries a confidence tier (1=full-scale data, 4=literature)

Calibration anchors
-------------------
Mangere conventional:  165 tDS/d, 6.1%TS, 20d HRT → 52% VSR, 62,385 Nm³/d
Mangere THP:           156.8 tDS/d, 10%TS, 20d HRT → 55.7% VSR, 63,151 Nm³/d
Ringsend THP:          12%DS feed, OLR 6 kgVS/m³/d → 62% VSR, 34% cake DS
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from math import exp
from typing import Dict, List, Optional, Tuple


# ── Enumerations ──────────────────────────────────────────────────────────

class SludgeType(str, Enum):
    PRIMARY         = "primary"
    WAS_CONVENTIONAL= "was_conventional"   # BNR/CAS activated sludge
    WAS_AGS         = "was_ags"            # aerobic granular sludge
    MIXED           = "mixed"              # blended PS+WAS
    THP_TREATED     = "thp_treated"        # post-THP
    FAT_TRADE       = "fat_trade"          # high-fat trade waste co-digest

class THPMode(str, Enum):
    NONE            = "none"
    FULL            = "full_thp"           # all feed hydrolysed
    WAS_ONLY        = "was_only"           # secondary stream only
    INTERMEDIATE    = "intermediate"       # retained in engine but not in BioPoint UI
    THERMO_MESO     = "thermo_meso"        # retained in engine but not in BioPoint UI
    THTPAD          = "thtpad"             # retained in engine but not in BioPoint UI
    SOLIDSTREAM     = "solidstream"        # WAS-only THP with hot centrate recycle
    # BioPoint V1 active modes: NONE, FULL, WAS_ONLY, SOLIDSTREAM

class DewateringTech(str, Enum):
    CENTRIFUGE      = "centrifuge"
    BELT_PRESS      = "belt_press"
    FILTER_PRESS    = "filter_press"
    SCREW_PRESS     = "screw_press"

class ConfidenceTier(int, Enum):
    FULL_SCALE      = 1   # validated against multi-year operating data
    PILOT           = 2   # pilot or short-term full-scale
    VENDOR          = 3   # vendor claim or single reference
    LITERATURE      = 4   # literature estimate


# ── Sludge type physical constants ───────────────────────────────────────

COD_VS_FACTORS: Dict[SludgeType, float] = {
    SludgeType.PRIMARY:          2.00,   # lipid-rich, high energy density
    SludgeType.WAS_CONVENTIONAL: 1.40,   # cell-mass dominated
    SludgeType.WAS_AGS:          1.35,   # denser granules, slightly lower COD/VS
    SludgeType.MIXED:            1.65,   # weighted blend
    SludgeType.THP_TREATED:      1.55,   # partially solubilised
    SludgeType.FAT_TRADE:        2.70,   # high-fat co-substrate
}

# N content as fraction of DS (kg N / kg DS)
N_FRACTION: Dict[SludgeType, float] = {
    SludgeType.PRIMARY:          0.030,
    SludgeType.WAS_CONVENTIONAL: 0.085,
    SludgeType.WAS_AGS:          0.080,
    SludgeType.MIXED:            0.055,
    SludgeType.THP_TREATED:      0.085,  # N released to liquor, not reduced in DS
    SludgeType.FAT_TRADE:        0.015,
}

# P content as fraction of DS
P_FRACTION: Dict[SludgeType, float] = {
    SludgeType.PRIMARY:          0.018,
    SludgeType.WAS_CONVENTIONAL: 0.030,
    SludgeType.WAS_AGS:          0.014,  # AGS releases much less soluble P
    SludgeType.MIXED:            0.024,
    SludgeType.THP_TREATED:      0.030,
    SludgeType.FAT_TRADE:        0.005,
}

# EPS-related water binding (g water bound / g DS) — affects dewaterability
EPS_WATER_BINDING: Dict[SludgeType, float] = {
    SludgeType.PRIMARY:          1.5,
    SludgeType.WAS_CONVENTIONAL: 4.5,   # EPS binds 4-5 g water/g (Kopp)
    SludgeType.WAS_AGS:          2.5,   # granular structure, lower EPS
    SludgeType.MIXED:            3.2,
    SludgeType.THP_TREATED:      1.8,   # EPS disrupted by thermal hydrolysis
    SludgeType.FAT_TRADE:        1.0,
}

# Biogas yield per kg VS destroyed (Nm³ TOTAL BIOGAS/kg VS_destroyed)
# Calibrated: Mangere blend (105 PS + 60 WAS) → 0.995 Nm³/kg VS at 20d HRT
# Note: biogas = CH4/0.63 — using biogas as primary avoids CH4 fraction assumption
BIOGAS_YIELD_BASE: Dict[SludgeType, float] = {
    SludgeType.PRIMARY:          1.08,   # lipid-rich → higher gas yield
    SludgeType.WAS_CONVENTIONAL: 0.88,   # protein-rich → lower yield
    SludgeType.WAS_AGS:          0.82,   # granular, similar to WAS
    SludgeType.MIXED:            0.995,  # Mangere calibration anchor
    SludgeType.THP_TREATED:      0.995,  # THP improves accessibility → same as mixed
    SludgeType.FAT_TRADE:        1.35,   # high lipid co-substrate
}

# Digestion kinetics: time constants (τ, days) and VSRmax (fraction)
# VSR = VSRmax * (1 - exp(-HRT/τ))
# Default: spec equations (conservative, suitable for range of plants)
KINETICS: Dict[SludgeType, Tuple[float, float]] = {
    # (tau_days, VSRmax)
    SludgeType.PRIMARY:          (8.0,  0.65),
    SludgeType.WAS_CONVENTIONAL: (18.0, 0.55),
    SludgeType.WAS_AGS:          (20.0, 0.52),
    SludgeType.MIXED:            (12.0, 0.60),
    SludgeType.THP_TREATED:      (10.0, 0.65),  # τ=10d calibrated to Mangere 55.7%@20d
    # Note: spec τ=5d refers to hydrolysis completion; overall digestion τ≈10d
    # (methanogenesis and VFA conversion still require time after hydrolysis)
    SludgeType.FAT_TRADE:        (6.0,  0.75),
}

# Mangere-calibrated preset (more aggressive, validated at 6.1%TS, 20d HRT)
KINETICS_MANGERE: Dict[SludgeType, Tuple[float, float]] = {
    SludgeType.PRIMARY:          (1/0.18, 0.60),   # τ = 5.6d
    SludgeType.WAS_CONVENTIONAL: (1/0.08, 0.50),   # τ = 12.5d
    SludgeType.MIXED:            (1/0.13, 0.55),
    SludgeType.THP_TREATED:      (1/0.27, 0.60),   # τ = 3.7d
    SludgeType.WAS_AGS:          (1/0.085, 0.52),
    SludgeType.FAT_TRADE:        (1/0.14, 0.75),
}


# ── Dataclasses ───────────────────────────────────────────────────────────

@dataclass
class StreamInput:
    """One sludge stream entering digestion."""
    ds_tpd:       float                          # dry solids, t/d
    ts_pct:       float                          # feed concentration, %TS
    vs_pct:       float                          # volatile fraction, %DS
    sludge_type:  SludgeType = SludgeType.MIXED
    temperature_c:float = 15.0                   # feed temperature, °C

    @property
    def vs_tpd(self) -> float:
        return self.ds_tpd * self.vs_pct / 100.0

    @property
    def flow_m3d(self) -> float:
        return self.ds_tpd / max(self.ts_pct / 100.0, 1e-9)

    @property
    def cod_tpd(self) -> float:
        return self.vs_tpd * COD_VS_FACTORS.get(self.sludge_type, 1.65)

    @property
    def n_kg_d(self) -> float:
        return self.ds_tpd * N_FRACTION.get(self.sludge_type, 0.055) * 1000.0

    @property
    def p_kg_d(self) -> float:
        return self.ds_tpd * P_FRACTION.get(self.sludge_type, 0.024) * 1000.0


@dataclass
class DigesterConfig:
    """Digester physical configuration."""
    volume_m3:              float = 64000.0
    ps_volume_m3:           Optional[float] = None   # None = blended
    was_volume_m3:          Optional[float] = None
    temperature_c:          float = 35.0             # mesophilic
    thp_mode:               THPMode = THPMode.NONE
    thp_temperature_c:      float = 165.0
    thp_retention_min:      float = 30.0
    thp_feed_ds_pct:        float = 10.0             # THP feed after pre-dewatering
    dewatering_tech:        DewateringTech = DewateringTech.CENTRIFUGE
    hrt_criterion_d:        float = 15.0             # adopted screening minimum
    olr_max_kg_vs_m3_d:     float = 3.0              # conventional limit
    kinetics_preset:        str = "spec"             # "spec" | "mangere"


@dataclass
class HydrolysisState:
    """
    Hydrolysis effectiveness — the key state variable.
    0.0 = untreated WAS (hydrolysis rate-limiting)
    0.5 = mechanical/chemical enhancement
    0.8 = thermophilic pretreatment
    1.0 = full THP (hydrolysis barrier removed)
    """
    factor:    float = 0.0       # 0.0–1.0
    mechanism: str   = "none"    # description
    confidence:ConfidenceTier = ConfidenceTier.LITERATURE

    @classmethod
    def from_thp_mode(cls, mode: THPMode,
                      temp_c: float = 165.0,
                      time_min: float = 30.0) -> "HydrolysisState":
        sf = _severity_factor(temp_c, time_min)
        if mode == THPMode.NONE:
            return cls(0.0, "conventional MAD — hydrolysis rate-limiting for WAS",
                       ConfidenceTier.FULL_SCALE)
        if mode == THPMode.FULL:
            return cls(min(1.0, 0.95 * sf),
                       f"full THP at {temp_c}°C/{time_min}min — hydrolysis barrier removed",
                       ConfidenceTier.FULL_SCALE)
        if mode == THPMode.WAS_ONLY:
            return cls(min(0.90, 0.88 * sf),
                       f"WAS-only THP — secondary stream hydrolysed",
                       ConfidenceTier.FULL_SCALE)
        if mode == THPMode.SOLIDSTREAM:
            # SolidStream is WAS-only THP with hot centrate recycle — same
            # hydrolysis effectiveness as WAS_ONLY. Previously missing here, so it
            # fell through to factor=0.0 and digested as conventional MAD (A27 fix).
            return cls(min(0.90, 0.88 * sf),
                       "SolidStream (WAS-only THP, hot centrate recycle) — "
                       "secondary stream hydrolysed",
                       ConfidenceTier.FULL_SCALE)
        if mode == THPMode.INTERMEDIATE:
            return cls(min(1.0, 1.02 * sf),
                       "intermediate THP — pre-digested material re-hydrolysed",
                       ConfidenceTier.PILOT)
        if mode in {THPMode.THERMO_MESO, THPMode.THTPAD}:
            return cls(0.75,
                       f"{mode.value} — thermophilic stage provides partial hydrolysis",
                       ConfidenceTier.PILOT)
        return cls(0.0, "unknown", ConfidenceTier.LITERATURE)


@dataclass
class StreamResult:
    """Digestion result for one stream."""
    sludge_type:         SludgeType
    ds_in_tpd:           float
    vs_in_tpd:           float
    hrt_d:               float
    olr_kg_vs_m3_d:      float
    tau_d:               float        # effective time constant
    vsr_max:             float        # effective VSR ceiling
    vsr_frac:            float        # achieved VSR
    vs_destroyed_tpd:    float
    biogas_yield_nm3_kg: float
    ch4_nm3_d:           float
    biogas_nm3_d:        float
    n_released_kg_d:     float
    p_released_kg_d:     float
    hrt_flag:            str
    olr_flag:            str
    hydrolysis_flag:     str
    controlling_constraint: str


@dataclass
class EnergyBalance:
    """Full energy balance — electricity, heat, steam."""
    biogas_nm3_d:            float
    ch4_nm3_d:               float
    biogas_lhv_mj_d:         float
    gross_elec_kw:            float
    net_elec_kw:              float
    net_elec_mwh_yr:          float
    heat_recovered_kw:        float     # CHP jacket heat
    digester_heat_demand_kw:  float
    thp_steam_demand_kw:      float
    thp_steam_kg_h:           float
    external_heat_kw:         float     # deficit requiring boiler
    gas_to_boiler_pct:        float
    net_heat_export_kw:       float
    confidence:               ConfidenceTier


@dataclass
class DewateringResult:
    """Dewatering prediction with EPS and hydrolysis effects."""
    cake_ds_pct:             float
    eps_factor:              float
    polymer_kg_per_tds:      float
    wet_cake_tpd:            float
    wet_cake_tpy:            float
    volume_reduction_pct:    float
    confidence:              ConfidenceTier


@dataclass
class SystemDiagnostics:
    """
    Constraint identification — the primary diagnostic output.
    Each flag: 'ok' | 'warning' | 'limiting'
    """
    hrt_limited:           bool
    olr_limited:           bool
    hydrolysis_limited:    bool
    dewaterability_limited:bool
    sidestream_n_limited:  bool
    energy_limited:        bool
    controlling_constraint:str
    constraint_chain:      List[str]
    intervention_priority: List[str]
    confidence:            ConfidenceTier


@dataclass
class MADv2Result:
    """Complete digestion system result."""
    # Configuration summary
    thp_mode:            str
    total_ds_tpd:        float
    total_vs_tpd:        float
    feed_ts_pct:         float         # effective blended feed TS%
    hydraulic_hrt_d:     float
    olr_kg_vs_m3_d:      float
    # Stream results
    streams:             List[StreamResult]
    # Aggregates
    overall_vsr_pct:     float
    vs_destroyed_tpd:    float
    # Energy
    energy:              EnergyBalance
    # Dewatering
    dewatering:          DewateringResult
    # Nutrients
    nh4_n_kg_d:          float
    soluble_p_kg_d:      float
    centrate_nh4_mg_l:   float
    # Diagnostics
    diagnostics:         SystemDiagnostics
    # Calibration
    kinetics_preset:     str
    confidence_overall:  ConfidenceTier


# ── Physics functions ─────────────────────────────────────────────────────

def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _severity_index(temp_c: float, time_min: float) -> float:
    """THP severity index: SI = t * exp((T-100)/14.75)"""
    return max(time_min, 0.0) * exp((temp_c - 100.0) / 14.75)


def _severity_factor(temp_c: float, time_min: float) -> float:
    """Normalised severity factor vs reference (165°C, 30 min)."""
    ref = _severity_index(165.0, 30.0)
    raw = _severity_index(temp_c, time_min) / max(ref, 1e-9)
    # Cap: high severity can produce refractory Maillard products
    return _clip(raw ** 0.18, 0.85, 1.08)


def _effective_kinetics(stream: StreamInput,
                         hydrolysis: HydrolysisState,
                         cfg: DigesterConfig) -> Tuple[float, float]:
    """
    Return effective (tau_d, vsr_max) incorporating:
    - sludge type base kinetics
    - hydrolysis factor (0–1)
    - temperature correction (Arrhenius proxy)
    - kinetics preset
    """
    preset = KINETICS_MANGERE if cfg.kinetics_preset == "mangere" else KINETICS
    tau_base, vsr_max_base = preset.get(
        stream.sludge_type, (12.0, 0.55))

    # Hydrolysis improvement: only reduces τ for WAS streams
    # PRIMARY sludge is digestion-limited (lipid/carb hydrolyse readily)
    # WAS is hydrolysis-limited (EPS and cell wall) — THP removes this barrier
    was_stream = stream.sludge_type in {SludgeType.WAS_CONVENTIONAL,
                                        SludgeType.WAS_AGS, SludgeType.MIXED}
    is_treated = stream.sludge_type == SludgeType.THP_TREATED
    hydro_tau_reduction = (1.0 - 0.50 * hydrolysis.factor) if was_stream else 1.0
    hydro_vsr_uplift    = (0.08 * hydrolysis.factor) if was_stream else 0.0

    tau_eff    = tau_base * hydro_tau_reduction
    vsr_max_eff= _clip(vsr_max_base + hydro_vsr_uplift, 0.10, 0.75)

    # Temperature correction: Q10 ≈ 2 for AD (doubles per 10°C)
    # Reference 35°C mesophilic
    temp_factor = 2.0 ** ((cfg.temperature_c - 35.0) / 10.0)
    tau_eff = tau_eff / max(temp_factor, 0.1)

    return tau_eff, vsr_max_eff


def _vsr(hrt_d: float, tau_d: float, vsr_max: float,
          olr: float, olr_max: float) -> float:
    """
    VSR = VSRmax * (1 - exp(-HRT/τ)) with OLR inhibition.
    OLR above limit applies a progressive VSR penalty.
    """
    base_vsr = vsr_max * (1.0 - exp(-max(hrt_d, 0) / max(tau_d, 0.1)))
    # OLR inhibition: >10% above limit → progressive penalty
    olr_ratio = olr / max(olr_max, 0.1)
    if olr_ratio > 1.0:
        olr_penalty = 0.05 * (olr_ratio - 1.0)   # 5% VSR per unit OLR excess
        base_vsr = max(base_vsr - olr_penalty, 0.10)
    return _clip(base_vsr, 0.0, vsr_max)


def _biogas_yield(stream: StreamInput,
                  hydrolysis: HydrolysisState,
                  cfg: DigesterConfig) -> float:
    """
    Biogas yield per kg VS destroyed (Nm³ total biogas/kg VS_destroyed).
    Uses BIOGAS (not CH4) as primary — avoids CH4 fraction assumption.
    Calibration: Mangere blend → 0.995 Nm³/kg VS at 20d HRT.
    Adjusted by hydrolysis factor and THP severity.
    No double-counting: THP_TREATED sludge already has high base yield.
    """
    base = BIOGAS_YIELD_BASE.get(stream.sludge_type, 0.995)
    # Hydrolysis uplift only for untreated streams
    is_pre_treated = stream.sludge_type == SludgeType.THP_TREATED
    hydro_adj = 1.0 if is_pre_treated else (1.0 + 0.06 * hydrolysis.factor)
    # THP severity: marginal uplift (already captured in base for THP_TREATED)
    sf = _severity_factor(cfg.thp_temperature_c, cfg.thp_retention_min)
    thp_adj = sf if (cfg.thp_mode != THPMode.NONE and not is_pre_treated) else 1.0
    return base * hydro_adj * thp_adj


def _stream_hrt(stream: StreamInput,
                stream_vol_m3: Optional[float],
                total_vol_m3: float,
                total_flow_m3d: float,
                blended: bool) -> float:
    if blended or stream_vol_m3 is None:
        return total_vol_m3 / max(total_flow_m3d, 1e-9)
    return stream_vol_m3 / max(stream.flow_m3d, 1e-9)


def _digester_heat_demand(streams: List[StreamInput],
                           cfg: DigesterConfig) -> float:
    """Heat to raise feed to digestion temperature + losses (kW)."""
    cp_water = 4.18   # kJ/kg/°C
    total_flow_m3d = sum(s.flow_m3d for s in streams)
    feed_temp = sum(s.temperature_c * s.flow_m3d for s in streams) / max(total_flow_m3d, 1e-9)
    dt = cfg.temperature_c - feed_temp
    sensible_kw = total_flow_m3d * 1000 * cp_water * dt / 86400
    # Losses: ~15% of sensible heat for insulated digesters
    return max(sensible_kw * 1.15, 0.0)


def _thp_steam_demand(streams: List[StreamInput],
                       cfg: DigesterConfig,
                       thp_ds_tpd: float) -> Tuple[float, float]:
    """
    THP steam demand using reference-based model.
    Calibration: Mangere → ~900 kg steam/tDS to THP (6,111 kg/h at 165 tDS/d).
    Adjusted for feed temperature and DS concentration (lower DS = more water to heat).
    Returns (steam_kw, steam_kg_h).
    """
    if cfg.thp_mode == THPMode.NONE or thp_ds_tpd <= 0:
        return 0.0, 0.0
    # Reference: 900 kg steam per tDS at 165°C / 30 min / 20°C feed / 16.5%DS
    steam_kg_per_tds_ref = 900.0
    feed_temp  = sum(s.temperature_c * s.flow_m3d for s in streams) / max(
                 sum(s.flow_m3d for s in streams), 1e-9)
    # Temperature correction
    temp_factor = 1.0 + 0.006 * (20.0 - feed_temp)
    # DS concentration correction (lower DS% → more water → more steam)
    ds_factor   = (0.165 / max(cfg.thp_feed_ds_pct / 100.0, 1e-9)) ** 0.25
    # Severity factor
    sf = _severity_factor(cfg.thp_temperature_c, cfg.thp_retention_min)
    steam_kg_h  = thp_ds_tpd * steam_kg_per_tds_ref * temp_factor * ds_factor * sf / 24.0
    steam_kw    = steam_kg_h * 0.63
    return steam_kw, steam_kg_h


def _energy_balance(streams: List[StreamInput],
                     biogas_nm3_d: float,
                     ch4_nm3_d: float,
                     digester_heat_kw: float,
                     thp_steam_kw: float,
                     thp_steam_kg_h: float,
                     cfg: DigesterConfig) -> EnergyBalance:
    """Full energy balance: electricity + heat + steam."""
    # Gas energy
    ch4_lhv_mj_nm3 = 35.8
    biogas_lhv_mj_d = ch4_nm3_d * ch4_lhv_mj_nm3
    # CHP
    chp_elec_eff  = 0.38
    chp_heat_eff  = 0.45   # recoverable heat from jacket + exhaust
    parasitic_frac= 0.12   # plant auxiliary load
    gross_elec_kw = ch4_nm3_d * 9.97 * chp_elec_eff / 24.0
    net_elec_kw   = gross_elec_kw * (1 - parasitic_frac)
    heat_recovered= gross_elec_kw * (chp_heat_eff / chp_elec_eff)
    # Heat balance
    total_heat_demand = digester_heat_kw + thp_steam_kw
    heat_surplus = heat_recovered - total_heat_demand
    external_kw  = max(0.0, -heat_surplus)
    # Gas to boiler if heat deficit
    boiler_eff    = 0.85
    ch4_lhv_kw_nm3= 9.97  # kWh per Nm³
    gas_to_boiler = external_kw * 24.0 / max(
        ch4_nm3_d * ch4_lhv_kw_nm3 * boiler_eff, 1e-9)
    gas_to_boiler_pct = _clip(gas_to_boiler, 0.0, 1.0)
    heat_export = max(0.0, heat_surplus)

    return EnergyBalance(
        biogas_nm3_d           = biogas_nm3_d,
        ch4_nm3_d              = ch4_nm3_d,
        biogas_lhv_mj_d        = biogas_lhv_mj_d,
        gross_elec_kw          = round(gross_elec_kw, 1),
        net_elec_kw            = round(net_elec_kw, 1),
        net_elec_mwh_yr        = round(net_elec_kw * 8760 / 1000, 0),
        heat_recovered_kw      = round(heat_recovered, 1),
        digester_heat_demand_kw= round(digester_heat_kw, 1),
        thp_steam_demand_kw    = round(thp_steam_kw, 1),
        thp_steam_kg_h         = round(thp_steam_kg_h, 0),
        external_heat_kw       = round(external_kw, 1),
        gas_to_boiler_pct      = round(gas_to_boiler_pct * 100, 1),
        net_heat_export_kw     = round(heat_export, 1),
        confidence             = ConfidenceTier.FULL_SCALE,
    )


def _dewatering(streams: List[StreamInput],
                hydrolysis: HydrolysisState,
                overall_vsr: float,
                residual_ds_tpd: float,
                cfg: DigesterConfig) -> DewateringResult:
    """
    Cake DS prediction incorporating EPS and hydrolysis effects.
    cake_ds = f(VSR, EPS_factor, hydrolysis_factor, sludge_type, dewatering_tech)

    Calibration anchors:
    - Conventional AD: 20-25% DS (Mangere reference)
    - THP full (20d):  30% DS (Mangere 2015)
    - Ringsend THP:    34% DS (12%DS feed, high OLR)
    - SolidStream:     38-43% DS (Cambi guarantee)
    """
    ds_total = sum(s.ds_tpd for s in streams)
    # EPS-weighted water binding
    eps_wb = sum(s.ds_tpd * EPS_WATER_BINDING.get(s.sludge_type, 3.2)
                 for s in streams) / max(ds_total, 1e-9)
    # Normalised EPS factor (1.0 = conventional WAS baseline)
    eps_factor = eps_wb / 4.5

    # Base cake DS from dewatering technology
    tech_base = {
        DewateringTech.CENTRIFUGE:   20.0,
        DewateringTech.BELT_PRESS:   18.0,
        DewateringTech.FILTER_PRESS: 28.0,
        DewateringTech.SCREW_PRESS:  16.0,
    }.get(cfg.dewatering_tech, 20.0)

    # Hydrolysis improvement: THP disrupts EPS → better dewatering
    # Full THP (factor=1.0) → +10-15pp improvement on base
    if cfg.thp_mode == THPMode.SOLIDSTREAM:
        # SolidStream hot centrate recycle maintains dewaterability at shorter HRT
        hydro_improvement = 18.0
    elif cfg.thp_mode in {THPMode.FULL, THPMode.WAS_ONLY,
                           THPMode.INTERMEDIATE, THPMode.THTPAD}:
        # THP dewaterability curve (Mangere calibrated):
        # potential 46%DS undigested → falls through digestion → plateaus ~30%
        from math import exp as _e
        # Effective HRT = weighted average of stream HRTs
        total_vol = cfg.volume_m3
        total_flow = sum(s.flow_m3d for s in streams)
        eff_hrt = total_vol / max(total_flow, 1e-9)
        # THP pre-dewatering is to ~10-16%DS → higher DS → longer HRT from smaller volume
        # Use digester config for feed DS
        thp_feed_hrt = (cfg.thp_feed_ds_pct / 10.0) * eff_hrt
        plateau_loss = 16.5
        loss = plateau_loss * (1.0 - _e(-0.28 * max(thp_feed_hrt, 0)))
        cake_ds_thp = 46.0 - loss
        # Mode adjustments
        if cfg.thp_mode == THPMode.WAS_ONLY:
            cake_ds_thp += 2.0   # secondary only → slightly better
        elif cfg.thp_mode == THPMode.INTERMEDIATE:
            cake_ds_thp += 1.0
        return DewateringResult(
            cake_ds_pct          = round(_clip(cake_ds_thp, 28.0, 38.0), 1),
            eps_factor           = round(eps_factor, 2),
            polymer_kg_per_tds   = round(_polymer_demand(eps_factor, hydrolysis, cfg), 2),
            wet_cake_tpd         = round(residual_ds_tpd / (_clip(cake_ds_thp,28,38)/100), 1),
            wet_cake_tpy         = round(residual_ds_tpd / (_clip(cake_ds_thp,28,38)/100) * 365, 0),
            volume_reduction_pct = round((1 - residual_ds_tpd / max(ds_total, 1e-9)) * 100, 1),
            confidence           = ConfidenceTier.FULL_SCALE,
        )
    else:
        hydro_improvement = 0.0

    # EPS penalty: higher EPS → worse dewatering
    eps_penalty = (eps_factor - 1.0) * 3.0   # -3pp per unit EPS above baseline
    # VSR improvement: higher VSR → lower residual VS → marginally better dewatering
    vsr_adj = (overall_vsr - 0.45) * 5.0     # +5pp per 10pp VSR above 45%
    cake_ds = tech_base + hydro_improvement - eps_penalty + vsr_adj
    cake_ds = _clip(cake_ds, 14.0, 42.0)

    wet_cake = residual_ds_tpd / max(cake_ds / 100.0, 1e-9)
    return DewateringResult(
        cake_ds_pct          = round(cake_ds, 1),
        eps_factor           = round(eps_factor, 2),
        polymer_kg_per_tds   = round(_polymer_demand(eps_factor, hydrolysis, cfg), 2),
        wet_cake_tpd         = round(wet_cake, 1),
        wet_cake_tpy         = round(wet_cake * 365, 0),
        volume_reduction_pct = round((1 - residual_ds_tpd / max(ds_total, 1e-9)) * 100, 1),
        confidence           = ConfidenceTier.LITERATURE,
    )


def _polymer_demand(eps_factor: float,
                    hydrolysis: HydrolysisState,
                    cfg: DigesterConfig) -> float:
    """
    Polymer demand (kg active polymer per tDS dewatered).
    Influenced by EPS, hydrolysis extent, and dewatering technology.
    """
    # Base by dewatering tech (kg/tDS)
    tech_base = {
        DewateringTech.CENTRIFUGE:   8.0,
        DewateringTech.BELT_PRESS:   5.0,
        DewateringTech.FILTER_PRESS: 3.0,
        DewateringTech.SCREW_PRESS:  6.0,
    }.get(cfg.dewatering_tech, 8.0)
    # EPS increases polymer demand
    eps_multiplier = 1.0 + 0.4 * (eps_factor - 1.0)
    # THP reduces EPS → reduces polymer demand
    hydro_reduction = 1.0 - 0.25 * hydrolysis.factor
    return _clip(tech_base * eps_multiplier * hydro_reduction, 1.0, 25.0)


def _nutrient_release(streams: List[StreamInput],
                       overall_vsr: float,
                       hydrolysis: HydrolysisState,
                       cfg: DigesterConfig) -> Tuple[float, float]:
    """
    NH4-N and soluble P released to centrate (kg/d).
    Release fraction = f(VSR, hydrolysis, sludge type).
    """
    total_n = sum(s.n_kg_d for s in streams)
    total_p = sum(s.p_kg_d for s in streams)
    # N release fraction. Recalibrated against measured Mangere/Malabar centrate
    # NH4-N anchors (A25): the prior 0.30 + 0.22*VSR (+0.04 THP) ran ~10-13% high
    # versus measured. Lowering the intercept to 0.27 and the THP solubilisation
    # adder to 0.02 centres the two directly-runnable anchors (Mangere
    # conventional, Mangere 2015 full THP) to within ~2% of measured.
    n_release = 0.27 + 0.22 * overall_vsr
    if cfg.thp_mode != THPMode.NONE:
        n_release += 0.02   # THP extra solubilisation (measured effect is small)
    n_release = _clip(n_release, 0.25, 0.72)
    nh4_kg_d  = total_n * n_release
    # P release — reduced for AGS sludge
    ags_frac = sum(s.ds_tpd for s in streams
                   if s.sludge_type == SludgeType.WAS_AGS) / max(
               sum(s.ds_tpd for s in streams), 1e-9)
    p_release = (0.42 + 0.25 * overall_vsr) * (1.0 - 0.45 * ags_frac)
    p_release = _clip(p_release, 0.15, 0.80)
    sol_p_kg_d= total_p * p_release
    return nh4_kg_d, sol_p_kg_d


def _diagnostics(streams: List[StreamInput],
                  stream_results: List[StreamResult],
                  energy: EnergyBalance,
                  dewatering: DewateringResult,
                  nh4_kg_d: float,
                  cfg: DigesterConfig,
                  hydrolysis: HydrolysisState) -> SystemDiagnostics:
    """Identify the controlling constraint and build the constraint chain."""
    flags = {}

    # HRT
    was_hrts = [r.hrt_d for r in stream_results
                if r.sludge_type in {SludgeType.WAS_CONVENTIONAL, SludgeType.WAS_AGS}]
    min_was_hrt = min(was_hrts) if was_hrts else min(r.hrt_d for r in stream_results)
    flags["hrt"] = min_was_hrt < cfg.hrt_criterion_d

    # OLR
    total_vs = sum(s.vs_tpd for s in streams)
    actual_olr = total_vs * 1000 / max(cfg.volume_m3, 1e-9)
    flags["olr"] = actual_olr > cfg.olr_max_kg_vs_m3_d

    # Hydrolysis: is WAS hydrolysis the limiting step?
    flags["hydrolysis"] = (
        hydrolysis.factor < 0.3 and
        any(s.sludge_type in {SludgeType.WAS_CONVENTIONAL, SludgeType.WAS_AGS}
            for s in streams)
    )

    # Dewaterability
    flags["dewatering"] = dewatering.cake_ds_pct < 22.0

    # Sidestream N: >15% of plant TKN is significant
    plant_n_approx = sum(s.n_kg_d for s in streams)
    flags["sidestream_n"] = nh4_kg_d / max(plant_n_approx, 1e-9) > 0.40

    # Energy: net import
    flags["energy"] = energy.net_elec_kw < 0

    # Build constraint chain in priority order
    chain = []
    interventions = []
    controlling = "none identified"

    if flags["hrt"]:
        controlling = f"WAS HRT deficiency ({min_was_hrt:.1f}d < {cfg.hrt_criterion_d:.0f}d)"
        chain.append(controlling)
        chain.append("→ WAS hydrolysis is rate-limiting (slow k_WAS)")
        chain.append("→ Co-digestion suppression compounds WAS constraint")
        interventions.append("1. WAS pre-thickening to increase TS% and extend HRT")
        interventions.append("2. Optimised MAD: volume redistribution to WAS stream")
        interventions.append("3. Evaluate separate PS/WAS digestion")
        interventions.append("4. Only then evaluate THP")
    elif flags["hydrolysis"]:
        controlling = "WAS hydrolysis rate-limiting (no pre-treatment)"
        chain.append(controlling)
        chain.append("→ EPS and cell-wall structure resist enzymatic attack")
        chain.append("→ Rate constant τ_WAS=18d — most benefit before 15d HRT")
        interventions.append("1. Evaluate THP to remove hydrolysis barrier")
        interventions.append("2. Mechanical/ultrasonic pre-treatment (partial benefit)")
        interventions.append("3. Separate PS/WAS digestion to optimise each stream")
    elif flags["olr"]:
        controlling = f"OLR constraint ({actual_olr:.1f} > {cfg.olr_max_kg_vs_m3_d:.1f} kgVS/m³/d)"
        chain.append(controlling)
        chain.append("→ High VS loading risks VFA accumulation, pH drop, foaming")
        chain.append("→ OLR constraint may be more binding than HRT constraint")
        interventions.append("1. Increase digester volume")
        interventions.append("2. THP: allows OLR up to 6 kgVS/m³/d (Ringsend reference)")
        interventions.append("3. Reduce feed VS concentration")
    else:
        controlling = "digestion configuration sub-optimal (architecture opportunity)"
        chain.append("WAS HRT and OLR within criteria")
        chain.append("→ Co-digestion suppression still active (PS and WAS blended)")
        chain.append("→ Separate digestion may recover 13-33% additional biogas")
        interventions.append("1. Evaluate separate PS/WAS digestion")
        interventions.append("2. Paired BMP testing to quantify co-digestion suppression")

    if flags["sidestream_n"]:
        chain.append("→ High centrate NH4-N return load")
        interventions.append("Parallel: centrate characterisation + PN/A feasibility")
    if flags["energy"]:
        chain.append("→ Net electricity import — plant not energy self-sufficient")
        interventions.append("Parallel: biogas capture and CHP efficiency audit")

    return SystemDiagnostics(
        hrt_limited           = flags["hrt"],
        olr_limited           = flags["olr"],
        hydrolysis_limited    = flags["hydrolysis"],
        dewaterability_limited= flags["dewatering"],
        sidestream_n_limited  = flags["sidestream_n"],
        energy_limited        = flags["energy"],
        controlling_constraint= controlling,
        constraint_chain      = chain,
        intervention_priority = interventions,
        confidence            = ConfidenceTier.FULL_SCALE,
    )


# ── Main entry point ──────────────────────────────────────────────────────

def run_mad_v2(streams: List[StreamInput],
               cfg: DigesterConfig) -> MADv2Result:
    """
    Run the v2 digestion engine.
    streams: list of StreamInput (one per sludge stream)
    cfg:     DigesterConfig
    """
    if not streams:
        raise ValueError("At least one stream required")

    # Hydrolysis state from THP mode
    hydrolysis = HydrolysisState.from_thp_mode(
        cfg.thp_mode, cfg.thp_temperature_c, cfg.thp_retention_min)

    # THP: which streams go to hydrolysis
    thp_ds_tpd = 0.0
    if cfg.thp_mode == THPMode.FULL:
        thp_ds_tpd = sum(s.ds_tpd for s in streams) * 0.95
    elif cfg.thp_mode in {THPMode.WAS_ONLY, THPMode.INTERMEDIATE,
                           THPMode.THTPAD, THPMode.SOLIDSTREAM}:
        thp_ds_tpd = sum(s.ds_tpd for s in streams
                         if s.sludge_type in {SludgeType.WAS_CONVENTIONAL,
                                               SludgeType.WAS_AGS}) * 0.95

    # Hydraulics
    total_flow_m3d = sum(s.flow_m3d for s in streams)
    # THP pre-dewaters feed → reduces hydraulic volume
    if cfg.thp_mode != THPMode.NONE and cfg.thp_feed_ds_pct > 0:
        # THP fraction flows at higher DS%
        thp_frac_ds = thp_ds_tpd / max(sum(s.ds_tpd for s in streams), 1e-9)
        thp_flow_red = thp_frac_ds * total_flow_m3d * (
            1.0 - sum(s.ts_pct/100 for s in streams) / len(streams) /
            (cfg.thp_feed_ds_pct / 100.0))
        total_flow_m3d = max(total_flow_m3d - thp_flow_red, total_flow_m3d * 0.3)

    hydraulic_hrt = cfg.volume_m3 / max(total_flow_m3d, 1e-9)
    blended = (cfg.ps_volume_m3 is None or cfg.was_volume_m3 is None)

    # Per-stream results
    total_ds = sum(s.ds_tpd for s in streams)
    total_vs = sum(s.vs_tpd for s in streams)
    total_vs_destroyed = 0.0
    total_ch4 = 0.0
    stream_results = []
    olr_total = total_vs * 1000 / max(cfg.volume_m3, 1e-9)

    for s in streams:
        # Volume allocation for separate digestion
        if not blended:
            if s.sludge_type == SludgeType.PRIMARY and cfg.ps_volume_m3:
                stream_vol = cfg.ps_volume_m3
            elif s.sludge_type in {SludgeType.WAS_CONVENTIONAL,
                                    SludgeType.WAS_AGS} and cfg.was_volume_m3:
                stream_vol = cfg.was_volume_m3
            else:
                stream_vol = None
        else:
            stream_vol = None

        hrt = _stream_hrt(s, stream_vol, cfg.volume_m3,
                           total_flow_m3d, blended)

        # Effective kinetics
        tau, vsr_max = _effective_kinetics(s, hydrolysis, cfg)
        olr_stream   = s.vs_tpd * 1000 / max(
            stream_vol or cfg.volume_m3, 1e-9)
        achieved_vsr = _vsr(hrt, tau, vsr_max, olr_stream,
                             cfg.olr_max_kg_vs_m3_d)

        vs_dest = s.vs_tpd * achieved_vsr
        bg_y    = _biogas_yield(s, hydrolysis, cfg)
        bg_d    = vs_dest * 1000 * bg_y    # Nm³/d total biogas
        ch4_d   = bg_d * 0.63              # 63% CH4 in biogas

        total_vs_destroyed += vs_dest
        total_ch4          += ch4_d

        # Flags
        hrt_flag = ("below criterion" if hrt < cfg.hrt_criterion_d
                    else "meets criterion")
        olr_flag = ("above limit" if olr_stream > cfg.olr_max_kg_vs_m3_d
                    else "within limit")
        hydro_flag = ("hydrolysis rate-limiting" if hydrolysis.factor < 0.3
                       and s.sludge_type in {SludgeType.WAS_CONVENTIONAL,
                                              SludgeType.WAS_AGS}
                       else "hydrolysis adequate")
        constraint = ("HRT" if hrt < cfg.hrt_criterion_d
                      else "OLR" if olr_stream > cfg.olr_max_kg_vs_m3_d
                      else "hydrolysis" if hydrolysis.factor < 0.3
                      else "none")

        stream_results.append(StreamResult(
            sludge_type          = s.sludge_type,
            ds_in_tpd            = round(s.ds_tpd, 1),
            vs_in_tpd            = round(s.vs_tpd, 1),
            hrt_d                = round(hrt, 1),
            olr_kg_vs_m3_d       = round(olr_stream, 2),
            tau_d                = round(tau, 1),
            vsr_max              = round(vsr_max, 3),
            vsr_frac             = round(achieved_vsr, 3),
            vs_destroyed_tpd     = round(vs_dest, 2),
            biogas_yield_nm3_kg  = round(bg_y, 3),
            ch4_nm3_d            = round(ch4_d, 0),
            biogas_nm3_d         = round(bg_d, 0),
            n_released_kg_d      = round(s.n_kg_d * (0.30 + 0.22*achieved_vsr), 0),
            p_released_kg_d      = round(s.p_kg_d * (0.42 + 0.25*achieved_vsr), 0),
            hrt_flag             = hrt_flag,
            olr_flag             = olr_flag,
            hydrolysis_flag      = hydro_flag,
            controlling_constraint=constraint,
        ))

    # Aggregates
    overall_vsr = total_vs_destroyed / max(total_vs, 1e-9)
    total_biogas = total_ch4 / 0.63
    residual_ds  = total_ds - total_vs_destroyed

    # Energy
    dig_heat    = _digester_heat_demand(streams, cfg)
    thp_steam_kw, thp_steam_kg_h = _thp_steam_demand(streams, cfg, thp_ds_tpd)
    energy = _energy_balance(streams, total_biogas, total_ch4,
                              dig_heat, thp_steam_kw, thp_steam_kg_h, cfg)

    # Dewatering
    dew = _dewatering(streams, hydrolysis, overall_vsr, residual_ds, cfg)

    # Nutrients
    nh4, sol_p = _nutrient_release(streams, overall_vsr, hydrolysis, cfg)
    # Centrate (dewatering liquor) flow = sludge-to-dewatering flow minus the
    # dewatered cake volume. Previously this used half the wet-CAKE mass as the
    # liquid flow, which made the concentration ~10x too high (cake ~= 1 t/m3,
    # and the cake stream is far smaller than the centrate stream). Use the
    # digested-sludge throughput (total_flow_m3d, already THP-adjusted) minus the
    # cake volume, floored to avoid blow-up at extreme dewatering.
    wet_cake_m3d = residual_ds / max(dew.cake_ds_pct / 100.0, 1e-9)   # cake ~1 t/m3
    reject_flow = max(total_flow_m3d - wet_cake_m3d, total_flow_m3d * 0.1)
    centrate_nh4 = nh4 * 1000 / max(reject_flow, 1e-9)

    # Diagnostics
    diag = _diagnostics(streams, stream_results, energy, dew,
                         nh4, cfg, hydrolysis)

    # Effective feed TS%
    eff_ts = total_ds / max(total_flow_m3d, 1e-9) * 100

    return MADv2Result(
        thp_mode            = cfg.thp_mode.value,
        total_ds_tpd        = round(total_ds, 1),
        total_vs_tpd        = round(total_vs, 1),
        feed_ts_pct         = round(eff_ts, 1),
        hydraulic_hrt_d     = round(hydraulic_hrt, 1),
        olr_kg_vs_m3_d      = round(olr_total, 2),
        streams             = stream_results,
        overall_vsr_pct     = round(overall_vsr * 100, 1),
        vs_destroyed_tpd    = round(total_vs_destroyed, 2),
        energy              = energy,
        dewatering          = dew,
        nh4_n_kg_d          = round(nh4, 0),
        soluble_p_kg_d      = round(sol_p, 0),
        centrate_nh4_mg_l   = round(centrate_nh4, 0),
        diagnostics         = diag,
        kinetics_preset     = cfg.kinetics_preset,
        confidence_overall  = ConfidenceTier.FULL_SCALE
            if cfg.kinetics_preset == "mangere"
            else ConfidenceTier.PILOT,
    )


# ── Calibration validation ────────────────────────────────────────────────

def validate_calibration() -> None:
    """Validate engine against known calibration anchors."""
    print("MADv2 CALIBRATION VALIDATION")
    print("=" * 65)

    # ── Mangere conventional ──────────────────────────────────────────────
    streams_mg_conv = [
        StreamInput(105.0, 6.1, 75.0, SludgeType.PRIMARY,          15.0),
        StreamInput( 60.0, 6.1, 70.0, SludgeType.WAS_CONVENTIONAL, 15.0),
    ]
    cfg_mg_conv = DigesterConfig(
        volume_m3=54000, temperature_c=35,
        thp_mode=THPMode.NONE, hrt_criterion_d=15,
        olr_max_kg_vs_m3_d=3.0, kinetics_preset="spec",
    )
    r = run_mad_v2(streams_mg_conv, cfg_mg_conv)
    print(f"\nMangere conventional (target: 52% VSR, 62,385 Nm³/d biogas)")
    print(f"  HRT:    {r.hydraulic_hrt_d:.1f}d  OLR: {r.olr_kg_vs_m3_d:.2f} kgVS/m³/d")
    print(f"  VSR:    {r.overall_vsr_pct:.1f}%  {'✓' if abs(r.overall_vsr_pct-52)<5 else '⚠'}")
    print(f"  Biogas: {r.energy.biogas_nm3_d:,.0f} Nm³/d  {'✓' if abs(r.energy.biogas_nm3_d-62385)<8000 else '⚠'}")
    print(f"  Cake:   {r.dewatering.cake_ds_pct:.1f}% DS")
    print(f"  NH4-N:  {r.nh4_n_kg_d:,.0f} kg/d")
    print(f"  Net elec: {r.energy.net_elec_kw:,.0f} kW")
    print(f"  Constraint: {r.diagnostics.controlling_constraint}")

    # ── Mangere THP ───────────────────────────────────────────────────────
    # Feed: PS (conventional kinetics, THP boosts hydrolysis_factor)
    #       WAS (kinetics improved by THP via hydrolysis_factor=1.0)
    # Note: use PRIMARY/WAS_CONVENTIONAL sludge types — the THP mode
    # applies hydrolysis_factor automatically via HydrolysisState
    streams_mg_thp = [
        StreamInput(105.0, 10.0, 75.0, SludgeType.PRIMARY,          14.0),
        StreamInput( 51.8, 10.0, 70.0, SludgeType.WAS_CONVENTIONAL, 14.0),
    ]
    cfg_mg_thp = DigesterConfig(
        volume_m3=31350, temperature_c=35,
        thp_mode=THPMode.FULL, thp_temperature_c=165, thp_retention_min=30,
        thp_feed_ds_pct=10.0, hrt_criterion_d=15,
        olr_max_kg_vs_m3_d=6.0, kinetics_preset="spec",
    )
    r2 = run_mad_v2(streams_mg_thp, cfg_mg_thp)
    print(f"\nMangere THP (target: 55.7% VSR, 63,151 Nm³/d, 30% cake DS)")
    print(f"  HRT:    {r2.hydraulic_hrt_d:.1f}d  OLR: {r2.olr_kg_vs_m3_d:.2f} kgVS/m³/d")
    print(f"  VSR:    {r2.overall_vsr_pct:.1f}%  {'✓' if abs(r2.overall_vsr_pct-55.7)<5 else '⚠'}")
    print(f"  Biogas: {r2.energy.biogas_nm3_d:,.0f} Nm³/d  {'✓' if abs(r2.energy.biogas_nm3_d-63151)<8000 else '⚠'}")
    print(f"  Cake:   {r2.dewatering.cake_ds_pct:.1f}% DS  {'✓' if abs(r2.dewatering.cake_ds_pct-30)<4 else '⚠'}")
    print(f"  Steam:  {r2.energy.thp_steam_kg_h:,.0f} kg/h  (target ~6,111)")
    print(f"  NH4-N:  {r2.nh4_n_kg_d:,.0f} kg/d  (target ~3,134)")
    print(f"  Constraint: {r2.diagnostics.controlling_constraint}")

    # ── Ringsend THP ─────────────────────────────────────────────────────
    streams_ringsend = [
        StreamInput( 80.0, 12.0, 72.0, SludgeType.PRIMARY,          10.0),
        StreamInput(100.0, 12.0, 68.0, SludgeType.WAS_CONVENTIONAL, 10.0),
    ]
    cfg_ringsend = DigesterConfig(
        volume_m3=30000, temperature_c=37,
        thp_mode=THPMode.FULL, thp_temperature_c=165, thp_retention_min=30,
        thp_feed_ds_pct=12.0, hrt_criterion_d=15,
        olr_max_kg_vs_m3_d=6.0, kinetics_preset="spec",
    )
    r3 = run_mad_v2(streams_ringsend, cfg_ringsend)
    print(f"\nRingsend THP (target: 62% VSR, 34% cake DS, OLR ~6 kgVS/m³/d)")
    print(f"  HRT:    {r3.hydraulic_hrt_d:.1f}d  OLR: {r3.olr_kg_vs_m3_d:.2f} kgVS/m³/d")
    print(f"  VSR:    {r3.overall_vsr_pct:.1f}%  {'✓' if abs(r3.overall_vsr_pct-62)<6 else '⚠'}")
    print(f"  Cake:   {r3.dewatering.cake_ds_pct:.1f}% DS  {'✓' if abs(r3.dewatering.cake_ds_pct-34)<4 else '⚠'}")
    print(f"  Polymer:{r3.dewatering.polymer_kg_per_tds:.1f} kg/tDS")
    print(f"  Constraint: {r3.diagnostics.controlling_constraint}")

    # ── ETP parameters ────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print("ETP COMPARISON (PS=120.7 tDS/d, WAS=98.8 tDS/d, 64,000m³)")
    etp_ps  = StreamInput(120.7, 4.0, 75.0, SludgeType.PRIMARY,          15.0)
    etp_was = StreamInput( 98.8, 4.0, 70.0, SludgeType.WAS_CONVENTIONAL, 15.0)
    print(f"\n{'Mode':22s} | {'HRT':>5} | {'OLR':>5} | {'VSR':>5} | {'Biogas':>8} | {'Cake':>5} | {'Constraint'}")
    print("-" * 85)
    for label, mode, ps_v, was_v, olr_lim, thp_ds in [
        ("Conv AD (blended)",  THPMode.NONE,    None,  None,  3.0, 4.0),
        ("Sep PS/WAS",         THPMode.NONE,    35200, 28800, 3.0, 4.0),
        ("Full THP",           THPMode.FULL,    None,  None,  6.0, 10.0),
        ("WAS-only THP",       THPMode.WAS_ONLY,None,  None,  5.0, 8.0),
    ]:
        cfg_e = DigesterConfig(
            volume_m3=64000, ps_volume_m3=ps_v, was_volume_m3=was_v,
            temperature_c=35, thp_mode=mode,
            thp_temperature_c=165, thp_retention_min=30,
            thp_feed_ds_pct=thp_ds,
            hrt_criterion_d=15, olr_max_kg_vs_m3_d=olr_lim,
            kinetics_preset="spec",
        )
        re = run_mad_v2([etp_ps, etp_was], cfg_e)
        print(f"{label:22s} | {re.hydraulic_hrt_d:5.1f} | {re.olr_kg_vs_m3_d:5.2f} | "
              f"{re.overall_vsr_pct:5.1f} | {re.energy.biogas_nm3_d:8,.0f} | "
              f"{re.dewatering.cake_ds_pct:5.1f} | {re.diagnostics.controlling_constraint}")


if __name__ == "__main__":
    validate_calibration()
