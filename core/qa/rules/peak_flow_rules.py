"""
core/qa/rules/peak_flow_rules.py

Peak flow / operability checks — the checklist's biggest gap.

P1 — BNR clarifier surface overflow rate (SOR) at peak flow
P2 — BNR MLSS dilution at peak flow
P3 — AGS SBR fill ratio at peak (now computed in granular_sludge.py; surfaced here)
P4 — Peak flow assessed at all (warn if no peak data exists)

Ref: Metcalf 5th Ed Table 7-20 (peak hydraulic loading)
     WEF MOP 8 secondary clarifier design
     Royal HaskoningDHV Nereda design guidelines
"""
from __future__ import annotations
from typing import Any
from core.qa.qa_model import QAFinding, QAResult, Severity


def run(scenario: Any, tech_code: str = None) -> QAResult:
    findings = []
    sn = getattr(scenario, "scenario_name", None)
    di = scenario.domain_inputs or {}
    tp_all = (scenario.domain_specific_outputs or {}).get("technology_performance", {})
    tp = tp_all.get(tech_code, {}) if tech_code else {}

    def f(code, sev, msg, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="PeakFlow", severity=sev, message=msg,
            scenario=sn, metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    flow_mld    = di.get("design_flow_mld") or 0
    peak_factor = tp.get("peak_flow_factor") or di.get("peak_flow_factor") or 1.5
    peak_flow   = flow_mld * peak_factor * 1000  # m³/d

    # ── P1: BNR clarifier SOR at peak ─────────────────────────────────────
    if tech_code == "bnr":
        clar_area = tp.get("clarifier_area_m2") or 0
        if clar_area > 0 and peak_flow > 0:
            sor_peak = (peak_flow / 24.0) / clar_area   # m/hr
            sor_limit = 1.6   # m/hr (Metcalf Table 7-20, conservative)
            sor_warn  = 1.4

            if sor_peak > sor_limit:
                f("P1", Severity.FAIL,
                  f"Clarifier SOR at peak {peak_factor:.1f}× = {sor_peak:.2f} m/hr "
                  f"exceeds maximum guideline {sor_limit:.1f} m/hr "
                  f"(area={clar_area:.0f} m², peak flow={peak_flow/24:.0f} m³/hr). "
                  "Risk of solids carryover and effluent quality failure.",
                  metric="clarifier_area_m2",
                  expected=f"SOR ≤ {sor_limit:.1f} m/hr at peak",
                  actual=f"{sor_peak:.2f} m/hr",
                  rec="Increase clarifier area or reduce peak flow factor via flow equalisation")
            elif sor_peak > sor_warn:
                f("P1", Severity.WARN,
                  f"Clarifier SOR at peak {peak_factor:.1f}× = {sor_peak:.2f} m/hr "
                  f"(marginal — guideline {sor_limit:.1f} m/hr). "
                  f"Area={clar_area:.0f} m², peak={peak_flow/24:.0f} m³/hr.",
                  metric="clarifier_area_m2",
                  expected=f"SOR ≤ {sor_limit:.1f} m/hr",
                  actual=f"{sor_peak:.2f} m/hr",
                  rec="Confirm with dynamic simulation; consider clarifier uprating")
            else:
                f("P1", Severity.INFO,
                  f"Clarifier SOR at peak = {sor_peak:.2f} m/hr ✅ (guideline ≤ {sor_limit:.1f} m/hr).",
                  metric="clarifier_area_m2")
        else:
            f("P4", Severity.WARN,
              "BNR clarifier area not found — peak SOR cannot be checked.",
              rec="Ensure clarifier_area_m2 is populated in BNR technology outputs")

    # ── P2: BNR MLSS dilution at peak ─────────────────────────────────────
    if tech_code == "bnr":
        mlss_design = tp.get("mlss_mg_l") or di.get("mlss_mg_l") or 4000
        # At peak wet weather flow, dilution from stormwater reduces MLSS
        # Simplified: MLSS_peak ≈ MLSS_design × (DWF / WWF) = MLSS / peak_factor
        # This is conservative — SRT control will partially compensate
        mlss_peak = mlss_design / peak_factor
        mlss_min  = 2000   # mg/L minimum for biological function
        mlss_warn = 2500

        if mlss_peak < mlss_min:
            f("P2", Severity.FAIL,
              f"MLSS at peak {peak_factor:.1f}× estimated {mlss_peak:.0f} mg/L "
              f"(design {mlss_design:.0f} ÷ {peak_factor:.1f}) — "
              f"below minimum {mlss_min:.0f} mg/L for stable biological function. "
              "Effluent quality failure likely at peak flow.",
              metric="mlss_mg_l",
              expected=f"MLSS ≥ {mlss_min:.0f} mg/L at peak",
              actual=f"~{mlss_peak:.0f} mg/L",
              rec="Increase SRT or MLSS setpoint, or reduce peak flow via equalization")
        elif mlss_peak < mlss_warn:
            f("P2", Severity.WARN,
              f"MLSS at peak {peak_factor:.1f}× estimated {mlss_peak:.0f} mg/L "
              f"(design {mlss_design:.0f}): marginal. "
              f"Monitor biokinetics at peak flow conditions.",
              metric="mlss_mg_l",
              rec="Consider higher design MLSS or SRT for cold/peak resilience")
        else:
            f("P2", Severity.INFO,
              f"MLSS at peak estimated {mlss_peak:.0f} mg/L ✅ "
              f"(design {mlss_design:.0f} ÷ {peak_factor:.1f} ≥ {mlss_warn:.0f} mg/L).")

    # ── P3: AGS SBR fill ratio at peak (computed in granular_sludge.py) ────
    if tech_code == "granular_sludge":
        fill_ratio = tp.get("peak_fill_ratio")
        feed_per_fill = tp.get("feed_per_fill_m3")

        if fill_ratio is None:
            f("P4", Severity.WARN,
              "AGS peak flow fill ratio not computed — cycle compression not checked.",
              rec="Ensure peak_fill_ratio is calculated in granular_sludge technology outputs")
        elif fill_ratio > 1.5:
            # Severe — genuinely risky at concept stage
            f("P3", Severity.FAIL,
              f"AGS SBR fill ratio at peak = {fill_ratio:.2f}× guideline "
              f"(feed {feed_per_fill:.0f} m³/fill event exceeds 50% reactor volume). "
              "Granule stability at risk; treatment cycle compression likely at this level.",
              metric="peak_fill_ratio",
              expected="Fill ratio ≤ 1.0× (≤ 50% reactor volume)",
              actual=f"{fill_ratio:.2f}×",
              rec="Increase flow balance tank volume or add 4th SBR reactor. "
                  "Confirm with detailed hydraulic modelling at next stage.")
        elif fill_ratio > 1.0:
            # Marginal — flag for next stage but don't block report
            f("P3", Severity.WARN,
              f"AGS SBR peak fill ratio = {fill_ratio:.2f}× guideline "
              f"(feed {feed_per_fill:.0f} m³/fill event vs 50% reactor volume limit). "
              "Flag for detailed hydraulic design — consider increasing FBT or adding SBR reactor.",
              metric="peak_fill_ratio",
              expected="Fill ratio ≤ 1.0× (≤ 50% reactor volume)",
              actual=f"{fill_ratio:.2f}×",
              rec="Increase flow balance tank volume or add 4th SBR reactor. "
                  "At concept stage this is a design flag, not a blocking issue.")
        elif fill_ratio > 0.75:
            f("P3", Severity.WARN,
              f"AGS SBR fill ratio at peak = {fill_ratio:.2f}× guideline (marginal). "
              f"Feed {feed_per_fill:.0f} m³ per fill event.",
              metric="peak_fill_ratio",
              rec="Verify FBT sizing with detailed hydraulic modelling")
        else:
            f("P3", Severity.INFO,
              f"AGS SBR fill check ✅ — fill ratio {fill_ratio:.2f}× guideline at peak.")

    # ── P4: Peak flow not assessed at all ─────────────────────────────────
    if tech_code not in ("bnr", "granular_sludge", "bnr_mbr", "ifas_mbbr", "mabr_bnr"):
        pass   # unknown technology
    elif flow_mld == 0:
        f("P4", Severity.WARN,
          "Design flow not set — peak flow operability cannot be assessed.",
          rec="Set design flow before running peak flow checks")

    return QAResult(findings=findings)
