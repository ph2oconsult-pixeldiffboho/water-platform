"""
apps/biosolids_app/pages/page_07_mad.py
BioPoint V1 — MAD Analyser (standalone).

Runs the MAD engine directly without requiring the full BioPoint
pathway analysis. User configures digester geometry, feed quality,
mixing system, and chemistry; gets full diagnostic output immediately.

All inputs are independent of the main BioPoint inputs page.
"""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from engine.mad import MADInputs, run_mad


# ── Status colour helpers ──────────────────────────────────────────────────
STATUS_COLOURS = {
    "SAFE":    ("🟢", "success"),
    "WATCH":   ("🟡", "warning"),
    "LIMITING":("🟠", "warning"),
    "FAILURE": ("🔴", "error"),
}
FEASIBILITY_COLOURS = {
    "FEASIBLE":   "🟢",
    "MARGINAL":   "🟡",
    "INFEASIBLE": "🔴",
}


def _status_display(status: str) -> str:
    icon, _ = STATUS_COLOURS.get(status, ("⬜", "info"))
    return f"{icon} **{status}**"


def _show_status(status: str, label: str = ""):
    icon, kind = STATUS_COLOURS.get(status, ("⬜", "info"))
    text = f"{icon} **{label + ': ' if label else ''}{status}**"
    if kind == "success":  st.success(text)
    elif kind == "error":  st.error(text)
    else:                  st.warning(text)


