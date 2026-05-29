"""
apps/biosolids_app/pages/page_12_separate.py
BioPoint V1 — Separate vs Blended Digestion Analysis.
ph2o Consulting — v25B02
"""
import sys
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from engine.separate_digestion import (
    run_separate_analysis, vsr_cstr, vsr_batch, hrt_batch_target,
    K_PS_CENTRAL, K_WAS_CENTRAL, K_BLEND_CENTRAL, Y_PS_SEP, Y_WAS, Y_BLEND,
    BIOPOINT_CALIBRATION,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _metric_delta(label, value, delta=None, suffix="", help_text=None):
    st.metric(label, f"{value:,.0f}{suffix}", delta=delta, help=help_text)


def _throughput_chart(ps_vol, was_vol, ps_ts, was_ts, ps_vs, was_vs, k_ps, k_was):
    """HRT vs biogas chart for both streams."""
    import numpy as np
    hrts = list(range(5, 35))
    ps_bg_cstr  = [vsr_cstr(k_ps,  h) * (ps_ds_local  * ps_vs/100 * 1000 * Y_PS_SEP * BIOPOINT_CALIBRATION) for h in hrts]
    was_bg_cstr = [vsr_cstr(k_was, h) * (was_ds_local * was_vs/100 * 1000 * Y_WAS   * BIOPOINT_CALIBRATION) for h in hrts]
    ps_bg_batch = [vsr_batch(k_ps,  h) * (ps_ds_local  * ps_vs/100 * 1000 * Y_PS_SEP * BIOPOINT_CALIBRATION) for h in hrts]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hrts, y=ps_bg_cstr, name="PS — CSTR (separate)",
        line=dict(color="#0077b6", width=2.5)))
    fig.add_trace(go.Scatter(x=hrts, y=was_bg_cstr, name="WAS — CSTR",
        line=dict(color="#52b788", width=2.5)))
    fig.add_trace(go.Scatter(x=hrts, y=ps_bg_batch, name="PS — batch reference",
        line=dict(color="#0077b6", width=1.5, dash="dot"),
        opacity=0.5))
    # Mark current HRTs
    ps_hrt_cur  = ps_vol  / (ps_ds_local  / (ps_ts /100))
    was_hrt_cur = was_vol / (was_ds_local / (was_ts/100))
    for stream, hrt, bg_list, col in [
        ("PS",  ps_hrt_cur,  ps_bg_cstr,  "#0077b6"),
        ("WAS", was_hrt_cur, was_bg_cstr, "#52b788"),
    ]:
        idx = min(range(len(hrts)), key=lambda i: abs(hrts[i]-hrt))
        fig.add_vline(x=hrt, line_color=col, line_dash="dash", opacity=0.4)
        fig.add_annotation(x=hrt, y=bg_list[idx]*1.08,
                           text=f"{stream}: {hrt:.0f}d", font_size=10,
                           font_color=col, showarrow=False)
    fig.add_vline(x=10, line_color="grey", line_dash="dot", opacity=0.3)
    fig.add_annotation(x=10, y=max(max(ps_bg_cstr),max(was_bg_cstr))*0.95,
                       text="PS 10d<br>batch target", font_size=9,
                       showarrow=False, font_color="grey")
    fig.add_vline(x=15, line_color="grey", line_dash="dot", opacity=0.3)
    fig.add_annotation(x=15, y=max(max(ps_bg_cstr),max(was_bg_cstr))*0.88,
                       text="WAS 15d<br>min", font_size=9,
                       showarrow=False, font_color="grey")
    fig.update_layout(
        height=340, title="Biogas vs HRT by stream",
        xaxis_title="HRT (days)", yaxis_title="Stream biogas (Nm³/day)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=60, b=40, l=50, r=20),
        plot_bgcolor="#f8fafc", paper_bgcolor="white",
    )
    return fig


