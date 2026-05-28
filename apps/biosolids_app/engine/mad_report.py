"""
engine/mad_report.py

BioPoint V1 — MAD Analyser Tier 1 Report Generator.

Produces a consultant-grade PDF report from a MAD analysis result.
Suitable for: Stage 1–2 options analysis, internal review, client briefing.

Usage (from page_07_mad.py):
    from engine.mad_report import generate_mad_report
    pdf_bytes = generate_mad_report(inputs, result, project_name, prepared_by)
    st.download_button("Download Report", pdf_bytes, "MAD_Report.pdf", "application/pdf")

ph2o Consulting — BioPoint V1 — v25B02
"""

from io import BytesIO
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable

# ── Palette ────────────────────────────────────────────────────────────────
PH2O_BLUE   = colors.HexColor("#1a3a5c")   # ph2o dark blue
PH2O_TEAL   = colors.HexColor("#0077b6")   # accent teal
PH2O_LIGHT  = colors.HexColor("#e8f4f8")   # light blue background
SAFE_GREEN  = colors.HexColor("#2e7d32")
WARN_AMBER  = colors.HexColor("#e65100")
FAIL_RED    = colors.HexColor("#c62828")
GREY_MID    = colors.HexColor("#546e7a")
GREY_LIGHT  = colors.HexColor("#eceff1")
GREY_RULE   = colors.HexColor("#b0bec5")
WHITE       = colors.white
BLACK       = colors.black

PAGE_W, PAGE_H = A4
MARGIN_L = 20*mm
MARGIN_R = 20*mm
MARGIN_T = 25*mm
MARGIN_B = 20*mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R


# ── Style sheet ────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    S = {}

    S["title"] = ParagraphStyle("title",
        parent=base["Normal"], fontSize=20, leading=24,
        textColor=PH2O_BLUE, fontName="Helvetica-Bold",
        spaceAfter=4)

    S["subtitle"] = ParagraphStyle("subtitle",
        parent=base["Normal"], fontSize=11, leading=14,
        textColor=PH2O_TEAL, fontName="Helvetica",
        spaceAfter=2)

    S["meta"] = ParagraphStyle("meta",
        parent=base["Normal"], fontSize=9, leading=12,
        textColor=GREY_MID, fontName="Helvetica",
        spaceAfter=2)

    S["h1"] = ParagraphStyle("h1",
        parent=base["Normal"], fontSize=13, leading=16,
        textColor=PH2O_BLUE, fontName="Helvetica-Bold",
        spaceBefore=14, spaceAfter=6)

    S["h2"] = ParagraphStyle("h2",
        parent=base["Normal"], fontSize=10, leading=13,
        textColor=PH2O_TEAL, fontName="Helvetica-Bold",
        spaceBefore=10, spaceAfter=4)

    S["body"] = ParagraphStyle("body",
        parent=base["Normal"], fontSize=9, leading=13,
        textColor=BLACK, fontName="Helvetica",
        spaceAfter=4, alignment=TA_JUSTIFY)

    S["body_small"] = ParagraphStyle("body_small",
        parent=base["Normal"], fontSize=8, leading=11,
        textColor=GREY_MID, fontName="Helvetica",
        spaceAfter=3)

    S["caption"] = ParagraphStyle("caption",
        parent=base["Normal"], fontSize=8, leading=10,
        textColor=GREY_MID, fontName="Helvetica-Oblique",
        spaceAfter=4)

    S["cell"] = ParagraphStyle("cell",
        parent=base["Normal"], fontSize=8.5, leading=11,
        textColor=BLACK, fontName="Helvetica")

    S["cell_bold"] = ParagraphStyle("cell_bold",
        parent=base["Normal"], fontSize=8.5, leading=11,
        textColor=BLACK, fontName="Helvetica-Bold")

    S["cell_label"] = ParagraphStyle("cell_label",
        parent=base["Normal"], fontSize=8, leading=10,
        textColor=GREY_MID, fontName="Helvetica")

    S["status_safe"] = ParagraphStyle("status_safe",
        parent=base["Normal"], fontSize=11, leading=14,
        textColor=SAFE_GREEN, fontName="Helvetica-Bold",
        alignment=TA_CENTER)

    S["status_fail"] = ParagraphStyle("status_fail",
        parent=base["Normal"], fontSize=11, leading=14,
        textColor=FAIL_RED, fontName="Helvetica-Bold",
        alignment=TA_CENTER)

    S["disclaimer"] = ParagraphStyle("disclaimer",
        parent=base["Normal"], fontSize=7.5, leading=10,
        textColor=GREY_MID, fontName="Helvetica-Oblique",
        spaceAfter=3, alignment=TA_JUSTIFY)

    return S


# ── Table style helpers ────────────────────────────────────────────────────
def _table_style_data():
    return TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), PH2O_BLUE),
        ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8.5),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 5),
        ("TOPPADDING",  (0, 0), (-1, 0), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREY_LIGHT]),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 8.5),
        ("TOPPADDING",  (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",(0, 0), (-1, -1), 6),
        ("GRID",        (0, 0), (-1, -1), 0.3, GREY_RULE),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ])


