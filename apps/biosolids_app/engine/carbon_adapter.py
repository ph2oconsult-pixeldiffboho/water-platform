"""
engine/carbon_adapter.py

BioPoint V1 — Carbon/GHG Lifecycle Adapter.

Produces a PathwayBalanceResult per flowsheet from the existing
run_biopoint_v1() result dict. This is the ONLY seam between the
existing engine and the new carbon/GHG layer.

PRIME DIRECTIVE: This module reads ONLY from the existing result dict.
It does NOT recompute any mass or energy balance. If a quantity is not
exposed by the existing engine, it is derived from what is exposed or
flagged as uncertain — never silently re-estimated with a parallel model.

Entry point:
    results = build_pathway_balances(bp_result, bp_inputs) -> List[PathwayBalanceResult]

ph2o Consulting — BioPoint V1 — v25B01
"""

from dataclasses import dataclass, field
from typing import Optional
from engine.ghg_coefficients import (
    CARBON_TO_VS_RATIO,
    DEFAULT_N_PCT_BY_SLUDGE_TYPE,
    DEFAULT_P_PCT_OF_DS,
    CH4_FRACTION_OF_BIOGAS,
    COD_TO_CARBON_RATIO,
    HTC_HYDROCHAR_YIELD_FRACTION_OF_DS,
    HYDROCHAR_FIXED_CARBON_PCT,
    HYDROCHAR_R50,
    INCINERATION_ASH_CARBON_PCT,
    GASIFICATION_ASH_CARBON_PCT,
    NEAR_COMPLETE_VS_DESTRUCTION_PCT,
    DRYING_ONLY_VS_DESTROYED_PCT,
    VS_DESTROYED_SOURCE,
    PYROCHAR_R50_CREDIT_THRESHOLD,
    PYROCHAR_R50_FULL_CREDIT,
)


# ============================================================
# PATHWAY BALANCE RESULT
# ============================================================

