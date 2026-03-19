"""
apps/wastewater_app/pages/page_00_version.py

Version & Changelog
====================
Shows the current deployed git commit, release date, and a human-readable
changelog so the user always knows exactly what version is running before
generating reports.
"""
from __future__ import annotations
import subprocess
from pathlib import Path
import streamlit as st
from apps.ui.ui_components import render_page_header

ROOT = Path(__file__).resolve().parents[4]   # repo root

# ── Changelog ─────────────────────────────────────────────────────────────
# Add a new entry here with every bundle that changes user-visible behaviour.
# Format: (version_tag, date, [changes])
CHANGELOG: list[tuple[str, str, list[str]]] = [
    ("v24Z4", "19 Mar 2026", [
        "Compliance labels: 'Compliant with intervention' removed for achievability-note-only scenarios",
        "NEREDA maturity recalibrated 65→72 (100+ global reference plants, AU precedent)",
        "Trade-off in Decision Summary now references compliant runner-up only (not non-compliant options)",
        "Carbon narrative quantifies cost/carbon trade-off with carbon price threshold",
        "QA warnings surfaced in Section 9 conclusions (not just Appendix B)",
    ]),
    ("v24Z3", "19 Mar 2026", [
        "scenario.is_compliant — single source of truth stamped on ScenarioModel after every run",
        "Platform QA layer (core/decision/platform_qa.py) — 8 checks, errors/warnings/notes",
        "Intervention scenarios: ferric dosing for TP failures, methanol for TN failures",
        "Carbon decision pathway: Low-carbon profile re-ranking in every report",
        "Appendix B extended: intervention table + carbon pathway + QA status",
    ]),
    ("v24Z+1", "19 Mar 2026", [
        "Added Version & Changelog page (this page)",
        "Git commit hash shown in sidebar for instant version check",
    ]),
    ("v24Z", "19 Mar 2026", [
        "Driver text now compares preferred vs compliant runner-up (not non-compliant baseline)",
        "Driver correction applied in report_engine — affects PDF, DOCX, and page-3 box",
        "Single compliance source confirmed: all report surfaces use same compliance_flag",
    ]),
    ("v24Y", "19 Mar 2026", [
        "Score clamping 20–85: no more 0/100 binary extremes in Appendix B",
        "Decision Logic table added to Appendix B (compliance → cost → risk → close-decision)",
        "_classify_compliance_inline now reads pre-computed compliance_flag — single source",
        "Section 9 'Both scenarios achieve...' now dynamic based on compliant count",
        "Decision Summary box driven by scoring_result (single source of truth)",
    ]),
    ("v24X", "19 Mar 2026", [
        "Section 9 text: 'Both scenarios' → dynamic count of compliant options",
        "Decision Summary box overridden by scoring_result for all output formats",
        "Driver direction corrected",
    ]),
    ("v24W", "19 Mar 2026", [
        "Streamlit auto-restart on file change — app reloads automatically after git push",
        "No more stale-code reports from forgetting to restart",
    ]),
    ("v24V", "18 Mar 2026", [
        "Achievability warnings no longer block compliance recommendation",
        "Executive summary conclusion uses scoring_result preferred option",
        "Scenarios Evaluated table now populated with technology name and key characteristic",
        "Runner-up in Decision Summary prefers compliant options over non-compliant",
    ]),
    ("v24U", "18 Mar 2026", [
        "Fixed is_rec star (★) in executive summary — now compares by tech code not display label",
    ]),
    ("v24T", "18 Mar 2026", [
        "Fixed comprehensive PDF crash: TableStyle tuple error in Appendix B",
        "Removed Streamlit import from report_engine compliance check",
        "Scoring result now correctly populates in all reports",
    ]),
    ("v24S", "18 Mar 2026", [
        "Effluent Headroom removed from score table display (always zero — biological models target exactly)",
        "Rationale bullets now show raw advantage not normalised score",
        "Low-score disclosure: options scoring < 30/100 get an explanatory note",
        "Tied criteria note now shows full criterion list (no truncation)",
    ]),
    ("v24Q", "18 Mar 2026", [
        "Correlation detection suppressed for 2-scenario comparisons (eliminates 36 spurious warnings)",
        "binary_comparison flag added — recommendation notes that scores are field-relative",
        "Below-uncertainty escalation at 60%: CAUTION level added above Note level",
    ]),
    ("v24P", "18 Mar 2026", [
        "Uncertainty note decoupled from tied_criteria — now uses below_uncertainty correctly",
        "Recommendation restructured: decision / indistinguishable criteria / caveats",
        "weight_profile_name added to recommendation narrative",
        "Low-carbon profile carbon×implementation_risk anti-correlation documented",
    ]),
]


def _git_info() -> tuple[str, str, str]:
    """Return (short_hash, full_hash, commit_datetime). Returns '?' on failure."""
    try:
        short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        full = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        dt = subprocess.check_output(
            ["git", "log", "-1", "--format=%cd", "--date=format:%d %b %Y %H:%M"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        return short, full, dt
    except Exception:
        return "?", "?", "?"


def _latest_tag() -> str:
    if CHANGELOG:
        return CHANGELOG[0][0]
    return "?"


def render() -> None:
    render_page_header(
        "🔖 Version & Changelog",
        subtitle="What's currently deployed — check this before generating reports",
    )

    short_hash, full_hash, commit_dt = _git_info()
    latest_tag = _latest_tag()

    # ── Current version banner ─────────────────────────────────────────────
    st.success(
        f"**Running: {latest_tag}** · commit `{short_hash}` · deployed {commit_dt}"
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Release tag", latest_tag)
    col2.metric("Git commit", f"`{short_hash}`")
    col3.metric("Deployed", commit_dt.split(" ")[0] + " " + commit_dt.split(" ")[1]
                if commit_dt != "?" else "?")

    # ── How to verify ─────────────────────────────────────────────────────
    with st.expander("How to verify you're on the latest version", expanded=False):
        st.markdown(f"""
**1. Compare this commit hash to your local repo:**
```
cd ~/wp_new
git log --oneline -1
```
The 7-character hash should match **`{short_hash}`**.

**2. Check the sidebar** — the commit hash is shown at the bottom of the left sidebar on every page.

**3. After pushing a new bundle**, the app restarts automatically (v24W+).
Wait 3–5 seconds, then reload this page. The hash will update.

**Full commit hash:** `{full_hash}`
""")

    st.divider()

    # ── Changelog ─────────────────────────────────────────────────────────
    st.subheader("Changelog")

    for i, (tag, date, changes) in enumerate(CHANGELOG):
        is_latest = (i == 0)
        label = f"{'🟢 ' if is_latest else ''}{tag} — {date}{'  ← current' if is_latest else ''}"
        with st.expander(label, expanded=is_latest):
            for change in changes:
                st.markdown(f"- {change}")
