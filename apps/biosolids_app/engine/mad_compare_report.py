"""
engine/mad_compare_report.py

BioPoint V1 — MAD Configuration Comparison Report Generator.

Produces a two-part PDF:
  Part 1 — A4 Portrait: executive summary, driver analysis,
           recommendations, OPEX comparison, GHG breakdown
  Part 2 — A4 Landscape appendix: full comparison tables,
           equipment lists, heatmap

ph2o Consulting — BioPoint V1 — v25B02
"""

from io import BytesIO
from datetime import date
import math

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)

# Re-use palette from mad_report
PH2O_BLUE  = colors.HexColor("#1a3a5c")
PH2O_TEAL  = colors.HexColor("#0077b6")
PH2O_LIGHT = colors.HexColor("#e8f4f8")
SAFE_GREEN = colors.HexColor("#2e7d32")
WARN_AMBER = colors.HexColor("#e65100")
FAIL_RED   = colors.HexColor("#c62828")
GREY_MID   = colors.HexColor("#546e7a")
GREY_LIGHT = colors.HexColor("#eceff1")
GREY_RULE  = colors.HexColor("#b0bec5")
WHITE      = colors.white
BLACK      = colors.black

# Heatmap palette (4 levels: best → worst)
HEAT = [
    colors.HexColor("#1b5e20"),   # 4 = best  — dark green
    colors.HexColor("#558b2f"),   # 3 = good  — medium green
    colors.HexColor("#f57f17"),   # 2 = fair  — amber
    colors.HexColor("#b71c1c"),   # 1 = worst — dark red
]
HEAT_TEXT = [WHITE, WHITE, BLACK, WHITE]

PAGE_W, PAGE_H = A4
MARGIN = 20*mm
CONTENT_W_P  = PAGE_W  - 2*MARGIN
CONTENT_W_L  = PAGE_H  - 2*MARGIN   # landscape: wider

VERSION = "v25B02"


# ── Style sheet ────────────────────────────────────────────────────────────
def _S():
    b = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=b["Normal"], fontSize=18, leading=22,
            textColor=PH2O_BLUE, fontName="Helvetica-Bold", spaceAfter=3),
        "subtitle": ParagraphStyle("st", parent=b["Normal"], fontSize=10, leading=13,
            textColor=PH2O_TEAL, fontName="Helvetica", spaceAfter=2),
        "meta": ParagraphStyle("m", parent=b["Normal"], fontSize=8.5, leading=11,
            textColor=GREY_MID, fontName="Helvetica"),
        "h1": ParagraphStyle("h1", parent=b["Normal"], fontSize=12, leading=15,
            textColor=PH2O_BLUE, fontName="Helvetica-Bold",
            spaceBefore=12, spaceAfter=5),
        "h2": ParagraphStyle("h2", parent=b["Normal"], fontSize=10, leading=13,
            textColor=PH2O_TEAL, fontName="Helvetica-Bold",
            spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", parent=b["Normal"], fontSize=9, leading=13,
            fontName="Helvetica", spaceAfter=4, alignment=TA_JUSTIFY),
        "small": ParagraphStyle("sm", parent=b["Normal"], fontSize=8, leading=11,
            textColor=GREY_MID, fontName="Helvetica", spaceAfter=3),
        "caption": ParagraphStyle("cap", parent=b["Normal"], fontSize=7.5, leading=10,
            textColor=GREY_MID, fontName="Helvetica-Oblique", spaceAfter=3),
        "cell": ParagraphStyle("cell", parent=b["Normal"], fontSize=8.5, leading=11,
            fontName="Helvetica"),
        "cell_b": ParagraphStyle("cb", parent=b["Normal"], fontSize=8.5, leading=11,
            fontName="Helvetica-Bold"),
        "cell_c": ParagraphStyle("cc", parent=b["Normal"], fontSize=8.5, leading=11,
            fontName="Helvetica", alignment=TA_CENTER),
        "winner": ParagraphStyle("w", parent=b["Normal"], fontSize=11, leading=14,
            textColor=SAFE_GREEN, fontName="Helvetica-Bold"),
    }


def _p(text, style): return Paragraph(text, style)
def _rule(): return HRFlowable(width="100%", thickness=0.5, color=GREY_RULE, spaceAfter=4)
def _sp(h=4): return Spacer(1, h*mm)


def _tbl_style_base():
    return TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), PH2O_BLUE),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 8.5),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, GREY_LIGHT]),
        ("GRID",          (0,0), (-1,-1), 0.3, GREY_RULE),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ])


