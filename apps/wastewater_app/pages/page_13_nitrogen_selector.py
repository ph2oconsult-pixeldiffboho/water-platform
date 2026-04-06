"""
apps/wastewater_app/pages/page_13_nitrogen_selector.py

Shortcut Nitrogen Pathway Selector
====================================
Helps experienced engineers evaluate and select between Nitrite Shunt
and PdNA (Partial Denitrification-Anammox) for advanced nitrogen removal.

Structured as:
  Tab 1 — Overview (summary cards + landing context)
  Tab 2 — Side-by-Side Comparison
  Tab 3 — Decision Guide (active plant-condition selector)
  Tab 4 — Key Risks & Failure Modes
  Tab 5 — Full-Scale Implementation Challenges
  Tab 6 — Engineering Recommendation
"""
from __future__ import annotations
import streamlit as st
from apps.ui.ui_components import render_page_header

# ── Content data (single source of truth) ─────────────────────────────────────

FEATURE = {
    "title": "Shortcut Nitrogen Pathway Selector",
    "subtitle": "Nitrite Shunt vs PdNA — operational decision support for advanced nitrogen removal",
    "landing_intro": (
        "Shortcut nitrogen pathways offer significant reductions in aeration energy and carbon "
        "demand — but only under the right plant conditions. This module compares Nitrite Shunt "
        "and Partial Denitrification-Anammox (PdNA), cuts through the theory, and gives you a "
        "clear basis for selection based on your influent characteristics, temperature regime, "
        "and compliance obligations."
    ),
}

CARDS = [
    {
        "title": "Nitrite Shunt",
        "tag": "Kinetic Control System",
        "icon": "⚡",
        "colour": "#1b4f7a",
        "body": (
            "Stops the nitrogen cycle at nitrite — skipping conversion to nitrate. "
            "The lock is biological: NOB suppression must be maintained continuously. "
            "Any lapse in DO control, SRT management, or temperature stability lets "
            "NOBs recover and the shortcut collapses."
        ),
        "stats": {"Aeration saving": "~25%", "Carbon saving": "~40%"},
        "best": ["Warm climates (>15°C)", "Existing sensor infrastructure",
                 "Strong process control capability"],
    },
    {
        "title": "PdNA",
        "tag": "Stoichiometric Control System",
        "icon": "🔬",
        "colour": "#0e5c48",
        "body": (
            "Two-stage shortcut: partial denitrification reduces nitrate to nitrite, "
            "then Anammox bacteria remove remaining ammonia and nitrite together. "
            "The lever is carbon dosing precision — too little stalls the reaction, "
            "too much bypasses Anammox entirely. Biomass protection is non-negotiable."
        ),
        "stats": {"Aeration saving": "50–60%", "Carbon saving": "up to 80%"},
        "best": ["Low-carbon influent", "Strict TN limits (< 5 mg/L)",
                 "Cold operating temperatures", "IFAS, MBBR, or MABR capability"],
    },
    {
        "title": "Full-Scale Reality",
        "tag": "What Actually Happens",
        "icon": "🏭",
        "colour": "#4a2c00",
        "body": (
            "Success depends far more on primary treatment performance, hydraulic stability, "
            "and control system reliability than on the biology alone. Nitrite Shunt is more "
            "proven in sidestream and warm high-rate systems. PdNA is emerging as the standard "
            "for mainstream shortcut removal where strict TN compliance is required — but "
            "Anammox washout during hydraulic surges is catastrophic and recovery takes months."
        ),
        "insight": (
            "Neither pathway tolerates a poor primary treatment process "
            "or an unreliable automation system."
        ),
    },
]

COMPARISON = {
    "Nitrite Shunt": {
        "How it works": "Suppresses NOB to halt nitrogen cycle at nitrite, bypassing nitrate formation",
        "Control mechanism": "Biological competition — DO, SRT, and temperature manipulation",
        "Main benefit": "Proven in high-rate systems; ~25% aeration saving; simpler biomass management",
        "Main weakness": "NOB adaptation is a continuous threat; unstable below 15°C in mainstream",
        "Best application": "Warm-climate plants with strong automation and existing control infrastructure",
    },
    "PdNA": {
        "How it works": "Controlled partial denitrification to nitrite, followed by Anammox co-removal of ammonia and nitrite",
        "Control mechanism": "COD:NO₃ ratio dosing — target 2.4–3.0 gCOD/gNO₃-N",
        "Main benefit": "Up to 80% carbon saving; more robust in cold, low-carbon conditions; higher TN removal potential",
        "Main weakness": "Anammox washout slow to recover; carbon overdosing causes full denitrification",
        "Best application": "Low-carbon influent, strict TN limits, cold climates, plants with fixed-film or MABR capability",
    },
}

