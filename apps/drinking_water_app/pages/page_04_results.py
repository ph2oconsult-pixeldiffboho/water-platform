"""
AquaPoint — Page 5: Analysis Results
Full dual-engine results dashboard.
Reasoning engine provides philosophy context; calc engine provides quantified results.
ph2o Consulting | Water Utility Planning Platform
"""
import streamlit as st
from ..engine import run_full_analysis, TECHNOLOGIES, LIFECYCLE_DEFAULTS, MCA_DEFAULT_WEIGHTS
from ..engine.reasoning import SourceWaterInputs, run_reasoning_engine
from ..ui_helpers import (
    section_header, warning_box, info_box, success_box, error_box,
    format_currency, risk_badge, compliance_badge,
    render_mca_gauge, render_kpi_card, score_colour,
)

PLANT_TO_SOURCE = {
    "conventional": "river", "membrane": "river",
    "groundwater": "groundwater", "desalination": "desalination",
}


# ─── Input builders ───────────────────────────────────────────────────────────

def _calc_inputs() -> dict:
    return {
        "plant_type":           st.session_state.get("plant_type", "conventional"),
        "flow_ML_d":            st.session_state.get("flow_ML_d", 10.0),
        "source_water":         st.session_state.get("source_water", {
            "turbidity_ntu": 5, "toc_mg_l": 5, "tds_mg_l": 300,
            "hardness_mg_l": 150, "iron_mg_l": 0.1, "manganese_mg_l": 0.02,
            "colour_hu": 10, "algal_cells_ml": 500,
        }),
        "selected_technologies": st.session_state.get("selected_technologies", []),
        "lifecycle_params": {
            "analysis_period_years":  st.session_state.get("analysis_period",  LIFECYCLE_DEFAULTS["analysis_period_years"]),
            "discount_rate_pct":      st.session_state.get("discount_rate",     LIFECYCLE_DEFAULTS["discount_rate_pct"]),
            "opex_escalation_pct":    st.session_state.get("opex_escalation",   LIFECYCLE_DEFAULTS["opex_escalation_pct"]),
            "capex_contingency_pct":  st.session_state.get("capex_contingency", LIFECYCLE_DEFAULTS["capex_contingency_pct"]),
        },
        "electricity_cost_AUD_kWh": st.session_state.get("electricity_cost", 0.12),
        "coagulant":                st.session_state.get("coagulant", "alum"),
        "mca_weights":              st.session_state.get("mca_weights", MCA_DEFAULT_WEIGHTS),
    }


def _reasoning_inputs(plant_type: str, sw: dict) -> SourceWaterInputs:
    algal = float(sw.get("algal_cells_ml", 0))
    algae_risk = ("high" if algal > 10000 else "moderate" if algal > 2000 else "low")
    turb = float(sw.get("turbidity_ntu", 5))
    return SourceWaterInputs(
        source_type=PLANT_TO_SOURCE.get(plant_type, "river"),
        turbidity_median_ntu=turb,
        turbidity_p95_ntu=turb * 4,
        turbidity_p99_ntu=turb * 10,
        toc_median_mg_l=float(sw.get("toc_mg_l", 5)),
        toc_p95_mg_l=float(sw.get("toc_mg_l", 5)) * 1.5,
        colour_median_hu=float(sw.get("colour_hu", 10)),
        hardness_median_mg_l=float(sw.get("hardness_mg_l", 150)),
        iron_median_mg_l=float(sw.get("iron_mg_l", 0.1)),
        manganese_median_mg_l=float(sw.get("manganese_mg_l", 0.02)),
        tds_median_mg_l=float(sw.get("tds_mg_l", 300)),
        algae_risk=algae_risk,
        variability_class="moderate",
        catchment_risk="moderate",
        treatment_objective="potable",
    )


# ─── Rendering helpers ────────────────────────────────────────────────────────

def _kv(label, value, colour="#e8f4fd"):
    return (
        f'<div style="display:flex;justify-content:space-between;padding:0.3rem 0;'
        f'border-bottom:1px solid #e2e8f0;font-size:0.83rem">'
        f'<span style="color:#8899aa">{label}</span>'
        f'<span style="color:{colour};font-weight:600">{value}</span></div>'
    )


def _section_card(title, html_body, border="#2a3a52"):
    return f"""
        <div style="background:#f0f4f8;border:1px solid {border};border-radius:8px;
                    padding:0.8rem 1rem;margin-bottom:0.7rem">
            <div style="font-size:0.72rem;color:#8899aa;text-transform:uppercase;
                        letter-spacing:0.05em;margin-bottom:0.5rem">{title}</div>
            {html_body}
        </div>"""


# ─── Main render ──────────────────────────────────────────────────────────────

