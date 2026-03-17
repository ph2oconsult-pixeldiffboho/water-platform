"""
tests/core/test_costing_engine.py

Unit tests for the shared CostingEngine.
Domain-agnostic. Runs standalone without pytest.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.project.project_model import CostItem, DomainType
from core.costing.costing_engine import CostingEngine
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
    return CostingEngine(AssumptionsManager().load_defaults(DomainType.WASTEWATER))

# ── Basic ─────────────────────────────────────────────────────────────────────

def test_empty_items_returns_zero_cost():
    r = engine().calculate(capex_items=[], opex_items=[], design_flow_mld=10.0)
    chk("empty → capex_total == 0",   r.capex_total  == 0.0, f"got {r.capex_total}")
    chk("empty → opex_annual == 0",   r.opex_annual  == 0.0,
        f"got {r.opex_annual}; bd={r.opex_breakdown}")

def test_capex_item_with_override():
    items = [CostItem("Test Tank", "some_key", 100.0, "m³", unit_cost_override=1000.0)]
    r = engine().calculate(capex_items=items, opex_items=[], design_flow_mld=10.0)
    chk("capex override > 100,000", r.capex_total > 100_000.0, f"got {r.capex_total:.0f}")
    chk("Test Tank in breakdown",   "Test Tank" in r.capex_breakdown)

def test_opex_item_with_override():
    """No CAPEX → no labour/maintenance. OPEX = exactly electricity × 365."""
    items = [CostItem("Electricity", "electricity_per_kwh", 1000.0, "kWh/day")]
    r = engine().calculate(capex_items=[], opex_items=items, design_flow_mld=10.0)
    expected = 1000.0 * 0.14 * 365  # 51,100
    chk("electricity ≈ $51,100 (no extras)", approx(r.opex_annual, expected, 0.05),
        f"got {r.opex_annual:.0f} expected {expected:.0f}")

def test_specific_cost_per_kl_calculated():
    items = [CostItem("OPEX", "x", 100.0, "unit/day", unit_cost_override=10.0)]
    r = engine().calculate(capex_items=[], opex_items=items, design_flow_mld=10.0)
    chk("specific_cost_per_kl not None", r.specific_cost_per_kl is not None)
    chk("specific_cost_per_kl > 0",     (r.specific_cost_per_kl or 0) > 0)

def test_analysis_period_affects_lifecycle_cost():
    cap = [CostItem("Asset", "x", 1.0, "lump", unit_cost_override=1_000_000.0)]
    r30 = engine().calculate(cap, [], design_flow_mld=10, analysis_period_years=30, apply_oncosts=False)
    r20 = engine().calculate(cap, [], design_flow_mld=10, analysis_period_years=20, apply_oncosts=False)
    chk("20yr LCC > 30yr LCC", r20.lifecycle_cost_annual > r30.lifecycle_cost_annual,
        f"20yr={r20.lifecycle_cost_annual:.0f} 30yr={r30.lifecycle_cost_annual:.0f}")

def test_currency_and_year_from_assumptions():
    r = engine().calculate([], [], design_flow_mld=5.0)
    chk("currency == AUD",         r.currency == "AUD",       f"got {r.currency!r}")
    chk("price_base_year == 2024", r.price_base_year == 2024, f"got {r.price_base_year}")

# ── Library lookup ────────────────────────────────────────────────────────────

def test_electricity_cost_looked_up_from_library():
    items = [CostItem("Power", "electricity_per_kwh", 500.0, "kWh/day")]
    r = engine().calculate([], items, design_flow_mld=5.0)
    expected = 500.0 * 0.14 * 365  # 25,550
    chk("electricity library lookup ≈ $25,550",
        approx(r.opex_annual, expected, 0.05),
        f"got {r.opex_annual:.0f} expected {expected:.0f}")

def test_unknown_cost_key_returns_zero():
    items = [CostItem("Unknown Widget", "nonexistent_key_xyz", 100.0, "unit")]
    r = engine().calculate(items, [], design_flow_mld=5.0)
    chk("unknown key → zero in breakdown",
        r.capex_breakdown.get("Unknown Widget", 0.0) == 0.0,
        f"got {r.capex_breakdown}")

# ── Fixed O&M guard ───────────────────────────────────────────────────────────

def test_real_scenario_includes_labour_and_maintenance():
    """Real scenario (tech_codes + capex > 0) MUST include labour and maintenance."""
    from domains.wastewater.technologies.bnr import BNRTechnology, BNRInputs
    a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)
    a.engineering_assumptions.update({
        "influent_bod_mg_l": 250, "influent_tkn_mg_l": 45,
        "influent_tn_mg_l": 45, "influent_nh4_mg_l": 35, "influent_tss_mg_l": 280,
    })
    bnr_r = BNRTechnology(a).calculate(10.0, BNRInputs())
    r = CostingEngine(a).calculate(
        capex_items=bnr_r.capex_items, opex_items=bnr_r.opex_items,
        design_flow_mld=10.0, tech_codes=["bnr"],
    )
    chk("real scenario: labour in OPEX",
        any("labour" in k.lower() for k in r.opex_breakdown),
        f"keys: {list(r.opex_breakdown)}")
    chk("real scenario: maintenance in OPEX",
        any("maintenance" in k.lower() for k in r.opex_breakdown),
        f"keys: {list(r.opex_breakdown)}")

def test_item_only_has_no_fixed_om():
    """Item-only call (no tech_codes, no capex) must NOT add fixed O&M."""
    items = [CostItem("Elec", "electricity_per_kwh", 500.0, "kWh/day")]
    r = engine().calculate(capex_items=[], opex_items=items, design_flow_mld=10.0)
    chk("item-only: no labour",
        not any("labour" in k.lower() for k in r.opex_breakdown),
        f"found: {[k for k in r.opex_breakdown if 'labour' in k.lower()]}")
    chk("item-only: no maintenance",
        not any("maintenance" in k.lower() for k in r.opex_breakdown),
        f"found: {[k for k in r.opex_breakdown if 'maintenance' in k.lower()]}")

# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  COSTING ENGINE TESTS")
    print("=" * 55)
    test_empty_items_returns_zero_cost()
    test_capex_item_with_override()
    test_opex_item_with_override()
    test_specific_cost_per_kl_calculated()
    test_analysis_period_affects_lifecycle_cost()
    test_currency_and_year_from_assumptions()
    test_electricity_cost_looked_up_from_library()
    test_unknown_cost_key_returns_zero()
    test_real_scenario_includes_labour_and_maintenance()
    test_item_only_has_no_fixed_om()
    print(f"\n  {_p} passed, {_f} failed")
    if _err: [print(f"  ❌ {e}") for e in _err]
    else: print("  ✅ ALL PASSED")
    return _f

if __name__ == "__main__":
    sys.exit(main())
