"""
core/reporting/pfd_generator.py

Generates schematic Process Flow Diagrams (PFDs) for each treatment technology
using ReportLab Drawing primitives. Returns a ReportLab Flowable that can be
embedded directly in PDF reports.

No external SVG/image library required.
"""
from __future__ import annotations
from typing import Dict, Any, Optional


# ── Colours ────────────────────────────────────────────────────────────────
def _hex(h): 
    from reportlab.lib import colors
    return colors.HexColor(f"#{h}")

BLUE    = "1F6AA5"
BLUE_LT = "D5E8F0"
GREY    = "AAAAAA"
GREY_LT = "F4F4F4"
GREEN   = "27AE60"
ORANGE  = "E67E22"
RED     = "C0392B"
WHITE   = "FFFFFF"
BLACK   = "000000"


def get_pfd(tech_code: str, tech_perf: Dict[str, Any],
            width: float = 480, height: float = 160) -> object:
    """
    Return a ReportLab Drawing of the PFD for the given technology.
    tech_perf = technology_performance dict from domain_specific_outputs.
    """
    drawers = {
        "bnr":             _pfd_bnr,
        "granular_sludge": _pfd_ags,
        "mabr_bnr":        _pfd_mabr,
        "bnr_mbr":         _pfd_bnr_mbr,
        "ifas_mbbr":       _pfd_ifas,
        "anmbr":           _pfd_anmbr,
    }
    fn = drawers.get(tech_code, _pfd_generic)
    return fn(tech_perf, width, height)


# ── Drawing helpers ────────────────────────────────────────────────────────

def _base_drawing(width, height):
    from reportlab.graphics.shapes import Drawing, Rect
    d = Drawing(width, height)
    # Light background
    d.add(Rect(0, 0, width, height, fillColor=_hex(GREY_LT),
               strokeColor=_hex(GREY), strokeWidth=0.5))
    return d


def _box(d, x, y, w, h, label, sublabel="", fill=BLUE_LT, stroke=BLUE,
         label_size=7, sub_size=6):
    """Draw a process unit box with label."""
    from reportlab.graphics.shapes import Rect, String
    d.add(Rect(x, y, w, h, fillColor=_hex(fill),
               strokeColor=_hex(stroke), strokeWidth=1))
    # Main label centred
    d.add(String(x + w/2, y + h/2 + (4 if sublabel else 1),
                 label,
                 fontSize=label_size, fontName="Helvetica-Bold",
                 textAnchor="middle", fillColor=_hex(BLACK)))
    if sublabel:
        d.add(String(x + w/2, y + h/2 - 6,
                     sublabel,
                     fontSize=sub_size, fontName="Helvetica",
                     textAnchor="middle", fillColor=_hex(GREY)))


def _arrow(d, x1, y1, x2, y2, label="", color=GREY, lw=1.0):
    """Draw a flow arrow with optional label."""
    from reportlab.graphics.shapes import Line, Polygon, String
    import math
    d.add(Line(x1, y1, x2, y2, strokeColor=_hex(color),
               strokeWidth=lw))
    # Arrowhead
    angle = math.atan2(y2-y1, x2-x1)
    ah = 5
    ax1 = x2 - ah * math.cos(angle - 0.4)
    ay1 = y2 - ah * math.sin(angle - 0.4)
    ax2 = x2 - ah * math.cos(angle + 0.4)
    ay2 = y2 - ah * math.sin(angle + 0.4)
    d.add(Polygon([x2, y2, ax1, ay1, ax2, ay2],
                  fillColor=_hex(color), strokeColor=_hex(color), strokeWidth=0.5))
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        d.add(String(mx, my + 3, label,
                     fontSize=5.5, fontName="Helvetica",
                     textAnchor="middle", fillColor=_hex(GREY)))


