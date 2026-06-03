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
    F_BIO_PS, F_BIO_WAS, VS_SPLIT_PS,
    Y_PS_SEP, Y_WAS, BIOPOINT_CALIBRATION,
    bmp_biogas_comparison, BMP_PS_ML_G, BMP_WAS_ML_G, BMP_WAS_THP_ML_G, BMP_BLEND_ML_G,
    separate_scenario, tradeoff_sweep, F_BIO_WAS_THP,
    hrt_limited_diagnosis, recuperative_value, SRT_PLATEAU_WAS,
)


# ── Chart helpers (all receive data as arguments — no globals) ─────────────

def _hrt_biogas_chart(ps_ds, was_ds, ps_ts, was_ts, ps_vs, was_vs,
                      ps_vol, was_vol, k_ps, k_was):
    hrts = list(range(5, 35))
    ps_cstr  = [vsr_cstr(k_ps,  h, F_BIO_PS)  * ps_ds  * (ps_vs/100) * 1000 * Y_PS_SEP * BIOPOINT_CALIBRATION for h in hrts]
    was_cstr = [vsr_cstr(k_was, h, F_BIO_WAS) * was_ds * (was_vs/100) * 1000 * Y_WAS   * BIOPOINT_CALIBRATION for h in hrts]
    ps_batch = [vsr_batch(k_ps, h, F_BIO_PS)  * ps_ds  * (ps_vs/100) * 1000 * Y_PS_SEP * BIOPOINT_CALIBRATION for h in hrts]

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
    for xv, txt in [(10, "PS 10d<br>fast"), (12, "WAS 12d<br>floor")]:
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
            bps  = vsr_cstr(k_ps,  hps,  F_BIO_PS)  * ps_ds  * (ps_vs/100) * 1000 * Y_PS_SEP * BIOPOINT_CALIBRATION
            bwas = vsr_cstr(k_was, hwas, F_BIO_WAS) * was_ds * (was_vs/100) * 1000 * Y_WAS   * BIOPOINT_CALIBRATION
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
    for k, fb, label, col in [
        (k_ps,  F_BIO_PS,  "PS (separate)",         "#0077b6"),
        (k_was, F_BIO_WAS, "WAS (ceiling-limited)", "#52b788"),
    ]:
        fig.add_trace(go.Scatter(
            x=hrts, y=[vsr_cstr(k, h, fb) * 100 for h in hrts],
            name=label, line=dict(color=col, width=2)))
    fig.add_trace(go.Scatter(
        x=hrts,
        y=[(VS_SPLIT_PS * vsr_cstr(k_ps, h, F_BIO_PS)
            + (1 - VS_SPLIT_PS) * vsr_cstr(k_was, h, F_BIO_WAS)) * 100 for h in hrts],
        name="Blended", line=dict(color="#aaaaaa", width=2)))
    for xv, txt in [(10, "PS fast"), (12, "WAS 12d floor")]:
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


def _tradeoff_chart(sweep, cur_hrt, cur_ch4):
    hs=[p[0] for p in sweep]; ch4=[p[1] for p in sweep]; freed=[p[2] for p in sweep]
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=hs,y=ch4,name="Biomethane (m³ CH4/d)",
                             line=dict(color="#0077b6",width=2),yaxis="y"))
    fig.add_trace(go.Scatter(x=hs,y=freed,name="Freed volume (m³)",
                             line=dict(color="#e76f51",width=2,dash="dot"),yaxis="y2"))
    fig.add_trace(go.Scatter(x=[cur_hrt],y=[cur_ch4],mode="markers",
                             marker=dict(size=11,color="#0077b6"),showlegend=False))
    fig.update_layout(height=320,title="Biogas vs capacity (sweep WAS HRT; dot = selected)",
        xaxis_title="WAS HRT (days)",
        yaxis=dict(title="Biomethane m³ CH4/d"),
        yaxis2=dict(title="Freed volume m³",overlaying="y",side="right",showgrid=False,zeroline=True),
        legend=dict(orientation="h",yanchor="bottom",y=1.02),
        margin=dict(t=50,b=40,l=55,r=55),plot_bgcolor="#f8fafc",paper_bgcolor="white")
    return fig


# ── Page ──────────────────────────────────────────────────────────────────

