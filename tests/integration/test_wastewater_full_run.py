"""
tests/integration/test_wastewater_full_run.py

Integration tests: full scenario pipeline.
Standalone — no pytest required.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.project.project_model import DomainType, TreatmentPathway
from core.project.project_manager import ProjectManager
from core.assumptions.assumptions_manager import AssumptionsManager
from domains.wastewater.domain_interface import WastewaterDomainInterface
from domains.wastewater.input_model import WastewaterInputs

_p = _f = 0
_err = []

def chk(name, cond, detail=""):
    global _p, _f
    if cond: _p += 1; print(f"  ✅ {name}")
    else:
        _f += 1; _err.append(name)
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

def approx(a, b, rel=0.001):
    return abs(a - b) / max(abs(b), 1e-10) < rel

def _assumptions():
    return AssumptionsManager().load_defaults(DomainType.WASTEWATER)

def _standard_inputs():
    # Uses canonical field influent_tkn_mg_l (not influent_tn_mg_l)
    return WastewaterInputs(
        design_flow_mld=10.0,
        influent_bod_mg_l=250.0,
        influent_tkn_mg_l=45.0,
        influent_tp_mg_l=7.0,
        effluent_bod_mg_l=10.0,
        effluent_tn_mg_l=10.0,
        effluent_tp_mg_l=0.5,
    )

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_bnr_full_scenario_produces_all_results():
    a = _assumptions()
    r = WastewaterDomainInterface(a).run_scenario(
        _standard_inputs(), ["bnr"], {"bnr": {"srt_days": 12.0, "mlss_mg_l": 4000.0}}
    )
    chk("BNR is_valid",                   r.is_valid,          f"validation={r.validation_result}")
    chk("BNR cost_result not None",       r.cost_result is not None)
    chk("BNR carbon_result not None",     r.carbon_result is not None)
    chk("BNR risk_result not None",       r.risk_result is not None)
    chk("BNR validation_result not None", r.validation_result is not None)

def test_bnr_capex_in_reasonable_range_for_10mld():
    a = _assumptions()
    r = WastewaterDomainInterface(a).run_scenario(_standard_inputs(), ["bnr"], {"bnr": {}})
    capex = r.cost_result.capex_total
    chk("BNR CAPEX $5M–$150M",
        5_000_000 < capex < 150_000_000, f"got ${capex:,.0f}")

def test_mbr_full_scenario():
    a = _assumptions()
    r = WastewaterDomainInterface(a).run_scenario(
        _standard_inputs(), ["bnr_mbr"], {"bnr_mbr": {}}
    )
    chk("BNR+MBR is_valid",                    r.is_valid)
    chk("BNR+MBR capex_total > 0",             r.cost_result.capex_total > 0)
    chk("BNR+MBR net_tco2e_yr > 0",            r.carbon_result.net_tco2e_yr > 0)

def test_missing_design_flow_fails_validation():
    a = _assumptions()
    r = WastewaterDomainInterface(a).run_scenario(
        WastewaterInputs(design_flow_mld=None), ["bnr"], {}
    )
    chk("None flow → not valid",        not r.is_valid)
    chk("None flow → cost_result None", r.cost_result is None)

def test_invalid_effluent_target_fails_validation():
    a = _assumptions()
    bad = WastewaterInputs(
        design_flow_mld=10.0,
        influent_tkn_mg_l=10.0,   # canonical field name
        effluent_tn_mg_l=15.0,    # effluent > influent — impossible
    )
    r = WastewaterDomainInterface(a).run_scenario(bad, ["bnr"], {})
    chk("effluent TN > influent TKN → not valid", not r.is_valid)

def test_influent_tkn_drives_results():
    """influent_tkn_mg_l must propagate to technology calculations."""
    a = _assumptions()
    iface = WastewaterDomainInterface(a)
    lo = iface.run_scenario(
        WastewaterInputs(design_flow_mld=10, influent_tkn_mg_l=25, influent_nh4_mg_l=20,
                         influent_bod_mg_l=250), ["bnr"], {}
    )
    hi = iface.run_scenario(
        WastewaterInputs(design_flow_mld=10, influent_tkn_mg_l=65, influent_nh4_mg_l=50,
                         influent_bod_mg_l=250), ["bnr"], {}
    )
    kwh_lo = lo.to_domain_outputs_dict()["engineering_summary"]["specific_energy_kwh_kl"]
    kwh_hi = hi.to_domain_outputs_dict()["engineering_summary"]["specific_energy_kwh_kl"]
    chk("higher TKN → higher energy", kwh_hi > kwh_lo,
        f"lo={kwh_lo*1000:.0f} hi={kwh_hi*1000:.0f} kWh/ML")

def test_project_round_trip_with_results():
    """Full save/load cycle preserving calculation results."""
    import tempfile, os
    a = _assumptions()
    std = _standard_inputs()

    with tempfile.TemporaryDirectory() as tmp:
        pm = ProjectManager(storage_path=Path(tmp))
        project = pm.create_project(
            project_name="Test WWTP", domain=DomainType.WASTEWATER,
            plant_name="Test Plant", author="Test Engineer",
        )
        scenario = project.get_active_scenario()
        scenario.domain_inputs = {
            k: getattr(std, k)
            for k in std.__dataclass_fields__ if not k.startswith("_")
        }
        scenario.design_flow_mld = std.design_flow_mld
        scenario.assumptions = a
        scenario.treatment_pathway = TreatmentPathway(
            pathway_name="BNR", technology_sequence=["bnr"],
            technology_parameters={"bnr": {}},
        )
        iface = WastewaterDomainInterface(a)
        calc  = iface.run_scenario(std, ["bnr"], {"bnr": {}})
        iface.update_scenario_model(scenario, calc)

        pm.save(project)
        loaded = pm.load(project.metadata.project_id)
        loaded_s = loaded.get_active_scenario()

        chk("round-trip: cost_result not None",  loaded_s.cost_result is not None)
        chk("round-trip: CAPEX matches",
            approx(loaded_s.cost_result.capex_total, scenario.cost_result.capex_total),
            f"saved={scenario.cost_result.capex_total:.0f} "
            f"loaded={loaded_s.cost_result.capex_total:.0f}")
        chk("round-trip: not stale",             not loaded_s.is_stale)

# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  INTEGRATION TESTS — FULL PIPELINE")
    print("=" * 55)
    test_bnr_full_scenario_produces_all_results()
    test_bnr_capex_in_reasonable_range_for_10mld()
    test_mbr_full_scenario()
    test_missing_design_flow_fails_validation()
    test_invalid_effluent_target_fails_validation()
    test_influent_tkn_drives_results()
    test_project_round_trip_with_results()
    print(f"\n  {_p} passed, {_f} failed")
    if _err: [print(f"  ❌ {e}") for e in _err]
    else: print("  ✅ ALL PASSED")
    return _f

if __name__ == "__main__":
    sys.exit(main())