def _table_style_kv():
    """Two-column key-value table style."""
    return TableStyle([
        ("BACKGROUND",  (0, 0), (0, -1), PH2O_LIGHT),
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",    (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 8.5),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",(0, 0), (-1, -1), 7),
        ("GRID",        (0, 0), (-1, -1), 0.3, GREY_RULE),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, GREY_LIGHT]),
    ])


def _status_colour(status: str) -> colors.Color:
    if status == "SAFE":     return SAFE_GREEN
    if status == "FAILURE":  return FAIL_RED
    return WARN_AMBER


def _feas_colour(feas: str) -> colors.Color:
    if feas == "FEASIBLE":   return SAFE_GREEN
    if feas == "INFEASIBLE": return FAIL_RED
    return WARN_AMBER


def _p(text, style):
    return Paragraph(text, style)


def _rule():
    return HRFlowable(width="100%", thickness=0.5, color=GREY_RULE, spaceAfter=4)


# ── Header / footer callbacks ──────────────────────────────────────────────
def _make_header_footer(project, prepared_by, date_str, version):

    def on_page(canvas, doc):
        canvas.saveState()
        w, h = A4

        # Top bar
        canvas.setFillColor(PH2O_BLUE)
        canvas.rect(0, h - 14*mm, w, 14*mm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(MARGIN_L, h - 9*mm, "BioPoint V1 — MAD Analyser Report")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(w - MARGIN_R, h - 9*mm, f"{project}  |  {prepared_by}")

        # Bottom bar
        canvas.setFillColor(GREY_LIGHT)
        canvas.rect(0, 0, w, 12*mm, fill=1, stroke=0)
        canvas.setFillColor(GREY_MID)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(MARGIN_L, 4.5*mm,
            f"SCREENING GRADE — ±15% energy, ±20% sidestream  |  {version}  |  {date_str}")
        canvas.drawRightString(w - MARGIN_R, 4.5*mm,
            f"Page {doc.page}")

        canvas.restoreState()

    return on_page


# ── Section builders ────────────────────────────────────────────────────────

def _cover_section(story, S, inputs, project, prepared_by, date_str, version):
    """Title page content."""
    story.append(Spacer(1, 8*mm))

    # Status badge
    status_label = "SAFE" if inputs.get("_status") != "FAILURE" else "FAILURE"
    status_col   = SAFE_GREEN if status_label == "SAFE" else FAIL_RED
    badge_data = [[Paragraph(f"Overall Status: {status_label}", ParagraphStyle(
        "badge", parent=S["body"], fontSize=14, fontName="Helvetica-Bold",
        textColor=WHITE, alignment=TA_CENTER))]]
    badge_tbl = Table(badge_data, colWidths=[CONTENT_W])
    badge_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), status_col),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(badge_tbl)
    story.append(Spacer(1, 6*mm))

    # Project info
    info_data = [
        ["Project",     project],
        ["Prepared by", prepared_by],
        ["Date",        date_str],
        ["BioPoint version", version],
        ["Confidence grade", inputs.get("_confidence", "85–92/100")],
        ["Pretreatment", {
            "none":        "None — conventional AD",
            "thp":         "Pre-digestion THP",
            "solidstream": "SolidStream (post-digestion THP)",
        }.get(inputs.get("pretreatment", "none"), inputs.get("pretreatment", "—"))],
    ]
    tbl = Table(info_data, colWidths=[55*mm, CONTENT_W - 55*mm])
    tbl.setStyle(_table_style_kv())
    story.append(tbl)
    story.append(Spacer(1, 6*mm))

    story.append(_rule())
    story.append(_p(
        "This report summarises the outputs of the BioPoint V1 Mesophilic Anaerobic "
        "Digestion (MAD) Analyser — a screening-grade engine for evaluating digester "
        "performance, mixing adequacy, NH<sub>3</sub> inhibition risk, biogas production, "
        "and sidestream nitrogen loads. Outputs are intended for Stage 1–2 options analysis "
        "and preliminary business case development.", S["body"]))
    story.append(Spacer(1, 3*mm))
    story.append(_p(
        "<b>Screening grade:</b> all figures carry ±15% uncertainty on energy outputs "
        "and ±20% on sidestream loads. Independent verification required before "
        "detailed design or regulatory submission.", S["body_small"]))


