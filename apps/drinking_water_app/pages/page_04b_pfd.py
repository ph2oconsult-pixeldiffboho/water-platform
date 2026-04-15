"""
apps/drinking_water_app/pages/page_04b_pfd.py
AquaPoint — Treatment Train Options + Process Flow Diagram

Reasoning engine generates up to 3 viable treatment train options.
User selects one. PFD is generated automatically from that selection.
Selected train is written back to session state for the results page.
"""
import streamlit as st
from ..engine.constants import TECHNOLOGIES
from ..engine.reasoning import SourceWaterInputs, run_reasoning_engine
from ..engine import run_full_analysis

# ── Canonical technology trains per archetype ─────────────────────────────────
ARCHETYPE_TRAINS = {
    "A": ["coagulation_flocculation", "rapid_gravity_filtration",
          "uv_disinfection", "chlorination"],
    "B": ["screening", "coagulation_flocculation", "sedimentation",
          "rapid_gravity_filtration", "uv_disinfection", "chlorination", "sludge_thickening"],
    "C": ["screening", "actiflo_carb",
          "rapid_gravity_filtration", "uv_disinfection", "chlorination", "sludge_thickening"],
    "D": ["screening", "coagulation_flocculation", "daf",
          "rapid_gravity_filtration", "uv_disinfection", "chlorination", "sludge_thickening"],
    "E": ["screening", "coagulation_flocculation", "sedimentation",
          "rapid_gravity_filtration", "bac", "uv_disinfection", "chlorination", "sludge_thickening"],
    "F": ["coagulation_flocculation", "chemical_softening", "sedimentation",
          "rapid_gravity_filtration", "uv_disinfection", "chlorination", "sludge_thickening"],
    "G": ["screening", "coagulation_flocculation", "sedimentation",
          "rapid_gravity_filtration", "ozonation", "bac",
          "uv_disinfection", "chlorination", "sludge_thickening"],
    "H": ["screening", "coagulation_flocculation", "mf_uf", "ro",
          "uv_disinfection", "chloramination", "brine_management"],
    "I": ["screening", "coagulation_flocculation", "sedimentation",
          "rapid_gravity_filtration", "gac", "uv_disinfection", "chlorination", "sludge_thickening"],
}

# ── Chemical injection per technology ─────────────────────────────────────────
CHEM_INJECTION_MAP = {
    "coagulation_flocculation": ["ferric_chloride", "alum", "lime", "caustic_soda"],
    "daf":                      ["ferric_chloride", "alum", "polymer"],
    "sedimentation":            ["polymer"],
    "mf_uf":                    ["caustic_soda"],
    "nf":                       ["antiscalant", "acid"],
    "ro":                       ["antiscalant", "acid"],
    "aop":                      ["h2o2"],
    "uv_disinfection":          ["h2o2"],
    "chlorination":             ["naocl", "chlorine"],
    "chloramination":           ["naocl", "ammonia"],
    "actiflo_carb":             ["ferric_chloride", "alum", "polymer"],
    "chemical_softening":       ["lime", "soda_ash"],
    "pre_filter_chlorination":  ["naocl"],
    "kmno4_pre_oxidation":      ["kmno4"],
    "polydadmac":               ["polydadmac"],
}

CHEM_SHORT = {
    "ferric_chloride": "FeCl₃", "alum": "Alum", "lime": "Lime",
    "soda_ash": "Na₂CO₃", "caustic_soda": "NaOH", "co2": "CO₂",
    "polymer": "Poly", "antiscalant": "Antiscalant", "acid": "H₂SO₄",
    "naocl": "NaOCl", "chlorine": "Cl₂", "ammonia": "NH₃", "h2o2": "H₂O₂",
    "kmno4": "KMnO₄", "polydadmac": "pDADMAC",
}

