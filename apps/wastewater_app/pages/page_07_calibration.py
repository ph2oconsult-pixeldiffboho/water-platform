"""
apps/wastewater_app/pages/page_07_calibration.py

Plant Data, Calibration and Digital Twin page.
Provides: data upload, KPI calculation, benchmarking, anomaly detection,
calibration factor review, and saving a calibrated scenario.
"""

from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import io

from apps.ui.session_state import (
    require_project, get_current_project, update_current_project,
    get_active_scenario, set_active_scenario,
)
from apps.ui.ui_components import render_page_header, render_scenario_selector
from core.project.project_manager import ProjectManager
from core.assumptions.assumptions_manager import AssumptionsManager
from core.project.project_model import DomainType
from core.data_ingestion.data_cleaning import (
    PlantDataCleaner, generate_sample_csv, COLUMN_SPEC
)
from domains.wastewater.plant_kpis import PlantKPICalculator
from core.calibration.calibration_engine import (
    CalibrationEngine, CalibrationStatus
)
from core.benchmarking.benchmark_engine import BenchmarkEngine, AnomalyDetector


PROCESS_TYPES = {
    "bnr":            "Conventional BNR",
    "mbr":            "MBR",
    "granular_sludge":"Aerobic Granular Sludge",
    "digestion":      "Anaerobic Digestion",
}


def render() -> None:
    render_page_header(
        "07 Plant Data & Calibration",
        "Upload operational data, calculate KPIs, benchmark performance, "
        "and calibrate model assumptions to real plant behaviour.",
    )
    require_project()

    project  = get_current_project()
    pm       = ProjectManager()
    scenario = get_active_scenario()

    render_scenario_selector(project)
    scenario = get_active_scenario()

    # Session state keys
    cal_data_key  = "cal_plant_df"
    cal_clean_key = "cal_clean_result"
    cal_kpi_key   = "cal_kpi_result"
    cal_result_key= "cal_engine_result"

    # ── DATA UPLOAD ────────────────────────────────────────────────────────
    st.subheader("Step 1 — Upload Plant Data")

    col1, col2 = st.columns([3, 1])
    with col1:
        uploaded = st.file_uploader(
            "Upload CSV file of plant operational data",
            type=["csv"],
            help="Accepts daily or hourly data. Column names are flexible — see the expected format below.",
        )
    with col2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("📥 Load sample data", help="Load a synthetic 90-day dataset for demonstration"):
            st.session_state[cal_data_key] = generate_sample_csv(90)
            st.session_state.pop(cal_clean_key, None)
            st.session_state.pop(cal_kpi_key, None)
            st.session_state.pop(cal_result_key, None)
            st.rerun()

    if uploaded:
        st.session_state[cal_data_key] = uploaded.read().decode("utf-8", errors="replace")
        st.session_state.pop(cal_clean_key, None)
        st.session_state.pop(cal_kpi_key, None)
        st.session_state.pop(cal_result_key, None)
        st.rerun()

    # Show expected format
    with st.expander("Expected CSV format and column names"):
        spec_rows = [
            {"Column name": k, "Importance": v[0], "Description": v[1]}
            for k, v in COLUMN_SPEC.items()
        ]
        st.dataframe(pd.DataFrame(spec_rows), use_container_width=True, hide_index=True)
        st.caption(
            "Column names are flexible — common alternatives are automatically recognised. "
            "Partial datasets are accepted; KPIs are calculated only when required columns are present."
        )

    if cal_data_key not in st.session_state:
        st.info("Upload a CSV file or load the sample dataset to begin.")
        return

    # ── DATA CLEANING ──────────────────────────────────────────────────────
    if cal_clean_key not in st.session_state:
        with st.spinner("Cleaning and validating data…"):
            interval = st.session_state.get("cal_interval", "daily")
            cleaner = PlantDataCleaner()
            clean_result = cleaner.clean(st.session_state[cal_data_key], target_interval=interval)
            st.session_state[cal_clean_key] = clean_result

    clean_result = st.session_state[cal_clean_key]
    df = clean_result.df

    if df is None or len(df) == 0:
        st.error("No valid data after cleaning. Check the data quality issues below.")
        _render_issues(clean_result)
        return

    # ── TABS ───────────────────────────────────────────────────────────────
    tabs = st.tabs([
        "📋 Data Quality", "📊 KPIs", "📐 Benchmarking",
        "📈 Trends", "🚨 Anomalies", "🎯 Calibration"
    ])

    with tabs[0]:
        _render_data_quality(clean_result)

    with tabs[1]:
        _render_kpis(df, clean_result, cal_kpi_key)

    with tabs[2]:
        _render_benchmarking(cal_kpi_key)

    with tabs[3]:
        _render_trends(df)

    with tabs[4]:
        _render_anomalies(df)

    with tabs[5]:
        _render_calibration(cal_result_key, cal_kpi_key, scenario, project, pm)