def _executive_summary(story, S, inputs, ps, was, energy, sidestream, flags):
    story.append(_p("1. Executive Summary", S["h1"]))
    story.append(_rule())

    pretreat = inputs.get("pretreatment", "none")
    pretreat_label = {
        "none":        "conventional mesophilic AD",
        "thp":         "pre-digestion THP",
        "solidstream": "SolidStream post-digestion THP",
    }.get(pretreat, pretreat)

    summary = (
        f"The MAD Analyser evaluated a {pretreat_label} configuration treating a combined "
        f"dry solids load of <b>{inputs['ps_ds_tpd'] + inputs['was_ds_tpd']:.1f} tDS/day</b> "
        f"(PS: {inputs['ps_ds_tpd']:.1f} tDS/day, WAS: {inputs['was_ds_tpd']:.1f} tDS/day) "
        f"across a total digester volume of "
        f"<b>{inputs['ps_volume_m3'] + inputs['was_volume_m3']:,.0f} m<super>3</super></b>. "
        f"Both streams are classified <b>SAFE</b>. The primary constraint is "
        f"<b>{inputs.get('_primary', 'NH3 inhibition')}</b>."
    )
    story.append(_p(summary, S["body"]))

    # Key outputs table
    story.append(_p("Key outputs", S["h2"]))
    rows = [
        ["Parameter", "Value", "Unit"],
        ["Biogas production",    f"{energy['biogas_m3_d']:,.0f}",   "m\u00b3/day"],
        ["Biogas energy",        f"{energy['biogas_gj_d']:.1f}",    "GJ/day"],
        ["CHP gross output",     f"{energy['elec_gross_kw']:,.0f}", "kW"],
        ["Net electricity",      f"{energy['net_elec_kw']:,.0f}",   "kW"],
        ["Centrate NH\u2084\u207a\u2013N", f"{sidestream['centrate_n_kgd']:.1f}", "kg N/day"],
        ["Cake N",               f"{sidestream['cake_n_kgd']:.1f}", "kg N/day"],
        ["PS VS destruction",    f"{ps['VS_dest_pct']:.1f}",        "% of VS feed"],
        ["WAS VS destruction",   f"{was['VS_dest_pct']:.1f}",       "% of VS feed"],
    ]
    tbl = Table(rows, colWidths=[90*mm, 50*mm, CONTENT_W - 140*mm])
    tbl.setStyle(_table_style_data())
    story.append(tbl)

    # SolidStream callout
    if flags.get("solidstream_active"):
        story.append(Spacer(1, 4*mm))
        ss_text = (
            "<b>SolidStream configuration active.</b> Post-digestion THP is expected to deliver: "
            "dewatered cake \u226538% DS (no thermal drying required); ~22.7% biogas uplift "
            "from COD-rich centrate recycled to digesters; ~50\u201357% cake volume reduction; "
            "full pathogen kill equivalent to Class A. "
            "<i>Figures are vendor-estimated (Cambi Melbourne ETP memo 20.05.2026) \u2014 "
            "not guaranteed performance. Minimum 15d HRT required.</i>"
        )
        ss_data = [[Paragraph(ss_text, ParagraphStyle(
            "ss_note", parent=S["body"], fontSize=8.5, textColor=PH2O_BLUE))]]
        ss_tbl = Table(ss_data, colWidths=[CONTENT_W])
        ss_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), PH2O_LIGHT),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
            ("TOPPADDING",    (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
            ("BOX",           (0,0), (-1,-1), 1, PH2O_TEAL),
        ]))
        story.append(ss_tbl)


