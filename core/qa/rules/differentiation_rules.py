"""
core/qa/rules/differentiation_rules.py

Technology differentiation QA rules (T1–T4).
Checks that structurally different technologies produce meaningfully different outputs.

These run at project level across pairs of scenarios.

Rules:
  T1 — Process structure reflected in outputs (PFD and sizing)
  T2 — Physical sizing meaningfully different for structurally different techs
  T3 — Risk differentiation: novel vs conventional must differ
  T4 — Output clustering: multiple novel techs must not all collapse to baseline
"""
from __future__ import annotations
from typing import List, Any
from core.qa.qa_model import QAFinding, QAResult, Severity
from domains.wastewater.technology_signatures import get_signature


def run(scenarios: List[Any]) -> QAResult:
    """
    scenarios: list of ScenarioModel with treatment_pathway and domain_specific_outputs
    """
    findings = []

    def f(code, sev, msg, scenario=None, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Differentiation", severity=sev,
            message=msg, scenario=scenario, metric=metric,
            expected=expected, actual=actual, recommendation=rec,
        ))

    # Build lookup: tech_code → (scenario, signature, metrics)
    tech_data = {}
    for sc in scenarios:
        tp = getattr(sc, "treatment_pathway", None)
        tc = (tp.technology_sequence[0]
              if tp and getattr(tp, "technology_sequence", None) else None)
        if not tc:
            continue
        sig = get_signature(tc)
        eng = (sc.domain_specific_outputs or {}).get("engineering_summary", {})
        perf = (sc.domain_specific_outputs or {}).get("technology_performance", {}).get(tc, {})
        risk = sc.risk_result
        cost = sc.cost_result
        tech_data[tc] = {
            "sc": sc, "sig": sig,
            "reactor_m3": perf.get("reactor_volume_m3") or 0,
            "footprint_m2": perf.get("footprint_m2") or 0,
            "sludge": perf.get("sludge_production_kgds_day") or 0,
            "kwh_ml": (eng.get("specific_energy_kwh_kl") or 0) * 1000,
            "risk_score": risk.overall_score if risk else 0,
            "capex_m": cost.capex_total / 1e6 if cost else 0,
            "has_clarifiers": bool(perf.get("clarifier_area_m2")),
            "n_reactors": perf.get("n_reactors"),
            "cycle_time": perf.get("cycle_time_hours"),
            "mlss": perf.get("mlss_granular_mg_l") or perf.get("mlss_mg_l") or 0,
        }

    bnr_data = tech_data.get("bnr")
    codes = list(tech_data.keys())

    # ── T1: Process structure reflected in outputs ─────────────────────────
    # AGS must show no clarifiers; BNR must show clarifiers
    for tc, d in tech_data.items():
        sig = d["sig"]
        if sig is None:
            continue
        if tc == "granular_sludge":
            if d["has_clarifiers"]:
                f("T1", Severity.FAIL,
                  f"{d['sc'].scenario_name}: AGS/Nereda shows secondary clarifiers in outputs. "
                  "Nereda is an SBR process — no secondary clarifiers should be present.",
                  scenario=d["sc"].scenario_name,
                  expected="No secondary clarifiers",
                  actual="clarifier_area_m2 > 0",
                  rec="Check AGS technology module — clarifier CAPEX and footprint must not be included")
            if not d["n_reactors"]:
                f("T1", Severity.WARN,
                  f"{d['sc'].scenario_name}: AGS/Nereda missing SBR reactor count. "
                  "SBR configuration should be explicit.",
                  scenario=d["sc"].scenario_name,
                  rec="Ensure n_reactors is populated in AGS technology output")
        if tc == "bnr":
            if not d["has_clarifiers"]:
                f("T1", Severity.FAIL,
                  f"{d['sc'].scenario_name}: BNR shows no secondary clarifiers. "
                  "Conventional BNR requires secondary clarification.",
                  scenario=d["sc"].scenario_name,
                  rec="Check BNR technology module — clarifier sizing must be included")

    # ── T2: Physical sizing meaningfully different ─────────────────────────
    if bnr_data:
        bnr_reactor = bnr_data["reactor_m3"]
        bnr_footprint = bnr_data["footprint_m2"]
        bnr_sludge = bnr_data["sludge"]
        bnr_energy = bnr_data["kwh_ml"]

        for tc, d in tech_data.items():
            if tc == "bnr" or d["sig"] is None:
                continue
            sig = d["sig"]
            scen_name = d["sc"].scenario_name

            # Reactor volume
            if bnr_reactor > 0 and d["reactor_m3"] > 0:
                reactor_delta = abs(d["reactor_m3"] - bnr_reactor) / bnr_reactor
                fp_lo, fp_hi = sig.footprint_factor_vs_bnr
                if reactor_delta < 0.05:
                    f("T2", Severity.FAIL,
                      f"{scen_name}: Reactor volume ({d['reactor_m3']:.0f} m³) is within 5% of "
                      f"BNR ({bnr_reactor:.0f} m³). Technologies differ structurally — "
                      "reactor sizing must reflect different MLSS and process configuration.",
                      scenario=scen_name,
                      metric="reactor_volume_m3",
                      expected=f">5% difference from BNR {bnr_reactor:.0f} m³",
                      actual=f"{d['reactor_m3']:.0f} m³ ({reactor_delta*100:.0f}% diff)",
                      rec="Check MLSS and SRT assumptions are technology-specific")

            # Footprint
            if bnr_footprint > 0 and d["footprint_m2"] > 0:
                fp_delta = abs(d["footprint_m2"] - bnr_footprint) / bnr_footprint
                if fp_delta < 0.05:
                    f("T2", Severity.FAIL,
                      f"{scen_name}: Footprint ({d['footprint_m2']:.0f} m²) is within 5% of "
                      f"BNR ({bnr_footprint:.0f} m²). {sig.name} should have a distinctly "
                      "different footprint.",
                      scenario=scen_name,
                      metric="footprint_m2",
                      expected=f"Footprint factor {sig.footprint_factor_vs_bnr[0]:.2f}–{sig.footprint_factor_vs_bnr[1]:.2f}× BNR",
                      actual=f"{d['footprint_m2']:.0f} m² ({fp_delta*100:.0f}% diff from BNR)",
                      rec="Check that clarifier area is correctly excluded/included per technology")

            # Footprint outside expected band
            if bnr_footprint > 0 and d["footprint_m2"] > 0:
                fp_ratio = d["footprint_m2"] / bnr_footprint
                fp_lo, fp_hi = sig.footprint_factor_vs_bnr
                if fp_ratio < fp_lo * 0.80 or fp_ratio > fp_hi * 1.20:
                    f("T2", Severity.WARN,
                      f"{scen_name}: Footprint ratio vs BNR = {fp_ratio:.2f} is outside "
                      f"expected range [{fp_lo:.2f}–{fp_hi:.2f}] for {sig.name}.",
                      scenario=scen_name,
                      metric="footprint_m2",
                      expected=f"Ratio {fp_lo:.2f}–{fp_hi:.2f}",
                      actual=f"{fp_ratio:.2f}",
                      rec="Verify footprint calculation — check clarifier area, SWD, and reactor geometry")

    # ── T3: Risk differentiation ────────────────────────────────────────────
    if bnr_data:
        bnr_risk = bnr_data["risk_score"]
        for tc, d in tech_data.items():
            if tc == "bnr" or d["sig"] is None:
                continue
            sig = d["sig"]
            scen_name = d["sc"].scenario_name

            # Novel vs conventional — risk must differ
            novel_techs = {"granular_sludge", "mabr_bnr", "bnr_mbr"}
            if tc in novel_techs:
                risk_delta = d["risk_score"] - bnr_risk
                if risk_delta < 3.0:
                    sev = Severity.FAIL if risk_delta < 0 else Severity.WARN
                    f("T3", sev,
                      f"{scen_name}: Risk score ({d['risk_score']:.0f}) is not meaningfully "
                      f"higher than BNR ({bnr_risk:.0f}). {sig.name} carries higher "
                      "implementation and operational risk than conventional BNR.",
                      scenario=scen_name,
                      metric="risk_score",
                      expected=f">3 points above BNR ({bnr_risk:.0f}+3 = {bnr_risk+3:.0f})",
                      actual=f"{d['risk_score']:.0f} (delta {risk_delta:+.0f})",
                      rec="Review risk scoring for novel technology — "
                          "implementation, operational, and regulatory risk should be elevated")

    # ── T4: MLSS differentiation ────────────────────────────────────────────
    for tc, d in tech_data.items():
        sig = d["sig"]
        if sig is None or d["mlss"] == 0:
            continue
        lo, hi = sig.typical_mlss_mg_l
        if not (lo * 0.70 <= d["mlss"] <= hi * 1.30):
            f("T4", Severity.WARN,
              f"{d['sc'].scenario_name}: MLSS = {d['mlss']:.0f} mg/L is outside typical range "
              f"[{lo:.0f}–{hi:.0f}] for {sig.name}.",
              scenario=d["sc"].scenario_name,
              metric="mlss",
              expected=f"{lo:.0f}–{hi:.0f} mg/L",
              actual=f"{d['mlss']:.0f} mg/L",
              rec=f"Check MLSS assumption for {sig.name} — default should be {lo:.0f}–{hi:.0f} mg/L")

    return QAResult(findings=findings)