DECISION_GUIDE = {
    "Nitrite Shunt": {
        "icon": "⚡",
        "colour": "#1b4f7a",
        "conditions": [
            "Operating temperature consistently above 15°C",
            "Influent has reasonable biodegradable COD and existing EBPR or denitrification is functional",
            "Plant has reliable online nitrite and ammonia monitoring already in place",
            "Compliance target is TN reduction but not extreme low-end (not sub-5 mg/L TN)",
            "Priority is energy saving on an existing biological system without major civil works",
        ],
    },
    "PdNA": {
        "icon": "🔬",
        "colour": "#0e5c48",
        "conditions": [
            "Influent COD:N is low and external carbon is already in use or planned",
            "Operating temperatures fall below 15°C for significant periods of the year",
            "Compliance requires very low TN — typically below 5 mg/L",
            "Plant has or can install IFAS, MBBR, or MABR for Anammox biomass retention",
            "Long-term process confidence matters more than avoiding upfront complexity",
        ],
    },
}

# Active decision guide questions
DECISION_QUESTIONS = [
    {
        "key": "temperature",
        "question": "What is your operating temperature range?",
        "options": ["Consistently above 15°C", "Mixed — seasonal variation", "Frequently below 15°C"],
        "weights": {"Nitrite Shunt": [2, 0, -2], "PdNA": [-1, 1, 2]},
    },
    {
        "key": "tn_target",
        "question": "What is your TN compliance target?",
        "options": ["TN > 8 mg/L (moderate)", "TN 5–8 mg/L", "TN < 5 mg/L (strict)"],
        "weights": {"Nitrite Shunt": [2, 1, -1], "PdNA": [-1, 1, 2]},
    },
    {
        "key": "cod_n",
        "question": "What is your influent COD:N ratio?",
        "options": ["High (> 10:1)", "Moderate (6–10:1)", "Low (< 6:1)"],
        "weights": {"Nitrite Shunt": [1, 1, -1], "PdNA": [-1, 0, 2]},
    },
    {
        "key": "biofilm",
        "question": "Do you have or can you install fixed-film / MABR capability?",
        "options": ["Yes — already have IFAS/MBBR/MABR", "Possible — could be retrofitted", "No — suspended growth only"],
        "weights": {"Nitrite Shunt": [0, 0, 1], "PdNA": [2, 1, -2]},
    },
    {
        "key": "sensors",
        "question": "What is your online monitoring capability?",
        "options": ["Advanced — NH₄, NO₂, NO₃ online analysers", "Basic — NH₄ online only", "Limited — grab samples only"],
        "weights": {"Nitrite Shunt": [2, 0, -2], "PdNA": [1, 0, -1]},
    },
]

RISKS = [
    {
        "title": "NOB Adaptation",
        "icon": "⚠️",
        "severity": "High",
        "colour": "#8b0000",
        "impact": "Nitrite shunt collapses as NOBs recover — nitrate formation returns and energy savings are lost",
        "mitigation": "Transient anoxia, intermittent aeration, rigorous SRT and DO control. Treat NOB suppression as ongoing operational discipline, not a commissioning task.",
        "affects": "Nitrite Shunt",
    },
    {
        "title": "Anammox Washout",
        "icon": "⚠️",
        "severity": "Critical",
        "colour": "#5a0000",
        "impact": "Hydraulic surge strips slow-growing Anammox from the reactor — recovery takes 3–6 months with full compliance impact",
        "mitigation": "Fixed-film retention (IFAS, MBBR, or MABR) is non-negotiable. Do not operate PdNA in a suspended-growth-only system.",
        "affects": "PdNA",
    },
    {
        "title": "Carbon Overdosing",
        "icon": "⚠️",
        "severity": "High",
        "colour": "#7a4200",
        "impact": "Excess external carbon drives complete denitrification, bypassing Anammox and undermining TN removal",
        "mitigation": "Feed-forward dosing control linked to real-time nitrate and COD measurement. Calibrate COD:NO₃ setpoint before full-scale operation.",
        "affects": "PdNA",
    },
    {
        "title": "Sensor Drift & Control Failure",
        "icon": "⚠️",
        "severity": "High",
        "colour": "#2c0a6e",
        "impact": "Drift in nitrite, nitrate, or ammonia probes causes control logic to operate on incorrect assumptions — compounds rapidly",
        "mitigation": "Redundant online analysers, regular calibration against grab samples, alarm thresholds tied to effluent quality trends not just sensor values.",
        "affects": "Both",
    },
]

