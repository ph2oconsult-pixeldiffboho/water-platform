"""
AquaPoint — Page 6: Treatment Philosophy
Runs the full Gate 1–5 reasoning engine and renders structured output.
ph2o Consulting | Water Utility Planning Platform
"""
import streamlit as st
from ..engine.reasoning import (
    SourceWaterInputs, run_reasoning_engine, ARCHETYPES,
)
from ..ui_helpers import (
    section_header, warning_box, info_box, success_box, error_box,
    render_kpi_card, score_colour,
)


# ─── Plant type → reasoning source_type mapping ───────────────────────────────
PLANT_TO_SOURCE = {
    "conventional":  "river",
    "membrane":      "river",
    "groundwater":   "groundwater",
    "desalination":  "desalination",
}


# ─── Build reasoning inputs from session state ────────────────────────────────

def _build_inputs() -> SourceWaterInputs:
    sw = st.session_state.get("source_water", {})
    tp = lambda k, d: st.session_state.get(k, d)

    plant_key   = st.session_state.get("plant_type", "conventional")
    source_type = tp("tp_source_type", PLANT_TO_SOURCE.get(plant_key, "river"))

    turb_med = float(sw.get("turbidity_ntu", 5.0))
    toc_med  = float(sw.get("toc_mg_l", 5.0))

    ev_raw = tp("tp_turb_max", None)
    event_max = float(ev_raw) if ev_raw and float(ev_raw) > 0 else None

    return SourceWaterInputs(
        source_type=source_type,
        turbidity_median_ntu=turb_med,
        turbidity_p95_ntu=float(tp("tp_turb_p95", round(turb_med * 4, 1))),
        turbidity_p99_ntu=float(tp("tp_turb_p99", round(turb_med * 10, 1))),
        turbidity_event_max_ntu=event_max,
        toc_median_mg_l=toc_med,
        toc_p95_mg_l=float(tp("tp_toc_p95", round(toc_med * 1.5, 1))),
        colour_median_hu=float(sw.get("colour_hu", 10.0)),
        dbp_concern=bool(tp("tp_dbp_concern", False)),
        algae_risk=tp("tp_algae_risk", "low"),
        cyanobacteria_confirmed=bool(tp("tp_cyano_confirmed", False)),
        cyanotoxin_detected=bool(tp("tp_cyanotoxin", False)),
        mib_geosmin_issue=bool(tp("tp_mib_geosmin", False)),
        hardness_median_mg_l=float(sw.get("hardness_mg_l", 150.0)),
        alkalinity_median_mg_l=float(tp("tp_alkalinity", 80.0)),
        iron_median_mg_l=float(sw.get("iron_mg_l", 0.1)),
        manganese_median_mg_l=float(sw.get("manganese_mg_l", 0.02)),
        arsenic_ug_l=float(tp("tp_arsenic_ug_l", 0.0)),
        tds_median_mg_l=float(sw.get("tds_mg_l", 300.0)),
        ph_median=float(tp("tp_ph_median", 7.5)),
        ph_min=float(tp("tp_ph_min", 7.0)),
        pfas_detected=bool(tp("tp_pfas_detected", False)),
        pfas_concentration_ng_l=float(tp("tp_pfas_ng_l", 0.0)),
        troc_concern=bool(tp("tp_troc_concern", False)),
        catchment_risk=tp("tp_catchment_risk", "moderate"),
        pathogen_lrv_required_protozoa=float(tp("tp_lrv_protozoa", 4.0)),
        pathogen_lrv_required_bacteria=float(tp("tp_lrv_bacteria", 6.0)),
        pathogen_lrv_required_virus=float(tp("tp_lrv_virus", 6.0)),
        is_retrofit=bool(tp("tp_retrofit", False)),
        land_constrained=bool(tp("tp_land_constrained", False)),
        remote_operation=bool(tp("tp_remote", False)),
        design_flow_ML_d=float(st.session_state.get("flow_ML_d", 10.0)),
        treatment_objective=tp("tp_treatment_objective", "potable"),
        variability_class=tp("tp_variability_class", "moderate"),
    )


# ─── Input panel (expander in main area — does not touch st.sidebar) ──────────