def _header_footer(project, prepared_by, date_str, page_type="portrait"):
    def on_page(canvas, doc):
        canvas.saveState()
        w, h = landscape(A4) if page_type == "landscape" else A4

        # Top bar
        canvas.setFillColor(PH2O_BLUE)
        canvas.rect(0, h - 13*mm, w, 13*mm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawString(MARGIN, h - 8.5*mm, "BioPoint V1 — MAD Configuration Comparison")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(w - MARGIN, h - 8.5*mm,
            f"{project}  |  {prepared_by}")

        # Bottom bar
        canvas.setFillColor(GREY_LIGHT)
        canvas.rect(0, 0, w, 11*mm, fill=1, stroke=0)
        canvas.setFillColor(GREY_MID)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(MARGIN, 4*mm,
            f"SCREENING GRADE — ±15% energy, ±20% sidestream  |  {VERSION}  |  {date_str}")
        prefix = "A-" if page_type == "landscape" else ""
        canvas.drawRightString(w - MARGIN, 4*mm, f"{prefix}Page {doc.page}")
        canvas.restoreState()
    return on_page


# ── Cover page ─────────────────────────────────────────────────────────────
def _cover(story, S, result, date_str):
    from engine.mad_compare import CONFIG_LABELS_SHORT
    story.append(_sp(6))
    story.append(_p("MAD Configuration Comparison", S["title"]))
    story.append(_p("Mesophilic Anaerobic Digestion — Options Assessment", S["subtitle"]))
    story.append(_sp(4))
    story.append(_rule())
    story.append(_sp(3))

    site = result.site
    meta_data = [
        ["Project",        site.project_name if site else "—"],
        ["Prepared by",    site.prepared_by  if site else "—"],
        ["Date",           date_str],
        ["BioPoint version", VERSION],
        ["Configurations compared",
         ", ".join(CONFIG_LABELS_SHORT.get(k, k) for k in result.included_ids)],
        ["Recommended configuration",
         result.winner_label or "—"],
    ]
    tbl = Table(meta_data, colWidths=[50*mm, CONTENT_W_P - 50*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,-1), PH2O_LIGHT),
        ("FONTNAME",      (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",      (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 7),
        ("GRID",          (0,0), (-1,-1), 0.3, GREY_RULE),
        ("ROWBACKGROUNDS",(0,0), (-1,-1), [WHITE, GREY_LIGHT]),
    ]))
    story.append(tbl)
    story.append(_sp(5))

    # Winner badge — tie-aware
    if result.winner_id:
        wc   = result.configs[result.winner_id]
        is_tie = getattr(result, "is_tie", False)
        tie_ids = getattr(result, "tie_ids", [])
        if is_tie:
            tie_labels = " and ".join(CONFIG_LABELS_SHORT.get(k,"") for k in tie_ids)
            badge_text = (
                f"Effectively tied: <b>{tie_labels}</b>  "
                f"(weighted score {wc.weighted_score:.0f}/100 each) — "
                f"see sensitivity note"
            )
            badge_colour = WARN_AMBER
        else:
            badge_text = (
                f"Recommended: <b>{result.winner_label}</b>  "
                f"(weighted score {wc.weighted_score:.0f}/100)"
            )
            badge_colour = SAFE_GREEN
        badge = Table([[Paragraph(badge_text, ParagraphStyle(
            "badge", parent=S["body"], fontSize=11, fontName="Helvetica-Bold",
            textColor=WHITE, alignment=TA_CENTER))]],
            colWidths=[CONTENT_W_P])
        badge.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), badge_colour),
            ("TOPPADDING",    (0,0), (-1,-1), 9),
            ("BOTTOMPADDING", (0,0), (-1,-1), 9),
        ]))
        story.append(badge)
        story.append(_sp(4))
        if is_tie:
            story.append(_p(
                "<b>Sensitivity note:</b> The scores above are within the tie threshold "
                "(2 points). A change in any single driver weighting could alter the "
                "ranking. Review driver weights carefully and consider whether the "
                "project context clearly favours one option before proceeding.",
                S["small"]))
            story.append(_sp(2))

    story.append(_p(result.executive_summary, S["body"]))
    story.append(_sp(3))
    story.append(_rule())
    story.append(_p(
        "This report compares four digestion configurations against eight project drivers. "
        "Part 1 (portrait) contains the narrative assessment, driver analysis, OPEX comparison, "
        "and GHG breakdown. Part 2 (landscape appendix) contains the full comparison tables, "
        "equipment lists, and heatmap.",
        S["small"]))