def _dashed_arrow(d, x1, y1, x2, y2, label=""):
    """Dashed recycle arrow."""
    from reportlab.graphics.shapes import Line, String
    # Draw as short dashes
    import math
    dx, dy = x2-x1, y2-y1
    length = math.sqrt(dx*dx + dy*dy)
    if length == 0:
        return
    nx, ny = dx/length, dy/length
    dash_len, gap_len = 5, 3
    pos = 0
    drawing = True
    while pos < length:
        end = min(pos + (dash_len if drawing else gap_len), length)
        if drawing:
            sx, sy = x1 + pos*nx, y1 + pos*ny
            ex, ey = x1 + end*nx, y1 + end*ny
            d.add(Line(sx, sy, ex, ey, strokeColor=_hex(ORANGE),
                       strokeWidth=0.8))
        pos = end
        drawing = not drawing
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        d.add(String(mx, my + 3, label,
                     fontSize=5, fontName="Helvetica",
                     textAnchor="middle", fillColor=_hex(ORANGE)))


def _circle(d, cx, cy, r, label, fill=WHITE, stroke=BLUE):
    from reportlab.graphics.shapes import Circle, String
    d.add(Circle(cx, cy, r, fillColor=_hex(fill),
                 strokeColor=_hex(stroke), strokeWidth=0.8))
    d.add(String(cx, cy - 2.5, label, fontSize=5.5, fontName="Helvetica",
                 textAnchor="middle", fillColor=_hex(BLACK)))


def _label(d, x, y, text, size=6, color=GREY, anchor="middle"):
    from reportlab.graphics.shapes import String
    d.add(String(x, y, text, fontSize=size, fontName="Helvetica",
                 textAnchor=anchor, fillColor=_hex(color)))


def _title(d, width, height, tech_name):
    from reportlab.graphics.shapes import String, Rect
    d.add(Rect(0, height-14, width, 14, fillColor=_hex(BLUE),
               strokeColor=_hex(BLUE), strokeWidth=0))
    d.add(String(8, height-10, f"Process Flow Diagram — {tech_name}",
                 fontSize=7, fontName="Helvetica-Bold",
                 fillColor=_hex(WHITE)))
    d.add(String(width-8, height-10, "SCHEMATIC — NOT TO SCALE",
                 fontSize=6, fontName="Helvetica",
                 textAnchor="end", fillColor=_hex(BLUE_LT)))


# ── Technology PFDs ────────────────────────────────────────────────────────

