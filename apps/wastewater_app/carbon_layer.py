"""
apps/wastewater_app/carbon_layer.py

Carbon Layer — Production V1
==============================

Estimates greenhouse gas (GHG) emissions for a WaterPoint upgrade pathway
using a simplified but defensible IPCC-aligned wastewater emissions framework.

This layer:
  - calculates baseline plant emissions (Scope 1, 2, 3)
  - adjusts emissions for each technology stage in the recommended stack
  - compares baseline vs upgraded emissions
  - returns a CarbonReport with breakdown and insight statements

Does NOT modify any upstream layer output.

Emission framework
------------------
Scope 1 — Direct:
  N₂O from biological nitrification/denitrification (dominant):
    EF_N2O = 1.0% of influent TN load (IPCC 2019 default range 0.5–2.0%)
    N₂O-N → N₂O: × (44/28)
    N₂O GWP₁₀₀ = 273 (IPCC AR6)

  CH₄ from anaerobic zones (if applicable):
    EF_CH4 = 0.25 kg CH₄ per kg COD removed anaerobically
    CH₄ GWP₁₀₀ = 27.9 (IPCC AR6)

Scope 2 — Indirect (electricity):
  Technology-specific kWh/m³ benchmarks (see _ENERGY_INTENSITY)
  Grid emission factor: 0.8 kg CO₂e/kWh default (adjustable)

Scope 3 — Chemicals (simplified):
  Methanol:  1.37 kg CO₂e/kg
  Ferric:    2.0  kg CO₂e/kg (range 1.5–2.5)
  Alum:      1.8  kg CO₂e/kg
  Magnetite: qualitative only (low ongoing, flagged as note)

Technology emission adjustments (applied multiplicatively):
  See _TECH_ADJUSTMENTS — each has N₂O factor, energy factor, notes.

Main entry point
----------------
  calculate_carbon(pathway, plant_context) -> CarbonReport
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apps.wastewater_app.stack_generator import (
    UpgradePathway,
    TI_COMAG, TI_BIOMAG, TI_EQ_BASIN, TI_STORM_STORE,
    TI_INDENSE, TI_MIGINDENSE, TI_MEMDENSE,
    TI_HYBAS, TI_IFAS, TI_MBBR, TI_MABR,
    TI_BARDENPHO, TI_RECYCLE_OPT, TI_ZONE_RECONF,
    TI_DENFILTER, TI_TERT_P,
)

# ── IPCC constants ────────────────────────────────────────────────────────────
GWP_N2O    = 273.0    # IPCC AR6 GWP100
GWP_CH4    = 27.9     # IPCC AR6 GWP100
N2O_CONV   = 44 / 28  # N₂O-N → N₂O mass ratio
EF_N2O_DEFAULT  = 0.010   # 1.0% of influent TN load as N₂O-N (IPCC 2019 default)
EF_CH4_DEFAULT  = 0.25    # kg CH₄ / kg COD removed anaerobically

# ── Scope 3 chemical emission factors ────────────────────────────────────────
EF_METHANOL = 1.37    # kg CO₂e / kg MeOH (combustion + upstream)
EF_FERRIC   = 2.0     # kg CO₂e / kg FeCl₃ (production)
EF_ALUM     = 1.8     # kg CO₂e / kg Al₂(SO₄)₃ (production)

# Methanol dose: IPCC/WERF guidance for tertiary denitrification
MEOH_DOSE_KG_PER_KG_NO3 = 2.75  # kg MeOH / kg NO₃-N removed (mid of 2.5–3.0)

# Ferric dose for tertiary P removal
FERRIC_DOSE_KG_PER_KG_P = 22.5  # kg FeCl₃ / kg P removed (mid of 20–25)

# ── Baseline energy intensities (kWh/m³) ────────────────────────────────────
# Used for baseline calculation based on plant_type / technology_code
_BASELINE_ENERGY: Dict[str, float] = {
    "cas":  0.40,
    "bnr":  0.45,
    "sbr":  0.42,
    "mbr":  1.00,
    "nereda": 0.35,
    "mabr": 0.25,
    "default": 0.45,
}

# ── Technology-specific energy increments (kWh/m³, added to baseline) ────────
_ENERGY_INCREMENT: Dict[str, float] = {
    TI_COMAG:      +0.08,
    TI_BIOMAG:     +0.10,
    TI_EQ_BASIN:   +0.02,   # pumping for return
    TI_STORM_STORE:+0.02,
    TI_INDENSE:    +0.01,   # hydrocyclone — negligible
    TI_MIGINDENSE: +0.02,   # hydrocyclone + carriers
    TI_MEMDENSE:   -0.05,   # membrane aeration reduction
    TI_HYBAS:      +0.02,   # minor aeration adjustment
    TI_IFAS:       +0.02,
    TI_MBBR:       +0.02,
    TI_MABR:       -0.20,   # significant aeration saving
    TI_BARDENPHO:  0.00,
    TI_RECYCLE_OPT:+0.01,
    TI_ZONE_RECONF:0.00,
    TI_DENFILTER:  +0.05,   # backwash + blower
    TI_TERT_P:     +0.03,   # dosing pumps + filter
}

# ── N₂O emission factors per technology ──────────────────────────────────────
# Multiplied against the baseline N₂O emission to get the upgraded value.
# Factor < 1.0 = reduction; factor > 1.0 = increase
_N2O_FACTOR: Dict[str, float] = {
    TI_COMAG:      1.00,   # no biological effect
    TI_BIOMAG:     1.00,
    TI_EQ_BASIN:   1.00,
    TI_STORM_STORE:1.00,
    TI_INDENSE:    0.85,   # improved settling → better sludge age control → lower N₂O
    TI_MIGINDENSE: 0.70,   # 30% reduction: improved biological stability + SRT control
    TI_MEMDENSE:   0.90,   # PAO retention improves process stability
    TI_HYBAS:      0.85,   # 15% reduction: nitrification stability improvement
    TI_IFAS:       0.85,
    TI_MBBR:       0.85,
    TI_MABR:       0.75,   # 25% reduction: simultaneous nitrification-denitrification in biofilm
    TI_BARDENPHO:  0.85,   # 15% reduction: improved N control reduces transient N₂O spikes
    TI_RECYCLE_OPT:0.90,   # 10% reduction: better anoxic zone utilisation
    TI_ZONE_RECONF:0.90,
    TI_DENFILTER:  0.80,   # significant TN reduction lowers N₂O from downstream residuals
    TI_TERT_P:     1.00,   # no N pathway effect
}

# ── Technology-specific labels for carbon drivers ────────────────────────────
_CARBON_DRIVER: Dict[str, str] = {
    TI_COMAG:      "CoMag: slight energy increase from magnetite recovery system.",
    TI_BIOMAG:     "BioMag: energy increase from ballast and biological components.",
    TI_INDENSE:    "inDENSE: N₂O reduction from improved sludge density and process stability.",
    TI_MIGINDENSE: "MOB (inDENSE + miGRATE): N₂O reduction from improved biological stability and SRT control; small aeration energy saving.",
    TI_MEMDENSE:   "memDENSE: N₂O reduction from PAO retention; energy reduction from lower membrane fouling and reduced scouring demand.",
    TI_HYBAS:      "Hybas: N₂O reduction from nitrification stability; modest energy increment from carrier aeration.",
    TI_IFAS:       "IFAS: N₂O reduction from nitrification stability improvement via biofilm.",
    TI_MBBR:       "MBBR: N₂O reduction from nitrification stability; similar energy to conventional aeration.",
    TI_MABR:       "MABR: significant energy reduction (up to 50%) from membrane-aerated biofilm; N₂O reduction from improved N cycling.",
    TI_BARDENPHO:  "Bardenpho: N₂O reduction from improved denitrification control and reduced transient N₂O spikes.",
    TI_RECYCLE_OPT:"Recycle optimisation: marginal N₂O reduction from better anoxic zone utilisation.",
    TI_ZONE_RECONF:"Zone reconfiguration: marginal N₂O improvement from EBPR optimisation.",
    TI_DENFILTER:  "Denitrification filter: N₂O reduction from lower TN discharge; Scope 3 increase from methanol dosing.",
    TI_TERT_P:     "Tertiary P removal: Scope 3 increase from ferric/alum production; no direct N₂O effect.",
    TI_EQ_BASIN:   "EQ basin: minimal carbon impact; slight energy increase from return pumping.",
    TI_STORM_STORE:"Storm storage: minimal carbon impact; slight energy increase from return pumping.",
}


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class EmissionBreakdown:
    """GHG emissions split by source."""
    n2o_scope1_kgCO2e_d:   float   # N₂O Scope 1
    ch4_scope1_kgCO2e_d:   float   # CH₄ Scope 1 (if applicable)
    energy_scope2_kgCO2e_d:float   # Electricity Scope 2
    chem_scope3_kgCO2e_d:  float   # Chemicals Scope 3
    total_kgCO2e_d:        float   # sum of above
    total_kgCO2e_m3:       float   # per m³ treated
    energy_intensity_kWh_m3:float  # energy benchmark
    n2o_ef_applied:        float   # EF_N2O used (fraction)


@dataclass
class TechCarbonEffect:
    """Per-stage carbon adjustment applied."""
    technology:    str
    tech_display:  str
    n2o_factor:    float   # multiplier on baseline N₂O
    energy_delta_kWh_m3: float   # increment to energy intensity
    chem_kgCO2e_d: float   # chemical Scope 3 added by this stage
    driver_note:   str     # one-line explanation


@dataclass
class CarbonReport:
    """
    Full carbon assessment for an UpgradePathway.

    Produced by calculate_carbon() from an UpgradePathway.
    Does NOT modify the pathway.
    """
    # Plant context used
    flow_mld:          float
    influent_tn_mg_l:  float
    influent_cod_mg_l: float
    grid_factor:       float   # kg CO₂e / kWh

    # Baseline (before upgrade)
    baseline:          EmissionBreakdown

    # Per-stage effects
    tech_effects:      List[TechCarbonEffect]

    # Upgraded (after full stack)
    upgraded:          EmissionBreakdown

    # Delta
    delta_kgCO2e_d:    float   # upgraded − baseline (negative = reduction)
    delta_pct:         float   # % change from baseline
    delta_n2o_kgCO2e_d:    float
    delta_energy_kgCO2e_d: float
    delta_chem_kgCO2e_d:   float

    # Insight
    carbon_drivers:    List[str]   # key driver statements
    scope1_dominance:  float       # N₂O as % of baseline total
    insight_statements:List[str]   # IPCC insight sentences
    data_quality:      str         # "Indicative" / "Screening" / "Detailed"
    assumptions:       List[str]


# ── Step 1-2: Baseline emissions model ───────────────────────────────────────

def _baseline_emissions(
    flow_mld: float,
    influent_tn_mg_l: float,
    influent_cod_mg_l: float,
    plant_type: str,
    grid_factor: float,
    has_anaerobic: bool,
    ef_n2o: float,
) -> EmissionBreakdown:
    """Calculate baseline plant emissions before any upgrade."""
    flow_m3d = flow_mld * 1000.0

    # ── Scope 1: N₂O ──────────────────────────────────────────────────────────
    tn_load_kgd    = flow_m3d * influent_tn_mg_l / 1_000_000 * 1e6 / 1000
    # TN load (kg/d) = flow (m³/d) × TN (g/m³) / 1000
    tn_load_kgd    = flow_m3d * influent_tn_mg_l / 1000.0
    n2o_n_kgd      = tn_load_kgd * ef_n2o            # kg N₂O-N/d
    n2o_kgd        = n2o_n_kgd * N2O_CONV             # kg N₂O/d
    n2o_co2e       = n2o_kgd * GWP_N2O                # kg CO₂e/d

    # ── Scope 1: CH₄ ──────────────────────────────────────────────────────────
    if has_anaerobic and influent_cod_mg_l > 0:
        cod_load_kgd  = flow_m3d * influent_cod_mg_l / 1000.0
        ch4_kgd       = cod_load_kgd * 0.3 * EF_CH4_DEFAULT  # ~30% COD to anaerobic
        ch4_co2e      = ch4_kgd * GWP_CH4
    else:
        ch4_co2e = 0.0

    # ── Scope 2: Electricity ───────────────────────────────────────────────────
    energy_kwh_m3  = _BASELINE_ENERGY.get(plant_type.lower(), _BASELINE_ENERGY["default"])
    energy_kwh_d   = flow_m3d * energy_kwh_m3
    energy_co2e    = energy_kwh_d * grid_factor

    total          = n2o_co2e + ch4_co2e + energy_co2e
    total_per_m3   = total / flow_m3d if flow_m3d > 0 else 0.0

    return EmissionBreakdown(
        n2o_scope1_kgCO2e_d    = round(n2o_co2e, 1),
        ch4_scope1_kgCO2e_d    = round(ch4_co2e, 1),
        energy_scope2_kgCO2e_d = round(energy_co2e, 1),
        chem_scope3_kgCO2e_d   = 0.0,
        total_kgCO2e_d         = round(total, 1),
        total_kgCO2e_m3        = round(total_per_m3, 4),
        energy_intensity_kWh_m3= round(energy_kwh_m3, 3),
        n2o_ef_applied         = ef_n2o,
    )


# ── Step 3-4: Technology adjustments ─────────────────────────────────────────

def _apply_tech_adjustments(
    pathway: UpgradePathway,
    baseline: EmissionBreakdown,
    flow_mld: float,
    influent_tn_mg_l: float,
    grid_factor: float,
) -> tuple:
    """
    Apply per-stage emission adjustments.
    Returns (upgraded EmissionBreakdown, List[TechCarbonEffect], List[str] drivers).
    """
    flow_m3d   = flow_mld * 1000.0
    tech_codes = [s.technology for s in pathway.stages]

    # Accumulate adjustments multiplicatively for N₂O, additively for energy
    n2o_factor_cumulative   = 1.0
    energy_delta_cumulative = 0.0
    chem_scope3_cumulative  = 0.0

    effects: List[TechCarbonEffect] = []
    drivers: List[str]              = []

    for stage in pathway.stages:
        tech = stage.technology
        n2o_f    = _N2O_FACTOR.get(tech, 1.0)
        e_delta  = _ENERGY_INCREMENT.get(tech, 0.0)
        chem_add = 0.0
        driver   = _CARBON_DRIVER.get(tech, f"{tech}: no specific carbon adjustment.")

        # Chemical Scope 3 additions
        if tech == TI_DENFILTER:
            # Methanol dose: estimate from TN removed to effluent target
            # Use influent TN × 60% removal as NO₃-N treated (conservative)
            tn_load_kgd = flow_m3d * influent_tn_mg_l / 1000.0
            no3_treated = tn_load_kgd * 0.60
            meoh_kg_d   = no3_treated * MEOH_DOSE_KG_PER_KG_NO3
            chem_add    = meoh_kg_d * EF_METHANOL

        elif tech == TI_TERT_P:
            # Ferric dose: estimate from influent TP assumption (use influent TN/10 as TP proxy)
            tp_assumed_mg_l = max(1.0, influent_tn_mg_l / 10.0)
            tp_load_kgd     = flow_m3d * tp_assumed_mg_l / 1000.0
            tp_removed      = tp_load_kgd * 0.80   # 80% removal
            ferric_kg_d     = tp_removed * FERRIC_DOSE_KG_PER_KG_P
            chem_add        = ferric_kg_d * EF_FERRIC

        elif tech in (TI_COMAG, TI_BIOMAG):
            # Magnetite: qualitative note only — flag but not quantified
            driver += " (Magnetite supply chain carbon not quantified — typically low ongoing.)"

        # Accumulate
        n2o_factor_cumulative   *= n2o_f
        energy_delta_cumulative += e_delta
        chem_scope3_cumulative  += chem_add

        effects.append(TechCarbonEffect(
            technology    = tech,
            tech_display  = stage.tech_display,
            n2o_factor    = n2o_f,
            energy_delta_kWh_m3 = e_delta,
            chem_kgCO2e_d = round(chem_add, 1),
            driver_note   = driver,
        ))
        if chem_add > 0 or abs(e_delta) >= 0.03 or abs(n2o_f - 1.0) >= 0.05:
            drivers.append(driver)

    # ── Build upgraded breakdown ───────────────────────────────────────────────
    upg_n2o    = baseline.n2o_scope1_kgCO2e_d * n2o_factor_cumulative
    upg_ch4    = baseline.ch4_scope1_kgCO2e_d   # CH₄ unchanged (process adjustments are N₂O-focused)

    upg_energy_kwh_m3 = max(0.05, baseline.energy_intensity_kWh_m3 + energy_delta_cumulative)
    upg_energy_co2e   = flow_m3d * upg_energy_kwh_m3 * grid_factor

    upg_total  = upg_n2o + upg_ch4 + upg_energy_co2e + chem_scope3_cumulative
    upg_per_m3 = upg_total / flow_m3d if flow_m3d > 0 else 0.0

    upgraded = EmissionBreakdown(
        n2o_scope1_kgCO2e_d    = round(upg_n2o, 1),
        ch4_scope1_kgCO2e_d    = round(upg_ch4, 1),
        energy_scope2_kgCO2e_d = round(upg_energy_co2e, 1),
        chem_scope3_kgCO2e_d   = round(chem_scope3_cumulative, 1),
        total_kgCO2e_d         = round(upg_total, 1),
        total_kgCO2e_m3        = round(upg_per_m3, 4),
        energy_intensity_kWh_m3= round(upg_energy_kwh_m3, 3),
        n2o_ef_applied         = round(baseline.n2o_ef_applied * n2o_factor_cumulative, 5),
    )
    return upgraded, effects, drivers


# ── Step 7: Insight statements ────────────────────────────────────────────────

def _insight_statements(
    baseline: EmissionBreakdown,
    upgraded: EmissionBreakdown,
    scope1_dominance: float,
    tech_codes: set,
) -> List[str]:
    stmts = [
        f"N₂O emissions represent {scope1_dominance:.0f}% of the plant's baseline carbon footprint "
        f"— Scope 1 biological emissions dominate over electricity (Scope 2) for this plant configuration.",
    ]

    if scope1_dominance > 70:
        stmts.append(
            "Process stability improvements that reduce N₂O formation will deliver the greatest "
            "carbon benefit — energy efficiency is secondary to biological N₂O control at this plant."
        )
    elif scope1_dominance < 40:
        stmts.append(
            "Electricity (Scope 2) is a significant carbon driver at this plant. "
            "Energy-efficient technologies (MABR, memDENSE) should be prioritised alongside "
            "biological N₂O control measures."
        )

    if upgraded.total_kgCO2e_d < baseline.total_kgCO2e_d:
        reduction_pct = (baseline.total_kgCO2e_d - upgraded.total_kgCO2e_d) / baseline.total_kgCO2e_d * 100
        stmts.append(
            f"The recommended stack delivers a net carbon reduction of {reduction_pct:.1f}%, "
            f"primarily through N₂O reduction from improved process stability."
        )
    else:
        increase_pct = (upgraded.total_kgCO2e_d - baseline.total_kgCO2e_d) / baseline.total_kgCO2e_d * 100
        stmts.append(
            f"The recommended stack results in a net carbon increase of {increase_pct:.1f}% "
            f"due to chemical dosing (Scope 3) — this is typical where tertiary denitrification "
            f"or chemical P removal is required for licence compliance."
        )

    if TI_MABR in tech_codes:
        stmts.append(
            "MABR delivers significant Scope 2 savings — oxygen transfer efficiency up to 14 kgO₂/kWh "
            "reduces blower energy demand by 30–50% compared to conventional diffused aeration."
        )
    if TI_DENFILTER in tech_codes:
        stmts.append(
            "The Denitrification Filter reduces TN discharge (environmental benefit) but introduces "
            "Scope 3 methanol emissions — the net carbon impact depends on the methanol supply chain "
            "and whether green methanol is available."
        )
    if TI_MIGINDENSE in tech_codes or TI_INDENSE in tech_codes:
        stmts.append(
            "Biomass selection (inDENSE / MOB) reduces N₂O by improving sludge quality and "
            "biological process stability — this is a Scope 1 benefit with no significant energy penalty."
        )

    stmts.append(
        "All emission estimates are indicative (IPCC Tier 1 / Tier 2 defaults). "
        "Site-specific monitoring is required to verify actual N₂O emission factors, "
        "which can vary significantly with temperature, DO, and loading conditions."
    )
    return stmts


# ── Main entry point ──────────────────────────────────────────────────────────

def calculate_carbon(
    pathway: UpgradePathway,
    plant_context: Optional[Dict] = None,
) -> CarbonReport:
    """
    Calculate GHG emissions for a WaterPoint upgrade pathway.

    Parameters
    ----------
    pathway : UpgradePathway
        Output of build_upgrade_pathway() from stack_generator.py.

    plant_context : dict, optional
        Plant-specific inputs:
          flow_mld          float  (required — defaults to pathway.proximity_pct / 10)
          influent_tn_mg_l  float  (default 45 mg/L)
          influent_cod_mg_l float  (default 300 mg/L, used only if anaerobic zones)
          plant_type        str    "cas"/"bnr"/"sbr"/"mbr"/"nereda"/"mabr"
          has_anaerobic     bool   True if anaerobic digester or zones (for CH₄)
          grid_factor       float  kg CO₂e / kWh (default 0.8)
          ef_n2o            float  override EF_N2O (default 0.010)

    Returns
    -------
    CarbonReport
    """
    ctx = plant_context or {}

    # ── Inputs with defaults ───────────────────────────────────────────────────
    flow_mld         = float(ctx.get("flow_mld", max(1.0, pathway.proximity_pct / 10.0)))
    influent_tn      = float(ctx.get("influent_tn_mg_l", 45.0))
    influent_cod     = float(ctx.get("influent_cod_mg_l", 300.0))
    plant_type       = str(ctx.get("plant_type", pathway.plant_type or "bnr")).lower()
    has_anaerobic    = bool(ctx.get("has_anaerobic", False))
    grid_factor      = float(ctx.get("grid_factor", 0.8))
    ef_n2o           = float(ctx.get("ef_n2o", EF_N2O_DEFAULT))

    # ── Step 2: Baseline ───────────────────────────────────────────────────────
    baseline = _baseline_emissions(
        flow_mld, influent_tn, influent_cod, plant_type,
        grid_factor, has_anaerobic, ef_n2o,
    )

    # ── Steps 3-4: Technology adjustments ─────────────────────────────────────
    upgraded, tech_effects, carbon_drivers = _apply_tech_adjustments(
        pathway, baseline, flow_mld, influent_tn, grid_factor,
    )

    # ── Step 5: Delta ──────────────────────────────────────────────────────────
    delta_total  = upgraded.total_kgCO2e_d - baseline.total_kgCO2e_d
    delta_pct    = (delta_total / baseline.total_kgCO2e_d * 100.0) if baseline.total_kgCO2e_d > 0 else 0.0
    delta_n2o    = upgraded.n2o_scope1_kgCO2e_d - baseline.n2o_scope1_kgCO2e_d
    delta_energy = upgraded.energy_scope2_kgCO2e_d - baseline.energy_scope2_kgCO2e_d
    delta_chem   = upgraded.chem_scope3_kgCO2e_d - baseline.chem_scope3_kgCO2e_d

    # ── Scope 1 dominance ─────────────────────────────────────────────────────
    scope1_dominance = (
        (baseline.n2o_scope1_kgCO2e_d + baseline.ch4_scope1_kgCO2e_d)
        / baseline.total_kgCO2e_d * 100.0
        if baseline.total_kgCO2e_d > 0 else 0.0
    )

    # ── Step 7: Insight statements ─────────────────────────────────────────────
    tech_codes = {s.technology for s in pathway.stages}
    insights   = _insight_statements(baseline, upgraded, scope1_dominance, tech_codes)

    # ── Assumptions ───────────────────────────────────────────────────────────
    assumptions = [
        f"Influent TN = {influent_tn:.0f} mg/L (adjust via plant_context['influent_tn_mg_l']).",
        f"N₂O emission factor EF_N2O = {ef_n2o*100:.1f}% of influent TN (IPCC 2019 Tier 1 default).",
        f"Grid emission factor = {grid_factor:.2f} kg CO₂e/kWh — update for local grid mix.",
        f"Technology N₂O adjustments are indicative factors (±20–30% typical range).",
        "Methanol Scope 3 uses production + combustion factor 1.37 kg CO₂e/kg.",
        "CH₄ from anaerobic zones: " + ("included." if has_anaerobic else "excluded (no anaerobic zones specified)."),
        "All estimates are IPCC Tier 1 / Tier 2 screening-level. Site monitoring is required for verification.",
    ]

    return CarbonReport(
        flow_mld          = flow_mld,
        influent_tn_mg_l  = influent_tn,
        influent_cod_mg_l = influent_cod,
        grid_factor       = grid_factor,
        baseline          = baseline,
        tech_effects      = tech_effects,
        upgraded          = upgraded,
        delta_kgCO2e_d    = round(delta_total, 1),
        delta_pct         = round(delta_pct, 1),
        delta_n2o_kgCO2e_d    = round(delta_n2o, 1),
        delta_energy_kgCO2e_d = round(delta_energy, 1),
        delta_chem_kgCO2e_d   = round(delta_chem, 1),
        carbon_drivers    = carbon_drivers[:6],
        scope1_dominance  = round(scope1_dominance, 1),
        insight_statements= insights,
        data_quality      = "Indicative",
        assumptions       = assumptions,
    )