def _uplift_sensitivity_chart(r):
    """Waterfall showing blended → separate biogas uplift components."""
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "total"],
        x=["Blended\n(base)", "PS kinetics\n(k uplift)", "PS yield\n(×1.30 separate)", "Separate\n(total)"],
        y=[r.blend_biogas,
           (r.sep_biogas - r.blend_biogas) * 0.35,   # approx kinetics share
           (r.sep_biogas - r.blend_biogas) * 0.65,   # approx yield share
           0],
        connector=dict(line=dict(color="#cccccc")),
        increasing=dict(marker=dict(color="#52b788")),
        decreasing=dict(marker=dict(color="#e57373")),
        totals=dict(marker=dict(color="#0077b6")),
        text=[f"{r.blend_biogas:,.0f}", f"+{(r.sep_biogas-r.blend_biogas)*0.35:,.0f}",
              f"+{(r.sep_biogas-r.blend_biogas)*0.65:,.0f}", f"{r.sep_biogas:,.0f}"],
        textposition="outside",
    ))
    fig.update_layout(
        height=300, title="Biogas uplift breakdown",
        yaxis_title="Nm³/day", showlegend=False,
        margin=dict(t=50, b=40, l=50, r=20),
        plot_bgcolor="#f8fafc", paper_bgcolor="white",
    )
    return fig


def _volume_optimisation_chart(ps_ds, was_ds, ps_ts, was_ts, ps_vs, was_vs,
                                v_total, k_ps, k_was):
    """Show biogas vs V_PS fraction for optimisation mode."""
    fracs = [f/100 for f in range(5, 95)]
    bg_totals = []
    ps_vol_feed  = ps_ds  / (ps_ts /100)
    was_vol_feed = was_ds / (was_ts/100)
    for frac in fracs:
        V_PS = v_total * frac; V_WAS = v_total - V_PS
        hps  = V_PS  / ps_vol_feed  if ps_vol_feed  > 0 else 0
        hwas = V_WAS / was_vol_feed if was_vol_feed > 0 else 0
        if hps < 8 or hwas < 10:
            bg_totals.append(None)
        else:
            bps  = vsr_cstr(k_ps, hps)   * ps_ds  * (ps_vs /100)*1000*Y_PS_SEP*BIOPOINT_CALIBRATION
            bwas = vsr_cstr(k_was, hwas) * was_ds * (was_vs/100)*1000*Y_WAS  *BIOPOINT_CALIBRATION
            bg_totals.append(bps + bwas)
    best_idx = max((i for i,v in enumerate(bg_totals) if v), key=lambda i: bg_totals[i])
    best_frac = fracs[best_idx]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[f*100 for f in fracs], y=bg_totals,
        line=dict(color="#0077b6", width=2.5), name="Total biogas"))
    fig.add_vline(x=best_frac*100, line_color="#52b788", line_dash="dash",
                  annotation_text=f"Optimal {best_frac*100:.0f}% PS",
                  annotation_font_size=10)
    fig.add_vline(x=ps_ds/(ps_ds+was_ds)*100, line_color="#e57373", line_dash="dot",
                  annotation_text="DS-proportional split", annotation_font_size=10)
    fig.update_layout(
        height=320, title="Total biogas vs PS volume fraction",
        xaxis_title="PS volume fraction (%)", yaxis_title="Total biogas (Nm³/day)",
        margin=dict(t=50, b=40, l=50, r=20),
        plot_bgcolor="#f8fafc", paper_bgcolor="white",
    )
    return fig


# ── Page ──────────────────────────────────────────────────────────────────

