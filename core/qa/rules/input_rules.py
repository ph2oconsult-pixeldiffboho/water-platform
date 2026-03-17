"""
core/qa/rules/input_rules.py  —  Pre-run input validation rules

Runs BEFORE the engineering calculation to catch missing data,
physically impossible inputs, and plausibility issues.
"""
from __future__ import annotations
from typing import Any, Dict
from core.qa.qa_model import QAFinding, QAResult, Severity


def run(inputs: Dict[str, Any], scenario_name: str = None) -> QAResult:
    """
    inputs: dict of WastewaterInputs fields (or domain_inputs dict from ScenarioModel)
    """
    findings = []
    sn = scenario_name

    def get(key, default=None):
        return inputs.get(key, default)

    def f(code, sev, msg, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Input", severity=sev,
            message=msg, scenario=sn,
            metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    # ── A. Required fields present ────────────────────────────────────────
    required = {
        "design_flow_mld":            "Design flow (ML/day)",
        "influent_bod_mg_l":          "Influent BOD (mg/L)",
        "influent_tkn_mg_l":          "Influent TKN (mg/L)",
        "influent_nh4_mg_l":          "Influent NH₄ (mg/L)",
        "influent_tss_mg_l":          "Influent TSS (mg/L)",
        "effluent_tn_mg_l":           "Effluent TN target (mg/L)",
        "effluent_nh4_mg_l":          "Effluent NH₄ target (mg/L)",
        "effluent_tp_mg_l":           "Effluent TP target (mg/L)",
        "electricity_price_per_kwh":  "Electricity price ($/kWh)",
    }
    for key, label in required.items():
        val = get(key)
        if val is None or val == 0:
            f("I0", Severity.FAIL,
              f"Required input missing or zero: {label}",
              metric=key, rec=f"Enter a valid value for {label}")

    # Short-circuit: can't do plausibility checks without basic values
    bod  = get("influent_bod_mg_l") or 0
    cod  = get("influent_cod_mg_l") or 0
    tkn  = get("influent_tkn_mg_l") or 0
    nh4  = get("influent_nh4_mg_l") or 0
    tp   = get("influent_tp_mg_l") or 0
    flow = get("design_flow_mld") or 0
    temp = get("influent_temperature_celsius") or 20.0
    eff_tn  = get("effluent_tn_mg_l") or 0
    eff_nh4 = get("effluent_nh4_mg_l") or 0
    peak_f  = get("peak_flow_factor") or 2.5

    # ── B. Physical consistency ────────────────────────────────────────────
    if cod > 0 and bod > 0 and cod < bod:
        f("I1", Severity.FAIL,
          f"COD ({cod} mg/L) < BOD ({bod} mg/L) — physically impossible",
          metric="influent_cod_mg_l",
          expected=f"COD ≥ BOD ({bod} mg/L)",
          actual=f"{cod} mg/L",
          rec="Correct influent COD — must be ≥ BOD at all times")

    if tkn > 0 and nh4 > 0 and nh4 > tkn:
        f("I2", Severity.FAIL,
          f"NH₄ ({nh4} mg/L) > TKN ({tkn} mg/L) — NH₄ is a subset of TKN",
          metric="influent_nh4_mg_l",
          expected=f"NH₄ ≤ TKN ({tkn} mg/L)",
          actual=f"{nh4} mg/L",
          rec="Correct influent NH₄ — NH₄-N cannot exceed total TKN")

    # ── C. Plausibility ranges ─────────────────────────────────────────────
    plausibility = [
        ("design_flow_mld",         flow,   0.1,  500,   "Flow (ML/day)"),
        ("influent_bod_mg_l",       bod,    50,   800,   "Influent BOD (mg/L)"),
        ("influent_tkn_mg_l",       tkn,    15,   120,   "Influent TKN (mg/L)"),
        ("influent_tp_mg_l",        tp,     0.5,  20,    "Influent TP (mg/L)"),
        ("influent_temperature_celsius", temp, 5, 35,    "Temperature (°C)"),
        ("peak_flow_factor",        peak_f, 1.2,  5.0,   "Peak flow factor"),
        ("electricity_price_per_kwh",
            get("electricity_price_per_kwh") or 0, 0.05, 0.50, "Electricity price ($/kWh)"),
    ]
    for key, val, lo, hi, label in plausibility:
        if val and not (lo <= val <= hi):
            sev = Severity.FAIL if (val < lo * 0.5 or val > hi * 2) else Severity.WARN
            f("I3", sev,
              f"{label} = {val} is outside plausible range [{lo}–{hi}]",
              metric=key,
              expected=f"{lo}–{hi}",
              actual=str(val),
              rec=f"Verify {label} — typical municipal range: {lo}–{hi}")

    # ── D. Engineering warning checks ─────────────────────────────────────
    # COD:TKN ratio for denitrification
    if cod > 0 and tkn > 0:
        cod_tkn = cod / tkn
        if cod_tkn < 4.5:
            f("I4", Severity.WARN,
              f"COD:TKN = {cod_tkn:.1f} — severely carbon-limited. TN removal will be restricted.",
              metric="cod_tkn_ratio",
              expected="≥ 7.0 for reliable TN removal",
              actual=f"{cod_tkn:.1f}",
              rec="Consider supplemental carbon (methanol) or primary sludge fermentation")
        elif cod_tkn < 7.0:
            f("I4", Severity.WARN,
              f"COD:TKN = {cod_tkn:.1f} — partial denitrification only without supplemental carbon.",
              metric="cod_tkn_ratio",
              expected="≥ 7.0",
              actual=f"{cod_tkn:.1f}",
              rec="Assess carbon source adequacy before committing to TN targets")

    # Temperature nitrification warning
    if temp < 12.0:
        f("I5", Severity.WARN,
          f"Temperature {temp}°C — nitrification is unreliable. Only MABR achieves NH₄<3 mg/L without intervention.",
          metric="influent_temperature_celsius",
          expected="≥ 12°C for reliable nitrification",
          actual=f"{temp}°C",
          rec="Consider thermal management or MABR for cold-climate sites")
    elif temp < 15.0:
        f("I5", Severity.WARN,
          f"Temperature {temp}°C — nitrification is marginal. Verify SRT adequacy.",
          metric="influent_temperature_celsius",
          rec="Increase SRT or consider IFAS/MABR augmentation")

    # Tight NH₄ target
    if eff_nh4 > 0 and eff_nh4 < 2.0:
        f("I6", Severity.INFO,
          f"Tight NH₄ target ({eff_nh4} mg/L) — confirm MABR or IFAS included in comparison.",
          metric="effluent_nh4_mg_l",
          rec="At tight NH₄ limits, conventional BNR may fail — include biofilm-augmented options")

    # Tight TN target
    if eff_tn > 0 and eff_tn < 5.0:
        f("I7", Severity.INFO,
          f"Tight TN target ({eff_tn} mg/L) — near-complete denitrification required. "
          "Supplemental carbon likely needed.",
          metric="effluent_tn_mg_l",
          rec="Evaluate methanol dosing and extended SRT for TN < 5 mg/L")

    # Reuse / advanced polishing flag
    eff_tss = get("effluent_tss_mg_l") or 10
    eff_bod = get("effluent_bod_mg_l") or 10
    if eff_tss < 5 or eff_bod < 5:
        f("I8", Severity.INFO,
          f"Effluent targets (TSS={eff_tss}, BOD={eff_bod} mg/L) indicate reuse / advanced polishing. "
          "MBR or tertiary filtration required.",
          rec="Include MBR in technology comparison for reuse-grade effluent")

    return QAResult(findings=findings)
