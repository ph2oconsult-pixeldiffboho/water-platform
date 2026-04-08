"""page_03_class_assessment.py"""
import streamlit as st
from ..ui_helpers import (
    section_header, warning_box, success_box, info_box,
    feasibility_card, class_header_bar, margin_badge, lrv_status_badge,
)
from ..engine import CLASS_LABELS, CLASS_COLOURS


def render_class_assessment():
    result = st.session_state.get("purepoint_result")
    if result is None:
        st.warning("No assessment results found. Please complete Effluent Quality and run the assessment.")
        return

    st.markdown("## Class Assessment")
    inputs = result.inputs

    # Governing constraints
    if result.governing_constraints:
        section_header("Governing constraints", "⚠️")
        for c in result.governing_constraints:
            warning_box(c)
        st.markdown("")

    # Feasibility overview cards
    section_header("Class feasibility overview", "✅")
    cols = st.columns(len(result.classes))
    for col, (cls, cr) in zip(cols, result.classes.items()):
        with col:
            feasibility_card(cls, cr.status, cr.feasible, len(cr.warnings))

    st.markdown("---")

    # Per-class detail
    section_header("WaterVal LRV assessment — by class", "🔬")
    tabs = st.tabs([f"Class {cls}" for cls in result.classes])

    for tab, (cls, cr) in zip(tabs, result.classes.items()):
        with tab:
            class_header_bar(cls)

            # Warnings
            if cr.warnings:
                for w in cr.warnings:
                    warning_box(w)

            if cr.lrv_penalty_note:
                warning_box(cr.lrv_penalty_note)

            # LRV table
            st.markdown("**Barrier-credit LRV table**")
            header_cols = st.columns([3, 1.5, 1.5, 1.5])
            header_cols[0].markdown("**Barrier**")
            header_cols[1].markdown("**Protozoa**")
            header_cols[2].markdown("**Bacteria**")
            header_cols[3].markdown("**Virus**")

            for barrier in cr.lrv_barriers:
                row = st.columns([3, 1.5, 1.5, 1.5])
                row[0].markdown(barrier["barrier"])
                row[1].markdown(f"`{barrier['protozoa'] or '—'}`")
                row[2].markdown(f"`{barrier['bacteria'] or '—'}`")
                row[3].markdown(f"`{barrier['virus'] or '—'}`")

            st.markdown("---")
            st.markdown("**Achieved vs Required**")

            for pathogen in ["protozoa", "bacteria", "virus"]:
                achieved = cr.lrv_achieved.get(pathogen, 0)
                required = cr.lrv_required.get(pathogen, 0)
                margin = cr.lrv_margin.get(pathogen, 0)
                row = st.columns([3, 1.5, 1.5, 1.5, 3])
                row[0].markdown(f"**{pathogen.capitalize()}**")
                row[1].markdown(f"`{achieved}`")
                row[2].markdown(f"`{required}` required")
                row[3].markdown(margin_badge(margin), unsafe_allow_html=True)
                row[4].markdown(lrv_status_badge(margin), unsafe_allow_html=True)

    st.markdown("---")

    # Upgrade pathway
    section_header("Upgrade pathway — C → A → A+ → PRW", "⬆️")
    upgrade_cols = st.columns(4)
    for col, (cls, delta) in zip(upgrade_cols, result.upgrade_deltas.items()):
        colour = CLASS_COLOURS.get(cls, "#8fa3b8")
        with col:
            st.markdown(
                f'<div style="border-top:3px solid {colour};padding:10px 0;">'
                f'<div style="font-weight:600;color:{colour};margin-bottom:6px;">Class {cls}</div>'
                f'<div style="font-size:0.82rem;color:#6b7a8d;">{delta}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )

    info_box(
        "Design for the upgrade pathway from day one. "
        "Locate civil works and pipe routes to allow future additions without demolition."
    )