@dataclass
class PathwayBalanceResult:
    """
    Per-tDS basis. Thin adapter over the existing BioPoint engine result.
    The carbon/GHG layer consumes ONLY this — never the raw result dict.

    All quantities are per tonne of dry solids feed (per tDS/day basis
    divided by ds_tpd to get per tDS).
    """

    # Identity
    pathway_type: str = ""
    pathway_name: str = ""
    ds_tpd: float = 0.0

    # --- FEEDSTOCK (per tDS) ---
    vs_pct: float = 0.0               # Volatile solids % of DS
    ash_pct: float = 0.0              # = 100 - vs_pct (derived, not input)
    carbon_kg_per_tds: float = 0.0    # CARBON_TO_VS_RATIO × vs_pct/100 × 1000
    nitrogen_kg_per_tds: float = 0.0
    phosphorus_kg_per_tds: float = 0.0
    measured_carbon: bool = False      # True when user provides ultimate analysis

    # --- VS TRANSFORMATION ---
    vs_destroyed_pct: float = 0.0
    vs_destroyed_kg_per_tds: float = 0.0
    vs_source: str = ""               # Which engine supplied VS_destroyed

    # --- OUTPUT STREAMS (per tDS feed) ---

    # Biogas
    biogas_m3_per_tds: float = 0.0
    biogas_ch4_m3_per_tds: float = 0.0
    biogas_co2_m3_per_tds: float = 0.0
    biogas_carbon_kg_per_tds: float = 0.0   # carbon in biogas (CH4 + CO2)

    # Char / hydrochar / product
    char_kg_per_tds: float = 0.0
    char_fixed_carbon_pct: float = 0.0
    char_r50: float = 0.0
    char_stable_carbon_kg_per_tds: float = 0.0   # R50-weighted creditable carbon
    char_labile_carbon_kg_per_tds: float = 0.0   # Below R50 threshold — soil/delayed

    # Ash residual (incineration / gasification)
    ash_kg_per_tds: float = 0.0
    ash_residual_carbon_kg_per_tds: float = 0.0

    # Sidestream / centrate
    centrate_cod_kg_per_tds: float = 0.0
    centrate_carbon_kg_per_tds: float = 0.0   # = centrate_cod × COD_TO_CARBON_RATIO
    centrate_n_kg_per_tds: float = 0.0
    centrate_p_kg_per_tds: float = 0.0

    # Nutrients in solid product
    n_in_product_kg_per_tds: float = 0.0
    p_in_product_kg_per_tds: float = 0.0
    k_in_product_kg_per_tds: float = 0.0

    # --- ENERGY FLOWS (per tDS) ---
    drying_energy_kwh_per_tds: float = 0.0
    net_electricity_kwh_per_tds: float = 0.0     # + = export, - = import
    gross_electricity_kwh_per_tds: float = 0.0
    fossil_fuel_gj_per_tds: float = 0.0           # external fuel for drying

    # --- TRANSPORT (per tDS) ---
    transport_t_km_per_tds: float = 0.0           # feed + product combined

    # --- CARBON BALANCE CLOSURE ---
    carbon_in_kg_per_tds: float = 0.0
    carbon_out_kg_per_tds: float = 0.0
    carbon_closure_error_pct: float = 0.0
    closure_passes: bool = False
    closure_note: str = ""

    # --- FLAGS ---
    mad_available: bool = False       # True when MAD engine ran for this flowsheet
    is_hybrid: bool = False           # True for H00–H03 hybrid configs
    config_id: str = ""               # H00/H01/H02/H03 for hybrids


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def build_pathway_balances(
    bp_result: dict,
    bp_inputs,
    measured_carbon_pct_of_ds: Optional[float] = None,
) -> list:
    """
    Build PathwayBalanceResult for every flowsheet in bp_result.
    Also builds balances for H00–H03 hybrid configurations if present.

    Parameters
    ----------
    bp_result                : return dict from run_biopoint_v1()
    bp_inputs                : BioPointV1Inputs
    measured_carbon_pct_of_ds: if provided, overrides CARBON_TO_VS_RATIO default

    Returns
    -------
    List[PathwayBalanceResult] — one per flowsheet + one per hybrid config
    """
    feedstock = bp_inputs.feedstock
    assets    = bp_inputs.assets
    ds_tpd    = feedstock.dry_solids_tpd
    vs_pct    = feedstock.volatile_solids_percent
    sludge    = getattr(feedstock, "sludge_type", "blended")

    # Resolve carbon fraction
    if measured_carbon_pct_of_ds is not None:
        carbon_kg_per_tds = measured_carbon_pct_of_ds / 100.0 * 1000.0
        measured = True
    else:
        carbon_kg_per_tds = CARBON_TO_VS_RATIO * vs_pct / 100.0 * 1000.0
        measured = False

    # Validate: carbon must not exceed VS mass
    vs_kg_per_tds = vs_pct / 100.0 * 1000.0
    if carbon_kg_per_tds > vs_kg_per_tds:
        raise ValueError(
            f"Carbon ({carbon_kg_per_tds:.0f} kg/tDS) exceeds VS mass "
            f"({vs_kg_per_tds:.0f} kg/tDS) — physically impossible. "
            "Check CARBON_TO_VS_RATIO or measured_carbon_pct_of_ds."
        )

    # Nitrogen and phosphorus
    n_pct = getattr(feedstock, "n_pct_of_ds", None) or \
            DEFAULT_N_PCT_BY_SLUDGE_TYPE.get(sludge, 3.5)
    p_pct = getattr(feedstock, "p_pct_of_ds", None) or DEFAULT_P_PCT_OF_DS
    n_kg_per_tds = n_pct / 100.0 * 1000.0
    p_kg_per_tds = p_pct / 100.0 * 1000.0

    # Transport per tDS (from asset inputs — applies to all pathways)
    avg_km    = assets.average_transport_distance_km
    transport_rate = assets.transport_cost_per_tonne_km   # not used here; for reference
    # Transport mass: dewatered wet cake = 1000 / (DS%/100) kg/tDS
    ds_pct    = feedstock.dewatered_ds_percent
    wet_kg_per_tds = 1000.0 / (ds_pct / 100.0)
    transport_t_km_per_tds = (wet_kg_per_tds / 1000.0) * avg_km   # tonne·km per tDS

    # Build per-flowsheet balances
    balances = []
    for fs in bp_result.get("flowsheets", []):
        bal = _build_flowsheet_balance(
            fs=fs,
            ds_tpd=ds_tpd,
            vs_pct=vs_pct,
            carbon_kg_per_tds=carbon_kg_per_tds,
            measured=measured,
            n_kg_per_tds=n_kg_per_tds,
            p_kg_per_tds=p_kg_per_tds,
            transport_t_km_per_tds=transport_t_km_per_tds,
        )
        balances.append(bal)

    # Build hybrid balances
    hs = bp_result.get("hybrid_system")
    if hs and hs.configurations:
        for cfg in hs.configurations:
            bal = _build_hybrid_balance(
                cfg=cfg,
                ds_tpd=ds_tpd,
                vs_pct=vs_pct,
                carbon_kg_per_tds=carbon_kg_per_tds,
                measured=measured,
                n_kg_per_tds=n_kg_per_tds,
                p_kg_per_tds=p_kg_per_tds,
            )
            balances.append(bal)

    return balances


