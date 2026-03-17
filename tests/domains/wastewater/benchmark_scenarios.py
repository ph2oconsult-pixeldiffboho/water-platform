"""
tests/domains/wastewater/benchmark_scenarios.py

BENCHMARK SCENARIO PACK — Wastewater Planning Platform
=======================================================
8 realistic municipal wastewater planning scenarios with expected output
ranges for regression testing.

All ranges are calibrated against:
  Metcalf & Eddy 5th Ed (primary engineering reference)
  WEF Cost Estimating Manual 2018 (cost ranges)
  de Kreuk 2007, van Dijk 2020 (AGS references)
  GE/Ovivo 2017 (MABR reference)
  AU Water Association utility benchmarks (cost/energy)
  IPCC 2019 Tier 1 (N2O factors)

All costs AUD 2024. CAPEX ±40%, OPEX ±25%.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class ExpectedRange:
    """Min/max acceptable output range with reference."""
    lo: float
    hi: float
    ref: str = ""

    def check(self, value: float) -> bool:
        return self.lo <= value <= self.hi

    def fmt(self) -> str:
        return f"[{self.lo:.1f}, {self.hi:.1f}]"


@dataclass
class BenchmarkScenario:
    """A single benchmark scenario with inputs and expected output ranges."""
    id: str
    name: str
    description: str

    # ── Inputs ────────────────────────────────────────────────────────────
    design_flow_mld: float
    peak_flow_factor: float
    influent_bod_mg_l: float
    influent_cod_mg_l: float
    influent_tss_mg_l: float
    influent_nh4_mg_l: float
    influent_tkn_mg_l: float
    influent_tp_mg_l: float
    influent_temperature_celsius: float

    # Economic inputs
    electricity_price_per_kwh: float = 0.14
    sludge_disposal_per_tds: float = 280.0
    carbon_price_per_tco2e: float = 35.0
    discount_rate: float = 0.07
    analysis_period_years: int = 30

    # Effluent targets
    effluent_bod_mg_l: float = 10.0
    effluent_tss_mg_l: float = 10.0
    effluent_tn_mg_l:  float = 10.0
    effluent_nh4_mg_l: float = 5.0
    effluent_tp_mg_l:  float = 1.0

    # Technologies to evaluate
    technologies: List[str] = field(default_factory=lambda: ["bnr"])

    # ── Expected output ranges per technology ─────────────────────────────
    # Format: { tech_code: { metric_name: ExpectedRange } }
    expected: Dict[str, Dict[str, ExpectedRange]] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

BENCHMARK_SCENARIOS: List[BenchmarkScenario] = [

    # ── S1: Medium municipal BNR baseline ────────────────────────────────
    BenchmarkScenario(
        id="S1",
        name="Medium Municipal BNR Baseline",
        description=(
            "10 MLD conventional municipal BNR. Typical suburban catchment, "
            "standard TN/TP limits. Primary reference scenario — all other "
            "scenarios are deviations from this baseline."
        ),
        design_flow_mld=10.0,
        peak_flow_factor=2.5,
        influent_bod_mg_l=250, influent_cod_mg_l=500,
        influent_tss_mg_l=280, influent_nh4_mg_l=35,
        influent_tkn_mg_l=45,  influent_tp_mg_l=6,
        influent_temperature_celsius=20,
        effluent_tn_mg_l=10, effluent_nh4_mg_l=5, effluent_tp_mg_l=1,
        technologies=["bnr", "granular_sludge", "ifas_mbbr", "mabr_bnr"],
        expected={
            "bnr": {
                "capex_m": ExpectedRange(6.0, 12.0,  "WEF Cost Manual 2018, ±40% on $7.8M"),
                "opex_k":  ExpectedRange(500, 1000,  "AU utility benchmark 10 MLD BNR"),
                "lcc_k":   ExpectedRange(900, 1700,  "CRF(7%,30yr)×CAPEX + OPEX"),
                "kwh_ml":  ExpectedRange(300, 500,   "Metcalf 5th Ed Table 12-10"),
                "sludge":  ExpectedRange(1000, 2000, "y_obs=0.31, TSS+inorganic"),
                "net_co2": ExpectedRange(1200, 2200, "Scope1+2 at 0.79 kgCO2/kWh"),
                "footprint_m2": ExpectedRange(1000, 2500, "reactor/4.5 + clarifier"),
                "eff_tn":  ExpectedRange(0, 11,     "Target 10 mg/L at BOD/TKN=11"),
            },
            "granular_sludge": {
                "capex_m": ExpectedRange(5.0, 10.0,  "AGS: no clarifiers, ±40%"),
                "kwh_ml":  ExpectedRange(200, 380,   "de Kreuk 2007"),
                "sludge":  ExpectedRange(800, 1700,  "17% less than BNR (longer SRT)"),
            },
            "mabr_bnr": {
                "kwh_ml":  ExpectedRange(200, 420,   "GE/Ovivo 2017: 15-25% below BNR"),
                "capex_m": ExpectedRange(10.0, 20.0, "MABR membrane premium"),
            },
        },
    ),

    # ── S2: Cold climate nitrification ───────────────────────────────────
    BenchmarkScenario(
        id="S2",
        name="Cold Climate Nitrification",
        description=(
            "8 MLD, 12°C wastewater temperature. Nitrification is the "
            "primary design constraint. Tests cold-temperature penalties "
            "on BNR (SRT extension) and AGS (granule stability risk)."
        ),
        design_flow_mld=8.0,
        peak_flow_factor=3.0,
        influent_bod_mg_l=220, influent_cod_mg_l=440,
        influent_tss_mg_l=240, influent_nh4_mg_l=38,
        influent_tkn_mg_l=48,  influent_tp_mg_l=5,
        influent_temperature_celsius=12,
        effluent_tn_mg_l=10, effluent_nh4_mg_l=3, effluent_tp_mg_l=1,
        technologies=["bnr", "granular_sludge", "mabr_bnr", "ifas_mbbr"],
        expected={
            "bnr": {
                "capex_m":    ExpectedRange(4.0, 9.0,   "8 MLD cold climate BNR"),
                "kwh_ml":     ExpectedRange(280, 480,   "Cold T: aeration ~same, ancillary same"),
                "reactor_m3": ExpectedRange(2000, 4000, "SRT extended at 12°C"),
                "eff_nh4":    ExpectedRange(0, 8.0,    "At 12°C NH4 penalty ×4 on target → up to ~4-6 mg/L"),
            },
            "granular_sludge": {
                "kwh_ml":     ExpectedRange(220, 380,   "Cold T AGS: T_factor reduces nit O2 demand; net energy similar to warm; cold_reactor_penalty adds reactor volume not energy"),
                "reactor_m3": ExpectedRange(1200, 3000, "SRT extended 25% at 12°C"),
                "eff_nh4":    ExpectedRange(1.5, 5.0,  "Granule instability → NH4 penalty"),
            },
            "mabr_bnr": {
                "kwh_ml":     ExpectedRange(200, 380,   "MABR less affected by cold T"),
            },
        },
    ),

    # ── S3: Tight ammonia compliance ─────────────────────────────────────
    BenchmarkScenario(
        id="S3",
        name="Tight Ammonia Compliance",
        description=(
            "12 MLD, effluent NH4 < 1 mg/L. Tests nitrification adequacy "
            "across technologies. MABR and IFAS relevant."
        ),
        design_flow_mld=12.0,
        peak_flow_factor=2.5,
        influent_bod_mg_l=250, influent_cod_mg_l=500,
        influent_tss_mg_l=280, influent_nh4_mg_l=40,
        influent_tkn_mg_l=52,  influent_tp_mg_l=6,
        influent_temperature_celsius=18,
        effluent_tn_mg_l=10, effluent_nh4_mg_l=1, effluent_tp_mg_l=1,
        technologies=["bnr", "mabr_bnr", "ifas_mbbr", "bnr_mbr"],
        expected={
            "bnr": {
                "capex_m":  ExpectedRange(7.0, 14.0,  "12 MLD BNR"),
                "kwh_ml":   ExpectedRange(300, 520,   "High TKN → more nitrification O2"),
                "eff_nh4":  ExpectedRange(0, 1.5,    "Target 1 mg/L achievable at 18°C"),
            },
            "mabr_bnr": {
                "kwh_ml":   ExpectedRange(200, 400,   "MABR energy advantage"),
                "capex_m":  ExpectedRange(14.0, 26.0, "MABR membrane premium"),
                "eff_nh4":  ExpectedRange(0, 1.5,    "MABR reliable nitrification"),
            },
        },
    ),

    # ── S4: Capacity expansion, footprint constrained ────────────────────
    BenchmarkScenario(
        id="S4",
        name="Capacity Expansion — Footprint Constrained",
        description=(
            "20 MLD, limited site. Primary driver: minimise m²/MLD. "
            "AGS and MBR should show lowest footprint."
        ),
        design_flow_mld=20.0,
        peak_flow_factor=2.2,
        influent_bod_mg_l=240, influent_cod_mg_l=480,
        influent_tss_mg_l=260, influent_nh4_mg_l=32,
        influent_tkn_mg_l=42,  influent_tp_mg_l=5,
        influent_temperature_celsius=19,
        effluent_tn_mg_l=10, effluent_tp_mg_l=1,
        technologies=["bnr", "granular_sludge", "bnr_mbr", "ifas_mbbr"],
        expected={
            "bnr": {
                "capex_m":    ExpectedRange(9.0, 20.0,  "20 MLD BNR with scale economy"),
                "footprint_m2": ExpectedRange(2000, 5000, "Reactor + 2 clarifiers"),
            },
            "granular_sludge": {
                "footprint_m2": ExpectedRange(1200, 3500, "SBR: smaller than BNR+clarifiers"),
                "capex_m":    ExpectedRange(8.0, 18.0,  "AGS: no secondary clarifiers"),
            },
            "bnr_mbr": {
                "footprint_m2": ExpectedRange(1000, 3000, "MBR: highest density, no clarifiers"),
                "capex_m":    ExpectedRange(15.0, 32.0,  "MBR membrane premium"),
                "kwh_ml":     ExpectedRange(400, 700,   "MBR: high aeration + membrane scour"),
            },
        },
    ),

    # ── S5: Low COD:TKN — carbon-limited denitrification ─────────────────
    BenchmarkScenario(
        id="S5",
        name="Carbon-Limited Denitrification",
        description=(
            "10 MLD, BOD=120 mg/L, TKN=45 mg/L (COD/TKN ≈ 5.3). "
            "Denitrification severely limited without supplemental carbon. "
            "Tests model response to carbon-limited conditions."
        ),
        design_flow_mld=10.0,
        peak_flow_factor=2.5,
        influent_bod_mg_l=120, influent_cod_mg_l=240,
        influent_tss_mg_l=160, influent_nh4_mg_l=35,
        influent_tkn_mg_l=45,  influent_tp_mg_l=5,
        influent_temperature_celsius=20,
        effluent_tn_mg_l=10, effluent_nh4_mg_l=5, effluent_tp_mg_l=1,
        technologies=["bnr", "ifas_mbbr"],
        expected={
            "bnr": {
                "capex_m":  ExpectedRange(4.0, 9.0,  "Low BOD → smaller reactor"),
                "kwh_ml":   ExpectedRange(150, 320,  "Low BOD load → less aeration"),
                "eff_tn":   ExpectedRange(12, 35,    "COD/TKN=5.3 → carbon-limited TN"),
                "sludge":   ExpectedRange(400, 900,  "Low BOD → low sludge"),
            },
            "ifas_mbbr": {
                "eff_tn":   ExpectedRange(15, 40,    "IFAS even more C-limited (less anoxic zone)"),
            },
        },
    ),

    # ── S6: Energy and carbon reduction ──────────────────────────────────
    BenchmarkScenario(
        id="S6",
        name="Energy and Carbon Reduction",
        description=(
            "12 MLD at $0.22/kWh (high electricity). Carbon price AUD $80/t. "
            "Decision driver is lifecycle cost at high energy price. "
            "MABR and AGS energy advantage becomes material."
        ),
        design_flow_mld=12.0,
        peak_flow_factor=2.5,
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
                "kwh_ml":   ExpectedRange(300, 500,   "Standard BNR energy"),
                "net_co2":  ExpectedRange(1400, 2600, "Scope1+2"),
                "opex_k":   ExpectedRange(700, 1400,  "Higher elec price → higher OPEX"),
            },
            "mabr_bnr": {
                "kwh_ml":   ExpectedRange(200, 400,   "MABR 15-25% energy saving"),
                "net_co2":  ExpectedRange(1100, 2200, "Lower Scope 2"),
            },
            "granular_sludge": {
                "kwh_ml":   ExpectedRange(200, 380,   "AGS lower energy than BNR"),
            },
        },
    ),

    # ── S7: Biosolids disposal cost pressure ─────────────────────────────
    BenchmarkScenario(
        id="S7",
        name="Biosolids Disposal Cost Pressure",
        description=(
            "25 MLD, sludge disposal AUD $450/t DS. High sludge cost makes "
            "technologies with lower sludge production (AGS, MBR) more "
            "competitive on lifecycle cost despite higher CAPEX."
        ),
        design_flow_mld=25.0,
        peak_flow_factor=2.3,
        influent_bod_mg_l=280, influent_cod_mg_l=560,
        influent_tss_mg_l=300, influent_nh4_mg_l=38,
        influent_tkn_mg_l=50,  influent_tp_mg_l=7,
        influent_temperature_celsius=20,
        sludge_disposal_per_tds=450.0,
        effluent_tn_mg_l=10, effluent_tp_mg_l=1,
        technologies=["bnr", "granular_sludge", "bnr_mbr"],
        expected={
            "bnr": {
                "capex_m":  ExpectedRange(13.0, 28.0, "25 MLD with scale economy"),
                "sludge":   ExpectedRange(3000, 5500, "25 MLD at BOD=280"),
                "opex_k":   ExpectedRange(1200, 2800, "High sludge cost drives OPEX up"),
            },
            "granular_sludge": {
                "sludge":   ExpectedRange(2300, 4500, "17% less than BNR"),
                "opex_k":   ExpectedRange(1000, 2400, "Lower sludge disposal"),
            },
        },
    ),

    # ── S8: Reuse-ready effluent polishing ────────────────────────────────
    BenchmarkScenario(
        id="S8",
        name="Reuse-Ready Effluent Polishing",
        description=(
            "10 MLD, tight effluent targets suitable for indirect potable reuse "
            "pathway. BOD<5, TSS<5, TN<5, NH4<1, TP<0.5. "
            "BNR+MBR or AGS+ferric are the relevant options."
        ),
        design_flow_mld=10.0,
        peak_flow_factor=2.5,
        influent_bod_mg_l=250, influent_cod_mg_l=500,
        influent_tss_mg_l=280, influent_nh4_mg_l=35,
        influent_tkn_mg_l=45,  influent_tp_mg_l=6,
        influent_temperature_celsius=20,
        effluent_bod_mg_l=5, effluent_tss_mg_l=5,
        effluent_tn_mg_l=5,  effluent_nh4_mg_l=1, effluent_tp_mg_l=0.3,
        technologies=["bnr_mbr", "granular_sludge", "bnr"],
        expected={
            "bnr_mbr": {
                "capex_m":  ExpectedRange(9.0, 18.0,  "BNR+MBR for reuse"),
                "kwh_ml":   ExpectedRange(400, 700,   "MBR high energy"),
                "eff_bod":  ExpectedRange(0, 5.0,    "MBR achieves BOD <3 mg/L"),
                "eff_tss":  ExpectedRange(0, 2.0,    "MBR achieves TSS <1 mg/L"),
                "eff_tn":   ExpectedRange(0, 6.0,    "Tight TN target"),
            },
            "granular_sludge": {
                "eff_tp":   ExpectedRange(0, 0.5,    "AGS+ferric for TP<0.5"),
                "opex_k":   ExpectedRange(500, 1100,  "Chemical P polish adds cost"),
            },
        },
    ),
]


def get_scenario_by_id(scenario_id: str) -> Optional[BenchmarkScenario]:
    return next((s for s in BENCHMARK_SCENARIOS if s.id == scenario_id), None)


def get_all_scenarios() -> List[BenchmarkScenario]:
    return BENCHMARK_SCENARIOS


def scenario_to_inputs_dict(s: BenchmarkScenario) -> dict:
    """Convert scenario to WastewaterInputs keyword arguments."""
    return {
        "design_flow_mld":             s.design_flow_mld,
        "peak_flow_factor":            s.peak_flow_factor,
        "influent_bod_mg_l":           s.influent_bod_mg_l,
        "influent_cod_mg_l":           s.influent_cod_mg_l,
        "influent_tss_mg_l":           s.influent_tss_mg_l,
        "influent_nh4_mg_l":           s.influent_nh4_mg_l,
        "influent_tkn_mg_l":           s.influent_tkn_mg_l,
        "influent_tp_mg_l":            s.influent_tp_mg_l,
        "influent_temperature_celsius": s.influent_temperature_celsius,
        "effluent_bod_mg_l":           s.effluent_bod_mg_l,
        "effluent_tss_mg_l":           s.effluent_tss_mg_l,
        "effluent_tn_mg_l":            s.effluent_tn_mg_l,
        "effluent_nh4_mg_l":           s.effluent_nh4_mg_l,
        "effluent_tp_mg_l":            s.effluent_tp_mg_l,
    }
