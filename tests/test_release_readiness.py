"""
tests/test_release_readiness.py

MINIMUM CREDIBLE RELEASE CHECKLIST
====================================
Automated checks that must ALL pass before the wastewater planning tool
is considered ready for concept design and option evaluation work.

Run: python3 tests/test_release_readiness.py

Fail = not ready for release.
Pass = ready for internal concept planning use.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run_release_checks():
    from core.assumptions.assumptions_manager import AssumptionsManager
    from core.project.project_model import (
        DomainType, ProjectModel, ProjectMetadata, ScenarioModel, TreatmentPathway
    )
    from domains.wastewater.domain_interface import WastewaterDomainInterface, TECHNOLOGY_REGISTRY
    from domains.wastewater.input_model import WastewaterInputs
    from domains.wastewater.technology_fit import assess_all_technologies
    from core.reporting.report_engine import ReportEngine
    from core.reporting.report_exporter import ReportExporter
    import ast, math

    a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)
    iface = WastewaterDomainInterface(a)

    def run(code, **kw):
        return iface.run_scenario(WastewaterInputs(**kw), [code], {})

    std = dict(design_flow_mld=10, influent_bod_mg_l=250,
               influent_tkn_mg_l=45, influent_nh4_mg_l=35)

    checks = []

    def check(category, name, condition, detail=""):
        status = "✅ PASS" if condition else "❌ FAIL"
        checks.append((category, name, condition, detail))
        print(f"  {status}  [{category}] {name}" + (f" — {detail}" if detail and not condition else ""))

    print("=" * 65)
    print("  MINIMUM CREDIBLE RELEASE CHECKLIST")
    print("  Water Utility Planning Platform — Wastewater Module")
    print("=" * 65)

    # ── 1. All technologies return non-zero CAPEX/OPEX ────────────────────
    print("\n1. ALL TECHNOLOGIES — COST COMPLETENESS")
    for code in sorted(TECHNOLOGY_REGISTRY.keys()):
        r = run(code, **std)
        ok = r.cost_result.capex_total > 0 and r.cost_result.opex_annual > 0
        check("Tech costs", f"{code}: CAPEX>0 and OPEX>0", ok,
              f"CAPEX=${r.cost_result.capex_total/1e6:.2f}M OPEX=${r.cost_result.opex_annual/1e3:.0f}k")

    # ── 2. Core engineering calculations verified ─────────────────────────
    print("\n2. CORE ENGINEERING CALCULATIONS")
    from domains.wastewater.technologies.bnr import BNRTechnology, BNRInputs
    a2 = AssumptionsManager().load_defaults(DomainType.WASTEWATER)
    a2.engineering_assumptions.update({"influent_bod_mg_l":250,"influent_tkn_mg_l":45,
        "influent_nh4_mg_l":35,"influent_tss_mg_l":280,"effluent_tn_mg_l":10,"effluent_nh4_mg_l":1})
    bnr_r = BNRTechnology(a2).calculate(10.0, BNRInputs())

    o2 = bnr_r.performance.additional.get("o2_demand_kg_day", 0)
    check("Engineering", "O2 demand within 5% of manual (2096 kg/d — M&E Eq 8-20)",
          abs(o2 - 2096) / 2096 < 0.05, f"got {o2:.0f}")

    slg = bnr_r.sludge.biological_sludge_kgds_day
    yield_r = slg / (10000 * 240 / 1000)
    check("Engineering", "Sludge yield 0.30–1.00 kgDS/kgBOD",
          0.30 <= yield_r <= 1.00, f"got {yield_r:.3f}")

    sae = o2 / bnr_r.energy.aeration_kwh_day if bnr_r.energy.aeration_kwh_day > 0 else 0
    check("Engineering", "Implied SAE_proc 0.80–1.20 kgO2/kWh",
          0.80 <= sae <= 1.20, f"got {sae:.3f}")

    for code, lo, hi in [("bnr",300,500),("granular_sludge",200,380),
                          ("mabr_bnr",200,420),("bnr_mbr",400,700),("ifas_mbbr",300,600)]:
        r = run(code, **std)
        kwh = r.to_domain_outputs_dict()["engineering_summary"]["specific_energy_kwh_kl"] * 1000
        check("Engineering", f"{code} energy in literature range [{lo},{hi}]",
              lo <= kwh <= hi, f"got {kwh:.0f} kWh/ML")

    # ── 3. Lifecycle cost uses CRF ────────────────────────────────────────
    print("\n3. LIFECYCLE COST CALCULATION")
    for code in ["bnr", "granular_sludge", "bnr_mbr"]:
        r = run(code, **std)
        cr = r.cost_result
        i, n = cr.discount_rate, cr.analysis_period_years
        crf = i * (1 + i) ** n / ((1 + i) ** n - 1)
        expected = cr.capex_total * crf + cr.opex_annual
        ok = abs(cr.lifecycle_cost_annual - expected) / expected < 0.01
        check("LCC", f"{code}: LCC = CAPEX×CRF + OPEX", ok,
              f"got {cr.lifecycle_cost_annual/1e3:.0f}k expected {expected/1e3:.0f}k")

    # ── 4. Influent quality drives outputs ────────────────────────────────
    print("\n4. INFLUENT QUALITY DRIVES OUTPUTS")
    r_lo = run("bnr", design_flow_mld=10, influent_bod_mg_l=120, influent_tkn_mg_l=28, influent_nh4_mg_l=22)
    r_hi = run("bnr", design_flow_mld=10, influent_bod_mg_l=450, influent_tkn_mg_l=70, influent_nh4_mg_l=55)
    kwh_lo = r_lo.to_domain_outputs_dict()["engineering_summary"]["specific_energy_kwh_kl"] * 1000
    kwh_hi = r_hi.to_domain_outputs_dict()["engineering_summary"]["specific_energy_kwh_kl"] * 1000
    ratio = kwh_hi / kwh_lo
    # Ratio ~2.4-3.1× expected: BOD 120→450 (3.75×) but TKN 28→70 (2.5×)
    # Combined load drives O2; net ratio is between the two constituent ratios
    check("Inputs", "Energy ratio BOD_hi/BOD_lo > 2.0× (proportional loads)",
          ratio > 2.0, f"got {ratio:.2f}× (BOD 120→450, TKN 28→70)")

    # ── 5. Carbon-limited TN active ───────────────────────────────────────
    print("\n5. CARBON-LIMITED DENITRIFICATION")
    for code in ["bnr", "ifas_mbbr"]:
        r = run(code, design_flow_mld=10, influent_bod_mg_l=80,
                influent_tkn_mg_l=45, influent_nh4_mg_l=35, effluent_tn_mg_l=10)
        tn = float(r.to_domain_outputs_dict()["technology_performance"]
                   .get(code, {}).get("effluent_tn_mg_l", 10))
        check("Carbon-limited TN", f"{code} BOD=80 → TN>15 (carbon-limited)",
              tn > 15, f"got TN={tn:.1f}")

    # ── 6. Cold temperature penalties ─────────────────────────────────────
    print("\n6. COLD TEMPERATURE PENALTIES")
    nh4_20 = float(run("bnr", design_flow_mld=10, influent_temperature_celsius=20,
                        influent_tkn_mg_l=45)
                   .to_domain_outputs_dict()["technology_performance"]
                   .get("bnr", {}).get("effluent_nh4_mg_l", 1))
    nh4_12 = float(run("bnr", design_flow_mld=10, influent_temperature_celsius=12,
                        influent_tkn_mg_l=45)
                   .to_domain_outputs_dict()["technology_performance"]
                   .get("bnr", {}).get("effluent_nh4_mg_l", 1))
    check("Cold T", f"BNR NH4 increases at 12°C vs 20°C",
          nh4_12 > nh4_20, f"20°C={nh4_20:.1f} → 12°C={nh4_12:.1f}")

    kwh_20 = run("granular_sludge", design_flow_mld=10, influent_temperature_celsius=20,
                 influent_bod_mg_l=250, influent_tkn_mg_l=45
                 ).to_domain_outputs_dict()["engineering_summary"]["specific_energy_kwh_kl"] * 1000
    kwh_10 = run("granular_sludge", design_flow_mld=10, influent_temperature_celsius=10,
                 influent_bod_mg_l=250, influent_tkn_mg_l=45
                 ).to_domain_outputs_dict()["engineering_summary"]["specific_energy_kwh_kl"] * 1000
    check("Cold T", "AGS energy increases at 10°C vs 20°C",
          kwh_10 > kwh_20, f"20°C={kwh_20:.0f} → 10°C={kwh_10:.0f} kWh/ML")

    # ── 7. Comparison table completeness ──────────────────────────────────
    print("\n7. COMPARISON TABLE COMPLETENESS")
    project = ProjectModel(metadata=ProjectMetadata(project_name="Test", plant_name="WWTP"))
    for code, name in [("bnr", "BNR"), ("granular_sludge", "AGS"), ("mabr_bnr", "MABR")]:
        calc = run(code, **std)
        sc = ScenarioModel(scenario_name=name)
        sc.treatment_pathway = TreatmentPathway(
            pathway_name=code, technology_sequence=[code], technology_parameters={})
        sc.domain_inputs = {"design_flow_mld": 10.0}
        iface.update_scenario_model(sc, calc)
        project.add_scenario(sc)

    rep = ReportEngine().build_report(
        project, [sid for sid, s in project.scenarios.items() if s.cost_result], True)
    criteria = [r["Criterion"] for r in rep.comparison_table]

    for must_have in ["Footprint", "Effluent TN", "Specific Cost", "Energy", "Sludge", "Risk"]:
        ok = any(must_have in c for c in criteria)
        check("Comparison", f"'{must_have}' in comparison table", ok)

    # ── 8. Report generation ──────────────────────────────────────────────
    print("\n8. REPORT GENERATION")
    for mode in ["executive", "comprehensive"]:
        for fmt, fn in [("PDF", ReportExporter.to_pdf), ("DOCX", ReportExporter.to_docx)]:
            d = fn(rep, mode=mode)
            check("Reports", f"{fmt} {mode} generates (>{5000} bytes)",
                  len(d) > 5000, f"got {len(d):,} bytes")

    # ── 9. OPEX completeness ──────────────────────────────────────────────
    print("\n9. OPEX COMPLETENESS")
    r = run("bnr", **std)
    bd = r.cost_result.opex_breakdown
    check("OPEX", "Labour in OPEX",      any("labour" in k.lower() for k in bd))
    check("OPEX", "Maintenance in OPEX", any("maintenance" in k.lower() for k in bd))
    check("OPEX", "Sludge in OPEX",      any("sludge" in k.lower() for k in bd))
    check("OPEX", "Electricity in OPEX", any("lectricit" in k.lower() for k in bd))
    total_opex = r.cost_result.opex_annual
    check("OPEX", "BNR OPEX in AU benchmark ($600k–$1.2M at 10 MLD)",
          600_000 <= total_opex <= 1_200_000, f"got ${total_opex/1e3:.0f}k")

    # ── 10. Economy of scale ──────────────────────────────────────────────
    print("\n10. ECONOMY OF SCALE")
    for code in ["bnr", "bnr_mbr"]:
        u5  = run(code, design_flow_mld=5,  influent_bod_mg_l=250, influent_tkn_mg_l=45
                  ).cost_result.capex_total / 5
        u50 = run(code, design_flow_mld=50, influent_bod_mg_l=250, influent_tkn_mg_l=45
                  ).cost_result.capex_total / 50
        check("Scale", f"{code} CAPEX/MLD decreases 5→50 MLD",
              u50 < u5 * 0.75, f"5MLD=${u5/1e6:.2f}M/MLD 50MLD=${u50/1e6:.2f}M/MLD")

    # ── 11. Peak flow clarifier ───────────────────────────────────────────
    print("\n11. PEAK FLOW CLARIFIER SIZING")
    c15 = float(run("bnr", design_flow_mld=10, peak_flow_factor=1.5,
                     influent_bod_mg_l=250, influent_tkn_mg_l=45)
                .to_domain_outputs_dict()["technology_performance"]
                .get("bnr", {}).get("clarifier_area_m2", 0))
    c35 = float(run("bnr", design_flow_mld=10, peak_flow_factor=3.5,
                     influent_bod_mg_l=250, influent_tkn_mg_l=45)
                .to_domain_outputs_dict()["technology_performance"]
                .get("bnr", {}).get("clarifier_area_m2", 0))
    check("Peak flow", f"Clarifier scales with peak factor (pf=1.5→{c15:.0f}m² pf=3.5→{c35:.0f}m²)",
          c35 > c15 * 1.5)

    # ── 12. Input validation fires ────────────────────────────────────────
    print("\n12. INPUT VALIDATION")
    from domains.wastewater.validation_rules import register_wastewater_validators
    from core.validation.validation_engine import ValidationEngine
    ve = ValidationEngine()
    register_wastewater_validators(ve)
    r_val = ve.validate(WastewaterInputs(design_flow_mld=10, influent_bod_mg_l=30,
                                          influent_tkn_mg_l=45))
    bod_warns = [m for m in r_val.messages
                 if m.get("level") == "warning" and "influent_bod_mg_l" in m.get("field", "")]
    check("Validation", "BOD=30 triggers plausibility warning", len(bod_warns) >= 1)

    # ── 13. Technology fit assessment works ───────────────────────────────
    print("\n13. TECHNOLOGY FIT INDICATORS")
    try:
        inp = WastewaterInputs(**std)
        fits = assess_all_technologies(
            ["bnr", "granular_sludge", "mabr_bnr"],
            inp,
            {}
        )
        check("Tech fit", "Fit assessment runs for 3 technologies",
              len(fits) == 3)
        check("Tech fit", "BNR has 'good' fit at standard conditions",
              fits.get("bnr") and fits["bnr"].overall_level.value == "good")
    except Exception as e:
        check("Tech fit", "Tech fit assessment runs without error", False, str(e))

    # ── 14. Risk differentiation ──────────────────────────────────────────
    print("\n14. RISK DIFFERENTIATION")
    scores = {code: run(code, **std).risk_result.overall_score
              for code in ["bnr", "granular_sludge", "mabr_bnr", "bnr_mbr", "ifas_mbbr"]}
    unique = len(set(round(v, 0) for v in scores.values()))
    check("Risk", f"≥4 distinct risk scores across 5 technologies (got {unique})",
          unique >= 4, str(scores))

    # ── 15. Risk scenario sensitivity ────────────────────────────────────
    print("\n15. RISK SCENARIO SENSITIVITY")
    r_warm = iface.run_scenario(
        WastewaterInputs(design_flow_mld=10, influent_temperature_celsius=22, effluent_tn_mg_l=12),
        ["bnr"], {}
    ).risk_result.overall_score
    r_cold = iface.run_scenario(
        WastewaterInputs(design_flow_mld=10, influent_temperature_celsius=12, effluent_tn_mg_l=5),
        ["bnr"], {}
    ).risk_result.overall_score
    check("Risk", f"Cold/tight scenario riskier than warm/easy ({r_warm:.1f} → {r_cold:.1f})",
          r_cold > r_warm)

    # ── 16. Benchmark scenario pack ───────────────────────────────────────
    print("\n16. BENCHMARK SCENARIO PACK (8 scenarios)")
    try:
        from tests.domains.wastewater.test_benchmark_scenarios import run_all_benchmarks
        passes, failures, _ = run_all_benchmarks(verbose=False)
        check("Benchmarks", f"All 8 benchmark scenarios pass ({len(passes)} checks)",
              len(failures) == 0,
              f"{len(failures)} failures: {failures[:2] if failures else ''}")
    except Exception as e:
        check("Benchmarks", "Benchmark pack runs without error", False, str(e))

    # ── 17. New pages syntax ──────────────────────────────────────────────
    print("\n17. NEW PAGES SYNTAX")
    import ast as ast_mod
    for page in ["apps/wastewater_app/pages/page_09_assumptions.py",
                 "apps/wastewater_app/pages/page_10_sensitivity.py",
                 "apps/wastewater_app/app.py",
                 "domains/wastewater/technology_fit.py",
                 "core/reporting/report_engine.py",
                 "apps/wastewater_app/pages/page_04_results.py",
                 "apps/wastewater_app/pages/page_05_comparison.py"]:
        try:
            with open(page) as f: ast_mod.parse(f.read())
            check("Syntax", f"{page.split('/')[-1]} syntax OK", True)
        except SyntaxError as e:
            check("Syntax", f"{page.split('/')[-1]} syntax OK", False, str(e))

    # ── Summary ──────────────────────────────────────────────────────────
    passed = sum(1 for c in checks if c[2])
    failed = sum(1 for c in checks if not c[2])
    total  = len(checks)

    print(f"\n{'='*65}")
    print(f"  RELEASE READINESS SUMMARY")
    print(f"{'='*65}")
    print(f"  Total checks:  {total}")
    print(f"  Passed:        {passed}")
    print(f"  Failed:        {failed}")
    print(f"  Pass rate:     {passed/total*100:.0f}%")
    print()

    if failed == 0:
        print("  ✅ ALL CHECKS PASSED")
        print()
        print("  VERDICT: Platform is RELEASE-READY for concept planning use.")
        print("  Suitable for: internal utility review, consultant working drafts,")
        print("  concept design option selection, early-stage feasibility assessment.")
        print()
        print("  CAVEATS (always apply):")
        print("  • All costs ±40% concept-level estimate")
        print("  • Carbon ±×3–10 (N₂O uncertainty)")
        print("  • Not for procurement, funding approval, or regulatory submission")
        print("  • Detailed design required before implementation")
    else:
        print(f"  ❌ {failed} CHECKS FAILED — NOT release-ready")
        print()
        print("  Failed checks:")
        for cat, name, ok, detail in checks:
            if not ok:
                print(f"    ❌ [{cat}] {name}" + (f" — {detail}" if detail else ""))

    print(f"{'='*65}")
    return failed == 0


if __name__ == "__main__":
    success = run_release_checks()
    sys.exit(0 if success else 1)
