"""
PurePoint — app.py
PAGES dict, run(), render_sidebar()
Follows the AquaPoint app.py pattern exactly.
Registered in apps/main_app.py as the prw_app route.
"""

import streamlit as st
from .pages import (
    render_project_setup,
    render_effluent_quality,
    render_class_assessment,
    render_treatment_trains,
    render_chemical_matrix,
    render_failure_modes,
    render_report,
    render_manual,
)
from .engine import CLASS_COLOURS

# ---------------------------------------------------------------------------
# PAGES dict — mirrors AquaPoint convention exactly
# number: display order in nav
# label: sidebar label
# icon: emoji prefix
# render: render function
# ---------------------------------------------------------------------------

PAGES = {
    "project_setup": {
        "number": 1,
        "label": "Project Setup",
        "icon": "🏗️",
        "render": render_project_setup,
    },
    "effluent_quality": {
        "number": 2,
        "label": "Effluent Quality",
        "icon": "💧",
        "render": render_effluent_quality,
    },
    "class_assessment": {
        "number": 3,
        "label": "Class Assessment",
        "icon": "✅",
        "render": render_class_assessment,
    },
    "treatment_trains": {
        "number": 4,
        "label": "Treatment Trains",
        "icon": "⚙️",
        "render": render_treatment_trains,
    },
    "chemical_matrix": {
        "number": 5,
        "label": "Chemical Matrix",
        "icon": "🧪",
        "render": render_chemical_matrix,
    },
    "failure_modes": {
        "number": 6,
        "label": "Failure Modes",
        "icon": "⚠️",
        "render": render_failure_modes,
    },
    "report": {
        "number": 7,
        "label": "Report",
        "icon": "📄",
        "render": render_report,
    },
    "manual": {
        "number": 8,
        "label": "User Manual",
        "icon": "📖",
        "render": render_manual,
    },
}

# Default landing page
_DEFAULT_PAGE = "project_setup"

# Session state key for current page
_PAGE_KEY = "pp_page"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar():
    """Render PurePoint navigation sidebar."""
    st.sidebar.markdown("""
    <div style="padding:1.1rem 0.2rem 0.6rem 0.2rem;text-align:center;">
        <div style="font-size:2rem;line-height:1;margin-bottom:4px;">♻️</div>
        <div style="font-size:1.25rem;font-weight:800;color:#1a2b4a;letter-spacing:-0.02em;margin-bottom:2px;">PurePoint</div>
        <div style="font-size:0.65rem;color:#7a8499;text-transform:uppercase;letter-spacing:0.08em;">Advanced Water Reuse Engine</div>
    </div>
    """, unsafe_allow_html=True)

    if st.sidebar.button("⬅  Platform Home", key="pp_home", use_container_width=True):
        for _k in ("active_app", _PAGE_KEY, "_app_context"):
            st.session_state.pop(_k, None)
        st.rerun()

    st.sidebar.markdown(
        "<div style='font-size:0.62rem;font-weight:700;color:#9aa0ad;text-transform:uppercase;"
        "letter-spacing:0.1em;padding:0.6rem 0 0.3rem 0.1rem;'>Navigate</div>",
        unsafe_allow_html=True,
    )

    current = st.session_state.get(_PAGE_KEY, _DEFAULT_PAGE)

    for key, page in PAGES.items():
        label = f"{page['icon']} {page['number']}. {page['label']}"
        is_current = key == current

        # Highlight active page
        if is_current:
            st.sidebar.markdown(
                f"<div style='background:#00b4d811;border-left:3px solid #00b4d8;"
                f"padding:6px 10px;border-radius:0 4px 4px 0;margin:2px 0;"
                f"font-weight:600;font-size:0.88rem;color:#00b4d8;'>{label}</div>",
                unsafe_allow_html=True,
            )
        else:
            if st.sidebar.button(label, key=f"pp_nav_{key}", use_container_width=True):
                st.session_state[_PAGE_KEY] = key
                st.rerun()

    st.sidebar.markdown("---")

    # Assessment status indicator
    result = st.session_state.get("purepoint_result")
    if result:
        st.sidebar.markdown(
            "<span style='font-size:0.75rem;color:#22c87a;'>✓ Assessment complete</span>",
            unsafe_allow_html=True,
        )
        classes = list(result.classes.keys())
        for cls in classes:
            cr = result.classes[cls]
            colour = CLASS_COLOURS.get(cls, "#8fa3b8")
            icon = "✓" if cr.feasible else "⚠"
            st.sidebar.markdown(
                f"<span style='font-size:0.75rem;color:{colour};'>"
                f"{icon} Class {cls}: {cr.status}"
                f"</span>",
                unsafe_allow_html=True,
            )
    else:
        st.sidebar.markdown(
            "<span style='font-size:0.75rem;color:#8fa3b8;'>No assessment run yet</span>",
            unsafe_allow_html=True,
        )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='font-size:0.67rem;color:#9aa0ad;text-align:center;padding:0.5rem 0 0.2rem 0;line-height:1.6;'>"
        "PurePoint v1.0<br>ph2o Consulting</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run():
    """
    Main entry point called by apps/main_app.py.
    Renders sidebar + active page.
    """
    render_sidebar()

    current_key = st.session_state.get(_PAGE_KEY, _DEFAULT_PAGE)
    page = PAGES.get(current_key, PAGES[_DEFAULT_PAGE])
    page["render"]()
