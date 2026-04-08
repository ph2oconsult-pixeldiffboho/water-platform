"""
AquaPoint UI Helpers & Shared Components
"""
import streamlit as st


def risk_badge(label: str) -> str:
    """Return coloured HTML badge for risk level."""
    colour_map = {
        "Low": "#2ecc71",
        "Medium": "#f39c12",
        "High": "#e74c3c",
    }
    colour = colour_map.get(label, "#95a5a6")
    return f'<span style="background:{colour};color:white;padding:2px 8px;border-radius:4px;font-size:0.8rem;font-weight:600">{label}</span>'


def compliance_badge(compliant: bool) -> str:
    if compliant:
        return '<span style="background:#2ecc71;color:white;padding:2px 8px;border-radius:4px;font-size:0.8rem">✓ Compliant</span>'
    return '<span style="background:#e74c3c;color:white;padding:2px 8px;border-radius:4px;font-size:0.8rem">✗ Exceedance</span>'


def format_currency(value: float, decimals: int = 0) -> str:
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value/1_000:.1f}k"
    return f"${value:.{decimals}f}"


def score_colour(score: float) -> str:
    if score >= 75:
        return "#2ecc71"
    elif score >= 50:
        return "#f39c12"
    return "#e74c3c"


def render_mca_gauge(score: float, label: str = "Overall Score") -> None:
    """Render a simple score gauge using Streamlit metric + progress."""
    colour = score_colour(score)
    st.markdown(f"""
        <div style="text-align:center; padding:1rem; background:#1a2332; border-radius:8px; border:1px solid #2a3a52">
            <div style="font-size:0.85rem; color:#8899aa; margin-bottom:0.3rem">{label}</div>
            <div style="font-size:2.5rem; font-weight:700; color:{colour}">{score:.0f}</div>
            <div style="font-size:0.75rem; color:#8899aa">/ 100</div>
        </div>
    """, unsafe_allow_html=True)


def render_kpi_card(label: str, value: str, unit: str = "", delta: str = "") -> None:
    """Render a simple KPI card."""
    st.markdown(f"""
        <div style="padding:0.8rem 1rem; background:#1a2332; border-radius:8px;
                    border:1px solid #2a3a52; margin-bottom:0.5rem">
            <div style="font-size:0.75rem; color:#8899aa; text-transform:uppercase;
                        letter-spacing:0.05em">{label}</div>
            <div style="font-size:1.4rem; font-weight:700; color:#e8f4fd;
                        margin-top:0.2rem">{value}
                <span style="font-size:0.8rem; color:#8899aa">{unit}</span>
            </div>
            {f'<div style="font-size:0.75rem;color:#8899aa;margin-top:0.2rem">{delta}</div>' if delta else ''}
        </div>
    """, unsafe_allow_html=True)


def section_header(title: str, icon: str = "●") -> None:
    st.markdown(f"""
        <div style="display:flex;align-items:center;gap:0.6rem;margin:1.2rem 0 0.8rem 0">
            <span style="color:#4a9eff;font-size:1rem">{icon}</span>
            <span style="font-size:1rem;font-weight:600;color:#e8f4fd;letter-spacing:0.01em">{title}</span>
        </div>
    """, unsafe_allow_html=True)


def warning_box(message: str) -> None:
    st.markdown(f"""
        <div style="background:#2d1f0e;border-left:3px solid #f39c12;padding:0.6rem 1rem;
                    border-radius:0 6px 6px 0;margin:0.5rem 0;font-size:0.85rem;color:#f39c12">
            ⚠ {message}
        </div>
    """, unsafe_allow_html=True)


def info_box(message: str) -> None:
    st.markdown(f"""
        <div style="background:#0e1e2d;border-left:3px solid #4a9eff;padding:0.6rem 1rem;
                    border-radius:0 6px 6px 0;margin:0.5rem 0;font-size:0.85rem;color:#89b4e8">
            ℹ {message}
        </div>
    """, unsafe_allow_html=True)


def success_box(message: str) -> None:
    st.markdown(f"""
        <div style="background:#0e2d1a;border-left:3px solid #2ecc71;padding:0.6rem 1rem;
                    border-radius:0 6px 6px 0;margin:0.5rem 0;font-size:0.85rem;color:#2ecc71">
            ✓ {message}
        </div>
    """, unsafe_allow_html=True)


def error_box(message: str) -> None:
    st.markdown(f"""
        <div style="background:#2d0e0e;border-left:3px solid #e74c3c;padding:0.6rem 1rem;
                    border-radius:0 6px 6px 0;margin:0.5rem 0;font-size:0.85rem;color:#e74c3c">
            ✗ {message}
        </div>
    """, unsafe_allow_html=True)