def run_separation(scenarios: list) -> "QAResult":
    """
    T5 — Scenario separation rule (checklist item 10).
    If ALL of CAPEX, OPEX, energy, sludge, and footprint are within 5%
    of each other across all scenarios → FAIL (not a real comparison).
    """
    from core.qa.qa_model import QAResult, QAFinding, Severity

    findings = []
    if len(scenarios) < 2:
        return QAResult()

    metrics = []
    for sc in scenarios:
        tp_all = (sc.domain_specific_outputs or {}).get("technology_performance", {})
        eng    = (sc.domain_specific_outputs or {}).get("engineering_summary", {})
        tp = sc.treatment_pathway
        tc = tp.technology_sequence[0] if tp and tp.technology_sequence else None
        perf = tp_all.get(tc, {}) if tc else {}
        cr = sc.cost_result
        metrics.append({
            "name":      sc.scenario_name,
            "capex":     cr.capex_total if cr else 0,
            "opex":      cr.opex_annual if cr else 0,
            "energy":    (eng.get("specific_energy_kwh_kl") or 0) * 1000,
            "sludge":    perf.get("sludge_production_kgds_day") or 0,
            "footprint": perf.get("footprint_m2") or 0,
        })

    # Check if ALL key metrics are within 5% across ALL pairs
    keys = ["capex", "opex", "energy", "sludge", "footprint"]
    key_max_deltas = {}
    for key in keys:
        vals = [m[key] for m in metrics if m[key] > 0]
        if len(vals) >= 2:
            max_delta = (max(vals) - min(vals)) / max(max(vals), 1)
            key_max_deltas[key] = max_delta

    # If ALL metrics <5% different → FAIL
    all_too_similar = all(d < 0.05 for d in key_max_deltas.values()) and len(key_max_deltas) >= 3

    if all_too_similar:
        findings.append(QAFinding(
            code="T5", category="Differentiation", severity=Severity.FAIL,
            message=(
                "All scenarios produce nearly identical outputs — this is not a meaningful "
                "comparison. CAPEX, OPEX, energy, sludge and footprint all differ by less "
                "than 5%.\n"
                "Deltas: " + ", ".join(f"{k}={v*100:.1f}%" for k, v in key_max_deltas.items()),
            ),
            metric="all",
            expected="At least one metric differs by >10% between scenarios",
            actual="All metrics within 5%",
            recommendation="Verify technology modules are producing distinct outputs. "
                           "Check MLSS, Yobs, clarifier sizing, and recycle assumptions."
        ))
    else:
        # Informational — show which metrics are well-differentiated
        well_diff = [k for k, v in key_max_deltas.items() if v > 0.10]
        if well_diff:
            findings.append(QAFinding(
                code="T5", category="Differentiation", severity=Severity.INFO,
                message=(
                    f"Scenario separation check ✅ — meaningful differences in: "
                    f"{', '.join(well_diff)}. "
                    "Deltas: " + ", ".join(f"{k}={v*100:.0f}%" for k, v in key_max_deltas.items())
                ),
            ))

    return QAResult(findings=findings)
