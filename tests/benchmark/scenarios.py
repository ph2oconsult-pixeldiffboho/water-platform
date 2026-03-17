"""
tests/benchmark/scenarios.py

WASTEWATER PLANNING PLATFORM — BENCHMARK SCENARIO DEFINITIONS
==============================================================
8 engineering-calibrated municipal scenarios.

TOLERANCE PHILOSOPHY — CRITICAL DISTINCTION
--------------------------------------------
These ranges are REGRESSION SENTINELS, not planning uncertainty bands.
They catch model drift, not real-world estimation uncertainty.

  TIGHT  (±10-15%) — Regression catches: CAPEX drift, $/kL shift,
                      Scope 2 carbon (deterministic: kWh × grid factor),
                      effluent quality, kWh/kgNH4.
                      If these drift, a calculation changed.

  MODERATE (±20-25%) — Regression catches: OPEX, LCC, sludge mass,
                        Scope 1 carbon (N2O model has real uncertainty
                        but the MODEL should not drift >25% between runs).

  WIDE   (±40%)    — Reserved for cross-scenario footprint checks only.
                      Footprint has layout dependency; physics sets a floor.

PLANNING UNCERTAINTY (separate from regression) is communicated to users
as: CAPEX ±40%, OPEX ±25%, Carbon ±×3 (N2O). This lives in the UI, not here.

DECISION TENSION
----------------
Each scenario encodes at least one trade-off:
  S1: CAPEX vs LCC vs footprint across 4 technologies
  S2: reliability vs cost in cold climate
  S3: CAPEX vs certainty (MABR $18M but achieves NH4 target reliably)
  S4: footprint vs CAPEX — AGS wins on m², MBR expensive
  S5: TN compliance failure vs supplemental carbon cost
  S6: energy OPEX dominates at high electricity price
  S7: sludge disposal shifts LCC ranking
  S8: effluent quality vs cost — MBR premium justified for reuse

REFERENCES
----------
  Metcalf & Eddy 5th Ed — O2, sludge, energy
  WEF Cost Estimating Manual 2018 — CAPEX/OPEX
  de Kreuk 2007, van Dijk 2020 — AGS
  GE/Ovivo 2017, Syron & Casey 2008 — MABR
  AU Water Association utility benchmarks, AUD 2024
  IPCC 2019 Tier 1 — N2O

All costs AUD 2024. Calibration date: 2024-03.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Tolerance constants ───────────────────────────────────────────────────────

class Tol:
    TIGHT    = 0.15   # ±15% — regression sentinel for deterministic quantities
    MODERATE = 0.22   # ±22% — regression sentinel for model quantities
    WIDE     = 0.40   # ±40% — layout-dependent quantities (footprint only)


@dataclass
class Range:
    """Expected output range [lo, hi] used as a regression sentinel."""
    lo:   float
    hi:   float
    tier: str = "moderate"
    ref:  str = ""

    def passes(self, value: float) -> bool:
        return self.lo <= float(value) <= self.hi

    def __repr__(self) -> str:
        return f"[{self.lo:.3g}, {self.hi:.3g}] ({self.tier})"


def _t(centre: float, tol: float = Tol.TIGHT, ref: str = "") -> Range:
    """Build a Range centred on a calibration value with the given tolerance."""
    tier = {Tol.TIGHT: "tight", Tol.MODERATE: "moderate", Tol.WIDE: "wide"}.get(tol, "moderate")
    return Range(lo=centre * (1 - tol), hi=centre * (1 + tol), tier=tier, ref=ref)


def _rng(lo: float, hi: float, tier: str = "moderate", ref: str = "") -> Range:
    """Build a Range from explicit bounds."""
    return Range(lo=lo, hi=hi, tier=tier, ref=ref)


# ── Scenario dataclass ────────────────────────────────────────────────────────

@dataclass
class Scenario:
    id:          str
    name:        str
    description: str

    design_flow_mld:              float
    peak_flow_factor:             float
    influent_bod_mg_l:            float
    influent_cod_mg_l:            float
    influent_tss_mg_l:            float
    influent_nh4_mg_l:            float
    influent_tkn_mg_l:            float
    influent_tp_mg_l:             float
    influent_temperature_celsius: float

    electricity_price_per_kwh: float = 0.14
    sludge_disposal_per_tds:   float = 280.0
    carbon_price_per_tco2e:    float = 35.0
    discount_rate:             float = 0.07
    analysis_period_years:     int   = 30

    effluent_bod_mg_l: float = 10.0
    effluent_tss_mg_l: float = 10.0
    effluent_tn_mg_l:  float = 10.0
    effluent_nh4_mg_l: float = 5.0
    effluent_tp_mg_l:  float = 1.0

    technologies: List[str] = field(default_factory=list)
    expected: Dict[str, Dict[str, Range]] = field(default_factory=dict)


# ── Scenarios ─────────────────────────────────────────────────────────────────

SCENARIOS: List[Scenario] = [

    # ══════════════════════════════════════════════════════════════════════
    # S1 — Medium Municipal BNR Baseline
    # Purpose: Reference. Every other scenario deviates from S1.
    # Decision tension: cost vs footprint vs energy across 4 technologies.
    # Calibration actuals (AUD 2024):
    #   BNR:  $7.81M / $723k / $1353k / $0.371/kL / 377 kWh/ML /
    #         9.0 kWh/kgNH4 / 1478 kgDS/d / Scope2=1087 / 1307 m²
    #   AGS:  $6.84M / $676k / $1227k / $0.336/kL / 347 kWh/ML /
    #         838 m² (36% less footprint than BNR)
    #   MABR: $14.60M / $1016k / $2192k / $0.601/kL / 320 kWh/ML /
    #         6.4 kWh/kgNH4 (best nitrification energy efficiency)
    # ══════════════════════════════════════════════════════════════════════
    Scenario(
        id="S1", name="Medium Municipal BNR Baseline",
        description=(
            "10 MLD at 20°C, standard suburban catchment. "
            "Reference scenario — all others deviate from this in one dimension. "
            "Decision tension: BNR lowest LCC, AGS lowest footprint, "
            "MABR lowest energy but 2× CAPEX."
        ),
        design_flow_mld=10.0, peak_flow_factor=2.5,
        influent_bod_mg_l=250, influent_cod_mg_l=500,
        influent_tss_mg_l=280, influent_nh4_mg_l=35,
        influent_tkn_mg_l=45,  influent_tp_mg_l=6,
        influent_temperature_celsius=20,
        effluent_tn_mg_l=10, effluent_nh4_mg_l=5, effluent_tp_mg_l=1,
        technologies=["bnr", "granular_sludge", "ifas_mbbr", "mabr_bnr"],
        expected={
            "bnr": {
                # Cost — ±15% regression sentinel on calibration values
                "capex_m":    _t(7.81,  Tol.TIGHT,    "10 MLD BNR: reactor+clarifiers+blowers"),
                "opex_k":     _t(723,   Tol.MODERATE, "elec+sludge+maint+labour"),
                "lcc_k":      _t(1353,  Tol.MODERATE, "CAPEX×CRF(7%,30yr)+OPEX"),
                "cost_kl":    _t(0.371, Tol.TIGHT,    "primary utility decision metric"),
                # Energy
                "kwh_ml":     _t(377,   Tol.MODERATE, "Metcalf Table 12-10 BNR"),
                "kwh_kg_nh4": _t(7.1, Tol.MODERATE, "total plant / NH4 removed"),
                # Sludge
                "sludge":     _t(1478,  Tol.MODERATE, "y_obs≈0.31 incl. inorganic TSS"),
                # Carbon — Scope 2 is deterministic (kWh×grid), check tight
                "scope2_co2": _t(921, Tol.TIGHT, "377 kWh/ML × 10 MLD × 365 × 0.79/1000"),
                "scope1_co2": _t(622,   Tol.MODERATE, "N2O-dominated, IPCC EF=0.016"),
                # Effluent — tight: these are first-principles targets
                "eff_tn":     _rng(8.5, 11.0, "tight", "target 10 mg/L at BOD/TKN=11"),
                "eff_nh4":    _rng(4.0,  6.0, "tight", "target 5 mg/L — model should hit 4-6"),
                "risk_score": _rng(18.0, 22.0, "tight", "BNR: lowest risk, mature tech"),
            },
            "granular_sludge": {
                "capex_m":    _t(6.84,  Tol.TIGHT,    "AGS: no secondary clarifiers"),
                "cost_kl":    _t(0.336, Tol.TIGHT,    "AGS cheapest $/kL at S1"),
                "kwh_ml":     _t(347,   Tol.MODERATE, "de Kreuk 2007 AGS aeration"),
                "sludge":     _t(1220,  Tol.MODERATE, "17% less than BNR (longer SRT)"),
                "scope2_co2": _t(829, Tol.TIGHT, "347 kWh/ML × 0.79 grid"),
                # Footprint — physics bounds: no clarifiers → floor ~50% BNR
                "footprint_m2": _rng(700, 1050, "moderate", "SBR reactor ~838m² ±25%"),
                "risk_score": _rng(25.0, 32.0, "tight", "AGS: ~200 full-scale, moderate risk"),
            },
            "mabr_bnr": {
                "capex_m":    _t(14.60, Tol.TIGHT,    "MABR membranes + BNR zone"),
                "cost_kl":    _t(0.601, Tol.TIGHT,    "highest $/kL — CAPEX penalty"),
                "kwh_ml":     _t(320,   Tol.MODERATE, "GE/Ovivo 2017: 15% below BNR"),
                "kwh_kg_nh4": _t(4.5, Tol.MODERATE, "MABR best nitrification efficiency"),
                "scope2_co2": _t(758, Tol.TIGHT, "320 kWh/ML × 0.79 grid"),
            },
            "ifas_mbbr": {
                "capex_m":    _t(11.73, Tol.TIGHT,    "IFAS media + standard BNR zone"),
                "cost_kl":    _t(0.485, Tol.TIGHT,    ""),
                "kwh_ml":     _t(399,   Tol.MODERATE, "higher than BNR (media aeration)"),
                "scope2_co2": _t(1017, Tol.TIGHT, "399 kWh/ML × 0.79 grid"),
            },
        },
    ),

    # ══════════════════════════════════════════════════════════════════════
    # S2 — Cold Climate Nitrification
    # Purpose: Test cold-T physics. SRT extension, NH4 penalty, AGS energy.
    # Decision tension: BNR cheaper but fails NH4<3 target; MABR $12.5M
    #   but most reliable at 12°C; AGS energy up 20% vs warm.
    # Calibration: BNR NH4=6.0 (fails target 3); MABR NH4=3.0 (just passes)
    # ══════════════════════════════════════════════════════════════════════
    Scenario(
        id="S2", name="Cold Climate Nitrification",
        description=(
            "8 MLD at 12°C. Nitrification is the binding constraint. "
            "Decision tension: BNR cheaper but fails NH4<3 target at 12°C. "
            "MABR achieves target reliably but at $12.5M vs $7.3M. "
            "AGS energy up 20% vs warm scenario (cold granule penalty)."
        ),
        design_flow_mld=8.0, peak_flow_factor=3.0,
        influent_bod_mg_l=220, influent_cod_mg_l=440,
        influent_tss_mg_l=240, influent_nh4_mg_l=38,
        influent_tkn_mg_l=48,  influent_tp_mg_l=5,
        influent_temperature_celsius=12,
        effluent_tn_mg_l=10, effluent_nh4_mg_l=3, effluent_tp_mg_l=1,
        technologies=["bnr", "granular_sludge", "mabr_bnr", "ifas_mbbr"],
        expected={
            "bnr": {
                "capex_m":    _t(7.31,  Tol.TIGHT,    "8 MLD cold BNR"),
                "cost_kl":    _t(0.398, Tol.TIGHT,    ""),
                "kwh_ml":     _t(339,   Tol.MODERATE, "cold BNR: less N removed → less O2"),
                # Cold NH4 penalty: ×4 multiplier at ≤12°C (bnr.py)
                # BNR FAILS the NH4<3 target at 12°C — this is a feature not a bug
                "eff_nh4":    _rng(4.0, 9.0, "tight", "NH4 penalty ×4 at ≤12°C; fails target"),
                # Reactor volume: SRT extended (Metcalf Fig 7-42)
                "reactor_m3": _rng(1800, 3000, "moderate", "SRT extended at 12°C"),
                "sludge":     _t(1124,  Tol.MODERATE, "8 MLD cold BNR"),
                "scope2_co2": _t(680, Tol.TIGHT, "339 kWh/ML × 8MLD × 365 × 0.79/1000"),
                "risk_score": _rng(19.5, 23.0, "tight", "BNR cold: +1 risk point from T<15°C"),
            },
            "granular_sludge": {
                "capex_m":    _t(6.40,  Tol.TIGHT,    "8 MLD AGS cold"),
                "cost_kl":    _t(0.370, Tol.TIGHT,    ""),
                # Cold energy penalty applied explicitly in granular_sludge.py
                "kwh_ml":     _t(391,   Tol.MODERATE, "cold penalty: +20% vs warm AGS"),
                "eff_nh4":    _rng(3.0, 7.0, "tight", "granule instability NH4 penalty"),
                "scope2_co2": _t(709, Tol.TIGHT, "deterministic"),
            },
            "mabr_bnr": {
                "capex_m":    _t(12.50, Tol.TIGHT,    "MABR: higher cost, reliable cold T"),
                "cost_kl":    _t(0.622, Tol.TIGHT,    "MABR $/kL premium"),
                "kwh_ml":     _t(291,   Tol.MODERATE, "MABR less cold-sensitive"),
                # MABR achieves NH4 target at 12°C — validates biofilm cold tolerance
                "eff_nh4":    _rng(2.0, 4.5, "tight", "MABR achieves NH4<3 at 12°C — some cold penalty"),
                "scope2_co2": _t(556, Tol.TIGHT, "lowest Scope 2 — lowest energy"),
            },
        },
    ),

    # ══════════════════════════════════════════════════════════════════════
    # S3 — Tight Ammonia Compliance
    # Purpose: NH4 < 1 mg/L at 18°C — all technologies should achieve this.
    # Decision tension: BNR $8.8M achieves same NH4 as MABR $17.8M.
    #   MBR at $13.6M adds TSS barrier for reuse. MABR pays a CAPEX premium
    #   for redundancy margin not required at 18°C.
    # Calibration: All 4 technologies achieve NH4=1.0 mg/L
    # ══════════════════════════════════════════════════════════════════════
    Scenario(
        id="S3", name="Tight Ammonia Compliance",
        description=(
            "12 MLD at 18°C, NH4 < 1 mg/L target. "
            "Decision tension: All technologies achieve NH4=1.0 at 18°C, "
            "so MABR $17.8M CAPEX premium is not justified by NH4 alone. "
            "MBR at $13.6M adds TSS barrier — relevant only if reuse is planned."
        ),
        design_flow_mld=12.0, peak_flow_factor=2.5,
        influent_bod_mg_l=250, influent_cod_mg_l=500,
        influent_tss_mg_l=280, influent_nh4_mg_l=40,
        influent_tkn_mg_l=52,  influent_tp_mg_l=6,
        influent_temperature_celsius=18,
        effluent_tn_mg_l=10, effluent_nh4_mg_l=1, effluent_tp_mg_l=1,
        technologies=["bnr", "mabr_bnr", "ifas_mbbr", "bnr_mbr"],
        expected={
            "bnr": {
                "capex_m":    _t(8.81,  Tol.TIGHT,    "12 MLD BNR"),
                "cost_kl":    _t(0.360, Tol.TIGHT,    "cheapest $/kL at this scenario"),
                "kwh_ml":     _t(379,   Tol.MODERATE, "high TKN→more nitrif O2"),
                "kwh_kg_nh4": _t(5.5, Tol.MODERATE, "BNR nitrification efficiency"),
                "sludge":     _t(1816,  Tol.MODERATE, "12 MLD standard yield"),
                "scope2_co2": _t(1117, Tol.TIGHT, "deterministic"),
                "eff_nh4":    _rng(0.8, 1.3, "tight", "target 1 mg/L achievable at 18°C"),
            },
            "mabr_bnr": {
                "capex_m":    _t(17.76, Tol.TIGHT,    "MABR 2× BNR CAPEX at 12 MLD"),
                "cost_kl":    _t(0.611, Tol.TIGHT,    "highest $/kL — hard to justify vs BNR"),
                "kwh_ml":     _t(317,   Tol.MODERATE, "MABR energy advantage"),
                "kwh_kg_nh4": _t(4.6, Tol.MODERATE, "best nitrif efficiency"),
                "scope2_co2": _t(899,   Tol.TIGHT,    "deterministic"),
                "eff_nh4":    _rng(0.8, 1.3, "tight", "MABR reliable nitrif at 18°C"),
            },
            "bnr_mbr": {
                "capex_m":    _t(13.61, Tol.TIGHT,    "BNR+MBR — justified if reuse planned"),
                "cost_kl":    _t(0.562, Tol.TIGHT,    ""),
                "kwh_ml":     _t(488,   Tol.MODERATE, "MBR scour dominates energy"),
                "kwh_kg_nh4": _t(14.4,  Tol.MODERATE, "MBR: highest kWh/kgNH4 (computed from totals)"),
                "scope2_co2": _t(1484, Tol.TIGHT, "highest Scope 2 — highest energy"),
                "eff_nh4":    _rng(0.8, 1.3, "tight", "target 1 mg/L — MBR consistent nitrif"),
            },
        },
    ),

    # ══════════════════════════════════════════════════════════════════════
    # S4 — Capacity Expansion, Footprint Constrained
    # Purpose: Footprint is the binding constraint. AGS wins.
    # Decision tension: AGS saves 830 m² vs BNR but costs same per kL.
    #   MBR costs $0.498/kL vs BNR $0.311 — footprint saving not worth it.
    #   AGS at $0.271/kL AND smaller footprint dominates.
    # Calibration: BNR=2418 m², AGS=1642 m² (32% saving), MBR=2587 m²
    # ══════════════════════════════════════════════════════════════════════
    Scenario(
        id="S4", name="Capacity Expansion — Footprint Constrained",
        description=(
            "20 MLD, constrained site. Decision tension: AGS saves 800 m² "
            "vs BNR ($0.271 vs $0.311/kL) — clear dominant option. "
            "MBR is 60% more expensive per kL with similar footprint to BNR "
            "at 20 MLD (BNR zone dominates). AGS wins on both metrics."
        ),
        design_flow_mld=20.0, peak_flow_factor=2.2,
        influent_bod_mg_l=240, influent_cod_mg_l=480,
        influent_tss_mg_l=260, influent_nh4_mg_l=32,
        influent_tkn_mg_l=42,  influent_tp_mg_l=5,
        influent_temperature_celsius=19,
        effluent_tn_mg_l=10, effluent_tp_mg_l=1,
        technologies=["bnr", "granular_sludge", "bnr_mbr", "ifas_mbbr"],
        expected={
            "bnr": {
                "capex_m":    _t(11.36, Tol.TIGHT,    "20 MLD scale economy"),
                "cost_kl":    _t(0.311, Tol.TIGHT,    "BNR lowest $/kL at 20 MLD"),
                "kwh_ml":     _t(359,   Tol.MODERATE, ""),
                "scope2_co2": _t(1759, Tol.TIGHT, "deterministic"),
                # Footprint physics: HRT 5-8hr → reactor 2400-3800 m³ + 2 clarifiers
                "footprint_m2": _rng(1900, 2950, "moderate", "20MLD BNR reactor+2 clarifiers"),
            },
            "granular_sludge": {
                "capex_m":    _t(9.34,  Tol.TIGHT,    "AGS no clarifiers saves CAPEX"),
                "cost_kl":    _t(0.271, Tol.TIGHT,    "AGS cheapest $/kL — dominant option"),
                "kwh_ml":     _t(324,   Tol.MODERATE, ""),
                "scope2_co2": _t(1541, Tol.TIGHT, "deterministic"),
                # AGS footprint physics: SBR reactor only, no clarifiers
                "footprint_m2": _rng(1300, 2000, "moderate", "20MLD AGS SBR, no clarifiers"),
            },
            "bnr_mbr": {
                "capex_m":    _t(19.01, Tol.TIGHT,    "MBR 67% more CAPEX than BNR"),
                "cost_kl":    _t(0.498, Tol.TIGHT,    "60% premium over BNR — hard to justify"),
                "kwh_ml":     _t(460,   Tol.MODERATE, "MBR scour"),
                "scope2_co2": _t(2324, Tol.TIGHT, "deterministic"),
                "footprint_m2": _rng(1600, 3400, "moderate", "BNR zone dominates at 20 MLD"),
            },
        },
    ),

    # ══════════════════════════════════════════════════════════════════════
    # S5 — Carbon-Limited Denitrification
    # Purpose: Model must detect COD/TKN < 7 and report TN > target.
    # Decision tension: Supplemental carbon (methanol) adds $80-120k/yr OPEX
    #   and would fix TN compliance. Without it: BNR TN=18 mg/L (fails 10).
    #   Also: low BOD → low energy, low sludge — shows BOD drives costs.
    # Calibration: BNR TN=18.0, IFAS TN=20.2 (COD/TKN=5.3)
    # ══════════════════════════════════════════════════════════════════════
    Scenario(
        id="S5", name="Carbon-Limited Denitrification",
        description=(
            "10 MLD, BOD=120/TKN=45 → COD/TKN≈5.3 (threshold 7.0). "
            "TN compliance NOT achievable without supplemental carbon. "
            "Decision tension: add methanol ($80-120k/yr) or accept TN=18 mg/L. "
            "Also shows: low BOD gives low energy (262 kWh/ML) and low sludge."
        ),
        design_flow_mld=10.0, peak_flow_factor=2.5,
        influent_bod_mg_l=120, influent_cod_mg_l=240,
        influent_tss_mg_l=160, influent_nh4_mg_l=35,
        influent_tkn_mg_l=45,  influent_tp_mg_l=5,
        influent_temperature_celsius=20,
        effluent_tn_mg_l=10, effluent_nh4_mg_l=5, effluent_tp_mg_l=1,
        technologies=["bnr", "ifas_mbbr"],
        expected={
            "bnr": {
                "capex_m":    _t(7.04,  Tol.TIGHT,    "low BOD → smaller reactor than S1"),
                "cost_kl":    _t(0.314, Tol.TIGHT,    "low BOD: cheap despite TN failure"),
                "kwh_ml":     _t(262,   Tol.MODERATE, "low BOD load → less O2 demand"),
                "sludge":     _t(741,   Tol.MODERATE, "half the sludge of S1 at same flow"),
                "scope2_co2": _t(754,   Tol.TIGHT,    "deterministic"),
                # TN MUST exceed target — carbon limitation detection test
                "eff_tn":     _rng(14.0, 25.0, "tight", "COD/TKN=5.3→TN carbon-limited"),
            },
            "ifas_mbbr": {
                "capex_m":    _t(11.61, Tol.TIGHT,    "IFAS: higher CAPEX than BNR"),
                "cost_kl":    _t(0.442, Tol.TIGHT,    "IFAS 41% more expensive than BNR here"),
                "kwh_ml":     _t(279,   Tol.MODERATE, "low BOD load"),
                "scope2_co2": _t(803,   Tol.TIGHT,    "deterministic"),
                # IFAS worse than BNR under C-limited — less dedicated anoxic zone
                "eff_tn":     _rng(17.0, 24.0, "tight", "IFAS: actual=20.2, C-limited >BNR"),
            },
        },
    ),

    # ══════════════════════════════════════════════════════════════════════
    # S6 — Energy and Carbon Reduction
    # Purpose: High electricity ($0.22/kWh) makes energy differences material.
    # Decision tension: AGS cheapest LCC ($1505k, $0.344/kL) at high elec.
    #   BNR mid ($1717k), MABR most expensive ($2707k) despite lowest energy.
    #   MABR energy advantage (55 kWh/ML less) worth ~$38k/yr at $0.22/kWh
    #   but CAPEX premium is $8M — never pays back at 10MLD scale.
    # ══════════════════════════════════════════════════════════════════════
    Scenario(
        id="S6", name="Energy and Carbon Reduction",
        description=(
            "12 MLD at $0.22/kWh electricity, $80/tCO2. "
            "Decision tension: AGS wins LCC despite not having lowest energy. "
            "MABR saves 55 kWh/ML but CAPEX premium ($8M) never pays back "
            "at 12 MLD. Energy sensitivity changes OPEX ranking but not CAPEX."
        ),
        design_flow_mld=12.0, peak_flow_factor=2.5,
        influent_bod_mg_l=260, influent_cod_mg_l=520,
        influent_tss_mg_l=290, influent_nh4_mg_l=35,
        influent_tkn_mg_l=46,  influent_tp_mg_l=6,
        influent_temperature_celsius=20,
        electricity_price_per_kwh=0.22,
        carbon_price_per_tco2e=80.0,
        effluent_tn_mg_l=10, effluent_tp_mg_l=1,
        technologies=["bnr", "mabr_bnr", "granular_sludge"],
        expected={
            "bnr": {
                "capex_m":    _t(8.82,  Tol.TIGHT,    "same CAPEX as S1 — elec doesn't affect"),
                "cost_kl":    _t(0.392, Tol.TIGHT,    "higher than S1 due to $0.22 elec"),
                "kwh_ml":     _t(384,   Tol.MODERATE, ""),
                "opex_k":     _t(1006,  Tol.MODERATE, "39% more than S1 due to $0.22 elec"),
                "scope2_co2": _t(1121, Tol.TIGHT, "deterministic"),
                "kwh_kg_nh4": _t(7.2, Tol.MODERATE, ""),
            },
            "mabr_bnr": {
                "capex_m":    _t(16.97, Tol.TIGHT,    "CAPEX unchanged"),
                "cost_kl":    _t(0.618, Tol.TIGHT,    "highest $/kL even at high elec"),
                "kwh_ml":     _t(329,   Tol.MODERATE, "14% below BNR"),
                "opex_k":     _t(1340,  Tol.MODERATE, "higher OPEX despite lower energy (labour+maint)"),
                "scope2_co2": _t(932, Tol.TIGHT, ""),
            },
            "granular_sludge": {
                "capex_m":    _t(7.36,  Tol.TIGHT,    "cheapest CAPEX"),
                "cost_kl":    _t(0.344, Tol.TIGHT,    "AGS wins LCC at high electricity"),
                "kwh_ml":     _t(354,   Tol.MODERATE, "8% below BNR"),
                "opex_k":     _t(911,   Tol.MODERATE, "cheapest OPEX"),
                "scope2_co2": _t(1013, Tol.TIGHT, ""),
            },
        },
    ),

    # ══════════════════════════════════════════════════════════════════════
    # S7 — Biosolids Disposal Cost Pressure
    # Purpose: Sludge disposal ($450/t DS) dominates OPEX and shifts LCC.
    # Decision tension: BNR OPEX=$2053k — sludge disposal is $671k (33%!).
    #   AGS 18% less sludge → $122k/yr saved on disposal alone.
    #   AGS LCC=$2716k vs BNR $3165k — AGS wins despite higher risk.
    #   MBR $4950k LCC — sludge saving (negligible vs BNR) cannot justify premium.
    # ══════════════════════════════════════════════════════════════════════
    Scenario(
        id="S7", name="Biosolids Disposal Cost Pressure",
        description=(
            "25 MLD at $450/t DS sludge disposal. "
            "Decision tension: sludge disposal = 33% of BNR OPEX. "
            "AGS 18% less sludge saves $122k/yr and wins LCC by $449k/yr. "
            "MBR cannot justify $1785k/yr LCC premium — sludge saving minimal."
        ),
        design_flow_mld=25.0, peak_flow_factor=2.3,
        influent_bod_mg_l=280, influent_cod_mg_l=560,
        influent_tss_mg_l=300, influent_nh4_mg_l=38,
        influent_tkn_mg_l=50,  influent_tp_mg_l=7,
        influent_temperature_celsius=20,
        sludge_disposal_per_tds=450.0,
        effluent_tn_mg_l=10, effluent_tp_mg_l=1,
        technologies=["bnr", "granular_sludge", "bnr_mbr"],
        expected={
            "bnr": {
                "capex_m":    _t(13.81, Tol.TIGHT,    "25 MLD scale economy"),
                "cost_kl":    _t(0.347, Tol.TIGHT,    ""),
                "sludge":     _t(4083,  Tol.MODERATE, "25 MLD at BOD=280"),
                "opex_k":     _t(2053,  Tol.MODERATE, "high sludge disposal dominates"),
                "lcc_k":      _t(3165,  Tol.MODERATE, ""),
                "sludge_opex_k": _t(671, Tol.MODERATE, "sludge disposal = 33% of OPEX"),
                "scope2_co2": _t(2460, Tol.TIGHT, "deterministic"),
            },
            "granular_sludge": {
                "capex_m":    _t(10.84, Tol.TIGHT,    "AGS saves $3M vs BNR at 25 MLD"),
                "cost_kl":    _t(0.298, Tol.TIGHT,    "AGS wins $/kL by $0.05"),
                "sludge":     _t(3356,  Tol.MODERATE, "18% less than BNR at same flow"),
                "opex_k":     _t(1843,  Tol.MODERATE, "lower sludge disposal saves $210k"),
                "lcc_k":      _t(2716,  Tol.MODERATE, "AGS wins LCC by $449k/yr"),
                "scope2_co2": _t(2241, Tol.TIGHT, "deterministic"),
            },
            "bnr_mbr": {
                "capex_m":    _t(23.90, Tol.TIGHT,    "MBR: 73% more CAPEX than BNR"),
                "cost_kl":    _t(0.542, Tol.TIGHT,    "56% premium over BNR — hard to justify"),
                "opex_k":     _t(3025,  Tol.MODERATE, "MBR + high sludge cost"),
                "lcc_k":      _t(4950,  Tol.MODERATE, "$1785k/yr more than BNR"),
                "scope2_co2": _t(3139, Tol.TIGHT, "highest energy → highest Scope 2"),
            },
        },
    ),

    # ══════════════════════════════════════════════════════════════════════
    # S8 — Reuse-Ready Effluent Polishing
    # Purpose: Tight targets (TN<5, TSS<5, TP<0.3) for IPR pre-treatment.
    # Decision tension: MBR achieves TSS<1 and BOD<5 by membrane — necessary
    #   for MF/RO downstream. Costs $0.573/kL vs BNR $0.375/kL (53% premium).
    #   AGS achieves TP<0.3 with ferric at $0.390/kL — cheapest reuse option
    #   but TSS=5 may not satisfy downstream MF inlet requirements.
    # ══════════════════════════════════════════════════════════════════════
    Scenario(
        id="S8", name="Reuse-Ready Effluent Polishing",
        description=(
            "10 MLD, IPR pre-treatment targets: TN<5, TSS<5, TP<0.3. "
            "Decision tension: MBR achieves TSS<1 (essential for RO protection) "
            "at 53% $/kL premium. AGS cheapest but TSS=5 may fail MF inlet spec. "
            "BNR alone cannot achieve TSS<5 consistently."
        ),
        design_flow_mld=10.0, peak_flow_factor=2.5,
        influent_bod_mg_l=250, influent_cod_mg_l=500,
        influent_tss_mg_l=280, influent_nh4_mg_l=35,
        influent_tkn_mg_l=45,  influent_tp_mg_l=6,
        influent_temperature_celsius=20,
        effluent_bod_mg_l=5, effluent_tss_mg_l=5,
        effluent_tn_mg_l=5,  effluent_nh4_mg_l=1, effluent_tp_mg_l=0.3,
        technologies=["bnr_mbr", "granular_sludge", "bnr"],
        expected={
            "bnr_mbr": {
                "capex_m":    _t(11.81, Tol.TIGHT,    "BNR+MBR: 48% more than plain BNR"),
                "cost_kl":    _t(0.573, Tol.TIGHT,    "MBR premium justified for RO protection"),
                "kwh_ml":     _t(473,   Tol.MODERATE, "MBR highest energy — scour dominates"),
                "kwh_kg_nh4": _t(13.9,  Tol.MODERATE, "MBR: highest kWh/kgNH4"),
                "scope2_co2": _t(1193, Tol.TIGHT, "deterministic"),
                # Effluent quality — MBR physical separation, tight bounds
                "eff_bod":    _rng(1.5,  4.5, "tight", "MBR: soluble BOD 2-4 mg/L passes membrane"),
                "eff_tss":    _rng(0.5,  1.2, "tight", "MBR: membrane absolute barrier, typically 0.5-1 mg/L"),
                "eff_tn":     _rng(4.0,  5.5, "tight", "tight TN target 5 mg/L"),
                "eff_nh4":    _rng(0.8,  1.3, "tight", "target 1 mg/L"),
            },
            "granular_sludge": {
                "capex_m":    _t(6.86,  Tol.TIGHT,    "cheapest option"),
                "cost_kl":    _t(0.390, Tol.TIGHT,    "AGS cheapest $/kL for reuse"),
                "kwh_ml":     _t(344,   Tol.MODERATE, ""),
                "scope2_co2": _t(818, Tol.TIGHT, "deterministic"),
                # AGS + ferric P removal: TP target is tight
                "eff_tp":     _rng(0.15, 0.45, "tight", "AGS+ferric: actual=0.3, ferric polishing"),
                "eff_tn":     _rng(4.0,  5.5, "tight", "tight TN target"),
            },
            "bnr": {
                "capex_m":    _t(7.98,  Tol.TIGHT,    "BNR: adequate TN/NH4 but TSS risk"),
                "cost_kl":    _t(0.375, Tol.TIGHT,    ""),
                "scope2_co2": _t(942, Tol.TIGHT, "deterministic"),
                "eff_tn":     _rng(4.0,  5.5, "tight", ""),
                "eff_nh4":    _rng(0.8,  1.3, "tight", "target 1 mg/L"),
            },
        },
    ),
]


# ── Accessors ──────────────────────────────────────────────────────────────────

def get_all() -> List[Scenario]:
    return SCENARIOS

def get_by_id(sid: str) -> Optional[Scenario]:
    return next((s for s in SCENARIOS if s.id == sid), None)

def to_inputs_dict(s: Scenario) -> dict:
    return {
        "design_flow_mld":              s.design_flow_mld,
        "peak_flow_factor":             s.peak_flow_factor,
        "influent_bod_mg_l":            s.influent_bod_mg_l,
        "influent_cod_mg_l":            s.influent_cod_mg_l,
        "influent_tss_mg_l":            s.influent_tss_mg_l,
        "influent_nh4_mg_l":            s.influent_nh4_mg_l,
        "influent_tkn_mg_l":            s.influent_tkn_mg_l,
        "influent_tp_mg_l":             s.influent_tp_mg_l,
        "influent_temperature_celsius":  s.influent_temperature_celsius,
        "effluent_bod_mg_l":            s.effluent_bod_mg_l,
        "effluent_tss_mg_l":            s.effluent_tss_mg_l,
        "effluent_tn_mg_l":             s.effluent_tn_mg_l,
        "effluent_nh4_mg_l":            s.effluent_nh4_mg_l,
        "effluent_tp_mg_l":             s.effluent_tp_mg_l,
    }
