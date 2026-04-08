"""page_05_chemical_matrix.py"""
import streamlit as st
from ..ui_helpers import section_header, info_box, risk_badge, class_header_bar
from ..engine import CHEMICAL_GROUPS


def render_chemical_matrix():
    result = st.session_state.get("purepoint_result")
    if result is None:
        st.warning("Run the assessment first.")
        return

    st.markdown("## Chemical Contaminant Matrix")
    st.markdown(
        "Barrier-credit assessment for seven chemical contaminant groups across all assessed classes. "
        "Residual risk reflects the risk remaining after the recommended treatment train is applied."
    )

    tabs = st.tabs([f"Class {cls}" for cls in result.classes])

    for tab, (cls, cr) in zip(tabs, result.classes.items()):
        with tab:
            class_header_bar(cls)
            matrix = cr.chem_matrix

            header = st.columns([2, 1.2, 2.5, 1.8, 2.5, 1.5])
            header[0].markdown("**Chemical group**")
            header[1].markdown("**Risk**")
            header[2].markdown("**Barrier / mechanism**")
            header[3].markdown("**Credit**")
            header[4].markdown("**CCP surrogate**")
            header[5].markdown("**Residual risk**")

            for group in CHEMICAL_GROUPS:
                row_data = matrix.get(group, {})
                st.markdown("---")
                cols = st.columns([2, 1.2, 2.5, 1.8, 2.5, 1.5])
                cols[0].markdown(f"**{group}**")
                cols[1].markdown(risk_badge(row_data.get("risk", "")), unsafe_allow_html=True)
                cols[2].markdown(
                    f"<span style='font-size:0.82rem'>{row_data.get('mechanism', '')}</span>",
                    unsafe_allow_html=True,
                )
                cols[3].markdown(
                    f"<span style='font-size:0.82rem'>{row_data.get('credit', '')}</span>",
                    unsafe_allow_html=True,
                )
                cols[4].markdown(
                    f"<span style='font-size:0.82rem;color:#8fa3b8'>{row_data.get('surrogate', '')}</span>",
                    unsafe_allow_html=True,
                )
                cols[5].markdown(risk_badge(row_data.get("residual_risk", "")), unsafe_allow_html=True)

    # Bioassay section
    st.markdown("---")
    section_header("Bioassay layer", "🧬")
    info_box(
        "Bioassay is a chemical safety proxy — not a sole compliance method. "
        "Use multi-endpoint panels (ER-CALUX, DR-CALUX, genotoxicity, cytotoxicity) "
        "as a trend indicator and early warning system. "
        "Bioassay results trigger investigation and analytical confirmation — they do not replace it."
    )

    bioassay_rows = [
        ("Rapid screening", "Bioassay panels applied to process stream samples provide early warning of chemical breakthrough before individual compound analytics would detect it."),
        ("Trend indicator", "Sequential bioassay across process stages maps removal efficiency per barrier. Rising trend post-BAC or post-UV signals media exhaustion or lamp degradation."),
        ("Chemical safety proxy", "For A+ and PRW, multi-endpoint bioassay (genotoxicity, estrogenicity, AhR activity, cytotoxicity) provides system-level verification of chemical transformation performance."),
        ("NOT sole compliance", "Bioassay never replaces analytical chemistry for compliance. It informs operational decisions and investigation priority — not regulatory sign-off."),
    ]

    for role, desc in bioassay_rows:
        col1, col2 = st.columns([2, 5])
        col1.markdown(f"**{role}**")
        col2.markdown(f"<span style='font-size:0.85rem;color:#8fa3b8'>{desc}</span>", unsafe_allow_html=True)
        st.markdown("")

    st.markdown(
        "<span style='font-size:0.8rem;color:#4a6070;font-style:italic'>"
        "Recommended minimum: monthly bioassay for A+; fortnightly for PRW during commissioning. "
        "Annual trend review for all classes in operation."
        "</span>",
        unsafe_allow_html=True,
    )
