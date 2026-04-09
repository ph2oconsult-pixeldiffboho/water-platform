"""
apps/biosolids_app/pages/page_02_results.py
BioPoint V1 — Pathway Rankings & Summary Results.
"""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# Ensure the engine is importable from within the platform structure
_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


def _build_inputs():
    """Reconstruct BioPointV1Inputs from session state."""
    from engine.input_schema import (
        BioPointV1Inputs, FeedstockInputsV2, AssetInputs, StrategicInputs
    )
    return BioPointV1Inputs(
        feedstock=FeedstockInputsV2(
            dry_solids_tpd=st.session_state.get("bp_ds_tpd", 10.0),
            dewatered_ds_percent=st.session_state.get("bp_feed_ds_pct", 20.0),
            volatile_solids_percent=st.session_state.get("bp_vs_pct", 70.0),
            gross_calorific_value_mj_per_kg_ds=st.session_state.get("bp_gcv", 12.0),
            sludge_type=st.session_state.get("bp_sludge_type", "blended"),
            feedstock_variability=st.session_state.get("bp_variability", "moderate"),
            pfas_present=st.session_state.get("bp_pfas", "unknown"),
        ),
        assets=AssetInputs(
            anaerobic_digestion_present=st.session_state.get("bp_ad", True),
            chp_present=st.session_state.get("bp_chp", False),
            thp_present=st.session_state.get("bp_thp", False),
            waste_heat_available_kwh_per_day=st.session_state.get("bp_waste_heat", 0.0),
            local_power_price_per_kwh=st.session_state.get("bp_electricity", 0.18),
            fuel_price_per_gj=st.session_state.get("bp_fuel", 14.0),
            disposal_cost_per_tds=st.session_state.get("bp_disposal", 180.0),
            transport_cost_per_tonne_km=st.session_state.get("bp_transport", 0.25),
            average_transport_distance_km=st.session_state.get("bp_avg_km", 50.0),
        ),
        strategic=StrategicInputs(
            optimisation_priority=st.session_state.get("bp_priority", "balanced"),
            regulatory_pressure=st.session_state.get("bp_reg", "moderate"),
            carbon_credit_value_per_tco2e=st.session_state.get("bp_carbon_price", 40.0),
            biochar_market_confidence=st.session_state.get("bp_biochar_mkt", "low"),
            land_constraint=st.session_state.get("bp_land", "low"),
            social_licence_pressure=st.session_state.get("bp_social", "low"),
            discount_rate_pct=st.session_state.get("bp_discount_rate", 7.0),
            asset_life_years=int(st.session_state.get("bp_asset_life", 25)),
        ),
    )


def _run_engine():
    """Run engine and cache result in session state."""
    from engine.biopoint_v1_runner import run_biopoint_v1
    inputs = _build_inputs()
    result = run_biopoint_v1(inputs)
    st.session_state["bp_result"] = result
    st.session_state["bp_inputs"] = inputs
    st.session_state["bp_run"] = False
    return result


