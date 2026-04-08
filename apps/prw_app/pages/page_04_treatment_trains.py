"""page_04_treatment_trains.py"""
import streamlit as st
from ..ui_helpers import section_header, info_box, warning_box, class_header_bar
from ..engine import CLASS_COLOURS, CCP_FRAMEWORK


def render_treatment_trains():
    result = st.session_state.get("purepoint_result")
    if result is None:
        st.warning("Run the assessment first.")
        return

    st.markdown("## Treatment Trains")
    st.markdown(
        "Minimum-sufficient treatment trains for each assessed class. "
        "Key barriers are those that carry primary LRV or chemical treatment credit."
    )

    # Treatment trains
    for cls, cr in result.classes.items():
        st.markdown("---")
        class_header_bar(cls)
        train = cr.train
        colour = CLASS_COLOURS.get(cls, "#8fa3b8")

        # Flow display
        steps = train.get("steps", [])
        key_barriers = train.get("key_barriers", [])

        flow_html = ""
        for i, step in enumerate(steps):
            is_key = step in key_barriers
            bg = f"{colour}22" if is_key else "#1a2636"
            border = colour if is_key else "#1e2d3d"
            text_col = colour if is_key else "#e2eaf2"
            flow_html += (
                f'<span style="background:{bg};border:1px solid {border};'
                f'border-radius:3px;padding:4px 10px;font-family:monospace;'
                f'font-size:0.8rem;color:{text_col};white-space:nowrap;">{step}</span>'
            )
            if i < len(steps) - 1:
                flow_html += '<span style="color:#4a6070;margin:0 4px;">→</span>'

        st.markdown(
            f'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;'
            f'padding:12px;background:#111820;border:1px solid #1e2d3d;border-radius:4px;">'
            f"{flow_html}</div>",
            unsafe_allow_html=True,
        )

        # Design note
        st.markdown(
            f'<div style="font-size:0.85rem;color:#8fa3b8;margin:8px 0 4px;">'
            f"{train.get('note', '')}</div>",
            unsafe_allow_html=True,
        )

        # Annotations
        for ann in train.get("annotations", []):
            warning_box(ann)

    # CCP framework
    st.markdown("---")
    section_header("CCP and surrogate monitoring framework", "📡")
    info_box(
        "CCPs are the critical control points where barrier performance is verified in real time. "
        "Each CCP parameter must be continuously monitored with defined alarm thresholds."
    )

    ccp_rows = result.ccp_table
    if not ccp_rows:
        ccp_rows = CCP_FRAMEWORK

    header = st.columns([2, 2.5, 2, 2, 2.5])
    header[0].markdown("**Barrier**")
    header[1].markdown("**Mechanism**")
    header[2].markdown("**CCP parameter**")
    header[3].markdown("**Operating envelope**")
    header[4].markdown("**Failure indicator / response**")

    for row in ccp_rows:
        st.markdown("---")
        cols = st.columns([2, 2.5, 2, 2, 2.5])
        cols[0].markdown(f"**{row['barrier']}**")
        cols[1].markdown(f"<span style='font-size:0.85rem'>{row['mechanism']}</span>", unsafe_allow_html=True)
        cols[2].markdown(
            f"<span style='font-size:0.85rem;color:#00b4d8;font-family:monospace'>{row['ccp']}</span>",
            unsafe_allow_html=True,
        )
        cols[3].markdown(f"<span style='font-size:0.85rem'>{row['envelope']}</span>", unsafe_allow_html=True)
        cols[4].markdown(
            f"<span style='font-size:0.85rem;color:#f05252'>{row['failure']}</span>",
            unsafe_allow_html=True,
        )
