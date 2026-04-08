"""page_06_failure_modes.py"""
import streamlit as st
from ..ui_helpers import section_header, info_box, warning_box, action_badge
from ..engine import FAILURE_SCENARIOS, CLASS_COLOURS


def render_failure_modes():
    result = st.session_state.get("purepoint_result")
    if result is None:
        st.warning("Run the assessment first.")
        return

    st.markdown("## Failure Mode Analysis")
    st.markdown(
        "Tests the treatment train for each class under four failure scenarios. "
        "The action column defines the required operational response — continue, divert, or shutdown."
    )

    # Failure mode tables — one per scenario
    classes = list(result.classes.keys())

    for scenario in FAILURE_SCENARIOS:
        key = scenario["key"]
        st.markdown("---")
        section_header(scenario["scenario"], "⚠️")

        header_cols = st.columns([3] + [2] * len(classes))
        header_cols[0].markdown("**Assessment**")
        for i, cls in enumerate(classes):
            colour = CLASS_COLOURS.get(cls, "#8fa3b8")
            header_cols[i + 1].markdown(
                f"<span style='color:{colour};font-weight:600;'>Class {cls}</span>",
                unsafe_allow_html=True,
            )

        for field, label in [("lrv", "LRV impact"), ("chem", "Chemical protection"), ("action", "Required action")]:
            row_cols = st.columns([3] + [2] * len(classes))
            row_cols[0].markdown(f"*{label}*")
            for i, cls in enumerate(classes):
                cr = result.classes.get(cls)
                fm = cr.failure_modes.get(key, {}) if cr else {}
                val = fm.get(field, "—")
                if field == "action":
                    row_cols[i + 1].markdown(action_badge(val), unsafe_allow_html=True)
                else:
                    row_cols[i + 1].markdown(
                        f"<span style='font-size:0.82rem;color:#8fa3b8'>{val}</span>",
                        unsafe_allow_html=True,
                    )

    # WaterPoint interface sensitivities
    st.markdown("---")
    section_header("WaterPoint interface — effluent quality sensitivities", "🔗")
    info_box(
        "These sensitivities show how changes in WaterPoint effluent quality affect PurePoint "
        "treatment intensity, operational risk, and class feasibility."
    )

    header_cols = st.columns([3, 4, 1.5])
    header_cols[0].markdown("**WaterPoint parameter**")
    header_cols[1].markdown("**Impact on PurePoint**")
    header_cols[2].markdown("**Severity**")

    from ..ui_helpers import risk_badge
    for sens in result.wp_sensitivities:
        st.markdown("---")
        cols = st.columns([3, 4, 1.5])
        cols[0].markdown(f"**{sens['parameter']}**")
        cols[1].markdown(
            f"<span style='font-size:0.85rem;color:#8fa3b8'>{sens['impact']}</span>",
            unsafe_allow_html=True,
        )
        cols[2].markdown(risk_badge(sens["severity"]), unsafe_allow_html=True)