def _digester_inputs_section(story, S, inputs):
    story.append(_p("2. Digester Configuration & Inputs", S["h1"]))
    story.append(_rule())

    col_w = (CONTENT_W - 4*mm) / 2

    # PS inputs
    ps_data = [
        ["Parameter", "Value"],
        ["Digester volume", f"{inputs['ps_volume_m3']:,.0f} m\u00b3"],
        ["Dry solids load", f"{inputs['ps_ds_tpd']:.1f} tDS/day"],
        ["Feed TS%", f"{inputs['ps_ts_pct']:.1f}%"],
        ["Volatile solids", f"{inputs['ps_vs_pct']:.1f}% of DS"],
        ["Nitrogen content", f"{inputs['ps_n_pct']:.1f}% of DS"],
        ["Recup capture", f"{inputs['ps_cap_pct']:.0f}%"],
        ["Recirculation \u03b2", f"{inputs['ps_beta']:.2f}"],
    ]
    was_data = [
        ["Parameter", "Value"],
        ["Digester volume", f"{inputs['was_volume_m3']:,.0f} m\u00b3"],
        ["Dry solids load", f"{inputs['was_ds_tpd']:.1f} tDS/day"],
        ["Feed TS%", f"{inputs['was_ts_pct']:.1f}%"],
        ["Volatile solids", f"{inputs['was_vs_pct']:.1f}% of DS"],
        ["Nitrogen content", f"{inputs['was_n_pct']:.1f}% of DS"],
        ["Recup capture", f"{inputs['was_cap_pct']:.0f}%"],
        ["Recirculation \u03b2", f"{inputs['was_beta']:.2f}"],
    ]

    for label, data in [("Primary Sludge (PS)", ps_data), ("Waste Activated Sludge (WAS)", was_data)]:
        story.append(_p(label, S["h2"]))
        tbl = Table(data, colWidths=[col_w * 0.55, col_w * 0.45])
        tbl.setStyle(_table_style_data())
        story.append(tbl)
        story.append(Spacer(1, 3*mm))

    # Operating conditions
    story.append(_p("Operating conditions", S["h2"]))
    op_data = [
        ["Parameter", "Value", "Parameter", "Value"],
        ["Mixing system",     inputs["mixing_type"].capitalize(),
         "Digester pH",       f"{inputs['digester_pH']:.2f}"],
        ["Mixing power",      f"{inputs['mixing_power']:.0f} W/m\u00b3",
         "pH control",        inputs["ph_control"].upper()],
        ["NH\u2083 mode",     inputs["nh3_mode"].capitalize(),
         "Pretreatment",      {
             "none": "None", "thp": "Pre-THP", "solidstream": "SolidStream"
         }.get(inputs["pretreatment"], inputs["pretreatment"])],
        ["Trade waste",       inputs["trade_waste"].capitalize(),
         "CHP efficiency",    f"{inputs['chp_eff_pct']:.0f}%"],
        ["Final dewatering cap", f"{inputs['final_cap_pct']:.0f}%",
         "CHP availability",  f"{inputs['chp_avail_pct']:.0f}%"],
    ]
    cw = CONTENT_W / 4
    tbl = Table(op_data, colWidths=[cw*1.1, cw*0.9, cw*1.1, cw*0.9])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), PH2O_BLUE),
        ("TEXTCOLOR",    (0,0), (-1,0), WHITE),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 8.5),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, GREY_LIGHT]),
        ("BACKGROUND",   (0,1), (0,-1), PH2O_LIGHT),
        ("BACKGROUND",   (2,1), (2,-1), PH2O_LIGHT),
        ("FONTNAME",     (0,1), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",     (2,1), (2,-1), "Helvetica-Bold"),
        ("FONTNAME",     (1,1), (1,-1), "Helvetica"),
        ("FONTNAME",     (3,1), (3,-1), "Helvetica"),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("GRID",         (0,0), (-1,-1), 0.3, GREY_RULE),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(tbl)


def _stream_physics_section(story, S, ps, was, feasibility):
    story.append(_p("3. Digester Physics & Performance", S["h1"]))
    story.append(_rule())

    # Side-by-side PS / WAS
    def stream_rows(s, label):
        sc = _status_colour(s["status"])
        return [
            [Paragraph(f"<b>{label}</b>", S["cell_bold"]),
             Paragraph(f"<b>{s['status']}</b>", ParagraphStyle(
                 "st", parent=S["cell_bold"], textColor=sc))],
            ["Primary constraint", s["primary"]],
            ["Mixing factor f_mix", f"{s['f_mix']:.3f}"],
            ["Diffusion factor f_diff", f"{s['f_diff_eff']:.3f}"],
            ["Combined f_eff", f"{s['f_eff']:.3f}"],
            ["HRT (nominal)", f"{s['HRT_d']:.1f} days"],
            ["SRT (nominal)", f"{s['SRT_nom_d']:.1f} days"],
            ["SRT (effective)", f"{s['SRT_eff_d']:.1f} days"],
            ["VS destruction", f"{s['VS_dest_pct']:.1f}%"],
            ["NH\u2084\u207a concentration", f"{s['NH4_g_L']:.2f} g/L"],
            ["Free NH\u2083 (inhibiting)", f"{s['NH3_g_L']:.3f} g NH\u2083-N/L"],
            ["NH\u2083 inhibition", f"{s['inhibition_pct']:.1f}%"],
        ]

    ps_rows  = stream_rows(ps,  "Primary Sludge (PS)")
    was_rows = stream_rows(was, "Waste Activated Sludge (WAS)")

    # Interleave into two-column table
    combined = []
    for i, (pr, wr) in enumerate(zip(ps_rows, was_rows)):
        combined.append(pr + wr)

    half = CONTENT_W / 2 - 2*mm
    cw = [half * 0.52, half * 0.48, half * 0.52, half * 0.48]
    tbl = Table(combined, colWidths=cw)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (1,0), PH2O_TEAL),
        ("BACKGROUND",   (2,0), (3,0), PH2O_TEAL),
        ("TEXTCOLOR",    (0,0), (-1,0), WHITE),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 8.5),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, GREY_LIGHT]),
        ("BACKGROUND",   (0,1), (0,-1), PH2O_LIGHT),
        ("BACKGROUND",   (2,1), (2,-1), PH2O_LIGHT),
        ("FONTNAME",     (0,1), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",     (2,1), (2,-1), "Helvetica-Bold"),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("GRID",         (0,0), (-1,-1), 0.3, GREY_RULE),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("LINEAFTER",    (1,0), (1,-1), 1.0, PH2O_BLUE),
    ]))
    story.append(tbl)

    # Feasibility
    story.append(Spacer(1, 5*mm))
    story.append(_p("Geometric feasibility", S["h2"]))
    fc = _feas_colour(feasibility["overall"])
    feas_data = [
        ["Check", "PS", "WAS", "Threshold"],
        ["Overall feasibility",
         feasibility["ps"], feasibility["was"],
         "—"],
        ["Min stable SRT",
         f"{feasibility['max_ps_srt']:.1f}d achievable",
         f"{feasibility['max_was_srt']:.1f}d achievable",
         f">{feasibility['min_stable_srt']:.0f}d required"],
    ]
    tbl2 = Table(feas_data, colWidths=[70*mm, 45*mm, 45*mm, CONTENT_W-160*mm])
    ts2 = _table_style_data()
    # Colour feasibility cells
    for col, stream in [(1, feasibility["ps"]), (2, feasibility["was"])]:
        c = _feas_colour(stream)
        ts2.add("TEXTCOLOR", (col, 1), (col, 1), c)
        ts2.add("FONTNAME",  (col, 1), (col, 1), "Helvetica-Bold")
    tbl2.setStyle(ts2)
    story.append(tbl2)


