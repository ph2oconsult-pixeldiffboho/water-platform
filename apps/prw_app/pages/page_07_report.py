"""page_07_report.py"""
import streamlit as st
from datetime import datetime
from ..ui_helpers import section_header, success_box, info_box
from ..engine import CLASS_LABELS, CHEMICAL_GROUPS


def render_report():
    result = st.session_state.get("purepoint_result")
    if result is None:
        st.warning("No assessment results found. Please complete Effluent Quality and run the assessment.")
        return

    st.markdown("## Report")
    st.markdown("Full assessment report in markdown format. Download or copy for documentation purposes.")

    info_box(
        "This report is generated from the current PurePoint session. "
        "Re-run the assessment if inputs have changed before exporting."
    )

    report_md = _build_report(result)

    st.download_button(
        label="⬇ Download report (.md)",
        data=report_md,
        file_name=_report_filename(result),
        mime="text/markdown",
        type="primary",
    )

    st.markdown("---")
    section_header("Report preview", "📄")
    st.markdown(report_md)


def _report_filename(result) -> str:
    project = result.inputs.project_name or "purepoint"
    slug = project.lower().replace(" ", "_")[:40]
    ts = datetime.now().strftime("%Y%m%d")
    return f"purepoint_{slug}_{ts}.md"


def _build_report(result) -> str:
    inp = result.inputs
    ts = datetime.now().strftime("%d %B %Y %H:%M")
    classes = list(result.classes.keys())

    lines = []

    # Cover
    lines += [
        f"# PurePoint Assessment Report",
        f"",
        f"**Project:** {inp.project_name or '—'}  ",
        f"**Plant / scheme:** {inp.plant_name or '—'}  ",
        f"**Effluent source:** {inp.effluent_type.upper()}  ",
        f"**Classes assessed:** {', '.join(f'Class {c}' for c in classes)}  ",
        f"**Generated:** {ts}  ",
        f"**Engine:** PurePoint v1.0 — ph2o Consulting  ",
        f"",
        f"---",
        f"",
    ]

    # 1 — Input quality summary
    lines += [
        f"## 1. Input Quality Summary — WaterPoint Effluent",
        f"",
        f"| Parameter | Median | P95 | P99 |",
        f"|---|---|---|---|",
        f"| Turbidity (NTU) | {inp.turb_med} | {inp.turb_p95} | {inp.turb_p99} |",
        f"| TSS (mg/L) | {inp.tss_med} | {inp.tss_p95} | {inp.tss_p99} |",
        f"| DOC (mg/L) | {inp.doc_med} | {inp.doc_p95} | {inp.doc_p99} |",
        f"| UV254 (cm⁻¹) | {inp.uv254_med} | {inp.uv254_p95} | {inp.uv254_p99} |",
        f"| AOC (µg/L) | {inp.aoc} | — | — |",
        f"| NH₃-N (mg/L) | {inp.nh3} | — | — |",
        f"| NO₃-N (mg/L) | {inp.no3} | — | — |",
        f"| E. coli (cfu/100mL) | {int(inp.ecoli_med):,} | {int(inp.ecoli_p95):,} | {int(inp.ecoli_p99):,} |",
        f"| PFAS sum (ng/L) | {inp.pfas} | — | — |",
        f"| Conductivity (µS/cm) | {inp.cond} | — | — |",
        f"| CEC risk | {inp.cec_risk.capitalize()} | — | — |",
        f"| Nitrosamine precursor risk | {inp.nitrosamine_risk.capitalize()} | — | — |",
        f"",
    ]

    # 2 — Governing constraints
    lines += [
        f"## 2. Governing Constraints",
        f"",
    ]
    if result.governing_constraints:
        for c in result.governing_constraints:
            lines.append(f"- {c}")
    else:
        lines.append("No significant governing constraints identified at median conditions.")
    lines.append("")

    # 3 — Class feasibility
    lines += [
        f"## 3. Class Feasibility Overview",
        f"",
        f"| Class | Status | Conditions / Warnings |",
        f"|---|---|---|",
    ]
    for cls, cr in result.classes.items():
        warn_summary = "; ".join(cr.warnings[:2]) if cr.warnings else "None"
        if len(cr.warnings) > 2:
            warn_summary += f" (+{len(cr.warnings) - 2} more)"
        lines.append(f"| Class {cls} | {cr.status} | {warn_summary} |")
    lines.append("")

    # 4 — LRV tables per class
    lines += [
        f"## 4. WaterVal LRV Assessment",
        f"",
    ]
    for cls, cr in result.classes.items():
        lines += [
            f"### Class {cls}",
            f"",
            f"| Barrier | Protozoa | Bacteria | Virus |",
            f"|---|---|---|---|",
        ]
        for b in cr.lrv_barriers:
            lines.append(
                f"| {b['barrier']} | {b['protozoa'] or '—'} | {b['bacteria'] or '—'} | {b['virus'] or '—'} |"
            )
        lines += [
            f"",
            f"| Pathogen | Required LRV | Achieved LRV | Margin | Status |",
            f"|---|---|---|---|---|",
        ]
        for pathogen in ["protozoa", "bacteria", "virus"]:
            req = cr.lrv_required.get(pathogen, 0)
            ach = cr.lrv_achieved.get(pathogen, 0)
            margin = cr.lrv_margin.get(pathogen, 0)
            status = "✓ Pass" if margin >= 0 else "✗ Insufficient"
            margin_str = f"+{margin}" if margin >= 0 else str(margin)
            lines.append(f"| {pathogen.capitalize()} | {req} | {ach} | {margin_str} | {status} |")
        if cr.lrv_penalty_note:
            lines.append(f"")
            lines.append(f"> {cr.lrv_penalty_note}")
        if cr.warnings:
            lines.append(f"")
            lines.append(f"**Conditions:**")
            for w in cr.warnings:
                lines.append(f"- {w}")
        lines.append("")

    # 5 — Treatment trains
    lines += [
        f"## 5. Recommended Treatment Trains",
        f"",
    ]
    for cls, cr in result.classes.items():
        train = cr.train
        steps = " → ".join(train.get("steps", []))
        lines += [
            f"### Class {cls}",
            f"",
            f"**Train:** {steps}",
            f"",
            f"{train.get('note', '')}",
            f"",
        ]
        if train.get("annotations"):
            lines.append("**Design notes:**")
            for ann in train["annotations"]:
                lines.append(f"- {ann}")
            lines.append("")

    # 6 — Chemical matrix
    lines += [
        f"## 6. Chemical Contaminant Matrix",
        f"",
    ]
    for cls, cr in result.classes.items():
        lines += [
            f"### Class {cls}",
            f"",
            f"| Group | Risk | Mechanism | Credit | Surrogate | Residual Risk |",
            f"|---|---|---|---|---|---|",
        ]
        for group in CHEMICAL_GROUPS:
            row = cr.chem_matrix.get(group, {})
            lines.append(
                f"| {group} | {row.get('risk','')} | {row.get('mechanism','')} | "
                f"{row.get('credit','')} | {row.get('surrogate','')} | {row.get('residual_risk','')} |"
            )
        lines.append("")

    # 7 — CCP framework
    lines += [
        f"## 7. CCP and Surrogate Monitoring Framework",
        f"",
        f"| Barrier | Mechanism | CCP Parameter | Operating Envelope | Failure Response |",
        f"|---|---|---|---|---|",
    ]
    for row in result.ccp_table:
        lines.append(
            f"| {row['barrier']} | {row['mechanism']} | {row['ccp']} | "
            f"{row['envelope']} | {row['failure']} |"
        )
    lines.append("")

    # 8 — Failure modes
    lines += [
        f"## 8. Failure Mode Analysis",
        f"",
    ]
    from ..engine import FAILURE_SCENARIOS
    for scenario in FAILURE_SCENARIOS:
        key = scenario["key"]
        lines += [
            f"### {scenario['scenario']}",
            f"",
            f"| Class | LRV Impact | Chemical Protection | Required Action |",
            f"|---|---|---|---|",
        ]
        for cls, cr in result.classes.items():
            fm = cr.failure_modes.get(key, {})
            lines.append(
                f"| Class {cls} | {fm.get('lrv','—')} | {fm.get('chem','—')} | {fm.get('action','—')} |"
            )
        lines.append("")

    # 9 — WaterPoint interface
    lines += [
        f"## 9. WaterPoint Interface — Effluent Quality Sensitivities",
        f"",
        f"| Parameter | Impact | Severity |",
        f"|---|---|---|",
    ]
    for sens in result.wp_sensitivities:
        lines.append(f"| {sens['parameter']} | {sens['impact']} | {sens['severity']} |")
    lines += ["", ""]

    # 10 — Upgrade pathway
    lines += [
        f"## 10. Upgrade Pathway",
        f"",
    ]
    for cls, delta in result.upgrade_deltas.items():
        lines.append(f"- **Class {cls}:** {delta}")
    lines += [
        f"",
        f"> Design for the upgrade pathway from day one. Civil works and pipe routes "
        f"should allow future additions without demolition.",
        f"",
        f"---",
        f"",
        f"*Report generated by PurePoint v1.0 — ph2o Consulting. "
        f"Assessment outputs are decision-support only and do not constitute regulatory approval.*",
    ]

    return "\n".join(lines)
