"""
engine/tier1_report.py
BioPoint V1 — Tier 1 Consulting Report Builder.
ph2o Consulting — v25B02
ReportLab A4, max 50pp excl appendices.
"""
from __future__ import annotations
from io import BytesIO
from datetime import date
from typing import List, Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.platypus.tableofcontents import TableOfContents

try:
    from engine.tier1_data import (
        Tier1ReportData, CAPEX_BANDS, CAPEX_STARS, narrative_feed,
        narrative_comparison_executive, narrative_ghg, narrative_next_steps,
    )
except ImportError:
    from tier1_data import (
        Tier1ReportData, CAPEX_BANDS, CAPEX_STARS, narrative_feed,
        narrative_comparison_executive, narrative_ghg, narrative_next_steps,
    )

# ── Brand colours ─────────────────────────────────────────────────────────
PH2O_BLUE   = colors.HexColor("#1a3a5c")
PH2O_MID    = colors.HexColor("#0077b6")
PH2O_TEAL   = colors.HexColor("#2e86ab")
PH2O_LIGHT  = colors.HexColor("#e8f4f8")
PH2O_ACCENT = colors.HexColor("#48cae4")
SAFE_GREEN  = colors.HexColor("#1b5e20")
WARN_AMBER  = colors.HexColor("#e65100")
FAIL_RED    = colors.HexColor("#b71c1c")
GREY_LIGHT  = colors.HexColor("#f5f5f5")
GREY_RULE   = colors.HexColor("#cccccc")
WHITE       = colors.white
BLACK       = colors.black

# ── Page geometry ─────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN        = 22*mm
CONTENT_W     = PAGE_W - 2*MARGIN
FOOTER_Y      = 12*mm
VERSION       = "v25B02"

# ── Styles ────────────────────────────────────────────────────────────────

def _styles():
    s = {}
    base = ParagraphStyle

    s["cover_title"] = base("cover_title",
        fontName="Helvetica-Bold", fontSize=26, leading=32,
        textColor=WHITE, spaceAfter=6)
    s["cover_sub"] = base("cover_sub",
        fontName="Helvetica", fontSize=13, leading=18,
        textColor=PH2O_ACCENT, spaceAfter=4)
    s["cover_meta"] = base("cover_meta",
        fontName="Helvetica", fontSize=10, leading=14,
        textColor=WHITE, spaceAfter=3)

    s["h1"] = base("h1",
        fontName="Helvetica-Bold", fontSize=14, leading=18,
        textColor=PH2O_BLUE, spaceBefore=14, spaceAfter=4)
    s["h2"] = base("h2",
        fontName="Helvetica-Bold", fontSize=11, leading=14,
        textColor=PH2O_BLUE, spaceBefore=8, spaceAfter=3)
    s["h3"] = base("h3",
        fontName="Helvetica-Bold", fontSize=10, leading=13,
        textColor=PH2O_MID, spaceBefore=6, spaceAfter=2)

    s["body"] = base("body",
        fontName="Helvetica", fontSize=9.5, leading=14,
        textColor=BLACK, spaceBefore=3, spaceAfter=4,
        alignment=TA_JUSTIFY)
    s["body_bold"] = base("body_bold",
        fontName="Helvetica-Bold", fontSize=9.5, leading=14,
        textColor=BLACK, spaceBefore=3, spaceAfter=4)
    s["small"] = base("small",
        fontName="Helvetica", fontSize=8.5, leading=12,
        textColor=colors.HexColor("#546e7a"), spaceAfter=3,
        alignment=TA_JUSTIFY)
    s["caption"] = base("caption",
        fontName="Helvetica-Oblique", fontSize=8, leading=11,
        textColor=colors.HexColor("#78909c"), spaceAfter=2)

    s["cell"]    = base("cell",    fontName="Helvetica",      fontSize=8.5, leading=11)
    s["cell_b"]  = base("cell_b",  fontName="Helvetica-Bold", fontSize=8.5, leading=11)
    s["cell_hdr"]= base("cell_hdr",fontName="Helvetica-Bold", fontSize=9,   leading=12,
                         textColor=WHITE)
    s["bullet"]  = base("bullet",
        fontName="Helvetica", fontSize=9.5, leading=14,
        leftIndent=12, firstLineIndent=-12,
        spaceBefore=2, spaceAfter=2, alignment=TA_JUSTIFY)
    s["toc_1"]   = base("toc_1",
        fontName="Helvetica", fontSize=10, leading=14,
        textColor=PH2O_BLUE, spaceBefore=2)
    s["toc_2"]   = base("toc_2",
        fontName="Helvetica", fontSize=9, leading=13,
        leftIndent=12, textColor=BLACK, spaceBefore=1)
    return s


# ── Helpers ───────────────────────────────────────────────────────────────

def _p(text, style):
    return Paragraph(str(text), style)

def _sp(mm_val=4):
    return Spacer(1, mm_val*mm)

def _rule():
    return HRFlowable(width="100%", thickness=0.5, color=GREY_RULE, spaceAfter=4)

def _section_rule():
    return HRFlowable(width="100%", thickness=1.5, color=PH2O_BLUE, spaceAfter=6)

def _tbl(rows, col_widths, style_cmds=None, row_bgs=None):
    """Generic table builder with default styling."""
    tbl = Table(rows, colWidths=col_widths)
    cmds = [
        ("FONTSIZE",      (0,0),(-1,-1), 8.5),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("WORDWRAP",      (0,0),(-1,-1), "LTR"),
        ("GRID",          (0,0),(-1,-1), 0.3, GREY_RULE),
        # Header row
        ("BACKGROUND",    (0,0),(-1,0),  PH2O_BLUE),
        ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
    ]
    if row_bgs:
        cmds.append(("ROWBACKGROUNDS", (0,1),(-1,-1), [WHITE, GREY_LIGHT]))
    if style_cmds:
        cmds.extend(style_cmds)
    tbl.setStyle(TableStyle(cmds))
    return tbl

def P(text, S, key="cell"):
    return Paragraph(str(text), S[key])

def PH(text, S):
    return Paragraph(str(text), S["cell_b"])

def _chem(t):
    """Apply sub tags to chemical formula strings."""
    return (str(t)
        .replace("NH4-N", "NH<sub>4</sub>-N")
        .replace("NH4",   "NH<sub>4</sub>")
        .replace("NH3",   "NH<sub>3</sub>")
        .replace("CH4",   "CH<sub>4</sub>")
        .replace("CO2e",  "CO<sub>2</sub>e")
        .replace("CO2",   "CO<sub>2</sub>")
        .replace("N2O",   "N<sub>2</sub>O"))

def _capex_stars(config_id, S):
    band, desc, rank = CAPEX_BANDS.get(config_id, ("Unknown","",0))
    stars = CAPEX_STARS.get(rank, "")
    return Paragraph(f"{stars} {band}", S["cell"])

# ── Page headers/footers ──────────────────────────────────────────────────

def _make_on_page(project_name, date_str, page_type="portrait"):
    def on_page(canvas, doc):
        canvas.saveState()
        w, h = canvas._pagesize

        if doc.page > 1:
            # Header bar
            canvas.setFillColor(PH2O_BLUE)
            canvas.rect(0, h - 14*mm, w, 14*mm, fill=1, stroke=0)
            canvas.setFillColor(WHITE)
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawString(MARGIN, h - 9*mm, "BioPoint V1 — Tier 1 Options Assessment")
            canvas.setFont("Helvetica", 8)
            canvas.drawRightString(w - MARGIN, h - 9*mm,
                f"{project_name}  |  {date_str}  |  {VERSION}")

        # Footer
        canvas.setFillColor(colors.HexColor("#546e7a"))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(MARGIN, FOOTER_Y,
            "SCREENING GRADE — For Stage 1-2 options analysis only. "
            "Independent verification required before detailed design.")
        prefix = "A-" if page_type == "landscape" else ""
        canvas.drawRightString(w - MARGIN, FOOTER_Y, f"{prefix}Page {doc.page}")
        canvas.setStrokeColor(GREY_RULE)
        canvas.line(MARGIN, FOOTER_Y + 4*mm, w - MARGIN, FOOTER_Y + 4*mm)
        canvas.restoreState()
    return on_page


# ══════════════════════════════════════════════════════════════════════════
# SECTION BUILDERS
# ══════════════════════════════════════════════════════════════════════════


def _digester_heat_kw(ps_ds, ps_ts_pct, was_ds, was_ts_pct,
                      t_feed=15.0, t_digester=37.0, cp=4.18):
    """
    Digester heating demand using Cp×ΔT formula.
    Q = feed_volume_m3/day × ρ × Cp × ΔT / 86400 → kW
    Source: standard heat balance (Metcalf & Eddy 5th ed.)
    """
    ps_vol  = ps_ds  / (ps_ts_pct  / 100) if ps_ts_pct  > 0 else 0   # m³/day
    was_vol = was_ds / (was_ts_pct / 100) if was_ts_pct > 0 else 0
    total_vol = ps_vol + was_vol   # m³/day
    dt = t_digester - t_feed
    return total_vol * 1000 * cp * dt / 86400   # kW


def _centrate_heat_credit_kw(ds_total, config_id,
                              centrate_temp=77.0, t_digester=37.0, cp=4.18,
                              centrate_vol_per_tds=5.47):
    """
    SolidStream hot centrate recycle heat credit.
    Centrate ~1,200 m³/day at 219.5 tDS/day = 5.47 m³/tDS/day (Cambi memo Scenario 1).
    Q = centrate_vol × ρ × Cp × (T_centrate - T_digester) / 86400
    """
    if config_id not in ("solidstream", "expansion"):
        return 0.0
    centrate_vol = ds_total * centrate_vol_per_tds  # m³/day
    return centrate_vol * 1000 * cp * (centrate_temp - t_digester) / 86400


def _cover(story, S, d: Tier1ReportData, date_str):
    # Full-page blue cover
    story.append(_p(
        "BioPoint V1",
        ParagraphStyle("cv0", fontName="Helvetica", fontSize=11,
                       textColor=PH2O_ACCENT, spaceAfter=8)))
    story.append(_p(
        "MAD & THP Screening Assessment",
        ParagraphStyle("cv1", fontName="Helvetica-Bold", fontSize=28,
                       textColor=WHITE, spaceAfter=4, leading=34)))
    story.append(_p(
        "Mesophilic Anaerobic Digestion — THP Configuration Screening",
        ParagraphStyle("cv2", fontName="Helvetica", fontSize=13,
                       textColor=PH2O_ACCENT, spaceAfter=20, leading=17)))

    story.append(_sp(8))

    # Project details table
    meta_rows = [
        ["Project",     d.project_name],
        ["Prepared for",d.prepared_for or "—"],
        ["Prepared by", d.prepared_by],
        ["Project no.", d.project_number or "—"],
        ["Date",        date_str],
        ["Revision",    d.revision],
        ["BioPoint",    VERSION],
        ["Regulatory",  d.regulatory.get("label","—")],
    ]
    cw = [40*mm, CONTENT_W - 40*mm]
    tbl_rows = [
        [Paragraph(k, ParagraphStyle("mk", fontName="Helvetica",
                   fontSize=9, textColor=PH2O_ACCENT)),
         Paragraph(v, ParagraphStyle("mv", fontName="Helvetica-Bold",
                   fontSize=9, textColor=WHITE))]
        for k, v in meta_rows
    ]
    tbl = Table(tbl_rows, colWidths=cw)
    tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 4),
        ("LINEBELOW",     (0,0),(-1,-2), 0.3, colors.HexColor("#2e86ab")),
    ]))
    story.append(tbl)

    story.append(_sp(10))

    # Scope badge
    avail = d.available
    scope_items = []
    if avail.get("mad"):            scope_items.append("MAD Analyser")
    if avail.get("comparison"):     scope_items.append("Config Comparison")
    if avail.get("pathway_rankings"):scope_items.append("Pathway Rankings")
    if avail.get("drying"):         scope_items.append("Drying & Coupling")
    if avail.get("its_pfas"):       scope_items.append("ITS & PFAS")
    if avail.get("pyrolysis"):      scope_items.append("Pyrolysis")
    if avail.get("carbon_ghg"):     scope_items.append("Carbon & GHG")

    story.append(_p(
        "Analyses included: " + "  |  ".join(scope_items),
        ParagraphStyle("scope", fontName="Helvetica", fontSize=8.5,
                       textColor=PH2O_ACCENT, spaceAfter=4)))

    story.append(_sp(6))
    story.append(_p(
        "SCREENING GRADE — Stage 1-2 options analysis only. "
        "Not suitable for detailed design, procurement, or regulatory submission "
        "without independent engineering verification.",
        ParagraphStyle("disc", fontName="Helvetica-Oblique", fontSize=8,
                       textColor=colors.HexColor("#90caf9"), spaceAfter=4)))
    story.append(_sp(3))
    story.append(_p(
        "Scope note: This report assesses mesophilic anaerobic digestion and "
        "thermal hydrolysis (THP) variants only. It does not assess pyrolysis, "
        "incineration, composting, drying-only, or gasification as stand-alone "
        "options. A separate Tier 1 biosolids strategy assessment is required "
        "for full options coverage.",
        ParagraphStyle("scope_note", fontName="Helvetica-Oblique", fontSize=7.5,
                       textColor=colors.HexColor("#90caf9"), spaceAfter=4)))



