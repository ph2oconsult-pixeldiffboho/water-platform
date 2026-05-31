"""
engine/nutrient_recovery.py
BioPoint V1 — Nutrient Recovery Screening Module

Estimates the potential for nutrient recovery from digestion centrate
through three pathways:
  1. Struvite (MgNH4PO4·6H2O) crystallisation — recovers P and some N
  2. Ammonium sulphate (NH4)2SO4 — recovers N as a fertiliser product
  3. Partial nitritation / anammox (PN/A) — destroys N, reduces aeration load

Screening level only. All estimates use literature-based recovery
efficiencies. Site-specific treatability testing required for detailed design.

Literature basis:
  - Struvite: Doyle & Parsons 2002; Münch & Barr 2001; Bhuiyan et al. 2008
  - Ammonium sulphate: Lei et al. 2007; Bonmati & Flotats 2003
  - PN/A: Siegrist et al. 2008; Lackner et al. 2014; Cao et al. 2017
  - Market prices: ABARES 2024; DAF 2025 (AUD, ex-works estimate)

ph2o Consulting — v25B02
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

# ── Molecular constants ────────────────────────────────────────────────────
MW_P     = 30.97   # g/mol
MW_N     = 14.01   # g/mol
MW_Mg    = 24.31   # g/mol
MW_STRUVITE = 245.41  # MgNH4PO4·6H2O
MW_AS    = 132.14  # (NH4)2SO4
MW_MgCl2 = 95.21  # MgCl2 (common Mg source)
MW_MgO   = 40.30  # MgO (alternative)

# ── Default market prices (AUD/tonne, ex-works, 2024-25) ──────────────────
STRUVITE_PRICE_AUD_PER_T    = 550.0   # ~$300–800/t depending on purity/offtake
AS_PRICE_AUD_PER_T          = 350.0   # ~$200–450/t as liquid or granular
MGCL2_COST_AUD_PER_T        = 420.0   # MgCl2 reagent cost
H2SO4_COST_AUD_PER_T        = 180.0   # Sulphuric acid (98%)
CAOH2_COST_AUD_PER_T        = 220.0   # Ca(OH)2 for pH adjustment in stripping

# ── Default recovery efficiencies ─────────────────────────────────────────
STRUVITE_P_RECOVERY    = 0.65   # fraction of centrate P recovered as struvite
STRUVITE_SUPERSATURATION_FACTOR = 1.05  # Mg:P molar ratio (slight excess)
AS_NH3_STRIP_EFF       = 0.75   # fraction of centrate NH4-N stripped at pH>10, 50°C
AS_ABSORPTION_EFF      = 0.92   # fraction of stripped NH3 absorbed as AS
PNA_N_REMOVAL          = 0.88   # fraction of NH4-N removed by PN/A (to N2)
PNA_MIN_NH4_MG_L       = 400.0  # minimum centrate NH4-N for PN/A (mg/L)
PNA_ENERGY_SAVING      = 0.60   # energy saving vs conventional nitrification

# ── Centrate volume estimation ─────────────────────────────────────────────
# Dewatering centrate volume estimated from DS load and cake DS%
# Typical: 6–10 L centrate per kg DS fed (press filtrate)
CENTRATE_L_PER_KG_DS   = 8.0   # L/kg DS (mid-range for belt press / centrifuge)


@dataclass
class CentrateCharacterisation:
    """Centrate stream characterisation for a given configuration."""
    config_id:       str
    config_label:    str
    nh4_n_kg_d:      float   # NH4-N load, kg/day
    tp_kg_d:         float   # Total P load, kg/day
    volume_m3_d:     float   # Estimated centrate volume, m3/day
    nh4_n_mg_l:      float   # Concentration, mg/L
    tp_mg_l:         float   # Concentration, mg/L
    tn_mainstream_kg_d: float  # Mainstream TN for headroom calc


@dataclass
class StruviteResult:
    """Struvite crystallisation screening result."""
    config_id:          str
    p_available_kg_d:   float   # P entering struvite reactor
    struvite_kg_d:      float   # Struvite product, kg/day
    struvite_t_yr:      float   # Struvite product, t/year
    p_recovered_kg_d:   float   # P in struvite, kg/day
    n_removed_kg_d:     float   # NH4-N co-precipitated, kg/day
    mg_dose_kg_d:       float   # MgCl2 required, kg/day
    mg_cost_aud_yr:     float   # Reagent cost, AUD/year
    revenue_aud_yr:     float   # Gross revenue, AUD/year
    net_value_aud_yr:   float   # Revenue minus reagent, AUD/year
    p_recovery_pct:     float   # % of centrate P recovered
    n_recovery_pct:     float   # % of centrate NH4-N co-removed


@dataclass
class AmmoniumSulphateResult:
    """Ammonium sulphate (AS) recovery screening result."""
    config_id:          str
    n_available_kg_d:   float   # NH4-N entering stripping tower
    n_stripped_kg_d:    float   # NH4-N stripped as NH3
    as_kg_d:            float   # AS product, kg/day
    as_t_yr:            float   # AS product, t/year
    n_recovered_kg_d:   float   # N in AS product, kg/day
    h2so4_kg_d:         float   # H2SO4 required, kg/day
    caoh2_kg_d:         float   # Ca(OH)2 for pH adjustment, kg/day
    reagent_cost_aud_yr:float   # Total reagent cost, AUD/year
    revenue_aud_yr:     float   # Gross revenue, AUD/year
    net_value_aud_yr:   float   # Revenue minus reagents, AUD/year
    n_recovery_pct:     float   # % of centrate NH4-N recovered as AS


@dataclass
class PNAResult:
    """Partial nitritation / anammox screening result."""
    config_id:          str
    applicable:         bool    # True if NH4-N concentration meets threshold
    nh4_n_in_kg_d:      float   # NH4-N load to PN/A reactor
    n_removed_kg_d:     float   # NH4-N destroyed (to N2), kg/day
    n_removal_pct:      float   # % of influent NH4-N removed
    energy_saved_kwh_d: float   # vs conventional nitrification
    reason:             str     # Applicability note


@dataclass
class NutrientRecoverySummary:
    """Complete nutrient recovery analysis for one configuration."""
    config_id:      str
    config_label:   str
    centrate:       CentrateCharacterisation
    struvite:       StruviteResult
    amm_sulphate:   AmmoniumSulphateResult
    pna:            PNAResult

    # Combined metrics
    max_n_recovered_kg_d:   float   # Best-case N removed from return stream
    max_p_recovered_kg_d:   float   # Best-case P recovered
    max_revenue_aud_yr:     float   # Best-case combined revenue
    tn_headroom_base_pct:   float   # Return N as % of mainstream TN (no recovery)
    tn_headroom_best_pct:   float   # Return N as % after best recovery scenario


# ── Core calculation functions ─────────────────────────────────────────────

def characterise_centrate(
    config_id:      str,
    config_label:   str,
    nh4_n_kg_d:     float,
    tp_kg_d:        float,
    ds_total_tpd:   float,
    tn_mainstream_kg_d: float,
) -> CentrateCharacterisation:
    """
    Characterise the centrate stream from dewatering.

    Parameters
    ----------
    nh4_n_kg_d          : NH4-N return load from centrate, kg/day
    tp_kg_d             : Total P in centrate, kg/day
    ds_total_tpd        : Total DS feed to digesters, tDS/day
    tn_mainstream_kg_d  : Mainstream TN load for headroom calculation
    """
    vol_m3_d = ds_total_tpd * CENTRATE_L_PER_KG_DS   # m3/day
    nh4_n_mg_l = nh4_n_kg_d * 1000 / vol_m3_d if vol_m3_d > 0 else 0
    tp_mg_l    = tp_kg_d    * 1000 / vol_m3_d if vol_m3_d > 0 else 0
    return CentrateCharacterisation(
        config_id=config_id, config_label=config_label,
        nh4_n_kg_d=nh4_n_kg_d, tp_kg_d=tp_kg_d,
        volume_m3_d=vol_m3_d,
        nh4_n_mg_l=nh4_n_mg_l, tp_mg_l=tp_mg_l,
        tn_mainstream_kg_d=tn_mainstream_kg_d,
    )


def struvite_potential(
    centrate: CentrateCharacterisation,
    p_recovery: float = STRUVITE_P_RECOVERY,
    struvite_price: float = STRUVITE_PRICE_AUD_PER_T,
) -> StruviteResult:
    """
    Estimate struvite crystallisation potential.

    Stoichiometry: Mg2+ + NH4+ + PO43- + 6H2O → MgNH4PO4·6H2O
    Molar masses: P=30.97, N=14.01, struvite=245.41

    The limiting reagent is P (P is typically the limiting nutrient
    for struvite precipitation in digestion centrate).
    """
    p_avail = centrate.tp_kg_d          # kg P/day available in centrate
    p_rec   = p_avail * p_recovery       # kg P/day recovered

    # Moles of P recovered per day
    mol_p_d = p_rec * 1000 / MW_P        # mol/day (p_rec in kg = 1000g)

    # Struvite yield: 1 mol P → 1 mol struvite
    struvite_kg_d = mol_p_d * MW_STRUVITE / 1000   # kg/day

    # NH4-N co-precipitated: 1 mol N per mol P
    n_removed_kg_d = mol_p_d * MW_N / 1000          # kg N/day

    # Mg dosing: MgCl2 at 1.05:1 Mg:P molar ratio
    mol_mg_d = mol_p_d * STRUVITE_SUPERSATURATION_FACTOR
    mgcl2_kg_d = mol_mg_d * MW_MgCl2 / 1000

    # Economics
    mg_cost     = mgcl2_kg_d * 365 / 1000 * MGCL2_COST_AUD_PER_T  # AUD/yr
    revenue     = struvite_kg_d * 365 / 1000 * struvite_price        # AUD/yr
    net_value   = revenue - mg_cost

    return StruviteResult(
        config_id=centrate.config_id,
        p_available_kg_d=p_avail,
        struvite_kg_d=struvite_kg_d,
        struvite_t_yr=struvite_kg_d * 365 / 1000,
        p_recovered_kg_d=p_rec,
        n_removed_kg_d=n_removed_kg_d,
        mg_dose_kg_d=mgcl2_kg_d,
        mg_cost_aud_yr=mg_cost,
        revenue_aud_yr=revenue,
        net_value_aud_yr=net_value,
        p_recovery_pct=p_recovery * 100,
        n_recovery_pct=(n_removed_kg_d / centrate.nh4_n_kg_d * 100
                        if centrate.nh4_n_kg_d > 0 else 0),
    )


def ammonium_sulphate_recovery(
    centrate: CentrateCharacterisation,
    strip_eff: float = AS_NH3_STRIP_EFF,
    abs_eff:   float = AS_ABSORPTION_EFF,
    as_price:  float = AS_PRICE_AUD_PER_T,
) -> AmmoniumSulphateResult:
    """
    Estimate ammonium sulphate recovery via air stripping + acid absorption.

    Reaction: 2NH3 + H2SO4 → (NH4)2SO4
    Molar masses: N=14.01, AS=132.14, H2SO4=98.08

    Stripping efficiency depends on pH, temperature and HRT.
    Default assumes pH>10 (lime dosing), T~50°C, HRT~6h.
    """
    n_avail    = centrate.nh4_n_kg_d          # kg N/day
    n_stripped = n_avail * strip_eff           # kg N stripped as NH3
    n_absorbed = n_stripped * abs_eff          # kg N in AS product

    # AS yield: each mol N → 0.5 mol AS (2 NH3 per AS molecule)
    mol_n_d    = n_absorbed * 1000 / MW_N
    as_kg_d    = mol_n_d * 0.5 * MW_AS / 1000

    # H2SO4 requirement: 1 mol H2SO4 per 2 mol NH3 = 0.5 mol per mol N
    mol_h2so4_d = mol_n_d * 0.5
    h2so4_kg_d  = mol_h2so4_d * 98.08 / 1000

    # Ca(OH)2 for pH adjustment (raise to pH 10+): ~2 mol Ca(OH)2 per mol N (approx)
    caoh2_kg_d  = n_avail * 2 * 74.09 / MW_N / 1000 * 0.5  # 50% of theoretical

    # Economics
    h2so4_cost  = h2so4_kg_d * 365 / 1000 * H2SO4_COST_AUD_PER_T
    caoh2_cost  = caoh2_kg_d * 365 / 1000 * CAOH2_COST_AUD_PER_T
    reagent_cost = h2so4_cost + caoh2_cost
    revenue     = as_kg_d * 365 / 1000 * as_price
    net_value   = revenue - reagent_cost

    return AmmoniumSulphateResult(
        config_id=centrate.config_id,
        n_available_kg_d=n_avail,
        n_stripped_kg_d=n_stripped,
        as_kg_d=as_kg_d,
        as_t_yr=as_kg_d * 365 / 1000,
        n_recovered_kg_d=n_absorbed,
        h2so4_kg_d=h2so4_kg_d,
        caoh2_kg_d=caoh2_kg_d,
        reagent_cost_aud_yr=reagent_cost,
        revenue_aud_yr=revenue,
        net_value_aud_yr=net_value,
        n_recovery_pct=(n_absorbed / n_avail * 100 if n_avail > 0 else 0),
    )


def pna_applicability(
    centrate: CentrateCharacterisation,
    o2_cost_aud_per_kwh: float = 0.12,  # electricity price for O2
) -> PNAResult:
    """
    Assess PN/A (partial nitritation/anammox) applicability.

    PN/A requires high NH4-N concentrations (>400 mg/L typically) and
    removes ~88% of NH4-N to N2 with significant energy savings vs
    conventional nitrification/denitrification.

    Energy basis: conventional N removal ~6 kWh/kg N removed;
    PN/A ~2.4 kWh/kg N (60% saving per Lackner et al. 2014).
    """
    applicable  = centrate.nh4_n_mg_l >= PNA_MIN_NH4_MG_L
    n_removed   = centrate.nh4_n_kg_d * PNA_N_REMOVAL if applicable else 0.0

    # Energy saving vs conventional nitrification (6 kWh/kg N)
    conv_energy = centrate.nh4_n_kg_d * 6.0   # kWh/day conventional
    pna_energy  = centrate.nh4_n_kg_d * 2.4   # kWh/day PN/A
    energy_saved = (conv_energy - pna_energy) if applicable else 0.0

    if applicable:
        reason = (
            f"APPLICABLE — centrate NH4-N = {centrate.nh4_n_mg_l:.0f} mg/L "
            f"(threshold: {PNA_MIN_NH4_MG_L:.0f} mg/L). "
            f"Removes ~{PNA_N_REMOVAL*100:.0f}% of NH4-N to N2. "
            "Recommended as primary sidestream treatment before any "
            "struvite or AS recovery system."
        )
    else:
        reason = (
            f"NOT RECOMMENDED — centrate NH4-N = {centrate.nh4_n_mg_l:.0f} mg/L "
            f"(threshold: {PNA_MIN_NH4_MG_L:.0f} mg/L). "
            "Consider dilution reduction, thickening, or conventional "
            "nitrification/denitrification instead."
        )

    return PNAResult(
        config_id=centrate.config_id,
        applicable=applicable,
        nh4_n_in_kg_d=centrate.nh4_n_kg_d,
        n_removed_kg_d=n_removed,
        n_removal_pct=PNA_N_REMOVAL * 100 if applicable else 0.0,
        energy_saved_kwh_d=energy_saved,
        reason=reason,
    )


def nutrient_recovery_summary(
    config_id:          str,
    config_label:       str,
    nh4_n_kg_d:         float,
    tp_kg_d:            float,
    ds_total_tpd:       float,
    tn_mainstream_kg_d: float,
) -> NutrientRecoverySummary:
    """
    Run complete nutrient recovery analysis for one configuration.
    Returns a NutrientRecoverySummary with all three pathways.
    """
    centrate  = characterise_centrate(
        config_id, config_label,
        nh4_n_kg_d, tp_kg_d, ds_total_tpd, tn_mainstream_kg_d,
    )
    struvite  = struvite_potential(centrate)
    am_sulf   = ammonium_sulphate_recovery(centrate)
    pna       = pna_applicability(centrate)

    # Best-case combined: PN/A for N (if applicable), struvite for P
    # If PN/A not applicable, best N recovery is from AS
    if pna.applicable:
        best_n_kg_d = pna.n_removed_kg_d
    else:
        best_n_kg_d = am_sulf.n_recovered_kg_d

    # Revenue: struvite + AS (these can run in series after PN/A)
    best_revenue = struvite.net_value_aud_yr + am_sulf.net_value_aud_yr

    # TN headroom: return N as % of mainstream TN
    # Without recovery: all nh4_n returns to mainstream
    tn_base_pct = nh4_n_kg_d / tn_mainstream_kg_d * 100 if tn_mainstream_kg_d > 0 else 0
    # With best recovery: remaining N after treatment
    remaining_n = nh4_n_kg_d - best_n_kg_d - struvite.n_removed_kg_d
    remaining_n = max(0, remaining_n)
    tn_best_pct = remaining_n / tn_mainstream_kg_d * 100 if tn_mainstream_kg_d > 0 else 0

    return NutrientRecoverySummary(
        config_id=config_id,
        config_label=config_label,
        centrate=centrate,
        struvite=struvite,
        amm_sulphate=am_sulf,
        pna=pna,
        max_n_recovered_kg_d=best_n_kg_d + struvite.n_removed_kg_d,
        max_p_recovered_kg_d=struvite.p_recovered_kg_d,
        max_revenue_aud_yr=best_revenue,
        tn_headroom_base_pct=tn_base_pct,
        tn_headroom_best_pct=tn_best_pct,
    )


def run_recovery_comparison(
    configs: list[tuple[str, str, float, float]],  # (id, label, nh4_n_kg_d, tp_kg_d)
    ds_total_tpd:       float,
    tn_mainstream_kg_d: float,
) -> list[NutrientRecoverySummary]:
    """Run nutrient recovery analysis across multiple configurations."""
    return [
        nutrient_recovery_summary(cid, lbl, n, p, ds_total_tpd, tn_mainstream_kg_d)
        for cid, lbl, n, p in configs
    ]


# ── Self-test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # ETP-scale test: 220 tDS/d, 8,814 kg NH4-N/d (base), TN = 17,675 kg/d
    configs = [
        ("base",        "Conv. MAD",     8_814, 660),
        ("solidstream", "SolidStream",  10_332, 770),
        ("pre_thp",     "Pre-THP",      10_417, 780),
        ("separate",    "Separate",      8_814, 620),
        ("separate_thp","Sep+THP",       8_814, 620),
    ]
    results = run_recovery_comparison(configs, ds_total_tpd=220,
                                       tn_mainstream_kg_d=17_675)

    print("ETP NUTRIENT RECOVERY SCREENING — 220 tDS/d")
    print("="*72)
    print(f"\n{'Config':16} {'NH4-N':>8} {'TP':>7} {'Struvite':>10} "
          f"{'AS t/yr':>9} {'Max rev':>12} {'TN base':>8} {'TN best':>8}")
    print("-"*72)
    for r in results:
        print(f"  {r.config_label:14} "
              f"{r.centrate.nh4_n_kg_d:>8,.0f} "
              f"{r.centrate.tp_kg_d:>7,.0f} "
              f"{r.struvite.struvite_t_yr:>10,.0f} "
              f"{r.amm_sulphate.as_t_yr:>9,.0f} "
              f"${r.max_revenue_aud_yr/1e6:>10.2f}M "
              f"{r.tn_headroom_base_pct:>7.1f}% "
              f"{r.tn_headroom_best_pct:>7.1f}%")

    print()
    base = results[0]
    print(f"\nBase case detail:")
    print(f"  Centrate volume:   {base.centrate.volume_m3_d:,.0f} m3/day")
    print(f"  NH4-N conc:        {base.centrate.nh4_n_mg_l:,.0f} mg/L")
    print(f"  TP conc:           {base.centrate.tp_mg_l:,.0f} mg/L")
    print(f"  PN/A applicable:   {base.pna.applicable} ({base.centrate.nh4_n_mg_l:.0f} mg/L vs {PNA_MIN_NH4_MG_L:.0f} threshold)")
    print(f"  Struvite potential:{base.struvite.struvite_t_yr:,.0f} t/yr "
          f"(revenue: ${base.struvite.revenue_aud_yr/1e6:.2f}M/yr)")
    print(f"  AS potential:      {base.amm_sulphate.as_t_yr:,.0f} t/yr "
          f"(net value: ${base.amm_sulphate.net_value_aud_yr/1e6:.2f}M/yr)")
    print(f"  Max N recovered:   {base.max_n_recovered_kg_d:,.0f} kg/d "
          f"({base.max_n_recovered_kg_d/base.centrate.nh4_n_kg_d*100:.0f}% of centrate N)")
    print(f"  TN headroom base:  {base.tn_headroom_base_pct:.1f}% of mainstream TN")
    print(f"  TN headroom best:  {base.tn_headroom_best_pct:.1f}% after recovery")
