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



    # ── E7. GREENFIELD DELIVERY MODEL COMPARISON ──────────────────────────
    _INTENSIFIED_TECHS = {
        "MABR (OxyFAS retrofit)", "PdNA (Partial Denitrification-Anammox)",
        "Denitrification Filter", "IFAS", "Hybas (IFAS)", "MBBR",
        "MOB (miGRATE + inDENSE)",
    }
    _gf_flag         = bool(ctx.get("greenfield", False))
    _stage_techs     = {st.technology for st in pathway.stages}
    _has_intensified = bool(_stage_techs & _INTENSIFIED_TECHS)
    _show_gf_compare = _gf_flag or _has_intensified

    if _show_gf_compare:
        with st.expander(
            "🏗️ Greenfield Delivery Model Comparison",
            expanded=False,
        ):
            st.caption(
                "Comparison of conventional and intensified greenfield approaches "
                "across key decision dimensions."
            )
            _rows = [
                ("Dimension",     "Conventional",                          "Intensified"),
                ("Footprint",     "High — land typically available",  "Low — reduced footprint / lower civil CAPEX"),
                ("Resilience",    "High — volume provides buffering against shocks",
                                  "Moderate — performance depends on control systems and sensors"),
                ("OPEX Style",    "Low-tech / high-energy",                "High-tech / low-energy"),
                ("Complexity",    "Low — standard operating practices",
                                  "High — requires specialist training and tighter control"),
            ]
            _col_w = [1.5, 3, 3]
            _header_row = st.columns(_col_w)
            _header_row[0].markdown(f"**{_rows[0][0]}**")
            _header_row[1].markdown(f"**{_rows[0][1]}**")
            _header_row[2].markdown(f"**{_rows[0][2]}**")
            st.markdown(
                "<hr style='margin:4px 0; border-color:#dde3ea;'>",
                unsafe_allow_html=True,
            )
            for dim, conv, intens in _rows[1:]:
                _r = st.columns(_col_w)
                _r[0].markdown(f"**{dim}**")
                _r[1].caption(conv)
                _r[2].caption(intens)
            st.markdown(
                "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                unsafe_allow_html=True,
            )
            st.caption(
                "Selection between conventional and intensified approaches depends on "
                "utility capability, land availability, energy strategy, and risk tolerance."
            )


    # ── E7b. BROWNFIELD vs REPLACEMENT ASSESSMENT ─────────────────────────
    try:
        from apps.wastewater_app.bf_gf_layer import build_bf_gf_assessment

        _bfgf = build_bf_gf_assessment(pathway, feas, ctx)

        _rec_icon = {
            "Strong Brownfield":   "🟢",
            "Brownfield Preferred":"🟡",
            "Balanced":            "🟠",
            "Replacement Viable":  "🔴",
            "Strong Replacement":  "🔴",
        }.get(_bfgf.recommendation, "⬜")

        with st.expander(
            f"{_rec_icon} Brownfield vs Replacement — {_bfgf.recommendation}",
            expanded=False,
        ):
            # ── Recommendation + rationale ─────────────────────────────
            st.markdown(f"**{_bfgf.recommendation}** — score {_bfgf.total_score}/14")
            st.caption(_bfgf.rationale)

            # ── Dimension scoring table ─────────────────────────────────
            st.markdown("**Scoring dimensions**")
            _dcols = st.columns([2.5, 0.8, 4])
            _dcols[0].markdown("**Dimension**")
            _dcols[1].markdown("**Score**")
            _dcols[2].markdown("**Note**")
            st.markdown(
                "<hr style='margin:3px 0; border-color:#dde3ea;'>",
                unsafe_allow_html=True,
            )
            for _dim, _dscore in _bfgf.dimension_scores.items():
                _dnote = _bfgf.dimension_notes.get(_dim, "")
                _dc = st.columns([2.5, 0.8, 4])
                _dc[0].caption(_dim)
                _dc[1].caption(str(_dscore))
                _dc[2].caption(_dnote)

            st.markdown(
                "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                unsafe_allow_html=True,
            )

            # ── BF vs GF side-by-side ───────────────────────────────────
            _bc, _gc = st.columns(2)

            with _bc:
                st.markdown(f"**{_bfgf.brownfield_pathway.label}**")
                st.caption(
                    f"CAPEX class: {_bfgf.brownfield_pathway.capex_class} · "
                    f"Disruption: {_bfgf.brownfield_pathway.disruption} · "
                    f"Timeline: {_bfgf.brownfield_pathway.timeline_years}"
                )
                st.caption("Technologies: " + ", ".join(_bfgf.brownfield_pathway.key_technologies))
                for _b in _bfgf.brownfield_pathway.benefits:
                    st.caption(f"✅ {_b}")
                for _r in _bfgf.brownfield_pathway.risks:
                    st.caption(f"⚠️ {_r}")

            with _gc:
                st.markdown(f"**{_bfgf.replacement_pathway.label}**")
                st.caption(
                    f"CAPEX class: {_bfgf.replacement_pathway.capex_class} · "
                    f"Disruption: {_bfgf.replacement_pathway.disruption} · "
                    f"Timeline: {_bfgf.replacement_pathway.timeline_years}"
                )
                st.caption("Technologies: " + ", ".join(_bfgf.replacement_pathway.key_technologies))
                for _b in _bfgf.replacement_pathway.benefits:
                    st.caption(f"✅ {_b}")
                for _r in _bfgf.replacement_pathway.risks:
                    st.caption(f"⚠️ {_r}")

            st.markdown(
                "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                unsafe_allow_html=True,
            )

            # ── Tipping point ───────────────────────────────────────────
            st.markdown(
                f"**Tipping point** — what would shift from "
                f"*{_bfgf.tipping_point.from_category}* "
                f"to *{_bfgf.tipping_point.to_category}*:"
            )
            for _t in _bfgf.tipping_point.triggers:
                st.caption(f"→ {_t}")

            # ── Decision tension ────────────────────────────────────────
            st.info(_bfgf.decision_tension, icon="⚖️")

            # ── Validation flags ────────────────────────────────────────
            if not _bfgf.brownfield_reflects_stack:
                st.warning(
                    "Note: brownfield pathway technologies do not fully reflect the "
                    "recommended primary stack — review key_technologies alignment.",
                    icon="⚠️",
                )
            if not _bfgf.nereda_in_replacement_only:
                st.warning(
                    "Note: Nereda / AGS appears in the primary stack — "
                    "this technology is intended as a full process replacement option only.",
                    icon="⚠️",
                )
            if not _bfgf.mbr_appropriately_positioned:
                st.warning(
                    "Note: MBR positioning may warrant review — "
                    "confirm it is not competing with brownfield intensification options.",
                    icon="⚠️",
                )

    except Exception as _e7b_err:
        with st.expander("🏗️ Brownfield vs Replacement — error", expanded=False):
            st.warning(f"BF/GF layer could not load: {_e7b_err}")

    # ── E7c. MABR DECISION FRAMEWORK ──────────────────────────────────────
    try:
        _mabr = getattr(cred, "mabr_assessment", None)
        if _mabr is not None:
            _mabr_dec_icon = {
                "Strategically preferred":  "🟢",
                "Conditionally preferred":  "🟡",
                "Situationally useful":     "🟠",
                "Not preferred":            "🔴",
            }.get(_mabr.decision, "⬜")

            with st.expander(
                f"{_mabr_dec_icon} MABR Decision Framework — {_mabr.decision}",
                expanded=False,
            ):
                # ── Header row: decision + role + carbon strategy ──────────
                _mc1, _mc2, _mc3 = st.columns(3)
                _mc1.metric("WaterPoint Decision", _mabr.decision)
                _mc2.metric("MABR Role", _mabr.role)
                _mc3.metric("Carbon Strategy", _mabr.carbon_strategy_label)

                st.markdown(
                    "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                    unsafe_allow_html=True,
                )

                # ── NP guard flags ─────────────────────────────────────────
                _any_np = _mabr.np1_triggered or _mabr.np2_triggered or _mabr.np3_triggered
                if _any_np:
                    st.markdown("**Not-preferred guards triggered**")
                    if _mabr.np1_triggered:
                        st.caption("🔴 NP-1: No carbon-capture-first architecture — MABR auxiliary "
                                   "complexity does not deliver whole-plant benefit without upstream "
                                   "carbon strategy.")
                    if _mabr.np2_triggered:
                        st.caption("🔴 NP-2: Remote or small plant without confirmed instrumentation "
                                   "capability — dual blower, condensate, exhaust O₂ and NH₄ "
                                   "dependency is disproportionate.")
                    if _mabr.np3_triggered:
                        st.caption("🔴 NP-3: Aeration headroom ≥ 15% confirmed — IFAS delivers "
                                   "equivalent nitrification intensification at lower complexity.")
                    st.markdown(
                        "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                        unsafe_allow_html=True,
                    )

                # ── Whole-plant value test ─────────────────────────────────
                st.markdown("**Whole-plant value test**")
                _wv1, _wv2 = st.columns(2)
                with _wv1:
                    st.caption("✅ **Passes**")
                    for _p in _mabr.wpv_passes:
                        st.caption(f"✅ {_p}")
                with _wv2:
                    st.caption("⚠️ **Fails / gaps**")
                    for _f in _mabr.wpv_fails:
                        st.caption(f"⚠️ {_f}")

                st.markdown(
                    "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                    unsafe_allow_html=True,
                )

                # ── Energy + complexity scores ─────────────────────────────
                _es1, _es2 = st.columns(2)
                _es1.markdown("**Net energy verdict**")
                _es1.caption(_mabr.net_energy_verdict)
                _es2.markdown(f"**Complexity / risk score: {_mabr.complexity_risk_score}/8**")
                for _rf in _mabr.active_risk_factors:
                    _es2.caption(f"• {_rf}")

                st.markdown(
                    "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                    unsafe_allow_html=True,
                )

                # ── Narrative sections ─────────────────────────────────────
                _na1, _na2 = st.columns(2)
                with _na1:
                    st.markdown("**Role in plant architecture**")
                    st.caption(_mabr.best_fit_role_in_plant)
                    st.markdown("**What it replaces**")
                    st.caption(_mabr.what_it_replaces)
                with _na2:
                    st.markdown("**What it enables**")
                    st.caption(_mabr.what_it_enables)
                    st.markdown("**Risks introduced**")
                    st.caption(_mabr.risks_introduced)

                st.markdown(
                    "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                    unsafe_allow_html=True,
                )

                # ── Comparison table ───────────────────────────────────────
                st.markdown("**System-level technology comparison**")
                _ct_cols = st.columns([1.2, 1.4, 1.4, 1.2, 1.0, 1.8, 1.8])
                for _hdr, _col in zip(
                    ["Technology", "System role", "Carbon alignment",
                     "Aeration energy", "Retrofit fit", "Best application",
                     "WaterPoint view"],
                    _ct_cols,
                ):
                    _col.markdown(f"**{_hdr}**")
                st.markdown(
                    "<hr style='margin:2px 0; border-color:#dde3ea;'>",
                    unsafe_allow_html=True,
                )
                for _row in _mabr.comparison_table:
                    _rc = st.columns([1.2, 1.4, 1.4, 1.2, 1.0, 1.8, 1.8])
                    _rc[0].caption(f"**{_row.technology}**")
                    _rc[1].caption(_row.system_role)
                    _rc[2].caption(_row.carbon_alignment)
                    _rc[3].caption(_row.aeration_energy)
                    _rc[4].caption(_row.retrofit_fit)
                    _rc[5].caption(_row.best_application)
                    _rc[6].caption(_row.waterpoint_view)

                st.markdown(
                    "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                    unsafe_allow_html=True,
                )

                # ── Conclusion ─────────────────────────────────────────────
                st.markdown("**WaterPoint conclusion**")
                st.caption(_mabr.conclusion)

    except Exception as _e7c_err:
        with st.expander("🔬 MABR Decision Framework — error", expanded=False):
            st.warning(f"MABR decision layer could not load: {_e7c_err}")

    # ── E8. REFINEMENT PROMPT (Phase 1 → Phase 2) ─────────────────────────
    _render_refinement_section(pathway, ctx)

    # ── E9. ADAPTIVE PATHWAYS ─────────────────────────────────────────────
    _render_adaptive_pathways(pathway, ctx)

    # -- E10. AFFORDABILITY AND RISK COMPARISON -----------------------
    try:
        from apps.wastewater_app.compliance_layer    import build_compliance_report
        from apps.wastewater_app.affordability_layer import build_affordability_comparison
        _co_aff = build_compliance_report(pathway, feas, ctx)
        _aff    = build_affordability_comparison(pathway, _co_aff, ctx)
        _render_affordability(pathway, _co_aff, _aff, ctx)
    except Exception as _e10_err:
        with st.expander('Affordability & Risk Comparison -- error', expanded=False):
            st.warning(f'Affordability layer could not load: {_e10_err}')

    # -- E11. DEFERRAL CONSEQUENCE ENGINE ---------------------------------
    try:
        from apps.wastewater_app.deferral_consequence_engine import build_deferral_consequence
        _dce = build_deferral_consequence(pathway, _co_aff, ap, ctx)
        if _dce.is_active:
            _render_deferral(_dce)
    except Exception as _e11_err:
        with st.expander('Deferral Consequence Analysis -- error', expanded=False):
            st.warning(f'Deferral engine could not load: {_e11_err}')

    # -- E12. TECHNOLOGY ABSTRACTION + AVAILABILITY -----------------------
    try:
        from apps.wastewater_app.tech_abstraction_layer import build_tech_abstraction
        _ta = build_tech_abstraction(pathway, ctx)
        _render_tech_abstraction(_ta)
    except Exception as _e12_err:
        with st.expander('Technology Delivery Context -- error', expanded=False):
            st.warning(f'Technology abstraction layer could not load: {_e12_err}')



