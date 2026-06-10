"""filter_comparator.report.pdf_report

Python port of lib/pdfReport.js.

Builds the governance-grade filter performance assessment as a PDF using
reportlab. ``pdfReport.js`` is the content, structure and wording
specification: every section, table, heading and paragraph is reproduced
as-is. The technical computation is in engine/report_model.py; the charts
in report/charts.py.

Public entry point:

    build_pdf(model, charts=None, output_path=None) -> bytes

``model`` is the dict returned by engine.report_model.build_report_model.
The function returns the PDF as bytes, and also writes it to
``output_path`` if one is given.
"""

import io
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm  # noqa: F401  (kept for downstream use)
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, Flowable, KeepTogether,
)

from .charts import build_all_charts

# --------------------------------------------------------------------------
# Colour palette (from pdfReport.js COL)
# --------------------------------------------------------------------------
COL = {
    "ink":    HexColor("#0E1116"),
    "ink500": HexColor("#5B5F66"),
    "rust":   HexColor("#B0451F"),
    "ochre":  HexColor("#C8961A"),
    "sage":   HexColor("#5A7359"),
    "slate":  HexColor("#3F5870"),
    "rule":   HexColor("#C8C2B4"),
}

# Content width: A4 (595.276 pt) minus 40 pt margins each side.
PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 80  # 515.276 pt

# --------------------------------------------------------------------------
# Number formatters (from pdfReport.js f0/f1/f2/f3/pct1)
# --------------------------------------------------------------------------
def f1(v): return "%.1f" % v
def f2(v): return "%.2f" % v
def f3(v): return "%.3f" % v
def f0(v): return "%.0f" % v
def pct1(v): return "%.1f%%" % v


def ratio(a, b):
    return ("%.2f" % (a / b)) if b else "-"


# --------------------------------------------------------------------------
# Paragraph styles (from pdfReport.js styles{})
# --------------------------------------------------------------------------
def _style(name, **kw):
    base = dict(fontName="Helvetica", textColor=COL["ink"], fontSize=9.5,
                leading=9.5 * 1.25)
    base.update(kw)
    return ParagraphStyle(name, **base)


STYLES = {
    "title":    _style("title", fontName="Helvetica-Bold", fontSize=21, leading=24),
    "subtitle": _style("subtitle", fontSize=11, leading=13, textColor=COL["ink500"]),
    "h1":       _style("h1", fontName="Helvetica-Bold", fontSize=14, leading=16),
    "h2":       _style("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                       textColor=COL["rust"]),
    "body":     _style("body", fontSize=9.5, leading=9.5 * 1.25, alignment=TA_JUSTIFY),
    "bodyB":    _style("bodyB", fontName="Helvetica-Bold", fontSize=9.5,
                       leading=9.5 * 1.25, alignment=TA_JUSTIFY),
    "eyebrow":  _style("eyebrow", fontName="Helvetica-Bold", fontSize=7, leading=9,
                       textColor=COL["ink500"]),
    "cell":     _style("cell", fontSize=8, leading=10),
    "cellR":    _style("cellR", fontSize=8, leading=10, alignment=TA_RIGHT),
    "note":     _style("note", fontName="Helvetica-Oblique", fontSize=8, leading=9.6,
                       textColor=COL["ink500"]),
    "caption":  _style("caption", fontName="Helvetica-Oblique", fontSize=7.5,
                       leading=9, textColor=COL["ink500"]),
    "foot":     _style("foot", fontSize=7, leading=8.4, textColor=COL["ink500"]),
    "partTitle": _style("partTitle", fontName="Helvetica-Bold", fontSize=16, leading=18),
    "dsTitle":  _style("dsTitle", fontName="Helvetica-Bold", fontSize=17, leading=19),
    "dsH":      _style("dsH", fontName="Helvetica-Bold", fontSize=10, leading=12,
                       textColor=COL["rust"]),
    "dsB":      _style("dsB", fontSize=9, leading=9 * 1.2, alignment=TA_JUSTIFY),
    "dsBb":     _style("dsBb", fontName="Helvetica-Bold", fontSize=9, leading=9 * 1.2,
                       alignment=TA_JUSTIFY),
    "boxBullet": _style("boxBullet", fontSize=8, leading=9.2),
    "boxNote":  _style("boxNote", fontName="Helvetica-Oblique", fontSize=7.5,
                       leading=9, textColor=COL["ink500"]),
}


def _esc(t):
    """Escape text for a reportlab Paragraph (mini-HTML markup)."""
    return _xml_escape(str(t))


def _hx(color):
    """Return a reportlab-markup hex string ('#rrggbb') for a Color."""
    if hasattr(color, "hexval"):
        return "#" + color.hexval()[2:]
    return str(color)


# --------------------------------------------------------------------------
# Flowables
# --------------------------------------------------------------------------
class HRule(Flowable):
    """A horizontal rule, matching pdfmake's {canvas:[{type:'line'...}]}."""

    def __init__(self, width=CONTENT_W, thickness=0.5, color=COL["rule"],
                 space_before=1, space_after=6):
        super().__init__()
        self.width = width
        self.thickness = thickness
        self.color = color
        self.space_before = space_before
        self.space_after = space_after
        self.height = thickness + space_before + space_after

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        y = self.space_after + self.thickness / 2.0
        self.canv.line(0, y, self.width, y)


# --------------------------------------------------------------------------
# Cell rendering for tables
# --------------------------------------------------------------------------
def _cell_para(spec, right=False, header=False):
    """Convert a cell spec (str or {text,bold,color}) into a Paragraph.

    Mirrors pdfReport.js cell rendering: header cells use the eyebrow style;
    body cells the cell style, right-aligned for non-label columns.
    """
    if header:
        text = spec if isinstance(spec, str) else str(spec.get("text", ""))
        text = _esc(text).replace("\n", "<br/>")
        st = ParagraphStyle("hc", parent=STYLES["eyebrow"],
                             alignment=TA_RIGHT if right else TA_LEFT)
        return Paragraph(text, st)

    if isinstance(spec, dict):
        text = _esc(spec.get("text", ""))
        bold = spec.get("bold", False)
        color = spec.get("color", COL["ink"])
        if bold:
            text = "<b>%s</b>" % text
        text = '<font color="%s">%s</font>' % (
            _hx(color) if hasattr(color, "hexval") else color, text)
    else:
        text = _esc(spec)

    st = STYLES["cellR"] if right else STYLES["cell"]
    return Paragraph(text, st)


# --------------------------------------------------------------------------
# Coloured-value cell helpers (from pdfReport.js mgn/hcol/conf/wcol/bold/flag)
# --------------------------------------------------------------------------
def mgn(v):
    """Margin cell: green if feasible, red if deficit."""
    return {"text": "%s%.2f" % ("+" if v >= 0 else "", v), "bold": True,
            "color": COL["sage"] if v >= 0 else COL["rust"]}


def hcol(v):
    """Head-for-load cell: green if comfortable, ochre if tight, red if near-zero."""
    color = COL["rust"] if v < 0.2 else (COL["ochre"] if v < 0.8 else COL["sage"])
    return {"text": "%s%.2f" % ("+" if v >= 0 else "", v), "bold": True, "color": color}


def bold_cell(t):
    return {"text": str(t), "bold": True}


def flag_cell(t):
    return {"text": str(t), "bold": True, "color": COL["ochre"]}


def conf(level):
    """Confidence cell colour."""
    l = str(level)
    low = l.lower()
    if "high" in low and "low" not in low:
        c = COL["sage"]
    elif "low" in low:
        c = COL["rust"]
    else:
        c = COL["ochre"]
    return {"text": l, "bold": True, "color": c}


def wcol(p, hi, mid):
    """Washwater % cell colour."""
    color = COL["sage"] if p < mid else (COL["ochre"] if p < hi else COL["rust"])
    return {"text": pct1(p), "bold": True, "color": color}


# --------------------------------------------------------------------------
# Style spacing (pdfmake element margins -> reportlab space before/after)
# --------------------------------------------------------------------------
STYLES["h1"].spaceBefore = 12
STYLES["h2"].spaceBefore = 8
STYLES["h2"].spaceAfter = 3
STYLES["body"].spaceAfter = 6
STYLES["bodyB"].spaceAfter = 6
STYLES["note"].spaceAfter = 6
STYLES["caption"].spaceBefore = 2
STYLES["caption"].spaceAfter = 8
STYLES["dsH"].spaceBefore = 7
STYLES["dsH"].spaceAfter = 2
STYLES["dsB"].spaceAfter = 4
STYLES["dsBb"].spaceAfter = 4
STYLES["title"].spaceAfter = 0
STYLES["subtitle"].spaceBefore = 2
STYLES["subtitle"].spaceAfter = 6


# --------------------------------------------------------------------------
# Table builders (from pdfReport.js sectionTable / gridTable / box)
# --------------------------------------------------------------------------
def section_table(rows, widths):
    """Rows are {"section": str} or {"cells": [...]}.

    Section rows span all columns with a heavier ink rule below; data rows
    carry a light rule. First column left-aligned, the rest right-aligned.
    """
    body = []
    section_idx = set()
    for row in rows:
        if "section" in row:
            section_idx.add(len(body))
            cells = [_cell_para({"text": row["section"]}, header=True)]
            cells += [""] * (len(widths) - 1)
            body.append(cells)
        else:
            body.append([
                _cell_para(c, right=(ci > 0))
                for ci, c in enumerate(row["cells"])
            ])

    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    n = len(body)
    for r in range(n):
        if r in section_idx:
            style.append(("SPAN", (0, r), (-1, r)))
            style.append(("TOPPADDING", (0, r), (-1, r), 5))
            style.append(("BOTTOMPADDING", (0, r), (-1, r), 2))
        if r < n - 1:  # line below row r
            if r in section_idx:
                style.append(("LINEBELOW", (0, r), (-1, r), 0.9, COL["ink"]))
            else:
                style.append(("LINEBELOW", (0, r), (-1, r), 0.3, COL["rule"]))
    t = Table(body, colWidths=widths)
    t.setStyle(TableStyle(style))
    t.spaceBefore = 2
    t.spaceAfter = 2
    return t


def grid_table(headers, rows, widths):
    """Generic grid table with a header row."""
    body = [[_cell_para(h, header=True) for h in headers]]
    for r in rows:
        body.append([
            _cell_para(c, right=False) for c in r
        ])
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, COL["ink"]),
    ]
    n = len(body)
    for r in range(1, n - 1):
        style.append(("LINEBELOW", (0, r), (-1, r), 0.3, COL["rule"]))
    t = Table(body, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle(style))
    t.spaceBefore = 2
    t.spaceAfter = 8
    return t


def box(flowables, accent=COL["ink"]):
    """Boxed callout with a coloured border."""
    inner = Table([[flowables]], colWidths=[CONTENT_W])
    inner.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    inner.spaceBefore = 2
    inner.spaceAfter = 10
    return inner


def bullet(text, accent=COL["rust"], style="body"):
    """A bulleted paragraph (bullet glyph in the accent colour)."""
    st = STYLES[style]
    hexc = _hx(accent) if hasattr(accent, "hexval") else accent
    para = Paragraph(
        '<font color="%s">&bull;&nbsp;&nbsp;</font>%s' % (hexc, _esc(text)),
        ParagraphStyle("bul", parent=st, leftIndent=10, firstLineIndent=-10,
                       spaceAfter=3))
    return para


def _chart_image(buf, width=470):
    buf.seek(0)
    img = Image(buf)
    scale = width / float(img.imageWidth)
    img.drawWidth = width
    img.drawHeight = img.imageHeight * scale
    img.hAlign = "CENTER"
    img.spaceBefore = 8
    img.spaceAfter = 2
    return img


# --------------------------------------------------------------------------
# Structural element helpers (from pdfReport.js H1/H2/NOTE/BODY/partHeader)
# --------------------------------------------------------------------------
def _H1(num, title, brk):
    out = []
    if brk:
        out.append(PageBreak())
    head = Paragraph("%s   %s" % (_esc(num), _esc(title)), STYLES["h1"])
    rule = HRule(thickness=0.5, color=COL["rule"], space_before=1, space_after=6)
    out.append(KeepTogether([head, rule]))
    return out


def _H2(t):
    return Paragraph(_esc(t), STYLES["h2"])


def _NOTE(t):
    return Paragraph(_esc(t), STYLES["note"])


def _BODY(t):
    return Paragraph(_esc(t), STYLES["body"])


def _BODYB(t):
    return Paragraph(_esc(t), STYLES["bodyB"])


def _CAP(t):
    return Paragraph(_esc(t), STYLES["caption"])


def _part_header(letter, title, sub):
    out = [PageBreak()]
    out.append(Paragraph(
        '<font color="%s">PART %s</font>' % (_hx(COL["rust"]), _esc(letter)),
        ParagraphStyle("ph", parent=STYLES["eyebrow"], spaceAfter=2)))
    out.append(Paragraph(_esc(title),
                          ParagraphStyle("pt", parent=STYLES["partTitle"], spaceAfter=2)))
    out.append(HRule(thickness=1.2, color=COL["ink"], space_before=0, space_after=4))
    out.append(Paragraph(_esc(sub),
                          ParagraphStyle("ps", parent=STYLES["note"], spaceAfter=8)))
    return out


def _box_bullet(text, accent=COL["rust"]):
    hexc = _hx(accent)
    return Paragraph(
        '<font color="%s">&bull;&nbsp;&nbsp;</font>%s' % (hexc, _esc(text)),
        ParagraphStyle("bb", parent=STYLES["boxBullet"], leftIndent=10,
                       firstLineIndent=-10, spaceAfter=2.5))


def _validation_block(model):
    """Validation outcome rendering (pdfReport.js validationBlock)."""
    v = model.get("validation")
    if not v or v.get("severity") == "ok":
        return _BODY(
            "Input validation: derived filtration velocities and solids holding "
            "capacities have been checked against physical limits and fall within "
            "plausible ranges for granular-media filtration. No implausible inputs "
            "were detected.")
    colr = COL["rust"] if v["severity"] == "error" else COL["ochre"]
    head_text = (
        "Input validation: physically impossible values were detected. This "
        "assessment is not decision-ready until the flagged inputs are corrected."
        if v["severity"] == "error" else
        "Input validation: values outside typical ranges were detected. Verify "
        "the flagged inputs before relying on the result.")
    items = [Paragraph(
        '<font color="%s"><b>%s</b></font>' % (_hx(colr), _esc(head_text)),
        ParagraphStyle("vh", parent=STYLES["body"], fontSize=9.5, spaceAfter=4))]
    for issue in v["issues"]:
        items.append(_box_bullet(issue["message"], accent=colr))
    return KeepTogether(items)