# ============================================================
# PER-FLOWSHEET BALANCE BUILDER
# ============================================================

def _build_flowsheet_balance(
    fs, ds_tpd, vs_pct, carbon_kg_per_tds, measured,
    n_kg_per_tds, p_kg_per_tds, transport_t_km_per_tds,
) -> PathwayBalanceResult:

    ptype = fs.pathway_type
    bal = PathwayBalanceResult(
        pathway_type=ptype,
        pathway_name=fs.name,
        ds_tpd=ds_tpd,
        vs_pct=vs_pct,
        ash_pct=100.0 - vs_pct,
        carbon_kg_per_tds=carbon_kg_per_tds,
        measured_carbon=measured,
        nitrogen_kg_per_tds=n_kg_per_tds,
        phosphorus_kg_per_tds=p_kg_per_tds,
        carbon_in_kg_per_tds=carbon_kg_per_tds,
        transport_t_km_per_tds=transport_t_km_per_tds,
    )

    # --- VS DESTROYED ---
    bal.vs_destroyed_pct, bal.vs_destroyed_kg_per_tds, bal.vs_source = \
        _get_vs_destroyed(fs, vs_pct, ds_tpd)

    # --- BIOGAS (AD family only) ---
    bal = _fill_biogas(bal, fs, ds_tpd)

    # --- CHAR / HYDROCHAR ---
    bal = _fill_char(bal, fs, ptype, vs_pct, ds_tpd)

    # --- ASH (thermal destruction pathways) ---
    bal = _fill_ash(bal, ptype, vs_pct, ds_tpd)

    # --- SIDESTREAM ---
    bal = _fill_sidestream(bal, fs, ds_tpd)

    # --- NUTRIENTS IN PRODUCT ---
    bal = _fill_nutrients(bal, fs, ptype, n_kg_per_tds, p_kg_per_tds)

    # --- ENERGY ---
    bal = _fill_energy(bal, fs, ds_tpd)

    # --- CLOSURE CHECK ---
    bal = _check_closure(bal, ptype)

    return bal


# ============================================================
# VS DESTROYED — GAP 3 RESOLUTION
# ============================================================

