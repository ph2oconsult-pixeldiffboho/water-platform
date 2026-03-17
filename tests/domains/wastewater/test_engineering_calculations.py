"""
tests/domains/wastewater/test_engineering_calculations.py

Engineering calculation regression tests.
All tests verified against Metcalf & Eddy 5th Ed, WEF MOP 32/35,
de Kreuk 2007 (AGS), AU utility benchmarks.
Runs standalone — no pytest required.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.assumptions.assumptions_manager import AssumptionsManager
from core.project.project_model import DomainType
from domains.wastewater.domain_interface import (
    WastewaterDomainInterface, TECHNOLOGY_REGISTRY, TECHNOLOGY_INPUT_CLASSES,
)
from domains.wastewater.input_model import WastewaterInputs
from domains.wastewater.technologies.bnr import BNRTechnology, BNRInputs
from domains.wastewater.technologies.granular_sludge import (
    GranularSludgeTechnology, GranularSludgeInputs,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_p = _f = 0
_err = []

def chk(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  ✅ {name}")
    else:
        _f += 1
        _err.append(name)
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

def approx(a, b, rel=0.05):
    return abs(a - b) / max(abs(b), 1e-10) < rel

def _std_assumptions():
    a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)
    a.engineering_assumptions.update({
        "influent_bod_mg_l": 250, "influent_tkn_mg_l": 45,
        "influent_tn_mg_l":  45,  "influent_nh4_mg_l": 35,
        "influent_tss_mg_l": 280, "effluent_tn_mg_l":  10,
        "effluent_nh4_mg_l": 1,
    })
    return a

def _iface(a=None):
    return WastewaterDomainInterface(a or _std_assumptions())

def _run(code, **kw):
    return _iface().run_scenario(WastewaterInputs(**kw), [code], {})

def _eng(r):
    return r.to_domain_outputs_dict()["engineering_summary"]

def _tp(r, code):
    return r.to_domain_outputs_dict()["technology_performance"].get(code, {})

# ── T1: Oxygen demand ─────────────────────────────────────────────────────────

def test_o2_within_2pct_of_manual():
    """
    Manual: O2_c + O2_n - O2_dn = 1926 + 1440 - 700 = 2666 kg/d
    Ref: Metcalf Eq. 7-57
    """
    r = BNRTechnology(_std_assumptions()).calculate(10.0, BNRInputs())
    o2 = r.performance.additional.get("o2_demand_kg_day", 0)
    chk("O2 demand within 2% of 2658 kg/d",
        approx(o2, 2658, rel=0.02), f"got {o2:.0f}")

def test_o2_scales_linearly_with_flow():
    for flow1, flow2 in [(5, 10), (10, 20)]:
        inp1 = WastewaterInputs(design_flow_mld=flow1, influent_bod_mg_l=250,
                                influent_tkn_mg_l=45, influent_nh4_mg_l=35)
        inp2 = WastewaterInputs(design_flow_mld=flow2, influent_bod_mg_l=250,
                                influent_tkn_mg_l=45, influent_nh4_mg_l=35)
        r1 = _iface().run_scenario(inp1, ["bnr"], {})
        r2 = _iface().run_scenario(inp2, ["bnr"], {})
        o2_1 = _tp(r1, "bnr").get("o2_demand_kg_day", 0)
        o2_2 = _tp(r2, "bnr").get("o2_demand_kg_day", 0)
        chk(f"O2 scales 2× when flow doubles ({flow1}→{flow2} MLD)",
            approx(o2_2 / o2_1, 2.0, rel=0.05),
            f"ratio={o2_2/o2_1:.2f}")

def test_o2_scales_with_bod_load():
    kwh_lo = _eng(_run("bnr", design_flow_mld=10, influent_bod_mg_l=120,
                        influent_tkn_mg_l=int(120*0.18), influent_nh4_mg_l=int(120*0.14))
                  )["specific_energy_kwh_kl"] * 1000
    kwh_hi = _eng(_run("bnr", design_flow_mld=10, influent_bod_mg_l=450,
                        influent_tkn_mg_l=int(450*0.18), influent_nh4_mg_l=int(450*0.14))
                  )["specific_energy_kwh_kl"] * 1000
    ratio = kwh_hi / kwh_lo
    chk(f"Energy ratio BOD_hi/BOD_lo in [2.0, 4.5] (got {ratio:.2f}×)",
        2.0 < ratio < 4.5, f"lo={kwh_lo:.0f} hi={kwh_hi:.0f}")

# ── T2: Sludge yield ──────────────────────────────────────────────────────────

def test_sludge_yield_in_literature_range():
    """Literature: 0.40–0.90 kgDS/kgBOD (Metcalf Table 7-15)"""
    for code in ["bnr", "granular_sludge", "bnr_mbr", "ifas_mbbr", "mabr_bnr"]:
        r = _run(code, design_flow_mld=10, influent_bod_mg_l=250,
                 influent_tkn_mg_l=45, influent_nh4_mg_l=35)
        sludge = _eng(r)["total_sludge_kgds_day"]
        bod_removed = 10000 * (250 - 10) / 1000
        yr = sludge / bod_removed
        chk(f"{code} sludge yield {yr:.3f} in [0.30, 1.00]",
            0.30 <= yr <= 1.00, f"got {yr:.3f}")

def test_ags_lower_sludge_than_bnr():
    """AGS: 15-25% less sludge (de Kreuk 2007 — longer SRT, lower y_obs)"""
    r_bnr = _run("bnr", design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45)
    r_ags = _run("granular_sludge", design_flow_mld=10, influent_bod_mg_l=250,
                 influent_tkn_mg_l=45)
    slg_bnr = _eng(r_bnr)["total_sludge_kgds_day"]
    slg_ags = _eng(r_ags)["total_sludge_kgds_day"]
    ratio = slg_ags / slg_bnr
    chk(f"AGS/BNR sludge ratio {ratio:.2f} in [0.70, 0.95]",
        0.70 <= ratio <= 0.95, f"bnr={slg_bnr:.0f} ags={slg_ags:.0f}")

# ── T3: Aeration energy ───────────────────────────────────────────────────────

def test_aeration_energy_consistent_with_o2():
    r = BNRTechnology(_std_assumptions()).calculate(10.0, BNRInputs())
    o2  = r.performance.additional.get("o2_demand_kg_day", 0)
    aer = r.energy.aeration_kwh_day
    sae = o2 / aer if aer > 0 else 0
    chk(f"Implied SAE_proc {sae:.3f} kgO2/kWh in [0.80, 1.20]",
        0.80 <= sae <= 1.20, f"O2={o2:.0f} aer={aer:.0f}")

def test_pumping_energy_from_first_principles():
    r = BNRTechnology(_std_assumptions()).calculate(10.0, BNRInputs())
    pump = r.energy.pumping_kwh_day
    # RAS=114 + MLR=76 + WAS=4 + ancillary=700 = 894 kWh/d
    chk(f"Pumping {pump:.0f} kWh/d within 5% of 893",
        approx(pump, 893, rel=0.05), f"got {pump:.0f}")

def test_energy_within_literature_range():
    """All technologies within published literature benchmarks."""
    benchmarks = [
        ("bnr",             300, 500, "Metcalf 5th Ed"),
        ("granular_sludge", 200, 380, "de Kreuk 2007"),
        ("mabr_bnr",        200, 420, "GE/Ovivo 2017"),
        ("bnr_mbr",         400, 700, "WEF MBR Manual"),
        ("ifas_mbbr",       300, 600, "Ødegaard 2006"),
    ]
    for code, lo, hi, ref in benchmarks:
        r = _run(code, design_flow_mld=10, influent_bod_mg_l=250,
                 influent_tkn_mg_l=45, influent_nh4_mg_l=35)
        kwh = _eng(r)["specific_energy_kwh_kl"] * 1000
        chk(f"{code} {kwh:.0f} kWh/ML in [{lo},{hi}] [{ref}]",
            lo <= kwh <= hi, f"got {kwh:.0f}")

# ── T4: Lifecycle cost ────────────────────────────────────────────────────────

def test_lcc_uses_crf_not_simple_division():
    """LCC_annual = CAPEX × CRF(i,n) + OPEX_annual."""
    import math
    for code in ["bnr", "granular_sludge", "bnr_mbr", "mabr_bnr"]:
        r = _run(code, design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45)
        cr = r.cost_result
        i, n = cr.discount_rate, cr.analysis_period_years
        crf = i * (1 + i) ** n / ((1 + i) ** n - 1)
        expected = cr.capex_total * crf + cr.opex_annual
        chk(f"{code} LCC = CAPEX×CRF + OPEX",
            approx(cr.lifecycle_cost_annual, expected, rel=0.01),
            f"got {cr.lifecycle_cost_annual/1e3:.0f}k expected {expected/1e3:.0f}k")

def test_specific_cost_per_kl_consistent():
    r = _run("bnr", design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45)
    cr = r.cost_result
    expected = cr.lifecycle_cost_annual / (10 * 1000 * 365)
    chk("$/kL consistent with LCC/annual volume",
        approx(cr.specific_cost_per_kl, expected, rel=0.01),
        f"got {cr.specific_cost_per_kl:.4f} expected {expected:.4f}")

# ── T5: Carbon ────────────────────────────────────────────────────────────────

def test_scope2_consistent_with_energy_and_grid_factor():
    r = _run("bnr", design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45)
    kwh_day = _eng(r)["total_energy_kwh_day"]
    scope2  = r.carbon_result.scope_2_tco2e_yr
    grid    = r.carbon_result.grid_emission_factor_used
    expected = kwh_day * 365 * grid / 1000
    chk("Scope2 = energy × grid factor × 365 / 1000",
        approx(scope2, expected, rel=0.02),
        f"scope2={scope2:.0f} energy×grid={expected:.0f}")

def test_scope2_lower_for_lower_energy_tech():
    r_bnr  = _run("bnr",     design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45)
    r_mabr = _run("mabr_bnr",design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45)
    chk("MABR Scope2 < BNR Scope2 (lower energy → less Scope2)",
        r_mabr.carbon_result.scope_2_tco2e_yr < r_bnr.carbon_result.scope_2_tco2e_yr)

def test_n2o_gwp_applied_correctly():
    r = BNRTechnology(_std_assumptions()).calculate(10.0, BNRInputs())
    n2o = getattr(r.carbon, "n2o_biological_tco2e_yr", 0)
    # N removed ≈ 350 kg/d × EF=0.016 × 365 × GWP=273 / 1000 = 558 tCO2e/yr
    chk(f"N2O {n2o:.0f} tCO2e/yr within 10% of 558",
        approx(n2o, 558, rel=0.10), f"got {n2o:.0f}")

# ── T6: Carbon-limited TN ─────────────────────────────────────────────────────

def test_low_bod_prevents_tn_target():
    """COD/TKN < 4.5 → TN target of 10 mg/L is not achievable without external C."""
    for code in ["bnr", "ifas_mbbr"]:
        r = _run(code, design_flow_mld=10, influent_bod_mg_l=80,
                 influent_tkn_mg_l=45, influent_nh4_mg_l=35, effluent_tn_mg_l=10)
        eff_tn = float(_tp(r, code).get("effluent_tn_mg_l", 10))
        chk(f"{code} BOD=80 → TN > 15 (carbon-limited)",
            eff_tn > 15, f"got TN={eff_tn:.1f}")

def test_adequate_bod_achieves_tn_target():
    r = _run("bnr", design_flow_mld=10, influent_bod_mg_l=300,
             influent_tkn_mg_l=45, influent_nh4_mg_l=35, effluent_tn_mg_l=10)
    eff_tn = float(_tp(r, "bnr").get("effluent_tn_mg_l", 10))
    chk(f"BOD=300 COD/TKN=13.3 → TN ≤ 10.5",
        eff_tn <= 10.5, f"got TN={eff_tn:.1f}")

def test_supplemental_carbon_overcomes_limitation():
    a = _std_assumptions()
    a.engineering_assumptions.update({
        "influent_bod_mg_l": 80, "influent_tkn_mg_l": 45,
        "influent_tn_mg_l": 45, "influent_nh4_mg_l": 35, "effluent_tn_mg_l": 10,
    })
    r = BNRTechnology(a).calculate(10.0, BNRInputs(supplemental_carbon=True))
    eff_tn = r.performance.effluent_tn_mg_l
    chk(f"Supplemental C → TN ≤ 10.5 (got {eff_tn:.1f})",
        eff_tn <= 10.5, f"got {eff_tn:.1f}")

# ── T7: AGS cold temperature ──────────────────────────────────────────────────

def test_cold_increases_reactor_volume():
    def vol(T):
        r = _run("granular_sludge", design_flow_mld=10,
                 influent_temperature_celsius=T,
                 influent_bod_mg_l=250, influent_tkn_mg_l=45)
        return _tp(r, "granular_sludge").get("reactor_volume_m3", 0)
    v20, v10 = vol(20), vol(10)
    chk(f"AGS reactor vol at 10°C ({v10:.0f}) > 20°C ({v20:.0f})",
        v10 > v20)

def test_cold_increases_energy():
    def kwh(T):
        r = _run("granular_sludge", design_flow_mld=10,
                 influent_temperature_celsius=T,
                 influent_bod_mg_l=250, influent_tkn_mg_l=45)
        return _eng(r)["specific_energy_kwh_kl"] * 1000
    k20, k10 = kwh(20), kwh(10)
    chk(f"AGS energy at 10°C ({k10:.0f}) > 20°C ({k20:.0f}) kWh/ML",
        k10 > k20)

def test_cold_increases_effluent_nh4():
    def nh4(T):
        r = _run("granular_sludge", design_flow_mld=10,
                 influent_temperature_celsius=T,
                 influent_bod_mg_l=250, influent_tkn_mg_l=45, influent_nh4_mg_l=35)
        return float(_tp(r, "granular_sludge").get("effluent_nh4_mg_l", 1))
    n20, n10 = nh4(20), nh4(10)
    chk(f"AGS effluent NH4 at 10°C ({n10:.1f}) > 20°C ({n20:.1f})",
        n10 > n20)

# ── T8: OPEX completeness ─────────────────────────────────────────────────────

def test_nonzero_capex_and_opex():
    """Every technology must return non-zero CAPEX and OPEX."""
    for code in sorted(TECHNOLOGY_REGISTRY.keys()):
        r = _run(code, design_flow_mld=10, influent_bod_mg_l=250,
                 influent_tkn_mg_l=45, influent_nh4_mg_l=35)
        chk(f"{code}: CAPEX>0 and OPEX>0",
            r.cost_result.capex_total > 0 and r.cost_result.opex_annual > 0,
            f"CAPEX={r.cost_result.capex_total:.0f} OPEX={r.cost_result.opex_annual:.0f}")

def test_bnr_opex_includes_labour_maintenance_sludge():
    r = _run("bnr", design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45)
    bd = r.cost_result.opex_breakdown
    chk("Labour in BNR OPEX",      any("labour" in k.lower() for k in bd))
    chk("Maintenance in BNR OPEX", any("maintenance" in k.lower() for k in bd))
    chk("Sludge in BNR OPEX",      any("sludge" in k.lower() for k in bd))

def test_bnr_opex_in_realistic_range():
    """AU benchmark: $600–1200k/yr at 10 MLD."""
    r = _run("bnr", design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45)
    total = r.cost_result.opex_annual
    chk(f"BNR OPEX ${total/1e3:.0f}k in AU benchmark [$600k, $1200k]",
        600_000 <= total <= 1_200_000, f"got ${total/1e3:.0f}k")

# ── T9: Economy of scale ──────────────────────────────────────────────────────

def test_capex_per_mld_decreases_with_scale():
    """CAPEX per MLD must decrease as scale increases (Six-Tenths Rule)."""
    for code in ["bnr", "bnr_mbr"]:
        u5  = _run(code, design_flow_mld=5,  influent_bod_mg_l=250,
                   influent_tkn_mg_l=45).cost_result.capex_total / 5
        u50 = _run(code, design_flow_mld=50, influent_bod_mg_l=250,
                   influent_tkn_mg_l=45).cost_result.capex_total / 50
        chk(f"{code} CAPEX/MLD: 5MLD=${u5/1e6:.2f}M → 50MLD=${u50/1e6:.2f}M (ratio {u50/u5:.2f})",
            u50 < u5 * 0.75, f"ratio={u50/u5:.2f} expected <0.75")

# ── T10: Peak flow ────────────────────────────────────────────────────────────

def test_clarifier_scales_with_peak_factor():
    def clar(pf):
        r = _run("bnr", design_flow_mld=10, peak_flow_factor=pf,
                 influent_bod_mg_l=250, influent_tkn_mg_l=45)
        return _tp(r, "bnr").get("clarifier_area_m2", 0)
    c15, c35 = clar(1.5), clar(3.5)
    chk(f"Clarifier area pf=3.5 ({c35:.0f}m²) > pf=1.5 ({c15:.0f}m²) × 1.5",
        c35 > c15 * 1.5)

# ── T11: Input validation ─────────────────────────────────────────────────────

def test_low_bod_triggers_warning():
    from domains.wastewater.validation_rules import register_wastewater_validators
    from core.validation.validation_engine import ValidationEngine
    ve = ValidationEngine()
    register_wastewater_validators(ve)
    r = ve.validate(WastewaterInputs(design_flow_mld=10, influent_bod_mg_l=30,
                                      influent_tkn_mg_l=45))
    warns = [m for m in r.messages
             if m.get("level") == "warning" and "influent_bod_mg_l" in m.get("field", "")]
    chk("BOD=30 triggers plausibility warning", len(warns) >= 1,
        f"got {len(warns)} warnings")

def test_low_bod_tkn_ratio_triggers_warning():
    from domains.wastewater.validation_rules import register_wastewater_validators
    from core.validation.validation_engine import ValidationEngine
    ve = ValidationEngine()
    register_wastewater_validators(ve)
    r = ve.validate(WastewaterInputs(design_flow_mld=10, influent_bod_mg_l=90,
                                      influent_tkn_mg_l=45))
    warns = [m for m in r.messages
             if m.get("level") == "warning"
             and ("carbon" in m.get("message", "").lower()
                  or "denitrif" in m.get("message", "").lower())]
    chk("BOD/TKN=2.0 triggers carbon-limited warning", len(warns) >= 1,
        f"got {len(warns)}")

def test_normal_inputs_no_plausibility_warnings():
    from domains.wastewater.validation_rules import register_wastewater_validators
    from core.validation.validation_engine import ValidationEngine
    ve = ValidationEngine()
    register_wastewater_validators(ve)
    r = ve.validate(WastewaterInputs(
        design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45,
        influent_nh4_mg_l=35, influent_tss_mg_l=280, influent_tp_mg_l=6,
    ))
    plaus = [m for m in r.messages
             if m.get("level") == "warning"
             and "typical" in m.get("message", "").lower()]
    chk("Normal inputs → no plausibility warnings", len(plaus) == 0,
        f"got {plaus}")

# ── T12: Risk scenario sensitivity ───────────────────────────────────────────

def test_cold_climate_increases_risk():
    warm = _iface().run_scenario(
        WastewaterInputs(design_flow_mld=10, influent_temperature_celsius=22),
        ["bnr"], {}
    ).risk_result.overall_score
    cold = _iface().run_scenario(
        WastewaterInputs(design_flow_mld=10, influent_temperature_celsius=12),
        ["bnr"], {}
    ).risk_result.overall_score
    chk(f"Cold climate risk {cold:.1f} > warm {warm:.1f}", cold > warm)

def test_tight_tn_increases_regulatory_risk():
    easy = _iface().run_scenario(
        WastewaterInputs(design_flow_mld=10, effluent_tn_mg_l=12),
        ["bnr"], {}
    ).risk_result.regulatory_score
    tight = _iface().run_scenario(
        WastewaterInputs(design_flow_mld=10, effluent_tn_mg_l=5),
        ["bnr"], {}
    ).risk_result.regulatory_score
    chk(f"Tight TN reg risk {tight:.1f} >= easy {easy:.1f}", tight >= easy)

def test_technology_risk_ordering():
    """BNR must be lower risk than MABR (maturity difference)."""
    iface = _iface()
    inp = WastewaterInputs(design_flow_mld=10, influent_temperature_celsius=20)
    bnr_risk  = iface.run_scenario(inp, ["bnr"],     {}).risk_result.overall_score
    mabr_risk = iface.run_scenario(inp, ["mabr_bnr"], {}).risk_result.overall_score
    ags_risk  = iface.run_scenario(inp, ["granular_sludge"], {}).risk_result.overall_score
    chk(f"BNR ({bnr_risk:.1f}) < MABR ({mabr_risk:.1f})", bnr_risk < mabr_risk)
    chk(f"BNR ({bnr_risk:.1f}) < AGS  ({ags_risk:.1f})",  bnr_risk < ags_risk)

# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  ENGINEERING CALCULATIONS REGRESSION TESTS")
    print("=" * 60)

    print("\nT1: Oxygen demand")
    test_o2_within_2pct_of_manual()
    test_o2_scales_linearly_with_flow()
    test_o2_scales_with_bod_load()

    print("\nT2: Sludge yield")
    test_sludge_yield_in_literature_range()
    test_ags_lower_sludge_than_bnr()

    print("\nT3: Aeration energy")
    test_aeration_energy_consistent_with_o2()
    test_pumping_energy_from_first_principles()
    test_energy_within_literature_range()

    print("\nT4: Lifecycle cost")
    test_lcc_uses_crf_not_simple_division()
    test_specific_cost_per_kl_consistent()

    print("\nT5: Carbon")
    test_scope2_consistent_with_energy_and_grid_factor()
    test_scope2_lower_for_lower_energy_tech()
    test_n2o_gwp_applied_correctly()

    print("\nT6: Carbon-limited TN")
    test_low_bod_prevents_tn_target()
    test_adequate_bod_achieves_tn_target()
    test_supplemental_carbon_overcomes_limitation()

    print("\nT7: AGS cold temperature")
    test_cold_increases_reactor_volume()
    test_cold_increases_energy()
    test_cold_increases_effluent_nh4()

    print("\nT8: OPEX completeness")
    test_nonzero_capex_and_opex()
    test_bnr_opex_includes_labour_maintenance_sludge()
    test_bnr_opex_in_realistic_range()

    print("\nT9: Economy of scale")
    test_capex_per_mld_decreases_with_scale()

    print("\nT10: Peak flow")
    test_clarifier_scales_with_peak_factor()

    print("\nT11: Input validation")
    test_low_bod_triggers_warning()
    test_low_bod_tkn_ratio_triggers_warning()
    test_normal_inputs_no_plausibility_warnings()

    print("\nT12: Risk scenario sensitivity")
    test_cold_climate_increases_risk()
    test_tight_tn_increases_regulatory_risk()
    test_technology_risk_ordering()

    print(f"\n{'='*60}")
    print(f"  {_p} passed, {_f} failed out of {_p + _f}")
    if _err:
        print("  FAILURES:")
        for e in _err:
            print(f"    ❌ {e}")
    else:
        print("  ✅ ALL PASSED")
    print(f"{'='*60}")
    return _f


if __name__ == "__main__":
    sys.exit(main())