def render():
    st.header("📊 Pathway Rankings")

    # Run engine if triggered or no cached result
    if st.session_state.get("bp_run") or "bp_result" not in st.session_state:
        with st.spinner("Running BioPoint V1 engine — evaluating 11 pathways across 13 layers..."):
            try:
                result = _run_engine()
            except Exception as ex:
                st.error(f"Engine error: {ex}")
                st.exception(ex)
                return
    else:
        result = st.session_state["bp_result"]

    fss = result["flowsheets"]
    dd  = result["drying_dominance"]
    its = result["its_classification"]

    # ── System alerts ─────────────────────────────────────────────────────
    if dd.system_water_constrained:
        st.error(
            f"⚠️ **WATER-REMOVAL CONSTRAINED** (Feed DS {dd.feed_ds_pct:.0f}%) — "
            "All thermal pathways blocked. Install mechanical dewatering first."
        )
    elif dd.primary_constraint_is_drying:
        n_fail = len(dd.gate_failed_pathways)
        st.warning(
            f"⚠️ **DRYING CONSTRAINED** (Feed DS {dd.feed_ds_pct:.0f}%) — "
            f"{n_fail} thermal pathways fail the drying feasibility gate."
        )

    pfas = st.session_state.get("bp_pfas", "unknown")
    if pfas == "confirmed":
        st.error("🔴 **PFAS CONFIRMED** — Only Level 3 ITS and Level 4 Incineration are acceptable. Thermal is mandatory.")
    elif pfas == "unknown":
        st.info("🟡 **PFAS unknown** — product pathway marketability is conditional. Commission characterisation before finalising any product revenue case.")

    # Engine warnings
    critical = [w for w in result["warnings"] if any(
        k in w for k in ["GATE", "PFAS", "MANDATORY", "NON-VIABLE", "DRYING"]
    )]
    if critical:
        with st.expander(f"⚠️ {len(critical)} engine flags"):
            for w in critical[:6]:
                st.warning(w[:160])

    # ── Ranked table ──────────────────────────────────────────────────────
    rows = []
    for fs in fss:
        ddr  = fs.drying_dominance
        itsc = fs.its_classification
        cc   = fs.coupling_classification
        sp   = fs.siting
        net  = fs.economics.net_annual_value
        rows.append({
            "Rank":        fs.rank,
            "Pathway":     fs.name,
            "Score":       round(fs.score, 1),
            "Net $/yr":    f"+${net:,.0f}" if net >= 0 else f"−${abs(net):,.0f}",
            "Mass red.":   f"{fs.mass_balance.total_mass_reduction_pct:.0f}%",
            "Drying gate": "✅" if (ddr and ddr.can_rank_as_preferred) else "❌",
            "PFAS (ITS)":  itsc.its_level_short if itsc else "—",
            "Coupling":    cc.coupling_tier_label[:14] if cc else "—",
            "Siting":      sp.siting_flexibility if sp else "—",
            "Status":      fs.decision_status,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Top 3 cards ───────────────────────────────────────────────────────
    st.subheader("Top pathways")
    top3 = [fs for fs in fss if fs.rank <= 3]
    cols = st.columns(3)
    for col, fs in zip(cols, top3):
        ddr = fs.drying_dominance
        net = fs.economics.net_annual_value
        itsc = fs.its_classification
        with col:
            icon = "🟢" if fs.decision_status == "Preferred" else (
                "🟡" if "conditional" in fs.decision_status.lower() else "🔴"
            )
            st.markdown(f"**{icon} #{fs.rank} {fs.name}**")
            st.metric("Score", f"{fs.score:.1f}")
            st.metric("Net $/yr",
                f"+${net:,.0f}" if net >= 0 else f"−${abs(net):,.0f}")
            st.metric("Mass reduction",
                f"{fs.mass_balance.total_mass_reduction_pct:.0f}%")
            if ddr:
                st.caption("Drying gate: " + ("✅ PASS" if ddr.can_rank_as_preferred else "❌ FAIL"))
            if itsc:
                st.caption(f"PFAS: {itsc.pfas_status}")

    # ── Inevitability ─────────────────────────────────────────────────────
    inv = result["inevitability"]
    st.subheader("Three-state strategy")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**PREFERRED (now)**")
        st.success(inv.best_current.flowsheet_name if inv.best_current else "None identified")
    with c2:
        st.markdown("**CONDITIONAL**")
        st.info(inv.best_future.flowsheet_name if inv.best_future else "None identified")
    with c3:
        st.markdown("**INEVITABLE fallback**")
        st.warning(inv.inevitable_fallback.flowsheet_name if inv.inevitable_fallback else "None")

    if inv.outcome_change_triggers:
        with st.expander("Investment triggers"):
            for t in inv.outcome_change_triggers[:5]:
                st.markdown(f"• {t[:130]}")

    # ── Economics table ───────────────────────────────────────────────────
    with st.expander("Full economics — all pathways"):
        econ_rows = []
        for fs in fss:
            ec = fs.economics
            econ_rows.append({
                "Pathway": fs.name,
                "CAPEX ($M)": f"{ec.capex_total_m_dollars:.1f}",
                "Ann. CAPEX ($/yr)": f"{ec.annualised_capex_per_year:,.0f}",
                "OPEX ($/yr)": f"{ec.total_opex_per_year:,.0f}",
                "Avoided ($/yr)": f"{ec.total_avoided_per_year:,.0f}",
                "Net ($/yr)": (
                    f"+${ec.net_annual_value:,.0f}" if ec.net_annual_value >= 0
                    else f"−${abs(ec.net_annual_value):,.0f}"
                ),
            })
        st.dataframe(pd.DataFrame(econ_rows), use_container_width=True, hide_index=True)

    # ── Decision Intelligence Layer ───────────────────────────────────────
    _render_biosolids_dil(result)


def _render_biosolids_dil(result: dict) -> None:
    """Render the BioPoint Decision Intelligence Layer expander."""
    try:
        from engine.dil_biosolids import build_biosolids_dil

        inputs = st.session_state.get("bp_inputs")
        if inputs is None:
            return  # inputs not yet cached — engine hasn't run

        di = build_biosolids_dil(inputs, result)

        _readiness_icon = {
            "Ready to Proceed":        "✅",
            "Proceed with Conditions": "⚠️",
            "Not Decision-Ready":      "🔴",
        }
        _crit_icon = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}
        _conf_icon = {"High": "🟢", "Acceptable": "🟡", "Low": "🔴", "Very Low": "🔴"}
        _voi_icon  = {"High": "🔴", "Moderate": "🟡", "Low": "🟢"}

        r_icon = _readiness_icon.get(di.readiness.status, "⚪")
        c_icon = _crit_icon.get(di.criticality.level, "⚪")

        with st.expander(
            f"🧠 Decision Intelligence — {r_icon} {di.readiness.status} "
            f"| Criticality: {c_icon} {di.criticality.level}",
            expanded=False,
        ):
            st.markdown("#### Decision Context")
            st.markdown(di.decision_context)

            tabs = st.tabs([
                "⚖️ Criticality",
                "📊 Data Confidence",
                "💡 Value of Information",
                "🤝 Risk Ownership",
                "🎯 Decision Boundary",
                "✅ Decision Readiness",
            ])

            # Tab 1: Criticality
            with tabs[0]:
                st.markdown("#### Decision Criticality")
                st.metric("Criticality", f"{c_icon} {di.criticality.level}")
                st.markdown("---")
                for label, text in [
                    ("Compliance",    di.criticality.compliance_consequence),
                    ("Service",       di.criticality.service_consequence),
                    ("Financial",     di.criticality.financial_consequence),
                    ("Reputational",  di.criticality.reputational_consequence),
                    ("Asset (WoL)",   di.criticality.asset_consequence),
                    ("Reversibility", di.criticality.reversibility),
                    ("Regulatory",    di.criticality.regulatory_exposure),
                ]:
                    st.markdown(f"**{label}:** {text}")
                st.info(di.criticality.classification_rationale)

            # Tab 2: Data Confidence
            with tabs[1]:
                st.markdown("#### Data Confidence Assessment")
                if di.data_confidence.high_volume_low_confidence:
                    st.warning(
                        "⚠️ **High-volume, low-confidence data:** "
                        + "; ".join(di.data_confidence.high_volume_low_confidence)
                        + ". More data of the same type will not resolve this."
                    )
                for d in di.data_confidence.dimensions:
                    icon = _conf_icon.get(d.confidence, "⚪")
                    with st.expander(
                        f"{icon} **{d.variable}** — {d.confidence} confidence",
                        expanded=False,
                    ):
                        col1, col2 = st.columns([1, 2])
                        with col1:
                            st.caption(f"**Data volume:** {d.volume.title()}")
                        with col2:
                            st.caption(f"**Issue:** {d.issue}")
                        st.caption(f"**Decision implication:** {d.implication}")
                st.markdown("---")
                st.info(di.data_confidence.summary)
                if di.data_confidence.critical_gaps:
                    st.warning(
                        "**Critical gaps:** "
                        + " · ".join(di.data_confidence.critical_gaps)
                    )

            # Tab 3: Value of Information
            with tabs[2]:
                st.markdown("#### Value of Information")
                st.caption(
                    "For each uncertainty, whether more data would change the decision. "
                    "Low VOI = proceed. High VOI = investigate before commitment."
                )
                for d in di.voi.dimensions:
                    icon = _voi_icon.get(d.voi_classification, "⚪")
                    with st.expander(
                        f"{icon} **{d.uncertainty}** — {d.voi_classification} VOI",
                        expanded=(d.voi_classification == "High"),
                    ):
                        col1, col2, col3 = st.columns(3)
                        col1.caption(f"Changes **pathway selection**: {'Yes ⚠️' if d.changes_pathway_selection else 'No'}")
                        col2.caption(f"Changes **sizing**: {'Yes' if d.changes_sizing else 'No'}")
                        col3.caption(f"Changes **compliance**: {'Yes' if d.changes_compliance_confidence else 'No'}")
                        col1.caption(f"Changes **product viability**: {'Yes ⚠️' if d.changes_product_viability else 'No'}")
                        col2.caption(f"Changes **lifecycle cost**: {'Yes' if d.changes_lifecycle_cost else 'No'}")
                        col3.caption(f"Changes **risk materially**: {'Yes ⚠️' if d.changes_risk_materially else 'No'}")
                        st.markdown(f"**Rationale:** {d.rationale}")
                st.markdown("---")
                if di.voi.high_voi_items:
                    st.warning(
                        f"**High VOI:** {'; '.join(di.voi.high_voi_items)}. "
                        "Resolve before pathway commitment."
                    )
                if di.voi.low_voi_items:
                    st.success(
                        f"**Low VOI — proceed without:** {'; '.join(di.voi.low_voi_items)}."
                    )
                st.info(di.voi.investigation_recommendation)

            # Tab 4: Risk Ownership
            with tabs[3]:
                st.markdown("#### Risk Ownership Mapping")
                st.caption("No delivery model removes the utility's accountability.")
                for d in di.risk_ownership.dimensions:
                    with st.expander(
                        f"**{d.risk_category}** — Primary owner: {d.primary_owner}",
                        expanded=False,
                    ):
                        if d.shared_with:
                            st.caption(f"**Shared with:** {', '.join(d.shared_with)}")
                        st.markdown(f"**Utility's irreducible exposure:** {d.utility_exposure}")
                        st.caption(f"*{d.note}*")
                st.markdown("---")
                st.error(f"⚠️ **Accountability:** {di.risk_ownership.utility_accountability_statement}")
                st.warning(f"**Residual risk:** {di.risk_ownership.residual_risk_statement}")

            # Tab 5: Decision Boundary
            with tabs[4]:
                st.markdown("#### Decision Boundary")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**Acceptable performance range**")
                    for item in di.decision_boundary.acceptable_performance_range:
                        st.markdown(f"• {item}")
                    st.markdown("**Acceptable uncertainty**")
                    for item in di.decision_boundary.acceptable_uncertainty:
                        st.markdown(f"• {item}")
                    st.markdown(f"**Resilience margin:** {di.decision_boundary.resilience_margin}")
                with col_b:
                    st.markdown("**Monitoring requirements**")
                    for item in di.decision_boundary.monitoring_requirements:
                        st.markdown(f"• {item}")
                    st.markdown("**Intervention triggers**")
                    for item in di.decision_boundary.intervention_triggers:
                        st.markdown(f"🔔 {item}")
                st.markdown("---")
                st.markdown("**Critical assumptions**")
                for item in di.decision_boundary.critical_assumptions:
                    st.markdown(f"⚡ {item}")
                st.info(f"**Fallback position:** {di.decision_boundary.fallback_position}")

            # Tab 6: Decision Readiness
            with tabs[5]:
                st.markdown("#### Decision Readiness")
                status = di.readiness.status
                if status == "Ready to Proceed":
                    st.success(f"✅ **{status}**")
                elif status == "Proceed with Conditions":
                    st.warning(f"⚠️ **{status}**")
                else:
                    st.error(f"🔴 **{status}**")
                st.markdown(f"**Basis:** {di.readiness.basis}")
                if di.readiness.conditions:
                    st.markdown("**Conditions:**")
                    for c in di.readiness.conditions:
                        st.markdown(f"• {c}")
                if di.readiness.critical_assumption_at_risk:
                    st.error(f"⚡ **Critical assumption at risk:** {di.readiness.critical_assumption_at_risk}")
                st.markdown("---")
                st.markdown(f"**Strategic implication:** {di.readiness.strategic_implication}")

            st.markdown("---")
            st.caption(f"*{di.closing_statement}*")

    except Exception as e:
        st.warning(f"Decision Intelligence Layer unavailable: {e}")