# --------------------------------------------------------------------------
# Story builder — the full report content (faithful port of docDefinition)
# --------------------------------------------------------------------------
def _build_story(model, charts):
    N = model["names"]
    d1, d2 = N["d1"], N["d2"]
    D1, D2 = "D1", "D2"
    F1, F2 = model["filters"]["D1"], model["filters"]["D2"]
    C, S = model["modes"]["coag"], model["modes"]["soft"]
    O = model["opportunityD2"]
    RM = model["removalOpportunityD2"]
    rd1, rd2 = model["redundancy"]["D1"], model["redundancy"]["D2"]
    cw1, cw2 = model["coldWater"]["D1"], model["coldWater"]["D2"]
    W = [225, 92, 92, 96]
    kCap = model["kCap"]
    poreFill = model["poreFill"]
    lfl = model["lfl"]

    # Project descriptors and per-design softening-route descriptions.
    project = model.get("project", {}) or {}
    routes = model.get("routes", {}) or {}
    plant = project.get("plant", "the water treatment plant")
    temp_basis = project.get("temperature_basis", "")
    algal_cells = project.get("algal_cells_ml", 0)
    algal_str = "{:,}".format(int(algal_cells)) if algal_cells else "the design-basis"
    route_d1 = (routes.get("D1", {}) or {}).get("text", "the route described by the designer")
    route_d2 = (routes.get("D2", {}) or {}).get("text", "the route described by the designer")
    mg_removal = (bool((routes.get("D1", {}) or {}).get("mg_removal"))
                  or bool((routes.get("D2", {}) or {}).get("mg_removal")))
    # A parenthetical "(a <basis> basis)" only when a basis phrase is supplied.
    temp_basis_paren = (" (a %s basis)" % temp_basis) if temp_basis else ""

    def layerD(filt, m):
        l = next((x for x in filt["mediaLayers"] if x["media"] == m), None)
        return l["depth"] if l else 0

    def rget(rd, key):
        return next((x for x in rd if x["key"] == key), {})

    def bed_depth(filt):
        return sum(l["depth"] for l in filt["mediaLayers"])

    c = []

    # ===================================================================
    # COVER
    # ===================================================================
    c.append(Paragraph("FILTER PERFORMANCE ASSESSMENT", STYLES["title"]))
    c.append(Paragraph("%s (RGMF) and %s (DMF), rapid gravity filtration"
                       % (_esc(d1), _esc(d2)), STYLES["subtitle"]))
    c.append(HRule(thickness=1, color=COL["ink"], space_before=0, space_after=10))

    ctrl = [
        ["Document", "Filter performance assessment, independent engineering review"],
        ["Project", "%s ML/d %s" % (f0(model["flow"]), plant)],
        ["Assessment type", "Independent comparative engineering review for design selection"],
        ["Configuration %s" % D1, d1],
        ["Configuration %s" % D2, d2],
        ["Operating modes assessed",
         "Coagulation (maximum turbidity) and 100% lime softening"],
        ["Governing flow", "%s ML/d maximum design flow" % f0(model["flow"])],
        ["Revision", "A, for client review"],
        ["Status", "Draft, subject to verification actions in Section 16"],
    ]
    if model.get("preparedBy"):
        ctrl.append(["Prepared by", model["preparedBy"]])
    ctrl_body = [[_cell_para({"text": k}, header=True), _cell_para(v)]
                 for k, v in ctrl]
    ctrl_tbl = Table(ctrl_body, colWidths=[135, 380])
    ctrl_style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for r in range(len(ctrl_body) - 1):
        ctrl_style.append(("LINEBELOW", (0, r), (-1, r), 0.3, COL["rule"]))
    ctrl_tbl.setStyle(TableStyle(ctrl_style))
    ctrl_tbl.spaceAfter = 14
    c.append(ctrl_tbl)

    # critical assumptions box
    assumptions = [
        ("Governing flow: %s ML/d maximum design flow. The assessment is anchored "
         "on the maximum design flow; N-1 and N-2 redundancy conditions are "
         "evaluated against it." % model["flow"]),
        ("Feed TSS to the filter is accepted as documented by the designers: "
         "coagulation %s mg/L (%s) and %s mg/L (%s); lime softening %s mg/L (%s) "
         "and %s mg/L (%s). Where the two lime-softening figures differ, the "
         "difference reflects the different softening routes adopted by the two "
         "designers, described below; the figures are designer-supplied and "
         "accepted as documented."
         % (f1(C["D1"]["tss"]), D1, f1(C["D2"]["tss"]), D2,
            f1(S["D1"]["tss"]), D1, f1(S["D2"]["tss"]), D2)),
        ("Softening route, %s: %s. Softening route, %s: %s. The deposit "
         "structure factor used for each lime-softening head budget reflects "
         "the precipitate composition implied by the route as documented; "
         "where a route generates a magnesium hydroxide fraction its size is "
         "to be confirmed (Section 11)." % (d1, route_d1, d2, route_d2)),
        ("Clean-bed headloss by Kozeny-Carman with uniformity-coefficient "
         "correction, evaluated at the %s degrees C minimum design water "
         "temperature for the source%s. Temperature sensitivity is assessed "
         "across the 15 to 28 degrees C range expected for the source water; "
         "the 21 and 28 degrees C values are indicative and to be confirmed."
         % (model["tempMin"], temp_basis_paren)),
        ("Driving head accepted as documented: %s %s m, %s %s m, to be confirmed "
         "against the plant hydraulic profile."
         % (D1, f2(F1["drivingHead_m"]), D2, f2(F2["drivingHead_m"]))),
        ("%s recycles filter-to-waste to the DAF inlet; %s sends filter-to-waste "
         "to waste." % (d2, d1)),
        ("Designer-supplied data not yet available is listed in Section 16. This "
         "assessment is subject to those confirmations."),
    ]
    box_content = [Paragraph(
        '<font color="%s">CRITICAL ASSUMPTIONS</font>' % _hx(COL["rust"]),
        ParagraphStyle("ca", parent=STYLES["eyebrow"], spaceAfter=4))]
    for t in assumptions:
        box_content.append(_box_bullet(t))
    box_content.append(Paragraph(
        _esc("This is a screening and comparative assessment for design review. "
             "It is subject to the confirmations above and is not a substitute "
             "for detailed design, pilot validation, or independent "
             "clarification modelling."),
        ParagraphStyle("can", parent=STYLES["boxNote"], spaceBefore=3)))
    c.append(box(box_content, COL["ink"]))

    # ===================================================================
    # EXECUTIVE DECISION SUMMARY
    # ===================================================================
    c.append(PageBreak())
    c.append(Paragraph(
        '<font color="%s">FOR THE DECISION-MAKER</font>' % _hx(COL["rust"]),
        ParagraphStyle("dse", parent=STYLES["eyebrow"], spaceAfter=2)))
    c.append(Paragraph("Executive Decision Summary",
                       ParagraphStyle("dst", parent=STYLES["dsTitle"], spaceAfter=3)))
    c.append(HRule(thickness=1.2, color=COL["ink"], space_before=0, space_after=4))
    c.append(Paragraph(_esc(
        "A plain-language decision note for senior readers. The full technical "
        "assessment, with all supporting figures, begins at Section 1."),
        ParagraphStyle("dsn", parent=STYLES["note"], spaceAfter=6)))

    def dsH(t):
        c.append(Paragraph(_esc(t), STYLES["dsH"]))

    def dsB(t):
        c.append(Paragraph(_esc(t), STYLES["dsB"]))

    def dsBb(t):
        c.append(Paragraph(_esc(t), STYLES["dsBb"]))

    dsH("Decision context")
    dsB("Two rapid gravity filtration configurations have been proposed for the "
        "120 ML/d plant, one by %s and one by %s. This note summarises an "
        "independent engineering comparison of the two, prepared to inform which "
        "should be selected. It compares how each configuration performs and how "
        "it operates; it does not compare cost." % (d1, d2))

    dsH("The main tradeoff")
    dsBb("The choice is a genuine tradeoff, not a case of one configuration being "
         "better. The %s configuration uses markedly less washwater and loses "
         "less water day to day, but operates with less spare hydraulic "
         "capacity. The %s configuration has greater hydraulic resilience and "
         "absorbs upset conditions more readily, but imposes a substantially "
         "larger washwater and recycle burden on the plant." % (d1, d2))

    dsH("What the assessment shows")
    dsB("Both configurations are hydraulically feasible across the full range of "
        "operating conditions assessed, including with filters out of service "
        "and at the coldest design water temperature. The %s configuration has "
        "the greater spare hydraulic capacity and the greater resilience to "
        "upsets such as a deterioration in the water reaching the filters. The "
        "%s configuration is the more economical in day-to-day water use, "
        "notably in softening operation, where it uses considerably less "
        "washwater. That washwater difference arises largely because the two "
        "designs soften the water by different routes, not because one filter "
        "is inferior to the other." % (d2, d1))

    dsH("What remains uncertain")
    dsB("Several of the findings depend on inputs that should be confirmed "
        "before they are relied upon for selection:")
    c.append(grid_table(
        ["Finding", "Depends on"],
        [
            ["%s uses less washwater" % d1,
             "Its softening route delivering the low solids carryover to the "
             "filters assumed in the assessment."],
            ["%s has greater hydraulic resilience" % d2,
             "The hydraulic head documented for the plant being available, and "
             "the larger washwater recycle being workable in operation."],
            ["%s could remove more solids than assumed" % d2,
             "The quality of the material reaching the filters being good enough "
             "to be captured efficiently."],
        ],
        [200, 315]))

    dsH("What must be verified before selection")
    dsB("Four things should be confirmed before this assessment is used to "
        "choose a configuration: the plant hydraulic design and the head "
        "available to drive flow through the filters; the softening duty "
        "assumed for each design; the basis for handling and recycling "
        "washwater; and evidence of the filtered-water quality each "
        "configuration achieves through a full filter cycle.")

    dsH("Practical implication for the client")
    dsBb("This assessment should not be used to select a preferred configuration "
         "until the plant hydraulic design, the softening duty, the washwater "
         "and recycle basis, and filtered-water quality evidence are confirmed.")
    dsB("Once those are in hand, the decision becomes a clear, values-based "
        "choice: lower day-to-day water use with the %s configuration, or "
        "greater hydraulic resilience with the %s configuration. The sections "
        "that follow provide the full technical basis for that choice."
        % (d1, d2))

    # ===================================================================
    # 1  EXECUTIVE SUMMARY
    # ===================================================================
    c.extend(_H1("1", "Executive summary", True))
    c.append(_H2("Purpose and basis"))
    c.append(_BODY(
        "This report is an independent comparative engineering review of two "
        "rapid gravity filter configurations proposed for the 120 ML/d plant: "
        "the %s configuration (an eight-cell, four-layer rapid gravity "
        "multimedia filter) and the %s configuration (a six-cell dual-media "
        "filter with DAF recirculation). The review covers intrinsic filter "
        "capability and whole-of-plant system performance across the two "
        "operating modes the plant runs: coagulation at maximum turbidity, and "
        "100%% lime softening. It is governed by the %s ML/d maximum design "
        "flow. Confidence levels, dependencies and limitations are stated in "
        "Sections 2 and 3." % (d1, d2, model["flow"])))
    c.append(_H2("Key findings"))
    c.append(_BODY(
        "Intrinsic filter capability. On intrinsic hydraulic capability, "
        "comprising pore-fill solids holding capacity, clean-bed headloss, "
        "redundancy headroom and resilience, the %s configuration demonstrates "
        "greater capacity and greater hydraulic margin in both operating modes. "
        "This finding rests on documented filter geometry and established "
        "headloss models and is assessed at high confidence." % d2))
    c.append(_BODY(
        "Washwater performance. On as-built whole-of-plant washwater demand the "
        "%s configuration demonstrates the lower demand. This outcome is "
        "materially dependent on the lower clarified-water solids loading "
        "delivered to the %s filters, particularly under lime softening (%s "
        "mg/L against %s mg/L). That difference is a designer-supplied "
        "consequence of the different softening routes the two designers adopt, "
        "not an intrinsic filter-design advantage; the basis for each "
        "lime-softening feed figure is set out in Section 8."
        % (d1, d1, f1(S["D1"]["tss"]), f1(S["D2"]["tss"]))))
    c.append(_BODY(
        "Hydraulic reserve. The %s configuration operates with the lower "
        "hydraulic reserve of the two. Its as-built head margin is %s m in "
        "coagulation and %s m in lime softening. At the governing redundancy "
        "condition, N-1 with one filter out of service, and the %s degrees C "
        "minimum design water temperature, its head available for solids load "
        "is about %s m, against about %s m for the %s configuration. Both are "
        "positive and workable; %s carries the lower reserve of the two, and "
        "that warrants confirmation against the plant hydraulic profile."
        % (d1, f2(C["D1"]["margin"]), f2(S["D1"]["margin"]), model["tempMin"],
           f1(cw1[0]["N1"]["headForLoad"]), f1(cw2[0]["N1"]["headForLoad"]),
           d2, d1)))
    c.append(_BODY(
        "Washwater handling. The %s configuration handles a substantially "
        "larger washwater volume, reaching approximately %s%% of plant flow in "
        "lime softening when filter-to-waste is included. While the "
        "filter-to-waste stream is recycled to the DAF and is not a net water "
        "loss, it is a material recycle, DAF and sludge loading consideration "
        "in its own right." % (d2, f0(S["D2"]["bw"]["totalPctFlow"]))))
    c.append(_H2("Critical dependencies"))
    c.append(_BODY(
        "These findings are conditional. The %s washwater-performance position "
        "depends on the %s softening route delivering the lower solids "
        "carryover assumed. The %s resilience position depends on the "
        "documented driving head being confirmed. The feasibility of %s's "
        "filter-to-waste recycling depends on acceptable DAF recycle loading. "
        "These and other dependencies are set out in Section 12; if a "
        "dependency is not met, the associated finding changes."
        % (d1, d1, d2, d2)))
    c.append(_BODY(
        "Where the lime-softening feed TSS differs between the configurations, "
        "%s mg/L for %s against %s mg/L for %s, the difference is attributed to "
        "the different softening routes the two designers have adopted, not to "
        "an unexplained clarifier-performance gap. The figures are "
        "designer-supplied and accepted as documented. The point to confirm is "
        "therefore that the difference in softening route and duty is intended "
        "and understood, since it carries through to the whole-of-plant "
        "comparison."
        % (f1(S["D1"]["tss"]), d1, f1(S["D2"]["tss"]), d2)))
    c.append(_H2("Implications"))
    c.append(_BODY(
        "Selecting the %s configuration would prioritise lower day-to-day "
        "washwater demand under stable clarified-water conditions, while "
        "accepting reduced hydraulic reserve and greater operational "
        "sensitivity to transient deterioration events. Selecting the %s "
        "configuration would prioritise hydraulic robustness and resilience to "
        "feed variability, while accepting greater washwater handling, recycle "
        "loading and operational complexity. Section 13 sets out a "
        "risk-weighted decision framework, and Section 14 the operational and "
        "lifecycle implications." % (d1, d2)))
    c.append(_H2("Recommended next actions"))
    for t in [
        "Confirm the plant hydraulic profile and the actual available driving "
        "head for each configuration, including the N-1 condition at the "
        "minimum design water temperature.",
        "Confirm that the difference in softening route and duty between the "
        "two designs is intended and understood, and, where a route generates "
        "a magnesium hydroxide fraction, confirm the size of that fraction in "
        "the softening precipitate.",
        "Challenge and verify the %s filter's assumed %s%% TSS removal, which "
        "appears conservative for the bed depth (Section 14)."
        % (d2, model["removalOpportunityD2"]["asBuiltRemoval"]),
        "Obtain dirty-bed terminal headloss data across the design temperature "
        "range, and backwash, air-scour and bed-expansion data, from each "
        "designer.",
        "Obtain the filter-to-waste duration basis with turbidity recovery "
        "curves, and pilot or reference-plant data, before selection.",
        "Complete the verification actions in Section 16 and re-confirm the "
        "comparison before a configuration is selected.",
    ]:
        c.append(bullet(t))
    c.append(_H2("Overall position"))
    c.append(box([_BODYB(
        "Based on the hydraulic head-budget assessment, solids holding capacity "
        "analysis and resilience testing undertaken for this review, the %s "
        "configuration demonstrates greater hydraulic robustness and resilience "
        "under the assessed operating envelopes. The %s configuration "
        "demonstrates a lower as-built whole-of-plant washwater demand. That "
        "comparative outcome is, however, highly sensitive to the realised %s "
        "softening carryover, because that single input materially drives the "
        "washwater, run-length and hydraulic-reserve comparisons; if the %s "
        "softening route carries more solids forward than documented, the "
        "apparent washwater advantage narrows quickly. Neither configuration "
        "should be selected or rejected on the basis of this assessment alone. "
        "The decision framework in Section 13 sets out how the choice depends "
        "on the client's prioritisation, and the verification actions in "
        "Section 16 should be completed first." % (d2, d1, d1, d1))],
        COL["rust"]))

    # ===================================================================
    # 2  BASIS OF ASSESSMENT AND CONFIDENCE
    # ===================================================================
    c.extend(_H1("2", "Basis of assessment and confidence", False))
    c.append(_BODY(
        "This assessment is governed by the %s ML/d maximum design flow. "
        "Filters must be robust at their worst hydraulic condition, so the head "
        "budget, filtration velocity and feasibility checks are evaluated at "
        "the maximum design flow rather than the average. The N-1 and N-2 "
        "redundancy conditions and a water-temperature sensitivity are "
        "evaluated against the same flow (Section 7)." % model["flow"]))
    c.append(_validation_block(model))
    c.append(_H2("Confidence in the assessment findings"))
    c.append(_NOTE(
        "Confidence reflects the quality and independence of the data "
        "underpinning each finding. Findings drawn from documented geometry and "
        "established models carry high confidence; findings dependent on "
        "un-verified upstream assumptions carry lower confidence."))
    c.append(grid_table(
        ["Finding area", "Confidence", "Basis for the rating"],
        [
            ["Intrinsic hydraulic comparison", conf("High"),
             "Documented filter geometry and established clean-bed and "
             "dirty-bed models."],
            ["Relative solids holding capacity", conf("High"),
             "Documented media depths and grading; capacity benchmarks from "
             "literature."],
            ["Redundancy and temperature robustness", conf("High"),
             "Derived from documented geometry; driving head still to be "
             "confirmed."],
            ["Coagulation feed assumptions", conf("Medium"),
             "Feed TSS accepted as submitted; similar between the two "
             "configurations."],
            ["Lime-softening feed assumptions", conf("Medium"),
             "Feed-TSS difference explained by the two softening duties; "
             "designer-supplied and within typical ranges."],
            ["Whole-of-plant washwater performance", conf("Medium"),
             "Depends on feed TSS and run-length assumptions, and on FTW "
             "handling philosophy."],
            ["Long-term fouling and media resilience", conf("Medium"),
             "No pilot or physical media-testing data available to this "
             "review."],
        ],
        [148, 78, 289]))
    c.append(_NOTE(
        "The confidence ratings above are the reviewing engineer's judgement "
        "and are to be confirmed by the report author prior to issue."))

    # ===================================================================
    # 3  METHODOLOGY AND LIMITATIONS
    # ===================================================================
    c.extend(_H1("3", "Assessment methodology and limitations", False))
    c.append(_H2("Methodology"))
    c.append(_BODY(
        "The assessment applies a hydraulic head-budget method. For each "
        "configuration and operating point the terminal headloss required to "
        "deliver the design run is built up from clean-bed headloss, underdrain "
        "headloss, solids-load headloss and appurtenance losses, and compared "
        "against the available driving head. A positive margin indicates "
        "hydraulic feasibility; the size of the margin indicates hydraulic "
        "reserve."))
    c.append(_BODY(
        "Clean-bed headloss is computed by the Kozeny-Carman equation with the "
        "Cleasby-Logsdon uniformity-coefficient correction, at the %s degrees C "
        "minimum design water temperature, with a sensitivity across the 15 to "
        "28 degrees C range expected for the source water. Solids-load headloss "
        "is computed by the Mints-Tien differential model; the effective "
        "specific deposit is adjusted for the precipitate type through a "
        "deposit structure factor (defined in Section 8). Solids holding "
        "capacity K is back-calculated from the documented backwash frequency "
        "and benchmarked against the bed's theoretical pore-fill ceiling, the "
        "Kawamura range, the AWWA M37 and Cleasby-Logsdon typical range, and a "
        "pragmatic breakthrough cap of %s kg/m2/run. That %s kg/m2/run value is "
        "used here as a screening-level operational ceiling consistent with "
        "conventional rapid gravity filtration practice, rather than as a "
        "universal physical limit; the achievable figure for a specific bed and "
        "floc should be confirmed by pilot or reference-plant data. Redundancy "
        "is assessed at N, N-1 and N-2 filters in service at the maximum design "
        "flow. Resilience is assessed by a 100%% feed-solids deterioration "
        "sensitivity. A validation layer checks derived velocities and K values "
        "against physical limits." % (model["tempMin"], f1(kCap), f1(kCap))))
    c.append(_H2("Scope of this assessment"))
    c.append(_BODY(
        "In scope: the two filter configurations as documented in the designer "
        "process calculations, comprising filter geometry and media, the "
        "hydraulic head budget, backwash and washwater balance, redundancy, and "
        "resilience to feed deterioration. Not in scope: clarifier and upstream "
        "process design, the detailed plant hydraulic profile, structural, "
        "mechanical and electrical design, and capital and lifecycle cost "
        "estimation. Feed TSS to each filter is accepted as submitted by the "
        "designers and is not independently modelled."))
    c.append(_H2("Limitations of assessment"))
    c.append(_NOTE("The following limitations apply and should be read with "
                   "every finding in this report."))
    for t in [
        "No pilot-plant validation has been undertaken or reviewed.",
        "The assessment relies on data submitted by the designers; proprietary "
        "designer assumptions are not independently accessible in full.",
        "No computational fluid dynamics verification of the filter or "
        "underdrain hydraulics has been performed.",
        "No physical media testing, grading verification or media-expansion "
        "testing has been performed.",
        "No independent clarification or lime-softening modelling has been "
        "performed; the feed TSS to each filter is accepted as submitted.",
        "The clean-bed and dirty-bed models are screening-level; dirty-bed "
        "terminal headloss has not been independently measured.",
        "Driving head is accepted as documented and has not been verified "
        "against an as-built or detailed-design hydraulic profile.",
    ]:
        c.append(bullet(t))
    c.append(_H2("Governing references"))
    for t in [
        "Cleasby, J.L. and Logsdon, G.S. (1999). Granular Bed and Precoat "
        "Filtration. In Water Quality and Treatment, 5th edition, AWWA and "
        "McGraw-Hill.",
        "Kawamura, S. (2000). Integrated Design and Operation of Water "
        "Treatment Facilities, 2nd edition, John Wiley and Sons.",
        "AWWA Manual M37, Operational Control of Coagulation and Filtration "
        "Processes.",
        "Mints, D.M. (1966). Modern theory of filtration. International Water "
        "Supply Congress, Barcelona.",
    ]:
        c.append(bullet(t, COL["rust"], "foot"))

    _build_part_a(c, locals())
    _build_part_b(c, locals())
    _build_part_c(c, locals())
    return c


