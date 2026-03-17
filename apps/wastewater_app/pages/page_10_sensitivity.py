"""
apps/wastewater_app/pages/page_10_sensitivity.py

Phase 6: Structured Sensitivity Analysis
==========================================
Multi-driver sensitivity analysis with tornado chart and ranking table.
Helps planners understand what drives the lifecycle cost decision.
"""
from __future__ import annotations
import copy
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from apps.ui.session_state import require_project, get_current_project
from apps.ui.ui_components import render_page_header
from core.assumptions.assumptions_manager import AssumptionsManager
from core.project.project_model import DomainType
from core.costing.costing_engine import CostingEngine
from domains.wastewater.domain_interface import WastewaterDomainInterface
from domains.wastewater.input_model import WastewaterInputs


# Drivers: (key, label, base_value, low_mult, high_mult, unit)
SENSITIVITY_DRIVERS = [
    ("electricity_per_kwh",       "Electricity price",      0.14, 0.60, 1.80, "$/kWh"),
    ("sludge_disposal_per_tds",   "Sludge disposal cost",   280,  0.50, 2.00, "$/t DS"),
    ("carbon_price_per_tco2e",    "Carbon price",           35,   0.25, 3.00, "$/tCO₂e"),
    ("discount_rate_pct",         "Discount rate",          7.0,  0.43, 1.57, "%"),  # 3-11%
    ("influent_nh4_mg_l",         "Influent NH₄-N",         35,   0.57, 1.43, "mg/L"),  # 20-50
    ("cod_tkn_ratio",             "COD:TKN ratio",          11,   0.45, 1.82, "—"),  # 5-20
    ("influent_temperature_celsius", "Temperature",         20,   0.60, 1.00, "°C"),   # 12-20
    ("peak_flow_factor",          "Peak flow factor",       2.5,  0.60, 1.40, "×"),   # 1.5-3.5
]


def render() -> None:
    render_page_header(
        "📈 Sensitivity Analysis",
        subtitle="How key drivers affect lifecycle cost and option ranking",
    )

    project = require_project()
    if not project:
        return

    # Get calculated scenarios
    calc = [s for s in project.scenarios.values()
            if s.cost_result and s.domain_specific_outputs]

    if len(calc) < 1:
        st.info("Run calculations on at least one scenario to use sensitivity analysis.")
        return

    # Scenario selector
    scen_names = [s.scenario_name for s in calc]
    selected_name = st.selectbox("Scenario to analyse", scen_names)
    selected = next(s for s in calc if s.scenario_name == selected_name)

    st.caption(
        f"Showing sensitivity for **{selected_name}**. "
        "Each driver is varied from its low to high value while others are held at base. "
        "Results show how annualised lifecycle cost ($/kL) responds."
    )

    # Run sensitivity
    with st.spinner("Running sensitivity calculations…"):
        results = _run_sensitivity(selected, project)

    if not results:
        st.error("Could not run sensitivity — check that scenario has valid inputs.")
        return

    _render_tornado_chart(results, selected)
    _render_sensitivity_table(results, selected)
    _render_ranking_sensitivity(calc, results, selected)


def _run_sensitivity(scenario, project):
    """Run sensitivity on all drivers for the selected scenario."""
    base_a = getattr(scenario, "assumptions", None)
    if base_a is None:
        base_a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)

    di = scenario.domain_inputs or {}
    known = {f for f in WastewaterInputs.__dataclass_fields__ if not f.startswith("_")}
    clean = {k: v for k, v in di.items() if k in known}
    tech_codes = (scenario.treatment_pathway.technology_sequence
                  if scenario.treatment_pathway else [])

    base_lcc = scenario.cost_result.lifecycle_cost_annual
    base_kl  = scenario.cost_result.specific_cost_per_kl or 0

    results = []
    for (key, label, base_val, lo_mult, hi_mult, unit) in SENSITIVITY_DRIVERS:
        lo_val = base_val * lo_mult
        hi_val = base_val * hi_mult

        lo_kl = _calc_kl(scenario, base_a, clean, tech_codes, key, lo_val)
        hi_kl = _calc_kl(scenario, base_a, clean, tech_codes, key, hi_val)

        if lo_kl is not None and hi_kl is not None:
            swing = abs(hi_kl - lo_kl)
            results.append({
                "key":     key,
                "label":   label,
                "unit":    unit,
                "base_val": base_val,
                "lo_val":  lo_val,
                "hi_val":  hi_val,
                "base_kl": base_kl,
                "lo_kl":   lo_kl,
                "hi_kl":   hi_kl,
                "swing":   swing,
                "lo_delta": lo_kl - base_kl,
                "hi_delta": hi_kl - base_kl,
            })

    # Sort by swing
    results.sort(key=lambda x: x["swing"], reverse=True)
    return results