SCALE_CHALLENGES = [
    {
        "title": "NOB Seeding from Influent",
        "icon": "🔄",
        "body": (
            "NOB are continuously introduced via incoming wastewater. Unlike sidestream systems "
            "where biomass can be more tightly managed, mainstream operation faces constant "
            "reinoculation pressure. Kinetic suppression must outpace continuous seeding — the "
            "fundamental reason full-scale mainstream Nitrite Shunt remains difficult to sustain."
        ),
    },
    {
        "title": "Hydraulic Washout of Anammox",
        "icon": "💧",
        "body": (
            "Anammox bacteria have doubling times measured in weeks, not hours. A single "
            "high-flow event that exceeds hydraulic retention capacity can eliminate months "
            "of biomass accumulation. Physical retention is not an optional upgrade — it is "
            "the design foundation that determines whether PdNA is operationally credible at "
            "full scale."
        ),
    },
    {
        "title": "Automation & Sensor Reliability",
        "icon": "📡",
        "body": (
            "Both pathways shift the operational burden from managing flows to managing data. "
            "Control logic that works in a pilot degrades under full-scale variability — "
            "diurnal load swings, storm events, and industrial discharges all create edge "
            "cases the control system must handle, not the operator. Sensor drift undetected "
            "for 24–48 hours can cause irreversible biomass or compliance damage."
        ),
    },
]

RECOMMENDATION = (
    "For most full-scale mainstream applications where strict TN compliance is the primary "
    "obligation, **PdNA is the more robust long-term pathway** — provided biomass retention "
    "is treated as a hard engineering constraint from the outset, not an add-on. "
    "Nitrite Shunt is viable for warm-climate plants with existing control infrastructure "
    "and moderate TN targets, but requires continuous vigilance to prevent NOB recovery. "
    "Neither pathway tolerates a poor primary treatment process or an unreliable automation "
    "system. **Get those right first.**"
)


# ── Render helpers ─────────────────────────────────────────────────────────────

def _severity_badge(severity: str, colour: str) -> str:
    return f'<span style="background:{colour};color:white;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700">{severity}</span>'


def _tag_badge(tag: str, colour: str) -> str:
    return f'<span style="background:{colour};color:white;padding:2px 10px;border-radius:12px;font-size:0.75rem;font-weight:600;letter-spacing:0.03em">{tag}</span>'


def _render_tab_overview() -> None:
    st.markdown(f"### {FEATURE['subtitle']}")
    st.markdown(FEATURE["landing_intro"])
    st.divider()

    cols = st.columns(3)
    for i, card in enumerate(CARDS):
        with cols[i]:
            colour = card["colour"]
            icon   = card["icon"]
            title  = card["title"]
            tag    = card["tag"]
            st.markdown(
                f"<div style='border-left:4px solid {colour};padding:0 0 0 12px;margin-bottom:8px'>"
                f"<span style='font-size:1.4rem'>{icon}</span> "
                f"<strong style='font-size:1rem'>{title}</strong></div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                _tag_badge(tag, colour),
                unsafe_allow_html=True,
            )
            st.markdown("")
            st.markdown(card["body"])

            if "stats" in card:
                stat_cols = st.columns(2)
                for j, (k, v) in enumerate(card["stats"].items()):
                    with stat_cols[j]:
                        st.metric(k, v)
                for b in card.get("best", []):
                    st.markdown(f"✔ {b}")

            if "insight" in card:
                st.info(f"**Key insight:** {card['insight']}")


