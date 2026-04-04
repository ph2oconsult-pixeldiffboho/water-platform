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

    st.markdown("---")