# --------------------------------------------------------------------------
# PART A — INTRINSIC FILTER CAPABILITY (sections 4-7)
# --------------------------------------------------------------------------
def _build_part_a(c, ctx):
    d1, d2 = ctx["d1"], ctx["d2"]
    D1, D2 = ctx["D1"], ctx["D2"]
    F1, F2 = ctx["F1"], ctx["F2"]
    C, S = ctx["C"], ctx["S"]
    rd1, rd2 = ctx["rd1"], ctx["rd2"]
    cw1, cw2 = ctx["cw1"], ctx["cw2"]
    W, kCap = ctx["W"], ctx["kCap"]
    poreFill, lfl = ctx["poreFill"], ctx["lfl"]
    layerD, rget, bed_depth = ctx["layerD"], ctx["rget"], ctx["bed_depth"]
    model = ctx["model"]

    c.extend(_part_header(
        "A", "Intrinsic filter capability",
        "The sections in Part A assess each filter on its own engineering "
        "merit, independent of upstream feed assumptions. They describe what "
        "each bed can do hydraulically."))

    # ---- 4  Filter design ----
    c.extend(_H1("4", "Filter design and configuration", False))
    c.append(_NOTE("Both configurations as documented in the designer process "
                   "calculations. Filter geometry and media are common to both "
                   "operating modes."))
    c.append(section_table([
        {"section": "Configuration"},
        {"cells": ["Filter type", "RGMF, 4-layer multimedia", "DMF, dual-media", ""]},
        {"cells": ["Number of filters", str(F1["numFilters"]), str(F2["numFilters"]),
                   "%s %sx" % (D1, ratio(F1["numFilters"], F2["numFilters"]))]},
        {"cells": ["Area per filter (m2)", f1(F1["areaPerFilter_m2"]),
                   f1(F2["areaPerFilter_m2"]),
                   "%s %sx" % (D2, ratio(F2["areaPerFilter_m2"], F1["areaPerFilter_m2"]))]},
        {"cells": ["Total filter area (m2)",
                   f1(F1["numFilters"] * F1["areaPerFilter_m2"]),
                   f1(F2["numFilters"] * F2["areaPerFilter_m2"]),
                   "%s %sx" % (D2, ratio(F2["numFilters"] * F2["areaPerFilter_m2"],
                                         F1["numFilters"] * F1["areaPerFilter_m2"]))]},
        {"section": "Media stack"},
        {"cells": ["Anthracite depth (m)", f2(layerD(F1, "anthracite")),
                   f2(layerD(F2, "anthracite")),
                   "%s %sx" % (D2, ratio(layerD(F2, "anthracite"),
                                         layerD(F1, "anthracite")))]},
        {"cells": ["Sand depth (m)", f2(layerD(F1, "sand")), f2(layerD(F2, "sand")),
                   "%s %sx" % (D2, ratio(layerD(F2, "sand"), layerD(F1, "sand")))]},
        {"cells": ["Total bed depth (m)", f3(bed_depth(F1)), f2(bed_depth(F2)), ""]},
        {"section": "Hydraulics"},
        {"cells": ["Driving head (m)", f2(F1["drivingHead_m"]), f2(F2["drivingHead_m"]),
                   "%s %sx" % (D2, ratio(F2["drivingHead_m"], F1["drivingHead_m"]))]},
        {"cells": ["Appurtenance loss (m)", f2(F1["appurtenanceLoss_m"]),
                   f2(F2["appurtenanceLoss_m"]), "equal"]},
    ], W))
    c.append(_BODY(
        "The %s configuration provides materially greater media depth and total "
        "filtration volume. The bed is deeper, the anthracite layer is 40%% "
        "deeper, and the anthracite grain is coarser. The %s configuration "
        "spreads the duty across more cells, %s against %s, which is relevant "
        "to its redundancy behaviour in Section 7."
        % (d2, d1, F1["numFilters"], F2["numFilters"])))
    c.append(_H2("Media grading"))
    c.append(_NOTE("Effective size, uniformity coefficient and density govern "
                   "clean-bed headloss and backwash behaviour. Values as "
                   "documented by the designers."))
    MED_DENS = {"anthracite": 1600, "sand": 2650, "garnet": 4100, "gac": 1450}
    layer_name = {"anthracite": "Anthracite", "sand": "Silica sand",
                  "garnet": "Garnet", "gac": "GAC"}
    media_rows = []
    for tag, name, filt in [("D1", d1, F1), ("D2", d2, F2)]:
        for i, l in enumerate(filt["mediaLayers"]):
            is_support = l["media"] == "garnet" and (l.get("d_mm") or 0) >= 1.5
            media_rows.append([
                ("%s  %s" % (tag, name)) if i == 0 else "",
                layer_name.get(l["media"], l["media"]) + (" (support)" if is_support else ""),
                f2(l["depth"]), f2(l["d_mm"]), f2(l["uc"]),
                str(MED_DENS.get(l["media"], "-")),
            ])
    c.append(grid_table(
        ["Configuration", "Layer", "Depth (m)", "Effective size (mm)", "UC",
         "Density (kg/m3)"],
        media_rows, [120, 110, 62, 95, 50, 78]))
    c.append(_H2("Multimedia configuration: four-layer against dual-media"))
    c.append(_BODY(
        "The two configurations adopt different media philosophies. The %s "
        "configuration is a conventional dual-media bed, coarse anthracite over "
        "finer sand, with a single media interface. The %s configuration is a "
        "four-layer multimedia bed, anthracite over sand over garnet over a "
        "coarse garnet support, with three interfaces. Where properly designed "
        "and controlled, a graded multimedia bed can improve depth filtration "
        "and delay surface blinding relative to a conventional dual-media bed, "
        "making fuller use of the bed depth. That benefit, however, is obtained "
        "at the cost of operational sensitivity: each additional interface adds "
        "a place where the grading can be disturbed." % (d2, d1)))
    c.append(_BODY(
        "Each medium fluidises at a different backwash rate, so a four-layer "
        "bed has a narrower backwash-rate window within which all layers expand "
        "without intermixing. Imperfect restratification blurs the interfaces "
        "over time, raising clean-bed headloss, increasing mudball "
        "susceptibility and reducing filtrate quality. The %s four-layer bed is "
        "therefore more sensitive to backwash control and operator practice "
        "than the %s dual-media bed, and carries a higher long-term "
        "media-stability risk. This is a recognised characteristic of "
        "multimedia beds rather than a disqualifying feature, but the backwash "
        "and air-scour regime, bed expansion and restratification behaviour of "
        "the four-layer stack should be confirmed (Section 15)." % (d1, d2)))
    c.append(_H2("Media interface behaviour and long-term performance"))
    c.append(_BODY(
        "Because the four-layer arrangement turns on how its media interfaces "
        "behave over the plant life, it is worth setting out plainly why those "
        "interfaces matter. Multimedia filtration is graded by design. The bed "
        "is built coarse at the top and progressively finer with depth, so that "
        "water passes through steadily smaller pore spaces as it descends. The "
        "intent is to filter in depth rather than at the surface: the coarse "
        "upper anthracite removes the bulk of the solids without quickly "
        "blinding over, while the finer media below polish the water. A "
        "well-graded multimedia bed therefore makes fuller use of its depth and "
        "can run longer between washes than a bed that captures everything in "
        "its top layer. The progressively finer structure is the source of the "
        "benefit."))
    c.append(_BODY(
        "That same structure creates media interfaces, the zones where one "
        "medium meets the next and the pore size steps down. Particle capture "
        "and hydraulic behaviour change relatively abruptly across an "
        "interface, and solids tend to accumulate there. Particles that have "
        "travelled freely through the larger pores above arrive at the smaller "
        "pore throats below, where interception and deposition increase. Local "
        "flow then redistributes around the developing deposit, and because "
        "coagulated and softening flocs are compressible, they can consolidate "
        "and concentrate further in these transition zones. An interface is, in "
        "effect, a secondary filtration front within the bed."))
    c.append(_BODY(
        "Interfaces are maintained by backwashing. When the bed is fluidised "
        "and then allowed to settle, the media should restratify cleanly back "
        "into their layers, because each medium has a different size and "
        "density. If restratification is imperfect, repeated wash cycles can "
        "gradually blur an interface or create a mixed transition zone where "
        "the media intermingle. The sand-to-garnet interface in the %s "
        "four-layer bed is the most sensitive in this respect: garnet is "
        "considerably denser than sand, so the two respond very differently to "
        "a given wash rate, and garnet expands only modestly during backwash. "
        "Achieving enough expansion to clean the lower bed without drawing sand "
        "down into the garnet is a comparatively narrow operating window." % d1))
    c.append(_BODY(
        "The consequence of imperfect interface management is not sudden "
        "failure; it is gradual degradation over many operating cycles. The "
        "symptoms appear slowly: clean-bed headloss creeps upward, filter runs "
        "shorten, filtration becomes less even across the bed, mudballs may "
        "form, and ripening after backwash becomes less reliable. Effective air "
        "scour materially reduces this risk, by improving lower-bed cleaning "
        "and breaking up incipient deposits, but it does not remove the "
        "underlying need to manage the interfaces over the life of the plant. "
        "Because a multimedia bed contains more interfaces than a dual-media "
        "bed, it is generally less forgiving operationally and depends more "
        "heavily on consistent, well-controlled backwashing."))
    c.append(_BODYB(
        "These are recognised characteristics of multimedia filtration, not "
        "defects. Multimedia beds are widely and successfully used, and a "
        "well-designed installation performs very effectively where the media "
        "grading, underdrain system, air scour, wash sequencing and any "
        "collapse-pulse strategy are properly designed and consistently "
        "operated. The engineering requirement is therefore one of "
        "demonstration rather than doubt: the %s four-layer configuration "
        "should be supported by evidence that its interfaces restratify "
        "reliably and that clean-bed performance remains stable over the long "
        "term, drawn from pilot data, comparable reference-plant experience, or "
        "commissioning verification. The %s dual-media bed, with a single "
        "interface, carries less of this long-term management burden."
        % (d1, d2)))

    # ---- 5  Solids holding capacity ----
    c.extend(_H1("5", "Solids holding capacity", False))
    c.append(_NOTE("Filter capacity K is the dry solids retained per m2 of "
                   "filter area per run. The measures below are properties of "
                   "the filter bed and apply in both operating modes."))
    c.append(section_table([
        {"section": "Capacity measure (kg/m2/run)"},
        {"cells": ["Theoretical pore-fill ceiling (anthracite 7.0, sand 1.0 kg/m3)",
                   bold_cell(f2(poreFill["D1"])), bold_cell(f2(poreFill["D2"])),
                   "%s %sx" % (D2, ratio(poreFill["D2"], poreFill["D1"]))]},
        {"cells": ["Kawamura range (1.0 to 1.5x anthracite depth)",
                   "%s to %s" % (f2(layerD(F1, "anthracite")),
                                 f2(layerD(F1, "anthracite") * 1.5)),
                   "%s to %s" % (f2(layerD(F2, "anthracite")),
                                 f2(layerD(F2, "anthracite") * 1.5)), ""]},
        {"cells": ["AWWA M37 and Cleasby-Logsdon typical", "2.0 to 5.0",
                   "2.0 to 5.0", "same range"]},
        {"cells": ["Pragmatic breakthrough cap", f1(kCap), f1(kCap), "equal"]},
    ], W))
    c.append(_chart_image(ctx["charts"]["capacity"]))
    c.append(_CAP("Figure 1. Solids holding capacity by measure. The %s "
                  "configuration carries more capacity on every depth-dependent "
                  "measure." % d2))
    c.append(_BODY(
        "On every depth-dependent measure the %s configuration carries more "
        "capacity per unit area, owing to its deeper anthracite. The "
        "theoretical pore-fill ceiling states the difference plainly: %s "
        "kg/m2/run for %s and %s for %s. Both configurations sit within or just "
        "above the AWWA and Cleasby-Logsdon literature band of 2 to 5 "
        "kg/m2/run, and neither relies on an implausible loading."
        % (d2, f1(poreFill["D1"]), d1, f1(poreFill["D2"]), d2)))
    c.append(_NOTE(
        "The pore-fill ceiling is a theoretical maximum, not an operationally "
        "demonstrated capacity. The achievable fraction of it depends on floc "
        "compressibility, the deposition profile through the bed, media shape "
        "and stratification, and backwash effectiveness, and should be "
        "confirmed by pilot or reference-plant data. It is used here as a "
        "comparative upper bound, not as a design loading."))

    # ---- 6  Hydraulic head budget ----
    c.extend(_H1("6", "Hydraulic head budget, like-for-like", False))
    c.append(_NOTE("Both filters at a common 20 mg/L feed, 95% removal, 24 h "
                   "run. This isolates intrinsic filter-design performance from "
                   "the upstream feed differences. The two modes differ only in "
                   "the precipitate chemistry."))

    def lfl_block(label, a1, a2):
        return [
            {"section": label},
            {"cells": ["Clean-bed headloss (m)", f3(a1["cb"]), f3(a2["cb"]), ""]},
            {"cells": ["Solids-load headloss (m)", f3(a1["load"]), f3(a2["load"]), ""]},
            {"cells": ["Total headloss required (m)", bold_cell(f2(a1["totalDH"])),
                       bold_cell(f2(a2["totalDH"])), ""]},
            {"cells": ["Margin against available head (m)", mgn(a1["margin"]),
                       mgn(a2["margin"]), ""]},
        ]

    c.append(section_table(
        lfl_block("Coagulation chemistry, common 20 mg/L feed",
                  lfl["coag"]["D1"], lfl["coag"]["D2"])
        + lfl_block("Lime softening chemistry, common 20 mg/L feed",
                    lfl["soft"]["D1"], lfl["soft"]["D2"]), W))
    c.append(_BODY(
        "At an identical feed the %s configuration retains more head margin "
        "than %s in both chemistries. The difference arises from %s's larger "
        "total area, which lowers the filtration velocity, and its larger "
        "driving head. The %s configuration is tighter under coagulation "
        "chemistry (%s m) than under lime softening (%s m), because ferric's "
        "deposit structure factor (%s) is lower than the lime-softening "
        "precipitate's (%s), which raises the solids-load headloss. Held at an "
        "equal feed, the %s configuration provides the greater intrinsic "
        "hydraulic capacity."
        % (d2, d1, d2, d1, f2(lfl["coag"]["D1"]["margin"]),
           f2(lfl["soft"]["D1"]["margin"]), f2(C["D1"]["kmult"]),
           f2(S["D1"]["kmult"]), d2)))

    # ---- 7  Redundancy and temperature robustness ----
    c.extend(_H1("7", "Redundancy and temperature robustness", False))
    c.append(_NOTE("The governing intrinsic robustness check. With filters out "
                   "of service or at colder water, filtration velocity and "
                   "clean-bed headloss rise and the head left for solids load "
                   "shrinks. All cases are at the maximum design flow."))
    c.append(section_table([
        {"section": "Hydraulic headroom at %s ML/d and %s degrees C, by "
                    "redundancy condition" % (model["flow"], model["tempMin"])},
        {"cells": ["Filtration velocity, N all in service (m/h)",
                   f2(rget(rd1, "N")["v_mh"]), f2(rget(rd2, "N")["v_mh"]), ""]},
        {"cells": ["Filtration velocity, N-1 one offline (m/h)",
                   f2(rget(rd1, "N-1")["v_mh"]), f2(rget(rd2, "N-1")["v_mh"]), ""]},
        {"cells": ["Filtration velocity, N-2 offline plus backwash (m/h)",
                   f2(rget(rd1, "N-2")["v_mh"]), f2(rget(rd2, "N-2")["v_mh"]), ""]},
        {"cells": ["Head for solids load, N (m)",
                   hcol(rget(rd1, "N")["headForLoad"]),
                   hcol(rget(rd2, "N")["headForLoad"]), ""]},
        {"cells": ["Head for solids load, N-1 (m)",
                   hcol(rget(rd1, "N-1")["headForLoad"]),
                   hcol(rget(rd2, "N-1")["headForLoad"]), ""]},
        {"cells": ["Head for solids load, N-2 (m)",
                   hcol(rget(rd1, "N-2")["headForLoad"]),
                   hcol(rget(rd2, "N-2")["headForLoad"]), ""]},
    ], W))
    c.append(_BODY(
        "At the maximum design flow and the %s degrees C minimum design water "
        "temperature, with all filters in service, both configurations have "
        "adequate hydraulic headroom. With filters out of service the head left "
        "for solids load reduces. The governing redundancy condition is N-1, "
        "one filter out of service, because this is a sustained state the plant "
        "can hold for hours or days while maintenance is carried out. At N-1 "
        "the %s configuration retains %s m of head for the solids load and the "
        "%s configuration %s m; both are comfortable, with %s carrying the "
        "lower of the two reserves."
        % (model["tempMin"], d1, f2(rget(rd1, "N-1")["headForLoad"]), d2,
           f2(rget(rd2, "N-1")["headForLoad"]), d1)))
    c.append(_BODY(
        "The N-2 condition, one filter out of service with a second briefly in "
        "backwash, is a short and schedulable transient rather than a sustained "
        "state: a backwash lasts only tens of minutes and can be staggered to "
        "avoid coinciding with a filter being offline. It is reported here as a "
        "transient check, not as the design-governing case. At N-2 the %s "
        "configuration retains %s m and the %s configuration %s m; both remain "
        "positive, so the plant rides through the transient, with %s again the "
        "tighter of the two."
        % (d1, f2(rget(rd1, "N-2")["headForLoad"]), d2,
           f2(rget(rd2, "N-2")["headForLoad"]), d1)))
    c.append(_BODY(
        "Filtration velocity rises as filters are taken out of service. At the "
        "governing N-1 condition the sustained velocities are approximately %s "
        "m/h for %s and %s m/h for %s, within normal practice for rapid gravity "
        "filtration. The brief N-2 transient reaches approximately %s m/h, in "
        "the upper practical range; sustained operation at that rate would "
        "reduce the margin against floc breakthrough and terminal headloss, "
        "particularly under lime-softening duty, but as a short transient it is "
        "manageable. Both configurations operate well below these velocities "
        "with all filters in service."
        % (f1(rget(rd1, "N-1")["v_mh"]), d1, f1(rget(rd2, "N-1")["v_mh"]), d2,
           f1(rget(rd1, "N-2")["v_mh"]))))
    c.append(section_table([
        {"section": "Clean-bed headloss sensitivity to water temperature, N at "
                    "maximum design flow"},
        {"cells": ["Clean-bed headloss at %s degrees C, minimum design (m)"
                   % cw1[0]["temp_C"], f3(cw1[0]["N"]["cb"]),
                   f3(cw2[0]["N"]["cb"]), ""]},
        {"cells": ["Clean-bed headloss at %s degrees C, indicative mean (m)"
                   % cw1[1]["temp_C"], f3(cw1[1]["N"]["cb"]),
                   f3(cw2[1]["N"]["cb"]), ""]},
        {"cells": ["Clean-bed headloss at %s degrees C, indicative summer (m)"
                   % cw1[2]["temp_C"], f3(cw1[2]["N"]["cb"]),
                   f3(cw2[2]["N"]["cb"]), ""]},
        {"cells": ["Head for solids load at %s degrees C, N (m)"
                   % cw1[0]["temp_C"], hcol(cw1[0]["N"]["headForLoad"]),
                   hcol(cw2[0]["N"]["headForLoad"]), ""]},
        {"cells": ["Head for solids load at %s degrees C, N-1 (m)"
                   % cw1[0]["temp_C"], hcol(cw1[0]["N1"]["headForLoad"]),
                   hcol(cw2[0]["N1"]["headForLoad"]), ""]},
    ], W))
    c.append(_BODY(
        "Clean-bed headloss rises with water viscosity, so colder water "
        "increases it. The assessment is anchored on the %s degrees C minimum "
        "design water temperature%s; the source water is not expected to fall "
        "below this, and at warmer temperatures the head budget improves. The "
        "governing case is therefore the %s degrees C minimum at the N-1 "
        "condition. There the %s configuration retains %s m of head for the "
        "solids load and the %s configuration %s m; both are positive and "
        "workable, with %s the lower of the two. As the water warms to the %s "
        "degrees C indicative summer value the %s N-1 figure rises to %s m. The "
        "%s configuration therefore carries the lower temperature-and-redundancy "
        "reserve, but it remains hydraulically feasible across the design "
        "temperature range at the governing N-1 condition; the driving head and "
        "the minimum design water temperature should still be confirmed."
        % (model["tempMin"],
           (", a conservative %s basis" % ctx["temp_basis"]) if ctx.get("temp_basis") else "",
           model["tempMin"], d1,
           f2(cw1[0]["N1"]["headForLoad"]), d2, f2(cw2[0]["N1"]["headForLoad"]),
           d1, cw1[2]["temp_C"], d1, f2(cw1[2]["N1"]["headForLoad"]), d1)))