def _render_tab_comparison() -> None:
    st.markdown("#### Side-by-Side Comparison")
    st.caption("Five dimensions that drive selection at full scale.")
    st.markdown("")

    rows = list(next(iter(COMPARISON.values())).keys())
    for row in rows:
        st.markdown(f"**{row}**")
        cols = st.columns(2)
        for i, (tech, fields) in enumerate(COMPARISON.items()):
            with cols[i]:
                colour = CARDS[i]["colour"]
                st.markdown(
                    f"<div style='border-left:3px solid {colour};padding:4px 10px;"
                    f"background:#f8f9fa;border-radius:4px;margin-bottom:4px'>"
                    f"<small style='color:{colour};font-weight:700'>{tech}</small><br>"
                    f"{fields[row]}</div>",
                    unsafe_allow_html=True,
                )
        st.markdown("")


def _render_tab_decision() -> None:
    st.markdown("#### Which Pathway Fits Your Plant?")
    st.caption(
        "Answer five questions about your operating conditions. "
        "The selector weights your answers and recommends a pathway."
    )
    st.markdown("")

    scores = {"Nitrite Shunt": 0, "PdNA": 0}
    answered = 0

    for q in DECISION_QUESTIONS:
        choice = st.radio(
            q["question"],
            options=q["options"],
            index=None,
            key=f"dg_{q['key']}",
            horizontal=False,
        )
        if choice is not None:
            idx = q["options"].index(choice)
            for tech in scores:
                scores[tech] += q["weights"][tech][idx]
            answered += 1
        st.markdown("")

    st.divider()

    if answered == 0:
        st.info("Answer the questions above to get a pathway recommendation.")
        return

    # Show partial results if not all answered
    ns = scores["Nitrite Shunt"]
    pd_ = scores["PdNA"]
    total = ns + pd_
    ns_pct = int((ns / total * 100) if total > 0 else 50)
    pd_pct = 100 - ns_pct

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"<div style='border:2px solid {'#1b4f7a' if ns >= pd_ else '#ddd'};"
            f"border-radius:8px;padding:16px;text-align:center'>"
            f"<div style='font-size:2rem'>⚡</div>"
            f"<strong>Nitrite Shunt</strong><br>"
            f"<span style='font-size:1.8rem;color:#1b4f7a;font-weight:700'>{ns_pct}%</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div style='border:2px solid {'#0e5c48' if pd_ > ns else '#ddd'};"
            f"border-radius:8px;padding:16px;text-align:center'>"
            f"<div style='font-size:2rem'>🔬</div>"
            f"<strong>PdNA</strong><br>"
            f"<span style='font-size:1.8rem;color:#0e5c48;font-weight:700'>{pd_pct}%</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("")

    if answered < len(DECISION_QUESTIONS):
        st.caption(f"Based on {answered}/{len(DECISION_QUESTIONS)} questions answered — complete all for a full recommendation.")

    if ns > pd_:
        st.success(
            "**Recommendation: Nitrite Shunt** — your operating conditions favour "
            "kinetic NOB suppression. Prioritise DO control, SRT management, and "
            "online nitrite monitoring before commissioning."
        )
    elif pd_ > ns:
        st.success(
            "**Recommendation: PdNA** — your conditions favour the stoichiometric "
            "pathway. Confirm fixed-film biomass retention and calibrate your "
            "COD:NO₃ dosing setpoint before full-scale operation."
        )
    else:
        st.warning(
            "**Borderline — both pathways are plausible.** The deciding factor is "
            "likely your biomass retention capability: if IFAS, MBBR, or MABR is "
            "available, PdNA offers the more robust long-term position."
        )

    st.divider()
    st.markdown("#### Static Criteria Reference")
    st.caption("Use alongside the selector above.")

    col1, col2 = st.columns(2)
    for i, (tech, guide) in enumerate(DECISION_GUIDE.items()):
        with [col1, col2][i]:
            st.markdown(
                f"<div style='border-left:4px solid {guide['colour']};padding:4px 12px;"
                f"margin-bottom:8px'><strong>{guide['icon']} Choose {tech} if…</strong></div>",
                unsafe_allow_html=True,
            )
            for cond in guide["conditions"]:
                st.markdown(f"• {cond}")


