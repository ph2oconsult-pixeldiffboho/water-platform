"""
engine/thermal_treatment.py
BioPoint V1 — Thermal Treatment Screening Engine

Provides screening-level energy balances, mass balances, CAPEX/OPEX estimates
and PFAS destruction curves for four thermal endpoint technologies:
  1. Pyrolysis          (400–700°C slow pyrolysis)
  2. Hydrothermal Liquefaction (HTL, 250–350°C, 15–25 MPa)
  3. Gasification       (750–1000°C, partial oxidation)
  4. Incineration / WtE (800–950°C)

All estimates are Class 5 (±50%) screening level.
Full-scale reference plants are scarce for pyrolysis and HTL applied to
biosolids — confidence levels reflect this.

Literature basis:
  Pyrolysis:    Bridgwater 2012; Ro et al. 2010; Winchell et al. 2022
  HTL:          Elliott et al. 2015; Biller & Ross 2011; Davis et al. 2018
  Gasification: Dogru et al. 2002; GTC 2015; Werther & Ogada 1999
  Incineration: Werther & Ogada 1999; CEWEP 2022; USEPA 2020
  PFAS DRE:     ITRC 2020; Winchell et al. 2022; Rahman et al. 2014

ph2o Consulting — v25B02
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math


# ── Technology identifiers ──────────────────────────────────────────────────
TECH_IDS = ("pyrolysis", "htl", "gasification", "incineration")


# ── Grid and fuel emission factors ─────────────────────────────────────────
GRID_INTENSITY_DEFAULT    = 0.60    # kg CO2e/kWh (Victorian grid 2025)
DIESEL_EMISSION_FACTOR    = 2.68    # kg CO2e/L displaced (bio-crude = diesel equiv.)
DIESEL_ENERGY_MJ_PER_L    = 35.8   # MJ/L diesel


# ── Technology parameters (central estimates) ──────────────────────────────
# All per tonne of dry solids (tDS) input unless noted.

TECH_PARAMS = {

    "pyrolysis": {
        "name":              "Slow Pyrolysis",
        "temp_c_lo":         400,
        "temp_c_hi":         700,
        "temp_c_typical":    500,
        "input_ds_pct_min":  25,     # minimum input DS% (requires drying if below)
        "input_ds_pct_typ":  30,     # typical operating DS%
        # Energy
        "syngas_gj_per_tds": 6.5,    # syngas energy yield (HHV), GJ/tDS
        "gross_elec_kwh_tds":350,    # gross electricity from syngas CHP, kWh/tDS
        "parasitic_kwh_tds": 120,    # process parasitic (dryer, fans, controls)
        "net_elec_kwh_tds":  230,    # net export electricity, kWh/tDS
        # Mass balance
        "biochar_frac_ds":   0.40,   # biochar as fraction of DS input
        "ash_frac_ds":       0.00,   # separate ash (negligible for slow pyrolysis)
        "oil_frac_ds":       0.05,   # condensate/oil fraction
        # PFAS (temperature-dependent — see pfas_dre_curve)
        "pfas_dre_500c":     0.55,
        "pfas_dre_700c":     0.90,
        "pfas_dre_typical":  0.55,   # at 500°C default operating temperature
        # CAPEX/OPEX (AUD 2024, Class 5 ±50%)
        "capex_aud_per_tds_yr_lo": 800,
        "capex_aud_per_tds_yr_hi": 1500,
        "capex_aud_per_tds_yr":    1100,  # central
        "opex_aud_per_tds_lo":     150,
        "opex_aud_per_tds_hi":     250,
        "opex_aud_per_tds":        200,   # central
        # P recovery
        "p_recovery_pct":    70,     # % of incoming P in biochar
        "p_pathway":         "Biochar land application (slow-release P fertiliser)",
        # Carbon products
        "biochar_c_stable_frac": 0.85,  # fraction of biochar C that is stable >100yr
        # Scale viability
        "min_viable_tds_d":  5,      # minimum scale (tDS/d)
        "maturity":          "Emerging — pilot/demo scale for biosolids",
        "confidence":        "Low",
    },

    "htl": {
        "name":              "Hydrothermal Liquefaction (HTL)",
        "temp_c_lo":         250,
        "temp_c_hi":         350,
        "temp_c_typical":    300,
        "pressure_mpa":      20,
        "input_ds_pct_min":  10,     # accepts wet feed — key advantage
        "input_ds_pct_typ":  15,
        # Energy
        "biocrude_gj_per_tds": 12.0, # bio-crude energy yield, GJ/tDS
        "biocrude_gj_per_l":    0.035,# energy density ~35 MJ/L ≈ diesel
        "gross_elec_kwh_tds":  450,  # if bio-crude combusted in CHP
        "parasitic_kwh_tds":   150,  # high-pressure pumping, heat recovery
        "net_elec_kwh_tds":    300,  # or bio-crude exported as fuel product
        # Mass balance
        "biocrude_frac_ds":    0.25, # bio-crude as fraction of DS input (by mass)
        "hydrochar_frac_ds":   0.10, # residual char
        "aqueous_vol_l_per_tds": 800,# aqueous product volume, L/tDS (high N, P)
        # PFAS (variable — sub-critical water partial mineralisation)
        "pfas_dre_lo":         0.30,
        "pfas_dre_hi":         0.70,
        "pfas_dre_typical":    0.45,
        # CAPEX/OPEX
        "capex_aud_per_tds_yr_lo": 1500,
        "capex_aud_per_tds_yr_hi": 3000,
        "capex_aud_per_tds_yr":    2200,
        "opex_aud_per_tds_lo":     250,
        "opex_aud_per_tds_hi":     450,
        "opex_aud_per_tds":        350,
        # P recovery (from aqueous product via struvite)
        "p_recovery_pct":    45,
        "p_pathway":         "Struvite from aqueous product (~45% recovery)",
        # Carbon
        "biocrude_c_frac":   0.75,  # C content of bio-crude (fraction)
        # Scale
        "min_viable_tds_d":  20,
        "maturity":          "Pre-commercial — limited full-scale biosolids refs",
        "confidence":        "Very Low",
    },

    "gasification": {
        "name":              "Gasification",
        "temp_c_lo":         750,
        "temp_c_hi":         1000,
        "temp_c_typical":    850,
        "input_ds_pct_min":  75,     # requires drying for autothermal
        "input_ds_pct_typ":  85,
        # Energy
        "syngas_gj_per_tds": 8.0,
        "gross_elec_kwh_tds":440,
        "parasitic_kwh_tds": 160,    # includes drying energy
        "net_elec_kwh_tds":  280,
        "drying_heat_gj_tds":3.5,    # heat demand for drying to 85%DS
        # Mass balance
        "ash_frac_ds":       0.20,   # vitrified slag/ash
        "char_frac_ds":      0.02,   # residual char (well-gasified)
        # PFAS (high temperature destruction)
        "pfas_dre_750c":     0.95,
        "pfas_dre_1000c":    0.999,
        "pfas_dre_typical":  0.97,
        # CAPEX/OPEX
        "capex_aud_per_tds_yr_lo": 1200,
        "capex_aud_per_tds_yr_hi": 2500,
        "capex_aud_per_tds_yr":    1800,
        "opex_aud_per_tds_lo":     200,
        "opex_aud_per_tds_hi":     350,
        "opex_aud_per_tds":        270,
        # P recovery (from ash/slag via acid leaching)
        "p_recovery_pct":    90,
        "p_pathway":         "Acid leaching of vitrified slag (~90% P recovery)",
        # Scale
        "min_viable_tds_d":  30,
        "maturity":          "Limited full-scale biosolids-specific references",
        "confidence":        "Low",
    },

    "incineration": {
        "name":              "Incineration / WtE",
        "temp_c_lo":         800,
        "temp_c_hi":         950,
        "temp_c_typical":    860,
        "residence_time_s":  2,      # EU Waste Incineration Directive minimum
        "input_ds_pct_min":  18,     # minimum DS% for autothermal
        "input_ds_pct_typ":  25,
        # Energy (HHV of biosolids ~8-12 GJ/tDS)
        "hhv_gj_per_tds":    10.0,   # HHV of dewatered biosolids, GJ/tDS
        "gross_elec_kwh_tds":310,    # WtE turbine output, kWh/tDS
        "parasitic_kwh_tds": 80,     # fans, ID fan, controls
        "net_elec_kwh_tds":  230,    # net export
        "heat_export_gj_tds":3.0,    # district heat or process steam (optional)
        # Mass balance
        "ash_frac_ds":       0.25,   # bottom ash + fly ash combined
        "bottom_ash_frac":   0.18,   # bottom ash (P-rich)
        "fly_ash_frac":      0.07,   # fly ash (hazardous if PFAS-contaminated)
        # PFAS
        "pfas_dre_typical":  0.95,
        "pfas_dre_hi":       0.999,  # at >850°C + 2s
        # CAPEX/OPEX (strong scale dependency)
        "capex_aud_per_tds_yr_lo":  2000,
        "capex_aud_per_tds_yr_hi":  4000,
        "capex_aud_per_tds_yr":     3000,
        "capex_min_viable_scale_td": 50,  # below this CAPEX/tDS becomes very high
        "opex_aud_per_tds_lo":      150,
        "opex_aud_per_tds_hi":      300,
        "opex_aud_per_tds":         220,
        # P recovery (from bottom ash)
        "p_recovery_pct":    92,
        "p_pathway":         "Bottom ash P recovery (Ash Dec / wet chemical, 90-95%)",
        # Scale
        "min_viable_tds_d":  50,
        "maturity":          "Established technology; few biosolids-only plants in AUS",
        "confidence":        "Medium",
    },
}


# ── PFAS DRE temperature curve ─────────────────────────────────────────────

def pfas_dre(tech_id: str, temp_c: Optional[float] = None) -> float:
    """
    Return PFAS Destruction and Removal Efficiency (0–1) for a technology
    at a given temperature. If temp_c is None, uses the typical value.

    The DRE curve is based on:
      - Sub-critical (250–350°C): partial mineralisation (HTL)
      - Pyrolysis (400–700°C): temperature-dependent defluorination
      - Gasification (>750°C): near-complete at all operating temps
      - Incineration (>850°C): compliant with EU WI Directive

    Literature: ITRC 2020; Sörengård et al. 2019; Winchell et al. 2022.
    """
    p = TECH_PARAMS.get(tech_id, {})
    if temp_c is None:
        return p.get("pfas_dre_typical", 0.0)

    if tech_id == "htl":
        # Increases with temperature 250–350°C
        lo, hi = p["pfas_dre_lo"], p["pfas_dre_hi"]
        frac = (temp_c - 250) / 100.0
        return lo + (hi - lo) * max(0, min(1, frac))

    if tech_id == "pyrolysis":
        # Sigmoid-like curve 400–700°C
        lo5  = p["pfas_dre_500c"]
        hi7  = p["pfas_dre_700c"]
        if temp_c <= 400:
            return 0.10
        if temp_c >= 700:
            return hi7
        frac = (temp_c - 400) / 300.0
        # Approximate sigmoid
        return lo5 + (hi7 - lo5) * (frac ** 0.7)

    if tech_id == "gasification":
        if temp_c < 750:
            return 0.85
        lo7 = p["pfas_dre_750c"]
        hi10 = p["pfas_dre_1000c"]
        frac = (temp_c - 750) / 250.0
        return lo7 + (hi10 - lo7) * max(0, min(1, frac))

    if tech_id == "incineration":
        if temp_c < 800:
            return 0.80
        if temp_c >= 850:
            return p["pfas_dre_hi"]
        return p["pfas_dre_typical"]

    return p.get("pfas_dre_typical", 0.0)


# ── Result dataclass ────────────────────────────────────────────────────────

@dataclass
class ThermalResult:
    """Screening result for one thermal technology at a given scale."""
    tech_id:            str
    tech_name:          str
    ds_tpd:             float    # DS input, tDS/day
    input_ds_pct:       float    # required input DS%

    # Energy
    gross_elec_kw:      float    # gross electricity, kW
    parasitic_kw:       float    # process parasitic, kW
    net_elec_kw:        float    # net electricity export, kW
    net_elec_kwh_yr:    float    # net annual MWh/yr
    energy_revenue_aud_yr: float # electricity revenue, AUD/yr

    # Mass balance
    residual_t_d:       float    # residual solid (ash/char/biochar), tDS/day
    product_description:str      # description of main product streams

    # PFAS
    pfas_dre_pct:       float    # PFAS destruction efficiency, %
    pfas_confidence:    str

    # Costs (AUD 2024, Class 5 ±50%)
    capex_aud_m:        float    # central CAPEX estimate, $M
    capex_lo_aud_m:     float
    capex_hi_aud_m:     float
    opex_aud_per_tds:   float    # unit OPEX, $/tDS
    opex_total_aud_yr:  float    # total annual OPEX, AUD/yr

    # P recovery
    p_recovered_kg_d:   float    # P in recoverable product stream, kg/day
    p_recovery_pct:     float
    p_pathway:          str

    # Net GHG (plant boundary + energy credit)
    net_ghg_kg_co2e_d:  float    # net GHG, kg CO2e/day (negative = avoided)
    net_ghg_t_co2e_yr:  float

    # Scale
    min_viable_tds_d:   float
    scale_viable:       bool     # True if ds_tpd >= min_viable_tds_d
    maturity:           str
    confidence:         str

    # Nitrogen fate (from cnp_fate partitions; 0.0 if not available)
    n_in_kg_d:          float = 0.0  # total N into thermal process
    n_to_atm_kg_d:      float = 0.0  # NOx + N2 + N2O + NH3 to atmosphere
    n_to_liquid_kg_d:   float = 0.0  # to aqueous product / condensate
    n_to_solid_kg_d:    float = 0.0  # to char/ash/slag
    n_atm_pct:          float = 0.0  # % to atmosphere
    n_liquid_pct:       float = 0.0  # % to liquid streams
    n_liquid_note:      str   = field(default="")
    nox_kg_d:           float = 0.0  # NOx (flue gas treatment required)


def run_thermal(
    tech_id:        str,
    ds_tpd:         float,
    p_in_kg_d:      float,
    n_in_kg_d:      float = 0.0,
    grid_intensity: float = GRID_INTENSITY_DEFAULT,
    elec_price_aud_kwh: float = 0.12,
    temp_c:         Optional[float] = None,
) -> ThermalResult:
    """
    Run screening analysis for one thermal technology.

    Parameters
    ----------
    tech_id             : "pyrolysis", "htl", "gasification", or "incineration"
    ds_tpd              : Dry solids feed, tDS/day
    p_in_kg_d           : Phosphorus input to thermal process, kg/day
    grid_intensity      : Grid emission factor, kg CO2e/kWh
    elec_price_aud_kwh  : Electricity price, AUD/kWh
    temp_c              : Operating temperature (optional; uses typical if None)
    """
    p = TECH_PARAMS[tech_id]

    # Energy
    gross_kw = ds_tpd * p["gross_elec_kwh_tds"] / 24
    para_kw  = ds_tpd * p["parasitic_kwh_tds"]  / 24
    net_kw   = ds_tpd * p["net_elec_kwh_tds"]   / 24
    net_kwh_yr = net_kw * 24 * 365
    elec_rev = net_kwh_yr * elec_price_aud_kwh

    # Mass balance
    if tech_id == "pyrolysis":
        residual_t_d = ds_tpd * p["biochar_frac_ds"]
        product_desc = (
            f"Biochar: {residual_t_d:.1f} tDS/d "
            f"({p['biochar_frac_ds']*100:.0f}% of DS input). "
            "Stable carbon product for soil amendment. "
            f"Syngas combusted for electricity ({p['gross_elec_kwh_tds']:.0f} kWh/tDS gross)."
        )
    elif tech_id == "htl":
        biocrude_t_d = ds_tpd * p["biocrude_frac_ds"]
        char_t_d     = ds_tpd * p["hydrochar_frac_ds"]
        residual_t_d = char_t_d
        biocrude_gj_d= ds_tpd * p["biocrude_gj_per_tds"]
        product_desc = (
            f"Bio-crude: {biocrude_t_d:.1f} t/d ({biocrude_gj_d:.0f} GJ/d, "
            f"diesel-equivalent fuel). "
            f"Hydrochar: {char_t_d:.1f} tDS/d. "
            f"Aqueous product: {ds_tpd * p['aqueous_vol_l_per_tds'] / 1000:.0f} m3/d "
            "(high N+P, requires treatment)."
        )
    elif tech_id == "gasification":
        residual_t_d = ds_tpd * p["ash_frac_ds"]
        product_desc = (
            f"Vitrified ash/slag: {residual_t_d:.1f} t/d "
            f"({p['ash_frac_ds']*100:.0f}% of DS input). "
            f"Syngas electricity: {net_kw:.0f} kW net. "
            "Ash suitable for P recovery and aggregate use."
        )
    else:  # incineration
        bottom_ash   = ds_tpd * p["bottom_ash_frac"]
        fly_ash      = ds_tpd * p["fly_ash_frac"]
        residual_t_d = bottom_ash + fly_ash
        product_desc = (
            f"Bottom ash (P-rich): {bottom_ash:.1f} t/d. "
            f"Fly ash (hazardous): {fly_ash:.1f} t/d. "
            f"Net electricity: {net_kw:.0f} kW. "
            f"Optional heat export: {ds_tpd * p['heat_export_gj_tds'] / 24:.0f} GJ/hr."
        )

    # PFAS DRE
    dre = pfas_dre(tech_id, temp_c)
    pfas_conf = p["confidence"]

    # CAPEX (central, lo, hi)
    capex_m    = ds_tpd * 365 * p["capex_aud_per_tds_yr"]     / 1e6
    capex_lo_m = ds_tpd * 365 * p["capex_aud_per_tds_yr_lo"]  / 1e6
    capex_hi_m = ds_tpd * 365 * p["capex_aud_per_tds_yr_hi"]  / 1e6

    # OPEX
    opex_tds   = p["opex_aud_per_tds"]
    opex_yr    = ds_tpd * 365 * opex_tds

    # P recovery
    p_rec_kg_d = p_in_kg_d * p["p_recovery_pct"] / 100
    p_rec_pct  = p["p_recovery_pct"]
    p_path     = p["p_pathway"]

    # Net GHG
    # Avoided grid emissions from net electricity export
    avoided_grid = net_kwh_yr * grid_intensity     # kg CO2e/yr avoided
    # For pyrolysis: biochar sequestration credit
    if tech_id == "pyrolysis":
        biochar_c_kg_d = residual_t_d * 1000 * 0.52 * p["biochar_c_stable_frac"]
        seq_credit_kg_co2e_yr = biochar_c_kg_d * 365 * 44/12   # C → CO2e
    else:
        seq_credit_kg_co2e_yr = 0
    # HTL: bio-crude displaces diesel
    if tech_id == "htl":
        biocrude_l_d  = ds_tpd * p["biocrude_frac_ds"] * 1000 / 0.85  # ~0.85 kg/L
        avoided_diesel = biocrude_l_d * 365 * DIESEL_EMISSION_FACTOR
    else:
        avoided_diesel = 0

    net_ghg_yr = -(avoided_grid + seq_credit_kg_co2e_yr + avoided_diesel)  # negative = net avoided

    # ── Nitrogen fate (from cnp_fate) ─────────────────────────────────────
    n_in_kg_d_val = n_in_kg_d
    n_atm = n_to_liq = n_to_sol = nox = 0.0
    n_liq_note = ""
    try:
        from cnp_fate import TECH_PARTITIONS as _CNP_PARTS
    except ImportError:
        try:
            import sys as _sn; _sn.path.insert(0, "/mnt/user-data/outputs")
            from cnp_fate import TECH_PARTITIONS as _CNP_PARTS
        except ImportError:
            _CNP_PARTS = None
    if _CNP_PARTS and tech_id in _CNP_PARTS:
        _np = _CNP_PARTS[tech_id]["N"]
        n_atm = n_in_kg_d * (_np.get("atm_nox",0) + _np.get("atm_n2",0)
                               + _np.get("atm_n2o",0) + _np.get("atm_nh3",0))
        n_to_liq = n_in_kg_d * (_np.get("digestate_liq",0)
                                  + _np.get("thermal_liq",0))
        n_to_sol = n_in_kg_d * (_np.get("thermal_char",0)
                                  + _np.get("digestate_sol",0))
        nox      = n_in_kg_d * _np.get("atm_nox", 0)
        if n_to_liq > n_in_kg_d * 0.5:
            n_liq_note = (
                f"{n_to_liq:,.0f} kg N/day in aqueous product "
                "(larger sidestream burden than typical digestion centrate). "
                "Requires dedicated N-treatment or struvite recovery."
            )
        elif n_to_liq > 0:
            n_liq_note = (
                f"{n_to_liq:,.0f} kg N/day in condensate/scrubber liquor "
                "(sidestream treatment required)."
            )

    return ThermalResult(
        tech_id=tech_id,
        tech_name=p["name"],
        ds_tpd=ds_tpd,
        input_ds_pct=p["input_ds_pct_typ"],
        gross_elec_kw=gross_kw,
        parasitic_kw=para_kw,
        net_elec_kw=net_kw,
        net_elec_kwh_yr=net_kwh_yr,
        energy_revenue_aud_yr=elec_rev,
        residual_t_d=residual_t_d,
        product_description=product_desc,
        pfas_dre_pct=dre * 100,
        pfas_confidence=pfas_conf,
        capex_aud_m=capex_m,
        capex_lo_aud_m=capex_lo_m,
        capex_hi_aud_m=capex_hi_m,
        opex_aud_per_tds=opex_tds,
        opex_total_aud_yr=opex_yr,
        p_recovered_kg_d=p_rec_kg_d,
        p_recovery_pct=p_rec_pct,
        p_pathway=p_path,
        net_ghg_kg_co2e_d=net_ghg_yr / 365,
        net_ghg_t_co2e_yr=net_ghg_yr / 1000,
        n_in_kg_d=n_in_kg_d_val,
        n_to_atm_kg_d=n_atm,
        n_to_liquid_kg_d=n_to_liq,
        n_to_solid_kg_d=n_to_sol,
        n_atm_pct=n_atm/n_in_kg_d_val*100 if n_in_kg_d_val>0 else 0,
        n_liquid_pct=n_to_liq/n_in_kg_d_val*100 if n_in_kg_d_val>0 else 0,
        n_liquid_note=n_liq_note,
        nox_kg_d=nox,
        min_viable_tds_d=p["min_viable_tds_d"],
        scale_viable=ds_tpd >= p["min_viable_tds_d"],
        maturity=p["maturity"],
        confidence=p["confidence"],
    )


def run_thermal_comparison(
    ds_tpd:         float,
    p_in_kg_d:      float,
    n_in_kg_d:      float = 0.0,
    grid_intensity: float = GRID_INTENSITY_DEFAULT,
    elec_price:     float = 0.12,
) -> list[ThermalResult]:
    """Run all four thermal technologies for comparison."""
    return [
        run_thermal(tid, ds_tpd, p_in_kg_d, n_in_kg_d, grid_intensity, elec_price)
        for tid in TECH_IDS
    ]


# ── Scale-adjusted CAPEX helper ────────────────────────────────────────────

def scale_adjusted_capex(tech_id: str, ds_tpd: float) -> dict:
    """
    Return scale-adjusted CAPEX estimate.
    Small plants (<20 tDS/d) carry a scale penalty of 1.5–2.5×.
    Large plants (>100 tDS/d) benefit from economy of scale (~0.7×).
    Uses a 0.6 scaling exponent (standard for process plant scale-up).
    """
    p = TECH_PARAMS[tech_id]
    ref_scale = 50.0  # tDS/d reference scale for unit rate
    scale_factor = (ds_tpd / ref_scale) ** 0.6 / (ds_tpd / ref_scale)
    # scale_factor > 1 for small plants, < 1 for large
    adj_unit = p["capex_aud_per_tds_yr"] * scale_factor
    total_m  = ds_tpd * 365 * adj_unit / 1e6
    return {
        "unit_rate_aud_per_tds_yr":  adj_unit,
        "total_capex_aud_m":          total_m,
        "scale_factor":               scale_factor,
        "note": (f"Scale-adjusted from ${p['capex_aud_per_tds_yr']:.0f}/tDS/yr "
                 f"reference (50 tDS/d) using 0.6 exponent"),
    }


# ── Self-test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("THERMAL TREATMENT SCREENING — ETP 220 tDS/d")
    print("="*72)
    print(f"\n{'Technology':22} {'Net kW':>8} {'MWh/yr':>8} "
          f"{'PFAS DRE':>10} {'Capex $M':>10} {'Opex $/yr':>12} {'P rec%':>8}")
    print("-"*72)

    results = run_thermal_comparison(ds_tpd=220, p_in_kg_d=4400)
    for r in results:
        viable = "✓" if r.scale_viable else "✗"
        print(f"  {r.tech_name:20} {r.net_elec_kw:>8.0f} {r.net_elec_kwh_yr/1e6:>7.1f}M "
              f"{r.pfas_dre_pct:>9.0f}%  ${r.capex_aud_m:>7.0f}M  "
              f"${r.opex_total_aud_yr/1e6:>8.1f}M/yr  {r.p_recovery_pct:>7.0f}%  {viable}")

    print()
    print("PFAS DRE temperature sensitivity:")
    for tid, temps in [("pyrolysis",[400,500,600,700]),
                        ("gasification",[750,850,1000]),
                        ("incineration",[800,850,900])]:
        line = f"  {tid:14}: " + "  ".join(f"{t}°C={pfas_dre(tid,t)*100:.0f}%" for t in temps)
        print(line)

    print()
    print("Scale viability (minimum tDS/d):")
    for tid in TECH_IDS:
        p = TECH_PARAMS[tid]
        print(f"  {p['name']:28}: ≥{p['min_viable_tds_d']:3} tDS/d  "
              f"({p['maturity']})")
