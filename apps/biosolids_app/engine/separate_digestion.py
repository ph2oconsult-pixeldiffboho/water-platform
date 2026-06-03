"""
engine/separate_digestion.py
BioPoint - Separate vs Blended Digestion Analysis.
ph2o Consulting

Physics basis - reconciled onto BioPoint V2 (the BMP-fitted spine is the single
source of truth; this module no longer carries its own kinetics):
  - Ceiling-limited CSTR model: VSR = f_bio * (k * HRT) / (1 + k * HRT)
    via biopoint_v2_spine.vs_destruction()
  - k and f_bio sourced from spine.KIN: k_PS 0.286, k_WAS 0.380 (WAS hydrolyses
    AS FAST AS PS); f_bio_PS 0.97, f_bio_WAS 0.31 (WAS is CEILING-limited, not
    rate-limited - it reaches a low biodegradable ceiling quickly)
  - The legacy rate-limited WAS (k_WAS 0.12), the ceiling-free CSTR (VSR -> 1.0),
    the empirical x1.30 PS uplift and the 1.482 calibration are all RETIRED:
    f_bio now expresses the PS/WAS difference, so separate digestion's benefit is
    freed CAPACITY, not a biogas uplift.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import math


# --- V2 spine: the single source of truth for digestion kinetics ---
import os as _os, sys as _sys
_ED = _os.path.dirname(_os.path.abspath(__file__))
if _ED not in _sys.path:
    _sys.path.append(_ED)
import biopoint_v2_spine as _S


# -- Kinetic constants - V2 (BMP-fitted spine) is the source of truth --───────

# WAS hydrolyses AS FAST AS PS (k ~0.38/d); the stream difference is the
# biodegradable CEILING (f_bio), not the rate. This replaces the legacy
# rate-limited WAS (k 0.12) and the ceiling-free CSTR (VSR climbing toward 1.0).
K_PS_CENTRAL  = _S.KIN.K_PS                 # 0.286 /day (BMP fit)
K_PS_LOW, K_PS_HIGH   = 0.24, 0.34
K_WAS_CENTRAL = _S.KIN.K_WAS                # 0.380 /day - as fast as PS
K_WAS_LOW, K_WAS_HIGH = 0.30, 0.45
K_BLEND_CENTRAL = _S.KIN.K_WAS              # legacy import; blend now uses the VS-weighted model
K_BLEND_LOW, K_BLEND_HIGH = 0.30, 0.45

# Biodegradable ceilings (ultimate biodegradable VS fraction), from BMP
F_BIO_PS    = _S.KIN.F_BIO_PS               # 0.97
F_BIO_WAS   = _S.KIN.F_BIO_WAS              # 0.31 - WAS is CEILING-limited, not rate-limited
VS_SPLIT_PS = _S.KIN.VS_SPLIT_PS            # PS share of feed VS

# Biogas yield per kg VS DESTROYED is ~constant across streams in the V2 basis.
# The old empirical x1.30 separate-PS uplift is REMOVED - it double-counted what
# f_bio now expresses (PS reaches its high 0.97 ceiling; WAS its low 0.31 ceiling).
CH4_FRAC  = _S.K.CH4_FRACTION                                   # 0.63
Y_PS_SEP = Y_PS_BL = Y_WAS = Y_BLEND = _S.K.BIOGAS_NM3_PER_KG_VSD * CH4_FRAC  # CH4/kgVSdest
BIOPOINT_CALIBRATION = 1.0   # f_bio ceiling + BMP k reproduce the spine; no fudge factor


# --- CHE4180 per-stream BMP (measured Mangere sludge; Hillis & Taylor / Monash CHE4180) ---
# Ultimate biomethane potentials, mL CH4 / g VS (numerically = m3 CH4 / tonne VS).
BMP_PS_ML_G      = 470.0   # primary sludge - high ceiling, realised when digested SEPARATELY
BMP_WAS_ML_G     = 152.0   # raw WAS - low ceiling (~1/3 of PS)
BMP_BLEND_ML_G   = 258.0   # measured BLENDED base case (depressed vs the streams' own potential)
# SolidStream THP-treated WAS BMP: INFERRED by backing the Cambi overall VSR 0.703 (ETP, whole-system)
# onto the WAS term, holding PS at 470. No per-stream Cambi BMP exists -> confidence D, cross-plant transfer.
BMP_WAS_THP_ML_G = 320.0   # ~2.1x raw WAS; defensible band ~300-360


def bmp_biogas_comparison(vs_ps_tpd: float, vs_was_tpd: float,
                          solidstream: bool = False, ch4_frac: float = CH4_FRAC) -> dict:
    """Per-stream BMP additive model (CHE4180) - the honest basis for the separate-digestion uplift.

    Blended digestion is the measured depressed base case (BMP 258). Separate digestion lets each stream
    realise its OWN measured BMP - PS 470, WAS 152 - which is where the ~+30% uplift comes from (almost
    entirely PS reaching its high ceiling). SolidStream THP is an ADDITIONAL, independent layer that lifts
    ONLY the WAS term (152 -> inferred ~320 from Cambi 0.703); PS is untouched. The two datasets therefore
    combine at the STREAM level and are never multiplied as whole-plant percentages. Operating HRTs realise
    ~full BMP, so no approach factor is applied here (it is used only for the HRT-sensitivity curves)."""
    vs_tot = vs_ps_tpd + vs_was_tpd
    bmp_was = BMP_WAS_THP_ML_G if solidstream else BMP_WAS_ML_G
    ch4_blend = vs_tot * BMP_BLEND_ML_G
    ch4_ps    = vs_ps_tpd  * BMP_PS_ML_G
    ch4_was   = vs_was_tpd * bmp_was
    ch4_sep   = ch4_ps + ch4_was
    return {
        "ch4_blend_m3d": ch4_blend, "biogas_blend_m3d": ch4_blend / ch4_frac,
        "ch4_sep_m3d": ch4_sep, "biogas_sep_m3d": ch4_sep / ch4_frac,
        "ch4_ps_m3d": ch4_ps, "ch4_was_m3d": ch4_was,
        "uplift_pct": (ch4_sep / ch4_blend - 1) * 100 if ch4_blend > 0 else 0.0,
        "uplift_vs_raw_pct": ((ch4_ps + vs_was_tpd * BMP_WAS_THP_ML_G) /
                              (ch4_ps + vs_was_tpd * BMP_WAS_ML_G) - 1) * 100 if solidstream else 0.0,
        "was_bmp_used": bmp_was, "solidstream": solidstream,
        "ps_bmp": BMP_PS_ML_G, "was_bmp_raw": BMP_WAS_ML_G, "blend_bmp": BMP_BLEND_ML_G,
    }



import math as _math
# Methane yield per g VS destroyed (constant across streams: BMP / f_bio ~= 485 mL CH4/g VSd).
Y_CH4_ML_PER_G_VSD = BMP_PS_ML_G / F_BIO_PS                      # ~485
F_BIO_WAS_THP = BMP_WAS_THP_ML_G / Y_CH4_ML_PER_G_VSD           # ~0.66 SolidStream-lifted WAS ceiling (conf D)
# Rate constants fitted to the CHE4180 BMP-vs-time curves (Mangere HRT Tests): fraction of ULTIMATE
# biomethane realised at retention t ~= 1 - exp(-k_b * t). Both streams plateau by ~15-18 d.
K_BMP_PS  = 0.275
K_BMP_WAS = 0.256

def bmp_fraction(k_b: float, t_d: float) -> float:
    """Fraction of ultimate BMP realised at retention t (CHE4180 batch curve, screening basis)."""
    return 1.0 - _math.exp(-k_b * t_d) if t_d > 0 else 0.0


def separate_scenario(vs_ps_tpd: float, vs_was_tpd: float,
                      ps_flow_m3d: float, was_flow_m3d: float, installed_vol_m3: float,
                      hrt_ps_d: float = 10.0, hrt_was_d: float = 18.0,
                      solidstream: bool = False, recup_was_srt_d: float = None,
                      ch4_frac: float = CH4_FRAC) -> dict:
    """Biogas-vs-capacity trade-off for separate digestion, driven by user-selected HRTs.

    Biomethane is read off the CHE4180 BMP curves at the retention each stream sees (SRT); digester
    VOLUME is set by HRT. Without recuperative thickening SRT = HRT. Recuperative thickening on WAS
    DECOUPLES them - it holds the WAS SRT (e.g. 18 d) while the HRT, and hence the volume, drops, so the
    WAS gas is kept at a fraction of the tankage. SolidStream THP additionally lifts ONLY the WAS ceiling
    (BMP 152 -> ~320, inferred from Cambi 0.703, confidence D). Blended baseline is the measured base case
    (BMP 258, depressed by co-digestion + real-plant losses per the CHE4180 note)."""
    bmp_was  = BMP_WAS_THP_ML_G if solidstream else BMP_WAS_ML_G
    srt_ps   = hrt_ps_d
    srt_was  = recup_was_srt_d if recup_was_srt_d else hrt_was_d
    frac_ps  = bmp_fraction(K_BMP_PS,  srt_ps)
    frac_was = bmp_fraction(K_BMP_WAS, srt_was)
    ch4_ps   = vs_ps_tpd  * BMP_PS_ML_G * frac_ps
    ch4_was  = vs_was_tpd * bmp_was      * frac_was
    ch4_sep  = ch4_ps + ch4_was
    vol_ps   = ps_flow_m3d  * hrt_ps_d
    vol_was  = was_flow_m3d * hrt_was_d
    vol_sep  = vol_ps + vol_was
    ch4_blend = (vs_ps_tpd + vs_was_tpd) * BMP_BLEND_ML_G
    return {
        "ch4_blend_m3d": ch4_blend, "biogas_blend_m3d": ch4_blend / ch4_frac,
        "ch4_sep_m3d": ch4_sep, "biogas_sep_m3d": ch4_sep / ch4_frac,
        "ch4_ps_m3d": ch4_ps, "ch4_was_m3d": ch4_was,
        "uplift_pct": (ch4_sep / ch4_blend - 1) * 100 if ch4_blend > 0 else 0.0,
        "vol_ps_m3": vol_ps, "vol_was_m3": vol_was, "vol_sep_m3": vol_sep,
        "freed_vol_m3": installed_vol_m3 - vol_sep,
        "freed_vol_pct": (installed_vol_m3 - vol_sep) / installed_vol_m3 * 100 if installed_vol_m3 > 0 else 0.0,
        "bmp_realised_ps_pct": frac_ps * 100, "bmp_realised_was_pct": frac_was * 100,
        "srt_was_d": srt_was, "hrt_was_d": hrt_was_d, "hrt_ps_d": hrt_ps_d,
        "recup": bool(recup_was_srt_d), "solidstream": solidstream, "was_bmp_used": bmp_was,
    }


def tradeoff_sweep(vs_ps_tpd, vs_was_tpd, ps_flow_m3d, was_flow_m3d, installed_vol_m3,
                   hrt_ps_d, solidstream, recup_was_srt_d, ch4_frac=CH4_FRAC,
                   was_hrt_range=range(8, 31, 2)):
    """Sweep WAS HRT -> (hrt, separate biomethane, freed volume) for the trade-off chart."""
    out = []
    for h in was_hrt_range:
        r = separate_scenario(vs_ps_tpd, vs_was_tpd, ps_flow_m3d, was_flow_m3d, installed_vol_m3,
                              hrt_ps_d=hrt_ps_d, hrt_was_d=float(h), solidstream=solidstream,
                              recup_was_srt_d=recup_was_srt_d, ch4_frac=ch4_frac)
        out.append((float(h), r["ch4_sep_m3d"], r["freed_vol_m3"]))
    return out


# BMP plateau SRT per stream (retention to reach 98% of ultimate BMP). Below this, SRT drives biogas;
# above it, more retention adds ~nothing. This is the hinge for whether recuperative thickening pays.
SRT_PLATEAU_PS  = -_math.log(0.02) / K_BMP_PS     # ~14 d
SRT_PLATEAU_WAS = -_math.log(0.02) / K_BMP_WAS    # ~15 d


def hrt_limited_diagnosis(ps_flow_m3d, was_flow_m3d, installed_vol_m3,
                          srt_ps_d=12.0, srt_was_d=18.0):
    """Is the plant HRT(volume)-limited for the biogas-optimal separate config?

    Compares the volume needed to run the target SRTs hydraulically (SRT = HRT) against installed.
    Also reports the WAS SRT actually achievable hydraulically once PS has its target, and whether
    that achievable SRT sits BELOW the BMP plateau - the only regime in which recuperative thickening
    unlocks biogas rather than merely freeing volume."""
    req = ps_flow_m3d * srt_ps_d + was_flow_m3d * srt_was_d
    was_srt_ach = max(0.0, installed_vol_m3 - ps_flow_m3d * srt_ps_d) / was_flow_m3d if was_flow_m3d > 0 else 0.0
    return {
        "required_vol_m3": req, "installed_vol_m3": installed_vol_m3,
        "hrt_limited": req > installed_vol_m3,
        "deficit_m3": max(0.0, req - installed_vol_m3),
        "surplus_m3": max(0.0, installed_vol_m3 - req),
        "was_srt_achievable_d": was_srt_ach,
        "plateau_srt_was_d": SRT_PLATEAU_WAS,
        "biogas_unlock_available": was_srt_ach < SRT_PLATEAU_WAS,
        "srt_ps_target_d": srt_ps_d, "srt_was_target_d": srt_was_d,
    }


def recuperative_value(vs_was_tpd, was_flow_m3d, hrt_was_d, recup_srt_d,
                       solidstream=False, ch4_frac=CH4_FRAC):
    """Decompose what recuperative thickening on WAS actually buys.

    It holds WAS SRT at recup_srt while the HRT (volume) runs at hrt_was. The BIOGAS benefit is the gas
    you would LOSE by freeing that volume WITHOUT it (i.e. running SRT = HRT = hrt_was) instead of holding
    SRT = recup_srt. That is ~zero whenever hrt_was already sits at/above the WAS BMP plateau (~15 d) - the
    not-HRT-limited case. The CAPACITY benefit is the WAS volume saved by running HRT below the held SRT."""
    bmp_was  = BMP_WAS_THP_ML_G if solidstream else BMP_WAS_ML_G
    ch4_held = vs_was_tpd * bmp_was * bmp_fraction(K_BMP_WAS, recup_srt_d)   # SRT held by recuperative
    ch4_hyd  = vs_was_tpd * bmp_was * bmp_fraction(K_BMP_WAS, hrt_was_d)     # SRT = HRT, no recuperative
    benefit  = ch4_held - ch4_hyd
    return {
        "ch4_held_m3d": ch4_held, "ch4_hydraulic_m3d": ch4_hyd,
        "biogas_benefit_m3d": benefit,
        "biogas_benefit_pct_of_was": (benefit / ch4_hyd * 100) if ch4_hyd > 0 else 0.0,
        "vol_saved_m3": was_flow_m3d * max(0.0, recup_srt_d - hrt_was_d),
        "below_plateau": hrt_was_d < SRT_PLATEAU_WAS,
        "plateau_srt_was_d": SRT_PLATEAU_WAS, "hrt_was_d": hrt_was_d, "recup_srt_d": recup_srt_d,
    }


# ── Core physics ──────────────────────────────────────────────────────────

def vsr_cstr(k: float, hrt: float, f_bio: float = 1.0) -> float:
    """CSTR VS destruction = f_bio * (k*hrt)/(1+k*hrt). Delegates to the V2 spine so the
    biodegradable ceiling (f_bio) is the single source of truth. f_bio=1.0 reproduces the
    legacy ceiling-free curve."""
    if hrt <= 0 or k <= 0:
        return 0.0
    return _S.vs_destruction(k, hrt, f_bio)


def vsr_batch(k: float, hrt: float, f_bio: float = 1.0) -> float:
    """Batch exponential VS destruction, ceiling-limited: f_bio*(1-exp(-k*hrt))."""
    return f_bio * (1.0 - math.exp(-k * hrt))


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
                   f_bio: float = 1.0,
                   is_separate_ps: bool = False,
                   chp_eff: float = 0.42, chp_avail: float = 0.88) -> StreamResult:
    """Compute a single stream digestion result (ceiling-limited via f_bio, V2 basis)."""
    vs_tpd   = ds_tpd * vs_pct / 100
    q_m3d    = ds_tpd / (ts_pct / 100)
    hrt      = volume_m3 / q_m3d if q_m3d > 0 else 0.0
    vsr      = vsr_cstr(k, hrt, f_bio)
    yield_m3 = yield_                       # VSR/HRT basis only; biogas UPLIFT now via bmp_biogas_comparison (CHE4180)
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
    # V2 blended VSR: VS-weighted stream destruction, each ceiling-limited by its f_bio
    _wP = ((ps_ds_tpd*ps_vs_pct) / (ps_ds_tpd*ps_vs_pct + was_ds_tpd*was_vs_pct)
           if (ps_ds_tpd*ps_vs_pct + was_ds_tpd*was_vs_pct) > 0 else VS_SPLIT_PS)
    vsr_bl   = (_wP * vsr_cstr(K_PS_CENTRAL, hrt_bl, F_BIO_PS)
                + (1.0 - _wP) * vsr_cstr(K_WAS_CENTRAL, hrt_bl, F_BIO_WAS))
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
                                 ps_volume_m3,  k_ps,  Y_PS_SEP, f_bio=F_BIO_PS,
                                 is_separate_ps=True,
                                 chp_eff=chp_eff, chp_avail=chp_avail)
        was_res = _stream_result("WAS", was_ds_tpd, was_ts_pct, was_vs_pct,
                                 was_volume_m3, k_was, Y_WAS, f_bio=F_BIO_WAS,
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
            bg = (biogas_nm3d(ps_ds_tpd*(ps_vs_pct/100),   vsr_cstr(k_ps,  hps,  F_BIO_PS),  Y_PS_SEP) +
                  biogas_nm3d(was_ds_tpd*(was_vs_pct/100), vsr_cstr(k_was, hwas, F_BIO_WAS), Y_WAS))
            if bg > best_bg:
                best_bg = bg; best_vf = vf
        ps_volume_m3  = v_total * best_vf / 100
        was_volume_m3 = v_total - ps_volume_m3
        ps_res  = _stream_result("PS",  ps_ds_tpd,  ps_ts_pct,  ps_vs_pct,
                                 ps_volume_m3,  k_ps,  Y_PS_SEP, f_bio=F_BIO_PS,
                                 is_separate_ps=True)
        was_res = _stream_result("WAS", was_ds_tpd, was_ts_pct, was_vs_pct,
                                 was_volume_m3, k_was, Y_WAS, f_bio=F_BIO_WAS)
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
                           vsr_cstr(kps,  ps_res.hrt_days, F_BIO_PS),   Y_PS_SEP)
        bwas = biogas_nm3d(was_ds_tpd*(was_vs_pct/100),
                           vsr_cstr(kwas, was_res.hrt_days, F_BIO_WAS),  Y_WAS)
        return bps + bwas

    bg_lo = _bg_sep(K_PS_LOW,  K_WAS_HIGH)   # pessimistic
    bg_hi = _bg_sep(K_PS_HIGH, K_WAS_LOW)    # optimistic
    uplift_lo = (bg_lo / bg_bl - 1) * 100 if bg_bl > 0 else 0
    uplift_hi = (bg_hi / bg_bl - 1) * 100 if bg_bl > 0 else 0

    # ── Throughput capacity ───────────────────────────────────────────────
    # At current PS digester volume, max PS throughput = V_PS / HRT_PS_min (10d)
    ps_max = ps_volume_m3 / 10 * (ps_ts_pct/100) * 365   # tDS/yr
    was_max= was_volume_m3 / 12 * (was_ts_pct/100) * 365   # V2 floor 12 d (was 15)

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
