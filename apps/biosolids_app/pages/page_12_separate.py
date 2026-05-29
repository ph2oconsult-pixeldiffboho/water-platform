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
    run_separate_analysis, vsr_cstr, vsr_batch,
    K_PS_CENTRAL, K_WAS_CENTRAL, K_BLEND_CENTRAL,
    Y_PS_SEP, Y_WAS, BIOPOINT_CALIBRATION,
)


# ── Chart helpers (all receive data as arguments — no globals) ─────────────

def _hrt_biogas_chart(ps_ds, was_ds, ps_ts, was_ts, ps_vs, was_vs,
                      ps_vol, was_vol, k_ps, k_was):
    hrts = list(range(5, 35))
    ps_cstr  = [vsr_cstr(k_ps,  h) * ps_ds  * (ps_vs/100) * 1000 * Y_PS_SEP * BIOPOINT_CALIBRATION for h in hrts]
    was_cstr = [vsr_cstr(k_was, h) * was_ds * (was_vs/100) * 1000 * Y_WAS   * BIOPOINT_CALIBRATION for h in hrts]
    ps_batch = [vsr_batch(k_ps, h) * ps_ds  * (ps_vs/100) * 1000 * Y_PS_SEP * BIOPOINT_CALIBRATION for h in hrts]

    ps_q  = ps_ds  / (ps_ts/100)  if ps_ts  > 0 else 1
    was_q = was_ds / (was_ts/100) if was_ts > 0 else 1
    hrt_ps_cur  = ps_vol  / ps_q
    hrt_was_cur = was_vol / was_q

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hrts, y=ps_cstr, name="PS — CSTR (separate)",
        line=dict(color="#0077b6", width=2.5)))
    fig.add_trace(go.Scatter(x=hrts, y=was_cstr, name="WAS — CSTR",
        line=dict(color="#52b788", width=2.5)))
    fig.add_trace(go.Scatter(x=hrts, y=ps_batch, name="PS — batch reference",
        line=dict(color="#0077b6", width=1.5, dash="dot"), opacity=0.5))

    for hrt, bg_list, col, label in [
        (hrt_ps_cur,  ps_cstr,  "#0077b6", "PS"),
        (hrt_was_cur, was_cstr, "#52b788", "WAS"),
    ]:
        idx = min(range(len(hrts)), key=lambda i: abs(hrts[i] - hrt))
        fig.add_vline(x=hrt, line_color=col, line_dash="dash", opacity=0.4)
        fig.add_annotation(x=hrt, y=bg_list[idx]*1.1, text=f"{label}: {hrt:.0f}d",
                           font=dict(size=10, color=col), showarrow=False)
    for xv, txt in [(10, "PS 10d<br>batch target"), (15, "WAS 15d<br>min")]:
        fig.add_vline(x=xv, line_color="grey", line_dash="dot", opacity=0.3)
        fig.add_annotation(x=xv, y=max(max(ps_cstr), max(was_cstr)) * 0.9,
                           text=txt, font=dict(size=9, color="grey"), showarrow=False)
    fig.update_layout(
        height=340, title="Biogas vs HRT by stream",
        xaxis_title="HRT (days)", yaxis_title="Stream biogas (Nm³/day)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=60, b=40, l=50, r=20),
        plot_bgcolor="#f8fafc", paper_bgcolor="white",
    )
    return fig


def _volume_optimisation_chart(ps_ds, was_ds, ps_ts, was_ts, ps_vs, was_vs,
                                v_total, k_ps, k_was):
    fracs = list(range(5, 95))
    bg_totals = []
    ps_q  = ps_ds  / (ps_ts/100)  if ps_ts  > 0 else 1
    was_q = was_ds / (was_ts/100) if was_ts > 0 else 1
    for frac in fracs:
        V_PS = v_total * frac / 100
        V_WAS = v_total - V_PS
        hps  = V_PS  / ps_q
        hwas = V_WAS / was_q
        if hps < 8 or hwas < 10:
            bg_totals.append(None)
        else:
            bps  = vsr_cstr(k_ps,  hps)  * ps_ds  * (ps_vs/100) * 1000 * Y_PS_SEP * BIOPOINT_CALIBRATION
            bwas = vsr_cstr(k_was, hwas) * was_ds * (was_vs/100) * 1000 * Y_WAS   * BIOPOINT_CALIBRATION
            bg_totals.append(bps + bwas)

    valid = [(f, v) for f, v in zip(fracs, bg_totals) if v is not None]
    best_frac = max(valid, key=lambda x: x[1])[0] if valid else 50
    ds_frac = ps_ds / (ps_ds + was_ds) * 100 if (ps_ds + was_ds) > 0 else 50

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fracs, y=bg_totals,
        line=dict(color="#0077b6", width=2.5),
        name="Total biogas",
        connectgaps=False,
    ))
    fig.add_vline(x=best_frac, line_color="#52b788", line_dash="dash",
                  annotation_text=f"Optimal {best_frac}% PS",
                  annotation_font=dict(size=10, color="#52b788"))
    fig.add_vline(x=ds_frac, line_color="#e57373", line_dash="dot",
                  annotation_text=f"DS-proportional {ds_frac:.0f}%",
                  annotation_font=dict(size=10, color="#e57373"))
    fig.update_layout(
        height=320, title="Total biogas vs PS volume fraction",
        xaxis_title="PS volume as % of total (%)",
        yaxis_title="Total biogas (Nm³/day)",
        margin=dict(t=50, b=40, l=50, r=20),
        plot_bgcolor="#f8fafc", paper_bgcolor="white",
    )
    return fig


