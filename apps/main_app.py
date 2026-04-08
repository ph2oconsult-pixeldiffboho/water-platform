"""
apps/main_app.py

Water Utility Planning Platform — main launcher.
Run with: streamlit run apps/main_app.py

This is the platform homepage. It presents the four domain applications
and routes the user to the correct module.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(
    page_title="Water Utility Planning Platform",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .app-card {
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 12px;
        padding: 28px 24px;
        text-align: center;
        transition: box-shadow 0.2s;
        height: 260px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: flex-start;
    }
    .app-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.10); }
    .app-icon { font-size: 3rem; margin-bottom: 12px; flex-shrink: 0; }
    .app-title { font-size: 1.2rem; font-weight: 700; color: #1f6aa5; margin-bottom: 8px; flex-shrink: 0; }
    .app-desc  { font-size: 0.9rem; color: #555; margin-bottom: 0; flex-grow: 1; }
    .app-card .status-badge { margin-top: auto; }
    .platform-header { text-align: center; padding: 32px 0 8px 0; }
    .status-badge {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 600;
        padding: 2px 10px;
        border-radius: 99px;
        margin-top: 10px;
    }
    .badge-ready    { background: #d4edda; color: #155724; }
    .badge-coming   { background: #fff3cd; color: #856404; }

    /* ── Unified sidebar ───────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: #f0f2f6;
        border-right: 1px solid #dde1e7;
    }
    .sb-header { padding: 1.1rem 0.2rem 0.6rem 0.2rem; text-align: center; }
    .sb-app-icon { font-size: 2rem; line-height: 1; margin-bottom: 4px; }
    .sb-app-name { font-size: 1.25rem; font-weight: 800; color: #1a2b4a;
                   letter-spacing: -0.02em; margin-bottom: 2px; }
    .sb-app-sub  { font-size: 0.65rem; color: #7a8499; text-transform: uppercase;
                   letter-spacing: 0.08em; }
    .sb-section  { font-size: 0.62rem; font-weight: 700; color: #9aa0ad;
                   text-transform: uppercase; letter-spacing: 0.1em;
                   padding: 0.6rem 0 0.3rem 0.1rem; }
    .sb-footer   { font-size: 0.67rem; color: #9aa0ad; text-align: center;
                   padding: 0.5rem 0 0.2rem 0; line-height: 1.6; }

    /* Active nav button */
    [data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
        background: #e8f4f0 !important;
        color: #0d6e57 !important;
        border: 1px solid #b2d8cc !important;
        border-left: 3px solid #0d9e7a !important;
        font-weight: 700 !important;
        text-align: left !important;
    }
    /* Inactive nav buttons */
    [data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {
        background: #ffffff !important;
        color: #2c3a4f !important;
        border: 1px solid #dde1e7 !important;
        font-weight: 500 !important;
        text-align: left !important;
    }
    [data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
        background: #f5f7fa !important;
        border-color: #bcc3ce !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="platform-header">
    <h1>💧 Water Utility Planning Platform</h1>
    <p style="color:#555; font-size:1.1rem;">
        Integrated concept-stage planning for water utilities and consultants
    </p>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Application cards ──────────────────────────────────────────────────────
APPS = [
    {
        "icon": "🌊",
        "title": "Wastewater Treatment",
        "description": (
            "Activated sludge, BNR, MBR and advanced biological processes. "
            "Lifecycle costing, carbon analysis, and risk assessment."
        ),
        "key": "wastewater",
        "status": "ready",
        "status_label": "✓ Available",
    },
    {
        "icon": "🚰",
        "title": "Drinking Water Treatment",
        "description": (
            "Coagulation, DAF, filtration, GAC, UF/NF/RO, AOP and disinfection. "
            "Catchment to tap planning."
        ),
        "key": "drinking_water",
        "status": "ready",
        "status_label": "✓ Available",
    },
    {
        "icon": "♻️",
        "title": "Purified Recycled Water",
        "description": (
            "Advanced water treatment trains. LRV calculations, QMRA, "
            "HACCP/CCP framework and indirect potable reuse planning."
        ),
        "key": "prw",
        "status": "coming",
        "status_label": "Coming — Stage 3",
    },
    {
        "icon": "🌱",
        "title": "Biosolids & Sludge Management",
        "description": (
            "Digestion, dewatering, thermal drying, pyrolysis and land application. "
            "Mass and energy balance with end-use pathway analysis."
        ),
        "key": "biosolids",
        "status": "ready",
        "status_label": "✓ Available",
    },
]

cols = st.columns(4, gap="large")

for col, app in zip(cols, APPS):
    with col:
        badge_class = "badge-ready" if app["status"] == "ready" else "badge-coming"
        st.markdown(f"""
        <div class="app-card">
            <div class="app-icon">{app["icon"]}</div>
            <div class="app-title">{app["title"]}</div>
            <div class="app-desc">{app["description"]}</div>
            <span class="status-badge {badge_class}">{app["status_label"]}</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        if app["status"] == "ready":
            if st.button(
                f"Open {app['title'].split()[0]} Planner →",
                key=f"btn_{app['key']}",
                type="primary",
                use_container_width=True,
            ):
                st.session_state["launch_app"] = app["key"]
                st.rerun()
        else:
            st.button(
                "Not yet available",
                key=f"btn_{app['key']}",
                disabled=True,
                use_container_width=True,
            )

