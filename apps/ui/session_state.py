"""
apps/shared/session_state.py

Shared session state management for Streamlit applications.
Provides a clean interface for reading and writing project/scenario state
across all domain apps.
"""

from __future__ import annotations
from typing import Optional
import streamlit as st

from core.project.project_model import ProjectModel, ScenarioModel


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE KEYS
# ─────────────────────────────────────────────────────────────────────────────

KEY_PROJECT = "current_project"
KEY_SCENARIO_ID = "active_scenario_id"
KEY_LAST_CALC = "last_calculation_result"
KEY_UNSAVED_CHANGES = "has_unsaved_changes"


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT ACCESS
# ─────────────────────────────────────────────────────────────────────────────

def get_current_project() -> Optional[ProjectModel]:
    """Return the current project from session state, or None."""
    return st.session_state.get(KEY_PROJECT)


def set_current_project(project: ProjectModel) -> None:
    """Store a project in session state and sync the active scenario ID."""
    st.session_state[KEY_PROJECT] = project
    if project.active_scenario_id:
        st.session_state[KEY_SCENARIO_ID] = project.active_scenario_id
    st.session_state[KEY_UNSAVED_CHANGES] = False


def update_current_project(project: ProjectModel) -> None:
    """Update project in session state and mark unsaved changes."""
    st.session_state[KEY_PROJECT] = project
    st.session_state[KEY_UNSAVED_CHANGES] = True


def has_project() -> bool:
    """Return True if a project is loaded in session state."""
    return KEY_PROJECT in st.session_state and st.session_state[KEY_PROJECT] is not None


def has_unsaved_changes() -> bool:
    return st.session_state.get(KEY_UNSAVED_CHANGES, False)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO ACCESS
# ─────────────────────────────────────────────────────────────────────────────

def get_active_scenario(project: Optional[ProjectModel] = None) -> Optional[ScenarioModel]:
    """Return the active scenario from the given project (or session project)."""
    proj = project or get_current_project()
    if proj is None:
        return None
    return proj.get_active_scenario()


def set_active_scenario(scenario_id: str) -> None:
    """Set the active scenario in both project and session state."""
    project = get_current_project()
    if project:
        project.set_active_scenario(scenario_id)
        st.session_state[KEY_SCENARIO_ID] = scenario_id


def get_active_scenario_id() -> Optional[str]:
    return st.session_state.get(KEY_SCENARIO_ID)


# ─────────────────────────────────────────────────────────────────────────────
# CALCULATION RESULT CACHE
# ─────────────────────────────────────────────────────────────────────────────

def cache_calculation_result(result: object) -> None:
    st.session_state[KEY_LAST_CALC] = result


def get_cached_calculation_result() -> Optional[object]:
    return st.session_state.get(KEY_LAST_CALC)


def clear_calculation_cache() -> None:
    st.session_state.pop(KEY_LAST_CALC, None)


# ─────────────────────────────────────────────────────────────────────────────
# INITIALISATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def initialise_session_defaults() -> None:
    """Called once on app start to ensure all keys are present."""
    defaults = {
        KEY_PROJECT: None,
        KEY_SCENARIO_ID: None,
        KEY_LAST_CALC: None,
        KEY_UNSAVED_CHANGES: False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def require_project(error_message: str = "Please create or load a project first.") -> bool:
    """
    Guard function for pages that require an active project.
    Returns True if a project is loaded; shows error and returns False otherwise.
    """
    if not has_project():
        st.error(f"⚠️ {error_message}")
        st.stop()
        return False
    return True


def mark_scenario_stale() -> None:
    """Mark the active scenario as needing recalculation."""
    project = get_current_project()
    if project:
        scenario = project.get_active_scenario()
        if scenario:
            scenario.mark_stale()
            clear_calculation_cache()