# --------------------------------------------------------------------------
# PART B — WHOLE-OF-PLANT SYSTEM PERFORMANCE (sections 8-11)
# --------------------------------------------------------------------------
def _build_part_b(c, ctx):
    d1, d2 = ctx["d1"], ctx["d2"]
    D1, D2 = ctx["D1"], ctx["D2"]
    F1, F2 = ctx["F1"], ctx["F2"]
    C, S = ctx["C"], ctx["S"]
    W = ctx["W"]
    layerD, bed_depth = ctx["layerD"], ctx["bed_depth"]
    model = ctx["model"]
    route_d1, route_d2 = ctx["route_d1"], ctx["route_d2"]
    mg_removal = ctx["mg_removal"]
    algal_str = ctx["algal_str"]

    c.extend(_part_header(
        "B", "Whole-of-plant system performance",
        "The sections in Part B assess how each configuration performs in "
        "service. These outcomes depend on upstream clarification, operating "
        "strategy and washwater philosophy, not on filter design alone."))

    # ---- 8  Feed conditions ----
    c.extend(_H1("8", "Feed conditions and chemistry", False))
    c.append(_NOTE("Feed TSS delivered to the filter and the precipitate "
                   "chemistry, for each operating mode, accepted as documented "
                   "by the designers."))
    c.append(section_table([
        {"section": "Coagulation (maximum turbidity)"},
        {"cells": ["Feed TSS to filter (mg/L)", bold_cell(f1(C["D1"]["tss"])),
                   bold_cell(f1(C["D2"]["tss"])),
                   "%s %sx" % (D1, ratio(C["D1"]["tss"], C["D2"]["tss"]))]},
        {"cells": ["Coagulant", "Ferric", "Alum", ""]},
        {"cells": ["Deposit structure factor", f2(C["D1"]["kmult"]),
                   f2(C["D2"]["kmult"]), ""]},
        {"cells": ["TSS removal efficiency (%)", f0(C["D1"]["removal"]),
                   f0(C["D2"]["removal"]), ""]},
        {"cells": ["Designer run length (h)", bold_cell(f0(C["D1"]["runHours"])),
                   bold_cell(f0(C["D2"]["runHours"])), ""]},
        {"section": "100% lime softening at pH 10"},
        {"cells": ["Feed TSS to filter (mg/L)", bold_cell(f1(S["D1"]["tss"])),
                   bold_cell(f1(S["D2"]["tss"])),
                   "%s %sx" % (D2, ratio(S["D2"]["tss"], S["D1"]["tss"]))]},
        {"cells": ["Precipitate", "CaCO3-dominant", "CaCO3 with Mg(OH)2", ""]},
        {"cells": ["Deposit structure factor", f2(S["D1"]["kmult"]),
                   f2(S["D2"]["kmult"]), "equal"]},
        {"cells": ["TSS removal efficiency (%)", f0(S["D1"]["removal"]),
                   f0(S["D2"]["removal"]), ""]},
        {"cells": ["Designer run length (h)", bold_cell(f0(S["D1"]["runHours"])),
                   bold_cell(f0(S["D2"]["runHours"])), ""]},
    ], W))
    c.append(_BODY(
        "In coagulation the two filters see similar feed TSS but different "
        "coagulants. The deposit structure factor used in this assessment "
        "scales how favourable a precipitate's deposit structure is for "
        "headloss: it is distinct from the solids holding capacity K, and a "
        "higher factor means less headloss for the same captured mass. On that "
        "scale the %s coagulation precipitate (%s) is the more headloss-prone "
        "and the %s precipitate (%s) the less, with the lime-softening "
        "precipitate (%s) the most favourable of the three. In lime softening "
        "the feed TSS reported for the two designs is %s mg/L for %s and %s "
        "mg/L for %s. Where these differ, the difference is attributed to the "
        "different softening routes the two designers have adopted: %s adopts "
        "%s; %s adopts %s. The two feed-TSS figures are designer-supplied and "
        "accepted as documented; the difference reflects the chosen softening "
        "routes rather than an unexplained clarifier-performance gap. What "
        "should be confirmed is that this difference in softening route and "
        "duty is intended and understood, since it carries through to the "
        "whole-of-plant comparison in Part B."
        % (d2, f2(C["D2"]["kmult"]), d1, f2(C["D1"]["kmult"]),
           f2(S["D1"]["kmult"]),
           f1(S["D1"]["tss"]), d1, f1(S["D2"]["tss"]), d2,
           d1, route_d1, d2, route_d2)))
    if mg_removal:
        c.append(_BODY(
            "Where a softening route removes magnesium, its lime-softening "
            "precipitate is not purely calcium-carbonate-dominant: it carries a "
            "magnesium hydroxide fraction, the least favourable precipitate for "
            "headloss. The deposit structure factor used for the lime-softening "
            "head budget reflects the precipitate composition implied by the "
            "documented route. Where a magnesium hydroxide fraction is present "
            "its actual size is uncertain and could be materially higher than "
            "assumed; its effect on the head budget is examined as a "
            "sensitivity in Section 11."))
    c.append(_BODY(
        "One further assumption warrants challenge. The %s filter is credited "
        "with %s%% TSS removal in lime softening, against %s%% for %s. For a %s "
        "m dual-media bed with %s m of anthracite, run at a filtration velocity "
        "of %s m/h, %s%% is a conservative figure: a bed of that depth would "
        "typically be expected to achieve 95%% or better on a well-formed floc. "
        "The %s%% value is most likely a conservative design assumption rather "
        "than a capability limit of the bed. Section 14 quantifies the "
        "implications of correcting it."
        % (d2, f0(S["D2"]["removal"]), f0(S["D1"]["removal"]), d1,
           f2(bed_depth(F2)), f2(layerD(F2, "anthracite")), f1(S["D2"]["v_mh"]),
           f0(S["D2"]["removal"]), f0(S["D2"]["removal"]))))
    c.append(_BODY(
        "A general qualification applies to all of the feed assumptions above. "
        "The performance of both configurations, and particularly the deeper "
        "%s bed, remains strongly dependent on upstream floc structure and "
        "settleability. A deep bed delivers its advantage by distributing the "
        "captured solids through the bed depth: this delays surface blinding "
        "and extends the run, but only where the floc is well-formed and "
        "robust, so that it is intercepted progressively within the upper and "
        "middle media. Where the floc is poorly formed or shear-sensitive, the "
        "mechanism works against the bed: the solids penetrate too deeply, the "
        "lower media foul, the bed becomes harder to clean by backwash, and "
        "runs shorten rather than lengthen. The deeper %s bed therefore carries "
        "a real hydraulic advantage, but one that is conditional on floc "
        "quality: the additional depth is a benefit with good floc and a "
        "liability with poor floc. This is a further reason the upstream "
        "coagulation and softening basis should be confirmed alongside the feed "
        "TSS figures." % (d2, d2)))

    # ---- 9  As-built operating point ----
    c.extend(_H1("9", "As-built operating point", False))
    c.append(_NOTE("Each configuration at its own documented feed TSS, run "
                   "length and chemistry, for both operating modes."))

    def ab_block(label, a1, a2):
        return [
            {"section": label},
            {"cells": ["Feed TSS (mg/L)", f1(a1["tss"]), f1(a2["tss"]), ""]},
            {"cells": ["Run length (h)", f0(a1["runHours"]), f0(a2["runHours"]), ""]},
            {"cells": ["K at design run (kg/m2/run)", bold_cell(f2(a1["K"])),
                       bold_cell(f2(a2["K"])), ""]},
            {"cells": ["K utilisation vs theoretical pore-fill ceiling (%)",
                       f0((a1["K"] / a1["poreFill"]) * 100),
                       f0((a2["K"] / a2["poreFill"]) * 100), ""]},
            {"cells": ["Total headloss required (m)", f2(a1["totalDH"]),
                       f2(a2["totalDH"]), ""]},
            {"cells": ["Margin against available head (m)", mgn(a1["margin"]),
                       mgn(a2["margin"]), ""]},
        ]

    c.append(section_table(
        ab_block("Coagulation (maximum turbidity)", C["D1"], C["D2"])
        + ab_block("100% lime softening", S["D1"], S["D2"]), W))
    c.append(_chart_image(ctx["charts"]["headBudget"]))
    c.append(_CAP("Figure 2. As-built head budget, both modes. Stacked "
                  "components, appurtenances at the base, against the available "
                  "driving head line."))
    c.append(_BODY(
        "The %s configuration is feasible with comfortable margin in both "
        "modes, %s m in coagulation and %s m in lime softening. The %s "
        "configuration is feasible but operates with limited reserve in both, "
        "%s m in coagulation and %s m in lime softening. %s's coagulation point "
        "is the tightest of the four cases: its feed TSS is close to its "
        "lime-softening value, but ferric's lower deposit structure factor "
        "raises the solids-load headloss. A positive margin confirms "
        "feasibility; it does not by itself indicate hydraulic reserve, which "
        "is assessed in Section 11."
        % (d2, f2(C["D2"]["margin"]), f2(S["D2"]["margin"]), d1,
           f2(C["D1"]["margin"]), f2(S["D1"]["margin"]), d1)))

    # ---- 10  Backwash and washwater ----
    c.extend(_H1("10", "Backwash and washwater balance", False))
    c.append(_NOTE("Dump water, filter backwash water and filter-to-waste, at "
                   "the maximum design flow. D1 sends filter-to-waste to waste; "
                   "D2 recycles it to the DAF inlet, so D2's net water loss is "
                   "lower than its total water handled."))

    def bw_block(label, a1, a2):
        return [
            {"section": label},
            {"cells": ["Run length (h)", f0(a1["runHours"]), f0(a2["runHours"]), ""]},
            {"cells": ["Dump + backwash water per cycle (m3)",
                       f0(a1["bw"]["perCycle"]), f0(a2["bw"]["perCycle"]), ""]},
            {"cells": ["Filter-to-waste per cycle (m3)",
                       f0(a1["bw"]["ftwPerCycle"]), f0(a2["bw"]["ftwPerCycle"]), ""]},
            {"cells": ["Dump + backwash water (% of plant flow)",
                       wcol(a1["bw"]["pctFlow"], 8, 5),
                       wcol(a2["bw"]["pctFlow"], 8, 5), ""]},
            {"cells": ["Filter-to-waste (% of plant flow)",
                       wcol(a1["bw"]["ftwPctFlow"], 8, 5),
                       wcol(a2["bw"]["ftwPctFlow"], 8, 5), ""]},
            {"cells": ["Total water handled (% of plant flow)",
                       wcol(a1["bw"]["totalPctFlow"], 12, 6),
                       wcol(a2["bw"]["totalPctFlow"], 12, 6), ""]},
        ]

    c.append(section_table(
        bw_block("Coagulation (maximum turbidity)", C["D1"], C["D2"])
        + bw_block("100% lime softening", S["D1"], S["D2"]), W))
    c.append(_BODY(
        "Dump and backwash water is the water sent to waste each cycle. On that "
        "measure the %s configuration uses %s%% of plant flow in both modes, "
        "against the %s configuration's %s%% in coagulation and %s%% in lime "
        "softening." % (d1, f1(C["D1"]["bw"]["pctFlow"]), d2,
                        f1(C["D2"]["bw"]["pctFlow"]), f1(S["D2"]["bw"]["pctFlow"]))))
    c.append(_BODYB(
        "%s's filter-to-waste recycle to the DAF inlet is not a free recovery. "
        "The filter-to-waste volume is %s m3 per cycle, against %s m3 for %s, "
        "and counting all washwater the %s configuration handles up to %s%% of "
        "plant flow in lime softening. Returning a stream of that size to the "
        "head of the plant adds to recycle hydraulics, DAF and sludge loading "
        "and pumping energy, can affect control-loop stability, and returns "
        "fine precipitate to the process. The net washwater performance favours "
        "the %s configuration, but %s's washwater handling is a material design "
        "consideration in its own right and is carried into the decision "
        "framework and lifecycle implications in Part C."
        % (d2, f0(S["D2"]["bw"]["ftwPerCycle"]), f0(S["D1"]["bw"]["ftwPerCycle"]),
           d1, d2, f1(S["D2"]["bw"]["totalPctFlow"]), d1, d2)))
    c.append(_BODY(
        "Beyond the average loading, a large intermittent recycle stream can "
        "also introduce cyclic hydraulic and solids-loading disturbances into "
        "the DAF process, particularly during frequent filter washing under "
        "softening duty. Each return event briefly alters the DAF hydraulic "
        "loading rate, flocculation residence time, polymer demand and sludge "
        "blanket behaviour, which can produce cyclic rather than steady process "
        "behaviour. The operational significance of this depends on recycle "
        "equalisation, the plant control philosophy and the hydraulic "
        "resilience of the DAF, and it is identified here as a matter to be "
        "confirmed rather than assessed."))

    # ---- 11  Sensitivity to feed deterioration ----
    c.extend(_H1("11", "Sensitivity to feed deterioration", False))
    c.append(_NOTE("Feed solids increased by 100%, doubling the TSS delivered "
                   "to each filter, in each operating mode. The achievable K is "
                   "the lower of the head-budget limit and the breakthrough "
                   "cap; run length shortens only if the doubled-feed load "
                   "exceeds that achievable K."))

    def sen_block(label, a1, a2):
        return [
            {"section": label},
            {"cells": ["Doubled feed TSS (mg/L)", f1(a1["sens"]["tss2"]),
                       f1(a2["sens"]["tss2"]), ""]},
            {"cells": ["K required at design run (kg/m2/run)",
                       bold_cell(f2(a1["sens"]["kReq"])),
                       bold_cell(f2(a2["sens"]["kReq"])), ""]},
            {"cells": ["Achievable K (kg/m2/run)", f2(a1["sens"]["kAch"]),
                       f2(a2["sens"]["kAch"]), ""]},
            {"cells": ["Binding constraint", flag_cell(a1["sens"]["bind"]),
                       flag_cell(a2["sens"]["bind"]), ""]},
            {"cells": ["Run length retained (h)", bold_cell(f1(a1["sens"]["runRet"])),
                       bold_cell(f1(a2["sens"]["runRet"])), ""]},
            {"cells": ["Head margin at doubled feed (m)", mgn(a1["sens"]["margin"]),
                       mgn(a2["sens"]["margin"]), ""]},
        ]

    c.append(section_table(
        sen_block("Coagulation, feed doubled", C["D1"], C["D2"])
        + sen_block("Lime softening, feed doubled", S["D1"], S["D2"]), W))
    c.append(_chart_image(ctx["charts"]["sensitivity"]))
    c.append(_CAP("Figure 3. Run length retained, as-built feed against feed "
                  "doubled, for all four configuration and mode combinations."))
    c.append(_BODY(
        "The %s configuration demonstrates greater resilience to feed "
        "deterioration in both modes. Under a doubled feed it remains feasible "
        "with positive head margin; in coagulation it is so lightly loaded that "
        "a doubled feed does not shorten its run. The %s configuration is "
        "head-constrained in both modes: a doubled feed pushes the required K "
        "above what the head budget allows, so its run shortens materially, to "
        "roughly half its design length, and little or no head margin remains. "
        "Combined with its lower temperature-and-redundancy reserve from "
        "Section 7, the %s configuration has the more limited capacity of the "
        "two to absorb transient feed deterioration without loss of production "
        "or hydraulic margin." % (d2, d1, d1)))
    if mg_removal:
        c.append(_H2("Sensitivity to magnesium hydroxide content in the "
                     "softening floc"))
        c.append(_NOTE("Where a design's softening route removes magnesium, its "
                       "lime-softening precipitate carries a magnesium "
                       "hydroxide fraction. Magnesium hydroxide is the least "
                       "favourable precipitate for headloss; the fraction is "
                       "uncertain, so its effect is bounded here by a sweep. "
                       "Run length held at the design value."))
        MG = model["mgFlocSensitivityD2"]

        def mg_row(p):
            m = p["margin"]
            color = (COL["ochre"] if m < 0.5 else COL["sage"]) if m >= 0 else COL["rust"]
            return [
                "%s%% magnesium hydroxide" % f0(p["mgFrac"] * 100),
                f2(p["kmult"]), f2(p["load"]), f2(p["totalDH"]),
                {"text": "%s%s" % ("+" if m >= 0 else "", f2(m)), "bold": True,
                 "color": color},
            ]

        c.append(grid_table(
            ["Softening floc composition", "Deposit\nstructure factor",
             "Solids-load\nheadloss (m)", "Total headloss\nrequired (m)",
             "Head margin\n(m)"],
            [mg_row(p) for p in MG["points"]],
            [150, 86, 90, 96, 86]))
        c.append(_BODY(
            "As the magnesium hydroxide fraction rises, the deposit structure "
            "factor falls, from %s for a calcium-carbonate-dominant floc to %s "
            "at the high end of the sweep, and the solids-load headloss rises "
            "accordingly. The lime-softening head margin reduces from %s m to "
            "%s m across the range, a swing of about %s m. The margin remains "
            "positive and comfortable at every point tested, so the "
            "magnesium-removal duty erodes the softening reserve but does not "
            "threaten hydraulic feasibility. The report's headline softening "
            "figures are computed on the designer's documented precipitate "
            "assumption; the true operating point lies on this sweep, and its "
            "position should be fixed once the designer confirms the magnesium "
            "hydroxide fraction in the softening precipitate."
            % (f2(MG["points"][0]["kmult"]), f2(MG["points"][-1]["kmult"]),
               f2(MG["points"][0]["margin"]), f2(MG["points"][-1]["margin"]),
               f2(MG["marginSwing"]))))
    c.append(_H2("Algal loading and filter-clogging risk"))
    c.append(_BODY(
        "The plant design basis allows for raw water carrying up to %s algae "
        "cells/mL, and there is evidence that filter-clogging algae are present "
        "in the source. At an assumed 95%% removal across upstream treatment, a "
        "small fraction of that count would reach the filters. This is a "
        "recognised feed-deterioration mechanism for the plant and is set out "
        "here for that reason." % algal_str))
    c.append(_BODY(
        "Algal clogging is not captured by the solids-loading analysis in the "
        "body of this report, and this is an honest limitation of the "
        "comparison. The head-budget and solids holding capacity work is "
        "mass-based: it scales with the dry mass of solids captured. Algae load "
        "a filter very differently. They contribute little to solids mass but "
        "disproportionately to headloss, because the cells are low-density, "
        "often elongated, filamentous or colonial, and they deform and mat at "
        "the bed surface rather than distributing as a mineral floc does. The "
        "rate and severity of algal headloss are governed by cell morphology "
        "and species, not by the mass-based measures used here, so a cell count "
        "cannot be converted into a run-length or headloss figure without the "
        "species composition and supporting pilot or seasonal data."))
    c.append(_BODY(
        "The directional consequence for the comparison nonetheless follows "
        "from the hydraulics already established. A seasonal algal load is a "
        "surface-blinding transient, and algae tend to blind at or near the bed "
        "surface largely regardless of total bed depth. The %s bed, with its "
        "deeper and coarser anthracite layer, is expected to have greater "
        "tolerance to algal surface loading before terminal headloss develops, "
        "although the magnitude of that advantage depends strongly on algal "
        "species, morphology and the removal achieved by upstream treatment. "
        "The leaner %s four-layer bed, with finer media and the lower hydraulic "
        "reserve identified in Section 7, is the more exposed to a rapid algal "
        "headloss excursion, in the same way it is the more exposed to cold "
        "water and to feed deterioration. A first-order, risk-screening "
        "estimate of the effect is given immediately below; the "
        "characterisation needed to confirm it is set out "
        "in Section 15." % (d2, d1)))

    # Quantitative risk-screening from the algae-clogging model (model["algae"]).
    alg = model.get("algae")
    if alg:
        a1, a2 = alg["D1"], alg["D2"]

        def _runs(block):
            m = block.get("modes", {}).get("N", {})
            if not m or m.get("infeasible"):
                return {}
            sc = m.get("scenarios", {})
            return {s: sc[s]["run_h"] for s in ("W", "A", "B", "C", "D", "E") if s in sc}

        r1, r2 = _runs(a1), _runs(a2)
        c.append(_H2("Algae-clogging screening model"))
        c.append(_BODY(
            "The estimate below is from a morphology-based clogging model. Mass "
            "is conserved: the residual algal load is split into mineral-bound, "
            "free-cell and extracellular-polymer streams, each with its own "
            "filtration resistance, compressibility and surface-blinding "
            "behaviour, and run length is the time to reach the available "
            "clogging head. The figures are indicative, about plus or minus 30 "
            "percent, and are intended to rank conditions rather than to set a "
            "backwash schedule."))
        names = {"W": "Well-coagulated", "A": "Mineral floc", "B": "Mixed algae",
                 "C": "Colonial", "D": "Filamentous", "E": "EPS-rich bloom"}
        rows = [
            {"section": "Run length to terminal head at N, by morphology "
                        "(hours, risk-screening)"},
            {"cells": [{"text": "Morphology", "bold": True},
                       {"text": "%s (h)" % d1, "bold": True},
                       {"text": "%s (h)" % d2, "bold": True}]},
        ]
        for s in ("W", "A", "B", "C", "D", "E"):
            rows.append({"cells": [
                names[s],
                ("%.0f" % r1[s]) if s in r1 else "n/a",
                ("%.0f" % r2[s]) if s in r2 else "n/a"]})
        b1 = (a1.get("modes", {}).get("N", {}) or {}).get("baseline_run_h")
        b2 = (a2.get("modes", {}).get("N", {}) or {}).get("baseline_run_h")
        rows.append({"cells": [
            {"text": "No-algae baseline", "bold": True},
            ("%.0f" % b1) if b1 else "n/a",
            ("%.0f" % b2) if b2 else "n/a"]})
        c.append(section_table(rows, [221, 142, 142]))

        if ctx["charts"].get("algae"):
            c.append(_chart_image(ctx["charts"]["algae"]))
            c.append(_CAP("Figure 4. Algae run length by morphology scenario at N, "
                          "against a 24 h reference. Risk-screening estimates."))

        if r1:
            c.append(_BODY(
                "The result is governed by morphology rather than by cell count. "
                "For %s the run length spans roughly %.0f hours for a "
                "well-coagulated residual down to about %.0f hours for an "
                "EPS-rich bloom, a several-fold range that is far larger than "
                "the effect of temperature or head basis. An EPS-rich residual "
                "is the condition a clarifier supernatant recycle tends to "
                "promote, so where such a recycle is present the lower end of "
                "the range is the more representative." % (
                    d1, r1.get("W", 0.0), r1.get("E", 0.0))))
        c.append(_NOTE(
            "Risk-screening only, about plus or minus 30 percent. The "
            "resistances are granular-bed effective values and must not be read "
            "as membrane or sludge-cake resistances. The estimate depends far "
            "more on algal morphology than on the cell count."))