def _pfd_bnr(perf: dict, W: float, H: float):
    """BNR with secondary clarifiers."""
    d = _base_drawing(W, H)
    _title(d, W, H, "BNR with Secondary Clarifiers")

    # Layout: Influent → [Pre-Screen] → [Anaerobic] → [Anoxic] → [Aerobic] → [Clarifier] → Effluent
    #                                                    ↑ MLR ←←←←←←←←←←←←←←←←←←←←←←←
    #                                         ↑ RAS ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←

    bh = 46   # box height
    by = 60   # box y base
    margin = 14

    # boxes: x, width
    boxes = [
        (margin,        40,  "Screen/\nGrit",  "",       GREY_LT, GREY),
        (62,            46,  "Anaerobic",      "An",     BLUE_LT, BLUE),
        (116,           52,  "Anoxic",         "Ax",     BLUE_LT, BLUE),
        (176,           62,  "Aerobic",        "Ae\n(FBDA)", BLUE_LT, BLUE),
        (246,           50,  "Secondary\nClarifier", "",  "EBF2F7", BLUE),
    ]

    v_react = perf.get("reactor_volume_m3", 0)
    v_ax    = perf.get("v_anoxic_m3",  0)
    v_ae    = perf.get("v_aerobic_m3", 0)
    n_clar  = perf.get("n_clarifiers", 2)
    area    = perf.get("clarifier_area_m2", 0)
    o2      = perf.get("o2_demand_kg_day", 0)

    subs = ["", "", f"{v_ax:.0f} m³" if v_ax else "", f"{v_ae:.0f} m³" if v_ae else "",
            f"{n_clar}×{area/max(n_clar,1):.0f} m²" if area else ""]

    for i, (bx, bw, lbl, sub2, fill, stroke) in enumerate(boxes):
        sublabel = subs[i] if subs[i] else sub2
        _box(d, bx, by, bw, bh, lbl.replace("\n"," "), sublabel, fill, stroke)

    # Flow arrows
    xpos = [margin+40, 62+46, 116+52, 176+62, 246+50]
    for i in range(len(xpos)-1):
        _arrow(d, xpos[i], by+bh/2, xpos[i]+2, by+bh/2, color=BLUE, lw=1.2)

    # Influent arrow
    _arrow(d, 2, by+bh/2, margin, by+bh/2, "Influent", BLUE, 1.2)

    # Effluent arrow
    _arrow(d, xpos[-1], by+bh/2, xpos[-1]+22, by+bh/2, "Effluent", GREEN, 1.2)

    # RAS: clarifier bottom → anoxic (dashed)
    ras_x = 271; clar_bot = by
    _dashed_arrow(d, ras_x, clar_bot, ras_x, by-20)
    _arrow(d, ras_x, by-20, 140, by-20, "", ORANGE, 0.8)
    _arrow(d, 140, by-20, 140, by, "", ORANGE, 0.8)
    _label(d, (ras_x+140)/2, by-25, "RAS", 5.5, ORANGE)

    # MLR: end of aerobic → anoxic (dashed at top)
    mlr_x = 220
    _dashed_arrow(d, mlr_x, by+bh, mlr_x, by+bh+18)
    _arrow(d, mlr_x, by+bh+18, 142, by+bh+18, "", ORANGE, 0.8)
    _arrow(d, 142, by+bh+18, 142, by+bh, "", ORANGE, 0.8)
    _label(d, (mlr_x+142)/2+5, by+bh+22, "MLR (4×Q)", 5.5, ORANGE)

    # WAS arrow from clarifier
    _arrow(d, 271, by+8, 271, by-12, "", RED, 0.8)
    _label(d, 279, by-8, "WAS", 5.5, RED, "start")

    # Blower symbol
    _circle(d, 207, by-14, 8, "Blower", WHITE, BLUE)
    _arrow(d, 207, by-6, 207, by, "", BLUE, 0.8)
    _label(d, 207, by-28, f"O₂ {o2:.0f} kg/d" if o2 else "Aeration", 5.5, BLUE)

    # Sludge treatment
    _box(d, 305, by+8, 40, 28, "Sludge Thickening\n& Dewatering", "", GREY_LT, GREY, 5.5)
    _arrow(d, 271, by+22, 305, by+22, "", RED, 0.8)
    _label(d, 326, by+2, "Biosolids", 5.5, RED)

    # Dimensions label
    fp = perf.get("footprint_m2", 0)
    if fp:
        _label(d, W-8, 12, f"Reactor: {v_react:.0f} m³  |  Footprint: {fp:.0f} m²",
               5.5, GREY, "end")

    return d


