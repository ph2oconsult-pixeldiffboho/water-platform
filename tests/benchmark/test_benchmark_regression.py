"""
tests/benchmark/test_benchmark_regression.py

WASTEWATER PLANNING PLATFORM — ENGINEERING REGRESSION TESTS
============================================================
Pytest-based regression suite that runs all 8 benchmark scenarios and
checks outputs against calibrated engineering ranges.

HOW TO RUN
----------
    # All benchmark tests
    pytest tests/benchmark/ -v

    # Single scenario
    pytest tests/benchmark/ -v -k "S1"

    # Only range checks
    pytest tests/benchmark/ -v -k "range"

    # Only behavioural checks
    pytest tests/benchmark/ -v -k "behaviour"

    # Fast smoke test (one tech per scenario)
    pytest tests/benchmark/ -v -k "S1 or S5 or S8"

FAILURE INTERPRETATION
----------------------
Range failure  → a number drifted outside its tolerance band.
               Check: recent costing/energy/sludge code changes.
               The failed test name includes scenario ID, tech, and metric.

Behaviour fail → an engineering relationship was violated.
               e.g. "cold_ags_energy_increases" failing means cold temperature
               no longer raises AGS energy — a physics regression.

STRUCTURE
---------
test_scenario_range_*  — numeric output checks against Range bounds
test_behaviour_*       — qualitative engineering relationship checks
test_smoke_*           — fast sanity checks (non-zero, valid, no crash)
"""
from __future__ import annotations
import copy
try:
    import pytest
    _PYTEST_AVAILABLE = True
except ImportError:
    # Running standalone — pytest not installed.
    # Use `python3 tests/benchmark/run_benchmarks.py` instead.
    _PYTEST_AVAILABLE = False
    class _PytestShim:
        """Minimal shim so the module parses without pytest installed."""
        @staticmethod
        def mark():
            class _M:
                @staticmethod
                def parametrize(*a, **kw):
                    def decorator(fn): return fn
                    return decorator
                fixture = parametrize
            return _M()
        @staticmethod
        def param(*args, **kwargs): return args[0] if args else None
        mark = type('mark', (), {
            'parametrize': lambda *a, **kw: (lambda fn: fn),
        })()
        fixture = staticmethod(lambda *a, **kw: (lambda fn: fn))
        approx = staticmethod(lambda x, **kw: x)
    pytest = _PytestShim()

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.benchmark.scenarios import get_all, get_by_id, SCENARIOS, to_inputs_dict
from tests.benchmark.conftest import run_scenario_tech, extract_metrics

from core.assumptions.assumptions_manager import AssumptionsManager
from core.project.project_model import DomainType
from domains.wastewater.domain_interface import WastewaterDomainInterface
from domains.wastewater.input_model import WastewaterInputs


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _run(scenario_id: str, tech: str, assumptions):
    s = get_by_id(scenario_id)
    assert s is not None, f"Scenario {scenario_id!r} not found"
    return run_scenario_tech(s, tech, assumptions)


def _metrics(scenario_id: str, tech: str, assumptions) -> dict:
    r = _run(scenario_id, tech, assumptions)
    return extract_metrics(r, tech)


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TESTS — fast sanity, runs all scenario×tech combinations
# ─────────────────────────────────────────────────────────────────────────────

class TestSmoke:
    """
    Non-zero, valid, no-crash checks for every scenario × technology.

    These catch import errors, missing technology modules, and total
    calculation failures before the detailed range tests run.
    """

    @pytest.mark.parametrize("scenario_id,tech", [
        (s.id, tech)
        for s in SCENARIOS
        for tech in s.technologies
    ])
    def test_produces_nonzero_costs(self, scenario_id, tech, base_assumptions):
        """Every (scenario, tech) must produce CAPEX > 0 and OPEX > 0."""
        r = _run(scenario_id, tech, base_assumptions)
        assert r.cost_result is not None, (
            f"{scenario_id}/{tech}: cost_result is None")
        assert r.cost_result.capex_total > 0, (
            f"{scenario_id}/{tech}: CAPEX = 0")
        assert r.cost_result.opex_annual > 0, (
            f"{scenario_id}/{tech}: OPEX = 0")

    @pytest.mark.parametrize("scenario_id,tech", [
        (s.id, tech)
        for s in SCENARIOS
        for tech in s.technologies
    ])
    def test_produces_positive_energy(self, scenario_id, tech, base_assumptions):
        m = _metrics(scenario_id, tech, base_assumptions)
        assert m["kwh_ml"] > 0, (
            f"{scenario_id}/{tech}: energy = 0 kWh/ML")

    @pytest.mark.parametrize("scenario_id,tech", [
        (s.id, tech)
        for s in SCENARIOS
        for tech in s.technologies
    ])
    def test_validation_passes(self, scenario_id, tech, base_assumptions):
        """All well-defined scenarios must produce valid results."""
        r = _run(scenario_id, tech, base_assumptions)
        assert r.is_valid, (
            f"{scenario_id}/{tech}: is_valid=False — "
            f"messages={getattr(r.validation_result, 'messages', [])[:3]}")


