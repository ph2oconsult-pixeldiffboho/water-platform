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
    check_data_gate, assemble_report_data, REGULATORY_CONTEXTS,
)
from engine.tier1_report import generate_tier1_report


REGULATORY_OPTIONS = {
    "epa_vic":      "EPA Victoria",
    "sydney_water": "Sydney Water / NSW EPA",
    "qld_des":      "Queensland DES / Seqwater / Council",
    "sa_water":     "SA Water / EPA South Australia",
    "wa_water":     "Water Corporation WA / DWER",
    "nz":           "Watercare / NZ EPA",
    "custom":       "Custom / Specify",
}

SECTION_ICONS = {
    "mad":               ("🔬", "MAD Analyser",         "Digester physics results"),
    "comparison":        ("⚖️",  "Config Comparison",    "Four-way configuration comparison"),
    "pathway_rankings":  ("📊", "Pathway Rankings",     "Full pathway scoring"),
    "drying":            ("🔥", "Drying & Coupling",    "Thermal drying options"),
    "its_pfas":          ("🛡️",  "ITS & PFAS",          "Regulatory pathway analysis"),
    "pyrolysis":         ("📈", "Pyrolysis",            "Pyrolysis envelope"),
    "carbon_ghg":        ("🌍", "Carbon & GHG",        "Unified GHG picture"),
}


def render():
    st.header("📋 Tier 1 Report")
    st.caption(
        "Generates a full Tier 1 MAD & THP screening assessment. "
        "Requires the MAD Analyser and Config Comparison to be run first."
    )

    ss = st.session_state

    # ── Data gate ──────────────────────────────────────────────────────────
    gate = check_data_gate(ss)

    # Always show data availability
    st.subheader("Data availability")
    cols = st.columns(4)
    for idx, (key, (icon, label, desc)) in enumerate(SECTION_ICONS.items()):
        available = gate.available.get(key, False)
        required  = key in ("mad", "comparison")
        with cols[idx % 4]:
            st.markdown(
                f"{'✅' if available else '🔴' if required else '⬜'} "
                f"**{icon} {label}**"
                f"{' *(required)*' if required else ' *(optional)*'}"
            )
            st.caption(desc)

    # Hard gate
    if not gate.passed:
        st.error("**Report cannot be generated — complete these steps first:**")
        for m in gate.missing:
            st.markdown(f"❌  {m}")
        st.info(
            "**Workflow:** run 🔬 MAD Analyser → then ⚖️ Config Comparison "
            "(click **Run Comparison**) → then return here.",
            icon="👆",
        )
        return

    if gate.warnings:
        with st.expander("⚠️  Optional sections will be omitted", expanded=False):
            for w in gate.warnings:
                st.warning(w)

    st.divider()

    # ── Report settings ────────────────────────────────────────────────────
    st.subheader("Report settings")
    c1, c2 = st.columns(2)
    with c1:
        project_name = st.text_input("Project name",
            value=ss.get("cmp_project", ss.get("mad_project_name", "BioPoint Analysis")),
            key="t1_project_name")
        prepared_by = st.text_input("Prepared by",
            value=ss.get("cmp_prepby", ss.get("mad_prepared_by", "ph2o Consulting")),
            key="t1_prepared_by")
        prepared_for = st.text_input("Prepared for (client)",
            value=ss.get("t1_prepared_for", ""), key="t1_prepared_for")
    with c2:
        project_number = st.text_input("Project / document number",
            value=ss.get("t1_project_number", ""), key="t1_project_number")
        revision = st.selectbox("Revision",
            ["A", "B", "C", "0", "1", "2"], key="t1_revision")
        reg_key = st.selectbox("Regulatory context",
            list(REGULATORY_OPTIONS.keys()),
            format_func=lambda k: REGULATORY_OPTIONS[k],
            key="t1_regulatory")

    with st.expander("Advanced GHG assumptions", expanded=False):
        n2o_options = {
            0.010: "IPCC default (0.010 kg N2O-N/kg N) — recommended for screening",
            0.003: "Conservative (0.003) — well-managed application sites",
            0.025: "High (0.025) — wet soils, high N loading",
            0.000: "Zero — incineration / thermal treatment pathway (no land application)",
        }
        n2o_ef = st.selectbox("N₂O emission factor basis",
            options=list(n2o_options.keys()),
            format_func=lambda k: n2o_options[k],
            index=0, key="t1_n2o_ef")
        st.caption(
            "The N2O emission factor is the single most influential assumption in the "
            "GHG analysis for land-applied biosolids. Select Zero if the long-term "
            "pathway is thermal treatment (incineration/pyrolysis) rather than land application.")

    with st.expander("Project background (optional)", expanded=False):
        client_context = st.text_area("Brief project description",
            value=ss.get("t1_client_context", ""), height=90,
            placeholder="e.g. Melbourne Water evaluating THP options at ETP ahead of 2027 EPA Class A deadline...",
            key="t1_client_context")

    st.divider()

    # ── Generate + download ────────────────────────────────────────────────
    col_gen, col_dl = st.columns([2, 3])

    with col_gen:
        if st.button("📋 Generate Tier 1 Report", type="primary", use_container_width=True):
            cfg = {
                "project_name":   project_name,
                "prepared_by":    prepared_by,
                "prepared_for":   prepared_for,
                "project_number": project_number,
                "revision":       revision,
                "regulatory_key": reg_key,
                "client_context": client_context,
            }
            with st.spinner("Building report…"):
                try:
                    data = assemble_report_data(ss, cfg)
                    pdf  = generate_tier1_report(data)
                    ss["t1_report_pdf"]  = pdf
                    ss["t1_report_name"] = project_name.replace(" ", "_")
                    st.success(f"Report ready — {len(pdf)//1024} kB", icon="✅")
                except Exception as ex:
                    st.error(f"Generation failed: {ex}")
                    st.exception(ex)

    with col_dl:
        if "t1_report_pdf" in ss:
            st.download_button(
                "⬇  Download PDF",
                data=ss["t1_report_pdf"],
                file_name=f"BioPoint_Tier1_{ss.get('t1_report_name','Report')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
        else:
            st.caption("Generate the report first, then download here.")
