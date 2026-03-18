"""
core/reporting/report_exporter.py

Two report formats:
  1. Executive Summary (1-2 pages) — key metrics, comparison table, recommendation
  2. Comprehensive Report — full sections, narrative, charts-as-tables, assumptions

Both available as PDF (reportlab) and Word (.docx).

Usage:
    from core.reporting.report_exporter import ReportExporter
    pdf_exec  = ReportExporter.to_pdf(report, mode="executive")
    pdf_full  = ReportExporter.to_pdf(report, mode="comprehensive")
    docx_exec = ReportExporter.to_docx(report, mode="executive")
    docx_full = ReportExporter.to_docx(report, mode="comprehensive")
"""
from __future__ import annotations
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.reporting.report_engine import ReportObject

# ── Brand colours ──────────────────────────────────────────────────────────
BLUE_HEX   = "1F6AA5"
BLUE_LT    = "D5E8F0"
GREY_HEX   = "555555"
GREY_LT    = "F4F4F4"
RED_HEX    = "C0392B"
GREEN_HEX  = "27AE60"
ORANGE_HEX = "E67E22"


class ReportExporter:

    @staticmethod
    def to_pdf(report: ReportObject, mode: str = "comprehensive") -> bytes:
        if mode == "executive":
            return _pdf_executive(report)
        return _pdf_comprehensive(report)

    @staticmethod
    def to_docx(report: ReportObject, mode: str = "comprehensive") -> bytes:
        if mode == "executive":
            return _docx_executive(report)
        return _docx_comprehensive(report)


# ─────────────────────────────────────────────────────────────────────────────
# PDF HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_styles():
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
    from reportlab.lib.units import mm

    rl_blue   = colors.HexColor(f"#{BLUE_HEX}")
    rl_lt     = colors.HexColor(f"#{BLUE_LT}")
    rl_grey   = colors.HexColor(f"#{GREY_HEX}")
    rl_ltgrey = colors.HexColor(f"#{GREY_LT}")

    base = getSampleStyleSheet()
    return {
        "title":    ParagraphStyle("rpt_title", parent=base["Normal"],
                       fontSize=22, fontName="Helvetica-Bold",
                       textColor=rl_blue, spaceAfter=4, spaceBefore=0),
        "subtitle": ParagraphStyle("rpt_subtitle", parent=base["Normal"],
                       fontSize=11, fontName="Helvetica", textColor=rl_grey,
                       spaceAfter=10),
        "h1":       ParagraphStyle("rpt_h1", parent=base["Normal"],
                       fontSize=13, fontName="Helvetica-Bold", textColor=rl_blue,
                       spaceBefore=14, spaceAfter=4),
        "h2":       ParagraphStyle("rpt_h2", parent=base["Normal"],
                       fontSize=10, fontName="Helvetica-Bold", textColor=rl_grey,
                       spaceBefore=8, spaceAfter=2),
        "body":     ParagraphStyle("rpt_body", parent=base["Normal"],
                       fontSize=9, fontName="Helvetica", leading=13,
                       spaceBefore=3, spaceAfter=3, alignment=TA_JUSTIFY),
        "bullet":   ParagraphStyle("rpt_bullet", parent=base["Normal"],
                       fontSize=9, fontName="Helvetica", leading=13,
                       spaceBefore=1, spaceAfter=1, leftIndent=12,
                       bulletIndent=4),
        "caption":  ParagraphStyle("rpt_caption", parent=base["Normal"],
                       fontSize=7.5, fontName="Helvetica-Oblique",
                       textColor=rl_grey, spaceBefore=2, spaceAfter=4),
        "disc":     ParagraphStyle("rpt_disc", parent=base["Normal"],
                       fontSize=7.5, fontName="Helvetica", textColor=rl_grey,
                       spaceBefore=4, spaceAfter=4, alignment=TA_JUSTIFY),
        "kpi_val":  ParagraphStyle("rpt_kpi_val", parent=base["Normal"],
                       fontSize=18, fontName="Helvetica-Bold",
                       textColor=rl_blue, spaceAfter=0, spaceBefore=0),
        "kpi_lbl":  ParagraphStyle("rpt_kpi_lbl", parent=base["Normal"],
                       fontSize=7, fontName="Helvetica", textColor=rl_grey,
                       spaceAfter=0, spaceBefore=0),
    }, {"blue": rl_blue, "lt": rl_lt, "grey": rl_grey, "ltgrey": rl_ltgrey}


def _pdf_tbl_style(colours, header=True, zebra=True):
    from reportlab.platypus import TableStyle
    from reportlab.lib import colors
    cmds = [
        ("FONTNAME",      (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("GRID",          (0,0), (-1,-1), 0.25, colors.HexColor("#CCCCCC")),
        ("ALIGN",         (1,0), (-1,-1), "RIGHT"),
        ("ALIGN",         (0,0), (0,-1), "LEFT"),
    ]
    if header:
        cmds += [
            ("BACKGROUND",  (0,0), (-1,0), colours["blue"]),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,0), 8),
            ("ALIGN",       (0,0), (-1,0), "CENTER"),
        ]
    if zebra:
        cmds.append(("ROWBACKGROUNDS", (0,1), (-1,-1),
                     [colors.white, colours["ltgrey"]]))
    return TableStyle(cmds)


def _pdf_header_footer(canvas, doc, report, is_exec=False):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    w, h = A4
    canvas.saveState()
    # Header
    canvas.setFillColorRGB(0x1F/255, 0x6A/255, 0xA5/255)
    canvas.rect(0, h-22*mm, w, 22*mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(18*mm, h-13*mm, report.project_name or "Treatment Technology Study")
    canvas.setFont("Helvetica", 8)
    rtype = "Executive Summary" if is_exec else "Detailed Report"
    canvas.drawRightString(w-18*mm, h-13*mm,
        f"{rtype} | {datetime.now().strftime('%d %b %Y')}")
    # Footer
    canvas.setFillColorRGB(0x55/255, 0x55/255, 0x55/255)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(18*mm, 10*mm,
        "CONCEPT LEVEL — ±40% — NOT FOR PROCUREMENT OR FUNDING APPROVAL  |  "
        f"ph2o consulting  |  {report.plant_name or ''}")
    canvas.drawRightString(w-18*mm, 10*mm, f"Page {doc.page}")
    canvas.restoreState()


def _make_pdf_doc(buf, is_exec=False):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.units import mm
    return SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=28*mm, bottomMargin=20*mm,
        leftMargin=18*mm, rightMargin=18*mm,
    )


def _pdf_hr(colours):
    from reportlab.platypus import HRFlowable
    return HRFlowable(width="100%", thickness=0.6,
                      color=colours["blue"], spaceAfter=4, spaceBefore=2)


def _render_dict_table(data: dict, styles, colours, W):
    """Render a {headers, rows} dict as a PDF Table."""
    from reportlab.platypus import Table, Paragraph
    from reportlab.lib.units import mm
    hdrs = data.get("headers", [])
    rows = data.get("rows", [])
    if not hdrs or not rows:
        return None
    n = len(hdrs)
    # First col wider (scenario name)
    if n >= 2:
        col_w = [W * 0.28] + [W * 0.72 / (n-1)] * (n-1)
    else:
        col_w = [W / n] * n
    tbl_data = [[Paragraph(str(h), styles["h2"]) for h in hdrs]]
    for r in rows:
        tbl_data.append([Paragraph(str(r.get(h, "—")), styles["body"]) for h in hdrs])
    t = Table(tbl_data, colWidths=col_w, repeatRows=1)
    t.setStyle(_pdf_tbl_style(colours))
    return t