# --------------------------------------------------------------------------
# PART C — DECISION SUPPORT (sections 12-16)
# --------------------------------------------------------------------------
def _build_part_c(c, ctx):
    d1, d2 = ctx["d1"], ctx["d2"]
    S = ctx["S"]
    O = ctx["O"]
    RM = ctx["RM"]
    model = ctx["model"]
    route_d1, route_d2 = ctx["route_d1"], ctx["route_d2"]
    mg_removal = ctx["mg_removal"]
    algal_str = ctx["algal_str"]

    c.extend(_part_header(
        "C", "Decision support",
        "Part C draws the assessment together for the selection decision: the "
        "dependencies the findings rest on, a risk-weighted decision framework, "
        "the operational and lifecycle implications, and the risks and "
        "verification actions."))

    # ---- 12  Critical dependencies ----
    c.extend(_H1("12", "Critical dependencies", False))
    c.append(_BODY(
        "The findings in this report are conditional on the assumptions below. "
        "Each row identifies a finding, the dependency it rests on, and how the "
        "finding would change if the dependency is not met. These are the "
        "points at which the comparison could move, and they should be closed "
        "out through the verification actions in Section 16."))
    c.append(grid_table(
        ["Finding", "Critical dependency",
         "Effect if the dependency is not met"],
        [
            ["%s lower whole-of-plant washwater demand" % d1,
             "The %s softening route delivers the documented lower solids "
             "carryover, as a designer-supplied input accepted as documented."
             % d1,
             "If the %s softening route carries more solids forward than "
             "documented, its run shortens and its washwater-demand advantage "
             "narrows." % d1],
            ["%s hydraulic resilience advantage" % d2,
             "The documented driving head is confirmed available at the filter.",
             "If the available head is lower, D2's margin reduces, though it "
             "remains above D1's."],
            ["%s hydraulic feasibility" % d1,
             "Driving head as documented, and water temperature not below the "
             "design minimum.",
             "At materially reduced head or below the minimum design "
             "temperature, D1's N-1 margin erodes further; N-1 is the governing "
             "sustained redundancy condition."],
            ["%s filter-to-waste recycle is workable" % d2,
             "DAF, recycle and sludge systems can accept the filter-to-waste "
             "recycle loading.",
             "If recycle loading is not acceptable, D2's washwater philosophy "
             "must be revised."],
            ["Designer run lengths are achievable",
             "Coagulation and softening perform as assumed and the media stay "
             "clean between washes.",
             "If runs are shorter in practice, backwash frequency and water use "
             "rise for both."],
            ["Coagulation head budget as assessed",
             "Coagulant type as assumed: ferric for D1, alum for D2.",
             "A different coagulant changes the deposit structure factor and "
             "the coagulation head budget."],
        ],
        [120, 185, 210]))

    # ---- 13  Decision framework ----
    c.extend(_H1("13", "Risk-weighted decision framework", False))
    c.append(_BODY(
        "The two configurations are not separated by a single decisive "
        "measure. The appropriate choice depends on how the client weights "
        "hydraulic robustness, washwater performance, operational complexity "
        "and dependence on upstream performance. The matrix below sets out the "
        "comparison criterion by criterion; the table that follows indicates "
        "the direction of preference under different client priorities. The "
        "assessment does not recommend a single configuration."))
    c.append(_H2("Comparative assessment by criterion"))
    c.append(grid_table(
        ["Criterion", "Weighting", d1, d2],
        [
            ["Hydraulic resilience", "High", "Moderate", bold_cell("Strong")],
            ["Temperature resilience", "High", "Moderate", bold_cell("Strong")],
            ["Resilience to feed deterioration", "High", "Moderate to low",
             bold_cell("Strong")],
            ["Risk of hydraulic constraint", "High", "Moderate", bold_cell("Low")],
            ["Operational flexibility", "High", "Moderate", bold_cell("Strong")],
            ["Dependence on upstream clarification", "High", "High dependency",
             "Moderate dependency"],
            ["Whole-of-plant washwater demand", "High", bold_cell("Strong"),
             "Moderate"],
            ["Recycle and washwater loading", "Medium", "Lower", "Higher"],
            ["Operational simplicity", "Medium", bold_cell("Strong"), "Moderate"],
        ],
        [165, 70, 140, 140]))
    c.append(_NOTE(
        "Weightings and ratings are the reviewing engineer's judgement for the "
        "purpose of structuring the decision, and are to be confirmed by the "
        "report author and the client prior to issue. The criteria are not all "
        "independent; temperature resilience and risk of hydraulic constraint "
        "both reflect the head-budget findings of Sections 7 and 11."))
    c.append(_H2("Indicated direction by client priority"))
    c.append(grid_table(
        ["If the client's governing priority is", "Indicated direction"],
        [
            ["Lowest current whole-of-plant washwater demand", bold_cell(d1)],
            ["Highest hydraulic resilience", bold_cell(d2)],
            ["Highest robustness to feed variability", bold_cell(d2)],
            ["Lowest operational dependency on upstream clarification",
             bold_cell(d2)],
            ["Lowest recycle and washwater handling complexity", bold_cell(d1)],
            ["Lowest long-term operational risk",
             "%s, on the present evidence" % d2],
        ],
        [320, 195]))
    c.append(_BODY(
        "The framework shows the decision turning on a single question: whether "
        "the client places greater weight on the demonstrated lower "
        "whole-of-plant washwater demand of the %s configuration, or on the "
        "hydraulic robustness and lower upstream dependency of the %s "
        "configuration. That weighting is a client decision. The verification "
        "actions in Section 16 should be completed first, because several of "
        "them could move the washwater-demand comparison that the %s position "
        "depends on." % (d1, d2, d1)))
    c.append(_H2("Basis of the comparison"))
    c.append(_BODY(
        "Capital and lifecycle cost are outside the scope of this assessment "
        "(Section 3). One point should nonetheless be made transparent for the "
        "decision. The greater hydraulic resilience of the %s configuration is "
        "associated with materially greater filtration area, media depth, "
        "driving head and washwater handling requirement. This assessment "
        "compares performance and operability, not commercial value. The "
        "resilience advantage is therefore not without cost, and a "
        "whole-of-life assessment is needed to weigh the resilience and "
        "operability differences against the capital and operating commitment "
        "they carry; that assessment is recommended before selection." % d2))
    c.append(_H2("Selection philosophy"))
    c.append(_BODY(
        "The comparison ultimately reflects two coherent but different design "
        "philosophies, and the selection is best understood in those terms "
        "rather than as a contest of measures. The %s configuration "
        "prioritises lower washwater demand and recycle burden, and performs "
        "well under stable, well-clarified feed conditions. The %s "
        "configuration prioritises hydraulic resilience and operational "
        "robustness, and is better suited to deteriorated, cold or variable "
        "feed conditions, accepting a larger washwater and recycle burden in "
        "return. The right choice depends on how the client expects the plant "
        "to be operated over its life and on the confidence that can be placed "
        "in sustained upstream clarification performance." % (d1, d2)))
    c.append(_BODY(
        "Expressed as an operating philosophy, the two configurations suit "
        "different but equally legitimate utility approaches. The %s "
        "configuration is a leaner hydraulic design with a lower recycle "
        "burden; it places more reliance on stable upstream clarification and "
        "on consistent operating discipline to keep within its hydraulic "
        "reserve. The %s configuration is a more conservative hydraulic design "
        "with greater process buffering; it tolerates feed deterioration and "
        "operational variability more readily, in exchange for a larger "
        "washwater and recycle system to manage. Neither approach is more "
        "capable than the other, and choosing the leaner design does not imply "
        "a less able operator. The selection is properly a match between the "
        "configuration and the client's intended operating philosophy and risk "
        "appetite: how much process buffering the utility wants to build in, "
        "and how much it prefers to manage through operations. That judgement "
        "is for the client, informed by the verification actions in "
        "Section 16." % (d1, d2)))

    # ---- 14  Client and lifecycle implications ----
    c.extend(_H1("14", "Client and lifecycle implications", False))
    c.append(_H2("Operational implications"))
    c.append(_BODY(
        "The %s configuration may deliver lower day-to-day washwater demand "
        "under stable clarified-water conditions. Its reduced hydraulic "
        "reserve, however, increases operational sensitivity to transient "
        "deterioration events, including algae breakthrough, clarifier upset, "
        "media fouling and elevated cold-water viscosity. With limited margin, "
        "the operating response to such events is constrained and run lengths "
        "shorten quickly. The %s configuration carries more hydraulic margin "
        "and so absorbs transient events with less operational intervention."
        % (d1, d2)))
    c.append(_BODY(
        "The %s hydraulic advantage is, however, accompanied by a materially "
        "larger operational burden. Handling close to %s%% of plant flow as "
        "dump, backwash and filter-to-waste in lime softening is a significant "
        "volume to manage. It increases operator workload and backwash "
        "frequency, places a continuous demand on recycle control, and adds "
        "transient load to the DAF and the sludge-handling system each time a "
        "filter is washed. It also makes whole-of-plant hydraulic balancing "
        "more demanding, since a recycle stream of that size interacts with the "
        "inlet works. Modern utility practice increasingly treats operational "
        "risk as comparable in weight to hydraulic capacity, and on that basis "
        "the %s configuration's washwater and recycle regime is its principal "
        "operational consideration, just as limited hydraulic reserve is the %s "
        "configuration's. The optimisation discussion later in this section "
        "sets out how the %s burden can be reduced."
        % (d2, f0(S["D2"]["bw"]["totalPctFlow"]), d2, d1, d2)))
    c.append(_H2("Lifecycle implications"))
    c.append(_BODY(
        "The deeper %s media bed and lower filtration velocity are generally "
        "favourable for media life and for underdrain fouling risk. The larger "
        "%s washwater and filter-to-waste volumes increase recycle pumping "
        "energy, DAF and sludge loading, and the return of fine precipitate to "
        "the process, which can affect chemical demand and process stability "
        "over the plant life. The %s four-layer media arrangement requires "
        "confirmation that the layers restratify reliably after backwash; if "
        "they do not, long-term filtration performance and maintenance effort "
        "are affected. Neither configuration has been assessed for capital or "
        "lifecycle cost in this review, and a whole-of-life cost comparison is "
        "recommended before selection." % (d2, d2, d1)))
    c.append(_BODY(
        "Lime-softening duty introduces a further set of long-term media risks "
        "that apply to both configurations and warrant attention in detailed "
        "design. Calcium carbonate is a scale-forming precipitate: where "
        "recarbonation upstream of the filters is incomplete, it can continue "
        "to precipitate within the bed, progressively scaling the lower media "
        "and the underdrain, gradually raising clean-bed headloss, and in the "
        "longer term cementing or coating media grains and reducing their "
        "effective porosity. Repeated backwashing also causes slow anthracite "
        "attrition and a gradual loss of media depth that is itself capacity. "
        "These mechanisms are qualitative considerations here rather than "
        "assessed quantities, but they bear most heavily on the %s four-layer "
        "bed, where the sand-to-garnet interface stability discussed in "
        "Section 4 is the point most exposed to them. They are manageable "
        "through effective recarbonation control, sound air-scour and washing, "
        "and periodic media inspection and topping-up, and should be addressed "
        "in the operations and maintenance strategy." % d1))
    c.append(_BODY(
        "The long-term effectiveness of both configurations depends heavily on "
        "underdrain hydraulic performance, which this assessment has not been "
        "able to evaluate. In lime-softening duty in particular, carbonate "
        "scaling or solids accumulation within nozzle systems or "
        "air-distribution laterals can progressively impair the uniformity of "
        "air and washwater delivery, leading to localised dead zones, uneven "
        "media expansion, reduced cleaning of the lower bed and a gradual "
        "deterioration of restratification performance. The effect compounds "
        "the interface and scaling mechanisms above, and it bears more heavily "
        "on the %s four-layer bed, whose restratification is the more "
        "sensitive. Underdrain distribution quality is therefore a material "
        "detailed-design and verification item for both configurations; it is "
        "identified here and carried into Section 15." % d1))
    c.append(_H2("Climate and event resilience"))
    c.append(_BODY(
        "Under drought or low-demand operation both configurations operate well "
        "within their hydraulic envelope. The governing concern is the opposite "
        "case: the minimum design water temperature, peak demand, a filter out "
        "of service, and an algae or clarifier-upset event raising the solids "
        "load together. Section 7 shows that at the combined "
        "minimum-temperature N-1 condition, one filter out of service, the %s "
        "configuration retains the lower head allowance for the solids load, "
        "around %s m, so its reserve against a compound event is the more "
        "limited of the two, though it remains positive and workable. The %s "
        "configuration retains a larger margin, around %s m, under the same "
        "compound condition."
        % (d1, f1(model["coldWater"]["D1"][0]["N1"]["headForLoad"]), d2,
           f1(model["coldWater"]["D2"][0]["N1"]["headForLoad"]))))
    c.append(_H2("Operational optimisation opportunity for the %s "
                 "configuration" % d2))
    c.append(_BODY(
        "In lime softening the %s configuration operates at K of %s kg/m2/run, "
        "about %s%% of its %s kg/m2/run theoretical pore-fill ceiling, so it "
        "has unused bed capacity. Its washwater handling, the largest "
        "operational consideration against it, can be reduced by two means that "
        "can be combined: running the filter closer to the breakthrough cap, "
        "and improving the upstream lime-softening clarification. The table "
        "below quantifies both."
        % (d2, f2(O["asBuilt"]["K"]), f0(O["asBuiltPctOfCeiling"]),
           f1(O["poreFill"]))))

    def opp_row(label, s):
        bp, m = s["bwPct"], s["margin"]
        bc = COL["sage"] if bp < 5 else (COL["ochre"] if bp < 8 else COL["rust"])
        return [
            label, f1(s["tss"]), f2(s["K"]), f0(s["run"]),
            {"text": pct1(bp), "bold": True, "color": bc},
            {"text": "%s%s" % ("+" if m >= 0 else "", f2(m)), "bold": True,
             "color": COL["sage"] if m >= 0 else COL["rust"]},
        ]

    c.append(grid_table(
        ["Scenario", "Feed TSS\n(mg/L)", "K\n(kg/m2/run)", "Run\n(h)",
         "Backwash\n(% flow)", "Head margin\n(m)"],
        [
            opp_row("As-built, lime softening", O["asBuilt"]),
            opp_row("Run to breakthrough cap, current feed", O["runToCap"]),
            opp_row("50% turbidity reduction, current K", O["turbCut"]),
            opp_row("50% turbidity reduction, run to cap", O["turbCutCap"]),
        ],
        [150, 62, 78, 50, 78, 97]))
    c.append(_BODY(
        "Running closer to capacity is available without a plant change and "
        "roughly halves the backwash penalty. Improving the softening carryover "
        "is the larger opportunity and, combined with the higher operating K, "
        "would bring the %s configuration's washwater use close to %s's while "
        "retaining its intrinsic hydraulic advantages." % (d2, d1)))
    c.append(_H2("Removal efficiency: a conservative assumption for the %s "
                 "filter" % d2))
    c.append(_BODY(
        "A second opportunity concerns filtrate quality. The %s filter is "
        "credited with only %s%% TSS removal in lime softening. As noted in "
        "Section 8, that is conservative for a bed of its depth; the analysis "
        "here treats it as a design assumption to be challenged, and quantifies "
        "what higher removal would mean. The table holds the design run length "
        "and tests %s, %s and %s%% removal at the %s mg/L lime-softening feed."
        % (d2, f0(RM["asBuiltRemoval"]), f0(RM["points"][0]["removal"]),
           f0(RM["points"][1]["removal"]), f0(RM["points"][2]["removal"]),
           f1(RM["feedTSS"]))))

    def rem_row(p):
        m, ft = p["margin"], p["filtrateTSS"]
        fc = COL["sage"] if ft < 1.5 else (COL["ochre"] if ft < 3 else COL["rust"])
        return [
            "%s%% removal" % f0(p["removal"]),
            f1(p["capturedTSS"]), f2(p["K"]), f0(p["runHours"]),
            {"text": "%s%s" % ("+" if m >= 0 else "", f2(m)), "bold": True,
             "color": COL["sage"] if m >= 0 else COL["rust"]},
            {"text": f2(ft), "bold": True, "color": fc},
        ]

    c.append(grid_table(
        ["Removal case", "Captured solids\n(mg/L)", "K\n(kg/m2/run)",
         "Run\n(h)", "Head margin\n(m)", "Indicative\nfiltrate TSS (mg/L)"],
        [rem_row(p) for p in RM["points"]],
        [108, 86, 80, 44, 86, 101]))
    c.append(_BODY(
        "Raising removal does not overload the bed. Because most of the solids "
        "are already captured at %s%%, lifting removal to %s%% increases the "
        "captured mass by only a few per cent: the solids holding capacity K "
        "rises by about %s kg/m2/run and the head margin gives up only about %s "
        "m, with the design run length retained and the operating point still "
        "comfortably feasible. The benefit, by contrast, is large. Indicative "
        "filtrate TSS falls from %s mg/L at %s%% to %s mg/L at %s%%, roughly a "
        "%s-fold reduction in solids passing to the clear well, with the "
        "improved barrier performance and lower downstream loading that "
        "follows."
        % (f0(RM["points"][0]["removal"]), f0(RM["points"][2]["removal"]),
           f2(RM["kRise"]), f2(RM["marginCost"]),
           f1(RM["points"][0]["filtrateTSS"]), f0(RM["points"][0]["removal"]),
           f2(RM["points"][2]["filtrateTSS"]), f0(RM["points"][2]["removal"]),
           f0(RM["filtrateGain"]))))
    c.append(_BODY(
        "The %s%% assumption may therefore understate the achievable "
        "performance of the %s filter rather than describe a limitation of it, "
        "and confirming it is a genuine opportunity: materially better treated "
        "water at negligible hydraulic cost. The opportunity is conditional on "
        "upstream coagulation and floc quality being adequate, since a deep bed "
        "can only realise high removal if the solids reaching it are "
        "filterable. The recommendation is to challenge the %s%% figure with "
        "the designer, confirm the achievable removal by pilot or "
        "reference-plant data, and verify the coagulation basis."
        % (f0(RM["asBuiltRemoval"]), d2, f0(RM["asBuiltRemoval"]))))
    c.append(_BODY(
        "The downstream consequences reinforce why this is worth pursuing. "
        "Lower filtrate solids mean less solids accumulating in the clearwater "
        "storage, a lower particulate component of disinfection demand, less "
        "solids carried into downstream sludge handling, and a wider margin "
        "against treated-water turbidity limits. Lower and more stable filtrate "
        "turbidity also strengthens confidence in the filtration step as a "
        "pathogen barrier. These consequences are described qualitatively and "
        "are not quantified here; they remain indicative and, as above, subject "
        "to upstream floc quality and validation."))
    c.append(_NOTE(
        "The optimisation opportunities discussed in this section are set out "
        "for the %s configuration because the data available to this review "
        "allowed them to be quantified. Equivalent opportunities may also exist "
        "for the %s configuration, but sufficient operating-basis data was not "
        "available within this review to quantify them; this asymmetry reflects "
        "data availability, not a conclusion that only one configuration can be "
        "optimised." % (d2, d1)))

    # ---- 15  Further areas for investigation ----
    c.extend(_H1("15", "Further areas for investigation and assessment", False))
    c.append(_BODY(
        "This assessment is a hydraulic and solids-loading comparison. Several "
        "aspects of filter performance that bear on the selection have not been "
        "assessed, because they depend on data the designers have not yet "
        "supplied. They are set out here as a structured scope for the next "
        "stage rather than as findings: for each, the questions to be answered "
        "and the evidence required are stated, so the designers and the client "
        "can close them out before selection. They are distinct from the "
        "verification actions in Section 16, which confirm the inputs to this "
        "report; the items below extend the assessment into areas it has not "
        "yet covered."))
    c.append(_H2("Filtered-water quality and barrier performance"))
    c.append(_BODY(
        "The report compares the two configurations on hydraulic capacity and "
        "solids holding, not on the quality of the water they produce or their "
        "reliability as a pathogen barrier. That is the most significant "
        "aspect not yet assessed, and it should be established before "
        "selection. Questions to be answered: what filtered-water turbidity "
        "does each configuration achieve, in each operating mode, through the "
        "full filter cycle; what particle-count performance is demonstrated; "
        "what is the turbidity peak and duration during ripening after "
        "backwash; what is the end-of-run breakthrough behaviour as terminal "
        "headloss is approached; what pathogen log-removal credit can reliably "
        "be claimed; and how does the return of recycled streams affect "
        "filtered-water stability. Evidence required: pilot-plant or "
        "reference-plant filtered-water turbidity and particle-count records, "
        "ripening profiles, and any validated log-removal basis. Why it "
        "matters: the configuration with the greater hydraulic margin is not "
        "necessarily the one with the more reliable filtered water, and a "
        "selection decision should rest on both."))
    c.append(_H2("Backwash effectiveness"))
    c.append(_BODY(
        "The report establishes how much washwater each configuration uses, "
        "but not how effectively each bed is cleaned. Questions to be answered: "
        "what air-scour and water-wash rates are applied; how is the combined "
        "air-and-water sequence structured; is a collapse-pulse step used; what "
        "bed expansion is achieved, layer by layer; how uniformly are air and "
        "washwater distributed through the underdrain system; what is the risk "
        "of media carryover to waste; how is mudball formation controlled; how "
        "reliably does the bed restratify after each wash; and what does the "
        "solids-release profile of the washwater look like through the wash. "
        "Evidence required: the designers' backwash design basis, bed-expansion "
        "calculations or test data, and reference-plant wash performance "
        "records. Why it matters: backwash effectiveness governs long-term "
        "clean-bed headloss, run length and media life, and it is the central "
        "uncertainty for the %s four-layer bed, whose interfaces are the more "
        "sensitive (Section 4)." % d1))
    c.append(_H2("Filter ripening and filter-to-waste basis"))
    c.append(_BODY(
        "The %s configuration commits a large filter-to-waste volume, %s m3 per "
        "cycle in lime softening, yet the basis for it has not been assessed. "
        "Questions to be answered: is filter-to-waste terminated on a fixed "
        "time or on a filtered-water turbidity target; what turbidity target is "
        "used; what does the post-backwash turbidity recovery curve look like; "
        "is the %s m3 per cycle a conservative allowance or an evidence-based "
        "figure; and does lime-softening operation lengthen ripening because "
        "fine calcium carbonate is slower to be retained. Evidence required: "
        "the filter-to-waste control philosophy and turbidity recovery data for "
        "each configuration. Why it matters: if the filter-to-waste volume is "
        "conservative rather than evidence-based, part of the %s washwater "
        "burden quantified in Section 10 may be recoverable, which would narrow "
        "one of the main differences between the configurations."
        % (d2, f0(S["D2"]["bw"]["ftwPerCycle"]),
           f0(S["D2"]["bw"]["ftwPerCycle"]), d2)))
    c.append(_H2("Operational control philosophy"))
    c.append(_BODY(
        "How each filter is operated will influence how the differences in "
        "this report play out, and the intended control philosophy has not "
        "been assessed. Questions to be answered: will backwash be initiated on "
        "fixed time, on headloss, on filtered-water turbidity, or on a dual "
        "trigger; what scope does the operator have to intervene during an "
        "algae or clarifier-upset event; and how is the change between "
        "coagulation and lime-softening operation managed. Evidence required: "
        "the designers' and operator's intended control and operating "
        "philosophy for each configuration. Why it matters: the two "
        "configurations point toward different control emphasis. The %s "
        "configuration operates with limited hydraulic reserve, so its control "
        "regime must protect run length and respond promptly to deterioration; "
        "the %s configuration has spare bed capacity, so the opportunity "
        "identified in Section 14 depends on a control regime that allows "
        "longer runs to be realised." % (d1, d2)))
    c.append(_H2("Softening duty and a possible relaxation of the CCPP target"))
    c.append(_BODY(
        "The lime-softening duty, and so the solids load carried to the "
        "filters, depends on the finished-water targets the plant is designed "
        "to meet. The current basis assumes a calcium carbonate precipitation "
        "potential target of zero. If that target were relaxed, for example to "
        "a positive value of the order of +5, less softening would be "
        "required, which would reduce the precipitate generated and the solids "
        "carried forward to the filters. Questions to be answered: is a "
        "relaxation of the CCPP target under consideration; what revised "
        "softening duty and feed TSS would result for each configuration; and "
        "would the magnesium-removal requirement change. Evidence required: the "
        "confirmed finished-water target and the revised softening basis from "
        "the process designers. Why it matters: a less stringent CCPP target "
        "would reduce the lime-softening feed solids for both configurations, "
        "and most materially for the %s configuration, which carries the "
        "heavier softening duty. That would ease the %s washwater handling and "
        "narrow one of the main differences between the configurations. It is "
        "identified here as a potential opportunity to be quantified once the "
        "finished-water basis is confirmed, not as a change assessed in this "
        "report." % (d2, d2)))
    c.append(_H2("Media inspection and replacement strategy"))
    c.append(_BODY(
        "Granular media are a consumable asset, and how the media will be "
        "inspected and maintained over the plant life has not been assessed. "
        "Questions to be answered: what anthracite loss rate is expected from "
        "attrition and washing, and how will media depth be monitored and "
        "topped up; how will garnet migration and the stability of the media "
        "grading be managed; at what intervals will the bed be inspected and "
        "sampled; and how will reliable restratification be confirmed in "
        "service. Evidence required: the designers' media specification, "
        "expected media life and loss rates, and a media inspection, sampling "
        "and replacement philosophy for each configuration. Why it matters: a "
        "gradual drift in media depth or grading raises clean-bed headloss and "
        "erodes performance slowly, and it bears more heavily on the %s "
        "four-layer bed, which has more interfaces and is the more sensitive to "
        "grading drift; a defined inspection and replacement strategy is needed "
        "to keep either bed performing to design over its life." % d1))
    c.append(_H2("Algal loading and filter-clogging risk"))
    c.append(_BODY(
        "The design basis allows for up to %s algae cells/mL in the raw "
        "water and filter-clogging algae are known to be present, but the "
        "effect on the filters has not been assessed, because algal clogging "
        "depends on cell morphology rather than solids mass and falls outside "
        "the mass-based analysis in this report (Section 11). Questions to be "
        "answered: which algal species are present, and which filter-clogging "
        "forms, filamentous, colonial or elongated diatoms, dominate; what "
        "seasonal peak cell counts the %s cells/mL design figure "
        "represents; what algal removal is achieved across upstream "
        "clarification; and what headloss and run-length impact algal loading "
        "has in pilot or comparable operating experience. Evidence required: "
        "raw-water algal monitoring data with species composition, the seasonal "
        "profile, and any pilot or reference-plant record of algal effect on "
        "filter runs. Why it matters: a seasonal algal load is a "
        "surface-blinding transient that bears more heavily on the leaner %s "
        "four-layer bed, while the deeper %s bed has more capacity to absorb "
        "it; quantifying the loading is needed to size that difference and to "
        "confirm both configurations can sustain runs through an algal season."
        % (algal_str, algal_str, d1, d2)))

    # ---- 16  Risk register and verification ----
    c.extend(_H1("16", "Risk register and verification recommendations", False))
    risks = [
        ["Lime-softening softening-duty difference", "Low",
         "The lime-softening feed TSS differs between the two configurations. "
         "The figures are designer-supplied and within typical softening "
         "ranges; the basis for each is as described by the respective "
         "designers' softening routes. The residual action is to confirm the "
         "difference in softening duty is intended and understood."],
    ]
    if mg_removal:
        risks.append(
            ["Magnesium hydroxide fraction in the softening floc", "Medium",
             "A softening route that removes magnesium introduces a magnesium "
             "hydroxide fraction, the least favourable precipitate for "
             "headloss, whose size is uncertain. Section 11 shows the "
             "softening margin stays positive across the plausible range; "
             "confirm the fraction to fix the operating point."])
    risks += [
        ["Filter-clogging algae in the raw water", "Medium",
         "The design basis allows up to %s algae cells/mL and "
         "filter-clogging algae are present in the source. Algal clogging is "
         "morphology-driven and outside the mass-based analysis; it bears more "
         "heavily on the leaner D1 bed. Characterise the species mix and "
         "seasonal behaviour and confirm the upstream removal assumption "
         "(Section 11)." % algal_str],
        ["D1 redundancy margin at minimum temperature", "Low to Medium",
         "At the maximum design flow, the governing N-1 condition (one filter "
         "out of service) and the 15 degrees C minimum design water "
         "temperature, D1 retains the lower head allowance for solids load, "
         "around +1.2 m. It is positive and workable but the lower reserve of "
         "the two. Confirm the driving head and the minimum design water "
         "temperature."],
        ["D2 removal efficiency assumption", "Medium",
         "The 90% TSS removal assumed for the D2 filter in lime softening is "
         "conservative for a 2.10 m dual-media bed and may understate its "
         "capability. Challenge and verify the achievable removal; see "
         "Section 14."],
        ["D2 washwater and recycle loading", "Medium to High",
         "In lime softening D2 handles close to 20% of plant flow as dump, "
         "backwash and filter-to-waste. Confirm the washwater recovery design "
         "and acceptable DAF and recycle loading."],
        ["Coagulant chemistry assumptions", "Medium",
         "The coagulation analysis assumes ferric for D1 and alum for D2. The "
         "deposit structure factor, and so the head budget, depends on this."],
        ["Feed deterioration beyond the tested range", "Medium",
         "Section 11 tests a 100% deterioration. D1 has the least head reserve "
         "at that point, so a larger or compound deterioration would erode its "
         "margin first."],
        ["Media restratification, D1 four-layer bed", "Medium",
         "Reliable restratification of the four-layer arrangement after "
         "backwash has not been verified and affects long-term performance and "
         "maintenance."],
    ]
    risk_body = [[_cell_para("Risk", header=True),
                  _cell_para("Rating", header=True),
                  _cell_para("Description and required action", header=True)]]
    for r in risks:
        risk_body.append([_cell_para(bold_cell(r[0])), _cell_para(r[1]),
                           _cell_para(r[2])])
    risk_style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, COL["ink"]),
    ]
    for r in range(1, len(risk_body) - 1):
        risk_style.append(("LINEBELOW", (0, r), (-1, r), 0.3, COL["rule"]))
    risk_tbl = Table(risk_body, colWidths=[135, 62, 318], repeatRows=1)
    risk_tbl.setStyle(TableStyle(risk_style))
    risk_tbl.spaceBefore = 2
    risk_tbl.spaceAfter = 8
    c.append(risk_tbl)
    c.append(_H2("Independent verification recommendations"))
    c.append(_BODY(
        "The following independent verification of the inputs to this report "
        "should be completed before it is used as a basis for configuration "
        "selection. Further areas of assessment that extend beyond this report "
        "are set out in Section 15."))
    for t in [
        "Independent hydraulic review confirming the plant hydraulic profile "
        "and the available driving head, including the governing N-1 condition "
        "at the minimum design water temperature.",
        "Confirmation of the minimum design water temperature used as the "
        "head-budget basis.",
        "Confirmation that the difference in softening duty (D2 magnesium "
        "removal, D1 calcium-carbonate-dominant) is intended, and confirmation "
        "of the magnesium hydroxide fraction in the D2 softening precipitate "
        "(Section 11).",
        "Verification of the achievable D2 filter TSS removal, assumed "
        "conservatively at 90% and expected to be higher subject to floc "
        "quality and validation (Section 14).",
        "Pilot or reference-plant data confirming each configuration sustains "
        "its stated run length in each operating mode.",
        "Seasonal algal characterisation, including dominant species, cell "
        "morphology, colonial or filamentous forms, upstream removal "
        "efficiency, and pilot or reference-plant filter run data during algal "
        "events (Section 11).",
        "Dirty-bed terminal headloss across the design water-temperature range, "
        "from each designer.",
        "Whole-of-life operating cost modelling covering washwater, recycle "
        "pumping, chemical and sludge implications.",
    ]:
        c.append(bullet(t))
    c.append(HRule(thickness=0.5, color=COL["rule"], space_before=8, space_after=4))
    c.append(Paragraph(_esc(
        "This comparative assessment supports design review and selection. It "
        "is subject to the limitations, verification actions and further areas "
        "of assessment set out in this report, and is not a substitute for "
        "detailed design, pilot validation or independent clarification "
        "modelling."), STYLES["foot"]))


