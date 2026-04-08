"""
apps/biosolids_app/pages/page_01_inputs.py
BioPoint V1 — Inputs page.
"""
import streamlit as st


def render():
    st.header("⚙️ System Inputs")
    st.caption("Define feedstock, site, and economic parameters for the analysis.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Feedstock")
        st.session_state["bp_ds_tpd"] = st.number_input(
            "Dry solids (tDS/day)", 1.0, 500.0,
            st.session_state.get("bp_ds_tpd", 10.0), step=1.0,
            help="Total dry solids produced per day"
        )
        st.session_state["bp_feed_ds_pct"] = st.number_input(
            "Feed DS% (post-digestion)", 3.0, 50.0,
            st.session_state.get("bp_feed_ds_pct", 20.0), step=0.5,
            help="Dry solids concentration entering the biosolids pathway. "
                 "3% = digested sludge direct. 20-22% = after centrifuge. 30-38% = after THP+filter press."
        )
        st.session_state["bp_vs_pct"] = st.number_input(
            "Volatile solids (% of DS)", 45.0, 85.0,
            st.session_state.get("bp_vs_pct", 70.0), step=1.0
        )
        st.session_state["bp_gcv"] = st.number_input(
            "GCV (MJ/kgDS)", 6.0, 18.0,
            st.session_state.get("bp_gcv", 12.0), step=0.5,
            help="Gross calorific value. Digested sludge: 9-12. Raw sludge: 13-16."
        )
        st.session_state["bp_sludge_type"] = st.selectbox(
            "Sludge type",
            ["blended", "digested", "primary", "secondary", "thp_digested"],
            index=["blended","digested","primary","secondary","thp_digested"].index(
                st.session_state.get("bp_sludge_type", "blended"))
        )
        st.session_state["bp_variability"] = st.selectbox(
            "Feed variability",
            ["low", "moderate", "high"],
            index=["low","moderate","high"].index(
                st.session_state.get("bp_variability", "moderate"))
        )
        st.session_state["bp_pfas"] = st.selectbox(
            "PFAS status",
            ["unknown", "negative", "confirmed"],
            index=["unknown","negative","confirmed"].index(
                st.session_state.get("bp_pfas", "unknown")),
            help="If confirmed: incineration becomes mandatory; biochar routes close."
        )
        if st.session_state["bp_pfas"] == "confirmed":
            st.error("⚠️ PFAS confirmed — only ITS (Level 3) and Incineration (Level 4) pathways are acceptable.")
        elif st.session_state["bp_pfas"] == "unknown":
            st.warning("🟡 PFAS unknown — product revenue business case is conditional.")

    with col2:
        st.subheader("Site Infrastructure")
        st.session_state["bp_ad"] = st.checkbox(
            "Anaerobic digestion present",
            st.session_state.get("bp_ad", True)
        )
        st.session_state["bp_chp"] = st.checkbox(
            "CHP present",
            st.session_state.get("bp_chp", False)
        )
        st.session_state["bp_thp"] = st.checkbox(
            "THP present",
            st.session_state.get("bp_thp", False)
        )
        st.session_state["bp_waste_heat"] = st.number_input(
            "Waste heat available (kWh/day)", 0.0, 200000.0,
            st.session_state.get("bp_waste_heat", 0.0), step=1000.0,
            help="Confirmed recoverable waste heat for drying (CHP jacket, process, etc.)"
        )

        st.subheader("Strategy")
        st.session_state["bp_priority"] = st.selectbox(
            "Optimisation priority",
            ["balanced", "highest_resilience", "cost_minimisation", "carbon_optimised"],
            index=["balanced","highest_resilience","cost_minimisation","carbon_optimised"].index(
                st.session_state.get("bp_priority", "balanced"))
        )
        st.session_state["bp_reg"] = st.selectbox(
            "Regulatory pressure",
            ["low", "moderate", "high"],
            index=["low","moderate","high"].index(
                st.session_state.get("bp_reg", "moderate"))
        )
        st.session_state["bp_land"] = st.selectbox(
            "Land constraint",
            ["low", "moderate", "high"],
            index=["low","moderate","high"].index(
                st.session_state.get("bp_land", "low"))
        )
        st.session_state["bp_social"] = st.selectbox(
            "Social licence / community sensitivity",
            ["low", "moderate", "high"],
            index=["low","moderate","high"].index(
                st.session_state.get("bp_social", "low"))
        )
        st.session_state["bp_biochar_mkt"] = st.selectbox(
            "Biochar market confidence",
            ["low", "moderate", "high"],
            index=["low","moderate","high"].index(
                st.session_state.get("bp_biochar_mkt", "low")),
            help="Confidence in confirmed biochar offtake at market price."
        )

    with col3:
        st.subheader("Economics")
        st.session_state["bp_disposal"] = st.number_input(
            "Disposal cost ($/tDS)", 50.0, 600.0,
            st.session_state.get("bp_disposal", 180.0), step=10.0
        )
        st.session_state["bp_electricity"] = st.number_input(
            "Electricity ($/kWh)", 0.10, 0.50,
            st.session_state.get("bp_electricity", 0.18), step=0.01,
            format="%.2f"
        )
        st.session_state["bp_fuel"] = st.number_input(
            "Fuel price ($/GJ)", 8.0, 30.0,
            st.session_state.get("bp_fuel", 14.0), step=1.0
        )
        st.session_state["bp_transport"] = st.number_input(
            "Transport ($/t·km)", 0.10, 0.60,
            st.session_state.get("bp_transport", 0.25), step=0.05,
            format="%.2f"
        )
        st.session_state["bp_avg_km"] = st.number_input(
            "Avg transport distance (km)", 5.0, 300.0,
            st.session_state.get("bp_avg_km", 50.0), step=5.0
        )
        st.session_state["bp_carbon_price"] = st.number_input(
            "Carbon price ($/tCO₂e)", 0.0, 300.0,
            st.session_state.get("bp_carbon_price", 40.0), step=5.0
        )
        st.session_state["bp_discount_rate"] = st.number_input(
            "Discount rate (%)", 3.0, 15.0,
            st.session_state.get("bp_discount_rate", 7.0), step=0.5
        )
        st.session_state["bp_asset_life"] = st.number_input(
            "Asset life (years)", 10, 40,
            int(st.session_state.get("bp_asset_life", 25)), step=5
        )

    st.divider()

    # DS% context note
    feed_ds = st.session_state["bp_feed_ds_pct"]
    if feed_ds < 20:
        st.error(
            f"⚠️ **WATER-REMOVAL CONSTRAINED** — At {feed_ds:.0f}% DS, all thermal pathways are "
            "physically blocked. Drying energy would be >200% of feedstock energy. "
            "Install mechanical dewatering to ≥20% DS before evaluating thermal options."
        )
    elif feed_ds < 30:
        st.warning(
            f"🟡 Feed DS {feed_ds:.0f}% — thermal pathways are drying-constrained. "
            "Incineration passes the feasibility gate at ~32% DS. "
            "Pyrolysis requires ~42-48% DS for energy neutrality."
        )
    else:
        st.success(
            f"✅ Feed DS {feed_ds:.0f}% — incineration is within the viable range. "
            "Run the analysis to see the full drying gate assessment."
        )

    st.markdown("---")
    if st.button("▶ Run BioPoint Analysis", type="primary", use_container_width=False):
        st.session_state["bp_run"] = True
        st.session_state["page"] = "02_results"
        st.rerun()
