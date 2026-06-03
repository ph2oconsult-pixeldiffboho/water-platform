"""
apps/biosolids_app/engine/foaming_risk.py
BioPoint Digester Foaming Risk Engine.

Foaming risk is NOT a single variable. Four independent mechanisms are scored 0-100 and reported as a
PROFILE - never collapsed to one figure that hides the trade-offs:

  Type 1  Filament        - Nocardia / Gordonia / mycolata (live in WAS; concentrate when not diluted by PS)
  Type 2  Gas entrapment  - high gas flux, high viscosity (digester TS), poor mixing, gas hold-up
  Type 3  Surfactant      - FOG, proteins, cell-lysis products, surface-active compounds
  Type 4  Instability     - VFA accumulation, methanogen washout, pH instability, organic overloading

This is a screening / structured-judgment index, not a mechanistic CFD/biology model. The pathway DIRECTIONS
match documented behaviour (separate digestion concentrates filaments; recuperative thickening protects SRT
but raises viscosity; SolidStream + hot-liquor recycle buffers instability but adds solubles/filaments). The
absolute coefficients are a first-pass calibration to be tuned against site foaming history - confidence C.
"""
from dataclasses import dataclass

SRT_WASHOUT_FLOOR = 12.0          # consistent with separate_digestion.py
SRT_ROBUST        = 15.0
SRT_CONSERVATIVE  = 18.0

def band(score: float) -> str:
    return "Low" if score < 30 else "Moderate" if score < 60 else "High"

def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


@dataclass
class FoamInputs:
    was_vs_fraction: float = 0.45      # WAS VS / total VS (PS dilutes filaments in a blended digester)
    filament_prevalence: float = 40.0  # 0-100 SITE index: Nocardia/Gordonia/mycolata load in the activated sludge
    fog_loading: float = 20.0          # 0-100 relative FOG / oil & grease load
    mixing_adequacy: float = 70.0      # 0-100 (100 = strong mixing; low -> gas hold-up)
    digester_ts_pct: float = 3.5       # % TS in the governing (WAS) digester at the operating point
    srt_d: float = 18.0                # solids retention time (biology) - already reflects recuperative thickening
    olr_kgvs_m3d: float = 2.0          # organic loading rate
    # pathway switches
    separate: bool = False
    recuperative: bool = False
    solidstream: bool = False
    hot_liquor_recycle: bool = False
    thp_feed_kill: bool = False        # THP on the FEED thermally destroys filaments. OFF by default: K+
                                       # recycles hot LIQUOR while live WAS still feeds the digester.


def foaming_profile(inp: FoamInputs) -> dict:
    """Score the four mechanisms 0-100 for one operating point and report the binding one."""
    # Filaments live in the WAS; a dedicated WAS digester (separate) is no longer diluted by primary sludge.
    eff_was = 1.0 if inp.separate else inp.was_vs_fraction

    # Type 1 - Filament
    t1 = 0.45*inp.filament_prevalence + 35.0*max(0.0, eff_was-0.30)/0.70 + 0.25*inp.fog_loading
    if inp.hot_liquor_recycle: t1 += 10.0       # recycle concentrates filament organisms
    if inp.thp_feed_kill:      t1 -= 40.0       # feed THP thermally destroys them
    t1 = _clamp(t1)

    # Type 2 - Gas entrapment (viscosity from TS, gas flux from OLR, poor mixing)
    t2 = 3.0*max(0.0, inp.digester_ts_pct-3.0) + 8.0*max(0.0, inp.olr_kgvs_m3d-1.5) + 0.35*(100.0-inp.mixing_adequacy)
    if inp.solidstream: t2 += 12.0              # higher gas flux + viscosity
    t2 = _clamp(t2)

    # Type 3 - Surfactant (FOG, protein-rich WAS, cell-lysis solubles, recycled solubles)
    t3 = 0.45*inp.fog_loading + 28.0*max(0.0, eff_was-0.30)/0.70
    if inp.solidstream:        t3 += 20.0       # THP cell lysis releases proteins/surfactants
    if inp.hot_liquor_recycle: t3 += 12.0       # recycle returns soluble proteins/surfactants
    t3 = _clamp(t3)

    # Type 4 - Instability (SRT vs floor -> washout; OLR overloading; recycle buffers VFA/alkalinity)
    if   inp.srt_d >= SRT_CONSERVATIVE:  t4 = 8.0
    elif inp.srt_d >= SRT_ROBUST:        t4 = 22.0
    elif inp.srt_d >= SRT_WASHOUT_FLOOR: t4 = 42.0
    else:                                t4 = 80.0
    t4 += 6.0*max(0.0, inp.olr_kgvs_m3d-3.0)
    if inp.hot_liquor_recycle: t4 -= 25.0       # alkalinity/buffering + soluble-COD conversion -> strongly reduced
    t4 = _clamp(t4)

    types = {"Type1_filament": t1, "Type2_gas_entrapment": t2,
             "Type3_surfactant": t3, "Type4_instability": t4}
    dominant = max(types, key=types.get)
    overall  = _clamp(0.6*max(types.values()) + 0.4*(sum(types.values())/4.0))   # binding-mechanism dominated
    return {**types, "overall": overall, "dominant": dominant,
            "bands": {k: band(v) for k, v in types.items()}, "overall_band": band(overall),
            "srt_washout": inp.srt_d < SRT_WASHOUT_FLOOR}


# Canonical pathways, composed from the switches (so the same engine scores every configuration).
PATHWAYS = {
    "Conventional blended": dict(separate=False, recuperative=False, solidstream=False, hot_liquor_recycle=False),
    "Separate PS/WAS":      dict(separate=True,  recuperative=False, solidstream=False, hot_liquor_recycle=False),
    "Separate + RT":        dict(separate=True,  recuperative=True,  solidstream=False, hot_liquor_recycle=False),
    "K+ (Sep+SolidStream+Recycle)": dict(separate=True, recuperative=True, solidstream=True, hot_liquor_recycle=True),
}

def compare_pathways(was_vs_fraction, filament_prevalence, fog_loading, mixing_adequacy,
                     ts_by_pathway, srt_by_pathway, olr_by_pathway):
    """Run the four canonical pathways. ts/srt/olr are dicts keyed by pathway name (the biogas/capacity
    engine supplies these per config), so foaming reads the SAME operating point as the rest of BioPoint."""
    out = {}
    for name, sw in PATHWAYS.items():
        inp = FoamInputs(was_vs_fraction=was_vs_fraction, filament_prevalence=filament_prevalence,
                         fog_loading=fog_loading, mixing_adequacy=mixing_adequacy,
                         digester_ts_pct=ts_by_pathway.get(name, 3.5),
                         srt_d=srt_by_pathway.get(name, 18.0), olr_kgvs_m3d=olr_by_pathway.get(name, 2.0), **sw)
        out[name] = foaming_profile(inp)
    return out