# ── Driver weights table ───────────────────────────────────────────────────
def _driver_weights_section(story, S, result):
    from engine.mad_compare import DRIVER_LABELS, DRIVER_DESCRIPTIONS, DRIVER_IDS
    story.append(_p("1. Project Driver Weightings", S["h1"]))
    story.append(_rule())
    story.append(_p(
        "The following driver weightings were applied. A weight of 4–5 indicates "
        "a primary project driver; 1–2 indicates a secondary consideration. "
        "The weighted total score is calculated as: "
        "Σ (driver_rank × driver_weight) / (4 × Σ weights) × 100. "
        "Score 100 = best on all drivers; scores below 50 indicate below-average performance.",
        S["body"]))

    P = lambda t: Paragraph(str(t), S["cell"])
    PH = lambda t: Paragraph(str(t), S["cell_b"])
    # Apply <sub> tags to driver descriptions
    rows = [[PH("Driver"), PH("Weight"), PH("Description")]]
    for d in DRIVER_IDS:
        w = result.driver_weights.get(d, 1)
        filled = ("+" * w).ljust(5, "-")
        # Chemical names in descriptions need <sub> tags
        desc = (DRIVER_DESCRIPTIONS.get(d, "")
                .replace("NH₄",  "NH<sub>4</sub>")
                .replace("CO₂e", "CO<sub>2</sub>e")
                .replace("CO₂",  "CO<sub>2</sub>")
                .replace("CH₄",  "CH<sub>4</sub>")
                .replace("N₂O",  "N<sub>2</sub>O")
                .replace("NH4",  "NH<sub>4</sub>")
                .replace("CO2e", "CO<sub>2</sub>e")
                .replace("CO2",  "CO<sub>2</sub>")
                .replace("CH4",  "CH<sub>4</sub>")
                .replace("N2O",  "N<sub>2</sub>O"))
        def _dl(text):
            t = (str(text)
                 .replace("NH4", "NH<sub>4</sub>")
                 .replace("CO2e", "CO<sub>2</sub>e")
                 .replace("CO2",  "CO<sub>2</sub>")
                 .replace("CH4",  "CH<sub>4</sub>")
                 .replace("N2O",  "N<sub>2</sub>O"))
            return Paragraph(t, S["cell"])

        rows.append([
            _dl(DRIVER_LABELS.get(d, d)),
            P(f"{w}/5  [{filled}]"),
            P(desc),
        ])
    tbl = Table(rows, colWidths=[42*mm, 24*mm, CONTENT_W_P - 66*mm])
    ts = _tbl_style_base()
    ts.add("WORDWRAP", (0,0), (-1,-1), "LTR")
    tbl.setStyle(ts)
    story.append(tbl)


# ── Per-config narrative ───────────────────────────────────────────────────
def _config_narratives(story, S, result):
    story.append(_p("2. Configuration Assessments", S["h1"]))
    story.append(_rule())

    for cfg_id in result.included_ids:
        cr = result.configs[cfg_id]
        is_winner = cfg_id == result.winner_id
        is_tie    = getattr(result, "is_tie", False)
        in_tie    = cfg_id in getattr(result, "tie_ids", [])

        # Section header
        label_text = (
            f"{'★ TIED — ' if (in_tie and is_tie) else ('★ RECOMMENDED — ' if is_winner else '')}"
            f"{cr.config_label}  "
            f"(weighted score: {cr.weighted_score:.0f}/100)"
        )
        col = SAFE_GREEN if is_winner else PH2O_BLUE
        hdr_style = ParagraphStyle("ch", parent=S["h2"],
                                   textColor=col,
                                   fontName="Helvetica-Bold")
        story.append(KeepTogether([
            _p(label_text, hdr_style),
            _p(cr.recommendation_text, S["body"]),
        ]))

        # Benefits / Risks two-column
        benefit_text = "<br/>".join(f"+ {b}" for b in cr.key_benefits)
        risk_text    = "<br/>".join(f"- {r}" for r in cr.key_risks)
        br_data = [[
            Paragraph("<b>Key benefits</b><br/>" + benefit_text,
                      ParagraphStyle("ben", parent=S["body"], fontSize=8.5,
                                     textColor=SAFE_GREEN)),
            Paragraph("<b>Key risks</b><br/>" + risk_text,
                      ParagraphStyle("risk", parent=S["body"], fontSize=8.5,
                                     textColor=FAIL_RED)),
        ]]
        half = (CONTENT_W_P - 3*mm) / 2
        br_tbl = Table(br_data, colWidths=[half, half])
        br_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (0,0), colors.HexColor("#e8f5e9")),
            ("BACKGROUND",    (1,0), (1,0), colors.HexColor("#ffebee")),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (0,0), (-1,-1), 7),
            ("BOX",           (0,0), (0,0), 0.5, SAFE_GREEN),
            ("BOX",           (1,0), (1,0), 0.5, FAIL_RED),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ]))
        story.append(br_tbl)
        story.append(_sp(4))


