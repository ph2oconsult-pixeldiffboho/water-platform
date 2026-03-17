"""
tests/domains/wastewater/test_benchmark_scenarios.py

BENCHMARK REGRESSION TEST SUITE
================================
Runs all 8 benchmark scenarios and verifies outputs fall within
defined engineering credibility ranges.

Run with: python3 tests/domains/wastewater/test_benchmark_scenarios.py
(or: pytest tests/domains/wastewater/test_benchmark_scenarios.py -v)

PASS criteria: all outputs within ±40% concept-level ranges.
FAIL criteria: output outside range, zero output, or crash.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.assumptions.assumptions_manager import AssumptionsManager
from core.project.project_model import DomainType
from domains.wastewater.domain_interface import WastewaterDomainInterface
from domains.wastewater.input_model import WastewaterInputs
from tests.domains.wastewater.benchmark_scenarios import (
    BENCHMARK_SCENARIOS, scenario_to_inputs_dict, ExpectedRange
)


def run_benchmark_scenario(scenario, iface, assumptions):
    """Run one scenario across all technologies and check expected ranges."""
    inp_kw = scenario_to_inputs_dict(scenario)
    inp = WastewaterInputs(**inp_kw)

    # Apply economic overrides
    import copy
    a_mod = copy.deepcopy(assumptions)
    if scenario.electricity_price_per_kwh != 0.14:
        a_mod.cost_assumptions["opex_unit_rates"]["electricity_per_kwh"] = scenario.electricity_price_per_kwh
    if scenario.sludge_disposal_per_tds != 280.0:
        a_mod.cost_assumptions["opex_unit_rates"]["sludge_disposal_per_tds"] = scenario.sludge_disposal_per_tds
    if scenario.carbon_price_per_tco2e != 35.0:
        a_mod.carbon_assumptions["carbon_price_per_tonne_co2e"] = scenario.carbon_price_per_tco2e
    if scenario.discount_rate != 0.07:
        a_mod.cost_assumptions["discount_rate"] = scenario.discount_rate

    iface_mod = WastewaterDomainInterface(a_mod)

    results = {}
    failures = []
    passes = []

    for tech_code in scenario.technologies:
        try:
            r = iface_mod.run_scenario(inp, [tech_code], {})
            eng  = r.to_domain_outputs_dict()["engineering_summary"]
            tp   = r.to_domain_outputs_dict()["technology_performance"].get(tech_code, {})
            cr   = r.cost_result
            car  = r.carbon_result

            actual = {
                "capex_m":    cr.capex_total / 1e6,
                "opex_k":     cr.opex_annual / 1e3,
                "lcc_k":      cr.lifecycle_cost_annual / 1e3,
                "cost_kl":    cr.specific_cost_per_kl or 0,
                "kwh_ml":     (eng.get("specific_energy_kwh_kl", 0) or 0) * 1000,
                "sludge":     eng.get("total_sludge_kgds_day", 0) or 0,
                "net_co2":    car.net_tco2e_yr if car else 0,
                "footprint_m2": tp.get("footprint_m2", 0) or 0,
                "reactor_m3": tp.get("reactor_volume_m3", 0) or 0,
                "eff_bod":    tp.get("effluent_bod_mg_l", 0) or 0,
                "eff_tss":    tp.get("effluent_tss_mg_l", 0) or 0,
                "eff_tn":     tp.get("effluent_tn_mg_l", 0) or 0,
                "eff_nh4":    float(tp.get("effluent_nh4_mg_l", 0) or 0),
                "eff_tp":     tp.get("effluent_tp_mg_l", 0) or 0,
                "kwh_kg_nh4": tp.get("kwh_per_kg_nh4_removed", 0) or 0,
            }
            results[tech_code] = actual

            # Check expected ranges if defined
            expected_for_tech = scenario.expected.get(tech_code, {})
            for metric, expected_range in expected_for_tech.items():
                value = actual.get(metric, None)
                if value is None:
                    failures.append(f"{scenario.id}/{tech_code}/{metric}: metric not found in output")
                    continue
                if not expected_range.check(value):
                    failures.append(
                        f"{scenario.id}/{tech_code}/{metric}: "
                        f"got {value:.2f}, expected {expected_range.fmt()} "
                        f"[{expected_range.ref}]"
                    )
                else:
                    passes.append(f"{scenario.id}/{tech_code}/{metric}: {value:.2f} ✓")

        except Exception as e:
            failures.append(f"{scenario.id}/{tech_code}: CRASH — {e}")
            import traceback
            traceback.print_exc()

    return results, passes, failures


def run_all_benchmarks(verbose: bool = True) -> tuple:
    """Run all 8 benchmark scenarios. Returns (passes, failures, results)."""
    a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)
    iface = WastewaterDomainInterface(a)

    all_passes = []
    all_failures = []
    all_results = {}

    for scenario in BENCHMARK_SCENARIOS:
        if verbose:
            print(f"\n{'─'*60}")
            print(f"  {scenario.id}: {scenario.name}")
            print(f"  {scenario.design_flow_mld} MLD | {scenario.influent_temperature_celsius}°C | "
                  f"BOD={scenario.influent_bod_mg_l} | TKN={scenario.influent_tkn_mg_l} | "
                  f"techs={scenario.technologies}")
            print(f"{'─'*60}")

        results, passes, failures = run_benchmark_scenario(scenario, iface, a)
        all_passes.extend(passes)
        all_failures.extend(failures)
        all_results[scenario.id] = results

        if verbose:
            # Print summary table for this scenario
            print(f"  {'Tech':<20} {'CAPEX$M':>8} {'OPEX k$':>8} {'LCC k$':>8} "
                  f"{'kWh/ML':>8} {'Sludge':>8} {'CO2 t/yr':>10} {'TN mg/L':>8}")
            print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*10} {'─'*8}")
            for tech_code, act in results.items():
                status = "❌" if any(f"{scenario.id}/{tech_code}/" in f for f in failures) else "✅"
                print(
                    f"  {status} {tech_code:<18} "
                    f"{act['capex_m']:>8.1f} {act['opex_k']:>8.0f} {act['lcc_k']:>8.0f} "
                    f"{act['kwh_ml']:>8.0f} {act['sludge']:>8.0f} {act['net_co2']:>10.0f} "
                    f"{act['eff_tn']:>8.1f}"
                )

            if failures:
                scen_fails = [f for f in failures if f.startswith(scenario.id)]
                for fail in scen_fails:
                    print(f"  ❌ FAIL: {fail}")

    return all_passes, all_failures, all_results


def print_summary(passes, failures):
    total = len(passes) + len(failures)
    print(f"\n{'='*60}")
    print(f"BENCHMARK REGRESSION RESULTS")
    print(f"{'='*60}")
    print(f"  Checks run:   {total}")
    print(f"  Passed:       {len(passes)}")
    print(f"  Failed:       {len(failures)}")
    print(f"  Pass rate:    {len(passes)/max(total,1)*100:.0f}%")
    if failures:
        print(f"\n  FAILURES:")
        for f in failures:
            print(f"    ❌ {f}")
    else:
        print(f"\n  ✅ ALL BENCHMARK CHECKS PASSED")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Run only this scenario ID (e.g. S1)")
    args = parser.parse_args()

    a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)
    iface = WastewaterDomainInterface(a)

    scenarios = BENCHMARK_SCENARIOS
    if args.scenario:
        scenarios = [s for s in BENCHMARK_SCENARIOS if s.id == args.scenario]
        if not scenarios:
            print(f"Unknown scenario: {args.scenario}")
            sys.exit(1)

    all_p, all_f, _ = [], [], {}
    for scen in scenarios:
        results, p, f = run_benchmark_scenario(scen, iface, a)
        all_p.extend(p); all_f.extend(f)

        if not args.quiet:
            print(f"\n{scen.id}: {scen.name}")
            for code, act in results.items():
                status = "❌" if any(f"{scen.id}/{code}/" in x for x in f) else "✅"
                print(f"  {status} {code}: CAPEX=${act['capex_m']:.1f}M  OPEX=${act['opex_k']:.0f}k  "
                      f"{act['kwh_ml']:.0f} kWh/ML  TN={act['eff_tn']:.1f}mg/L  "
                      f"CO2={act['net_co2']:.0f}t")
            for fail in [x for x in f if x.startswith(scen.id)]:
                print(f"  ❌ {fail}")

    print_summary(all_p, all_f)
    sys.exit(0 if not all_f else 1)
