"""
AquaPoint — Page 1: Project Setup
"""
import streamlit as st
from ..engine.constants import PLANT_TYPES, LIFECYCLE_DEFAULTS, APP_NAME
from ..ui_helpers import section_header, info_box


def render():
    st.markdown(f"""
        <div style="margin-bottom:1.5rem">
            <h2 style="color:#e8f4fd;font-size:1.4rem;font-weight:600;margin-bottom:0.3rem">
                Project Setup
            </h2>
            <p style="color:#8899aa;font-size:0.9rem;margin:0">
                Define project parameters, plant type, and design flow for your drinking water treatment analysis.
            </p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])

    with col1:
        # ── Project Details ──────────────────────────────────────────────────
        section_header("Project Details", "📋")

        project_name = st.text_input(
            "Project Name",
            value=st.session_state.get("project_name", ""),
            placeholder="e.g. Merri Creek Regional WTP Upgrade",
        )
        st.session_state["project_name"] = project_name

        col_a, col_b = st.columns(2)
        with col_a:
            client = st.text_input(
                "Client / Utility",
                value=st.session_state.get("client", ""),
                placeholder="e.g. Melbourne Water",
            )
            st.session_state["client"] = client
        with col_b:
            location = st.text_input(
                "Location",
                value=st.session_state.get("location", ""),
                placeholder="e.g. Epping, VIC",
            )
            st.session_state["location"] = location

        author = st.text_input(
            "Prepared By",
            value=st.session_state.get("author", ""),
            placeholder="Engineer name",
        )
        st.session_state["author"] = author

        # ── Plant Type ───────────────────────────────────────────────────────
        section_header("Plant Type", "🏭")

        plant_options = list(PLANT_TYPES.keys())
        plant_labels = [f"{v['icon']} {v['label']}" for v in PLANT_TYPES.values()]
        current_plant = st.session_state.get("plant_type", plant_options[0])
        current_idx = plant_options.index(current_plant) if current_plant in plant_options else 0

        selected_idx = st.radio(
            "Select plant type",
            range(len(plant_options)),
            format_func=lambda i: plant_labels[i],
            index=current_idx,
            label_visibility="collapsed",
        )
        selected_plant_key = plant_options[selected_idx]
        selected_plant = PLANT_TYPES[selected_plant_key]
        st.session_state["plant_type"] = selected_plant_key

        info_box(selected_plant["description"])

        # ── Design Flow ──────────────────────────────────────────────────────
        section_header("Design Flow", "💧")

        flow_min, flow_max = selected_plant["typical_flow_range_ML_d"]
        flow_default = st.session_state.get("flow_ML_d", max(flow_min, min(10.0, flow_max)))

        col_f1, col_f2 = st.columns([3, 1])
        with col_f1:
            flow_ML_d = st.number_input(
                "Average Day Design Flow (ML/d)",
                min_value=0.1,
                max_value=1000.0,
                value=float(flow_default),
                step=0.5,
                format="%.1f",
            )
        with col_f2:
            st.markdown("<br>", unsafe_allow_html=True)
            st.metric("Annual (ML)", f"{flow_ML_d * 365:,.0f}")

        st.session_state["flow_ML_d"] = flow_ML_d

        if flow_ML_d < flow_min or flow_ML_d > flow_max:
            from ..ui_helpers import warning_box
            warning_box(
                f"Note: {flow_ML_d} ML/d is outside the typical range for this plant type "
                f"({flow_min}–{flow_max} ML/d). Analysis will proceed."
            )

        # Peak flow factor
        peak_factor = st.slider(
            "Peak Day Factor (× average day)",
            min_value=1.1,
            max_value=3.0,
            value=st.session_state.get("peak_factor", 1.5),
            step=0.1,
            help="Used to size treatment units. Typically 1.3–2.0 for surface water plants.",
        )
        st.session_state["peak_factor"] = peak_factor

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.metric("Peak Day Flow (ML/d)", f"{flow_ML_d * peak_factor:.1f}")
        with col_p2:
            st.metric("Peak Day Flow (L/s)", f"{flow_ML_d * peak_factor * 1e6 / 86400:.1f}")

    with col2:
        # ── Lifecycle Parameters ─────────────────────────────────────────────
        section_header("Lifecycle Parameters", "📊")

        analysis_period = st.number_input(
            "Analysis Period (years)",
            min_value=10,
            max_value=50,
            value=st.session_state.get("analysis_period", LIFECYCLE_DEFAULTS["analysis_period_years"]),
            step=5,
        )
        st.session_state["analysis_period"] = analysis_period

        discount_rate = st.number_input(
            "Discount Rate (%)",
            min_value=1.0,
            max_value=15.0,
            value=st.session_state.get("discount_rate", LIFECYCLE_DEFAULTS["discount_rate_pct"]),
            step=0.5,
            format="%.1f",
        )
        st.session_state["discount_rate"] = discount_rate

        opex_escalation = st.number_input(
            "OPEX Escalation Rate (%/yr)",
            min_value=0.0,
            max_value=8.0,
            value=st.session_state.get("opex_escalation", LIFECYCLE_DEFAULTS["opex_escalation_pct"]),
            step=0.5,
            format="%.1f",
        )
        st.session_state["opex_escalation"] = opex_escalation

        contingency = st.slider(
            "CAPEX Contingency (%)",
            min_value=5,
            max_value=40,
            value=st.session_state.get("capex_contingency", int(LIFECYCLE_DEFAULTS["capex_contingency_pct"])),
            step=5,
        )
        st.session_state["capex_contingency"] = contingency

        # ── Electricity Cost ─────────────────────────────────────────────────
        section_header("Energy Cost", "⚡")

        electricity_cost = st.number_input(
            "Electricity Cost (AUD/kWh)",
            min_value=0.05,
            max_value=0.50,
            value=st.session_state.get("electricity_cost", 0.12),
            step=0.01,
            format="%.3f",
        )
        st.session_state["electricity_cost"] = electricity_cost

        # ── Summary Card ─────────────────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        section_header("Setup Summary", "✓")

        summary_items = [
            ("Plant Type", selected_plant["label"]),
            ("Avg Day Flow", f"{flow_ML_d:.1f} ML/d"),
            ("Peak Day Flow", f"{flow_ML_d * peak_factor:.1f} ML/d"),
            ("Analysis Period", f"{analysis_period} years"),
            ("Discount Rate", f"{discount_rate:.1f}%"),
            ("Contingency", f"{contingency}%"),
            ("Electricity", f"${electricity_cost:.3f}/kWh"),
        ]

        for label, val in summary_items:
            st.markdown(f"""
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:0.3rem 0;border-bottom:1px solid #1e2d3d">
                    <span style="color:#8899aa;font-size:0.82rem">{label}</span>
                    <span style="color:#e8f4fd;font-size:0.85rem;font-weight:600">{val}</span>
                </div>
            """, unsafe_allow_html=True)

    # ── Navigation ────────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    _, right = st.columns([4, 1])
    with right:
        if st.button("Next → Source Water", type="primary", use_container_width=True):
            st.session_state["current_page"] = "source_water"
            st.rerun()