# ── OPEX comparison ────────────────────────────────────────────────────────
def _opex_section(story, S, result):
    story.append(_p("3. Operating Cost (OPEX) Comparison", S["h1"]))
    story.append(_rule())
    story.append(_p(
        "Annual OPEX breakdown for each configuration. Energy cost is net "
        "(positive = import cost, negative = export revenue). "
        "All figures are screening-grade ±20%.",
        S["body"]))

    included = [result.configs[k] for k in result.included_ids]
    headers = ["OPEX Component"] + [cr.config_label for cr in included]
    rows = [headers]

    def fmt(v):
        if v < 0:
            return f"(${abs(v)/1000:,.0f}k)"  # brackets = credit
        return f"${v/1000:,.0f}k"

    rows.append(
        ["Polymer"] + [fmt(cr.opex_polymer_per_yr) for cr in included])
    rows.append(
        ["Energy (net)"] + [fmt(cr.opex_energy_net_per_yr) for cr in included])
    rows.append(
        ["Disposal & transport"] + [fmt(cr.opex_disposal_per_yr) for cr in included])
    rows.append(
        ["Sidestream treatment"] + [fmt(cr.opex_sidestream_per_yr) for cr in included])
    rows.append(
        ["THP/equip. O&M"] + [fmt(cr.opex_thp_maintenance_per_yr) for cr in included])
    rows.append(
        ["TOTAL ($/yr)"] + [f"${cr.opex_total_per_yr/1000:,.0f}k" for cr in included])
    rows.append(
        ["vs Base case"] + [
            ("—" if cr.config_id == "base"
             else f"{'+' if cr.opex_delta_vs_base_per_yr > 0 else ''}${cr.opex_delta_vs_base_per_yr/1000:,.0f}k")
            for cr in included])

    n = len(included)
    cw_label = 48*mm
    cw_col   = (CONTENT_W_P - cw_label) / n
    tbl = Table(rows, colWidths=[cw_label] + [cw_col]*n)
    ts = _tbl_style_base()
    # Highlight total row
    ts.add("BACKGROUND",  (0, len(rows)-2), (-1, len(rows)-2), PH2O_LIGHT)
    ts.add("FONTNAME",    (0, len(rows)-2), (-1, len(rows)-2), "Helvetica-Bold")
    ts.add("BACKGROUND",  (0, len(rows)-1), (-1, len(rows)-1), GREY_LIGHT)
    ts.add("FONTNAME",    (0, len(rows)-1), (-1, len(rows)-1), "Helvetica-Bold")
    tbl.setStyle(ts)
    story.append(tbl)
    story.append(_sp(3))
    story.append(_p(
        "Parentheses () denote credits (revenue). "
        "A negative TOTAL indicates net operating revenue — energy export credits exceed all costs. "
        "Sidestream treatment OPEX applies when centrate NH<sub>4</sub> return exceeds 10% of plant TKN "
        "(operating cost only; sidestream treatment CAPEX is a separate item). "
        "All figures screening-grade ±20%.",
        S["caption"]))


# ── GHG section ────────────────────────────────────────────────────────────
def _ghg_section(story, S, result):
    story.append(_p("4. Greenhouse Gas Assessment", S["h1"]))
    story.append(_rule())
    story.append(_p(
        "Net GHG per configuration. Scope 1: fugitive CH<sub>4</sub> and N<sub>2</sub>O from "
        "land application. Scope 2: grid electricity import/export (negative = credit). "
        "Scope 3: transport of dewatered cake and upstream polymer production. "
        "GWP basis: AR5, 100-year (CH\u2084=28, N\u2082O=265).",
        S["body"]))

    included = [result.configs[k] for k in result.included_ids]
    headers = [Paragraph("GHG Component\n(kg CO<sub>2</sub>e/day)", S["cell_b"])] + [Paragraph(cr.config_label, S["cell_b"]) for cr in included]
    rows = [headers]

    def fmt_ghg(v):
        if abs(v) < 1:
            return f"{v:.1f}"
        return f"{v:,.0f}"

    def PG(text): return Paragraph(str(text), S["cell"])
    def PGH(text): return Paragraph(str(text), S["cell_b"])

    rows.append([PG("Scope 1 — fugitive CH<sub>4</sub>")] +
                [PG(fmt_ghg(getattr(cr, 'scope1_ch4_kg_co2e_per_d', cr.scope1_kg_co2e_per_d * 0.85)))
                 for cr in included])
    rows.append([PG("Scope 1 — N<sub>2</sub>O (land app.)")] +
                [PG(fmt_ghg(getattr(cr, 'scope1_n2o_kg_co2e_per_d', cr.scope1_kg_co2e_per_d * 0.15)))
                 for cr in included])
    rows.append([PG("Scope 2 — grid electricity (net)")] +
                [PG(fmt_ghg(cr.scope2_kg_co2e_per_d)) for cr in included])
    rows.append([PG("Scope 3 — transport (cake haulage)")] +
                [PG(fmt_ghg(getattr(cr, 'scope3_transport_kg_co2e_per_d', cr.scope3_kg_co2e_per_d * 0.5)))
                 for cr in included])
    rows.append([PG("Scope 3 — polymer (upstream)")] +
                [PG(fmt_ghg(getattr(cr, 'scope3_polymer_kg_co2e_per_d', cr.scope3_kg_co2e_per_d * 0.5)))
                 for cr in included])
    rows.append([PGH("NET GHG (kg CO<sub>2</sub>e/day)")] +
                [PGH(fmt_ghg(cr.net_ghg_kg_co2e_per_d)) for cr in included])
    rows.append([PGH("NET GHG (t CO<sub>2</sub>e/yr)")] +
                [PGH(f"{cr.net_ghg_t_co2e_per_yr:,.0f}") for cr in included])

    cw_label = 55*mm
    n = len(included)
    cw_col   = (CONTENT_W_P - cw_label) / n
    tbl = Table(rows, colWidths=[cw_label] + [cw_col]*n)
    ts = _tbl_style_base()
    ts.add("BACKGROUND", (0, len(rows)-2), (-1, len(rows)-2), PH2O_LIGHT)
    ts.add("FONTNAME",   (0, len(rows)-2), (-1, len(rows)-2), "Helvetica-Bold")
    ts.add("BACKGROUND", (0, len(rows)-1), (-1, len(rows)-1), GREY_LIGHT)
    ts.add("FONTNAME",   (0, len(rows)-1), (-1, len(rows)-1), "Helvetica-Bold")
    tbl.setStyle(ts)
    story.append(tbl)
    story.append(_sp(3))
    story.append(_p(
        "Scope 2 credits (negative) reflect avoided grid electricity from CHP export. "
        f"Grid intensity: {result.site.grid_intensity_kg_co2e_per_kwh:.2f} kg CO<sub>2</sub>e/kWh. "
        "Biogenic CO<sub>2</sub> from biogas combustion is excluded (IPCC carbon-neutral convention). "
        "Figures are screening-grade \u00b120%.",
        S["caption"]))