def _pfd_ags(perf: dict, W: float, H: float):
    """Aerobic Granular Sludge (Nereda SBR)."""
    d = _base_drawing(W, H)
    _title(d, W, H, "Aerobic Granular Sludge (Nereda®) — SBR Process")

    bh = 50; by = 55
    n_react = perf.get("n_reactors", 3)
    vol_each = perf.get("vol_per_reactor_m3", 550)
    fbt_vol  = perf.get("fbt_volume_m3", 0)
    mlss     = perf.get("mlss_granular_mg_l", 8000)
    o2       = perf.get("o2_demand_kg_day", 0)
    fp       = perf.get("footprint_m2", 0)

    # Flow balance tank
    fbt_x = 16
    _box(d, fbt_x, by, 46, bh, "Flow Balance\nTank", f"{fbt_vol:.0f} m³" if fbt_vol else "",
         GREY_LT, GREY)

    # Feed pump
    _circle(d, fbt_x+56, by+bh/2, 7, "Feed\nPump", WHITE, BLUE)

    # SBR reactors (show as 3 parallel units)
    sbr_x = fbt_x + 72
    for i in range(min(n_react, 3)):
        rx = sbr_x + i*58
        _box(d, rx, by, 52, bh,
             f"SBR Reactor {i+1}",
             f"{vol_each:.0f} m³\nMLSS {mlss:.0f}",
             BLUE_LT, BLUE, 6.5, 5.5)
        # Blower arrow up from bottom
        _arrow(d, rx+26, by-14, rx+26, by, "", BLUE, 0.8)
        _circle(d, rx+26, by-20, 7, "Blwr", WHITE, BLUE)

    # Aeration note
    _label(d, sbr_x + n_react*29, by-28,
           f"High-intensity aeration (feast phase)  O₂: {o2:.0f} kg/d" if o2 else "Aeration",
           5.5, BLUE, "middle")

    # Flow arrows from FBT to reactors
    _arrow(d, fbt_x+46, by+bh/2, fbt_x+49, by+bh/2, "", BLUE, 1.0)
    _arrow(d, fbt_x+63, by+bh/2, sbr_x, by+bh/2, "", BLUE, 1.0)

    # Effluent decant from each reactor
    decant_x = sbr_x + n_react*58 + 6
    for i in range(min(n_react, 3)):
        rx = sbr_x + i*58 + 52
        _arrow(d, rx, by+bh*0.7, decant_x-4, by+bh*0.7, "", GREEN, 0.8)

    # Effluent collection
    _box(d, decant_x, by+10, 38, 30, "Effluent\nCollection", "", "EBF2F7", BLUE)
    _arrow(d, decant_x+38, by+25, decant_x+58, by+25, "Effluent", GREEN, 1.2)

    # WAS from each reactor
    was_y = by + 4
    _arrow(d, sbr_x+26, was_y, sbr_x+26, was_y-16, "", RED, 0.8)
    _label(d, sbr_x+28, was_y-14, "WAS", 5.5, RED, "start")
    _box(d, sbr_x-2, was_y-32, 50, 20, "Sludge Dewatering", "", GREY_LT, GREY, 5.5)
    _label(d, sbr_x+22, was_y-44, "Biosolids", 5.5, RED)

    # Influent
    _arrow(d, 2, by+bh/2, fbt_x, by+bh/2, "Influent", BLUE, 1.2)

    # SBR cycle note
    cycle_x = W - 90
    _box(d, cycle_x, by+6, 82, 40, "SBR Cycle", "", GREY_LT, GREY, 6.5)
    _label(d, cycle_x+4, by+36, "1. Fill (anaerobic)", 5, GREY, "start")
    _label(d, cycle_x+4, by+28, "2. React (aeration)", 5, GREY, "start")
    _label(d, cycle_x+4, by+20, "3. Settle", 5, GREY, "start")
    _label(d, cycle_x+4, by+12, "4. Decant", 5, GREY, "start")

    if fp:
        _label(d, W-8, 12, f"Reactor: {perf.get('reactor_volume_m3',0):.0f} m³  |  Footprint: {fp:.0f} m²  |  {n_react} reactors",
               5.5, GREY, "end")
    return d


