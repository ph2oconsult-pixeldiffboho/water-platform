"""
apps/wastewater_app/compliance_layer.py

Percentile Compliance Logic Layer — Production V1
==================================================

A risk-based reliability framework for assessing whether a proposed
treatment pathway is likely to achieve:

  → Median compliance          (process capability)
  → 95th percentile compliance (design robustness and regulatory confidence)
  → 99th percentile / event    (infrastructure resilience — when requested)

Design principles
-----------------
1. This is NOT a dynamic process simulator.
2. Precise percentile predictions (e.g. "95th percentile TN = 2.87 mg/L")
   are never generated. They would require a validated statistical or
   process model with site-specific calibration data that does not exist
   at concept / pre-FEED stage.
3. All outputs use structured outcome classes: "Achievable", "Conditional",
   "Not yet credible". These represent reliability judgements, not
   simulation outputs.
4. Decision variables (carbon fractionation, regulatory target basis,
   dewatering capacity, winter stability) are classified as such —
   not buried as risk items.
5. Confidence reflects data maturity. Unresolved decision variables
   always reduce confidence.

Terminology
-----------
"Achievable"        — process pathway is sound; central performance likely meets target.
"Conditional"       — achievable only if specified enabling conditions are met.
"Not yet credible"  — further data, additional process stage, or infrastructure
                      intervention required before this assessment can be made.

Main entry point
----------------
  build_compliance_report(pathway, feasibility, plant_context) -> ComplianceReport
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apps.wastewater_app.stack_generator import (
    UpgradePathway,
    CT_HYDRAULIC, CT_SETTLING, CT_NITRIFICATION,
    CT_TN_POLISH, CT_TP_POLISH, CT_BIOLOGICAL, CT_WET_WEATHER,
    TI_COMAG, TI_BIOMAG, TI_MABR, TI_IFAS, TI_HYBAS, TI_PDNA,
    TI_BARDENPHO, TI_RECYCLE_OPT, TI_DENFILTER, TI_TERT_P, TI_EQ_BASIN,
)
from apps.wastewater_app.feasibility_layer import FeasibilityReport

# ── Outcome constants ──────────────────────────────────────────────────────────
ACHIEVABLE        = "Achievable"
CONDITIONAL       = "Conditional"
NOT_YET_CREDIBLE  = "Not yet credible"

# ── Target basis constants ─────────────────────────────────────────────────────
BASIS_MEDIAN = "Median"
BASIS_P95    = "95th percentile"
BASIS_P99    = "99th percentile / event"

# ── Confidence constants ───────────────────────────────────────────────────────
CONF_HIGH   = "High"
CONF_MEDIUM = "Medium"
CONF_LOW    = "Low"

# ── Disclaimer (always attached to all outputs) ────────────────────────────────
DISCLAIMER = (
    "This assessment is a reliability framework for concept / pre-FEED evaluation. "
    "It does not constitute a validated statistical or dynamic process model. "
    "Precise percentile effluent values are not generated: they require site-specific "
    "calibration data that does not yet exist. Outcomes should be interpreted as "
    "engineering judgements on process robustness, not deterministic predictions."
)


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class ParameterCompliance:
    """Compliance reliability assessment for one effluent parameter."""
    parameter:          str    # "NH₄", "TN", "TP", "TSS"
    target_mg_l:        float
    target_basis:       str    # BASIS_MEDIAN / BASIS_P95 / BASIS_P99

    # Median assessment
    median_outcome:     str    # ACHIEVABLE / CONDITIONAL / NOT_YET_CREDIBLE
    median_conditions:  List[str]   # enabling conditions for median
    median_uncertainty: str         # dominant unresolved variable

    # 95th percentile assessment
    p95_outcome:        str
    p95_conditions:     List[str]
    p95_uncertainty:    str

    # 99th percentile (only populated when basis = P99)
    p99_outcome:        Optional[str]  = None
    p99_conditions:     List[str]      = field(default_factory=list)
    p99_uncertainty:    str            = ""

    # Overall
    confidence:         str            = CONF_MEDIUM
    decision_variables: List[str]      = field(default_factory=list)
    design_implication: str            = ""


@dataclass
class ReliabilityDriver:
    """One reliability driver and its impact on percentile compliance."""
    driver:      str   # name from the eight-driver framework
    level:       str   # "High" / "Medium" / "Low" impact
    explanation: str
    affects:     List[str]   # which parameters it threatens


@dataclass
class BrownfieldComplianceNote:
    """
    Explicit note on how percentile basis interacts with the BF/GF decision.
    This is the critical intersection: brownfield may achieve median targets
    but may not credibly deliver 95th percentile compliance without
    additional infrastructure that tips the balance toward replacement.
    """
    brownfield_viable_for_median:   bool
    brownfield_viable_for_p95:      bool
    compliance_drives_replacement:  bool   # True if p95 drives toward GF
    explanation:                    str


@dataclass
class ComplianceReport:
    """Full Percentile Compliance Logic Layer output."""
    parameters:         List[ParameterCompliance]
    drivers:            List[ReliabilityDriver]
    brownfield_note:    BrownfieldComplianceNote
    overall_confidence: str
    disclaimer:         str
    # Validation flags
    no_precise_percentile_values:   bool   # always True — confirms the rule
    decision_variables_identified:  bool
    brownfield_interaction_stated:  bool
    stack_compliance_gap:     bool = False
    stack_consistency_note:   str  = ""
    operator_capability_flag: bool = False
    operator_capability_note: str  = ""
    # Phase 2 realism
    sludge_flag:          str   = ""
    diagnosis_statement:  str   = ""  # plain-language cause of failure
    closure_statement:    str   = ""  # what is required to achieve compliance
    escalation_note:      str   = ""  # escalation mode if triggered
    effective_cod_tn_val: float = 0.
    # Confidence score layer
    confidence_score:   int  = 100
    confidence_label:   str  = "High"
    confidence_drivers: list = None  # List[str] — top penalty drivers
    delivery_considerations: list = None  # List[str] — institutional/operational rationale

    def __post_init__(self):
        if self.confidence_drivers is None:
            object.__setattr__(self, 'confidence_drivers', [])


# ── Internal helpers ───────────────────────────────────────────────────────────

def _cold(ctx: Dict) -> bool:
    return (bool(ctx.get("cold_temperature", False)) or
            (ctx.get("temp_celsius") is not None and
             float(ctx.get("temp_celsius", 20.)) <= 12.))


def _aer_constrained(ctx: Dict) -> bool:
    return bool(ctx.get("aeration_constrained", False))



# ── Phase 2 realism helpers ───────────────────────────────────────────────────

def _influent_tn_mg_l(ctx: Dict) -> float:
    v = ctx.get("tn_in_mg_l") or ctx.get("influent_tn_mg_l")
    if v: return float(v)
    cod_tn = ctx.get("cod_tn_ratio")
    # If we have cod_tn ratio, can't infer TN — return 0 (unknown)
    return 0.

def _influent_cod_mg_l(ctx: Dict) -> float:
    v = ctx.get("cod_mg_l") or ctx.get("influent_cod_mg_l")
    if v: return float(v)
    cod_tn = ctx.get("cod_tn_ratio")
    tn_in  = ctx.get("tn_in_mg_l") or ctx.get("influent_tn_mg_l")
    if cod_tn and tn_in:
        return float(cod_tn) * float(tn_in)
    return 0.

def _high_tkn_removal_required(tkn_in: float, tn_target: float) -> bool:
    if tkn_in <= 0: return False
    return ((tkn_in - tn_target) / tkn_in) >= 0.90

def _effective_cod_tn(cod_in: float, tkn_in: float) -> float:
    if tkn_in <= 0 or cod_in <= 0: return 999.
    return (cod_in * 0.60) / tkn_in

def _downgrade_outcome(outcome: str) -> str:
    if outcome == ACHIEVABLE:   return CONDITIONAL
    if outcome == CONDITIONAL:  return NOT_YET_CREDIBLE
    return outcome


def _carbon_limited(ctx: Dict) -> bool:
    return bool(ctx.get("carbon_limited_tn", False))


def _cod_tn_unknown(ctx: Dict) -> bool:
    return ctx.get("cod_tn_ratio") is None


def _flow_ratio(ctx: Dict) -> float:
    return float(ctx.get("flow_ratio", 1.0) or 1.0)


def _has_tech(pathway: UpgradePathway, *techs) -> bool:
    ts = {s.technology for s in pathway.stages}
    return any(t in ts for t in techs)


def _target_basis_from_ctx(ctx: Dict, param: str) -> str:
    key = f"{param}_target_basis"
    val = ctx.get(key, BASIS_MEDIAN)
    return val if val in (BASIS_MEDIAN, BASIS_P95, BASIS_P99) else BASIS_MEDIAN


def _confidence(low_count: int, med_count: int) -> str:
    if low_count >= 2:
        return CONF_LOW
    if low_count >= 1 or med_count >= 2:
        return CONF_MEDIUM
    return CONF_HIGH


# ── Parameter assessors ───────────────────────────────────────────────────────

def _assess_nh4(
    pathway: UpgradePathway,
    ctx: Dict,
    nh4_target: float,
    target_basis: str,
) -> ParameterCompliance:
    cold        = _cold(ctx)
    aer         = _aer_constrained(ctx)
    has_mabr    = _has_tech(pathway, TI_MABR)
    has_ifas    = _has_tech(pathway, TI_IFAS, TI_HYBAS)
    fr          = _flow_ratio(ctx)
    nitrification_tech = has_mabr or has_ifas

    # ── Median ────────────────────────────────────────────────────────────────
    if nitrification_tech:
        median_outcome = ACHIEVABLE
        median_conds = [
            "Nitrification technology (MABR or IFAS) correctly commissioned and stable.",
            "Aeration adequacy confirmed for the selected technology.",
            "SRT maintained above the winter minimum threshold.",
        ]
        median_unc = ("Winter commissioning timing — MABR biofilm establishment takes "
                      "4\u20138 weeks; underperformance during establishment is the "
                      "most likely median compliance risk.")
    elif cold and aer:
        median_outcome = CONDITIONAL
        median_conds   = [
            "Nitrification intensification (MABR) required — aeration is constrained "
            "and cold conditions reduce kinetics 40\u201350% vs design.",
        ]
        median_unc = "Blower capacity and cold temperature jointly constrain nitrification."
    else:
        median_outcome = CONDITIONAL
        median_conds   = ["Nitrification pathway must be established before NH\u2084 median compliance is credible."]
        median_unc     = "Nitrification SRT and aeration headroom."

    # ── 95th percentile ────────────────────────────────────────────────────────
    if not nitrification_tech:
        p95_outcome = NOT_YET_CREDIBLE
        p95_conds   = ["95th percentile NH\u2084 compliance requires a commissioned "
                       "nitrification intensification technology."]
        p95_unc     = "Absence of a confirmed nitrification upgrade pathway."
    elif cold and aer and not has_mabr:
        p95_outcome = CONDITIONAL
        p95_conds   = [
            "MABR or equivalent commissioned and stable across winter and summer.",
            "Biofilm establishment confirmed at correct temperature.",
            "Hydraulic stress does not cause biomass loss from secondary clarifiers.",
        ]
        p95_unc = "Winter nitrification stability — the dominant risk for 95th percentile NH\u2084 compliance."
    elif has_mabr:
        p95_outcome = CONDITIONAL
        p95_conds = [
            "MABR commissioned in spring (not winter) and NH\u2084 < 1 mg/L confirmed "
            "across one full summer + winter cycle before crediting 95th percentile reliability.",
            "Hydraulic attenuation adequate at peak flow events — clarifier washout "
            "during extreme peaks is the primary threat to 95th percentile compliance.",
            f"Peak flow ratio ({fr:.1f}\u00d7 ADWF) managed through CoMag or equivalent "
            "at peak events."
            if fr >= 2.5 else
            "Hydraulic loading within manageable range.",
        ]
        p95_unc = ("Seasonal nitrification stability — particularly the transition into "
                   "the first winter post-commissioning. One cold-season confirmation "
                   "is the minimum credible basis for 95th percentile NH\u2084 reliability.")
    else:
        p95_outcome = CONDITIONAL
        p95_conds   = ["Standard nitrification reliability conditions apply."]
        p95_unc     = "Seasonal performance variability."

    # DVs
    dvs = []
    if cold and aer:
        dvs.append("Winter nitrification stability — confirm MABR achieves NH\u2084 < 1 mg/L "
                   "across summer and winter before citing 95th percentile reliability.")
    if fr >= 3.0:
        dvs.append("Hydraulic attenuation at >3\u00d7 ADWF — percentile NH\u2084 reliability "
                   "is reduced without confirmed clarifier protection at extreme peaks.")

    conf = _confidence(
        low_count=(1 if (cold and aer and not has_mabr) else 0),
        med_count=(1 if (has_mabr and fr >= 3.0) else 0)
    )

    design = (
        f"NH\u2084 \u2264{nh4_target} mg/L at {target_basis}: "
        + ("MABR is required for 95th percentile reliability — IFAS cannot resolve "
           "the aeration constraint."
           if (cold and aer and not has_mabr and has_ifas) else
           "Spring commissioning and one full seasonal cycle are the minimum credible "
           "basis before 95th percentile reliability can be asserted."
           if has_mabr else
           "Nitrification intensification required for any credible percentile compliance claim.")
    )

    return ParameterCompliance(
        parameter="NH\u2084",
        target_mg_l=nh4_target,
        target_basis=target_basis,
        median_outcome=median_outcome,
        median_conditions=median_conds,
        median_uncertainty=median_unc,
        p95_outcome=p95_outcome,
        p95_conditions=p95_conds,
        p95_uncertainty=p95_unc,
        confidence=conf,
        decision_variables=dvs,
        design_implication=design,
    )


def _assess_tn(
    pathway: UpgradePathway,
    ctx: Dict,
    tn_target: float,
    target_basis: str,
) -> ParameterCompliance:
    carbon_lim  = _carbon_limited(ctx)
    cod_unknown = _cod_tn_unknown(ctx)
    has_bard    = _has_tech(pathway, TI_BARDENPHO, TI_RECYCLE_OPT)
    has_dnf     = _has_tech(pathway, TI_DENFILTER)
    has_mabr    = _has_tech(pathway, TI_MABR)
    cold        = _cold(ctx)
    fr          = _flow_ratio(ctx)

    # ── Median ────────────────────────────────────────────────────────────────
    if tn_target <= 3.0:
        if has_dnf and has_mabr:
            median_outcome = ACHIEVABLE
            median_conds = [
                "NH\u2084 < 1 mg/L established before DNF commissioning.",
                "Carbon sufficiency confirmed or external carbon dosing in place.",
                "DNF DO at filter inlet < 0.5 mg/L.",
            ]
            median_unc = "Carbon availability — COD fractionation must be confirmed."
        elif has_bard and not has_dnf:
            median_outcome = CONDITIONAL
            median_conds = [
                "TN \u22643 mg/L on biological optimisation alone is unlikely without "
                "confirmed carbon surplus and optimal Bardenpho performance.",
                "COD fractionation audit required before design to establish whether "
                "Bardenpho alone can achieve this target.",
            ]
            median_unc = ("Whether biological TN removal alone can reach \u22643 mg/L. "
                          "DNF will almost certainly be required.")
        else:
            median_outcome = NOT_YET_CREDIBLE
            median_conds   = ["TN \u22643 mg/L requires at minimum Bardenpho + nitrification stabilisation, "
                              "and DNF is likely required for median compliance."]
            median_unc     = "Process pathway is not yet sufficient for TN \u22643 mg/L."
    elif tn_target <= 5.0:
        if has_bard:
            median_outcome = CONDITIONAL
            median_conds = [
                "COD fractionation confirms carbon is not limiting (rbCOD:TN \u22654:1 "
                "in settled influent).",
                "Stable nitrification established — TN polishing depends on "
                "adequate NOx substrate.",
                "Bardenpho zone HRT correctly sized for winter denitrification kinetics.",
            ]
            median_unc = "Carbon availability — currently unconfirmed for this plant."
        else:
            median_outcome = CONDITIONAL
            median_conds   = ["Bardenpho or equivalent process optimisation required for TN \u22645 mg/L."]
            median_unc     = "TN polishing pathway not yet confirmed."
    else:
        median_outcome = (ACHIEVABLE if has_bard else CONDITIONAL)
        median_conds   = ["Standard biological TN removal with recycle optimisation."]
        median_unc     = "Carbon availability under seasonal variation."

    # ── 95th percentile ────────────────────────────────────────────────────────
    if tn_target <= 3.0:
        if has_dnf:
            if cod_unknown or carbon_lim:
                p95_outcome = CONDITIONAL
                p95_conds = [
                    "Carbon availability must be confirmed — COD fractionation is a "
                    "DECISION VARIABLE, not a risk item.",
                    "If rbCOD:TN < 4:1: external carbon dosing is mandatory; "
                    "without it, 95th percentile TN \u22643 mg/L is not credible.",
                    "NH\u2084 < 1 mg/L confirmed stable across summer and winter "
                    "before DNF commissioning.",
                    "Methanol dose control automated with online TN feedback.",
                ]
                p95_unc = ("Settled influent rbCOD:TN ratio — the dominant unresolved "
                           "variable for 95th percentile TN reliability.")
            else:
                p95_outcome = CONDITIONAL
                p95_conds = [
                    "DNF commissioned only after NH\u2084 gate is passed.",
                    "Methanol dosing automated and dual-supplied.",
                    "Cold-season DNF performance confirmed (methanol dose may need "
                    "to increase in winter due to lower denitrification kinetics).",
                ]
                p95_unc = "Winter denitrification kinetics in the DNF filter."
        else:
            p95_outcome = NOT_YET_CREDIBLE
            p95_conds = [
                "TN \u22643 mg/L at 95th percentile is not credible on biological "
                "optimisation alone unless carbon sufficiency is extraordinary.",
                "DNF is strongly indicated for 95th percentile reliability at this target.",
                "Carbon fractionation audit required before any 95th percentile "
                "TN compliance claim can be made.",
            ]
            p95_unc = ("Absence of tertiary denitrification and unresolved carbon "
                       "availability — the two dominant variables for 95th percentile "
                       "TN \u22643 mg/L reliability.")
    elif tn_target <= 5.0:
        if cod_unknown or carbon_lim:
            p95_outcome = CONDITIONAL
            p95_conds = [
                "Carbon fractionation audit required before 95th percentile TN \u22645 mg/L "
                "can be assessed credibly.",
                "If carbon-limited: external carbon required; DNF should be included "
                "in Stage 3 scope.",
                "Temperature robustness of denitrification must be confirmed at "
                f"{ctx.get('temp_celsius', 15)}\u00b0C operating conditions.",
            ]
            p95_unc = "Carbon availability — the dominant unresolved variable for TN polishing reliability."
        else:
            p95_outcome = ACHIEVABLE
            p95_conds   = [
                "Bardenpho carbon confirmed sufficient.",
                "Temperature-corrected zone sizing confirmed.",
            ]
            p95_unc = "Seasonal variation in denitrification rate."
    else:
        p95_outcome = ACHIEVABLE
        p95_conds   = ["Standard biological TN removal."]
        p95_unc     = "Seasonal carbon variability."

    dvs = []
    if cod_unknown:
        dvs.append("COD fractionation / carbon availability — must be resolved before "
                   "Stage 3 design. Governs whether biological polishing alone is viable "
                   "and whether DNF is mandatory.")
    if tn_target <= 3.0:
        dvs.append("Regulatory TN target basis — confirm whether TN \u22643 mg/L is a "
                   "current legal obligation or a planning horizon target. This determines "
                   "whether DNF is in near-term scope.")

    conf = _confidence(
        low_count=(1 if (tn_target <= 3. and not has_dnf) else
                   1 if (tn_target <= 3. and (cod_unknown or carbon_lim) and not has_dnf) else 0),
        med_count=(1 if cod_unknown else 0) + (1 if cold else 0),
    )

    design = (
        f"TN \u2264{tn_target} mg/L at {target_basis}: "
        + ("DNF is required for credible 95th percentile compliance at this target. "
           "Biological optimisation alone is unlikely to be reliable at the 95th percentile "
           "without confirmed carbon surplus."
           if (tn_target <= 3. and not has_dnf) else
           "COD fractionation audit is the critical next step — it determines whether "
           "biological polishing alone is sufficient or DNF must be added."
           if cod_unknown else
           "Process pathway appears sound for 95th percentile TN compliance "
           "once carbon availability is confirmed and seasonal performance established.")
    )

    return ParameterCompliance(
        parameter="TN",
        target_mg_l=tn_target,
        target_basis=target_basis,
        median_outcome=median_outcome,
        median_conditions=median_conds,
        median_uncertainty=median_unc,
        p95_outcome=p95_outcome,
        p95_conditions=p95_conds,
        p95_uncertainty=p95_unc,
        confidence=conf,
        decision_variables=dvs,
        design_implication=design,
    )


def _assess_tp(
    pathway: UpgradePathway,
    ctx: Dict,
    tp_target: float,
    target_basis: str,
) -> ParameterCompliance:
    has_tertp   = _has_tech(pathway, TI_TERT_P, TI_COMAG)
    tp_influent = float(ctx.get("tp_in_mg_l") or ctx.get("influent_tp_mg_l") or 6.)
    dewater_confirmed = bool(ctx.get("dewatering_confirmed", False))
    fr          = _flow_ratio(ctx)
    high_tp_in  = tp_influent >= 6.

    # ── Median ────────────────────────────────────────────────────────────────
    if tp_target <= 0.1:
        if has_tertp:
            median_outcome = ACHIEVABLE
            median_conds = [
                "Tertiary chemical polishing (FeCl\u2083 + filtration) correctly commissioned.",
                "Automated dose control with online P analyser at filter outlet.",
                "Sludge handling pathway confirmed for increased chemical sludge volume.",
            ]
            median_unc = "Dose calibration at variable influent TP — particularly relevant "                       "at influent TP of {:.0f} mg/L which is above the typical range.".format(tp_influent)
        else:
            median_outcome = NOT_YET_CREDIBLE
            median_conds   = ["TP \u22640.1 mg/L requires tertiary chemical polishing. "
                              "EBPR alone cannot achieve this target."]
            median_unc     = "Absence of tertiary P removal in the current stack."
    elif tp_target <= 0.5:
        if has_tertp:
            median_outcome = ACHIEVABLE
            median_conds   = ["Tertiary filtration and chemical dosing correctly commissioned."]
            median_unc     = "Dose control under variable influent TP."
        else:
            median_outcome = CONDITIONAL
            median_conds   = ["Tertiary P removal or supplementary chemical dosing required for TP \u22640.5 mg/L."]
            median_unc     = "EBPR variability under seasonal conditions."
    else:
        median_outcome = (ACHIEVABLE if has_tertp else CONDITIONAL)
        median_conds   = ["EBPR optimisation combined with chemical dosing for moderate targets."]
        median_unc     = "Seasonal EBPR variability."

    # ── 95th percentile ────────────────────────────────────────────────────────
    if tp_target <= 0.1:
        if not has_tertp:
            p95_outcome = NOT_YET_CREDIBLE
            p95_conds   = [
                "Tertiary chemical polishing is mandatory for TP \u22640.1 mg/L at any "
                "compliance basis. EBPR alone is insufficient.",
            ]
            p95_unc = "Absence of tertiary P removal."
        elif not dewater_confirmed:
            p95_outcome = CONDITIONAL
            p95_conds = [
                "Dewatering capacity confirmation is a STAGE GATE before Stage 3c "
                "contract award — not an advisory action.",
                "At TP influent {:.1f} mg/L, chemical sludge volume increase is material "
                "and must be quantified before committing Stage 3c capital.".format(tp_influent),
                "Dose control automated with online P analyser at filter outlet.",
                "Solids capture robustness confirmed at peak hydraulic loading — "
                "TSS in filter effluent must remain below threshold during storm events.",
                "Dual FeCl\u2083 supplier agreement in place before commissioning.",
            ]
            p95_unc = ("Dewatering capacity — a decision variable that governs whether "
                       "Stage 3c is deliverable without additional capital. Until confirmed, "
                       "95th percentile TP compliance cannot be credibly asserted.")
        else:
            p95_outcome = ACHIEVABLE
            p95_conds = [
                "Dewatering capacity confirmed.",
                "Dose control automated and calibrated.",
                "Filter performance validated under peak hydraulic loading.",
            ]
            p95_unc = "Filter performance during extreme hydraulic events."
    elif tp_target <= 0.5:
        p95_outcome = CONDITIONAL if not has_tertp else ACHIEVABLE
        p95_conds   = (["Tertiary filtration required for 95th percentile reliability at TP \u22640.5 mg/L."]
                       if not has_tertp else
                       ["Chemical dose control and solids capture must be robust "
                        "under seasonal TP variability."])
        p95_unc = "Seasonal EBPR variability."
    else:
        p95_outcome = ACHIEVABLE
        p95_conds   = ["Standard TP control."]
        p95_unc     = "Seasonal EBPR performance."

    dvs = []
    if tp_target <= 0.1 and not dewater_confirmed:
        dvs.append("Dewatering capacity for tertiary P sludge — a stage gate before "
                   "Stage 3c contract award. At influent TP {:.0f} mg/L, chemical sludge "
                   "volume increase is material.".format(tp_influent))

    conf = _confidence(
        low_count=(1 if not has_tertp and tp_target <= 0.1 else 0),
        med_count=(1 if (tp_target <= 0.1 and not dewater_confirmed) else 0),
    )

    design = (
        f"TP \u2264{tp_target} mg/L at {target_basis}: "
        + ("Tertiary chemical polishing is mandatory — EBPR alone cannot achieve this target. "
           "At influent TP {:.0f} mg/L, dewatering capacity confirmation is a stage gate.".format(tp_influent)
           if tp_target <= 0.1 else
           "Tertiary filtration improves reliability for 95th percentile compliance.")
    )

    return ParameterCompliance(
        parameter="TP",
        target_mg_l=tp_target,
        target_basis=target_basis,
        median_outcome=median_outcome,
        median_conditions=median_conds,
        median_uncertainty=median_unc,
        p95_outcome=p95_outcome,
        p95_conditions=p95_conds,
        p95_uncertainty=p95_unc,
        confidence=conf,
        decision_variables=dvs,
        design_implication=design,
    )


def _assess_tss(
    pathway: UpgradePathway,
    ctx: Dict,
    tss_target: float,
    target_basis: str,
) -> ParameterCompliance:
    fr         = _flow_ratio(ctx)
    has_comag  = _has_tech(pathway, TI_COMAG, TI_BIOMAG)
    has_eq     = _has_tech(pathway, TI_EQ_BASIN)

    high_flow = fr >= 3.0
    attenuated = has_comag or has_eq

    median_outcome = ACHIEVABLE if attenuated else (CONDITIONAL if high_flow else ACHIEVABLE)
    median_conds = (
        ["High-rate clarification (CoMag) or equivalent provides hydraulic protection "
         "during peak wet weather events."]
        if attenuated else
        ["Secondary clarifiers adequate under dry weather conditions."]
        if not high_flow else
        ["TSS compliance during peak wet weather flows is not credible without "
         "hydraulic attenuation or high-rate clarification."]
    )
    median_unc = ("Wet weather hydraulic loading on secondary clarifiers."
                  if high_flow else "Dry weather TSS variability.")

    p95_outcome = (ACHIEVABLE if attenuated else
                   NOT_YET_CREDIBLE if high_flow else CONDITIONAL)
    p95_conds = (
        ["High-rate clarification provides 95th percentile TSS protection.",
         f"CoMag or equivalent sized for the {fr:.1f}\u00d7 ADWF peak flow regime.",
         "Recovery performance confirmed post-bypass events."]
        if attenuated else
        ["95th percentile TSS compliance is not credible at {:.1f}\u00d7 ADWF "
         "without hydraulic attenuation or high-rate clarification.".format(fr),
         "Secondary clarifier SOR will periodically exceed advisory limits, "
         "causing solids carryover events that fail the 95th percentile test."]
        if high_flow else
        ["TSS variability under wet weather conditions should be characterised "
         "before asserting 95th percentile compliance."]
    )
    p95_unc = ("Clarifier performance at peak wet weather — primary threat to "
               "95th percentile TSS compliance."
               if high_flow and not attenuated else
               "Wet weather solids recovery after bypass events."
               if attenuated else "Clarifier performance variability.")

    conf = _confidence(
        low_count=(1 if high_flow and not attenuated else 0),
        med_count=(1 if high_flow and attenuated else 0),
    )

    design = (
        f"TSS at {target_basis}: "
        + ("Hydraulic attenuation included — 95th percentile TSS reliability is supported."
           if attenuated else
           f"At {fr:.1f}\u00d7 ADWF, high-rate clarification or upstream attenuation "
           "is required for credible 95th percentile TSS reliability.")
    )

    return ParameterCompliance(
        parameter="TSS",
        target_mg_l=tss_target,
        target_basis=target_basis,
        median_outcome=median_outcome,
        median_conditions=median_conds,
        median_uncertainty=median_unc,
        p95_outcome=p95_outcome,
        p95_conditions=p95_conds,
        p95_uncertainty=p95_unc,
        confidence=conf,
        decision_variables=(["Hydraulic attenuation adequacy — at {:.1f}\u00d7 ADWF, "
                             "percentile TSS reliability requires confirmed clarifier "
                             "protection at peak events.".format(fr)]
                             if high_flow and not attenuated else []),
        design_implication=design,
    )


# ── Reliability drivers ────────────────────────────────────────────────────────

def _build_drivers(pathway: UpgradePathway, ctx: Dict) -> List[ReliabilityDriver]:
    fr          = _flow_ratio(ctx)
    cold        = _cold(ctx)
    aer         = _aer_constrained(ctx)
    cod_unknown = _cod_tn_unknown(ctx)
    carbon_lim  = _carbon_limited(ctx)
    has_mabr    = _has_tech(pathway, TI_MABR)
    has_dnf     = _has_tech(pathway, TI_DENFILTER)
    has_comag   = _has_tech(pathway, TI_COMAG)
    has_tertp   = _has_tech(pathway, TI_TERT_P, TI_COMAG)

    drivers = []

    # 1. Peak flow ratio
    if fr >= 3.5:
        lvl = "High"
        expl = (f"At {fr:.1f}\u00d7 ADWF, secondary clarifiers will be periodically "
                "overloaded regardless of biological performance. This is the single "
                "greatest threat to all percentile parameters simultaneously. "
                "CoMag provides material relief but does not replace upstream attenuation.")
    elif fr >= 2.5:
        lvl = "Medium"
        expl = (f"Peak flow ratio of {fr:.1f}\u00d7 ADWF creates material hydraulic stress. "
                "Solids carryover events are plausible during storm events. "
                "High-rate clarification at Stage 1 is appropriate.")
    else:
        lvl = "Low"
        expl = f"Peak flow ratio of {fr:.1f}\u00d7 ADWF is within manageable range."
    drivers.append(ReliabilityDriver("Peak flow ratio", lvl, expl, ["NH\u2084","TN","TP","TSS"]))

    # 2. Winter temperature
    if cold and aer:
        drivers.append(ReliabilityDriver("Winter temperature + aeration constraint", "High",
            "At \u226412\u00b0C with blowers near capacity, nitrification kinetics are reduced "
            "40\u201350% and oxygen delivery is constrained simultaneously. "
            "MABR is required — IFAS would consume blower headroom that does not exist. "
            "95th percentile NH\u2084 and TN compliance are conditional until MABR demonstrates "
            "seasonal stability.",
            ["NH\u2084", "TN"]))
    elif cold:
        drivers.append(ReliabilityDriver("Winter temperature", "Medium",
            "Cold conditions reduce nitrification kinetics. Seasonal monitoring required "
            "to confirm 95th percentile NH\u2084 compliance.",
            ["NH\u2084", "TN"]))

    # 3. Carbon availability
    if cod_unknown:
        drivers.append(ReliabilityDriver("COD fractionation / carbon availability", "High",
            "The readily biodegradable COD:TN ratio in settled influent is unknown. "
            "This is a DECISION VARIABLE — it determines whether biological denitrification "
            "is carbon-limited, whether DNF is mandatory, and what the long-term OPEX profile "
            "will be. No credible 95th percentile TN compliance claim can be made until "
            "this is resolved.",
            ["TN"]))
    elif carbon_lim:
        drivers.append(ReliabilityDriver("Carbon limitation confirmed", "High",
            "Carbon limitation is active. External carbon dosing is required for "
            "reliable denitrification. DNF should be treated as mandatory for 95th "
            "percentile TN \u22643 mg/L compliance.",
            ["TN"]))

    # 4. Aeration headroom
    if aer and not has_mabr:
        drivers.append(ReliabilityDriver("Aeration headroom (insufficient)", "High",
            "Blowers are at or near maximum capacity without MABR. 95th percentile "
            "NH\u2084 compliance is not credible in cold conditions without oxygen delivery "
            "independent of the blower system.",
            ["NH\u2084"]))
    elif aer and has_mabr:
        drivers.append(ReliabilityDriver("Aeration headroom (addressed by MABR)", "Medium",
            "MABR bypasses the blower constraint via membrane oxygen delivery. "
            "Seasonal establishment and module integrity are the residual aeration risks.",
            ["NH\u2084"]))

    # 5. Solids separation reliability
    if fr >= 3.0 and not has_comag:
        drivers.append(ReliabilityDriver("Settling / solids separation reliability", "High",
            f"At {fr:.1f}\u00d7 ADWF without high-rate clarification, secondary clarifier "
            "SOR will periodically exceed advisory limits. Solids carryover events will "
            "degrade all percentile parameters during wet weather.",
            ["NH\u2084","TN","TP","TSS"]))

    # 6. Chemical dosing dependency
    if has_dnf:
        drivers.append(ReliabilityDriver("Methanol dosing (DNF)", "Medium",
            "Continuous methanol supply is required for tertiary denitrification. "
            "Supply disruption immediately halts TN polishing. Dual supply agreement "
            "and 30-day on-site stock are minimum requirements for 95th percentile "
            "TN reliability.",
            ["TN"]))
    if has_tertp:
        drivers.append(ReliabilityDriver("Chemical dosing — tertiary P", "Medium",
            "FeCl\u2083 dosing continuity is required for TP compliance. Dose control "
            "accuracy under variable influent TP is the primary operational risk "
            "for 95th percentile TP reliability.",
            ["TP"]))

    # 7. Operator complexity
    n_specialist = sum(1 for s in pathway.stages
                       if s.technology in (TI_MABR, TI_COMAG, TI_DENFILTER))
    if n_specialist >= 2:
        drivers.append(ReliabilityDriver("Operator / commissioning complexity", "Medium",
            f"{n_specialist} specialist technologies in the stack require coordinated "
            "commissioning and O&M capability. Percentile compliance reliability depends "
            "on correct sequencing of commissioning gates — particularly the MABR \u2192 "
            "Bardenpho \u2192 DNF sequence.",
            ["NH\u2084","TN"]))

    # 8. Hydraulic attenuation
    if fr >= 3.0 and has_comag:
        drivers.append(ReliabilityDriver("Hydraulic attenuation (CoMag + I/I reduction needed)", "Medium",
            f"CoMag provides high-rate clarification at {fr:.1f}\u00d7 ADWF but does not "
            "replace upstream attenuation. 99th percentile / event compliance for all "
            "parameters requires I/I reduction or storm storage as a parallel workstream.",
            ["NH\u2084","TN","TP","TSS"]))

    return drivers


# ── Brownfield / compliance interaction ────────────────────────────────────────

def _build_brownfield_note(
    params: List[ParameterCompliance],
    ctx: Dict,
) -> BrownfieldComplianceNote:
    fr = _flow_ratio(ctx)

    median_all_achievable = all(
        p.median_outcome == ACHIEVABLE for p in params)
    p95_any_not_credible  = any(
        p.p95_outcome == NOT_YET_CREDIBLE for p in params)
    p95_all_at_least_conditional = all(
        p.p95_outcome in (ACHIEVABLE, CONDITIONAL) for p in params)

    brownfield_median = median_all_achievable or all(
        p.median_outcome in (ACHIEVABLE, CONDITIONAL) for p in params)
    brownfield_p95    = p95_all_at_least_conditional and not p95_any_not_credible

    drives_replacement = (
        not brownfield_p95 and
        any(p.p95_outcome == NOT_YET_CREDIBLE for p in params)
    )

    if drives_replacement:
        expl = (
            "Brownfield intensification appears viable for achieving median compliance "
            "targets. However, 95th percentile compliance — the standard expected by most "
            "regulatory frameworks — is not credible on the current brownfield pathway "
            "without resolving the decision variables identified above. "
            "If the regulatory obligation is explicitly stated as a 95th percentile "
            "standard, this gap strengthens the case for full process replacement "
            "(Nereda AGS or equivalent), which provides a simpler, more robust process "
            "architecture with fewer compounded reliability dependencies."
        )
    elif not brownfield_p95:
        expl = (
            "Brownfield intensification is viable for median compliance across all "
            "parameters. 95th percentile compliance is achievable on the brownfield "
            "pathway but is conditional on resolving the identified decision variables "
            "before Stage 3 design commences. If these cannot be resolved, the "
            "reliability case for brownfield weakens."
        )
    else:
        expl = (
            "Brownfield intensification is viable for both median and 95th percentile "
            "compliance across all assessed parameters, subject to the stage gate "
            "conditions identified for each. The brownfield pathway is appropriate "
            "for the current planning horizon."
        )

    return BrownfieldComplianceNote(
        brownfield_viable_for_median   = brownfield_median,
        brownfield_viable_for_p95      = brownfield_p95,
        compliance_drives_replacement  = drives_replacement,
        explanation                    = expl,
    )


# ── Overall confidence ─────────────────────────────────────────────────────────

def _overall_confidence(params: List[ParameterCompliance], ctx: Dict) -> str:
    conf_order = {CONF_HIGH: 2, CONF_MEDIUM: 1, CONF_LOW: 0}
    worst = min(conf_order[p.confidence] for p in params)
    if worst == 0: return CONF_LOW
    if worst == 1: return CONF_MEDIUM
    return CONF_HIGH


# ── Main entry point ───────────────────────────────────────────────────────────


def _assess_tn_pdna(pathway, ctx, tn_target, target_basis):
    """Fix 2: PdNA-specific TN compliance — NO2 window, NOB, Anammox retention."""
    cold        = _cold(ctx)
    fr          = _flow_ratio(ctx)
    has_biofilm = _has_tech(pathway, TI_MABR, TI_IFAS, TI_HYBAS)
    high_hyd    = fr >= 3.0
    weak_ctrl   = not bool(ctx.get("has_no2_analyser", False))
    nob_high    = cold or high_hyd or weak_ctrl

    if not has_biofilm:
        med, p95 = NOT_YET_CREDIBLE, NOT_YET_CREDIBLE
        mc  = ["Anammox retention (IFAS/MBBR/MABR) absent. PdNA cannot be sustained in suspended growth."]
        mu  = "Certain Anammox washout without fixed-film retention."
        pc  = ["Biomass retention is a hard design prerequisite."]
        pu  = "Anammox washout from hydraulic events."
    elif cold and tn_target <= 3.:
        med = CONDITIONAL
        mc  = ["NO\u2082 window (0.5\u20135 mg/L) must be maintained continuously.",
               "At \u226412\u00b0C Anammox kinetics fall 40\u201350% \u2014 NO\u2082 "
               "accumulates as partial denitrification continues near-normally.",
               "Rising TN requires REDUCING carbon dose \u2014 operator training mandatory."]
        mu  = "Cold-temperature NO\u2082 accumulation and FNA inhibition spiral."
        p95 = CONDITIONAL
        pc  = ["NOB intrusion risk elevated under cold/high hydraulic stress.",
               "NO\u2082 online analyser with alarm at 4 mg/L mandatory for P95 reliability."]
        pu  = "NOB colonisation of biofilm carriers under combined temperature and hydraulic stress."
    else:
        med = CONDITIONAL
        mc  = ["COD:NO\u2083 controlled to 2.4\u20133.0 gCOD/gNO\u2083-N.",
               "Real-time NO\u2082 monitoring active.",
               "NOB suppression via low DO maintained as ongoing discipline."]
        mu  = "NO\u2082 window stability \u2014 narrow margin between starvation and FNA inhibition."
        if nob_high or weak_ctrl:
            p95, pc = CONDITIONAL, ["NOB intrusion or control system limitation.",
                                     "Real-time NO\u2082 and NH\u2084 monitoring required."]
            pu  = "NOB intrusion or weak dosing control."
        else:
            p95, pc = ACHIEVABLE, ["Anammox retention confirmed.", "NO\u2082 monitoring active.",
                                    "NOB suppression maintained."]
            pu  = "Seasonal temperature variation."

    dvs = []
    if not bool(ctx.get("has_no2_analyser", False)):
        dvs.append("NO\u2082 online analyser \u2014 mandatory for PdNA stoichiometric control.")
    if cold:
        dvs.append("Winter protocol: carbon dose REDUCTION when TN rises \u2014 must be in O&M plan.")

    return ParameterCompliance(
        parameter="TN", target_mg_l=tn_target, target_basis=target_basis,
        median_outcome=med, median_conditions=mc, median_uncertainty=mu,
        p95_outcome=p95, p95_conditions=pc, p95_uncertainty=pu,
        confidence=_confidence(
            low_count=(1 if not has_biofilm else 0),
            med_count=(1 if nob_high else 0) + (1 if weak_ctrl else 0)),
        decision_variables=dvs,
        design_implication=(
            f"TN \u2264{tn_target} mg/L via PdNA: compliance depends on NO\u2082 window "
            "control, NOB suppression, and Anammox retention \u2014 not carbon availability."
        ),
    )


def _build_delivery_considerations(
    pathway,
    ctx: dict,
    op_flag: bool,
    confidence_score: int,
) -> list:
    """
    Delivery and Operational Considerations layer.

    Triggered when any of:
      - intensified/specialist process in stack
      - greenfield mode
      - confidence <= 70
      - operator_flag = True
      - TN target <= 5 mg/L at P95

    Returns a list of 3-4 plain-language consideration strings,
    or an empty list when none of the trigger conditions are met.
    """
    tech_set = {s.technology for s in pathway.stages}

    INTENSIFIED = {
        TI_MABR, TI_COMAG, TI_BIOMAG, TI_PDNA, TI_DENFILTER,
        TI_IFAS, TI_HYBAS,
    }
    has_intensified = bool(tech_set & INTENSIFIED)
    has_specialist  = bool(tech_set & {TI_MABR, TI_COMAG, TI_BIOMAG, TI_PDNA})
    has_mabr_comag  = bool(tech_set & {TI_MABR, TI_COMAG, TI_BIOMAG})
    is_greenfield   = bool(ctx.get("greenfield", False))
    tn_tgt          = float(ctx.get("tn_target_mg_l") or 10.)
    is_p95          = "95" in (ctx.get("tn_target_basis") or "")
    tight_tn        = tn_tgt <= 5. and is_p95
    loc             = ctx.get("location_type", "metro")

    # Trigger gate
    triggered = (
        has_intensified
        or is_greenfield
        or confidence_score <= 70
        or op_flag
        or tight_tn
    )
    if not triggered:
        return []

    points: list = []

    # 1. Volume as buffer (greenfield)
    if is_greenfield:
        points.append(
            "Conventional high-volume systems provide hydraulic and biological "
            "buffering, offering greater tolerance to shock loads and operational "
            "variability. This should be weighed against the efficiency advantages "
            "of the selected configuration."
        )

    # 2. Operational complexity
    if has_intensified:
        points.append(
            "The selected process configuration requires tighter operational "
            "control, higher instrumentation reliability, and more specialist "
            "operator capability than conventional activated sludge."
        )

    # 3. Response time
    if has_intensified:
        points.append(
            "High-rate and intensified systems reduce hydraulic and biological "
            "reaction time, requiring faster operator response to disturbances "
            "compared to conventional systems with greater inherent buffering."
        )

    # 4. Regulatory defensibility (greenfield + intensified) — before lifecycle
    if is_greenfield and has_intensified:
        points.append(
            "In a greenfield context, regulators and owners may favour proven "
            "conventional configurations unless a clear technical or capacity "
            "driver justifies advanced process selection."
        )

    # 5. Maintenance / lifecycle complexity
    if has_mabr_comag:
        points.append(
            "This configuration relies on specialist components — including "
            "membrane modules, magnetic ballast recovery, or biofilm carriers — "
            "with maintenance cycles and supply chains that may increase lifecycle "
            "complexity compared to conventional concrete-based assets."
        )

    # 6. Remote / operator burden flag
    if op_flag and loc in ("remote", "regional"):
        points.append(
            "At a remote or regional site, operator access, training, and "
            "specialist support availability are material constraints on the "
            "long-term reliability of an intensified process stack."
        )

    # Cap at 4 content points before appending the mandatory closing statement
    points = points[:4]

    # 7. Strategic trade-off — always last
    points.append(
        "This configuration represents a trade-off between process efficiency "
        "and operational simplicity. Selection should align with utility "
        "capability, risk tolerance, and long-term asset strategy."
    )

    return points



def build_compliance_report(
    pathway: UpgradePathway,
    feasibility: FeasibilityReport,
    plant_context: Optional[Dict] = None,
    include_tss: bool = True,
) -> ComplianceReport:
    """
    Build the Percentile Compliance Logic Layer report.

    Parameters
    ----------
    pathway       : UpgradePathway     — output of build_upgrade_pathway()
    feasibility   : FeasibilityReport  — output of assess_feasibility()
    plant_context : dict, optional     — same context dict passed to other layers
    include_tss   : bool               — include TSS assessment (default True)

    Returns
    -------
    ComplianceReport
        Does NOT modify pathway or feasibility.

    Important
    ---------
    This layer generates NO precise percentile effluent values.
    All outcomes are structured reliability judgements:
    "Achievable", "Conditional", or "Not yet credible".
    """
    ctx = plant_context or {}

    # Extract targets
    nh4_tgt = float(ctx.get("nh4_target_mg_l") or 1.)
    tn_tgt  = float(ctx.get("tn_target_mg_l")  or 10.)
    tp_tgt  = float(ctx.get("tp_target_mg_l")  or 1.)
    tss_tgt = float(ctx.get("tss_target_mg_l") or 30.)

    # Target basis — read from context or default to P95 for tight targets
    nh4_basis = _target_basis_from_ctx(ctx, "nh4") or (
        BASIS_P95 if nh4_tgt <= 1. else BASIS_MEDIAN)
    tn_basis  = _target_basis_from_ctx(ctx, "tn") or (
        BASIS_P95 if tn_tgt <= 5. else BASIS_MEDIAN)
    tp_basis  = _target_basis_from_ctx(ctx, "tp") or (
        BASIS_P95 if tp_tgt <= 0.5 else BASIS_MEDIAN)
    tss_basis = _target_basis_from_ctx(ctx, "tss") or BASIS_P95

    # Fix 2: PdNA TN routing
    _pdna_stack = _has_tech(pathway, TI_PDNA)
    _tn_p = (
        _assess_tn_pdna(pathway, ctx, tn_tgt, tn_basis)
        if _pdna_stack else
        _assess_tn(pathway, ctx, tn_tgt, tn_basis)
    )

    # Build parameter assessments
    params = [
        _assess_nh4(pathway, ctx, nh4_tgt, nh4_basis),
        _tn_p,
        _assess_tp (pathway, ctx, tp_tgt,  tp_basis),
    ]
    if include_tss:
        params.append(_assess_tss(pathway, ctx, tss_tgt, tss_basis))

    drivers            = _build_drivers(pathway, ctx)
    brownfield_note    = _build_brownfield_note(params, ctx)
    overall_confidence = _overall_confidence(params, ctx)

    # ── Phase 2 realism (Fixes 1, 2, 3) ─────────────────────────────────────
    _tkn_in  = _influent_tn_mg_l(ctx)
    _cod_in  = _influent_cod_mg_l(ctx)
    _tn_p    = next(p for p in params if p.parameter == "TN")
    _tn_idx  = params.index(_tn_p)
    _has_adv = _has_tech(pathway, TI_PDNA, TI_DENFILTER)

    # Fix 1: High TKN removal >90% at P95
    if (_tkn_in > 50. and tn_tgt <= 5.
            and tn_basis in (BASIS_P95, BASIS_P99)
            and _high_tkn_removal_required(_tkn_in, tn_tgt)):
        _f1 = ("High TKN removal requirement (>90%) \u2014 "
               "performance risk at P95 conditions.")
        _new_p95 = _downgrade_outcome(_tn_p.p95_outcome)
        _new_dvs = list(_tn_p.decision_variables) + [_f1]
        _new_p95c = [_f1] + list(_tn_p.p95_conditions)
        from dataclasses import replace as _dc_replace
        _tn_p = _dc_replace(_tn_p,
            p95_outcome=_new_p95,
            p95_conditions=_new_p95c,
            decision_variables=_new_dvs)

    # Fix 2: COD fractionation / effective COD:TN
    _eff_codn = _effective_cod_tn(_cod_in, _tkn_in) if _tkn_in > 0 else 999.
    _fix3_note = ""
    if (_tkn_in > 50. or tn_tgt <= 5.) and _cod_in > 0.:
        if _eff_codn < 5.:
            _f2 = ("Biologically available COD may be insufficient for target TN — "
                   "effective COD:TN after settling ≈{:.1f} (threshold 5.0). "
                   "Carbon limitation likely at P95.".format(_eff_codn))
            from dataclasses import replace as _dc_replace
            if not _has_adv:
                _new_med  = _downgrade_outcome(_tn_p.median_outcome)
                _new_mc2  = [_f2] + list(_tn_p.median_conditions)
                _new_dvs2 = list(_tn_p.decision_variables) + [_f2]
                _tn_p = _dc_replace(_tn_p, median_outcome=_new_med,
                    median_conditions=_new_mc2, decision_variables=_new_dvs2)
            else:
                # Advanced N removal present: flag only, do not downgrade
                _tn_p = _dc_replace(_tn_p,
                    decision_variables=list(_tn_p.decision_variables) + [_f2])

    # Fix 3: Sludge production flag
    if _cod_in > 400. or _tkn_in > 50.:
        _fix3_note = ("Sludge production significantly above typical municipal baseline \u2014 "
                      "verify sludge handling capacity before committing to design.")

    params[_tn_idx] = _tn_p

    # ── Compliance consistency enforcement (Rules 1-3) ───────────────────
    # Applied AFTER all base/Phase-2 adjustments are complete.
    # References are re-fetched so they reflect the latest state.

    from dataclasses import replace as _dcr

    _tn_p2  = next(p for p in params if p.parameter == "TN")
    _nh4_p2 = next((p for p in params if p.parameter == "NH₄"), None)
    _tn_idx2 = params.index(_tn_p2)
    _changed = False

    # Rule 1: TN median Not credible ⇒ TN P95 must also be Not credible
    if (_tn_p2.median_outcome == NOT_YET_CREDIBLE
            and _tn_p2.p95_outcome != NOT_YET_CREDIBLE):
        _r1_flag = ("P95 downgraded due to median non-credibility — "
                    "target not achievable under average conditions.")
        _tn_p2 = _dcr(_tn_p2,
            p95_outcome   = NOT_YET_CREDIBLE,
            p95_conditions= [_r1_flag] + list(_tn_p2.p95_conditions),
            decision_variables = list(_tn_p2.decision_variables) + [_r1_flag])
        _changed = True

    # Rule 2: NH4 P95 ≠ Achievable ⇒ degrade TN P95 by one level
    if _nh4_p2 is not None and _nh4_p2.p95_outcome != ACHIEVABLE:
        if _tn_p2.p95_outcome != NOT_YET_CREDIBLE:   # don't degrade floor twice
            _r2_flag = "TN reliability limited by nitrification performance."
            _tn_p2 = _dcr(_tn_p2,
                p95_outcome   = _downgrade_outcome(_tn_p2.p95_outcome),
                p95_conditions= [_r2_flag] + list(_tn_p2.p95_conditions),
                decision_variables = list(_tn_p2.decision_variables) + [_r2_flag])
            _changed = True

    if _changed:
        params[_tn_idx2] = _tn_p2

    # Rule 3 + original Fix-1 gap: fire gap whenever TN median or P95 = Not credible
    _tn_final = next(p for p in params if p.parameter == "TN")
    _gap = (
        _tn_final.median_outcome == NOT_YET_CREDIBLE
        or _tn_final.p95_outcome == NOT_YET_CREDIBLE
    )
    _gap_note = (
        "Current process stack cannot meet TN ≤{:.0f} mg/L target — "
        "upgrade or process change required (DNF or PdNA minimum)."
        .format(tn_tgt)
        if _gap else ""
    )


    # Fix 4: operator capability vs stack complexity
    _remote = ctx.get("location_type", "metro") in ("remote", "regional")
    _spec   = {"CoMag", "BioMag", "MABR (OxyFAS retrofit)",
               "PdNA (Partial Denitrification-Anammox)", "Denitrification Filter",
               "IFAS", "MBBR", "Hybas (IFAS)",
               "MOB (miGRATE + inDENSE)", "inDENSE"}
    _match  = sorted({s.technology for s in pathway.stages} & _spec)
    _op_flag = _remote and bool(_match)
    _op_note = (
        "Operational capability risk: {} specialist process{} ({}) require{} sustained "
        "control discipline at a {} location. Confirm operator capability before committing."
        .format(len(_match), "es" if len(_match)>1 else "", ", ".join(_match),
                "" if len(_match)>1 else "s",
                ctx.get("location_type", "regional"))
        if _op_flag else ""
    )


    # ── Confidence Score Layer ────────────────────────────────────────────────
    # Penalties are collected as (points, plain_language_driver) tuples,
    # sorted descending by penalty magnitude before top-3 selection.
    _score    = 100
    _pen: list = []   # (penalty_pts, driver_label)

    def _p(pts, label):
        nonlocal _score
        _score -= pts
        _pen.append((pts, label))

    # 1. High TKN severity
    if _tkn_in > 50.:
        _req_rem = (_tkn_in - tn_tgt) / _tkn_in if _tkn_in > 0 else 0.
        if _req_rem >= 0.90:
            _p(20, "High nitrogen removal requirement (>{:.0f}%)".format(int(_req_rem * 100)))
        else:
            _p(10, "High nitrogen load requires elevated removal efficiency")

    # 2. Carbon limitation
    if _eff_codn < 5. and _cod_in > 0.:
        if _eff_codn < 3.:
            _p(25, "Severe carbon limitation — denitrification unlikely without external carbon")
        else:
            _p(15, "Insufficient biologically available carbon for denitrification")

    # 3. Low temperature (three-tier: ≤15°C / ≤12°C / ≤10°C)
    _temp = float(ctx.get("temp_celsius") or ctx.get("temperature_celsius") or 20.)
    if _temp <= 10.:
        _p(5, "Moderate temperature constraint (≤15°C)")
        _p(5, "Low temperature limits biological reaction rates")
        _p(5, "Very low temperature — biological processes significantly impaired")
    elif _temp <= 12.:
        _p(5, "Moderate temperature constraint (≤15°C)")
        _p(5, "Low temperature limits biological reaction rates")
    elif _temp <= 15.:
        _p(5, "Moderate temperature constraint (≤15°C)")

    # 4. Hydraulic stress
    _fr = _flow_ratio(ctx)
    if _fr >= 4.:
        _p(15, "Extreme hydraulic loading challenges system capacity")
    elif _fr >= 3.:
        _p(10, "High hydraulic variability reduces process stability")

    # 5. Compliance status
    _tn_final_p = next(p for p in params if p.parameter == "TN")
    if _tn_final_p.median_outcome == NOT_YET_CREDIBLE:
        _p(25, "Target not achievable under average conditions")
    elif _tn_final_p.median_outcome == CONDITIONAL:
        _p(10, "Target achievable under average conditions only")
    if _tn_final_p.p95_outcome == NOT_YET_CREDIBLE:
        _p(25, "Target not achievable under peak conditions")
    elif _tn_final_p.p95_outcome == CONDITIONAL:
        _p(10, "Performance risk under peak conditions")

    # 6. NH4 limitation (differentiated: Conditional=-10, Not credible=-20)
    _nh4_final_p = next((p for p in params if p.parameter == "NH₄"), None)
    if _nh4_final_p:
        if _nh4_final_p.p95_outcome == NOT_YET_CREDIBLE:
            _p(20, "Nitrification not reliable at peak conditions")
        elif _nh4_final_p.p95_outcome == CONDITIONAL:
            _p(10, "Nitrification performance uncertain at peak conditions")

    # 7. Process complexity
    _tech_set = {s.technology for s in pathway.stages}
    if "PdNA (Partial Denitrification-Anammox)" in _tech_set:
        _p(10, "Process depends on tight control and specialist operation")
    _adv_stage = {"MABR (OxyFAS retrofit)", "Denitrification Filter",
                  "IFAS", "MOB (miGRATE + inDENSE)"}
    if _tech_set & _adv_stage:
        _p(5, "Advanced process configuration increases operational complexity")

    # 8. Operator capability
    if _op_flag:
        _p(10, "Operator capability may not support process complexity")

    # 9. Sludge / high load — informational only, no score penalty

    # 10. Stack compliance gap
    if _gap:
        _p(20, "Selected process cannot meet target without upgrade")

    # Normalise and band
    _score = max(0, min(100, _score))
    if _score >= 80:
        _c_label = "High"
    elif _score >= 60:
        _c_label = "Moderate"
    elif _score >= 40:
        _c_label = "Low"
    else:
        _c_label = "Very Low"

    # Enforce: Not credible compliance cannot be High confidence
    if (_tn_final_p.median_outcome == NOT_YET_CREDIBLE or
            _tn_final_p.p95_outcome == NOT_YET_CREDIBLE):
        if _c_label == "High":
            _c_label = "Moderate"
            _score   = min(_score, 79)

    # ── Cause-before-consequence driver selection ───────────────────────
    # Compliance outcomes (consequences) — never show only these
    _CONSEQUENCE_SET = {
        "Target not achievable under average conditions",
        "Target not achievable under peak conditions",
        "Selected process cannot meet target without upgrade",
        "Target achievable under average conditions only",
        "Performance risk under peak conditions",
    }

    # Sort all penalties descending; deduplicate by label
    _seen: set = set()
    _all_ranked: list = []   # (pts, label) in descending penalty order
    for _pts, _lbl in sorted(_pen, key=lambda x: x[0], reverse=True):
        if _lbl not in _seen:
            _seen.add(_lbl)
            _all_ranked.append((_pts, _lbl))

    # Take top 3 by magnitude
    _ranked = [_lbl for _, _lbl in _all_ranked[:3]]

    # Rule 1+2: If all top 3 are consequences, inject highest-penalty cause
    if _ranked and all(d in _CONSEQUENCE_SET for d in _ranked):
        _cause_candidate = next(
            (_lbl for _, _lbl in _all_ranked if _lbl not in _CONSEQUENCE_SET),
            None)
        if _cause_candidate is not None:
            # Rule 3: keep at least 1 consequence — replace only position 2 (index 2)
            _insert_at = min(2, len(_ranked) - 1)
            _ranked[_insert_at] = _cause_candidate

    # Rule 4: Operator override — ensure op flag visible for remote/regional
    _OP_DRIVER = "Operator capability may not support process complexity"
    if (_op_flag
            and _OP_DRIVER not in _ranked
            and ctx.get("location_type", "metro") in ("remote", "regional")):
        # Replace the lowest-ranked compliance consequence in _ranked
        for _i in range(len(_ranked) - 1, -1, -1):
            if _ranked[_i] in _CONSEQUENCE_SET:
                _ranked[_i] = _OP_DRIVER
                break
        else:
            # No consequence to displace — append if room
            if len(_ranked) < 3:
                _ranked.append(_OP_DRIVER)

    # Rule 5: Final deduplication pass
    _final: list = []
    _fseen: set = set()
    for _d in _ranked:
        if _d not in _fseen:
            _fseen.add(_d)
            _final.append(_d)
    _ranked = _final[:3]

    # ── Forced-visibility overrides (Rule 1: temperature, Rule 2: hydraulic) ──
    # Labels that must never be displaced by forced overrides
    _PROTECTED = {
        "Severe carbon limitation — denitrification unlikely without external carbon",
        "Insufficient biologically available carbon for denitrification",
        "Selected process cannot meet target without upgrade",
        "Nitrification not reliable at peak conditions",
    }

    def _force_driver(candidate: str, ranked: list) -> list:
        """Insert candidate at end, displacing lowest non-protected entry."""
        if candidate in ranked:
            return ranked
        for _i in range(len(ranked) - 1, -1, -1):
            if ranked[_i] not in _PROTECTED:
                ranked = ranked[:_i] + ranked[_i+1:] + [candidate]
                return ranked
        # All slots protected — no override
        return ranked

    # Rule 1: Temperature forced visibility
    if _temp <= 10.:
        _temp_driver = "Very low temperature — biological processes significantly impaired"
    elif _temp <= 12.:
        _temp_driver = "Low temperature limits biological reaction rates"
    else:
        _temp_driver = None
    if _temp_driver and _temp_driver not in _ranked:
        _ranked = _force_driver(_temp_driver, _ranked)

    # Rule 2: Hydraulic forced visibility
    if _fr >= 4.:
        _hyd_driver = "Extreme hydraulic loading challenges system capacity"
    elif _fr >= 3.:
        _hyd_driver = "High hydraulic variability reduces process stability"
    else:
        _hyd_driver = None
    if _hyd_driver and _hyd_driver not in _ranked:
        _ranked = _force_driver(_hyd_driver, _ranked)

    # Final deduplication and cap
    _seen2: set = set()
    _top_drivers: list = []
    for _d in _ranked:
        if _d not in _seen2:
            _seen2.add(_d)
            _top_drivers.append(_d)
    _top_drivers = _top_drivers[:3]

    _delivery = _build_delivery_considerations(
        pathway, ctx, _op_flag, _score)

    # ── Diagnosis and closure statements (Part 4) ─────────────────────────────
    _tn_fp = _tn_final_p
    _root_causes_4 = [d for d in _top_drivers if d not in {
        "Target not achievable under average conditions",
        "Target not achievable under peak conditions",
        "Selected process cannot meet target without upgrade",
        "Target achievable under average conditions only",
        "Performance risk under peak conditions",
    }]
    _diag_cause = (_root_causes_4[0] if _root_causes_4
                   else _top_drivers[0] if _top_drivers else "")
    # Part 1: distinguish 'not credible' failure from 'conditional' risk
    _tn_med_nc_diag = (_tn_fp.median_outcome == NOT_YET_CREDIBLE)
    _tn_p95_nc_diag = (_tn_fp.p95_outcome   == NOT_YET_CREDIBLE)
    if _diag_cause:
        if _tn_med_nc_diag or _tn_p95_nc_diag:
            _diagnosis = (
                "Current configuration cannot meet the target under current constraints due to: "
                + _diag_cause.lower()
                + (". Compliance is not credible at 95th percentile."
                   if _tn_p95_nc_diag else
                   ". Compliance is not credible under average conditions.")
            )
        else:
            # TN is Achievable or Conditional — performance risk, not outright failure
            _diagnosis = (
                "Current configuration can meet the target under average conditions "
                "but carries performance risk under peak or stressed conditions due to: "
                + _diag_cause.lower() + "."
            )
    else:
        _diagnosis = ""

    _esc_in_notes = any("Escalation Mode" in n for n in pathway.guardrail_notes)
    if _gap or _esc_in_notes:
        _esc_tech_names = [s.technology for s in pathway.stages
                           if s.technology in (
                               "Denitrification Filter",
                               "PdNA (Partial Denitrification-Anammox)")]
        _closure_elems: list = []
        if _esc_tech_names:
            _closure_elems.append(" + ".join(_esc_tech_names)
                                  + " as tertiary nitrogen closure")
        if float(ctx.get("tp_target_mg_l") or 1.) <= 0.1:
            _closure_elems.append("tertiary phosphorus removal")
        _closure = (
            "Achieving compliance requires: "
            + "; ".join(_closure_elems) + ". "
            "Base biological optimisation alone is insufficient."
        ) if _closure_elems else ""
        _esc_note = (
            "Escalation Mode — Compliance Closure Strategy: "
            "The base configuration cannot achieve the target under current constraints. "
            + (_closure if _closure else
               "Tertiary closure processes are required.")
        ) if _esc_in_notes else ""
    else:
        _closure = ""
        _esc_note = ""

    return ComplianceReport(
        parameters             = params,
        drivers                = drivers,
        brownfield_note        = brownfield_note,
        overall_confidence     = overall_confidence,
        disclaimer             = DISCLAIMER,
        no_precise_percentile_values  = True,
        decision_variables_identified = any(len(p.decision_variables) > 0 for p in params),
        brownfield_interaction_stated = True,
        stack_compliance_gap          = _gap,
        stack_consistency_note        = _gap_note,
        operator_capability_flag      = _op_flag,
        operator_capability_note      = _op_note,
        sludge_flag                   = _fix3_note,
        effective_cod_tn_val          = _eff_codn,
        confidence_score              = _score,
        confidence_label              = _c_label,
        confidence_drivers            = _top_drivers,
        delivery_considerations       = _delivery,
        diagnosis_statement           = _diagnosis,
        closure_statement             = _closure,
        escalation_note               = _esc_note,
    )