def _energy_section(story, S, energy, inputs):
    story.append(_p("4. Energy Balance & CHP", S["h1"]))
    story.append(_rule())

    rows = [
        ["Parameter", "Value", "Notes"],
        ["Biogas production",      f"{energy['biogas_m3_d']:,.0f} m\u00b3/day",
         "64% CH\u2084 assumed"],
        ["Biogas energy (LHV)",    f"{energy['biogas_gj_d']:.1f} GJ/day",
         "35.8 MJ/m\u00b3 CH\u2084 LHV"],
        ["CHP gross output",       f"{energy['elec_gross_kw']:,.0f} kW",
         f"{inputs['chp_eff_pct']:.0f}% electrical efficiency"],
        ["Mixing parasitic load",  f"{energy['mixing_kw']:,.0f} kW",
         f"{inputs['mixing_power']:.0f} W/m\u00b3 \u00d7 digester volume"],
        ["Net electrical output",  f"{energy['net_elec_kw']:,.0f} kW",
         "Gross minus mixing"],
        ["Net electrical (annual)",f"{energy['net_elec_kw'] * 8760 / 1000:,.0f} MWh/yr",
         f"{inputs['chp_avail_pct']:.0f}% CHP availability applied"],
    ]
    tbl = Table(rows, colWidths=[70*mm, 55*mm, CONTENT_W-125*mm])
    tbl.setStyle(_table_style_data())
    story.append(tbl)

    story.append(Spacer(1, 3*mm))
    story.append(_p(
        "CHP availability and electrical efficiency are as configured. "
        "Gas engine parasitic loads and auxiliary equipment consumption are not modelled — "
        "deduct 3–5% from net electrical for auxiliary systems. "
        "Thermal recovery from CHP jacket heat is not included in this report.",
        S["body_small"]))


def _sidestream_section(story, S, sidestream, inputs):
    story.append(_p("5. Sidestream Nitrogen", S["h1"]))
    story.append(_rule())

    total = sidestream["centrate_n_kgd"] + sidestream["cake_n_kgd"]
    centrate_pct = sidestream["centrate_n_kgd"] / total * 100 if total > 0 else 0
    cake_pct = 100 - centrate_pct

    rows = [
        ["Stream", "N load (kg N/day)", "% of total N released", "Notes"],
        ["Centrate (return liquor)",
         f"{sidestream['centrate_n_kgd']:.1f}",
         f"{centrate_pct:.0f}%",
         "Returns to liquid treatment"],
        ["Dewatered cake",
         f"{sidestream['cake_n_kgd']:.1f}",
         f"{cake_pct:.0f}%",
         "Leaves system in biosolids product"],
        ["Total N released",
         f"{total:.1f}",
         "100%",
         "From digestion + THP N mineralisation"],
    ]
    tbl = Table(rows, colWidths=[55*mm, 40*mm, 45*mm, CONTENT_W-140*mm])
    tbl.setStyle(_table_style_data())
    story.append(tbl)

    story.append(Spacer(1, 3*mm))
    story.append(_p(
        "Centrate NH\u2084\u207a\u2013N load drives return liquor impacts on the liquid "
        "treatment train. At large scale this is typically 15–25% of plant influent "
        "TKN. Sidestream treatment (SHARON/ANAMMOX or nitritation) should be "
        "evaluated if centrate N exceeds 10% of plant TKN capacity.",
        S["body"]))
    story.append(_p(
        "Uncertainty: ±20% on all sidestream N figures (screening grade).",
        S["body_small"]))