SHORT_LABELS = {
    "screening": "Screens", "coagulation_flocculation": "Coag/Floc",
    "daf": "DAF", "sedimentation": "Densadeg/\nActiflo", "rapid_gravity_filtration": "RGF",
    "slow_sand_filtration": "SSF", "mf_uf": "MF/UF", "nf": "NF", "ro": "RO",
    "ozonation": "Ozone", "bac": "BAC", "gac": "GAC", "aop": "UV/AOP",
    "uv_disinfection": "UV", "chlorination": "Cl₂", "chloramination": "NH₂Cl",
    "actiflo_carb": "Actiflo\nCarb",
    "chemical_softening": "Lime\nSoftening", "sludge_thickening": "Sludge\nThickener",
    "pre_filter_chlorination": "Pre-Filt\nCl₂",
    "kmno4_pre_oxidation": "KMnO₄\nPre-Ox", "polydadmac": "pDADMAC",
    "brine_management": "Brine\nMgmt",
}

RESIDUALS_TECHS = {
    "sedimentation", "daf", "coagulation_flocculation",
    "rapid_gravity_filtration", "slow_sand_filtration",
    "mf_uf", "chemical_softening", "sludge_thickening",
    "actiflo_carb",
}

SCORE_LABELS = {
    "capex": "CAPEX", "opex": "OPEX", "energy_demand": "Energy",
    "operability": "Operability", "footprint": "Footprint",
    "event_response": "Event Response", "variability_robustness": "Variability",
    "barrier_redundancy": "Barrier Redundancy", "delivery_risk": "Delivery Risk",
}