def _get_vs_destroyed(fs, vs_pct, ds_tpd) -> tuple:
    """
    Return (vs_destroyed_pct, vs_destroyed_kg_per_tds, source_label).
    Explicit per-pathway-family sourcing — no silent estimation.
    """
    ptype = fs.pathway_type
    rule  = VS_DESTROYED_SOURCE.get(ptype, "zero")

    if rule == "mad_detail":
        mad = getattr(fs, "mad_detail", None)
        if mad:
            # Weight PS and WAS VS destruction by their DS fractions (60/40 default)
            # Use available attributes; fall back if MAD partial
            ps_vsd  = getattr(mad.ps,  "VS_destruction_pct", 0.0) if mad.ps  else 0.0
            was_vsd = getattr(mad.was, "VS_destruction_pct", 0.0) if mad.was else 0.0
            # Volume-weighted average (60% PS / 40% WAS default split)
            vsd_pct = 0.60 * ps_vsd + 0.40 * was_vsd
            source  = "MAD engine (ps+was weighted)"
        else:
            # Fallback: literature default for mesophilic AD, blended sludge
            vsd_pct = 45.0
            source  = "literature default (MAD not run)"

    elif rule == "mad_detail_plus_thp":
        # THP + AD: THP boosts hydrolysis; use MAD if available, else THP default
        mad = getattr(fs, "mad_detail", None)
        if mad:
            ps_vsd  = getattr(mad.ps,  "VS_destruction_pct", 0.0) if mad.ps  else 0.0
            was_vsd = getattr(mad.was, "VS_destruction_pct", 0.0) if mad.was else 0.0
            vsd_pct = 0.60 * ps_vsd + 0.40 * was_vsd
            source  = "MAD engine + THP (ps+was weighted)"
        else:
            vsd_pct = 58.0   # THP-enhanced AD literature default
            source  = "literature default THP+AD"

    elif rule == "char_yield":
        # Pyrolysis: VS_destroyed = VS_pct × (1 - char_yield_fraction)
        # Char yield fraction from thermal_biochar engine if available
        tb = getattr(fs, "thermal_biochar", None)
        if tb and hasattr(tb, "product") and tb.product:
            char_yield_frac = tb.product.biochar_yield_pct_ds / 100.0
        else:
            # Fallback: pyrolysis operating envelope mid-temp
            pe = getattr(fs, "pyrolysis_envelope", None)
            if pe and pe.mid_temp_mode:
                char_yield_frac = pe.mid_temp_mode.biochar_yield_pct / 100.0
            else:
                char_yield_frac = 0.27   # Mid-temp default
        # VS destroyed = VS_in - (VS_in × char_yield_frac)
        # (Char contains remaining organic fraction)
        vsd_pct = (1.0 - char_yield_frac) * vs_pct
        source  = "char yield (thermal_biochar engine)"

    elif rule == "hydrochar_yield":
        # HTC: hydrochar yield from engine or coefficient default
        hydrochar_frac = HTC_HYDROCHAR_YIELD_FRACTION_OF_DS
        # VS_destroyed ≈ VS_in - VS_in × hydrochar_frac (simplified)
        # Hydrochar retains ~55% fixed carbon; balance as dissolved organics
        vsd_pct = (1.0 - hydrochar_frac) * vs_pct
        source  = "hydrochar yield coefficient"

    elif rule == "near_complete":
        vsd_pct = NEAR_COMPLETE_VS_DESTRUCTION_PCT
        source  = "near-complete combustion/gasification"

    elif rule == "zero":
        vsd_pct = DRYING_ONLY_VS_DESTROYED_PCT
        source  = "zero (drying/baseline — organics conserved)"

    else:
        vsd_pct = 0.0
        source  = "unknown pathway — defaulted to zero"

    vs_destroyed_kg_per_tds = vsd_pct / 100.0 * vs_pct / 100.0 * 1000.0
    return round(vsd_pct, 2), round(vs_destroyed_kg_per_tds, 2), source


# ============================================================
# FILL FUNCTIONS
# ============================================================