def render():
    st.header("🔀 Separate vs Blended Digestion")
    st.caption(
        "Analyses the throughput and biogas impact of digesting primary sludge (PS) and "
        "waste activated sludge (WAS) in separate digesters vs a blended feed. "
        "Literature shows separate PS digestion yields ~30% more biogas per unit VS "
        "(Bolzonella 2005; Silvestre 2015; WEF MOP 8)."
    )

    # ── Sidebar help ──────────────────────────────────────────────────────
    with st.expander("📖 Kinetic model basis", expanded=False):
        st.markdown("""
**CSTR first-order model** (Chen & Hashimoto; Metcalf & Eddy 5th ed.):

$$VSR = 1 - \\frac{1}{1 + k \\cdot HRT}$$

| Stream | k central | Range | Rationale |
|--------|-----------|-------|-----------|
| PS (separate) | 0.25 /day | 0.20–0.35 | Lipid/carbohydrate substrate; no WAS inhibition |
| WAS | 0.12 /day | 0.08–0.15 | Cell wall hydrolysis rate-limiting |
| Blended | 0.13 /day | 0.10–0.18 | WAS-dominated kinetics |

**Note:** "PS >90% in 10 days" refers to the *batch exponential* model 
(1−e^(−0.25×10)=91.8%), which is a test condition, not a CSTR design target.  
For continuous CSTR design, target HRT=12–15 days for PS.

**30% specific yield uplift** (PS separate): empirical observation from multiple 
studies comparing separate vs blended digestion. Applied as a multiplier on CH4 yield 
per tVS. Mechanism: removal of WAS inhibition of lipase activity; improved hydrolysis 
of primary lipids and carbohydrates.
        """)

    # ── Inputs ────────────────────────────────────────────────────────────
    st.subheader("Site inputs")

    # Pre-fill from MAD/comparison session state
    ss = st.session_state
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Primary Sludge (PS)**")
        ps_ds  = st.number_input("PS dry solids (tDS/day)", 1.0, 500.0,
                    ss.get("mad_psDS", ss.get("cmp_ps_ds", 6.0)), 0.5, key="sep_ps_ds")
        ps_ts  = st.number_input("PS feed TS%", 1.0, 15.0,
                    ss.get("mad_psTS", ss.get("cmp_ps_ts", 4.0)), 0.1, key="sep_ps_ts")
        ps_vs  = st.number_input("PS volatile solids (% DS)", 50.0, 90.0,
                    ss.get("mad_psVS", ss.get("cmp_ps_vs", 75.0)), 0.5, key="sep_ps_vs")
        ps_vol = st.number_input("PS digester volume (m³)", 100.0, 200000.0,
                    ss.get("mad_psV", ss.get("cmp_ps_vol", 3000.0)), 100.0,
                    format="%.0f", key="sep_ps_vol")

    with c2:
        st.markdown("**Waste Activated Sludge (WAS)**")
        was_ds = st.number_input("WAS dry solids (tDS/day)", 1.0, 500.0,
                    ss.get("mad_wasDS", ss.get("cmp_was_ds", 4.0)), 0.5, key="sep_was_ds")
        was_ts = st.number_input("WAS feed TS%", 0.5, 8.0,
                    ss.get("mad_wasTS", ss.get("cmp_was_ts", 4.0)), 0.1, key="sep_was_ts")
        was_vs = st.number_input("WAS volatile solids (% DS)", 50.0, 90.0,
                    ss.get("mad_wasVS", ss.get("cmp_was_vs", 70.0)), 0.5, key="sep_was_vs")
        was_vol= st.number_input("WAS digester volume (m³)", 100.0, 200000.0,
                    ss.get("mad_wasV", ss.get("cmp_was_vol", 1200.0)), 100.0,
                    format="%.0f", key="sep_was_vol")

    # Store for throughput chart
    global ps_ds_local, was_ds_local
    ps_ds_local = ps_ds; was_ds_local = was_ds

    v_total = ps_vol + was_vol

    st.divider()

    # Analysis mode
    mode_labels = {
        "separate":  "🔀 Separate — user-defined volume split",
        "optimised": "⚙️  Optimise — find best volume split automatically",
    }
    mode_key = st.radio("Analysis mode", list(mode_labels.keys()),
                        format_func=lambda k: mode_labels[k],
                        horizontal=True, key="sep_mode")

    if mode_key == "separate":
        st.caption(
            f"Using PS digester = {ps_vol:,.0f} m³ and WAS digester = {was_vol:,.0f} m³ "
            f"(total {v_total:,.0f} m³). Adjust volumes above to explore different splits."
        )
        hrt_ps_target  = None
        hrt_was_target = None
    else:
        st.caption(
            f"BioPoint will find the optimal V_PS : V_WAS split within the total "
            f"{v_total:,.0f} m³ to maximise total biogas production. "
            f"PS volume in the inputs above sets the current allocation — "
            f"the optimiser will override it."
        )
        with st.expander("Advanced kinetic constants", expanded=False):
            c1k, c2k = st.columns(2)
            K_PS_USE  = c1k.slider("k_PS (/day)", 0.15, 0.40, K_PS_CENTRAL, 0.01)
            K_WAS_USE = c2k.slider("k_WAS (/day)", 0.06, 0.18, K_WAS_CENTRAL, 0.01)
        if "K_PS_USE" not in dir():
            K_PS_USE = K_PS_CENTRAL; K_WAS_USE = K_WAS_CENTRAL
    
    K_PS_USE  = locals().get("K_PS_USE",  K_PS_CENTRAL)
    K_WAS_USE = locals().get("K_WAS_USE", K_WAS_CENTRAL)

    st.divider()

    # ── Run analysis ──────────────────────────────────────────────────────
    r = run_separate_analysis(
        ps_ds_tpd=ps_ds, was_ds_tpd=was_ds,
        ps_ts_pct=ps_ts, was_ts_pct=was_ts,
        ps_vs_pct=ps_vs, was_vs_pct=was_vs,
        ps_volume_m3=ps_vol, was_volume_m3=was_vol,
        mode=mode_key,
        k_ps=K_PS_USE, k_was=K_WAS_USE,
    )

    # ── Top metrics ───────────────────────────────────────────────────────
    st.subheader("Results")
    m1, m2, m3, m4, m5 = st.columns(5)

    bg_delta = f"+{r.sep_biogas - r.blend_biogas:,.0f} Nm³/d" if r.sep_biogas else None
    m1.metric("Blended biogas",  f"{r.blend_biogas:,.0f}", "Nm³/day (reference)")
    m2.metric("Separate biogas", f"{r.sep_biogas:,.0f}" if r.sep_biogas else "—",
              bg_delta)
    m3.metric("Biogas uplift",
              f"+{r.biogas_uplift_pct:.1f}%" if r.sep_biogas else "—",
              f"range {r.biogas_uplift_lo_pct:.1f}–{r.biogas_uplift_hi_pct:.1f}%")
    if r.ps:
        m4.metric("PS HRT", f"{r.ps.hrt_days:.1f} days",
                  "✓ <15d" if r.ps.hrt_days < 15 else "⚠ >15d")
        m5.metric("WAS HRT", f"{r.was.hrt_days:.1f} days",
                  "✓ ≥15d" if r.was.hrt_days >= 15 else "⚠ below 15d recommended")

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_compare, tab_streams, tab_throughput, tab_optimise = st.tabs([
        "📊 Comparison",
        "🧪 Stream Detail",
        "📈 Throughput",
        "⚙️  Volume Optimiser",
    ])

    # ── TAB 1: Comparison ─────────────────────────────────────────────────
    with tab_compare:
        if not r.ps:
            st.info("Run the analysis above to see comparison results.")
        else:
            st.subheader("Blended vs Separate — Key Results")
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("**Blended digestion**")
                st.metric("HRT",         f"{r.blend_hrt:.1f} days")
                st.metric("Combined VSR",f"{r.blend_vsr_pct:.1f}%")
                st.metric("Biogas",      f"{r.blend_biogas:,.0f} Nm³/day")
                st.metric("Net electricity", f"{r.blend_elec_kw:,.0f} kW")
                st.metric("Wet cake",    f"{r.blend_cake_tpd:.1f} t/day")

            with col_b:
                st.markdown("**Separate digestion**")
                st.metric("PS HRT",      f"{r.ps.hrt_days:.1f} days")
                st.metric("WAS HRT",     f"{r.was.hrt_days:.1f} days")
                bg_up = r.sep_biogas - r.blend_biogas
                st.metric("Biogas",      f"{r.sep_biogas:,.0f} Nm³/day",
                          f"+{bg_up:,.0f} Nm³/d ({r.biogas_uplift_pct:+.1f}%)")
                st.metric("Net electricity", f"{r.sep_elec_kw:,.0f} kW",
                          f"+{r.elec_uplift_kw:,.0f} kW")
                st.metric("Wet cake", f"{r.sep_cake_tpd:.1f} t/day")

            st.divider()

            # Biogas waterfall
            st.plotly_chart(_uplift_sensitivity_chart(r), use_container_width=True)

            st.caption(
                f"Sensitivity: uplift range {r.biogas_uplift_lo_pct:.1f}–"
                f"{r.biogas_uplift_hi_pct:.1f}% (literature kinetic constant range). "
                f"Central estimate: +{r.biogas_uplift_pct:.1f}%. "
                "30% specific yield uplift is an empirical factor applied to PS stream "
                "(Bolzonella 2005; Silvestre 2015). All values screening-grade ±15%."
            )

    # ── TAB 2: Stream detail ───────────────────────────────────────────────
    with tab_streams:
        if not r.ps:
            st.info("Run the analysis above.")
        else:
            st.subheader("Stream-by-Stream Analysis")
            c_ps, c_was = st.columns(2)

            for col, stream, stream_label in [
                (c_ps, r.ps, "Primary Sludge (PS)"),
                (c_was, r.was, "Waste Activated Sludge (WAS)"),
            ]:
                with col:
                    st.markdown(f"**{stream_label}**")
                    data = {
                        "Dry solids (tDS/day)":   f"{stream.ds_tpd:.1f}",
                        "Volatile solids (tVS/d)":f"{stream.vs_tpd:.1f}",
                        "Feed volume (m³/day)":   f"{stream.ds_tpd/(stream_ts:=ps_ts if stream.stream=='PS' else was_ts)/100:.0f}",
                        "Digester volume (m³)":   f"{stream.volume_m3:,.0f}",
                        "HRT (days)":             f"{stream.hrt_days:.1f}",
                        "VS loading (kgVS/m³/d)": f"{stream.vs_loading_kgVS_m3_d:.2f}",
                        "VSR (CSTR model)":        f"{stream.vsr_pct:.1f}%",
                        "Biogas (Nm³/day)":        f"{stream.biogas_nm3d:,.0f}",
                        "Gross electricity (kW)":  f"{stream.elec_gross_kw:,.0f}",
                        "Wet cake (t/day)":        f"{stream.wet_cake_tpd:.1f}",
                        "Cake DS%":                f"{stream.cake_ds_pct:.0f}%",
                        "k used (/day)":           f"{stream.k_used:.2f}",
                    }
                    if stream.stream == "PS":
                        data["Yield uplift (separate)"] = "×1.30 (literature)"
                    for k, v in data.items():
                        st.markdown(f"**{k}:** {v}")

            st.divider()
            # VSR comparison chart
            import numpy as np
            hrts = list(range(5, 30))
            fig_vsr = go.Figure()
            for k, label, col in [
                (K_PS_USE,     "PS (separate)",  "#0077b6"),
                (K_WAS_USE,    "WAS",            "#52b788"),
                (K_BLEND_CENTRAL,"Blended",       "#aaaaaa"),
            ]:
                fig_vsr.add_trace(go.Scatter(
                    x=hrts, y=[vsr_cstr(k,h)*100 for h in hrts],
                    name=label, line=dict(color=col, width=2)))
            for hrt, label in [(10,"PS 10d batch"), (15,"WAS 15d min")]:
                fig_vsr.add_vline(x=hrt, line_color="grey", line_dash="dot", opacity=0.4,
                                  annotation_text=label, annotation_font_size=9)
            fig_vsr.update_layout(height=300, title="VSR vs HRT (CSTR model)",
                xaxis_title="HRT (days)", yaxis_title="VSR (%)",
                margin=dict(t=50, b=40, l=50, r=20),
                plot_bgcolor="#f8fafc", paper_bgcolor="white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_vsr, use_container_width=True)

    # ── TAB 3: Throughput ──────────────────────────────────────────────────
    with tab_throughput:
        st.subheader("Throughput Capacity Analysis")
        st.markdown(
            "This tab answers: **given the current digester volumes, how does "
            "separating the streams affect capacity for future load growth?**"
        )

        if not r.ps:
            st.info("Run the analysis.")
        else:
            # Key insight
            ps_hrt_feed = r.ps.hrt_days
            was_hrt_needed = 15.0
            ps_vol_for_15d = (ps_ds / (ps_ts/100)) * was_hrt_needed
            volume_freed   = ps_vol - ps_vol_for_15d

            if volume_freed > 0:
                st.success(
                    f"**Volume optimisation opportunity:** PS digestion is complete "
                    f"well within 15 days at the current PS volume "
                    f"({ps_hrt_feed:.1f}d HRT). "
                    f"If PS is designed for {was_hrt_needed:.0f}d HRT, "
                    f"**{volume_freed:,.0f} m³** of PS digester volume is freed "
                    f"({volume_freed/8000:.1f}× 8,000 m³ digester). "
                    f"This volume could be reallocated to WAS, to new load, or avoided in new builds."
                )
            else:
                st.info(
                    f"PS HRT ({ps_hrt_feed:.1f}d) is near or below the 15-day design target. "
                    "Consider increasing PS digester volume or reducing HRT target."
                )

            c1, c2, c3 = st.columns(3)
            c1.metric("PS HRT (current split)",  f"{r.ps.hrt_days:.1f} days",
                      "✓ below 15d — volume available" if r.ps.hrt_days < 15
                      else "⚠ at or above 15d limit")
            c2.metric("WAS HRT (current split)", f"{r.was.hrt_days:.1f} days",
                      "✓ meets 15d min" if r.was.hrt_days >= 15
                      else "⚠ below 15d — WAS under-digested")
            c3.metric("Volume freed (if PS@15d)", f"{max(0,volume_freed):,.0f} m³",
                      f"{max(0,volume_freed)/8000:.1f}× 8,000 m³ digesters")

            st.divider()

            # Throughput scenarios
            st.markdown("**Capacity scenarios at current total volume**")

            ps_q  = ps_ds  / (ps_ts /100)  # m³/day feed flow
            was_q = was_ds / (was_ts/100)
            rows  = []
            scenarios = [
                ("Blended (current)",        v_total, 0, v_total),
                ("Separate (current split)", ps_vol,  was_vol, v_total),
                ("PS at 12d, WAS gets rest", ps_q*12, v_total-ps_q*12, v_total),
                ("PS at 15d, WAS gets rest", ps_q*15, v_total-ps_q*15, v_total),
                ("PS at 10d, WAS gets rest", ps_q*10, v_total-ps_q*10, v_total),
            ]
            for label, V_PS, V_WAS, V_tot in scenarios:
                if V_WAS < was_q * 10: continue
                if label == "Blended (current)":
                    h_ps = V_tot/(ps_q+was_q); h_was = h_ps
                    max_ps_tDS_yr = V_tot*(ps_ts/100)/1 * 365  # bound by WAS requirement
                    max_was_tDS_yr= V_tot*(was_ts/100)/1 * 365
                else:
                    h_ps  = V_PS  / ps_q  if ps_q  > 0 else 0
                    h_was = V_WAS / was_q if was_q > 0 else 0
                    max_ps_tDS_yr  = V_PS  / 10 * (ps_ts /100) * 365   # PS can be 10d
                    max_was_tDS_yr = V_WAS / 15 * (was_ts/100) * 365   # WAS needs 15d
                rows.append({
                    "Scenario": label,
                    "V_PS (m³)":  f"{V_PS:,.0f}" if label!="Blended (current)" else f"{V_tot:,.0f}",
                    "V_WAS (m³)": f"{V_WAS:,.0f}" if label!="Blended (current)" else "—",
                    "PS HRT (d)": f"{h_ps:.1f}",
                    "WAS HRT (d)":f"{h_was:.1f}",
                    "Max PS cap. (tDS/yr)": f"{max_ps_tDS_yr:,.0f}",
                    "Max WAS cap. (tDS/yr)":f"{max_was_tDS_yr:,.0f}",
                })
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            st.caption(
                "Max capacity assumes minimum HRT constraints (PS=10d, WAS=15d). "
                "Actual maximum throughput is typically 80-90% of theoretical capacity "
                "to allow for peak loading. Screening-grade ±20%."
            )

            # HRT vs biogas chart
            st.plotly_chart(
                _throughput_chart(ps_vol, was_vol, ps_ts, was_ts, ps_vs, was_vs,
                                  K_PS_USE, K_WAS_USE),
                use_container_width=True
            )

    # ── TAB 4: Volume optimiser ─────────────────────────────────────────────
    with tab_optimise:
        st.subheader("Volume Optimiser")
        st.markdown(
            "Find the optimal allocation of total digester volume between PS and WAS "
            "to **maximise total biogas production**. The optimiser also shows the "
            "volume saving if separate digestion is used to match the same biogas "
            "as blended digestion."
        )

        st.plotly_chart(
            _volume_optimisation_chart(ps_ds, was_ds, ps_ts, was_ts, ps_vs, was_vs,
                                        v_total, K_PS_USE, K_WAS_USE),
            use_container_width=True
        )

        if mode_key == "optimised" and r.opt_v_ps_m3 > 0:
            o1, o2, o3, o4 = st.columns(4)
            o1.metric("Optimal V_PS",  f"{r.opt_v_ps_m3:,.0f} m³",
                      f"{r.opt_v_ps_m3/v_total:.0%} of total")
            o2.metric("Optimal V_WAS", f"{r.opt_v_was_m3:,.0f} m³",
                      f"{r.opt_v_was_m3/v_total:.0%} of total")
            o3.metric("PS HRT",        f"{r.opt_hrt_ps:.1f} days")
            o4.metric("WAS HRT",       f"{r.opt_hrt_was:.1f} days")
            st.metric("Max biogas at optimal split",
                      f"{r.opt_biogas:,.0f} Nm³/day",
                      f"+{r.opt_biogas_uplift_pct:.1f}% vs blended")
        else:
            st.info(
                "Switch to **Optimise** mode above to run the optimiser "
                "and see the recommended volume split.",
                icon="💡"
            )

        st.divider()
        # Volume saving analysis
        st.markdown("**Volume saving: same biogas as blended with separate digestion**")
        ps_q_flow  = ps_ds  / (ps_ts /100)
        was_q_flow = was_ds / (was_ts/100)
        v_saving = None
        for V in range(int(v_total*0.3), int(v_total)+500, 500):
            V_PS_f = ps_q_flow * 12  # PS at 12d
            V_WAS_f= V - V_PS_f
            if V_WAS_f < was_q_flow * 10: continue
            h_was = V_WAS_f / was_q_flow
            bps   = vsr_cstr(K_PS_USE,  12)      * ps_ds *(ps_vs/100)*1000*Y_PS_SEP *BIOPOINT_CALIBRATION
            bwas  = vsr_cstr(K_WAS_USE, h_was)   * was_ds*(was_vs/100)*1000*Y_WAS  *BIOPOINT_CALIBRATION
            if bps + bwas >= r.blend_biogas:
                v_saving = v_total - V
                v_saving_n = v_saving / 8000
                st.success(
                    f"To match blended biogas ({r.blend_biogas:,.0f} Nm³/day), "
                    f"separate digestion needs only **{V:,} m³** total "
                    f"(PS at 12d HRT + WAS at {h_was:.1f}d HRT). "
                    f"This saves **{v_saving:,.0f} m³ "
                    f"({v_saving_n:.1f}× 8,000 m³ digesters)** vs blended — "
                    f"volume that can accommodate future load growth or be avoided in new builds."
                )
                break
        if v_saving is None:
            st.info("Insufficient volume to match blended biogas with separate digestion "
                    "at the current WAS minimum HRT constraint.")

        st.caption(
            "**Assumptions:** PS designed for 12-day HRT (adequate for CSTR kinetics). "
            "WAS gets remaining volume. 30% PS yield uplift applied (empirical literature). "
            "CSTR first-order kinetics (Chen & Hashimoto). All values screening-grade ±15%."
        )
