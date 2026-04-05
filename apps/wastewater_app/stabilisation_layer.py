"""
apps/wastewater_app/stabilisation_layer.py

Stabilisation Layer — Production V1
=====================================

An optional pre-capital layer that identifies low-cost, low-regret,
low-disruption interventions that may be implemented before major capital
investment to improve process stability, reduce uncertainty, and de-risk
subsequent upgrades.

Design principles
-----------------
- Does NOT modify the primary stack in any way.
- Only included when a genuinely credible low-cost option exists.
- Suppressed entirely if no credible option is identifiable.
- Does NOT turn into "recommend inDENSE everywhere".
- Language: practical, engineering-led, non-promotional.

Guard rules
-----------
Rule 1: inDENSE as optional stabilisation — only when settling uncertainty exists,
        clarifier stress is real, or MLSS/SVI is elevated/variable/unknown.
Rule 2: inDENSE must NOT appear for MBR-only fouling, purely hydraulic,
        purely nitrification with stable clarifiers, or purely aeration.
Rule 3: Recycle optimisation only when TN is elevated and nitrification is compliant.
Rule 4: DO/aeration audit only when aeration is near-constrained and NH4 borderline.
Rule 5: COD fractionation only when TN performance may be carbon-limited.
Rule 6: Monitoring/trial only when major capital decision depends on unconfirmed bottleneck.
Rule 7: Never more than 4 options. Suppress section entirely if none credible.

Main entry point
----------------
  build_stabilisation_report(pathway, plant_context) -> StabilisationReport
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apps.wastewater_app.stack_generator import (
    UpgradePathway,
    CT_HYDRAULIC, CT_SETTLING, CT_NITRIFICATION,
    CT_TN_POLISH, CT_TP_POLISH, CT_BIOLOGICAL,
    CT_MEMBRANE, CT_WET_WEATHER,
    TI_INDENSE, TI_MIGINDENSE, TI_MEMDENSE,
    TI_HYBAS, TI_IFAS, TI_MBBR, TI_MABR,
    TI_COMAG, TI_BIOMAG, TI_EQ_BASIN,
    TI_BARDENPHO, TI_RECYCLE_OPT,
    TI_DENFILTER,
)

# ── Capital classification constants ──────────────────────────────────────────
CAP_DEFER  = "May defer capital"
CAP_DERISK = "De-risks capital"
CAP_OPS    = "Improves operational confidence only"


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class StabilisationOption:
    """A single low-cost stabilisation option."""
    name:           str
    why_it_helps:   str   # engineering rationale
    what_it_does_not_solve: str   # explicit limitation
    when_to_use:    str
    capital_class:  str   # CAP_DEFER / CAP_DERISK / CAP_OPS
    estimated_cost: str   # "Nil–Low", "Low", "Low–Medium"
    time_to_result: str   # "Immediate", "1–3 months", "3–6 months"


@dataclass
class StabilisationReport:
    """Full output of the stabilisation layer."""
    options:         List[StabilisationOption]
    has_options:     bool
    preamble:        str   # intro paragraph if options exist
    nil_message:     str   # message when no options exist
    # Validation flags (for test suite)
    indense_included:      bool
    indense_excluded:      bool   # explicitly suppressed for correct reason
    recycle_included:      bool
    do_audit_included:     bool
    cod_audit_included:    bool
    monitoring_included:   bool


# ── Internal guard functions ───────────────────────────────────────────────────

def _settling_uncertainty_credible(pathway: UpgradePathway, ctx: Dict) -> bool:
    """
    True when there is a credible settling or biomass stability concern justifying
    inDENSE as a stabilisation option.

    Requires at least one CONTEXT-LEVEL signal (operator-supplied / plant-data-derived).
    A stress-engine-derived CT_SETTLING constraint alone is NOT sufficient — the engine
    fires clarifier SOR for almost any PWWF scenario regardless of whether settling is
    the clinical bottleneck.

    Accepted signals:
    - high_mlss          MLSS elevated or variable (operator flag)
    - svi_elevated       SVI outside normal range
    - svi_unknown        SVI not characterised
    - solids_carryover   Visible TSS carry-over in dry weather
    - clarifier_util>=0.85  Approaching design capacity (caller-supplied)
    - capex_constrained AND High/Medium settling constraint confirmed in pathway
    """
    high_mlss         = bool(ctx.get("high_mlss", False))
    svi_elevated      = bool(ctx.get("svi_elevated", False))
    svi_unknown       = bool(ctx.get("svi_unknown", False))
    solids_carryover  = bool(ctx.get("solids_carryover", False))
    clarifier_util    = ctx.get("clarifier_util", 0.0) or 0.0
    capex_constrained = bool(ctx.get("capex_constrained", False))

    has_context = (
        high_mlss
        or svi_elevated
        or svi_unknown
        or solids_carryover
        or clarifier_util >= 0.85
    )

    # capex_constrained + confirmed High/Medium settling in stack is also credible
    if not has_context and capex_constrained:
        ct_set  = {c.constraint_type for c in pathway.constraints}
        sev_map = {c.constraint_type: c.severity for c in pathway.constraints}
        if (CT_SETTLING in ct_set
                and sev_map.get(CT_SETTLING, "Low") in ("High", "Medium")):
            has_context = True

    return has_context


def _indense_excluded(pathway: UpgradePathway, ctx: Dict) -> bool:
    """
    True when inDENSE must NOT be suggested as stabilisation.
    MBR-only fouling, purely hydraulic, purely nitrification with stable clarifiers.
    """
    is_mbr     = bool(ctx.get("is_mbr", False))
    ct_set     = {c.constraint_type for c in pathway.constraints}
    tech_set   = {s.technology for s in pathway.stages}

    # MBR case — memDENSE territory always; inDENSE is never appropriate
    # (MBR settling is handled by membrane biomass selection, not gravimetric selection)
    if is_mbr:
        return True

    # Purely hydraulic — CoMag / EQ basin are primary; inDENSE irrelevant
    if ct_set == {CT_HYDRAULIC} or ct_set == {CT_WET_WEATHER}:
        return True

    # Purely nitrification with stable clarifiers AND no settling uncertainty
    purely_nit = ct_set <= {CT_NITRIFICATION} and not _settling_uncertainty_credible(pathway, ctx)
    if purely_nit:
        return True

    # Already in primary stack — no need to repeat as stabilisation
    if TI_INDENSE in tech_set or TI_MIGINDENSE in tech_set:
        return True

    return False


def _recycle_credible(pathway: UpgradePathway, ctx: Dict) -> bool:
    """TN elevated AND nitrification compliant AND recycle not yet in stack."""
    ct_set   = {c.constraint_type for c in pathway.constraints}
    tech_set = {s.technology for s in pathway.stages}
    tn_at_limit  = bool(ctx.get("tn_at_limit", False))
    nh4_compliant= not bool(ctx.get("nh4_near_limit", False))
    already_in   = TI_RECYCLE_OPT in tech_set or TI_BARDENPHO in tech_set

    return (
        (CT_TN_POLISH in ct_set or CT_BIOLOGICAL in ct_set)
        and tn_at_limit
        and nh4_compliant
        and not already_in
    )


def _do_audit_credible(pathway: UpgradePathway, ctx: Dict) -> bool:
    """Aeration near-constrained OR NH4 borderline, and not purely settling."""
    ct_set  = {c.constraint_type for c in pathway.constraints}
    tech_set= {s.technology for s in pathway.stages}
    aer_constrained = bool(ctx.get("aeration_constrained", False))
    nh4_near        = bool(ctx.get("nh4_near_limit", False))
    has_mabr        = TI_MABR in tech_set   # already recommended — audit still valid pre-capital
    has_nit_ct      = CT_NITRIFICATION in ct_set

    # Not useful if purely settling or purely hydraulic with no biological issue
    if ct_set <= {CT_SETTLING} or ct_set <= {CT_HYDRAULIC, CT_WET_WEATHER}:
        return False

    return (aer_constrained or nh4_near) and (has_nit_ct or has_mabr)


def _cod_audit_credible(pathway: UpgradePathway, ctx: Dict) -> bool:
    """Carbon-limited TN or Bardenpho in stack — COD fractionation de-risks decision."""
    ct_set   = {c.constraint_type for c in pathway.constraints}
    tech_set = {s.technology for s in pathway.stages}
    carbon_limited = bool(ctx.get("carbon_limited_tn", False))
    has_tn         = CT_TN_POLISH in ct_set or CT_BIOLOGICAL in ct_set
    has_bardenpho  = TI_BARDENPHO in tech_set or TI_RECYCLE_OPT in tech_set
    has_dnf        = TI_DENFILTER in tech_set

    return has_tn and (carbon_limited or has_bardenpho or has_dnf)


def _monitoring_credible(pathway: UpgradePathway, ctx: Dict) -> bool:
    """
    Include a monitoring / trial programme when:
    - Major capital decision depends on unconfirmed bottleneck
    - Carbon claims need on-site N2O validation
    - Data confidence is low / medium
    - Multi-constraint and high uncertainty
    """
    n_constraints = len(pathway.constraints)
    high_value_capital = (
        any(s.capex_class == "High" for s in pathway.stages)
        or any(s.technology in (TI_COMAG, TI_BIOMAG, TI_MABR, TI_EQ_BASIN)
               for s in pathway.stages)
    )
    multi = pathway.multi_constraint
    capex_constrained = bool(ctx.get("capex_constrained", False))
    needs_n2o_validation = bool(ctx.get("tn_at_limit", False)) or n_constraints >= 2

    return high_value_capital or (multi and needs_n2o_validation) or capex_constrained


# ── Option builders ────────────────────────────────────────────────────────────

def _indense_option(pathway: UpgradePathway, ctx: Dict) -> StabilisationOption:
    is_sbr = bool(ctx.get("is_sbr", False))
    ct_set = {c.constraint_type for c in pathway.constraints}
    tech_names = [s.technology for s in pathway.stages]

    primary_has_biomag = TI_BIOMAG in tech_names or TI_COMAG in tech_names
    has_hyd = CT_HYDRAULIC in ct_set or CT_WET_WEATHER in ct_set

    if is_sbr:
        basis = (
            "inDENSE gravimetric selection may be trialled as a low-cost first step in the SBR "
            "intensification programme. It improves sludge settleability and density, reduces SVI "
            "variability, and enables shorter or more productive cycle operation. "
            "This allows the utility to confirm the settling improvement before committing to the "
            "full MOB programme (inDENSE + miGRATE)."
        )
        not_solve = (
            "inDENSE alone does not address cycle throughput under wet weather, does not replace "
            "miGRATE for biological optimisation, and does not provide hydraulic attenuation."
        )
        cap_class = CAP_DEFER
        when = (
            "When capital for the full MOB programme is constrained and settling confirmation is "
            "required before committing to carrier installation and cycle compression."
        )
    elif primary_has_biomag and has_hyd:
        basis = (
            "inDENSE may be trialled as a low-cost interim measure to improve baseline sludge "
            "settleability and reduce SVI variability before the BioMag programme is commissioned. "
            "This provides early process stability data and helps confirm the magnitude of the "
            "settling improvement achievable within existing tanks."
        )
        not_solve = (
            "inDENSE does not provide the combined settling and biological intensification of BioMag, "
            "does not address hydraulic peak flows, and does not replace CoMag or EQ basin "
            "for wet weather events."
        )
        cap_class = CAP_DERISK
        when = (
            "When the utility wants early evidence of settleability improvement before committing "
            "to the full BioMag capital programme, or as a bridge intervention during procurement."
        )
    else:
        basis = (
            "inDENSE may be trialled as a low-cost stabilisation step to improve sludge "
            "settleability, reduce SVI variability, and de-risk subsequent upgrade decisions. "
            "Gravitational selection progressively improves biomass density without major civil works "
            "or operational disruption. Results are typically visible within 4\u20138 weeks of commissioning."
        )
        not_solve = (
            "inDENSE does not address nitrification SRT limitations, hydraulic overload, or TN/TP "
            "compliance directly. It is a settling stabilisation measure only."
        )
        cap_class = CAP_DERISK
        when = (
            "When MLSS is elevated or SVI is variable/unknown, clarifier performance is marginal, "
            "or the utility wants to characterise the settling baseline before committing to a "
            "larger capital programme."
        )

    return StabilisationOption(
        name          = "inDENSE\u00ae trial (settling stabilisation)",
        why_it_helps  = basis,
        what_it_does_not_solve = not_solve,
        when_to_use   = when,
        capital_class = cap_class,
        estimated_cost= "Low",
        time_to_result= "4\u20138 weeks post-commissioning",
    )


def _recycle_option(pathway: UpgradePathway) -> StabilisationOption:
    return StabilisationOption(
        name = "Internal recycle ratio optimisation",
        why_it_helps = (
            "The internal recycle (MLR) ratio directly controls denitrification efficiency. "
            "At R \u2248 2, approximately 67% of nitrate is recycled; at R = 4, approximately 80%. "
            "Where recycle pumps have headroom, increasing R to the engineering optimum (R \u2248 2\u20134) "
            "may measurably reduce effluent TN without capital spend. "
            "This should be the first TN optimisation step before any process reconfiguration."
        ),
        what_it_does_not_solve = (
            "Recycle optimisation alone cannot achieve TN < 5 mg/L if the carbon/TN ratio is "
            "insufficient, if nitrification is not stable, or if the process configuration lacks "
            "a functioning anoxic zone. It is a process tuning step, not a treatment upgrade."
        ),
        when_to_use = (
            "When TN is elevated, NH\u2084 is compliant, and there is reason to believe "
            "the internal recycle is not currently operating at the engineering optimum. "
            "Confirm MLR pump capacity before increasing ratio."
        ),
        capital_class = CAP_DEFER,
        estimated_cost= "Nil\u2013Low (control system adjustment + pump capacity verification)",
        time_to_result= "Immediate\u20131 month",
    )


def _do_option(pathway: UpgradePathway, ctx: Dict) -> StabilisationOption:
    aer_constrained = bool(ctx.get("aeration_constrained", False))
    has_mabr = TI_MABR in {s.technology for s in pathway.stages}

    if aer_constrained and has_mabr:
        why = (
            "Before commissioning MABR, optimising DO setpoints in existing aeration zones may "
            "recover some nitrification headroom and reduce over-aeration energy waste. "
            "Fine-grained DO control (targeting 1.5\u20132.0 mg/L rather than 3\u20134 mg/L) "
            "can reduce blower demand by 10\u201320% and reduce N\u2082O formation from "
            "partially anoxic zones. This may marginally defer or right-size the MABR installation."
        )
        not_solve = (
            "DO optimisation alone cannot resolve nitrification SRT limitation when blowers "
            "are genuinely at maximum capacity. It is a pre-capital tuning step and does not "
            "replace the MABR recommendation."
        )
        cap_class = CAP_DEFER
    else:
        why = (
            "DO setpoint optimisation may improve nitrification stability and reduce N\u2082O "
            "hot-spot formation before capital-intensive aeration upgrades are committed. "
            "Targeting DO 1.5\u20132.0 mg/L (rather than 3\u20134 mg/L where over-aerated) "
            "reduces energy consumption and may improve denitrification efficiency in anoxic zones."
        )
        not_solve = (
            "DO optimisation cannot resolve fundamentally insufficient aeration capacity. "
            "If blowers are genuinely at maximum, this is a tuning step only."
        )
        cap_class = CAP_OPS

    return StabilisationOption(
        name = "DO / aeration control optimisation",
        why_it_helps  = why,
        what_it_does_not_solve = not_solve,
        when_to_use   = (
            "When NH\u2084 is borderline or aeration is near-constrained. Confirm DO profiles "
            "across aeration zones with portable instrumentation before adjusting setpoints."
        ),
        capital_class = cap_class,
        estimated_cost= "Nil\u2013Low (control system adjustment + portable DO monitoring)",
        time_to_result= "Immediate\u20133 months",
    )


def _cod_option(pathway: UpgradePathway, ctx: Dict) -> StabilisationOption:
    has_dnf = TI_DENFILTER in {s.technology for s in pathway.stages}
    carbon_limited = bool(ctx.get("carbon_limited_tn", False))

    if has_dnf:
        why = (
            "A COD fractionation audit quantifies the readily biodegradable COD (rbCOD) fraction "
            "available for denitrification. This is required before sizing the denitrification "
            "filter carbon dose and confirming whether methanol is the appropriate carbon source. "
            "It also identifies whether primary effluent diversion or industrial trade waste "
            "could substitute as a lower-cost carbon source."
        )
        not_solve = (
            "The COD audit does not provide carbon for denitrification \u2014 it informs the "
            "carbon strategy. External carbon supply infrastructure is still required."
        )
        cap_class = CAP_DERISK
    elif carbon_limited:
        why = (
            "A COD fractionation audit (rbCOD measurement by season) quantifies whether the "
            "influent carbon is sufficient to support Bardenpho denitrification without external "
            "supplementation. If COD/TN < 4, external carbon dosing will be required. "
            "Confirming this before Bardenpho reconfiguration avoids designing a process zone "
            "that cannot achieve the intended TN target."
        )
        not_solve = (
            "The audit does not supply carbon. If carbon limitation is confirmed, external carbon "
            "dosing infrastructure must be designed and budgeted."
        )
        cap_class = CAP_DERISK
    else:
        why = (
            "A carbon audit (COD fractionation, COD/TN by season) characterises available "
            "biodegradable COD and confirms whether denitrification is carbon-limited. "
            "This de-risks the Bardenpho optimisation decision and confirms whether "
            "recycle optimisation alone can achieve the TN target."
        )
        not_solve = "The audit does not resolve carbon limitation \u2014 it characterises it."
        cap_class = CAP_DERISK

    return StabilisationOption(
        name = "COD fractionation / carbon audit",
        why_it_helps  = why,
        what_it_does_not_solve = not_solve,
        when_to_use   = (
            "Before committing to Bardenpho reconfiguration, external carbon dosing infrastructure, "
            "or a denitrification filter. Conduct by season (summer and winter minimum)."
        ),
        capital_class = cap_class,
        estimated_cost= "Low (laboratory analysis + data review, typically < $15k)",
        time_to_result= "1\u20133 months (sampling + analysis + interpretation)",
    )


def _monitoring_option(pathway: UpgradePathway, ctx: Dict) -> StabilisationOption:
    has_mabr      = TI_MABR in {s.technology for s in pathway.stages}
    has_comag     = TI_COMAG in {s.technology for s in pathway.stages}
    tn_at_limit   = bool(ctx.get("tn_at_limit", False))
    n2o_relevant  = tn_at_limit or has_mabr
    high_capex    = any(s.capex_class == "High" for s in pathway.stages)

    why_parts = []
    if has_mabr:
        why_parts.append(
            "Continuous N\u2082O offgas monitoring before MABR commissioning establishes a "
            "verified baseline emission factor. This converts post-upgrade N\u2082O reduction "
            "claims from indicative to measured, directly supporting carbon credit verification "
            "and net-zero reporting."
        )
    if has_comag:
        why_parts.append(
            "A wet weather event monitoring programme (flow, TSS, SOR, compliance) during the "
            "next 2\u20133 PWWF events characterises the actual hydraulic failure mode, confirms "
            "CoMag bypass capacity sizing, and de-risks the capital decision."
        )
    if not why_parts:
        why_parts.append(
            "Enhanced process monitoring (flow, MLSS, SVI, DO, NH\u2084, TN by hour across a "
            "2\u20134 week period) characterises the actual operating envelope and confirms "
            "which constraint is genuinely binding. This prevents capital commitment to the "
            "wrong first intervention."
        )

    return StabilisationOption(
        name = "Monitoring and process trial programme",
        why_it_helps  = " ".join(why_parts),
        what_it_does_not_solve = (
            "Monitoring does not improve process performance in itself. "
            "It reduces decision uncertainty and supports confident capital commitment, "
            "but does not defer major capital unless trial data reveals the constraint "
            "is less severe than modelled."
        ),
        when_to_use   = (
            "When a major capital decision (> $1M) depends on an unconfirmed bottleneck, "
            "when N\u2082O carbon claims require on-site validation, or when process data is "
            "insufficient to confidently size the recommended technology."
        ),
        capital_class = CAP_OPS if not high_capex else CAP_DERISK,
        estimated_cost= "Low\u2013Medium (instrumentation hire + data analysis, typically $10\u2013$50k)",
        time_to_result= "3\u20136 months (events-based for wet weather; 4 weeks minimum for process audit)",
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def build_stabilisation_report(
    pathway: UpgradePathway,
    plant_context: Optional[Dict] = None,
) -> StabilisationReport:
    """
    Build the Low-Cost Stabilisation Options report.

    Parameters
    ----------
    pathway : UpgradePathway
        Output of build_upgrade_pathway().

    plant_context : dict, optional
        Same dict passed to prior layers:
          is_sbr, is_mbr, high_mlss, svi_elevated, svi_unknown,
          solids_carryover, clarifier_util,
          nh4_near_limit, aeration_constrained,
          tn_at_limit, carbon_limited_tn,
          capex_constrained.

    Returns
    -------
    StabilisationReport
        Does NOT modify pathway.
    """
    ctx = plant_context or {}
    options: List[StabilisationOption] = []

    # Tracking flags for validation
    indense_inc  = False
    indense_exc  = False
    recycle_inc  = False
    do_inc       = False
    cod_inc      = False
    mon_inc      = False

    # ── inDENSE guard ────────────────────────────────────────────────────────
    if _indense_excluded(pathway, ctx):
        indense_exc = True
    elif _settling_uncertainty_credible(pathway, ctx):
        options.append(_indense_option(pathway, ctx))
        indense_inc = True

    # ── Recycle optimisation ──────────────────────────────────────────────────
    if _recycle_credible(pathway, ctx):
        options.append(_recycle_option(pathway))
        recycle_inc = True

    # ── DO / aeration audit ───────────────────────────────────────────────────
    if _do_audit_credible(pathway, ctx):
        options.append(_do_option(pathway, ctx))
        do_inc = True

    # ── COD audit ────────────────────────────────────────────────────────────
    if _cod_audit_credible(pathway, ctx):
        options.append(_cod_option(pathway, ctx))
        cod_inc = True

    # ── Monitoring / trial ────────────────────────────────────────────────────
    if _monitoring_credible(pathway, ctx):
        options.append(_monitoring_option(pathway, ctx))
        mon_inc = True

    # Cap at 4 options — take highest-value by capital classification order
    _class_order = {CAP_DEFER: 0, CAP_DERISK: 1, CAP_OPS: 2}
    options.sort(key=lambda o: _class_order.get(o.capital_class, 2))
    options = options[:4]

    has_opts = len(options) > 0

    if has_opts:
        preamble = (
            "Before committing to major capital upgrades, the following low-cost stabilisation "
            "measures may be considered. These measures do not replace the recommended stack, "
            "but may reduce uncertainty, improve operational stability, and in some cases "
            "defer capital commitment pending confirmed performance data."
        )
    else:
        preamble = ""

    nil_message = (
        "No credible low-cost stabilisation options identified ahead of the recommended "
        "capital pathway. The primary constraint requires a capital-grade intervention; "
        "process-level tuning is unlikely to meaningfully defer or de-risk the recommended stack."
    )

    return StabilisationReport(
        options           = options,
        has_options       = has_opts,
        preamble          = preamble,
        nil_message       = nil_message,
        indense_included  = indense_inc,
        indense_excluded  = indense_exc,
        recycle_included  = recycle_inc,
        do_audit_included = do_inc,
        cod_audit_included= cod_inc,
        monitoring_included = mon_inc,
    )