def _executive_decision_matrix(story, S, d: Tier1ReportData, section_num: int):
    """One-page executive decision matrix — at-a-glance summary."""
    story.append(_p(f"{section_num}. Executive Decision Matrix", S["h1"]))
    story.append(_section_rule())
    story.append(_p(
        "This matrix provides a rapid at-a-glance comparison across the criteria that matter "
        "most to Melbourne Water. It is a summary only — refer to the detailed sections for "
        "full supporting analysis and caveats.",
        S["body"]))
    story.append(_sp(3))

    if not d.cmp_result:
        return

    result  = d.cmp_result
    configs = [result.configs[k] for k in result.included_ids]

    # Cell helpers
    def tick(yes, uncertain=False):
        if uncertain:
            return Paragraph("?", ParagraphStyle("unk", parent=S["cell_b"],
                             textColor=colors.HexColor("#f57f17"), alignment=1))
        col = SAFE_GREEN if yes else FAIL_RED
        txt = "✓" if yes else "✗"
        if yes is None:
            col = colors.HexColor("#f57f17"); txt = "?"
        return Paragraph(txt, ParagraphStyle("t", parent=S["cell_b"],
                         textColor=col, alignment=1))

    def score_cell(v):
        """Relative rating bar."""
        stars = "●" * v + "○" * (4-v)
        col = [FAIL_RED, colors.HexColor("#e65100"),
               colors.HexColor("#f9a825"), SAFE_GREEN][v-1]
        return Paragraph(stars, ParagraphStyle("sc", parent=S["cell"],
                         textColor=col, alignment=1))

    P2 = lambda t, bold=False, center=False: Paragraph(str(t),
        ParagraphStyle("mx", parent=S["cell_b"] if bold else S["cell"],
                       alignment=1 if center else 0))
    PH2 = lambda t: Paragraph(str(t), ParagraphStyle("mxh", parent=S["cell_hdr"],
                               alignment=1))

    # Build rows
    hdr = [Paragraph("Criterion", S["cell_hdr"])] +           [PH2(cr.config_label.replace("\n"," ")) for cr in configs]

    criteria = []

    # Class A compliance
    row = [P2("EPA Vic Class A compliance")]
    for cr in configs:
        row.append(tick(getattr(cr,"class_a_achieved", getattr(cr,"class_a",False))))
    criteria.append(row)

    # HRT compliant
    row = [P2("HRT ≥15d (SolidStream basis)")]
    for cr in configs:
        if cr.config_id == "base":          row.append(tick(True))
        elif cr.config_id == "solidstream": row.append(tick(False))
        elif cr.config_id == "expansion":   row.append(tick(None))  # ? = marginal 15.1d
        else:                               row.append(tick(None))
    criteria.append(row)

    # CAPEX relative
    row = [P2("Capital cost (lower = better)")]
    for cr in configs:
        stars = {"base":4,"recup":3,"solidstream":2,"pre_thp":1,"expansion":1}.get(cr.config_id,2)
        row.append(score_cell(stars))
    criteria.append(row)

    # OPEX relative (lower total = better)
    base_opex = result.configs.get("base")
    max_opex  = max(cr.opex_total_per_yr for cr in configs)
    min_opex  = min(cr.opex_total_per_yr for cr in configs)
    row = [P2("Operating cost (lower = better)")]
    for cr in configs:
        rng = max_opex - min_opex if max_opex != min_opex else 1
        stars = max(1, min(4, round(4 - 3*(cr.opex_total_per_yr - min_opex)/rng)))
        row.append(score_cell(stars))
    criteria.append(row)

    # GHG (complex — note uncertainty)
    row = [P2("Net GHG (central estimate)")]
    min_ghg = min(cr.net_ghg_kg_co2e_per_d for cr in configs)
    max_ghg = max(cr.net_ghg_kg_co2e_per_d for cr in configs)
    for cr in configs:
        rng = max_ghg - min_ghg if max_ghg != min_ghg else 1
        stars = max(1, min(4, round(4 - 3*(cr.net_ghg_kg_co2e_per_d - min_ghg)/rng)))
        row.append(score_cell(stars))
    criteria.append(row)

    # Thermal treatment readiness
    row = [P2("Thermal treatment ready (38%DS)")]
    for cr in configs:
        row.append(tick(cr.cake_ds_pct >= 38))
    criteria.append(row)

    # PFAS resilience (land application eliminated with thermal path)
    row = [P2("PFAS resilience (THP → thermal path)")]
    for cr in configs:
        row.append(tick(getattr(cr,"class_a_achieved", getattr(cr,"class_a",False))))  # THP options enable thermal treatment
    criteria.append(row)

    # Retrofit compatibility
    row = [P2("Retrofit compatible (no new digesters)")]
    for cr in configs:
        row.append(tick(cr.config_id in ("base","recup","solidstream")))
    criteria.append(row)

    # Load growth headroom (>15d HRT with growth to 164 tDS/day)
    row = [P2("Load growth headroom (60k tDS/yr)")]
    for cr in configs:
        if cr.config_id == "base":
            row.append(tick(True))   # more HRT headroom
        elif cr.config_id == "solidstream":
            row.append(tick(False))  # HRT drops to ~11d at growth load
        elif cr.config_id in ("expansion","pre_thp"):
            row.append(tick(True))
        else:
            row.append(tick(None))
    criteria.append(row)

    # Confidence level
    row = [P2("Evidence confidence")]
    for cr in configs:
        conf = {"base":"High","solidstream":"Medium\n(vendor data)",
                "pre_thp":"Low\n(literature)", "expansion":"Medium\n(vendor data)"}.get(cr.config_id,"—")
        col  = {"High": SAFE_GREEN, "Medium\n(vendor data)": colors.HexColor("#f57f17"),
                "Low\n(literature)": FAIL_RED}.get(conf, BLACK)
        row.append(Paragraph(conf, ParagraphStyle("cf", parent=S["cell"],
                              textColor=col, alignment=1, fontSize=8)))
    criteria.append(row)

    # Weighted score
    row = [P2("Weighted score (/100)", bold=True)]
    for cr in configs:
        is_w = cr.config_id == result.winner_id
        col  = SAFE_GREEN if is_w else PH2O_BLUE
        row.append(Paragraph(f"{cr.weighted_score:.0f}", ParagraphStyle("ws",
                              parent=S["cell_b"], textColor=WHITE,
                              alignment=1, fontSize=12)))
    criteria.append(row)

    n = len(configs)
    cw_l = 62*mm; cw_c = (CONTENT_W - cw_l) / n
    tbl_rows = [hdr] + criteria
    tbl = Table(tbl_rows, colWidths=[cw_l] + [cw_c]*n)
    ts  = TableStyle([
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("GRID",          (0,0),(-1,-1), 0.3, GREY_RULE),
        ("BACKGROUND",    (0,0),(-1,0),  PH2O_BLUE),
        ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0,1),(-1,-2), [WHITE, GREY_LIGHT]),
        # Winner column header highlight
    ])
    # Highlight winner column
    winner_col = result.included_ids.index(result.winner_id) + 1 if result.winner_id in result.included_ids else 0
    if winner_col:
        ts.add("BACKGROUND", (winner_col,1), (winner_col,-1), colors.HexColor("#f0f7f0"))
    # Score row
    ts.add("BACKGROUND", (0, len(tbl_rows)-1), (-1, len(tbl_rows)-1), PH2O_BLUE)
    ts.add("TEXTCOLOR",  (0, len(tbl_rows)-1), (-1, len(tbl_rows)-1), WHITE)
    ts.add("FONTNAME",   (0, len(tbl_rows)-1), (-1, len(tbl_rows)-1), "Helvetica-Bold")
    if winner_col:
        ts.add("BACKGROUND", (winner_col, len(tbl_rows)-1), (winner_col,-1),
               SAFE_GREEN)
    tbl.setStyle(ts)
    story.append(tbl)
    story.append(_sp(2))
    story.append(_p(
        "✓ = meets criterion  ✗ = does not meet  ? = marginal / subject to confirmation. "
        "GHG uses central screening estimate (1.5% fugitive CH4) — refer to sensitivity analysis. "
        "Shaded column = recommended configuration under current driver weightings.",
        S["caption"]))


def _exec_summary(story, S, d: Tier1ReportData, section_num: int):
    story.append(_p(f"{section_num}. Executive Summary", S["h1"]))
    story.append(_section_rule())

    result = d.cmp_result
    if not result:
        story.append(_p("Config Comparison data not available.", S["body"]))
        return

    winner = result.configs.get(result.winner_id) if result.winner_id else None
    is_tie = getattr(result, "is_tie", False)

    # Winner badge
    badge_text = (
        f"{'Effectively tied: ' if is_tie else 'Recommended configuration: '}"
        f"<b>{result.winner_label}</b>"
        + (f" — {winner.weighted_score:.0f}/100" if winner else "")
    )
    badge_col = WARN_AMBER if is_tie else SAFE_GREEN
    badge = Table(
        [[Paragraph(badge_text, ParagraphStyle("badge", fontName="Helvetica-Bold",
                    fontSize=11, textColor=WHITE, alignment=TA_CENTER))]],
        colWidths=[CONTENT_W])
    badge.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), badge_col),
        ("TOPPADDING",    (0,0),(-1,-1), 9),
        ("BOTTOMPADDING", (0,0),(-1,-1), 9),
        ("ROUNDEDCORNERS",(0,0),(-1,-1), 4),
    ]))
    story.append(badge)
    story.append(_sp(4))

    # Narrative paragraphs
    story.append(_p(narrative_comparison_executive(d), S["body"]))
    story.append(_sp(2))

    ds_total = d.ps_ds_tpd + d.was_ds_tpd
    story.append(_p(
        f"This assessment evaluates four mesophilic anaerobic digestion configurations "
        f"for a plant treating {ds_total:.1f} tDS/day across "
        f"{d.ps_volume_m3 + d.was_volume_m3:,.0f} m³ of digester volume. "
        f"The regulatory context is {d.regulatory.get('label','—')}. "
        + d.regulatory.get("class_a_req",""),
        S["body"]))
    story.append(_sp(2))

    ghg_para = narrative_ghg(d)
    if ghg_para:
        story.append(_p(ghg_para, S["body"]))
        story.append(_sp(2))

    # Decision summary table
    story.append(_p("Key findings at a glance", S["h2"]))
    configs = [result.configs[k] for k in result.included_ids]
    base_cr = result.configs.get("base")

    hdr = [PH("Configuration", S), PH("Score /100", S), PH("Biosolids", S),
           PH("OPEX vs base", S), PH("CAPEX band", S), PH("Heat self-suff.", S)]
    rows = [hdr]
    for cr in configs:
        is_w = cr.config_id == result.winner_id
        opex_delta = ""
        if base_cr and cr.config_id != "base":
            delta = base_cr.opex_total_per_yr - cr.opex_total_per_yr
            opex_delta = f"{'−' if delta > 0 else '+'}${abs(delta)/1000:.0f}k/yr"
        elif cr.config_id == "base":
            opex_delta = f"${cr.opex_total_per_yr/1000:.0f}k/yr (base)"

        heat_ok = getattr(cr, "heat_self_sufficient", True)
        thp = cr.config_id in ("pre_thp","solidstream")
        heat_str = ("Yes ✓" if heat_ok else "No — boiler reqd") if thp else "N/A"

        lbl_style = ParagraphStyle("ew", parent=S["cell_b"],
                    textColor=SAFE_GREEN) if is_w else S["cell_b"]
        rows.append([
            Paragraph(("★ " if is_w else "") + cr.config_label, lbl_style),
            P(f"{cr.weighted_score:.0f}", S),
            P("Class A" if getattr(cr,"class_a_achieved", getattr(cr,"class_a",False)) else "Class B", S),
            P(opex_delta, S),
            _capex_stars(cr.config_id, S),
            P(heat_str, S),
        ])

    cw = [52*mm, 20*mm, 22*mm, 32*mm, 32*mm, CONTENT_W-158*mm]
    t = _tbl(rows, cw, row_bgs=True)
    story.append(t)
    story.append(_sp(2))
    story.append(_p(
        "CAPEX band: ★☆☆☆ Minimal | ★★☆☆ Low | ★★★☆ Moderate-High | ★★★★ High. "
        "No cost estimates are provided — CAPEX bands are relative indicators only. "
        "Vendor quotation required for detailed CAPEX.",
        S["caption"]))


def _project_context(story, S, d: Tier1ReportData, section_num: int):
    story.append(_p(f"{section_num}. Project Context & Constraints", S["h1"]))
    story.append(_section_rule())

    # Feed characterisation narrative
    story.append(_p("Feed Characterisation", S["h2"]))
    story.append(_p(narrative_feed(d), S["body"]))
    story.append(_sp(3))

    # Feed data table
    P2 = lambda t: Paragraph(_chem(str(t)), S["cell"])
    rows = [
        [PH("Parameter", S), PH("Primary Sludge (PS)", S), PH("Waste Activated Sludge (WAS)", S)],
        [P2("Digester volume (m³)"),  P2(f"{d.ps_volume_m3:,.0f}"),  P2(f"{d.was_volume_m3:,.0f}")],
        [P2("Dry solids (tDS/day)"),  P2(f"{d.ps_ds_tpd:.1f}"),      P2(f"{d.was_ds_tpd:.1f}")],
        [P2("Feed TS%"),              P2(f"{d.ps_ts_pct:.1f}%"),      P2(f"{d.was_ts_pct:.1f}%")],
        [P2("Volatile solids (% DS)"),P2(f"{d.ps_vs_pct:.1f}%"),      P2(f"{d.was_vs_pct:.1f}%")],
        [P2("Nitrogen content (% DS)"),P2(f"{d.ps_n_pct:.1f}%"),     P2(f"{d.was_n_pct:.1f}%")],
    ]
    cw = [65*mm, (CONTENT_W-65*mm)/2, (CONTENT_W-65*mm)/2]
    story.append(_tbl(rows, cw, row_bgs=True))
    story.append(_sp(4))

    # Regulatory context
    story.append(_p("Regulatory Context", S["h2"]))
    reg = d.regulatory
    story.append(_p(reg.get("class_a_req",""), S["body"]))
    story.append(_sp(2))

    if reg.get("stockpile"):
        story.append(_p(reg["stockpile"], S["body"]))
        story.append(_sp(2))

    if reg.get("n_discharge"):
        story.append(_p(reg["n_discharge"], S["body"]))
        story.append(_sp(2))

    # Client context if provided
    if d.client_context:
        story.append(_p("Project Background", S["h2"]))
        story.append(_p(d.client_context, S["body"]))