def _calc_kl(scenario, base_a, clean_inputs, tech_codes, driver_key, driver_val):
    """Calculate $/kL with one driver changed."""
    try:
        a = copy.deepcopy(base_a)
        inp_kw = dict(clean_inputs)

        # Apply driver override
        if driver_key == "electricity_per_kwh":
            a.cost_assumptions["opex_unit_rates"]["electricity_per_kwh"] = driver_val
        elif driver_key == "sludge_disposal_per_tds":
            a.cost_assumptions["opex_unit_rates"]["sludge_disposal_per_tds"] = driver_val
        elif driver_key == "carbon_price_per_tco2e":
            a.carbon_assumptions["carbon_price_per_tonne_co2e"] = driver_val
        elif driver_key == "discount_rate_pct":
            a.cost_assumptions["discount_rate"] = driver_val / 100.0
        elif driver_key == "influent_nh4_mg_l":
            inp_kw["influent_nh4_mg_l"] = driver_val
        elif driver_key == "cod_tkn_ratio":
            # Adjust BOD to achieve target COD:TKN
            tkn = inp_kw.get("influent_tkn_mg_l", 45)
            inp_kw["influent_bod_mg_l"] = driver_val * tkn / 2.0
        elif driver_key == "influent_temperature_celsius":
            inp_kw["influent_temperature_celsius"] = driver_val
        elif driver_key == "peak_flow_factor":
            inp_kw["peak_flow_factor"] = driver_val

        iface = WastewaterDomainInterface(a)
        inp = WastewaterInputs(**inp_kw)
        r = iface.run_scenario(inp, tech_codes, {})
        return r.cost_result.specific_cost_per_kl or 0
    except Exception:
        return None


def _render_tornado_chart(results, scenario):
    """Tornado chart showing $/kL swing per driver."""
    if not results:
        return

    st.subheader("🌪️ Tornado Chart — Lifecycle Cost Sensitivity")
    st.caption(
        "Each bar shows the $/kL swing from base when a driver moves from its low to high value. "
        "Longer bars = higher sensitivity. Base case shown as vertical reference line."
    )

    base_kl = results[0]["base_kl"] if results else 0
    labels = [r["label"] for r in results]
    lo_deltas = [r["lo_delta"] for r in results]
    hi_deltas = [r["hi_delta"] for r in results]

    fig = go.Figure()

    # Low bars (negative or positive depending on direction)
    fig.add_trace(go.Bar(
        name="Low value",
        y=labels,
        x=lo_deltas,
        orientation="h",
        marker_color="#2196F3",
        text=[f"{d:+.3f}" for d in lo_deltas],
        textposition="auto",
    ))
    fig.add_trace(go.Bar(
        name="High value",
        y=labels,
        x=hi_deltas,
        orientation="h",
        marker_color="#F44336",
        text=[f"{d:+.3f}" for d in hi_deltas],
        textposition="auto",
    ))

    fig.add_vline(x=0, line_width=2, line_color="black",
                  annotation_text=f"Base: ${base_kl:.3f}/kL",
                  annotation_position="top right")

    fig.update_layout(
        barmode="overlay",
        xaxis_title="Change in $/kL vs base case",
        yaxis_title="",
        height=max(300, len(results) * 45),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        plot_bgcolor="white",
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_sensitivity_table(results, scenario):
    """Table showing all driver values and resulting $/kL."""
    st.subheader("📊 Sensitivity Table")

    base_kl = results[0]["base_kl"] if results else 0
    rows = []
    for r in results:
        rows.append({
            "Driver":          r["label"],
            "Low value":       f"{r['lo_val']:.2f} {r['unit']}",
            "Base value":      f"{r['base_val']:.2f} {r['unit']}",
            "High value":      f"{r['hi_val']:.2f} {r['unit']}",
            "$/kL (low)":      f"${r['lo_kl']:.3f}",
            "$/kL (base)":     f"${r['base_kl']:.3f}",
            "$/kL (high)":     f"${r['hi_kl']:.3f}",
            "Swing ($/kL)":    f"${r['swing']:.3f}",
            "% of base":       f"{r['swing']/max(base_kl,0.001)*100:.0f}%",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(
        "Low/High values represent ±realistic planning range, not worst case. "
        "Hold all other inputs at base while varying each driver."
    )


def _render_ranking_sensitivity(calc, results, selected):
    """Show if option ranking changes when key drivers move."""
    if len(calc) < 2:
        return

    st.subheader("🔄 Ranking Stability")
    st.caption(
        "Shows whether the preferred option changes when the most sensitive driver "
        "moves from its base value to low and high extremes."
    )

    if not results:
        return

    # Take top 3 most sensitive drivers
    top_drivers = results[:3]

    base_a = getattr(selected, "assumptions", None)
    if base_a is None:
        base_a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)

    ranking_rows = []
    for scen in calc:
        di = scen.domain_inputs or {}
        row = {"Scenario": scen.scenario_name,
               "Base ($/kL)": f"${scen.cost_result.specific_cost_per_kl:.3f}" if scen.cost_result and scen.cost_result.specific_cost_per_kl else "—"}

        known = {f for f in WastewaterInputs.__dataclass_fields__ if not f.startswith("_")}
        clean = {k: v for k, v in di.items() if k in known}
        tech_codes = scen.treatment_pathway.technology_sequence if scen.treatment_pathway else []

        for drv in top_drivers[:2]:
            for case, val in [("Low", drv["lo_val"]), ("High", drv["hi_val"])]:
                kl = _calc_kl(scen, base_a, clean, tech_codes, drv["key"], val)
                col_name = f"{drv['label']} {case}"
                row[col_name] = f"${kl:.3f}" if kl else "—"

        ranking_rows.append(row)

    df = pd.DataFrame(ranking_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(
        "If ranking changes significantly between Base and Low/High columns, "
        "the preferred option is sensitive to that assumption — "
        "a deeper cost risk analysis is warranted."
    )
