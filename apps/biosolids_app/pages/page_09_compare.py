"""
apps/biosolids_app/pages/page_09_compare.py
BioPoint V1 — MAD Configuration Comparison.
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


def _from_mad(ss, mad_key, cmp_key, default):
    """
    Return value for a comparison input, preferring:
    1. An already-set comparison value (cmp_key in session_state)
    2. The MAD Analyser value (mad_key in session_state)
    3. The hardcoded default
    """
    if cmp_key in ss and ss[cmp_key] != default:
        return ss[cmp_key]          # user has already customised comparison inputs
    if mad_key in ss:
        return ss[mad_key]          # pull from MAD Analyser
    return default


def _mad_prefill_banner():
    """Show a banner if comparison inputs were pre-filled from the MAD Analyser."""
    import streamlit as st
    mad_keys = ["mad_psV","mad_wasV","mad_psDS","mad_wasDS"]
    if any(k in st.session_state for k in mad_keys):
        st.info(
            "📋 **Site inputs pre-filled from MAD Analyser.** "
            "Expand Step 3 to review or adjust.",
            icon=None,
        )

HEAT_COLOURS = {4:"#1b5e20", 3:"#558b2f", 2:"#f57f17", 1:"#b71c1c"}
HEAT_TEXT    = {4:"white",   3:"white",   2:"black",   1:"white"}

CONFIG_INFO = {
    "base": {
        "icon": "🏭",
        "title": "Base Case",
        "subtitle": "Conventional AD",
        "desc": "No THP, no recup upgrade. Establishes the performance baseline.",
        "tag": "Lowest risk & cost",
        "tag_colour": "#546e7a",
    },
    "recup": {
        "icon": "⚡",
        "title": "Recuperative Thickening",
        "subtitle": "Feed TS% upgrade",
        "desc": "Higher feed TS% via centrifuge recirculation. Moderate CAPEX, no Class A.",
        "tag": "Moderate uplift",
        "tag_colour": "#0077b6",
    },
    "pre_thp": {
        "icon": "🔥",
        "title": "Pre-digestion THP",
        "subtitle": "THP before digesters",
        "desc": "Cell disintegration before digestion. Highest biogas uplift, Class A biosolids.",
        "tag": "Best energy",
        "tag_colour": "#2e7d32",
    },
    "solidstream": {
        "icon": "💧",
        "title": "SolidStream",
        "subtitle": "Post-digestion THP",
        "desc": "THP after existing digesters. Best dewatering (≥38% DS), Class A, retrofit-friendly.",
        "tag": "Best dewatering",
        "tag_colour": "#1a3a5c",
    },
}

def _config_card(cfg_id, selected):
    info = CONFIG_INFO[cfg_id]
    border = "2px solid #0077b6" if selected else "1px solid #ddd"
    bg = "#e8f4f8" if selected else "#fafafa"
    return f"""
    <div style="border:{border};border-radius:8px;padding:14px 16px;
                background:{bg};height:100%;box-sizing:border-box;">
      <div style="font-size:22px;margin-bottom:4px;">{info['icon']}</div>
      <div style="font-weight:700;font-size:14px;color:#1a3a5c;">{info['title']}</div>
      <div style="font-size:11px;color:#546e7a;margin-bottom:6px;">{info['subtitle']}</div>
      <div style="font-size:12px;color:#333;margin-bottom:8px;">{info['desc']}</div>
      <span style="background:{info['tag_colour']};color:white;
                   font-size:10px;padding:2px 8px;border-radius:10px;">
        {info['tag']}
      </span>
    </div>"""


def render():
    st.header("⚖️ Configuration Comparison")
    st.caption(
        "Compare up to four digestion configurations against your project drivers. "
        "Select options, set priorities, then run."
    )
    _mad_prefill_banner()

    # ═══════════════════════════════════════════════════════════════
    # STEP 1 — SELECT CONFIGURATIONS
    # ═══════════════════════════════════════════════════════════════
    st.subheader("Step 1 — Select configurations to compare")
    st.caption("Click to select or deselect. At least two recommended for a meaningful comparison.")

    cfg_cols = st.columns(4)
    selections = {}
    for col, cfg_id in zip(cfg_cols, ALL_CONFIGS):
        with col:
            # Checkbox drives selection state
            default = cfg_id != "recup"   # base, pre_thp, solidstream on by default
            checked = st.checkbox(
                CONFIG_INFO[cfg_id]["title"],
                value=st.session_state.get(f"cmp_inc_{cfg_id}", default),
                key=f"cmp_inc_{cfg_id}",
            )
            selections[cfg_id] = checked
            st.markdown(_config_card(cfg_id, checked), unsafe_allow_html=True)

    selected_ids = [k for k, v in selections.items() if v]
    if len(selected_ids) < 2:
        st.warning("Select at least two configurations to run a comparison.")

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # STEP 2 — PROJECT DRIVERS
    # ═══════════════════════════════════════════════════════════════
    st.subheader("Step 2 — Set project driver priorities")
    st.caption("5 = critical for this project. 1 = minor consideration.")

    driver_col1, driver_col2 = st.columns(2)
    weights = {}
    driver_list = list(zip(DRIVER_IDS[::2], DRIVER_IDS[1::2]))  # pair them

    for d_left, d_right in driver_list:
        with driver_col1:
            weights[d_left] = st.select_slider(
                DRIVER_LABELS[d_left],
                options=[1, 2, 3, 4, 5],
                value=st.session_state.get(f"cmp_w_{d_left}", DEFAULT_WEIGHTS.get(d_left, 3)),
                key=f"cmp_w_{d_left}",
                help=DRIVER_DESCRIPTIONS[d_left],
                format_func=lambda x: {1:"1 — Low", 2:"2", 3:"3 — Medium", 4:"4", 5:"5 — Critical"}[x],
            )
        with driver_col2:
            weights[d_right] = st.select_slider(
                DRIVER_LABELS[d_right],
                options=[1, 2, 3, 4, 5],
                value=st.session_state.get(f"cmp_w_{d_right}", DEFAULT_WEIGHTS.get(d_right, 3)),
                key=f"cmp_w_{d_right}",
                help=DRIVER_DESCRIPTIONS[d_right],
                format_func=lambda x: {1:"1 — Low", 2:"2", 3:"3 — Medium", 4:"4", 5:"Critical (5)"}[x],
            )

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # STEP 3 — SITE INPUTS (collapsed by default)
    # ═══════════════════════════════════════════════════════════════
    with st.expander("Step 3 — Site inputs (click to expand)", expanded=False):
        st.caption("Shared across all configurations. Defaults are suitable for initial screening.")

        si1, si2, si3 = st.columns(3)

        with si1:
            st.markdown("**Feed flows**")
            ps_ds  = st.number_input("PS dry solids (tDS/day)", 0.5, 500.0,
                _from_mad(st.session_state,"mad_psDS","cmp_ps_ds",6.0), step=0.5, key="cmp_ps_ds")
            was_ds = st.number_input("WAS dry solids (tDS/day)", 0.5, 500.0,
                _from_mad(st.session_state,"mad_wasDS","cmp_was_ds",4.0), step=0.5, key="cmp_was_ds")
            ps_vs  = st.number_input("PS volatile solids (% DS)", 50.0, 90.0,
                _from_mad(st.session_state,"mad_psVS","cmp_ps_vs",75.0), step=1.0, key="cmp_ps_vs")
            was_vs = st.number_input("WAS volatile solids (% DS)", 45.0, 85.0,
                _from_mad(st.session_state,"mad_wasVS","cmp_was_vs",70.0), step=1.0, key="cmp_was_vs")
            ps_n   = st.number_input("PS nitrogen (% DS)", 1.0, 8.0,
                _from_mad(st.session_state,"mad_psN","cmp_ps_n",3.0), step=0.1, key="cmp_ps_n")
            was_n  = st.number_input("WAS nitrogen (% DS)", 4.0, 15.0,
                _from_mad(st.session_state,"mad_wasN","cmp_was_n",8.5), step=0.1, key="cmp_was_n")

        with si2:
            st.markdown("**Digester geometry**")
            ps_ts  = st.number_input("PS feed TS% (base case)", 2.0, 12.0,
                _from_mad(st.session_state,"mad_psTS","cmp_ps_ts",4.0), step=0.5, key="cmp_ps_ts")
            was_ts = st.number_input("WAS feed TS% (base case)", 2.0, 12.0,
                _from_mad(st.session_state,"mad_wasTS","cmp_was_ts",4.0), step=0.5, key="cmp_was_ts")
            ps_vol  = st.number_input("PS digester volume (m³)", 100.0, 200000.0,
                _from_mad(st.session_state,"mad_psV","cmp_ps_vol",3000.0), step=100.0, key="cmp_ps_vol")
            was_vol = st.number_input("WAS digester volume (m³)", 100.0, 200000.0,
                _from_mad(st.session_state,"mad_wasV","cmp_was_vol",1200.0), step=100.0, key="cmp_was_vol")
            st.markdown("**Recup thickening target TS%**")
            recup_ps_ts  = st.number_input("Recup PS TS%", 4.0, 12.0,
                st.session_state.get("cmp_recup_ps_ts", 6.0), step=0.5, key="cmp_recup_ps_ts",
                help="Achievable feed TS% after centrifuge recirculation upgrade")
            recup_was_ts = st.number_input("Recup WAS TS%", 3.0, 10.0,
                st.session_state.get("cmp_recup_was_ts", 5.5), step=0.5, key="cmp_recup_was_ts")

        with si3:
            st.markdown("**Economics & GHG**")
            elec_buy  = st.number_input("Electricity buy ($/kWh)", 0.05, 0.50,
                st.session_state.get("cmp_elec_buy", 0.18), step=0.01,
                format="%.2f", key="cmp_elec_buy")
            elec_sell = st.number_input("Electricity sell ($/kWh)", 0.05, 0.30,
                st.session_state.get("cmp_elec_sell", 0.10), step=0.01,
                format="%.2f", key="cmp_elec_sell")
            disposal  = st.number_input("Disposal ($/wet tonne)", 20.0, 400.0,
                st.session_state.get("cmp_disposal", 80.0), step=5.0, key="cmp_disposal")
            transport_km = st.number_input("Transport distance (km)", 5.0, 300.0,
                st.session_state.get("cmp_transport_km", 50.0), step=5.0, key="cmp_transport_km")
            polymer_cost = st.number_input("Polymer cost ($/kg)", 1.0, 10.0,
                st.session_state.get("cmp_polymer_cost", 3.50), step=0.25,
                format="%.2f", key="cmp_polymer_cost")
            plant_tkn = st.number_input("Plant TKN (kg N/day)", 50.0, 10000.0,
                st.session_state.get("cmp_plant_tkn", 500.0), step=50.0, key="cmp_plant_tkn",
                help="Used to calculate centrate NH4 return as % of plant TKN")
            grid_i = st.selectbox("Grid state",
                ["VIC (0.60)", "NSW (0.55)", "QLD (0.72)", "SA (0.25)",
                 "WA (0.65)", "TAS (0.08)", "NZ (0.12)", "Custom"],
                index=0, key="cmp_grid_state")
            grid_intensity = (
                st.number_input("Grid intensity (kgCO₂e/kWh)", 0.0, 1.5,
                    st.session_state.get("cmp_grid_custom", 0.55),
                    step=0.01, format="%.3f", key="cmp_grid_custom")
                if grid_i == "Custom"
                else float(grid_i.split("(")[1].rstrip(")"))
            )

    # ── Report settings ────────────────────────────────────────────
    with st.expander("📄 Report settings", expanded=False):
        rc1, rc2 = st.columns(2)
        with rc1:
            st.text_input("Project name",
                _from_mad(st.session_state,"mad_project_name","cmp_project","BioPoint Analysis"),
                key="cmp_project")
        with rc2:
            st.text_input("Prepared by",
                _from_mad(st.session_state,"mad_prepared_by","cmp_prepby","ph2o Consulting"),
                key="cmp_prepby")

    # ═══════════════════════════════════════════════════════════════
    # RUN
    # ═══════════════════════════════════════════════════════════════
    st.divider()
    run_col, _ = st.columns([2, 5])
    with run_col:
        run = st.button("▶ Run Comparison", type="primary",
                        disabled=len(selected_ids) < 2)

    if not run and "cmp_result" not in st.session_state:
        return

    if run:
        if len(selected_ids) < 2:
            st.error("Select at least two configurations.")
            return

        # Read site inputs — use session state values since expander may be collapsed
        site = ComparisonSiteInputs(
            ps_ds_tpd  = st.session_state.get("cmp_ps_ds", 6.0),
            was_ds_tpd = st.session_state.get("cmp_was_ds", 4.0),
            ps_ts_pct  = st.session_state.get("cmp_ps_ts", 4.0),
            was_ts_pct = st.session_state.get("cmp_was_ts", 4.0),
            ps_vs_pct  = st.session_state.get("cmp_ps_vs", 75.0),
            was_vs_pct = st.session_state.get("cmp_was_vs", 70.0),
            ps_n_pct   = st.session_state.get("cmp_ps_n",  3.0),
            was_n_pct  = st.session_state.get("cmp_was_n", 8.5),
            ps_volume_m3  = st.session_state.get("cmp_ps_vol",  3000.0),
            was_volume_m3 = st.session_state.get("cmp_was_vol", 1200.0),
            recup_ps_ts_pct  = st.session_state.get("cmp_recup_ps_ts",  6.0),
            recup_was_ts_pct = st.session_state.get("cmp_recup_was_ts", 5.5),
            electricity_buy_per_kwh  = st.session_state.get("cmp_elec_buy",  0.18),
            electricity_sell_per_kwh = st.session_state.get("cmp_elec_sell", 0.10),
            disposal_cost_per_t_wet  = st.session_state.get("cmp_disposal",  80.0),
            transport_km             = st.session_state.get("cmp_transport_km", 50.0),
            polymer_cost_per_kg      = st.session_state.get("cmp_polymer_cost", 3.50),
            grid_intensity_kg_co2e_per_kwh = grid_intensity,
            plant_tkn_kg_per_d = st.session_state.get("cmp_plant_tkn", 500.0),
            project_name = st.session_state.get("cmp_project", "BioPoint Analysis"),
            prepared_by  = st.session_state.get("cmp_prepby",  "ph2o Consulting"),
        )
        with st.spinner("Running comparison..."):
            result = run_comparison(site, weights, selected_ids)
            st.session_state["cmp_result"] = result
            st.session_state.pop("cmp_report_pdf", None)

    result = st.session_state.get("cmp_result")
    if not result:
        return

    included = result.included_ids

    # ═══════════════════════════════════════════════════════════════
    # RESULTS
    # ═══════════════════════════════════════════════════════════════

    # Winner banner
    if result.winner_id:
        wc = result.configs[result.winner_id]
        st.success(
            f"★ **Recommended: {result.winner_label}** "
            f"— weighted score {wc.weighted_score:.0f}/100  \n"
            + result.executive_summary
        )

    st.divider()

    # ── Heatmap ────────────────────────────────────────────────────
    st.subheader("Driver heatmap")
    st.caption("Dark green = best among compared configurations. Dark red = worst. Scores are relative.")

    configs = [result.configs[k] for k in included]

    header_cells = '<th style="text-align:left;padding:10px 12px;background:#1a3a5c;color:white;min-width:160px;font-size:13px;">Driver</th>'
    for cr in configs:
        star = "★ " if cr.config_id == result.winner_id else ""
        header_cells += (
            f'<th style="text-align:center;padding:10px 8px;background:#1a3a5c;'
            f'color:white;min-width:130px;font-size:12px;">{star}{cr.config_label}</th>'
        )

    rows_html = ""
    for d in DRIVER_IDS:
        w = result.driver_weights.get(d, 1)
        row_html = (
            f'<td style="padding:8px 12px;background:#e8f4f8;font-weight:bold;'
            f'font-size:12px;border-bottom:1px solid #ddd;">'
            f'{DRIVER_LABELS.get(d, d)}'
            f'<br/><span style="font-weight:normal;font-size:10px;color:#546e7a;">'
            f'Weight: {w}/5</span></td>'
        )
        for cr in configs:
            sc  = cr.driver_scores.get(d, 1)
            raw = cr.driver_raw.get(d, 0)
            raw_fmt = {
                "energy":      f"{raw:,.0f} m³/d",
                "biosolids":   "Class A" if raw >= 4 else "Class B",
                "dewatering":  f"{raw:.0f}% DS",
                "return_load": f"{raw:.0f} kg N/d",
                "carbon":      f"{raw:,.0f} kgCO2e/d",
                "opex":        f"${raw/1000:,.0f}k/yr",
                "capex":       f"${raw:.1f}M",
                "headroom":    f"{raw:.1f}d",
            }.get(d, f"{raw:.1f}")
            bg   = HEAT_COLOURS.get(sc, "#eceff1")
            text = HEAT_TEXT.get(sc, "black")
            label = {4:"★ Best", 3:"Good", 2:"Fair", 1:"Worst"}.get(sc, str(sc))
            row_html += (
                f'<td style="padding:4px 6px;border-bottom:1px solid #eee;">'
                f'<div style="background:{bg};color:{text};text-align:center;'
                f'padding:8px 4px;border-radius:4px;font-size:12px;font-weight:bold;">'
                f'{label}<br/><span style="font-size:10px;opacity:0.85;">{raw_fmt}</span>'
                f'</div></td>'
            )
        rows_html += f"<tr>{row_html}</tr>"

    # Total row
    wt_row = (
        '<td style="padding:10px 12px;background:#1a3a5c;color:white;'
        'font-weight:bold;font-size:13px;border-top:2px solid #fff;">WEIGHTED TOTAL /100</td>'
    )
    for cr in configs:
        is_winner = cr.config_id == result.winner_id
        bg = "#1b5e20" if is_winner else "#1a3a5c"
        wt_row += (
            f'<td style="padding:8px 6px;border-top:2px solid #fff;">'
            f'<div style="background:{bg};color:white;text-align:center;'
            f'padding:10px 4px;border-radius:4px;font-size:16px;font-weight:bold;">'
            f'{cr.weighted_score:.0f}</div></td>'
        )
    rows_html += f"<tr>{wt_row}</tr>"

    st.html(f"""
    <div style="overflow-x:auto;margin-bottom:16px;">
    <table style="border-collapse:collapse;width:100%;font-family:sans-serif;border-radius:8px;overflow:hidden;">
    <thead><tr>{header_cells}</tr></thead>
    <tbody>{rows_html}</tbody>
    </table>
    </div>
    """)

    st.divider()

    # ── Per-config tabs ────────────────────────────────────────────
    st.subheader("Configuration detail")
    tabs = st.tabs([
        f"{'★ ' if result.configs[k].config_id == result.winner_id else ''}{CONFIG_LABELS_SHORT[k]}"
        for k in included
    ])
    for tab, cfg_id in zip(tabs, included):
        cr = result.configs[cfg_id]
        with tab:
            if cfg_id == result.winner_id:
                st.success(f"★ Recommended — weighted score {cr.weighted_score:.0f}/100")

            st.markdown(cr.recommendation_text)

            bc1, bc2 = st.columns(2)
            with bc1:
                st.markdown("**Key benefits**")
                for b in cr.key_benefits:
                    st.markdown(f"✅ {b}")
            with bc2:
                st.markdown("**Key risks / considerations**")
                for r_item in cr.key_risks:
                    st.markdown(f"⚠️ {r_item}")

            st.markdown("**GHG breakdown (kg CO₂e/day)**")
            g1, g2, g3, g4 = st.columns(4)
            g1.metric("Scope 1", f"{cr.scope1_kg_co2e_per_d:,.0f}")
            g2.metric("Scope 2", f"{cr.scope2_kg_co2e_per_d:,.0f}")
            g3.metric("Scope 3", f"{cr.scope3_kg_co2e_per_d:,.0f}")
            g4.metric("Net GHG", f"{cr.net_ghg_kg_co2e_per_d:,.0f}")

            with st.expander("Equipment scope"):
                for item in cr.equipment_list:
                    st.markdown(f"• {item}")

    st.divider()

    # ── Download ───────────────────────────────────────────────────
    st.subheader("📄 Download report")
    dl1, dl2 = st.columns([2, 3])
    with dl1:
        if st.button("Generate comparison report", type="secondary"):
            with st.spinner("Building report..."):
                try:
                    pdf = generate_comparison_report(
                        result,
                        project_name=st.session_state.get("cmp_project", "BioPoint Analysis"),
                        prepared_by=st.session_state.get("cmp_prepby",  "ph2o Consulting"),
                    )
                    st.session_state["cmp_report_pdf"] = pdf
                    st.success("Report ready.")
                except Exception as ex:
                    st.error(f"Report error: {ex}")
                    st.exception(ex)
    with dl2:
        if "cmp_report_pdf" in st.session_state:
            proj = st.session_state.get("cmp_project", "MAD").replace(" ", "_")
            st.download_button(
                "⬇ Download PDF",
                data=st.session_state["cmp_report_pdf"],
                file_name=f"MAD_Comparison_{proj}.pdf",
                mime="application/pdf",
                type="primary",
            )