# ── Disclaimer ─────────────────────────────────────────────────────────────
def _disclaimer(story, S):
    story.append(PageBreak())
    story.append(_p("Disclaimer", S["h1"]))
    story.append(_rule())
    story.append(_p(
        "This report is produced by BioPoint V1 (ph2o Consulting). All outputs are "
        "screening-grade for Stage 1–2 options analysis. "
        "Capital cost estimates are not provided — equipment scope lists are in Appendix C. "
        "Energy and sidestream figures carry ±15–20% uncertainty. "
        "SolidStream performance figures are vendor-estimated (Cambi Melbourne ETP "
        "memo, May 2026) and are not guaranteed. Independent engineering verification "
        "is required before capital commitment or regulatory submission. "
        "GHG figures are indicative only and do not constitute a certified carbon account.",
        S["body"]))


# ════════════════════════════════════════════════════════════════════════════
# PART 2 — LANDSCAPE APPENDIX
# ════════════════════════════════════════════════════════════════════════════

def _heatmap_table(story, S, result):
    from engine.mad_compare import DRIVER_LABELS, DRIVER_IDS
    story.append(_p("Appendix A — Driver Heatmap", S["h1"]))
    story.append(_rule())
    story.append(_p(
        "Score 4 (dark green) = best performance among included configurations. "
        "Score 1 (dark red) = worst. Weighted total score shown in final row. "
        "Driver weights applied as configured.",
        S["body"]))

    included = [result.configs[k] for k in result.included_ids]
    n = len(included)

    header = ["Driver  (weight)"] + [cr.config_label for cr in included]
    def _hl(text):
        """Heatmap label — plain string with sub tags applied."""
        t = (str(text)
             .replace("NH4", "NH<sub>4</sub>")
             .replace("CO2e", "CO<sub>2</sub>e")
             .replace("CO2",  "CO<sub>2</sub>")
             .replace("CH4",  "CH<sub>4</sub>")
             .replace("N2O",  "N<sub>2</sub>O"))
        return Paragraph(t, S["cell_b"])

    rows = [header]

    for d in DRIVER_IDS:
        w = result.driver_weights.get(d, 1)
        row = [_hl(f"{DRIVER_LABELS.get(d, d)}  ({w})")]
        for cr in included:
            sc = cr.driver_scores.get(d, 1)
            row.append(str(sc))
        rows.append(row)

    # Weighted total row
    wt_row = [Paragraph("WEIGHTED TOTAL  (/100)", S["cell_b"])]
    for cr in included:
        wt_row.append(f"{cr.weighted_score:.1f}")
    rows.append(wt_row)

    cw_label = 55*mm
    cw_col   = (CONTENT_W_L - cw_label) / n
    tbl = Table(rows, colWidths=[cw_label] + [cw_col]*n)
    ts = TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), PH2O_BLUE),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("GRID",          (0,0), (-1,-1), 0.5, WHITE),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ("BACKGROUND",    (0,1), (0,-1), PH2O_LIGHT),
        ("FONTNAME",      (0,1), (0,-1), "Helvetica-Bold"),
        # Last row (weighted total)
        ("BACKGROUND",    (0, len(rows)-1), (-1, len(rows)-1), PH2O_BLUE),
        ("TEXTCOLOR",     (0, len(rows)-1), (-1, len(rows)-1), WHITE),
        ("FONTNAME",      (0, len(rows)-1), (-1, len(rows)-1), "Helvetica-Bold"),
    ])

    # Colour score cells by value
    for row_i, row in enumerate(rows[1:-1], 1):   # skip header and total
        for col_j, cr in enumerate(included, 1):
            d = DRIVER_IDS[row_i - 1]
            sc = cr.driver_scores.get(d, 1)
            heat_idx = 4 - sc   # sc=4 → idx=0 (green), sc=1 → idx=3 (red)
            heat_idx = max(0, min(3, heat_idx))
            ts.add("BACKGROUND", (col_j, row_i), (col_j, row_i), HEAT[heat_idx])
            ts.add("TEXTCOLOR",  (col_j, row_i), (col_j, row_i), HEAT_TEXT[heat_idx])
            ts.add("FONTNAME",   (col_j, row_i), (col_j, row_i), "Helvetica-Bold")

    # Apply cell colours LAST so they override row backgrounds
    final_ts = TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), PH2O_BLUE),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("GRID",          (0,0), (-1,-1), 0.5, WHITE),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ("BACKGROUND",    (0,1), (0,-1), PH2O_LIGHT),
        ("FONTNAME",      (0,1), (0,-1), "Helvetica-Bold"),
        # Last row (weighted total)
        ("BACKGROUND",    (0, len(rows)-1), (-1, len(rows)-1), PH2O_BLUE),
        ("TEXTCOLOR",     (0, len(rows)-1), (-1, len(rows)-1), WHITE),
        ("FONTNAME",      (0, len(rows)-1), (-1, len(rows)-1), "Helvetica-Bold"),
    ])
    # Add score cell colours AFTER all other styles
    for row_i, row in enumerate(rows[1:-1], 1):
        for col_j, cr in enumerate(included, 1):
            d = DRIVER_IDS[row_i - 1]
            sc = cr.driver_scores.get(d, 1)
            heat_idx = 4 - sc
            heat_idx = max(0, min(3, heat_idx))
            final_ts.add("BACKGROUND", (col_j, row_i), (col_j, row_i), HEAT[heat_idx])
            final_ts.add("TEXTCOLOR",  (col_j, row_i), (col_j, row_i), HEAT_TEXT[heat_idx])
            final_ts.add("FONTNAME",   (col_j, row_i), (col_j, row_i), "Helvetica-Bold")
    tbl.setStyle(final_ts)
    story.append(tbl)
    story.append(_sp(3))
    story.append(_p(
        "Score 4 (dark green) = best among configurations compared. "
        "Score 1 (dark red) = worst. Scores are relative — "
        "adding or removing configurations changes rankings.",
        S["caption"]))


