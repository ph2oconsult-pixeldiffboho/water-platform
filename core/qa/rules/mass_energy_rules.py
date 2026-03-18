"""
core/qa/rules/mass_energy_rules.py

Post-run mass and energy consistency checks.
These would have caught the O2/energy mismatch in the uploaded report.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from core.qa.qa_model import QAFinding, QAResult, Severity

# Technology-specific energy benchmarks (kWh/ML)
ENERGY_BENCHMARKS = {
    "bnr":             (250, 450),
    "granular_sludge": (220, 420),
    "ifas_mbbr":       (280, 500),
    "bnr_mbr":         (450, 800),
    "mabr_bnr":        (180, 380),
}

def run(scenario, tech_code: str = None) -> QAResult:
    """
    scenario: ScenarioModel with cost_result, carbon_result, domain_specific_outputs
    tech_code: primary technology code string
    """
    findings = []
    sn = getattr(scenario, "scenario_name", None)
    di = scenario.domain_inputs or {}
    eng = (scenario.domain_specific_outputs or {}).get("engineering_summary", {})
    tp  = (scenario.domain_specific_outputs or {}).get("technology_performance", {})
    tech_perf = tp.get(tech_code, {}) if tech_code else {}

    def f(code, sev, msg, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Energy", severity=sev, message=msg,
            scenario=sn, metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    # ── E1: O2 demand vs aeration energy consistency ───────────────────────
    o2_kg_day = tech_perf.get("o2_demand_kg_day") or 0
    total_kwh_day = eng.get("total_energy_kwh_day") or 0
    flow_mld = di.get("design_flow_mld") or 0

    if o2_kg_day > 0 and total_kwh_day > 0:
        # SAE_process ≈ 1.8 × alpha (alpha=0.55 typical) ≈ 0.99 kg O2/kWh
        # Aeration fraction of total energy: typically 50-75%
        sae_proc = 1.8 * 0.55  # conservative process SAE
        aeration_kwh_implied = o2_kg_day / sae_proc
        aeration_kwh_actual  = total_kwh_day * 0.65  # assume 65% of total is aeration

        ratio = aeration_kwh_implied / max(aeration_kwh_actual, 1)
        if ratio > 1.5 or ratio < 0.4:
            sev = Severity.FAIL if (ratio > 2.0 or ratio < 0.25) else Severity.WARN
            f("E1", sev,
              f"O₂ demand ({o2_kg_day:.0f} kg/d) and aeration energy "
              f"({aeration_kwh_actual:.0f} kWh/d estimated from total) are inconsistent "
              f"(implied aeration = {aeration_kwh_implied:.0f} kWh/d, ratio={ratio:.1f}×).",
              metric="o2_demand_kg_day",
              expected=f"Aeration kWh/d within 50% of O₂-implied value",
              actual=f"O₂-implied {aeration_kwh_implied:.0f} vs reported ~{aeration_kwh_actual:.0f}",
              rec="Verify aeration energy calculation — check SAE factor and O₂ demand formula")

    # ── E2: Specific energy plausibility ──────────────────────────────────
    kwh_kl = eng.get("specific_energy_kwh_kl") or 0
    kwh_ml = kwh_kl * 1000

    if kwh_ml > 0 and tech_code:
        lo, hi = ENERGY_BENCHMARKS.get(tech_code, (200, 900))
        if kwh_ml < lo:
            sev = Severity.FAIL if kwh_ml < lo * 0.6 else Severity.WARN
            f("E2", sev,
              f"Specific energy {kwh_ml:.0f} kWh/ML is below benchmark range for "
              f"{tech_code} ({lo}–{hi} kWh/ML). Likely underestimate.",
              metric="specific_energy_kwh_kl",
              expected=f"{lo}–{hi} kWh/ML",
              actual=f"{kwh_ml:.0f} kWh/ML",
              rec="Check aeration, pumping, and ancillary energy components are all included")
        elif kwh_ml > hi:
            f("E2", Severity.WARN,
              f"Specific energy {kwh_ml:.0f} kWh/ML is above benchmark range for "
              f"{tech_code} ({lo}–{hi} kWh/ML). Verify inputs.",
              metric="specific_energy_kwh_kl",
              expected=f"{lo}–{hi} kWh/ML",
              actual=f"{kwh_ml:.0f} kWh/ML",
              rec="Check for unusually high oxygen demand or aeration inefficiency")

    # ── E3: Energy and CAPEX both non-zero ────────────────────────────────
    cr = scenario.cost_result
    if cr:
        if cr.capex_total <= 0:
            f("E3", Severity.FAIL,
              "CAPEX is zero or negative for an active scenario.",
              metric="capex_total",
              expected="> 0",
              actual=str(cr.capex_total),
              rec="Check that technology cost items are correctly defined")
        if cr.opex_annual <= 0:
            f("E3", Severity.FAIL,
              "OPEX is zero or negative — energy, sludge, and labour costs missing.",
              metric="opex_annual",
              expected="> 0",
              actual=str(cr.opex_annual),
              rec="Check electricity, sludge disposal, and labour cost items")

    return QAResult(findings=findings)


def run_directional(scenarios: list) -> "QAResult":
    """
    E4: Energy breakdown explained when >15% difference between scenarios.
    E5: Higher load must produce higher O2 and energy (directional sanity).
    Cross-scenario checks — call with a list of ScenarioModel objects.
    """
    from core.qa.qa_model import QAResult, QAFinding, Severity

    findings = []

    def f(code, sev, msg, scenario=None, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Energy", severity=sev, message=msg,
            scenario=scenario, metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    # Build per-scenario data
    data = []
    for sc in scenarios:
        tp_all = (sc.domain_specific_outputs or {}).get("technology_performance", {})
        eng    = (sc.domain_specific_outputs or {}).get("engineering_summary", {})
        tp_code = (sc.treatment_pathway.technology_sequence[0]
                   if sc.treatment_pathway and sc.treatment_pathway.technology_sequence else None)
        tp = tp_all.get(tp_code, {}) if tp_code else {}
        di = sc.domain_inputs or {}
        data.append({
            "name":       sc.scenario_name,
            "kwh_ml":     (eng.get("specific_energy_kwh_kl") or 0) * 1000,
            "o2":         tp.get("o2_demand_kg_day") or 0,
            "aer_kwh":    tp.get("aeration_energy_kwh_day") or 0,
            "total_kwh":  tp.get("net_energy_kwh_day") or 0,
            "bod_load":   ((di.get("influent_bod_mg_l") or 0) * (di.get("design_flow_mld") or 1)),
            "pumping_note": any(
                "RAS" in (n or "") or "MLR" in (n or "") or "decant" in (n or "")
                for n in tp.get("_notes", {}).get("assumptions", [])
            ),
        })

    # E4: if two scenarios differ >15% in total energy, aeration breakdown must be present
    for i, a in enumerate(data):
        for b in data[i+1:]:
            if a["kwh_ml"] > 0 and b["kwh_ml"] > 0:
                delta = abs(a["kwh_ml"] - b["kwh_ml"]) / max(a["kwh_ml"], b["kwh_ml"])
                if delta > 0.15:
                    # Check if aeration breakdown exists for both
                    a_has_breakdown = a["aer_kwh"] > 0
                    b_has_breakdown = b["aer_kwh"] > 0
                    if not (a_has_breakdown and b_has_breakdown):
                        f("E4", Severity.WARN,
                          f"Energy difference {delta*100:.0f}% between "
                          f"{a['name']} ({a['kwh_ml']:.0f} kWh/ML) and "
                          f"{b['name']} ({b['kwh_ml']:.0f} kWh/ML) "
                          "but aeration vs pumping breakdown is not available.",
                          metric="specific_energy_kwh_kl",
                          rec="Ensure aeration_energy_kwh_day is populated in technology outputs")
                    else:
                        # Breakdown exists — check pumping difference explains energy diff
                        pump_a = a["total_kwh"] - a["aer_kwh"]
                        pump_b = b["total_kwh"] - b["aer_kwh"]
                        if not (a["pumping_note"] or b["pumping_note"]):
                            f("E4", Severity.INFO,
                              f"{a['name']} vs {b['name']}: "
                              f"aeration {a['aer_kwh']:.0f} vs {b['aer_kwh']:.0f} kWh/d, "
                              f"ancillary/pumping {pump_a:.0f} vs {pump_b:.0f} kWh/d. "
                              "Energy difference explained by recycle pumping savings "
                              "(no RAS/MLR in SBR process).",
                              metric="aeration_energy_kwh_day")

    # E5: directional — higher BOD load must not give lower energy
    if len(data) >= 2:
        sorted_by_load = sorted([d for d in data if d["bod_load"] > 0],
                                  key=lambda x: x["bod_load"])
        for i in range(len(sorted_by_load) - 1):
            lo = sorted_by_load[i]
            hi = sorted_by_load[i+1]
            load_diff = (hi["bod_load"] - lo["bod_load"]) / max(lo["bod_load"], 1)
            if load_diff > 0.20:  # >20% load difference
                if hi["kwh_ml"] < lo["kwh_ml"] * 0.90:  # energy drops >10% despite 20% more load
                    f("E5", Severity.WARN,
                      f"Directional check: {hi['name']} has {load_diff*100:.0f}% higher BOD load "
                      f"than {lo['name']} but {(lo['kwh_ml']-hi['kwh_ml'])/lo['kwh_ml']*100:.0f}% "
                      "lower energy. Verify energy calculation.",
                      metric="specific_energy_kwh_kl",
                      expected="Higher load → higher or equal energy",
                      actual=f"{lo['name']}={lo['kwh_ml']:.0f}  {hi['name']}={hi['kwh_ml']:.0f} kWh/ML",
                      rec="Check if different process type (SBR vs CAS) explains difference; "
                          "if same technology, investigate")

    return QAResult(findings=findings)
