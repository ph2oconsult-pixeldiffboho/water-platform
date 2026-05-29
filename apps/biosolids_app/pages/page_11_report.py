"""
apps/biosolids_app/pages/page_11_report.py
BioPoint V1 — Tier 1 Report Generator.
ph2o Consulting — v25B02
"""
import sys
from pathlib import Path
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from engine.tier1_data import (
    check_data_gate, assemble_report_data,
    REGULATORY_CONTEXTS,
)
from engine.tier1_report import generate_tier1_report


REGULATORY_OPTIONS = {
    "epa_vic":     "EPA Victoria",
    "sydney_water":"Sydney Water / NSW EPA",
    "sa_water":    "SA Water / EPA South Australia",
    "wa_water":    "Water Corporation WA / DWER",
    "nz":          "Watercare / NZ EPA",
    "custom":      "Custom / Specify",
}

SECTION_ICONS = {
    "mad":              ("🔬", "MAD Analyser",         "Digester physics results"),
    "comparison":       ("⚖️", "Config Comparison",    "Four-way configuration comparison"),
    "pathway_rankings": ("📊", "Pathway Rankings",     "Full pathway scoring table"),
    "drying":           ("🔥", "Drying & Coupling",    "Thermal drying options"),
    "its_pfas":         ("🛡️", "ITS & PFAS",          "Regulatory pathway analysis"),
    "pyrolysis":        ("📈", "Pyrolysis",            "Pyrolysis envelope analysis"),
    "carbon_ghg":       ("🌍", "Carbon & GHG",        "Unified GHG picture"),
}


def render():
    st.header("📋 Tier 1 Report")
    st.caption(
        "Generate a full Tier 1 options assessment report covering all analyses "
        "completed in this session. Mandatory analyses must be run first."
    )

    ss = st.session_state

    # ── Data gate check ───────────────────────────────────────────────────
    gate = check_data_gate(ss)

    # Show data availability status
    st.subheader("Data availability")
    cols = st.columns(4)
    col_idx = 0
    for key, (icon, label, desc) in SECTION_ICONS.items():
        available = gate.available.get(key, False)
        with cols[col_idx % 4]:
            status = "✅" if available else "⬜"
            required = key in ("mad", "comparison")
            req_label = " *(required)*" if required else " *(optional)*"
            st.markdown(f"{status} **{icon} {label}**{req_label}")
            st.caption(desc)
        col_idx += 1

    # Hard gate errors
    if not gate.passed:
        st.error("**Cannot generate report — mandatory data missing:**")
        for m in gate.missing:
            st.markdown(f"❌ {m}")
        st.info(
            "Run the mandatory analyses above, then return here to generate the report.",
            icon="ℹ️",
        )
        return

    # Warnings for missing optional sections
    if gate.warnings:
        with st.expander("⚠️ Warnings — optional sections will be omitted", expanded=True):
            for w in gate.warnings:
                st.warning(w)

    st.divider()

    # ── Report configuration ──────────────────────────────────────────────
    st.subheader("Report settings")

    c1, c2 = st.columns(2)
    with c1:
        project_name = st.text_input(
            "Project name",
            value=ss.get("cmp_project", ss.get("mad_project_name", "BioPoint Analysis")),
            key="t1_project_name",
        )
        prepared_by = st.text_input(
            "Prepared by",
            value=ss.get("cmp_prepby", ss.get("mad_prepared_by", "ph2o Consulting")),
            key="t1_prepared_by",
        )
        prepared_for = st.text_input(
            "Prepared for (client / authority)",
            value=ss.get("t1_prepared_for", ""),
            key="t1_prepared_for",
        )

    with c2:
        project_number = st.text_input(
            "Project / document number",
            value=ss.get("t1_project_number", ""),
            key="t1_project_number",
        )
        revision = st.selectbox(
            "Revision",
            options=["A", "B", "C", "0", "1", "2"],
            index=0,
            key="t1_revision",
        )
        reg_key = st.selectbox(
            "Regulatory context",
            options=list(REGULATORY_OPTIONS.keys()),
            format_func=lambda k: REGULATORY_OPTIONS[k],
            index=0,
            key="t1_regulatory",
        )

    # Client context — optional free text
    with st.expander("Project background (optional — appears in report context section)"):
        client_context = st.text_area(
            "Brief project description / context",
            value=ss.get("t1_client_context", ""),
            height=100,
            placeholder="e.g. Melbourne Water is evaluating options to upgrade biosolids "
                        "management at the Eastern Treatment Plant ahead of the 2027 EPA "
                        "Victoria Class A compliance deadline...",
            key="t1_client_context",
        )

    st.divider()

    # ── Sections preview ──────────────────────────────────────────────────
    st.subheader("Report will include")

    avail = gate.available
    always_sections = [
        "1. Executive Summary",
        "2. Project Context & Constraints",
        "3. Assessment Framework",
        "4. Digester Performance Assessment",
        "5. Operating Cost & GHG Assessment",
    ]
    sec = 6
    optional_sections = []
    if avail.get("comparison") and any(
        k in ss.get("cmp_result", type("x",(),{"included_ids":[]})()).included_ids
        if hasattr(ss.get("cmp_result"), "included_ids") else []
        for k in ("pre_thp","solidstream")
    ):
        optional_sections.append(f"{sec}. Heat Recovery & Steam Balance"); sec+=1
    optional_sections.append(f"{sec}. Recommended Pathway"); sec+=1
    optional_sections.append(f"{sec}. Next Steps"); sec+=1
    optional_sections.append(f"{sec}. Disclaimer")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Mandatory sections:**")
        for s in always_sections:
            st.markdown(f"  ✅ {s}")
    with col_b:
        st.markdown("**Additional sections:**")
        for s in optional_sections:
            st.markdown(f"  ✅ {s}")

    st.caption(
        "Optional analysis sections (Pathway Rankings, Drying, ITS/PFAS, Pyrolysis, "
        "Carbon & GHG) will be added automatically if those analyses have been run."
    )

    st.divider()

    # ── Generate button ───────────────────────────────────────────────────
    gen_col, dl_col = st.columns([2, 3])

    with gen_col:
        generate = st.button(
            "📋 Generate Tier 1 Report",
            type="primary",
            use_container_width=True,
        )

    if generate:
        report_cfg = {
            "project_name":   project_name,
            "prepared_by":    prepared_by,
            "prepared_for":   prepared_for,
            "project_number": project_number,
            "revision":       revision,
            "regulatory_key": reg_key,
            "client_context": client_context,
            "include_sankey": True,
        }
        with st.spinner("Assembling data and building report..."):
            try:
                data = assemble_report_data(ss, report_cfg)
                pdf  = generate_tier1_report(data)
                ss["t1_report_pdf"]  = pdf
                ss["t1_report_name"] = project_name.replace(" ", "_")
                st.success(
                    f"Report generated — {len(pdf)/1024:.0f} kB. "
                    "Download below.",
                    icon="✅",
                )
            except Exception as ex:
                st.error(f"Report generation failed: {ex}")
                st.exception(ex)
                return

    with dl_col:
        if "t1_report_pdf" in ss:
            proj = ss.get("t1_report_name", "BioPoint")
            st.download_button(
                "⬇ Download Tier 1 Report (PDF)",
                data=ss["t1_report_pdf"],
                file_name=f"BioPoint_Tier1_{proj}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