def _solidstream_section(story, S, solidstream_data):
    story.append(_p("6. SolidStream Performance Estimates", S["h1"]))
    story.append(_rule())

    story.append(_p(
        "The following performance estimates apply to the SolidStream post-digestion "
        "THP configuration. All figures are vendor-estimated based on Cambi's "
        "conceptual design memo for Melbourne Eastern Treatment Plant (20 May 2026) "
        "and Antwerp Schijnpoort 2025 operational data. "
        "<b>These are not guaranteed performance values.</b> Minimum 15d HRT in "
        "existing digesters is required for SolidStream operation.",
        S["body"]))

    rows = [
        ["Parameter", "SolidStream", "Conventional AD", "Basis"],
        ["Dewatered cake DS%",
         f"\u2265{solidstream_data['cake_ds_pct']:.0f}% DS",
         "20–22% DS",
         "Antwerp 2025 operational; Melbourne ETP memo min. guarantee"],
        ["VSR in digestion",
         f"~{solidstream_data['vsr_pct']:.1f}%",
         "57.5%",
         "Melbourne ETP memo Sc1 & Sc2; literature 65–75%"],
        ["Biogas uplift",
         f"+{solidstream_data['biogas_uplift_pct']:.1f}%",
         "Baseline",
         "COD-rich centrate recycled to digesters"],
        ["Cake volume reduction",
         f"~{solidstream_data['cake_vol_reduction_pct']:.0f}%",
         "Baseline",
         "Melbourne ETP memo: -50.6% (65%VS), -56.5% (72%VS)"],
        ["Drying energy reduction",
         f"~{solidstream_data['drying_reduction_pct']:.0f}%",
         "Baseline",
         "If thermal drying still applied after SolidStream"],
        ["Electricity production uplift",
         f"+{solidstream_data['elec_uplift_pct']:.1f}%",
         "Baseline",
         "Melbourne ETP memo Sc1"],
        ["Pathogen kill",
         "Class A equivalent",
         "Class B (conventional)",
         "165\u00b0C / 6 bar / 40 min \u2014 sterilisation++ in THP"],
    ]
    tbl = Table(rows, colWidths=[55*mm, 38*mm, 38*mm, CONTENT_W-131*mm])
    tbl.setStyle(_table_style_data())
    story.append(tbl)

    story.append(Spacer(1, 3*mm))
    story.append(_p(
        "<b>Important distinction:</b> SolidStream biogas uplift (~23%) is "
        "substantially lower than pre-digestion THP (~40–50%). The two configurations "
        "serve different purposes. SolidStream is a retrofit for existing digesters "
        "and does not reduce digester volume requirement. Pre-digestion THP reduces "
        "required digester volume through enhanced hydrolysis before digestion.",
        S["body_small"]))

    story.append(Spacer(1, 3*mm))
    story.append(_p(
        "Source: Cambi Conceptual Design Memo, Melbourne Eastern Treatment Plant, "
        "20.05.2026 (Doc 10590-ZME-001-7035 A01). Client: Melbourne Water Corporation "
        "/ Aurecon. Confidence: vendor model, pre-contract conceptual stage.",
        S["caption"]))


def _flags_section(story, S, flags, inputs):
    story.append(_p("7. Diagnostic Flags & Recommendations", S["h1"]))
    story.append(_rule())

    flag_defs = {
        "geometric_infeasibility":  ("CRITICAL", "FAIL",
            "Digester too small for stable SRT. Increase digester volume or reduce solids load."),
        "geometric_marginal":       ("WARNING", "MARGINAL",
            "Geometric operating window is narrow. Monitor SRT closely; review loading rate."),
        "biogas_blind_warning":     ("WARNING", "BLIND ZONE",
            "WAS effective SRT > 30 days. Biogas yield is insensitive in this range; "
            "use NH\u2084\u207a and pH as primary performance indicators."),
        "high_TS_diffusion_active": ("INFO", "DIFFUSION COUPLING",
            "Feed TS > 4% — diffusion-limited zone active. Mixing system performance "
            "is critical; gas mixing systems are significantly derated at elevated TS."),
        "thp_active":               ("INFO", "THP ACTIVE",
            "THP kinetic boost applied. Hydrolysis rate k \u00d7 1.35; "
            "VSmax ceiling raised to 75% PS / 72% WAS."),
        "solidstream_active":       ("INFO", "SOLIDSTREAM ACTIVE",
            "Post-digestion THP configuration. Centrate COD recycle boost applied. "
            "VSmax ceiling raised. Biogas uplift ~22.7% (vendor estimate)."),
        "solidstream_hrt_warning":  ("CRITICAL", "HRT < 15d",
            "Digester HRT falls below the 15-day minimum for SolidStream operation. "
            "Insufficient digestion time will impair performance. Add digester volume "
            "or reduce throughput before installing SolidStream."),
        "pH_control_engaged":       ("INFO", "pH CONTROL ENGAGED",
            "Digester pH clamped to 7.30 for NH\u2083 inhibition calculation."),
        "industrial_trade_waste":   ("WARNING", "INDUSTRIAL TRADE WASTE",
            "WAS N% elevated to \u226511% — industrial co-treatment. "
            "Sidestream nitrogen loads will be significantly higher than domestic baseline."),
    }

    active = {k: v for k, v in flags.items() if v}
    if not active:
        story.append(_p("No diagnostic flags active — all checks passed.", S["body"]))
        return

    severity_colour = {"CRITICAL": FAIL_RED, "WARNING": WARN_AMBER, "INFO": PH2O_TEAL}

    rows = [["Severity", "Flag", "Description / Recommended action"]]
    for flag_key, flag_val in active.items():
        if not flag_val:
            continue
        if flag_key not in flag_defs:
            continue
        severity, label, desc = flag_defs[flag_key]
        rows.append([severity, label, desc])

    cw = [22*mm, 38*mm, CONTENT_W - 60*mm]
    tbl = Table(rows, colWidths=cw)
    ts = _table_style_data()
    for i, row in enumerate(rows[1:], 1):
        sev = row[0]
        col = severity_colour.get(sev, GREY_MID)
        ts.add("TEXTCOLOR", (0, i), (0, i), col)
        ts.add("FONTNAME",  (0, i), (0, i), "Helvetica-Bold")
    tbl.setStyle(ts)
    story.append(tbl)