def render():
    st.header("🔀 Separate vs Blended Digestion")
    st.caption(
        "Analyses the throughput and capacity impact of digesting PS and WAS in separate "
        "digesters vs a blended feed, on the V2 BMP basis. The benefit is mainly FREED "
        "CAPACITY, not more biogas: PS reaches its high biodegradable ceiling quickly at "
        "short HRT, while WAS is ceiling-limited and gains little from long retention."
    )

    with st.expander("📖 Kinetic model basis", expanded=False):
        st.markdown("""
**Ceiling-limited CSTR model** (BMP-fitted; the V2 spine is the source of truth):

VSR = f_bio x (k x HRT) / (1 + k x HRT)

| Stream | k (BMP) | f_bio ceiling | Behaviour |
|--------|---------|---------------|-----------|
| PS  | 0.29 /day | 0.97 | high ceiling, reached fast |
| WAS | 0.38 /day | 0.31 | hydrolyses AS FAST AS PS, but only ~1/3 is biodegradable |

WAS is **ceiling-limited, not rate-limited**: it reaches its low biodegradable ceiling
quickly, so extra HRT adds little. This overturns the older "WAS needs long HRT because
hydrolysis is slow" model (the prior k_WAS 0.12, no ceiling).

The separate-digestion advantage is therefore **freed volume** (run PS at a short HRT; give
WAS only its floor), not a biogas uplift. The old empirical x1.30 PS uplift is removed - the
high PS ceiling (0.97 vs WAS 0.31) already expresses that difference. (At Mangere/ETP;
plant-specific until a local BMP - older / colder / industrial WAS can be genuinely slow.)
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
        k_ps  = ka1.slider("k_PS (/day)",  0.20, 0.40, K_PS_CENTRAL,  0.01, key="sep_kps")
        k_was = ka2.slider("k_WAS (/day)", 0.25, 0.50, K_WAS_CENTRAL, 0.01, key="sep_kwas")
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

    # ── Separate digestion: biogas vs capacity (HRT-driven, CHE4180 BMP curves) ──
    vs_ps_t  = ps_ds  * ps_vs  / 100.0
    vs_was_t = was_ds * was_vs / 100.0
    ps_flow  = ps_ds  / (ps_ts  / 100.0) if ps_ts  > 0 else 0.0
    was_flow = was_ds / (was_ts / 100.0) if was_ts > 0 else 0.0
    installed_vol = ps_vol + was_vol      # total existing tankage

    st.markdown("**Operating point — pick the HRTs; biogas comes off the BMP curves, volume off the HRT**")
    hc1, hc2, hc3 = st.columns(3)
    hrt_ps  = hc1.slider("TPS HRT (days)", 6.0, 25.0, 10.0, 0.5, key="sep_hrt_ps",
                         help="PS reaches ~94% of its 470 BMP by 10 d, ~96% by 12 d (CHE4180 curve).")
    hrt_was = hc2.slider("WAS HRT (days)", 8.0, 30.0, 18.0, 0.5, key="sep_hrt_was",
                         help="WAS is at its ceiling by ~15-18 d.")
    recup = hc3.checkbox("Recuperative thickening (WAS)", value=False, key="sep_recup",
                         help="Decouples WAS SRT from HRT: holds the biology at a target SRT while the HRT "
                              "(and volume) drops, keeping WAS gas at a fraction of the tankage.")
    recup_srt = hc3.slider("WAS target SRT (days)", 12.0, 25.0, 18.0, 0.5,
                           key="sep_recup_srt") if recup else None
    ss_on = st.checkbox(
        "Add SolidStream THP on the WAS stream (additional, inferred, confidence D)",
        value=False, key="sep_solidstream",
        help="Lifts ONLY the WAS BMP from the measured 152 to an inferred ~320 mL CH4/gVS, backed out of "
             "the Cambi 0.703 overall VSR (ETP). PS is untouched. Cross-plant transfer, unproven at this plant.",
    )
    scn = separate_scenario(vs_ps_t, vs_was_t, ps_flow, was_flow, installed_vol,
                            hrt_ps_d=hrt_ps, hrt_was_d=hrt_was, solidstream=ss_on,
                            recup_was_srt_d=recup_srt)

    st.subheader("Results — biogas vs capacity")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Blended (base case)", f"{scn['ch4_blend_m3d']:,.0f}", "m³ CH4/d · BMP 258")
    m2.metric("Separate biomethane", f"{scn['ch4_sep_m3d']:,.0f}",
              f"+{scn['ch4_sep_m3d']-scn['ch4_blend_m3d']:,.0f} ({scn['uplift_pct']:+.0f}%)")
    m3.metric("Freed digester volume", f"{scn['freed_vol_m3']:,.0f}",
              f"{scn['freed_vol_pct']:+.0f}% of installed")
    m4.metric("WAS SRT / HRT", f"{scn['srt_was_d']:.0f} / {scn['hrt_was_d']:.0f} d",
              "recuperative" if scn['recup'] else "SRT = HRT")
    st.caption(
        f"Biogas is read off the CHE4180 BMP curves at each stream's retention (PS {scn['bmp_realised_ps_pct']:.0f}% "
        f"of its 470 ceiling at {hrt_ps:.0f} d; WAS {scn['bmp_realised_was_pct']:.0f}% of {scn['was_bmp_used']:.0f} "
        f"at {scn['srt_was_d']:.0f} d). Volume is set by HRT, so dropping HRT frees tankage but gives up a little "
        "biogas — the trade-off chart below. Recuperative thickening breaks the trade-off by holding WAS SRT while "
        "the HRT drops; SolidStream THP raises the WAS ceiling (inferred, confidence D). The blended base case (258) "
        "is depressed by real-plant losses per the CHE4180 note, so part of the uplift recovers that, not separation alone."
    )

    # ── Recuperative thickening only pays when HRT-limited below the BMP plateau ──
    diag = hrt_limited_diagnosis(ps_flow, was_flow, installed_vol, srt_ps_d=hrt_ps, srt_was_d=18.0)
    if diag["hrt_limited"]:
        st.warning(
            f"**HRT-limited.** The biogas-adequate split (PS {hrt_ps:.0f} d / WAS 18 d) needs "
            f"{diag['required_vol_m3']:,.0f} m³ but only {installed_vol:,.0f} m³ is installed "
            f"(deficit {diag['deficit_m3']:,.0f} m³). The highest WAS SRT you can reach hydraulically is "
            f"{diag['was_srt_achievable_d']:.1f} d. This is the regime where recuperative thickening earns its "
            "place — it lets you free volume without dropping the SRT (and biogas) you need."
        )
    else:
        st.info(
            f"**Not HRT-limited.** The biogas-adequate split fits in {installed_vol:,.0f} m³ with "
            f"{diag['surplus_m3']:,.0f} m³ to spare (WAS SRT {diag['was_srt_achievable_d']:.1f} d achievable, well "
            f"past the ~{SRT_PLATEAU_WAS:.0f} d plateau). Recuperative thickening adds no biogas here — it would only "
            "free volume you don't currently need. Its benefit with respect to biogas is negligible."
        )
    if recup:
        rv = recuperative_value(vs_was_t, was_flow, hrt_was, recup_srt, solidstream=ss_on)
        rc1, rc2 = st.columns(2)
        rc1.metric("Recup. biogas preserved", f"{rv['biogas_benefit_m3d']:+,.0f} m³ CH4/d",
                   f"{rv['biogas_benefit_pct_of_was']:+.1f}% on WAS")
        rc2.metric("WAS volume saved", f"{rv['vol_saved_m3']:,.0f} m³",
                   f"hold SRT {recup_srt:.0f} d at HRT {hrt_was:.0f} d")
        if rv["below_plateau"]:
            st.caption(
                f"WAS HRT {hrt_was:.0f} d is **below the ~{SRT_PLATEAU_WAS:.0f} d plateau**, so recuperative thickening "
                f"is doing real work: holding WAS SRT at {recup_srt:.0f} d preserves {rv['biogas_benefit_m3d']:,.0f} m³ "
                f"CH4/d that running SRT = HRT would lose, while freeing {rv['vol_saved_m3']:,.0f} m³. At a genuinely "
                "HRT-limited plant this is the unlock; the freed volume is worth pursuing if you need it for load "
                "growth, co-feed, or deferring tankage."
            )
        else:
            st.caption(
                f"WAS HRT {hrt_was:.0f} d is **at/above the ~{SRT_PLATEAU_WAS:.0f} d plateau**, so SRT = HRT already "
                f"reaches the biogas ceiling — recuperative thickening's biogas benefit is negligible "
                f"({rv['biogas_benefit_pct_of_was']:+.1f}% on WAS). Push the WAS HRT below the plateau before it starts "
                "preserving biogas; above it, recuperative thickening only frees volume."
            )

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_compare, tab_streams, tab_throughput, tab_optimise = st.tabs([
        "📊 Comparison", "🧪 Stream Detail", "📈 Throughput", "⚙️ Volume Optimiser",
    ])

    # ── TAB 1: Comparison ─────────────────────────────────────────────────
    with tab_compare:
        sweep = tradeoff_sweep(vs_ps_t, vs_was_t, ps_flow, was_flow, installed_vol,
                               hrt_ps_d=hrt_ps, solidstream=ss_on, recup_was_srt_d=recup_srt)
        st.plotly_chart(_tradeoff_chart(sweep, scn["hrt_was_d"], scn["ch4_sep_m3d"]),
                        use_container_width=True)
        ca, cb = st.columns(2)
        with ca:
            st.markdown("**Blended (current plant)**")
            st.metric("Biomethane",      f"{scn['ch4_blend_m3d']:,.0f} m³ CH4/d")
            st.metric("Blended HRT",      f"{r.blend_hrt:.1f} days")
            st.metric("Installed volume", f"{installed_vol:,.0f} m³")
        with cb:
            st.markdown("**Separate (your operating point)**")
            st.metric("Biomethane",  f"{scn['ch4_sep_m3d']:,.0f} m³ CH4/d",
                      f"+{scn['ch4_sep_m3d']-scn['ch4_blend_m3d']:,.0f} ({scn['uplift_pct']:+.0f}%)")
            st.metric("Volume used", f"{scn['vol_sep_m3']:,.0f} m³",
                      f"freed {scn['freed_vol_m3']:+,.0f}")
            st.metric("PS / WAS HRT", f"{scn['hrt_ps_d']:.0f} / {scn['hrt_was_d']:.0f} d")
        st.caption(
            "Longer HRT pushes biomethane toward the +28% ceiling (CHE4180) but needs more tankage; shorter HRT "
            "frees volume at a small biogas cost. Recuperative thickening lifts the freed-volume curve at constant "
            "biogas (holds WAS SRT while the HRT drops); SolidStream lifts the biomethane curve. The dot marks your "
            "selected WAS HRT. This tab is driven by the HRT sliders above, independent of the mode selector (which "
            "drives the Stream Detail / Throughput / Volume Optimiser tabs)."
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
                        "Biomethane (m³ CH4/d)":  f"{stream.vs_tpd * (BMP_PS_ML_G if stream.stream=='PS' else scn['was_bmp_used']):,.0f}",
                        "Electricity (kW)":       f"{stream.elec_gross_kw:,.0f}",
                        "Wet cake (t/day)":       f"{stream.wet_cake_tpd:.1f}",
                        "k used (/day)":          f"{stream.k_used:.2f}",
                    }.items():
                        st.markdown(f"**{k}:** {v}")
                    if stream.stream == "PS":
                        st.markdown(f"**BMP:** {BMP_PS_ML_G:.0f} mL CH4/gVS (f_bio 0.97, high - CHE4180)")
                    else:
                        _tag = "THP-lifted, inferred conf. D" if scn['solidstream'] else "raw, measured CHE4180"
                        st.markdown(f"**BMP:** {scn['was_bmp_used']:.0f} mL CH4/gVS ({_tag})")

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
                  "✓ ≥12d" if r.was and r.was.hrt_days >= 12 else "⚠ below 12d floor")
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
            was_max = V_WAS_s / 12 * (was_ts/100) * 1000 * 365 / 1000 if V_WAS_s > 0 else 0
            rows.append({
                "Scenario":      label,
                "PS HRT (d)":    f"{h_ps:.1f}",
                "WAS HRT (d)":   f"{h_was:.1f}",
                "PS max (tDS/yr)":  f"{ps_max:,.0f}" if label != "Blended (current)" else "—",
                "WAS max (tDS/yr)": f"{was_max:,.0f}" if label != "Blended (current)" else "—",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("Min HRT assumptions: PS=10d, WAS=12d (V2 floor). Capacity = volume / HRT_min x TS% x 1000 x 365. Screening-grade.")

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
            "PS designed for a 12-day CSTR HRT (adequate for PS kinetics). WAS gets the "
            "remaining volume. Capacity is the robust separate-digestion benefit; the biomethane "
            "uplift is shown on the Comparison tab (CHE4180 per-stream BMP). Values screening-grade."
        )