# ── App routing ────────────────────────────────────────────────────────────

# Resolve any pending launch → active transition first
_pending = st.session_state.pop("launch_app", None)
if _pending:
    st.session_state["active_app"] = _pending

_active = st.session_state.get("active_app")

if _active == "drinking_water":
    from apps.drinking_water_app.app import run as run_aquapoint
    run_aquapoint()

elif _active == "biosolids":
    import sys
    from pathlib import Path as _Path
    _bp_dir = _Path(__file__).resolve().parent / "biosolids_app"
    if str(_bp_dir) not in sys.path:
        sys.path.insert(0, str(_bp_dir))
    _bp_sidebar = st.sidebar
    with _bp_sidebar:
        st.markdown("""
        <div class="sb-header">
            <div class="sb-app-icon">🌱</div>
            <div class="sb-app-name">BioPoint</div>
            <div class="sb-app-sub">Biosolids Decision Engine</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("⬅  Platform Home", key="bp_home", use_container_width=True):
            for _k in ("active_app", "page", "_app_context"):
                st.session_state.pop(_k, None)
            st.rerun()

        st.markdown("<div class='sb-section'>Navigate</div>", unsafe_allow_html=True)

    BP_PAGES = {
        "📂  Load Data":          "00_load_data",
        "⚙️  Inputs":             "01_inputs",
        "📊  Pathway Rankings":   "02_results",
        "🔥  Drying & Coupling":  "03_drying",
        "🛡️  ITS & PFAS":         "04_pathways",
        "📈  Pyrolysis Envelope": "05_pyrolysis",
    }
    if st.session_state.get("_app_context") != "biosolids":
        st.session_state["page"] = "01_inputs"
        st.session_state["_app_context"] = "biosolids"

    current_bp_page = st.session_state.get("page", "01_inputs")
    for label, page_val in BP_PAGES.items():
        is_active = current_bp_page == page_val
        btn_type = "primary" if is_active else "secondary"
        if _bp_sidebar.button(label, key=f"bp_nav_{page_val}", type=btn_type, use_container_width=True):
            st.session_state["page"] = page_val
            st.rerun()

    page_key = st.session_state.get("page", "01_inputs")
    if page_key == "00_load_data":
        from apps.biosolids_app.pages import page_00_load_data; page_00_load_data.render()
    elif page_key == "01_inputs":
        from apps.biosolids_app.pages import page_01_inputs; page_01_inputs.render()
    elif page_key == "02_results":
        from apps.biosolids_app.pages import page_02_results; page_02_results.render()
    elif page_key == "03_drying":
        from apps.biosolids_app.pages import page_03_drying; page_03_drying.render()
    elif page_key == "04_pathways":
        from apps.biosolids_app.pages import page_04_pathways; page_04_pathways.render()
    elif page_key == "05_pyrolysis":
        from apps.biosolids_app.pages import page_05_pyrolysis; page_05_pyrolysis.render()
    _bp_sidebar.markdown("<div class='sb-footer'>BioPoint V1<br>ph2o Consulting</div>", unsafe_allow_html=True)

elif _active == "wastewater":
    # Import and initialise shared session state
    from apps.ui.session_state import initialise_session_defaults
    initialise_session_defaults()

    # Only set page to project_setup on first entry (not on every rerender)
    if "page" not in st.session_state:
        st.session_state["page"] = "01_project_setup"

    # Render the full wastewater app inline
    _ww_sidebar = st.sidebar
    with _ww_sidebar:
        st.markdown("""
        <div class="sb-header">
            <div class="sb-app-icon">💧</div>
            <div class="sb-app-name">WaterPoint</div>
            <div class="sb-app-sub">Wastewater Treatment</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("⬅  Platform Home", key="ww_home", use_container_width=True):
            for _k in ("active_app", "page", "_app_context"):
                st.session_state.pop(_k, None)
            st.rerun()

        st.markdown("<div class='sb-section'>Navigate</div>", unsafe_allow_html=True)

    PAGES = {
        "🏠  Project Setup":           "01_project_setup",
        "📋  Inputs":                  "02_inputs",
        "⚙️  Treatment Selection":     "03_treatment_selection",
        "📊  Results":                 "04_results",
        "🫧  Aeration System":         "04b_aeration",
        "♻️  Biosolids & Sludge":      "04c_biosolids",
        "🧪  PFAS & Risk":             "04d_pfas",
        "🔁  Compare Scenarios":       "05_comparison",
        "📄  Report":                  "06_report",
        "🔬  Plant Data & Calibration":"07_calibration",
        "📖  User Manual":             "08_manual",
    }

    current_ww_page = st.session_state.get("page", "01_project_setup")
    if current_ww_page not in PAGES.values():
        current_ww_page = "01_project_setup"
        st.session_state["page"] = current_ww_page

    for label, page_val in PAGES.items():
        is_active = current_ww_page == page_val
        btn_type = "primary" if is_active else "secondary"
        if _ww_sidebar.button(label, key=f"ww_nav_{page_val}", type=btn_type, use_container_width=True):
            st.session_state["page"] = page_val
            st.rerun()

    page_key = st.session_state["page"]

    if page_key == "01_project_setup":
        from apps.wastewater_app.pages import page_01_project_setup
        page_01_project_setup.render()
    elif page_key == "02_inputs":
        from apps.wastewater_app.pages import page_02_inputs
        page_02_inputs.render()
    elif page_key == "03_treatment_selection":
        from apps.wastewater_app.pages import page_03_treatment_selection
        page_03_treatment_selection.render()
    elif page_key == "04_results":
        from apps.wastewater_app.pages import page_04_results
        page_04_results.render()
    elif page_key == "04b_aeration":
        from apps.wastewater_app.pages import page_04b_aeration
        page_04b_aeration.render()
    elif page_key == "04c_biosolids":
        from apps.wastewater_app.pages import page_04c_biosolids
        page_04c_biosolids.render()
    elif page_key == "04d_pfas":
        from apps.wastewater_app.pages import page_04d_pfas
        page_04d_pfas.render()
    elif page_key == "05_comparison":
        from apps.wastewater_app.pages import page_05_comparison
        page_05_comparison.render()
    elif page_key == "06_report":
        from apps.wastewater_app.pages import page_06_report
        page_06_report.render()
    elif page_key == "07_calibration":
        from apps.wastewater_app.pages import page_07_calibration
        page_07_calibration.render()
    elif page_key == "08_manual":
        from apps.wastewater_app.pages import page_08_manual
        page_08_manual.render()

    # Sidebar footer
    from apps.ui.session_state import has_project, has_unsaved_changes, get_current_project
    from core.project.project_manager import ProjectManager
    if has_project():
        project = get_current_project()
        _ww_sidebar.markdown("<div class='sb-section'>Current Project</div>", unsafe_allow_html=True)
        _ww_sidebar.caption(f"📁 {project.metadata.project_name}")
        _ww_sidebar.caption(f"🌊 {project.metadata.plant_name or 'No plant set'}")
        if has_unsaved_changes():
            if _ww_sidebar.button("💾 Save Project", type="primary", use_container_width=True):
                ProjectManager().save(project)
                st.session_state["has_unsaved_changes"] = False
                _ww_sidebar.success("Saved ✓")
    try:
        import subprocess
        _git_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
        _git_date = subprocess.check_output(
            ["git", "log", "-1", "--format=%cd", "--date=format:%d %b %H:%M"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
        _ww_sidebar.markdown(f"<div class='sb-footer'>WaterPoint · ph2o Consulting<br><code>{_git_hash}</code> · {_git_date}</div>", unsafe_allow_html=True)
    except Exception:
        _ww_sidebar.markdown("<div class='sb-footer'>WaterPoint · ph2o Consulting</div>", unsafe_allow_html=True)

# ── Platform footer (homepage only) ───────────────────────────────────────
else:
    st.divider()
    st.markdown("""
    <div style="text-align:center; color:#888; font-size:0.85rem; padding: 8px 0 24px 0;">
        Water Utility Planning Platform &nbsp;·&nbsp; v1.0.0
        &nbsp;·&nbsp; Concept-stage planning tool for water utilities and consultants
    </div>
    """, unsafe_allow_html=True)

    # ── About section ──────────────────────────────────────────────────────
    with st.expander("About this platform"):
        st.markdown("""
        ### One shared brain. Four specialist applications.

        This platform provides concept-stage decision support across the full water cycle.
        All four applications share a common engine for:

        - **Lifecycle costing** — CAPEX, OPEX, and annualised cost
        - **Carbon accounting** — Scope 1, 2 and 3 emissions with avoided credit
        - **Risk assessment** — Technical, implementation, operational and regulatory risk
        - **Scenario comparison** — Side-by-side multi-option analysis
        - **Report generation** — Structured outputs ready for client delivery

        Domain-specific engineering science (treatment train calculations, process design,
        LRV analysis, mass and energy balances) is isolated within each application module.

        **Build order:** Wastewater → Biosolids → Drinking Water → PRW

        **To run a specific app directly:**
        ```
        streamlit run apps/wastewater_app/app.py
        ```
        """)