def _pfd_mabr(perf: dict, W: float, H: float):
    """MABR + BNR retrofit."""
    d = _base_drawing(W, H)
    _title(d, W, H, "MABR + BNR — MABR Retrofit into Aerobic Zone")

    bh = 46; by = 58
    v_an   = perf.get("v_anaerobic_m3", 315)
    v_ax   = perf.get("v_anoxic_m3", 1278)
    v_ae   = perf.get("v_aerobic_reduced_m3", 1212)
    mabr_a = perf.get("mabr_membrane_area_m2", 0)
    n_clar = perf.get("n_clarifiers", 3)
    o2     = perf.get("o2_demand_kg_day", 0)
    fp     = perf.get("footprint_m2", 0)

    # Boxes
    _box(d, 14,  by, 36, bh, "Screen/\nGrit", "", GREY_LT, GREY)
    _box(d, 58,  by, 44, bh, "Anaerobic", f"{v_an:.0f} m³", BLUE_LT, BLUE)
    _box(d, 110, by, 58, bh, "Anoxic\n(enlarged)", f"{v_ax:.0f} m³", BLUE_LT, BLUE)
    _box(d, 176, by, 68, bh, "MABR Aerobic Zone", f"{v_ae:.0f} m³\n{mabr_a:.0f} m² membrane",
         "D5EAF5", BLUE, 6.5, 5)
    _box(d, 252, by, 48, bh, "Secondary\nClarifier", f"{n_clar} units", "EBF2F7", BLUE)

    # Flow arrows
    pts = [14+36, 58+44, 110+58, 176+68, 252+48]
    for i in range(len(pts)-1):
        _arrow(d, pts[i], by+bh/2, pts[i]+2, by+bh/2, color=BLUE, lw=1.2)

    _arrow(d, 2, by+bh/2, 14, by+bh/2, "Influent", BLUE, 1.2)
    _arrow(d, pts[-1], by+bh/2, pts[-1]+24, by+bh/2, "Effluent", GREEN, 1.2)

    # MABR gas supply (different from blower)
    _circle(d, 210, by-18, 8, "MABR\nGas", WHITE, "D44000")
    _arrow(d, 210, by-10, 210, by, "", "D44000", 0.8)
    _label(d, 210, by-32, "Low-pressure gas supply", 5.5, "D44000")

    # Conventional blower (50% of load)
    _circle(d, 175, by-18, 7, "Blower\n50%", WHITE, BLUE)
    _arrow(d, 175, by-11, 175, by, "", BLUE, 0.8)

    # RAS
    ras_x = 276
    _dashed_arrow(d, ras_x, by, ras_x, by-20)
    _arrow(d, ras_x, by-20, 130, by-20, "", ORANGE, 0.8)
    _arrow(d, 130, by-20, 130, by, "", ORANGE, 0.8)
    _label(d, (ras_x+130)/2, by-25, "RAS", 5.5, ORANGE)

    # MLR
    _dashed_arrow(d, 215, by+bh, 215, by+bh+16)
    _arrow(d, 215, by+bh+16, 140, by+bh+16, "", ORANGE, 0.8)
    _arrow(d, 140, by+bh+16, 140, by+bh, "", ORANGE, 0.8)
    _label(d, 178, by+bh+20, "MLR (4×Q)", 5.5, ORANGE)

    # WAS + sludge
    _arrow(d, 276, by+8, 276, by-12, "", RED, 0.8)
    _label(d, 280, by-8, "WAS", 5.5, RED, "start")
    _box(d, 308, by+10, 40, 26, "Sludge\nDewatering", "", GREY_LT, GREY, 5.5)
    _arrow(d, 276, by+22, 308, by+22, "", RED, 0.8)

    # Capacity uplift note
    _box(d, W-85, by+2, 80, 42, "MABR Benefit", "", GREY_LT, GREY, 6)
    _label(d, W-82, by+34, "30% NH₄ capacity uplift", 5, GREY, "start")
    _label(d, W-82, by+26, "44% aeration energy saving", 5, GREEN, "start")
    _label(d, W-82, by+18, "Same reactor volume as BNR", 5, GREY, "start")
    _label(d, W-82, by+10, "Conventional clarifiers retained", 5, GREY, "start")

    if fp:
        _label(d, 8, 12, f"Reactor: {perf.get('reactor_volume_m3',0):.0f} m³  |  Footprint: {fp:.0f} m²",
               5.5, GREY, "start")
    return d


