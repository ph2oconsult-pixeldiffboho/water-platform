"""
AquaPoint — Page 7: Scenario Comparison
Side-by-side comparison of two treatment trains against the same source water.
Scenario A = current session selection.
Scenario B = named preset treatment train.
ph2o Consulting | Water Utility Planning Platform
"""
import streamlit as st
from ..engine import run_full_analysis, TECHNOLOGIES, LIFECYCLE_DEFAULTS, MCA_DEFAULT_WEIGHTS
from ..engine.reasoning import SourceWaterInputs, run_reasoning_engine
from ..engine.reasoning.lrv import get_lrv_for_archetype, ARCHETYPE_DEFAULT_BARRIERS
from ..engine.reasoning.residuals import assess_archetype_residuals
from ..ui_helpers import (
    section_header, warning_box, info_box, success_box, error_box,
    format_currency, render_kpi_card, score_colour,
)

# ─── Preset scenario definitions ─────────────────────────────────────────────

SCENARIO_PRESETS = {
    "A_direct": {
        "label": "Direct Filtration",
        "archetype": "A",
        "icon": "⚡",
        "description": "Coagulation → Filtration → UV → Chlorination. No clarification. Lowest cost, lowest footprint. Suitable only for stable, low-turbidity source waters.",
        "technologies": [
            "screening", "coagulation_flocculation",
            "rapid_gravity_filtration", "uv_disinfection", "chlorination",
        ],
        "plant_type": "conventional",
    },
    "B_conventional": {
        "label": "Conventional Sedimentation",
        "archetype": "B",
        "icon": "🏭",
        "description": "Coagulation → Sedimentation → Filtration → UV → Chlorination. Industry workhorse. Robust across wide source water variability.",
        "technologies": [
            "screening", "coagulation_flocculation", "sedimentation",
            "rapid_gravity_filtration", "uv_disinfection", "chlorination",
            "sludge_thickening",
        ],
        "plant_type": "conventional",
    },
    "D_daf": {
        "label": "DAF-Led Treatment",
        "archetype": "D",
        "icon": "🫧",
        "description": "Coagulation → DAF → Filtration → UV → Chlorination. Best in class for algae and NOM-rich source waters.",
        "technologies": [
            "screening", "coagulation_flocculation", "daf",
            "rapid_gravity_filtration", "uv_disinfection", "chlorination",
            "sludge_thickening",
        ],
        "plant_type": "conventional",
    },
    "E_enhanced": {
        "label": "Enhanced Coagulation + BAC",
        "archetype": "E",
        "icon": "🧫",
        "description": "Coagulation → Sedimentation → Filtration → BAC → UV → Chlorination. NOM and DBP precursor control as primary driver.",
        "technologies": [
            "screening", "coagulation_flocculation", "sedimentation",
            "rapid_gravity_filtration", "bac",
            "uv_disinfection", "chlorination", "sludge_thickening",
        ],
        "plant_type": "conventional",
    },
    "G_ozone_bac": {
        "label": "Ozone + BAC Train",
        "archetype": "G",
        "icon": "⚗️",
        "description": "Coagulation → Sedimentation → Filtration → Ozone → BAC → UV → Chlorination. Taste/odour control and advanced organic removal.",
        "technologies": [
            "screening", "coagulation_flocculation", "sedimentation",
            "rapid_gravity_filtration", "ozonation", "bac",
            "uv_disinfection", "chlorination", "sludge_thickening",
        ],
        "plant_type": "conventional",
    },
    "H_membrane": {
        "label": "Full Membrane Train",
        "archetype": "H",
        "icon": "🔬",
        "description": "Coagulation → MF/UF → RO → UV → Chloramination. Highest LRV credits. Required for PFAS, high TDS, or recycled water contexts.",
        "technologies": [
            "screening", "coagulation_flocculation",
            "mf_uf", "ro",
            "uv_disinfection", "chloramination", "brine_management",
        ],
        "plant_type": "membrane",
    },
}

PLANT_TO_SOURCE = {
    "conventional": "river", "membrane": "river",
    "groundwater": "groundwater", "desalination": "desalination",
}


# ─── Input builders ───────────────────────────────────────────────────────────

