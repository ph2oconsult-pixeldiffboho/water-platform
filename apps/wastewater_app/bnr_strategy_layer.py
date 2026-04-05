"""
apps/wastewater_app/bnr_strategy_layer.py

BNR Strategy & Future-Proofing Layer — Production V1
=====================================================

A strategic interpretation layer that provides a structured,
engineering-grounded framework for biological nutrient removal under:
  - uncertain influent characterisation
  - cold temperature conditions
  - extreme hydraulic variability
  - brownfield constraints

Design principles
-----------------
- Does NOT modify the Stress Engine, Stack Generator, or any other layer.
- Reads already-generated outputs (pathway, feasibility, context).
- Adds engineering context, safe harbour assumptions, red flags, and
  a staged future-proofing strategy aligned to the selected stack.
- Language: practical, non-promotional, engineering-led.

Main entry point
----------------
  build_bnr_strategy(pathway, feasibility, plant_context) -> BNRStrategyReport
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from apps.wastewater_app.stack_generator import (
    UpgradePathway,
    CT_HYDRAULIC, CT_SETTLING, CT_NITRIFICATION,
    CT_TN_POLISH, CT_TP_POLISH, CT_BIOLOGICAL, CT_WET_WEATHER,
    TI_COMAG, TI_BIOMAG, TI_MABR, TI_IFAS, TI_HYBAS, TI_MBBR,
    TI_BARDENPHO, TI_RECYCLE_OPT, TI_DENFILTER, TI_TERT_P,
    TI_INDENSE, TI_MIGINDENSE, TI_EQ_BASIN,
)
from apps.wastewater_app.feasibility_layer import FeasibilityReport


# ── BNR configuration constants ────────────────────────────────────────────────
BNR_MLE       = "MLE (Modified Ludzack-Ettinger)"
BNR_A2O       = "3-stage A2O (Anaerobic-Anoxic-Oxic)"
BNR_BARDENPHO = "4-stage Bardenpho"
BNR_BARDENPHO_PLUS = "5-stage Bardenpho + tertiary denitrification"


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class BNRConfiguration:
    """Maps effluent targets to an appropriate BNR process configuration."""
    configuration:   str          # BNR_MLE / BNR_A2O / BNR_BARDENPHO / BNR_BARDENPHO_PLUS
    tn_target_mg_l:  float
    tp_target_mg_l:  float
    key_process_elements: List[str]
    design_parameters:    List[str]   # zone sizing, HRT, recycle ratios
    tertiary_required:    bool
    dnf_required:         bool
    rationale:            str


@dataclass
class SafeHarbourAssumption:
    """A single conservative design assumption."""
    dimension:   str   # Carbon / Phosphorus / Temperature / Hydraulic
    assumption:  str
    trigger:     str   # the condition that makes this assumption binding
    action:      str   # what to do when the assumption is triggered
    triggered:   bool  # whether it fires for this scenario


@dataclass
class UpgradeStage:
    """One stage in the future-proofing upgrade sequence."""
    stage_number:   int
    label:          str
    technologies:   List[str]
    purpose:        str
    prerequisite:   str
    gate_condition: str   # what must be confirmed before next stage proceeds
    in_stack:       bool  # whether this stage is already in the recommended stack


@dataclass
class RedFlag:
    """An explicit engineering warning."""
    category:  str   # Hydraulic / Sequencing / Chemistry / Safety / Carbon
    severity:  str   # High / Medium
    warning:   str
    triggered: bool


@dataclass
class BNRStrategyReport:
    """Full BNR Strategy & Future-Proofing output."""
    # Section 1: Configuration matrix
    selected_configuration:  BNRConfiguration
    all_configurations:      List[BNRConfiguration]  # full matrix for reference

    # Section 2: Safe harbour assumptions
    safe_harbour:            List[SafeHarbourAssumption]
    any_triggered:           bool

    # Section 3: Staged future-proofing
    upgrade_stages:          List[UpgradeStage]

    # Section 4: Red flags
    red_flags:               List[RedFlag]
    high_severity_flags:     int

    # Section 5: Alignment
    stack_alignment_notes:   List[str]
    stack_is_aligned:        bool

    # Section 6: Decision tension
    decision_tension:        str

    # Validation flags
    bardenpho_without_dnf_for_tn5:  bool   # Case A
    dnf_after_biology_for_tn3:      bool   # Case B
    carbon_flag_for_low_cod:        bool   # Case C
    mabr_for_cold_constrained:      bool   # Case D
    hydraulic_flag_for_high_peaks:  bool   # Case E


# ── Section 1: BNR Configuration Matrix ───────────────────────────────────────

def _build_configuration_matrix() -> List[BNRConfiguration]:
    """Full BNR configuration matrix — targets to process architecture."""
    return [
        BNRConfiguration(
            configuration   = BNR_MLE,
            tn_target_mg_l  = 10.,
            tp_target_mg_l  = 2.0,
            key_process_elements=[
                "Single anoxic zone ahead of aeration (pre-anoxic configuration).",
                "Internal nitrate recycle (MLR) from aerobic to anoxic zone; target R \u2248 2\u20133.",
                "Secondary metal salt dosing (FeCl\u2083 or alum) to achieve TP \u22642 mg/L.",
            ],
            design_parameters=[
                "Anoxic zone HRT: 1.5\u20132.0 h (temperature-corrected).",
                "MLR ratio R = 2 as starting point; confirm with on-site TN monitoring.",
                "Aerobic SRT \u226510 d at 20\u00b0C; \u226515 d at 10\u00b0C for reliable nitrification.",
            ],
            tertiary_required = False,
            dnf_required      = False,
            rationale=(
                "MLE is appropriate for moderate TN and TP targets where biological "
                "denitrification driven by the pre-anoxic zone is sufficient. "
                "Chemical P dosing supplements EBPR to reliably achieve TP \u22642 mg/L."
            ),
        ),
        BNRConfiguration(
            configuration   = BNR_A2O,
            tn_target_mg_l  = 7.,
            tp_target_mg_l  = 1.0,
            key_process_elements=[
                "Anaerobic zone (2.0\u20132.5 h HRT) ahead of anoxic and aerobic zones.",
                "EBPR enabled \u2014 phosphorus release in anaerobic zone and luxury uptake "
                "in aerobic zone.",
                "Internal nitrate recycle (R \u2248 2\u20133) from aerobic to anoxic.",
                "Nitrified return must be minimised to the anaerobic zone to protect EBPR.",
            ],
            design_parameters=[
                "Anaerobic HRT 2.0\u20132.5 h \u2014 critical for PAO enrichment.",
                "Aerobic SRT \u226512 d at 20\u00b0C; \u226518 d at 10\u00b0C.",
                "RAS split: \u226550% of RAS to anaerobic zone to protect EBPR function.",
                "Confirm rbCOD/TN \u22652 for reliable EBPR; supplement carbon if necessary.",
            ],
            tertiary_required = False,
            dnf_required      = False,
            rationale=(
                "A2O delivers simultaneous nitrogen and phosphorus removal using anaerobic "
                "zone for PAO enrichment. EBPR reduces chemical dosing requirement but "
                "requires careful RAS and recycle management to protect the anaerobic zone."
            ),
        ),
        BNRConfiguration(
            configuration   = BNR_BARDENPHO,
            tn_target_mg_l  = 5.,
            tp_target_mg_l  = 0.5,
            key_process_elements=[
                "Second anoxic zone (post-aerobic) for additional denitrification "
                "of remaining NOx.",
                "First anoxic zone (MLR-fed) and second anoxic zone (endogenous "
                "denitrification) in series.",
                "Tertiary P filtration required for TP \u22640.5 mg/L.",
            ],
            design_parameters=[
                "First anoxic HRT: 2.0\u20132.5 h (pre-anoxic).",
                "Second anoxic HRT: 2.0\u20133.0 h \u2014 endogenous denitrification kinetics "
                "at 11\u00b0C require extended HRT.",
                "MLR R \u2248 2\u20134 into first anoxic zone.",
                "COD/TN \u22654 in settled influent required; conduct fractionation audit "
                "before design.",
            ],
            tertiary_required = True,
            dnf_required      = False,
            rationale=(
                "Bardenpho 4-stage achieves TN ~5 mg/L through dual anoxic zones. "
                "The second anoxic zone operates on endogenous carbon \u2014 its performance "
                "is temperature-dependent and must be sized for winter conditions. "
                "COD fractionation audit is mandatory before design."
            ),
        ),
        BNRConfiguration(
            configuration   = BNR_BARDENPHO_PLUS,
            tn_target_mg_l  = 3.,
            tp_target_mg_l  = 0.1,
            key_process_elements=[
                "5-stage Bardenpho: anaerobic \u2192 anoxic 1 \u2192 aerobic \u2192 anoxic 2 "
                "\u2192 reaeration.",
                "Tertiary denitrification filter (DNF) with external carbon (methanol or "
                "acetate) for TN \u22643 mg/L.",
                "High-rate chemical clarification (CoMag or equivalent) for TP \u22640.1 mg/L.",
            ],
            design_parameters=[
                "DNF DO setpoint at filter inlet must be < 0.5 mg/L.",
                "Methanol dose 2.5\u20133.0 mg/mg NO\u2083-N removed.",
                "CoMag or equivalent: SOR 10\u201320 m/hr with FeCl\u2083 co-dosing.",
                "MANDATORY SEQUENCE: Bardenpho stable \u2192 MABR achieves NH\u2084 "
                "< 1 mg/L \u2192 DNF commissioned.",
            ],
            tertiary_required = True,
            dnf_required      = True,
            rationale=(
                "Achieving TN \u22643 mg/L requires tertiary denitrification \u2014 biological "
                "processes alone cannot reliably achieve this target. DNF must not be "
                "commissioned before upstream nitrification achieves NH\u2084 < 1 mg/L: "
                "DNF removes NOx, not ammonia. TP \u22640.1 mg/L requires high-rate "
                "chemical clarification as a tertiary polishing step."
            ),
        ),
    ]


def _select_configuration(
    pathway: UpgradePathway,
    ctx: Dict,
    matrix: List[BNRConfiguration],
) -> BNRConfiguration:
    """Select the appropriate BNR configuration based on targets and stack."""
    tn_tgt = float(ctx.get("tn_target_mg_l") or
                   ctx.get("tn_out_upgraded_mg_l") or 10.)
    tp_tgt = float(ctx.get("tp_target_mg_l") or 1.)
    tech_set = {s.technology for s in pathway.stages}

    # Use actual stack as primary signal, targets as tiebreaker
    has_dnf   = TI_DENFILTER in tech_set
    has_bard  = TI_BARDENPHO in tech_set or TI_RECYCLE_OPT in tech_set
    has_tertp = TI_TERT_P in tech_set or TI_COMAG in tech_set

    if has_dnf or tn_tgt <= 3.:
        return next(c for c in matrix if c.configuration == BNR_BARDENPHO_PLUS)
    if has_bard and (tn_tgt <= 5. or has_tertp):
        return next(c for c in matrix if c.configuration == BNR_BARDENPHO)
    if tn_tgt <= 7.:
        return next(c for c in matrix if c.configuration == BNR_A2O)
    return next(c for c in matrix if c.configuration == BNR_MLE)


# ── Section 2: Safe Harbour Assumptions ───────────────────────────────────────

def _build_safe_harbour(
    pathway: UpgradePathway,
    ctx: Dict,
) -> List[SafeHarbourAssumption]:
    """Build safe harbour assumptions. Each flags whether it is triggered."""
    tech_set   = {s.technology for s in pathway.stages}
    ct_set     = {c.constraint_type for c in pathway.constraints}
    tn_tgt     = float(ctx.get("tn_target_mg_l") or 10.)
    tp_tgt     = float(ctx.get("tp_target_mg_l") or 1.)
    cod_tn     = ctx.get("cod_tn_ratio")   # if explicitly supplied
    carbon_lim = bool(ctx.get("carbon_limited_tn", False))
    cold       = bool(ctx.get("cold_temperature", False)) or \
                 (ctx.get("temp_celsius") is not None and
                  float(ctx.get("temp_celsius", 20.)) <= 12.)
    aer_constr = bool(ctx.get("aeration_constrained", False))
    flow_ratio = float(ctx.get("flow_ratio", 1.0) or 1.0)
    has_mabr   = TI_MABR in tech_set
    has_dnf    = TI_DENFILTER in tech_set

    assumptions = []

    # ── Carbon buffer ──────────────────────────────────────────────────────────
    carbon_triggered = carbon_lim or (cod_tn is not None and float(cod_tn) < 4.)
    assumptions.append(SafeHarbourAssumption(
        dimension  = "Carbon availability",
        assumption = "Assume COD:TN \u226512:1 (raw influent) is required for reliable "
                     "biological TN removal across all seasons. If bioavailable "
                     "(readily biodegradable) COD:TN < 4:1 in settled influent, "
                     "denitrification will be carbon-limited.",
        trigger    = "Bioavailable COD:TN < 4:1 in settled influent (confirmed by "
                     "COD fractionation audit, minimum summer and winter measurements).",
        action     = "Include external carbon dosing (methanol or acetate) in the "
                     "process design. Pre-qualify dual carbon suppliers. Budget for "
                     "ongoing chemical OPEX in the lifecycle cost model.",
        triggered  = carbon_triggered,
    ))

    # ── Phosphorus buffer ──────────────────────────────────────────────────────
    tp_triggered = tp_tgt <= 0.2
    assumptions.append(SafeHarbourAssumption(
        dimension  = "Phosphorus removal",
        assumption = "Assume EBPR alone achieves ~1.0 mg/L TP under good operating "
                     "conditions. For TP \u22640.5 mg/L, supplementary chemical dosing "
                     "is required. For TP \u22640.1 mg/L, a dedicated tertiary chemical "
                     "polishing step (high-rate clarification or filtration) is mandatory.",
        trigger    = "TP licence target \u22640.2 mg/L, or effluent TP consistently "
                     "exceeding the licence limit despite optimised EBPR.",
        action     = "Include CoMag or tertiary chemical clarification (FeCl\u2083 + "
                     "filtration) in the process design. Size for chemical sludge volume "
                     "increase \u2014 audit dewatering and disposal capacity before design. "
                     "Note: TP \u22640.1 mg/L significantly increases chemical sludge production.",
        triggered  = tp_triggered,
    ))

    # ── Temperature factor ─────────────────────────────────────────────────────
    temp_triggered = cold and aer_constr
    assumptions.append(SafeHarbourAssumption(
        dimension  = "Temperature and aeration",
        assumption = "At \u226412\u00b0C, nitrification kinetics are significantly reduced "
                     "(Arrhenius factor \u03b8 = 1.07\u20131.08 per \u00b0C). At 11\u00b0C, "
                     "nitrification rate is ~40\u201350% of the 20\u00b0C design rate. "
                     "If aeration blowers are at or near capacity, oxygen delivery "
                     "becomes the binding constraint under cold conditions.",
        trigger    = "Operating temperature \u226412\u00b0C AND aeration system at or above "
                     "85% of rated capacity.",
        action     = "MABR (membrane-aerated biofilm reactor) is required to provide "
                     "supplementary oxygen delivery independent of blower capacity. "
                     "IFAS is not appropriate when blowers are constrained. "
                     "Do not commission MABR during winter \u2014 biofilm establishment "
                     "takes 4\u20138 weeks and performance is suboptimal below 12\u00b0C.",
        triggered  = temp_triggered,
    ))

    # ── Hydraulic variability ──────────────────────────────────────────────────
    hyd_triggered = flow_ratio >= 3.0
    assumptions.append(SafeHarbourAssumption(
        dimension  = "Hydraulic variability",
        assumption = "Assume peak wet weather flows at or above 2.5\u00d7 ADWF create "
                     "clinically significant hydraulic stress on secondary clarifiers. "
                     "Above 3\u00d7 ADWF, process intensification alone (biological "
                     "upgrades, carrier media, MABR) is insufficient \u2014 hydraulic "
                     "infrastructure intervention is required.",
        trigger    = "Design peak flow \u22653\u00d7 ADWF, or frequent clarifier "
                     "SOR exceedances during wet weather events.",
        action     = "Install CoMag (or equivalent high-rate clarification) for immediate "
                     "hydraulic relief. Assess I/I reduction programme and upstream "
                     "attenuation (EQ storage) as a long-term parallel workstream. "
                     "CoMag mitigates but does not fully replace the need for upstream "
                     "attenuation at peak flows above 3\u00d7 ADWF.",
        triggered  = hyd_triggered,
    ))

    # ── DNF prerequisite ───────────────────────────────────────────────────────
    dnf_triggered = has_dnf or tn_tgt <= 3.
    assumptions.append(SafeHarbourAssumption(
        dimension  = "DNF sequencing prerequisite",
        assumption = "DNF (denitrification filter) removes dissolved NOx. It cannot "
                     "compensate for incomplete nitrification. If NH\u2084 is not "
                     "reliably below 1 mg/L upstream, methanol carbon dose produces "
                     "no TN reduction and is wasted.",
        trigger    = "TN licence target \u22643 mg/L, or DNF is included in the "
                     "upgrade pathway.",
        action     = "Enforce commissioning gate: DNF must not be installed or "
                     "operated until MABR (or IFAS) has demonstrated NH\u2084 < 1 mg/L "
                     "across both summer and winter profiles. This is a "
                     "non-negotiable engineering sequence.",
        triggered  = dnf_triggered,
    ))

    return assumptions


# ── Section 3: Staged Future-Proofing Strategy ────────────────────────────────

def _build_upgrade_stages(
    pathway: UpgradePathway,
    ctx: Dict,
    selected_config: BNRConfiguration,
) -> List[UpgradeStage]:
    """Build the four-stage future-proofing upgrade sequence."""
    tech_set  = {s.technology for s in pathway.stages}
    tn_tgt    = float(ctx.get("tn_target_mg_l") or 10.)

    stages = [
        UpgradeStage(
            stage_number  = 1,
            label         = "Stage 1 \u2014 Hydraulic Stabilisation",
            technologies  = ["CoMag\u00ae (or equivalent high-rate clarification)",
                             "EQ basin / storm storage (long-term parallel workstream)"],
            purpose       = (
                "Prevent biomass washout and secondary clarifier overload under peak wet "
                "weather flows. This is the prerequisite for all subsequent biological "
                "upgrades \u2014 no biological upgrade delivers compliance if the "
                "clarifier is overwhelmed at peak flow."
            ),
            prerequisite  = "None \u2014 Stage 1 may commence immediately.",
            gate_condition= (
                "Clarifier SOR confirmed stable at peak flow events. "
                "Biomass washout events eliminated. CoMag performance KPIs met."
            ),
            in_stack = (TI_COMAG in tech_set or TI_BIOMAG in tech_set
                        or TI_EQ_BASIN in tech_set),
        ),
        UpgradeStage(
            stage_number  = 2,
            label         = "Stage 2 \u2014 Biological Intensification",
            technologies  = ["MABR OxyFAS\u00ae (primary pathway where aeration is constrained)",
                             "IFAS / Hybas\u2122 (where blower headroom \u226515% is confirmed)"],
            purpose       = (
                "Increase nitrification capacity and achieve reliable NH\u2084 < 1 mg/L "
                "across winter and summer profiles. MABR is the preferred pathway where "
                "blowers are at or near capacity. IFAS is preferred where confirmed "
                "blower headroom exists."
            ),
            prerequisite  = (
                "Stage 1 complete and hydraulic performance stable. "
                "Aeration capacity audit completed to determine MABR vs IFAS pathway."
            ),
            gate_condition= (
                "NH\u2084 < 1 mg/L confirmed across minimum one full summer + winter cycle. "
                "This gate is mandatory before Stage 3b (DNF) is commissioned."
            ),
            in_stack = (TI_MABR in tech_set or TI_IFAS in tech_set
                        or TI_HYBAS in tech_set),
        ),
        UpgradeStage(
            stage_number  = 3,
            label         = "Stage 3 \u2014 Nutrient Polishing",
            technologies  = (
                ["Bardenpho zone optimisation (mandatory first step)",
                 "COD fractionation audit before design",
                 "Denitrification filter (DNF) \u2014 only after Stage 2 gate is passed"]
                if tn_tgt <= 3. else
                ["Bardenpho zone optimisation",
                 "COD fractionation audit before design"]
            ),
            purpose       = (
                "Achieve TN compliance target through biological optimisation first, "
                "then chemical tertiary denitrification (DNF) if needed for TN \u22643 mg/L. "
                "Bardenpho optimisation must be exhausted before DNF is commissioned "
                "\u2014 biological denitrification is always the lower-cost first step."
            ),
            prerequisite  = (
                "Stage 2 gate passed: NH\u2084 < 1 mg/L confirmed summer and winter. "
                "COD fractionation audit completed. "
                "DNF methanol supply chain, safety management plan, and permits in place "
                "before DNF commissioning."
                if tn_tgt <= 3. else
                "Stage 2 gate passed. COD fractionation audit completed."
            ),
            gate_condition= (
                "TN compliance achieved and stable across seasons. "
                "If DNF deployed: methanol dose rate optimised and TN < 3 mg/L "
                "confirmed across winter profile."
            ),
            in_stack = (TI_BARDENPHO in tech_set or TI_RECYCLE_OPT in tech_set
                        or TI_DENFILTER in tech_set),
        ),
        UpgradeStage(
            stage_number  = 4,
            label         = "Stage 4 \u2014 Tertiary Phosphorus",
            technologies  = ["Tertiary chemical polishing (FeCl\u2083 dosing + filtration)",
                             "CoMag (if not already in Stage 1, dual-use for TP \u22640.1 mg/L)"],
            purpose       = (
                "Achieve TP \u22640.5 mg/L (filtration) or TP \u22640.1 mg/L "
                "(high-rate chemical clarification). Chemical tertiary P polishing is "
                "the only reliable pathway to TP \u22640.1 mg/L. EBPR alone cannot "
                "reliably achieve this target from a typical municipal influent."
            ),
            prerequisite  = (
                "Secondary biological treatment stable. "
                "Dewatering and disposal capacity for increased chemical sludge volume "
                "confirmed before commissioning \u2014 tertiary P dosing significantly "
                "increases sludge production."
            ),
            gate_condition= (
                "TP < target confirmed across seasons. Chemical sludge disposal "
                "pathway confirmed and operating within capacity."
            ),
            in_stack = (TI_TERT_P in tech_set or TI_COMAG in tech_set
                        or TI_BIOMAG in tech_set),
        ),
    ]
    return stages


# ── Section 4: Engineering Red Flags ──────────────────────────────────────────

def _build_red_flags(
    pathway: UpgradePathway,
    ctx: Dict,
    selected_config: BNRConfiguration,
) -> List[RedFlag]:
    """Build the set of mandatory engineering red flags."""
    tech_set   = {s.technology for s in pathway.stages}
    flow_ratio = float(ctx.get("flow_ratio", 1.0) or 1.0)
    has_dnf    = TI_DENFILTER in tech_set or selected_config.dnf_required
    tp_tgt     = float(ctx.get("tp_target_mg_l") or 1.)
    cold       = bool(ctx.get("cold_temperature", False)) or \
                 (ctx.get("temp_celsius") is not None and
                  float(ctx.get("temp_celsius", 20.)) <= 12.)
    aer_constr = bool(ctx.get("aeration_constrained", False))
    carbon_lim = bool(ctx.get("carbon_limited_tn", False))
    has_mabr   = TI_MABR in tech_set

    flags = []

    # ── Hydraulic reality (always included if flow_ratio >= 2.5) ──────────────
    flags.append(RedFlag(
        category  = "Hydraulic",
        severity  = "High" if flow_ratio >= 3.0 else "Medium",
        warning   = (
            f"At {flow_ratio:.1f}\u00d7 ADWF, process intensification alone is insufficient. "
            "Secondary clarifiers will be periodically overloaded regardless of biological "
            "upgrade. Long-term solutions require EQ storage, upstream I/I reduction, or "
            "high-rate clarification (CoMag) as a parallel workstream. "
            "Biological upgrades (MABR, IFAS, Bardenpho) do not resolve clarifier hydraulic "
            "overload and must not be relied upon to achieve compliance during storm events."
        ),
        triggered = flow_ratio >= 2.5,
    ))

    # ── DNF sequencing ─────────────────────────────────────────────────────────
    flags.append(RedFlag(
        category  = "Sequencing",
        severity  = "High",
        warning   = (
            "DNF must not be commissioned until nitrification is stable (NH\u2084 "
            "< 1 mg/L confirmed across both summer and winter profiles). DNF removes "
            "NOx \u2014 it cannot compensate for incomplete nitrification. If NH\u2084 "
            "is elevated at the DNF inlet, methanol carbon dose is consumed without "
            "producing TN reduction. This is a non-negotiable engineering guardrail, "
            "not a scheduling preference."
        ),
        triggered = has_dnf,
    ))

    # ── Sludge production ──────────────────────────────────────────────────────
    flags.append(RedFlag(
        category  = "Chemistry",
        severity  = "Medium",
        warning   = (
            "Achieving TP \u22640.1 mg/L through chemical tertiary polishing significantly "
            "increases chemical sludge production relative to secondary treatment alone. "
            "Dewatering capacity (centrifuge or belt press throughput), cake storage, and "
            "ultimate disposal pathway must be audited and confirmed to accommodate the "
            "additional sludge volume before Stage 4 is commissioned."
        ),
        triggered = tp_tgt <= 0.2,
    ))

    # ── DNF safety ────────────────────────────────────────────────────────────
    flags.append(RedFlag(
        category  = "Safety",
        severity  = "High",
        warning   = (
            "DNF systems using methanol require appropriate safety design and hazardous "
            "area classification. Methanol is a flammable liquid (flash point 11\u00b0C) "
            "with toxic vapour. Requirements include: bunded storage, ventilation, ATEX "
            "electrical classification in storage and dosing areas, spill containment, "
            "and operator safety training. Regulatory approval of chemical storage and "
            "handling permits must be obtained before construction commences."
        ),
        triggered = has_dnf,
    ))

    # ── Cold temperature nitrification ────────────────────────────────────────
    flags.append(RedFlag(
        category  = "Temperature",
        severity  = "High" if (cold and aer_constr) else "Medium",
        warning   = (
            "Cold operating temperatures (\u226412\u00b0C) reduce nitrification kinetics "
            "by 40\u201350% relative to 20\u00b0C design conditions (Arrhenius "
            "\u03b8 \u2248 1.07\u20131.08). "
            + ("At this plant, aeration is already near capacity: MABR is the correct "
               "response to deliver additional oxygen independently of blower constraints. "
               "MABR commissioning should be scheduled for spring to avoid the winter "
               "biofilm establishment window."
               if (cold and aer_constr) else
               "Confirm aerobic SRT is \u226515 d at the winter design temperature before "
               "assuming nitrification compliance is achievable without upgrade. "
               "If blower headroom exists, IFAS can assist with nitrification SRT decoupling.")
        ),
        triggered = cold or aer_constr,
    ))

    # ── Carbon limitation ─────────────────────────────────────────────────────
    flags.append(RedFlag(
        category  = "Carbon",
        severity  = "Medium",
        warning   = (
            "Carbon limitation for denitrification is flagged for this scenario. "
            "If bioavailable COD:TN < 4:1 in settled influent, Bardenpho zone "
            "optimisation will not achieve the TN target without external carbon "
            "supplementation. Conduct a COD fractionation audit (rbCOD measurement, "
            "summer and winter minimum) before finalising Stage 3 design. "
            "Do not design or budget Stage 3 without this data."
        ),
        triggered = carbon_lim,
    ))

    # ── MABR N₂O co-benefit ───────────────────────────────────────────────────
    flags.append(RedFlag(
        category  = "Carbon accounting",
        severity  = "Medium",
        warning   = (
            "MABR is included in the upgrade pathway. N\u2082O offgas reduction is a "
            "potential co-benefit (indicative 14\u201338% total CO\u2082e reduction, "
            "IPCC AR6 EF range). This must not be presented as a confirmed figure. "
            "Establish continuous N\u2082O baseline monitoring before MABR commissioning "
            "to convert the carbon claim from indicative to verified. Without a "
            "measured baseline, no carbon credit can be claimed post-upgrade."
        ),
        triggered = has_mabr,
    ))

    return flags


# ── Section 5: Stack alignment notes ──────────────────────────────────────────

def _build_alignment_notes(
    pathway: UpgradePathway,
    ctx: Dict,
    selected_config: BNRConfiguration,
) -> Tuple[List[str], bool]:
    """Confirm the recommended stack aligns with BNR strategy principles."""
    tech_set   = {s.technology for s in pathway.stages}
    notes      = []
    aligned    = True
    tn_tgt     = float(ctx.get("tn_target_mg_l") or 10.)
    aer_constr = bool(ctx.get("aeration_constrained", False))

    # MABR alignment
    if aer_constr:
        if TI_MABR in tech_set:
            notes.append(
                "\u2714 MABR correctly selected: aeration is at or near capacity and MABR "
                "provides supplementary oxygen delivery independent of blower constraints.")
        elif TI_IFAS in tech_set or TI_HYBAS in tech_set:
            notes.append(
                "\u26a0 IFAS is in the stack but aeration is flagged as constrained. "
                "Confirm blower headroom (\u226515% spare capacity) before proceeding \u2014 "
                "if blowers are at maximum, MABR is the correct technology.")
            aligned = False
    elif TI_IFAS in tech_set or TI_HYBAS in tech_set:
        notes.append(
            "\u2714 IFAS correctly selected: blower headroom is available and nitrification "
            "SRT decoupling is the primary requirement.")

    # DNF sequencing
    if TI_DENFILTER in tech_set:
        if TI_MABR in tech_set or TI_IFAS in tech_set or TI_HYBAS in tech_set:
            notes.append(
                "\u2714 DNF correctly placed after MABR/IFAS in the upgrade sequence. "
                "The commissioning gate (NH\u2084 < 1 mg/L confirmed) must be enforced "
                "before DNF is installed.")
        else:
            notes.append(
                "\u274c DNF appears in the stack without a preceding nitrification upgrade. "
                "DNF removes NOx, not NH\u2084 \u2014 this is an invalid sequence.")
            aligned = False

    # CoMag role
    if TI_COMAG in tech_set:
        notes.append(
            "\u2714 CoMag correctly positioned as a hydraulic relief and/or tertiary P "
            "polishing technology. It is not being used as a biological treatment system.")

    # Bardenpho before DNF
    if TI_BARDENPHO in tech_set and TI_DENFILTER not in tech_set and tn_tgt <= 3.:
        notes.append(
            "\u2714 Bardenpho is in the stack. For TN \u22643 mg/L, DNF will be required "
            "after Bardenpho is stable \u2014 it should appear in the high-performance "
            "alternative pathway if not already in the primary stack.")

    # Tertiary P
    if TI_TERT_P in tech_set:
        notes.append(
            "\u2714 Tertiary P removal correctly placed as the final stage. Chemical sludge "
            "volume increase must be assessed before commissioning.")

    if not notes:
        notes.append(
            "\u2714 Recommended stack aligns with BNR strategy principles across all "
            "dimensions evaluated.")

    return notes, aligned


# ── Decision tension ───────────────────────────────────────────────────────────

_DECISION_TENSION = (
    "The strategy balances staged brownfield intensification against increasing process "
    "complexity, trading lower upfront disruption for higher operational sophistication "
    "and future upgrade flexibility. Each stage gate preserves capital optionality: "
    "if performance at one stage exceeds expectations, subsequent stages may be deferred "
    "or right-sized. If performance falls short, the gate prevents premature commitment "
    "to the next layer of investment."
)


# ── Main entry point ───────────────────────────────────────────────────────────

def build_bnr_strategy(
    pathway: UpgradePathway,
    feasibility: FeasibilityReport,
    plant_context: Optional[Dict] = None,
) -> BNRStrategyReport:
    """
    Build the BNR Strategy & Future-Proofing report.

    Parameters
    ----------
    pathway     : UpgradePathway   — output of build_upgrade_pathway()
    feasibility : FeasibilityReport — output of assess_feasibility()
    plant_context : dict, optional  — same context dict passed to other layers

    Returns
    -------
    BNRStrategyReport
        Does NOT modify pathway or feasibility.
    """
    ctx = plant_context or {}

    matrix           = _build_configuration_matrix()
    selected_config  = _select_configuration(pathway, ctx, matrix)
    safe_harbour     = _build_safe_harbour(pathway, ctx)
    upgrade_stages   = _build_upgrade_stages(pathway, ctx, selected_config)
    red_flags        = _build_red_flags(pathway, ctx, selected_config)
    alignment_notes, is_aligned = _build_alignment_notes(pathway, ctx, selected_config)

    tech_set   = {s.technology for s in pathway.stages}
    tn_tgt     = float(ctx.get("tn_target_mg_l") or 10.)
    flow_ratio = float(ctx.get("flow_ratio", 1.0) or 1.0)
    cold       = bool(ctx.get("cold_temperature", False)) or \
                 (ctx.get("temp_celsius") is not None and
                  float(ctx.get("temp_celsius", 20.)) <= 12.)
    aer_constr = bool(ctx.get("aeration_constrained", False))
    carbon_lim = bool(ctx.get("carbon_limited_tn", False))

    return BNRStrategyReport(
        selected_configuration = selected_config,
        all_configurations     = matrix,
        safe_harbour           = safe_harbour,
        any_triggered          = any(s.triggered for s in safe_harbour),
        upgrade_stages         = upgrade_stages,
        red_flags              = red_flags,
        high_severity_flags    = sum(1 for f in red_flags
                                     if f.severity == "High" and f.triggered),
        stack_alignment_notes  = alignment_notes,
        stack_is_aligned       = is_aligned,
        decision_tension       = _DECISION_TENSION,
        # Validation flags
        bardenpho_without_dnf_for_tn5 = (
            tn_tgt <= 5. and tn_tgt > 3. and
            TI_BARDENPHO in tech_set and
            TI_DENFILTER not in tech_set
        ),
        dnf_after_biology_for_tn3 = (
            tn_tgt <= 3. and
            selected_config.dnf_required and
            selected_config.configuration == BNR_BARDENPHO_PLUS
        ),
        carbon_flag_for_low_cod = (
            carbon_lim and
            any(s.triggered for s in safe_harbour if s.dimension == "Carbon availability")
        ),
        mabr_for_cold_constrained = (
            cold and aer_constr and TI_MABR in tech_set
        ) or (
            cold and aer_constr and  # flagged even if MABR not yet in stack
            any(s.triggered for s in safe_harbour if s.dimension == "Temperature and aeration")
        ),
        hydraulic_flag_for_high_peaks = (
            flow_ratio >= 2.5 and
            any(f.triggered for f in red_flags if f.category == "Hydraulic")
        ),
    )
