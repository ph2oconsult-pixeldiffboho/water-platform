"""
core/qa/rules/cost_rules.py
Cost integrity checks: LCC formula, OPEX completeness, CAPEX plausibility.
"""
from __future__ import annotations
from core.qa.qa_model import QAFinding, QAResult, Severity


def run(scenario) -> QAResult:
    findings = []
    sn = getattr(scenario, "scenario_name", None)
    cr = scenario.cost_result
    di = scenario.domain_inputs or {}

    if not cr:
        return QAResult(findings=[QAFinding(
            code="K0", category="Cost", severity=Severity.FAIL,
            message="Cost results not populated — run calculations first.",
            scenario=sn)])

    def f(code, sev, msg, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Cost", severity=sev, message=msg,
            scenario=sn, metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    flow = di.get("design_flow_mld") or 0
    dr   = di.get("discount_rate") or 0.07
    n    = di.get("analysis_period_years") or 30

    # ── K1: CAPEX and OPEX non-zero ───────────────────────────────────────
    if cr.capex_total <= 0:
        f("K1", Severity.FAIL, "CAPEX = 0 for active scenario.",
          metric="capex_total", expected="> 0", actual=str(cr.capex_total),
          rec="Check technology CAPEX items are populated")
    if cr.opex_annual <= 0:
        f("K1", Severity.FAIL, "OPEX = 0 — cost model incomplete.",
          metric="opex_annual", expected="> 0", actual=str(cr.opex_annual),
          rec="Check electricity, sludge, and labour cost items")

    # ── K2: LCC formula integrity ─────────────────────────────────────────
    if cr.capex_total > 0 and cr.opex_annual > 0 and cr.lifecycle_cost_annual > 0:
        crf = dr * (1 + dr)**n / ((1 + dr)**n - 1)
        lcc_expected = cr.capex_total * crf + cr.opex_annual
        lcc_reported = cr.lifecycle_cost_annual
        delta = abs(lcc_reported - lcc_expected) / max(lcc_expected, 1)
        if delta > 0.01:
            f("K2", Severity.FAIL,
              f"LCC formula error: reported ${lcc_reported/1e3:.0f}k/yr ≠ "
              f"CAPEX×CRF + OPEX = ${lcc_expected/1e3:.0f}k/yr "
              f"(discrepancy = {delta*100:.1f}%).",
              metric="lifecycle_cost_annual",
              expected=f"${lcc_expected/1e3:.0f}k/yr",
              actual=f"${lcc_reported/1e3:.0f}k/yr",
              rec=f"Check CRF calculation: dr={dr}, n={n}, CRF={crf:.4f}")

    # ── K3: $/kL plausibility ─────────────────────────────────────────────
    cost_kl = cr.specific_cost_per_kl or 0
    if cost_kl > 0 and flow > 0:
        if cost_kl < 0.10:
            f("K3", Severity.WARN,
              f"Specific cost ${cost_kl:.2f}/kL is very low — verify OPEX completeness.",
              metric="specific_cost_per_kl",
              expected="$0.20–$2.00/kL for municipal WW",
              actual=f"${cost_kl:.2f}/kL")
        elif cost_kl > 5.0:
            f("K3", Severity.WARN,
              f"Specific cost ${cost_kl:.2f}/kL is very high — verify inputs (especially OPEX).",
              metric="specific_cost_per_kl",
              expected="$0.20–$2.00/kL for municipal WW",
              actual=f"${cost_kl:.2f}/kL",
              rec="Check OPEX for unit scaling errors (e.g. $/t vs $/kg, daily vs annual)")

    # ── K4: OPEX:CAPEX ratio sanity ───────────────────────────────────────
    if cr.capex_total > 0 and cr.opex_annual > 0:
        opex_capex_ratio = cr.opex_annual / cr.capex_total
        if opex_capex_ratio > 0.30:
            f("K4", Severity.FAIL,
              f"OPEX/CAPEX ratio = {opex_capex_ratio*100:.0f}%/yr — physically impossible. "
              "Maximum credible is ~10%/yr (electricity + labour + sludge + maintenance).",
              metric="opex_annual",
              expected="OPEX < 10% of CAPEX per year",
              actual=f"OPEX = {opex_capex_ratio*100:.0f}% of CAPEX/yr",
              rec="Check for unit scaling errors in OPEX — likely a daily rate applied annually twice, "
                  "or $/t applied to kg values")

    return QAResult(findings=findings)


def run_cross_scenario(scenarios: list) -> "QAResult":
    """
    K5 — CAPEX vs footprint logic (cross-scenario).
    A smaller-footprint technology should not have significantly higher
    civil CAPEX without an explicit reason (specialist equipment, membranes, etc.).
    """
    from core.qa.qa_model import QAResult, QAFinding, Severity
    findings = []

    data = []
    for sc in scenarios:
        cr = sc.cost_result
        tp = sc.treatment_pathway
        tc = tp.technology_sequence[0] if tp and tp.technology_sequence else None
        perf = (sc.domain_specific_outputs or {}).get("technology_performance", {}).get(tc or "", {})
        from domains.wastewater.technology_signatures import get_signature
        sig = get_signature(tc) if tc else None
        data.append({
            "name":        sc.scenario_name,
            "capex":       cr.capex_total if cr else 0,
            "footprint":   perf.get("footprint_m2") or 0,
            "has_membranes": tc in ("bnr_mbr", "adv_reuse") if tc else False,
            "has_specialist": tc in ("mabr_bnr", "granular_sludge") if tc else False,
        })

    for i, a in enumerate(data):
        for b in data[i+1:]:
            if a["footprint"] > 0 and b["footprint"] > 0 and a["capex"] > 0 and b["capex"] > 0:
                # B has smaller footprint but higher capex
                if b["footprint"] < a["footprint"] * 0.85:   # B footprint ≥15% smaller
                    if b["capex"] > a["capex"] * 1.20:        # B capex >20% higher
                        # This is ACCEPTABLE if B has membranes or specialist equipment
                        if b["has_membranes"] or b["has_specialist"]:
                            findings.append(QAFinding(
                                code="K5", category="Cost", severity=Severity.INFO,
                                message=(
                                    f"{b['name']}: smaller footprint ({b['footprint']:.0f} m²) "
                                    f"but higher CAPEX (${b['capex']/1e6:.1f}M vs "
                                    f"${a['capex']/1e6:.1f}M for {a['name']}). "
                                    "Expected: specialist equipment (membranes / proprietary systems) "
                                    "offset civil savings."
                                ),
                                recommendation="Confirm CAPEX breakdown shows specialist "
                                               "equipment as the driver of higher cost."
                            ))
                        else:
                            findings.append(QAFinding(
                                code="K5", category="Cost", severity=Severity.WARN,
                                message=(
                                    f"{b['name']}: footprint {b['footprint']:.0f} m² "
                                    f"vs {a['name']} {a['footprint']:.0f} m² "
                                    f"(−{(a['footprint']-b['footprint'])/a['footprint']*100:.0f}%) "
                                    f"but CAPEX is ${b['capex']/1e6:.1f}M vs "
                                    f"${a['capex']/1e6:.1f}M "
                                    f"(+{(b['capex']-a['capex'])/a['capex']*100:.0f}%). "
                                    "Smaller footprint should not produce higher civil CAPEX "
                                    "without specialist equipment justification."
                                ),
                                metric="capex_total",
                                expected="CAPEX decreases with footprint unless specialist equipment",
                                actual=f"CAPEX higher despite smaller footprint",
                                recommendation="Review CAPEX item unit rates — check no double-counting"
                            ))

    return QAResult(findings=findings)