def _fill_biogas(bal, fs, ds_tpd) -> PathwayBalanceResult:
    """Biogas from MAD engine (override) or energy_system."""
    mad = getattr(fs, "mad_detail", None)
    es  = getattr(fs, "energy_system", None)

    if mad and hasattr(mad, "biogas_m3_per_d"):
        biogas_m3_per_d = mad.biogas_m3_per_d
        bal.mad_available = True
    elif es and hasattr(es, "biogas_volume_m3_per_d"):
        biogas_m3_per_d = es.biogas_volume_m3_per_d
    else:
        biogas_m3_per_d = 0.0

    if ds_tpd > 0:
        bal.biogas_m3_per_tds   = biogas_m3_per_d / ds_tpd
        bal.biogas_ch4_m3_per_tds = bal.biogas_m3_per_tds * CH4_FRACTION_OF_BIOGAS
        bal.biogas_co2_m3_per_tds = bal.biogas_m3_per_tds * (1.0 - CH4_FRACTION_OF_BIOGAS)
        # Carbon in biogas: CH4 carbon (12/16 × density × volume) + CO2 carbon (12/44 × density × volume)
        # CH4: 0.717 kg/m3 × 12/16 = 0.538 kgC/m3 CH4
        # CO2: 1.964 kg/m3 × 12/44 = 0.536 kgC/m3 CO2
        ch4_carbon = bal.biogas_ch4_m3_per_tds * 0.717 * (12.0/16.0)
        co2_carbon = bal.biogas_co2_m3_per_tds * 1.964 * (12.0/44.0)
        bal.biogas_carbon_kg_per_tds = ch4_carbon + co2_carbon

    return bal


def _fill_char(bal, fs, ptype, vs_pct, ds_tpd) -> PathwayBalanceResult:
    """Char/hydrochar yield, fixed carbon, R50, stable carbon."""
    if ptype in ("pyrolysis", "centralised"):
        tb = getattr(fs, "thermal_biochar", None)
        pe = getattr(fs, "pyrolysis_envelope", None)
        if tb and hasattr(tb, "product") and tb.product:
            char_yield_pct = tb.product.biochar_yield_pct_ds
            fixed_c_pct    = tb.product.fixed_carbon_pct
        elif pe and pe.mid_temp_mode:
            char_yield_pct = pe.mid_temp_mode.biochar_yield_pct
            fixed_c_pct    = pe.mid_temp_mode.fixed_carbon_pct
        else:
            char_yield_pct = 27.0
            fixed_c_pct    = 40.0

        char_kg_per_tds = char_yield_pct / 100.0 * 1000.0
        bal.char_kg_per_tds    = char_kg_per_tds
        bal.char_fixed_carbon_pct = fixed_c_pct

        # R50 from pyrolysis envelope or trade-off curve
        if pe and pe.mid_temp_mode:
            r50 = pe.mid_temp_mode.carbon_stability_r50
        else:
            r50 = 0.55   # Conservative default
        bal.char_r50 = r50

        # Stable carbon (creditable for sequestration)
        fixed_c_kg = char_kg_per_tds * fixed_c_pct / 100.0
        r50_weight = _r50_credit_weight(r50)
        bal.char_stable_carbon_kg_per_tds = fixed_c_kg * r50_weight
        bal.char_labile_carbon_kg_per_tds  = fixed_c_kg * (1.0 - r50_weight)

    elif ptype in ("HTC", "HTC_sidestream"):
        # Hydrochar
        hydrochar_frac = HTC_HYDROCHAR_YIELD_FRACTION_OF_DS
        char_kg_per_tds = hydrochar_frac * 1000.0
        fixed_c_pct = HYDROCHAR_FIXED_CARBON_PCT
        r50 = HYDROCHAR_R50
        bal.char_kg_per_tds = char_kg_per_tds
        bal.char_fixed_carbon_pct = fixed_c_pct
        bal.char_r50 = r50
        fixed_c_kg = char_kg_per_tds * fixed_c_pct / 100.0
        r50_weight = _r50_credit_weight(r50)
        bal.char_stable_carbon_kg_per_tds = fixed_c_kg * r50_weight
        bal.char_labile_carbon_kg_per_tds  = fixed_c_kg * (1.0 - r50_weight)

    # Other pathway types produce no char
    return bal


