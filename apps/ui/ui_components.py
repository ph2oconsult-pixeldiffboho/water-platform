"""
apps/shared/ui_components.py

Shared Streamlit UI components used across all four domain applications.
All domain apps import from this module to maintain a consistent UX.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from core.project.project_model import (
    CostResult, CarbonResult, RiskResult, ValidationResult, ValidationLevel,
)

# ── Colour palette ─────────────────────────────────────────────────────────
COLOURS = {
    "primary": "#1f6aa5",
    "secondary": "#2ca02c",
    "warning": "#ff7f0e",
    "danger": "#d62728",
    "neutral": "#7f7f7f",
    "scope1": "#d62728",
    "scope2": "#ff7f0e",
    "scope3": "#9467bd",
    "avoided": "#2ca02c",
    "capex": "#1f6aa5",
    "opex": "#aec7e8",
    "risk_low": "#2ca02c",
    "risk_medium": "#ff7f0e",
    "risk_high": "#d62728",
    "risk_very_high": "#7b0000",
}

RISK_LEVEL_COLOURS = {
    "Low": COLOURS["risk_low"],
    "Medium": COLOURS["risk_medium"],
    "High": COLOURS["risk_high"],
    "Very High": COLOURS["risk_very_high"],
}


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION BANNER
# ─────────────────────────────────────────────────────────────────────────────

def render_validation_banner(validation_result: ValidationResult) -> None:
    """Display validation messages as coloured banners."""
    if not validation_result:
        return

    messages = validation_result.messages

    critical = [m for m in messages if m.get("level") == "critical"]
    warnings = [m for m in messages if m.get("level") == "warning"]
    infos = [m for m in messages if m.get("level") == "info"]

    for msg in critical:
        st.error(f"❌ **{msg.get('field', 'Error')}:** {msg.get('message', '')}")

    for msg in warnings:
        st.warning(f"⚠️ **{msg.get('field', 'Warning')}:** {msg.get('message', '')}")

    for msg in infos:
        st.info(f"ℹ️ {msg.get('message', '')}")


# ─────────────────────────────────────────────────────────────────────────────
# COST SUMMARY CARD
# ─────────────────────────────────────────────────────────────────────────────

def render_cost_summary_card(cost_result: CostResult) -> None:
    """Display a cost summary metric card row."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="CAPEX",
            value=f"${cost_result.capex_total/1e6:.2f}M",
            help=f"Capital cost — confidence {cost_result.cost_confidence}",
        )
    with col2:
        st.metric(
            label="OPEX (per year)",
            value=f"${cost_result.opex_annual/1e3:.0f}k",
        )
    with col3:
        st.metric(
            label="Annualised Lifecycle Cost",
            value=f"${cost_result.lifecycle_cost_annual/1e3:.0f}k/yr",
            help=f"Over {cost_result.analysis_period_years} year analysis period",
        )
    with col4:
        if cost_result.specific_cost_per_kl is not None:
            st.metric(
                label="Specific Cost",
                value=f"${cost_result.specific_cost_per_kl:.2f}/kL",
            )
        elif cost_result.specific_cost_per_tonne_ds is not None:
            st.metric(
                label="Specific Cost",
                value=f"${cost_result.specific_cost_per_tonne_ds:.0f}/t DS",
            )

    # CAPEX breakdown chart
    if cost_result.capex_breakdown:
        st.subheader("CAPEX Breakdown")
        fig = _build_horizontal_bar(
            labels=list(cost_result.capex_breakdown.keys()),
            values=[v / 1e6 for v in cost_result.capex_breakdown.values()],
            xlabel="Cost ($M)",
            colour=COLOURS["capex"],
        )
        st.plotly_chart(fig, use_container_width=True)

    # OPEX breakdown
    if cost_result.opex_breakdown:
        st.subheader("Annual OPEX Breakdown")
        fig2 = _build_horizontal_bar(
            labels=list(cost_result.opex_breakdown.keys()),
            values=[v / 1e3 for v in cost_result.opex_breakdown.values()],
            xlabel="Annual Cost ($k/yr)",
            colour=COLOURS["opex"],
        )
        st.plotly_chart(fig2, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# CARBON SUMMARY CARD
# ─────────────────────────────────────────────────────────────────────────────

def render_carbon_summary_card(carbon_result: CarbonResult) -> None:
    """Display a carbon summary metric card row and stacked bar chart."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Net Emissions",
            value=f"{carbon_result.net_tco2e_yr:.0f} tCO₂e/yr",
        )
    with col2:
        st.metric(
            label="Scope 2 (Electricity)",
            value=f"{carbon_result.scope_2_tco2e_yr:.0f} tCO₂e/yr",
            help=f"Grid factor: {carbon_result.grid_emission_factor_used} kg CO₂e/kWh",
        )
    with col3:
        st.metric(
            label="Avoided Emissions",
            value=f"{carbon_result.avoided_tco2e_yr:.0f} tCO₂e/yr",
        )
    with col4:
        if carbon_result.specific_kg_co2e_per_kl is not None:
            st.metric(
                label="Carbon Intensity",
                value=f"{carbon_result.specific_kg_co2e_per_kl:.3f} kg CO₂e/kL",
            )

    # Waterfall chart: Scope 1 + 2 + 3 - Avoided = Net
    st.subheader("Carbon Breakdown")
    fig = _build_carbon_waterfall(carbon_result)
    st.plotly_chart(fig, use_container_width=True)


def _build_carbon_waterfall(carbon_result: CarbonResult) -> go.Figure:
    labels = ["Scope 1\n(Process)", "Scope 2\n(Electricity)", "Scope 3\n(Chemicals & Embodied)",
              "Avoided\nEmissions", "Net"]
    values = [
        carbon_result.scope_1_tco2e_yr,
        carbon_result.scope_2_tco2e_yr,
        carbon_result.scope_3_tco2e_yr,
        -carbon_result.avoided_tco2e_yr,
        carbon_result.net_tco2e_yr,
    ]
    colours = [
        COLOURS["scope1"],
        COLOURS["scope2"],
        COLOURS["scope3"],
        COLOURS["avoided"],
        COLOURS["primary"] if carbon_result.net_tco2e_yr >= 0 else COLOURS["secondary"],
    ]

    fig = go.Figure(go.Bar(
        x=labels,
        y=values,
        marker_color=colours,
        text=[f"{v:,.0f}" for v in values],
        textposition="auto",
    ))
    fig.update_layout(
        yaxis_title="tCO₂e / year",
        plot_bgcolor="white",
        height=350,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# RISK MATRIX / SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def render_risk_matrix(risk_result: RiskResult) -> None:
    """Display risk scores and the risk item table."""
    colour = RISK_LEVEL_COLOURS.get(risk_result.overall_level, COLOURS["neutral"])

    st.markdown(
        f"<h3 style='color:{colour}'>Overall Risk: {risk_result.overall_level} "
        f"({risk_result.overall_score:.0f}/100)</h3>",
        unsafe_allow_html=True,
    )

    if risk_result.risk_narrative:
        st.markdown(risk_result.risk_narrative)

    # Category radar chart
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Risk by Category")
        categories = ["Technical", "Implementation", "Operational", "Regulatory"]
        scores = [
            risk_result.technical_score,
            risk_result.implementation_score,
            risk_result.operational_score,
            risk_result.regulatory_score,
        ]
        fig = _build_risk_radar(categories, scores)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Category Scores")
        df = pd.DataFrame({
            "Category": categories,
            "Score (0–100)": [round(s, 1) for s in scores],
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Risk item table
    st.subheader("Risk Item Register")
    if risk_result.risk_items:
        rows = []
        for item in risk_result.risk_items:
            rows.append({
                "Category": item.category.title(),
                "Risk": item.name,
                "L": item.likelihood,
                "C": item.consequence,
                "Score": int(item.score),
                "Level": _score_to_level(item.score),
                "Mitigation": item.mitigation,
            })
        df_risks = pd.DataFrame(rows)

        # Colour the Level column
        def colour_level(val: str) -> str:
            c = RISK_LEVEL_COLOURS.get(val, "white")
            return f"background-color: {c}; color: white; font-weight: bold"

        styled = df_risks.style.map(colour_level, subset=["Level"])
        st.dataframe(styled, use_container_width=True, hide_index=True)


def _score_to_level(score: float) -> str:
    if score <= 6:
        return "Low"
    elif score <= 12:
        return "Medium"
    elif score <= 20:
        return "High"
    return "Very High"


def _build_risk_radar(categories: List[str], scores: List[float]) -> go.Figure:
    cats = categories + [categories[0]]
    vals = scores + [scores[0]]
    fig = go.Figure(go.Scatterpolar(
        r=vals,
        theta=cats,
        fill="toself",
        fillcolor="rgba(31, 106, 165, 0.3)",
        line_color=COLOURS["primary"],
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        height=300,
        margin=dict(l=40, r=40, t=40, b=40),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# COMPARISON TABLE
# ─────────────────────────────────────────────────────────────────────────────

def render_comparison_table(comparison_data: List[Dict]) -> None:
    """Render a multi-scenario comparison table."""
    if not comparison_data:
        st.info("No scenario data available for comparison.")
        return

    df = pd.DataFrame(comparison_data)

    # Select display columns
    display_cols = [
        c for c in [
            "scenario_name", "technologies",
            "capex_total_m", "opex_annual_k", "lifecycle_cost_annual_k",
            "net_tco2e_yr", "overall_risk_level", "overall_risk_score",
            "is_preferred",
        ]
        if c in df.columns
    ]

    rename_map = {
        "scenario_name": "Scenario",
        "technologies": "Technologies",
        "capex_total_m": "CAPEX ($M)",
        "opex_annual_k": "OPEX (k$/yr)",
        "lifecycle_cost_annual_k": "Lifecycle (k$/yr)",
        "net_tco2e_yr": "Net Carbon (tCO₂e/yr)",
        "overall_risk_level": "Risk Level",
        "overall_risk_score": "Risk Score",
        "is_preferred": "Preferred",
    }

    display_df = df[display_cols].rename(columns=rename_map)
    st.dataframe(display_df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# ASSUMPTIONS EDITOR
# ─────────────────────────────────────────────────────────────────────────────

def render_assumptions_editor(
    assumptions,
    category: str = "engineering",
    title: str = "Engineering Assumptions",
) -> Dict[str, Any]:
    """
    Render an editable table of assumptions.
    Returns a dict of {key: new_value} for any changes made.
    """
    st.subheader(title)
    cat_dict: Dict = getattr(assumptions, f"{category}_assumptions", {})
    overrides: Dict[str, Any] = {}

    for key, default_val in cat_dict.items():
        if isinstance(default_val, dict):
            continue  # Skip nested dicts — handled separately
        if isinstance(default_val, (int, float)):
            is_override = f"{category}.{key}" in assumptions.user_overrides
            label = f"{'⭐ ' if is_override else ''}{key}"
            new_val = st.number_input(
                label=label,
                value=float(default_val),
                key=f"assump_{category}_{key}",
                help=f"Default: {default_val}",
                format="%g",
            )
            if new_val != float(default_val):
                overrides[key] = new_val

    return overrides


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO SELECTOR
# ─────────────────────────────────────────────────────────────────────────────

def render_scenario_selector(project, label: str = "Active Scenario") -> Optional[str]:
    """Render a scenario selector dropdown. Updates active scenario and reruns on change."""
    if not project or not project.scenarios:
        st.warning("No scenarios found in this project.")
        return None

    scenario_options = {
        s.scenario_name: sid
        for sid, s in project.scenarios.items()
    }

    current_name = None
    if project.active_scenario_id and project.active_scenario_id in project.scenarios:
        current_name = project.scenarios[project.active_scenario_id].scenario_name

    selected_name = st.selectbox(
        label=label,
        options=list(scenario_options.keys()),
        index=list(scenario_options.keys()).index(current_name)
        if current_name in scenario_options else 0,
    )

    selected_id = scenario_options.get(selected_name)

    # If the user switched scenarios, update active and rerun so all page data refreshes
    if selected_id and selected_id != project.active_scenario_id:
        project.set_active_scenario(selected_id)
        from apps.ui.session_state import update_current_project
        update_current_project(project)
        st.rerun()

    return selected_id


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _build_horizontal_bar(
    labels: List[str],
    values: List[float],
    xlabel: str,
    colour: str,
) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker_color=colour,
        text=[f"{v:,.2f}" for v in values],
        textposition="auto",
    ))
    fig.update_layout(
        xaxis_title=xlabel,
        plot_bgcolor="white",
        height=max(250, 40 * len(labels)),
        margin=dict(l=200, r=20, t=20, b=40),
    )
    return fig


def stale_warning() -> None:
    """Banner shown when scenario results are outdated."""
    st.warning(
        "⏳ Results are out of date — inputs have changed since the last calculation. "
        "Run the calculation to refresh."
    )


def render_page_header(title: str, subtitle: str = "") -> None:
    """Consistent page header across all apps."""
    st.title(title)
    if subtitle:
        st.markdown(f"*{subtitle}*")
    st.divider()
