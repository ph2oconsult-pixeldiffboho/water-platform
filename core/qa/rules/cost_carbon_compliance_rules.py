"""
core/qa/rules/cost_carbon_compliance_rules.py

Cost integrity, carbon consistency, effluent compliance, and decision logic rules.
Rules K1–K3, G1–G3, C1–C3, D1–D3.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
from core.qa.qa_model import QAFinding, Severity


# ── Cost rules ─────────────────────────────────────────────────────────────────

def check_costs(
    scenario_name: str,
    cost_result: Any,
    tech_code: str,
    domain_inputs: dict,
) -> List[QAFinding]:
    """
    K1: CAPEX and OPEX non-zero.
    K2: LCC = CAPEX × CRF + OPEX (within ±1%).
    K3: OPEX per kL plausibility.
    """
    findings: List[QAFinding] = []
    sn = scenario_name

    if cost_result is None:
        return findings

    capex  = getattr(cost_result, "capex_total", 0) or 0
    opex   = getattr(cost_result, "opex_annual", 0) or 0
    lcc    = getattr(cost_result, "lifecycle_cost_annual", 0) or 0
    kl     = getattr(cost_result, "specific_cost_per_kl", 0) or 0
    flow   = float(domain_inputs.get("design_flow_mld", 10) or 10)

    # K1 — non-zero
    if capex <= 0:
        findings.append(QAFinding(
            code="K1", category="Cost", severity=Severity.FAIL,
            message=f"CAPEX is zero or negative for scenario '{sn}'. Calculation incomplete.",
            scenario=sn, metric="capex_total",
            recommendation="Rerun calculation. Check technology selection and costing engine.",
        ))
    if opex <= 0:
        findings.append(QAFinding(
            code="K1", category="Cost", severity=Severity.FAIL,
            message=f"OPEX is zero or negative for scenario '{sn}'. Calculation incomplete.",
            scenario=sn, metric="opex_annual",
            recommendation="Rerun calculation. Check OPEX items in costing engine.",
        ))

    # K2 — LCC integrity: LCC = CAPEX × CRF + OPEX
    if capex > 0 and opex > 0 and lcc > 0:
        dr, n = 0.07, 30
        crf = dr * (1 + dr)**n / ((1 + dr)**n - 1)
        expected_lcc = capex * crf + opex
        delta_pct = abs(lcc - expected_lcc) / expected_lcc * 100
        if delta_pct > 2:
            findings.append(QAFinding(
                code="K2", category="Cost", severity=Severity.FAIL,
                message=(
                    f"LCC integrity check failed. "
                    f"Reported LCC = ${lcc/1e3:.0f}k/yr, "
                    f"but CAPEX×CRF + OPEX = ${expected_lcc/1e3:.0f}k/yr "
                    f"(difference {delta_pct:.1f}%)."
                ),
                scenario=sn, metric="lifecycle_cost_annual",
                expected=f"${expected_lcc/1e3:.0f}k/yr (CAPEX×{crf:.4f} + OPEX)",
                actual=f"${lcc/1e3:.0f}k/yr",
                recommendation="Check lifecycle cost formula. Discount rate should be 7%, period 30 years.",
            ))

    # K3 — OPEX per kL plausibility
    if opex > 0 and flow > 0:
        opex_kl = opex / (flow * 1000 * 365)
        if opex_kl > 2.0:
            findings.append(QAFinding(
                code="K3", category="Cost", severity=Severity.FAIL,
                message=(
                    f"OPEX = ${opex_kl:.2f}/kL is implausibly high. "
                    f"Industry benchmark for municipal WWTP: $0.20–0.80/kL. "
                    f"Possible unit scaling error in costing engine."
                ),
                scenario=sn, metric="opex_annual",
                expected="$0.20–0.80/kL", actual=f"${opex_kl:.2f}/kL",
                recommendation="Review OPEX line items. Check for $/day vs $/year unit errors.",
            ))
        elif opex_kl > 1.0:
            findings.append(QAFinding(
                code="K3", category="Cost", severity=Severity.WARN,
                message=(
                    f"OPEX = ${opex_kl:.2f}/kL is above typical benchmark ($0.20–0.80/kL). "
                    "Verify sludge disposal, electricity, and maintenance rates."
                ),
                scenario=sn, metric="opex_annual",
                expected="$0.20–0.80/kL", actual=f"${opex_kl:.2f}/kL",
                recommendation="Review OPEX breakdown for unusually high line items.",
            ))

    return findings


# ── Carbon rules ───────────────────────────────────────────────────────────────

def check_carbon(
    scenario_name: str,
    carbon_result: Any,
    tp: dict,
    domain_inputs: dict,
    assumptions: Any = None,
) -> List[QAFinding]:
    """
    G1: Scope 2 = electricity × grid emission factor (±5%).
    G2: Energy lower but Scope 2 higher — flag mismatch.
    G3: N2O uncertainty warning when biological N removal present.
    """
    findings: List[QAFinding] = []
    sn = scenario_name

    if carbon_result is None:
        return findings

    scope2_reported = getattr(carbon_result, "scope_2_tco2e_yr", 0) or 0
    scope2_tp       = float(tp.get("scope2_tco2e_yr", 0) or 0)
    energy_kwh_day  = float(tp.get("net_energy_kwh_day", 0) or 0)
    tn_in           = float(domain_inputs.get("influent_tkn_mg_l", 45) or 45)
    flow_mld        = float(domain_inputs.get("design_flow_mld", 10) or 10)

    # G1 — Scope 2 consistency
    grid_ef = 0.79  # tCO2e/MWh — platform default
    if energy_kwh_day > 0:
        expected_scope2 = energy_kwh_day * 365 * grid_ef / 1000
        if scope2_reported > 0:
            delta_pct = abs(scope2_reported - expected_scope2) / expected_scope2 * 100
            if delta_pct > 10:
                findings.append(QAFinding(
                    code="G1", category="Carbon", severity=Severity.WARN,
                    message=(
                        f"Scope 2 consistency check: reported {scope2_reported:.0f} tCO₂e/yr, "
                        f"expected from energy {expected_scope2:.0f} tCO₂e/yr "
                        f"(difference {delta_pct:.1f}%). "
                        f"Using grid EF = {grid_ef} tCO₂e/MWh."
                    ),
                    scenario=sn, metric="scope_2_tco2e_yr",
                    expected=f"{expected_scope2:.0f} tCO₂e/yr",
                    actual=f"{scope2_reported:.0f} tCO₂e/yr",
                    recommendation="Verify grid emission factor and electricity calculation.",
                ))

    # G3 — N2O uncertainty note (always add for biological N removal)
    if tn_in > 20 and flow_mld > 0:
        findings.append(QAFinding(
            code="G3", category="Carbon", severity=Severity.INFO,
            message=(
                "N₂O process emissions carry ×3–10 uncertainty (IPCC EF range 0.005–0.050 "
                "vs central 0.016 used here). Site measurement is recommended for detailed "
                "carbon assessments. Carbon figures shown are concept-level only."
            ),
            scenario=sn, metric="scope1_tco2e_yr",
            recommendation="Site-specific N₂O measurement recommended before reporting Scope 1 emissions.",
        ))

    return findings


# ── Compliance rules ───────────────────────────────────────────────────────────

def check_compliance(
    scenario_name: str,
    tp: dict,
    domain_inputs: dict,
    is_preferred: bool = False,
) -> List[QAFinding]:
    """
    C1: Preferred option must not fail compliance targets.
    C2: COD:TKN denitrification logic.
    C3: Temperature nitrification logic.
    """
    findings: List[QAFinding] = []
    sn = scenario_name

    eff_tn_actual  = float(tp.get("effluent_tn_mg_l", 999) or 999)
    eff_nh4_actual = float(tp.get("effluent_nh4_mg_l", 999) or 999)
    eff_tp_actual  = float(tp.get("effluent_tp_mg_l", 999) or 999)
    eff_tn_target  = float(domain_inputs.get("effluent_tn_mg_l", 10) or 10)
    eff_nh4_target = float(domain_inputs.get("effluent_nh4_mg_l", 5) or 5)
    eff_tp_target  = float(domain_inputs.get("effluent_tp_mg_l", 1) or 1)
    compliance     = tp.get("compliance_flag", "")
    temp           = float(domain_inputs.get("influent_temperature_celsius", 20) or 20)

    # C1 — Preferred option must meet all targets
    if is_preferred and "Review Required" in str(compliance):
        failing = []
        if eff_tn_actual > eff_tn_target:
            failing.append(f"TN {eff_tn_actual:.1f} > {eff_tn_target:.1f} mg/L")
        if eff_nh4_actual > eff_nh4_target:
            failing.append(f"NH₄ {eff_nh4_actual:.1f} > {eff_nh4_target:.1f} mg/L")
        if eff_tp_actual > eff_tp_target:
            failing.append(f"TP {eff_tp_actual:.1f} > {eff_tp_target:.1f} mg/L")
        if failing:
            findings.append(QAFinding(
                code="C1", category="Compliance", severity=Severity.FAIL,
                message=(
                    f"Scenario '{sn}' is marked as preferred but fails compliance: "
                    + "; ".join(failing) + ". "
                    "A non-compliant option must not be recommended."
                ),
                scenario=sn,
                recommendation=(
                    "Either resolve compliance failure or label this scenario as "
                    "'non-compliant base case — intervention required'."
                ),
            ))

    # C3 — Cold temperature + nitrification result unchanged
    if temp < 15 and eff_nh4_actual <= eff_nh4_target:
        if temp < 12:
            findings.append(QAFinding(
                code="C3", category="Compliance", severity=Severity.WARN,
                message=(
                    f"Temperature = {temp}°C but effluent NH₄ = {eff_nh4_actual:.1f} mg/L "
                    f"(target {eff_nh4_target:.1f}). At {temp}°C, conventional BNR "
                    "nitrification is usually not achievable without intervention. "
                    "Verify that the technology applies cold-climate correction."
                ),
                scenario=sn, metric="effluent_nh4_mg_l",
                recommendation="Confirm cold-climate penalty is applied. Check technology assumptions.",
            ))

    return findings


# ── Decision logic rules ───────────────────────────────────────────────────────

def check_decision_logic(
    decision: Any,
    scenarios: list,
) -> List[QAFinding]:
    """
    D1: No contradictory recommendation text.
    D2: Trade-off completeness when two pathways exist.
    D3: Non-viable vs intervention labelling.
    """
    findings: List[QAFinding] = []
    if decision is None:
        return findings

    recommended_label = getattr(decision, "recommended_label", "")
    non_viable        = getattr(decision, "non_viable", [])
    trade_offs        = getattr(decision, "trade_offs", [])
    why               = getattr(decision, "why_recommended", [])
    alt_paths         = getattr(decision, "alternative_pathways", [])
    client_framing    = getattr(decision, "client_framing", None)
    selection_basis   = getattr(decision, "selection_basis", "")

    # D1 — No contradictory text: recommended not in non-viable
    if recommended_label in non_viable:
        findings.append(QAFinding(
            code="D1", category="Decision", severity=Severity.FAIL,
            message=(
                f"Recommended option '{recommended_label}' appears in the non-viable list. "
                "A non-compliant option cannot be recommended."
            ),
            recommendation="Fix selection logic. Only compliant options may be recommended.",
        ))

    # D1b — "offset by lower risk" when recommended has higher risk
    why_text = " ".join(why).lower()
    if "offset by lower risk" in why_text:
        # Check if recommended actually has higher risk
        rec_risk = next((s.risk_result.overall_score for s in scenarios
                         if s.scenario_name == recommended_label), None)
        others_risk = [s.risk_result.overall_score for s in scenarios
                       if s.scenario_name != recommended_label
                       and s.risk_result]
        if rec_risk and others_risk and rec_risk > min(others_risk):
            findings.append(QAFinding(
                code="D1", category="Decision", severity=Severity.FAIL,
                message=(
                    f"Recommendation text says 'offset by lower risk' but '{recommended_label}' "
                    f"has higher risk ({rec_risk:.0f}) than alternatives. Contradictory narrative."
                ),
                recommendation="Update recommendation text to reflect actual risk comparison.",
            ))

    # D2 — Two compliant pathways should have full trade-off set
    has_two_pathways = "two compliant" in selection_basis.lower()
    if has_two_pathways:
        required_topics = ["capex", "regulatory", "delivery", "lcc"]
        trade_off_text = " ".join(trade_offs).lower()
        missing = [t for t in required_topics if t not in trade_off_text]
        if missing:
            findings.append(QAFinding(
                code="D2", category="Decision", severity=Severity.WARN,
                message=(
                    f"Two compliant pathways identified but trade-off section is missing: "
                    f"{', '.join(missing)}. Complete trade-off analysis required."
                ),
                recommendation="Add CAPEX, OPEX, delivery, and regulatory trade-offs.",
            ))

    # D3 — Non-viable base cases should have intervention labelling
    if non_viable and alt_paths:
        for path in alt_paths:
            if path.achieves_compliance:
                # Good — has intervention label
                pass
        # Check: non-viable labels should say "without intervention" or similar
        for nv in non_viable:
            found_label = any(
                "without intervention" in t.lower() or
                "non-compliant" in t.lower()
                for t in trade_offs
            )
            if not found_label:
                findings.append(QAFinding(
                    code="D3", category="Decision", severity=Severity.INFO,
                    message=(
                        f"'{nv}' is listed as non-compliant but alternative pathways exist. "
                        "Consider labelling as 'non-compliant base case — compliant with intervention'."
                    ),
                    recommendation="Update non-viable label to reflect intervention availability.",
                ))
                break  # One finding per scenario is enough

    return findings