# ── TAB RENDERERS ─────────────────────────────────────────────────────────────

def _render_data_quality(clean_result) -> None:
    st.subheader("Data Quality Report")

    score = clean_result.data_quality_score
    colour = "#2ca02c" if score > 70 else ("#ff7f0e" if score > 40 else "#d62728")
    st.markdown(
        f"<div style='background:{colour}; color:white; padding:10px; border-radius:6px; "
        f"font-size:1.1rem; font-weight:bold'>"
        f"Data Quality Score: {score:.0f}/100</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Raw rows",         clean_result.n_rows_raw)
    c2.metric("Clean rows",       clean_result.n_rows_clean)
    c3.metric("Rows removed",     clean_result.n_rows_removed)
    c4.metric("Date range",       clean_result.date_range or "—")

    iss = clean_result.issue_summary()
    c1, c2, c3 = st.columns(3)
    c1.metric("Critical issues", iss["critical"])
    c2.metric("Warnings",        iss["warning"])
    c3.metric("Info",            iss["info"])

    st.divider()

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("**Columns found**")
        for c in clean_result.columns_found:
            imp = COLUMN_SPEC.get(c, ("optional",))[0]
            icon = "🟢" if imp == "core" else "🔵"
            st.markdown(f"  {icon} `{c}`")
    with col_right:
        if clean_result.columns_missing_core:
            st.markdown("**Missing core columns**")
            for c in clean_result.columns_missing_core:
                st.markdown(f"  ⚠️ `{c}`")

    _render_issues(clean_result)


def _render_issues(clean_result) -> None:
    if not clean_result.issues:
        st.success("No data quality issues found.")
        return
    st.markdown("**Data quality issues**")
    for issue in clean_result.issues:
        if issue.severity.value == "critical":
            st.error(str(issue))
        elif issue.severity.value == "warning":
            st.warning(str(issue))
        else:
            st.info(str(issue))


def _render_kpis(df, clean_result, kpi_key: str) -> None:
    st.subheader("Plant KPIs")

    if kpi_key not in st.session_state:
        calc = PlantKPICalculator()
        kpi_result = calc.calculate(df)
        st.session_state[kpi_key] = kpi_result

    kpi_result = st.session_state[kpi_key]
    rows = kpi_result.to_summary_rows()

    if not rows:
        st.info("No KPIs could be calculated from the available data.")
        return

    kpi_df = pd.DataFrame(rows)

    def colour_conf(val):
        c = {"high": "#2ca02c", "medium": "#ff7f0e", "low": "#aaa"}.get(val)
        return f"color:{c}; font-weight:bold" if c else ""

    for group_name in kpi_df["Group"].unique():
        st.markdown(f"**{group_name}**")
        sub = kpi_df[kpi_df["Group"] == group_name].drop(columns=["Group"])
        try:
            styled = sub.style.map(colour_conf, subset=["Confidence"])
            st.dataframe(styled, use_container_width=True, hide_index=True)
        except Exception:
            st.dataframe(sub, use_container_width=True, hide_index=True)


