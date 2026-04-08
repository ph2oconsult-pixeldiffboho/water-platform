"""
AquaPoint — Page 5: Report Export
Generates a structured plain-text / markdown summary report.
"""
import streamlit as st
from datetime import date
from ..engine.constants import TECHNOLOGIES, PLANT_TYPES, APP_NAME, APP_VERSION
from ..ui_helpers import section_header, success_box, info_box


def _format_currency(value: float) -> str:
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value/1_000:.1f}k"
    return f"${value:.0f}"


def _build_report_text(inputs: dict, results: dict) -> str:
    """Build a structured markdown report from results."""
    today = date.today().strftime("%d %B %Y")
    project = st.session_state.get("project_name", "Unnamed Project")
    client = st.session_state.get("client", "—")
    location = st.session_state.get("location", "—")
    author = st.session_state.get("author", "—")
    plant_type = inputs["plant_type"]
    flow = inputs["flow_ML_d"]
    plant_label = PLANT_TYPES[plant_type]["label"]
    techs = inputs["selected_technologies"]
    tech_labels = [TECHNOLOGIES[t]["label"] for t in techs]

    mca = results["mca"]
    lcost = results["lifecycle_cost"]
    opex = results["opex"]
    capex = results["capex"]
    energy = results["energy"]
    env = results["environmental"]
    reg = results["regulatory"]
    risk = results["risk"]
    tp = results["treatment_performance"]
    chem = results["chemical_use"]

    lines = []
    lines.append(f"# {APP_NAME} — Drinking Water Treatment Analysis Report")
    lines.append(f"**{APP_NAME} {APP_VERSION} | ph2o Consulting | Water Utility Planning Platform**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Project Details")
    lines.append(f"- **Project:** {project}")
    lines.append(f"- **Client/Utility:** {client}")
    lines.append(f"- **Location:** {location}")
    lines.append(f"- **Prepared By:** {author}")
    lines.append(f"- **Date:** {today}")
    lines.append(f"- **Plant Type:** {plant_label}")
    lines.append(f"- **Design Flow:** {flow:.1f} ML/d ({flow*365:,.0f} ML/yr)")
    lines.append("")
    lines.append("## Treatment Train")
    for i, label in enumerate(tech_labels, 1):
        lines.append(f"{i}. {label}")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append(f"- **MCA Score:** {mca['total_score']:.0f}/100")
    lines.append(f"- **NPV (30yr):** {_format_currency(lcost['npv_total_AUD'])} AUD")
    lines.append(f"- **Annual OPEX:** {_format_currency(opex['total_annual_opex_AUD'])} AUD/yr ({opex['unit_opex_AUD_ML']:.0f} AUD/ML)")
    lines.append(f"- **Specific Energy:** {energy['specific_energy_kWh_ML']['typical']:.0f} kWh/ML (typical)")
    lines.append(f"- **ADWG Compliance:** {'Predicted compliant' if tp['overall_compliant'] else 'Exceedance predicted — review required'}")
    lines.append(f"- **Overall Risk:** {risk.get('overall', {}).get('overall_label', '—')}")
    lines.append(f"- **Annual GHG:** {env['total_annual_CO2_tonnes']:,.0f} t CO₂-e/yr ({env['unit_CO2_kg_per_kL']:.3f} kg CO₂-e/kL)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Feasibility Screening")
    for tech_key, feas in results["feasibility"].items():
        status = "✓ Feasible" if feas["feasible"] else "✗ Not Feasible"
        lines.append(f"- **{feas['label']}**: {status}")
        for flag in feas.get("flags", []):
            lines.append(f"  - ⚠ {flag}")
    lines.append("")
    lines.append("## 2. Water Quality & ADWG Compliance")
    lines.append(f"**Disinfection:** {'Adequate' if tp['disinfection_adequate'] else 'NOT ADEQUATE — no disinfection selected'}")
    lines.append("")
    lines.append("| Parameter | Predicted | ADWG Limit | Status |")
    lines.append("|-----------|-----------|------------|--------|")
    for param, comp in tp.get("compliance", {}).items():
        status = "✓" if comp["compliant"] else "✗"
        lines.append(f"| {param.replace('_', ' ').title()} | {comp['predicted']} {comp['unit']} | {comp['guideline']} {comp['unit']} | {status} |")
    lines.append("")
    lines.append("## 3. Energy")
    lines.append(f"- Specific Energy: {energy['specific_energy_kWh_ML']['low']:.0f} – {energy['specific_energy_kWh_ML']['high']:.0f} kWh/ML (typical: {energy['specific_energy_kWh_ML']['typical']:.0f})")
    lines.append(f"- Annual Energy: {energy['annual_energy_MWh']['typical']:,.0f} MWh/yr (typical)")
    lines.append(f"- Annual Energy Cost: {_format_currency(energy['annual_cost_AUD']['typical'])} AUD/yr (typical)")
    lines.append("")
    lines.append("## 4. Chemical Use")
    lines.append(f"- Total Annual Chemical Cost: {_format_currency(chem['total_annual_cost_AUD'])} AUD/yr")
    for chem_key, chem_data in chem["chemicals"].items():
        lines.append(f"  - {chem_data['label']}: {chem_data['dose_mg_L']} mg/L, {chem_data['annual_kg']:,.0f} kg/yr, {_format_currency(chem_data['annual_cost_AUD'])}/yr")
    lines.append("")
    lines.append("## 5. Capital Cost (CAPEX)")
    lines.append(f"- Low: {_format_currency(capex['total_capex_AUD']['low'])} AUD")
    lines.append(f"- Typical: {_format_currency(capex['total_capex_AUD']['typical'])} AUD (incl. {capex['contingency_pct']:.0f}% contingency)")
    lines.append(f"- High: {_format_currency(capex['total_capex_AUD']['high'])} AUD")
    lines.append(f"*(Class 4–5 estimate, ±40–50%)*")
    lines.append("")
    lines.append("## 6. Operating Cost (OPEX)")
    lines.append(f"- Total Annual OPEX: {_format_currency(opex['total_annual_opex_AUD'])} AUD/yr")
    lines.append(f"- Unit OPEX: {opex['unit_opex_AUD_ML']:.0f} AUD/ML")
    lines.append(f"  - Energy: {_format_currency(opex['energy_AUD'])}/yr")
    lines.append(f"  - Chemicals: {_format_currency(opex['chemicals_AUD'])}/yr")
    lines.append(f"  - Maintenance: {_format_currency(opex['maintenance_AUD'])}/yr")
    lines.append(f"  - Labour: {_format_currency(opex['labour_AUD'])}/yr")
    lines.append(f"  - Membrane Replacement: {_format_currency(opex['membrane_replacement_AUD'])}/yr")
    lines.append(f"  - Media Replacement: {_format_currency(opex['media_replacement_AUD'])}/yr")
    lines.append("")
    lines.append("## 7. Lifecycle Cost (NPV)")
    lines.append(f"- CAPEX (Year 0): {_format_currency(lcost['capex_AUD'])} AUD ({lcost['capex_fraction_pct']:.0f}% of NPV)")
    lines.append(f"- PV of OPEX: {_format_currency(lcost['pv_opex_AUD'])} AUD ({lcost['opex_fraction_pct']:.0f}% of NPV)")
    lines.append(f"- **Total NPV: {_format_currency(lcost['npv_total_AUD'])} AUD**")
    lines.append(f"- Parameters: {lcost['analysis_period_years']}yr, {lcost['discount_rate_pct']:.1f}% discount, {lcost['opex_escalation_pct']:.1f}% OPEX escalation")
    lines.append("")
    lines.append("## 8. Risk Assessment")
    overall = risk.get("overall", {})
    lines.append(f"- Implementation Risk: {overall.get('implementation_label', '—')}")
    lines.append(f"- Operational Risk: {overall.get('operational_label', '—')}")
    lines.append(f"- Regulatory Risk: {overall.get('regulatory_label', '—')}")
    lines.append(f"- **Overall Risk: {overall.get('overall_label', '—')}**")
    for flag in risk.get("water_quality_risk_flags", []):
        lines.append(f"  - ⚠ {flag}")
    lines.append("")
    lines.append("## 9. Environmental")
    lines.append(f"- Annual Energy GHG: {env['annual_energy_CO2_tonnes']:,.0f} t CO₂-e/yr")
    lines.append(f"- Annual Chemical GHG: {env['annual_chemical_CO2_tonnes']:,.0f} t CO₂-e/yr")
    lines.append(f"- Total Annual GHG: {env['total_annual_CO2_tonnes']:,.0f} t CO₂-e/yr")
    lines.append(f"- Unit GHG: {env['unit_CO2_kg_per_kL']:.3f} kg CO₂-e/kL")
    for flag in env.get("residuals_considerations", []):
        lines.append(f"  - {flag}")
    lines.append("")
    lines.append("## 10. Regulatory Compliance")
    lines.append(f"**Framework:** {reg.get('framework', 'ADWG 2022')}")
    lines.append(f"**Overall Status:** {'Compliant' if reg['overall_compliant'] else 'Exceedances identified'}")
    for note in reg.get("regulatory_notes", []):
        lines.append(f"- ⚠ {note}")
    lines.append("")
    lines.append("## 11. MCA Score")
    lines.append(f"**Total: {mca['total_score']:.0f}/100**")
    for criterion, score in mca["scores"].items():
        weight = mca["weights"].get(criterion, 0)
        lines.append(f"- {criterion.replace('_', ' ').title()}: {score:.0f}/100 (weight: {weight*100:.0f}%)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*This report is generated by AquaPoint for decision-support purposes. "
                 "All cost estimates are Class 4–5 (±40–50%). "
                 "Engage registered engineers for detailed design and procurement. "
                 "ph2o Consulting | Water Utility Planning Platform.*")

    return "\n".join(lines)


