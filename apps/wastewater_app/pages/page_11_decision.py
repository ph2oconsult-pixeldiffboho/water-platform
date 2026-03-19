"""
apps/wastewater_app/pages/page_11_decision.py

Decision Framework Page
========================
Transforms engineering outputs into investment decision content.
Covers all 10 outputs required:

  1. Recommendation
  2. Non-viable options
  3. Trade-offs
  4. Fit ratings
  5. Delivery model suitability
  6. Constructability
  7. Upgrade pathway
  8. Operational complexity
  9. Failure modes
 10. Regulatory confidence
 11. Executive summary
"""
from __future__ import annotations
import streamlit as st
from apps.ui.session_state import require_project, get_current_project
from apps.ui.ui_components import render_page_header
from domains.wastewater.decision_engine import (
    evaluate_scenario, Rating, Complexity,
    DeliveryModelAssessment, ConstructabilityAssessment,
    StagingPathway, OperationalComplexity,
    FailureModeProfile, RegulatoryConfidence,
    TechnologyDecisionProfile, ScenarioDecision,
)
from domains.wastewater.input_model import WastewaterInputs
from domains.wastewater.technology_fit import assess_all_technologies


def render() -> None:
    render_page_header(
        "🎯 Decision Framework",
        subtitle="Investment decision content aligned with utility capital planning",
    )

    project = require_project()
    if not project:
        return

    # Collect calculated scenarios
    calc = [s for s in project.scenarios.values()
            if s.cost_result and s.risk_result and s.domain_specific_outputs]

    if len(calc) < 1:
        st.info("Calculate at least one scenario to generate the decision framework.")
        return

    if len(calc) < 2:
        st.warning(
            "⚠️ Only one scenario calculated. "
            "The decision framework is most useful with 2–4 options compared. "
            "Showing single-option analysis."
        )

    # Reconstruct WastewaterInputs from first scenario
    di = calc[0].domain_inputs or {}
    known = {f for f in WastewaterInputs.__dataclass_fields__ if not f.startswith("_")}
    inputs = WastewaterInputs(**{k: v for k, v in di.items() if k in known})

    # Run decision engine
    decision = evaluate_scenario(calc, inputs)

    # ── Engineering Decision Pathway (from scoring engine) ───────────────────
    _dp11  = st.session_state.get("decision_pathway") or []
    _fs11  = st.session_state.get("feasibility_statuses") or {}
    _fix11 = st.session_state.get("fixed_scenarios") or []
    _rem11 = st.session_state.get("remediation_results") or []

    if _dp11 or _fs11 or _fix11:
        with st.expander("⚙️ Engineering Decision Pathway", expanded=True):
            if _fs11:
                _status_icon = {"PASS": "✅", "CONDITIONAL": "⚠️", "FAIL": "❌"}
                _cols11 = st.columns(len(_fs11))
                for _i11, (_sn11, _fst11) in enumerate(_fs11.items()):
                    with _cols11[min(_i11, len(_cols11)-1)]:
                        _ic = _status_icon.get(_fst11.status, "")
                        st.metric(
                            label=_sn11[:16],
                            value=f"{_ic} {_fst11.status}",
                            help=_fst11.rationale,
                        )

            if _fix11:
                st.divider()
                for _rem11_item in _rem11:
                    _ms11 = _rem11_item.modified_scenario
                    if _ms11 and _ms11.cost_result:
                        _lcc11 = _ms11.cost_result.lifecycle_cost_annual / 1e3
                        st.success(
                            f"🔧 **Redesign applied**: {_rem11_item.scenario_name} → "
                            f"**{_ms11.scenario_name}**  |  "
                            f"{_rem11_item.fix_description[:70]}  |  "
                            f"LCC: ${_lcc11:.0f}k/yr  |  "
                            f"[{_rem11_item.hydraulic_status_after}] after fix"
                        )

            if _dp11:
                st.divider()
                import pandas as pd
                _dp11_df = pd.DataFrame(_dp11)[["step","title","outcome","status"]]
                _dp11_df.columns = ["Step","Stage","Outcome","Confidence"]
                st.dataframe(_dp11_df, use_container_width=True, hide_index=True)

        st.divider()

    # ── Executive Summary ─────────────────────────────────────────────────────
    _render_executive_summary(decision, calc, inputs)

    # ── Detailed sections ─────────────────────────────────────────────────────
    tabs = st.tabs([
        "📋 Trade-offs",
        "🏗️ Delivery Model",
        "🔧 Constructability",
        "📈 Staging & Upgrades",
        "⚙️ Ops Complexity",
        "⚠️ Failure Modes",
        "📜 Regulatory",
        "🎯 Fit Assessment",
        "🔀 Alternative Pathways",
        "🤝 Client Decision",
        "💰 Financial Risk",
        "⚖️ Weighted Scoring",
    ])

    with tabs[0]:
        _render_tradeoffs(decision, calc)

    with tabs[1]:
        _render_delivery(decision)

    with tabs[2]:
        _render_constructability(decision)

    with tabs[3]:
        _render_staging(decision)

    with tabs[4]:
        _render_ops_complexity(decision)

    with tabs[5]:
        _render_failure_modes(decision)

    with tabs[6]:
        _render_regulatory(decision)

    with tabs[7]:
        _render_fit_assessment(calc, inputs)

    with tabs[8]:
        _render_alternative_pathways(decision)

    with tabs[9]:
        _render_client_framing(decision)

    with tabs[10]:
        _render_financial_risk(decision)

    with tabs[11]:
        _render_weighted_scoring(decision, calc)