def _full_comparison_table(story, S, result):
    from engine.mad_compare import DRIVER_LABELS
    story.append(_p("Appendix B — Full Performance Comparison", S["h1"]))
    story.append(_rule())

    included = [result.configs[k] for k in result.included_ids]
    n = len(included)
    cw_label = 60*mm
    cw_col   = (CONTENT_W_L - cw_label) / n

    def row(label, vals):
        return [label] + list(vals)

    def fmt_f(v, dp=1, suffix=""):
        return f"{v:.{dp}f}{suffix}"

    def fmt_i(v, suffix=""):
        return f"{v:,.0f}{suffix}"

    sections = [
        # (section title, [(row_label, [values per config])])
        ("Energy & Biogas", [
            ("Biogas (m³/day)",   [fmt_i(cr.biogas_m3_per_d) for cr in included]),
            ("Biogas (GJ/day)",   [fmt_f(cr.biogas_gj_per_d) for cr in included]),
            ("CHP gross (kW)",    [fmt_i(cr.elec_gross_kw) for cr in included]),
            ("Net electricity (kW)", [fmt_i(cr.elec_net_kw) for cr in included]),
            ("Electricity (MWh/yr)", [fmt_i(cr.elec_annual_mwh) for cr in included]),
            ("Biogas uplift vs base",[f"{cr.biogas_uplift_pct:+.1f}%" for cr in included]),
        ]),
        ("Biosolids Quality", [
            ("Pathogen class",    [cr.pathogen_class for cr in included]),
            ("Class A achieved",  ["Yes" if cr.class_a_achieved else "No" for cr in included]),
            ("VSR (%)",           [fmt_f(cr.vsr_pct) for cr in included]),
        ]),
        ("Dewatering & Cake", [
            ("Cake DS%",          [f"{cr.cake_ds_pct:.0f}%" for cr in included]),
            ("Wet cake (t/day)",  [fmt_f(cr.wet_cake_t_per_day) for cr in included]),
            ("Wet cake (t/yr)",   [fmt_i(cr.wet_cake_t_per_year) for cr in included]),
            ("Trucks/day (40t)",  [fmt_f(cr.trucks_per_day, 1) for cr in included]),
            ("Volume reduction vs base", [
            "—" if cr.config_id == "base" else f"{cr.cake_vol_reduction_pct:+.0f}%"
            for cr in included]),
        ]),
        ("Return Load", [
            ("Centrate NH\u2084-N (kg/day)", [fmt_f(cr.centrate_nh4_kg_per_d) for cr in included]),
            ("% of plant TKN",    [fmt_f(cr.centrate_pct_of_plant_tkn) + "%" for cr in included]),
            ("SS treatment req'd?",["Yes" if cr.sidestream_treatment_reqd else "No" for cr in included]),
        ]),
        ("GHG (kg CO<sub>2</sub>e/day)", [
            ("Scope 1",           [fmt_i(cr.scope1_kg_co2e_per_d) for cr in included]),
            ("Scope 2",           [fmt_i(cr.scope2_kg_co2e_per_d) for cr in included]),
            ("Scope 3",           [fmt_i(cr.scope3_kg_co2e_per_d) for cr in included]),
            ("Net GHG",           [fmt_i(cr.net_ghg_kg_co2e_per_d) for cr in included]),
            ("Net GHG (t/yr)",    [fmt_f(cr.net_ghg_t_co2e_per_yr) for cr in included]),
        ]),
        ("Digester Headroom", [
            ("PS HRT (days)",     [fmt_f(cr.hrt_ps_d) for cr in included]),
            ("WAS HRT (days)",    [fmt_f(cr.hrt_was_d) for cr in included]),
            ("PS SRT headroom",   [fmt_f(cr.ps_srt_headroom_d) + "d" for cr in included]),
            ("WAS SRT headroom",  [fmt_f(cr.was_srt_headroom_d) + "d" for cr in included]),
        ]),
        ("CAPEX — Scope only (no cost estimate)", [
            ("Scope summary",     [getattr(cr, "capex_scope_summary", "See Appendix C")
                                   for cr in included]),
        ]),
        ("OPEX ($/yr)", [
            ("Total OPEX",        [f"${cr.opex_total_per_yr/1e6:.2f}M" for cr in included]),
            ("vs Base case",      [
                "—" if cr.config_id == "base"
                else f"${cr.opex_delta_vs_base_per_yr/1e6:+.2f}M"
                for cr in included]),
        ]),
    ]

    for section_title, section_rows in sections:
        # Section header row
        # Apply sub tags to section title
        section_title_p = (section_title
            .replace("CO₂e", "CO<sub>2</sub>e")
            .replace("CO₂", "CO<sub>2</sub>")
            .replace("CH₄", "CH<sub>4</sub>")
            .replace("CO2e", "CO<sub>2</sub>e")
            .replace("CO2", "CO<sub>2</sub>")
            .replace("CH4", "CH<sub>4</sub>"))
        hdr = Table([[Paragraph(section_title_p, ParagraphStyle(
            "sh", parent=S["cell_b"], textColor=WHITE))]
            + [Paragraph("", S["cell"]) for _ in included]],
            colWidths=[cw_label] + [cw_col]*n)
        hdr.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), PH2O_TEAL),
            ("SPAN", (0,0), (-1,0)),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
        ]))
        story.append(hdr)

        def _wrap_label(t):
            """Wrap label string in Paragraph with chemical sub tags."""
            t2 = (str(t)
                  .replace("NH₄", "NH<sub>4</sub>")
                  .replace("CO₂e", "CO<sub>2</sub>e")
                  .replace("CO₂", "CO<sub>2</sub>")
                  .replace("CH₄", "CH<sub>4</sub>")
                  .replace("N₂O", "N<sub>2</sub>O")
                  .replace("NH4", "NH<sub>4</sub>")
                  .replace("CO2e", "CO<sub>2</sub>e")
                  .replace("CO2", "CO<sub>2</sub>")
                  .replace("CH4", "CH<sub>4</sub>")
                  .replace("N2O", "N<sub>2</sub>O"))
            return Paragraph(t2, S["cell_b"])
        def _wrap_val(t):
            return Paragraph(str(t), S["cell_c"])
        data_rows = [[_wrap_label(r[0])] + [_wrap_val(v) for v in r[1]]
                     for r in section_rows]
        tbl = Table(data_rows, colWidths=[cw_label] + [cw_col]*n)
        ts = TableStyle([
            ("BACKGROUND",    (0,0), (0,-1), PH2O_LIGHT),
            ("FONTSIZE",      (0,0), (-1,-1), 8.5),
            ("ROWBACKGROUNDS",(0,0), (-1,-1), [WHITE, GREY_LIGHT]),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
            ("RIGHTPADDING",  (0,0), (-1,-1), 6),
            ("GRID",          (0,0), (-1,-1), 0.3, GREY_RULE),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
            ("WORDWRAP",      (0,0), (-1,-1), "LTR"),
        ])
        tbl.setStyle(ts)
        story.append(tbl)
        story.append(_sp(3))


