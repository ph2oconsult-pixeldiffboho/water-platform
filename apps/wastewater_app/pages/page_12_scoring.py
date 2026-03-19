"""
apps/wastewater_app/pages/page_12_scoring.py

Weighted Decision Scoring Page
================================
Transparent multi-criteria scoring with user-selectable weight profiles.

Outputs:
  - Compliance gate (pass/fail per scenario)
  - Weighted score table (0–100 per criterion)
  - Decision summary card (preferred / runner-up / excluded)
  - Trade-off narrative
  - Weight profile selector
  - QA guardrails (no non-compliant option ranked first, weights sum to 100)
"""
from __future__ import annotations

import streamlit as st
import pandas as pd
from apps.ui.session_state import require_project, get_current_project
from apps.ui.ui_components import render_page_header
from core.decision.scoring_engine import (
    ScoringEngine, WeightProfile, WEIGHT_PROFILES,
    CRITERION_LABELS, CRITERION_LOWER_IS_BETTER,
    DecisionResult, ScoredOption,
)


# ── Colour helpers ────────────────────────────────────────────────────────────

def _compliance_badge(status: str) -> str:
    if status == "Compliant":
        return "✅ Compliant"
    if "intervention" in status.lower():
        return "⚠️ Compliant with intervention"
    return "❌ Non-compliant"


def _score_colour(score: float) -> str:
    if score >= 70:
        return "#27AE60"
    if score >= 45:
        return "#E67E22"
    return "#C0392B"


def _bar(score: float, width: int = 120) -> str:
    """Mini progress bar as HTML."""
    pct  = min(100, max(0, score))
    col  = _score_colour(score)
    fill = int(pct / 100 * width)
    return (
        f'<div style="display:inline-block;width:{width}px;height:10px;'
        f'background:#eee;border-radius:5px;vertical-align:middle;">'
        f'<div style="width:{fill}px;height:10px;background:{col};border-radius:5px;"></div>'
        f'</div>'
    )


# ── Compliance classifier ─────────────────────────────────────────────────────