def _render_input_panel():
    with st.expander("⚙️  Reasoning Engine Inputs  (click to expand)", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Source & Objective**")
            plant_key = st.session_state.get("plant_type", "conventional")
            default_src = PLANT_TO_SOURCE.get(plant_key, "river")
            src_options = ["river", "reservoir", "groundwater", "blended", "recycled", "desalination"]
            src_labels  = {
                "river":        "🌊 River / Stream",
                "reservoir":    "🏞️ Reservoir / Lake",
                "groundwater":  "🪨 Groundwater",
                "blended":      "🔀 Blended / Conjunctive",
                "recycled":     "♻️ Recycled Water",
                "desalination": "🌊 Desalination",
            }
            cur_src = st.session_state.get("tp_source_type", default_src)
            if cur_src not in src_options:
                cur_src = default_src
            st.session_state["tp_source_type"] = st.selectbox(
                "Source Type", src_options,
                format_func=lambda x: src_labels.get(x, x),
                index=src_options.index(cur_src), key="_tp_src",
            )

            obj_options = ["potable", "recycled", "industrial"]
            obj_labels  = {"potable": "Potable supply", "recycled": "Recycled / advanced barrier", "industrial": "Industrial"}
            cur_obj = st.session_state.get("tp_treatment_objective", "potable")
            st.session_state["tp_treatment_objective"] = st.selectbox(
                "Treatment Objective", obj_options,
                format_func=lambda x: obj_labels.get(x, x),
                index=obj_options.index(cur_obj), key="_tp_obj",
            )

            var_options = ["low", "moderate", "high", "extreme"]
            cur_var = st.session_state.get("tp_variability_class", "moderate")
            if cur_var not in var_options:
                cur_var = "moderate"
            st.session_state["tp_variability_class"] = st.select_slider(
                "Variability Class", var_options, value=cur_var, key="_tp_var",
            )

            cat_options = ["low", "moderate", "high", "very_high"]
            cur_cat = st.session_state.get("tp_catchment_risk", "moderate")
            st.session_state["tp_catchment_risk"] = st.selectbox(
                "Catchment Risk", cat_options,
                index=cat_options.index(cur_cat), key="_tp_cat",
            )

        with col2:
            st.markdown("**Turbidity & NOM**")
            sw = st.session_state.get("source_water", {})
            turb_med = float(sw.get("turbidity_ntu", 5.0))
            toc_med  = float(sw.get("toc_mg_l", 5.0))

            st.session_state["tp_turb_p95"] = st.number_input(
                "Turbidity P95 (NTU)", 0.1, 2000.0,
                value=float(st.session_state.get("tp_turb_p95", round(turb_med * 4, 1))),
                step=1.0, format="%.1f", key="_tp_t95",
            )
            st.session_state["tp_turb_p99"] = st.number_input(
                "Turbidity P99 (NTU)", 0.1, 5000.0,
                value=float(st.session_state.get("tp_turb_p99", round(turb_med * 10, 1))),
                step=5.0, format="%.1f", key="_tp_t99",
            )
            ev_val = float(st.session_state.get("tp_turb_max") or 0.0)
            ev_in  = st.number_input(
                "Peak Event Turbidity (NTU, 0=unknown)", 0.0, 10000.0,
                value=ev_val, step=10.0, format="%.0f", key="_tp_tmax",
            )
            st.session_state["tp_turb_max"] = ev_in if ev_in > 0 else None

            st.session_state["tp_toc_p95"] = st.number_input(
                "TOC P95 (mg/L)", 0.0, 50.0,
                value=float(st.session_state.get("tp_toc_p95", round(toc_med * 1.5, 1))),
                step=0.5, format="%.1f", key="_tp_toc95",
            )
            st.session_state["tp_alkalinity"] = st.number_input(
                "Alkalinity (mg/L CaCO₃)", 0.0, 500.0,
                value=float(st.session_state.get("tp_alkalinity", 80.0)),
                step=5.0, key="_tp_alk",
            )
            st.session_state["tp_ph_median"] = st.number_input(
                "pH (median)", 4.0, 10.0,
                value=float(st.session_state.get("tp_ph_median", 7.5)),
                step=0.1, format="%.1f", key="_tp_ph",
            )
            st.session_state["tp_ph_min"] = st.number_input(
                "pH (minimum)", 4.0, 10.0,
                value=float(st.session_state.get("tp_ph_min", 7.0)),
                step=0.1, format="%.1f", key="_tp_phmin",
            )

        with col3:
            st.markdown("**Biological & Contaminants**")
            alg_options = ["low", "moderate", "high", "confirmed_bloom"]
            cur_alg = st.session_state.get("tp_algae_risk", "low")
            if cur_alg not in alg_options:
                cur_alg = "low"
            st.session_state["tp_algae_risk"] = st.select_slider(
                "Algae / Cyano Risk", alg_options, value=cur_alg, key="_tp_algae",
            )
            st.session_state["tp_cyano_confirmed"] = st.checkbox(
                "Cyanobacteria confirmed", value=bool(st.session_state.get("tp_cyano_confirmed", False)), key="_tp_cyano",
            )
            st.session_state["tp_cyanotoxin"] = st.checkbox(
                "Cyanotoxin detected", value=bool(st.session_state.get("tp_cyanotoxin", False)), key="_tp_cyt",
            )
            st.session_state["tp_mib_geosmin"] = st.checkbox(
                "MIB / geosmin confirmed", value=bool(st.session_state.get("tp_mib_geosmin", False)), key="_tp_mib",
            )
            st.session_state["tp_dbp_concern"] = st.checkbox(
                "DBP formation concern", value=bool(st.session_state.get("tp_dbp_concern", False)), key="_tp_dbp",
            )
            st.session_state["tp_arsenic_ug_l"] = st.number_input(
                "Arsenic (μg/L)", 0.0, 500.0,
                value=float(st.session_state.get("tp_arsenic_ug_l", 0.0)),
                step=1.0, format="%.1f", key="_tp_as",
            )
            st.session_state["tp_pfas_detected"] = st.checkbox(
                "PFAS detected", value=bool(st.session_state.get("tp_pfas_detected", False)), key="_tp_pfas",
            )
            if st.session_state.get("tp_pfas_detected"):
                st.session_state["tp_pfas_ng_l"] = st.number_input(
                    "PFAS concentration (ng/L)", 0.0, 10000.0,
                    value=float(st.session_state.get("tp_pfas_ng_l", 0.0)),
                    step=5.0, key="_tp_pfasc",
                )
            st.session_state["tp_troc_concern"] = st.checkbox(
                "Trace organics concern", value=bool(st.session_state.get("tp_troc_concern", False)), key="_tp_troc",
            )

        # Second row — LRV targets and site flags
        col4, col5, col6 = st.columns(3)
        with col4:
            st.markdown("**LRV Targets (log)**")
            st.session_state["tp_lrv_protozoa"] = st.number_input(
                "Protozoa", 0.0, 10.0,
                value=float(st.session_state.get("tp_lrv_protozoa", 4.0)),
                step=0.5, key="_tp_lrvp",
            )
            st.session_state["tp_lrv_bacteria"] = st.number_input(
                "Bacteria", 0.0, 12.0,
                value=float(st.session_state.get("tp_lrv_bacteria", 6.0)),
                step=0.5, key="_tp_lrvb",
            )
            st.session_state["tp_lrv_virus"] = st.number_input(
                "Virus", 0.0, 12.0,
                value=float(st.session_state.get("tp_lrv_virus", 6.0)),
                step=0.5, key="_tp_lrvv",
            )
        with col5:
            st.markdown("**Site Constraints**")
            st.session_state["tp_land_constrained"] = st.checkbox(
                "Land constrained", value=bool(st.session_state.get("tp_land_constrained", False)), key="_tp_land",
            )
            st.session_state["tp_retrofit"] = st.checkbox(
                "Retrofit / brownfield", value=bool(st.session_state.get("tp_retrofit", False)), key="_tp_ret",
            )
            st.session_state["tp_remote"] = st.checkbox(
                "Remote / limited operator access", value=bool(st.session_state.get("tp_remote", False)), key="_tp_rem",
            )
        with col6:
            st.markdown("**Pre-populated from Source Water page**")
            sw = st.session_state.get("source_water", {})
            for lbl, key in [
                ("Turbidity median", "turbidity_ntu"),
                ("TOC median", "toc_mg_l"),
                ("TDS", "tds_mg_l"),
                ("Hardness", "hardness_mg_l"),
                ("Iron", "iron_mg_l"),
                ("Manganese", "manganese_mg_l"),
                ("Colour", "colour_hu"),
            ]:
                val = sw.get(key, "—")
                st.caption(f"{lbl}: {val}")
            st.caption("Edit on the Source Water page, then return here.")


# ─── Rendering helpers ────────────────────────────────────────────────────────

def _strength_pill(strength: str) -> str:
    colours = {
        "strong":          "#2ecc71",
        "moderate":        "#4a9eff",
        "conditional":     "#f39c12",
        "not_recommended": "#e74c3c",
    }
    c = colours.get(strength, "#8899aa")
    return (
        f'<span style="background:{c};color:white;padding:2px 9px;'
        f'border-radius:4px;font-size:0.75rem;font-weight:600">'
        f'{strength.replace("_"," ").title()}</span>'
    )


def _lrv_bar(pathogen: str, required: float, lo: float, hi: float) -> str:
    ok_hi = hi >= required
    ok_lo = lo >= required
    if not ok_hi:
        status = f'<span style="color:#e74c3c;font-weight:700">DEFICIT {required - hi:.1f} log</span>'
    elif not ok_lo:
        status = '<span style="color:#f39c12">Marginal</span>'
    else:
        status = '<span style="color:#2ecc71">✓ Met</span>'

    pct_hi  = min(100.0, hi  / max(required, 0.01) * 100)
    pct_lo  = min(100.0, lo  / max(required, 0.01) * 100)

    return f"""
    <div style="margin-bottom:0.7rem">
      <div style="display:flex;justify-content:space-between;align-items:center;
                  font-size:0.82rem;margin-bottom:0.25rem">
        <span style="color:#1a1a2e;font-weight:600;min-width:80px">{pathogen.title()}</span>
        <span style="color:#8899aa">Required: {required:.1f} log</span>
        <span style="color:#1a56a0">Credited: {lo:.1f}–{hi:.1f} log</span>
        <span>{status}</span>
      </div>
      <div style="position:relative;background:#f0f4f8;border-radius:4px;height:12px">
        <div style="width:{pct_hi:.1f}%;background:#4a9eff33;height:100%;
                    border-radius:4px;position:absolute"></div>
        <div style="width:{pct_lo:.1f}%;background:#4a9eff;height:100%;
                    border-radius:4px;position:absolute"></div>
        <div style="position:absolute;left:{min(99.5, 100):.1f}%;top:-2px;bottom:-2px;
                    width:2px;background:#e74c3c;opacity:0.85"></div>
      </div>
    </div>"""


def _archetype_card(key, label, viable, rationale="", flags=None, preferred=False, exclusions=None):
    if viable:
        border = "#4a9eff" if preferred else "#2a6a3a"
        bg     = "#0d1e30" if preferred else "#0d2010"
        icon   = "✓"
        ic     = "#2ecc71"
        tag    = " ⭐" if preferred else ""
    else:
        border = "#3a1a1a"; bg = "#1a0a0a"; icon = "✗"; ic = "#e74c3c"; tag = ""

    body   = f'<div style="font-size:0.78rem;color:#1a56a0;margin-top:0.28rem">{rationale[:170]}</div>' if rationale else ""
    f_html = "".join(
        f'<div style="font-size:0.72rem;color:#f39c12;margin-top:0.12rem">⚠ {f[:140]}</div>'
        for f in (flags or [])[:2]
    )
    e_html = "".join(
        f'<div style="font-size:0.72rem;color:#e74c3c;margin-top:0.12rem">{e[:140]}</div>'
        for e in (exclusions or [])[:1]
    )
    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:8px;'
        f'padding:0.65rem 0.9rem;margin-bottom:0.35rem">'
        f'<div style="font-size:0.88rem;font-weight:600;color:{ic}">{icon} {key}. {label}{tag}</div>'
        f'{body}{f_html}{e_html}</div>'
    )