def _equipment_section(story, S, result):
    story.append(_p("Appendix C — Equipment Scope", S["h1"]))
    story.append(_rule())
    story.append(_p(
        "Equipment scope listed for comparison purposes. "
        "Capital cost estimates are not provided — vendor quotations and "
        "site-specific civil assessment are required before any cost estimate "
        "can be produced. Lists are indicative of the major scope items only.",
        S["body"]))

    for cfg_id in result.included_ids:
        cr = result.configs[cfg_id]
        scope_summary = getattr(cr, "capex_scope_summary", "")
        story.append(_p(f"{cr.config_label}", S["h2"]))
        if scope_summary:
            story.append(_p(f"Scope summary: {scope_summary}", S["small"]))

        eq_rows = [[f"• {item}"] for item in cr.equipment_list]
        if eq_rows:
            tbl = Table(eq_rows, colWidths=[CONTENT_W_L])
            tbl.setStyle(TableStyle([
                ("FONTNAME",      (0,0), (-1,-1), "Helvetica"),
                ("FONTSIZE",      (0,0), (-1,-1), 8.5),
                ("ROWBACKGROUNDS",(0,0), (-1,-1), [WHITE, GREY_LIGHT]),
                ("TOPPADDING",    (0,0), (-1,-1), 3),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ("LEFTPADDING",   (0,0), (-1,-1), 10),
            ]))
            story.append(tbl)

        story.append(_sp(3))