def _base_inputs() -> dict:
    """Common inputs from session state."""
    return {
        "flow_ML_d": st.session_state.get("flow_ML_d", 10.0),
        "source_water": st.session_state.get("source_water", {
            "turbidity_ntu": 5, "toc_mg_l": 5, "tds_mg_l": 300,
            "hardness_mg_l": 150, "iron_mg_l": 0.1, "manganese_mg_l": 0.02,
            "colour_hu": 10, "algal_cells_ml": 500,
        }),
        "lifecycle_params": {
            "analysis_period_years":  st.session_state.get("analysis_period",  LIFECYCLE_DEFAULTS["analysis_period_years"]),
            "discount_rate_pct":      st.session_state.get("discount_rate",     LIFECYCLE_DEFAULTS["discount_rate_pct"]),
            "opex_escalation_pct":    st.session_state.get("opex_escalation",   LIFECYCLE_DEFAULTS["opex_escalation_pct"]),
            "capex_contingency_pct":  st.session_state.get("capex_contingency", LIFECYCLE_DEFAULTS["capex_contingency_pct"]),
        },
        "electricity_cost_AUD_kWh": st.session_state.get("electricity_cost", 0.12),
        "mca_weights": st.session_state.get("mca_weights", MCA_DEFAULT_WEIGHTS),
    }


def _run_scenario(plant_type: str, techs: list, base: dict) -> dict:
    return run_full_analysis({
        "plant_type": plant_type,
        "selected_technologies": techs,
        **base,
    })


def _get_lrv_summary(archetype_key: str, required_lrv: dict) -> dict:
    """Get LRV credited high for protozoa/bacteria/virus."""
    try:
        lrv = get_lrv_for_archetype(archetype_key, required_lrv)
        return {
            p: lrv.total_credited_high.get(p, 0)
            for p in ["protozoa", "bacteria", "virus"]
        }
    except Exception:
        return {"protozoa": 0.0, "bacteria": 0.0, "virus": 0.0}


def _get_residuals_complexity(archetype_key: str, sw: dict) -> str:
    try:
        inputs = SourceWaterInputs(
            source_type="river",
            turbidity_median_ntu=float(sw.get("turbidity_ntu", 5)),
            toc_median_mg_l=float(sw.get("toc_mg_l", 5)),
        )
        res = assess_archetype_residuals(archetype_key, inputs)
        return res.complexity_rating
    except Exception:
        return "moderate"


# ─── Rendering helpers ────────────────────────────────────────────────────────

def _delta_html(val_a, val_b, higher_is_better=True, fmt=None):
    """Render a delta cell — green if B is better, red if worse."""
    if val_a == 0 and val_b == 0:
        return '<span style="color:#8899aa">—</span>'
    try:
        delta = val_b - val_a
        if fmt == "currency":
            delta_str = f"{'+' if delta >= 0 else ''}{format_currency(delta)}"
        elif fmt == "pct":
            delta_str = f"{'+' if delta >= 0 else ''}{delta:.1f}%"
        elif fmt == "int":
            delta_str = f"{'+' if delta >= 0 else ''}{delta:.0f}"
        else:
            delta_str = f"{'+' if delta >= 0 else ''}{delta:.1f}"

        if abs(delta) < 0.001 * max(abs(val_a), abs(val_b), 1):
            colour = "#8899aa"
        elif (delta > 0) == higher_is_better:
            colour = "#2ecc71"
        else:
            colour = "#e74c3c"

        return f'<span style="color:{colour};font-weight:600">{delta_str}</span>'
    except Exception:
        return '<span style="color:#8899aa">—</span>'


def _metric_row(label, val_a, val_b, higher_is_better=True, fmt=None,
                format_fn=None, suffix=""):
    """Render one comparison table row."""
    def _fmt(v):
        if format_fn:
            return format_fn(v)
        if fmt == "currency":
            return format_currency(v)
        if fmt == "pct":
            return f"{v:.1f}%"
        if fmt == "int":
            return f"{v:.0f}"
        return f"{v:.1f}{suffix}"

    delta = _delta_html(val_a, val_b, higher_is_better, fmt)
    c_a = score_colour(val_a) if fmt not in ["currency"] else "#e8f4fd"
    c_b = score_colour(val_b) if fmt not in ["currency"] else "#e8f4fd"

    return f"""
        <div style="display:grid;grid-template-columns:2fr 1.5fr 1.5fr 1.2fr;
                    gap:0.5rem;padding:0.4rem 0;border-bottom:1px solid #e2e8f0;
                    align-items:center;font-size:0.83rem">
            <span style="color:#334155">{label}</span>
            <span style="color:{c_a};font-weight:600;text-align:right">{_fmt(val_a)}</span>
            <span style="color:{c_b};font-weight:600;text-align:right">{_fmt(val_b)}</span>
            <span style="text-align:right">{delta}</span>
        </div>"""