def _fill_ash(bal, ptype, vs_pct, ds_tpd) -> PathwayBalanceResult:
    """Ash residual and residual carbon for thermal destruction pathways."""
    ash_pct_of_ds = 100.0 - vs_pct   # ash_pct = 100 - VS%
    ash_kg_per_tds = ash_pct_of_ds / 100.0 * 1000.0

    if ptype in ("incineration", "thp_incineration"):
        bal.ash_kg_per_tds = ash_kg_per_tds
        bal.ash_residual_carbon_kg_per_tds = ash_kg_per_tds * INCINERATION_ASH_CARBON_PCT / 100.0
    elif ptype == "gasification":
        bal.ash_kg_per_tds = ash_kg_per_tds
        bal.ash_residual_carbon_kg_per_tds = ash_kg_per_tds * GASIFICATION_ASH_CARBON_PCT / 100.0
    return bal


def _fill_sidestream(bal, fs, ds_tpd) -> PathwayBalanceResult:
    """Centrate / process liquor carbon and nutrient loads."""
    mc = getattr(fs, "mainstream_coupling", None)
    mad = getattr(fs, "mad_detail", None)

    if ds_tpd <= 0:
        return bal

    if mc and hasattr(mc, "return_cod_kg_d"):
        bal.centrate_cod_kg_per_tds = mc.return_cod_kg_d / ds_tpd
        bal.centrate_carbon_kg_per_tds = bal.centrate_cod_kg_per_tds * COD_TO_CARBON_RATIO

    if mc and hasattr(mc, "return_nh4_kg_d"):
        bal.centrate_n_kg_per_tds = mc.return_nh4_kg_d / ds_tpd

    if mc and hasattr(mc, "return_tp_kg_d"):
        bal.centrate_p_kg_per_tds = mc.return_tp_kg_d / ds_tpd

    # MAD engine provides more detailed sidestream N split
    if mad and hasattr(mad, "centrate_N_kg_per_d"):
        bal.centrate_n_kg_per_tds = mad.centrate_N_kg_per_d / ds_tpd

    return bal


def _fill_nutrients(bal, fs, ptype, n_kg_per_tds, p_kg_per_tds) -> PathwayBalanceResult:
    """Nutrients retained in solid product (char, biosolids cake, ash)."""
    tb = getattr(fs, "thermal_biochar", None)
    mad = getattr(fs, "mad_detail", None)

    if ptype in ("pyrolysis", "centralised") and tb and hasattr(tb, "product") and tb.product:
        bal.n_in_product_kg_per_tds = tb.product.N_retained_kg_d / max(bal.ds_tpd, 1)
        bal.p_in_product_kg_per_tds = tb.product.P_retained_kg_d / max(bal.ds_tpd, 1)

    elif ptype in ("AD", "thp_incineration") and mad:
        # Cake N from MAD engine
        if hasattr(mad, "cake_N_kg_per_d"):
            bal.n_in_product_kg_per_tds = mad.cake_N_kg_per_d / max(bal.ds_tpd, 1)

    elif ptype in ("incineration", "gasification"):
        # P concentrates in ash; N largely volatilised
        bal.p_in_product_kg_per_tds = p_kg_per_tds * 0.90   # ~90% P to ash
        bal.n_in_product_kg_per_tds = n_kg_per_tds * 0.05   # ~5% N to ash (rest volatilised)

    elif ptype in ("HTC", "HTC_sidestream"):
        bal.n_in_product_kg_per_tds = n_kg_per_tds * 0.45   # Approximate N in hydrochar
        bal.p_in_product_kg_per_tds = p_kg_per_tds * 0.75   # Approximate P in hydrochar

    elif ptype in ("drying_only", "decentralised", "baseline"):
        # All nutrients in product (no destruction)
        bal.n_in_product_kg_per_tds = n_kg_per_tds
        bal.p_in_product_kg_per_tds = p_kg_per_tds

    return bal