# ── Main entry point ────────────────────────────────────────────────────────

def generate_comparison_report(result, project_name: str = None,
                                prepared_by: str = None) -> bytes:
    """
    Generate two-part comparison report PDF.
    Part 1: A4 portrait.  Part 2: A4 landscape appendix.
    Returns bytes for st.download_button.
    """
    site = result.site
    proj = project_name or (site.project_name if site else "BioPoint Analysis")
    prep = prepared_by  or (site.prepared_by  if site else "ph2o Consulting")
    date_str = date.today().strftime("%d %B %Y")

    # Build portrait part
    portrait_buf = BytesIO()
    doc_p = SimpleDocTemplate(
        portrait_buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 8*mm, bottomMargin=MARGIN + 7*mm,
        title=f"MAD Comparison — {proj}",
        author=prep,
    )
    S = _S()
    story_p = []
    on_page_p = _header_footer(proj, prep, date_str, "portrait")

    _cover(story_p, S, result, date_str)
    story_p.append(PageBreak())
    _driver_weights_section(story_p, S, result)
    story_p.append(PageBreak())
    _config_narratives(story_p, S, result)
    story_p.append(PageBreak())
    _opex_section(story_p, S, result)
    story_p.append(_sp(4))
    _ghg_section(story_p, S, result)
    _disclaimer(story_p, S)

    doc_p.build(story_p, onFirstPage=on_page_p, onLaterPages=on_page_p)

    # Build landscape appendix
    landscape_buf = BytesIO()
    doc_l = SimpleDocTemplate(
        landscape_buf, pagesize=landscape(A4),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 8*mm, bottomMargin=MARGIN + 7*mm,
        title=f"MAD Comparison Appendix — {proj}",
        author=prep,
    )
    story_l = []
    on_page_l = _header_footer(proj, prep, date_str, "landscape")

    _heatmap_table(story_l, S, result)
    story_l.append(PageBreak())
    _full_comparison_table(story_l, S, result)
    story_l.append(PageBreak())
    _equipment_section(story_l, S, result)

    doc_l.build(story_l, onFirstPage=on_page_l, onLaterPages=on_page_l)

    # Merge portrait + landscape using pypdf
    try:
        from pypdf import PdfWriter, PdfReader
        writer = PdfWriter()
        for buf in (portrait_buf, landscape_buf):
            buf.seek(0)
            reader = PdfReader(buf)
            for page in reader.pages:
                writer.add_page(page)
        merged = BytesIO()
        writer.write(merged)
        return merged.getvalue()
    except ImportError:
        # Fall back to portrait only if pypdf not available
        return portrait_buf.getvalue()
