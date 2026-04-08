"""page_02_effluent_quality.py"""
import streamlit as st
from ..ui_helpers import section_header, info_box, warning_box
from ..engine import EFFLUENT_PRESETS, EffluentInputs, run_full_analysis, CLASSES


def render_effluent_quality():
    st.markdown("## Effluent Quality")
    st.markdown(
        "Enter WaterPoint final effluent quality. Provide median, P95, and P99 values "
        "where available — the engine uses P99 for failure mode and resilience assessment."
    )

    # Pre-fill from preset
    preset_key = st.session_state.get("pp_effluent_type", "cas")
    preset = EFFLUENT_PRESETS.get(preset_key, EFFLUENT_PRESETS["cas"])

    def _default(key, fallback):
        return float(st.session_state.get(f"pp_{key}", fallback))

    # Physical
    st.markdown("---")
    section_header("Physical", "📊")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Turbidity (NTU)**")
        tc1, tc2, tc3 = st.columns(3)
        tc1.number_input("Median", min_value=0.0, value=_default("turb_med", preset["turb_med"]), step=0.1, key="pp_turb_med")
        tc2.number_input("P95",    min_value=0.0, value=_default("turb_p95", preset["turb_p95"]), step=0.1, key="pp_turb_p95")
        tc3.number_input("P99",    min_value=0.0, value=_default("turb_p99", preset["turb_p99"]), step=0.1, key="pp_turb_p99")
    with col2:
        st.markdown("**TSS (mg/L)**")
        tc1, tc2, tc3 = st.columns(3)
        tc1.number_input("Median", min_value=0.0, value=_default("tss_med", preset["tss_med"]), step=0.5, key="pp_tss_med")
        tc2.number_input("P95",    min_value=0.0, value=_default("tss_p95", preset["tss_p95"]), step=0.5, key="pp_tss_p95")
        tc3.number_input("P99",    min_value=0.0, value=_default("tss_p99", preset["tss_p99"]), step=0.5, key="pp_tss_p99")

    # Organic
    st.markdown("---")
    section_header("Organic", "🧪")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**DOC (mg/L)**")
        dc1, dc2, dc3 = st.columns(3)
        dc1.number_input("Median", min_value=0.0, value=_default("doc_med", preset["doc_med"]), step=0.5, key="pp_doc_med")
        dc2.number_input("P95",    min_value=0.0, value=_default("doc_p95", preset["doc_p95"]), step=0.5, key="pp_doc_p95")
        dc3.number_input("P99",    min_value=0.0, value=_default("doc_p99", preset["doc_p99"]), step=0.5, key="pp_doc_p99")
    with col2:
        st.markdown("**UV254 (cm⁻¹)**")
        uc1, uc2, uc3 = st.columns(3)
        uc1.number_input("Median", min_value=0.0, value=_default("uv254_med", preset["uv254_med"]), step=0.01, format="%.2f", key="pp_uv254_med")
        uc2.number_input("P95",    min_value=0.0, value=_default("uv254_p95", preset["uv254_p95"]), step=0.01, format="%.2f", key="pp_uv254_p95")
        uc3.number_input("P99",    min_value=0.0, value=_default("uv254_p99", preset["uv254_p99"]), step=0.01, format="%.2f", key="pp_uv254_p99")

    col1, col2 = st.columns(2)
    with col1:
        st.number_input("AOC / BDOC (µg/L) — optional", min_value=0.0,
                        value=_default("aoc", preset["aoc"]), step=10.0, key="pp_aoc")

    # Nutrients
    st.markdown("---")
    section_header("Nutrients", "🌿")
    col1, col2 = st.columns(2)
    with col1:
        st.number_input("NH₃-N (mg/L)", min_value=0.0, value=_default("nh3", preset["nh3"]), step=1.0, key="pp_nh3")
    with col2:
        st.number_input("NO₃-N (mg/L)", min_value=0.0, value=_default("no3", preset["no3"]), step=1.0, key="pp_no3")

    if st.session_state.get("pp_no3", preset["no3"]) > 11.3:
        warning_box("NO₃-N exceeds drinking water guideline (11.3 mg/L) — RO required for PRW classification.")

    # Microbial
    st.markdown("---")
    section_header("Microbial indicators", "🦠")
    st.markdown("**E. coli (cfu/100mL)**")
    mc1, mc2, mc3 = st.columns(3)
    mc1.number_input("Median", min_value=0.0, value=_default("ecoli_med", preset["ecoli_med"]), step=100.0, key="pp_ecoli_med")
    mc2.number_input("P95",    min_value=0.0, value=_default("ecoli_p95", preset["ecoli_p95"]), step=1000.0, key="pp_ecoli_p95")
    mc3.number_input("P99",    min_value=0.0, value=_default("ecoli_p99", preset["ecoli_p99"]), step=5000.0, key="pp_ecoli_p99")

    # Chemical
    st.markdown("---")
    section_header("Chemical contaminants", "⚗️")
    col1, col2 = st.columns(2)
    with col1:
        st.number_input("PFAS sum (ng/L)", min_value=0.0, value=_default("pfas", preset["pfas"]), step=5.0, key="pp_pfas")
    with col2:
        st.number_input("Conductivity (µS/cm)", min_value=0.0, value=_default("cond", preset["cond"]), step=10.0, key="pp_cond")

    col1, col2 = st.columns(2)
    with col1:
        st.selectbox(
            "CEC / PPCP indicator risk",
            options=["low", "medium", "high"],
            format_func=lambda x: x.capitalize(),
            index=1,
            key="pp_cec_risk",
        )
    with col2:
        st.selectbox(
            "Nitrosamine precursor risk",
            options=["low", "medium", "high"],
            format_func=lambda x: x.capitalize(),
            index=1,
            key="pp_nitrosamine_risk",
        )

    st.markdown("---")
    if st.button("▶ Run PurePoint Assessment", type="primary"):
        _run_assessment()