# ─────────────────────────────────────────────────────────────────────────────
# RANGE TESTS — parametrised over scenarios × technologies × metrics
# ─────────────────────────────────────────────────────────────────────────────

def _range_cases():
    """
    Generate (scenario_id, tech, metric, range_obj) tuples for all
    explicitly-defined expected ranges.
    """
    cases = []
    for s in SCENARIOS:
        for tech, metrics in s.expected.items():
            for metric, rng in metrics.items():
                cases.append(
                    pytest.param(
                        s.id, tech, metric, rng,
                        id=f"{s.id}-{tech}-{metric}",
                    )
                )
    return cases


class TestRanges:
    """
    Checks every defined expected range.

    A failure here means an output drifted outside its tolerance band.
    The test ID tells you exactly which scenario, technology, and metric failed.

    Tolerance tiers (defined in scenarios.py):
      tight    (±10%) — effluent quality, mass-balance quantities
      moderate (±30%) — CAPEX, OPEX, LCC, energy, sludge
      wide     (±55%) — carbon, footprint
    """

    @pytest.mark.parametrize("scenario_id,tech,metric,expected_range", _range_cases())
    def test_output_within_range(
        self, scenario_id, tech, metric, expected_range, base_assumptions
    ):
        m = _metrics(scenario_id, tech, base_assumptions)

        assert metric in m, (
            f"{scenario_id}/{tech}: metric '{metric}' not found in output dict. "
            f"Available: {list(m.keys())}")

        value = m[metric]
        assert expected_range.passes(value), (
            f"\n"
            f"  Scenario : {scenario_id}\n"
            f"  Tech     : {tech}\n"
            f"  Metric   : {metric}  [{expected_range.tier} tolerance]\n"
            f"  Got      : {value:.3g}\n"
            f"  Expected : {expected_range}\n"
            f"  Ref      : {expected_range.ref}\n"
            f"\n"
            f"  This may indicate a code change drifted the calculation.\n"
            f"  Check recent changes to: costing_engine, {tech}.py, domain_interface."
        )


# ─────────────────────────────────────────────────────────────────────────────
# BEHAVIOURAL TESTS — engineering relationships that must hold
# ─────────────────────────────────────────────────────────────────────────────