def _pfd_bnr_mbr(perf: dict, W: float, H: float):
    """BNR + MBR Hybrid."""
    d = _base_drawing(W, H)
    _title(d, W, H, "BNR + MBR Hybrid (BNR Basins + Membrane Separation)")

    bh = 46; by = 58
    v_ax    = perf.get("bnr_anoxic_volume_m3", 992)
    v_ae    = perf.get("bnr_aerobic_volume_m3", 1843)
    v_mem   = perf.get("membrane_tank_volume_m3", 1418)
    mem_a   = perf.get("membrane_area_m2", 0)
    fp      = perf.get("footprint_m2", 0)
    o2      = perf.get("o2_demand_kg_day", 0)

    _box(d, 14,  by, 36, bh, "Screen/\nGrit", "", GREY_LT, GREY)
    _box(d, 58,  by, 44, bh, "Anaerobic\nZone", "", BLUE_LT, BLUE)
    _box(d, 110, by, 52, bh, "Anoxic Zone", f"{v_ax:.0f} m³", BLUE_LT, BLUE)
    _box(d, 170, by, 58, bh, "Aerobic Zone", f"{v_ae:.0f} m³\n(FBDA aeration)", BLUE_LT, BLUE)
    _box(d, 236, by, 58, bh, "Membrane Tank", f"{v_mem:.0f} m³\n{mem_a:.0f} m² membrane",
         "D5EAF5", BLUE, 6.5, 5)

    pts = [14+36, 58+44, 110+52, 170+58, 236+58]
    for i in range(len(pts)-1):
        _arrow(d, pts[i], by+bh/2, pts[i]+2, by+bh/2, color=BLUE, lw=1.2)

    _arrow(d, 2, by+bh/2, 14, by+bh/2, "Influent", BLUE, 1.2)
    # Permeate (effluent) goes up from membrane tank
    perm_x = 265
    _arrow(d, perm_x, by+bh, perm_x, by+bh+20, "Permeate\n(Effluent)", GREEN, 1.2)
    _label(d, perm_x, by+bh+28, "TSS <1 mg/L", 5.5, GREEN)

    # RAS from membrane tank bottom
    _dashed_arrow(d, 255, by, 255, by-20)
    _arrow(d, 255, by-20, 130, by-20, "", ORANGE, 0.8)
    _arrow(d, 130, by-20, 130, by, "", ORANGE, 0.8)
    _label(d, (255+130)/2, by-25, "RAS (internal recycle)", 5.5, ORANGE)

    # MLR
    _dashed_arrow(d, 210, by+bh, 210, by+bh+16)
    _arrow(d, 210, by+bh+16, 136, by+bh+16, "", ORANGE, 0.8)
    _arrow(d, 136, by+bh+16, 136, by+bh, "", ORANGE, 0.8)
    _label(d, 174, by+bh+20, "MLR (4×Q)", 5.5, ORANGE)

    # Blower — bio aeration
    _circle(d, 199, by-16, 7, "Blower\n(Bio)", WHITE, BLUE)
    _arrow(d, 199, by-9, 199, by, "", BLUE, 0.8)

    # Membrane scour blower
    _circle(d, 258, by-16, 7, "Blower\n(Scour)", WHITE, "D44000")
    _arrow(d, 258, by-9, 258, by, "", "D44000", 0.8)

    # WAS
    _arrow(d, 275, by+10, 305, by+10, "", RED, 0.8)
    _label(d, 295, by+14, "WAS", 5.5, RED)
    _box(d, 305, by+2, 40, 26, "Sludge\nDewatering", "", GREY_LT, GREY, 5.5)

    # Standby clarifier (optional, shown dashed)
    _box(d, 350, by+8, 46, 30, "Standby\nClarifier", "(bypass)", "FAFAFA", GREY)
    _label(d, 373, by+4, "(optional)", 5, GREY)

    if fp:
        _label(d, W-8, 12, f"Reactor: {perf.get('reactor_volume_m3',0):.0f} m³  |  Footprint: {fp:.0f} m²",
               5.5, GREY, "end")
    return d


