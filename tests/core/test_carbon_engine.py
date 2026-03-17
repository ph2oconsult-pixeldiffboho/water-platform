"""
tests/core/test_carbon_engine.py

Unit tests for CarbonEngine. Standalone — no pytest required.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.project.project_model import DomainType
from core.carbon.carbon_engine import CarbonEngine
from core.assumptions.assumptions_manager import AssumptionsManager

_p = _f = 0
_err = []

def chk(name, cond, detail=""):
    global _p, _f
    if cond: _p += 1; print(f"  ✅ {name}")
    else:
        _f += 1; _err.append(name)
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

def approx(a, b, rel=0.05):
    return abs(a - b) / max(abs(b), 1e-10) < rel

def engine():
    return CarbonEngine(AssumptionsManager().load_defaults(DomainType.WASTEWATER))

def test_zero_inputs_returns_zero_emissions():
    r = engine().calculate(energy_kwh_per_day=0, chemical_consumption={})
    chk("zero inputs → net_tco2e_yr == 0", r.net_tco2e_yr == 0.0, f"got {r.net_tco2e_yr}")

def test_electricity_scope2_correct():
    # 1000 kWh/day × 0.79 kg/kWh × 365 / 1000 = 288.35 tCO2e/yr
    r = engine().calculate(energy_kwh_per_day=1000.0, chemical_consumption={})
    expected = 1000.0 * 0.79 * 365 / 1000
    chk("1000 kWh/d Scope2 ≈ 288.35 tCO2e/yr",
        approx(r.scope_2_tco2e_yr, expected, 0.01),
        f"got {r.scope_2_tco2e_yr:.2f} expected {expected:.2f}")

def test_chemical_emissions_sodium_hypochlorite():
    r = engine().calculate(energy_kwh_per_day=0,
                           chemical_consumption={"sodium_hypochlorite": 100.0})
    # 100 kg/day × 2.10 kg CO2e/kg × 365 / 1000 = 76.65 tCO2e/yr
    expected = 100.0 * 2.10 * 365 / 1000
    chk("NaOCl Scope3 ≈ 76.65 tCO2e/yr",
        approx(r.scope_3_tco2e_yr, expected, 0.05),
        f"got {r.scope_3_tco2e_yr:.2f} expected {expected:.2f}")

def test_avoided_reduces_net():
    no_av = engine().calculate(energy_kwh_per_day=1000.0, chemical_consumption={})
    with_av = engine().calculate(energy_kwh_per_day=1000.0, chemical_consumption={},
                                  avoided_kwh_per_day=200.0)
    chk("avoided emissions reduces net carbon",
        with_av.net_tco2e_yr < no_av.net_tco2e_yr,
        f"with={with_av.net_tco2e_yr:.2f} no_av={no_av.net_tco2e_yr:.2f}")

def test_specific_intensity_calculated():
    r = engine().calculate(energy_kwh_per_day=500.0, chemical_consumption={},
                            design_flow_mld=10.0)
    chk("specific intensity calculated",
        r.specific_kg_co2e_per_kl is not None and r.specific_kg_co2e_per_kl > 0,
        f"got {r.specific_kg_co2e_per_kl}")

def test_net_is_scope1_plus_scope2_plus_scope3_minus_avoided():
    r = engine().calculate(energy_kwh_per_day=1000.0,
                            chemical_consumption={"sodium_hypochlorite": 50.0},
                            avoided_kwh_per_day=100.0,
                            domain_specific_emissions={"n2o": 50.0})
    expected_net = (r.scope_1_tco2e_yr + r.scope_2_tco2e_yr
                    + r.scope_3_tco2e_yr - r.avoided_tco2e_yr)
    chk("net = scope1+2+3 - avoided",
        approx(r.net_tco2e_yr, expected_net, 0.001),
        f"net={r.net_tco2e_yr:.2f} computed={expected_net:.2f}")

def test_grid_emission_factor_stored():
    r = engine().calculate(energy_kwh_per_day=1000.0, chemical_consumption={})
    chk("grid emission factor stored and positive",
        r.grid_emission_factor_used is not None and r.grid_emission_factor_used > 0,
        f"got {r.grid_emission_factor_used}")

def main():
    print("=" * 55)
    print("  CARBON ENGINE TESTS")
    print("=" * 55)
    test_zero_inputs_returns_zero_emissions()
    test_electricity_scope2_correct()
    test_chemical_emissions_sodium_hypochlorite()
    test_avoided_reduces_net()
    test_specific_intensity_calculated()
    test_net_is_scope1_plus_scope2_plus_scope3_minus_avoided()
    test_grid_emission_factor_stored()
    print(f"\n  {_p} passed, {_f} failed")
    if _err: [print(f"  ❌ {e}") for e in _err]
    else: print("  ✅ ALL PASSED")
    return _f

if __name__ == "__main__":
    sys.exit(main())