def _render_tab_risks() -> None:
    st.markdown("#### Risks & Failure Modes")
    st.caption("Four failure modes that dominate full-scale shortcut nitrogen operation.")
    st.markdown("")

    for risk in RISKS:
        with st.container():
            st.markdown(
                f"<div style='border-left:4px solid {risk['colour']};padding:2px 12px;"
                f"margin-bottom:4px'>"
                f"<strong>{risk['icon']} {risk['title']}</strong> "
                + _severity_badge(risk["severity"], risk["colour"])
                + f"&nbsp;&nbsp;<small style='color:#888'>Affects: {risk['affects']}</small>"
                  f"</div>",
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Impact**")
                st.markdown(risk["impact"])
            with c2:
                st.markdown("**Mitigation**")
                st.markdown(risk["mitigation"])
            st.divider()


def _render_tab_scale() -> None:
    st.markdown("#### Full-Scale Implementation Challenges")
    st.caption(
        "The three constraints that most consistently determine whether a shortcut "
        "pathway succeeds or fails at full scale."
    )
    st.markdown("")

    for ch in SCALE_CHALLENGES:
        st.markdown(f"### {ch['icon']} {ch['title']}")
        st.markdown(ch["body"])
        st.markdown("")

    st.divider()
    st.markdown("#### What Actually Drives Success")
    st.info(
        "Shortcut systems shift the burden from moving more water to managing more data. "
        "The five determinants of full-scale success — in order of importance:\n\n"
        "1. **Primary treatment performance** — primary effluent quality sets the boundary conditions\n"
        "2. **Hydraulic stability** — surges are the primary washout risk\n"
        "3. **Biofilm retention** — non-negotiable for PdNA\n"
        "4. **Sensor reliability** — both pathways depend on precision measurement\n"
        "5. **Operator capability** — control system performance degrades without active management"
    )


def _render_tab_recommendation() -> None:
    st.markdown("#### Engineering Recommendation")
    st.markdown("")

    # Large recommendation block
    st.markdown(
        f"<div style='background:#e8f4ee;border-left:5px solid #0e5c48;"
        f"padding:20px 24px;border-radius:6px;font-size:1.02rem;line-height:1.7'>"
        f"{RECOMMENDATION.replace('**', '<strong>').replace('**', '</strong>')}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("PdNA aeration saving", "50–60%", delta="vs 25% Nitrite Shunt")
    with col2:
        st.metric("PdNA carbon saving", "up to 80%", delta="vs 40% Nitrite Shunt")
    with col3:
        st.metric("Anammox recovery time", "3–6 months", delta="if washout occurs", delta_color="inverse")

    st.divider()
    st.markdown("#### Design Principles — Non-Negotiable")

    principles = [
        ("Biomass retention first",
         "For PdNA: design IFAS, MBBR, or MABR before the biological process. "
         "Anammox retention is not an upgrade — it is the foundation."),
        ("Control before biology",
         "Commission the sensor and automation infrastructure before introducing "
         "the shortcut pathway. If the control system is not reliable, the biology will fail."),
        ("Primary treatment quality",
         "Optimise primary treatment before investing in shortcut nitrogen. "
         "Shortcut pathways amplify the effect of primary effluent variability, "
         "they do not compensate for it."),
        ("NOB suppression is ongoing",
         "Nitrite Shunt is not a set-and-forget system. NOB suppression requires "
         "continuous active management of DO, SRT, and aeration patterns for the "
         "operational life of the plant."),
    ]

    for title, body in principles:
        with st.expander(f"**{title}**", expanded=False):
            st.markdown(body)


# ── Main render ────────────────────────────────────────────────────────────────

def render() -> None:
    render_page_header(
        "⚗️ Shortcut Nitrogen Pathway Selector",
        subtitle="Nitrite Shunt vs PdNA — operational decision support for advanced nitrogen removal",
    )

    tabs = st.tabs([
        "Overview",
        "Comparison",
        "Decision Guide",
        "Key Risks",
        "Scale Challenges",
        "Recommendation",
    ])

    with tabs[0]:
        _render_tab_overview()

    with tabs[1]:
        _render_tab_comparison()

    with tabs[2]:
        _render_tab_decision()

    with tabs[3]:
        _render_tab_risks()

    with tabs[4]:
        _render_tab_scale()

    with tabs[5]:
        _render_tab_recommendation()
