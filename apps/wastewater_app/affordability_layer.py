"""
affordability_layer.py — WaterPoint v24Z73
Pre-CAPEX Decision Layer: Affordability Mode

Provides relative affordability, risk positioning, and decision framing.
Does NOT calculate actual CAPEX values.
Does NOT override engineering outputs.
This is a comparative decision layer only.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Band constants ─────────────────────────────────────────────────────────────
CAPEX_LOW         = "Low"
CAPEX_MEDIUM      = "Medium"
CAPEX_MEDIUM_HIGH = "Medium–High"
CAPEX_HIGH        = "High"

OPEX_LOW          = "Low"
OPEX_MODERATE     = "Moderate"
OPEX_MEDIUM_HIGH  = "Medium–High"
OPEX_HIGH         = "High"

COMPLEXITY_LOW    = "Low"
COMPLEXITY_MEDIUM = "Medium"
COMPLEXITY_HIGH   = "High"

RELIABILITY_HIGH      = "High"
RELIABILITY_MEDIUM    = "Medium"
RELIABILITY_SENSITIVE = "Sensitive"

DELIVERY_LOW    = "Low"
DELIVERY_MEDIUM = "Medium"
DELIVERY_HIGH   = "High"
DELIVERY_VERY_HIGH = "Very High"


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class AffordabilityOption:
    """One technology option in the affordability comparison."""
    label:              str           # e.g. "Brownfield Intensification"
    option_type:        str           # "brownfield" | "greenfield_conventional" | "greenfield_intensified"
    stack_summary:      List[str]     # short list of technologies
    capex_band:         str           # CAPEX_* constant
    opex_band:          str           # OPEX_* constant
    complexity:         str           # COMPLEXITY_* constant
    reliability:        str           # RELIABILITY_* constant
    delivery_risk:      str           # DELIVERY_* constant
    primary_risk_type:  str           # plain-language risk category
    failure_mode:       str           # "what fails first if assumptions are wrong"
    strategic_strengths: List[str]
    strategic_weaknesses: List[str]
    flexibility:        str           # "High" | "Medium" | "Low"
    upgrade_pathway:    str           # strength of future upgrade path
    carbon_closure_required: bool     # DNF / PdNA required?
    carbon_closure_tech: str          # "DNF" | "PdNA" | "DNF or PdNA" | ""


@dataclass
class AffordabilityComparison:
    """Full affordability comparison output."""
    options:                List[AffordabilityOption]
    comparison_table:       List[Dict[str, str]]      # rows: dimension → option values
    decision_framing:       str                        # mandatory trade-off statement
    board_bullets:          List[str]                  # 3–5 board-level summary points
    critical_insight:       str                        # shared constraint note (if any)
    preferred_path:         str                        # preferred path logic (Part 10)
    shared_carbon_closure:  bool                       # carbon closure required across all options
    shared_constraint_txt:  str                        # "eff COD:TN 4.22 — carbon-limited" etc.
    is_active:              bool = True                # False when only one option exists


# ── Classification helpers ─────────────────────────────────────────────────────

def _has_tech(stack: List[str], *keywords: str) -> bool:
    return any(any(kw.lower() in t.lower() for kw in keywords) for t in stack)


def _classify_stack(stack: List[str], option_type: str,
                    ctx: Dict) -> AffordabilityOption:
    """
    Derive affordability dimensions from a technology stack and context.
    All outputs are qualitative — no numbers.
    """
    carbon_lim   = bool(ctx.get("carbon_limited_tn", False))
    eff_codn     = float(ctx.get("eff_codn_val") or
                         (float(ctx.get("cod_mg_l", 0) or 0) * 0.6 /
                          max(float(ctx.get("tn_in_mg_l", 1) or 1), 0.1)))
    if eff_codn <= 0.: eff_codn = 999.
    carbon_closure = carbon_lim or eff_codn < 4.5

    has_comag   = _has_tech(stack, "CoMag", "CoMg")
    has_indense = _has_tech(stack, "inDENSE", "indense")
    has_mabr    = _has_tech(stack, "MABR")
    has_dnf     = _has_tech(stack, "Denitrification Filter", "DNF")
    has_pdna    = _has_tech(stack, "PdNA", "Anammox", "PN/A", "Partial Denif")
    has_mbr     = _has_tech(stack, "MBR")
    has_bardenpho = _has_tech(stack, "Bardenpho")
    has_tert_p  = _has_tech(stack, "Tertiary P", "TertP")
    n_stages    = len(stack)

    closure_tech = ("DNF or PdNA" if (has_dnf and has_pdna) else
                    "DNF"         if has_dnf else
                    "PdNA"        if has_pdna else "")

    # ── Brownfield ─────────────────────────────────────────────────────────────
    if option_type == "brownfield":
        # Civil work is minimised (existing concrete) but process/mechanical is extensive
        capex = (CAPEX_HIGH if (has_comag and has_indense and has_mabr) else
                 CAPEX_MEDIUM_HIGH if (has_comag or has_indense or has_mabr) else
                 CAPEX_MEDIUM)
        opex  = (OPEX_HIGH if (has_mabr and has_dnf) else
                 OPEX_MEDIUM_HIGH if (has_mabr or has_dnf) else
                 OPEX_MODERATE)
        complexity = (COMPLEXITY_HIGH if n_stages >= 5 else
                      COMPLEXITY_MEDIUM if n_stages >= 3 else
                      COMPLEXITY_LOW)
        reliability  = RELIABILITY_SENSITIVE if n_stages >= 5 else RELIABILITY_MEDIUM
        delivery     = DELIVERY_VERY_HIGH if has_comag and has_mabr else DELIVERY_HIGH
        primary_risk = "Integration risk — retrofit complexity and sequencing"
        failure_mode = _brownfield_failure_mode(ctx, has_mabr, has_comag, has_dnf,
                                                carbon_closure)
        strengths  = _brownfield_strengths(has_comag, has_indense, has_mabr, has_dnf)
        weaknesses = _brownfield_weaknesses(has_comag, has_indense, has_mabr, n_stages)
        flexibility = "Low"   # constrained by existing footprint
        upgrade_path = "Medium — further intensification limited by site constraints"

    # ── Greenfield conventional ────────────────────────────────────────────────
    elif option_type == "greenfield_conventional":
        capex = CAPEX_HIGH     # civil-heavy: large concrete volumes
        opex  = OPEX_LOW
        complexity  = COMPLEXITY_LOW
        reliability = RELIABILITY_HIGH
        delivery    = DELIVERY_MEDIUM
        primary_risk = "Capital risk — civil-heavy build with high upfront cost"
        failure_mode = ("Carbon limitation (eff COD:TN < 4.5) means TN compliance gap "
                        "cannot be closed by biological optimisation alone, even on a "
                        "new conventional plant. Tertiary closure must be incorporated "
                        "at design stage." if carbon_closure else
                        "Process undersizing if load projections underestimate future TKN "
                        "or if SVI variability exceeds design case.")
        strengths  = [
            "Highest reliability — large volumes buffer against peak loads and variability",
            "Lowest operational complexity — conventional operating model",
            "Lowest OPEX — no specialist chemicals or membrane maintenance",
            "Greatest passive resilience to shock loads",
        ]
        weaknesses = [
            "Highest civil CAPEX — large concrete footprint",
            "Least compact — requires most land",
            "Least flexible for future intensification without additional civil works",
        ]
        if carbon_closure:
            weaknesses.append(
                "Carbon closure (DNF/PdNA) is still required — this cost is not avoided "
                "by conventional design"
            )
        flexibility  = "Medium — sized for design horizon but civil capacity is fixed"
        upgrade_path = "Medium — additional tertiary stages can be added but civil work required"

    # ── Greenfield intensified ─────────────────────────────────────────────────
    else:  # greenfield_intensified
        capex = (CAPEX_HIGH if has_mabr and has_dnf else
                 CAPEX_MEDIUM_HIGH if has_mabr or has_dnf else
                 CAPEX_MEDIUM)
        opex  = (OPEX_HIGH if has_mabr and has_dnf else
                 OPEX_MEDIUM_HIGH if has_mabr or has_pdna else
                 OPEX_MODERATE)
        complexity  = COMPLEXITY_HIGH if has_mabr else COMPLEXITY_MEDIUM
        reliability = RELIABILITY_MEDIUM
        delivery    = DELIVERY_HIGH if has_mabr else DELIVERY_MEDIUM
        primary_risk = "Operational risk — high-complexity systems require specialist operation"
        failure_mode = ("Operational instability — intensified systems have narrower "
                        "operating windows and are more sensitive to load variability, "
                        "temperature changes, and control system reliability.")
        strengths  = [
            "Reduced civil footprint vs conventional — lower land requirement",
            "Higher nominal performance per unit volume",
            "Faster to deploy on constrained or greenfield sites",
        ]
        if has_mabr:
            strengths.append(
                "MABR provides kinetic protection at low temperature and high MLSS"
            )
        weaknesses = [
            "Higher OPEX — specialist chemicals, membrane maintenance, higher energy",
            "Higher operational complexity — tighter control requirements",
            "Less resilient to shock loads than conventional buffered design",
            "Supply chain dependency for specialist components",
        ]
        flexibility  = "High — compact footprint allows future stage additions"
        upgrade_path = "High — modular additions possible within existing footprint"

    return AffordabilityOption(
        label              = _option_label(option_type, stack),
        option_type        = option_type,
        stack_summary      = stack[:6],
        capex_band         = capex,
        opex_band          = opex,
        complexity         = complexity,
        reliability        = reliability,
        delivery_risk      = delivery,
        primary_risk_type  = primary_risk,
        failure_mode       = failure_mode,
        strategic_strengths  = strengths,
        strategic_weaknesses = weaknesses,
        flexibility        = flexibility,
        upgrade_pathway    = upgrade_path,
        carbon_closure_required = carbon_closure,
        carbon_closure_tech     = closure_tech,
    )


def _option_label(option_type: str, stack: List[str]) -> str:
    if option_type == "brownfield":
        return "Brownfield Intensification"
    if option_type == "greenfield_conventional":
        return "Greenfield — Conventional"
    return "Greenfield — Intensified"


def _brownfield_failure_mode(ctx: Dict, mabr: bool, comag: bool, dnf: bool,
                              carbon: bool) -> str:
    if float(ctx.get("flow_ratio", 1.5) or 1.5) >= 4.:
        return ("Hydraulic failure is the most likely first failure mode: clarifier "
                "overflow under peak wet weather flow. Without hydraulic relief "
                "(CoMag or equivalent), washout occurs before any biological "
                "compliance issue manifests.")
    if carbon:
        return ("Carbon-limited denitrification — eff COD:TN < 4.5 means TN compliance "
                "gap cannot be closed biologically, even after constraint relief. "
                "Tertiary closure must be in place before TN compliance is credible.")
    return ("Nitrification failure under peak load or winter conditions — "
            "aeration constraint and return liquor load create seasonal compliance risk.")


def _brownfield_strengths(comag: bool, indense: bool, mabr: bool, dnf: bool) -> List[str]:
    s = ["Lower civil cost — reuses existing concrete structures and tankage"]
    if comag:  s.append("CoMag provides immediate hydraulic protection under peak flow")
    if indense: s.append("inDENSE recovers clarifier SOR headroom without new tankage")
    if mabr:   s.append("MABR addresses aeration constraint within existing tank footprint")
    if dnf:    s.append("DNF closes the carbon-limited TN gap with no biological zone redesign")
    return s


def _brownfield_weaknesses(comag: bool, indense: bool, mabr: bool, n: int) -> List[str]:
    w = ["Highest process complexity — multiple retrofit technologies interacting"]
    w.append("Higher OPEX than conventional greenfield — specialist systems incur ongoing costs")
    if n >= 5:
        w.append("Delivery risk is high — commissioning sequence is critical; "
                 "errors compound across stages")
    if comag and mabr:
        w.append("Supply chain dependency for CoMag ballast, MABR membranes, and DNF media")
    return w


# ── Comparison table builder ───────────────────────────────────────────────────

def _build_comparison_table(options: List[AffordabilityOption]) -> List[Dict[str, str]]:
    """Build list of row dicts: dimension → {option_label: value}."""
    dims = [
        ("CAPEX",              lambda o: o.capex_band),
        ("OPEX",               lambda o: o.opex_band),
        ("Complexity",         lambda o: o.complexity),
        ("Reliability",        lambda o: o.reliability),
        ("Delivery risk",      lambda o: o.delivery_risk),
        ("Flexibility",        lambda o: o.flexibility),
        ("Upgrade pathway",    lambda o: o.upgrade_pathway[:40] + "…"
                                         if len(o.upgrade_pathway) > 40 else o.upgrade_pathway),
        ("Carbon closure req", lambda o: ("Yes — " + o.carbon_closure_tech)
                                          if o.carbon_closure_required else "No"),
    ]
    rows = []
    for dim_label, extractor in dims:
        row: Dict[str, str] = {"dimension": dim_label}
        for opt in options:
            row[opt.label] = extractor(opt)
        rows.append(row)
    return rows


# ── Board summary bullets ──────────────────────────────────────────────────────

def _build_board_bullets(options: List[AffordabilityOption],
                         shared_carbon: bool, eff_codn: float,
                         preferred_label: str) -> List[str]:
    bullets = []

    # Most capital intensive
    capex_order = {CAPEX_HIGH: 3, CAPEX_MEDIUM_HIGH: 2, CAPEX_MEDIUM: 1, CAPEX_LOW: 0}
    most_capex = max(options, key=lambda o: capex_order.get(o.capex_band, 0))
    bullets.append(
        f"{most_capex.label} is the most capital-intensive option ({most_capex.capex_band} "
        f"CAPEX) due to {most_capex.primary_risk_type.split(' —')[0].lower()} requirements."
    )

    # Most operationally complex
    comp_order = {COMPLEXITY_HIGH: 2, COMPLEXITY_MEDIUM: 1, COMPLEXITY_LOW: 0}
    most_complex = max(options, key=lambda o: comp_order.get(o.complexity, 0))
    bullets.append(
        f"{most_complex.label} is the most operationally complex ({most_complex.complexity} "
        "complexity) and requires specialist operation and control."
    )

    # Most robust
    rel_order = {RELIABILITY_HIGH: 2, RELIABILITY_MEDIUM: 1, RELIABILITY_SENSITIVE: 0}
    most_robust = max(options, key=lambda o: rel_order.get(o.reliability, 0))
    bullets.append(
        f"{most_robust.label} is the most robust option ({most_robust.reliability} reliability) "
        "with the greatest tolerance for load variability and operational disturbances."
    )

    # Most flexible
    flex_order = {"High": 2, "Medium": 1, "Low": 0}
    most_flex = max(options, key=lambda o: flex_order.get(o.flexibility, 0))
    bullets.append(
        f"{most_flex.label} offers the most flexibility ({most_flex.flexibility}) "
        "for future expansion within the existing footprint."
    )

    # Shared constraint
    if shared_carbon and eff_codn < 4.5:
        bullets.append(
            f"Key uncertainty affecting all options: biodegradable carbon availability "
            f"(eff COD:TN {eff_codn:.2f} — below 4.5 closure threshold). "
            "Carbon fractionation is required before final pathway selection."
        )

    return bullets


# ── Main entry point ───────────────────────────────────────────────────────────

def build_affordability_comparison(
    pathway,                  # UpgradePathway
    compliance_report,        # ComplianceReport
    ctx: Dict,
    additional_options: Optional[List[Dict]] = None,
) -> AffordabilityComparison:
    """
    Build the affordability comparison from engine outputs.

    Activation conditions:
      - pathway.greenfield_pathways has ≥1 entry (GF mode with design options)
      - OR additional_options list is provided (explicit multi-option comparison)
      - OR brownfield + greenfield cases both supplied via additional_options

    Parameters
    ----------
    pathway : UpgradePathway
        Primary engine pathway output.
    compliance_report : ComplianceReport
        Engine compliance output (for carbon signals).
    ctx : Dict
        Engine context dict.
    additional_options : list of dicts, optional
        Each dict: {"option_type": str, "stack": List[str], "label": str (optional)}
    """
    from apps.wastewater_app.compliance_layer import DISPLAY_NOT_CREDIBLE

    eff_codn   = float(getattr(compliance_report, "effective_cod_tn_val", 0.) or 0.)
    carbon_lim = bool(ctx.get("carbon_limited_tn", False)) or (0. < eff_codn < 4.5)
    is_gf      = bool(ctx.get("greenfield", False))
    gf_paths   = getattr(pathway, "greenfield_pathways", []) or []

    # ── Build options list ─────────────────────────────────────────────────────
    options: List[AffordabilityOption] = []

    if additional_options:
        # Explicit multi-option: caller provides option_type + stack
        for opt_def in additional_options:
            otype = opt_def.get("option_type", "brownfield")
            stack = opt_def.get("stack", [s.technology for s in pathway.stages])
            opt   = _classify_stack(stack, otype, ctx)
            if "label" in opt_def:
                from dataclasses import replace as _r
                opt = _r(opt, label=opt_def["label"])
            options.append(opt)

    elif gf_paths:
        # Greenfield mode with multiple design options from the engine
        for gp in gf_paths:
            otype = ("greenfield_conventional"
                     if "Conventional" in gp.label else
                     "greenfield_intensified")
            stack = gp.stack
            opt   = _classify_stack(stack, otype, ctx)
            from dataclasses import replace as _r
            opt = _r(opt, label=gp.label)
            options.append(opt)

    else:
        # Single primary pathway (brownfield or greenfield intensified)
        otype = "greenfield_intensified" if is_gf else "brownfield"
        options.append(_classify_stack(
            [s.technology for s in pathway.stages], otype, ctx))

    # ── Check activation ───────────────────────────────────────────────────────
    is_active = len(options) >= 2

    # ── Shared carbon signal ───────────────────────────────────────────────────
    shared_carbon = carbon_lim or any(o.carbon_closure_required for o in options)
    shared_closure_techs = set(o.carbon_closure_tech for o in options
                                if o.carbon_closure_required and o.carbon_closure_tech)
    closure_tech_str = " or ".join(sorted(shared_closure_techs)) if shared_closure_techs else ""

    shared_constraint_txt = ""
    if shared_carbon and eff_codn > 0.:
        shared_constraint_txt = (
            f"Effective COD:TN = {eff_codn:.2f} — below 4.5 biological denitrification "
            f"closure threshold. {closure_tech_str or 'Tertiary nitrogen closure'} is "
            "mechanistically required across all pathways."
        )

    # ── Comparison table ───────────────────────────────────────────────────────
    table = _build_comparison_table(options) if is_active else []

    # ── Decision framing (Part 7 — mandatory) ─────────────────────────────────
    decision_framing = (
        "There is no single lowest-cost option. The decision is a trade-off between "
        "capital investment and operational complexity. Higher capital spend on a "
        "conventional design typically reduces ongoing operational risk and specialist "
        "dependency; lower initial capital through intensification transfers risk to "
        "operations and supply chain."
    )

    # ── Critical insight (Part 9) ──────────────────────────────────────────────
    critical_insight = ""
    if shared_carbon:
        ct = closure_tech_str or "DNF or PdNA equivalent"
        critical_insight = (
            f"Key constraint persists across all options and cannot be designed out: "
            f"insufficient biodegradable carbon for biological denitrification "
            f"(eff COD:TN {eff_codn:.2f} < 4.5). All pathways require {ct} as a "
            "tertiary nitrogen closure element regardless of design approach or "
            "technology selection."
        )

    # ── Board bullets (Part 8) ─────────────────────────────────────────────────
    preferred_label = _find_preferred(options, ctx)
    board_bullets   = _build_board_bullets(options, shared_carbon, eff_codn, preferred_label)

    # ── Preferred path logic (Part 10) ────────────────────────────────────────
    preferred_path  = _preferred_path_statement(options, ctx, gf_paths)

    return AffordabilityComparison(
        options               = options,
        comparison_table      = table,
        decision_framing      = decision_framing,
        board_bullets         = board_bullets,
        critical_insight      = critical_insight,
        preferred_path        = preferred_path,
        shared_carbon_closure = shared_carbon,
        shared_constraint_txt = shared_constraint_txt,
        is_active             = is_active,
    )


def _find_preferred(options: List[AffordabilityOption], ctx: Dict) -> str:
    """Return label of preferred option for Part 10 logic."""
    land   = ctx.get("footprint_constraint", "constrained") or "constrained"
    op_cap = ctx.get("operator_context", "metro") or "metro"
    abundant_land = land in ("abundant", "unconstrained", "available", "none")
    moderate_ops  = op_cap in ("moderate", "rural", "regional")
    # Prefer conventional if land abundant + moderate ops
    for o in options:
        if o.option_type == "greenfield_conventional" and abundant_land:
            return o.label
    # Otherwise first option
    return options[0].label if options else ""


def _preferred_path_statement(options: List[AffordabilityOption],
                               ctx: Dict,
                               gf_paths: list) -> str:
    """Generate Part 10 preferred path logic statement."""
    if not options:
        return ""
    land   = (ctx.get("footprint_constraint", "constrained") or "constrained").lower()
    op_cap = (ctx.get("operator_context", "metro") or "metro").lower()
    abundant_land = land in ("abundant", "unconstrained", "available", "none")
    moderate_ops  = op_cap in ("moderate", "rural", "regional")
    has_conventional = any(o.option_type == "greenfield_conventional" for o in options)
    has_intensified  = any(o.option_type in ("greenfield_intensified", "brownfield")
                           for o in options)
    if has_conventional and abundant_land:
        return (
            "Conventional pathway preferred due to lower operational complexity and higher "
            "resilience, despite slightly higher civil capital cost. Land is available and "
            "operator capability favours a simpler, more forgiving operating model. "
            "The intensified option remains viable where compactness is a future priority."
        )
    if has_intensified and not abundant_land:
        return (
            "Intensified pathway preferred due to footprint constraint — conventional "
            "design is not viable on this site. Higher operational complexity must be "
            "managed through investment in instrumentation, control systems, and "
            "operator training."
        )
    if has_conventional and has_intensified:
        return (
            "Both pathways are technically viable. Selection depends on the balance "
            "between capital investment (conventional is higher), operational complexity "
            "(intensified is higher), and long-term operator capability. "
            "Confirm land availability and operator development capacity before commitment."
        )
    return (
        "Single pathway evaluated. Affordability comparison requires at least two "
        "viable options to generate a preference recommendation."
    )
