"""
apps/biosolids_app/pages/page_13_strategy.py

BioPoint V2 - Interactive Strategy page.

Surfaces the V2 decision engine directly in the app: the PFAS trigger score and
the regret crossover it drives, optionality / reversibility / complexity, the
nitrogen strategy, the Commit / Preserve / Monitor capital allocation, and the
constraint-migration ladder. Reads biopoint_v2_spine straight through - no PDF.

Prototype scope: runs against the calibrated plant presets (ETP / Mangere /
generic). Wiring the entered Tier-1 inputs through (including phosphorus and a
plant biogas yield, which the V1 data model does not yet capture) is the next
step and also fixes the download-report bridge.

ph2o Consulting - BioPoint V2
"""
import os as _os
import sys as _sys

import streamlit as st

# --- Load the V2 spine, mirroring the bridge's path handling so the spine's
#     bare sibling imports resolve on Streamlit Cloud without shadowing stdlib. ---
_ED = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "engine")
if _ED not in _sys.path:
    _sys.path.append(_ED)

_SPINE_OK = True
_IMPORT_ERR = None
try:
    import biopoint_v2_spine as S
except Exception as _e:          # pragma: no cover - import-time guard
    _SPINE_OK = False
    _IMPORT_ERR = _e

try:
    import plotly.graph_objects as go
    _PLOTLY = True
except Exception:                # pragma: no cover
    _PLOTLY = False

import pandas as pd


PATHWAY_LABELS = ["Conventional", "K+", "THP-WAS", "Thermal"]


def _build_quartet(plant):
    """The four board pathways, in the same order the V2 reports use."""
    return [
        S.build_conventional_pathway(plant),
        S.build_pathway_k_plus(plant),
        S.build_worked_pathway(plant),
        S.build_thermal_pathway(plant),
    ]


def _plant_options():
    return {
        "ETP (220 tDS/d, calibrated)":     S.ETP,
        "Mangere (124 tDS/d, calibrated)": S.MANGERE,
        "Generic demonstrator":            S.GENERIC,
    }


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