def _render_list_table(data: list, styles, colours, W, first_col_wide=True):
    """Render a list-of-dicts as a PDF Table (comparison style)."""
    from reportlab.platypus import Table, Paragraph
    if not data:
        return None
    hdrs = list(data[0].keys())
    n = len(hdrs)
    if first_col_wide and n >= 2:
        col_w = [W * 0.30] + [W * 0.70 / (n-1)] * (n-1)
    else:
        col_w = [W / n] * n
    tbl_data = [[Paragraph(str(h), styles["h2"]) for h in hdrs]]
    for r in data:
        tbl_data.append([Paragraph(str(r.get(h, "—")), styles["body"]) for h in hdrs])
    t = Table(tbl_data, colWidths=col_w, repeatRows=1)
    t.setStyle(_pdf_tbl_style(colours))
    return t


def _format_assumption_param(raw: str) -> str:
    """Convert raw assumption key to readable label."""
    label_map = {
        "electricity_per_kwh": "Electricity price ($/kWh)",
        "carbon_price_per_tonne": "Carbon price ($/tCO₂e)",
        "discount_rate": "Discount rate",
        "analysis_period_years": "Analysis period (years)",
        "grid_emission_factor": "Grid emission factor (kg CO₂e/kWh)",
        "aeration_tank_per_m3": "Aeration tank civil ($/m³)",
        "secondary_clarifier_per_m2": "Secondary clarifier ($/m²)",
        "blower_per_kw": "Blower system ($/kW)",
        "mbr_membrane_per_m2": "MBR membrane ($/m²)",
        "sludge_disposal_per_tds": "Sludge disposal ($/t DS)",
        "methanol_per_kg": "Methanol ($/kg)",
        "ferric_chloride_per_kg": "Ferric chloride ($/kg)",
    }
    # Handle nested keys like "capex_unit_costs → aeration_tank_per_m3"
    if "→" in raw:
        parts = raw.split("→")
        sub = parts[-1].strip()
        return label_map.get(sub, sub.replace("_", " ").title())
    return label_map.get(raw, raw.replace("_", " ").title())


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTIVE SUMMARY PDF  (1–2 pages)
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_executive(report: ReportObject) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import (
        Paragraph, Spacer, Table, TableStyle, KeepTogether,
    )
    from reportlab.lib import colors

    styles, colours = _pdf_styles()
    buf = io.BytesIO()
    doc = _make_pdf_doc(buf, is_exec=True)
    W = A4[0] - 36*mm

    def hf(canvas, doc):
        _pdf_header_footer(canvas, doc, report, is_exec=True)

    story = []

    # ── Title block ────────────────────────────────────────────────────────
    story.append(Paragraph(
        report.project_name or "Treatment Technology Comparison", styles["title"]))
    story.append(Paragraph(
        f"{report.plant_name or 'Wastewater Treatment'} — Executive Summary",
        styles["subtitle"]))
    story.append(Paragraph(
        f"Prepared by: {report.prepared_by or 'ph2o consulting'}  |  "
        f"Date: {datetime.now().strftime('%B %Y')}  |  "
        f"Scenarios evaluated: {len(report.scenario_names)}",
        styles["caption"]))
    story.append(_pdf_hr(colours))
    story.append(Spacer(1, 4))

    # ── Study description ──────────────────────────────────────────────────
    story.append(Paragraph("Study Overview", styles["h1"]))
    story.append(Paragraph(
        f"This executive summary presents the results of a concept-stage treatment "
        f"technology comparison study for <b>{report.plant_name or 'the facility'}</b>. "
        f"A total of <b>{len(report.scenario_names)} treatment scenarios</b> were evaluated "
        f"across capital cost, operating cost, lifecycle cost, energy consumption, carbon "
        f"footprint, and risk. All estimates are concept-level (±40%) and are intended for "
        f"comparative purposes only.",
        styles["body"]))
    story.append(Spacer(1, 4))

    # ── Scenarios overview table ───────────────────────────────────────────
    story.append(Paragraph("Scenarios Evaluated", styles["h1"]))
    story.append(_pdf_hr(colours))
    scen_rows = [["Scenario", "Technology", "Key Characteristic"]]
    tech_notes = {
        "bnr": "BNR with Secondary Clarifiers",
        "granular_sludge": "Aerobic Granular Sludge (Nereda®)",
        "mabr_bnr": "MABR retrofit into BNR aerobic zone",
        "bnr_mbr": "BNR basins + Membrane Separation",
        "ifas_mbbr": "IFAS carrier media retrofit",
        "anmbr": "Anaerobic MBR",
    }
    for name in (report.scenario_names or []):
        # Try to infer tech from comparison table
        scen_rows.append([name, "—", "—"])
    if len(scen_rows) > 1:
        t = Table(scen_rows, colWidths=[W*0.35, W*0.35, W*0.30], repeatRows=1)
        t.setStyle(_pdf_tbl_style(colours))
        story.append(t)
        story.append(Spacer(1, 6))

    # ── Multi-criteria comparison ──────────────────────────────────────────
    if report.comparison_table:
        story.append(Paragraph("Multi-Criteria Comparison", styles["h1"]))
        story.append(_pdf_hr(colours))
        t = _render_list_table(report.comparison_table, styles, colours, W)
        if t:
            story.append(t)
            story.append(Spacer(1, 4))

    # ── Key metrics KPI row ────────────────────────────────────────────────
    if report.cost_table:
        story.append(Spacer(1, 4))
        story.append(Paragraph("Cost Summary", styles["h1"]))
        story.append(_pdf_hr(colours))
        t = _render_dict_table(report.cost_table, styles, colours, W)
        if t:
            story.append(t)
            story.append(Paragraph(
                "All CAPEX figures are concept-level estimates (±40%) in AUD 2024. "
                "Lifecycle cost = OPEX + CAPEX annualised over 30 years at 7% discount rate.",
                styles["disc"]))

    # ── Carbon & Energy ────────────────────────────────────────────────────
    if report.carbon_table:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Carbon & Energy Summary", styles["h1"]))
        story.append(_pdf_hr(colours))
        t = _render_dict_table(report.carbon_table, styles, colours, W)
        if t:
            story.append(t)

    # ── Key conclusion ─────────────────────────────────────────────────────
    story.append(Spacer(1, 8))
    story.append(Paragraph("Conclusions", styles["h1"]))
    story.append(_pdf_hr(colours))
    if report.preferred_scenario:
        story.append(Paragraph(
            f"Based on the multi-criteria assessment, the <b>{report.preferred_scenario}</b> "
            f"scenario is identified as the preferred option. Detailed engineering assessment "
            f"is recommended before proceeding to procurement.",
            styles["body"]))
    else:
        story.append(Paragraph(
            "All scenarios have been evaluated on a consistent basis. No preferred scenario "
            "has been nominated at this stage. Selection should be based on site-specific "
            "constraints, effluent standards, and stakeholder priorities.",
            styles["body"]))

    # ── Disclaimer ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 12))
    story.append(_pdf_hr(colours))
    story.append(Paragraph(
        "DISCLAIMER: Concept-level estimates (±40%). Not for procurement, funding approval, "
        "or investment decisions without site-specific engineering by a qualified engineer. "
        "Prepared by ph2o consulting using the Water Utility Planning Platform.",
        styles["disc"]))

    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# COMPREHENSIVE REPORT PDF
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_comprehensive(report: ReportObject) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether,
    )
    from reportlab.lib import colors

    styles, colours = _pdf_styles()
    buf = io.BytesIO()
    doc = _make_pdf_doc(buf)
    W = A4[0] - 36*mm

    def hf(canvas, doc):
        _pdf_header_footer(canvas, doc, report)

    story = []

    # ── Cover page ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 20*mm))
    story.append(Paragraph(
        report.project_name or "Treatment Technology Comparison", styles["title"]))
    story.append(Paragraph(
        report.plant_name or "Wastewater Treatment Facility", styles["subtitle"]))
    story.append(Spacer(1, 4))
    meta_rows = [
        ["Report Type:", "Concept-Stage Treatment Technology Comparison"],
        ["Domain:", report.domain or "Wastewater Treatment"],
        ["Scenarios:", str(len(report.scenario_names))],
        ["Prepared by:", report.prepared_by or "ph2o consulting"],
        ["Reviewed by:", report.reviewed_by or "—"],
        ["Date:", datetime.now().strftime("%d %B %Y")],
        ["Status:", "CONCEPT — ±40% ESTIMATE"],
    ]
    t = Table(meta_rows, colWidths=[W*0.30, W*0.70])
    t.setStyle(TableStyle([
        ("FONTNAME",  (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",  (0,0), (-1,-1), 9),
        ("FONTNAME",  (0,0), (0,-1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0,0), (0,-1), colours["blue"]),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LINEBELOW",     (0,-1), (-1,-1), 0.5, colours["blue"]),
    ]))
    from reportlab.platypus import TableStyle
    story.append(t)
    story.append(Spacer(1, 8*mm))
    story.append(_pdf_hr(colours))
    story.append(Paragraph(
        "⚠ CONCEPT LEVEL ESTIMATE — ±40% — FOR COMPARATIVE PURPOSES ONLY. "
        "NOT FOR PROCUREMENT, FUNDING APPROVAL, OR INVESTMENT DECISIONS.",
        styles["disc"]))
    story.append(PageBreak())

    # ── 1. Introduction ────────────────────────────────────────────────────
    story.append(Paragraph("1. Introduction", styles["h1"]))
    story.append(_pdf_hr(colours))
    story.append(Paragraph(
        f"This report presents the results of a concept-stage treatment technology comparison "
        f"study for <b>{report.plant_name or 'the facility'}</b>. The study was undertaken using "
        f"the ph2o consulting Water Utility Planning Platform, which applies first-principles "
        f"engineering calculations based on Metcalf &amp; Eddy (5th Edition), WEF Manual of "
        f"Practice MOP 32 and MOP 35, and published technology-specific references.",
        styles["body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "The purpose of this study is to provide a structured, consistent basis for comparing "
        "treatment technology options at concept stage. All cost estimates are ±40% and are "
        "not suitable for procurement, detailed feasibility, or funding approval without "
        "site-specific investigation by a qualified engineer.",
        styles["body"]))
    story.append(Spacer(1, 8))

    # ── 2. Study Scope ─────────────────────────────────────────────────────
    story.append(Paragraph("2. Study Scope and Methodology", styles["h1"]))
    story.append(_pdf_hr(colours))
    story.append(Paragraph(
        f"A total of <b>{len(report.scenario_names)} treatment scenarios</b> were evaluated:",
        styles["body"]))
    for name in (report.scenario_names or []):
        story.append(Paragraph(f"• {name}", styles["bullet"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Each scenario was evaluated on the following criteria:",
        styles["body"]))
    criteria = [
        "Capital cost (CAPEX) — civil, mechanical, electrical, and membrane works",
        "Operating cost (OPEX) — electricity, chemicals, sludge disposal, maintenance",
        "Lifecycle cost — CAPEX annualised at 7% over 30 years plus OPEX",
        "Specific energy consumption (kWh/ML treated)",
        "Carbon footprint — Scope 1 (process emissions) and Scope 2 (grid electricity)",
        "Effluent quality — BOD, TSS, TN, NH₄, TP",
        "Biosolids production and sludge yield",
        "Technology risk — maturity, implementation, operational complexity, regulatory",
    ]
    for c in criteria:
        story.append(Paragraph(f"• {c}", styles["bullet"]))
    story.append(Spacer(1, 8))

    # ── 3. Multi-Criteria Comparison ───────────────────────────────────────
    if report.comparison_table:
        story.append(Paragraph("3. Multi-Criteria Comparison", styles["h1"]))
        story.append(_pdf_hr(colours))
        story.append(Paragraph(
            "Table 1 presents the key comparative metrics across all evaluated scenarios.",
            styles["body"]))
        t = _render_list_table(report.comparison_table, styles, colours, W)
        if t:
            story.append(t)
            story.append(Paragraph("Table 1: Multi-criteria comparison summary", styles["caption"]))
        story.append(Spacer(1, 8))

    # ── 4. Process Design Summary ─────────────────────────────────────────
    story.append(Paragraph("4. Process Design Summary", styles["h1"]))
    story.append(_pdf_hr(colours))
    story.append(Paragraph(
        "Table 2 presents the key process design parameters for each evaluated scenario, "
        "derived from first-principles calculations using standard biological treatment "
        "design methods (Metcalf & Eddy 5th Edition).",
        styles["body"]))

    # Build design table from report sections or comparison
    _design_rows_added = False
    for sec in (report.sections or []):
        if "design" in sec.title.lower() or "sizing" in sec.title.lower():
            t = _render_list_table(sec.content, styles, colours, W) if isinstance(sec.content, list) else None
            if t:
                story.append(t)
                _design_rows_added = True

    if not _design_rows_added and report.comparison_table:
        # Extract energy from comparison and add physical sizing if available
        pass

    # ── PFD section ────────────────────────────────────────────────────────
    story.append(Spacer(1, 6))
    story.append(Paragraph("5. Process Flow Diagrams", styles["h1"]))
    story.append(_pdf_hr(colours))
    story.append(Paragraph(
        "The following schematic process flow diagrams illustrate the treatment train "
        "configuration for each evaluated scenario. Diagrams show principal unit processes, "
        "key recycle streams (RAS, MLR, WAS), aeration systems, and sludge handling. "
        "Diagrams are schematic only and not to scale.",
        styles["body"]))
    story.append(Spacer(1, 4))

    try:
        from core.reporting.pfd_generator import get_pfd
        from reportlab.lib.units import mm
        pfd_w = W
        pfd_h = 155

        for sec in (report.sections or []):
            pass  # placeholder

        # Draw PFD for each scenario if tech code available
        design_data = getattr(report, "scenario_design_data", {})

        for scen_idx, scen_name in enumerate(report.scenario_names or []):
            sd = design_data.get(scen_name, {})
            tech_seq = sd.get("tech_sequence", [])
            tp_all   = sd.get("tech_performance", {})

            # Primary biological tech is first in sequence
            tech_code = tech_seq[0] if tech_seq else None
            perf      = tp_all.get(tech_code, {}) if tech_code else {}

            if tech_code:
                story.append(Paragraph(f"Scenario: {scen_name}", styles["h2"]))

                # ── Design parameters table ──────────────────────────────
                def _fmt(v, unit=""):
                    if v is None or v == 0: return "—"
                    if isinstance(v, float): return f"{v:,.0f}{unit}"
                    return f"{v}{unit}"

                design_rows = [["Parameter", "Value"]]
                r_vol = perf.get("reactor_volume_m3")
                if r_vol: design_rows.append(["Bioreactor volume", _fmt(r_vol, " m³")])
                fp_m2 = perf.get("footprint_m2")
                if fp_m2: design_rows.append(["Process footprint", _fmt(fp_m2, " m²")])
                hrt = perf.get("hydraulic_retention_time_hr")
                if hrt: design_rows.append(["HRT", f"{hrt:.1f} hr"])
                mlss = perf.get("mlss_mg_l") or perf.get("mlss_granular_mg_l")
                if mlss: design_rows.append(["MLSS", _fmt(mlss, " mg/L")])
                o2 = perf.get("o2_demand_kg_day")
                if o2: design_rows.append(["O₂ demand", _fmt(o2, " kg/day")])
                sludge = perf.get("sludge_production_kgds_day")
                if sludge: design_rows.append(["Sludge production", _fmt(sludge, " kgDS/day")])
                # Effluent
                eff_vals = []
                for k, lbl in [("effluent_bod_mg_l","BOD"), ("effluent_tss_mg_l","TSS"),
                                ("effluent_tn_mg_l","TN"), ("effluent_nh4_mg_l","NH₄")]:
                    v = perf.get(k)
                    if v is not None: eff_vals.append(f"{lbl} {v:.0f}")
                if eff_vals: design_rows.append(["Effluent quality", "  ".join(eff_vals) + " mg/L"])
                # Energy
                kwh = sd.get("specific_energy_kwh_kl", 0)
                if kwh: design_rows.append(["Specific energy", f"{kwh*1000:.0f} kWh/ML"])

                if len(design_rows) > 1:
                    t = Table(design_rows, colWidths=[W*0.45, W*0.55], repeatRows=1)
                    t.setStyle(_pdf_tbl_style(colours))
                    story.append(t)
                    story.append(Spacer(1, 4))

                # ── PFD drawing ───────────────────────────────────────────
                pfd = get_pfd(tech_code, perf, width=pfd_w, height=pfd_h)
                story.append(pfd)
                story.append(Paragraph(
                    f"Figure {scen_idx + 1} — Schematic PFD: {scen_name}. "
                    "Streams: ── Process flow  - - - Recycle (orange)  → Effluent (green)  → Sludge (red). Schematic only.",
                    styles["caption"]))
                story.append(Spacer(1, 10))
    except Exception:
        story.append(Paragraph(
            "Process flow diagrams not available for this report.", styles["body"]))

    # ── Re-number remaining sections ────────────────────────────────────────
    # ── 6. Capital Cost ─────────────────────────────────────────────────────
    if report.cost_table:
        story.append(Paragraph("6. Capital and Lifecycle Cost Assessment", styles["h1"]))
        story.append(_pdf_hr(colours))
        story.append(Paragraph(
            "Table 3 summarises the capital cost, operating cost, and lifecycle cost for each "
            "scenario. All costs are in AUD 2024 and are concept-level estimates (±40%).",
            styles["body"]))
        t = _render_dict_table(report.cost_table, styles, colours, W)
        if t:
            story.append(t)
            story.append(Paragraph("Table 3: Cost summary (AUD 2024, concept-level ±40%)", styles["caption"]))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "CAPEX estimates cover bioreactor civil works, mechanical and electrical equipment, "
            "membranes (where applicable), secondary clarifiers, and instrumentation. They exclude "
            "land, site preparation, headworks, sludge treatment train, buildings, electrical "
            "reticulation, owner's costs, and escalation. A 20% design contingency and 12% "
            "contractor margin are included in the unit rates.",
            styles["body"]))
        story.append(Spacer(1, 8))

    # ── 6a. OPEX Breakdown ────────────────────────────────────────────────
    if getattr(report, "opex_breakdown_table", None):
        story.append(Paragraph("6a. OPEX Cost Drivers", styles["h1"]))
        story.append(_pdf_hr(colours))
        story.append(Paragraph(
            "Table 3a breaks down annual operating cost by category. This identifies the primary "
            "cost drivers and explains the OPEX differential between scenarios. "
            "Energy and sludge disposal are typically the two largest OPEX components for "
            "biological treatment processes.",
            styles["body"]))
        t = _render_dict_table(report.opex_breakdown_table, styles, colours, W)
        if t:
            story.append(t)
            story.append(Paragraph(
                "Table 3a: OPEX breakdown by category (AUD 2024/yr). "
                "Percentages shown as proportion of total annual OPEX.",
                styles["caption"]))
        story.append(Spacer(1, 8))

    # ── 6b. Specific Performance Metrics ──────────────────────────────────
    if getattr(report, "specific_metrics_table", None):
        story.append(Paragraph("6b. Specific Performance Metrics", styles["h1"]))
        story.append(_pdf_hr(colours))
        story.append(Paragraph(
            "Table 3b presents normalised performance metrics to enable direct comparison "
            "across scenarios and benchmarking against industry references. "
            "Specific footprint (m²/MLD) and specific sludge (kgDS/ML) are standard "
            "planning metrics used in Australian utility capital planning.",
            styles["body"]))
        t = _render_dict_table(report.specific_metrics_table, styles, colours, W)
        if t:
            story.append(t)
            story.append(Paragraph(
                "Table 3b: Specific performance metrics. Carbon intensity in kgCO₂e/kL "
                "enables direct comparison with water supply carbon benchmarks.",
                styles["caption"]))
        story.append(Spacer(1, 8))

    # ── 7. Energy & Carbon ─────────────────────────────────────────────────
    if report.carbon_table:
        story.append(Paragraph("7. Energy and Carbon Footprint", styles["h1"]))
        story.append(_pdf_hr(colours))
        story.append(Paragraph(
            "Table 4 summarises the carbon emissions for each scenario. Scope 1 emissions "
            "include N₂O from biological nitrogen removal and CH₄ from sludge handling. "
            "Scope 2 emissions are calculated from grid electricity consumption using the "
            "applicable emission factor. Avoided emissions reflect CHP electricity generation "
            "where anaerobic digestion is included.",
            styles["body"]))
        t = _render_dict_table(report.carbon_table, styles, colours, W)
        if t:
            story.append(t)
            story.append(Paragraph("Table 4: Carbon and energy summary", styles["caption"]))
        story.append(Spacer(1, 8))

    # ── 8. Risk Assessment ─────────────────────────────────────────────────
    if report.risk_table:
        story.append(Paragraph("8. Risk Assessment", styles["h1"]))
        story.append(_pdf_hr(colours))
        story.append(Paragraph(
            "Table 5 presents the technology risk assessment across technical, implementation, "
            "operational, and regulatory dimensions. Risk scores are indicative and based on "
            "technology maturity, reference plant availability, and operational complexity.",
            styles["body"]))
        t = _render_dict_table(report.risk_table, styles, colours, W)
        if t:
            story.append(t)
            story.append(Paragraph("Table 5: Technology risk assessment", styles["caption"]))
        story.append(Spacer(1, 8))

    # ── 7. Conclusions ─────────────────────────────────────────────────────
    story.append(Paragraph("9. Conclusions and Recommendations", styles["h1"]))
    story.append(_pdf_hr(colours))
    if report.preferred_scenario:
        story.append(Paragraph(
            f"Based on the multi-criteria assessment, the <b>{report.preferred_scenario}</b> "
            f"scenario is identified as the preferred option, offering the best balance of "
            f"lifecycle cost, energy performance, carbon footprint, and risk.",
            styles["body"]))
    else:
        story.append(Paragraph(
            "All scenarios have been evaluated on a consistent, first-principles basis. "
            "The selection of a preferred option should be informed by:",
            styles["body"]))
    recs = [
        "Site-specific constraints (footprint, existing infrastructure, upgrade pathway)",
        "Effluent quality requirements and regulatory licence conditions",
        "Utility priorities (energy, carbon, cost, risk)",
        "Procurement strategy and local contractor capability",
        "Detailed geotechnical and hydraulic assessment",
    ]
    for rec in recs:
        story.append(Paragraph(f"• {rec}", styles["bullet"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "A detailed feasibility study with site-specific cost estimation (±15-20%) "
        "is recommended before proceeding to detailed design or procurement.",
        styles["body"]))
    story.append(Spacer(1, 8))

    # ── 8. Assumptions Appendix ────────────────────────────────────────────
    if report.assumptions_appendix:
        story.append(PageBreak())
        story.append(Paragraph("Appendix A — Key Assumptions", styles["h1"]))
        story.append(_pdf_hr(colours))
        story.append(Paragraph(
            "The following key assumptions were used in the analysis. User-entered "
            "site-specific values are noted where applied.",
            styles["body"]))
        story.append(Spacer(1, 4))

        # Clean up and format assumptions — skip internal/debugging entries
        skip_prefixes = ["capex_unit_costs", "pump_per_kw", "blower_per_kw",
                         "vsd_per_kw", "instrumentation", "design_contingency",
                         "contractor_margin", "client_oncosts", "return_sludge",
                         "gravity_thickener", "belt_thickener", "centrifuge",
                         "struvite", "fine_screen", "mbr_membrane_flat"]
        clean_rows = []
        for item in report.assumptions_appendix:
            param = str(item.get("Parameter", ""))
            # Skip raw unit cost keys — shown in screenshot as layout-breakers
            if any(param.startswith(p) for p in skip_prefixes):
                continue
            clean_rows.append({
                "Category":  item.get("Category", ""),
                "Parameter": _format_assumption_param(param),
                "Value":     str(item.get("Value", "")),
                "Override":  item.get("User Override", ""),
            })

        if clean_rows:
            hdrs = ["Category", "Parameter", "Value", "Override"]
            tbl_data = [[Paragraph(h, styles["h2"]) for h in hdrs]]
            for r in clean_rows:
                tbl_data.append([
                    Paragraph(r["Category"],  styles["body"]),
                    Paragraph(r["Parameter"], styles["body"]),
                    Paragraph(r["Value"],     styles["body"]),
                    Paragraph(r["Override"],  styles["body"]),
                ])
            t = Table(tbl_data,
                      colWidths=[W*0.12, W*0.52, W*0.22, W*0.14],
                      repeatRows=1)
            t.setStyle(_pdf_tbl_style(colours))
            story.append(t)

    # ── Disclaimer ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 14))
    story.append(_pdf_hr(colours))
    story.append(Paragraph(
        "DISCLAIMER: This report contains concept-level estimates (±40%) for comparative "
        "purposes only. CAPEX and OPEX figures are indicative AUD 2024 values and must not "
        "be used for procurement, funding approval, or investment decisions without "
        "site-specific engineering assessment by a qualified engineer. Energy and carbon "
        "values are based on standard industry parameters unless site calibration has been "
        "applied. All calculations follow Metcalf &amp; Eddy 5th Edition methodology.",
        styles["disc"]))

    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# WORD EXPORT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _docx_shade(cell, hex_color):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    # Remove any existing shd elements first
    for existing in tcPr.findall(qn("w:shd")):
        tcPr.remove(existing)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    # OOXML schema: shd must appear before vAlign, hideMark, headers in tcPr
    # Correct order: tcW, gridSpan, vMerge, tcBorders, shd, noWrap, tcMar,
    #                textDirection, tcFitText, vAlign, hideMark
    insert_before = None
    for tag in (qn("w:noWrap"), qn("w:tcMar"), qn("w:textDirection"),
                qn("w:tcFitText"), qn("w:vAlign"), qn("w:hideMark")):
        el = tcPr.find(tag)
        if el is not None:
            insert_before = el
            break
    if insert_before is not None:
        tcPr.insert(list(tcPr).index(insert_before), shd)
    else:
        tcPr.append(shd)


def _docx_hr(doc):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    p = doc.add_paragraph()
    p.paragraph_format.space_before = p.paragraph_format.space_after = 0
    pPr = p._p.get_or_add_pPr()
    # Remove existing pBdr if any
    for existing in pPr.findall(qn("w:pBdr")):
        pPr.remove(existing)
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), BLUE_HEX)
    pBdr.append(bottom)
    # Insert pBdr before ind/jc elements (correct schema position)
    insert_before = None
    for tag in (qn("w:shd"), qn("w:tabs"), qn("w:spacing"), qn("w:ind"), qn("w:jc")):
        el = pPr.find(tag)
        if el is not None:
            insert_before = el
            break
    if insert_before is not None:
        pPr.insert(list(pPr).index(insert_before), pBdr)
    else:
        pPr.append(pBdr)


def _docx_table(doc, data_rows, col_widths_cm, font_size=8):
    """data_rows[0] = header row (list of strings), rest = data."""
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
    if not data_rows:
        return
    n_cols = len(data_rows[0])
    t = doc.add_table(rows=len(data_rows), cols=n_cols)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    for r_idx, row in enumerate(data_rows):
        for c_idx, val in enumerate(row):
            cell = t.rows[r_idx].cells[c_idx]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            run = p.add_run(str(val) if val is not None else "—")
            run.font.size = Pt(font_size)
            if r_idx == 0:
                run.font.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                _docx_shade(cell, BLUE_HEX)
            elif r_idx % 2 == 0:
                _docx_shade(cell, GREY_LT)
    # Column widths
    for r in t.rows:
        for i, cell in enumerate(r.cells):
            if i < len(col_widths_cm):
                cell.width = Cm(col_widths_cm[i])


def _docx_heading(doc, text, level=1):
    from docx.shared import Pt, RGBColor
    h = doc.add_heading(text, level)
    if h.runs:
        h.runs[0].font.color.rgb = RGBColor(0x1F, 0x6A, 0xA5)
        h.runs[0].font.size = Pt(13 if level == 1 else 11)


def _docx_body(doc, text, size=9):
    from docx.shared import Pt
    p = doc.add_paragraph(text)
    if p.runs:
        p.runs[0].font.size = Pt(size)
    return p


def _docx_bullet(doc, text):
    from docx.shared import Pt
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(text)
    run.font.size = Pt(9)


def _render_dict_table_docx(doc, data: dict, col_cm: list = None):
    hdrs = data.get("headers", [])
    rows = data.get("rows", [])
    if not hdrs or not rows:
        return
    n = len(hdrs)
    if col_cm is None:
        col_cm = [4.5] + [12.0 / (n-1)] * (n-1) if n > 1 else [16.0]
    tbl_data = [hdrs] + [[str(r.get(h, "—")) for h in hdrs] for r in rows]
    _docx_table(doc, tbl_data, col_cm)


def _render_list_table_docx(doc, data: list, col_cm: list = None):
    if not data:
        return
    hdrs = list(data[0].keys())
    n = len(hdrs)
    if col_cm is None:
        col_cm = [4.5] + [11.5 / (n-1)] * (n-1) if n > 1 else [16.0]
    tbl_data = [hdrs] + [[str(r.get(h, "—")) for h in hdrs] for r in data]
    _docx_table(doc, tbl_data, col_cm)


def _docx_base(report):
    from docx import Document
    from docx.shared import Cm
    from docx.oxml.ns import qn
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = Cm(2.0)
        sec.left_margin = sec.right_margin = Cm(2.0)
    # Fix zoom element: add required w:percent attribute (OOXML schema compliance)
    settings_el = doc.settings.element
    zoom_els = settings_el.findall(qn("w:zoom"))
    for z in zoom_els:
        if not z.get(qn("w:percent")):
            z.set(qn("w:percent"), "100")
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTIVE SUMMARY WORD
# ─────────────────────────────────────────────────────────────────────────────

def _docx_executive(report: ReportObject) -> bytes:
    from docx.shared import Pt, RGBColor, Cm
    doc = _docx_base(report)

    # Title
    h = doc.add_heading(report.project_name or "Treatment Technology Comparison", 0)
    if h.runs:
        h.runs[0].font.color.rgb = RGBColor(0x1F, 0x6A, 0xA5)
    _docx_body(doc, f"{report.plant_name or ''} — Executive Summary", 11)
    _docx_body(doc,
        f"Prepared by: {report.prepared_by or 'ph2o consulting'}  |  "
        f"Date: {datetime.now().strftime('%B %Y')}  |  "
        f"Scenarios: {len(report.scenario_names)}", 8)
    _docx_hr(doc)

    # Overview
    _docx_heading(doc, "Study Overview")
    _docx_body(doc,
        f"This executive summary presents the results of a concept-stage treatment technology "
        f"comparison study for {report.plant_name or 'the facility'}. "
        f"{len(report.scenario_names)} treatment scenarios were evaluated across capital cost, "
        f"operating cost, lifecycle cost, energy, carbon, and risk. "
        f"All estimates are concept-level (±40%) for comparative purposes only.")

    # Comparison table
    if report.comparison_table:
        _docx_heading(doc, "Multi-Criteria Comparison")
        _docx_hr(doc)
        _render_list_table_docx(doc, report.comparison_table)
        _docx_body(doc, "Table 1: Multi-criteria comparison summary", 7)

    # Cost
    if report.cost_table:
        _docx_heading(doc, "Cost Summary")
        _docx_hr(doc)
        _render_dict_table_docx(doc, report.cost_table)
        _docx_body(doc,
            "All CAPEX in AUD 2024 (±40%). Lifecycle cost = OPEX + annualised CAPEX at 7% / 30 years.", 7)

    # Carbon
    if report.carbon_table:
        _docx_heading(doc, "Carbon & Energy")
        _docx_hr(doc)
        _render_dict_table_docx(doc, report.carbon_table)

    # Conclusions
    _docx_heading(doc, "Conclusions")
    _docx_hr(doc)
    if report.preferred_scenario:
        _docx_body(doc,
            f"The {report.preferred_scenario} scenario is identified as the preferred option "
            f"based on the multi-criteria assessment.")
    else:
        _docx_body(doc,
            "No preferred scenario nominated. Selection should consider site constraints, "
            "effluent standards, and stakeholder priorities.")

    # Disclaimer
    doc.add_paragraph()
    _docx_hr(doc)
    p = _docx_body(doc,
        "DISCLAIMER: Concept-level estimates (±40%). Not for procurement or funding approval. "
        "Prepared by ph2o consulting using the Water Utility Planning Platform.", 7)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# COMPREHENSIVE REPORT WORD
# ─────────────────────────────────────────────────────────────────────────────

def _docx_comprehensive(report: ReportObject) -> bytes:
    from docx.shared import Pt, RGBColor, Cm
    doc = _docx_base(report)

    # Cover
    h = doc.add_heading(report.project_name or "Treatment Technology Comparison", 0)
    if h.runs:
        h.runs[0].font.color.rgb = RGBColor(0x1F, 0x6A, 0xA5)
    _docx_body(doc, report.plant_name or "Wastewater Treatment Facility", 12)
    doc.add_paragraph()
    meta = [
        ["Report Type:", "Concept-Stage Treatment Technology Comparison"],
        ["Scenarios:", str(len(report.scenario_names))],
        ["Prepared by:", report.prepared_by or "ph2o consulting"],
        ["Reviewed by:", report.reviewed_by or "—"],
        ["Date:", datetime.now().strftime("%d %B %Y")],
        ["Status:", "CONCEPT — ±40% ESTIMATE"],
    ]
    _docx_table(doc, meta, [4.5, 11.5])
    doc.add_paragraph()
    _docx_hr(doc)
    _docx_body(doc,
        "⚠ CONCEPT LEVEL ESTIMATE — ±40% — FOR COMPARATIVE PURPOSES ONLY. "
        "NOT FOR PROCUREMENT, FUNDING APPROVAL, OR INVESTMENT DECISIONS.", 8)
    doc.add_page_break()

    # 1. Introduction
    _docx_heading(doc, "1. Introduction")
    _docx_hr(doc)
    _docx_body(doc,
        f"This report presents the results of a concept-stage treatment technology comparison "
        f"study for {report.plant_name or 'the facility'}. The study applies first-principles "
        f"engineering calculations based on Metcalf & Eddy (5th Edition), WEF MOP 32/35, "
        f"and published technology-specific references.")
    _docx_body(doc,
        "All cost estimates are ±40% and are not suitable for procurement, detailed "
        "feasibility, or funding approval without site-specific investigation.")

    # 2. Scope
    _docx_heading(doc, "2. Study Scope and Methodology")
    _docx_hr(doc)
    _docx_body(doc, f"{len(report.scenario_names)} treatment scenarios were evaluated:")
    for name in (report.scenario_names or []):
        _docx_bullet(doc, name)
    _docx_body(doc, "Each scenario was assessed on:")
    criteria = [
        "Capital cost (CAPEX) — civil, mechanical, electrical, membrane works",
        "Operating cost (OPEX) — electricity, chemicals, sludge disposal",
        "Lifecycle cost — CAPEX annualised at 7% over 30 years plus OPEX",
        "Specific energy consumption (kWh/ML treated)",
        "Carbon footprint — Scope 1 (process) and Scope 2 (grid electricity)",
        "Effluent quality — BOD, TSS, TN, NH₄, TP",
        "Biosolids production and sludge yield",
        "Technology risk — maturity, implementation, operational complexity, regulatory",
    ]
    for c in criteria:
        _docx_bullet(doc, c)

    # 3. Comparison
    if report.comparison_table:
        _docx_heading(doc, "3. Multi-Criteria Comparison")
        _docx_hr(doc)
        _docx_body(doc, "Table 1 presents key comparative metrics across all scenarios.")
        _render_list_table_docx(doc, report.comparison_table)
        _docx_body(doc, "Table 1: Multi-criteria comparison summary", 7)

    # 4b. Process Design Summary + PFDs
    _docx_heading(doc, "4. Process Design Summary")
    _docx_hr(doc)
    _docx_body(doc,
        "The following tables summarise key process design parameters for each scenario, "
        "derived from first-principles calculations.")

    design_data = getattr(report, "scenario_design_data", {})
    for scen_name in (report.scenario_names or []):
        sd = design_data.get(scen_name, {})
        tech_seq = sd.get("tech_sequence", [])
        tp_all   = sd.get("tech_performance", {})
        tech_code = tech_seq[0] if tech_seq else None
        perf = tp_all.get(tech_code, {}) if tech_code else {}

        if perf:
            _docx_heading(doc, scen_name, 2)
            def _fmt(v, unit=""):
                if not v: return "—"
                return f"{float(v):,.0f}{unit}"

            rows = [["Parameter", "Value"]]
            if perf.get("reactor_volume_m3"): rows.append(["Bioreactor volume", _fmt(perf["reactor_volume_m3"], " m³")])
            if perf.get("footprint_m2"): rows.append(["Process footprint", _fmt(perf["footprint_m2"], " m²")])
            if perf.get("hydraulic_retention_time_hr"): rows.append(["HRT", f"{perf['hydraulic_retention_time_hr']:.1f} hr"])
            mlss = perf.get("mlss_mg_l") or perf.get("mlss_granular_mg_l")
            if mlss: rows.append(["MLSS", _fmt(mlss, " mg/L")])
            if perf.get("o2_demand_kg_day"): rows.append(["O₂ demand", _fmt(perf["o2_demand_kg_day"], " kg/day")])
            if perf.get("sludge_production_kgds_day"): rows.append(["Sludge production", _fmt(perf["sludge_production_kgds_day"], " kgDS/day")])
            eff = []
            for k, l in [("effluent_bod_mg_l","BOD"),("effluent_tss_mg_l","TSS"),("effluent_tn_mg_l","TN"),("effluent_nh4_mg_l","NH₄")]:
                if perf.get(k) is not None: eff.append(f"{l} {perf[k]:.0f}")
            if eff: rows.append(["Effluent quality", "  ".join(eff) + " mg/L"])
            kwh = sd.get("specific_energy_kwh_kl", 0)
            if kwh: rows.append(["Specific energy", f"{kwh*1000:.0f} kWh/ML"])
            _docx_table(doc, rows, [7.0, 9.0])
            _docx_body(doc, f"Note: Process flow diagram for {scen_name} — see below.", 7)

    _docx_body(doc,
        "Process flow diagrams are included in the PDF version of this report. "
        "The Word version contains the design parameter tables above for each scenario.",
        7)

    # 5. Cost
    if report.cost_table:
        _docx_heading(doc, "5. Capital and Lifecycle Cost Assessment")
        _docx_hr(doc)
        _docx_body(doc,
            "Table 3 summarises capital cost, operating cost, and lifecycle cost. "
            "All costs are AUD 2024, concept-level (±40%).")
        _render_dict_table_docx(doc, report.cost_table)
        _docx_body(doc, "Table 3: Cost summary (AUD 2024, ±40%)", 7)
        _docx_body(doc,
            "CAPEX includes bioreactor civil, mechanical, electrical, membranes (where applicable), "
            "secondary clarifiers, and instrumentation. Excludes land, site preparation, headworks, "
            "sludge treatment, buildings, and owner's costs.")

    # 5a. OPEX Breakdown
    if getattr(report, "opex_breakdown_table", None):
        _docx_heading(doc, "5a. OPEX Cost Drivers")
        _docx_hr(doc)
        _docx_body(doc,
            "Table 3a breaks down annual operating cost by category to identify the primary "
            "drivers of the OPEX differential between scenarios. Energy and sludge disposal "
            "are typically the two largest components for biological treatment processes.")
        _render_dict_table_docx(doc, report.opex_breakdown_table)
        _docx_body(doc,
            "Table 3a: OPEX breakdown by category (AUD 2024/yr). "
            "Percentages shown as proportion of total annual OPEX.", 7)

    # 5b. Specific Performance Metrics
    if getattr(report, "specific_metrics_table", None):
        _docx_heading(doc, "5b. Specific Performance Metrics")
        _docx_hr(doc)
        _docx_body(doc,
            "Table 3b presents normalised performance metrics for benchmarking and "
            "comparison. Specific footprint (m²/MLD) and specific sludge (kgDS/ML) "
            "are standard Australian utility capital planning metrics. "
            "Carbon intensity (kgCO₂e/kL) enables comparison with water supply benchmarks.")
        _render_dict_table_docx(doc, report.specific_metrics_table)
        _docx_body(doc, "Table 3b: Specific performance metrics.", 7)

    # 6. Energy & Carbon
    if report.carbon_table:
        _docx_heading(doc, "6. Energy and Carbon Footprint")
        _docx_hr(doc)
        _docx_body(doc,
            "Table 4 summarises carbon emissions. Scope 1 includes N₂O from biological "
            "nitrogen removal and CH₄ from sludge handling. Scope 2 reflects grid electricity "
            "consumption. Avoided emissions reflect CHP electricity generation where applicable.")
        _render_dict_table_docx(doc, report.carbon_table)
        _docx_body(doc, "Table 4: Carbon and energy summary", 7)

    # 7. Risk
    if report.risk_table:
        _docx_heading(doc, "7. Risk Assessment")
        _docx_hr(doc)
        _docx_body(doc,
            "Table 5 presents technology risk across technical, implementation, operational, "
            "and regulatory dimensions. Scores are indicative based on technology maturity "
            "and reference plant availability.")
        _render_dict_table_docx(doc, report.risk_table)
        _docx_body(doc, "Table 5: Technology risk assessment", 7)

    # 8. Decision Framework (if decision engine ran)
    dec = getattr(report, "decision", None)
    if dec and getattr(dec, "recommended_tech", None):
        doc.add_page_break()
        _docx_heading(doc, "8. Decision Framework")
        _docx_hr(doc)

        # Selection basis banner
        _docx_body(doc, f"Selection basis: {dec.selection_basis}", 9)
        doc.add_paragraph()

        # Recommendation
        _docx_heading(doc, "Recommended Option", 2)
        _docx_body(doc, getattr(dec, "display_recommended_label", dec.recommended_label), 11)
        for reason in dec.why_recommended:
            _docx_bullet(doc, reason)

        # Non-viable
        if dec.non_viable:
            _docx_heading(doc, "Base Case Non-Compliant Options (without intervention)", 2)
            for nv in dec.non_viable:
                _docx_bullet(doc, f"{nv} — non-compliant as base case; compliant with engineering intervention")

        # Regulatory note
        reg_note = getattr(dec, "regulatory_note", "")
        if reg_note:
            _docx_heading(doc, "Regulatory Note", 2)
            _docx_body(doc, reg_note)

        # Alternative pathways
        alt_paths = getattr(dec, "alternative_pathways", [])
        if alt_paths:
            _docx_heading(doc, "Alternative Pathways — Interventions for Non-Compliant Base Cases", 2)
            _docx_body(doc,
                "The following engineering interventions can make currently non-compliant "
                "options viable. Evaluate before committing to procurement.")
            for p in alt_paths:
                icon = "✓" if p.achieves_compliance else "⚠"
                _docx_heading(doc, f"{p.tech_label} + Intervention", 3)
                rows = [
                    ["Intervention",        p.intervention],
                    ["CAPEX increment",     f"+${p.capex_delta_m:.1f}M"],
                    ["OPEX increment",      f"+${p.opex_delta_k:.0f}k/yr"],
                    ["Total LCC (pathway)", f"${p.lcc_total_k:.0f}k/yr"],
                    ["Achieves compliance", f"{icon} {'Yes' if p.achieves_compliance else 'Partial'}"],
                    ["Procurement",         p.procurement],
                    ["Regulatory",          p.regulatory],
                ]
                _docx_table(doc, rows, [5.0, 11.0])
                _docx_body(doc, p.summary, 8)
                if p.residual_risks:
                    _docx_body(doc, "Residual risks:", 9)
                    for r in p.residual_risks:
                        _docx_bullet(doc, r)

        # Client decision framing
        cf = getattr(dec, "client_framing", None)
        if cf:
            _docx_heading(doc, "Client Decision Framing", 2)
            _docx_body(doc,
                "The client is not choosing between technologies. The client is choosing "
                "how to manage risk, capital expenditure, and delivery complexity.")
            rows = [
                ["", cf.option_a_label, cf.option_b_label],
                ["What you get",    " | ".join(cf.option_a_bullets[:3]),
                                    " | ".join(cf.option_b_bullets[:3])],
                ["Risks accepted",  " | ".join(cf.option_a_risks[:2]),
                                    " | ".join(cf.option_b_risks[:2])],
            ]
            _docx_table(doc, rows, [3.5, 6.5, 6.0])
            _docx_body(doc, "Decision depends on:")
            for f in cf.deciding_factors:
                _docx_bullet(doc, f)
            _docx_body(doc, cf.framing_note, 8)

        # Technology profiles
        if dec.profiles:
            _docx_heading(doc, "Technology Delivery & Constructability", 2)
            _docx_body(doc,
                "Procurement model and constructability assessment for each technology.")
            hdr = ["Technology", "D&C", "DBOM", "Alliance", "Constructability", "Recommended"]
            rows = [hdr]
            for name, profile in dec.profiles.items():
                rows.append([
                    name,
                    profile.delivery.dnc.value,
                    profile.delivery.dbom.value,
                    profile.delivery.alliance.value,
                    profile.constructability.overall.value,
                    profile.delivery.recommended_model,
                ])
            _docx_table(doc, rows, [4.0, 2.0, 2.0, 2.0, 3.0, 3.0])

            # Failure modes
            _docx_heading(doc, "Key Failure Modes", 2)
            for name, profile in dec.profiles.items():
                _docx_heading(doc, name, 3)
                _docx_body(doc, f"Critical: {profile.failure_modes.critical_note}", 9)
                for fm in profile.failure_modes.modes:
                    _docx_bullet(doc,
                        f"{fm.name} — Likelihood: {fm.likelihood}, "
                        f"Consequence: {fm.consequence}. {fm.mitigation}")

        # Strategic Insight (process intensification vs robustness framing)
        si = getattr(dec, "strategic_insight", "")
        if si:
            _docx_heading(doc, "Strategic Insight", 2)
            _docx_body(doc,
                "This framing should guide technology selection and long-term asset strategy.")
            # Split on double-newline paragraphs
            for para in si.split("\n\n"):
                para = para.strip()
                if para:
                    _docx_body(doc, para)

        # Recommended Approach (parallel evaluation steps)
        ra = getattr(dec, "recommended_approach", [])
        if ra:
            _docx_heading(doc, "Recommended Approach", 2)
            _docx_body(doc,
                "No premature technology lock-in. Parallel concept design "
                "validation before final selection.")
            for step in ra:
                if step.startswith("  "):
                    # Sub-item — render as indented body text
                    _docx_body(doc, f"→ {step.strip()}", 9)
                elif step.endswith(":"):
                    _docx_body(doc, step, 9)
                else:
                    _docx_bullet(doc, step)

        # Trade-offs
        if dec.trade_offs:
            _docx_heading(doc, "Trade-off Summary", 2)
            for t in dec.trade_offs:
                _docx_bullet(doc, t)

        # Financial Risk Perspective
        alt_paths_fr = getattr(dec, "alternative_pathways", [])
        rec_capex = recommended_capex_for_report  if 'recommended_capex_for_report' in dir() else None
        _docx_heading(doc, "Financial Risk Perspective", 2)
        _docx_body(doc,
            "Capital and operating cost structures carry different financial risk profiles "
            "over the asset lifecycle. Both pathway characteristics are summarised below.")
        # Build rows from decision data
        cf_fr = getattr(dec, "client_framing", None)
        if cf_fr and alt_paths_fr:
            a_fr = alt_paths_fr[0]
            opt_a_capex = next((b for b in cf_fr.option_a_bullets if "CAPEX" in b), "—")
            opt_b_capex = next((b for b in cf_fr.option_b_bullets if "CAPEX" in b), "—")
            rows_fr = [
                ["Risk dimension",
                 f"Option A: {dec.recommended_label}",
                 f"Option B: {a_fr.tech_label} + thermal"],
                ["CAPEX exposure",
                 opt_a_capex.replace("CAPEX: ", ""),
                 opt_b_capex.replace("CAPEX: ", "")],
                ["OPEX exposure",
                 "Moderate — electricity (blowers) + vendor DBOM fee",
                 "Higher — heating energy + methanol (ongoing chemical cost)"],
                ["Energy dependency",
                 "Moderate — MABR gas-side pressure control",
                 "High — continuous heating (critical: 15°C compliance threshold)"],
                ["Chemical dependency",
                 "None — biological process only",
                 "High — methanol supply security, storage, dosing"],
                ["LCC sensitivity",
                 "Sensitive to electricity price, MABR vendor fee",
                 "Sensitive to gas/heating energy price, methanol price"],
                ["Long-term financial risk",
                 "Technology obsolescence if MABR market contracts; "
                 "higher ongoing vendor dependency",
                 "Commodity price exposure (methanol, energy); "
                 "heating system capital replacement at 15–20yr"],
            ]
            _docx_table(doc, rows_fr, [4.0, 6.0, 6.0])
            _docx_body(doc,
                "Both options carry lifecycle cost uncertainty of ±25%. "
                "BNR+thermal OPEX is more exposed to energy and chemical price inflation. "
                "MABR LCC is more exposed to vendor contract pricing and technology evolution.",
                8)

        # Confidence
        conf = getattr(dec, "confidence", None)
        if conf:
            _docx_heading(doc, f"Recommendation Confidence: {conf.level}", 2)
            for d in conf.drivers:
                _docx_bullet(doc, d)
            if conf.caveats:
                _docx_body(doc, "Caveats:")
                for c in conf.caveats:
                    _docx_bullet(doc, c)

    # 9. Conclusions
    _docx_heading(doc, "9. Conclusions and Recommendations")
    _docx_hr(doc)
    if dec and getattr(dec, "recommended_tech", None):
        _docx_body(doc, dec.conclusion)
    elif report.preferred_scenario:
        _docx_body(doc,
            f"The {report.preferred_scenario} scenario is identified as the preferred option, "
            f"offering the best balance of lifecycle cost, energy performance, carbon footprint, and risk.")
    else:
        _docx_body(doc,
            "Selection of a preferred option should be informed by site-specific constraints, "
            "effluent standards, utility priorities, and procurement strategy.")
    recs = [
        "Site constraints — footprint, existing infrastructure, upgrade pathway",
        "Effluent quality requirements and regulatory licence conditions",
        "Utility priorities — energy, carbon, cost reduction",
        "Local contractor capability and procurement strategy",
        "Detailed geotechnical and hydraulic assessment",
    ]
    for r in recs:
        _docx_bullet(doc, r)
    _docx_body(doc,
        "A detailed feasibility study with site-specific cost estimation (±15-20%) "
        "is recommended before proceeding to detailed design or procurement.")

    # Closing action statement — programme urgency
    dec_close = getattr(report, "decision", None)
    if dec_close and getattr(dec_close, "recommended_approach", []):
        from docx.shared import Pt
        p = doc.add_paragraph()
        run = p.add_run(
            "Recommended next step: initiate parallel concept validation immediately "
            "to maintain programme schedule and avoid premature technology lock-in."
        )
        run.bold = True
        run.font.size = Pt(9)

    # Appendix — Assumptions
    if report.assumptions_appendix:
        doc.add_page_break()
        _docx_heading(doc, "Appendix A — Key Assumptions")
        _docx_hr(doc)
        skip_prefixes = ["capex_unit_costs", "pump_per_kw", "blower_per_kw",
                         "vsd_per_kw", "instrumentation", "design_contingency",
                         "contractor_margin", "client_oncosts", "return_sludge",
                         "gravity_thickener", "belt_thickener", "centrifuge",
                         "struvite", "fine_screen", "mbr_membrane_flat"]
        clean = []
        for item in report.assumptions_appendix:
            param = str(item.get("Parameter", ""))
            if any(param.startswith(p) for p in skip_prefixes):
                continue
            clean.append([
                item.get("Category", ""),
                _format_assumption_param(param),
                str(item.get("Value", "")),
                item.get("User Override", ""),
            ])
        if clean:
            _docx_table(doc, [["Category", "Parameter", "Value", "Override"]] + clean,
                        [2.5, 8.0, 3.5, 2.0])

    # Disclaimer
    doc.add_paragraph()
    _docx_hr(doc)
    _docx_body(doc,
        "DISCLAIMER: This report contains concept-level estimates (±40%) for comparative "
        "purposes only. CAPEX and OPEX figures are indicative AUD 2024 values and must not "
        "be used for procurement, funding approval, or investment decisions without "
        "site-specific engineering assessment by a qualified engineer.", 7)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