class TestBehaviour:
    """
    Checks that expected engineering relationships hold across scenarios.

    These tests verify *direction* of change, not absolute values.
    They fail when a physical relationship was broken by a code change:
    e.g. cold temperature no longer penalises AGS energy.

    Each test documents the physical principle it encodes.
    """

    # ── B1: Cold climate — AGS energy increases ───────────────────────────────

    def test_cold_ags_energy_increases(self, base_assumptions):
        """
        AGS applies explicit cold-temperature energy penalties.
        At 12°C vs 20°C: aeration power increases due to slower kinetics,
        longer cycle times, and higher required DO.
        Ref: van Dijk 2020 — granule stability and energy at low T.
        """
        a = base_assumptions
        iface = WastewaterDomainInterface(a)
        base_inp = dict(design_flow_mld=8, influent_bod_mg_l=220,
                        influent_tkn_mg_l=48, influent_nh4_mg_l=38)

        r_warm = iface.run_scenario(WastewaterInputs(**base_inp,
            influent_temperature_celsius=20), ["granular_sludge"], {})
        r_cold = iface.run_scenario(WastewaterInputs(**base_inp,
            influent_temperature_celsius=12), ["granular_sludge"], {})

        kwh_warm = extract_metrics(r_warm, "granular_sludge")["kwh_ml"]
        kwh_cold = extract_metrics(r_cold, "granular_sludge")["kwh_ml"]

        assert kwh_cold > kwh_warm, (
            f"Cold AGS energy ({kwh_cold:.0f} kWh/ML) must exceed "
            f"warm AGS energy ({kwh_warm:.0f} kWh/ML). "
            f"Cold-temperature energy penalty in granular_sludge.py may have been removed."
        )

    # ── B2: Cold climate — BNR reactor volume increases ───────────────────────

    def test_cold_bnr_reactor_volume_increases(self, base_assumptions):
        """
        At cold temperatures BNR must extend SRT to maintain nitrification,
        producing a larger bioreactor volume.
        Ref: Metcalf & Eddy Fig 7-42 — SRT vs temperature for nitrification.
        """
        a = base_assumptions
        iface = WastewaterDomainInterface(a)
        base_inp = dict(design_flow_mld=8, influent_bod_mg_l=220,
                        influent_tkn_mg_l=48, influent_nh4_mg_l=38)

        r_warm = iface.run_scenario(WastewaterInputs(**base_inp,
            influent_temperature_celsius=20), ["bnr"], {})
        r_cold = iface.run_scenario(WastewaterInputs(**base_inp,
            influent_temperature_celsius=12), ["bnr"], {})

        vol_warm = extract_metrics(r_warm, "bnr")["reactor_m3"]
        vol_cold = extract_metrics(r_cold, "bnr")["reactor_m3"]

        assert vol_cold > vol_warm, (
            f"Cold BNR reactor ({vol_cold:.0f} m³) must exceed "
            f"warm BNR reactor ({vol_warm:.0f} m³). "
            f"Cold SRT extension in bnr.py may have been removed."
        )

    # ── B3: Cold climate — BNR effluent NH4 increases ─────────────────────────

    def test_cold_bnr_effluent_nh4_increases(self, base_assumptions):
        """
        Below 15°C nitrification rate drops. At 12°C the model applies
        a ×4 penalty on achievable effluent NH4.
        Ref: Metcalf & Eddy Eq. 7-98 — temperature correction for nitrification.
        """
        a = base_assumptions
        iface = WastewaterDomainInterface(a)
        base_inp = dict(design_flow_mld=8, influent_bod_mg_l=220,
                        influent_tkn_mg_l=48, influent_nh4_mg_l=38)

        r_warm = iface.run_scenario(WastewaterInputs(**base_inp,
            influent_temperature_celsius=20), ["bnr"], {})
        r_cold = iface.run_scenario(WastewaterInputs(**base_inp,
            influent_temperature_celsius=12), ["bnr"], {})

        nh4_warm = extract_metrics(r_warm, "bnr")["eff_nh4"]
        nh4_cold = extract_metrics(r_cold, "bnr")["eff_nh4"]

        assert nh4_cold > nh4_warm, (
            f"Cold BNR effluent NH4 ({nh4_cold:.1f} mg/L) must exceed "
            f"warm ({nh4_warm:.1f} mg/L). "
            f"Temperature NH4 penalty in bnr.py may have been removed."
        )

    # ── B4: Cold climate — risk score increases ────────────────────────────────

    def test_cold_increases_risk_score(self, base_assumptions):
        """
        Operating at 12°C increases operational risk for biological processes
        (nitrification impairment). Risk module must respond to scenario temperature.
        """
        a = base_assumptions
        iface = WastewaterDomainInterface(a)
        base_inp = dict(design_flow_mld=10, influent_bod_mg_l=250,
                        influent_tkn_mg_l=45)

        r_warm = iface.run_scenario(WastewaterInputs(**base_inp,
            influent_temperature_celsius=22), ["bnr"], {})
        r_cold = iface.run_scenario(WastewaterInputs(**base_inp,
            influent_temperature_celsius=12), ["bnr"], {})

        risk_warm = extract_metrics(r_warm, "bnr")["risk_score"]
        risk_cold = extract_metrics(r_cold, "bnr")["risk_score"]

        assert risk_cold > risk_warm, (
            f"Cold BNR risk ({risk_cold:.1f}) must exceed "
            f"warm risk ({risk_warm:.1f}). "
            f"Temperature risk modifier in risk_items.py may have been removed."
        )

    # ── B5: Carbon-limited — effluent TN exceeds target ───────────────────────

    def test_carbon_limited_tn_exceeds_target(self, base_assumptions):
        """
        When COD/TKN < 7, biological denitrification is carbon-limited.
        The model must compute effluent TN > the target 10 mg/L.
        S5: BOD=120, TKN=45 → COD/TKN ≈ 5.3 (threshold: 7.0).
        Ref: Metcalf & Eddy Table 7-32 — carbon requirements for denitrification.
        """
        s5 = get_by_id("S5")
        r = run_scenario_tech(s5, "bnr", base_assumptions)
        eff_tn = extract_metrics(r, "bnr")["eff_tn"]

        assert eff_tn > 12.0, (
            f"Carbon-limited BNR TN = {eff_tn:.1f} mg/L, expected > 12 mg/L. "
            f"COD/TKN = {s5.influent_bod_mg_l*2/s5.influent_tkn_mg_l:.1f} (threshold 7.0). "
            f"Carbon-limited denitrification logic in bnr.py may have been removed."
        )

    def test_carbon_limited_ifas_worse_than_bnr(self, base_assumptions):
        """
        IFAS has a limited dedicated anoxic zone, so it should achieve
        even worse TN removal than BNR under carbon-limited conditions.
        """
        s5 = get_by_id("S5")
        r_bnr  = run_scenario_tech(s5, "bnr",       base_assumptions)
        r_ifas = run_scenario_tech(s5, "ifas_mbbr",  base_assumptions)

        tn_bnr  = extract_metrics(r_bnr,  "bnr")["eff_tn"]
        tn_ifas = extract_metrics(r_ifas, "ifas_mbbr")["eff_tn"]

        assert tn_ifas >= tn_bnr, (
            f"IFAS TN ({tn_ifas:.1f}) must be >= BNR TN ({tn_bnr:.1f}) "
            f"under carbon-limited conditions. "
            f"IFAS carbon-limited logic in ifas_mbbr.py may have changed."
        )

    # ── B6: AGS footprint < BNR footprint (no secondary clarifiers) ──────────

    def test_ags_footprint_less_than_bnr(self, base_assumptions):
        """
        AGS SBR reactors require no secondary clarifiers, giving a
        material footprint saving vs BNR (typically 30-40%).
        Ref: Pronk 2015 — Nereda full-scale footprint comparison.
        """
        a = base_assumptions
        iface = WastewaterDomainInterface(a)
        inp = WastewaterInputs(design_flow_mld=20, influent_bod_mg_l=240,
                               influent_tkn_mg_l=42, influent_temperature_celsius=19)

        r_bnr = iface.run_scenario(inp, ["bnr"],             {})
        r_ags = iface.run_scenario(inp, ["granular_sludge"], {})

        fp_bnr = extract_metrics(r_bnr, "bnr")["footprint_m2"]
        fp_ags = extract_metrics(r_ags, "granular_sludge")["footprint_m2"]

        assert fp_ags < fp_bnr, (
            f"AGS footprint ({fp_ags:.0f} m²) must be less than "
            f"BNR footprint ({fp_bnr:.0f} m²). "
            f"Footprint calculation in granular_sludge.py or bnr.py may have changed."
        )

    # ── B7: MABR energy < BNR energy ─────────────────────────────────────────

    def test_mabr_energy_less_than_bnr(self, base_assumptions):
        """
        MABR delivers oxygen directly to biofilm, avoiding N2 dilution and
        operating at lower aeration energy than conventional activated sludge.
        Literature: 15-25% energy saving vs equivalent BNR.
        Ref: GE/Ovivo 2017, Syron & Casey 2008.
        """
        a = base_assumptions
        iface = WastewaterDomainInterface(a)
        inp = WastewaterInputs(design_flow_mld=12, influent_bod_mg_l=260,
                               influent_tkn_mg_l=46, influent_temperature_celsius=20)

        r_bnr  = iface.run_scenario(inp, ["bnr"],      {})
        r_mabr = iface.run_scenario(inp, ["mabr_bnr"], {})

        kwh_bnr  = extract_metrics(r_bnr,  "bnr")["kwh_ml"]
        kwh_mabr = extract_metrics(r_mabr, "mabr_bnr")["kwh_ml"]

        assert kwh_mabr < kwh_bnr, (
            f"MABR energy ({kwh_mabr:.0f} kWh/ML) must be less than "
            f"BNR energy ({kwh_bnr:.0f} kWh/ML). "
            f"MABR aeration model in mabr_bnr.py may have changed."
        )

    # ── B8: High sludge disposal → AGS LCC < BNR LCC ─────────────────────────

    def test_high_sludge_cost_advantages_ags(self, base_assumptions):
        """
        At $450/t DS (vs base $280), AGS lower sludge yield (~15% less)
        produces a materially lower lifecycle cost than BNR.
        This tests that LCC correctly reflects sludge quantity × disposal rate.
        """
        s7 = get_by_id("S7")
        r_bnr = run_scenario_tech(s7, "bnr",             base_assumptions)
        r_ags = run_scenario_tech(s7, "granular_sludge",  base_assumptions)

        lcc_bnr = r_bnr.cost_result.lifecycle_cost_annual
        lcc_ags = r_ags.cost_result.lifecycle_cost_annual

        assert lcc_ags < lcc_bnr, (
            f"At ${s7.sludge_disposal_per_tds:.0f}/t DS, "
            f"AGS LCC (${lcc_ags/1e3:.0f}k) must be less than "
            f"BNR LCC (${lcc_bnr/1e3:.0f}k). "
            f"Sludge disposal OPEX or LCC calculation may have changed."
        )

    # ── B9: AGS sludge production < BNR (same scenario) ─────────────────────

    def test_ags_lower_sludge_than_bnr(self, base_assumptions):
        """
        AGS operates at longer SRT (higher endogenous decay), producing
        approximately 15-20% less sludge per kg BOD removed than BNR.
        Ref: de Kreuk 2007, Pronk 2015.
        """
        s7 = get_by_id("S7")
        r_bnr = run_scenario_tech(s7, "bnr",            base_assumptions)
        r_ags = run_scenario_tech(s7, "granular_sludge", base_assumptions)

        slg_bnr = extract_metrics(r_bnr, "bnr")["sludge"]
        slg_ags = extract_metrics(r_ags, "granular_sludge")["sludge"]

        assert slg_ags < slg_bnr, (
            f"AGS sludge ({slg_ags:.0f} kgDS/d) must be less than "
            f"BNR sludge ({slg_bnr:.0f} kgDS/d). "
            f"AGS sludge yield in granular_sludge.py may have changed."
        )

    # ── B10: MBR achieves TSS < 1 mg/L (reuse quality) ───────────────────────

    def test_mbr_achieves_reuse_tss(self, base_assumptions):
        """
        MBR membrane retains all TSS by size exclusion — effluent TSS < 1 mg/L
        regardless of mixed-liquor TSS. This is a fundamental characteristic
        of membrane bioreactors used in potable reuse pathways.
        """
        s8 = get_by_id("S8")
        r = run_scenario_tech(s8, "bnr_mbr", base_assumptions)
        eff_tss = extract_metrics(r, "bnr_mbr")["eff_tss"]

        assert eff_tss < 2.0, (
            f"MBR effluent TSS = {eff_tss:.1f} mg/L; must be < 2 mg/L. "
            f"MBR TSS model in bnr_mbr.py or mbr.py may have changed."
        )

    # ── B11: Technology risk ordering (BNR < AGS < MABR) ─────────────────────

    def test_technology_risk_ordering(self, base_assumptions):
        """
        Risk scores must follow technology maturity: BNR (>5000 plants,
        lowest risk) < AGS (~200 full-scale, 2024) < MABR (<50 full-scale).
        Ref: IWA 2022 technology maturity review.
        """
        a = base_assumptions
        iface = WastewaterDomainInterface(a)
        inp = WastewaterInputs(design_flow_mld=10, influent_bod_mg_l=250,
                               influent_tkn_mg_l=45)

        scores = {}
        for tech in ["bnr", "granular_sludge", "mabr_bnr"]:
            r = iface.run_scenario(inp, [tech], {})
            scores[tech] = r.risk_result.overall_score

        assert scores["bnr"] < scores["granular_sludge"], (
            f"BNR risk ({scores['bnr']:.1f}) must be < AGS risk "
            f"({scores['granular_sludge']:.1f})"
        )
        assert scores["bnr"] < scores["mabr_bnr"], (
            f"BNR risk ({scores['bnr']:.1f}) must be < MABR risk "
            f"({scores['mabr_bnr']:.1f})"
        )

    # ── B12: Economy of scale — CAPEX/MLD decreases with flow ────────────────

    def test_economy_of_scale(self, base_assumptions):
        """
        Six-Tenths Rule applied to civil tankage: cost per MLD must decrease
        as plant size grows from 5 MLD to 50 MLD.
        Cost(V2)/Cost(V1) = (V2/V1)^0.6
        Ref: WEF Cost Estimating Manual 2018, Section 3.
        """
        a = base_assumptions
        iface = WastewaterDomainInterface(a)
        inp_5  = WastewaterInputs(design_flow_mld=5,  influent_bod_mg_l=250,
                                   influent_tkn_mg_l=45)
        inp_50 = WastewaterInputs(design_flow_mld=50, influent_bod_mg_l=250,
                                   influent_tkn_mg_l=45)

        r5  = iface.run_scenario(inp_5,  ["bnr"], {})
        r50 = iface.run_scenario(inp_50, ["bnr"], {})

        unit_5  = r5.cost_result.capex_total  / 5
        unit_50 = r50.cost_result.capex_total / 50

        assert unit_50 < unit_5, (
            f"CAPEX/MLD at 50 MLD (${unit_50/1e6:.2f}M) must be less than "
            f"at 5 MLD (${unit_5/1e6:.2f}M). "
            f"Six-Tenths Rule in costing_engine.py may have changed."
        )

    # ── B13: Electricity sensitivity — higher price lifts OPEX ───────────────

    def test_electricity_price_lifts_opex(self, base_assumptions):
        """
        Doubling electricity price must materially increase OPEX.
        S6 uses $0.22/kWh vs base $0.14/kWh — OPEX must be higher
        than an equivalent scenario at base electricity price.
        """
        a_base = copy.deepcopy(base_assumptions)
        a_high = copy.deepcopy(base_assumptions)
        a_high.cost_assumptions["opex_unit_rates"]["electricity_per_kwh"] = 0.22

        s6 = get_by_id("S6")
        inp = WastewaterInputs(**to_inputs_dict(s6))

        r_base = WastewaterDomainInterface(a_base).run_scenario(inp, ["bnr"], {})
        r_high = WastewaterDomainInterface(a_high).run_scenario(inp, ["bnr"], {})

        assert r_high.cost_result.opex_annual > r_base.cost_result.opex_annual, (
            f"High electricity OPEX (${r_high.cost_result.opex_annual/1e3:.0f}k) "
            f"must exceed base OPEX (${r_base.cost_result.opex_annual/1e3:.0f}k)."
        )