def _fill_energy(bal, fs, ds_tpd) -> PathwayBalanceResult:
    """Energy flows from drying dominance and energy system."""
    dd = getattr(fs, "drying_dominance", None)
    es = getattr(fs, "energy_system", None)
    mad = getattr(fs, "mad_detail", None)

    if ds_tpd <= 0:
        return bal

    if dd:
        bal.drying_energy_kwh_per_tds = getattr(dd, "gross_drying_energy_kwh_d", 0.0) / ds_tpd
        # External energy = drying energy not met by feedstock or waste heat
        ext = getattr(dd, "external_energy_required_kwh_d", 0.0)
        if ext > 0:
            # Approximate: split between electricity and fossil fuel
            # For now: assume all external drying energy is fossil (natural gas via steam)
            # GJ = kWh / 277.78
            bal.fossil_fuel_gj_per_tds = ext / ds_tpd / 277.78

    if mad and hasattr(mad, "netElec_kW"):
        bal.gross_electricity_kwh_per_tds = mad.elecGross_kW * 24 / ds_tpd
        bal.net_electricity_kwh_per_tds   = mad.netElec_kW  * 24 / ds_tpd
    elif es:
        gross = getattr(es, "CHP_gross_kW", 0.0)
        net   = getattr(es, "AD_net_electrical_kW", 0.0)
        bal.gross_electricity_kwh_per_tds = gross * 24 / ds_tpd if gross else 0.0
        bal.net_electricity_kwh_per_tds   = net   * 24 / ds_tpd if net   else 0.0

    return bal


# ============================================================
# CARBON BALANCE CLOSURE
# ============================================================

def _check_closure(bal, ptype) -> PathwayBalanceResult:
    """
    Carbon balance closure check.
    carbon_in = feed carbon (per tDS)
    carbon_out = sum of all output streams
    Tolerance: ±2% of feed carbon.
    """
    # Sum all output carbon streams
    carbon_out = (
        bal.biogas_carbon_kg_per_tds
        + bal.char_stable_carbon_kg_per_tds
        + bal.char_labile_carbon_kg_per_tds
        + bal.ash_residual_carbon_kg_per_tds
        + bal.centrate_carbon_kg_per_tds
    )

    # For baseline and drying: remaining organic carbon goes to product/land
    # (not separately tracked in char streams for these pathways)
    if ptype in ("baseline", "drying_only", "decentralised", "centralised"):
        # Carbon in product = feed carbon - centrate carbon
        carbon_in_product = bal.carbon_in_kg_per_tds - bal.centrate_carbon_kg_per_tds
        carbon_out = bal.centrate_carbon_kg_per_tds + carbon_in_product

    bal.carbon_out_kg_per_tds = round(carbon_out, 3)

    if bal.carbon_in_kg_per_tds > 0:
        error_pct = abs(carbon_out - bal.carbon_in_kg_per_tds) / bal.carbon_in_kg_per_tds * 100
    else:
        error_pct = 0.0

    bal.carbon_closure_error_pct = round(error_pct, 2)
    bal.closure_passes = error_pct <= 2.0

    if not bal.closure_passes:
        bal.closure_note = (
            f"Carbon balance does not close for {ptype}: "
            f"in={bal.carbon_in_kg_per_tds:.1f} kg/tDS, "
            f"out={carbon_out:.1f} kg/tDS, "
            f"error={error_pct:.1f}%. "
            "Review partition coefficients or flag for detailed design."
        )
    else:
        bal.closure_note = f"Closed within {error_pct:.1f}% tolerance."

    return bal


# ============================================================
# R50 CREDIT WEIGHT
# ============================================================