# ── SVG PFD generator ─────────────────────────────────────────────────────────
def build_pfd_svg(process_train, sludge_train, chemicals, source_water,
                  treated_water, flow_ML_d, detailed=False):

    BOX_W = 88; BOX_H = 50; GAP = 32; TOP = 145
    CHEM_ZONE = 85; SLU_Y = TOP + BOX_H + 70; MARGIN = 16; SW_W = 108

    n = len(process_train)
    total_w = MARGIN + SW_W + GAP + n * (BOX_W + GAP) + SW_W + MARGIN
    total_h = SLU_Y + BOX_H + 72

    C_BOX = "#1a56a0"; C_SLU = "#2d6a4f"; C_ARR = "#4a9eff"
    C_CHEM = "#e67e22"; C_TXT = "#ffffff"; C_SUB = "#cbd5e1"
    C_BG = "#f8fafc"; C_SRC = "#0f3460"; C_PRD = "#1a6b3a"; C_BDR = "#cbd5e1"

    flow_ls = flow_ML_d * 1e6 / 86400
    flow_m3h = flow_ML_d * 1e3 / 24

    s = []
    s.append(f'<svg viewBox="0 0 {total_w} {total_h}" xmlns="http://www.w3.org/2000/svg" '
             f'style="background:{C_BG};border-radius:8px;border:1px solid {C_BDR};'
             f'font-family:Arial,sans-serif;width:100%">')
    s.append('''<defs>
  <marker id="arr" markerWidth="8" markerHeight="6" refX="6" refY="3" orient="auto">
    <polygon points="0 0,8 3,0 6" fill="#4a9eff"/></marker>
  <marker id="arrc" markerWidth="6" markerHeight="5" refX="5" refY="2.5" orient="auto">
    <polygon points="0 0,6 2.5,0 5" fill="#e67e22"/></marker>
  <marker id="arrs" markerWidth="6" markerHeight="5" refX="5" refY="2.5" orient="auto">
    <polygon points="0 0,6 2.5,0 5" fill="#999"/></marker>
</defs>''')

    # Title
    s.append(f'<text x="{total_w//2}" y="20" text-anchor="middle" font-size="12" '
             f'font-weight="bold" fill="#1a3a5c">Process Flow Diagram'
             f'{" — Detailed" if detailed else ""}</text>')
    s.append(f'<text x="{total_w//2}" y="34" text-anchor="middle" font-size="9" fill="#64748b">'
             f'{flow_ML_d:.1f} ML/d  |  {flow_ls:.0f} L/s  |  {flow_m3h:.0f} m³/h</text>')

    def bx(i): return MARGIN + SW_W + GAP + i * (BOX_W + GAP)
    def bcx(i): return bx(i) + BOX_W // 2

    # Source water box
    sx = MARGIN; sy = TOP - BOX_H // 2 - 10
    s.append(f'<rect x="{sx}" y="{sy}" width="{SW_W}" height="{BOX_H+22}" rx="5" fill="{C_SRC}"/>')
    s.append(f'<text x="{sx+SW_W//2}" y="{sy+13}" text-anchor="middle" font-size="8" '
             f'font-weight="bold" fill="{C_TXT}">RAW WATER</text>')
    if detailed:
        items = [
            f"Turb: {source_water.get('turbidity_ntu',0):.0f} NTU",
            f"TOC:  {source_water.get('toc_mg_l',0):.1f} mg/L",
            f"Fe:   {source_water.get('iron_mg_l',0):.2f} mg/L",
            f"Mn:   {source_water.get('manganese_mg_l',0):.2f} mg/L",
            f"Colour: {source_water.get('colour_hu',0):.0f} HU",
        ]
        for idx, item in enumerate(items):
            s.append(f'<text x="{sx+5}" y="{sy+24+idx*10}" font-size="7.5" fill="{C_SUB}">'
                     f'{item}</text>')
    # Arrow out of source box
    s.append(f'<line x1="{sx+SW_W}" y1="{TOP}" x2="{bx(0)-4}" y2="{TOP}" '
             f'stroke="{C_ARR}" stroke-width="2" marker-end="url(#arr)"/>')

    # Process boxes
    for i, tech in enumerate(process_train):
        x = bx(i); y = TOP - BOX_H // 2
        lbl = SHORT_LABELS.get(tech, tech.replace("_", " "))
        s.append(f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" rx="5" fill="{C_BOX}"/>')
        lines = lbl.split("\n")
        base_y = y + BOX_H // 2 - (len(lines) - 1) * 6
        for li, ll in enumerate(lines):
            s.append(f'<text x="{x+BOX_W//2}" y="{base_y+li*13}" text-anchor="middle" '
                     f'font-size="9" font-weight="bold" fill="{C_TXT}">{ll}</text>')

        # Arrow to next
        if i < n - 1:
            s.append(f'<line x1="{x+BOX_W}" y1="{TOP}" x2="{bx(i+1)-4}" y2="{TOP}" '
                     f'stroke="{C_ARR}" stroke-width="2" marker-end="url(#arr)"/>')

        # Chemical injections
        chem_keys = CHEM_INJECTION_MAP.get(tech, [])
        active = [(k, chemicals[k]) for k in chem_keys if k in chemicals]
        for ci, (ck, cv) in enumerate(active):
            cx = x + 16 + ci * 24
            cy_top = y - CHEM_ZONE + 18
            cy_bot = y - 3
            s.append(f'<line x1="{cx}" y1="{cy_top}" x2="{cx}" y2="{cy_bot}" '
                     f'stroke="{C_CHEM}" stroke-width="1.5" stroke-dasharray="3,2" '
                     f'marker-end="url(#arrc)"/>')
            lbl_c = CHEM_SHORT.get(ck, ck[:6])
            s.append(f'<text x="{cx}" y="{cy_top-3}" text-anchor="middle" '
                     f'font-size="7.5" fill="{C_CHEM}">{lbl_c}</text>')
            if detailed:
                dose = cv.get("dose_mg_L", 0)
                s.append(f'<text x="{cx}" y="{cy_top+9}" text-anchor="middle" '
                         f'font-size="7" fill="{C_CHEM}">{dose:.0f}mg/L</text>')

        # Sludge arrow down
        if tech in RESIDUALS_TECHS and sludge_train:
            s.append(f'<line x1="{bcx(i)}" y1="{y+BOX_H+2}" x2="{bcx(i)}" '
                     f'y2="{SLU_Y-BOX_H//2-3}" stroke="#aaa" stroke-width="1.5" '
                     f'stroke-dasharray="3,3" marker-end="url(#arrs)"/>')

    # Product water box
    px = bx(n-1) + BOX_W + GAP; py = TOP - BOX_H // 2 - 10
    s.append(f'<line x1="{bx(n-1)+BOX_W}" y1="{TOP}" x2="{px-4}" y2="{TOP}" '
             f'stroke="{C_ARR}" stroke-width="2" marker-end="url(#arr)"/>')
    s.append(f'<rect x="{px}" y="{py}" width="{SW_W}" height="{BOX_H+22}" rx="5" fill="{C_PRD}"/>')
    s.append(f'<text x="{px+SW_W//2}" y="{py+13}" text-anchor="middle" font-size="8" '
             f'font-weight="bold" fill="{C_TXT}">PRODUCT WATER</text>')
    if detailed and treated_water:
        items = [
            f"Turb: {treated_water.get('turbidity_ntu',0):.3f} NTU",
            f"TOC:  {treated_water.get('toc_mg_l',0):.2f} mg/L",
            f"Fe:   {treated_water.get('iron_mg_l',0):.3f} mg/L",
            f"Mn:   {treated_water.get('manganese_mg_l',0):.3f} mg/L",
            f"Colour: {treated_water.get('colour_hu',0):.1f} HU",
        ]
        for idx, item in enumerate(items):
            s.append(f'<text x="{px+5}" y="{py+24+idx*10}" font-size="7.5" fill="{C_SUB}">'
                     f'{item}</text>')

    # Sludge train
    if sludge_train:
        slx = bx(0); sly = SLU_Y - BOX_H // 2
        s.append(f'<rect x="{slx}" y="{sly}" width="{BOX_W}" height="{BOX_H}" '
                 f'rx="5" fill="{C_SLU}"/>')
        s.append(f'<text x="{slx+BOX_W//2}" y="{sly+BOX_H//2-4}" text-anchor="middle" '
                 f'font-size="9" font-weight="bold" fill="{C_TXT}">Sludge</text>')
        s.append(f'<text x="{slx+BOX_W//2}" y="{sly+BOX_H//2+8}" text-anchor="middle" '
                 f'font-size="9" font-weight="bold" fill="{C_TXT}">Thickener</text>')
        s.append(f'<line x1="{slx+BOX_W}" y1="{SLU_Y}" x2="{slx+BOX_W+70}" y2="{SLU_Y}" '
                 f'stroke="#999" stroke-width="1.5" marker-end="url(#arrs)"/>')
        s.append(f'<text x="{slx+BOX_W+8}" y="{SLU_Y-5}" font-size="8" fill="#888">'
                 f'To disposal</text>')

    # Legend
    leg_y = total_h - 16
    for li, (col, lbl) in enumerate([(C_ARR, "Process stream"),
                                      (C_CHEM, "Chemical dosing"),
                                      ("#aaa", "Sludge / residuals")]):
        lx = MARGIN + li * 170
        s.append(f'<line x1="{lx}" y1="{leg_y}" x2="{lx+18}" y2="{leg_y}" '
                 f'stroke="{col}" stroke-width="2"/>')
        s.append(f'<text x="{lx+22}" y="{leg_y+4}" font-size="8" fill="#64748b">{lbl}</text>')

    s.append('</svg>')
    return "\n".join(s)


# ── Score bar renderer ────────────────────────────────────────────────────────
def _score_bar(label, value, max_val=10, width=120):
    pct = int(value / max_val * width)
    colour = "#2ecc71" if value >= 7 else "#f39c12" if value >= 5 else "#e74c3c"
    return (f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
            f'<span style="font-size:0.72rem;color:#555;width:110px">{label}</span>'
            f'<div style="background:#e2e8f0;border-radius:3px;width:{width}px;height:8px">'
            f'<div style="background:{colour};border-radius:3px;width:{pct}px;height:8px"></div>'
            f'</div>'
            f'<span style="font-size:0.72rem;color:#888">{value}/10</span>'
            f'</div>')


# ── Build reasoning inputs from session state ─────────────────────────────────
def _build_reasoning_inputs():
    sw = st.session_state.get("source_water", {})
    plant_type = st.session_state.get("plant_type", "conventional")
    flow = st.session_state.get("flow_ML_d", 10.0)

    source_map = {"conventional": "river", "membrane": "river",
                  "groundwater": "groundwater", "desalination": "desalination"}

    return SourceWaterInputs(
        source_type         = source_map.get(plant_type, "river"),
        turbidity_median_ntu= sw.get("turbidity_ntu", 5.0),
        turbidity_p95_ntu   = sw.get("turbidity_p95_ntu", sw.get("turbidity_ntu", 5.0) * 3),
        turbidity_p99_ntu   = sw.get("turbidity_p99_ntu", sw.get("turbidity_ntu", 5.0) * 6),
        toc_median_mg_l     = sw.get("toc_mg_l", 4.0),
        toc_p95_mg_l        = sw.get("toc_p95_mg_l", sw.get("toc_mg_l", 4.0) * 1.5),
        colour_median_hu    = sw.get("colour_hu", 10.0),
        algae_risk          = sw.get("algae_risk", "low"),
        algal_cells_per_ml  = float(sw.get("algal_cells_ml", 0)),
        catchment_risk      = sw.get("catchment_risk", "low"),
        variability_class   = sw.get("variability_class", "low"),
        pfas_detected       = sw.get("pfas_detected", False),
        pfas_concentration_ng_l = sw.get("pfas_concentration_ng_l", 0.0),
        hardness_median_mg_l    = sw.get("hardness_mg_l", 100.0),
        alkalinity_median_mg_l  = sw.get("alkalinity_mg_l", 60.0),
        iron_median_mg_l    = sw.get("iron_mg_l", 0.1),
        manganese_median_mg_l   = sw.get("manganese_mg_l", 0.02),
        arsenic_ug_l        = sw.get("arsenic_ug_l", 0.0),
        tds_median_mg_l     = sw.get("tds_mg_l", 300.0),
        ph_median           = sw.get("ph_median", 7.5),
        ph_min              = sw.get("ph_min", 7.0),
        pathogen_lrv_required_protozoa = 4.0,
        pathogen_lrv_required_bacteria = 6.0,
        pathogen_lrv_required_virus    = 6.0,
        design_flow_ML_d    = flow,
        is_retrofit         = sw.get("is_retrofit", False),
        land_constrained    = sw.get("land_constrained", False),
        remote_operation    = sw.get("remote_operation", False),
        treatment_objective = "potable",
    )


# ── Main render ───────────────────────────────────────────────────────────────
def render():
    from ..ui_helpers import section_header, info_box, warning_box

    st.markdown("## 🔀 Treatment Train Options & Process Flow Diagram")
    st.markdown("*Reasoning engine evaluates all viable archetypes. Select one to generate the PFD.*")
    st.divider()

    source_water = st.session_state.get("source_water", {})
    plant_type   = st.session_state.get("plant_type", "conventional")
    flow         = st.session_state.get("flow_ML_d", 10.0)
    coagulant    = st.session_state.get("coagulant", "alum")

    if not source_water:
        warning_box("No source water data — complete Source Water Quality first.")
        if st.button("← Source Water Quality"):
            st.session_state["current_page"] = "source_water"
            st.rerun()
        return

    # ── Run reasoning engine ─────────────────────────────────────────────────
    with st.spinner("Evaluating treatment train options…"):
        try:
            ri = _build_reasoning_inputs()
            reasoning = run_reasoning_engine(ri)
        except Exception as e:
            st.error(f"Reasoning engine error: {e}")
            return

    preferred_key = reasoning.preferred_archetype_key
    viable_scores = sorted(
        [s for s in reasoning.scores if s.tier1_pass],
        key=lambda s: s.overall_score, reverse=True
    )[:3]  # top 3 options

    if not viable_scores:
        warning_box("No viable archetypes found for this source water profile.")
        return

    # ── Option cards ─────────────────────────────────────────────────────────
    section_header("Viable Treatment Train Options", "⚙️")
    st.markdown(f"<div style='font-size:0.82rem;color:#555;margin-bottom:1rem'>"
                f"Showing top {len(viable_scores)} options ranked by overall score. "
                f"The reasoning engine prefers <b>Archetype {preferred_key}</b>.</div>",
                unsafe_allow_html=True)

    # Selected archetype state
    if "pfd_selected_archetype" not in st.session_state:
        st.session_state["pfd_selected_archetype"] = preferred_key

    cols = st.columns(len(viable_scores))

    for ci, score in enumerate(viable_scores):
        ak = score.archetype_key
        lrv = reasoning.lrv_by_archetype.get(ak)
        train = ARCHETYPE_TRAINS.get(ak, [])
        is_preferred = (ak == preferred_key)
        is_selected  = (ak == st.session_state["pfd_selected_archetype"])

        border = "#1a56a0" if is_selected else "#4a9eff" if is_preferred else "#cbd5e1"
        bg     = "#eff6ff" if is_selected else "#f8fafc"
        badge  = "🏆 Recommended" if is_preferred else f"Option {ci+1}"

        with cols[ci]:
            st.markdown(f"""
                <div style="border:2px solid {border};border-radius:8px;
                            padding:0.8rem;background:{bg};min-height:280px">
                    <div style="font-size:0.7rem;color:#888;margin-bottom:0.3rem">{badge}</div>
                    <div style="font-size:1rem;font-weight:700;color:#1a3a5c;margin-bottom:0.1rem">
                        Archetype {ak}</div>
                    <div style="font-size:0.82rem;font-weight:600;color:#1a56a0;margin-bottom:0.6rem">
                        {score.archetype_label}</div>
                    <div style="font-size:0.72rem;color:#555;margin-bottom:0.5rem">
                        <b>Score: {score.overall_score:.1f}/10</b></div>
                    {_score_bar("CAPEX", score.capex)}
                    {_score_bar("OPEX", score.opex)}
                    {_score_bar("Operability", score.operability)}
                    {_score_bar("Event Response", score.event_response)}
                    {_score_bar("Barrier Redundancy", score.barrier_redundancy)}
                    <div style="font-size:0.7rem;color:#555;margin-top:0.5rem">
                        <b>LRV:</b> P {lrv.total_credited_high.get('protozoa',0):.0f} |
                        B {lrv.total_credited_high.get('bacteria',0):.0f} |
                        V {lrv.total_credited_high.get('virus',0):.0f} log
                        {"✓" if lrv and all(lrv.meets_target_high.values()) else "✗"}
                    </div>
                    <div style="font-size:0.7rem;color:#555;margin-top:0.3rem">
                        <b>Train:</b> {" → ".join(SHORT_LABELS.get(t,t) for t in train
                                                   if t not in ("sludge_thickening","brine_management"))}
                    </div>
                </div>
            """, unsafe_allow_html=True)

            label = "✓ Selected" if is_selected else f"Select Archetype {ak}"
            if st.button(label, key=f"sel_{ak}", use_container_width=True,
                         type="primary" if is_selected else "secondary"):
                st.session_state["pfd_selected_archetype"] = ak
                # Update selected_technologies from canonical train
                st.session_state["selected_technologies"] = ARCHETYPE_TRAINS.get(ak, [])
                st.rerun()

    # ── PFD for selected archetype ────────────────────────────────────────────
    sel_key   = st.session_state["pfd_selected_archetype"]
    sel_train = ARCHETYPE_TRAINS.get(sel_key, [])

    # Inject chemical_softening into train when hardness is elevated
    # Position: after primary clarification (DAF/sedimentation), before filtration
    _sw_hard = float(source_water.get('hardness_mg_l', 0))
    _softening_required = _sw_hard > 200 and 'chemical_softening' not in sel_train
    if _softening_required:
        _clarif_techs = ('daf', 'sedimentation', 'coagulation_flocculation')
        _insert_after = max(
            (i for i, t in enumerate(sel_train) if t in _clarif_techs),
            default=-1
        )
        if _insert_after >= 0:
            sel_train = list(sel_train)
            sel_train.insert(_insert_after + 1, 'chemical_softening')
        if 'sludge_thickening' not in sel_train:
            sel_train.append('sludge_thickening')

    # Inject kmno4_pre_oxidation into train when manganese is elevated (>0.1 mg/L)
    # Position: before coagulation — pre-oxidation must precede coagulant
    _mn = float(source_water.get('manganese_mg_l', 0))
    _kmno4_required = _mn > 0.1 and 'kmno4_pre_oxidation' not in sel_train
    if _kmno4_required:
        sel_train = list(sel_train)
        # Insert before coagulation_flocculation
        _coag_idx = next(
            (i for i, t in enumerate(sel_train) if t == 'coagulation_flocculation'),
            0
        )
        sel_train.insert(_coag_idx, 'kmno4_pre_oxidation')

    # Inject polydadmac as coagulant aid when ballasted/high-rate clarifier is in the train
    # Densadeg (sedimentation), Actiflo Carb, DAF — all benefit from pDADMAC
    # Prospect PPTP: FeCl3 + pDADMAC standard for Densadeg
    _ballasted = any(t in sel_train for t in ('sedimentation', 'actiflo_carb', 'daf'))
    _polydadmac_required = _ballasted and 'polydadmac' not in sel_train
    if _polydadmac_required:
        sel_train = list(sel_train)
        sel_train.append('polydadmac')
        # Note: polydadmac appears as a chemical injection arrow only,
        # not as a standalone process box (no SHORT_LABELS box drawn for it)


    process_train = [t for t in sel_train if t not in ("sludge_thickening", "brine_management")]
    sludge_train  = [t for t in sel_train if t in ("sludge_thickening", "brine_management")]

    st.markdown("<br>", unsafe_allow_html=True)
    section_header(f"Process Flow Diagram — Archetype {sel_key}", "📐")

    # Run analysis for selected train to get chemicals and treated quality
    with st.spinner("Generating PFD…"):
        try:
            res = run_full_analysis({
                'plant_type': plant_type,
                'flow_ML_d': flow,
                'coagulant': coagulant,
                'source_water': source_water,
                'selected_technologies': sel_train,
                'lifecycle_params': {},
            })
            chemicals     = res['chemical_use']['chemicals']
            treated_water = res['treatment_performance']['predicted_quality']
            # Write back results
            st.session_state["last_results"] = res
            st.session_state["selected_technologies"] = sel_train
        except Exception as e:
            chemicals = {}
            treated_water = {}
            st.warning(f"Could not run analysis: {e}")

    # View toggle
    view_mode = st.radio("View", ["Schematic", "Detailed"], horizontal=True,
                         help="Detailed adds stream quality and dose labels")
    detailed = (view_mode == "Detailed")

    svg = build_pfd_svg(process_train, sludge_train, chemicals,
                        source_water, treated_water, flow, detailed)
    st.markdown(svg, unsafe_allow_html=True)

    # Download buttons
    st.markdown("<br>", unsafe_allow_html=True)
    col_d1, col_d2, _ = st.columns([1, 1, 2])
    with col_d1:
        st.download_button("⬇ Schematic SVG",
            data=build_pfd_svg(process_train, sludge_train, chemicals,
                               source_water, treated_water, flow, False),
            file_name=f"pfd_{sel_key}_schematic.svg", mime="image/svg+xml",
            use_container_width=True)
    with col_d2:
        st.download_button("⬇ Detailed SVG",
            data=build_pfd_svg(process_train, sludge_train, chemicals,
                               source_water, treated_water, flow, True),
            file_name=f"pfd_{sel_key}_detailed.svg", mime="image/svg+xml",
            use_container_width=True)

    # ── Train summary table ───────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Treatment Train Summary", "📋")

    import pandas as pd
    rows = []
    for i, tech in enumerate(process_train):
        td = TECHNOLOGIES.get(tech, {})
        chem_keys = CHEM_INJECTION_MAP.get(tech, [])
        active = [
            f"{CHEM_SHORT.get(k, k)}: {chemicals[k]['dose_mg_L']:.0f} mg/L"
            for k in chem_keys if k in chemicals
        ]
        rows.append({
            "Step": i + 1,
            "Unit Process": td.get("label", tech),
            "Category": td.get("category", "—"),
            "Chemicals": ", ".join(active) if active else "—",
        })
    if sludge_train:
        for tech in sludge_train:
            td = TECHNOLOGIES.get(tech, {})
            rows.append({
                "Step": "↓",
                "Unit Process": td.get("label", tech),
                "Category": "Residuals",
                "Chemicals": "—",
            })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Inject pre_filter_chlorination before RGF when Mn is elevated
    # and neither KMnO₄ alone nor softening is achieving spec
    _mn_after_kmno4 = (_mn * (1 - 0.88)) if "kmno4_pre_oxidation" in sel_train else _mn
    _pfc_required = (_mn > 0.1 and _mn_after_kmno4 > 0.03 and
                     "pre_filter_chlorination" not in sel_train and
                     "bac" not in sel_train)  # not compatible with BAC
    if _pfc_required:
        sel_train = list(sel_train)
        # Insert before rapid_gravity_filtration
        _rgf_idx = next(
            (i for i, t in enumerate(sel_train) if t == "rapid_gravity_filtration"),
            len(sel_train)
        )
        sel_train.insert(_rgf_idx, "pre_filter_chlorination")

    # ── Softening Analysis tab ───────────────────────────────────────────────
    sw_pfd     = st.session_state.get("source_water", {})
    hardness   = float(sw_pfd.get("hardness_mg_l", 150))
    alkalinity = float(sw_pfd.get("alkalinity_mg_l", 80))
    tds_pfd    = float(sw_pfd.get("tds_mg_l", 300))
    softening_in_sel = "chemical_softening" in sel_train

    if hardness > 200 or softening_in_sel:
        st.markdown("<br>", unsafe_allow_html=True)
        section_header("Split-Stream Softening Analysis", "🧂")

        from ..engine.softening_blend import calculate_softening_blend

        with st.expander("View split-stream analysis", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                pph = st.number_input(
                    "Product pH (post-recarbonation)",
                    min_value=7.0, max_value=8.5, value=7.8, step=0.1,
                    key="pfd_softening_ph",
                    help="pH after CO₂ recarbonation. Target 7.8–8.2."
                )
            with c2:
                cfrac = st.slider(
                    "Carbonate hardness fraction",
                    0.40, 0.90, 0.70, 0.05,
                    key="pfd_carb_frac",
                    help="Fraction of total hardness that is carbonate."
                )

            blend = calculate_softening_blend(
                total_flow_ML_d     = flow,
                raw_hardness_mg_l   = hardness,
                raw_alkalinity_mg_l = alkalinity,
                raw_tds_mg_l        = tds_pfd,
                product_ph          = pph,
                carbonate_fraction  = cfrac,
            )

            import pandas as pd
            rows = []
            for o in blend.options:
                rows.append({
                    "%":              f"{o.softening_fraction_pct:.0f}%",
                    "Soft (ML/d)":    f"{o.softening_flow_ML_d:.1f}",
                    "Bypass (ML/d)":  f"{o.bypass_flow_ML_d:.1f}",
                    "Hard (mg/L)":    f"{o.blended_hardness_mg_l:.0f}",
                    "Alk (mg/L)":     f"{o.blended_alkalinity_mg_l:.0f}",
                    "CCPP":           f"{o.ccpp_approx:+.1f}",
                    "H✓":             "✓" if o.hardness_compliant else "✗",
                    "CCPP✓":          "✓" if o.ccpp_compliant else "✗",
                    "All✓":           "✓✓✓" if o.fully_compliant else "—",
                    "Lime (mg/L)":    f"{o.lime_dose_mg_l:.0f}",
                    "Cost ($M/yr)":   f"{o.total_chemical_cost_AUD/1e6:.2f}",
                    "Sludge (t/d)":   f"{o.sludge_production_t_d:.1f}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if blend.recommended_option:
                rec = blend.recommended_option
                st.success(
                    f"**Recommended: {rec.softening_fraction_pct:.0f}% split-stream** — "
                    f"{rec.softening_flow_ML_d:.1f} ML/d softened | "
                    f"{rec.bypass_flow_ML_d:.1f} ML/d bypass | "
                    f"Hardness {rec.blended_hardness_mg_l:.0f} mg/L | "
                    f"CCPP {rec.ccpp_approx:+.1f} mg/L | "
                    f"Lime {rec.lime_dose_mg_l:.0f} mg/L | "
                    f"${rec.total_chemical_cost_AUD/1e6:.2f}M/yr"
                )
            else:
                st.warning(
                    f"Full-flow softening required at this raw water quality — "
                    f"no split-stream fraction achieves CCPP compliance at pH {pph:.1f}."
                )

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        if st.button("← Technology Selection", use_container_width=True):
            st.session_state["current_page"] = "technology_selection"
            st.rerun()
    with col_n2:
        if st.button("Analysis Results →", use_container_width=True):
            st.session_state["current_page"] = "results"
            st.rerun()