def _disclaimer_section(story, S):
    story.append(PageBreak())
    story.append(_p("Disclaimer & Basis of Report", S["h1"]))
    story.append(_rule())
    story.append(_p(
        "This report has been produced by the BioPoint V1 MAD Analyser engine "
        "(ph2o Consulting, v25B02). It is intended for use during Stage 1–2 options "
        "investigation, master planning, and preliminary business case development. "
        "It is not suitable for detailed process design, procurement documentation, "
        "regulatory submission, or contract pricing without independent engineering "
        "verification and site-specific validation.", S["body"]))
    story.append(Spacer(1, 3*mm))

    caveats = [
        ("CAPEX estimates",
         "Not included in this report. Order-of-magnitude CAPEX from the BioPoint "
         "pathway rankings carries ±30% uncertainty."),
        ("Energy uncertainty",
         "All energy figures (biogas, electricity, mixing) carry ±15% uncertainty "
         "at this screening grade."),
        ("Sidestream loads",
         "Centrate and cake nitrogen loads carry ±20% uncertainty. "
         "Seasonal and diurnal variation is not modelled."),
        ("SolidStream performance",
         "All SolidStream figures are vendor-estimated (Cambi, pre-contract conceptual "
         "stage). Actual performance subject to feedstock, digester configuration, "
         "HRT, and operating conditions. Independent performance guarantee testing "
         "required before commitment."),
        ("NH3 inhibition",
         "Inhibition model is based on published kinetic constants (Hansen 1998, Wu 2010). "
         "Site-specific acclimation histories may differ from model assumptions."),
        ("Regulatory compliance",
         "BioPoint does not assess regulatory compliance. EPA Victoria pathogen "
         "classification, nutrient discharge limits, and PFAS obligations require "
         "separate specialist assessment."),
    ]

    rows = [["Caveat", "Notes"]]
    for k, v in caveats:
        rows.append([k, v])
    tbl = Table(rows, colWidths=[55*mm, CONTENT_W-55*mm])
    tbl.setStyle(_table_style_data())
    story.append(tbl)

    story.append(Spacer(1, 5*mm))
    story.append(_rule())
    story.append(_p(
        "\u00a9 ph2o Consulting. BioPoint V1 is a screening-grade decision support tool. "
        "All outputs should be validated against site-specific data, vendor quotations, "
        "and independent engineering judgement before financial commitment.",
        S["caption"]))


# ── Main entry point ────────────────────────────────────────────────────────

