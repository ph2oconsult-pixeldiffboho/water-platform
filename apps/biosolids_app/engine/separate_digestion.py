"""
engine/separate_digestion.py
BioPoint V1 — Separate vs Blended Digestion Analysis.
ph2o Consulting — v25B02

Physics basis:
  - CSTR first-order kinetic model: VSR = 1 - 1/(1 + k × HRT)
    (Chen & Hashimoto; Metcalf & Eddy 5th ed.)
  - PS kinetic constant k_PS = 0.25 /day (Rittmann & McCarty; lit range 0.20-0.35)
  - WAS kinetic constant k_WAS = 0.12 /day (Bolzonella 2005; lit range 0.08-0.15)
  - Blended k_blend ≈ 0.13 /day (WAS-dominated; Silvestre 2015)
  - PS separate 30% specific biogas yield uplift (empirical; Bolzonella 2005; WEF MOP 8)
  - "PS >90% batch conversion in 10 days" refers to batch exponential model
    (k=0.25: 1-e^(-0.25×10)=91.8%); CSTR design target is HRT=12-15 days
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import math


# ── Kinetic constants ─────────────────────────────────────────────────────

K_PS_CENTRAL = 0.25    # /day — CSTR first-order, PS hydrolysis
K_PS_LOW     = 0.20
K_PS_HIGH    = 0.35

K_WAS_CENTRAL = 0.12   # /day — CSTR first-order, WAS hydrolysis
K_WAS_LOW     = 0.08
K_WAS_HIGH    = 0.15

K_BLEND_CENTRAL = 0.13  # /day — blended, WAS-dominated
K_BLEND_LOW     = 0.10
K_BLEND_HIGH    = 0.18

# Specific methane yields (Nm³ CH4 / kg VS destroyed)
Y_PS_SEP  = 0.55 * 1.30  # 30% uplift when PS digested separately (literature)
Y_PS_BL   = 0.55         # PS in blended digestion (suppressed by WAS)
Y_WAS     = 0.45
Y_BLEND   = 0.50         # weighted blended yield

# Calibration: BioPoint CSTR model vs Cambi ETP reference
# At ETP scale, Cambi's detailed model yields ~48% more biogas than our CSTR
# This is due to VS loading rate effects, temperature corrections, co-digestion
# Calibration is applied proportionally so relative uplift calculations are valid
BIOPOINT_CALIBRATION = 1.482   # = 74163 / 50043 (Cambi Scenario 1 / BioPoint CSTR)


# ── Core physics ──────────────────────────────────────────────────────────

def vsr_cstr(k: float, hrt: float) -> float:
    """CSTR first-order VSR. Returns fraction 0-1."""
    if hrt <= 0 or k <= 0:
        return 0.0
    return 1.0 - 1.0 / (1.0 + k * hrt)


def vsr_batch(k: float, hrt: float) -> float:
    """Batch exponential VSR — for '90% in X days' reference only."""
    return 1.0 - math.exp(-k * hrt)


def biogas_nm3d(vs_tpd: float, vsr: float, yield_m3_per_tVS: float,
                calibration: float = BIOPOINT_CALIBRATION) -> float:
    """Total biogas Nm³/day from a VS stream."""
    ch4_frac = 0.63   # CH4 fraction of biogas
    return vs_tpd * 1000 * vsr * yield_m3_per_tVS / ch4_frac * calibration / 1000


def hrt_batch_target(k: float, target_vsr: float = 0.90) -> float:
    """HRT required to achieve target VSR in batch (exponential) model."""
    if target_vsr >= 1.0:
        return float("inf")
    return -math.log(1.0 - target_vsr) / k


def hrt_cstr_target(k: float, target_vsr: float = 0.75) -> float:
    """HRT required to achieve target VSR in CSTR model."""
    if target_vsr >= 1.0:
        return float("inf")
    return target_vsr / (k * (1.0 - target_vsr))


# ── Result dataclass ──────────────────────────────────────────────────────

@dataclass
class StreamResult:
    stream:         str       # "PS" | "WAS"
    ds_tpd:         float
    vs_tpd:         float
    volume_m3:      float
    hrt_days:       float
    vsr_pct:        float
    biogas_nm3d:    float
    ch4_nm3d:       float
    elec_gross_kw:  float
    wet_cake_tpd:   float
    cake_ds_pct:    float
    vs_loading_kgVS_m3_d: float
    k_used:         float
    yield_used:     float


@dataclass
class SeparateDigestionResult:
    mode:            str    # "blended" | "separate" | "optimised"

    # Blended reference (always computed)
    blend_hrt:       float
    blend_vsr_pct:   float
    blend_biogas:    float
    blend_elec_kw:   float
    blend_cake_tpd:  float

    # Separate streams (None if mode == "blended")
    ps:              Optional[StreamResult] = None
    was:             Optional[StreamResult] = None

    # Combined separate outputs
    sep_biogas:      float = 0.0
    sep_elec_kw:     float = 0.0
    sep_cake_tpd:    float = 0.0
    sep_ps_vsr_pct:  float = 0.0
    sep_was_vsr_pct: float = 0.0

    # Uplift vs blended
    biogas_uplift_pct: float = 0.0
    elec_uplift_kw:    float = 0.0
    volume_freed_m3:   float = 0.0  # volume that could be reallocated

    # Throughput capacity analysis
    ps_max_throughput_tDS_per_yr:  float = 0.0  # at current V_PS
    was_max_throughput_tDS_per_yr: float = 0.0
    blend_bottleneck:              str   = ""   # "PS" | "WAS" | "none"

    # Sensitivity
    biogas_uplift_lo_pct: float = 0.0
    biogas_uplift_hi_pct: float = 0.0

    # Optimal split (only if mode == "optimised")
    opt_v_ps_m3:      float = 0.0
    opt_v_was_m3:     float = 0.0
    opt_hrt_ps:       float = 0.0
    opt_hrt_was:      float = 0.0
    opt_biogas:       float = 0.0
    opt_biogas_uplift_pct: float = 0.0


def _stream_result(stream: str, ds_tpd: float, ts_pct: float, vs_pct: float,
                   volume_m3: float, k: float, yield_: float,
                   is_separate_ps: bool = False,
                   chp_eff: float = 0.42, chp_avail: float = 0.88) -> StreamResult:
    """Compute a single stream digestion result."""
    vs_tpd   = ds_tpd * vs_pct / 100
    q_m3d    = ds_tpd / (ts_pct / 100)
    hrt      = volume_m3 / q_m3d if q_m3d > 0 else 0.0
    vsr      = vsr_cstr(k, hrt)
    yield_m3 = yield_ * 1.30 if is_separate_ps else yield_
    bg       = biogas_nm3d(vs_tpd, vsr, yield_m3)
    ch4      = bg * 0.63
    elec     = bg * 0.63 * 0.717 * 35.8 / 3.6 * chp_eff * chp_avail / 24  # kW
    vs_load  = vs_tpd * 1000 / volume_m3  # kg VS/m³/day

    # Dewatering: separate PS achieves higher DS% (less polymer, different cake)
    cake_ds  = 32.0 if (stream == "PS" and not is_separate_ps) else (
               22.0 if stream == "WAS" else 28.0)
    # Cake volume: digestate DS after digestion ≈ DS_in × (1-VSR) + inert DS
    inert    = ds_tpd * (1 - vs_pct/100)   # non-volatile DS through
    digest_ds= ds_tpd * vs_pct/100 * (1 - vsr) + inert
    wet_cake = digest_ds / (cake_ds / 100)

    return StreamResult(
        stream=stream, ds_tpd=ds_tpd, vs_tpd=vs_tpd,
        volume_m3=volume_m3, hrt_days=hrt,
        vsr_pct=vsr*100, biogas_nm3d=bg, ch4_nm3d=ch4,
        elec_gross_kw=elec, wet_cake_tpd=wet_cake,
        cake_ds_pct=cake_ds, vs_loading_kgVS_m3_d=vs_load,
        k_used=k, yield_used=yield_m3,
    )


# ── Main analysis function ────────────────────────────────────────────────

def run_separate_analysis(
    ps_ds_tpd:   float,  was_ds_tpd:  float,
    ps_ts_pct:   float,  was_ts_pct:  float,
    ps_vs_pct:   float,  was_vs_pct:  float,
    ps_volume_m3: float,  was_volume_m3: float,
    hrt_ps_days: float = 12.0,
    hrt_was_days: float = 18.0,
    mode: str = "separate",          # "blended" | "separate" | "optimised"
    k_ps:  float = K_PS_CENTRAL,
    k_was: float = K_WAS_CENTRAL,
    k_blend: float = K_BLEND_CENTRAL,
    chp_eff: float = 0.42,
    chp_avail: float = 0.88,
) -> SeparateDigestionResult:
    """
    Run separate vs blended digestion analysis.

    In 'separate' mode: user specifies how volume is split between PS and WAS.
    In 'optimised' mode: find the V_PS:V_WAS split maximising total biogas.
    """

    v_total = ps_volume_m3 + was_volume_m3

    # ── Always compute blended reference ─────────────────────────────────
    # Use Cambi 6.2% mixed TS basis for hydraulic loading
    ds_total = ps_ds_tpd + was_ds_tpd
    vs_total_tpd = ps_ds_tpd*(ps_vs_pct/100) + was_ds_tpd*(was_vs_pct/100)
    ts_mix_cambi  = (ps_ds_tpd*ps_ts_pct + was_ds_tpd*was_ts_pct) / ds_total
    q_blend  = ds_total / (ts_mix_cambi / 100)  # m³/day
    hrt_bl   = v_total / q_blend
    vsr_bl   = vsr_cstr(k_blend, hrt_bl)
    bg_bl    = biogas_nm3d(vs_total_tpd, vsr_bl, Y_BLEND)
    elec_bl  = bg_bl * 0.63 * 0.717 * 35.8 / 3.6 * chp_eff * chp_avail / 24
    # Blended cake (approximate)
    inert_bl = ds_total * (1 - (ps_vs_pct+was_vs_pct)/2/100)
    cake_ds_bl   = (ps_ds_tpd/ds_total)*20 + (was_ds_tpd/ds_total)*18  # DS% ~19%
    digest_ds_bl = ds_total*(ps_vs_pct/100+was_vs_pct/100)/2*(1-vsr_bl) + inert_bl
    cake_bl  = digest_ds_bl / (cake_ds_bl/100)

    # ── Separate streams ──────────────────────────────────────────────────
    if mode == "blended":
        return SeparateDigestionResult(
            mode="blended",
            blend_hrt=hrt_bl, blend_vsr_pct=vsr_bl*100,
            blend_biogas=bg_bl, blend_elec_kw=elec_bl, blend_cake_tpd=cake_bl,
        )

    elif mode == "separate":
        # User-specified volumes for each stream
        ps_res  = _stream_result("PS",  ps_ds_tpd,  ps_ts_pct,  ps_vs_pct,
                                 ps_volume_m3,  k_ps,  Y_PS_SEP/1.30,
                                 is_separate_ps=True,
                                 chp_eff=chp_eff, chp_avail=chp_avail)
        was_res = _stream_result("WAS", was_ds_tpd, was_ts_pct, was_vs_pct,
                                 was_volume_m3, k_was, Y_WAS,
                                 is_separate_ps=False,
                                 chp_eff=chp_eff, chp_avail=chp_avail)

    elif mode == "optimised":
        # Find optimal V_PS:V_WAS split for maximum biogas
        best_bg = 0.0; best_vf = 30
        ps_vol_feed = ps_ds_tpd / (ps_ts_pct / 100)
        was_vol_feed = was_ds_tpd / (was_ts_pct / 100)
        for vf in range(5, 95):
            V_PS  = v_total * vf / 100
            V_WAS = v_total - V_PS
            hps   = V_PS  / ps_vol_feed  if ps_vol_feed  > 0 else 0
            hwas  = V_WAS / was_vol_feed if was_vol_feed > 0 else 0
            if hps < 8 or hwas < 10: continue
            bg = (biogas_nm3d(ps_ds_tpd*(ps_vs_pct/100),   vsr_cstr(k_ps,  hps),  Y_PS_SEP) +
                  biogas_nm3d(was_ds_tpd*(was_vs_pct/100), vsr_cstr(k_was, hwas), Y_WAS))
            if bg > best_bg:
                best_bg = bg; best_vf = vf
        ps_volume_m3  = v_total * best_vf / 100
        was_volume_m3 = v_total - ps_volume_m3
        ps_res  = _stream_result("PS",  ps_ds_tpd,  ps_ts_pct,  ps_vs_pct,
                                 ps_volume_m3,  k_ps,  Y_PS_SEP/1.30,
                                 is_separate_ps=True)
        was_res = _stream_result("WAS", was_ds_tpd, was_ts_pct, was_vs_pct,
                                 was_volume_m3, k_was, Y_WAS)
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # ── Combined outputs ──────────────────────────────────────────────────
    sep_bg   = ps_res.biogas_nm3d + was_res.biogas_nm3d
    sep_elec = ps_res.elec_gross_kw + was_res.elec_gross_kw
    sep_cake = ps_res.wet_cake_tpd + was_res.wet_cake_tpd
    uplift   = (sep_bg / bg_bl - 1) * 100 if bg_bl > 0 else 0.0

    # ── Sensitivity: low/high kinetics ───────────────────────────────────
    def _bg_sep(kps, kwas):
        bps  = biogas_nm3d(ps_ds_tpd*(ps_vs_pct/100),
                           vsr_cstr(kps,  ps_res.hrt_days),   Y_PS_SEP)
        bwas = biogas_nm3d(was_ds_tpd*(was_vs_pct/100),
                           vsr_cstr(kwas, was_res.hrt_days),  Y_WAS)
        return bps + bwas

    bg_lo = _bg_sep(K_PS_LOW,  K_WAS_HIGH)   # pessimistic
    bg_hi = _bg_sep(K_PS_HIGH, K_WAS_LOW)    # optimistic
    uplift_lo = (bg_lo / bg_bl - 1) * 100 if bg_bl > 0 else 0
    uplift_hi = (bg_hi / bg_bl - 1) * 100 if bg_bl > 0 else 0

    # ── Throughput capacity ───────────────────────────────────────────────
    # At current PS digester volume, max PS throughput = V_PS / HRT_PS_min (10d)
    ps_max = ps_volume_m3 / 10 * (ps_ts_pct/100) * 365   # tDS/yr
    was_max= was_volume_m3 / 15 * (was_ts_pct/100) * 365

    # ── Volume freed relative to blended ─────────────────────────────────
    # If separate PS uses HRT_PS=12d, V_PS needed = Q_PS × 12
    ps_vol_feed  = ps_ds_tpd / (ps_ts_pct/100)
    v_ps_needed  = ps_vol_feed * max(8, ps_res.hrt_days)
    v_freed      = max(0.0, (ps_volume_m3 + was_volume_m3) - v_ps_needed - was_volume_m3)

    # Bottleneck: which stream controls overall capacity?
    ps_hrt_headroom  = ps_res.hrt_days  - 10  # above 10d batch-equiv target
    was_hrt_headroom = was_res.hrt_days - 15  # above 15d WAS requirement
    bottleneck = "WAS" if was_hrt_headroom < ps_hrt_headroom else "PS"

    return SeparateDigestionResult(
        mode=mode,
        blend_hrt=hrt_bl, blend_vsr_pct=vsr_bl*100,
        blend_biogas=bg_bl, blend_elec_kw=elec_bl, blend_cake_tpd=cake_bl,
        ps=ps_res, was=was_res,
        sep_biogas=sep_bg, sep_elec_kw=sep_elec, sep_cake_tpd=sep_cake,
        sep_ps_vsr_pct=ps_res.vsr_pct, sep_was_vsr_pct=was_res.vsr_pct,
        biogas_uplift_pct=uplift, elec_uplift_kw=sep_elec - elec_bl,
        volume_freed_m3=v_freed,
        ps_max_throughput_tDS_per_yr=ps_max,
        was_max_throughput_tDS_per_yr=was_max,
        blend_bottleneck=bottleneck,
        biogas_uplift_lo_pct=uplift_lo,
        biogas_uplift_hi_pct=uplift_hi,
        opt_v_ps_m3=ps_volume_m3 if mode=="optimised" else 0,
        opt_v_was_m3=was_volume_m3 if mode=="optimised" else 0,
        opt_hrt_ps=ps_res.hrt_days if mode=="optimised" else 0,
        opt_hrt_was=was_res.hrt_days if mode=="optimised" else 0,
        opt_biogas=sep_bg if mode=="optimised" else 0,
        opt_biogas_uplift_pct=uplift if mode=="optimised" else 0,
    )