def _pfd_ifas(perf: dict, W: float, H: float):
    """IFAS / MBBR."""
    d = _base_drawing(W, H)
    _title(d, W, H, "IFAS / MBBR — Integrated Fixed-Film Activated Sludge")

    bh = 46; by = 58
    media_a = perf.get("media_protected_area_m2", 0)
    fill_r  = perf.get("media_fill_ratio", 0.35)
    fp      = perf.get("footprint_m2", 0)
    o2      = perf.get("o2_demand_kg_day", 0)
    v_react = perf.get("reactor_volume_m3", 0)

    _box(d, 14,  by, 36, bh, "Screen/\nGrit", "", GREY_LT, GREY)
    _box(d, 58,  by, 44, bh, "Anaerobic\nZone", "", BLUE_LT, BLUE)
    _box(d, 110, by, 52, bh, "Anoxic Zone\n(existing basin)", "", BLUE_LT, BLUE)
    # IFAS zone — show carrier media hatching
    _box(d, 170, by, 70, bh, "IFAS Zone", 
         f"Media {fill_r*100:.0f}% fill\nFBDA aeration", "D5EAF5", BLUE, 6.5, 5)
    _box(d, 248, by, 52, bh, "Secondary\nClarifier", "", "EBF2F7", BLUE)

    # Media symbol inside IFAS box (small circles)
    import math
    for xi in range(5):
        for yi in range(2):
            cx = 178 + xi*12
            cy = by + 12 + yi*18
            _circle(d, cx, cy, 4, "", BLUE_LT, BLUE)
            _label(d, cx, cy-2.5, "☰", 4, BLUE)

    pts = [14+36, 58+44, 110+52, 170+70, 248+52]
    for i in range(len(pts)-1):
        _arrow(d, pts[i], by+bh/2, pts[i]+2, by+bh/2, color=BLUE, lw=1.2)

    _arrow(d, 2, by+bh/2, 14, by+bh/2, "Influent", BLUE, 1.2)
    _arrow(d, pts[-1], by+bh/2, pts[-1]+24, by+bh/2, "Effluent", GREEN, 1.2)

    # Blower
    _circle(d, 205, by-16, 7, "Blower", WHITE, BLUE)
    _arrow(d, 205, by-9, 205, by, "", BLUE, 0.8)
    _label(d, 205, by-28, f"O₂ {o2:.0f} kg/d" if o2 else "Aeration", 5.5, BLUE)

    # Media screens label
    _label(d, 170, by+bh+4, "↑ Retention screens keep media in zone", 5.5, BLUE, "start")

    # RAS
    ras_x = 274
    _dashed_arrow(d, ras_x, by, ras_x, by-18)
    _arrow(d, ras_x, by-18, 130, by-18, "", ORANGE, 0.8)
    _arrow(d, 130, by-18, 130, by, "", ORANGE, 0.8)
    _label(d, (ras_x+130)/2, by-23, "RAS", 5.5, ORANGE)

    # MLR
    _dashed_arrow(d, 220, by+bh, 220, by+bh+14)
    _arrow(d, 220, by+bh+14, 136, by+bh+14, "", ORANGE, 0.8)
    _arrow(d, 136, by+bh+14, 136, by+bh, "", ORANGE, 0.8)
    _label(d, 178, by+bh+18, "MLR (4×Q)", 5.5, ORANGE)

    _arrow(d, 274, by+10, 305, by+10, "", RED, 0.8)
    _label(d, 294, by+14, "WAS", 5.5, RED)
    _box(d, 305, by+2, 40, 26, "Sludge\nDewatering", "", GREY_LT, GREY, 5.5)

    if fp:
        _label(d, W-8, 12, f"Reactor: {v_react:.0f} m³  |  Footprint: {fp:.0f} m²",
               5.5, GREY, "end")
    return d


def _pfd_anmbr(perf: dict, W: float, H: float):
    _box_generic = lambda: None
    d = _base_drawing(W, H)
    _title(d, W, H, "Anaerobic MBR (AnMBR)")
    _label(d, W/2, H/2, "AnMBR — schematic in development", 9, GREY)
    return d


def _pfd_generic(perf: dict, W: float, H: float):
    d = _base_drawing(W, H)
    _title(d, W, H, "Treatment Process")
    _label(d, W/2, H/2, "Process flow schematic", 9, GREY)
    return d
