"""
apps/biosolids_app/pages/page_09_compare.py
BioPoint V1 — MAD Configuration Comparison.

Compares up to four digestion configurations (Base Case, Recuperative Thickening,
Pre-digestion THP, SolidStream) against eight project drivers with user-defined
weightings. Outputs heatmap, ranked recommendation, and downloadable report.

ph2o Consulting — BioPoint V1 — v25B02
"""
import sys
from pathlib import Path
import streamlit as st
import pandas as pd

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from engine.mad_compare import (
    ComparisonSiteInputs, run_comparison,
    DRIVER_LABELS, DRIVER_DESCRIPTIONS, DRIVER_IDS, DEFAULT_WEIGHTS,
    CONFIG_LABELS_SHORT, ALL_CONFIGS,
)
from engine.mad_compare_report import generate_comparison_report


# ── Heatmap colours ────────────────────────────────────────────────────────
HEAT_COLOURS = {
    4: "#1b5e20",   # dark green
    3: "#558b2f",   # mid green
    2: "#f57f17",   # amber
    1: "#b71c1c",   # dark red
}
HEAT_TEXT = {4: "white", 3: "white", 2: "black", 1: "white"}


def _heat_cell(score: int, value_str: str = "") -> str:
    bg   = HEAT_COLOURS.get(score, "#eceff1")
    text = HEAT_TEXT.get(score, "black")
    label = {4:"★ Best", 3:"Good", 2:"Fair", 1:"Worst"}.get(score, str(score))
    return (
        f'<div style="background:{bg};color:{text};text-align:center;'
        f'padding:8px 4px;border-radius:4px;font-size:12px;font-weight:bold;">'
        f'{label}<br/><span style="font-size:10px;opacity:0.85;">{value_str}</span>'
        f'</div>'
    )


