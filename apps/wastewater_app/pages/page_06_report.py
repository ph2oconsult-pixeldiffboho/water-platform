"""
apps/wastewater_app/pages/page_06_report.py

06 Report — structured engineering feasibility report with all sections.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
import streamlit as st
import pandas as pd

from apps.ui.session_state import require_project, get_current_project
from core.qa.qa_engine import QAEngine
from apps.wastewater_app.pages.qa_panel import render_export_gate
from apps.ui.ui_components import render_page_header
from core.reporting.report_engine import ReportEngine
from core.project.project_model import PlanningScenario


def render() -> None:
    render_page_header("06 Report", "Generate a structured concept-design feasibility report.")
    require_project()

    project  = get_current_project()
    all_scen = project.get_all_scenarios()
    calc     = [s for s in all_scen if s.cost_result]

    if not calc:
        st.warning("⚠️ Run calculations for at least one scenario before generating a report.")
        return

    # ── Report options ─────────────────────────────────────────────────────
    col1, col2 = st.columns([3, 1])
    with col1:
        sel_names = st.multiselect("Include scenarios",
            [s.scenario_name for s in calc], default=[s.scenario_name for s in calc])
    with col2:
        incl_assumptions = st.checkbox("Assumptions appendix", value=True)

    if not sel_names:
        st.info("Select at least one scenario.")
        return

    sel_ids = [sid for sid, s in project.scenarios.items() if s.scenario_name in sel_names]

    if st.button("Generate Report ▶", type="primary", use_container_width=True):
        with st.spinner("Building report..."):
            engine = ReportEngine()
            report = engine.build_report(project, sel_ids, incl_assumptions)
            st.session_state["generated_report"] = report
            st.success("✅ Report generated.")

    report = st.session_state.get("generated_report")
    if not report:
        return

    st.divider()

    # ── REPORT DISPLAY ─────────────────────────────────────────────────────
    meta = project.metadata

    # Cover block
    st.markdown(f"""
    <div style="border:2px solid #1f6aa5; border-radius:8px; padding:24px; margin-bottom:24px;">
        <h2 style="color:#1f6aa5; margin:0">{meta.project_name}</h2>
        <h3 style="color:#444; margin:4px 0 12px 0">Wastewater Treatment Planning Study — Concept Report</h3>
        <table style="width:100%; font-size:0.9rem;">
          <tr><td><b>Plant:</b> {meta.plant_name or '—'}</td>
              <td><b>Client:</b> {meta.client_name or '—'}</td></tr>
          <tr><td><b>Location:</b> {meta.plant_location or '—'}</td>
              <td><b>Project No.:</b> {meta.project_number or '—'}</td></tr>
          <tr><td><b>Prepared by:</b> {meta.author or '—'}</td>
              <td><b>Date:</b> {datetime.now(timezone.utc).strftime('%B %Y')}</td></tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

    # Planning scenario
    if meta.planning_scenario:
        try:
            ps = PlanningScenario(meta.planning_scenario)
            st.info(f"**Planning Scenario:** {ps.display_name}")
        except ValueError:
            pass

    # ── 1. Executive Summary ───────────────────────────────────────────────
    with st.expander("1. Executive Summary", expanded=True):
        st.markdown(report.executive_summary)

    # ── 2. Plant Inputs ────────────────────────────────────────────────────
    with st.expander("2. Plant Inputs", expanded=False):
        sel_scenarios = [project.scenarios[sid] for sid in sel_ids if sid in project.scenarios]
        for s in sel_scenarios:
            st.markdown(f"**{s.scenario_name}**")
            inp = s.domain_inputs or {}
            rows = [
                {"Parameter": "Average Flow", "Value": f"{inp.get('design_flow_mld','—')} ML/day"},
                {"Parameter": "Peak Flow",    "Value": f"{inp.get('peak_flow_mld','—')} ML/day"},
                {"Parameter": "Influent BOD", "Value": f"{inp.get('influent_bod_mg_l','—')} mg/L"},
                {"Parameter": "Influent COD", "Value": f"{inp.get('influent_cod_mg_l','—')} mg/L"},
                {"Parameter": "Influent TSS", "Value": f"{inp.get('influent_tss_mg_l','—')} mg/L"},
                {"Parameter": "Influent TKN", "Value": f"{inp.get('influent_tkn_mg_l','—')} mg/L"},
                {"Parameter": "Influent NH₄-N","Value": f"{inp.get('influent_nh4_mg_l','—')} mg/L"},
                {"Parameter": "Influent TP",  "Value": f"{inp.get('influent_tp_mg_l','—')} mg/L"},
                {"Parameter": "Effluent TN target","Value": f"{inp.get('effluent_tn_mg_l','—')} mg/L"},
                {"Parameter": "Effluent TP target","Value": f"{inp.get('effluent_tp_mg_l','—')} mg/L"},
                {"Parameter": "Electricity price","Value": f"${inp.get('electricity_price_per_kwh','—')}/kWh"},
                {"Parameter": "Carbon price","Value": f"${inp.get('carbon_price_per_tonne','—')}/t CO₂e"},
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── 3. Treatment Pathway Description ──────────────────────────────────
    with st.expander("3. Treatment Pathway Description", expanded=False):
        from apps.wastewater_app.pages.page_03_treatment_selection import TECHNOLOGIES
        for s in sel_scenarios:
            st.markdown(f"**{s.scenario_name}**")
            if s.treatment_pathway:
                seq = s.treatment_pathway.technology_sequence
                st.markdown(f"*Pathway:* {' → '.join(t.upper() for t in seq)}")
                for code in seq:
                    tech_info = TECHNOLOGIES.get(code, {})
                    if tech_info:
                        st.markdown(f"- **{tech_info['name']}**: {tech_info['description']}")
                        params = s.treatment_pathway.technology_parameters.get(code, {})
                        if params:
                            param_str = " | ".join(f"{k}: {v}" for k, v in params.items()
                                                    if not k.startswith("_"))
                            st.caption(f"  Parameters: {param_str}")

    # ── 4. Engineering Results ─────────────────────────────────────────────
    with st.expander("4. Engineering Results", expanded=False):
        for s in sel_scenarios:
            eng = s.domain_specific_outputs.get("engineering_summary", {})
            if eng:
                st.markdown(f"**{s.scenario_name}**")
                tech_perf = s.domain_specific_outputs.get("technology_performance", {})
                for code, perf in tech_perf.items():
                    if perf:
                        st.markdown(f"*{code.replace('_',' ').title()}*")
                        perf_rows = [{"Parameter": k.replace("_"," ").title(),
                                      "Value": str(v)} for k, v in perf.items()]
                        st.dataframe(pd.DataFrame(perf_rows), use_container_width=True, hide_index=True)

    # ── 5. Lifecycle Cost Comparison ───────────────────────────────────────
    with st.expander("5. Lifecycle Cost Comparison", expanded=False):
        if report.cost_table:
            _render_table(report.cost_table)
        if report.comparison_table:
            st.markdown("**Multi-Criteria Comparison**")
            st.dataframe(pd.DataFrame(report.comparison_table), use_container_width=True, hide_index=True)

    # ── 6. Energy and Carbon Analysis ─────────────────────────────────────
    with st.expander("6. Energy and Carbon Analysis", expanded=False):
        if report.carbon_table:
            _render_table(report.carbon_table)

        import plotly.graph_objects as go
        carbon_scens = [s for s in sel_scenarios if s.carbon_result]
        if carbon_scens:
            names = [s.scenario_name for s in carbon_scens]
            fig = go.Figure()
            for scope, vals, col in [
                ("Scope 1", [s.carbon_result.scope_1_tco2e_yr for s in carbon_scens], "#d62728"),
                ("Scope 2", [s.carbon_result.scope_2_tco2e_yr for s in carbon_scens], "#ff7f0e"),
                ("Scope 3", [s.carbon_result.scope_3_tco2e_yr for s in carbon_scens], "#9467bd"),
                ("Avoided", [-s.carbon_result.avoided_tco2e_yr for s in carbon_scens], "#2ca02c"),
            ]:
                fig.add_trace(go.Bar(name=scope, x=names, y=vals, marker_color=col))
            fig.update_layout(barmode="relative", yaxis_title="tCO₂e/yr",
                              plot_bgcolor="white", height=300,
                              legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig, use_container_width=True)

    # ── 7. Technology Risk Assessment ──────────────────────────────────────
    with st.expander("7. Technology Risk Assessment", expanded=False):
        if report.risk_table:
            _render_table(report.risk_table)
        for s in sel_scenarios:
            if s.risk_result and s.risk_result.risk_narrative:
                st.markdown(f"**{s.scenario_name}:** {s.risk_result.risk_narrative}")

    # ── 7b. Plant Data Review and Calibration ─────────────────────────────
    # Collect calibration data from any scenario that has plant data applied
    cal_scenarios = [s for s in sel_scenarios
                     if (s.domain_inputs or {}).get("_calibration_applied")]

    if cal_scenarios:
        with st.expander("7b. Plant Data Review and Calibration", expanded=False):
            _render_calibration_report_section(cal_scenarios, project)

    # ── 8. Model Assumptions ───────────────────────────────────────────────
    if incl_assumptions and report.assumptions_appendix:
        with st.expander("8. Model Assumptions", expanded=False):
            _render_table(report.assumptions_appendix)

    # ── Export ─────────────────────────────────────────────────────────────
    st.divider()

    # ── Pre-export QA gate ─────────────────────────────────────────────────
    try:
        from core.qa.qa_engine import validate_report, validate_project
        from apps.wastewater_app.components.qa_panel import render_export_gate
        from domains.wastewater.decision_engine import evaluate_scenario

        _sel_scens = [project.scenarios[sid] for sid in sel_ids if sid in project.scenarios]

        # Decision engine for cross-scenario QA
        _dec_qa = None
        try:
            _dec_qa = evaluate_scenario(_sel_scens)
        except Exception:
            pass

        # Run report QA
        _qa_report_result = validate_report(
            report=report,
            project=project,
            decision=_dec_qa,
            scenarios=_sel_scens,
        )

        # Show gate — blocks export if FAIL
        _warnings_ack = st.session_state.get("qa_warnings_acknowledged", False)
        _export_ok = render_export_gate(_qa_report_result, _warnings_ack)
    except Exception:
        # QA must never break export — if it crashes, allow export
        _export_ok = True

    if not _export_ok:
        st.stop()

    st.subheader("Download Report")
    fname_base = meta.project_name.replace(" ", "_") if meta.project_name else "report"

    from core.reporting.report_exporter import ReportExporter

    # Two report types
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**📋 Executive Summary** (1–2 pages)")
        st.caption("Key metrics, comparison table, cost and carbon summary")
        col_a, col_b = st.columns(2)
        with col_a:
            try:
                pdf_exec = ReportExporter.to_pdf(report, mode="executive")
                st.download_button("📄 PDF", data=pdf_exec,
                    file_name=f"{fname_base}_executive_summary.pdf",
                    mime="application/pdf", use_container_width=True, type="primary")
            except Exception as e:
                st.error(f"PDF failed: {e}")
        with col_b:
            try:
                docx_exec = ReportExporter.to_docx(report, mode="executive")
                st.download_button("📝 Word", data=docx_exec,
                    file_name=f"{fname_base}_executive_summary.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True)
            except Exception as e:
                st.error(f"Word failed: {e}")

    with c2:
        st.markdown("**📑 Comprehensive Report** (full detail)")
        st.caption("Introduction, methodology, all tables, assumptions appendix, recommendations")
        col_c, col_d = st.columns(2)
        with col_c:
            try:
                pdf_full = ReportExporter.to_pdf(report, mode="comprehensive")
                st.download_button("📄 PDF", data=pdf_full,
                    file_name=f"{fname_base}_full_report.pdf",
                    mime="application/pdf", use_container_width=True, type="primary")
            except Exception as e:
                st.error(f"PDF failed: {e}")
        with col_d:
            try:
                docx_full = ReportExporter.to_docx(report, mode="comprehensive")
                st.download_button("📝 Word", data=docx_full,
                    file_name=f"{fname_base}_full_report.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True)
            except Exception as e:
                st.error(f"Word failed: {e}")

    st.divider()
    report_dict = {
        "project": report.project_name, "plant": report.plant_name,
        "generated_at": report.generated_at,
        "executive_summary": report.executive_summary,
        "cost_table": report.cost_table,
        "carbon_table": report.carbon_table,
        "risk_table": report.risk_table,
        "comparison_table": report.comparison_table,
    }
    st.download_button("📥 Export raw data (JSON)",
        data=json.dumps(report_dict, indent=2, default=str),
        file_name=f"{fname_base}_data.json",
        mime="application/json")


def _render_calibration_report_section(cal_scenarios, project) -> None:
    """Render the Plant Data Review and Calibration report section."""
    st.markdown(
        "This section summarises the plant operational data upload, data quality review, "
        "calibration factors applied, and their effect on model assumptions."
    )
    st.warning(
        "Calibration confidence depends on the quality and completeness of uploaded plant data. "
        "Factors derived from limited observations should be treated with caution. "
        "All results should be validated against independent data where possible."
    )
    for s in cal_scenarios:
        di = s.domain_inputs or {}
        n_factors = di.get("_n_factors_calibrated", "unknown")
        st.markdown(f"**Scenario: {s.scenario_name}** — {n_factors} calibration factor(s) applied")

        # Show override log if present
        if s.assumptions and s.assumptions.override_log:
            cal_overrides = [
                entry for entry in s.assumptions.override_log
                if entry.get("author") == "Digital Twin Calibration"
            ]
            if cal_overrides:
                cal_df = pd.DataFrame([{
                    "Parameter":    e.get("key",""),
                    "Default→Calibrated": f"{e.get('new_value',''):.4g}",
                    "Source":       e.get("reason",""),
                    "Applied":      e.get("timestamp","")[:10] if e.get("timestamp") else "",
                } for e in cal_overrides])
                st.dataframe(cal_df, use_container_width=True, hide_index=True)
            else:
                st.info("No calibration override log entries found.")
        else:
            st.info("No calibration data stored in this scenario's assumptions.")

        st.caption(
            "Calibration factors were derived from uploaded plant operational data using the "
            "Plant Data and Calibration module (page 07). Each factor represents the ratio "
            "of observed plant performance to the model default assumption. "
            "Factors outside 0.5×–2.0× of the default were flagged for manual review."
        )


def _render_table(table_data) -> None:
    if isinstance(table_data, list) and table_data:
        st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
    elif isinstance(table_data, dict):
        rows = table_data.get("rows", [])
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