# ─────────────────────────────────────────────────────────────────────────────
# LIFECYCLE COST INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────

class TestLifecycleCostIntegrity:
    """
    Verifies the LCC calculation formula is correct.
    LCC_annual = CAPEX × CRF(i, n) + OPEX_annual
    where CRF = i(1+i)^n / ((1+i)^n - 1)
    """

    @pytest.mark.parametrize("scenario_id,tech", [
        ("S1", "bnr"),
        ("S1", "granular_sludge"),
        ("S4", "bnr_mbr"),
        ("S7", "bnr"),
        ("S8", "bnr_mbr"),
    ])
    def test_lcc_equals_capex_crf_plus_opex(self, scenario_id, tech, base_assumptions):
        r  = _run(scenario_id, tech, base_assumptions)
        cr = r.cost_result

        i   = cr.discount_rate
        n   = cr.analysis_period_years
        crf = i * (1 + i) ** n / ((1 + i) ** n - 1)
        expected_lcc = cr.capex_total * crf + cr.opex_annual

        assert abs(cr.lifecycle_cost_annual - expected_lcc) / expected_lcc < 0.01, (
            f"{scenario_id}/{tech}: LCC = ${cr.lifecycle_cost_annual/1e3:.0f}k "
            f"but CAPEX×CRF+OPEX = ${expected_lcc/1e3:.0f}k. "
            f"CRF calculation in costing_engine.py may have changed."
        )


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE ENTRY POINT
# When run directly (python3 test_benchmark_regression.py), delegates to the
# standalone runner which works without pytest installed.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import subprocess
    import sys
    from pathlib import Path
    runner = Path(__file__).parent / "run_benchmarks.py"
    result = subprocess.run([sys.executable, str(runner)] + sys.argv[1:])
    sys.exit(result.returncode)