def render():
    st.markdown("""
        <div style="margin-bottom:1.5rem">
            <h2 style="color:#e8f4fd;font-size:1.4rem;font-weight:600;margin-bottom:0.3rem">
                Export Report
            </h2>
            <p style="color:#8899aa;font-size:0.9rem;margin:0">
                Download a structured analysis report for client delivery or internal records.
            </p>
        </div>
    """, unsafe_allow_html=True)

    results = st.session_state.get("last_results")
    if not results:
        from ..ui_helpers import warning_box
        warning_box("No analysis results found. Please run the analysis first.")
        if st.button("← Back to Results"):
            st.session_state["current_page"] = "results"
            st.rerun()
        return

    section_header("Report Preview", "📄")

    inputs = {
        "plant_type": st.session_state.get("plant_type", "conventional"),
        "flow_ML_d": st.session_state.get("flow_ML_d", 10.0),
        "source_water": st.session_state.get("source_water", {}),
        "selected_technologies": st.session_state.get("selected_technologies", []),
    }

    report_text = _build_report_text(inputs, results)

    # Preview in expander
    with st.expander("Preview Report (Markdown)", expanded=True):
        st.markdown(report_text)

    # Download button
    project_name = st.session_state.get("project_name", "AquaPoint_Report").replace(" ", "_")
    today_str = date.today().strftime("%Y%m%d")
    filename = f"{project_name}_AquaPoint_{today_str}.md"

    st.download_button(
        label="⬇ Download Report (Markdown)",
        data=report_text,
        file_name=filename,
        mime="text/markdown",
        type="primary",
        use_container_width=True,
    )

    success_box(f"Report ready for download: {filename}")

    info_box(
        "The downloaded report is a Markdown file (.md) compatible with Word, Notion, "
        "Confluence, GitHub, and most documentation platforms. "
        "Full Word export (.docx) is on the AquaPoint roadmap."
    )

    st.markdown("<br>", unsafe_allow_html=True)
    left, _ = st.columns([1, 3])
    with left:
        if st.button("← Back to Results", use_container_width=True):
            st.session_state["current_page"] = "results"
            st.rerun()