def _render_refinement_section(pathway, ctx: dict) -> None:
    """
    E8: Show the Phase 1 → Phase 2 refinement prompt after all synthesis layers.

    Uses st.session_state to:
    - store whether the user has clicked "Add Plant Data"
    - store Phase 2 data if entered
    - preserve Phase 1 result for comparison

    Never blocks the user — the full Phase 1 result is already rendered above.
    """
    import streamlit as st
    from apps.wastewater_app.refinement_layer import (
        evaluate_refinement_trigger, apply_refinement_uplift,
        build_comparison_summary, SEV_HIGH, SEV_MEDIUM, SEV_LOW,
    )
    from apps.wastewater_app.compliance_layer import build_compliance_report
    from apps.wastewater_app.feasibility_layer import assess_feasibility

    # ── Derive confidence score from compliance report ─────────────────────
    try:
        from apps.wastewater_app.credibility_layer import build_credible_output
        feas_e8   = assess_feasibility(pathway, ctx)
        cred_e8   = build_credible_output(pathway, feas_e8, ctx)
        from apps.wastewater_app.waterpoint_adapter import build_waterpoint_input
        # Use the compliance layer to get the confidence score
        co_e8     = build_compliance_report(pathway, feas_e8, ctx)
        p1_score  = co_e8.confidence_score
        p1_drivers = co_e8.confidence_drivers
        p1_stack   = [s.technology for s in pathway.stages]
    except Exception:
        return   # fail silently — E8 is optional enhancement

    # ── Evaluate trigger ───────────────────────────────────────────────────
    trigger = evaluate_refinement_trigger(ctx, p1_score)
    if not trigger.triggered:
        return

    # ── Session state keys (unique per pathway) ───────────────────────────
    _key_base   = f"refine_{id(pathway)}"
    _key_open   = f"{_key_base}_open"
    _key_done   = f"{_key_base}_done"
    _key_skip   = f"{_key_base}_skip"
    _key_p2data = f"{_key_base}_p2data"
    _key_compare= f"{_key_base}_compare"

    if st.session_state.get(_key_skip):
        return   # Part 6: user chose "Continue with Current Assessment" — respect it

    st.markdown("---")

    # ── Severity styling ───────────────────────────────────────────────────
    sev_colour = {SEV_HIGH: "#8b0000", SEV_MEDIUM: "#7a4200", SEV_LOW: "#1b4f7a"}
    sev_icon   = {SEV_HIGH: "🔴", SEV_MEDIUM: "🟡", SEV_LOW: "🔵"}
    colour = sev_colour.get(trigger.severity, "#1b4f7a")
    icon   = sev_icon.get(trigger.severity, "🔵")

    # ── Part 2: UI prompt (always shown when triggered, before user acts) ──
    if not st.session_state.get(_key_done):
        st.markdown(
            f'<div style="border-left:4px solid {colour}; padding:10px 14px; '
            f'background:#f8f9fb; border-radius:4px; margin:8px 0;">'
            f'<b>{icon} Refine with Existing Plant Data</b><br>'
            f'<span style="color:#444; font-size:0.92rem;">{trigger.body_text}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Benefits panel
        with st.expander("What refinement adds", expanded=False):
            for b in [
                "📈  Improve confidence score",
                "🔍  Identify actual plant bottlenecks",
                "✂️  Refine upgrade scope",
                "🛡️  Reduce risk of overdesign",
            ]:
                st.markdown(f"- {b}")
            if trigger.reasons:
                st.markdown("---")
                st.caption("Why this scenario warrants refinement:")
                for r in trigger.reasons[:4]:
                    st.caption(f"→  {r}")

        # CTA buttons (Part 2)
        col_add, col_skip, _ = st.columns([1.4, 1.8, 2.8])
        if col_add.button("➕  Add Plant Data", key=f"{_key_base}_btn_add",
                          type="primary"):
            st.session_state[_key_open] = True
            st.rerun()
        if col_skip.button("Continue with Current Assessment",
                           key=f"{_key_base}_btn_skip"):
            st.session_state[_key_skip] = True
            st.rerun()

    # ── Part 3: Data entry form (shown only after "Add Plant Data" clicked) ─
    if st.session_state.get(_key_open) and not st.session_state.get(_key_done):
        with st.expander("📋 Enter Plant Data — Phase 2 Inputs", expanded=True):
            st.caption(
                "Provide what you have — partial data still improves confidence. "
                "Fields left blank retain Phase 1 assumptions."
            )

            c1, c2 = st.columns(2)

            with c1:
                st.markdown("**Biological reactors**")
                reactor_vol = st.number_input(
                    "Total reactor volume (m³)", min_value=0., value=0.,
                    key=f"{_key_base}_rvol",
                    help="Sum of all biological treatment zone volumes.")
                anoxic_frac = st.slider(
                    "Anoxic fraction (%)", 0, 60, 30,
                    key=f"{_key_base}_anox",
                    help="Percentage of reactor volume in anoxic zones.")

                st.markdown("**Clarifier performance**")
                svi = st.number_input(
                    "Average SVI (mL/g)", min_value=0., max_value=400.,
                    value=float(ctx.get("svi_ml_g") or 0.),
                    key=f"{_key_base}_svi",
                    help="Mixed liquor settleability. 0 = unknown.")
                cl_limited = st.checkbox(
                    "Clarifier identified as a bottleneck",
                    value=bool(ctx.get("clarifier_overloaded")),
                    key=f"{_key_base}_cllim")

            with c2:
                st.markdown("**Aeration system**")
                aer_util = st.slider(
                    "Peak blower utilisation (%)", 0, 100,
                    int(ctx.get("clarifier_util", 0.) * 100),
                    key=f"{_key_base}_aerutil",
                    help="Maximum recorded blower load at peak flow.")
                aer_limited = st.checkbox(
                    "Aeration system identified as a bottleneck",
                    value=bool(ctx.get("aeration_constrained")),
                    key=f"{_key_base}_aerlim")

                st.markdown("**Sludge handling**")
                sludge_status = st.selectbox(
                    "Dewatering / disposal capacity",
                    ["adequate", "constrained", "overloaded"],
                    key=f"{_key_base}_slstatus")

                st.markdown("**Operational context**")
                pain = st.text_area(
                    "Known operational constraints (free text)",
                    placeholder="e.g. winter nitrification failure, wet weather overflow",
                    key=f"{_key_base}_pain", height=68)

            confirm_col, _ = st.columns([1, 3])
            if confirm_col.button("✅  Confirm Plant Data", key=f"{_key_base}_confirm",
                                  type="primary"):
                # Build Phase 2 asset dict and ingest it
                from apps.wastewater_app.brownfield_asset_capture import (
                    ingest_brownfield_asset, COMPLETE, PARTIAL)

                asset_data = {
                    "plant_overview": {
                        "average_flow_MLD":      ctx.get("plant_size_mld", 10.),
                        "peak_flow_MLD":         ctx.get("plant_size_mld", 10.) *
                                                  ctx.get("flow_ratio", 1.5),
                        "TN_target_mgL":         ctx.get("tn_target_mg_l", 8.),
                        "temperature_typical_C": ctx.get("temp_celsius", 18.),
                        "footprint_constraint":  ctx.get("footprint_constraint", "abundant"),
                        "operator_context":      ctx.get("location_type", "metro"),
                    },
                    "aeration_system": {
                        "peak_utilisation_percent": aer_util,
                        "aeration_limited":          aer_limited,
                        "blower_count":              4,   # neutral default
                        "duty_blowers":              3,
                    },
                    "clarifiers": {
                        "average_SVI_mLg":  svi if svi > 0 else None,
                        "clarifier_limited": cl_limited,
                        "total_surface_area_m2": ctx.get("clarifier_area_m2"),
                    },
                    "sludge_system":  {"capacity_status": sludge_status},
                    "biological_reactors": (
                        [{"tank_id": "R1", "function": "mixed",
                          "volume_m3": reactor_vol, "depth_m": 5.,
                          "convertible_to_anoxic": True,
                          "convertible_to_aerobic": True,
                          "MABR_compatible": True,
                          "media_compatible": False}]
                        if reactor_vol > 0 else []
                    ),
                    "pain_points": [p.strip() for p in pain.split(",") if p.strip()],
                }

                p2_result = ingest_brownfield_asset(asset_data)

                if p2_result.status in (COMPLETE, PARTIAL):
                    st.session_state[_key_p2data] = p2_result
                    st.session_state[_key_done]   = True
                    st.session_state[_key_open]   = False
                    st.rerun()
                else:
                    st.error(
                        "Insufficient data provided. Please enter at least average flow "
                        "and temperature to confirm."
                    )

    # ── Part 5: Post-refinement display ───────────────────────────────────
    if st.session_state.get(_key_done):
        p2_result = st.session_state.get(_key_p2data)
        if not p2_result:
            return

        ref = apply_refinement_uplift(p1_score, p2_result.data_confidence, ctx)

        # Score display
        delta_sign = f"+{ref.delta}" if ref.delta >= 0 else str(ref.delta)
        col_orig, col_ref, col_delta = st.columns(3)
        col_orig.metric("Phase 1 Confidence",  f"{ref.original_score}/100")
        col_ref.metric("Refined Confidence",   f"{ref.refined_score}/100",
                       delta=delta_sign)
        col_delta.metric("Input Data Quality", f"{p2_result.data_confidence}/100")

        if ref.uplift_reasons:
            st.success(
                f"**{ref.display_text}**  \n"
                "Confidence improved due to: "
                + ", ".join(ref.uplift_reasons) + "."
            )
        if ref.cap_applied:
            st.caption(
                f"ℹ️ Score capped at {ref.cap_value} — this scenario type carries "
                "inherent uncertainty that plant data alone cannot eliminate."
            )

        if p2_result.assumptions:
            with st.expander("Assumptions retained from Phase 1", expanded=False):
                for a in p2_result.assumptions:
                    st.caption(f"~  {a}")
        if p2_result.guidance:
            with st.expander("Data improvement suggestions", expanded=False):
                for g in p2_result.guidance:
                    st.caption(f"→  {g}")

        # ── Part 7: Comparison view ────────────────────────────────────────
        if st.toggle("Compare Initial vs Refined", key=f"{_key_base}_cmp_toggle"):
            try:
                from apps.wastewater_app.stack_generator import build_upgrade_pathway
                from apps.wastewater_app.waterpoint_adapter import build_waterpoint_input
                from apps.wastewater_app.waterpoint_engine import analyse

                # Merge p2 ctx over p1 ctx for re-evaluation
                p2_ctx = {**ctx, **p2_result.ctx}
                p2_pathway = build_upgrade_pathway(
                    analyse(build_waterpoint_input(None.__class__(), None)),  # dummy — fallback
                    p2_ctx)
                p2_stack   = [s.technology for s in p2_pathway.stages]
                p2_co      = build_compliance_report(
                    p2_pathway, assess_feasibility(p2_pathway, p2_ctx), p2_ctx)
                p2_drivers = p2_co.confidence_drivers
            except Exception:
                # Fallback: show what we have without re-running full analysis
                p2_stack   = p1_stack
                p2_drivers = p1_drivers

            cmp = build_comparison_summary(p1_drivers, p2_drivers,
                                           p1_stack, p2_stack, ref)

            st.markdown("**Comparison: Initial vs Refined**")
            c_a, c_b = st.columns(2)
            with c_a:
                st.caption("Phase 1 (Initial)")
                st.metric("Confidence", f"{cmp['original_score']}/100")
                for s in cmp.get("removed_stages") or p1_stack[:3]:
                    st.markdown(f"→ {s}")
            with c_b:
                st.caption("Phase 2 (Refined)")
                st.metric("Confidence", f"{cmp['refined_score']}/100",
                           delta=f"+{cmp['score_change']}" if cmp['score_change'] >= 0
                           else str(cmp['score_change']))
                for s in cmp.get("added_stages") or p2_stack[:3]:
                    st.markdown(f"→ {s}")

            if cmp["stack_unchanged"]:
                st.info("Stack unchanged — refinement improved data confidence, not technology selection.")
            if cmp["added_drivers"]:
                st.caption("New drivers after refinement: " + "; ".join(cmp["added_drivers"][:3]))
            if cmp["removed_drivers"]:
                st.caption("Resolved drivers: " + "; ".join(cmp["removed_drivers"][:3]))


def _render_adaptive_pathways(pathway, ctx: dict) -> None:
    """
    E9: Adaptive Pathways — staged planning output.
    Shows: Baseline → Tipping Points → Future Stages → Decision Points → Monitoring.
    Pure read-only; never alters engineering outputs.
    """
    import streamlit as st
    try:
        from apps.wastewater_app.adaptive_pathways import build_adaptive_pathways
        from apps.wastewater_app.feasibility_layer import assess_feasibility
        from apps.wastewater_app.compliance_layer import build_compliance_report

        feas_e9 = assess_feasibility(pathway, ctx)
        co_e9   = build_compliance_report(pathway, feas_e9, ctx)
        ap      = build_adaptive_pathways(pathway, co_e9, ctx)
    except Exception as e:
        with st.expander("📍 Adaptive Pathways — error loading", expanded=False):
            st.warning(f"Adaptive Pathways could not load: {e}")
        return

    st.markdown("---")

    with st.expander("📍 Adaptive Pathways", expanded=False):
        st.caption(
            "A staged planning view connecting current constraints to future investment logic. "
            "Answers: What works now? What breaks next? What do we do then?"
        )

        # ── Baseline Pathway ────────────────────────────────────────────────
        st.markdown("### Baseline Pathway")
        st.markdown(
            "The minimum credible set of works required to maintain compliance "
            "and service under current assumptions."
        )

        col_score, col_constraint = st.columns([1, 2])
        conf_colour = {
            "High": "🟢", "Moderate": "🟡", "Low": "🟠", "Very Low": "🔴"
        }.get(ap.baseline_label, "🟡")
        col_score.metric(
            "Baseline Confidence",
            f"{conf_colour} {ap.baseline_confidence}/100",
            help="Confidence that the baseline pathway achieves compliance."
        )
        col_constraint.markdown(f"**Primary constraint:** {ap.baseline_constraint}")

        if ap.baseline_stack:
            st.markdown("**Representative stack:**  " +
                        "  →  ".join(ap.baseline_stack))

        st.info(ap.baseline_summary)

        st.markdown("---")

        # ── Adaptation Tipping Points ────────────────────────────────────────
        st.markdown("### Adaptation Tipping Points")
        st.caption(
            "Conditions under which the baseline pathway is no longer credible "
            "and the next pathway stage must be activated."
        )

        for tp in ap.tipping_points:
            with st.container():
                st.markdown(f"**⚡ {tp.name}**")
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.caption("Trigger condition")
                    st.markdown(tp.trigger)
                with c2:
                    st.caption("Likely consequence")
                    st.markdown(tp.consequence)
                st.markdown(
                    "<hr style='margin:6px 0; border-color:#dde3ea;'>",
                    unsafe_allow_html=True,
                )

        # ── Future Pathway Stages ────────────────────────────────────────────
        st.markdown("### Future Pathway Stages")

        stage_icons = ["1️⃣", "2️⃣", "3️⃣"]
        for i, stage in enumerate(ap.future_stages):
            icon = stage_icons[i] if i < len(stage_icons) else "▶️"
            with st.expander(f"{icon} {stage.stage}", expanded=(i == 0)):
                st.markdown(f"**Purpose:** {stage.purpose}")

                if stage.stack:
                    st.markdown("**Next credible pathway:**")
                    for tech in stage.stack:
                        st.markdown(f"  → {tech}")

                c1, c2 = st.columns([1, 1])
                with c1:
                    st.caption("What it solves")
                    st.markdown(stage.solves)
                with c2:
                    st.caption("Why it is triggered")
                    st.markdown(stage.trigger)

        # ── Decision Points ──────────────────────────────────────────────────
        if ap.decision_points:
            st.markdown("---")
            st.markdown("### Decision Points")
            st.caption(
                "Uncertainties that must be resolved before committing to the next pathway stage."
            )
            for dp in ap.decision_points:
                st.markdown(
                    f"🔷 **Decision Point:** confirm *{dp.issue}* "
                    f"— before: *{dp.before}*"
                )

        # ── Monitoring Priorities ────────────────────────────────────────────
        if ap.monitoring:
            st.markdown("---")
            st.markdown("### Monitoring Priorities")
            st.caption(
                "Practical observations linked directly to future tipping points. "
                "These inform the timing of the next pathway stage."
            )
            for item in ap.monitoring:
                st.markdown(f"📊 {item}")

        # ── Additional Regulatory and Strategic Drivers ──────────────
        if ap.regulatory_drivers:
            st.markdown("---")
            st.markdown("### Additional Regulatory and Strategic Drivers")
            st.caption(
                "Classified triggers that influence future pathway timing, "
                "technology selection, and investment decisions."
            )
            _cls_icon = {"compliance": "🔴", "strategic": "🟡", "system": "🔵"}
            for rd in ap.regulatory_drivers:
                icon = _cls_icon.get(rd.classification, "⚪")
                st.markdown(
                    f"{icon} **{rd.name}** "
                    f"_({rd.classification})_ — {rd.implication}"
                )


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


def _render_affordability(pathway, co, aff, ctx: dict) -> None:
    """
    E10: Affordability and Risk Comparison (v24Z73).
    Pre-CAPEX decision layer -- comparative, qualitative only.
    """
    import streamlit as st

    # Only render if active (>=2 options) or if user wants single-option framing
    if not aff.options:
        return

    is_active = aff.is_active

    title = ("Affordability & Risk Comparison -- " + str(len(aff.options)) + " options"
             if is_active else
             "Affordability & Risk Framing")

    with st.expander("💰 " + title, expanded=is_active):

        # Mandatory decision framing statement (Part 7)
        st.info("**Decision framing:** " + aff.decision_framing)

        # Critical insight -- shared constraint (Part 9)
        if aff.critical_insight:
            st.error("**Critical constraint (applies to ALL options):** " + aff.critical_insight)

        # -- Preferred option (Part 1: named, clear) --
        if aff.preferred_option:
            st.success("**Recommended pathway: " + aff.preferred_option + "**")

        # -- Board decision statement (Part 7) --
        if aff.board_decision:
            st.info("**Board decision:** " + aff.board_decision)

        # -- Performance leader vs recommended (Part 3) --
        if aff.performance_leader and aff.preferred_option and \
                aff.performance_leader != aff.preferred_option:
            st.caption(
                f"Performance leader: **{aff.performance_leader}** | "
                f"Recommended option: **{aff.preferred_option}** "
                "(see rationale below)"
            )
        elif aff.performance_leader:
            st.caption(
                f"Performance leader and recommended option: **{aff.performance_leader}**"
            )

        # -- Score interpretation (Part 2) --
        if aff.score_interpretation:
            st.caption("**Score interpretation:** " + aff.score_interpretation)

        # Preferred path (legacy narrative)
        if aff.preferred_path:
            st.caption(aff.preferred_path)

        if is_active:
            # Comparison table (Part 6)
            st.markdown("---")
            st.markdown("**Option comparison**")
            opt_labels = [o.label for o in aff.options]

            # Header
            n_opts = len(opt_labels)
            col_widths = [1.5] + [2.0] * n_opts
            header_cols = st.columns(col_widths)
            header_cols[0].markdown("**Dimension**")
            for i, lbl in enumerate(opt_labels):
                header_cols[i + 1].markdown(f"**{lbl}**")

            # Band colour helper
            _band_icon = {
                "Low": "🟢", "Moderate": "🟢", "Medium": "🟡",
                "Medium-High": "🟠", "Medium--High": "🟠", "High": "🔴",
                "Very High": "🔴", "Sensitive": "🔴",
            }
            def _icon(val):
                # strip leading emoji if present
                clean = val.split(" -- ")[0].strip()
                return _band_icon.get(clean, "")

            for row in aff.comparison_table:
                row_cols = st.columns(col_widths)
                row_cols[0].caption(row["dimension"])
                for i, lbl in enumerate(opt_labels):
                    val = row.get(lbl, "--")
                    row_cols[i + 1].caption(_icon(val) + " " + val)

            st.markdown("---")

        # Per-option detail cards
        st.markdown("**Option detail**")
        for opt in aff.options:
            with st.container():
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("CAPEX", opt.capex_band)
                c2.metric("OPEX",  opt.opex_band)
                c3.metric("Complexity", opt.complexity)
                c4.metric("Reliability", opt.reliability)

                col_l, col_r = st.columns(2)
                with col_l:
                    st.caption("**Strategic strengths**")
                    for s in opt.strategic_strengths[:4]:
                        st.markdown(f"+ {s}")
                with col_r:
                    st.caption("**Strategic weaknesses**")
                    for w in opt.strategic_weaknesses[:4]:
                        st.markdown(f"- {w}")

                st.caption(
                    f"**Primary risk:** {opt.primary_risk_type}  |  "
                    f"**Delivery risk:** {opt.delivery_risk}  |  "
                    f"**Flexibility:** {opt.flexibility}"
                )
                st.caption(f"**Failure mode:** {opt.failure_mode}")
                if opt.carbon_closure_required:
                    st.caption(
                        f"**Carbon closure required:** Yes -- {opt.carbon_closure_tech or 'DNF or PdNA'}"
                    )
                # Risk positioning (Part 4)
                if aff.risk_positioning and opt.label in aff.risk_positioning:
                    st.caption("**Risk position:** " + aff.risk_positioning[opt.label])
                st.markdown("---")

        # Preferred rationale expander (Part 1)
        if aff.preferred_rationale:
            with st.expander("Why this option is recommended", expanded=False):
                for line in aff.preferred_rationale.split('\n\n'):
                    if line.strip():
                        st.markdown(line.strip())

        # Board summary bullets (Part 8)
        if aff.board_bullets:
            st.markdown("**Board-level summary**")
            for b in aff.board_bullets:
                st.markdown(f"- {b}")


def _render_deferral(dce) -> None:
    """
    E11: Deferral Consequence Analysis (v24Z75).
    Answers: "If we do nothing, what happens next?"
    """
    import streamlit as st

    traj_icon = {
        "Stable": "🟢", "Increasing": "🟡",
        "Accelerating": "🟠", "Critical": "🔴",
    }
    cost_icon = {"Low": "🟢", "Moderate": "🟡", "High": "🟠", "Severe": "🔴"}

    t_icon = traj_icon.get(dce.risk_trajectory, "🟡")
    c_icon = cost_icon.get(dce.cost_exposure, "🟡")

    with st.expander(
        f"⏱️ Deferral Consequence Analysis — "
        f"{t_icon} Trajectory: {dce.risk_trajectory}  |  "
        f"{c_icon} Cost exposure: {dce.cost_exposure}",
        expanded=(dce.risk_trajectory in ("Critical", "Accelerating")),
    ):
        # Risk trajectory + cost exposure header
        col1, col2 = st.columns(2)
        col1.metric("Risk trajectory", f"{t_icon} {dce.risk_trajectory}")
        col2.metric("Cost exposure from deferral", f"{c_icon} {dce.cost_exposure}")

        st.caption(dce.risk_trajectory_reason)
        if dce.cost_exposure_reason:
            st.caption(dce.cost_exposure_reason)

        st.markdown("---")

        # Consequence timeline
        st.markdown("**Consequence timeline if investment is deferred**")
        horizon_icon = {"Immediate": "🔴", "Short": "🟠", "Medium": "🟡", "Long": "🔵"}

        for h in dce.consequence_timeline:
            hi = next((v for k,v in horizon_icon.items() if k.lower() in h.horizon.lower()), "🔵")
            with st.container():
                st.markdown(f"**{hi} {h.horizon}**")
                c_a, c_b = st.columns(2)
                with c_a:
                    st.caption("**Failure mode**")
                    st.markdown(h.primary_failure)
                    st.caption("**System impact**")
                    st.markdown(h.system_impact[:180])
                with c_b:
                    st.caption("**Regulatory impact**")
                    st.markdown(h.regulatory_impact[:150])
                    st.caption("**Operational impact**")
                    st.markdown(h.operational_impact[:120])
                st.markdown("<hr style='margin:4px 0;border-color:#eee;'>",
                            unsafe_allow_html=True)

        # Failure escalation pathway
        if dce.escalation_pathway:
            st.markdown("**Failure escalation pathway**")
            for i, step in enumerate(dce.escalation_pathway, 1):
                st.markdown(f"{i}. {step}")

        # Point of no return
        if dce.point_of_no_return:
            st.warning(f"**Point of no return:** {dce.point_of_no_return}")

        # Per-stage deferral frames
        if dce.stage_frames:
            st.markdown("---")
            st.markdown("**Per-stage deferral decision frame**")
            for sf in dce.stage_frames:
                st.markdown(f"**{sf.stage_label}**")
                st.caption(
                    f"Deferring this stage avoids: {sf.avoids}  |  "
                    f"But introduces: {sf.introduces_risk}  |  "
                    f"Failure mode: {sf.failure_mode}  |  "
                    f"Likely within: {sf.time_horizon}"
                )

        # Board delay bullets
        if dce.board_delay_bullets:
            st.markdown("---")
            st.markdown("**Consequence of delay — board summary**")
            for b in dce.board_delay_bullets:
                st.markdown(f"- {b}")


def _render_tech_abstraction(ta) -> None:
    """
    E12: Technology Abstraction, Availability and MOB Classification (v24Z76).
    Process-class-first language with delivery risk and alternatives.
    """
    import streamlit as st

    avail_icon = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}
    risk_icon  = {"Low": "🟢", "Medium": "🟡", "Medium--High": "🟠", "High": "🔴"}

    with st.expander("🔬 Technology Delivery Context", expanded=False):

        # Part 9: Board delivery context
        st.info("**Technology delivery context:** " + ta.delivery_context)

        if ta.consistency_flags:
            for flag in ta.consistency_flags:
                st.warning(f"⚠️ {flag}")

        # v24Z77 Technology Selection Confidence line (Part 7)
        sr = getattr(ta, 'selection_rationale', None)
        if sr and getattr(sr, 'board_confidence_line', ''):
            st.caption(sr.board_confidence_line)

        st.markdown("---")

        # v24Z77 Technology Selection Rationale (Part 3)
        if sr:
            with st.expander(
                f"Technology selection rationale — "
                f"{len(sr.selected)} selected, {len(sr.excluded)} excluded",
                expanded=False,
            ):
                if sr.selected:
                    st.markdown("**Selected technologies**")
                    for j in sr.selected:
                        st.markdown(f"**{j.process_class}**")
                        st.caption(
                            f"Status: ✅ Selected  |  Primary constraint: {j.primary_constraint}"
                        )
                        st.caption(j.reason)
                        st.markdown("<hr style='margin:4px 0;border-color:#eee;'>",
                                    unsafe_allow_html=True)
                if sr.excluded:
                    st.markdown("**Excluded technologies**")
                    for j in sr.excluded:
                        st.markdown(f"**{j.process_class}**")
                        st.caption(
                            f"Status: ❌ Not selected  |  Primary constraint: {j.primary_constraint}"
                        )
                        st.caption(j.reason)
                        st.markdown("<hr style='margin:4px 0;border-color:#eee;'>",
                                    unsafe_allow_html=True)

        st.markdown("---")

        # Per-technology profiles
        for prof in ta.profiles:
            ai = avail_icon.get(prof.availability, "🟡")
            ri = risk_icon.get(prof.delivery_risk, "🟡")

            st.markdown(f"**{prof.process_class}**")

            col_a, col_b = st.columns(2)
            col_a.caption(
                f"**Availability:** {ai} {prof.availability}  |  "
                f"**Delivery risk:** {ri} {prof.delivery_risk}"
            )
            if prof.vendor_examples:
                col_b.caption(f"*{prof.vendor_examples}*")

            st.caption(f"**Mechanism:** {prof.mechanism[:200]}")

            if prof.is_mob:
                st.info(f"**MOB — process class definition:** {prof.mob_note}")

            if prof.alternatives:
                st.caption(
                    "**Alternatives:** " + " | ".join(prof.alternatives[:3])
                )
            st.markdown("<hr style='margin:4px 0;border-color:#f0f0f0;'>",
                        unsafe_allow_html=True)