def _tab_pfas(q):
    st.subheader("PFAS trigger score")
    st.caption(
        "The PFAS-ban likelihood is the single assumption that most drives the ranking, so it is "
        "derived rather than asserted. Set the drivers below - the weighted composite IS the ban "
        "probability - and watch the regret crossover move."
    )
    factors = {}
    cols = st.columns(len(S.PFAS_TRIGGER_WEIGHTS))
    for col, (k, w) in zip(cols, S.PFAS_TRIGGER_WEIGHTS.items()):
        with col:
            short = S.PFAS_TRIGGER_LABELS[k].split("(")[0].strip()
            factors[k] = st.slider(
                short, 0.0, 1.0, float(S.PFAS_TRIGGER_DEFAULTS[k]), 0.05,
                help=f"weight {w:.2f}", key=f"v2_trig_{k}",
            )
    pts = S.pfas_trigger_score(factors)
    prob = pts["ban_probability"]

    m1, m2 = st.columns([1, 2])
    with m1:
        st.metric("Derived PFAS ban probability", f"{prob * 100:.0f}%")
    rs_cur = S.regret_sensitivity(q, pfas_probs=(prob,))[0]
    winner = PATHWAY_LABELS[rs_cur["winner_idx"]]
    with m2:
        st.success(f"At {prob * 100:.0f}% ban probability, the least-regret pathway is **{winner}**.")

    grid = tuple(round(x / 100.0, 2) for x in range(10, 91, 5))
    rs = S.regret_sensitivity(q, pfas_probs=grid)
    if _PLOTLY:
        fig = go.Figure()
        for j, lab in enumerate(PATHWAY_LABELS):
            fig.add_trace(go.Scatter(
                x=[r["pfas_prob"] * 100 for r in rs],
                y=[r["total_regret"][j] for r in rs],
                mode="lines", name=lab,
            ))
        fig.add_vline(x=prob * 100, line_dash="dash", line_color="#666",
                      annotation_text=f"{prob * 100:.0f}%")
        fig.update_layout(
            xaxis_title="PFAS ban probability (%)",
            yaxis_title="Total regret (lower is better)",
            height=380, margin=dict(l=10, r=10, t=30, b=10),
            legend_title="Pathway",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Driver breakdown**")
    st.dataframe(
        pd.DataFrame([
            {"Driver": r["label"], "Weight": r["weight"], "Score (0-1)": r["score"],
             "Contribution": r["contribution"]}
            for r in pts["rows"]
        ]),
        use_container_width=True, hide_index=True,
    )
    st.caption("Each driver is tunable per jurisdiction and plant; the score replaces a single "
               "asserted number with a defensible build-up.")


def _tab_optionality(q):
    st.subheader("Optionality, reversibility and complexity")
    st.caption("Optionality = how many futures a pathway keeps open. Reversibility = how easily the "
               "decision is unwound if it proves wrong. They are different questions.")
    rows = []
    for lab, p in zip(PATHWAY_LABELS, q):
        o = S.optionality(p)
        c = S.complexity_score(p)
        rows.append({
            "Pathway": lab,
            "Optionality %": round(o["score"] * 100),
            "Reversibility": round(o["reversibility"] * 100),
            "Complexity (1-6)": f"{c['score']} ({c['label']})",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if _PLOTLY:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=PATHWAY_LABELS,
                             y=[round(S.optionality(p)["score"] * 100) for p in q],
                             name="Optionality"))
        fig.add_trace(go.Bar(x=PATHWAY_LABELS,
                             y=[round(S.optionality(p)["reversibility"] * 100) for p in q],
                             name="Reversibility"))
        fig.update_layout(barmode="group", height=320, yaxis_title="0 - 100",
                          margin=dict(l=10, r=10, t=30, b=10), legend_title="")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Reversibility Index** - if the decision proves wrong, how easily is it unwound?")
    st.dataframe(
        pd.DataFrame([{"Decision": n, "Reversibility": v, "Why": why}
                      for n, v, why in S.reversibility_index()]),
        use_container_width=True, hide_index=True,
    )


def _tab_nitrogen(plant):
    nsc = S.nitrogen_strategy_comparison(plant)
    st.subheader("Nitrogen strategy")
    st.metric("Sidestream N to manage", f"{nsc['sidestream_N_kgd']:,} kgN/d")
    st.dataframe(
        pd.DataFrame([
            {"Strategy": r["strategy"], "Family": r["family"], "N to N2 (kgN/d)": r["n_to_n2_kgd"],
             "N recovered (kgN/d)": r["n_recovered_kgd"], "Residual load (kgN/d)": r["residual_load_kgd"],
             "Load cut %": r["load_cut_pct"], "Conf": r["confidence"]}
            for r in nsc["rows"]
        ]),
        use_container_width=True, hide_index=True,
    )
    st.caption(nsc["headline"])


def _tab_capital(plant):
    ca = S.capital_allocation(plant)
    st.subheader("Capital allocation - Commit / Preserve / Monitor")
    c1, c2, c3 = st.columns(3)
    for col, key, title in [(c1, "commit_now", "Commit now"),
                            (c2, "preserve", "Preserve"),
                            (c3, "monitor", "Monitor")]:
        with col:
            st.markdown(f"**{title}**")
            for item, why in ca[key]:
                st.markdown(f"- **{item}**  \n  _{why}_")
    st.caption(ca["note"])


def _tab_constraint(plant):
    cm = S.constraint_migration(plant)
    st.subheader("Constraint migration")
    st.caption(cm["headline"])
    st.dataframe(
        pd.DataFrame([{"Pathway": a, "Governing constraint": b, "Why": c}
                      for a, b, c in cm["rows"]]),
        use_container_width=True, hide_index=True,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render():
    st.header("🧭 Strategy (BioPoint V2)")

    if not _SPINE_OK:
        st.error("The BioPoint V2 engine could not be loaded.")
        st.caption(str(_IMPORT_ERR))
        return

    st.caption("Interactive view of the V2 decision engine - performance, confidence, resilience, "
               "optionality and regret, kept as separate lenses rather than collapsed into one score.")

    opts = _plant_options()
    name = st.selectbox("Plant", list(opts.keys()), index=0, key="v2_plant_select")
    plant = opts[name]
    st.info("Calibrated preset. Wiring the entered Tier-1 inputs through this page - including "
            "phosphorus and a plant-specific biogas yield, which the V1 data model does not yet "
            "capture - is the next step, and also recalibrates the downloadable V2 report.")

    q = _build_quartet(plant)

    tabs = st.tabs([
        "PFAS trigger & regret crossover",
        "Optionality & reversibility",
        "Nitrogen strategy",
        "Capital allocation",
        "Constraint migration",
    ])
    with tabs[0]:
        _tab_pfas(q)
    with tabs[1]:
        _tab_optionality(q)
    with tabs[2]:
        _tab_nitrogen(plant)
    with tabs[3]:
        _tab_capital(plant)
    with tabs[4]:
        _tab_constraint(plant)