def render():
    st.header("⚖️ MAD Configuration Comparison")
    st.caption(
        "Compare up to four digestion configurations against your project drivers. "
        "Configure site inputs, set driver priorities, select configurations to compare, "
        "then run the assessment."
    )

    # ── SITE INPUTS ────────────────────────────────────────────────────────
    with st.expander("🏭 Site inputs", expanded=True):
        st.caption("Shared across all configurations. Base case uses these directly.")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Feed — Primary Sludge**")
            ps_ds  = st.number_input("PS dry solids (tDS/day)", 0.5, 500.0,
                st.session_state.get("cmp_ps_ds", 6.0), step=0.5, key="cmp_ps_ds")
            ps_ts  = st.number_input("PS feed TS% (base case)", 2.0, 12.0,
                st.session_state.get("cmp_ps_ts", 4.0), step=0.5, key="cmp_ps_ts")
            ps_vs  = st.number_input("PS volatile solids (% DS)", 50.0, 90.0,
                st.session_state.get("cmp_ps_vs", 75.0), step=1.0, key="cmp_ps_vs")
            ps_n   = st.number_input("PS nitrogen (% DS)", 1.0, 8.0,
                st.session_state.get("cmp_ps_n", 3.0), step=0.1, key="cmp_ps_n")

            st.markdown("**Feed — WAS**")
            was_ds = st.number_input("WAS dry solids (tDS/day)", 0.5, 500.0,
                st.session_state.get("cmp_was_ds", 4.0), step=0.5, key="cmp_was_ds")
            was_ts = st.number_input("WAS feed TS% (base case)", 2.0, 12.0,
                st.session_state.get("cmp_was_ts", 4.0), step=0.5, key="cmp_was_ts")
            was_vs = st.number_input("WAS volatile solids (% DS)", 45.0, 85.0,
                st.session_state.get("cmp_was_vs", 70.0), step=1.0, key="cmp_was_vs")
            was_n  = st.number_input("WAS nitrogen (% DS)", 4.0, 15.0,
                st.session_state.get("cmp_was_n", 8.5), step=0.1, key="cmp_was_n")

        with c2:
            st.markdown("**Digester geometry**")
            ps_vol  = st.number_input("PS digester volume (m³)", 100.0, 200000.0,
                st.session_state.get("cmp_ps_vol", 3000.0), step=100.0, key="cmp_ps_vol")
            was_vol = st.number_input("WAS digester volume (m³)", 100.0, 200000.0,
                st.session_state.get("cmp_was_vol", 1200.0), step=100.0, key="cmp_was_vol")

            st.markdown("**Recuperative thickening (when selected)**")
            recup_ps_ts  = st.number_input("Recup PS TS% target", 4.0, 12.0,
                st.session_state.get("cmp_recup_ps_ts", 6.0), step=0.5,
                key="cmp_recup_ps_ts",
                help="Achievable feed TS% after centrifuge recirculation upgrade")
            recup_was_ts = st.number_input("Recup WAS TS% target", 3.0, 10.0,
                st.session_state.get("cmp_recup_was_ts", 5.5), step=0.5,
                key="cmp_recup_was_ts")

            st.markdown("**Plant context**")
            plant_tkn = st.number_input("Plant total TKN (kg N/day)", 50.0, 10000.0,
                st.session_state.get("cmp_plant_tkn", 500.0), step=50.0,
                key="cmp_plant_tkn",
                help="Used to calculate centrate NH₄ return as % of plant TKN")

        with c3:
            st.markdown("**Economics**")
            elec_buy  = st.number_input("Electricity buy ($/kWh)", 0.05, 0.50,
                st.session_state.get("cmp_elec_buy", 0.18), step=0.01,
                format="%.2f", key="cmp_elec_buy")
            elec_sell = st.number_input("Electricity sell ($/kWh)", 0.05, 0.30,
                st.session_state.get("cmp_elec_sell", 0.10), step=0.01,
                format="%.2f", key="cmp_elec_sell")
            disposal  = st.number_input("Disposal cost ($/wet tonne)", 20.0, 400.0,
                st.session_state.get("cmp_disposal", 80.0), step=5.0,
                key="cmp_disposal")
            transport_km = st.number_input("Transport distance (km)", 5.0, 300.0,
                st.session_state.get("cmp_transport_km", 50.0), step=5.0,
                key="cmp_transport_km")
            polymer_cost = st.number_input("Polymer cost ($/kg)", 1.0, 10.0,
                st.session_state.get("cmp_polymer_cost", 3.50), step=0.25,
                format="%.2f", key="cmp_polymer_cost")

            st.markdown("**GHG**")
            grid_i = st.selectbox("Grid state",
                ["QLD (0.72)", "NSW (0.55)", "VIC (0.60)", "SA (0.25)",
                 "WA (0.65)", "TAS (0.08)", "NZ (0.12)", "Custom"],
                index=2, key="cmp_grid_state")
            if grid_i == "Custom":
                grid_intensity = st.number_input(
                    "Custom grid intensity (kgCO₂e/kWh)", 0.0, 1.5,
                    st.session_state.get("cmp_grid_custom", 0.55),
                    step=0.01, format="%.3f", key="cmp_grid_custom")
            else:
                grid_intensity = float(grid_i.split("(")[1].rstrip(")"))

    # ── CONFIGURATIONS TO COMPARE ──────────────────────────────────────────
    with st.expander("🔀 Configurations to compare", expanded=True):
        st.caption("Select which configurations to include in the comparison.")
        cc1, cc2, cc3, cc4 = st.columns(4)
        with cc1:
            inc_base = st.checkbox("Base case\n(Conventional AD)",
                value=True, key="cmp_inc_base")
            st.caption("No THP, no recup upgrade. Establishes the performance baseline.")
        with cc2:
            inc_recup = st.checkbox("Recuperative\nThickening",
                value=True, key="cmp_inc_recup")
            st.caption("Higher feed TS% via centrifuge recirculation. Moderate CAPEX.")
        with cc3:
            inc_prethp = st.checkbox("Pre-digestion\nTHP",
                value=True, key="cmp_inc_prethp")
            st.caption("THP before digesters. Highest biogas uplift, Class A biosolids.")
        with cc4:
            inc_ss = st.checkbox("SolidStream\n(Post-THP)",
                value=True, key="cmp_inc_ss")
            st.caption("THP after existing digesters. Best dewatering, Class A, retrofit.")

    # ── DRIVER WEIGHTINGS ──────────────────────────────────────────────────
    with st.expander("🎯 Project driver weightings", expanded=True):
        st.caption(
            "Set the importance of each driver for this project. "
            "5 = critical project driver. 1 = minor consideration. "
            "Weights determine the heatmap total score."
        )
        w_cols = st.columns(4)
        weights = {}
        for i, d in enumerate(DRIVER_IDS):
            with w_cols[i % 4]:
                weights[d] = st.slider(
                    DRIVER_LABELS[d],
                    1, 5,
                    st.session_state.get(f"cmp_w_{d}", DEFAULT_WEIGHTS.get(d, 3)),
                    key=f"cmp_w_{d}",
                    help=DRIVER_DESCRIPTIONS[d],
                )

    # ── REPORT METADATA ────────────────────────────────────────────────────
    with st.expander("📄 Report settings", expanded=False):
        rc1, rc2 = st.columns(2)
        with rc1:
            cmp_project = st.text_input("Project name",
                st.session_state.get("cmp_project", "BioPoint Analysis"),
                key="cmp_project")
        with rc2:
            cmp_prepby = st.text_input("Prepared by",
                st.session_state.get("cmp_prepby", "ph2o Consulting"),
                key="cmp_prepby")

    # ── RUN ────────────────────────────────────────────────────────────────
    run = st.button("▶ Run Comparison", type="primary")

    if not run and "cmp_result" not in st.session_state:
        st.info(
            "Configure site inputs and driver weightings above, then click "
            "**▶ Run Comparison**."
        )
        return

    if run:
        configs_to_run = []
        if st.session_state.get("cmp_inc_base",   True):  configs_to_run.append("base")
        if st.session_state.get("cmp_inc_recup",  True):  configs_to_run.append("recup")
        if st.session_state.get("cmp_inc_prethp", True):  configs_to_run.append("pre_thp")
        if st.session_state.get("cmp_inc_ss",     True):  configs_to_run.append("solidstream")

        if not configs_to_run:
            st.error("Select at least one configuration to compare.")
            return

        site = ComparisonSiteInputs(
            ps_ds_tpd=ps_ds, was_ds_tpd=was_ds,
            ps_ts_pct=ps_ts, was_ts_pct=was_ts,
            ps_vs_pct=ps_vs, was_vs_pct=was_vs,
            ps_n_pct=ps_n,   was_n_pct=was_n,
            ps_volume_m3=ps_vol, was_volume_m3=was_vol,
            recup_ps_ts_pct=recup_ps_ts, recup_was_ts_pct=recup_was_ts,
            electricity_buy_per_kwh=elec_buy,
            electricity_sell_per_kwh=elec_sell,
            disposal_cost_per_t_wet=disposal,
            transport_km=transport_km,
            polymer_cost_per_kg=polymer_cost,
            grid_intensity_kg_co2e_per_kwh=grid_intensity,
            plant_tkn_kg_per_d=plant_tkn,
            project_name=st.session_state.get("cmp_project", "BioPoint Analysis"),
            prepared_by=st.session_state.get("cmp_prepby", "ph2o Consulting"),
        )

        with st.spinner("Running comparison across configurations..."):
            result = run_comparison(site, weights, configs_to_run)
            st.session_state["cmp_result"] = result
            st.session_state.pop("cmp_report_pdf", None)

    result = st.session_state.get("cmp_result")
    if not result:
        return

    included = result.included_ids

    # ── WINNER BANNER ──────────────────────────────────────────────────────
    st.divider()
    if result.winner_id:
        wc = result.configs[result.winner_id]
        st.success(
            f"★ **Recommended: {result.winner_label}** "
            f"(weighted score {wc.weighted_score:.1f}/25)  \n"
            + result.executive_summary
        )

    # ── HEATMAP ────────────────────────────────────────────────────────────
    st.subheader("Driver heatmap")
    st.caption(
        "🟢 Best performance among compared configurations. "
        "🔴 Worst. Scores are relative — adding/removing configurations changes rankings."
    )

    # Build heatmap as HTML table
    configs = [result.configs[k] for k in included]
    n = len(configs)

    # Header
    header_cells = '<th style="text-align:left;padding:8px;background:#1a3a5c;color:white;min-width:140px;">Driver (weight)</th>'
    for cr in configs:
        star = "★ " if cr.config_id == result.winner_id else ""
        header_cells += (
            f'<th style="text-align:center;padding:8px;background:#1a3a5c;'
            f'color:white;min-width:110px;">{star}{cr.config_label}</th>'
        )

    rows_html = ""
    for d in DRIVER_IDS:
        w = result.driver_weights.get(d, 1)
        bar = "■" * w + "□" * (5 - w)
        row_html = (
            f'<td style="padding:6px 8px;background:#e8f4f8;'
            f'font-weight:bold;font-size:12px;">'
            f'{DRIVER_LABELS[d]}<br/>'
            f'<span style="font-weight:normal;font-size:10px;color:#546e7a;">'
            f'Weight {w}/5 {bar}</span></td>'
        )
        for cr in configs:
            sc  = cr.driver_scores.get(d, 1)
            raw = cr.driver_raw.get(d, 0)

            # Format raw value for display
            raw_fmt = {
                "energy":      f"{raw:,.0f} m³/d",
                "biosolids":   "Class A" if raw >= 4 else "Class B",
                "dewatering":  f"{raw:.0f}% DS",
                "return_load": f"{raw:.0f} kg/d",
                "carbon":      f"{raw:,.0f} kg/d",
                "opex":        f"${raw/1000:,.0f}k/yr",
                "capex":       f"${raw:.1f}M",
                "headroom":    f"{raw:.1f}d",
            }.get(d, f"{raw:.1f}")

            row_html += (
                f'<td style="padding:4px;">'
                + _heat_cell(sc, raw_fmt)
                + '</td>'
            )
        rows_html += f"<tr>{row_html}</tr>"

    # Weighted total row
    wt_row = (
        '<td style="padding:6px 8px;background:#1a3a5c;color:white;'
        'font-weight:bold;font-size:12px;">WEIGHTED TOTAL (/25)</td>'
    )
    for cr in configs:
        is_winner = cr.config_id == result.winner_id
        bg = "#1b5e20" if is_winner else "#1a3a5c"
        wt_row += (
            f'<td style="padding:6px;text-align:center;background:{bg};'
            f'color:white;font-weight:bold;font-size:14px;">'
            f'{cr.weighted_score:.1f}</td>'
        )
    rows_html += f"<tr>{wt_row}</tr>"

    html = f"""
    <div style="overflow-x:auto;margin-bottom:16px;">
    <table style="border-collapse:collapse;width:100%;font-family:sans-serif;">
    <thead><tr>{header_cells}</tr></thead>
    <tbody>{rows_html}</tbody>
    </table>
    </div>
    """
    st.html(html)

    st.divider()

    # ── KEY METRICS COMPARISON ─────────────────────────────────────────────
    st.subheader("Key performance metrics")
    metrics = [
        ("Biogas", [f"{r.configs[k].biogas_m3_per_d:,.0f} m³/d" for k in included],
         [f"{r.configs[k].biogas_uplift_pct:+.1f}%" for k in included]),
        ("Cake DS%", [f"{r.configs[k].cake_ds_pct:.0f}%" for k in included],
         [f"{r.configs[k].cake_vol_reduction_pct:+.0f}% vol" for k in included]),
        ("Net electricity", [f"{r.configs[k].elec_net_kw:,.0f} kW" for k in included],
         [f"{r.configs[k].elec_annual_mwh:,.0f} MWh/yr" for k in included]),
        ("Centrate NH₄", [f"{r.configs[k].centrate_nh4_kg_per_d:.0f} kg/d" for k in included],
         [f"{r.configs[k].centrate_pct_of_plant_tkn:.1f}% plant TKN" for k in included]),
        ("Pathogen class", [r.configs[k].pathogen_class for k in included],
         ["✅ Class A" if r.configs[k].class_a_achieved else "⚠️ Class B" for k in included]),
        ("Net GHG", [f"{r.configs[k].net_ghg_kg_co2e_per_d:,.0f} kg/d" for k in included],
         [f"{r.configs[k].net_ghg_t_co2e_per_yr:,.0f} t/yr" for k in included]),
        ("OPEX total", [f"${r.configs[k].opex_total_per_yr/1e6:.2f}M/yr" for k in included],
         [("—" if k == "base"
           else f"${r.configs[k].opex_delta_vs_base_per_yr/1e6:+.2f}M vs base")
          for k in included]),
        ("CAPEX (mid)", [f"${r.configs[k].capex_mid_m:.1f}M" for k in included],
         [f"${r.configs[k].capex_low_m:.0f}M – ${r.configs[k].capex_high_m:.0f}M ±30%"
          for k in included]),
    ]

    r = result  # alias
    metric_rows = [["Metric"] + [CONFIG_LABELS_SHORT[k] for k in included]]
    for label, vals, deltas in metrics:
        row_vals = [f"{v}\n{d}" for v, d in zip(vals, deltas)]
        metric_rows.append([label] + row_vals)

    df = pd.DataFrame(metric_rows[1:], columns=metric_rows[0])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # ── PER-CONFIG DETAIL ──────────────────────────────────────────────────
    st.subheader("Configuration detail")
    tabs = st.tabs([CONFIG_LABELS_SHORT[k] for k in included])

    for tab, cfg_id in zip(tabs, included):
        cr = result.configs[cfg_id]
        with tab:
            if cfg_id == result.winner_id:
                st.success(f"★ **Recommended configuration** — weighted score {cr.weighted_score:.1f}/25")

            st.markdown(cr.recommendation_text)

            bc1, bc2 = st.columns(2)
            with bc1:
                st.markdown("**Key benefits**")
                for b in cr.key_benefits:
                    st.markdown(f"✅ {b}")
            with bc2:
                st.markdown("**Key risks**")
                for r_item in cr.key_risks:
                    st.warning(r_item, icon="⚠️")

            st.markdown("**GHG breakdown (kg CO₂e/day)**")
            ghg_cols = st.columns(4)
            ghg_cols[0].metric("Scope 1", f"{cr.scope1_kg_co2e_per_d:,.0f}")
            ghg_cols[1].metric("Scope 2", f"{cr.scope2_kg_co2e_per_d:,.0f}")
            ghg_cols[2].metric("Scope 3", f"{cr.scope3_kg_co2e_per_d:,.0f}")
            ghg_cols[3].metric("Net GHG", f"{cr.net_ghg_kg_co2e_per_d:,.0f}")

            with st.expander("Equipment list & CAPEX"):
                st.markdown(
                    f"**CAPEX estimate:** ${cr.capex_low_m:.1f}M – "
                    f"${cr.capex_high_m:.1f}M  (mid: ${cr.capex_mid_m:.1f}M, ±30%)")
                st.caption(cr.capex_note)
                for item in cr.equipment_list:
                    st.markdown(f"• {item}")

    st.divider()

    # ── DOWNLOAD ───────────────────────────────────────────────────────────
    st.subheader("📄 Download report")
    dl1, dl2 = st.columns([2, 5])
    with dl1:
        if st.button("Generate comparison report", type="secondary"):
            with st.spinner("Building report (portrait + landscape appendix)..."):
                try:
                    pdf = generate_comparison_report(
                        result,
                        project_name=st.session_state.get("cmp_project", "BioPoint Analysis"),
                        prepared_by=st.session_state.get("cmp_prepby", "ph2o Consulting"),
                    )
                    st.session_state["cmp_report_pdf"] = pdf
                    st.success("Report ready — click Download.")
                except Exception as ex:
                    st.error(f"Report error: {ex}")
                    st.exception(ex)
    with dl2:
        if "cmp_report_pdf" in st.session_state:
            proj_safe = st.session_state.get("cmp_project", "MAD").replace(" ", "_")
            st.download_button(
                "⬇ Download PDF report",
                data=st.session_state["cmp_report_pdf"],
                file_name=f"MAD_Comparison_{proj_safe}.pdf",
                mime="application/pdf",
                type="primary",
            )
        else:
            st.caption("Click Generate above after running the comparison.")