# ─── Main render ──────────────────────────────────────────────────────────────

def render():
    st.markdown("""
        <h2 style="color:#e8f4fd;font-size:1.4rem;font-weight:700;margin-bottom:0.2rem">
            Treatment Philosophy Analysis
        </h2>
        <p style="color:#8899aa;font-size:0.87rem;margin-bottom:1rem">
            System-level optimisation across Gates 1–5. Expand inputs to adjust
            parameters, then run the engine.
        </p>
    """, unsafe_allow_html=True)

    _render_input_panel()

    run_col, _ = st.columns([1, 3])
    with run_col:
        run_clicked = st.button("▶  Run Reasoning Engine", type="primary", use_container_width=True)

    if run_clicked or "tp_result" not in st.session_state:
        with st.spinner("Running reasoning engine…"):
            inputs = _build_inputs()
            st.session_state["tp_result"] = run_reasoning_engine(inputs)
            st.session_state["tp_inputs"]  = inputs

    result = st.session_state["tp_result"]
    inputs = st.session_state["tp_inputs"]

    # Executive summary
    st.markdown(f"""
        <div style="background:#f0f4ff;border-left:4px solid #4a9eff;padding:0.9rem 1.2rem;
                    border-radius:0 8px 8px 0;margin:0.5rem 0 0.8rem 0;
                    font-size:0.87rem;color:#334155;line-height:1.65">
            {result.executive_summary}
        </div>
    """, unsafe_allow_html=True)

    for w in result.key_warnings:
        error_box(w) if "⚠" in w else warning_box(w)

    st.markdown("<br>", unsafe_allow_html=True)

    tabs = st.tabs([
        "🏗️ Archetype Selection",
        "🎯 Preferred Philosophy",
        "🔬 LRV Barriers",
        "♻️ Residuals",
        "🧪 Contaminant Modules",
        "📊 Scoring",
        "⚠️ Uncertainties",
    ])

    # ══ TAB 1 — ARCHETYPE SELECTION ══════════════════════════════════════════
    with tabs[0]:
        cl = result.classification
        section_header("Gates 1–2: Classification & Primary Constraints", "🔍")

        c1, c2, c3 = st.columns(3)
        def _info_tile(heading, value, colour="#e8f4fd"):
            return (
                f'<div style="background:#f0f4f8;border-radius:8px;padding:0.8rem;'
                f'border:1px solid #e2e8f0">'
                f'<div style="font-size:0.7rem;color:#8899aa;text-transform:uppercase;'
                f'letter-spacing:0.05em">{heading}</div>'
                f'<div style="font-size:0.88rem;color:{colour};font-weight:600;margin-top:0.2rem">{value}</div>'
                f'</div>'
            )
        c1.markdown(_info_tile("Source Type", cl.source_description), unsafe_allow_html=True)
        c2.markdown(_info_tile("Primary Constraint", cl.primary_constraint_description, "#4a9eff"), unsafe_allow_html=True)
        df_c = "#2ecc71" if cl.direct_filtration_eligible else "#e74c3c"
        df_t = "Eligible" if cl.direct_filtration_eligible else f"Excluded ({len(cl.direct_filtration_exclusion_reasons)} reasons)"
        c3.markdown(_info_tile("Direct Filtration", df_t, df_c), unsafe_allow_html=True)

        if cl.secondary_constraints:
            st.markdown(
                f"<div style='font-size:0.8rem;color:#8899aa;margin:0.5rem 0'>"
                f"Secondary: <span style='color:#334155'>{', '.join(cl.secondary_constraints)}</span></div>",
                unsafe_allow_html=True,
            )

        if cl.governing_conditions:
            section_header("Governing Conditions (design-driving, not average)", "⚡")
            for cond in cl.governing_conditions:
                info_box(cond)

        if cl.direct_filtration_exclusion_reasons:
            with st.expander(f"Direct Filtration — {len(cl.direct_filtration_exclusion_reasons)} exclusion reasons"):
                for r in cl.direct_filtration_exclusion_reasons:
                    st.markdown(f"• {r}")

        if cl.contaminant_modules_required:
            section_header("Contaminant Modules Activated", "🧪")
            cols = st.columns(min(len(cl.contaminant_modules_required), 4))
            for i, m in enumerate(cl.contaminant_modules_required):
                cols[i % 4].markdown(
                    f"<div style='background:#0d2d3a;border:1px solid #1a5566;border-radius:6px;"
                    f"padding:0.4rem 0.7rem;font-size:0.8rem;color:#0284c7;text-align:center'>"
                    f"{m.replace('_',' ').title()}</div>",
                    unsafe_allow_html=True,
                )

        section_header("Gate 4: Treatment Archetypes", "🏭")
        lc, rc = st.columns(2)
        with lc:
            st.markdown(f"<div style='font-size:0.75rem;color:#2ecc71;font-weight:600;margin-bottom:0.4rem'>✓  VIABLE  ({len(result.archetype_selection.viable_archetypes)})</div>", unsafe_allow_html=True)
            for a in result.archetype_selection.viable_archetypes:
                st.markdown(_archetype_card(
                    a.key, a.label, viable=True,
                    rationale=a.inclusion_rationale[0] if a.inclusion_rationale else "",
                    flags=a.flags,
                    preferred=(a.key == result.preferred_archetype_key),
                ), unsafe_allow_html=True)
        with rc:
            st.markdown(f"<div style='font-size:0.75rem;color:#e74c3c;font-weight:600;margin-bottom:0.4rem'>✗  EXCLUDED  ({len(result.archetype_selection.excluded_archetypes)})</div>", unsafe_allow_html=True)
            for a in result.archetype_selection.excluded_archetypes:
                st.markdown(_archetype_card(
                    a.key, a.label, viable=False,
                    exclusions=a.exclusion_reasons,
                ), unsafe_allow_html=True)

    # ══ TAB 2 — PREFERRED PHILOSOPHY ════════════════════════════════════════
    with tabs[1]:
        pkey = result.preferred_archetype_key
        arch = ARCHETYPES.get(pkey, {})
        section_header(f"⭐  {result.preferred_archetype_label}", "🎯")
        st.markdown(f"""
            <div style="background:#eff6ff;border:2px solid #4a9eff;border-radius:10px;
                        padding:1rem 1.2rem;font-size:0.86rem;color:#1a56a0;line-height:1.7">
                {arch.get('philosophy', '')}
            </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        cs, cw = st.columns(2)
        with cs:
            section_header("Strengths", "✓")
            for s in arch.get("strengths", []):
                success_box(s)
        with cw:
            section_header("Weaknesses / Limitations", "✗")
            for w in arch.get("weaknesses", []):
                warning_box(w)
        st.markdown("<br>", unsafe_allow_html=True)
        section_header("Why This Philosophy is Preferred", "📝")
        info_box(result.preferred_archetype_rationale)
        section_header("Residuals Profile", "♻️")
        info_box(arch.get("residuals", "See Residuals tab for full assessment."))
        chips = [
            ("Energy",          arch.get("energy_class",   "").replace("_", " ").title()),
            ("Chemical demand", arch.get("chemical_class", "").replace("_", " ").title()),
            ("Footprint",       arch.get("footprint_class","").replace("_", " ").title()),
        ]
        st.markdown(
            '<div style="display:flex;gap:0.6rem;flex-wrap:wrap;margin-top:0.5rem">'
            + "".join(
                f'<div style="background:#f0f4f8;border-radius:6px;padding:0.45rem 0.8rem;font-size:0.8rem">'
                f'<span style="color:#8899aa">{lbl}: </span>'
                f'<span style="color:#1a1a2e;font-weight:600">{val}</span></div>'
                for lbl, val in chips
            )
            + "</div>",
            unsafe_allow_html=True,
        )

    # ══ TAB 3 — LRV BARRIERS ════════════════════════════════════════════════
    with tabs[2]:
        section_header("LRV Barrier Analysis", "🔬")
        info_box(
            f"Required LRVs — Protozoa: {result.required_lrv.get('protozoa',0):.1f} log  |  "
            f"Bacteria: {result.required_lrv.get('bacteria',0):.1f} log  |  "
            f"Virus: {result.required_lrv.get('virus',0):.1f} log  "
            f"(catchment risk: {inputs.catchment_risk}, objective: {inputs.treatment_objective})"
        )
        pkey = result.preferred_archetype_key
        lrv  = result.lrv_by_archetype.get(pkey)
        if lrv:
            section_header(f"Preferred — {result.preferred_archetype_label}", "⭐")
            for pathogen in ["protozoa", "bacteria", "virus"]:
                st.markdown(_lrv_bar(
                    pathogen,
                    lrv.required.get(pathogen, 0),
                    lrv.total_credited_low.get(pathogen, 0),
                    lrv.total_credited_high.get(pathogen, 0),
                ), unsafe_allow_html=True)

            da = lrv.disinfection_assessment
            section_header("Disinfection Adequacy", "💊")
            d1, d2, d3 = st.columns(3)
            for col, lbl, ok in [
                (d1, "Primary Disinfection",   da.get("primary_disinfection")),
                (d2, "Distribution Residual",  da.get("secondary_residual")),
                (d3, "Protozoan Inactivation", da.get("protozoan_inactivation_barrier")),
            ]:
                icon = "✓" if ok else "✗"
                c    = "#2ecc71" if ok else "#e74c3c"
                col.markdown(
                    f'<div style="text-align:center">'
                    f'<div style="font-size:1.8rem;color:{c}">{icon}</div>'
                    f'<div style="font-size:0.78rem;color:#8899aa">{lbl}</div></div>',
                    unsafe_allow_html=True,
                )

            for risk in lrv.key_risks:
                error_box(risk) if ("DEFICIT" in risk or "CRITICAL" in risk) else warning_box(risk)
            if lrv.single_barrier_dependence:
                section_header("Single-Barrier Dependence", "⚠️")
                for f in lrv.single_barrier_dependence:
                    warning_box(f)

        section_header("All Viable Archetypes — LRV credited high / required", "📊")
        hdr = st.columns([3, 2, 2, 2])
        for i, lbl in enumerate(["ARCHETYPE", "PROTOZOA", "BACTERIA", "VIRUS"]):
            hdr[i].markdown(f"<span style='font-size:0.72rem;color:#8899aa'>{lbl}</span>", unsafe_allow_html=True)
        for key, lrv_r in result.lrv_by_archetype.items():
            is_p = key == result.preferred_archetype_key
            row  = st.columns([3, 2, 2, 2])
            lbl  = ARCHETYPES.get(key, {}).get("label", key)
            row[0].markdown(
                f"<span style='font-size:0.82rem;color:{'#4a9eff' if is_p else '#e8f4fd'}'>"
                f"{'⭐ ' if is_p else ''}{key}. {lbl[:30]}</span>",
                unsafe_allow_html=True,
            )
            for i, pathogen in enumerate(["protozoa", "bacteria", "virus"]):
                req = lrv_r.required.get(pathogen, 0)
                hi  = lrv_r.total_credited_high.get(pathogen, 0)
                c   = "#2ecc71" if hi >= req else "#e74c3c"
                row[i+1].markdown(f"<span style='font-size:0.82rem;color:{c}'>{hi:.1f} / {req:.1f}</span>", unsafe_allow_html=True)

    # ══ TAB 4 — RESIDUALS ════════════════════════════════════════════════════
    with tabs[3]:
        section_header("Residuals & Side-Stream Assessment", "♻️")
        res_comp = result.residuals
        if res_comp.problem_transfer_warnings:
            section_header("Problem Transfer Flags", "⚠️")
            for flag in res_comp.problem_transfer_warnings:
                error_box(flag)

        section_header("Residuals by Viable Archetype", "📋")
        cx_colours = {"low": "#2ecc71", "moderate": "#f39c12", "high": "#e74c3c", "very_high": "#9b0000"}
        for key, res in res_comp.archetype_assessments.items():
            arch_lbl = ARCHETYPES.get(key, {}).get("label", key)
            is_pref  = key == result.preferred_archetype_key
            with st.expander(
                f"{'⭐ ' if is_pref else ''}{key}. {arch_lbl} — Complexity: {res.complexity_rating.upper()}",
                expanded=is_pref,
            ):
                if res.residual_streams:
                    st.markdown(f"**Streams:** `{'` | `'.join(res.residual_streams)}`")
                for cw in res.classified_waste_streams:
                    error_box(cw)
                if res.biopoint_handoff_required:
                    info_box("BioPoint handoff recommended: sludge management scope should be assessed separately.")
                for km in res.key_messages:
                    warning_box(km)
                for sk, sd in res.stream_details.items():
                    sp = "".join(
                        f'<div style="color:#f39c12;font-size:0.72rem;margin-top:0.1rem">⚠ {c}</div>'
                        for c in sd.get("special_considerations", [])[:2]
                    )
                    st.markdown(f"""
                        <div style="background:#f0f4f8;border-radius:6px;padding:0.55rem 0.85rem;margin:0.2rem 0;font-size:0.8rem">
                          <div style="color:#1a1a2e;font-weight:600">{sd['label']}</div>
                          <div style="color:#8899aa;margin-top:0.12rem">
                            Volume: {sd['volume_class']} | Generation: {sd['generation']}
                          </div>{sp}
                        </div>
                    """, unsafe_allow_html=True)

    # ══ TAB 5 — CONTAMINANT MODULES ══════════════════════════════════════════
    with tabs[4]:
        if not result.contaminant_modules:
            info_box("No contaminant-specific modules were triggered for this source water configuration.")
        else:
            for mod_key, mod in result.contaminant_modules.items():
                section_header(mod_key.replace("_", " ").title() + " Module", "🧪")
                info_box(mod.contaminant_summary)
                st.markdown(f"""
                    <div style="background:#0d2d1a;border:1px solid #2ecc71;border-radius:8px;
                                padding:0.8rem 1.1rem;margin:0.5rem 0">
                      <div style="font-size:0.7rem;color:#8899aa;margin-bottom:0.25rem;
                                  text-transform:uppercase;letter-spacing:0.04em">Preferred Pathway</div>
                      <div style="font-size:0.9rem;color:#2ecc71;font-weight:600">{mod.preferred_pathway}</div>
                      <div style="font-size:0.82rem;color:#89c89a;margin-top:0.35rem;line-height:1.6">
                          {mod.preferred_pathway_rationale}</div>
                    </div>
                """, unsafe_allow_html=True)
                if mod.problem_transfer_flag:
                    error_box(mod.problem_transfer_flag)
                if mod.critical_preconditions:
                    section_header("Critical Preconditions", "⚠️")
                    for pre in mod.critical_preconditions:
                        warning_box(pre)
                ca, cr = st.columns(2)
                with ca:
                    if mod.alternative_pathways:
                        with st.expander("Alternative Pathways"):
                            for alt in mod.alternative_pathways:
                                st.markdown(f"• {alt}")
                with cr:
                    if mod.key_risks:
                        with st.expander("Key Risks"):
                            for risk in mod.key_risks:
                                st.markdown(f"• {risk}")
                st.markdown("<br>", unsafe_allow_html=True)

    # ══ TAB 6 — SCORING ══════════════════════════════════════════════════════
    with tabs[5]:
        section_header("Tier 1–4 Comparative Scoring", "📊")
        info_box(
            "Tier 1 is a pass/fail safety gate — failure removes an archetype from consideration. "
            "Tier 2 (robustness) carries 50% of overall weight. Tier 3 (resources) 30%, Tier 4 (cost/risk) 20%."
        )
        for s in result.scores:
            is_pref = s.archetype_key == result.preferred_archetype_key
            t1_t    = "PASS" if s.tier1_pass else "FAIL"
            ov_str  = f"{s.overall_score:.1f}/10" if s.tier1_pass else "—"
            with st.expander(
                f"{'⭐ ' if is_pref else ''}{s.archetype_key}. {s.archetype_label}"
                f"   |   Tier 1: {t1_t}   |   Overall: {ov_str}",
                expanded=is_pref,
            ):
                if not s.tier1_pass:
                    for issue in s.tier1_issues:
                        error_box(issue)
                if s.tier1_pass:
                    render_kpi_card("Tier 2 Robustness",  f"{s.tier2_score:.1f}", "/ 10",
                                    f"Var {s.variability_robustness:.0f} · Event {s.event_response:.0f} · Barrier {s.barrier_redundancy:.0f} · Ops {s.operability:.0f}")
                    render_kpi_card("Tier 3 Resources",   f"{s.tier3_score:.1f}", "/ 10",
                                    f"Energy {s.energy_demand:.0f} · Chem {s.chemical_demand:.0f} · Residuals {s.residuals_burden:.0f}")
                    render_kpi_card("Tier 4 Cost / Risk", f"{s.tier4_score:.1f}", "/ 10",
                                    f"CAPEX {s.capex:.0f} · OPEX {s.opex:.0f} · Expand {s.expandability:.0f}")
                    render_kpi_card("Overall",            ov_str)
                st.markdown(f"**Recommendation:** {_strength_pill(s.recommendation_strength)}", unsafe_allow_html=True)

    # ══ TAB 7 — UNCERTAINTIES ════════════════════════════════════════════════
    with tabs[6]:
        section_header("Critical Uncertainties", "❓")
        for i, unc in enumerate(result.critical_uncertainties, 1):
            st.markdown(f"""
                <div style="background:#1a1a2e;border-left:3px solid #f39c12;padding:0.6rem 1rem;
                            border-radius:0 6px 6px 0;margin:0.35rem 0;
                            font-size:0.84rem;color:#d4a843;line-height:1.55">
                    {i}. {unc}
                </div>
            """, unsafe_allow_html=True)

        section_header("Recommended Next Steps", "→")
        for i, step in enumerate(result.next_steps, 1):
            st.markdown(f"""
                <div style="display:flex;gap:0.8rem;align-items:flex-start;padding:0.5rem 0;
                            border-bottom:1px solid #e2e8f0;font-size:0.85rem">
                    <span style="color:#4a9eff;font-weight:700;min-width:1.5rem">{i}.</span>
                    <span style="color:#334155;line-height:1.55">{step}</span>
                </div>
            """, unsafe_allow_html=True)

    # Navigation
    st.markdown("<br>", unsafe_allow_html=True)
    nl, nr = st.columns(2)
    with nl:
        if st.button("← Technology Selection", use_container_width=True):
            st.session_state["current_page"] = "technology_selection"
            st.rerun()
    with nr:
        if st.button("Analysis Results →", type="primary", use_container_width=True):
            st.session_state["current_page"] = "results"
            st.rerun()