# ─────────────────────────────────────────────────────────────────────────────
# WEIGHTED SCORING
# ─────────────────────────────────────────────────────────────────────────────

def _render_weighted_scoring(decision, calc) -> None:
    """Weighted multi-criteria scoring panel with profile selector."""
    import pandas as pd
    from core.decision.scoring_engine import (
        ScoringEngine, WeightProfile, WEIGHT_PROFILES, CRITERION_LABELS,
        DecisionResult,
    )

    st.subheader("⚖️ Weighted Multi-Criteria Decision Scoring")
    st.caption(
        "Normalised 0–100 score per criterion, weighted by selected profile. "
        "Compliance gate applied first — non-compliant options are excluded from ranking."
    )

    # ── Profile selector ──────────────────────────────────────────────────────
    profile_labels = {
        "Balanced utility planning":       WeightProfile.BALANCED,
        "Low-risk utility":                WeightProfile.LOW_RISK,
        "Low-carbon / future-focused":     WeightProfile.LOW_CARBON,
        "Budget-constrained utility":      WeightProfile.BUDGET,
        "Custom":                          WeightProfile.CUSTOM,
    }

    selected_label = st.selectbox(
        "Weight profile",
        list(profile_labels.keys()),
        index=0,
        help="Select a pre-set weight profile or choose Custom to adjust weights manually.",
    )
    selected_profile = profile_labels[selected_label]

    # ── Custom weights ────────────────────────────────────────────────────────
    custom_weights = None
    if selected_profile == WeightProfile.CUSTOM:
        st.markdown("**Adjust weights (must sum to 100%)**")
        defaults = WEIGHT_PROFILES[WeightProfile.BALANCED]
        cols = st.columns(3)
        w = {}
        crit_list = list(defaults.keys())
        for i, crit in enumerate(crit_list):
            col = cols[i % 3]
            w[crit] = col.slider(
                CRITERION_LABELS.get(crit, crit),
                0, 40,
                int(defaults[crit] * 100),
                5,
                key=f"w_{crit}",
            ) / 100.0
        total_w = sum(w.values())
        if abs(total_w - 1.0) > 0.05:
            st.warning(f"⚠️ Weights sum to {total_w*100:.0f}% — adjust to reach 100%")
        else:
            custom_weights = w

    # ── Build compliance map from existing decision ────────────────────────────
    compliance_map = {
        s.scenario_name: (
            "Non-compliant" if s.scenario_name in (decision.non_viable or [])
            else "Compliant"
        )
        for s in calc
    }

    # ── Run scoring engine ────────────────────────────────────────────────────
    try:
        engine = ScoringEngine()
        result: DecisionResult = engine.score(
            calc,
            weight_profile=selected_profile,
            custom_weights=custom_weights,
            compliance_map=compliance_map,
        )
    except Exception as e:
        st.error(f"Scoring engine error: {e}")
        return

    # ── Decision summary card ─────────────────────────────────────────────────
    if result.preferred:
        if result.close_decision:
            st.info(f"🔀 **Close decision** — {result.recommendation}")
        else:
            st.success(f"✅ **{result.preferred.scenario_name}** — {result.recommendation}")
        if result.trade_off:
            st.caption(f"Trade-off accepted: {result.trade_off}")

    # ── Excluded options ──────────────────────────────────────────────────────
    if result.excluded:
        with st.expander(f"⛔ {len(result.excluded)} option(s) excluded from ranking"):
            for opt in result.excluded:
                st.markdown(f"- **{opt.scenario_name}** — {opt.excluded_reason}")

    # ── Weighted score table ──────────────────────────────────────────────────
    st.markdown("#### Weighted Score Breakdown")
    st.caption(
        f"Weight profile: **{result.weight_profile}** | "
        "Scores: 0–100 (higher is always better) | "
        "Non-compliant options excluded from ranking."
    )

    eligible = [o for o in result.scored_options if o.is_eligible]
    if not eligible:
        st.warning("No compliant options to score.")
        return

    # Build score table
    crit_keys = list(WEIGHT_PROFILES[WeightProfile.BALANCED].keys())
    rows = []
    for opt in eligible:
        row = {
            "Rank":       f"{'★' if opt.rank == 1 else opt.rank}",
            "Option":     opt.scenario_name,
            "Compliance": opt.compliance_status,
            "Total Score": f"{opt.total_score:.0f}/100",
        }
        for ck in crit_keys:
            cs = opt.criterion_scores.get(ck)
            if cs:
                row[CRITERION_LABELS.get(ck, ck)] = f"{cs.normalised:.0f}"
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Weight display ────────────────────────────────────────────────────────
    with st.expander("📊 Active weight set"):
        w_rows = [
            {"Criterion": CRITERION_LABELS.get(k, k), "Weight": f"{v*100:.0f}%"}
            for k, v in result.weights.items()
        ]
        st.dataframe(pd.DataFrame(w_rows), use_container_width=True, hide_index=True)
        total = sum(result.weights.values())
        if abs(total - 1.0) > 0.01:
            st.caption(f"⚠️ Weights sum to {total*100:.0f}% (should be 100%)")
        else:
            st.caption(f"✓ Weights sum to {total*100:.0f}%")

    # ── Rationale ─────────────────────────────────────────────────────────────
    if result.rationale and result.preferred:
        st.markdown(f"#### Why {result.preferred.scenario_name} wins")
        for r in result.rationale:
            st.markdown(f"- {r}")

    # ── Guardrail: consistency check ──────────────────────────────────────────
    if result.preferred and decision.recommended_label:
        lcc_winner = decision.recommended_label
        score_winner = result.preferred.scenario_name
        if lcc_winner != score_winner:
            st.warning(
                f"ℹ️ **Note:** The LCC-hierarchy recommendation ({lcc_winner}) differs "
                f"from the weighted-score recommendation ({score_winner}) under the "
                f"**{result.weight_profile}** profile. "
                f"This indicates a genuine tension between cost and other criteria. "
                f"Review the weight set to reflect your utility's priorities."
            )