def _run_assessment():
    ss = st.session_state
    target_classes = []
    if ss.get("pp_class_C", True):    target_classes.append("C")
    if ss.get("pp_class_A", True):    target_classes.append("A")
    if ss.get("pp_class_Aplus", True): target_classes.append("A+")
    if ss.get("pp_class_PRW", True):  target_classes.append("PRW")
    if not target_classes:
        target_classes = CLASSES

    inputs = EffluentInputs(
        effluent_type=ss.get("pp_effluent_type", "cas"),
        project_name=ss.get("pp_project_name", ""),
        plant_name=ss.get("pp_plant_name", ""),
        target_classes=target_classes,
        notes=ss.get("pp_notes", ""),
        turb_med=ss.get("pp_turb_med", 2.0),
        turb_p95=ss.get("pp_turb_p95", 6.0),
        turb_p99=ss.get("pp_turb_p99", 12.0),
        tss_med=ss.get("pp_tss_med", 5.0),
        tss_p95=ss.get("pp_tss_p95", 12.0),
        tss_p99=ss.get("pp_tss_p99", 20.0),
        doc_med=ss.get("pp_doc_med", 10.0),
        doc_p95=ss.get("pp_doc_p95", 16.0),
        doc_p99=ss.get("pp_doc_p99", 22.0),
        uv254_med=ss.get("pp_uv254_med", 0.15),
        uv254_p95=ss.get("pp_uv254_p95", 0.25),
        uv254_p99=ss.get("pp_uv254_p99", 0.35),
        aoc=ss.get("pp_aoc", 300.0),
        nh3=ss.get("pp_nh3", 25.0),
        no3=ss.get("pp_no3", 8.0),
        ecoli_med=ss.get("pp_ecoli_med", 5000.0),
        ecoli_p95=ss.get("pp_ecoli_p95", 50000.0),
        ecoli_p99=ss.get("pp_ecoli_p99", 200000.0),
        pfas=ss.get("pp_pfas", 50.0),
        cond=ss.get("pp_cond", 900.0),
        cec_risk=ss.get("pp_cec_risk", "medium"),
        nitrosamine_risk=ss.get("pp_nitrosamine_risk", "medium"),
    )

    with st.spinner("Running PurePoint assessment..."):
        result = run_full_analysis(inputs)

    st.session_state["purepoint_result"] = result
    st.session_state["pp_page"] = "class_assessment"
    st.rerun()
