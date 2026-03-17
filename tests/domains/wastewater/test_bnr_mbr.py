"""
tests/domains/wastewater/test_bnr_mbr.py

Unit tests for BNR and MBR technology plugins.
Standalone — no pytest required.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.project.project_model import DomainType
from core.assumptions.assumptions_manager import AssumptionsManager
from domains.wastewater.technologies.bnr import BNRTechnology, BNRInputs

_p = _f = 0
_err = []

def chk(name, cond, detail=""):
    global _p, _f
    if cond: _p += 1; print(f"  ✅ {name}")
    else:
        _f += 1; _err.append(name)
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

def _assumptions():
    a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)
    a.engineering_assumptions.update({
        "influent_bod_mg_l": 250, "influent_tkn_mg_l": 45,
        "influent_tn_mg_l": 45, "influent_nh4_mg_l": 35,
        "influent_tss_mg_l": 280, "influent_tp_mg_l": 7,
        "effluent_tn_mg_l": 10, "effluent_nh4_mg_l": 1,
    })
    return a

def _bnr():
    return BNRTechnology(_assumptions())

def _default_inputs():
    return BNRInputs(process_configuration="a2o", srt_days=12.0,
                     mlss_mg_l=4000.0, do_aerobic_mg_l=2.0)

# ── BNR ───────────────────────────────────────────────────────────────────────

def test_technology_code():
    chk("bnr technology_code == 'bnr'", _bnr().technology_code == "bnr",
        f"got {_bnr().technology_code!r}")

def test_technology_name():
    name = _bnr().technology_name
    chk("technology_name contains BNR or Biological",
        "BNR" in name or "Biological" in name, f"got {name!r}")

def test_returns_technology_result():
    r = _bnr().calculate(10.0, _default_inputs())
    chk("calculate returns result",         r is not None)
    chk("result technology_code == 'bnr'",  r.technology_code == "bnr",
        f"got {r.technology_code!r}")

def test_positive_energy_consumption():
    r = _bnr().calculate(10.0, _default_inputs())
    chk("energy_kwh_per_day > 0", r.energy_kwh_per_day > 0,
        f"got {r.energy_kwh_per_day}")

def test_energy_scales_with_flow():
    bnr = _bnr()
    inp = _default_inputs()
    r10 = bnr.calculate(10.0, inp)
    r20 = bnr.calculate(20.0, inp)
    chk("energy at 20 MLD > energy at 10 MLD",
        r20.energy_kwh_per_day > r10.energy_kwh_per_day,
        f"10={r10.energy_kwh_per_day:.0f} 20={r20.energy_kwh_per_day:.0f}")

def test_sludge_production_positive():
    r = _bnr().calculate(10.0, _default_inputs())
    sludge = r.performance_outputs.get("sludge_production_kgds_day", 0)
    chk("sludge_production_kgds_day > 0", sludge > 0, f"got {sludge}")

def test_longer_srt_reduces_sludge_yield():
    bnr = _bnr()
    r_short = bnr.calculate(10.0, BNRInputs(srt_days=5.0))
    r_long  = bnr.calculate(10.0, BNRInputs(srt_days=20.0))
    s_short = r_short.performance_outputs.get("sludge_production_kgds_day", 0)
    s_long  = r_long.performance_outputs.get("sludge_production_kgds_day", 0)
    chk("longer SRT → less sludge",
        s_long < s_short, f"short={s_short:.0f} long={s_long:.0f}")

def test_reactor_volume_positive():
    r = _bnr().calculate(10.0, _default_inputs())
    vol = r.performance_outputs.get("reactor_volume_m3", 0)
    chk("reactor_volume_m3 > 0", vol > 0, f"got {vol}")

def test_capex_items_populated():
    r = _bnr().calculate(10.0, _default_inputs())
    chk("capex_items not empty", len(r.capex_items) > 0,
        f"got {len(r.capex_items)} items")

def test_opex_items_populated():
    r = _bnr().calculate(10.0, _default_inputs())
    chk("opex_items not empty", len(r.opex_items) > 0,
        f"got {len(r.opex_items)} items")

def test_process_emissions_populated():
    r = _bnr().calculate(10.0, _default_inputs())
    chk("process_emissions_tco2e_yr not empty",
        len(r.process_emissions_tco2e_yr) > 0)
    chk("N2O in process_emissions",
        any("n2o" in k.lower() for k in r.process_emissions_tco2e_yr),
        f"keys: {list(r.process_emissions_tco2e_yr)}")

def test_supplemental_carbon_adds_methanol():
    bnr = _bnr()
    r_no = bnr.calculate(10.0, BNRInputs(supplemental_carbon=False))
    r_yes = bnr.calculate(10.0, BNRInputs(supplemental_carbon=True))
    chk("no suppl C → no methanol",     "methanol_kg_day" not in r_no.chemical_consumption)
    chk("with suppl C → methanol added","methanol_kg_day" in r_yes.chemical_consumption)

def test_chemical_p_removal_adds_coagulant():
    r = _bnr().calculate(10.0, BNRInputs(chemical_p_removal=True, coagulant="ferric_chloride"))
    chk("chemical P removal → ferric_chloride_kg_day",
        "ferric_chloride_kg_day" in r.chemical_consumption,
        f"keys: {list(r.chemical_consumption)}")

def test_assumptions_used_recorded():
    inp = _default_inputs()
    r = _bnr().calculate(10.0, inp)
    chk("srt_days in assumptions_used", "srt_days" in r.assumptions_used)
    chk("assumptions_used srt_days matches input",
        r.assumptions_used.get("srt_days") == inp.srt_days,
        f"got {r.assumptions_used.get('srt_days')} expected {inp.srt_days}")

# ── MBR ───────────────────────────────────────────────────────────────────────

def test_mbr_basic_calculation():
    from domains.wastewater.technologies.mbr import MBRTechnology, MBRInputs
    a = _assumptions()
    mbr = MBRTechnology(a)
    r = mbr.calculate(10.0, MBRInputs(design_flux_lmh=25.0, srt_days=15.0,
                                       mlss_mg_l=10000.0))
    chk("MBR technology_code == 'mbr'",  r.technology_code == "mbr",
        f"got {r.technology_code!r}")
    chk("MBR energy > 0",                r.energy_kwh_per_day > 0)
    mem_area = r.performance_outputs.get("membrane_area_m2", 0)
    chk("MBR membrane_area_m2 > 0",      mem_area > 0, f"got {mem_area}")

def test_lower_flux_increases_membrane_area():
    from domains.wastewater.technologies.mbr import MBRTechnology, MBRInputs
    mbr = MBRTechnology(_assumptions())
    r_hi = mbr.calculate(10.0, MBRInputs(design_flux_lmh=35.0))
    r_lo = mbr.calculate(10.0, MBRInputs(design_flux_lmh=15.0))
    chk("lower flux → larger membrane area",
        r_lo.performance_outputs["membrane_area_m2"]
        > r_hi.performance_outputs["membrane_area_m2"],
        f"lo={r_lo.performance_outputs['membrane_area_m2']:.0f} "
        f"hi={r_hi.performance_outputs['membrane_area_m2']:.0f}")

# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  BNR + MBR TECHNOLOGY TESTS")
    print("=" * 55)
    test_technology_code()
    test_technology_name()
    test_returns_technology_result()
    test_positive_energy_consumption()
    test_energy_scales_with_flow()
    test_sludge_production_positive()
    test_longer_srt_reduces_sludge_yield()
    test_reactor_volume_positive()
    test_capex_items_populated()
    test_opex_items_populated()
    test_process_emissions_populated()
    test_supplemental_carbon_adds_methanol()
    test_chemical_p_removal_adds_coagulant()
    test_assumptions_used_recorded()
    test_mbr_basic_calculation()
    test_lower_flux_increases_membrane_area()
    print(f"\n  {_p} passed, {_f} failed")
    if _err: [print(f"  ❌ {e}") for e in _err]
    else: print("  ✅ ALL PASSED")
    return _f

if __name__ == "__main__":
    sys.exit(main())
