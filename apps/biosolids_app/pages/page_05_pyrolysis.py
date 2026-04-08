"""
apps/biosolids_app/pages/page_05_pyrolysis.py
BioPoint V1 — Pyrolysis Operating Envelope & Trade-Off Curve.
"""
import streamlit as st
import pandas as pd


def _get_result():
    if "bp_result" not in st.session_state:
        st.warning("Run the analysis first (Inputs page).")
        return None
    return st.session_state["bp_result"]


def render():
    st.header("📈 Pyrolysis Operating Envelope")

    result = _get_result()
    if not result:
        return

    pe = result.get("pyrolysis_envelope")
    pt = result.get("pyrolysis_tradeoff")

    if not pe or not pt:
        st.info("Pyrolysis envelope not available — check that a pyrolysis flowsheet was evaluated.")
        return

    # ── Board message ─────────────────────────────────────────────────────
    st.markdown(f"> **{pt.board_message}**")

    # ── Recommendation ────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Recommended mode", pt.recommended_mode)
    with c2:
        st.metric("Recommended temp", f"{pt.recommended_temp:.0f}°C")
    with c3:
        st.metric("Total value at rec. temp", f"${pt.recommended_value_per_tds:.0f}/tDS")

    if pt.recommended_mode == "COMPLIANCE-LED":
        st.error("PFAS confirmed — compliance drives the operating mode. PFAS destruction takes priority.")
    st.caption(pt.recommendation_rationale[:300])

    # ── Value vs temperature chart ────────────────────────────────────────
    st.subheader("Value vs temperature ($/tDS)")

    chart_data = pd.DataFrame({
        "Temperature (°C)": pt.chart_temps,
        "Total value": pt.chart_total_value,
        "Energy value": pt.chart_energy_value,
        "Biochar value": pt.chart_biochar_value,
        "Carbon credits": pt.chart_carbon_value,
    }).set_index("Temperature (°C)")

    st.line_chart(chart_data, height=300)

    # ── Optima ────────────────────────────────────────────────────────────
    o1, o2, o3 = st.columns(3)
    with o1:
        st.metric("Optimal for energy", f"{pt.optimal_energy_temp:.0f}°C",
                  f"${pt.optimal_energy_value:.0f}/tDS")
    with o2:
        st.metric("Optimal for product", f"{pt.optimal_product_temp:.0f}°C",
                  f"${pt.optimal_product_value:.0f}/tDS")
    with o3:
        st.metric("Optimal balanced", f"{pt.optimal_balanced_temp:.0f}°C",
                  f"${pt.optimal_balanced_value:.0f}/tDS")

    # ── Three-mode comparison ─────────────────────────────────────────────
    st.subheader("Three operating modes — side by side")

    mode_rows = []
    for lbl, row in pt.comparison_table.items():
        mode_rows.append({
            "Mode": lbl,
            "Temp °C": row["temp_c"],
            "Biochar yield %": f"{row['biochar_yield_pct']:.1f}%",
            "Biochar CV MJ/kg": row["biochar_cv_mj_kg"],
            "Fixed C%": f"{row['fixed_carbon_pct']:.0f}%",
            "R50": row["stability_r50"],
            "N ret.": f"{row['N_retention_pct']:.0f}%",
            "PFAS conf.": row["pfas_confidence"],
            "Energy $/tDS": f"${row['energy_val_per_tds']:.1f}",
            "Biochar $/tDS": f"${row['biochar_val_per_tds']:.1f}",
            "Credits $/tDS": f"${row['carbon_val_per_tds']:.1f}",
            "Total $/tDS": f"${row['total_val_per_tds']:.1f}",
            "Best for": row["best_for"][:40],
        })
    st.dataframe(pd.DataFrame(mode_rows), use_container_width=True, hide_index=True)

    # ── Yield vs energy trade-off ─────────────────────────────────────────
    st.subheader("Yield vs energy trade-off")
    with st.expander("Trade-off narrative (all three modes)"):
        st.text(pe.yield_energy_tradeoff_narrative)

    # ── Operating envelope curve ──────────────────────────────────────────
    st.subheader("Operating envelope — physical properties across 300–800°C")

    curve_rows = []
    for pt_c in pe.curve:
        curve_rows.append({
            "Temp °C": pt_c.temp_c,
            "Yield %DS": pt_c.biochar_yield_pct,
            "Fixed C%": pt_c.fixed_carbon_pct,
            "R50": pt_c.carbon_stability_r50,
            "N ret %": pt_c.N_retention_pct,
            "Pyrogas frac": round(pt_c.pyrogas_energy_fraction * 100, 1),
            "PFAS": pt_c.pfas_confidence,
        })
    curve_df = pd.DataFrame(curve_rows)

    st.line_chart(
        curve_df.set_index("Temp °C")[["Yield %DS", "Fixed C%", "N ret %"]],
        height=260
    )
    st.caption("Biochar yield decreases / Fixed carbon and stability increase with temperature")

    with st.expander("Full envelope data table"):
        st.dataframe(curve_df, use_container_width=True, hide_index=True)