def _render_executive_summary(decision: ScenarioDecision, calc, inputs):
    st.subheader("📋 Executive Summary")

    # Selection basis — makes the reasoning hierarchy visible
    if hasattr(decision, "selection_basis") and decision.selection_basis:
        st.info(f"**Selection basis:** {decision.selection_basis}")

    col_rec, col_alt = st.columns([3, 2])

    with col_rec:
        st.markdown("### ✅ Recommended Option")
        if decision.recommended_tech:
            display_label = getattr(decision, "display_recommended_label",
                                    decision.recommended_label)
            st.success(f"**{display_label}**")
            st.markdown("**Why this option:**")
            for reason in decision.why_recommended:
                st.markdown(f"• {reason}")
            if decision.key_risks:
                st.markdown("**Key risks:**")
                for risk in decision.key_risks:
                    st.markdown(f"• {risk}")
        else:
            st.warning("Insufficient data for recommendation.")

    with col_alt:
        if decision.non_viable:
            st.markdown("### ⚠️ Base Case Non-Compliant Options (without intervention)")
            for nv in decision.non_viable:
                st.error(f"**{nv}** — non-compliant as base case; compliant with engineering intervention")

        # Show best alternative pathway if available
        alt_paths = getattr(decision, "alternative_pathways", [])
        if alt_paths:
            st.markdown("### 🔧 Alternative Pathway Available")
            best = alt_paths[0]
            icon = "✅" if best.achieves_compliance else "⚠️"
            st.info(
                f"{icon} **{best.tech_label}** + intervention: "
                f"${best.lcc_total_k:.0f}k/yr LCC  |  "
                f"{'Achieves compliance' if best.achieves_compliance else 'Partial compliance'}"
            )
            st.caption(f"See Alternative Pathways tab for full details.")
        elif decision.alternative_label:
            st.markdown("### 🔄 Alternative")
            st.info(f"**{decision.alternative_label}**")
            if decision.alternative_note:
                st.caption(decision.alternative_note)

    # Regulatory note — only show if there's a tension to explain
    reg_note = getattr(decision, "regulatory_note", "")
    if reg_note and any(w in reg_note.lower() for w in ["low", "moderate", "not prevent"]):
        st.markdown("---")
        st.warning(f"**Regulatory note:** {reg_note}")

    st.markdown("---")
    st.markdown(f"**Conclusion:** {decision.conclusion}")

    # Recommendation confidence
    conf = getattr(decision, "confidence", None)
    if conf:
        colour_map = {"High": "success", "Moderate": "warning", "Low": "error"}
        method = getattr(st, colour_map.get(conf.level, "info"))
        method(f"**Recommendation confidence: {conf.level}**")
        with st.expander("Confidence detail"):
            st.markdown("**Drivers:**")
            for d in conf.drivers:
                st.markdown(f"• {d}")
            if conf.caveats:
                st.markdown("**Caveats:**")
                for c in conf.caveats:
                    st.markdown(f"• {c}")

    # Strategic insight box (two-pathway framing)
    si = getattr(decision, "strategic_insight", "")
    if si:
        st.markdown("---")
        with st.expander("💡 Strategic Insight — process intensification vs robustness",
                         expanded=True):
            for para in si.split("\n\n"):
                para = para.strip()
                if para:
                    st.markdown(para)

    # Recommended approach
    ra = getattr(decision, "recommended_approach", [])
    if ra:
        st.markdown("---")
        st.markdown("**📋 Recommended Approach**")
        st.caption("No premature technology lock-in — parallel evaluation before final selection.")
        for step in ra:
            if step.startswith("  "):
                # Sub-item — indent without top-level bullet
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;→ {step.strip()}")
            elif step.endswith(":"):
                st.markdown(f"**{step}**")
            else:
                st.markdown(f"• {step}")

    # Quick metrics strip
    if len(calc) > 1:
        st.markdown("---")
        _render_metrics_strip(calc)


