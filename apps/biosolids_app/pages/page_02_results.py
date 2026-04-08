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
