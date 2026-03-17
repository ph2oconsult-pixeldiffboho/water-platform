"""
domains/wastewater/technology_fit.py

Technology Fit Indicator Engine
================================
Evaluates how well each treatment technology suits the scenario
operating conditions. Produces green/amber/red ratings with brief
explanations for use in the planning comparison tool.

Basis: Engineering judgment from published literature and industry experience.
Not a substitute for detailed design — screening-level guidance only.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class FitLevel(Enum):
    GOOD        = "good"        # Technology well-suited to these conditions
    CONDITIONAL = "conditional" # Suitable with caveats or design measures
    POOR        = "poor"        # Significant disadvantage or risk in these conditions


@dataclass
class FitCriterion:
    """A single fit criterion result."""
    criterion: str       # e.g. "Temperature", "Footprint", "COD:TKN"
    level: FitLevel
    reason: str          # One-line explanation


@dataclass
class TechnologyFitResult:
    """Overall fit assessment for one technology in one scenario."""
    tech_code: str
    tech_label: str
    overall_level: FitLevel
    criteria: List[FitCriterion] = field(default_factory=list)
    summary: str = ""

    @property
    def icon(self) -> str:
        return {"good": "🟢", "conditional": "🟡", "poor": "🔴"}[self.overall_level.value]

    @property
    def label(self) -> str:
        return {"good": "Good fit", "conditional": "Conditional fit",
                "poor": "Poor fit"}[self.overall_level.value]


# ── Technology capability matrix ─────────────────────────────────────────────
# Thresholds below which a technology has specific challenges

_TECH_LABELS = {
    "bnr":            "BNR (Activated Sludge)",
    "granular_sludge":"Aerobic Granular Sludge",
    "mabr_bnr":       "MABR + BNR",
    "bnr_mbr":        "BNR + MBR",
    "ifas_mbbr":      "IFAS / MBBR",
    "ad_chp":         "Anaerobic Digestion + CHP",
    "anmbr":          "Anaerobic MBR",
    "adv_reuse":      "Advanced Reuse (UF+RO+UV)",
    "sidestream_pna": "Sidestream PN/A (Anammox)",
    "thermal_biosolids": "Thermal Biosolids",
    "tertiary_filt":  "Tertiary Filtration",
    "cpr":            "Chemical P Removal",
    "mob":            "Mobile Organic Biofilm",
}


def assess_technology_fit(
    tech_code: str,
    inputs: Any,          # WastewaterInputs
    tech_performance: Dict[str, Any],  # from domain outputs
) -> TechnologyFitResult:
    """
    Evaluate technology fit for the given scenario inputs and calculated performance.

    Parameters
    ----------
    tech_code : str
    inputs : WastewaterInputs
    tech_performance : dict  from technology_performance[tech_code]
    """
    label = _TECH_LABELS.get(tech_code, tech_code.upper())
    criteria: List[FitCriterion] = []

    T       = getattr(inputs, "influent_temperature_celsius", 20) or 20
    peak    = getattr(inputs, "peak_flow_factor", 2.5) or 2.5
    eff_tn  = getattr(inputs, "effluent_tn_mg_l", 10) or 10
    eff_tp  = getattr(inputs, "effluent_tp_mg_l", 1) or 1
    eff_nh4 = getattr(inputs, "effluent_nh4_mg_l", 5) or 5
    eff_tss = getattr(inputs, "effluent_tss_mg_l", 10) or 10
    flow    = getattr(inputs, "design_flow_mld", 10) or 10
    bod     = getattr(inputs, "influent_bod_mg_l", 250) or 250
    tkn     = getattr(inputs, "influent_tkn_mg_l", 45) or 45
    cod_tkn = bod * 2.0 / max(tkn, 1)
    is_reuse_quality = eff_tss <= 5 or eff_tn <= 5

    # ── BNR ───────────────────────────────────────────────────────────────
    if tech_code == "bnr":
        criteria.append(_temperature_bnr(T))
        criteria.append(_cod_tkn_bnr(cod_tkn))
        criteria.append(_tn_bnr(eff_tn))
        criteria.append(_footprint_bnr(flow))
        criteria.append(_reuse_bnr(is_reuse_quality, eff_tss))

    # ── Aerobic Granular Sludge ────────────────────────────────────────────
    elif tech_code == "granular_sludge":
        criteria.append(_temperature_ags(T))
        criteria.append(_cod_tkn_ags(cod_tkn))
        criteria.append(_tp_ags(eff_tp))
        criteria.append(_footprint_ags())
        criteria.append(_peak_ags(peak))

    # ── MABR + BNR ────────────────────────────────────────────────────────
    elif tech_code == "mabr_bnr":
        criteria.append(_temperature_mabr(T))
        criteria.append(_nh4_mabr(eff_nh4))
        criteria.append(_maturity_mabr())
        criteria.append(_cod_tkn_bnr(cod_tkn))  # same carbon limit as BNR

    # ── BNR + MBR ─────────────────────────────────────────────────────────
    elif tech_code == "bnr_mbr":
        criteria.append(_temperature_bnr(T))
        criteria.append(_reuse_mbr(is_reuse_quality))
        criteria.append(_footprint_mbr())
        criteria.append(_opex_mbr(flow))
        criteria.append(_cod_tkn_bnr(cod_tkn))

    # ── IFAS / MBBR ───────────────────────────────────────────────────────
    elif tech_code == "ifas_mbbr":
        criteria.append(_temperature_ifas(T))
        criteria.append(_cod_tkn_ifas(cod_tkn))
        criteria.append(_tn_ifas(eff_tn))
        criteria.append(_nitrif_ifas(eff_nh4))

    # Fallback for other technologies
    else:
        criteria.append(FitCriterion(
            "General applicability", FitLevel.CONDITIONAL,
            "Specialist technology — verify suitability for this application."
        ))

    # ── Overall level: worst of all criteria ─────────────────────────────
    if any(c.level == FitLevel.POOR for c in criteria):
        overall = FitLevel.POOR
    elif any(c.level == FitLevel.CONDITIONAL for c in criteria):
        overall = FitLevel.CONDITIONAL
    else:
        overall = FitLevel.GOOD

    # ── Summary sentence ─────────────────────────────────────────────────
    poor_reasons = [c.reason for c in criteria if c.level == FitLevel.POOR]
    cond_reasons = [c.reason for c in criteria if c.level == FitLevel.CONDITIONAL]
    if poor_reasons:
        summary = "Not recommended: " + "; ".join(poor_reasons[:2])
    elif cond_reasons:
        summary = "Suitable with caveats: " + "; ".join(cond_reasons[:2])
    else:
        summary = f"{label} is well-suited to these operating conditions."

    return TechnologyFitResult(
        tech_code=tech_code,
        tech_label=label,
        overall_level=overall,
        criteria=criteria,
        summary=summary,
    )


def assess_all_technologies(
    tech_codes: List[str],
    inputs: Any,
    tech_performances: Dict[str, Dict],
) -> Dict[str, TechnologyFitResult]:
    """Assess fit for all technologies in a scenario."""
    return {
        code: assess_technology_fit(code, inputs, tech_performances.get(code, {}))
        for code in tech_codes
    }


# ── Criterion helper functions ────────────────────────────────────────────────

def _temperature_bnr(T: float) -> FitCriterion:
    if T < 10:
        return FitCriterion("Temperature", FitLevel.POOR,
            f"{T:.0f}°C — nitrification unreliable; SRT extension required")
    if T < 15:
        return FitCriterion("Temperature", FitLevel.CONDITIONAL,
            f"{T:.0f}°C — marginal nitrification; SRT must be extended")
    return FitCriterion("Temperature", FitLevel.GOOD,
        f"{T:.0f}°C — adequate for reliable BNR nitrification")


def _temperature_ags(T: float) -> FitCriterion:
    if T < 10:
        return FitCriterion("Temperature", FitLevel.POOR,
            f"{T:.0f}°C — granule fragmentation risk; NOT recommended (van Dijk 2020)")
    if T < 15:
        return FitCriterion("Temperature", FitLevel.CONDITIONAL,
            f"{T:.0f}°C — granule stability risk; need thermal management or SRT extension")
    return FitCriterion("Temperature", FitLevel.GOOD,
        f"{T:.0f}°C — suitable for stable granule formation")


def _temperature_mabr(T: float) -> FitCriterion:
    if T < 10:
        return FitCriterion("Temperature", FitLevel.CONDITIONAL,
            f"{T:.0f}°C — MABR biofilm more cold-tolerant than suspended growth")
    return FitCriterion("Temperature", FitLevel.GOOD,
        f"{T:.0f}°C — MABR operates reliably across temperature range")


def _temperature_ifas(T: float) -> FitCriterion:
    if T < 10:
        return FitCriterion("Temperature", FitLevel.POOR,
            f"{T:.0f}°C — IFAS biofilm nitrification unreliable")
    if T < 13:
        return FitCriterion("Temperature", FitLevel.CONDITIONAL,
            f"{T:.0f}°C — increase media area by 25–40% for cold climate")
    return FitCriterion("Temperature", FitLevel.GOOD,
        f"{T:.0f}°C — adequate for IFAS nitrification")


def _cod_tkn_bnr(cod_tkn: float) -> FitCriterion:
    if cod_tkn < 4.5:
        return FitCriterion("COD:TKN", FitLevel.POOR,
            f"COD/TKN={cod_tkn:.1f} — severely carbon-limited; supplemental carbon essential")
    if cod_tkn < 7:
        return FitCriterion("COD:TKN", FitLevel.CONDITIONAL,
            f"COD/TKN={cod_tkn:.1f} — marginal carbon; supplemental carbon likely needed")
    return FitCriterion("COD:TKN", FitLevel.GOOD,
        f"COD/TKN={cod_tkn:.1f} — adequate carbon for denitrification")


def _cod_tkn_ags(cod_tkn: float) -> FitCriterion:
    if cod_tkn < 5:
        return FitCriterion("COD:TKN", FitLevel.POOR,
            f"COD/TKN={cod_tkn:.1f} — granule feast/famine requires BOD/TN > 5")
    if cod_tkn < 7:
        return FitCriterion("COD:TKN", FitLevel.CONDITIONAL,
            f"COD/TKN={cod_tkn:.1f} — marginal for stable granule formation")
    return FitCriterion("COD:TKN", FitLevel.GOOD,
        f"COD/TKN={cod_tkn:.1f} — adequate for AGS feast/famine cycle")


def _cod_tkn_ifas(cod_tkn: float) -> FitCriterion:
    if cod_tkn < 5:
        return FitCriterion("COD:TKN", FitLevel.POOR,
            f"COD/TKN={cod_tkn:.1f} — IFAS lacks dedicated anoxic zone; TN target unachievable")
    if cod_tkn < 8:
        return FitCriterion("COD:TKN", FitLevel.CONDITIONAL,
            f"COD/TKN={cod_tkn:.1f} — add external carbon or dedicated anoxic stage")
    return FitCriterion("COD:TKN", FitLevel.GOOD,
        f"COD/TKN={cod_tkn:.1f} — IFAS TN removal feasible")


def _tn_bnr(eff_tn: float) -> FitCriterion:
    if eff_tn < 5:
        return FitCriterion("TN target", FitLevel.CONDITIONAL,
            f"TN < {eff_tn:.0f} mg/L — requires extended SRT and supplemental carbon")
    return FitCriterion("TN target", FitLevel.GOOD,
        f"TN = {eff_tn:.0f} mg/L — achievable with standard BNR anoxic zones")


def _tn_ifas(eff_tn: float) -> FitCriterion:
    if eff_tn < 5:
        return FitCriterion("TN target", FitLevel.POOR,
            f"TN < {eff_tn:.0f} mg/L — IFAS limited denitrification cannot reliably achieve")
    if eff_tn < 8:
        return FitCriterion("TN target", FitLevel.CONDITIONAL,
            f"TN = {eff_tn:.0f} mg/L — add supplemental carbon or dedicated anoxic zone")
    return FitCriterion("TN target", FitLevel.GOOD,
        f"TN = {eff_tn:.0f} mg/L — achievable with IFAS")


def _tp_ags(eff_tp: float) -> FitCriterion:
    if eff_tp < 0.3:
        return FitCriterion("TP target", FitLevel.CONDITIONAL,
            f"TP < {eff_tp:.1f} mg/L — requires chemical P polish (ferric chloride)")
    return FitCriterion("TP target", FitLevel.GOOD,
        f"TP = {eff_tp:.1f} mg/L — achievable with AGS biological P removal")


def _footprint_bnr(flow: float) -> FitCriterion:
    # Footprint is only a concern if explicitly constrained — it is not a
    # general disadvantage. BNR is a Good fit unless site is known to be tight.
    return FitCriterion("Footprint", FitLevel.GOOD,
        "BNR footprint is standard for activated sludge. "
        "If site is constrained, AGS or MBR offer 30–50% reduction.")


def _footprint_ags() -> FitCriterion:
    return FitCriterion("Footprint", FitLevel.GOOD,
        "AGS SBR: 30–40% smaller footprint than BNR + clarifiers (no separate clarifiers)")


def _footprint_mbr() -> FitCriterion:
    return FitCriterion("Footprint", FitLevel.GOOD,
        "MBR: smallest footprint/MLD — no secondary clarifiers")


def _reuse_bnr(is_reuse_quality: bool, eff_tss: float) -> FitCriterion:
    if is_reuse_quality:
        return FitCriterion("Reuse readiness", FitLevel.POOR,
            f"BNR cannot achieve TSS ≤{eff_tss:.0f} mg/L — secondary clarifiers insufficient for reuse")
    return FitCriterion("Reuse readiness", FitLevel.GOOD,
        "Standard effluent limits — BNR secondary treatment adequate")


def _reuse_mbr(is_reuse_quality: bool) -> FitCriterion:
    if is_reuse_quality:
        return FitCriterion("Reuse readiness", FitLevel.GOOD,
            "MBR provides TSS < 1 mg/L — ideal pre-treatment for reuse AWT")
    return FitCriterion("Reuse readiness", FitLevel.GOOD,
        "MBR high effluent quality — suitable for reuse pathway")


def _opex_mbr(flow: float) -> FitCriterion:
    if flow > 30:
        return FitCriterion("OPEX profile", FitLevel.CONDITIONAL,
            f"{flow:.0f} MLD — membrane replacement cost is material at large scale")
    return FitCriterion("OPEX profile", FitLevel.CONDITIONAL,
        "Membrane replacement adds ~$300-500k/yr at 10 MLD — plan sinking fund")


def _nh4_mabr(eff_nh4: float) -> FitCriterion:
    if eff_nh4 <= 2:
        return FitCriterion("NH₄ target", FitLevel.GOOD,
            f"NH₄ < {eff_nh4:.1f} mg/L — MABR biofilm well-suited to low-NH₄ targets")
    return FitCriterion("NH₄ target", FitLevel.GOOD,
        f"NH₄ = {eff_nh4:.1f} mg/L — standard, MABR aeration efficiency advantage applies")


def _maturity_mabr() -> FitCriterion:
    return FitCriterion("Technology maturity", FitLevel.CONDITIONAL,
        "MABR: <50 full-scale references globally (2024) — allow for vendor pilot data requirement")


def _peak_ags(peak: float) -> FitCriterion:
    if peak > 3.5:
        return FitCriterion("Peak flow", FitLevel.CONDITIONAL,
            f"Peak {peak:.1f}× — SBR needs larger flow balance tank; confirm cycle time adequate")
    return FitCriterion("Peak flow", FitLevel.GOOD,
        f"Peak {peak:.1f}× — within typical AGS SBR operating range")


def _nitrif_ifas(eff_nh4: float) -> FitCriterion:
    if eff_nh4 <= 1:
        return FitCriterion("NH₄ target", FitLevel.GOOD,
            f"NH₄ < {eff_nh4:.1f} mg/L — IFAS biofilm enhances nitrification capacity")
    return FitCriterion("NH₄ target", FitLevel.GOOD,
        f"NH₄ = {eff_nh4:.1f} mg/L — IFAS suitable")
