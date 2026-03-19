"""
core/engineering/advanced_carbon.py

Advanced Carbon Model
======================
Provides explicit N₂O calculation with DO, SRT, and carbon-availability sensitivity,
plus scenario-level toggles.

The base platform uses:
  N₂O EF = 0.016 g N₂O-N / g N removed  (IPCC 2019 default)

This module refines it using:
  - DO setpoint (higher DO → higher N₂O in anoxic/aerobic transition zones)
  - SRT (longer SRT → lower N₂O, more complete denitrification)
  - Carbon availability (low C:N → incomplete denitrification → higher N₂O)
  - Technology type (MBR/MABR reduce N₂O via faster nitrification response)

Refs:
  IPCC (2019) 2019 Refinement to 2006 IPCC Guidelines, Vol 5 Ch 6
  Daelman et al. (2015) Methane and N₂O emissions from municipal WWTPs. WST 72(2).
  Kampschreur et al. (2009) Nitrous oxide emission during wastewater treatment. WR 43(17).
  Water Research Australia Project 4004 — N₂O emission factors for Australian WWTPs
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ── Base emission factors ────────────────────────────────────────────────────
N2O_EF_BASE     = 0.016   # g N₂O-N / g N removed (IPCC 2019 default)
N2O_EF_LOW      = 0.006   # optimised operation (long SRT, good DO control)
N2O_EF_HIGH     = 0.035   # poor DO/carbon control (US EPA high-end)
N2O_GWP         = 273     # AR6 100-yr GWP (matches platform default)
# Note: EF is g N₂O / g N removed (not g N₂O-N), so NO MW ratio needed

CH4_EF_BASE     = 0.0025  # g CH₄ / g BOD influent (IPCC default)
CH4_GWP         = 28      # AR4 100-yr GWP

# ── Technology N₂O adjustment factors ────────────────────────────────────────
# Multiplier on base EF. 1.0 = no change.
_TECH_N2O_FACTORS: Dict[str, float] = {
    "bnr":             1.00,   # conventional BNR — typical
    "granular_sludge": 0.75,   # AGS: feast-famine cycle reduces N₂O (Volcke et al. 2012)
    "mabr_bnr":        0.70,   # MABR: membrane-aerated biofilm has lower N₂O (aerobic shell)
    "bnr_mbr":         0.85,   # MBR: higher MLSS, more stable nitrification
    "ifas_mbbr":       0.90,   # IFAS: similar to BNR, slightly lower
    "anmbr":           0.60,   # anaerobic: very low N₂O, some CH₄ credit
    "sidestream_pna":  1.30,   # PNA/anammox: higher N₂O (pathway specific)
    "mob":             0.90,
}


@dataclass
class N2OSensitivity:
    """N₂O EF sensitivity to a single parameter."""
    parameter:    str
    low_value:    float
    high_value:   float
    low_ef:       float
    high_ef:      float
    unit:         str
    note:         str


@dataclass
class AdvancedCarbonResult:
    scenario_name:      str
    tech_code:          str
    # N₂O
    n2o_ef_base:        float           # g N₂O-N / g N removed (IPCC default)
    n2o_ef_adjusted:    float           # adjusted for conditions
    n2o_tco2e_yr:       float           # total N₂O as CO₂e
    n2o_tco2e_yr_low:   float           # low-end (optimised operations)
    n2o_tco2e_yr_high:  float           # high-end (poor DO control)
    # CH₄
    ch4_tco2e_yr:       float
    # Total Scope 1
    scope1_tco2e_yr:    float
    scope1_base_tco2e_yr: float         # from platform model (for comparison)
    scope1_delta_pct:   float           # % difference from base model
    # Sensitivity
    sensitivities:      List[N2OSensitivity] = field(default_factory=list)
    # Narrative
    narrative:          str = ""
    do_sensitivity_note:  str = ""
    srt_sensitivity_note: str = ""

    def build_narrative(self) -> None:
        delta = self.scope1_delta_pct
        adj   = self.n2o_ef_adjusted
        base  = self.n2o_ef_base
        adj_dir = "lower" if adj < base else "higher"
        parts = [
            f"N₂O emission factor adjusted to {adj:.4f} g N₂O-N/g N removed "
            f"({adj_dir} than IPCC default {base:.4f}), "
            f"resulting in {abs(delta):.1f}% {'lower' if delta < 0 else 'higher'} Scope 1 emissions. "
        ]
        if self.sensitivities:
            # Find largest sensitivity driver
            s = max(self.sensitivities, key=lambda x: abs(x.high_ef - x.low_ef))
            range_n2o = (s.high_ef - s.low_ef) / base * 100
            parts.append(
                f"Most sensitive to {s.parameter.lower()} "
                f"(EF range {s.low_ef:.4f}–{s.high_ef:.4f}, "
                f"±{range_n2o:.0f}% relative to default)."
            )
        if self.do_sensitivity_note:
            parts.append(self.do_sensitivity_note)
        self.narrative = " ".join(parts)


def calculate_advanced_n2o(
    scenario_name:      str,
    tech_code:          str,
    design_flow_mld:    float,
    eff_tn_mg_l:        float,
    inf_tn_mg_l:        float,
    inf_bod_mg_l:       float,
    do_setpoint_mg_l:   float  = 2.0,
    srt_days:           float  = 10.0,
    temperature_c:      float  = 20.0,
    base_n2o_tco2e_yr:  float  = 0.0,   # from platform model
    base_ch4_tco2e_yr:  float  = 0.0,
    base_scope1_tco2e_yr: float = 0.0,
) -> AdvancedCarbonResult:
    """
    Calculate advanced N₂O emissions for one scenario.
    """
    # ── TN removed ──────────────────────────────────────────────────────
    tn_removed_kg_day = (inf_tn_mg_l - eff_tn_mg_l) * design_flow_mld   # kg/day
    tn_removed_kg_yr  = tn_removed_kg_day * 365

    # ── Base EF × technology factor ────────────────────────────────────
    tech_factor = _TECH_N2O_FACTORS.get(tech_code, 1.0)
    n2o_ef_adj  = N2O_EF_BASE * tech_factor

    # ── DO adjustment ──────────────────────────────────────────────────
    # Higher DO → more aerobic N₂O production at nitrification/denitrification interface
    # Daelman et al. (2015): EF increases ~0.003 per mg/L DO above 1.5 mg/L
    do_adj = (do_setpoint_mg_l - 1.5) * 0.003
    do_adj = max(-0.004, min(0.008, do_adj))   # clamp

    # ── SRT adjustment ─────────────────────────────────────────────────
    # Longer SRT → more complete nitrification, less intermediate N₂O
    # Below SRT = 10d: EF increases; above 15d: EF decreases slightly
    srt_adj = 0.0
    if srt_days < 10:
        srt_adj = (10 - srt_days) * 0.001    # +0.001 per day below 10d
    elif srt_days > 15:
        srt_adj = -(srt_days - 15) * 0.0005  # -0.0005 per day above 15d
    srt_adj = max(-0.004, min(0.006, srt_adj))

    # ── Carbon availability adjustment ─────────────────────────────────
    # Low BOD/TKN → incomplete denitrification → higher N₂O
    cod_tkn = max(1.0, inf_bod_mg_l * 2.0 / max(1.0, inf_tn_mg_l))
    if cod_tkn < 4.5:
        carbon_adj = 0.008   # very limited carbon
    elif cod_tkn < 8.0:
        carbon_adj = 0.003
    else:
        carbon_adj = 0.0     # adequate carbon
    carbon_adj = min(0.008, carbon_adj)

    # ── Temperature adjustment ─────────────────────────────────────────
    # Cold temperatures slow denitrification, increase incomplete reduction
    temp_adj = 0.0
    if temperature_c < 12:
        temp_adj = 0.004
    elif temperature_c < 16:
        temp_adj = 0.002

    # ── Combined EF ────────────────────────────────────────────────────
    n2o_ef_final = max(N2O_EF_LOW * 0.5,
                       n2o_ef_adj + do_adj + srt_adj + carbon_adj + temp_adj)

    # ── N₂O as CO₂e ────────────────────────────────────────────────────
    # N₂O-N → N₂O mass: multiply by N2O_MW_RATIO
    n2o_kg_yr       = tn_removed_kg_yr * n2o_ef_final   # EF is g N2O / g N (direct, no MW ratio)
    n2o_tco2e_yr    = n2o_kg_yr * N2O_GWP / 1000

    # Low / high bounds
    n2o_ef_low  = max(N2O_EF_LOW,  n2o_ef_adj * 0.5)
    n2o_ef_high = min(N2O_EF_HIGH, n2o_ef_adj * 1.8)
    n2o_tco2e_low  = tn_removed_kg_yr * n2o_ef_low  * N2O_GWP / 1000
    n2o_tco2e_high = tn_removed_kg_yr * n2o_ef_high * N2O_GWP / 1000

    # ── CH₄ ────────────────────────────────────────────────────────────
    # Use base model value if provided; otherwise estimate
    inf_bod_kg_yr = inf_bod_mg_l * design_flow_mld * 365   # kg/yr
    ch4_kg_yr     = inf_bod_kg_yr * CH4_EF_BASE
    ch4_tco2e_yr  = ch4_kg_yr * CH4_GWP / 1000
    # Use base model value if it was calculated already
    if base_ch4_tco2e_yr > 0:
        ch4_tco2e_yr = base_ch4_tco2e_yr

    scope1_tco2e_yr = round(n2o_tco2e_yr + ch4_tco2e_yr, 1)
    scope1_base     = base_scope1_tco2e_yr if base_scope1_tco2e_yr > 0 else scope1_tco2e_yr
    delta_pct       = (scope1_tco2e_yr - scope1_base) / max(1.0, scope1_base) * 100

    # ── Sensitivity analysis ────────────────────────────────────────────
    sensitivities = []

    # DO sensitivity
    do_low_ef  = n2o_ef_adj + (1.0 - 1.5) * 0.003 + srt_adj + carbon_adj + temp_adj
    do_high_ef = n2o_ef_adj + (3.0 - 1.5) * 0.003 + srt_adj + carbon_adj + temp_adj
    do_low_ef  = max(N2O_EF_LOW * 0.5, do_low_ef)
    do_high_ef = min(N2O_EF_HIGH, do_high_ef)
    sensitivities.append(N2OSensitivity(
        parameter  = "DO setpoint",
        low_value  = 1.0, high_value = 3.0,
        low_ef     = round(do_low_ef, 5),
        high_ef    = round(do_high_ef, 5),
        unit       = "mg/L",
        note       = (f"Reducing DO from {do_setpoint_mg_l:.1f} to 1.0 mg/L could reduce "
                      f"N₂O EF from {n2o_ef_final:.4f} to {do_low_ef:.4f}.")
    ))

    # SRT sensitivity
    srt_low_ef  = n2o_ef_adj + do_adj + (10 - 8)  * 0.001 + carbon_adj + temp_adj
    srt_high_ef = n2o_ef_adj + do_adj - (20 - 15) * 0.0005 + carbon_adj + temp_adj
    srt_low_ef  = max(N2O_EF_LOW * 0.5, srt_low_ef)
    srt_high_ef = max(N2O_EF_LOW * 0.5, srt_high_ef)
    sensitivities.append(N2OSensitivity(
        parameter  = "SRT",
        low_value  = 8.0, high_value = 20.0,
        low_ef     = round(max(srt_low_ef, srt_high_ef), 5),
        high_ef    = round(min(srt_low_ef, srt_high_ef), 5),
        unit       = "days",
        note       = (f"Extending SRT from {srt_days:.0f}d to 20d could reduce N₂O EF "
                      f"from {n2o_ef_final:.4f} to {srt_high_ef:.4f}.")
    ))

    # DO note
    do_note = ""
    if do_setpoint_mg_l > 2.5:
        do_note = (f"DO setpoint of {do_setpoint_mg_l:.1f} mg/L is above 2.5 mg/L — "
                   "consider lowering DO in anoxic transition zones to reduce N₂O formation.")

    result = AdvancedCarbonResult(
        scenario_name        = scenario_name,
        tech_code            = tech_code,
        n2o_ef_base          = round(N2O_EF_BASE, 5),
        n2o_ef_adjusted      = round(n2o_ef_final, 5),
        n2o_tco2e_yr         = round(n2o_tco2e_yr, 1),
        n2o_tco2e_yr_low     = round(n2o_tco2e_low, 1),
        n2o_tco2e_yr_high    = round(n2o_tco2e_high, 1),
        ch4_tco2e_yr         = round(ch4_tco2e_yr, 1),
        scope1_tco2e_yr      = scope1_tco2e_yr,
        scope1_base_tco2e_yr = round(scope1_base, 1),
        scope1_delta_pct     = round(delta_pct, 1),
        sensitivities        = sensitivities,
        do_sensitivity_note  = do_note,
    )
    result.build_narrative()
    return result


def run_all_advanced_carbon(
    scenarios: List[Any],
) -> Dict[str, AdvancedCarbonResult]:
    """Run advanced carbon model for all scenarios."""
    results = {}
    for s in scenarios:
        tc   = (s.treatment_pathway.technology_sequence[0]
                if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
        dinp = getattr(s, "domain_inputs", None) or {}
        dso  = getattr(s, "domain_specific_outputs", None) or {}
        agg  = dso.get("aggregated", {}) or {}
        tp   = (dso.get("technology_performance", {}) or {}).get(tc, {})

        # Get base model values
        base_n2o  = agg.get("total_n2o_tco2e_yr") or tp.get("scope1_tco2e_yr", 0.0)
        base_ch4  = agg.get("total_ch4_tco2e_yr") or 0.0
        base_s1   = tp.get("scope1_tco2e_yr") or 0.0

        # Get SRT
        srt = (tp.get("granular_sludge_srt_days")
               or tp.get("srt_days")
               or dinp.get("granular_sludge_srt_days", 10.0))

        results[s.scenario_name] = calculate_advanced_n2o(
            scenario_name        = s.scenario_name,
            tech_code            = tc,
            design_flow_mld      = dinp.get("design_flow_mld", 10.0),
            eff_tn_mg_l          = dinp.get("effluent_tn_mg_l", 10.0),
            inf_tn_mg_l          = 45.0,   # standard influent
            inf_bod_mg_l         = 250.0,
            do_setpoint_mg_l     = tp.get("do_setpoint_mg_l") or dinp.get("do_setpoint_mg_l", 2.0),
            srt_days             = srt or 10.0,
            temperature_c        = tp.get("influent_temperature_celsius", 20.0),
            base_n2o_tco2e_yr    = base_n2o or 0.0,
            base_ch4_tco2e_yr    = base_ch4 or 0.0,
            base_scope1_tco2e_yr = base_s1  or 0.0,
        )
    return results