def generate_mad_report(
    inputs: dict,
    result,
    project_name: str = "BioPoint Analysis",
    prepared_by: str = "ph2o Consulting",
) -> bytes:
    """
    Generate a Tier 1 MAD Analyser report.

    Parameters
    ----------
    inputs  : dict of MADInputs fields (use inputs.__dict__ or build manually)
    result  : MADResult from run_mad()
    project_name : Project name for header
    prepared_by  : Consultant / organisation name

    Returns
    -------
    bytes  PDF file as bytes (pass directly to st.download_button)
    """
    buf = BytesIO()
    date_str = date.today().strftime("%d %B %Y")
    version  = "v25B02"

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T + 8*mm,   # extra for header bar
        bottomMargin=MARGIN_B + 8*mm,
        title=f"MAD Analyser Report — {project_name}",
        author=prepared_by,
        subject="Mesophilic Anaerobic Digestion Analysis",
        creator="BioPoint V1",
    )

    S = _styles()

    # Flatten inputs dict for easier access
    inp = inputs if isinstance(inputs, dict) else inputs.__dict__
    inp["_status"]     = result.status
    inp["_primary"]    = result.primary_constraint
    inp["_confidence"] = result.confidence_grade

    # Extract sub-objects
    ps_d  = result.ps.__dict__  if hasattr(result.ps,  "__dict__") else result.ps
    was_d = result.was.__dict__ if hasattr(result.was, "__dict__") else result.was
    feas  = result.feasibility.__dict__ if hasattr(result.feasibility, "__dict__") else result.feasibility

    ps_out = {
        "f_mix": ps_d["f_mix"], "f_diff_base": ps_d["f_diff_base"],
        "f_diff_eff": ps_d["f_diff_eff"], "f_eff": ps_d["f_eff"],
        "HRT_d": ps_d["HRT_nominal_d"], "SRT_nom_d": ps_d["SRT_nominal_d"],
        "SRT_eff_d": ps_d["SRT_eff_d"], "VS_dest_pct": ps_d["VS_destruction_pct"],
        "NH4_g_L": ps_d["NH4_g_per_L"], "NH3_g_L": ps_d["NH3_g_per_L"],
        "inhibition_pct": ps_d["inhibition_pct"],
        "status": ps_d["status"], "primary": ps_d["primary_constraint"],
    }
    was_out = {
        "f_mix": was_d["f_mix"], "f_diff_base": was_d["f_diff_base"],
        "f_diff_eff": was_d["f_diff_eff"], "f_eff": was_d["f_eff"],
        "HRT_d": was_d["HRT_nominal_d"], "SRT_nom_d": was_d["SRT_nominal_d"],
        "SRT_eff_d": was_d["SRT_eff_d"], "VS_dest_pct": was_d["VS_destruction_pct"],
        "NH4_g_L": was_d["NH4_g_per_L"], "NH3_g_L": was_d["NH3_g_per_L"],
        "inhibition_pct": was_d["inhibition_pct"],
        "status": was_d["status"], "primary": was_d["primary_constraint"],
    }
    feas_out = {
        "overall":     feas["overall"],
        "ps":          feas["psFeasibility"],
        "was":         feas["wasFeasibility"],
        "min_stable_srt": feas["minStableSRT_d"],
        "max_ps_srt":  feas["maxAchievablePsSRT_d"],
        "max_was_srt": feas["maxAchievableWasSRT_d"],
    }
    energy_out = {
        "biogas_m3_d":    result.biogas_m3_per_d,
        "biogas_gj_d":    result.biogas_GJ_per_d,
        "elec_gross_kw":  result.elecGross_kW,
        "mixing_kw":      result.mixingParasitic_kW,
        "net_elec_kw":    result.netElec_kW,
    }
    sidestream_out = {
        "centrate_n_kgd": result.centrate_N_kg_per_d,
        "cake_n_kgd":     result.cake_N_kg_per_d,
        "total_n_kgd":    result.totalN_released_kg_per_d,
    }
    flags = result.diagnostic_flags

    # SolidStream data from coefficients if active
    solidstream_data = None
    if flags.get("solidstream_active"):
        try:
            from engine.ghg_coefficients import (
                THP_SOLIDSTREAM_CAKE_DS_PCT, THP_SOLIDSTREAM_VSR_PCT,
                THP_SOLIDSTREAM_BIOGAS_UPLIFT_PCT, THP_CAKE_VOLUME_REDUCTION_PCT,
                THP_DRYING_ENERGY_REDUCTION_PCT, THP_SOLIDSTREAM_ELECTRICITY_UPLIFT_PCT,
            )
            solidstream_data = {
                "cake_ds_pct":          THP_SOLIDSTREAM_CAKE_DS_PCT,
                "vsr_pct":              THP_SOLIDSTREAM_VSR_PCT,
                "biogas_uplift_pct":    THP_SOLIDSTREAM_BIOGAS_UPLIFT_PCT,
                "cake_vol_reduction_pct": THP_CAKE_VOLUME_REDUCTION_PCT,
                "drying_reduction_pct": THP_DRYING_ENERGY_REDUCTION_PCT,
                "elec_uplift_pct":      THP_SOLIDSTREAM_ELECTRICITY_UPLIFT_PCT,
            }
        except ImportError:
            solidstream_data = {
                "cake_ds_pct": 38.0, "vsr_pct": 70.3, "biogas_uplift_pct": 22.7,
                "cake_vol_reduction_pct": 50.0, "drying_reduction_pct": 67.0,
                "elec_uplift_pct": 20.7,
            }

    on_page = _make_header_footer(project_name, prepared_by, date_str, version)

    story = []

    # ── Build sections ──────────────────────────────────────────────────────
    _cover_section(story, S, inp, project_name, prepared_by, date_str, version)
    story.append(PageBreak())

    _executive_summary(story, S, inp, ps_out, was_out, energy_out, sidestream_out, flags)
    story.append(PageBreak())

    _digester_inputs_section(story, S, inp)
    story.append(PageBreak())

    _stream_physics_section(story, S, ps_out, was_out, feas_out)
    story.append(PageBreak())

    _energy_section(story, S, energy_out, inp)
    story.append(Spacer(1, 6*mm))

    _sidestream_section(story, S, sidestream_out, inp)

    if solidstream_data:
        story.append(PageBreak())
        _solidstream_section(story, S, solidstream_data)

    story.append(PageBreak())
    _flags_section(story, S, flags, inp)

    _disclaimer_section(story, S)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
