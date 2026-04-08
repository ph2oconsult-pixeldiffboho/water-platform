"""
PurePoint ui_helpers.py
Follows the same pattern as AquaPoint ui_helpers.py.
All function signatures are compatible with the platform convention.
"""

import streamlit as st
from .engine import CLASS_COLOURS, CLASS_LABELS


# ---------------------------------------------------------------------------
# Platform-standard components (mirrors AquaPoint ui_helpers signatures)
# ---------------------------------------------------------------------------

def section_header(title: str, icon: str = "") -> None:
    prefix = f"{icon} " if icon else ""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
        f'<span style="width:8px;height:8px;border-radius:50%;background:#00b4d8;'
        f'display:inline-block;flex-shrink:0;"></span>'
        f'<span style="font-weight:600;font-size:1rem;">{prefix}{title}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def warning_box(msg: str) -> None:
    st.markdown(
        f'<div style="border-left:3px solid #f5a623;background:#fffbe8;'
        f'padding:10px 14px;border-radius:0 4px 4px 0;margin:8px 0;'
        f'color:#7a5c00;font-size:0.88rem;">{msg}</div>',
        unsafe_allow_html=True,
    )


def info_box(msg: str) -> None:
    st.markdown(
        f'<div style="border-left:3px solid #00b4d8;background:#e8f8fc;'
        f'padding:10px 14px;border-radius:0 4px 4px 0;margin:8px 0;'
        f'color:#005fa3;font-size:0.88rem;">{msg}</div>',
        unsafe_allow_html=True,
    )


def success_box(msg: str) -> None:
    st.markdown(
        f'<div style="border-left:3px solid #22c87a;background:#e8f5ee;'
        f'padding:10px 14px;border-radius:0 4px 4px 0;margin:8px 0;'
        f'color:#1a6b3c;font-size:0.88rem;">{msg}</div>',
        unsafe_allow_html=True,
    )


def error_box(msg: str) -> None:
    st.markdown(
        f'<div style="border-left:3px solid #f05252;background:#fdf2f2;'
        f'padding:10px 14px;border-radius:0 4px 4px 0;margin:8px 0;'
        f'color:#b91c1c;font-size:0.88rem;">{msg}</div>',
        unsafe_allow_html=True,
    )


def render_kpi_card(label: str, value: str, unit: str = "") -> None:
    st.markdown(
        f'<div style="background:#1a2636;border:1px solid #1e2d3d;border-radius:6px;'
        f'padding:14px 16px;">'
        f'<div style="font-size:0.72rem;color:#8fa3b8;text-transform:uppercase;'
        f'letter-spacing:0.1em;margin-bottom:6px;">{label}</div>'
        f'<div style="font-size:1.3rem;font-weight:600;color:#e2eaf2;">{value}'
        f'<span style="font-size:0.8rem;color:#8fa3b8;margin-left:4px;">{unit}</span>'
        f"</div></div>",
        unsafe_allow_html=True,
    )


def risk_badge(label: str) -> str:
    colour_map = {
        "High":        ("#f05252", "#fdf2f2"),
        "Medium-High": ("#f05252", "#fdf2f2"),
        "Medium":      ("#f5a623", "#fffbe8"),
        "Low-Medium":  ("#f5a623", "#fffbe8"),
        "Low":         ("#22c87a", "#e8f5ee"),
        "Very Low":    ("#22c87a", "#e8f5ee"),
        "None":        ("#8fa3b8", "#f0f4f8"),
    }
    fg, bg = colour_map.get(label, ("#8fa3b8", "#f0f4f8"))
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:20px;font-size:0.75rem;font-weight:600;">{label}</span>'
    )


def compliance_badge(compliant: bool) -> str:
    if compliant:
        return '<span style="background:#e8f5ee;color:#1a6b3c;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:600;">✓ Pass</span>'
    return '<span style="background:#fdf2f2;color:#b91c1c;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:600;">✗ Fail</span>'


def margin_badge(margin: float) -> str:
    if margin > 1.0:
        return f'<span style="color:#22c87a;font-family:monospace;font-weight:600;">+{margin}</span>'
    if margin >= 0:
        return f'<span style="color:#f5a623;font-family:monospace;font-weight:600;">+{margin}</span>'
    return f'<span style="color:#f05252;font-family:monospace;font-weight:600;">{margin}</span>'


def lrv_status_badge(margin: float) -> str:
    if margin > 1.0:
        return '<span style="background:#e8f5ee;color:#1a6b3c;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:600;">✓ Pass — good margin</span>'
    if margin >= 0:
        return '<span style="background:#fffbe8;color:#7a5c00;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:600;">⚠ Pass — tight</span>'
    return '<span style="background:#fdf2f2;color:#b91c1c;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:600;">✗ Insufficient</span>'


def action_badge(action: str) -> str:
    if action.startswith("Continue"):
        return f'<span style="background:#e8f5ee;color:#1a6b3c;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:600;">{action}</span>'
    if action.startswith("Divert"):
        return f'<span style="background:#fdf2f2;color:#b91c1c;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:600;">{action}</span>'
    if action.startswith("N/A"):
        return f'<span style="background:#f0f4f8;color:#8fa3b8;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:600;">{action}</span>'
    return f'<span style="background:#fffbe8;color:#7a5c00;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:600;">{action}</span>'


# ---------------------------------------------------------------------------
# PRW-specific helpers
# ---------------------------------------------------------------------------

def class_header_bar(cls: str) -> None:
    colour = CLASS_COLOURS.get(cls, "#8fa3b8")
    label = CLASS_LABELS.get(cls, cls)
    st.markdown(
        f'<div style="border-left:4px solid {colour};padding:8px 12px;'
        f'background:rgba(0,0,0,0.04);border-radius:0 4px 4px 0;margin-bottom:12px;">'
        f'<span style="font-weight:600;color:{colour};">{label}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def feasibility_card(cls: str, status: str, feasible: bool, n_warnings: int) -> None:
    colour = CLASS_COLOURS.get(cls, "#8fa3b8")
    icon = "✓" if feasible else "⚠"
    warn_text = f"{n_warnings} condition{'s' if n_warnings != 1 else ''} flagged"
    st.markdown(
        f'<div style="border:1px solid {colour}33;border-top:3px solid {colour};'
        f'border-radius:4px;padding:14px 16px;background:{colour}0d;">'
        f'<div style="font-size:0.72rem;color:{colour};text-transform:uppercase;'
        f'letter-spacing:0.1em;margin-bottom:6px;">Class {cls}</div>'
        f'<div style="font-size:1rem;font-weight:600;color:{colour};">{icon} {status}</div>'
        f'<div style="font-size:0.8rem;color:#8fa3b8;margin-top:2px;">{warn_text}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )
