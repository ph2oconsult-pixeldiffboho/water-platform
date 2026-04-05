"""
apps/wastewater_app/waterpoint_ui.py

WaterPoint Intelligence — Streamlit rendering component.

Called from page_04_results.py after calculations are available.
Uses st.container() to stay above existing engineering tabs.
Never raises — all errors are caught and displayed gracefully.
"""
from __future__ import annotations

from typing import Optional


def render_waterpoint(scenario, project=None) -> None:
    """
    Render the WaterPoint Intelligence layer for one scenario.

    Parameters
    ----------
    scenario : ScenarioModel with cost_result populated
    project  : ProjectModel (optional, for plant name / location)
    """
    import streamlit as st

    # ── Guard: only render if calculations exist ──────────────────────────
    if not getattr(scenario, "cost_result", None):
        return

    try:
        from apps.wastewater_app.waterpoint_adapter import build_waterpoint_input
        from apps.wastewater_app.waterpoint_engine  import analyse
        wp    = build_waterpoint_input(scenario, project)
        result = analyse(wp)
    except Exception as e:
        with st.expander("⚡ WaterPoint Intelligence — error loading", expanded=False):
            st.warning(f"WaterPoint could not load: {e}")
        return

    stress    = result.system_stress
    failure   = result.failure_modes
    decision  = result.decision_layer
    compliance = result.compliance_risk

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ⚡ WaterPoint Intelligence")
    st.caption(
        "Interprets engineering outputs to surface system stress, failure modes, "
        "and planning priorities. Read-only — does not alter engineering calculations."
    )

    # ── A. SYSTEM STRESS ──────────────────────────────────────────────────
    with st.container():
        col_state, col_prox, col_rate, col_conf = st.columns(4)

        state_colour = {
            "Stable":        "normal",
            "Tightening":    "off",
            "Fragile":       "inverse",
            "Failure Risk":  "inverse",
            "Unknown":       "off",
        }.get(stress.state, "off")

        col_state.metric("System State",    stress.state)
        col_prox.metric( "Load / Capacity", f"{stress.proximity_percent:.0f}%")
        col_rate.metric( "Trajectory",       stress.rate)
        col_conf.metric( "Confidence",       stress.confidence)

        # State badge
        badge_map = {
            "Stable":       ("🟢", "#1a7a1a"),
            "Tightening":   ("🟡", "#7a6a00"),
            "Fragile":      ("🟠", "#7a3a00"),
            "Failure Risk": ("🔴", "#7a0000"),
            "Unknown":      ("⚪", "#555"),
        }
        icon, colour = badge_map.get(stress.state, ("⚪", "#555"))
        st.markdown(
            f'<div style="border-left:4px solid {colour};padding:8px 12px;'
            f'background:#f8f8f8;border-radius:4px;margin:8px 0;">'
            f'<b>{icon} {stress.primary_constraint}</b><br>'
            f'<span style="color:#444;font-size:0.9rem;">{stress.rationale}</span><br>'
            f'<span style="color:#666;font-size:0.85rem;">⏱ Time to breach: {stress.time_to_breach}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── B. FAILURE MODES ──────────────────────────────────────────────────
    if failure.items:
        with st.expander(
            f"⚠️ Failure Mode Analysis — Overall Severity: **{failure.overall_severity}**",
            expanded=(failure.overall_severity == "High"),
        ):
            sev_icon = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get
            for m in failure.items:
                icon = sev_icon(m.severity, "⚪")
                st.markdown(
                    f"**{icon} {m.title}** — _{m.severity} severity_  \n{m.description}"
                )
    else:
        with st.expander("✅ Failure Mode Analysis", expanded=False):
            st.success("No significant failure modes identified under current scenario parameters.")

    # ── C. DECISION LAYER ─────────────────────────────────────────────────
    with st.expander("🎯 Decision Layer — Actions by Horizon", expanded=False):
        col_st, col_mt, col_lt = st.columns(3)

        with col_st:
            st.markdown("**Short-term**")
            st.caption("Operational — 0–12 months")
            for action in decision.short_term:
                st.markdown(f"• {action}")

        with col_mt:
            st.markdown("**Medium-term**")
            st.caption("Debottlenecking — 1–3 years")
            for action in decision.medium_term:
                st.markdown(f"• {action}")

        with col_lt:
            st.markdown("**Long-term**")
            st.caption("Capital — 3–10 years")
            for action in decision.long_term:
                st.markdown(f"• {action}")

        if decision.capex_range:
            st.info(f"💰 **Planning range:** {decision.capex_range}")

        if decision.risk_if_no_action:
            _risk_colour = {
                "Stable":       "🟢",
                "Tightening":   "🟡",
                "Fragile":      "🟠",
                "Failure Risk": "🔴",
            }.get(stress.state, "⚠️")
            st.warning(f"{_risk_colour} **Risk if no action:** {decision.risk_if_no_action}")

    # ── D. COMPLIANCE & RISK ──────────────────────────────────────────────
    risk_colour_map = {"Low": "🟢", "Medium": "🟡", "High": "🔴", "Unknown": "⚪"}
    risk_icon = risk_colour_map.get(compliance.compliance_risk, "⚪")

    with st.expander(
        f"📋 Compliance & Regulatory Risk — {risk_icon} {compliance.compliance_risk}",
        expanded=(compliance.compliance_risk == "High"),
    ):
        col_b, col_r = st.columns([1, 1])
        with col_b:
            st.markdown("**Likely breach type**")
            st.markdown(compliance.likely_breach_type)
            st.markdown("**Reputational risk**")
            st.markdown(compliance.reputational_risk)
        with col_r:
            st.markdown("**Regulatory exposure**")
            st.markdown(compliance.regulatory_exposure)

    # ── E. SYNTHESIS LAYERS (Stack → Feasibility → Credibility → Risk) ───
    _render_synthesis_layers(result, scenario, project)

    st.markdown("---")


def _render_synthesis_layers(result, scenario, project) -> None:
    """
    Render the post-stack synthesis layers:
    Stack Generator → Feasibility → Credibility → Uncertainty
    → Stabilisation → Risk & Mitigation → Positioning

    Called from render_waterpoint() after all primary outputs are shown.
    Fails gracefully — any layer error shows a warning without breaking the page.
    """
    import streamlit as st

    # Build plant_context from scenario / project fields
    ctx = _build_context(scenario, project)
    if ctx is None:
        return

    # ── Import layers ──────────────────────────────────────────────────────
    try:
        from apps.wastewater_app.waterpoint_adapter import build_waterpoint_input
        from apps.wastewater_app.stack_generator    import build_upgrade_pathway
        from apps.wastewater_app.feasibility_layer  import assess_feasibility
        from apps.wastewater_app.credibility_layer  import build_credible_output
        from apps.wastewater_app.uncertainty_layer  import build_uncertainty_report
        from apps.wastewater_app.stabilisation_layer import build_stabilisation_report
        from apps.wastewater_app.risk_layer          import build_risk_report, RL_LOW, RL_MEDIUM, RL_HIGH

        wp       = build_waterpoint_input(scenario, project)
        pathway  = build_upgrade_pathway(result, ctx)
        feas     = assess_feasibility(pathway, ctx)
        cred     = build_credible_output(pathway, feas, ctx)
        unc      = build_uncertainty_report(pathway, feas, cred, ctx)
        stab     = build_stabilisation_report(pathway, ctx)
        risk     = build_risk_report(pathway, feas, ctx)

    except Exception as e:
        with st.expander("⚡ Upgrade pathway — error loading synthesis layers", expanded=False):
            st.warning(f"Synthesis layers could not load: {e}")
        return

    _sev_col = {"Low": "🟢", "Medium": "🟡", "High": "🔴", "Very High": "🔴"}

    # ── E1. RECOMMENDED TECHNOLOGY STACK ──────────────────────────────────
    stack_label = "✅ Ready" if cred.ready_for_client else "⚠️ Review notes"
    with st.expander(
        f"🔧 Recommended Upgrade Stack — {len(pathway.stages)} stages — {stack_label}",
        expanded=(result.system_stress.state == "Failure Risk"),
    ):
        if not pathway.stages:
            st.info("No upgrade pathway identified for current scenario parameters.")
        else:
            st.caption(pathway.constraint_summary)
            for stage in pathway.stages:
                sf = next(
                    (s for s in feas.stage_feasibility if s.stage_number == stage.stage_number),
                    None)
                feas_icon = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(
                    sf.feasibility if sf else "Medium", "🟡")
                with st.container():
                    st.markdown(
                        f"**Stage {stage.stage_number} — {stage.tech_display}** "
                        f"{feas_icon} _{sf.feasibility if sf else '?'} feasibility_"
                    )
                    col_p, col_b = st.columns([1, 1])
                    with col_p:
                        st.caption("Purpose")
                        st.markdown(stage.purpose[:180])
                    with col_b:
                        st.caption("Engineering basis")
                        st.markdown(stage.engineering_basis[:180])
                    if stage.prerequisite:
                        st.caption(f"⚠️ Prerequisite: {stage.prerequisite}")

            # Credibility notes
            if cred.credibility_notes:
                for note in cred.credibility_notes:
                    icon = {"Warning": "⚠️", "Info": "ℹ️", "Correction": "🔴"}.get(
                        note.severity, "ℹ️")
                    st.info(f"{icon} **{note.category}:** {note.message}")
            if cred.consistency_flags:
                for flag in cred.consistency_flags:
                    st.warning(f"🔍 {flag}")
            if cred.compatibility_flags:
                for flag in cred.compatibility_flags:
                    st.caption(f"🔗 {flag[:120]}")

    # ── E2. ALTERNATIVE PATHWAYS ───────────────────────────────────────────
    if cred.alternatives:
        with st.expander(f"🔀 Alternative Pathways — {len(cred.alternatives)} options"):
            for alt in cred.alternatives:
                cap_icon = "🏗️" if "High" in alt.capex_class else "💰" if "Low" in alt.capex_class else "⚖️"
                st.markdown(f"**{cap_icon} {alt.label}**")
                col_s, col_w = st.columns([1, 1])
                with col_s:
                    st.caption("Stages")
                    for s in alt.stages:
                        st.markdown(f"→ {s}")
                with col_w:
                    st.caption("When preferred")
                    st.markdown(alt.when_preferred[:200])
                st.markdown("---")

    # ── E3. FEASIBILITY SUMMARY ────────────────────────────────────────────
    feas_icon_map = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}
    fi = feas_icon_map.get(feas.overall_feasibility, "🟡")
    with st.expander(
        f"📊 Feasibility Assessment — {fi} {feas.overall_feasibility} "
        f"| Confidence: {feas.adjusted_confidence} ({feas.confidence_change})"
    ):
        dim_cols = st.columns(3)
        dim_pairs = [
            ("Supply Chain", feas.supply_chain_risk),
            ("Op. Complexity", feas.operational_complexity),
            ("Chemical Dep.", feas.chemical_dependency),
            ("Energy / OPEX", feas.energy_impact),
            ("Integration", feas.integration_risk),
            ("Sludge / Residuals", feas.sludge_residuals_impact),
        ]
        level_icon = {"High": "🔴", "Medium": "🟡", "Low": "🟢",
                      "None": "🟢", "Very High": "🔴"}
        for i, (dim, val) in enumerate(dim_pairs):
            dim_cols[i % 3].metric(dim, f"{level_icon.get(val,'🟡')} {val}")

        if feas.key_risks:
            st.markdown("**Key risks**")
            for r2 in feas.key_risks[:4]:
                st.markdown(f"• {r2}")
        if feas.key_mitigations:
            st.markdown("**Mitigations**")
            for m in feas.key_mitigations[:3]:
                st.markdown(f"• {m}")
        if feas.lower_risk_alternative:
            lra = feas.lower_risk_alternative
            st.info(
                f"💡 **Lower-risk alternative:** {lra.label}  \n"
                f"CAPEX: {lra.capex_impact} · Feasibility: {lra.feasibility}  \n"
                + "  \n".join(f"→ {c}" for c in lra.stage_changes)
            )

    # ── E4. CARBON & UNCERTAINTY ───────────────────────────────────────────
    with st.expander(
        f"🌱 Carbon & Uncertainty — {unc.overall_confidence} confidence | "
        f"CO₂e reduction: {unc.carbon.low_band.pct_reduction:.0f}–"
        f"{unc.carbon.high_band.pct_reduction:.0f}% (central "
        f"{unc.carbon.central_band.pct_reduction:.0f}%)"
    ):
        # Uncertainty dimensions
        st.markdown("**Uncertainty dimensions**")
        unc_cols = st.columns(5)
        for i, dim in enumerate(unc.dimensions):
            icon = _sev_col.get(dim.level, "🟡")
            unc_cols[i].metric(
                dim.dimension.replace(" variability","").replace(" model",""),
                f"{icon} {dim.level}",
            )

        st.markdown("**Carbon reduction range (IPCC AR6, indicative)**")
        c_cols = st.columns(3)
        for i, band in enumerate(unc.carbon.bands):
            col = c_cols[i]
            col.metric(
                f"{band.label} (EF {band.ef_pct:.1f}%)",
                f"{band.pct_reduction:.0f}%",
                f"{band.total_delta_t:,} t CO₂e/yr",
            )
        st.caption(unc.carbon.ipcc_ref)

        # Sensitivity drivers
        st.markdown("**Top sensitivity drivers**")
        for dr in unc.sensitivity_drivers:
            icon = "🔴" if dr.impact_level == "High" else "🟡"
            st.markdown(f"{icon} **{dr.rank}. {dr.driver}**")
            st.caption(f"{dr.explanation[:150]}")

        # Decision tension
        st.markdown("**Decision tension**")
        st.info(unc.decision_tension.primary_tension)

    # ── E5. STABILISATION OPTIONS ─────────────────────────────────────────
    if stab.has_options:
        cap_icons = {"May defer capital": "💰", "De-risks capital": "🛡️",
                     "Improves operational confidence only": "📊"}
        with st.expander(
            f"🔬 Low-Cost Stabilisation Options — {len(stab.options)} identified"
        ):
            st.caption(stab.preamble)
            for opt in stab.options:
                icon = cap_icons.get(opt.capital_class, "📋")
                st.markdown(f"**{icon} {opt.name}** — _{opt.capital_class}_")
                col_w, col_n = st.columns([1, 1])
                with col_w:
                    st.caption("Why it may help")
                    st.markdown(opt.why_it_helps[:200])
                with col_n:
                    st.caption("What it does NOT solve")
                    st.markdown(opt.what_it_does_not_solve[:160])
                st.caption(
                    f"Est. cost: {opt.estimated_cost} · Time to result: {opt.time_to_result}"
                )
                st.markdown("---")

    # ── E6. RISK & MITIGATION ─────────────────────────────────────────────
    with st.expander(f"⚠️ Risk & Mitigation — {len(risk.profiles)} technology profiles"):
        st.caption(risk.stack_risk_summary)
        level_colour = {RL_LOW: "🟢", RL_MEDIUM: "🟡", RL_HIGH: "🔴"}
        for prof in risk.profiles:
            ol_icon = level_colour.get(prof.overall_level, "🟡")
            st.markdown(
                f"**Stage {prof.stage_number} — {prof.tech_display}** "
                f"{ol_icon} Overall: {prof.overall_level}"
            )
            st.caption(prof.risk_summary[:180])
            cat_cols = st.columns(4)
            for i, cat in enumerate(prof.categories):
                ci = level_colour.get(cat.level, "🟡")
                with cat_cols[i]:
                    st.markdown(f"**{ci} {cat.category}**")
                    st.caption(f"Risk: {cat.risk[:90]}")
                    st.caption(f"Mit: {cat.mitigation[:90]}")
            st.markdown("---")
        st.caption(risk.decision_tension)


def _build_context(scenario, project) -> dict | None:
    """
    Build plant_context dict from scenario / project fields.
    Returns None if insufficient data to run synthesis layers.
    """
    try:
        cr = scenario.cost_result
        if not cr:
            return None

        # Flow ratio
        avg  = getattr(scenario, "average_flow_mld",  None) or getattr(cr, "flow_mld", None)
        peak = getattr(scenario, "peak_flow_mld",     None)
        flow_ratio = (peak / avg) if (avg and peak and avg > 0) else 1.0

        # Process flags from scenario
        tech = getattr(scenario, "technology_code", "") or ""
        is_sbr = "sbr" in tech.lower()
        is_mbr = "mbr" in tech.lower()

        # Effluent flags
        nh4_eff = getattr(scenario, "effluent_nh4_mg_l", None) or 0.
        nh4_tgt = getattr(scenario, "nh4_target_mg_l",  None) or 1.
        tn_eff  = getattr(scenario, "effluent_tn_mg_l",  None) or 0.
        tn_tgt  = getattr(scenario, "tn_target_mg_l",   None) or 10.
        tp_eff  = getattr(scenario, "effluent_tp_mg_l",  None) or 0.
        tp_tgt  = getattr(scenario, "tp_target_mg_l",   None) or 1.

        # Plant location from project
        location = "metro"
        if project:
            loc = (getattr(project, "location_type", None)
                   or getattr(project, "location",      None) or "")
            if "remote" in str(loc).lower():  location = "remote"
            elif "regional" in str(loc).lower(): location = "regional"

        return {
            "plant_type"          : tech.upper() if tech else "BNR",
            "is_sbr"              : is_sbr,
            "is_mbr"              : is_mbr,
            "overflow_risk"       : flow_ratio >= 2.5,
            "wet_weather_peak"    : flow_ratio >= 2.0,
            "flow_ratio"          : flow_ratio,
            "aeration_constrained": getattr(cr, "aeration_utilisation_pct", 0) >= 85,
            "high_load"           : getattr(cr, "volume_utilisation_pct",    0) >= 80,
            "tn_at_limit"         : tn_eff  > tn_tgt  * 0.85,
            "tp_at_limit"         : tp_eff  > tp_tgt  * 0.85,
            "nh4_near_limit"      : nh4_eff > nh4_tgt * 0.70,
            "srt_pressure"        : getattr(cr, "srt_days", 99) < 12,
            "nitrification_flag"  : nh4_eff > nh4_tgt,
            "carbon_limited_tn"   : tn_eff  > tn_tgt  * 0.85,
            "high_mlss"           : getattr(cr, "mlss_mg_l", 0) >= 4500,
            "solids_carryover"    : False,   # conservative default
            "clarifier_util"      : getattr(cr, "clarifier_utilisation_pct", 0) / 100,
            "plant_size_mld"      : float(avg or 10),
            "location_type"       : location,
            # Carbon context
            "aeration_kwh_day"    : getattr(cr, "aeration_kwh_day",  0),
            "tn_in_mg_l"          : getattr(scenario, "influent_tn_mg_l", 45),
            "tn_out_baseline_mg_l": float(tn_eff or 10),
            "tn_out_upgraded_mg_l": float(tn_tgt  or 5),
            "grid_ef_kgco2e_kwh"  : 0.50,
            "chemical_co2e_increase_t": 100.,
        }
    except Exception:
        return None