def _assessment_framework(story, S, d: Tier1ReportData, section_num: int):
    story.append(_p(f"{section_num}. Assessment Framework", S["h1"]))
    story.append(_section_rule())
    story.append(_p(
        "BioPoint V1 is a screening-grade decision support engine developed by ph2o Consulting. "
        "It evaluates anaerobic digestion configurations against eight project drivers using "
        "a weighted ranking methodology. All outputs are intended for Stage 1-2 options "
        "analysis and preliminary business case development. They are not suitable for "
        "detailed process design, procurement documentation, regulatory submission, or "
        "contract pricing without independent engineering verification.",
        S["body"]))
    story.append(_sp(3))

    story.append(_p("Scoring Methodology", S["h2"]))
    story.append(_p(
        "Each configuration is scored 1-4 against eight drivers, where 4 = best among "
        "configurations compared and 1 = worst. Drivers are weighted 1-5 (1 = low importance, "
        "5 = critical project driver). The weighted total score is calculated as: "
        "Σ(rank × weight) / (4 × Σweights) × 100, giving a range of 25-100. "
        "Scores are relative — adding or removing configurations changes the rankings.",
        S["body"]))
    story.append(_sp(3))

    story.append(_p("CAPEX Approach", S["h2"]))
    story.append(_p(
        "Capital cost estimates are not provided in this report. At screening grade, "
        "CAPEX figures carry ±40-60% uncertainty and are strongly site-dependent. "
        "Instead, configurations are assigned a CAPEX band (Minimal / Low / Moderate-High / High) "
        "reflecting the relative capital intensity. Vendor quotation and site-specific "
        "civil assessment are required before any CAPEX estimate can be produced.",
        S["body"]))
    story.append(_sp(3))

    # Driver summary table
    story.append(_p("Project Driver Weightings Applied", S["h2"]))
    if d.cmp_result:
        try:
            from engine.mad_compare import DRIVER_LABELS, DRIVER_DESCRIPTIONS, DRIVER_IDS
        except ImportError:
            from mad_compare import DRIVER_LABELS, DRIVER_DESCRIPTIONS, DRIVER_IDS
        weights = d.cmp_result.driver_weights
        rows = [[PH("Driver", S), PH("Weight", S), PH("Description", S)]]
        for drv in DRIVER_IDS:
            w = weights.get(drv, 3)
            filled = ("+" * w).ljust(5, "-")
            desc = (DRIVER_DESCRIPTIONS.get(drv,"")
                    .replace("NH4","NH<sub>4</sub>").replace("CO2e","CO<sub>2</sub>e")
                    .replace("CH4","CH<sub>4</sub>").replace("N2O","N<sub>2</sub>O"))
            rows.append([
                P(DRIVER_LABELS.get(drv,drv).replace("NH4","NH<sub>4</sub>"), S),
                P(f"{w}/5  [{filled}]", S),
                Paragraph(desc, S["cell"]),
            ])
        cw = [42*mm, 24*mm, CONTENT_W-66*mm]
        story.append(_tbl(rows, cw,
            [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))


def _mad_performance(story, S, d: Tier1ReportData, section_num: int):
    story.append(_p(f"{section_num}. Digester Performance Assessment", S["h1"]))
    story.append(_section_rule())
    story.append(_p(
        "This section summarises the MAD engine physics results for all assessed "
        "configurations. The engine computes VS destruction, biogas production, "
        "NH3 inhibition risk, energy balance, and sidestream nitrogen loads using "
        "first-principles kinetic modelling (Hansen 1998, Wu 2010).",
        S["body"]))
    story.append(_sp(3))

    if not d.cmp_result:
        story.append(_p("Comparison data not available.", S["body"]))
        return

    result = d.cmp_result
    configs = [result.configs[k] for k in result.included_ids]

    # Performance comparison table
    story.append(_p("Configuration Performance Summary", S["h2"]))

    def fmt(v, dp=1, suffix=""):
        return f"{v:.{dp}f}{suffix}" if v is not None else "—"

    hdr = [PH("Parameter", S)] + [PH(cr.config_label, S) for cr in configs]
    rows_data = [
        ("Biogas (m³/day)",       [f"{cr.biogas_m3_per_d:,.0f}" for cr in configs]),
        ("Biogas uplift vs base", ["—" if cr.config_id=="base" else
                                   f"{getattr(cr,"biogas_uplift_pct",0.0):+.1f}%" for cr in configs]),
        ("PS VS destruction (%)", [fmt(getattr(cr,"ps_vsr_pct",  cr.vsr_pct)) for cr in configs]),
        ("WAS VS destruction (%)",[fmt(getattr(cr,"was_vsr_pct", cr.vsr_pct)) for cr in configs]),
        ("CHP gross (kW)",        [f"{cr.elec_gross_kw:,.0f}" for cr in configs]),
        ("Net electricity (kW)",  [f"{cr.elec_net_kw:,.0f}" for cr in configs]),
        ("Net electricity (MWh/yr)",[f"{cr.elec_net_kw * 8760 * result.site.chp_avail_pct/100 /1000:,.0f}"
                                     for cr in configs]),
        ("Cake DS%",              [fmt(cr.cake_ds_pct, dp=0, suffix="%") for cr in configs]),
        ("Wet cake (t/day)",      [fmt(cr.wet_cake_t_per_day) for cr in configs]),
        ("Pathogen class",        ["Class A" if getattr(cr,"class_a_achieved", getattr(cr,"class_a",False)) else "Class B" for cr in configs]),
        ("Centrate NH4-N (kg/day)",[fmt(cr.centrate_nh4_kg_per_d, dp=0) for cr in configs]),
        ("Digester HRT (days)",    [fmt(getattr(cr,"hrt_days", (getattr(cr,"hrt_ps_d",0)+getattr(cr,"hrt_was_d",0))/2), dp=1) for cr in configs]),
        ("CHP electricity — gross\n(Cambi basis MWhe/yr)",
         [f"{cr.elec_gross_kw * 8760 / 1000:,.0f}" for cr in configs]),
        ("Heat self-sufficient",  [("Yes" if getattr(cr,"heat_self_sufficient",True)
                                    else "No") if cr.config_id in ("pre_thp","solidstream")
                                   else "N/A" for cr in configs]),
    ]
    n = len(configs)
    cw_l = 62*mm
    cw_c = (CONTENT_W - cw_l) / n
    rows = [hdr]
    for label, vals in rows_data:
        rows.append([Paragraph(_chem(label), S["cell"])] +
                    [Paragraph(str(v), S["cell"]) for v in vals])
    story.append(_tbl(rows, [cw_l] + [cw_c]*n,
        [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "All performance figures are screening-grade ±15% (energy) and ±20% (sidestream). "
        "SolidStream dewatering performance (≥38% DS, Class A) is vendor-estimated "
        "(Cambi Melbourne ETP memo, May 2026).",
        S["caption"]))
    story.append(_sp(4))

    # HRT calculation transparency box
    story.append(_p("Hydraulic Retention Time — Calculation Basis", S["h2"]))
    story.append(_p(
        "HRT is calculated as digester volume divided by the total hydraulic loading "
        "to the digesters. For SolidStream configurations, the hot centrate recycle "
        "(1,233 m³/day at 3.8%DS, 76.8°C from Cambi Scenario 1) returns to the digester "
        "inlet, increasing the total hydraulic load and reducing effective HRT.",
        S["body"]))
    story.append(_sp(2))

    if d.cmp_result and d.cmp_result.site:
        site = d.cmp_result.site
        ds   = site.ps_ds_tpd + site.was_ds_tpd
        # Feed TS% (mixed, from Cambi: 6.2% Scenario 1)
        # Use Cambi stated mixed TS% (6.2% Scenario 1) — NOT weighted average of ps/was TS
        # Weighted TS% gives wrong combined volume; Cambi's 6.2% is the correct design basis
        # Verified: 219.5 tDS/day / 0.062 = 3,540 m³/day → HRT 64,000/3,540 = 18.1d ✓ (Cambi 18.1d)
        CAMBI_MIXED_TS_PCT = 6.2  # Cambi Scenario 1 design basis (recuperative thickening)
        q_feed = ds / (CAMBI_MIXED_TS_PCT/100)   # m³/day feed = 3,540
        # Centrate recycle adds hydraulic load to digesters (Cambi: 1,233 m³/day at 219.5 tDS/day)
        centrate_recycle = 1233.0 * (ds / 219.5)  # scaled proportionally
        q_ss   = q_feed + centrate_recycle         # total Q for SolidStream
        vol_base = site.ps_volume_m3 + site.was_volume_m3  # 64,000 m³
        vol_exp  = vol_base + 8000   # 72,000 m³ with 9th digester

        P2 = lambda t: Paragraph(str(t), S["cell"])
        PH2 = lambda t: Paragraph(str(t), S["cell_b"])
        hrt_rows = [
            [PH2("Parameter"), PH2("Value"), PH2("Notes")],
            [P2("Total dry solids (tDS/day)"), P2(f"{ds:.1f}"), P2("Cambi Scenario 1")],
            [P2("Mixed feed TS%"), P2(f"{CAMBI_MIXED_TS_PCT:.1f}% (Cambi design basis)"), P2("Stated in Cambi memo p.10 — recuperative thickening scenario")],
            [P2("Feed flow Q (m³/day)"), P2(f"{q_feed:,.0f}"),
             P2(f"= {ds:.1f} tDS/day ÷ {CAMBI_MIXED_TS_PCT/100:.3f}")],
            [P2("Centrate recycle (SolidStream)"), P2(f"{centrate_recycle:,.0f}"),
             P2("Cambi Scenario 1: 1,233 m³/day at 3.8%DS, 76.8°C")],
            [P2("Total Q with SS centrate recycle"), P2(f"{q_ss:,.0f}"),
             P2("= Feed + centrate recycle")],
            [P2("HRT — Conventional AD"), P2(f"{vol_base/q_feed:.1f} days"),
             P2(f"= {vol_base:,} m³ ÷ {q_feed:,.0f} m³/day")],
            [P2("HRT — SolidStream (64,000 m³)"), P2(f"{vol_base/q_ss:.1f} days"),
             P2(f"= {vol_base:,} m³ ÷ {q_ss:,.0f} m³/day  ← BELOW 15d minimum")],
            [P2("HRT — SS + Expansion (72,000 m³)"), P2(f"{vol_exp/q_ss:.1f} days"),
             P2(f"= {vol_exp:,} m³ ÷ {q_ss:,.0f} m³/day  ✓ above 15d minimum")],
            [P2("Min volume for 15d HRT (SS)"), P2(f"{q_ss*15:,.0f} m³"),
             P2(f"= {q_ss:,.0f} × 15 days = {q_ss*15/8000:.1f} × 8,000 m³ digesters")],
        ]
        cw = [68*mm, 32*mm, CONTENT_W-100*mm]
        story.append(_tbl(hrt_rows, cw,
            [("WORDWRAP",(0,0),(-1,-1),"LTR"),
             ("BACKGROUND",(0,7),(2,7), colors.HexColor("#fff3e0")),  # amber highlight for SS HRT
             ("FONTNAME",(0,7),(2,7),"Helvetica-Bold")],
            row_bgs=True))
        story.append(_sp(2))
        story.append(_p(
            "Key insight: the centrate recycle is the primary driver of the HRT reduction "
            "under SolidStream. Without centrate recycle (conventional AD basis), the "
            "existing 64,000 m³ gives 18.1 days HRT. With centrate recycle adding "
            f"{centrate_recycle:,.0f} m³/day of hydraulic load, HRT falls to "
            f"{vol_base/q_ss:.1f} days — below the 15-day minimum. The additional "
            "8,000 m³ digester (72,000 m³ total) restores HRT to "
            f"{vol_exp/q_ss:.1f} days, which is marginally above the minimum. "
            "This should be verified with actual centrate volume data from Cambi "
            "process modelling at detailed design stage.",
            S["small"]))

    # Narrative for each config
    story.append(_p("Configuration Narratives", S["h2"]))
    for cr in configs:
        is_winner = cr.config_id == result.winner_id
        is_tie    = getattr(result,"is_tie",False) and cr.config_id in getattr(result,"tie_ids",[])
        prefix = "★ RECOMMENDED — " if is_winner and not is_tie else \
                 "★ TIED — " if is_tie else ""

        story.append(KeepTogether([
            _p(f"{prefix}{cr.config_label}", S["h3"]),
            _p(cr.recommendation_text or "—", S["body"]),
        ]))
        benefit_risk_rows = []
        for b in (cr.key_benefits or []):
            benefit_risk_rows.append([
                Paragraph("+ " + b, ParagraphStyle("ben", parent=S["cell"],
                          textColor=SAFE_GREEN)),
            ])
        for r in (cr.key_risks or []):
            benefit_risk_rows.append([
                Paragraph("- " + r, ParagraphStyle("ris", parent=S["cell"],
                          textColor=colors.HexColor("#b71c1c"))),
            ])
        if benefit_risk_rows:
            bt = Table(benefit_risk_rows, colWidths=[CONTENT_W])
            bt.setStyle(TableStyle([
                ("TOPPADDING",   (0,0),(-1,-1), 2),
                ("BOTTOMPADDING",(0,0),(-1,-1), 2),
                ("LEFTPADDING",  (0,0),(-1,-1), 8),
                ("WORDWRAP",     (0,0),(-1,-1), "LTR"),
            ]))
            story.append(bt)
        story.append(_sp(3))


def _opex_ghg_section(story, S, d: Tier1ReportData, section_num: int):
    story.append(_p(f"{section_num}. Operating Cost & GHG Assessment", S["h1"]))
    story.append(_section_rule())

    if not d.cmp_result:
        story.append(_p("Data not available.", S["body"]))
        return

    result  = d.cmp_result
    configs = [result.configs[k] for k in result.included_ids]
    base_cr = result.configs.get("base")

    # ── OPEX table ────────────────────────────────────────────────────────
    story.append(_p("Annual Operating Cost Comparison", S["h2"]))
    story.append(_p(
        "Annual OPEX breakdown for each configuration. All figures are screening-grade "
        "±20%. Energy cost is net — negative values represent export revenue.",
        S["body"]))
    story.append(_sp(2))

    n   = len(configs)
    cw_l= 55*mm
    cw_c= (CONTENT_W - cw_l) / n

    def fmt_opex(v):
        if v == 0: return "$0k"
        if v < 0:  return f"(${abs(v)/1000:.0f}k)"
        return f"${v/1000:.0f}k"

    hdr = [PH("OPEX Component", S)] + [PH(cr.config_label, S) for cr in configs]
    opex_rows = [hdr]
    components = [
        ("Polymer",         lambda cr: cr.opex_polymer_per_yr),
        ("Energy (net)",    lambda cr: getattr(cr,"opex_energy_per_yr",0.0)),
        ("Disposal & transport", lambda cr: cr.opex_disposal_per_yr),
        ("Sidestream N treatment", lambda cr: cr.opex_sidestream_per_yr),
        ("THP / equip. O&M", lambda cr: getattr(cr,"opex_thp_om_per_yr", getattr(cr,"opex_thp_maintenance_per_yr",0.0))),
        ("TOTAL ($/yr)",    lambda cr: cr.opex_total_per_yr),
    ]
    for label, fn in components:
        is_total = label.startswith("TOTAL")
        style = S["cell_b"] if is_total else S["cell"]
        opex_rows.append(
            [Paragraph(label, style)] +
            [Paragraph(fmt_opex(fn(cr)), style) for cr in configs]
        )

    # vs base row
    if base_cr:
        opex_rows.append(
            [P("vs Base case", S)] +
            ["—" if cr.config_id=="base" else
             Paragraph(fmt_opex(cr.opex_total_per_yr - base_cr.opex_total_per_yr), S["cell"])
             for cr in configs]
        )

    story.append(_tbl(opex_rows, [cw_l]+[cw_c]*n,
        [("WORDWRAP",(0,0),(-1,-1),"LTR"),
         ("FONTNAME",(0,len(opex_rows)-2),(-1,len(opex_rows)-2),"Helvetica-Bold"),
         ("BACKGROUND",(0,len(opex_rows)-2),(-1,len(opex_rows)-2),PH2O_LIGHT)],
        row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "Parentheses indicate credits (revenue). CAPEX-related financing costs are not included. "
        "All figures screening-grade ±20%.",
        S["caption"]))
    story.append(_sp(5))

    # ── GHG table ─────────────────────────────────────────────────────────
    story.append(_p("Greenhouse Gas Assessment", S["h2"]))
    story.append(_p(narrative_ghg(d), S["body"]))
    story.append(_sp(3))

    def fg(v):
        return f"{v:.1f}" if abs(v)<10 else f"{v:,.0f}"

    hdr2 = [PH(_chem("GHG Component (kg CO2e/day)"), S)] + \
           [PH(cr.config_label, S) for cr in configs]
    ghg_rows = [hdr2]
    ghg_data = [
        ("Scope 1a — Fugitive CH4",
         lambda cr: getattr(cr,"scope1_ch4_kg_co2e_per_d", cr.scope1_kg_co2e_per_d*0.85)),
        ("Scope 1b — N2O (land app.)",
         lambda cr: getattr(cr,"scope1_n2o_kg_co2e_per_d", cr.scope1_kg_co2e_per_d*0.15)),
        ("Scope 1c — Boiler combustion",
         lambda cr: getattr(cr,"scope1_boiler_kg_co2e_per_d", 0.0)),
        ("Scope 1 Total",
         lambda cr: cr.scope1_kg_co2e_per_d),
        ("Scope 2 — Electricity export",
         lambda cr: cr.scope2_kg_co2e_per_d),
        ("Scope 3a — Transport",
         lambda cr: getattr(cr,"scope3_transport_kg_co2e_per_d", cr.scope3_kg_co2e_per_d*0.5)),
        ("Scope 3b — Polymer upstream",
         lambda cr: getattr(cr,"scope3_polymer_kg_co2e_per_d", cr.scope3_kg_co2e_per_d*0.5)),
        ("Scope 3c — Gas upstream",
         lambda cr: getattr(cr,"scope3_gas_upstream_kg_co2e_per_d", 0.0)),
        ("Scope 3 Total",
         lambda cr: cr.scope3_kg_co2e_per_d),
        ("NET GHG (kg CO2e/day)",
         lambda cr: cr.net_ghg_kg_co2e_per_d),
        ("NET GHG (t CO2e/yr)",
         lambda cr: cr.net_ghg_t_co2e_per_yr),
    ]
    bold_rows = {4, 8, 10, 11}
    for i, (label, fn) in enumerate(ghg_data):
        st_key = "cell_b" if i in bold_rows else "cell"
        ghg_rows.append(
            [Paragraph(_chem(label), S[st_key])] +
            [Paragraph(fg(fn(cr)), S[st_key]) for cr in configs]
        )

    story.append(_tbl(ghg_rows, [cw_l]+[cw_c]*n,
        [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "Scope 1 components are independent — fugitive CH4 controls reduce Scope 1a "
        "without affecting Scope 2 credit. GWP basis: AR5, 100-year (CH4=28, N2O=265). "
        "Biogenic CO2 from biogas combustion excluded (IPCC carbon-neutral convention). "
        "Fugitive CH4 assumed 1.5% of biogas CH4 content.",
        S["caption"]))


def _heat_balance_section(story, S, d: Tier1ReportData, section_num: int):
    story.append(_p(f"{section_num}. Heat Recovery & Steam Balance", S["h1"]))
    story.append(_section_rule())
    story.append(_p(
        "CHP waste heat (jacket water + exhaust gas recovery, ~45% of fuel input) "
        "is a key differentiator between configurations. For THP options, this heat "
        "must cover the THP steam boiler demand as well as digester heating. "
        "SolidStream benefits from hot centrate recycle (~77°C back to digesters) "
        "which reduces digester heating demand, improving self-sufficiency.",
        S["body"]))
    story.append(_sp(3))

    result  = d.cmp_result
    configs = [result.configs[k] for k in result.included_ids]
    n       = len(configs)
    cw_l    = 65*mm
    cw_c    = (CONTENT_W - cw_l) / n
    chp_eff = result.site.chp_eff_pct / 100
    ds_t    = result.site.ps_ds_tpd + result.site.was_ds_tpd

    hdr = [PH("Heat Balance Component", S)] + [PH(cr.config_label, S) for cr in configs]
    rows = [hdr]

    def fkw(v): return f"{v:,.0f} kW"

    heat_data = [
        ("CHP gross electrical",  lambda cr: cr.elec_gross_kw),
        ("CHP fuel input (LHV)",  lambda cr: cr.elec_gross_kw / max(chp_eff,0.01)),
        ("CHP heat available (45%)", lambda cr: cr.elec_gross_kw / max(chp_eff,0.01) * 0.45),
        ("THP steam demand",      lambda cr: getattr(cr,"thp_steam_demand_kw",0.0)),
        ("Digester heat (gross)", lambda cr: ds_t * 26.7),
        ("Centrate heat credit",  lambda cr: ds_t * 10.5 if cr.config_id=="solidstream" else 0.0),
        ("Heat surplus / deficit",lambda cr: getattr(cr,"heat_surplus_kw",0.0)),
    ]
    for i, (label, fn) in enumerate(heat_data):
        rows.append([P(label,S)] + [P(fkw(fn(cr)),S) for cr in configs])

    # Self-sufficiency row
    suf_row = [PH("Self-sufficient?", S)]
    for cr in configs:
        ok = getattr(cr,"heat_self_sufficient",True)
        thp = cr.config_id in ("pre_thp","solidstream")
        col = SAFE_GREEN if ok else WARN_AMBER
        txt = ("Yes ✓" if ok else "No — boiler reqd") if thp else "N/A"
        suf_row.append(Paragraph(txt,
            ParagraphStyle("sf", parent=S["cell_b"], textColor=col if thp else BLACK)))
    rows.append(suf_row)

    story.append(_tbl(rows, [cw_l]+[cw_c]*n,
        [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "Self-sufficiency means no gas boiler fuel is required — "
        "Scope 1c and Scope 3c GHG are eliminated. "
        "At small plant scales (<15 tDS/day) a supplementary boiler may be needed for "
        "pre-THP at low loads. SolidStream's centrate heat recycle typically avoids this. "
        "Source: Cambi Melbourne ETP memo 20.05.2026.",
        S["small"]))






def _pfas_section(story, S, d: Tier1ReportData, section_num: int):
    """PFAS risk register."""
    story.append(_p(f"{section_num}. PFAS & Contaminant Risk Register", S["h1"]))
    story.append(_section_rule())
    story.append(_p(
        "PFAS (per- and polyfluoroalkyl substances) present a specific risk for "
        "biosolids land application. The Eastern Treatment Plant catchment includes "
        "industrial and commercial areas that may contribute PFAS-laden influent. "
        "The current biosolids classification and management strategy must be reviewed "
        "against EPA Victoria's Interim Position Statement on PFAS (2021). "
        "The long-term thermal treatment pathway is relevant to PFAS strategy, "
        "as both incineration and pyrolysis offer high-temperature destruction.",
        S["body"]))
    story.append(_sp(3))

    P2 = lambda t: Paragraph(str(t), S["cell"])
    PH2 = lambda t: Paragraph(str(t), S["cell_b"])

    pfas_rows = [
        [PH2("Risk Item"), PH2("Relevance"), PH2("Configuration impact"), PH2("Action required")],
        [P2("PFAS in biosolids"),
         P2("High — ETP catchment includes industrial sources"),
         P2("Class B land application: full PFAS risk. Class A land application: same risk unless PFAS concentrations tested."),
         P2("Commission PFAS characterisation of current biosolids before any expansion of land application.")],
        [P2("Land application restriction"),
         P2("High — EPA Vic 2021 PFAS position may restrict or prohibit land application if PFAS thresholds exceeded"),
         P2("ALL configurations using land application carry this risk. Does not differentiate THP options."),
         P2("Obtain current PFAS testing data. Assess against EPA Vic PFAS interim criteria.")],
        [P2("Thermal treatment — PFAS destruction"),
         P2("Medium — incineration >850°C destroys PFAS >99.99%. Pyrolysis >600°C effective."),
         P2("SolidStream cake at 38%DS is the optimal feedstock for incineration without pre-drying. Enables PFAS destruction at lower overall energy cost."),
         P2("If PFAS risk is confirmed, thermal treatment pathway should be accelerated.")],
        [P2("Pyrolysis char — PFAS residual"),
         P2("Medium — char from pyrolysis <550°C may retain PFAS. Higher temperatures needed for full destruction."),
         P2("If pyrolysis is selected, process temperature must be confirmed to achieve PFAS destruction."),
         P2("Specify PFAS destruction requirements in pyrolysis process tender documentation.")],
        [P2("Ash disposal — PFAS in ash"),
         P2("Low-Medium — FBF ash may concentrate some PFAS if combustion temperature and gas treatment are inadequate"),
         P2("Ash classification may restrict disposal options if PFAS concentrations are high."),
         P2("Specify PFAS monitoring in FBF design. Plan for ash characterisation and classification.")],
    ]
    cw = [40*mm, 45*mm, 50*mm, CONTENT_W-135*mm]
    story.append(_tbl(pfas_rows, cw,
        [("WORDWRAP",(0,0),(-1,-1),"LTR"),
         ("FONTSIZE",(0,0),(-1,-1),8)], row_bgs=True))
    story.append(_sp(3))
    story.append(_p(
        "PFAS does not currently differentiate between the four AD/THP configurations "
        "assessed in this report — all carry the same land application risk. "
        "However, PFAS is a strong argument for accelerating the thermal treatment "
        "pathway. SolidStream at 38%DS significantly reduces the mass of material "
        "requiring PFAS-safe disposal, and the high-DS cake is the most economic "
        "feedstock for FBF incineration. "
        "A PFAS characterisation study and disposal strategy should be commissioned "
        "in parallel with the THP assessment.",
        S["body"]))


def _sidestream_nitrogen_section(story, S, d: Tier1ReportData, section_num: int):
    """Sidestream nitrogen impact on liquid treatment train."""
    story.append(_p(f"{section_num}. Sidestream Nitrogen Impact Assessment", S["h1"]))
    story.append(_section_rule())
    story.append(_p(
        "All THP configurations increase the centrate NH4-N return load to the "
        "liquid treatment train. At the scale of Melbourne ETP (~500 ML/day), "
        "this increase is material and must be assessed against mainstream TN "
        "licence headroom, aeration capacity, and alkalinity availability. "
        "This section quantifies the impact and identifies the key risk items.",
        S["body"]))
    story.append(_sp(3))

    result = d.cmp_result
    if not result:
        story.append(_p("Data not available.", S["body"]))
        return

    configs = [result.configs[k] for k in result.included_ids]
    P2 = lambda t: Paragraph(str(t), S["cell"])
    PH2 = lambda t: Paragraph(str(t), S["cell_b"])

    # ETP mainstream reference values
    FLOW_MLD  = 500
    TN_KGD    = FLOW_MLD * 1e6 * 35 / 1e6   # 35 mg/L TN × 500 ML/day = 17,500 kg/day
    O2_PER_N  = 4.6    # kg O2 per kg NH4-N nitrified
    ALK_PER_N = 7.14   # kg CaCO3 per kg NH4-N (alkalinity consumption)

    # Centrate load comparison
    story.append(_p("Centrate NH4-N Return Load", S["h2"]))
    hdr = [PH2("Parameter")] + [PH2(cr.config_label) for cr in configs]
    rows = [hdr]
    rows.append([P2("Centrate NH4-N (kg/day)")] +
                [P2(f"{cr.centrate_nh4_kg_per_d:,.0f}") for cr in configs])
    rows.append([P2("NH4-N as % mainstream TN")] +
                [P2(f"{cr.centrate_nh4_kg_per_d / TN_KGD * 100:.1f}%")
                 for cr in configs])
    base_nh4 = result.configs.get("base", configs[0]).centrate_nh4_kg_per_d
    rows.append([P2("Increase vs base (kg/day)")] +
                [P2("—" if cr.config_id == "base" else
                    f"+{cr.centrate_nh4_kg_per_d - base_nh4:,.0f}")
                 for cr in configs])
    rows.append([P2("Additional O2 demand (t/day)")] +
                [P2("—" if cr.config_id == "base" else
                    f"+{(cr.centrate_nh4_kg_per_d - base_nh4) * O2_PER_N / 1000:.1f}")
                 for cr in configs])
    rows.append([P2("Additional alkalinity (t CaCO3/day)")] +
                [P2("—" if cr.config_id == "base" else
                    f"+{(cr.centrate_nh4_kg_per_d - base_nh4) * ALK_PER_N / 1000:.1f}")
                 for cr in configs])
    rows.append([P2("Sidestream treatment reqd?")] +
                [P2("Yes" if cr.centrate_nh4_kg_per_d / TN_KGD > 0.10 else "No")
                 for cr in configs])

    n = len(configs)
    cw_l = 65*mm; cw_c = (CONTENT_W - cw_l) / n
    story.append(_tbl(rows, [cw_l] + [cw_c]*n,
        [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        f"Mainstream TN reference: {TN_KGD:,.0f} kg N/day "
        f"({FLOW_MLD} ML/day × 35 mg/L TN, ETP estimated). "
        "Sidestream treatment triggered when centrate exceeds 10% of mainstream TN. "
        "All configurations exceed this threshold. "
        "O2 demand and alkalinity figures represent the additional load from centrate "
        "NH4-N above the conventional AD baseline.",
        S["caption"]))
    story.append(_sp(4))

    # Key risk items
    story.append(_p("Key Risk Items — Sidestream Nitrogen", S["h2"]))
    risks = [
        ("Aeration capacity",
         "SolidStream increases centrate NH4-N by +1,481 kg/day (+47%) vs conventional. "
         "At 4.6 kg O2/kg N, this requires an additional 6.8 t O2/day of aeration capacity. "
         "Confirm aeration headroom at ETP before committing to THP."),
        ("Alkalinity",
         "Nitrification of the additional centrate NH4-N consumes ~10.6 t CaCO3/day of "
         "alkalinity. If ETP alkalinity supply is tight, external dosing (lime or sodium "
         "bicarbonate) may be required — this is a material OPEX item not included in this report."),
        ("Licence headroom",
         "If the ETP licence sets a TN limit in the treated effluent, the increased centrate "
         "load reduces the buffer between actual performance and consent limit. "
         "Confirm TN licence conditions with Melbourne Water and EPA Victoria."),
        ("Sidestream treatment CAPEX",
         "If centrate NH4-N cannot be managed within the mainstream process, "
         "dedicated sidestream treatment (SHARON, ANAMMOX, or MBBR nitritation) "
         "will be required. CAPEX for a system treating 4,645 kg NH4-N/day "
         "is typically $15-40M (Class 5, ±50%). This is a significant item not "
         "captured in the CAPEX band assessment."),
        ("N2O risk",
         "High NH4-N return loads to biological treatment increase the risk of "
         "N2O formation in the bioreactor — particularly if DO or pH control is poor. "
         "This is an emerging GHG risk that should be monitored. "
         "N2O from liquid treatment is currently excluded from this assessment."),
    ]
    for title, text in risks:
        story.append(KeepTogether([
            _p(title, S["h3"]),
            _p(text, S["body"]),
            _sp(2),
        ]))

    story.append(_sp(3))
    story.append(_p("Cost Accounting Basis — No Double Counting", S["h2"]))
    story.append(_p(
        "To avoid double-counting, this report treats sidestream nitrogen costs as follows: "
        "<b>Dedicated sidestream treatment OPEX</b> (SHARON/ANAMMOX, $4/kg NH4-N) is included "
        "in the OPEX comparison table and is charged to the biosolids management budget. "
        "<b>Mainstream aeration and alkalinity cost increases</b> (from higher centrate load) "
        "are NOT included in the OPEX table — these are impacts on the liquid treatment "
        "train budget and are noted qualitatively in this section. "
        "The two costs are alternatives: if dedicated sidestream treatment is installed, "
        "the mainstream aeration impact is eliminated. If no sidestream treatment is "  
        "installed, the mainstream aeration cost applies instead. "
        "Stage 2 should confirm which approach Melbourne Water prefers.",
        S["body"]))
    story.append(_sp(3))
    story.append(_p(
        "Recommendation: commission a dedicated sidestream nitrogen impact assessment "
        "as part of Stage 2, using actual ETP TN licence conditions, aeration capacity, "
        "and alkalinity data. This should be completed before the THP configuration "
        "is confirmed.",
        S["body_bold"]))


def _ghg_sensitivity_section(story, S, d: Tier1ReportData, section_num: int):
    """GHG sensitivity analysis table."""
    story.append(_p(f"{section_num}. GHG Sensitivity Analysis", S["h1"]))
    story.append(_section_rule())
    story.append(_p(
        "The central GHG estimates presented in this report carry significant uncertainty. "
        "The most influential variables are the fugitive methane rate, N2O emission factor, "
        "and grid carbon intensity (which determines the value of CHP electricity export). "
        "The table below shows the sensitivity of key GHG components to plausible "
        "variations in these assumptions, using the Conventional AD base case as the reference. "
        "THP configurations are proportionally more sensitive to fugitive methane assumptions "
        "because they produce more biogas.",
        S["body"]))
    story.append(_sp(3))

    P2 = lambda t: Paragraph(str(t), S["cell"])
    PH2 = lambda t: Paragraph(str(t), S["cell_b"])

    # ── Table 1: Fugitive CH4 sensitivity ────────────────────────────────
    story.append(_p("Scope 1a — Fugitive CH4 Sensitivity (Conventional AD baseline)", S["h2"]))
    biogas_conv = 74163; biogas_ss = 91014
    rows = [[PH2("Fugitive rate"), PH2("Conventional AD\n(kg CO2e/day)"),
             PH2("SolidStream\n(kg CO2e/day)"), PH2("Notes")]]
    central = biogas_conv * 0.63 * 0.015 * 0.717 * 28
    for rate, note in [(0.001,"Best practice: enclosed flare, gas capture"),
                       (0.005,"Good practice: covered storage, modern CHP"),
                       (0.010,"Average: partial gas capture"),
                       (0.015,"Screening assumption (this report)"),
                       (0.030,"Poor practice: open digesters, leaking system")]:
        v_conv = biogas_conv * 0.63 * rate * 0.717 * 28
        v_ss   = biogas_ss   * 0.63 * rate * 0.717 * 28
        is_central = abs(rate-0.015)<0.001
        row = [P2(f"{rate*100:.1f}% {'← central' if is_central else ''}"),
               P2(f"{v_conv:,.0f}"),
               P2(f"{v_ss:,.0f}"),
               P2(note)]
        rows.append(row)
    cw = [30*mm, 35*mm, 35*mm, CONTENT_W-100*mm]
    tbl = _tbl(rows, cw, [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True)
    story.append(tbl)
    story.append(_sp(2))
    story.append(_p(
        "Key implication: If fugitive methane controls are upgraded from the screening "
        "assumption (1.5%) to best practice (0.1%), Scope 1a reduces by ~93% for both "
        "configurations. This is the single most effective GHG mitigation available "
        "at ETP — and it is independent of the THP configuration chosen.",
        S["small"]))
    story.append(_sp(4))

    # ── Table 2: Grid intensity sensitivity ───────────────────────────────
    story.append(_p("Scope 2 — Grid Carbon Intensity Sensitivity (SolidStream, 9,299 kWe gross)", S["h2"]))
    elec = 9299; avail = 0.88
    rows2 = [[PH2("Grid intensity"), PH2("Scope 2 credit\n(kg CO2e/day)"), PH2("Notes")]]
    for gi, note in [(0.08, "Tasmania / NZ hydro-dominant grid (2026)"),
                     (0.25, "South Australia renewable-heavy (2030 trajectory)"),
                     (0.40, "National average projected 2030"),
                     (0.60, "Victoria current (2026) ← central"),
                     (0.72, "Queensland coal-heavy grid (2026)")]:
        v = -(elec * 24 * avail / 1000 * gi)
        rows2.append([P2(f"{gi:.2f} kg CO2e/kWh {'← central' if gi==0.60 else ''}"),
                      P2(f"{v:,.0f}"),
                      P2(note)])
    cw2 = [45*mm, 40*mm, CONTENT_W-85*mm]
    story.append(_tbl(rows2, cw2, [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "As the Victorian grid decarbonises toward 2030-2040, the Scope 2 export credit "
        "will reduce in value. This does not change the recommendation but does reduce "
        "the GHG benefit of CHP electricity export over time. Biomethane injection or "
        "fuel cell pathways may become more attractive as the grid decarbonises.",
        S["small"]))
    story.append(_sp(4))

    # ── Table 3: N2O sensitivity ──────────────────────────────────────────
    story.append(_p("Scope 1b — N2O Emission Factor Sensitivity (Conventional AD, 9,457 kg cake-N/day)", S["h2"]))
    cake_n = 9457
    rows3 = [[PH2("N2O EF\n(kg N2O-N / kg N)"), PH2("Scope 1b\n(kg CO2e/day)"), PH2("Notes")]]
    for ef, note in [(0.003,"IPCC Tier 1 lower bound (arid/semi-arid soils)"),
                     (0.008,"IPCC Tier 1 low range"),
                     (0.010,"IPCC default ← central (this report)"),
                     (0.015,"IPCC Tier 1 upper range"),
                     (0.025,"High-N soils, wet conditions")]:
        v = cake_n * ef * (44/28) * 265
        rows3.append([P2(f"{ef:.3f} {'← central' if ef==0.010 else ''}"),
                      P2(f"{v:,.0f}"),
                      P2(note)])
    cw3 = [50*mm, 40*mm, CONTENT_W-90*mm]
    story.append(_tbl(rows3, cw3, [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "N2O is highly variable in practice. If biosolids are incinerated rather than "
        "land-applied, Scope 1b N2O is completely eliminated — this is one of the "
        "strongest GHG arguments for thermal treatment as the long-term endpoint. "
        "Note also that if the disposal route changes from land application to "
        "incineration or landfill, the N2O assumption no longer applies.",
        S["small"]))
    story.append(_sp(4))

    # ── Summary ─────────────────────────────────────────────────────────────
    story.append(_p("GHG Assessment Conclusions", S["h2"]))
    story.append(_p(
        "The central GHG assessment shows THP configurations have higher net GHG than "
        "conventional AD at screening grade, primarily due to increased Scope 1a fugitive "
        "methane from greater biogas production. However this result is strongly sensitive "
        "to assumptions and should not be used as a primary decision driver. "
        "Three observations are important for client decision-making:",
        S["body"]))
    story.append(_sp(2))
    for bullet in [
        "Methane capture is the dominant lever. If fugitive emissions are controlled to "
        "0.1% (best practice), Scope 1a reduces by 93% regardless of THP configuration. "
        "Melbourne Water's 2035-2040 methane-to-zero target requires this investment "
        "independently of THP.",
        "Grid decarbonisation reduces Scope 2 value. The CHP export credit will shrink "
        "as Victoria's grid decarbonises. This does not change the AD/THP recommendation "
        "but does affect the long-term energy business case.",
        "Thermal treatment eliminates Scope 1b. If biosolids move to incineration or "
        "pyrolysis, N2O from land application (currently 39,000+ kg CO2e/day) is eliminated. "
        "This is the most significant long-term GHG reduction available to Melbourne Water.",
    ]:
        story.append(_p(f"• {bullet}", S["bullet"]))
    story.append(_sp(3))
    story.append(_p(
        "A formal GHG assessment to Greenhouse Gas Protocol or ISO 14064 standards "
        "is recommended as a Stage 2 activity before a capital commitment decision.",
        S["small"]))


def _thermal_treatment_section(story, S, d: Tier1ReportData, section_num: int):
    """Long-term thermal treatment pathway — incineration and pyrolysis."""
    story.append(_p(f"{section_num}. Long-Term Biosolids Pathway — Thermal Treatment", S["h1"]))
    story.append(_section_rule())
    story.append(_p(
        "Melbourne Water's strategic objectives include net zero Scope 1 emissions by 2030 "
        "and methane emissions to zero by 2035-2040. Thermal treatment of biosolids "
        "— either incineration or pyrolysis — provides a pathway to eliminate "
        "land application entirely, removing the dependency on agricultural markets, "
        "regulatory land use restrictions, and PFAS compliance requirements. "
        "The dewatered cake quality from SolidStream (≥38%DS) is a direct enabler "
        "of cost-effective thermal treatment, as it significantly reduces the "
        "thermal energy required for either drying or direct combustion.",
        S["body"]))
    story.append(_sp(3))

    # Carbon fate table
    story.append(_p("Carbon Fate by Pathway", S["h2"]))
    story.append(_p(
        "The long-term GHG outcome depends on what happens to the carbon in biosolids. "
        "Different end-use pathways result in fundamentally different carbon fates. "
        "This is important context for Melbourne Water's net zero planning.",
        S["body"]))
    story.append(_sp(2))
    P2c = lambda t: Paragraph(str(t), S["cell"])
    PH2c = lambda t: Paragraph(str(t), S["cell_b"])
    carbon_fate_rows = [
        [PH2c("Pathway"), PH2c("Carbon outcome"), PH2c("N2O outcome"), PH2c("Net zero alignment")],
        [P2c("Land application (Class B)"),
         P2c("Partial soil carbon storage; mineralisation releases CO2 over years"),
         P2c("N2O from soil (Scope 1b — significant)"),
         P2c("Partial — dependent on soil carbon stability and N2O controls")],
        [P2c("Land application (Class A — THP)"),
         P2c("As above — same carbon fate; THP improves product quality not carbon storage"),
         P2c("N2O from soil (same basis as Class B)"),
         P2c("Partial — same land application risks remain")],
        [P2c("Incineration (FBF)"),
         P2c("Biogenic CO2 oxidised to atmosphere — IPCC carbon-neutral convention applies"),
         P2c("N2O eliminated — no land application; stack NOx managed by gas treatment"),
         P2c("Strong — eliminates land application N2O; biogenic CO2 excluded from net zero accounting")],
        [P2c("Pyrolysis"),
         P2c("~30-50% carbon retained as biochar (long-term stable); remaining as syngas/CO2"),
         P2c("N2O eliminated from land application; pyrolysis N2O minimal"),
         P2c("Strong — biochar sequesters carbon; may generate certified carbon credits (ACCUs)")],
        [P2c("Hydrothermal liquefaction (HTL)"),
         P2c("~30-40% carbon to biocrude (displaces fossil fuel); remaining to aqueous phase"),
         P2c("N2O eliminated; ammonia in aqueous phase recovered"),
         P2c("Strong — carbon utilisation as renewable fuel; P recovery potential")],
        [P2c("Conventional AD only (no thermal)"),
         P2c("Biogas carbon: biogenic CO2 + methane (fugitive risk). Cake: land application carbon fate"),
         P2c("N2O from land application at current levels"),
         P2c("Weakest — land application N2O and fugitive CH4 both remain")],
    ]
    cw_cf = [45*mm, 50*mm, 42*mm, CONTENT_W-137*mm]
    story.append(_tbl(carbon_fate_rows, cw_cf,
        [("WORDWRAP",(0,0),(-1,-1),"LTR"),("FONTSIZE",(0,0),(-1,-1),8)],
        row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "Implication for Melbourne Water: "
        "<b>Incineration provides the strongest operational and regulatory alignment</b> "
        "— eliminating land application N2O, achieving regulatory certainty, and using "
        "proven technology at this scale. "
        "<b>Pyrolysis may ultimately win the carbon argument</b> — it eliminates land "
        "application N2O AND stores 30-50% of biosolids carbon as stable biochar, "
        "potentially qualifying for carbon credits (ACCUs). The choice depends on "
        "whether Melbourne Water prioritises operational certainty (incineration) or "
        "long-term carbon sequestration value (pyrolysis). "
        "Both pathways require THP or equivalent to produce the high-DS, Class A cake "
        "that makes thermal treatment economically viable — this is THP's most "
        "important long-term role.",
        S["small"]))
    story.append(_sp(4))

    # ── Phosphorus recovery table ─────────────────────────────────────────
    story.append(_p("Phosphorus Recovery by Pathway", S["h2"]))
    story.append(_p(
        "Phosphorus is a finite, non-substitutable resource. Melbourne Water's biosolids "
        "contain significant phosphorus currently exported via land application. "
        "The thermal treatment pathway choice directly affects whether this phosphorus "
        "can be recovered and reused. As Australian fertiliser sourcing requirements "
        "evolve and struvite recovery matures, phosphorus should be an explicit "
        "criterion in the thermal treatment selection.",
        S["body"]))
    story.append(_sp(2))
    P2p = lambda t: Paragraph(str(t), S["cell"])
    PH2p = lambda t: Paragraph(str(t), S["cell_b"])
    p_rows = [
        [PH2p("Pathway"), PH2p("P recovery potential"),
         PH2p("Product form"), PH2p("Market status")],
        [P2p("Land application (Class A/B)"),
         P2p("High — all P in cake; dependent on access"),
         P2p("Organic-bound digestate; slow-release"),
         P2p("Moderate — constrained by PFAS and loading limits")],
        [P2p("Incineration (FBF)"),
         P2p("Medium-High — P concentrated in ash (~25-30% P2O5)"),
         P2p("Ash; struvite or phosphoric acid via secondary processing"),
         P2p("Growing — EU mandating P recovery; Australian market emerging")],
        [P2p("Pyrolysis"),
         P2p("High — ~80-90% P retained in biochar"),
         P2p("Biochar; directly plant-available"),
         P2p("High where biochar market exists; circular economy premium")],
        [P2p("HTL"),
         P2p("Moderate — P splits between aqueous phase and char"),
         P2p("Struvite from aqueous phase processing"),
         P2p("Moderate — additional process complexity required")],
        [P2p("AD only (land application)"),
         P2p("High — P fully retained in digestate"),
         P2p("Digestate; slow-release organic fertiliser"),
         P2p("Moderate — restricted by PFAS and nutrient loading")],
    ]
    cw_p = [44*mm, 44*mm, 44*mm, CONTENT_W-132*mm]
    story.append(_tbl(p_rows, cw_p,
        [("WORDWRAP",(0,0),(-1,-1),"LTR"),("FONTSIZE",(0,0),(-1,-1),8)],
        row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "The EU Fertilising Products Regulation (2019) requires P recovery from sludge ash "
        "above certain thresholds from 2026 — this may influence future Australian policy. "
        "Melbourne Water should include P recovery potential in the thermal treatment "
        "business case to ensure long-term circular economy alignment.",
        S["small"]))
    story.append(_sp(4))

    story.append(_sp(3))

    # Drying energy comparison
    story.append(_p("Drying Energy Comparison (to 70%DS for thermal treatment)", S["h2"]))
    story.append(_p(
        "If thermal treatment requires pre-drying to 70%DS (for pelletisation or "
        "co-incineration), the SolidStream cake requires dramatically less drying energy "
        "than conventional dewatered cake, due to the higher starting DS%.",
        S["body"]))
    story.append(_sp(2))

    P2 = lambda t: Paragraph(str(t), S["cell"])
    PH2 = lambda t: Paragraph(str(t), S["cell_b"])
    drying_rows = [
        [PH2("Parameter"), PH2("Conventional AD"), PH2("SolidStream THP"), PH2("Saving")],
        [P2("Cake DS% (pre-drying)"), P2("22%"), P2("38%"), P2("—")],
        [P2("Water evaporation (t/h)"), P2("17.0"), P2("5.6"), P2("-67%")],
        [P2("Natural gas demand (MWh LHV/yr)"), P2("148,566"), P2("48,895"), P2("-67%")],
        [P2("Dryer size (relative)"), P2("100%"), P2("33%"), P2("-67%")],
        [P2("Dried cake volume (t/yr at 70%DS)"), P2("68,093"), P2("58,063"), P2("-15%")],
    ]
    cw = [65*mm, 38*mm, 38*mm, CONTENT_W - 141*mm]
    story.append(_tbl(drying_rows, cw,
        [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "Source: Cambi Conceptual Design Memo 10590-ZME-001-7035 A01, 20 May 2026 "
        "(Scenario 1, 65%VS). The 67% reduction in drying energy and dryer capacity "
        "is one of the most significant economic benefits of SolidStream at ETP.",
        S["caption"]))
    story.append(_sp(4))

    # Incineration
    story.append(_p("Option A — Fluidised Bed Incineration", S["h2"]))
    story.append(_p(
        "Fluidised bed incineration (FBF) of dewatered biosolids cake is an established "
        "technology in Europe and Asia for large-scale biosolids management. "
        "At 38%DS, the SolidStream cake has sufficient calorific value (~8-10 MJ/kg VS) "
        "to sustain autogenous combustion without auxiliary fuel under normal conditions. "
        "The ETP SolidStream cake at 106,958 wet t/yr (38%DS) = ~40,645 tDS/yr = "
        "~30,000 t organic VS/yr at ~68%VS. "
        "At 10 MJ/kg VS: ~300,000 MWh/yr thermal energy available. "
        "A 2-3 train FBF installation at 30-50 MW thermal would be appropriate. "
        "Ash (approximately 10,000-12,000 tDS/yr) requires disposal to landfill or "
        "use as cement replacement (PFAS may restrict some end uses).",
        S["body"]))
    story.append(_sp(2))

    inc_rows = [
        [PH2("Parameter"), PH2("Value"), PH2("Notes")],
        [P2("Cake input (wet t/yr)"), P2("106,958"), P2("SolidStream Scenario 1 (Cambi)")],
        [P2("Cake DS%"), P2("38%"), P2("Vendor-confirmed (Cambi)")],
        [P2("Organic VS content"), P2("~36% of wet mass"), P2("Scenario 1: 36% VS in cake")],
        [P2("Calorific value"), P2("~8-10 MJ/kg VS"), P2("Typical for digested sludge at 38%DS")],
        [P2("Thermal energy available"), P2("~290,000 MWh/yr"), P2("Before auxiliary fuel and losses")],
        [P2("FBF capacity required"), P2("~35 MW thermal"), P2("2-3 trains, standard modular units")],
        [P2("Ash output"), P2("~11,000 t/yr"), P2("~27% of DS input; landfill or cement blend")],
        [P2("Truck movements eliminated"), P2("7-8 trucks/day"), P2("vs 15/day conventional")],
        [P2("Land application requirement"), P2("Eliminated"), P2("No biosolids product to manage")],
        [P2("EPA Victoria stockpiling"), P2("Not required"), P2("THP achieves Class A pre-incineration")],
    ]
    cw2 = [60*mm, 40*mm, CONTENT_W - 100*mm]
    story.append(_tbl(inc_rows, cw2,
        [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "Note: incineration eliminates Scope 1b N2O from land application and "
        "Scope 3a transport emissions, but introduces stack CO2 (biogenic, IPCC carbon-neutral), "
        "NOx, and potentially dioxins/furans requiring EPA-compliant stack treatment. "
        "Under controlled combustion conditions at >850°C, FBF reported destruction efficiencies "
        "can exceed 99% for most PFAS compounds; however site-specific validation and "
        "regulator acceptance remain necessary as the science is still evolving.",
        S["small"]))
    story.append(_sp(4))

    # Pyrolysis
    story.append(_p("Option B — Pyrolysis", S["h2"]))
    story.append(_p(
        "Pyrolysis (thermal decomposition at 500-700°C in the absence of oxygen) converts "
        "biosolids to biochar, pyrolysis oil, and syngas. At ETP scale it merits serious "
        "consideration alongside incineration for four reasons:",
        S["body"]))
    for bullet in [
        "<b>Carbon sequestration:</b> biochar typically retains 30-50% of input carbon "
        "in a stable form that resists decomposition for centuries to millennia. "
        "This directly supports Melbourne Water's net zero objectives and may qualify "
        "for Australian Carbon Credit Units (ACCUs) under the Emissions Reduction Fund.",
        "<b>Phosphorus recovery:</b> biochar retains phosphorus in plant-available form, "
        "supporting soil amendment markets. As fertiliser prices remain elevated, "
        "phosphorus-rich biochar from a major WWTP has emerging commercial value.",
        "<b>PFAS destruction:</b> pyrolysis above 600°C destroys PFAS under controlled "
        "conditions; site-specific validation and regulator acceptance remain necessary. "
        "PFAS-contaminated biochar may require further management.",
        "<b>Future carbon policy:</b> as Australia's carbon markets develop, biochar "
        "sequestration may attract a price premium over incineration. Early mover "
        "advantage exists if Melbourne Water establishes a biochar market pathway now.",
    ]:
        story.append(_p("• " + bullet, S["bullet"]))
    story.append(_sp(2))
    story.append(_p(
        "Key constraint: pyrolysis processes typically require ≥50%DS feed for autogenous "
        "operation. SolidStream cake at 38%DS may require supplementary pre-drying "
        "(to approximately 50-55%DS) before pyrolysis, adding capital and operating cost. "
        "Some pyrolysis processes accept 35-40%DS — this should be confirmed with "
        "prospective technology providers. Capital and operating cost per tonne processed "
        "is typically higher than incineration for the same throughput.",
        S["body"]))
    story.append(_sp(2))

    # Decision framework
    story.append(_p("Thermal Treatment Decision Framework", S["h2"]))
    story.append(_p(
        "The choice between incineration and pyrolysis depends on four factors: "
        "(1) PFAS risk profile — if PFAS concentrations are high, both options provide "
        "destruction but incineration is more established for regulatory compliance; "
        "(2) biochar market — if a viable soil amendment market exists, pyrolysis may be "
        "preferred; (3) programme and risk — incineration technology is more mature and "
        "bankable at this scale; (4) GHG accounting — pyrolysis produces biochar with "
        "long-term carbon sequestration benefits that may count toward net zero. "
        "A dedicated Tier 1 thermal treatment study should be commissioned as the next "
        "step after confirming the AD configuration.",
        S["body"]))
    story.append(_sp(3))

    # Pathway summary
    # HTL note
    story.append(_p("Hydrothermal Liquefaction (HTL) — Scope Note", S["h2"]))
    story.append(_p(
        "Hydrothermal Liquefaction converts wet biosolids (15-25%DS) to biocrude, "
        "aqueous phase, and gas at 250-375°C and 150-250 bar. At commercial scale, "
        "HTL can produce a biocrude suitable for refinery co-processing into "
        "Sustainable Aviation Fuel (SAF) or renewable diesel. "
        "HTL was not assessed in this screening for the following reasons: "
        "(1) no commercial-scale biosolids HTL facility is operating in Australia; "
        "(2) technology readiness at ETP scale (219 tDS/day) is lower than FBF or pyrolysis; "
        "(3) offtake market for HTL biocrude in Victoria is currently uncertain; "
        "(4) capital cost and technical complexity are significantly higher than incineration. "
        "HTL should be assessed in the Stage 2 thermal treatment study, particularly if "
        "refinery co-processing or SAF offtake arrangements can be secured — the revenue "
        "potential from biocrude sales may significantly improve the business case. "
        "HTL technology maturity is evolving rapidly and should be reassessed "
        "periodically as commercial deployment increases globally.",
        S["body"]))
    story.append(_sp(4))

    story.append(_p(
        "Recommended pathway sequence: "
        "(1) Implement SolidStream + digester expansion — achieves Class A, "
        "dramatically reduces cake volume and drying cost, enables thermal treatment; "
        "(2) Commission thermal treatment feasibility study (FBF vs pyrolysis); "
        "(3) Procure thermal treatment facility as Stage 2 — eliminates land application, "
        "achieves net zero Scope 1 biosolids target. "
        "The 67% reduction in drying energy from SolidStream makes the thermal treatment "
        "economics significantly more favourable than conventional AD → thermal.",
        S["body"]))



def _separate_digestion_section(story, S, d: Tier1ReportData, section_num: int):
    """Separate vs Blended Digestion Analysis — ETP-specific."""
    story.append(_p(f"{section_num}. Separate vs Blended Digestion Analysis", S["h1"]))
    story.append(_section_rule())
    story.append(_p(
        "Literature consistently shows that primary sludge (PS) and waste activated "
        "sludge (WAS) have fundamentally different kinetics and should ideally be digested "
        "separately. PS is dominated by lipids and carbohydrates (rapid hydrolysis, "
        "k\u2248\u200a0.25\u2009/day), while WAS is cell-mass dominated (slow hydrolysis, "
        "k\u2248\u200a0.12\u2009/day). When blended, WAS kinetics suppress PS performance. "
        "This section quantifies the impact for ETP's existing 8\u2009\u00d7\u20048,000\u2009m\u00b3 "
        "digester configuration, and presents the volume optimisation results.",
        S["body"]))
    story.append(_sp(2))

    if not d.cmp_result:
        story.append(_p("Site data not available.", S["body"]))
        return

    site = d.cmp_result.site
    P2 = lambda t: Paragraph(str(t), S["cell"])
    PH2 = lambda t: Paragraph(str(t), S["cell_b"])

    # ── Kinetic basis ─────────────────────────────────────────────────────
    story.append(_p("Kinetic Basis", S["h2"]))
    kin_rows = [
        [PH2("Stream"), PH2("k central (/day)"), PH2("k range"), PH2("90% conversion"), PH2("Mechanism")],
        [P2("PS (separate)"), P2("0.25"), P2("0.20\u20130.35"),
         P2("CSTR design: 12\u201315d"), P2("Lipid & carbohydrate hydrolysis; no WAS inhibition")],
        [P2("WAS"), P2("0.12"), P2("0.08\u20130.15"),
         P2("CSTR design: \u226515d"), P2("Cell wall hydrolysis; slower rate-limiting step")],
        [P2("Blended"), P2("0.13"), P2("0.10\u20130.18"),
         P2("WAS-dominated"), P2("WAS kinetics suppress PS benefit; PS yield partially lost")],
    ]
    cw_k = [28*mm, 28*mm, 22*mm, 32*mm, CONTENT_W-110*mm]
    story.append(_tbl(kin_rows, cw_k,
        [("WORDWRAP",(0,0),(-1,-1),"LTR"),("FONTSIZE",(0,0),(-1,-1),8)], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "Note: \u201cPS >90% conversion in 10 days\u201d (cited in literature) refers to the "
        "batch exponential model (1\u2212e\u207b\u207a\u2070\u00b7\u00b2\u2075\u02e3\u00b9\u2070\u207b=91.8%). "
        "For a continuous CSTR digester, the equivalent design target is 12\u201315 days HRT. "
        "The 30% specific yield uplift when PS is digested separately is an empirical "
        "observation from multiple studies (Bolzonella 2005; Silvestre 2015; WEF MOP 8).",
        S["small"]))
    story.append(_sp(4))

    # ── ETP volume optimisation ───────────────────────────────────────────
    story.append(_p("ETP Volume Optimisation \u2014 8 \u00d7 8,000 m\u00b3", S["h2"]))

    PS_DS=120.7; WAS_DS=98.8; PS_TS=7.5; WAS_TS=3.5; PS_VS=65.0; WAS_VS=65.0
    V_EACH=8000; N_DIG=8; V_TOTAL=64000
    PS_Q=PS_DS/(PS_TS/100); WAS_Q=WAS_DS/(WAS_TS/100)
    PS_VS_TPD=PS_DS*PS_VS/100; WAS_VS_TPD=WAS_DS*WAS_VS/100
    BG_CAMBI=74163; K_PS=0.25; K_WAS=0.12; CAL=1.482

    from reportlab.lib import colors as rl_colors

    def vsr_cstr(k,h): return 1-1/(1+k*h)
    def bg_sep(hps,hwas,kps=K_PS,kwas=K_WAS):
        Y_PS_SEP=0.55*1.30; Y_WAS=0.45
        return (PS_VS_TPD*1000*vsr_cstr(kps,hps)*Y_PS_SEP +
                WAS_VS_TPD*1000*vsr_cstr(kwas,hwas)*Y_WAS)*CAL

    import math
    was_n_min = math.ceil(WAS_Q*15/V_EACH)

    story.append(_p(
        f"With 8 digesters of 8,000\u2009m\u00b3 each ({V_TOTAL:,}\u2009m\u00b3 total), "
        f"the WAS flow of {WAS_Q:.0f}\u2009m\u00b3/day requires a minimum of "
        f"{WAS_Q*15:,.0f}\u2009m\u00b3 to maintain the 15-day HRT minimum. "
        f"This demands at least {was_n_min} digesters for WAS, leaving a maximum of "
        f"{N_DIG-was_n_min} digesters for PS. The table below shows all feasible splits.",
        S["body"]))
    story.append(_sp(2))

    # Build split table
    AMBER = rl_colors.HexColor("#fff3e0")
    GREEN = rl_colors.HexColor("#e8f5e9")
    RED   = rl_colors.HexColor("#ffebee")
    rows  = [[PH2("Split"), PH2("PS HRT"), PH2("WAS HRT"),
              PH2("VSR PS"), PH2("VSR WAS"), PH2("Biogas Nm\u00b3/d"),
              PH2("Uplift vs blended"), PH2("WAS \u226515d?")]]
    best_bg=0; best_nps=0
    feasible = []
    for n_ps in range(1, N_DIG):
        n_was=N_DIG-n_ps
        V_PS=n_ps*V_EACH; V_WAS=n_was*V_EACH
        hps=V_PS/PS_Q; hwas=V_WAS/WAS_Q
        if hps<8 or hwas<10: continue
        vps=vsr_cstr(K_PS,hps)*100; vwas=vsr_cstr(K_WAS,hwas)*100
        bg=bg_sep(hps,hwas); uplift=(bg/BG_CAMBI-1)*100
        was_ok = hwas>=15
        feasible.append((n_ps,n_was,V_PS,V_WAS,hps,hwas,vps,vwas,bg,uplift,was_ok))
        if bg>best_bg: best_bg=bg; best_nps=n_ps

    row_style_cmds = []
    for i, (n_ps,n_was,V_PS,V_WAS,hps,hwas,vps,vwas,bg,uplift,was_ok) in enumerate(feasible):
        flag="\u2713" if was_ok else "\u2717 FAIL"
        col=GREEN if was_ok else RED
        row_style_cmds.append(("BACKGROUND",(7,i+1),(7,i+1),col))
        rows.append([
            P2(f"{n_ps}PS\u200a+\u200a{n_was}WAS"),
            P2(f"{hps:.1f}d"),
            P2(f"{hwas:.1f}d"),
            P2(f"{vps:.1f}%"),
            P2(f"{vwas:.1f}%"),
            P2(f"{bg:,.0f}"),
            Paragraph(f"{uplift:+.1f}%",
                ParagraphStyle("up", parent=S["cell_b"],
                    textColor=SAFE_GREEN if uplift>0 else FAIL_RED)),
            P2(flag),
        ])

    cw_s = [28*mm,18*mm,20*mm,18*mm,20*mm,28*mm,28*mm,CONTENT_W-160*mm]
    story.append(_tbl(rows, cw_s,
        [("WORDWRAP",(0,0),(-1,-1),"LTR"),("FONTSIZE",(0,0),(-1,-1),8)]
        + row_style_cmds, row_bgs=False))
    story.append(_sp(2))
    story.append(_p(
        f"Blended reference: {BG_CAMBI:,}\u2009Nm\u00b3/day, 18.1\u2009days HRT (Cambi Scenario 1). "
        "Only rows with WAS\u2009\u226515\u2009d are operationally compliant. "
        "The mathematical optimum (4PS\u200a+\u200a4WAS, +26.6%) violates the WAS minimum HRT.",
        S["caption"]))
    story.append(_sp(4))

    # ── Three scenarios ───────────────────────────────────────────────────
    story.append(_p("Recommended Scenarios", S["h2"]))
    scenarios = []
    for n_ps,n_was,V_PS,V_WAS,hps,hwas,vps,vwas,bg,uplift,was_ok in feasible:
        scenarios.append((n_ps,n_was,V_PS,V_WAS,hps,hwas,vps,vwas,bg,uplift,was_ok))

    sc_map = {r[0]:r for r in scenarios}

    sc_data = []
    if 2 in sc_map: sc_data.append(("2PS\u200a+\u200a6WAS  (compliant\u200a\u2014\u200aonly viable split)", sc_map[2], True))
    if 3 in sc_map: sc_data.append(("3PS\u200a+\u200a5WAS  (WAS HRT marginal at 14.2d)", sc_map[3], False))
    if 4 in sc_map: sc_data.append(("4PS\u200a+\u200a4WAS  (mathematical optimum\u200a\u2014\u200anot compliant)", sc_map[4], False))

    hdr2=[PH2("Parameter")]+[PH2(label.split("(")[0].strip()) for label,_,_ in sc_data]
    hdr2.insert(0,PH2("Parameter"))
    hdr2=[PH2("Parameter")]+[PH2(label.split("(")[0].strip()) for label,sc,ok in sc_data]

    rows2=[hdr2]
    def prow(label, vals):
        return [P2(label)] + [P2(v) for v in vals]

    for sc_row_data in [
        ("PS HRT (days)",     [f"{sc[4]:.1f}" for _,sc,_ in sc_data]),
        ("WAS HRT (days)",    [f"{sc[5]:.1f}" for _,sc,_ in sc_data]),
        ("PS VSR (%)",        [f"{sc[6]:.1f}" for _,sc,_ in sc_data]),
        ("WAS VSR (%)",       [f"{sc[7]:.1f}" for _,sc,_ in sc_data]),
        ("Biogas (Nm\u00b3/day)",  [f"{sc[8]:,.0f}" for _,sc,_ in sc_data]),
        ("Biogas uplift vs blended", [f"{sc[9]:+.1f}%" for _,sc,_ in sc_data]),
        ("Electricity uplift (kW)",  [f"+{sc[9]/100*7704:,.0f}" for _,sc,_ in sc_data]),
        ("Additional MWhe/yr",       [f"+{sc[9]/100*7704*8760*0.88/1000:,.0f}" for _,sc,_ in sc_data]),
        ("WAS \u226515d compliant?",  ["\u2713 Yes" if ok else "\u2717 No" for _,sc,ok in sc_data]),
    ]:
        rows2.append(prow(sc_row_data[0], sc_row_data[1]))

    n2=len(sc_data)
    cw2=[55*mm]+[(CONTENT_W-55*mm)/n2]*n2
    story.append(_tbl(rows2, cw2,
        [("WORDWRAP",(0,0),(-1,-1),"LTR"),("FONTSIZE",(0,0),(-1,-1),8),
         ("BACKGROUND",(1,1),(-1,-1), rl_colors.HexColor("#e8f5e9")),
         ("BACKGROUND",(2,1),(-1,-1), rl_colors.HexColor("#fff3e0")),
         ("BACKGROUND",(3,1),(-1,-1), rl_colors.HexColor("#ffebee")) if n2==3 else ("NOP",(0,0),(0,0))
        ], row_bgs=False))
    story.append(_sp(2))
    story.append(_p(
        "Only the 2PS\u200a+\u200a6WAS split fully complies with the WAS 15-day HRT minimum. "
        "3PS\u200a+\u200a5WAS is shown for comparison but WAS HRT of 14.2 days is "
        "marginally below the minimum and leaves no growth headroom.",
        S["caption"]))
    story.append(_sp(4))

    # ── Throughput capacity ───────────────────────────────────────────────
    story.append(_p("Throughput Capacity Analysis", S["h2"]))
    cur_ps=PS_DS*365; cur_was=WAS_DS*365; cur_total=(PS_DS+WAS_DS)*365
    blend_max=(V_TOTAL/15)*0.062*1000*365/1000
    # 2PS+6WAS capacity
    sc2=sc_map[2]
    ps_max = sc2[2]/10*(PS_TS/100)*1000*365/1000
    was_max= sc2[3]/15*(WAS_TS/100)*1000*365/1000

    story.append(_p(
        f"Current total load: {cur_total:,.0f}\u2009tDS/yr "
        f"(PS {cur_ps:,.0f}\u200a+\u200aWAS {cur_was:,.0f}). "
        f"Blended maximum (HRT\u2265\u200a15\u2009d): {blend_max:,.0f}\u2009tDS/yr "
        f"(current utilisation {cur_total/blend_max*100:.0f}%, headroom "
        f"+{blend_max-cur_total:,.0f}\u2009tDS/yr).",
        S["body"]))
    story.append(_sp(2))
    story.append(_p(
        f"Separate 2PS\u200a+\u200a6WAS \u2014 capacity at minimum HRT constraints "
        f"(PS\u2009=\u200910\u2009d, WAS\u2009=\u200915\u2009d):",
        S["body"]))

    cap_rows = [
        [PH2("Stream"), PH2("Digesters"), PH2("Volume (m\u00b3)"),
         PH2("Min HRT"), PH2("Max throughput (tDS/yr)"), PH2("Current load"), PH2("Headroom")],
        [P2("PS"), P2("2\u200a\u00d7\u20048,000"), P2("16,000"),
         P2("10 days"), P2(f"{ps_max:,.0f}"),
         P2(f"{cur_ps:,.0f}"), P2(f"+{ps_max-cur_ps:,.0f}")],
        [P2("WAS"), P2("6\u200a\u00d7\u20048,000"), P2("48,000"),
         P2("15 days"), P2(f"{was_max:,.0f}"),
         P2(f"{cur_was:,.0f}"),
         Paragraph(f"+{was_max-cur_was:,.0f}" if was_max>cur_was else
                   f"\u2212{cur_was-was_max:,.0f} DEFICIT",
             ParagraphStyle("hd", parent=S["cell_b"],
                 textColor=SAFE_GREEN if was_max>cur_was else FAIL_RED))],
        [P2("Bottleneck"), P2("\u2014"), P2("\u2014"), P2("\u2014"),
         P2("\u2014"),P2("\u2014"),
         Paragraph("WAS controls \u2014 6 digesters just cover current WAS load",
             ParagraphStyle("bt", parent=S["cell_b"], textColor=WARN_AMBER))],
    ]
    cw_c=[22*mm,28*mm,22*mm,20*mm,38*mm,28*mm,CONTENT_W-158*mm]
    story.append(_tbl(cap_rows, cw_c,
        [("WORDWRAP",(0,0),(-1,-1),"LTR"),("FONTSIZE",(0,0),(-1,-1),8)], row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "WAS bottleneck: 6 digesters at 17.0\u2009d HRT supports current WAS load "
        f"({cur_was:,.0f}\u2009tDS/yr) with moderate headroom. "
        "Any significant WAS catchment growth will require additional WAS digester volume. "
        "This is the primary operational constraint of separate digestion at ETP.",
        S["small"]))
    story.append(_sp(4))

    # ── New build opportunity ─────────────────────────────────────────────
    story.append(_p("New Build Opportunity \u2014 Volume Saving", S["h2"]))
    story.append(_p(
        "If Melbourne Water proceeds with the Stage 2 digester expansion, "
        "designing the new facility for separate PS/WAS streams from the outset "
        "delivers significant capital savings compared with blended digestion:",
        S["body"]))
    story.append(_sp(2))

    import math as _math
    for V_WAS_try in range(5000,50000,500):
        hrt_w=V_WAS_try/WAS_Q
        if hrt_w<10: continue
        bg_try=bg_sep(12,hrt_w)
        if bg_try>=BG_CAMBI:
            V_PS_new=PS_Q*12
            V_tot_new=V_PS_new+V_WAS_try
            saving=V_TOTAL-V_tot_new
            nb_rows=[
                [PH2("Parameter"), PH2("Blended"), PH2("Separate (to match blended biogas)")],
                [P2("PS volume"),  P2(f"{V_TOTAL:,}\u2009m\u00b3 (blended)"), P2(f"{V_PS_new:,.0f}\u2009m\u00b3 @ 12\u2009d HRT")],
                [P2("WAS volume"), P2("\u2014"),   P2(f"{V_WAS_try:,}\u2009m\u00b3 @ {hrt_w:.1f}\u2009d HRT")],
                [P2("Total volume"), P2(f"{V_TOTAL:,}\u2009m\u00b3"), P2(f"{V_tot_new:,.0f}\u2009m\u00b3")],
                [P2("Volume saved"), P2("\u2014"), P2(f"{saving:,.0f}\u2009m\u00b3  ({saving/V_EACH:.0f}\u200a\u00d7\u200a8,000\u2009m\u00b3 digesters)")],
                [P2("Indicative capital avoided"),  P2("\u2014"),
                 P2(f"${saving/V_EACH*15:.0f}M\u2013${saving/V_EACH*25:.0f}M  (Class 5, \u00b150%)")],
                [P2("Biogas output"), P2(f"{BG_CAMBI:,}\u2009Nm\u00b3/day"), P2(f"\u2265{BG_CAMBI:,}\u2009Nm\u00b3/day \u2713")],
            ]
            cw_nb=[55*mm,(CONTENT_W-55*mm)/2,(CONTENT_W-55*mm)/2]
            story.append(_tbl(nb_rows, cw_nb,
                [("WORDWRAP",(0,0),(-1,-1),"LTR"),("FONTSIZE",(0,0),(-1,-1),8)], row_bgs=True))
            story.append(_sp(2))
            story.append(_p(
                "Capital cost assumption: $15\u2013$25M per 8,000\u2009m\u00b3 digester (Class 5 estimate, \u00b150%). "
                "Separate digestion enables the same biogas output with 2 fewer digesters "
                "by exploiting PS\u2019s faster kinetics and allowing each stream to be "
                "designed for its own optimal HRT.",
                S["small"]))
            break
    story.append(_sp(4))

    # ── Pros and cons ─────────────────────────────────────────────────────
    story.append(_p("Pros and Cons \u2014 ETP-Specific Assessment", S["h2"]))

    # Pull 2PS+6WAS numbers
    sc2=sc_map[2]
    uplift_kw=sc2[9]/100*7704
    uplift_mwh=uplift_kw*8760*0.88/1000

    pros = [
        f"Biogas uplift +{sc2[9]:.1f}% (2PS+6WAS, only compliant split): "
        f"+{sc2[8]-BG_CAMBI:,.0f}\u2009Nm\u00b3/day \u2192 "
        f"+{uplift_kw:,.0f}\u2009kW gross / +{uplift_mwh:,.0f}\u2009MWh/yr",
        f"PS kinetics accelerated: k_PS=0.25/day vs k_blend=0.13/day; "
        f"PS VSR improves from ~70% (blended) to {sc2[6]:.1f}% (separate)",
        "New build capital avoided: if building new digesters, separate design "
        f"saves 2\u200a\u00d7\u20048,000\u2009m\u00b3 (~$30\u2013$50M) vs blended for same biogas output",
        "Operational independence: PS and WAS banks can be taken offline "
        "separately for maintenance without shutting whole plant",
        "WAS foam/scum isolation: WAS foaming events do not contaminate PS digesters",
        "SolidStream compatibility: PS digestate may reach higher TS% separately, "
        "potentially improving pre-dewatering performance before THP",
    ]
    cons = [
        "CURRENT PLANT CONSTRAINT: existing 8 digesters are almost certainly "
        "plumbed for blended feed. Separating requires new PS/WAS distribution "
        "pipework, isolation valves, gas manifolding. Estimated: $5\u2013$15M (Class 5)",
        "WAS HRT IS TIGHT AT 2PS+6WAS: WAS HRT=17.0\u2009d gives moderate headroom. "
        "Any significant WAS load growth requires additional WAS digester volume",
        "BLENDED HRT ALREADY GOOD: at 18.1\u2009d blended, the plant is well-operated. "
        f"The uplift (+{sc2[9]:.1f}%) is real but incremental, not transformational",
        "LITERATURE UNCERTAINTY: 30% PS yield uplift is empirical (range 10\u201335% "
        "across studies). ETP-specific PS characteristics should be validated",
        "MIXING COMPLEXITY: PS at 7.5%\u2009TS requires different mixing than "
        "WAS at 3.5%\u2009TS. Existing mixing systems may need modification",
        "SOLIDSTREAM INTERFACE: separate digestate streams must recombine "
        "before THP pre-dewatering \u2014 adds hydraulic complexity at the THP interface",
    ]

    for title, items, icon, col in [
        ("Benefits", pros, "\u2713", SAFE_GREEN),
        ("Constraints and risks", cons, "\u2717", FAIL_RED),
    ]:
        story.append(_p(title, S["h3"]))
        for item in items:
            story.append(_p(
                icon + "\u2002" + item,
                ParagraphStyle("pc", parent=S["bullet"], textColor=col)))
        story.append(_sp(2))

    story.append(_sp(2))

    # ── Verdict box ───────────────────────────────────────────────────────
    verdict = (
        "<b>Verdict:</b> For the EXISTING ETP plant, separate digestion (2PS\u200a+\u200a6WAS) "
        f"delivers a genuine +{sc2[9]:.1f}% biogas uplift (+{uplift_mwh:,.0f}\u2009MWh/yr) "
        "but re-piping cost and tight WAS HRT headroom make it a marginal business case "
        "at current energy prices. <b>For a NEW FACILITY (Stage 2 expansion), "
        "separate digestion should be the default design basis</b>\u200a\u2014 "
        "it saves 2\u200a\u00d7\u20048,000\u2009m\u00b3 digesters (~$30\u2013$50M) and eliminates "
        "the WAS HRT constraint by designing each bank for its own optimal retention time. "
        "Separate PS/WAS digestion should be included in the Stage 2 options scope."
    )
    box = Table([[Paragraph(verdict, ParagraphStyle(
        "verd", parent=S["body"], textColor=PH2O_BLUE))]],
        colWidths=[CONTENT_W])
    box.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(-1,-1), PH2O_LIGHT),
        ("TOPPADDING",  (0,0),(-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("LEFTPADDING", (0,0),(-1,-1), 12),
        ("RIGHTPADDING",(0,0),(-1,-1), 12),
        ("BOX",         (0,0),(-1,-1), 1.5, PH2O_BLUE),
    ]))
    story.append(box)


def _recommendation(story, S, d: Tier1ReportData, section_num: int):
    story.append(_p(f"{section_num}. Preferred Pathway — Conditional Recommendation", S["h1"]))
    story.append(_section_rule())

    result = d.cmp_result
    if not result:
        story.append(_p("Config Comparison data not available.", S["body"]))
        return

    winner = result.configs.get(result.winner_id)
    is_tie = getattr(result,"is_tie",False)
    reg    = d.regulatory

    if is_tie:
        tie_labels = " and ".join(
            result.configs[k].config_label for k in getattr(result,"tie_ids",[]))
        story.append(_p(
            f"Under the configured driver weightings, {tie_labels} are effectively tied. "
            "Neither option is clearly superior on the current evidence base at screening grade. "
            "The following considerations should guide the final selection:",
            S["body"]))
        story.append(_sp(2))
        bullet_items = [
            "Site-specific HRT confirmation — SolidStream requires ≥15 days HRT in all digesters.",
            "CAPEX sensitivity — obtain budgetary quotations for both options to determine "
            "if capital cost creates a clear differentiator.",
            "Contractor market — THP vendor availability and lead times in the current market.",
            "Operational capability — existing site team experience with thermal pressure systems.",
        ]
        for b in bullet_items:
            story.append(_p("• " + b, S["bullet"]))
        story.append(_sp(3))
    else:
        story.append(_p(narrative_comparison_executive(d), S["body"]))
        story.append(_sp(3))

    # Regulatory pathway narrative
    story.append(_p("Regulatory Pathway", S["h2"]))
    story.append(_p(reg.get("class_a_req",""), S["body"]))
    story.append(_sp(2))
    if reg.get("pfas_note"):
        story.append(_p(reg["pfas_note"], S["body"]))
        story.append(_sp(2))

    # Caveats

    # Decision hold points
    story.append(_sp(4))
    story.append(_p("Decision Hold Points", S["h2"]))
    story.append(_p(
        "The following hold points must be resolved before the preferred configuration "
        "can be confirmed for procurement or capital approval. Each is a gate: "
        "the recommendation remains conditional until all gates are cleared.",
        S["body"]))
    story.append(_sp(2))

    P2h = lambda t: Paragraph(str(t), S["cell"])
    PH2h = lambda t: Paragraph(str(t), S["cell_b"])
    WARN = colors.HexColor("#e65100")

    hold_rows = [
        [PH2h("Hold Point"), PH2h("Status"), PH2h("Responsible"), PH2h("Required action")],
        [P2h("HRT confirmation under peak load"),
         Paragraph("Required", ParagraphStyle("hp", parent=S["cell_b"], textColor=WARN)),
         P2h("Aurecon / Cambi"),
         P2h("Confirm HRT ≥15 days across all peak load and future growth scenarios. "
             "Include centrate recycle volume in hydraulic model.")],
        [P2h("Cambi performance guarantee"),
         Paragraph("Required", ParagraphStyle("hp2", parent=S["cell_b"], textColor=WARN)),
         P2h("Aurecon / Cambi"),
         P2h("Obtain contractual guarantee for 38%DS cake, Class A classification, "
             "22.7% biogas uplift, and minimum HRT requirement. Define test protocol.")],
        [P2h("PFAS biosolids characterisation"),
         Paragraph("Required", ParagraphStyle("hp3", parent=S["cell_b"], textColor=WARN)),
         P2h("Melbourne Water"),
         P2h("Commission PFAS testing of current ETP biosolids. Assess against EPA Victoria "
             "Interim Position Statement (2021). Determine whether land application is viable.")],
        [P2h("TN licence headroom assessment"),
         Paragraph("Required", ParagraphStyle("hp4", parent=S["cell_b"], textColor=WARN)),
         P2h("Melbourne Water"),
         P2h("Confirm ETP liquid treatment train can absorb additional 1,481 kg NH4-N/day "
             "from SolidStream centrate return. Assess against EPA Victoria TN licence limits.")],
        [P2h("Class A regulatory acceptance"),
         Paragraph("Required", ParagraphStyle("hp5", parent=S["cell_b"], textColor=WARN)),
         P2h("Aurecon / EPA Victoria"),
         P2h("Confirm EPA Victoria will accept Cambi THP (165°C, 20 min) as meeting Class A "
             "log reduction criteria under Publication 891.4. Obtain written in-principle position.")],
        [P2h("Digester siting — 9th digester"),
         Paragraph("Required", ParagraphStyle("hp6", parent=S["cell_b"], textColor=WARN)),
         P2h("Melbourne Water / Aurecon"),
         P2h("Confirm site space and civils for additional 8,000 m³ digester. "
             "Assess impact on existing plant operations during construction.")],
        [P2h("Thermal treatment strategy selection"),
         Paragraph("To be commissioned", ParagraphStyle("hp7", parent=S["cell_b"],
                   textColor=colors.HexColor("#1a3a5c"))),
         P2h("Melbourne Water"),
         P2h("Commission Tier 1 thermal treatment study (incineration vs pyrolysis vs HTL). "
             "Resolve PFAS, carbon fate, and biochar market questions before capital commitment.")],
        [P2h("Independent CAPEX estimate"),
         Paragraph("To be commissioned", ParagraphStyle("hp8", parent=S["cell_b"],
                   textColor=colors.HexColor("#1a3a5c"))),
         P2h("Aurecon"),
         P2h("Obtain Class 3-4 CAPEX estimate for THP + digester expansion scope. "
             "Current assessment uses relative bands only — not suitable for funding approval.")],
        [P2h("N2O emission factor validation"),
         Paragraph("To be confirmed", ParagraphStyle("hp9", parent=S["cell_b"],
                   textColor=colors.HexColor("#1a3a5c"))),
         P2h("Melbourne Water"),
         P2h("The N2O land application emission factor (IPCC default 0.01 kg N2O-N/kg N) "
             "drives a large portion of the GHG totals and the thermal treatment narrative. "
             "Sensitivity testing shows this factor can vary by ±8× (0.003–0.025). "
             "Confirm actual ETP biosolids application conditions and soil type before "
             "using GHG figures for carbon accounting or regulatory claims.")],
    ]
    cw_h = [50*mm, 28*mm, 30*mm, CONTENT_W-108*mm]
    story.append(_tbl(hold_rows, cw_h,
        [("WORDWRAP",(0,0),(-1,-1),"LTR"),("FONTSIZE",(0,0),(-1,-1),8)],
        row_bgs=True))
    story.append(_sp(2))
    story.append(_p(
        "Orange = required before proceeding to detailed design. "
        "Blue = required before capital commitment. "
        "All hold points must be cleared before Board investment approval.",
        S["caption"]))

    story.append(_p("Key Caveats & Limitations", S["h2"]))
    caveats = [
        "All outputs are screening-grade (±15% energy, ±20% sidestream, ±40-60% CAPEX context). "
        "Independent verification is required before detailed design or procurement.",
        "SolidStream dewatering performance (≥38% DS, Class A) is vendor-estimated from "
        "Cambi Melbourne ETP memo (May 2026). Performance guarantee requires site-specific testing.",
        "GHG figures are indicative only. The assumed fugitive CH4 rate of 1.5% is a screening "
        "assumption — actual rates vary significantly with gas handling system integrity.",
        "CAPEX band rankings reflect relative capital intensity only. No cost estimates are "
        "provided. Vendor quotation and site civil assessment required.",
        "The comparison is relative — adding or removing configurations changes rankings. "
        "All four configurations should be assessed before drawing conclusions.",
    ]
    for c in caveats:
        story.append(_p("• " + c, S["bullet"]))


def _next_steps(story, S, d: Tier1ReportData, section_num: int):
    story.append(_p(f"{section_num}. Recommended Next Steps", S["h1"]))
    story.append(_section_rule())
    # Conditional recommendation box
    cond_text = (
        "SolidStream with digester expansion is the <b>preferred THP-based pathway "
        "at screening level</b>, subject to confirmation of: "
        "(1) HRT adequacy under peak load scenarios; "
        "(2) centrate NH4-N management strategy and licence headroom; "
        "(3) methane fugitive emission controls; "
        "(4) Class A validation with EPA Victoria; "
        "(5) PFAS characterisation and disposal strategy; "
        "(6) independent CAPEX verification. "
        "Pre-digestion THP remains the preferred option if new digester volume "
        "is being planned, as it achieves higher biogas uplift and HRT reduction."
    )
    cond_tbl = Table([[Paragraph(cond_text, ParagraphStyle(
        "cond", parent=S["body"], fontName="Helvetica", textColor=PH2O_BLUE))]], 
        colWidths=[CONTENT_W])
    cond_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), PH2O_LIGHT),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
        ("BOX",           (0,0),(-1,-1), 1.5, PH2O_BLUE),
    ]))
    story.append(cond_tbl)
    story.append(_sp(4))
    story.append(_p(
        "The following actions are recommended to advance from Tier 1 screening "
        "to Stage 2 options development:",
        S["body"]))
    story.append(_sp(2))

    steps = narrative_next_steps(d, d.regulatory_key)
    for i, step in enumerate(steps, 1):
        story.append(_p(f"{i}.  {step}", S["bullet"]))

    story.append(_sp(4))
    story.append(_p(
        f"This report was prepared by {d.prepared_by} using BioPoint V1 ({VERSION}). "
        f"For questions regarding this assessment, contact {d.prepared_by}.",
        S["small"]))


def _disclaimer_section(story, S, d: Tier1ReportData):
    story.append(PageBreak())
    story.append(_p("Disclaimer & Basis of Assessment", S["h1"]))
    story.append(_section_rule())
    caveats = [
        ("Screening grade",
         "All BioPoint V1 outputs are screening-grade for Stage 1-2 options analysis. "
         "Not suitable for detailed design, procurement, regulatory submission, or "
         "contract pricing without independent engineering verification."),
        ("Energy uncertainty",
         "All energy figures (biogas, electricity, mixing) carry ±15% uncertainty."),
        ("Sidestream loads",
         "Centrate and cake nitrogen loads carry ±20% uncertainty. Seasonal and "
         "diurnal variation is not modelled."),
        ("SolidStream performance",
         "SolidStream figures are vendor-estimated (Cambi, pre-contract). Actual "
         "performance subject to feedstock, digester configuration, HRT, and operating "
         "conditions. Independent performance guarantee testing required."),
        ("CAPEX",
         "No CAPEX estimates are provided. CAPEX bands are relative indicators only. "
         "Vendor quotation and site-specific civil assessment required."),
        ("GHG",
         "GHG figures are indicative only and do not constitute a certified carbon "
         "account. Biogenic CO2 excluded (IPCC carbon-neutral convention)."),
        ("Regulatory compliance",
         "BioPoint does not assess regulatory compliance. EPA pathogen classification, "
         "nutrient discharge limits, and PFAS obligations require specialist assessment."),
        ("NH3 inhibition",
         "Inhibition model uses published kinetic constants (Hansen 1998, Wu 2010). "
         "Site-specific acclimation histories may differ from model assumptions."),
    ]
    rows = [[PH("Caveat", S), PH("Notes", S)]]
    for k, v in caveats:
        rows.append([P(k, S), Paragraph(v, S["cell"])])
    story.append(_tbl(rows, [50*mm, CONTENT_W-50*mm],
        [("WORDWRAP",(0,0),(-1,-1),"LTR")], row_bgs=True))
    story.append(_sp(4))
    story.append(_p(
        f"© {d.prepared_by}. BioPoint V1 is a screening-grade decision support tool. "
        "All outputs must be validated against site-specific data, vendor quotations, "
        "and independent engineering judgement before financial commitment.",
        S["small"]))


# ══════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ══════════════════════════════════════════════════════════════════════════

def generate_tier1_report(d: Tier1ReportData) -> bytes:
    """Generate the full Tier 1 PDF report. Returns bytes."""

    buf      = BytesIO()
    date_str = date.today().strftime("%-d %B %Y")
    S        = _styles()
    on_page  = _make_on_page(d.project_name, date_str)

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 6*mm, bottomMargin=MARGIN,
        title=f"BioPoint Tier 1 — {d.project_name}",
        author=d.prepared_by,
    )

    story = []

    # ── Cover (dark background) ───────────────────────────────────────────
    # Simulate dark cover with a table spanning full content width
    cover_rows = [[Paragraph("", ParagraphStyle("bl"))]]
    cover_tbl = Table(cover_rows, colWidths=[CONTENT_W], rowHeights=[PAGE_H - 2*MARGIN])
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), PH2O_BLUE),
        ("TOPPADDING", (0,0),(-1,-1), 30),
        ("LEFTPADDING",(0,0),(-1,-1), 20),
    ]))
    # Build cover content in a nested story
    cover_inner = []
    _cover(cover_inner, S, d, date_str)
    cover_inner_tbl = Table(
        [[item] for item in cover_inner],
        colWidths=[CONTENT_W - 40*mm])
    cover_inner_tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), PH2O_BLUE),
        ("TOPPADDING", (0,0),(-1,-1), 2),
        ("LEFTPADDING",(0,0),(-1,-1), 0),
        ("RIGHTPADDING",(0,0),(-1,-1),0),
        ("BOTTOMPADDING",(0,0),(-1,-1),2),
    ]))
    story.append(cover_inner_tbl)
    story.append(PageBreak())

    # ── Build section list dynamically ───────────────────────────────────
    sec = 1

    # Exec summary (mandatory)
    _exec_summary(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # Project context (mandatory)
    _project_context(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # Assessment framework (mandatory)
    _assessment_framework(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # Digester performance (mandatory)
    _mad_performance(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # Sidestream nitrogen impact (mandatory — always material at ETP scale)
    _sidestream_nitrogen_section(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # OPEX & GHG (mandatory)
    _opex_ghg_section(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # GHG sensitivity
    _ghg_sensitivity_section(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # Heat recovery (mandatory if THP configs present)
    thp_configs = [k for k in d.cmp_result.included_ids
                   if k in ("pre_thp","solidstream","expansion")] if d.cmp_result else []
    if thp_configs:
        _heat_balance_section(story, S, d, sec); sec += 1
        story.append(PageBreak())

    # PFAS risk register (include if EPA Vic or if thermal/land application context)
    _pfas_section(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # Thermal treatment (if long-term pathway context present)
    if d.client_context and any(kw in d.client_context.lower()
                                for kw in ['thermal','incineration','pyrolysis','net zero']):
        _thermal_treatment_section(story, S, d, sec); sec += 1
        story.append(PageBreak())

    # Separate vs blended digestion (always include — ETP-specific analysis)
    _separate_digestion_section(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # Recommendation (mandatory)
    _recommendation(story, S, d, sec); sec += 1
    story.append(PageBreak())

    # Next steps (mandatory)
    _next_steps(story, S, d, sec); sec += 1

    # Disclaimer
    _disclaimer_section(story, S, d)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