def _bar_chart_html(label_a, label_b, metrics: list, colour_a="#4a9eff", colour_b="#2ecc71"):
    """
    metrics: list of (label, val_a, val_b, higher_is_better)
    Returns HTML bar chart.
    """
    max_val = max((max(abs(m[1]), abs(m[2])) for m in metrics), default=1)
    if max_val == 0:
        max_val = 1

    rows = ""
    for lbl, va, vb, hib in metrics:
        pct_a = min(100, abs(va) / max_val * 100)
        pct_b = min(100, abs(vb) / max_val * 100)
        rows += f"""
            <div style="margin-bottom:0.7rem">
                <div style="font-size:0.78rem;color:#8899aa;margin-bottom:0.2rem">{lbl}</div>
                <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.15rem">
                    <span style="font-size:0.72rem;color:#4a9eff;min-width:80px">{label_a}</span>
                    <div style="flex:1;background:#f0f4f8;border-radius:3px;height:10px">
                        <div style="width:{pct_a:.1f}%;background:{colour_a};height:100%;border-radius:3px"></div>
                    </div>
                    <span style="font-size:0.72rem;color:#e8f4fd;min-width:50px;text-align:right">{va:.1f}</span>
                </div>
                <div style="display:flex;align-items:center;gap:0.5rem">
                    <span style="font-size:0.72rem;color:#2ecc71;min-width:80px">{label_b}</span>
                    <div style="flex:1;background:#f0f4f8;border-radius:3px;height:10px">
                        <div style="width:{pct_b:.1f}%;background:{colour_b};height:100%;border-radius:3px"></div>
                    </div>
                    <span style="font-size:0.72rem;color:#e8f4fd;min-width:50px;text-align:right">{vb:.1f}</span>
                </div>
            </div>"""

    return f'<div style="background:#f8fafc;border-radius:8px;padding:0.8rem 1rem">{rows}</div>'


def _compliance_label(results: dict) -> str:
    tp = results.get("treatment_performance", {})
    ok = tp.get("overall_compliant", False)
    disinfect = tp.get("disinfection_adequate", False)
    if ok and disinfect:
        return "✓ Full"
    elif disinfect:
        return "⚠ Partial"
    else:
        return "✗ Issues"


def _complexity_score(rating: str) -> int:
    return {"low": 1, "moderate": 2, "high": 3, "very_high": 4}.get(rating, 2)


# ─── Main render ──────────────────────────────────────────────────────────────