# --------------------------------------------------------------------------
# Page furniture: footer with "Page X of Y" (two-pass numbered canvas)
# --------------------------------------------------------------------------
from reportlab.pdfgen import canvas as _canvas  # noqa: E402


class _NumberedCanvas(_canvas.Canvas):
    """Defers footer drawing until the total page count is known."""

    def __init__(self, *args, **kwargs):
        self._footer_left = kwargs.pop("footer_left", "")
        super().__init__(*args, **kwargs)
        self._saved_states = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        self.setFont("Helvetica", 7)
        self.setFillColor(COL["ink500"])
        y = 30
        self.drawString(40, y, self._footer_left)
        self.drawRightString(PAGE_W - 40, y,
                             "Revision A   |   Page %d of %d"
                             % (self._pageNumber, total))


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def build_pdf(model, charts=None, output_path=None):
    """Build the filter performance assessment PDF.

    Parameters
    ----------
    model : dict
        The assessment model from engine.report_model.build_report_model.
    charts : dict, optional
        Pre-built chart buffers (report.charts.build_all_charts). Built
        automatically if not supplied.
    output_path : str, optional
        If given, the PDF is also written to this path.

    Returns
    -------
    bytes
        The rendered PDF document.
    """
    if charts is None:
        charts = build_all_charts(model)

    story = _build_story(model, charts)

    d1, d2 = model["names"]["d1"], model["names"]["d2"]
    footer_left = "Filter Performance Assessment   %s and %s" % (d1, d2)

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=40, rightMargin=40, topMargin=44, bottomMargin=48,
        title="Filter Performance Assessment, %s and %s" % (d1, d2),
        author=model.get("preparedBy") or "Filter Performance Comparator",
    )
    frame = Frame(40, 48, PAGE_W - 80, PAGE_H - 44 - 48, id="main",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])

    def _maker(*args, **kwargs):
        kwargs["footer_left"] = footer_left
        return _NumberedCanvas(*args, **kwargs)

    doc.build(story, canvasmaker=_maker)

    pdf = buf.getvalue()
    if output_path:
        with open(output_path, "wb") as fh:
            fh.write(pdf)
    return pdf