def _vsr_chart(k_ps, k_was):
    hrts = list(range(5, 30))
    fig = go.Figure()
    for k, label, col in [
        (k_ps,             "PS (separate)",  "#0077b6"),
        (k_was,            "WAS",            "#52b788"),
        (K_BLEND_CENTRAL,  "Blended",        "#aaaaaa"),
    ]:
        fig.add_trace(go.Scatter(
            x=hrts, y=[vsr_cstr(k, h) * 100 for h in hrts],
            name=label, line=dict(color=col, width=2)))
    for xv, txt in [(10, "PS 10d"), (15, "WAS 15d min")]:
        fig.add_vline(x=xv, line_color="grey", line_dash="dot", opacity=0.4,
                      annotation_text=txt, annotation_font=dict(size=9))
    fig.update_layout(
        height=300, title="VSR vs HRT (CSTR model)",
        xaxis_title="HRT (days)", yaxis_title="VSR (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=50, b=40, l=50, r=20),
        plot_bgcolor="#f8fafc", paper_bgcolor="white",
    )
    return fig


# ── Page ──────────────────────────────────────────────────────────────────

def render():
    st.header("🔀 Separate vs Blended Digestion")
    st.caption(
        "Analyses the throughput and biogas impact of digesting PS and WAS in separate "
        "digesters vs a blended feed. Literature shows separate PS digestion yields ~30% "
        "more biogas per unit VS (Bolzonella 2005; Silvestre 2015; WEF MOP 8)."
    )

    with st.expander("📖 Kinetic model basis", expanded=False):
        st.markdown("""
**CSTR first-order model** (Chen & Hashimoto; Metcalf & Eddy 5th ed.):

VSR = 1 − 1/(1 + k × HRT)

| Stream | k central | Range | Rationale |
|--------|-----------|-------|-----------|
| PS (separate) | 0.25 /day | 0.20–0.35 | Lipid/carbohydrate substrate; no WAS inhibition |
| WAS | 0.12 /day | 0.08–0.15 | Cell wall hydrolysis rate-limiting |
| Blended | 0.13 /day | 0.10–0.18 | WAS-dominated kinetics |

**"PS >90% in 10 days"** refers to the *batch exponential* model (test condition, not CSTR design).
For continuous CSTR digesters, target HRT = 12–15 days for PS.

**30% yield uplift** is an empirical multiplier on PS biogas when digested separately.
        """)

    # ── Inputs ────────────────────────────────────────────────────────────
    st.subheader("Site inputs")
    ss = st.session_state

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Primary Sludge (PS)**")
        ps_ds  = st.number_input("PS dry solids (tDS/day)", 1.0, 500.0,
                    float(ss.get("mad_psDS", ss.get("cmp_ps_ds", 6.0))),
                    0.5, key="sep_ps_ds")
        ps_ts  = st.number_input("PS feed TS%", 1.0, 15.0,
                    float(ss.get("mad_psTS", ss.get("cmp_ps_ts", 4.0))),
                    0.1, key="sep_ps_ts")
        ps_vs  = st.number_input("PS volatile solids (% DS)", 50.0, 90.0,
                    float(ss.get("mad_psVS", ss.get("cmp_ps_vs", 75.0))),
                    0.5, key="sep_ps_vs")
        ps_vol = st.number_input("PS digester volume (m³)", 100.0, 200000.0,
                    float(ss.get("mad_psV", ss.get("cmp_ps_vol", 3000.0))),
                    100.0, format="%.0f", key="sep_ps_vol")

    with c2:
        st.markdown("**Waste Activated Sludge (WAS)**")
        was_ds = st.number_input("WAS dry solids (tDS/day)", 1.0, 500.0,
                    float(ss.get("mad_wasDS", ss.get("cmp_was_ds", 4.0))),
                    0.5, key="sep_was_ds")
        was_ts = st.number_input("WAS feed TS%", 0.5, 8.0,
                    float(ss.get("mad_wasTS", ss.get("cmp_was_ts", 4.0))),
                    0.1, key="sep_was_ts")
        was_vs = st.number_input("WAS volatile solids (% DS)", 50.0, 90.0,
                    float(ss.get("mad_wasVS", ss.get("cmp_was_vs", 70.0))),
                    0.5, key="sep_was_vs")
        was_vol = st.number_input("WAS digester volume (m³)", 100.0, 200000.0,
                    float(ss.get("mad_wasV", ss.get("cmp_was_vol", 1200.0))),
                    100.0, format="%.0f", key="sep_was_vol")

    v_total = ps_vol + was_vol

    # Advanced kinetics
    with st.expander("Advanced — kinetic constants", expanded=False):
        ka1, ka2 = st.columns(2)
        k_ps  = ka1.slider("k_PS (/day)",  0.15, 0.40, K_PS_CENTRAL,  0.01, key="sep_kps")
        k_was = ka2.slider("k_WAS (/day)", 0.06, 0.18, K_WAS_CENTRAL, 0.01, key="sep_kwas")
    # (sliders always render so these are always defined)

    st.divider()

    # Analysis mode
    mode_key = st.radio(
        "Analysis mode",
        ["separate", "optimised"],
        format_func=lambda k: {
            "separate":  "🔀 Separate — use the volumes entered above",
            "optimised": "⚙️  Optimise — find best volume split automatically",
        }[k],
        horizontal=True,
        key="sep_mode",
    )

    # ── Run analysis ──────────────────────────────────────────────────────
    r = run_separate_analysis(
        ps_ds_tpd=ps_ds, was_ds_tpd=was_ds,
        ps_ts_pct=ps_ts, was_ts_pct=was_ts,
        ps_vs_pct=ps_vs, was_vs_pct=was_vs,
        ps_volume_m3=ps_vol, was_volume_m3=was_vol,
        mode=mode_key,
        k_ps=k_ps, k_was=k_was,
    )

    # ── Summary metrics ───────────────────────────────────────────────────
    st.subheader("Results")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Blended biogas",  f"{r.blend_biogas:,.0f}", "Nm³/day")
    m2.metric("Separate biogas",
              f"{r.sep_biogas:,.0f}" if r.sep_biogas else "—",
              f"+{r.sep_biogas - r.blend_biogas:,.0f} Nm³/d" if r.sep_biogas else None)
    m3.metric("Biogas uplift",
              f"+{r.biogas_uplift_pct:.1f}%" if r.sep_biogas else "—",
              f"range {r.biogas_uplift_lo_pct:.1f}–{r.biogas_uplift_hi_pct:.1f}%")
    if r.ps:
        m4.metric("PS HRT", f"{r.ps.hrt_days:.1f} days",
                  "✓ <15d" if r.ps.hrt_days < 15 else "⚠ >15d")
        m5.metric("WAS HRT", f"{r.was.hrt_days:.1f} days",
                  "✓ ≥15d" if r.was.hrt_days >= 15 else "⚠ below 15d")

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_compare, tab_streams, tab_throughput, tab_optimise = st.tabs([
        "📊 Comparison", "🧪 Stream Detail", "📈 Throughput", "⚙️ Volume Optimiser",
    ])

    # ── TAB 1: Comparison ─────────────────────────────────────────────────
    with tab_compare:
        if not r.ps:
            st.info("No separate results yet — run with Separate or Optimise mode.")
        else:
            ca, cb = st.columns(2)
            with ca:
                st.markdown("**Blended digestion**")
                st.metric("HRT",             f"{r.blend_hrt:.1f} days")
                st.metric("Combined VSR",    f"{r.blend_vsr_pct:.1f}%")
                st.metric("Biogas",          f"{r.blend_biogas:,.0f} Nm³/day")
                st.metric("Net electricity", f"{r.blend_elec_kw:,.0f} kW")
                st.metric("Wet cake",        f"{r.blend_cake_tpd:.1f} t/day")
            with cb:
                st.markdown("**Separate digestion**")
                st.metric("PS HRT",          f"{r.ps.hrt_days:.1f} days")
                st.metric("WAS HRT",         f"{r.was.hrt_days:.1f} days")
                st.metric("Biogas",          f"{r.sep_biogas:,.0f} Nm³/day",
                          f"+{r.sep_biogas-r.blend_biogas:,.0f} ({r.biogas_uplift_pct:+.1f}%)")
                st.metric("Net electricity", f"{r.sep_elec_kw:,.0f} kW",
                          f"+{r.elec_uplift_kw:,.0f} kW")
                st.metric("Wet cake",        f"{r.sep_cake_tpd:.1f} t/day")
            st.caption(
                f"Biogas uplift sensitivity: {r.biogas_uplift_lo_pct:.1f}–"
                f"{r.biogas_uplift_hi_pct:.1f}% (literature kinetic constant range). "
                "30% PS yield uplift factor applied per Bolzonella 2005 / Silvestre 2015. "
                "All values screening-grade ±15%."
            )

    # ── TAB 2: Stream Detail ───────────────────────────────────────────────
    with tab_streams:
        if not r.ps:
            st.info("Run analysis first.")
        else:
            cp, cw = st.columns(2)
            for col, stream, label in [
                (cp, r.ps,  "Primary Sludge (PS)"),
                (cw, r.was, "Waste Activated Sludge (WAS)"),
            ]:
                with col:
                    st.markdown(f"**{label}**")
                    ts = ps_ts if stream.stream == "PS" else was_ts
                    q  = stream.ds_tpd / (ts / 100) if ts > 0 else 0
                    for k, v in {
                        "Dry solids (tDS/day)":   f"{stream.ds_tpd:.1f}",
                        "Feed volume (m³/day)":   f"{q:.0f}",
                        "Digester volume (m³)":   f"{stream.volume_m3:,.0f}",
                        "HRT (days)":             f"{stream.hrt_days:.1f}",
                        "VS loading (kgVS/m³/d)": f"{stream.vs_loading_kgVS_m3_d:.2f}",
                        "VSR (CSTR)":             f"{stream.vsr_pct:.1f}%",
                        "Biogas (Nm³/day)":       f"{stream.biogas_nm3d:,.0f}",
                        "Electricity (kW)":       f"{stream.elec_gross_kw:,.0f}",
                        "Wet cake (t/day)":       f"{stream.wet_cake_tpd:.1f}",
                        "k used (/day)":          f"{stream.k_used:.2f}",
                    }.items():
                        st.markdown(f"**{k}:** {v}")
                    if stream.stream == "PS":
                        st.markdown("**Yield uplift:** ×1.30 (separate, literature)")

            st.divider()
            st.plotly_chart(
                _vsr_chart(k_ps, k_was),
                use_container_width=True,
            )

    # ── TAB 3: Throughput ──────────────────────────────────────────────────
    with tab_throughput:
        st.subheader("Throughput Capacity")
        st.markdown(
            "Given the current digester volumes, how does separating streams "
            "affect capacity for load growth?"
        )

        ps_q_flow  = ps_ds  / (ps_ts/100)  if ps_ts  > 0 else 1
        was_q_flow = was_ds / (was_ts/100) if was_ts > 0 else 1

        # Volume freed if PS at 15d
        v_ps_for_15d = ps_q_flow * 15
        vol_freed = ps_vol - v_ps_for_15d

        if vol_freed > 0:
            st.success(
                f"At 15d PS HRT, PS digesters need only {v_ps_for_15d:,.0f} m³. "
                f"**{vol_freed:,.0f} m³** is freed ({vol_freed/8000:.1f}× 8,000 m³ digesters) "
                f"for WAS, new load, or to avoid in new builds."
            )

        t1, t2, t3 = st.columns(3)
        t1.metric("PS HRT",  f"{r.ps.hrt_days:.1f}d" if r.ps else "—",
                  "✓ below 15d" if r.ps and r.ps.hrt_days < 15 else "⚠ above 15d")
        t2.metric("WAS HRT", f"{r.was.hrt_days:.1f}d" if r.was else "—",
                  "✓ ≥15d" if r.was and r.was.hrt_days >= 15 else "⚠ below 15d min")
        t3.metric("Volume freed (PS@15d)", f"{max(0, vol_freed):,.0f} m³",
                  f"{max(0, vol_freed)/8000:.1f}× 8,000 m³")

        st.divider()
        st.markdown("**Capacity scenarios at current total volume**")
        import pandas as pd
        rows = []
        for label, V_PS_s, V_WAS_s in [
            ("Blended (current)",        v_total, 0),
            ("Separate (entered above)", ps_vol,  was_vol),
            ("PS at 10d, WAS gets rest", ps_q_flow * 10, v_total - ps_q_flow * 10),
            ("PS at 12d, WAS gets rest", ps_q_flow * 12, v_total - ps_q_flow * 12),
            ("PS at 15d, WAS gets rest", ps_q_flow * 15, v_total - ps_q_flow * 15),
        ]:
            if V_WAS_s < was_q_flow * 10: continue
            h_ps  = v_total / (ps_q_flow + was_q_flow) if label == "Blended (current)" \
                    else (V_PS_s / ps_q_flow if ps_q_flow > 0 else 0)
            h_was = v_total / (ps_q_flow + was_q_flow) if label == "Blended (current)" \
                    else (V_WAS_s / was_q_flow if was_q_flow > 0 else 0)
            ps_max  = V_PS_s  / 10 * (ps_ts/100)  * 1000 * 365 / 1000 if V_PS_s  > 0 else 0
            was_max = V_WAS_s / 15 * (was_ts/100) * 1000 * 365 / 1000 if V_WAS_s > 0 else 0
            rows.append({
                "Scenario":      label,
                "PS HRT (d)":    f"{h_ps:.1f}",
                "WAS HRT (d)":   f"{h_was:.1f}",
                "PS max (tDS/yr)":  f"{ps_max:,.0f}" if label != "Blended (current)" else "—",
                "WAS max (tDS/yr)": f"{was_max:,.0f}" if label != "Blended (current)" else "—",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("Min HRT assumptions: PS=10d, WAS=15d. Capacity = volume ÷ HRT_min × TS% × 1000 × 365. Screening-grade ±20%.")

        st.divider()
        st.plotly_chart(
            _hrt_biogas_chart(ps_ds, was_ds, ps_ts, was_ts, ps_vs, was_vs,
                              ps_vol, was_vol, k_ps, k_was),
            use_container_width=True,
        )

    # ── TAB 4: Volume Optimiser ────────────────────────────────────────────
    with tab_optimise:
        st.subheader("Volume Optimiser")
        st.markdown(
            "Find the optimal V_PS : V_WAS allocation to maximise total biogas, "
            "and the minimum total volume needed to match blended biogas with separate digestion."
        )
        st.plotly_chart(
            _volume_optimisation_chart(ps_ds, was_ds, ps_ts, was_ts, ps_vs, was_vs,
                                       v_total, k_ps, k_was),
            use_container_width=True,
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
            st.info("Switch to **Optimise** mode above to run the optimiser.", icon="💡")

        st.divider()
        st.markdown("**Volume saving: match blended biogas with separate digestion**")
        ps_q_flow2 = ps_ds / (ps_ts/100) if ps_ts > 0 else 1
        was_q_flow2 = was_ds / (was_ts/100) if was_ts > 0 else 1
        for V_WAS_try in range(int(v_total * 0.1), int(v_total) + 500, 500):
            V_PS_try = ps_q_flow2 * 12
            hrt_w = V_WAS_try / was_q_flow2 if was_q_flow2 > 0 else 0
            if hrt_w < 10: continue
            bg_try = (vsr_cstr(k_ps,  12)    * ps_ds  * (ps_vs/100)  * 1000 * Y_PS_SEP * BIOPOINT_CALIBRATION +
                      vsr_cstr(k_was, hrt_w) * was_ds * (was_vs/100) * 1000 * Y_WAS   * BIOPOINT_CALIBRATION)
            if bg_try >= r.blend_biogas:
                v_tot_new = V_PS_try + V_WAS_try
                saving = v_total - v_tot_new
                if saving > 0:
                    st.success(
                        f"With PS@12d HRT ({V_PS_try:,.0f} m³) + WAS@{hrt_w:.1f}d HRT "
                        f"({V_WAS_try:,} m³): total **{v_tot_new:,.0f} m³** achieves the "
                        f"same biogas as blended. Saves **{saving:,.0f} m³** "
                        f"({saving/8000:.1f}× 8,000 m³ digesters) vs blended design."
                    )
                else:
                    st.info("Separate digestion requires similar total volume to blended "
                            "at the current inputs.")
                break

        st.caption(
            "PS designed for 12-day CSTR HRT (adequate for PS kinetics). "
            "WAS gets remaining volume. 30% PS yield uplift applied (empirical literature). "
            "All values screening-grade ±15%."
        )