def render():
    st.markdown("""
        <h2 style="color:#e8f4fd;font-size:1.4rem;font-weight:700;margin-bottom:0.2rem">
            Scenario Comparison
        </h2>
        <p style="color:#8899aa;font-size:0.87rem;margin-bottom:1rem">
            Compare two treatment trains against the same source water and project parameters.
            Scenario A is your current selection. Scenario B is a named preset train.
        </p>
    """, unsafe_allow_html=True)

    # ── Scenario A — current session ─────────────────────────────────────────
    techs_a    = st.session_state.get("selected_technologies", [])
    plant_a    = st.session_state.get("plant_type", "conventional")
    sw         = st.session_state.get("source_water", {})
    flow_ML_d  = st.session_state.get("flow_ML_d", 10.0)

    if not techs_a:
        warning_box("No technologies selected in the current session. "
                    "Complete Technology Selection first, then return here.")
        if st.button("← Technology Selection", use_container_width=False):
            st.session_state["current_page"] = "technology_selection"
            st.rerun()
        return

    label_a = "Scenario A — Current Selection"
    train_a_str = " → ".join(TECHNOLOGIES.get(t, {}).get("label", t) for t in techs_a)

    # ── Scenario B — preset selector ─────────────────────────────────────────
    section_header("Select Scenario B", "🔀")

    preset_keys   = list(SCENARIO_PRESETS.keys())
    preset_labels = [
        f"{SCENARIO_PRESETS[k]['icon']}  {SCENARIO_PRESETS[k]['label']}"
        for k in preset_keys
    ]

    selected_preset_idx = st.selectbox(
        "Preset treatment train",
        range(len(preset_keys)),
        format_func=lambda i: preset_labels[i],
        index=st.session_state.get("sc_preset_idx", 1),
        key="_sc_preset_sel",
        label_visibility="collapsed",
    )
    st.session_state["sc_preset_idx"] = selected_preset_idx
    preset_key = preset_keys[selected_preset_idx]
    preset     = SCENARIO_PRESETS[preset_key]
    label_b    = f"Scenario B — {preset['label']}"
    techs_b    = preset["technologies"]
    plant_b    = preset["plant_type"]

    # Preset description card
    st.markdown(f"""
        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;
                    padding:0.75rem 1rem;margin-bottom:1rem">
            <div style="font-size:0.88rem;font-weight:600;color:#e8f4fd;margin-bottom:0.2rem">
                {preset['icon']} {preset['label']} (Archetype {preset['archetype']})
            </div>
            <div style="font-size:0.8rem;color:#1a56a0;margin-bottom:0.4rem">
                {preset['description']}
            </div>
            <div style="font-size:0.75rem;color:#8899aa">
                Train: <span style="color:#0284c7">
                {" → ".join(TECHNOLOGIES.get(t,{}).get("label",t) for t in techs_b)}
                </span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ── Scenario headers ──────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"""
            <div style="background:#eff6ff;border:2px solid #4a9eff;border-radius:8px;
                        padding:0.7rem 0.9rem">
                <div style="font-size:0.7rem;color:#4a9eff;text-transform:uppercase;
                            letter-spacing:0.06em">Scenario A</div>
                <div style="font-size:0.9rem;font-weight:600;color:#e8f4fd;margin-top:0.2rem">
                    Current Selection</div>
                <div style="font-size:0.72rem;color:#8899aa;margin-top:0.3rem">{train_a_str}</div>
                <div style="font-size:0.72rem;color:#8899aa">{flow_ML_d:.1f} ML/d</div>
            </div>
        """, unsafe_allow_html=True)
    with col_b:
        st.markdown(f"""
            <div style="background:#f0fdf4;border:2px solid #2ecc71;border-radius:8px;
                        padding:0.7rem 0.9rem">
                <div style="font-size:0.7rem;color:#2ecc71;text-transform:uppercase;
                            letter-spacing:0.06em">Scenario B</div>
                <div style="font-size:0.9rem;font-weight:600;color:#e8f4fd;margin-top:0.2rem">
                    {preset['label']}</div>
                <div style="font-size:0.72rem;color:#8899aa;margin-top:0.3rem">
                    {" → ".join(TECHNOLOGIES.get(t,{}).get("label",t) for t in techs_b)}</div>
                <div style="font-size:0.72rem;color:#8899aa">{flow_ML_d:.1f} ML/d</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    run_col, _ = st.columns([1, 3])
    with run_col:
        run = st.button("▶  Run Comparison", type="primary", use_container_width=True)

    # Cache comparison results
    cache_key = f"sc_result_{preset_key}_{','.join(techs_a)}_{flow_ML_d}"
    if run or st.session_state.get("sc_cache_key") != cache_key:
        with st.spinner("Running both scenarios…"):
            base = _base_inputs()
            try:
                r_a = _run_scenario(plant_a, techs_a, base)
                r_b = _run_scenario(plant_b, techs_b, base)
                st.session_state["sc_r_a"]       = r_a
                st.session_state["sc_r_b"]       = r_b
                st.session_state["sc_cache_key"] = cache_key
            except Exception as e:
                error_box(f"Analysis failed: {e}")
                return

    r_a = st.session_state.get("sc_r_a")
    r_b = st.session_state.get("sc_r_b")
    if not r_a or not r_b:
        info_box("Press Run Comparison to analyse both scenarios.")
        return

    # ── Extract key metrics ───────────────────────────────────────────────────
    mca_a    = r_a["mca"]["total_score"]
    mca_b    = r_b["mca"]["total_score"]
    capex_a  = r_a["capex"]["total_capex_AUD"]["typical"]
    capex_b  = r_b["capex"]["total_capex_AUD"]["typical"]
    npv_a    = r_a["lifecycle_cost"]["npv_total_AUD"]
    npv_b    = r_b["lifecycle_cost"]["npv_total_AUD"]
    opex_a   = r_a["opex"]["total_annual_opex_AUD"]
    opex_b   = r_b["opex"]["total_annual_opex_AUD"]
    energy_a = r_a["energy"]["specific_energy_kWh_ML"]["typical"]
    energy_b = r_b["energy"]["specific_energy_kWh_ML"]["typical"]
    co2_a    = r_a["environmental"]["unit_CO2_kg_per_kL"]
    co2_b    = r_b["environmental"]["unit_CO2_kg_per_kL"]

    # LRV from reasoning engine
    required_lrv = {"protozoa": 4.0, "bacteria": 6.0, "virus": 6.0}
    lrv_a = _get_lrv_summary(
        "B" if "sedimentation" in techs_a else
        "D" if "daf" in techs_a else
        "H" if "ro" in techs_a else
        "A" if "sedimentation" not in techs_a and "daf" not in techs_a else "B",
        required_lrv,
    )
    lrv_b = _get_lrv_summary(preset["archetype"], required_lrv)

    # Residuals complexity
    res_key_a = (
        "D" if "daf" in techs_a else
        "H" if "ro" in techs_a else
        "G" if "ozonation" in techs_a else
        "A" if "sedimentation" not in techs_a else "B"
    )
    res_a_rating = _get_residuals_complexity(res_key_a, sw)
    res_b_rating = _get_residuals_complexity(preset["archetype"], sw)
    res_a_score  = _complexity_score(res_a_rating)
    res_b_score  = _complexity_score(res_b_rating)

    comp_a = _compliance_label(r_a)
    comp_b = _compliance_label(r_b)

    # ── Summary KPI row ───────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Summary", "📊")

    k1, k2, k3, k4, k5 = st.columns(5)
    def _kpi_compare(col, label, val_a, val_b, fmt_fn, higher_is_better=True):
        winner = "A" if (val_a > val_b) == higher_is_better else "B"
        colour = "#4a9eff" if winner == "A" else "#2ecc71"
        with col:
            st.markdown(f"""
                <div style="background:#f0f4f8;border-radius:8px;padding:0.7rem;
                            border:1px solid #e2e8f0;text-align:center">
                    <div style="font-size:0.68rem;color:#8899aa;text-transform:uppercase;
                                letter-spacing:0.04em;margin-bottom:0.3rem">{label}</div>
                    <div style="font-size:0.82rem;color:#4a9eff">A: {fmt_fn(val_a)}</div>
                    <div style="font-size:0.82rem;color:#2ecc71">B: {fmt_fn(val_b)}</div>
                    <div style="font-size:0.7rem;color:{colour};margin-top:0.2rem;font-weight:600">
                        {'↑' if winner == 'B' else '='} Scenario {winner} preferred</div>
                </div>
            """, unsafe_allow_html=True)

    _kpi_compare(k1, "MCA Score",       mca_a,    mca_b,    lambda v: f"{v:.0f}/100")
    _kpi_compare(k2, "CAPEX",           capex_a,  capex_b,  format_currency, higher_is_better=False)
    _kpi_compare(k3, "NPV (30yr)",      npv_a,    npv_b,    format_currency, higher_is_better=False)
    _kpi_compare(k4, "Energy (kWh/ML)", energy_a, energy_b, lambda v: f"{v:.0f}", higher_is_better=False)
    _kpi_compare(k5, "CO₂ (kg/kL)",    co2_a,    co2_b,    lambda v: f"{v:.3f}", higher_is_better=False)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    tabs = st.tabs(["📋 Comparison Table", "📊 Bar Charts", "🔬 LRV & Barriers", "♻️ Residuals & Environment"])

    # ══ TAB 1 — COMPARISON TABLE ══════════════════════════════════════════════
    with tabs[0]:
        section_header("Full Metric Comparison", "📋")

        # Table header
        st.markdown(f"""
            <div style="display:grid;grid-template-columns:2fr 1.5fr 1.5fr 1.2fr;
                        gap:0.5rem;padding:0.4rem 0;border-bottom:2px solid #94a3b8;
                        font-size:0.72rem;font-weight:600;text-transform:uppercase;
                        letter-spacing:0.05em">
                <span style="color:#8899aa">Metric</span>
                <span style="color:#4a9eff;text-align:right">Scenario A</span>
                <span style="color:#2ecc71;text-align:right">Scenario B</span>
                <span style="color:#8899aa;text-align:right">Delta (B−A)</span>
            </div>
        """, unsafe_allow_html=True)

        rows_html = ""

        # MCA
        rows_html += _metric_row("MCA Score (0–100)", mca_a, mca_b,
                                  higher_is_better=True, fmt="int")
        # Cost
        rows_html += _metric_row("CAPEX (typical)", capex_a, capex_b,
                                  higher_is_better=False, fmt="currency",
                                  format_fn=format_currency)
        rows_html += _metric_row("NPV 30-year", npv_a, npv_b,
                                  higher_is_better=False, fmt="currency",
                                  format_fn=format_currency)
        rows_html += _metric_row("Annual OPEX", opex_a, opex_b,
                                  higher_is_better=False, fmt="currency",
                                  format_fn=format_currency)
        # Energy
        rows_html += _metric_row("Specific Energy (kWh/ML)", energy_a, energy_b,
                                  higher_is_better=False, suffix=" kWh/ML")
        # Carbon
        rows_html += _metric_row("Carbon Intensity (kg CO₂/kL)", co2_a, co2_b,
                                  higher_is_better=False, fmt="pct",
                                  format_fn=lambda v: f"{v:.3f}")
        # Water quality
        wq_a = r_a["mca"]["scores"].get("water_quality", 0)
        wq_b = r_b["mca"]["scores"].get("water_quality", 0)
        rows_html += _metric_row("Water Quality MCA Score", wq_a, wq_b,
                                  higher_is_better=True, fmt="int")
        # LRV
        rows_html += _metric_row("LRV — Protozoa (credited log)",
                                  lrv_a["protozoa"], lrv_b["protozoa"],
                                  higher_is_better=True)
        rows_html += _metric_row("LRV — Bacteria (credited log)",
                                  lrv_a["bacteria"], lrv_b["bacteria"],
                                  higher_is_better=True)
        rows_html += _metric_row("LRV — Virus (credited log)",
                                  lrv_a["virus"], lrv_b["virus"],
                                  higher_is_better=True)
        # Residuals
        rows_html += _metric_row("Residuals Complexity (1=low, 4=very high)",
                                  float(res_a_score), float(res_b_score),
                                  higher_is_better=False, fmt="int")
        # Risk
        risk_a = r_a.get("risk", {}).get("overall", {}).get("composite_score", 2.0)
        risk_b = r_b.get("risk", {}).get("overall", {}).get("composite_score", 2.0)
        rows_html += _metric_row("Overall Risk Score (1=low, 3=high)",
                                  risk_a, risk_b,
                                  higher_is_better=False)
        # Technology count
        rows_html += _metric_row("Technologies in Train",
                                  float(len(techs_a)), float(len(techs_b)),
                                  higher_is_better=False, fmt="int")

        st.markdown(rows_html, unsafe_allow_html=True)

        # Water quality compliance row (non-numeric)
        st.markdown(f"""
            <div style="display:grid;grid-template-columns:2fr 1.5fr 1.5fr 1.2fr;
                        gap:0.5rem;padding:0.4rem 0;border-bottom:1px solid #e2e8f0;
                        align-items:center;font-size:0.83rem">
                <span style="color:#334155">ADWG Compliance</span>
                <span style="text-align:right">{comp_a}</span>
                <span style="text-align:right">{comp_b}</span>
                <span style="color:#8899aa;text-align:right">—</span>
            </div>
            <div style="display:grid;grid-template-columns:2fr 1.5fr 1.5fr 1.2fr;
                        gap:0.5rem;padding:0.4rem 0;border-bottom:1px solid #e2e8f0;
                        align-items:center;font-size:0.83rem">
                <span style="color:#334155">Residuals Complexity</span>
                <span style="color:#e8f4fd;text-align:right">{res_a_rating.replace('_',' ').title()}</span>
                <span style="color:#e8f4fd;text-align:right">{res_b_rating.replace('_',' ').title()}</span>
                <span style="color:#8899aa;text-align:right">—</span>
            </div>
        """, unsafe_allow_html=True)

    # ══ TAB 2 — BAR CHARTS ════════════════════════════════════════════════════
    with tabs[1]:
        section_header("Visual Comparison", "📊")

        c1, c2 = st.columns(2)
        with c1:
            section_header("Cost ($M)", "💰")
            st.markdown(_bar_chart_html(
                "Scenario A", "Scenario B",
                [
                    ("CAPEX", capex_a/1e6, capex_b/1e6, False),
                    ("NPV 30yr", npv_a/1e6, npv_b/1e6, False),
                    ("Annual OPEX", opex_a/1e6, opex_b/1e6, False),
                ],
            ), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            section_header("MCA Component Scores", "📊")
            mca_scores_a = r_a["mca"]["scores"]
            mca_scores_b = r_b["mca"]["scores"]
            mca_metrics = [
                (k.replace("_", " ").title(), mca_scores_a.get(k, 0), mca_scores_b.get(k, 0), True)
                for k in ["water_quality", "lifecycle_cost", "risk", "energy", "environmental", "regulatory_compliance"]
            ]
            st.markdown(_bar_chart_html("Scenario A", "Scenario B", mca_metrics), unsafe_allow_html=True)

        with c2:
            section_header("Energy & Carbon", "⚡")
            st.markdown(_bar_chart_html(
                "Scenario A", "Scenario B",
                [
                    ("Specific Energy (kWh/ML)", energy_a, energy_b, False),
                    ("Annual Energy (MWh/yr ÷ 100)", r_a["energy"]["annual_energy_MWh"]["typical"]/100,
                                                      r_b["energy"]["annual_energy_MWh"]["typical"]/100, False),
                    ("CO₂ (kg/kL × 100)", co2_a*100, co2_b*100, False),
                ],
            ), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            section_header("LRV Barrier Performance", "🔬")
            st.markdown(_bar_chart_html(
                "Scenario A", "Scenario B",
                [
                    ("Protozoa (log credited)", lrv_a["protozoa"], lrv_b["protozoa"], True),
                    ("Bacteria (log credited)",  lrv_a["bacteria"], lrv_b["bacteria"], True),
                    ("Virus (log credited)",     lrv_a["virus"],    lrv_b["virus"],    True),
                ],
            ), unsafe_allow_html=True)

    # ══ TAB 3 — LRV & BARRIERS ════════════════════════════════════════════════
    with tabs[2]:
        section_header("LRV Barrier Analysis", "🔬")
        info_box(
            f"Required LRVs: Protozoa {required_lrv['protozoa']:.0f} log | "
            f"Bacteria {required_lrv['bacteria']:.0f} log | "
            f"Virus {required_lrv['virus']:.0f} log"
        )

        for pathogen in ["protozoa", "bacteria", "virus"]:
            req   = required_lrv[pathogen]
            va    = lrv_a[pathogen]
            vb    = lrv_b[pathogen]
            ok_a  = va >= req
            ok_b  = vb >= req
            ca    = "#2ecc71" if ok_a else "#e74c3c"
            cb    = "#2ecc71" if ok_b else "#e74c3c"
            pct_a = min(100, va / max(req, 0.01) * 100)
            pct_b = min(100, vb / max(req, 0.01) * 100)
            st.markdown(f"""
                <div style="margin-bottom:0.8rem">
                    <div style="font-size:0.85rem;font-weight:600;color:#e8f4fd;margin-bottom:0.3rem">
                        {pathogen.title()} — required: {req:.0f} log
                    </div>
                    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.2rem">
                        <span style="font-size:0.75rem;color:#4a9eff;min-width:90px">Scenario A</span>
                        <div style="flex:1;background:#f0f4f8;border-radius:3px;height:12px;position:relative">
                            <div style="width:{pct_a:.1f}%;background:#4a9eff;height:100%;border-radius:3px"></div>
                            <div style="position:absolute;left:100%;top:-1px;bottom:-1px;width:2px;background:#e74c3c;opacity:0.7"></div>
                        </div>
                        <span style="font-size:0.75rem;color:{ca};min-width:60px;font-weight:600">
                            {va:.1f} log {'✓' if ok_a else '✗'}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:0.5rem">
                        <span style="font-size:0.75rem;color:#2ecc71;min-width:90px">Scenario B</span>
                        <div style="flex:1;background:#f0f4f8;border-radius:3px;height:12px;position:relative">
                            <div style="width:{pct_b:.1f}%;background:#2ecc71;height:100%;border-radius:3px"></div>
                            <div style="position:absolute;left:100%;top:-1px;bottom:-1px;width:2px;background:#e74c3c;opacity:0.7"></div>
                        </div>
                        <span style="font-size:0.75rem;color:{cb};min-width:60px;font-weight:600">
                            {vb:.1f} log {'✓' if ok_b else '✗'}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        # Disinfection adequacy
        section_header("Disinfection Adequacy", "💊")
        da_checks = [
            ("Primary Disinfection",   "chlorination" in techs_a or "uv_disinfection" in techs_a,
                                       "chlorination" in techs_b or "uv_disinfection" in techs_b),
            ("Distribution Residual",  "chlorination" in techs_a or "chloramination" in techs_a,
                                       "chlorination" in techs_b or "chloramination" in techs_b),
            ("Protozoan Inactivation", "uv_disinfection" in techs_a or "ozonation" in techs_a,
                                       "uv_disinfection" in techs_b or "ozonation" in techs_b),
        ]
        for check_lbl, ok_a_d, ok_b_d in da_checks:
            ia = "✓" if ok_a_d else "✗"
            ib = "✓" if ok_b_d else "✗"
            ca_d = "#2ecc71" if ok_a_d else "#e74c3c"
            cb_d = "#2ecc71" if ok_b_d else "#e74c3c"
            st.markdown(f"""
                <div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:0.5rem;
                            padding:0.35rem 0;border-bottom:1px solid #e2e8f0;font-size:0.83rem">
                    <span style="color:#334155">{check_lbl}</span>
                    <span style="color:{ca_d};font-weight:600;text-align:center">{ia} A</span>
                    <span style="color:{cb_d};font-weight:600;text-align:center">{ib} B</span>
                </div>
            """, unsafe_allow_html=True)

    # ══ TAB 4 — RESIDUALS & ENVIRONMENT ══════════════════════════════════════
    with tabs[3]:
        section_header("Residuals & Environmental Comparison", "♻️")

        col_r1, col_r2 = st.columns(2)
        complexity_colours = {"low": "#2ecc71", "moderate": "#f39c12", "high": "#e74c3c", "very_high": "#9b0000"}

        with col_r1:
            st.markdown(f"""
                <div style="background:#eff6ff;border:2px solid #4a9eff;border-radius:8px;
                            padding:0.8rem;margin-bottom:0.5rem">
                    <div style="font-size:0.7rem;color:#4a9eff;margin-bottom:0.3rem">SCENARIO A RESIDUALS</div>
                    <div style="font-size:0.88rem;color:{complexity_colours.get(res_a_rating,'#8899aa')};font-weight:600">
                        {res_a_rating.replace('_',' ').title()} Complexity</div>
                    <div style="font-size:0.78rem;color:#8899aa;margin-top:0.3rem">
                        Technologies: {", ".join(t for t in techs_a if t in ["daf","sedimentation","mf_uf","ro","bac","gac","ozonation","sludge_thickening"]) or "Standard filtration"}
                    </div>
                </div>
            """, unsafe_allow_html=True)

        with col_r2:
            st.markdown(f"""
                <div style="background:#f0fdf4;border:2px solid #2ecc71;border-radius:8px;
                            padding:0.8rem;margin-bottom:0.5rem">
                    <div style="font-size:0.7rem;color:#2ecc71;margin-bottom:0.3rem">SCENARIO B RESIDUALS</div>
                    <div style="font-size:0.88rem;color:{complexity_colours.get(res_b_rating,'#8899aa')};font-weight:600">
                        {res_b_rating.replace('_',' ').title()} Complexity</div>
                    <div style="font-size:0.78rem;color:#8899aa;margin-top:0.3rem">
                        Technologies: {", ".join(t for t in techs_b if t in ["daf","sedimentation","mf_uf","ro","bac","gac","ozonation","sludge_thickening","brine_management"]) or "Standard filtration"}
                    </div>
                </div>
            """, unsafe_allow_html=True)

        # Flags
        if "ro" in techs_b or "ro" in techs_a:
            error_box("RO concentrate management: significant residuals challenge — environmental licence required for discharge.")
        if "ozonation" in techs_a or "ozonation" in techs_b:
            warning_box("Ozone in train: bromide/bromate assessment required before finalising ozone dose.")

        section_header("Environmental Footprint", "🌿")
        env_rows = [
            ("Annual Energy CO₂ (t/yr)",
             r_a["environmental"]["annual_energy_CO2_tonnes"],
             r_b["environmental"]["annual_energy_CO2_tonnes"],),
            ("Annual Chemical CO₂ (t/yr)",
             r_a["environmental"]["annual_chemical_CO2_tonnes"],
             r_b["environmental"]["annual_chemical_CO2_tonnes"],),
            ("Total Annual CO₂ (t/yr)",
             r_a["environmental"]["total_annual_CO2_tonnes"],
             r_b["environmental"]["total_annual_CO2_tonnes"],),
            ("Carbon Intensity (kg CO₂/kL)",
             r_a["environmental"]["unit_CO2_kg_per_kL"],
             r_b["environmental"]["unit_CO2_kg_per_kL"],),
        ]
        st.markdown(f"""
            <div style="display:grid;grid-template-columns:2fr 1.5fr 1.5fr;gap:0.5rem;
                        padding:0.3rem 0;border-bottom:2px solid #94a3b8;
                        font-size:0.7rem;font-weight:600;text-transform:uppercase;color:#8899aa">
                <span>Metric</span>
                <span style="color:#4a9eff;text-align:right">Scenario A</span>
                <span style="color:#2ecc71;text-align:right">Scenario B</span>
            </div>
        """, unsafe_allow_html=True)
        for lbl, va, vb in env_rows:
            c_a = "#2ecc71" if va <= vb else "#e8f4fd"
            c_b = "#2ecc71" if vb <= va else "#e8f4fd"
            st.markdown(f"""
                <div style="display:grid;grid-template-columns:2fr 1.5fr 1.5fr;gap:0.5rem;
                            padding:0.35rem 0;border-bottom:1px solid #e2e8f0;font-size:0.83rem">
                    <span style="color:#334155">{lbl}</span>
                    <span style="color:{c_a};text-align:right;font-weight:600">{va:.1f}</span>
                    <span style="color:{c_b};text-align:right;font-weight:600">{vb:.1f}</span>
                </div>
            """, unsafe_allow_html=True)

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        if st.button("← Analysis Results", use_container_width=True):
            st.session_state["current_page"] = "results"
            st.rerun()
    with right:
        if st.button("Export Report →", type="primary", use_container_width=True):
            st.session_state["current_page"] = "report"
            st.rerun()