def render():
    st.markdown("""
        <div style="margin-bottom:1.2rem">
            <h2 style="color:#1a1a2e;font-size:1.4rem;font-weight:600;margin-bottom:0.2rem">
                Analysis Results
            </h2>
            <p style="color:#555;font-size:0.87rem;margin:0">
                Comprehensive treatment train evaluation across all analysis layers.
            </p>
        </div>
    """, unsafe_allow_html=True)

    selected_technologies = st.session_state.get("selected_technologies", [])
    if not selected_technologies:
        warning_box("No technologies selected. Please complete Technology Selection first.")
        if st.button("← Technology Selection"):
            st.session_state["current_page"] = "technology_selection"
            st.rerun()
        return

    # ── Run both engines ──────────────────────────────────────────────────────
    ci = _calc_inputs()

    with st.spinner("Running analysis…"):
        try:
            results = run_full_analysis(ci)
            st.session_state["last_results"] = results
        except Exception as e:
            error_box(f"Analysis failed: {e}")
            return

        try:
            r_result = run_reasoning_engine(_reasoning_inputs(ci["plant_type"], ci["source_water"]))
        except Exception:
            r_result = None

    # ── Dual-engine summary bar ───────────────────────────────────────────────
    mca = results.get("mca", {})
    lc  = results.get("lifecycle_cost", {})
    en  = results.get("energy", {})
    capx= results.get("capex", {})

    mca_score = mca.get("total_score", 0)
    npv       = lc.get("npv_total_AUD", 0)
    capex_v   = capx.get("total_capex_AUD", {}).get("typical", 0)
    energy_v  = en.get("specific_energy_kWh_ML", {}).get("typical", 0)

    k1, k2, k3, k4 = st.columns(4)
    with k1: render_kpi_card("MCA Score",     f"{mca_score:.0f}", "/ 100")
    with k2: render_kpi_card("CAPEX",         format_currency(capex_v))
    with k3: render_kpi_card("NPV (30 yr)",   format_currency(npv))
    with k4: render_kpi_card("Specific Energy", f"{energy_v:.0f}", "kWh/ML")

    # Reasoning context strip
    if r_result:
        rc = "#2ecc71" if r_result.preferred_archetype_key in ["B","C","D"] else "#4a9eff"
        st.markdown(f"""
            <div style="background:#0a1d2e;border-left:3px solid #4a9eff;padding:0.65rem 1rem;
                        border-radius:0 6px 6px 0;margin:0.5rem 0;font-size:0.83rem;color:#1a56a0">
                <span style="color:#4a9eff;font-weight:600">Philosophy: </span>
                {r_result.preferred_archetype_label} — {r_result.preferred_archetype_rationale}
            </div>
        """, unsafe_allow_html=True)

        for w in r_result.key_warnings[:2]:
            error_box(w) if "⚠" in w else warning_box(w)

    # Train display
    train_labels = [TECHNOLOGIES.get(t, {}).get("label", t) for t in selected_technologies]
    st.markdown(f"""
        <div style="background:#eff6ff;border:1px solid #4a9eff;border-radius:8px;
                    padding:0.6rem 1rem;font-size:0.83rem;color:#1a56a0;margin:0.5rem 0 1rem 0">
            <span style="color:#4a9eff;font-weight:600">Train: </span>
            {" → ".join(train_labels)}
        </div>
    """, unsafe_allow_html=True)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tabs = st.tabs([
        "📊 MCA Score",
        "💧 Water Quality",
        "⚡ Energy",
        "🧪 Chemicals",
        "🏗️ CAPEX",
        "💰 OPEX & NPV",
        "⚠️ Risk",
        "🌿 Environment",
        "📋 Regulatory",
        "✅ Feasibility",
        "🧂 Softening",
        "⚙️ Settings",
    ])

    # ══ TAB 1 — MCA SCORE ════════════════════════════════════════════════════
    with tabs[0]:
        section_header("Multi-Criteria Analysis (MCA)", "📊")
        col_g, col_b = st.columns([1, 2])
        with col_g:
            render_mca_gauge(mca_score, "Overall MCA Score")
        with col_b:
            scores = mca.get("scores", {})
            weights = mca.get("weights", MCA_DEFAULT_WEIGHTS)
            score_rows = ""
            for k, w in weights.items():
                s = scores.get(k, 0)
                c = score_colour(s)
                bar_pct = min(100, s)
                lbl = k.replace("_", " ").title()
                score_rows += f"""
                    <div style="margin-bottom:0.6rem">
                        <div style="display:flex;justify-content:space-between;
                                    font-size:0.8rem;margin-bottom:0.2rem">
                            <span style="color:#334155">{lbl}</span>
                            <span style="color:{c};font-weight:600">{s:.0f}/100</span>
                            <span style="color:#8899aa">weight {w:.0%}</span>
                        </div>
                        <div style="background:#f0f4f8;border-radius:4px;height:10px">
                            <div style="width:{bar_pct}%;background:{c};
                                        height:100%;border-radius:4px"></div>
                        </div>
                    </div>"""
            st.markdown(score_rows, unsafe_allow_html=True)

        if r_result:
            section_header("Reasoning Engine — Tier 2–4 Scores", "🏗️")
            cols = st.columns(len(r_result.scores))
            for i, s in enumerate(r_result.scores):
                with cols[i]:
                    c = score_colour(s.overall_score * 10) if s.tier1_pass else "#e74c3c"
                    t1 = "PASS" if s.tier1_pass else "FAIL"
                    t1c = "#2ecc71" if s.tier1_pass else "#e74c3c"
                    st.markdown(f"""
                        <div style="background:#f0f4f8;border-radius:8px;padding:0.6rem;
                                    text-align:center;border:1px solid #e2e8f0">
                            <div style="font-size:0.7rem;color:#8899aa">{s.archetype_key}. {s.archetype_label[:18]}</div>
                            <div style="font-size:1.4rem;font-weight:700;color:{c}">{s.overall_score:.1f}</div>
                            <div style="font-size:0.65rem;color:{t1c}">{t1}</div>
                        </div>
                    """, unsafe_allow_html=True)

    # ══ TAB 2 — WATER QUALITY ════════════════════════════════════════════════
    with tabs[1]:
        tp = results.get("treatment_performance", {})
        section_header("Predicted Treated Water Quality vs ADWG", "💧")

        comp = tp.get("compliance", {})
        if comp:
            hdr = st.columns([2, 2, 2, 2, 2])
            for i, lbl in enumerate(["Parameter", "Raw", "Predicted", "ADWG Limit", "Status"]):
                hdr[i].markdown(f"<span style='font-size:0.7rem;color:#8899aa'>{lbl}</span>", unsafe_allow_html=True)

            sw = ci["source_water"]
            param_labels = {
                "turbidity_ntu": "Turbidity (NTU)", "toc_mg_l": "TOC (mg/L)",
                "tds_mg_l": "TDS (mg/L)", "hardness_mg_l": "Hardness (mg/L)",
                "iron_mg_l": "Iron (mg/L)", "manganese_mg_l": "Manganese (mg/L)",
                "colour_hu": "Colour (HU)",
            }
            pq = tp.get("predicted_quality", {})
            for param, cdata in comp.items():
                row = st.columns([2, 2, 2, 2, 2])
                raw = sw.get(param, "—")
                pred = cdata["predicted"]
                lim  = cdata["guideline"]
                ok   = cdata["compliant"]
                row[0].markdown(f"<span style='font-size:0.82rem;color:#1a1a2e'>{param_labels.get(param, param)}</span>", unsafe_allow_html=True)
                row[1].markdown(f"<span style='font-size:0.82rem;color:#8899aa'>{raw}</span>", unsafe_allow_html=True)
                row[2].markdown(f"<span style='font-size:0.82rem;color:{'#2ecc71' if ok else '#e74c3c'}'>{pred}</span>", unsafe_allow_html=True)
                row[3].markdown(f"<span style='font-size:0.82rem;color:#8899aa'>{lim}</span>", unsafe_allow_html=True)
                row[4].markdown(compliance_badge(ok), unsafe_allow_html=True)

        disinfection_ok = tp.get("disinfection_adequate", False)
        if disinfection_ok:
            success_box(f"Disinfection: adequate — {', '.join(tp.get('disinfection_technologies', []))}")
        else:
            error_box("No primary disinfection technology in selected train.")

        overall = tp.get("overall_compliant", False)
        if overall:
            success_box("All assessed parameters comply with ADWG guidelines.")
        else:
            warning_box("One or more parameters do not comply with ADWG guidelines after treatment.")

    # ══ TAB 3 — ENERGY ═══════════════════════════════════════════════════════
    with tabs[2]:
        section_header("Energy Assessment", "⚡")
        en = results.get("energy", {})

        c1, c2, c3 = st.columns(3)
        with c1:
            render_kpi_card("Specific Energy (typical)", f"{en.get('specific_energy_kWh_ML',{}).get('typical',0):.0f}", "kWh/ML")
        with c2:
            render_kpi_card("Annual Energy (typical)", f"{en.get('annual_energy_MWh',{}).get('typical',0)/1000:.1f}", "GWh/yr")
        with c3:
            render_kpi_card("Annual Energy Cost", format_currency(en.get("annual_cost_AUD",{}).get("typical",0)))

        # Benchmark comparison
        bench = en.get("benchmark_kWh_ML", {})
        if bench:
            typ_energy = en.get("specific_energy_kWh_ML", {}).get("typical", 0)
            bench_typ  = bench.get("typical", 400)
            delta_pct  = (typ_energy - bench_typ) / bench_typ * 100
            delta_colour = "#2ecc71" if delta_pct <= 10 else "#f39c12" if delta_pct <= 30 else "#e74c3c"
            section_header("vs Plant Type Benchmark", "📊")
            bc1, bc2, bc3 = st.columns(3)
            with bc1: render_kpi_card("Benchmark Low",     f"{bench.get('low',0):.0f}", "kWh/ML")
            with bc2: render_kpi_card("Benchmark Typical", f"{bench.get('typical',0):.0f}", "kWh/ML")
            with bc3: render_kpi_card("Benchmark High",    f"{bench.get('high',0):.0f}", "kWh/ML")
            st.markdown(
                f"<div style='font-size:0.85rem;color:{delta_colour};margin-top:0.5rem'>"
                f"This train is {abs(delta_pct):.0f}% {'above' if delta_pct > 0 else 'below'} "
                f"the benchmark typical for this plant type.</div>",
                unsafe_allow_html=True,
            )

        # Technology breakdown
        section_header("Energy by Technology", "▸")
        breakdown = en.get("technology_breakdown_kWh_ML", {})
        for tech, bench_d in breakdown.items():
            lbl = TECHNOLOGIES.get(tech, {}).get("label", tech)
            typ = bench_d.get("typical", 0)
            lo  = bench_d.get("low", 0)
            hi  = bench_d.get("high", 0)
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:0.3rem 0;'
                f'border-bottom:1px solid #e2e8f0;font-size:0.82rem">'
                f'<span style="color:#334155">{lbl}</span>'
                f'<span style="color:#8899aa">{lo}–{hi} kWh/ML</span>'
                f'<span style="color:#1a1a2e;font-weight:600">{typ} kWh/ML typical</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ══ TAB 4 — CHEMICALS ════════════════════════════════════════════════════
    with tabs[3]:
        section_header("Chemical Use & Cost", "🧪")
        cu = results.get("chemical_use", {})
        chemicals = cu.get("chemicals", {})

        if chemicals:
            render_kpi_card("Total Annual Chemical Cost",
                            format_currency(cu.get("total_annual_cost_AUD", 0)))
            st.markdown("<br>", unsafe_allow_html=True)
            hdr = st.columns([2, 2, 2, 2])
            for i, lbl in enumerate(["Chemical", "Dose (mg/L)", "Annual (t)", "Annual Cost"]):
                hdr[i].markdown(f"<span style='font-size:0.7rem;color:#8899aa'>{lbl}</span>", unsafe_allow_html=True)
            for ck, cd in chemicals.items():
                row = st.columns([2, 2, 2, 2])
                row[0].markdown(f"<span style='font-size:0.82rem;color:#1a1a2e'>{cd['label']}</span>", unsafe_allow_html=True)
                row[1].markdown(f"<span style='font-size:0.82rem;color:#8899aa'>{cd['dose_mg_L']:.1f}</span>", unsafe_allow_html=True)
                row[2].markdown(f"<span style='font-size:0.82rem;color:#8899aa'>{cd['annual_kg']/1000:.1f}</span>", unsafe_allow_html=True)
                row[3].markdown(f"<span style='font-size:0.82rem;color:#1a1a2e'>{format_currency(cd['annual_cost_AUD'])}</span>", unsafe_allow_html=True)
        else:
            info_box("No chemical consumption data — check technology selection includes coagulation or disinfection.")

    # ══ TAB 5 — CAPEX ════════════════════════════════════════════════════════
    with tabs[4]:
        section_header("Capital Cost Estimate", "🏗️")
        cx = results.get("capex", {})
        totals = cx.get("total_capex_AUD", {})

        c1, c2, c3 = st.columns(3)
        with c1: render_kpi_card("CAPEX Low",     format_currency(totals.get("low", 0)))
        with c2: render_kpi_card("CAPEX Typical", format_currency(totals.get("typical", 0)))
        with c3: render_kpi_card("CAPEX High",    format_currency(totals.get("high", 0)))

        info_box(
            f"Includes {cx.get('contingency_pct',20):.0f}% contingency. "
            f"Scaled using economy-of-scale exponent 0.65 from 10 ML/d reference. "
            f"Order-of-magnitude estimate only — detailed design required."
        )

        section_header("CAPEX by Technology (typical)", "▸")
        bd = cx.get("technology_breakdown_AUD", {})
        total_typ = cx.get("subtotal_AUD", {}).get("typical", 1)
        for tech, costs in bd.items():
            lbl = TECHNOLOGIES.get(tech, {}).get("label", tech)
            typ = costs.get("typical", 0)
            pct = typ / max(total_typ, 1) * 100
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:0.3rem 0;border-bottom:1px solid #e2e8f0;font-size:0.82rem">'
                f'<span style="color:#334155;min-width:200px">{lbl}</span>'
                f'<div style="flex:1;margin:0 1rem;background:#f0f4f8;border-radius:3px;height:8px">'
                f'<div style="width:{pct:.0f}%;background:#4a9eff;height:100%;border-radius:3px"></div></div>'
                f'<span style="color:#1a1a2e;font-weight:600;min-width:80px;text-align:right">'
                f'{format_currency(typ)}</span></div>',
                unsafe_allow_html=True,
            )

    # ══ TAB 6 — OPEX & NPV ═══════════════════════════════════════════════════
    with tabs[5]:
        section_header("Operating Cost & Lifecycle NPV", "💰")
        op  = results.get("opex", {})
        lc2 = results.get("lifecycle_cost", {})

        c1, c2, c3 = st.columns(3)
        with c1: render_kpi_card("Annual OPEX",   format_currency(op.get("total_annual_opex_AUD", 0)))
        with c2: render_kpi_card("Unit OPEX",     f"{op.get('unit_opex_AUD_ML', 0):.0f}", "AUD/ML")
        with c3: render_kpi_card("30-yr NPV",     format_currency(lc2.get("npv_total_AUD", 0)))

        section_header("OPEX Breakdown", "▸")
        opex_items = [
            ("Energy",               op.get("energy_AUD", 0)),
            ("Chemicals",            op.get("chemicals_AUD", 0)),
            ("Maintenance",          op.get("maintenance_AUD", 0)),
            ("Labour",               op.get("labour_AUD", 0)),
            ("Membrane replacement", op.get("membrane_replacement_AUD", 0)),
            ("Media replacement",    op.get("media_replacement_AUD", 0)),
        ]
        total_opex = op.get("total_annual_opex_AUD", 1)
        rows_html = ""
        for lbl, val in opex_items:
            if val > 0:
                pct = val / max(total_opex, 1) * 100
                rows_html += _kv(lbl, format_currency(val))
        st.markdown(rows_html, unsafe_allow_html=True)

        section_header("NPV Composition", "▸")
        capex_frac = lc2.get("capex_fraction_pct", 0)
        opex_frac  = lc2.get("opex_fraction_pct", 0)
        st.markdown(f"""
            <div style="background:#f0f4f8;border-radius:8px;padding:0.8rem;margin:0.5rem 0">
                <div style="display:flex;height:20px;border-radius:4px;overflow:hidden;margin-bottom:0.4rem">
                    <div style="width:{capex_frac:.0f}%;background:#4a9eff"></div>
                    <div style="width:{opex_frac:.0f}%;background:#2ecc71"></div>
                </div>
                <div style="font-size:0.78rem;display:flex;gap:1.5rem">
                    <span><span style="color:#4a9eff">■</span>
                          <span style="color:#8899aa"> CAPEX {capex_frac:.0f}%
                          ({format_currency(lc2.get('capex_AUD',0))})</span></span>
                    <span><span style="color:#2ecc71">■</span>
                          <span style="color:#8899aa"> PV OPEX {opex_frac:.0f}%
                          ({format_currency(lc2.get('pv_opex_AUD',0))})</span></span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        info_box(
            f"30-year analysis | Discount rate: {lc2.get('discount_rate_pct',7):.1f}% | "
            f"OPEX escalation: {lc2.get('opex_escalation_pct',2.5):.1f}%/yr"
        )

    # ══ TAB 7 — RISK ═════════════════════════════════════════════════════════
    with tabs[6]:
        section_header("Risk Assessment", "⚠️")
        rk = results.get("risk", {})
        ov = rk.get("overall", {})

        r1, r2, r3 = st.columns(3)
        with r1: render_kpi_card("Implementation Risk", ov.get("implementation_label", "—"))
        with r2: render_kpi_card("Operational Risk",    ov.get("operational_label", "—"))
        with r3: render_kpi_card("Regulatory Risk",     ov.get("regulatory_label", "—"))

        for flag in rk.get("water_quality_risk_flags", []):
            warning_box(flag)

        section_header("Risk by Technology", "▸")
        for tech, trisk in rk.get("technology_risks", {}).items():
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:0.3rem 0;border-bottom:1px solid #e2e8f0;font-size:0.82rem">'
                f'<span style="color:#334155;min-width:220px">{trisk["label"]}</span>'
                f'<span style="margin:0 0.5rem">{risk_badge(trisk["implementation"])}</span>'
                f'<span style="margin:0 0.5rem">{risk_badge(trisk["operational"])}</span>'
                f'<span>{risk_badge(trisk["regulatory"])}</span></div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            "<div style='font-size:0.72rem;color:#8899aa;margin-top:0.4rem'>"
            "Implementation | Operational | Regulatory</div>",
            unsafe_allow_html=True,
        )

        # Reasoning engine LRV context
        if r_result:
            pkey = r_result.preferred_archetype_key
            lrv  = r_result.lrv_by_archetype.get(pkey)
            if lrv:
                section_header("LRV Barrier Assessment (Reasoning Engine)", "🔬")
                for pathogen in ["protozoa", "bacteria", "virus"]:
                    req  = lrv.required.get(pathogen, 0)
                    hi   = lrv.total_credited_high.get(pathogen, 0)
                    ok   = hi >= req
                    c    = "#2ecc71" if ok else "#e74c3c"
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:0.3rem 0;'
                        f'border-bottom:1px solid #e2e8f0;font-size:0.82rem">'
                        f'<span style="color:#1a1a2e">{pathogen.title()}</span>'
                        f'<span style="color:#8899aa">Required: {req:.1f} log</span>'
                        f'<span style="color:{c};font-weight:600">Credited: {hi:.1f} log</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                da = lrv.disinfection_assessment
                if not da.get("protozoan_inactivation_barrier"):
                    error_box("No validated protozoan inactivation barrier — UV or ozone required.")

    # ══ TAB 8 — ENVIRONMENT ══════════════════════════════════════════════════
    with tabs[7]:
        section_header("Environmental Assessment", "🌿")
        ev = results.get("environmental", {})

        e1, e2, e3 = st.columns(3)
        with e1: render_kpi_card("Annual Energy CO₂", f"{ev.get('annual_energy_CO2_tonnes',0):.0f}", "t CO₂/yr")
        with e2: render_kpi_card("Annual Chemical CO₂", f"{ev.get('annual_chemical_CO2_tonnes',0):.0f}", "t CO₂/yr")
        with e3: render_kpi_card("Unit Carbon Intensity", f"{ev.get('unit_CO2_kg_per_kL',0):.3f}", "kg CO₂/kL")

        total_co2 = ev.get("total_annual_CO2_tonnes", 0)
        info_box(
            f"Total annual GHG: {total_co2:.0f} t CO₂-e/yr. "
            f"Emission factor: {ev.get('emission_factor_kg_CO2_kWh',0.79):.2f} kg CO₂/kWh (Australian grid Scope 2)."
        )

        if ev.get("residuals_considerations"):
            section_header("Residuals & Side-Streams", "♻️")
            for r in ev["residuals_considerations"]:
                warning_box(r)

        # Reasoning engine residuals context
        if r_result:
            pkey = r_result.preferred_archetype_key
            res_ass = r_result.residuals.archetype_assessments.get(pkey)
            if res_ass and res_ass.problem_transfer_flags:
                section_header("Problem Transfer Flags (Reasoning Engine)", "⚠️")
                for flag in res_ass.problem_transfer_flags:
                    error_box(flag)

    # ══ TAB 9 — REGULATORY ═══════════════════════════════════════════════════
    with tabs[8]:
        section_header("Regulatory Compliance — ADWG", "📋")
        reg = results.get("regulatory", {})

        overall_ok = reg.get("overall_compliant", False)
        if overall_ok:
            success_box("Treatment train meets assessed ADWG compliance criteria.")
        else:
            error_box("One or more ADWG compliance issues identified — review parameters below.")

        for issue in reg.get("issues", []):
            error_box(issue)

        for note in reg.get("regulatory_notes", []):
            warning_box(note)

        comp_items = reg.get("compliance_items", [])
        if comp_items:
            section_header("Compliance Checklist", "▸")
            for c in comp_items:
                ok  = c["compliant"]
                col = "#2ecc71" if ok else "#e74c3c"
                icon = "✓" if ok else "✗"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:0.3rem 0;border-bottom:1px solid #e2e8f0;font-size:0.82rem">'
                    f'<span style="color:{col}">{icon} {c["parameter"]}</span>'
                    f'<span style="color:#8899aa">{c["predicted"]} {c["unit"]}</span>'
                    f'<span style="color:#8899aa">ADWG: {c["guideline"]} {c["unit"]}</span>'
                    f'<span style="color:#8899aa;font-size:0.72rem">{c["type"]}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        info_box(f"Framework: {reg.get('framework','ADWG 2022')}")

    # ══ TAB 10 — FEASIBILITY ═════════════════════════════════════════════════
    with tabs[9]:
        section_header("Technology Feasibility Screening", "✅")
        feas = results.get("feasibility", {})
        for tech, fd in feas.items():
            ok  = fd.get("feasible", True)
            lbl = fd.get("label", tech)
            col = "#2ecc71" if ok else "#e74c3c"
            icon = "✓" if ok else "✗"
            flags = fd.get("flags", [])
            flags_html = "".join(
                f'<div style="font-size:0.72rem;color:#f39c12;margin-top:0.1rem">⚠ {f}</div>'
                for f in flags
            )
            st.markdown(f"""
                <div style="border:1px solid {'#1a3a2a' if ok else '#3a1a1a'};
                            border-radius:6px;padding:0.55rem 0.8rem;margin-bottom:0.3rem;
                            background:{'#0d2010' if ok else '#1a0a0a'}">
                    <span style="color:{col};font-weight:600">{icon} {lbl}</span>
                    {flags_html}
                </div>
            """, unsafe_allow_html=True)

    # ══ TAB 11 — SETTINGS ════════════════════════════════════════════════════
    # ══ TAB 10 — SOFTENING ANALYSIS ══════════════════════════════════════════
    with tabs[10]:
        from ..engine.softening_blend import calculate_softening_blend

        sw_local   = st.session_state.get("source_water", {})
        hardness   = float(sw_local.get("hardness_mg_l", 150))
        alkalinity = float(sw_local.get("alkalinity_mg_l", 80))
        tds_local  = float(sw_local.get("tds_mg_l", 300))
        flow_local = st.session_state.get("flow_ML_d", 10.0)
        sel_tech   = st.session_state.get("selected_technologies", [])

        softening_in_train = "chemical_softening" in sel_tech
        hardness_elevated  = hardness > 200
        show_softening     = softening_in_train or hardness_elevated

        if not show_softening:
            info_box(
                f"Softening analysis not triggered. Raw hardness is {hardness:.0f} mg/L "
                f"(threshold: >200 mg/L) and chemical softening is not in the selected train."
            )
        else:
            if softening_in_train:
                success_box("Chemical softening is in the selected treatment train.")
            else:
                warning_box(
                    f"Raw hardness {hardness:.0f} mg/L CaCO\u2083 is elevated. "
                    "Consider adding chemical softening to the treatment train."
                )

            section_header("Split-Stream Softening Analysis", "\U0001f9c2")
            st.markdown(
                "<div style=\'font-size:0.82rem;color:#555;margin-bottom:1rem\'>"
                "Split-stream softening treats a fraction of total flow through the softening "
                "stage, then blends with bypass to achieve target hardness and CCPP. "
                "CCPP target: \u22125 to 0 mg/L CaCO\u2083. "
                "Lime dose expressed as mg/L applied to the <em>softening stream</em>."
                "</div>",
                unsafe_allow_html=True
            )

            c1, c2, c3 = st.columns(3)
            with c1:
                product_ph = st.number_input(
                    "Product pH (post-recarbonation)",
                    min_value=7.0, max_value=8.5, value=7.8, step=0.1,
                    help="pH after CO\u2082 recarbonation. Target 7.8\u20138.2 for CCPP compliance."
                )
            with c2:
                carb_frac = st.slider(
                    "Carbonate hardness fraction", 0.40, 0.90, 0.70, 0.05,
                    help="Fraction of total hardness that is carbonate. High-alk sources: 0.65\u20130.75."
                )
            with c3:
                ca_frac = st.slider(
                    "Ca\u00b2\u207a fraction of hardness", 0.50, 0.90, 0.75, 0.05,
                    help="Fraction of hardness as calcium vs magnesium. Typical: 0.70\u20130.80."
                )

            blend = calculate_softening_blend(
                total_flow_ML_d     = flow_local,
                raw_hardness_mg_l   = hardness,
                raw_alkalinity_mg_l = alkalinity,
                raw_tds_mg_l        = tds_local,
                product_ph          = product_ph,
                carbonate_fraction  = carb_frac,
                ca_fraction         = ca_frac,
            )

            import pandas as pd
            rows = []
            for o in blend.options:
                rows.append({
                    "Fraction":          f"{o.softening_fraction_pct:.0f}%",
                    "Soft (ML/d)":       f"{o.softening_flow_ML_d:.1f}",
                    "Bypass (ML/d)":     f"{o.bypass_flow_ML_d:.1f}",
                    "Hardness (mg/L)":   f"{o.blended_hardness_mg_l:.0f}",
                    "Alkalinity (mg/L)": f"{o.blended_alkalinity_mg_l:.0f}",
                    "CCPP (mg/L)":       f"{o.ccpp_approx:+.1f}",
                    "H \u2713":          "\u2713" if o.hardness_compliant else "\u2717",
                    "CCPP \u2713":       "\u2713" if o.ccpp_compliant else "\u2717",
                    "Alk \u2713":        "\u2713" if o.alkalinity_compliant else "\u2717",
                    "All \u2713":        "\u2713\u2713\u2713" if o.fully_compliant else "\u2014",
                    "Lime (mg/L)":       f"{o.lime_dose_mg_l:.0f}",
                    "Soda (mg/L)":       f"{o.soda_ash_dose_mg_l:.0f}",
                    "Cost ($M/yr)":      f"{o.total_chemical_cost_AUD/1e6:.2f}",
                    "Sludge (t/d)":      f"{o.sludge_production_t_d:.1f}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            st.markdown("<br>", unsafe_allow_html=True)
            if blend.recommended_option:
                rec = blend.recommended_option
                success_box(
                    f"**Recommended: {rec.softening_fraction_pct:.0f}% split-stream** — "
                    f"{rec.softening_flow_ML_d:.1f} ML/d softened, "
                    f"{rec.bypass_flow_ML_d:.1f} ML/d bypass. "
                    f"Blended hardness {rec.blended_hardness_mg_l:.0f} mg/L | "
                    f"CCPP {rec.ccpp_approx:+.1f} mg/L | "
                    f"Lime {rec.lime_dose_mg_l:.0f} mg/L | "
                    f"Cost ${rec.total_chemical_cost_AUD/1e6:.2f}M/yr | "
                    f"Sludge {rec.sludge_production_t_d:.1f} t/d."
                )
            else:
                warning_box(
                    f"No split-stream fraction achieves all targets at pH {product_ph:.1f}. "
                    f"Full-flow softening (100%) required. Design softener for {flow_local:.1f} ML/d."
                )

            with st.expander("Engineering notes"):
                st.markdown("""
**Lime dose:** Carbonate hardness removal — Ca(OH)\u2082 + Ca(HCO\u2083)\u2082 \u2192 2CaCO\u2083\u2193 + 2H\u2082O.
Dose \u2248 hardness removed \u00d7 0.74 \u00d7 1.15 (stoichiometric excess).

**Soda ash:** Non-carbonate hardness — Na\u2082CO\u2083 + CaCl\u2082 \u2192 CaCO\u2083\u2193 + 2NaCl.
Dose \u2248 non-carbonate hardness removed \u00d7 1.06.

**Recarbonation:** CO\u2082 dosed post-softening to lower pH from ~10.5 to product target.
Restores alkalinity and drives CCPP into \u22125 to 0 range.

**CCPP:** Concept-stage LSI approximation (\u00b13 mg/L). Full CCPP requires ionic strength correction.

**Sludge:** Predominantly CaCO\u2083 \u2014 dewaters to >35% DS. Higher density than coagulation sludge.
                """)

    with tabs[11]:
        section_header("Analysis Parameters", "⚙️")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.session_state["analysis_period"] = st.number_input(
                "Analysis Period (years)", 10, 50,
                value=int(st.session_state.get("analysis_period", LIFECYCLE_DEFAULTS["analysis_period_years"])),
                step=5, key="set_analysis_period",
            )
            st.session_state["discount_rate"] = st.number_input(
                "Discount Rate (%)", 1.0, 15.0,
                value=float(st.session_state.get("discount_rate", LIFECYCLE_DEFAULTS["discount_rate_pct"])),
                step=0.5, format="%.1f", key="set_discount",
            )
            st.session_state["opex_escalation"] = st.number_input(
                "OPEX Escalation (%/yr)", 0.0, 8.0,
                value=float(st.session_state.get("opex_escalation", LIFECYCLE_DEFAULTS["opex_escalation_pct"])),
                step=0.5, format="%.1f", key="set_escalation",
            )
        with col_s2:
            st.session_state["capex_contingency"] = st.number_input(
                "CAPEX Contingency (%)", 0.0, 50.0,
                value=float(st.session_state.get("capex_contingency", LIFECYCLE_DEFAULTS["capex_contingency_pct"])),
                step=5.0, format="%.0f", key="set_contingency",
            )
            st.session_state["electricity_cost"] = st.number_input(
                "Electricity Cost (AUD/kWh)", 0.05, 0.50,
                value=float(st.session_state.get("electricity_cost", 0.12)),
                step=0.01, format="%.3f", key="set_elec",
            )

        section_header("MCA Weights", "▸")
        wts = dict(st.session_state.get("mca_weights", MCA_DEFAULT_WEIGHTS))
        w_cols = st.columns(3)
        wt_keys = list(MCA_DEFAULT_WEIGHTS.keys())
        for i, wk in enumerate(wt_keys):
            with w_cols[i % 3]:
                wts[wk] = st.slider(
                    wk.replace("_", " ").title(),
                    0.0, 1.0,
                    value=float(wts.get(wk, MCA_DEFAULT_WEIGHTS[wk])),
                    step=0.05, key=f"wt_{wk}",
                )
        total_wt = sum(wts.values())
        if abs(total_wt - 1.0) > 0.01:
            warning_box(f"MCA weights sum to {total_wt:.2f} — they should sum to 1.0. Results will be scaled.")
        st.session_state["mca_weights"] = wts

        if st.button("↺ Re-run Analysis with Updated Settings", type="primary"):
            st.rerun()

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        if st.button("← Treatment Philosophy", use_container_width=True):
            st.session_state["current_page"] = "treatment_philosophy"
            st.rerun()
    with right:
        if st.button("Export Report →", type="primary", use_container_width=True):
            st.session_state["current_page"] = "report"
            st.rerun()
