"""
apps/wastewater_app/components/qa_panel.py

Reusable Streamlit component for rendering QA results.
Used on the Results page, Comparison page, and Report page.
"""
from __future__ import annotations
import streamlit as st
from core.qa.qa_model import QAResult, Severity


def render_qa_summary_badge(qa: QAResult, compact: bool = False) -> None:
    """
    Compact badge shown in headers and comparison tables.
    """
    if qa.fail_count > 0:
        st.error(f"❌ QA: {qa.fail_count} critical issue(s)")
    elif qa.warn_count > 0:
        st.warning(f"⚠️ QA: {qa.warn_count} warning(s)")
    else:
        st.success("✅ QA: All checks passed")


def render_qa_panel(qa: QAResult, title: str = "Engineering QA Status",
                    expanded: bool = False) -> None:
    """
    Full QA panel with expandable finding details.
    Used on Results page and Report page.
    """
    icon = qa.status_icon
    label = qa.status_label
    counts = []
    if qa.fail_count: counts.append(f"{qa.fail_count} critical")
    if qa.warn_count: counts.append(f"{qa.warn_count} warning")
    if qa.info_count: counts.append(f"{qa.info_count} info")
    count_str = " | ".join(counts) if counts else "all clear"

    with st.expander(f"{icon} {title} — {count_str}", expanded=expanded or qa.fail_count > 0):

        if not qa.findings:
            st.success("✅ All engineering QA checks passed. No issues found.")
            return

        # Severity summary
        col1, col2, col3 = st.columns(3)
        with col1:
            if qa.fail_count:
                st.metric("❌ Critical", qa.fail_count, help="Export blocked until resolved")
            else:
                st.metric("❌ Critical", 0)
        with col2:
            if qa.warn_count:
                st.metric("⚠️ Warnings", qa.warn_count, help="Export allowed with acknowledgement")
            else:
                st.metric("⚠️ Warnings", 0)
        with col3:
            st.metric("ℹ️ Info", qa.info_count)

        st.divider()

        # List findings by severity
        for sev, label_txt, colour in [
            (Severity.FAIL, "CRITICAL ISSUES — Export Blocked", "#C0392B"),
            (Severity.WARN, "WARNINGS — Review Before Export",  "#E67E22"),
            (Severity.INFO, "INFORMATION",                      "#2980B9"),
        ]:
            group = [f for f in qa.findings if f.severity == sev]
            if not group:
                continue

            st.markdown(f"**{label_txt}**")
            for finding in group:
                with st.container():
                    prefix = f"**[{finding.code}]** " if finding.code else ""
                    scen = f"*({finding.scenario})* " if finding.scenario else ""
                    st.markdown(
                        f"<div style='border-left:4px solid {colour}; "
                        f"padding:8px 12px; margin:4px 0; background:#fafafa'>"
                        f"{finding.icon} {prefix}{scen}{finding.message}"
                        + (f"<br><small>Expected: {finding.expected} | "
                           f"Actual: {finding.actual}</small>"
                           if finding.expected and finding.actual else "")
                        + (f"<br><small>💡 {finding.recommendation}</small>"
                           if finding.recommendation else "")
                        + "</div>",
                        unsafe_allow_html=True
                    )
            st.markdown("")


def render_export_gate(qa: QAResult, warnings_acknowledged: bool = False) -> bool:
    """
    Renders the export gate on the Report page.
    Returns True if export is allowed.
    """
    if qa.fail_count > 0:
        st.error(
            f"❌ **Export blocked** — {qa.fail_count} critical QA issue(s) must be "
            "resolved before this report can be exported."
        )
        render_qa_panel(qa, title="QA Issues Blocking Export", expanded=True)
        return False

    if qa.warn_count > 0:
        st.warning(
            f"⚠️ **{qa.warn_count} QA warning(s)** — export is allowed but review "
            "the findings below before issuing this report."
        )
        render_qa_panel(qa, title="QA Warnings", expanded=False)
        ack = st.checkbox(
            "I have reviewed the QA warnings and accept responsibility for export",
            value=warnings_acknowledged,
            key="qa_warnings_acknowledged"
        )
        return ack

    st.success("✅ QA passed — report is ready for export.")
    return True


def render_input_validation(qa: QAResult) -> None:
    """
    Compact input validation status panel shown on the Inputs page.
    """
    if not qa.findings:
        st.success("✅ All inputs complete and plausible.")
        return

    for sev, bg, border in [
        (Severity.FAIL, "#FDECEA", "#C0392B"),
        (Severity.WARN, "#FEF9E7", "#E67E22"),
        (Severity.INFO, "#EBF5FB", "#2980B9"),
    ]:
        group = [f for f in qa.findings if f.severity == sev]
        for finding in group:
            msg = f"{finding.icon} **[{finding.code}]** {finding.message}"
            if finding.recommendation:
                msg += f"\n\n> 💡 {finding.recommendation}"
            if sev == Severity.FAIL:
                st.error(f"{finding.icon} [{finding.code}] {finding.message}")
            elif sev == Severity.WARN:
                st.warning(f"{finding.icon} [{finding.code}] {finding.message}")
            else:
                st.info(f"{finding.icon} [{finding.code}] {finding.message}")