def _render_metrics_strip(calc):
    """Compact metrics comparison strip."""
    st.markdown("**At a glance**")
    cols = st.columns(len(calc))
    metrics = [
        ("LCC", lambda s: f"${s.cost_result.lifecycle_cost_annual/1e3:.0f}k/yr"),
        ("$/kL", lambda s: f"${s.cost_result.specific_cost_per_kl:.3f}"),
        ("Risk", lambda s: f"{s.risk_result.overall_score:.0f}/100"),
    ]
    for col, s in zip(cols, calc):
        with col:
            tc = (s.treatment_pathway.technology_sequence[0]
                  if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
            from domains.wastewater.decision_engine import _TECH_LABELS
            label = _TECH_LABELS.get(tc, tc)
            st.markdown(f"**{s.scenario_name}**")
            st.caption(label)
            st.metric("LCC", f"${s.cost_result.lifecycle_cost_annual/1e3:.0f}k/yr")
            st.metric("$/kL", f"${s.cost_result.specific_cost_per_kl:.3f}")
            st.metric("Risk", f"{s.risk_result.overall_score:.0f}/100")


# ─────────────────────────────────────────────────────────────────────────────
# TRADE-OFFS
# ─────────────────────────────────────────────────────────────────────────────

def _render_tradeoffs(decision: ScenarioDecision, calc):
    st.subheader("Trade-off Analysis")

    # Context note when two-pathway framing is active
    if "two compliant" in decision.selection_basis.lower():
        st.info(
            "Two compliant pathways identified. Trade-offs below compare the "
            "**modelled technology** against the **compliant alternative pathway** "
            "(BNR + thermal management), not against non-compliant base technologies."
        )
    else:
        st.caption(
            "How options compare across the key decision dimensions. "
            "Understanding trade-offs is the purpose of an options study."
        )

    if decision.trade_offs:
        for t in decision.trade_offs:
            st.markdown(f"• {t}")
    else:
        st.info("Run multiple scenarios to see trade-off analysis.")
        return

    # Decision matrix table
    if len(calc) < 2:
        return

    st.markdown("---")
    st.markdown("**Decision Matrix**")
    st.caption("🟢 Best in this scenario  🟡 Mid  🔴 Highest cost/risk")

    rows = []
    # Precompute ranks for colouring
    metrics_def = [
        ("Lifecycle cost (k$/yr)", lambda s: s.cost_result.lifecycle_cost_annual / 1e3, True),
        ("$/kL treated",           lambda s: s.cost_result.specific_cost_per_kl or 0, True),
        ("CAPEX ($M)",             lambda s: s.cost_result.capex_total / 1e6, True),
        ("OPEX (k$/yr)",           lambda s: s.cost_result.opex_annual / 1e3, True),
        ("Energy (kWh/ML)",        lambda s: (s.domain_specific_outputs.get("engineering_summary", {}).get("specific_energy_kwh_kl", 0) or 0) * 1000, True),
        ("Carbon (tCO₂e/yr)",      lambda s: s.carbon_result.net_tco2e_yr if s.carbon_result else 0, True),
        ("Footprint (m²)",         lambda s: float((s.domain_specific_outputs.get("technology_performance", {}).get(
            s.treatment_pathway.technology_sequence[0] if s.treatment_pathway and s.treatment_pathway.technology_sequence else "", {}
        ).get("footprint_m2", 0) or 0) if s.domain_specific_outputs else 0), True),
        ("Risk score",             lambda s: s.risk_result.overall_score if s.risk_result else 0, True),
    ]

    import pandas as pd

    matrix = {}
    for label, getter, lower_better in metrics_def:
        row = {}
        vals = {}
        for s in calc:
            try: v = getter(s)
            except Exception: v = 0
            vals[s.scenario_name] = v
        sorted_vals = sorted(vals.values(), reverse=not lower_better)
        for s in calc:
            v = vals.get(s.scenario_name, 0)
            if v == sorted_vals[0]:
                icon = "🟢"
            elif len(sorted_vals) > 2 and v == sorted_vals[-1]:
                icon = "🔴"
            else:
                icon = "🟡"
            if label.startswith("$") or "k$/yr" in label or "$M" in label or "$/kL" in label:
                row[s.scenario_name] = f"{icon} ${v:.2f}" if v < 1 else f"{icon} ${v:.0f}"
            else:
                row[s.scenario_name] = f"{icon} {v:.0f}"
        matrix[label] = row

    df = pd.DataFrame(matrix).T
    df.index.name = "Metric"
    st.dataframe(df, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY MODEL
# ─────────────────────────────────────────────────────────────────────────────

def _render_delivery(decision: ScenarioDecision):
    st.subheader("Delivery Model Suitability")
    st.caption(
        "Procurement model recommendation for each technology. "
        "Mature technologies suit competitive D&C. "
        "Novel or complex technologies require DBOM or Alliance to transfer risk appropriately."
    )

    _rating_legend()

    for name, profile in decision.profiles.items():
        d = profile.delivery
        with st.expander(f"**{name}** — {profile.tech_label}  →  Recommended: **{d.recommended_model}**",
                         expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**D&C (Design & Construct)**")
                st.markdown(f"{d.dnc.icon} **{d.dnc.value}**")
                st.caption(d.dnc_note)
            with col2:
                st.markdown(f"**DBOM**")
                st.markdown(f"{d.dbom.icon} **{d.dbom.value}**")
                st.caption(d.dbom_note)
            with col3:
                st.markdown(f"**Alliance / ECI**")
                st.markdown(f"{d.alliance.icon} **{d.alliance.value}**")
                st.caption(d.alliance_note)

            st.info(f"📋 **Procurement note:** {d.procurement_note}")


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRUCTABILITY
# ─────────────────────────────────────────────────────────────────────────────

def _render_constructability(decision: ScenarioDecision):
    st.subheader("Constructability & Brownfield Risk")
    st.caption(
        "Civil integration complexity, tie-in risk, and shutdown requirements. "
        "Critical for brownfield upgrades and constrained sites."
    )

    for name, profile in decision.profiles.items():
        c = profile.constructability
        with st.expander(
            f"**{name}** — {c.overall.icon} {c.overall.value} complexity", expanded=True
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Footprint**")
                st.caption(c.footprint_flag)
                st.markdown("**Tie-in risk**")
                st.caption(c.tie_in_risk)
                st.markdown("**Shutdown risk**")
                st.caption(c.shutdown_risk)
            with col2:
                st.markdown("**Civil complexity**")
                st.caption(c.civil_complexity)
                st.markdown("**Mechanical complexity**")
                st.caption(c.mechanical_complexity)

            st.info(f"🏗️ **Brownfield integration:** {c.brownfield_note}")


# ─────────────────────────────────────────────────────────────────────────────
# STAGING & UPGRADE PATHWAYS
# ─────────────────────────────────────────────────────────────────────────────

def _render_staging(decision: ScenarioDecision):
    st.subheader("Staging & Upgrade Pathways")
    st.caption(
        "Whether a technology can be staged to reduce upfront capital, "
        "and what upgrade paths are available as catchment grows or compliance tightens."
    )

    for name, profile in decision.profiles.items():
        s = profile.staging
        can_stage_icon = "✅" if s.can_stage else ("⚠️" if s.can_stage is None else "❌")
        with st.expander(
            f"**{name}** — {can_stage_icon} {'Can stage' if s.can_stage else ('Unknown' if s.can_stage is None else 'Full-conversion required')}",
            expanded=True
        ):
            st.caption(s.stage_note)

            st.markdown("**Delivery stages:**")
            for stage in s.stages:
                st.markdown(f"  → {stage}")

            col_up, col_down = st.columns(2)
            with col_up:
                if s.upgrade_from:
                    st.markdown("**Can upgrade FROM:**")
                    for u in s.upgrade_from:
                        st.markdown(f"• {u.replace('_', ' ').title()}")
            with col_down:
                if s.upgrade_to:
                    st.markdown("**Can upgrade TO:**")
                    for u in s.upgrade_to:
                        st.markdown(f"• {u.replace('_', ' ').title()}")

            st.info(f"🔄 **Flexibility:** {s.flexibility_note}")


# ─────────────────────────────────────────────────────────────────────────────
# OPERATIONAL COMPLEXITY
# ─────────────────────────────────────────────────────────────────────────────

def _render_ops_complexity(decision: ScenarioDecision):
    st.subheader("Operational Complexity")
    st.caption(
        "Day-to-day operational burden — distinct from technical risk. "
        "Affects resourcing, training investment, and ongoing vendor dependency."
    )

    for name, profile in decision.profiles.items():
        o = profile.ops_complexity
        with st.expander(
            f"**{name}** — {o.overall.icon} {o.overall.value}", expanded=True
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Automation requirement**")
                st.caption(o.automation_need)
                st.markdown("**Operator skill level**")
                st.caption(o.operator_skill)
                st.markdown("**Process sensitivity**")
                st.caption(o.process_sensitivity)
            with col2:
                st.markdown("**Maintenance**")
                st.caption(o.maintenance_note)
                st.markdown("**Training**")
                st.caption(o.training_note)


# ─────────────────────────────────────────────────────────────────────────────
# FAILURE MODES
# ─────────────────────────────────────────────────────────────────────────────

def _render_failure_modes(decision: ScenarioDecision):
    st.subheader("Failure Mode Awareness")
    st.caption(
        "Key failure modes planners and asset owners must plan for. "
        "Understanding failure modes is essential for commissioning plans, "
        "O&M manuals, and contingency provisions."
    )

    _consequence_colour = {
        "Low": "🟢", "Moderate": "🟡", "High": "🔴", "Severe": "🔴"
    }

    for name, profile in decision.profiles.items():
        fm = profile.failure_modes
        with st.expander(f"**{name}** — {len(fm.modes)} key failure modes", expanded=True):
            st.error(f"⚠️ **Critical:** {fm.critical_note}")

            import pandas as pd
            rows = []
            for mode in fm.modes:
                rows.append({
                    "Failure Mode":  mode.name,
                    "Likelihood":    mode.likelihood,
                    "Consequence":   mode.consequence,
                    "Mitigation":    mode.mitigation,
                })
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# REGULATORY CONFIDENCE
# ─────────────────────────────────────────────────────────────────────────────

def _render_regulatory(decision: ScenarioDecision):
    st.subheader("Regulatory Confidence")
    st.caption(
        "Regulator familiarity and approval likelihood for each technology in Australia. "
        "Novel technologies require additional engagement time — plan accordingly."
    )

    _rating_legend()

    for name, profile in decision.profiles.items():
        r = profile.regulatory
        with st.expander(
            f"**{name}** — {r.overall.icon} **{r.overall.value}** regulatory confidence",
            expanded=True
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Regulator familiarity**")
                st.caption(r.familiarity)
                st.markdown("**Approval risk**")
                st.caption(r.approval_risk)
            with col2:
                st.markdown("**AUS precedent**")
                st.caption(r.epa_precedent)
                st.markdown("**Public acceptance**")
                st.caption(r.public_acceptance)

            if r.overall in (Rating.LOW, Rating.MODERATE):
                st.warning(f"📋 {r.note}")
            else:
                st.info(f"📋 {r.note}")


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY FIT ASSESSMENT (from technology_fit.py)
# ─────────────────────────────────────────────────────────────────────────────

def _render_fit_assessment(calc, inputs):
    st.subheader("Technology Fit — Scenario Conditions")
    st.caption(
        "How well each technology suits the specific scenario conditions: "
        "temperature, COD:TKN, effluent targets, and technology maturity."
    )

    cols = st.columns(len(calc))
    for col, s in zip(cols, calc):
        tc = (s.treatment_pathway.technology_sequence[0]
              if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
        tp = (s.domain_specific_outputs.get("technology_performance", {}).get(tc, {})
              if s.domain_specific_outputs else {})

        try:
            fits = assess_all_technologies([tc], inputs, {tc: tp})
            fit = fits.get(tc)
        except Exception:
            fit = None

        with col:
            st.markdown(f"**{s.scenario_name}**")
            if fit:
                st.markdown(f"{fit.icon} **{fit.label}**")
                st.caption(fit.summary[:120])
                with st.expander("Details"):
                    for crit in fit.criteria:
                        icon = {"good": "✅", "conditional": "⚠️", "poor": "❌"}[crit.level.value]
                        st.markdown(f"{icon} **{crit.criterion}:** {crit.reason}")
            else:
                st.markdown("⚪ Not assessed")


# ─────────────────────────────────────────────────────────────────────────────
# ALTERNATIVE PATHWAYS
# ─────────────────────────────────────────────────────────────────────────────

def _render_alternative_pathways(decision: ScenarioDecision):
    """Render engineering interventions that make non-viable options viable."""
    st.subheader("Alternative Pathways — Interventions for Non-Compliant Base Cases")
    st.caption(
        "Engineering interventions that could make currently non-compliant options viable. "
        "Evaluate these pathways before committing to procurement of the recommended option."
    )

    alt_paths = getattr(decision, "alternative_pathways", [])
    if not alt_paths:
        if decision.non_viable:
            st.info(
                "Non-viable options exist in this comparison but no standard alternative "
                "pathway is defined for these technologies. Specialist input required."
            )
        else:
            st.success("All evaluated options meet compliance — no alternative pathways required.")
        return

    for p in alt_paths:
        icon = "✅" if p.achieves_compliance else "⚠️"
        with st.expander(
            f"**{p.tech_label}** + intervention — {icon} "
            f"{'Achieves compliance' if p.achieves_compliance else 'Partial compliance'}",
            expanded=True
        ):
            st.markdown(f"**Intervention:** {p.intervention}")
            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("CAPEX increment", f"+${p.capex_delta_m:.1f}M",
                          help="Additional CAPEX above base technology")
            with col2:
                st.metric("OPEX increment", f"+${p.opex_delta_k:.0f}k/yr",
                          help="Additional annual operating cost")
            with col3:
                st.metric("Total LCC (pathway)", f"${p.lcc_total_k:.0f}k/yr",
                          help="Full lifecycle cost of this intervention pathway")

            col4, col5 = st.columns(2)
            with col4:
                st.markdown(f"**Procurement:** {p.procurement}")
            with col5:
                st.markdown(f"**Regulatory:** {p.regulatory}")

            st.markdown("---")
            st.caption(p.summary)

            if p.residual_risks:
                st.markdown("**Residual risks with this pathway:**")
                for r in p.residual_risks:
                    st.markdown(f"• {r}")


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT DECISION FRAMING
# ─────────────────────────────────────────────────────────────────────────────

def _render_client_framing(decision: ScenarioDecision):
    """Two-option executive framing for board/client presentation."""
    st.subheader("Client Decision Framing")
    st.caption(
        "The client is not choosing between technologies. "
        "The client is choosing how to manage risk, capital expenditure, and delivery complexity."
    )

    cf = getattr(decision, "client_framing", None)
    if not cf:
        st.info(
            "Client decision framing is generated when multiple viable pathways exist. "
            "Run a scenario with both the recommended option and an alternative pathway "
            "to see this section populated."
        )
        return

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(f"### {cf.option_a_label}")
        st.markdown("**What you get:**")
        for b in cf.option_a_bullets:
            st.markdown(f"• {b}")
        st.markdown("**Risks you accept:**")
        for r in cf.option_a_risks:
            st.markdown(f"⚠️ {r}")

    with col_b:
        st.markdown(f"### {cf.option_b_label}")
        st.markdown("**What you get:**")
        for b in cf.option_b_bullets:
            st.markdown(f"• {b}")
        st.markdown("**Risks you accept:**")
        for r in cf.option_b_risks:
            st.markdown(f"⚠️ {r}")

    st.markdown("---")
    st.markdown("**Decision depends on:**")
    for f in cf.deciding_factors:
        st.markdown(f"• {f}")

    st.info(cf.framing_note)


# ─────────────────────────────────────────────────────────────────────────────
# FINANCIAL RISK
# ─────────────────────────────────────────────────────────────────────────────

def _render_financial_risk(decision: ScenarioDecision):
    """Capital vs operating cost exposure and long-term financial risk."""
    st.subheader("Financial Risk Perspective")
    st.caption(
        "Capital and operating cost structures carry different financial risk profiles. "
        "Understanding these is essential for long-term asset budgeting."
    )

    cf = getattr(decision, "client_framing", None)
    alt_paths = getattr(decision, "alternative_pathways", [])

    if not cf or not alt_paths:
        st.info(
            "Financial risk comparison is shown when two compliant pathways exist. "
            "Run a two-pathway scenario to see this analysis."
        )
        return

    a = alt_paths[0]
    import pandas as pd

    rows = [
        {"Risk Dimension": "CAPEX exposure",
         f"Option A: {decision.recommended_label}":
             next((b for b in cf.option_a_bullets if "CAPEX" in b), "—"),
         f"Option B: {a.tech_label} + thermal":
             next((b for b in cf.option_b_bullets if "CAPEX" in b), "—")},
        {"Risk Dimension": "OPEX character",
         f"Option A: {decision.recommended_label}":
             "Moderate — electricity + vendor DBOM fee",
         f"Option B: {a.tech_label} + thermal":
             "Higher — heating energy + methanol (ongoing)"},
        {"Risk Dimension": "Energy dependency",
         f"Option A: {decision.recommended_label}":
             "Moderate — MABR gas-side pressure",
         f"Option B: {a.tech_label} + thermal":
             "🔴 High — continuous heating critical (15°C threshold)"},
        {"Risk Dimension": "Chemical dependency",
         f"Option A: {decision.recommended_label}":
             "🟢 None — biological process only",
         f"Option B: {a.tech_label} + thermal":
             "🔴 High — methanol supply, storage, dosing"},
        {"Risk Dimension": "LCC sensitivity",
         f"Option A: {decision.recommended_label}":
             "Electricity price, vendor contract",
         f"Option B: {a.tech_label} + thermal":
             "Gas/energy price, methanol price"},
        {"Risk Dimension": "Long-term financial risk",
         f"Option A: {decision.recommended_label}":
             "Vendor dependency; technology evolution",
         f"Option B: {a.tech_label} + thermal":
             "Commodity price exposure; heating system replacement ~15–20yr"},
    ]

    df = pd.DataFrame(rows).set_index("Risk Dimension")
    st.dataframe(df, use_container_width=True)

    st.info(
        "Both options carry ±25% LCC uncertainty at concept stage. "
        "BNR+thermal OPEX is more exposed to energy and chemical price inflation. "
        "MABR LCC is more exposed to vendor contract pricing and technology evolution. "
        "A sensitivity analysis on electricity price and methanol cost is recommended "
        "at the next design stage."
    )


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _rating_legend():
    st.caption("🟢 High  🟡 Moderate  🔴 Low  ⛔ Not suited")