def render():
    st.header("🔬 MAD Analyser")
    st.caption(
        "Standalone mesophilic anaerobic digestion diagnostic. "
        "Configure your digester directly and run the MAD engine "
        "independently of the pathway rankings. "
        "Screening-grade — 85–91/100 confidence."
    )
    st.divider()

    # ── INPUTS ──────────────────────────────────────────────────────────────
    with st.expander("⚙️ Configure digester inputs", expanded=True):
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**Feed — Primary Sludge (PS)**")
            psV  = st.number_input("PS digester volume (m³)", 100.0, 500000.0,
                                   st.session_state.get("mad_psV", 3000.0), step=100.0, key="mad_psV")
            psDS = st.number_input("PS dry solids (tDS/day)", 0.1, 500.0,
                                   st.session_state.get("mad_psDS", 6.0), step=0.5, key="mad_psDS")
            psTS = st.number_input("PS feed TS (%)", 1.0, 10.0,
                                   st.session_state.get("mad_psTS", 4.0), step=0.5, key="mad_psTS",
                                   help="Typical 3–5% for thickened PS")
            psVS = st.number_input("PS volatile solids (% of DS)", 45.0, 90.0,
                                   st.session_state.get("mad_psVS", 75.0), step=1.0, key="mad_psVS")
            psN  = st.number_input("PS nitrogen (% of DS)", 1.0, 8.0,
                                   st.session_state.get("mad_psN", 3.0), step=0.1, key="mad_psN",
                                   help="Typical 2.5–3.5% for primary sludge")

            st.markdown("**Recup — PS**")
            psCap  = st.number_input("PS recup capture (%)", 50.0, 99.0,
                                     st.session_state.get("mad_psCap", 85.0), step=1.0, key="mad_psCap")
            psBeta = st.number_input("PS beta (recirculation ratio)", 1.0, 5.0,
                                     st.session_state.get("mad_psBeta", 1.5), step=0.1, key="mad_psBeta",
                                     help="Ratio of withdrawal flow to feed flow")

        with c2:
            st.markdown("**Feed — Waste Activated Sludge (WAS)**")
            wasV  = st.number_input("WAS digester volume (m³)", 100.0, 200000.0,
                                    st.session_state.get("mad_wasV", 1200.0), step=100.0, key="mad_wasV")
            wasDS = st.number_input("WAS dry solids (tDS/day)", 0.1, 300.0,
                                    st.session_state.get("mad_wasDS", 4.0), step=0.5, key="mad_wasDS")
            wasTS = st.number_input("WAS feed TS (%)", 1.0, 10.0,
                                    st.session_state.get("mad_wasTS", 4.0), step=0.5, key="mad_wasTS",
                                    help="Typical 3–5% for thickened WAS")
            wasVS = st.number_input("WAS volatile solids (% of DS)", 45.0, 90.0,
                                    st.session_state.get("mad_wasVS", 70.0), step=1.0, key="mad_wasVS")
            wasN  = st.number_input("WAS nitrogen (% of DS)", 3.0, 20.0,
                                    st.session_state.get("mad_wasN", 8.5), step=0.1, key="mad_wasN",
                                    help="Typical 7–12% municipal, up to 15% industrial")

            st.markdown("**Recup — WAS**")
            wasCap  = st.number_input("WAS recup capture (%)", 50.0, 99.0,
                                      st.session_state.get("mad_wasCap", 85.0), step=1.0, key="mad_wasCap")
            wasBeta = st.number_input("WAS beta", 1.0, 5.0,
                                      st.session_state.get("mad_wasBeta", 2.5), step=0.1, key="mad_wasBeta",
                                      help="Operating window typically 2.0–2.5")

        with c3:
            st.markdown("**Mixing system**")
            mixing_sys = st.selectbox("Mixing system type",
                ["mechanical", "gas", "draftTube", "staged"],
                index=["mechanical","gas","draftTube","staged"].index(
                    st.session_state.get("mad_mix_sys", "mechanical")),
                key="mad_mix_sys",
                help="gas = gas recirculation, draftTube = forced recirculation, staged = plug-flow approx")
            mixing_power = st.number_input("Mixing power (W/m³)", 1.0, 50.0,
                                           st.session_state.get("mad_mix_pwr", 15.0),
                                           step=1.0, key="mad_mix_pwr",
                                           help="Typical 8–15 W/m³")
            mixing_scale = st.number_input("Mixing scale factor", 0.5, 2.0,
                                           st.session_state.get("mad_mix_scale", 1.0),
                                           step=0.05, key="mad_mix_scale",
                                           help="0.75 = efficient, 1.0 = nominal, 1.25 = pessimistic")

            st.markdown("**Chemistry**")
            digester_pH = st.number_input("Digester pH", 6.8, 7.8,
                                          st.session_state.get("mad_pH", 7.25),
                                          step=0.05, key="mad_pH")
            ph_control = st.selectbox("pH control",
                ["off", "on"], key="mad_ph_ctrl",
                help="'on' clamps pH ≤ 7.30 within ±0.30 capability")
            nh3_mode = st.selectbox("NH3 acclimation mode",
                ["acclimated", "conservative", "thp", "custom"],
                key="mad_nh3_mode",
                help="Sets K_I inhibition constant. acclimated=0.70, conservative=0.40, thp=0.85")
            ki_custom = None
            if nh3_mode == "custom":
                ki_custom = st.number_input("Custom K_I (g NH3-N/L)", 0.1, 2.0, 0.70, step=0.05)

            st.markdown("**THP Options**")
            pretreatment = st.selectbox(
                "Pretreatment",
                ["none", "thp", "solidstream"],
                format_func=lambda x: {
                    "none":        "None — conventional AD",
                    "thp":         "Pre-digestion THP",
                    "solidstream": "SolidStream (post-digestion THP)",
                }[x],
                key="mad_pretreat",
                help="THP configuration. Pre-digestion THP processes feed BEFORE digesters. "
                     "SolidStream processes digestate AFTER existing digesters."
            )
            if pretreatment == "thp":
                st.info(
                    "**Pre-digestion THP** — thermal hydrolysis applied to raw sludge "
                    "before anaerobic digestion. Cell disintegration occurs before "
                    "digestion, allowing higher loading rates and reducing required "
                    "digester volume. Biogas uplift ~40–50% vs conventional AD. "
                    "Kinetic boost: k × 1.35."
                )
            elif pretreatment == "solidstream":
                st.info(
                    "**SolidStream (post-digestion THP)** — thermal hydrolysis applied "
                    "to digestate from existing digesters. Does **not** reduce digester "
                    "volume. Primary benefits: dewatered cake ≥38% DS (no thermal drying "
                    "required), full pathogen kill, 50–57% cake volume reduction, and "
                    "~22.7% biogas uplift from COD-rich centrate recycled to digesters. "
                    "Minimum 15d HRT required.  \n"
                    "_Source: Cambi Melbourne ETP memo 20.05.2026; "
                    "Antwerp Schijnpoort 2025 operational._"
                )
                # Auto-set NH3 mode to thp for both THP configurations
            if pretreatment in ("thp", "solidstream"):
                if nh3_mode != "thp":
                    st.caption(
                        "💡 NH₃ acclimation mode auto-recommended as **thp** "
                        "for THP configurations (K_I = 0.85 g NH₃-N/L)."
                    )
            trade_waste  = st.selectbox("Trade waste classification",
                ["normal", "industrial"], key="mad_trade",
                help="Industrial sets WAS N% baseline ≥ 11%")
            final_cap = st.number_input("Final dewatering capture (%)", 70.0, 99.0,
                                        st.session_state.get("mad_final_cap", 92.0),
                                        step=1.0, key="mad_final_cap",
                                        help="Separate from recup-loop capture. Affects centrate N split.")

            st.markdown("**CHP**")
            chp_eff   = st.number_input("CHP electrical efficiency (%)", 25.0, 55.0,
                                        st.session_state.get("mad_chp_eff", 40.0),
                                        step=1.0, key="mad_chp_eff")
            chp_avail = st.number_input("CHP availability (%)", 60.0, 98.0,
                                        st.session_state.get("mad_chp_avail", 88.0),
                                        step=1.0, key="mad_chp_avail")

    # ── RUN BUTTON ──────────────────────────────────────────────────────────
    run = st.button("▶ Run MAD Analysis", type="primary")

    if not run and "mad_result" not in st.session_state:
        st.info(
            "Configure your digester inputs above and click **▶ Run MAD Analysis**. "
            "The MAD engine runs independently of the BioPoint pathway rankings."
        )
        return

    if run:
        inputs = MADInputs(
            psV=psV, wasV=wasV,
            psDS=psDS, wasDS=wasDS,
            psTS=psTS, wasTS=wasTS,
            psVS=psVS, wasVS=wasVS,
            psN=psN, wasN=wasN,
            mode="separate", sepBenefit=1.10,
            pretreatment=pretreatment,
            recup=True,
            psCap=psCap, wasCap=wasCap,
            psBeta=psBeta, wasBeta=wasBeta,
            finalDewateringCap=final_cap,
            mixingSystemType=mixing_sys,
            mixingPower=mixing_power,
            mixingScale=mixing_scale,
            digester_pH=digester_pH,
            pHControl=ph_control,
            nh3Mode=nh3_mode,
            KI_NH3=ki_custom,
            tradeWaste=trade_waste,
            chpE=chp_eff,
            chpAvail=chp_avail,
        )
        with st.spinner("Running MAD engine..."):
            result = run_mad(inputs)
        st.session_state["mad_result"]  = result
        st.session_state["mad_inputs"]  = inputs

    result = st.session_state["mad_result"]
    inputs = st.session_state["mad_inputs"]

    st.divider()

    # ── HEADLINE STATUS ──────────────────────────────────────────────────────
    st.subheader("Diagnostic summary")

    h1, h2, h3, h4 = st.columns(4)
    with h1:
        _show_status(result.status, "Overall status")
    with h2:
        feas_icon = FEASIBILITY_COLOURS.get(result.feasibility.overall, "⬜")
        if result.feasibility.overall == "INFEASIBLE":
            st.error(f"{feas_icon} **INFEASIBLE geometry**")
        elif result.feasibility.overall == "MARGINAL":
            st.warning(f"{feas_icon} **MARGINAL geometry**")
        else:
            st.success(f"{feas_icon} **FEASIBLE geometry**")
    with h3:
        st.metric("Primary constraint", result.primary_constraint)
    with h4:
        st.metric("Confidence", result.confidence_grade)

    # Active diagnostic flags
    flags = result.diagnostic_flags
    active_flags = [k for k, v in flags.items() if v]
    if active_flags:
        st.markdown("**Active diagnostic flags:**")
        flag_labels = {
            "geometric_infeasibility":  "🔴 Geometric infeasibility — digester too small for stable SRT",
            "geometric_marginal":       "🟡 Geometric margin tight — operating window narrow",
            "biogas_blind_warning":     "🟠 Biogas blind zone — WAS SRT > 30d, use NH4+pH as indicators",
            "high_TS_diffusion_active": "🟡 High TS — diffusion coupling active (TS > 4%)",
            "thp_active":               "🔵 THP active — kinetic boost and VSmax uplift applied",
            "solidstream_active":       "🔵 SolidStream active — post-digestion THP: k × 1.15, "
                                        "biogas uplift +22.7%, VSmax × 1.22",
            "solidstream_hrt_warning":  "🟠 SolidStream HRT < 15d — minimum 15d HRT required for "
                                        "SolidStream. Consider adding digester volume.",
            "pH_control_engaged":       "🔵 pH control engaged — pH clamped to 7.30",
            "industrial_trade_waste":   "🟠 Industrial trade waste — WAS N% elevated to ≥ 11%",
        }
        for f in active_flags:
            st.markdown(f"• {flag_labels.get(f, f)}")

    st.divider()

    # ── ENERGY & GAS ────────────────────────────────────────────────────────
    st.subheader("Energy & biogas")
    e1, e2, e3, e4, e5 = st.columns(5)
    e1.metric("Biogas", f"{result.biogas_m3_per_d:,.0f} m³/day")
    e2.metric("Biogas energy", f"{result.biogas_GJ_per_d:.1f} GJ/day")
    e3.metric("CHP gross", f"{result.elecGross_kW:,.0f} kW")
    e4.metric("Mixing parasitic", f"{result.mixingParasitic_kW:,.0f} kW")
    e5.metric("Net electrical", f"{result.netElec_kW:,.0f} kW",
              delta=f"{result.netElec_kW - result.elecGross_kW:+,.0f} kW (mixing loss)")

    # ── SOLIDSTREAM PERFORMANCE SUMMARY ─────────────────────────────────────
    if flags.get("solidstream_active"):
        st.divider()
        st.subheader("SolidStream dewatering performance")
        st.caption(
            "Estimates based on Cambi Melbourne ETP conceptual design memo (20.05.2026) "
            "and Antwerp Schijnpoort 2025 operational data. "
            "_Vendor-estimated — not guaranteed performance._"
        )
        from engine.ghg_coefficients import (
            THP_SOLIDSTREAM_CAKE_DS_PCT,
            THP_SOLIDSTREAM_BIOGAS_UPLIFT_PCT,
            THP_SOLIDSTREAM_VSR_PCT,
            THP_CAKE_VOLUME_REDUCTION_PCT,
            THP_DRYING_ENERGY_REDUCTION_PCT,
            THP_SOLIDSTREAM_ELECTRICITY_UPLIFT_PCT,
            THP_SOLIDSTREAM_TRUCK_REDUCTION_PCT,
        )
        ss1, ss2, ss3 = st.columns(3)
        with ss1:
            st.metric("Dewatered cake DS%",
                      f"≥{THP_SOLIDSTREAM_CAKE_DS_PCT:.0f}% DS",
                      delta="vs 20–22% conventional",
                      delta_color="normal")
            st.metric("Cake volume reduction",
                      f"~{THP_CAKE_VOLUME_REDUCTION_PCT:.0f}%",
                      delta="fewer trucks, lower disposal cost",
                      delta_color="normal")
        with ss2:
            st.metric("VSR with SolidStream",
                      f"~{THP_SOLIDSTREAM_VSR_PCT:.1f}%",
                      delta="vs 57.5% conventional",
                      delta_color="normal")
            st.metric("Biogas uplift",
                      f"+{THP_SOLIDSTREAM_BIOGAS_UPLIFT_PCT:.1f}%",
                      delta="COD-rich centrate recycled to digesters",
                      delta_color="normal")
        with ss3:
            st.metric("Drying energy reduction",
                      f"~{THP_DRYING_ENERGY_REDUCTION_PCT:.0f}%",
                      delta="if thermal drying still applied",
                      delta_color="normal")
            st.metric("Electricity uplift",
                      f"+{THP_SOLIDSTREAM_ELECTRICITY_UPLIFT_PCT:.1f}%",
                      delta="from higher biogas production",
                      delta_color="normal")
        st.success(
            "✅ **Pathogen kill:** SolidStream operates at 145–165°C / 6 bar for 40 min "
            "— full sterilisation, Class A equivalent. "
            "3-year stockpiling for EPA Victoria pathogen criteria is eliminated."
        )
        if flags.get("solidstream_hrt_warning"):
            st.error(
                "⚠️ **HRT < 15d** — SolidStream requires minimum 15d hydraulic retention time "
                "in existing digesters. Current digester volume is insufficient at this throughput. "
                "Either reduce throughput or add digester volume before installing SolidStream."
            )

    st.divider()

    # ── PER-STREAM DETAIL ────────────────────────────────────────────────────
    st.subheader("Per-stream physics")

    tab_ps, tab_was = st.tabs(["Primary Sludge (PS)", "Waste Activated Sludge (WAS)"])

    def _stream_table(stream, label):
        _show_status(stream.status, label)
        st.markdown(f"**Primary constraint:** {stream.primary_constraint}")

        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown("**Volume fractions**")
            st.metric("f_mix (mixing)",       f"{stream.f_mix:.3f}")
            st.metric("f_diff_base (TS)",      f"{stream.f_diff_base:.3f}")
            st.metric("f_diff_eff (coupled)",  f"{stream.f_diff_eff:.3f}")
            st.metric("f_eff (combined)",      f"{stream.f_eff:.3f}",
                      help="f_mix × f_diff_eff — the active volume fraction driving kinetics")

        with m2:
            st.markdown("**Retention times**")
            st.metric("HRT nominal",   f"{stream.HRT_nominal_d:.1f} d")
            st.metric("SRT nominal",   f"{stream.SRT_nominal_d:.1f} d")
            st.metric("SRT effective", f"{stream.SRT_eff_d:.1f} d",
                      help="Capped at 35d for WAS (kinetic plateau)")
            st.metric("VS destruction", f"{stream.VS_destruction_pct:.1f}%")

        with m3:
            st.markdown("**NH3 inhibition**")
            st.metric("NH4⁺ concentration", f"{stream.NH4_g_per_L:.2f} g N/L")
            st.metric("NH3 (FAN)",          f"{stream.NH3_g_per_L:.3f} g N/L")
            st.metric("Inhibition",         f"{stream.inhibition_pct:.1f}%",
                      delta=f"K_I = {result.effective_KI:.2f} g/L",
                      delta_color="off")

    with tab_ps:
        _stream_table(result.ps, "PS status")
    with tab_was:
        _stream_table(result.was, "WAS status")

    st.divider()

    # ── SIDESTREAM NITROGEN ──────────────────────────────────────────────────
    st.subheader("Sidestream nitrogen")
    n1, n2, n3 = st.columns(3)
    n1.metric("Total N released (liquid)", f"{result.totalN_released_kg_per_d:,.0f} kg/day",
              help="N solubilised during digestion — returns to liquid stream")
    n2.metric("Centrate N (to headworks)", f"{result.centrate_N_kg_per_d:,.0f} kg/day",
              help="N load returned to plant inlet via final dewatering centrate. Affects BNR loading.")
    n3.metric("Cake N (in product)",       f"{result.cake_N_kg_per_d:,.0f} kg/day",
              help="N retained in dewatered cake — relevant for biosolids product quality and land application.")

    # N mass balance check
    feed_n = (inputs.psDS * inputs.psN / 100 + inputs.wasDS * inputs.wasN / 100) * 1000
    out_n  = result.centrate_N_kg_per_d + result.cake_N_kg_per_d
    closure = abs(out_n - feed_n) / feed_n * 100 if feed_n > 0 else 0
    st.caption(
        f"Feed N: {feed_n:,.0f} kg/day | "
        f"Output N: {out_n:,.0f} kg/day | "
        f"Mass balance closure: {closure:.1f}% error"
    )

    st.divider()

    # ── GEOMETRIC FEASIBILITY ────────────────────────────────────────────────
    st.subheader("Geometric feasibility")
    st.caption(
        "Tests whether digester volumes can reach stable SRT under typical "
        "operating values (cap 85%, β 2.0, f_eff 0.85). "
        f"Min stable SRT for {result.feasibility.minStableSRT_d:.0f}d "
        f"({inputs.nh3Mode} mode)."
    )

    f1, f2, f3 = st.columns(3)
    feas = result.feasibility
    f1.metric("Overall",
              f"{FEASIBILITY_COLOURS[feas.overall]} {feas.overall}")
    f2.metric("PS max achievable SRT", f"{feas.maxAchievablePsSRT_d:.1f}d",
              delta=f"min = {feas.minStableSRT_d:.0f}d",
              delta_color="off")
    f3.metric("WAS max achievable SRT", f"{feas.maxAchievableWasSRT_d:.1f}d",
              delta=f"min = {feas.minStableSRT_d:.0f}d",
              delta_color="off")

    st.divider()

    # ── OPERATING CONDITIONS ──────────────────────────────────────────────────
    with st.expander("Resolved operating conditions"):
        st.markdown(f"""
| Parameter | Value |
|---|---|
| Effective pH | {result.effective_pH:.2f} |
| Effective K_I | {result.effective_KI:.2f} g NH3-N/L |
| NH3 mode | {inputs.nh3Mode} |
| Pretreatment | {inputs.pretreatment} |
| Mixing system | {inputs.mixingSystemType} |
| Mixing power | {inputs.mixingPower:.0f} W/m³ |
| Trade waste | {inputs.tradeWaste} |
| pH control | {inputs.pHControl} |
        """)

    # ── DATA TABLE ───────────────────────────────────────────────────────────
    with st.expander("Full results table"):
        rows = [
            ("Overall status",           result.status,              "—"),
            ("Primary constraint",       result.primary_constraint,  "—"),
            ("Feasibility",              result.feasibility.overall, "—"),
            ("Biogas",                   f"{result.biogas_m3_per_d:,.0f}", "m³/day"),
            ("Biogas energy",            f"{result.biogas_GJ_per_d:.2f}",  "GJ/day"),
            ("CHP gross",                f"{result.elecGross_kW:,.0f}",    "kW"),
            ("Mixing parasitic",         f"{result.mixingParasitic_kW:,.0f}", "kW"),
            ("Net electrical",           f"{result.netElec_kW:,.0f}",      "kW"),
            ("PS f_eff",                 f"{result.ps.f_eff:.3f}",         "—"),
            ("PS SRT effective",         f"{result.ps.SRT_eff_d:.1f}",     "d"),
            ("PS VS destruction",        f"{result.ps.VS_destruction_pct:.1f}", "%"),
            ("PS inhibition",            f"{result.ps.inhibition_pct:.1f}", "%"),
            ("PS status",                result.ps.status,                 "—"),
            ("WAS f_mix",                f"{result.was.f_mix:.3f}",        "—"),
            ("WAS f_diff_base",          f"{result.was.f_diff_base:.3f}",  "—"),
            ("WAS f_diff_eff",           f"{result.was.f_diff_eff:.3f}",   "—"),
            ("WAS f_eff",                f"{result.was.f_eff:.3f}",        "—"),
            ("WAS SRT effective",        f"{result.was.SRT_eff_d:.1f}",    "d"),
            ("WAS VS destruction",       f"{result.was.VS_destruction_pct:.1f}", "%"),
            ("WAS NH4",                  f"{result.was.NH4_g_per_L:.2f}",  "g N/L"),
            ("WAS NH3 (FAN)",            f"{result.was.NH3_g_per_L:.3f}",  "g N/L"),
            ("WAS inhibition",           f"{result.was.inhibition_pct:.1f}", "%"),
            ("WAS status",               result.was.status,                "—"),
            ("Centrate N",               f"{result.centrate_N_kg_per_d:,.0f}", "kg/day"),
            ("Cake N",                   f"{result.cake_N_kg_per_d:,.0f}",     "kg/day"),
            ("Total N released",         f"{result.totalN_released_kg_per_d:,.0f}", "kg/day"),
            ("Effective pH",             f"{result.effective_pH:.2f}",     "—"),
            ("Effective K_I",            f"{result.effective_KI:.2f}",     "g NH3-N/L"),
        ]
        df = pd.DataFrame(rows, columns=["Parameter", "Value", "Units"])
        st.dataframe(df, use_container_width=True, hide_index=True)