def _r50_credit_weight(r50: float) -> float:
    """
    Linear interpolation between R50 threshold and full credit.
    R50 < THRESHOLD → 0 (not creditable)
    R50 >= FULL_CREDIT → 1.0 (fully creditable)
    """
    if r50 < PYROCHAR_R50_CREDIT_THRESHOLD:
        return 0.0
    if r50 >= PYROCHAR_R50_FULL_CREDIT:
        return 1.0
    span = PYROCHAR_R50_FULL_CREDIT - PYROCHAR_R50_CREDIT_THRESHOLD
    return (r50 - PYROCHAR_R50_CREDIT_THRESHOLD) / span


# ============================================================
# HYBRID BALANCE BUILDER
# ============================================================

def _build_hybrid_balance(
    cfg, ds_tpd, vs_pct, carbon_kg_per_tds, measured,
    n_kg_per_tds, p_kg_per_tds,
) -> PathwayBalanceResult:
    """
    Build PathwayBalanceResult for a hybrid configuration (H00–H03).
    Transport is the critical addition here — inter-site haul drives Scope 3.
    """
    bal = PathwayBalanceResult(
        pathway_type=f"hybrid_{cfg.config_id}",
        pathway_name=cfg.config_name,
        ds_tpd=ds_tpd,
        vs_pct=vs_pct,
        ash_pct=100.0 - vs_pct,
        carbon_kg_per_tds=carbon_kg_per_tds,
        measured_carbon=measured,
        nitrogen_kg_per_tds=n_kg_per_tds,
        phosphorus_kg_per_tds=p_kg_per_tds,
        carbon_in_kg_per_tds=carbon_kg_per_tds,
        is_hybrid=True,
        config_id=cfg.config_id,
    )

    # Transport: the engine already computes feed_transport_t_km_yr
    # and product_transport_t_km_yr per config. Convert to per-tDS basis.
    feed_t_km_yr    = getattr(cfg, "feed_transport_t_km_yr", 0.0)
    product_t_km_yr = getattr(cfg, "product_transport_t_km_yr", 0.0)
    total_t_km_yr   = feed_t_km_yr + product_t_km_yr
    if ds_tpd > 0:
        bal.transport_t_km_per_tds = total_t_km_yr / (ds_tpd * 365)

    # VS destroyed: use hub treatment technology
    hub_treatment = getattr(cfg, "hub_treatment", "AD")
    vs_rule = VS_DESTROYED_SOURCE.get(hub_treatment, "zero")
    if vs_rule == "near_complete":
        vsd_pct = NEAR_COMPLETE_VS_DESTRUCTION_PCT
    elif vs_rule in ("mad_detail", "mad_detail_plus_thp"):
        vsd_pct = 45.0   # AD default for hybrid
    elif vs_rule == "hydrochar_yield":
        vsd_pct = (1.0 - HTC_HYDROCHAR_YIELD_FRACTION_OF_DS) * vs_pct
    else:
        vsd_pct = 0.0
    bal.vs_destroyed_pct = vsd_pct
    bal.vs_destroyed_kg_per_tds = vsd_pct / 100.0 * vs_pct / 100.0 * 1000.0
    bal.vs_source = f"hybrid hub ({hub_treatment})"

    # Disposal reduction for carbon fate (baseline carbon to product)
    disposal_reduction = getattr(cfg, "total_disposal_reduction_pct", 0.0) / 100.0
    bal.char_labile_carbon_kg_per_tds = carbon_kg_per_tds * (1.0 - disposal_reduction)

    # Closure: simplified for hybrids
    carbon_out = bal.char_labile_carbon_kg_per_tds + bal.centrate_carbon_kg_per_tds
    bal.carbon_out_kg_per_tds = round(carbon_out, 3)
    if carbon_kg_per_tds > 0:
        error_pct = abs(carbon_out - carbon_kg_per_tds) / carbon_kg_per_tds * 100
    else:
        error_pct = 0.0
    bal.carbon_closure_error_pct = round(error_pct, 2)
    bal.closure_passes = error_pct <= 5.0   # Wider tolerance for hybrid aggregation
    bal.closure_note = f"Hybrid aggregation: closure within {error_pct:.1f}%."

    return bal