def _classify_compliance(scenario) -> str:
    """
    Returns "Compliant" | "Compliant with intervention" | "Non-compliant"
    by comparing technology_performance effluent values against domain_inputs targets.
    """
    dso  = getattr(scenario, "domain_specific_outputs", None) or {}
    tp   = dso.get("technology_performance", {})
    dinp = getattr(scenario, "domain_inputs", None) or {}

    tn_target  = dinp.get("effluent_tn_mg_l",  10.0)
    nh4_target = dinp.get("effluent_nh4_mg_l",  5.0)
    tp_target  = dinp.get("effluent_tp_mg_l",   1.0)
    bod_target = dinp.get("effluent_bod_mg_l",  20.0)
    tss_target = dinp.get("effluent_tss_mg_l",  20.0)

    hard_fail = False
    marginal  = False

    for tech_perf in tp.values():
        for actual_key, target, margin in [
            ("effluent_tn_mg_l",  tn_target,  0.10),
            ("effluent_nh4_mg_l", nh4_target, 0.10),
            ("effluent_tp_mg_l",  tp_target,  0.10),
            ("effluent_bod_mg_l", bod_target, 0.10),
            ("effluent_tss_mg_l", tss_target, 0.10),
        ]:
            actual = tech_perf.get(actual_key)
            if actual is None:
                continue
            if actual > target * (1 + margin):
                hard_fail = True
            elif actual > target * 1.02:
                marginal = True

    if hard_fail:
        return "Non-compliant"
    if marginal:
        return "Compliant with intervention"
    return "Compliant"


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    render_page_header(
        "🏆 Decision Scoring",
        subtitle="Transparent multi-criteria ranking with user-defined weights",
    )
    require_project()
    project = get_current_project()
    all_scen = project.get_all_scenarios()
    calc     = [s for s in all_scen if s.cost_result and s.risk_result]

    if len(calc) < 2:
        st.info("Calculate at least 2 scenarios to use the Decision Scoring page.")
        return

    # ── Weight profile selector ───────────────────────────────────────────
    st.subheader("Weight Profile")

    profile_options = {
        WeightProfile.BALANCED:  "Balanced utility planning",
        WeightProfile.LOW_RISK:  "Low-risk utility",
        WeightProfile.LOW_CARBON: "Low-carbon / future-focused",
        WeightProfile.BUDGET:    "Budget-constrained utility",
        WeightProfile.CUSTOM:    "Custom weights",
    }

    selected_profile = st.selectbox(
        "Select weighting profile",
        options=list(profile_options.keys()),
        format_func=lambda p: profile_options[p],
        help=(
            "Each profile reflects a different utility priority. "
            "Compliance is always a hard gate — non-compliant options are excluded regardless."
        ),
    )

    # Custom weight sliders
    custom_weights = None
    if selected_profile == WeightProfile.CUSTOM:
        st.caption("Set weights below — they will be normalised to sum to 100%.")
        base = WEIGHT_PROFILES[WeightProfile.BALANCED]
        cols = st.columns(3)
        raw_weights = {}
        for i, (crit, label) in enumerate(CRITERION_LABELS.items()):
            col = cols[i % 3]
            raw_weights[crit] = col.slider(
                label, 0, 30,
                int(base.get(crit, 0.10) * 100),
                key=f"weight_{crit}",
            )
        total = sum(raw_weights.values())
        if total == 0:
            st.error("Weights must sum to more than 0.")
            return
        custom_weights = {k: v / total for k, v in raw_weights.items()}
        st.caption(f"Total before normalisation: {total}% → normalised to 100%")
    else:
        # Display the selected profile's weights
        weights = WEIGHT_PROFILES[selected_profile]
        w_df = pd.DataFrame([
            {"Criterion": CRITERION_LABELS[k], "Weight": f"{v*100:.0f}%"}
            for k, v in weights.items()
        ])
        with st.expander("View weight breakdown", expanded=False):
            st.dataframe(w_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Build compliance map ──────────────────────────────────────────────
    compliance_map = {s.scenario_name: _classify_compliance(s) for s in calc}

    # ── Engineering Feasibility Status ────────────────────────────────────
    # Pull from session state (computed by report engine) if available
    _feasibility    = st.session_state.get("feasibility_statuses") or {}
    _fixed_scens    = st.session_state.get("fixed_scenarios") or []
    _hydraulic      = st.session_state.get("hydraulic_stress") or {}
    _remediations   = st.session_state.get("remediation_results") or []
    _decision_path  = st.session_state.get("decision_pathway") or []

    # If not in session, compute them now
    if not _feasibility and len(calc) >= 2:
        try:
            from core.engineering.hydraulic_stress import run_all_hydraulic_stress
            from core.engineering.remediation import remediate_scenarios
            from core.engineering.feasibility_status import compute_feasibility
            _hydraulic    = run_all_hydraulic_stress(calc)
            _remediations = remediate_scenarios(calc, _hydraulic, None)
            _fixed_scens  = [r.modified_scenario for r in _remediations
                             if r.feasible and r.modified_scenario]
            _feasibility  = compute_feasibility(calc, _hydraulic, _remediations)
        except Exception:
            pass

    # Extend calc with fixed scenarios for scoring
    _calc_extended = calc + _fixed_scens
    for _fs in _fixed_scens:
        compliance_map[_fs.scenario_name] = "Compliant"

    # ── Run scoring engine ────────────────────────────────────────────────
    engine = ScoringEngine()
    try:
        result: DecisionResult = engine.score(
            _calc_extended,
            weight_profile=selected_profile,
            custom_weights=custom_weights,
            compliance_map=compliance_map,
        )
        # Mark original FAIL scenarios as excluded
        from core.engineering.feasibility_status import FEASIBILITY_FAIL
        for _opt in result.scored_options:
            _fst = _feasibility.get(_opt.scenario_name)
            if _fst and _fst.status == FEASIBILITY_FAIL:
                _opt.is_eligible = False
                _opt.excluded_reason = "Engineering Feasibility: FAIL"
        # Apply confidence penalties
        try:
            from core.engineering.feasibility_status import apply_confidence_penalties
            _all_fs = dict(_feasibility)
            for _fs in _fixed_scens:
                _all_fs[_fs.scenario_name] = type("_FS",(),{
                    "status": "CONDITIONAL", "confidence_penalty": 5.0
                })()
            apply_confidence_penalties(result.scored_options, _all_fs)
            # Recompute preferred after penalties
            _elig = sorted([o for o in result.scored_options if o.is_eligible],
                           key=lambda x: -x.total_score)
            if _elig:
                result.preferred = _elig[0]
                result.runner_up  = _elig[1] if len(_elig) > 1 else None
        except Exception:
            pass
    except Exception as e:
        st.error(f"Scoring error: {e}")
        return

    # Store in session for comparison page integration
    st.session_state["decision_scoring_result"] = result
    st.session_state["feasibility_statuses"]    = _feasibility
    st.session_state["fixed_scenarios"]         = _fixed_scens
    st.session_state["hydraulic_stress"]        = _hydraulic
    st.session_state["remediation_results"]     = _remediations

    # ── Engineering Feasibility Panel ─────────────────────────────────────
    if _feasibility:
        st.subheader("Engineering Feasibility Status")
        _status_colours = {"PASS": "#27AE60", "CONDITIONAL": "#E67E22", "FAIL": "#C0392B"}
        _fs_cols = st.columns(len(_feasibility))
        for _i, (_sn, _fst) in enumerate(_feasibility.items()):
            with _fs_cols[min(_i, len(_fs_cols)-1)]:
                _col = _status_colours.get(_fst.status, "#888")
                st.markdown(
                    f'<div style="border:2px solid {_col};border-radius:6px;padding:8px;text-align:center;">'
                    f'<div style="font-weight:700;font-size:0.8rem;">{_sn[:16]}</div>'
                    f'<div style="color:{_col};font-weight:800;font-size:1rem;">{_fst.status}</div>'
                    f'<div style="font-size:0.7rem;color:#666;">{_fst.hydraulic_gate}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        st.divider()

        # Hydraulic warnings / failures
        _hydr_warns = [(n, h) for n,h in _hydraulic.items() if h.overall_status != "PASS"]
        if _hydr_warns:
            for _hn, _hs in _hydr_warns:
                _icon = "🚨" if _hs.overall_status == "FAIL" else "⚠️"
                st.warning(f"{_icon} **{_hn}** — {_hs.narrative[:120]}")
        if _fixed_scens:
            st.info(
                f"ℹ️ {len(_fixed_scens)} remediated scenario(s) added to comparison: "
                + ", ".join(f"**{fs.scenario_name}**" for fs in _fixed_scens)
                + ". Confidence adjusted (−5 pts) to reflect redesign cost uncertainty."
            )
        st.divider()

    # ── QA guardrail check ────────────────────────────────────────────────
    if result.preferred:
        pref_compliance = compliance_map.get(result.preferred.scenario_name, "Compliant")
        if pref_compliance == "Non-compliant":
            st.error(
                "⛔ QA GUARDRAIL TRIGGERED: Preferred option is non-compliant. "
                "This should not be possible — please report this as a bug."
            )
            return

    weights_total = sum(
        (custom_weights or WEIGHT_PROFILES.get(selected_profile, {})).values()
    )
    if not (0.98 <= weights_total <= 1.02):
        st.warning(f"⚠️ Weights sum to {weights_total*100:.1f}% — should be 100%.")

    # ── Decision Summary Card ─────────────────────────────────────────────
    st.subheader("Decision Summary")

    if not result.preferred:
        st.error(
            "⛔ No compliant option available. All scenarios fail mandatory effluent targets. "
            "Engineering intervention required before any option can be recommended."
        )
    else:
        # Top banner
        pref = result.preferred
        ru   = result.runner_up

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown(
                f"""
                <div style="border:2px solid #27AE60;border-radius:8px;padding:16px;">
                <div style="color:#27AE60;font-size:0.75rem;font-weight:700;
                            text-transform:uppercase;letter-spacing:1px;">Preferred Option</div>
                <div style="font-size:1.4rem;font-weight:700;margin:4px 0;">{pref.scenario_name}</div>
                <div style="font-size:2rem;font-weight:800;color:#27AE60;">{pref.total_score:.0f}
                    <span style="font-size:1rem;font-weight:400;color:#666;">/100</span>
                </div>
                <div style="margin-top:6px;font-size:0.85rem;color:#444;">
                    {_compliance_badge(pref.compliance_status)}
                </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            if ru:
                st.markdown(
                    f"""
                    <div style="border:2px solid #1F6AA5;border-radius:8px;padding:16px;">
                    <div style="color:#1F6AA5;font-size:0.75rem;font-weight:700;
                                text-transform:uppercase;letter-spacing:1px;">Runner-Up</div>
                    <div style="font-size:1.4rem;font-weight:700;margin:4px 0;">{ru.scenario_name}</div>
                    <div style="font-size:2rem;font-weight:800;color:#1F6AA5;">{ru.total_score:.0f}
                        <span style="font-size:1rem;font-weight:400;color:#666;">/100</span>
                    </div>
                    <div style="margin-top:6px;font-size:0.85rem;color:#444;">
                        {_compliance_badge(ru.compliance_status)}
                    </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.info("No runner-up — only one compliant option available.")

        st.markdown("")

        # Close decision warning
        if result.close_decision and ru:
            gap = pref.total_score - ru.total_score
            st.warning(
                f"⚠️ **Close decision** — scoring gap is {gap:.1f} points. "
                f"This is within concept-stage scoring uncertainty. "
                "Final selection should depend on site constraints and risk appetite, not score alone."
            )

        # Recommendation narrative
        st.markdown(f"**Recommendation:** {result.recommendation}")
        if result.trade_off:
            st.markdown(f"**Trade-off accepted:** {result.trade_off}")

        # Why it won
        if result.rationale:
            with st.expander("Why the preferred option won", expanded=True):
                for r in result.rationale:
                    st.markdown(f"• {r}")

    # ── Weighted Score Table ──────────────────────────────────────────────
    st.subheader("Weighted Score Table")
    st.caption(
        "Scores normalised 0–100. Higher = better for all criteria. "
        "Weighted score = normalised × weight. Compliance gate applied before ranking."
    )

    all_scored = result.scored_options
    if all_scored:
        crit_order = list(CRITERION_LABELS.keys())
        crit_labels = list(CRITERION_LABELS.values())

        # Header row — add confidence adjustment column
        _has_conf_adj = any(hasattr(o, "confidence_adj") and o.confidence_adj for o in all_scored)
        _extra_cols   = [1] if _has_conf_adj else []
        header_cols = st.columns([2, 1.5, 1] + _extra_cols + [1] * len(crit_order))
        header_cols[0].markdown("**Scenario**")
        header_cols[1].markdown("**Compliance / Status**")
        header_cols[2].markdown("**Total**")
        if _has_conf_adj:
            header_cols[3].markdown("**Conf. Adj**")
        for i, label in enumerate(crit_labels):
            w = WEIGHT_PROFILES.get(selected_profile, {}).get(crit_order[i], 0)
            w_pct = int(w * 100)
            header_cols[3 + i].markdown(f"**{label[:10]}**<br><small>{w_pct}%</small>",
                                         unsafe_allow_html=True)

        st.markdown("---")

        for opt in all_scored:
            row_cols = st.columns([2, 1.5, 1] + [1] * len(crit_order))
            # Name
            if opt.rank == 1:
                row_cols[0].markdown(f"⭐ **{opt.scenario_name}**")
            elif opt.excluded_reason:
                row_cols[0].markdown(f"~~{opt.scenario_name}~~")
            else:
                row_cols[0].markdown(f"{opt.scenario_name}")

            # Compliance / feasibility status
            _fst_ui = _feasibility.get(opt.scenario_name) if _feasibility else None
            if _fst_ui:
                _status_icon = {"PASS": "✅", "CONDITIONAL": "⚠️", "FAIL": "❌"}.get(_fst_ui.status, "")
                row_cols[1].markdown(f"{_status_icon} **{_fst_ui.status}**")
            else:
                row_cols[1].markdown(_compliance_badge(opt.compliance_status))
            # Confidence adjustment (if present)
            if _has_conf_adj:
                _base  = getattr(opt, "base_score", None)
                _cadj  = getattr(opt, "confidence_adj", 0)
                if _base is not None and _cadj:
                    row_cols[3].markdown(f"<small>{_cadj:+.0f} pts</small>", unsafe_allow_html=True)
                else:
                    row_cols[3].markdown("<small>—</small>", unsafe_allow_html=True)

            # Total score
            col = _score_colour(opt.total_score)
            row_cols[2].markdown(
                f'<span style="font-size:1.1rem;font-weight:700;color:{col};">'
                f'{opt.total_score:.0f}</span>',
                unsafe_allow_html=True,
            )

            # Per-criterion scores
            for i, crit in enumerate(crit_order):
                cs = opt.criterion_scores.get(crit)
                if cs:
                    row_cols[3 + i].markdown(
                        f"{cs.normalised:.0f}<br>"
                        f'<small style="color:#888;">{cs.raw_value:.1f}</small>',
                        unsafe_allow_html=True,
                    )
                else:
                    row_cols[3 + i].markdown("—")

    # ── Excluded Options ──────────────────────────────────────────────────
    if result.excluded:
        st.subheader("Excluded from Ranking")
        for opt in result.excluded:
            st.markdown(
                f"""
                <div style="border-left:4px solid #C0392B;padding:8px 12px;
                            margin:4px 0;background:#FEF9F9;border-radius:0 4px 4px 0;">
                <b>{opt.scenario_name}</b> — {opt.excluded_reason}<br>
                <small style="color:#888;">
                This option is shown for reference only and cannot be recommended for procurement.
                Engineering intervention may make it viable — see alternative pathways.
                </small>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ── Compliance Detail ─────────────────────────────────────────────────
    st.subheader("Compliance Detail")
    for s in calc:
        status = compliance_map.get(s.scenario_name, "Compliant")
        dso    = getattr(s, "domain_specific_outputs", None) or {}
        tp     = dso.get("technology_performance", {})
        dinp   = getattr(s, "domain_inputs", None) or {}

        with st.expander(f"{s.scenario_name} — {_compliance_badge(status)}"):
            if not tp:
                st.caption("No technology performance data available.")
                continue
            for tech, perf in tp.items():
                targets = {
                    "TN":  ("effluent_tn_mg_l",  dinp.get("effluent_tn_mg_l",  10.0)),
                    "NH4": ("effluent_nh4_mg_l",  dinp.get("effluent_nh4_mg_l",  5.0)),
                    "TP":  ("effluent_tp_mg_l",   dinp.get("effluent_tp_mg_l",   1.0)),
                    "BOD": ("effluent_bod_mg_l",  dinp.get("effluent_bod_mg_l",  20.0)),
                    "TSS": ("effluent_tss_mg_l",  dinp.get("effluent_tss_mg_l",  20.0)),
                }
                rows = []
                for param, (key, target) in targets.items():
                    actual = perf.get(key)
                    if actual is None:
                        continue
                    margin = actual / target if target else 0
                    if margin > 1.10:
                        flag = "❌ FAIL"
                    elif margin > 1.02:
                        flag = "⚠️ Marginal"
                    else:
                        flag = "✅ Pass"
                    rows.append({
                        "Parameter": param,
                        "Actual (mg/L)": f"{actual:.1f}",
                        "Target (mg/L)": f"{target:.1f}",
                        "Status": flag,
                    })
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Weight profile note ───────────────────────────────────────────────
    st.caption(
        f"Weight profile: **{profile_options[selected_profile]}**. "
        "Scores are concept-stage comparisons only (±40%). "
        "Sensitivity test with alternative profiles before technology lock-in."
    )


    # ── Engineering Decision Pathway ──────────────────────────────────────
    if _decision_path:
        st.divider()
        st.subheader("⚙️ Engineering Decision Pathway")
        st.caption(
            "Four-step pathway from initial scoring to final recommendation, "
            "incorporating feasibility checking, remediation, and confidence adjustment."
        )
        import pandas as pd
        _dp_df = pd.DataFrame(_decision_path)[["step","title","outcome","status"]]
        _dp_df.columns = ["Step","Stage","Outcome","Confidence / Status"]
        st.dataframe(_dp_df, use_container_width=True, hide_index=True)
    elif _fixed_scens or _remediations:
        # Compute a live pathway if not stored
        st.divider()
        st.subheader("⚙️ Remediation Summary")
        for _rem in _remediations:
            _ms = _rem.modified_scenario
            if _ms and _ms.cost_result:
                _lcc = _ms.cost_result.lifecycle_cost_annual / 1e3
                st.success(
                    f"🔧 **{_rem.scenario_name}** → **{_ms.scenario_name}**: "
                    f"{_rem.fix_description[:80]}. "
                    f"LCC after fix: ${_lcc:.0f}k/yr. "
                    f"Hydraulic status: [{_rem.hydraulic_status_after}]."
                )