def _render_benchmarking(kpi_key: str) -> None:
    st.subheader("Performance Benchmarking")

    if kpi_key not in st.session_state:
        st.info("Calculate KPIs first (see KPIs tab).")
        return

    process_type = st.selectbox(
        "Process type for benchmarking",
        list(PROCESS_TYPES.keys()),
        format_func=lambda x: PROCESS_TYPES[x],
    )

    kpi_result = st.session_state[kpi_key]
    kpi_dict   = kpi_result.to_calibration_dict()
    bench      = BenchmarkEngine()
    rows       = bench.benchmark(kpi_dict, process_type)

    bench_df = pd.DataFrame(rows)

    def colour_class(val):
        c = {"Within normal range": "#1f6aa5",
             "Below expected range": "#2ca02c",
             "Above expected range": "#d62728",
             "No data": "#aaa"}.get(val)
        return f"background-color:{c}; color:white; font-weight:bold" if c else ""

    try:
        styled = bench_df[["KPI","Plant Value","Benchmark Range","Classification","Note"]].style\
            .map(colour_class, subset=["Classification"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        st.dataframe(bench_df[["KPI","Plant Value","Benchmark Range","Classification","Note"]],
                     use_container_width=True, hide_index=True)

    st.caption(
        "Benchmark ranges from: WEF Energy Conservation in WWTP (2009), "
        "AWA Benchmarking Report (2023), Metcalf & Eddy 5th ed."
    )


def _render_trends(df: pd.DataFrame) -> None:
    st.subheader("Time-Series Trends")

    trend_cols = {
        "flow_mld":                  "Flow (ML/day)",
        "influent_nh4_mg_l":         "Influent NH₄ (mg/L)",
        "effluent_nh4_mg_l":         "Effluent NH₄ (mg/L)",
        "blower_power_kw":           "Blower Power (kW)",
        "biogas_m3_day":             "Biogas (m³/day)",
        "sludge_production_t_ds_day":"Sludge Production (t DS/day)",
        "do_aerobic_mg_l":           "Aerobic DO (mg/L)",
        "mlss_mg_l":                 "MLSS (mg/L)",
    }
    available = {v: k for k, v in trend_cols.items() if k in df.columns}

    if not available:
        st.info("No time-series columns available for plotting.")
        return

    view_mode = st.radio("View", ["Time series", "Seasonal summary"], horizontal=True)

    if view_mode == "Seasonal summary":
        _render_seasonal(df)
        return

    selected_labels = st.multiselect(
        "Select parameters to plot",
        list(available.keys()),
        default=list(available.keys())[:3],
    )

    if not selected_labels:
        return

    ts_col = "timestamp" if "timestamp" in df.columns else df.index.name or None

    for label in selected_labels:
        col_name = available[label]
        if col_name not in df.columns:
            continue
        avg_col = f"{col_name}_7d_avg"

        fig = go.Figure()
        x = df[ts_col] if ts_col and ts_col in df.columns else df.index

        fig.add_trace(go.Scatter(
            x=x, y=df[col_name],
            mode="lines", name=label,
            line=dict(color="#aec7e8", width=1), opacity=0.6,
        ))

        if avg_col in df.columns:
            fig.add_trace(go.Scatter(
                x=x, y=df[avg_col],
                mode="lines", name=f"{label} (7-day avg)",
                line=dict(color="#1f6aa5", width=2.5),
            ))

        fig.update_layout(
            title=label, yaxis_title=label,
            plot_bgcolor="white", height=250,
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation="h", y=-0.3),
        )
        st.plotly_chart(fig, use_container_width=True)


def _render_seasonal(df: pd.DataFrame) -> None:
    """Monthly and quarterly bar charts."""
    from domains.wastewater.plant_kpis import PlantKPICalculator
    kpi_calc = PlantKPICalculator()
    seasonal = kpi_calc._seasonal_summary(df)

    if not seasonal:
        st.info("Seasonal summary requires at least 4 weeks of data.")
        return

    monthly = pd.DataFrame(seasonal["monthly"])
    key_cols = [c for c in seasonal["monthly_columns"] if c in monthly.columns]

    if not key_cols:
        st.info("No numeric columns for seasonal summary.")
        return

    col_labels = {
        "flow_mld":          "Flow (ML/day)",
        "influent_nh4_mg_l": "Influent NH₄ (mg/L)",
        "effluent_nh4_mg_l": "Effluent NH₄ (mg/L)",
        "blower_power_kw":   "Blower Power (kW)",
        "biogas_m3_day":     "Biogas (m³/day)",
    }

    sel = st.selectbox("Parameter", [c for c in key_cols],
                       format_func=lambda x: col_labels.get(x, x))

    if sel in monthly.columns and "month" in monthly.columns:
        fig = go.Figure(go.Bar(
            x=monthly["month"],
            y=monthly[sel].round(2),
            marker_color="#1f6aa5",
            text=monthly[sel].round(1),
            textposition="auto",
        ))
        fig.update_layout(
            title=f"Monthly average — {col_labels.get(sel, sel)}",
            yaxis_title=col_labels.get(sel, sel),
            xaxis_tickangle=-30,
            plot_bgcolor="white", height=320,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Quarterly table
    quarterly = pd.DataFrame(seasonal["quarterly"])
    if not quarterly.empty and "quarter" in quarterly.columns:
        st.markdown("**Quarterly averages**")
        q_display = quarterly[["quarter"] + [c for c in key_cols if c in quarterly.columns]]
        q_display.columns = ["Quarter"] + [col_labels.get(c, c) for c in key_cols if c in quarterly.columns]
        st.dataframe(q_display.round(2), use_container_width=True, hide_index=True)


def _render_anomalies(df: pd.DataFrame) -> None:
    st.subheader("Anomaly Detection")
    st.caption(
        "Rule-based detection using IQR bounds and step-change analysis. "
        "All anomalies are flagged with the reason and triggering parameters. "
        "Review before acting — anomalies may be real events, not errors."
    )

    detector = AnomalyDetector()
    anomalies = detector.detect(df)

    if not anomalies:
        st.success("No anomalies detected in the uploaded dataset.")
        return

    n_alert   = sum(1 for a in anomalies if a.severity == "alert")
    n_warning = sum(1 for a in anomalies if a.severity == "warning")
    c1, c2 = st.columns(2)
    c1.metric("Alerts",   n_alert)
    c2.metric("Warnings", n_warning)

    anom_rows = [a.to_dict() for a in anomalies]
    anom_df   = pd.DataFrame(anom_rows)

    def colour_sev(val):
        c = {"alert": "#d62728", "warning": "#ff7f0e"}.get(val)
        return f"background-color:{c}; color:white" if c else ""

    try:
        styled = anom_df.style.map(colour_sev, subset=["Severity"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        st.dataframe(anom_df, use_container_width=True, hide_index=True)


def _render_calibration(cal_result_key, kpi_key, scenario, project, pm) -> None:
    st.subheader("Model Calibration")
    st.markdown(
        "Compare plant KPIs against model default assumptions, "
        "review suggested calibration factors, and optionally apply them "
        "to produce a plant-calibrated scenario."
    )

    if kpi_key not in st.session_state:
        st.info("Calculate KPIs first (see KPIs tab).")
        return

    kpi_result = st.session_state[kpi_key]
    kpi_dict   = kpi_result.to_calibration_dict()

    # Load assumptions for the active scenario (or defaults)
    assumptions = None
    if scenario and scenario.assumptions:
        assumptions = scenario.assumptions
    else:
        assumptions = AssumptionsManager().load_defaults(DomainType.WASTEWATER)

    # Run calibration
    if cal_result_key not in st.session_state:
        engine = CalibrationEngine()
        # FIX: pass obs counts and confidence levels so the safety gates fire
        cal_result = engine.calibrate(
            assumptions,
            kpi_dict,
            kpi_confidence=kpi_result.to_confidence_dict(),
            kpi_obs_count=kpi_result.to_obs_dict(),
        )
        st.session_state[cal_result_key] = cal_result

    cal_result = st.session_state[cal_result_key]

    # ── Calibration factor table with interactive accept/reject ───────────
    st.markdown("**Calibration factors — review and accept/reject each**")

    for i, factor in enumerate(cal_result.factors):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 1.5, 1.5, 1.5, 2])
            c1.markdown(f"**{factor.display_name}**")
            c1.caption(factor.rationale[:80] + "…" if len(factor.rationale) > 80 else factor.rationale)

            c2.metric("Default",  f"{factor.model_default:.3g} {factor.unit}")
            if factor.observed_value:
                c3.metric("Observed", f"{factor.observed_value:.3g} {factor.unit}",
                          delta=f"{(factor.adjustment_factor-1)*100:+.0f}%" if factor.adjustment_factor else None)
            else:
                c3.metric("Observed", "No data")

            if factor.is_out_of_bounds:
                c4.metric("Factor", f"{factor.adjustment_factor:.2f}×", delta="⚠ Out of bounds")
            elif factor.adjustment_factor:
                c4.metric("Factor", f"{factor.adjustment_factor:.2f}×")
            else:
                c4.metric("Factor", "—")

            with c5:
                if factor.observed_value is None:
                    st.caption("No data — cannot calibrate")
                    cal_result.factors[i].status = CalibrationStatus.UNCHANGED
                else:
                    action = st.selectbox(
                        "Action",
                        ["pending", "accepted", "rejected", "manual"],
                        index=["pending","accepted","rejected","manual"].index(factor.status.value)
                              if factor.status.value in ["pending","accepted","rejected","manual"] else 0,
                        key=f"cal_action_{i}",
                        label_visibility="collapsed",
                    )
                    cal_result.factors[i].status = CalibrationStatus(action)
                    if action == "manual":
                        manual_val = st.number_input(
                            "Override value", value=float(factor.suggested_value or factor.model_default),
                            key=f"cal_manual_{i}", step=0.01, format="%.4f",
                            label_visibility="collapsed",
                        )
                        cal_result.factors[i].user_override = manual_val

            if factor.calibration_note:
                st.caption(factor.calibration_note)

    st.divider()

    # ── Apply calibration ─────────────────────────────────────────────────
    n_accepted = sum(1 for f in cal_result.factors
                     if f.status in (CalibrationStatus.ACCEPTED, CalibrationStatus.MANUAL))

    col_btn, col_toggle = st.columns([2, 1])
    with col_btn:
        if st.button(
            f"Apply {n_accepted} calibration factor(s) to scenario",
            type="primary", use_container_width=True,
            disabled=(n_accepted == 0 or scenario is None),
        ):
            engine = CalibrationEngine()
            calibrated_assumptions = engine.apply_accepted_factors(cal_result, assumptions)
            if scenario:
                scenario.assumptions = calibrated_assumptions
                # Mark the scenario to distinguish calibrated from default
                scenario.domain_inputs = scenario.domain_inputs or {}
                scenario.domain_inputs["_calibration_applied"] = True
                scenario.domain_inputs["_n_factors_calibrated"] = n_accepted
                scenario.is_stale = True
                update_current_project(project)
                pm.save(project)
                st.session_state[cal_result_key] = cal_result
                st.success(
                    f"✅ {n_accepted} calibration factor(s) applied to scenario "
                    f"**{scenario.scenario_name}**. "
                    f"Re-run Results (04) to see calibrated outputs."
                )

    with col_toggle:
        st.info(
            f"Accepted: {n_accepted} | "
            f"Pending: {sum(1 for f in cal_result.factors if f.status == CalibrationStatus.PENDING)}"
        )

    # ── Calibration summary table ─────────────────────────────────────────
    with st.expander("Full calibration summary table"):
        cal_df = pd.DataFrame(cal_result.to_summary_rows())
        if not cal_df.empty:
            st.dataframe(cal_df, use_container_width=True, hide_index=True)

    st.caption(
        "Calibration is based on the quality and completeness of uploaded plant data. "
        "Factors derived from <30 observations or low-confidence KPIs should be reviewed carefully. "
        "Calibrated scenarios should be re-validated against independent data if possible."
    )
