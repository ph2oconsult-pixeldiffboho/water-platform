"""
core/characteriser/envelope_renderer.py

Render a populated DesignEnvelope to markdown.

The renderer walks the six sections in order, producing a self-contained
markdown document. Charts are referenced by relative path; the markdown
plus the charts directory together form the design memo artefact the
engineer hands to a colleague.

Output discipline
-----------------
- Tables use compact formatting (right-aligned numerics where appropriate)
- Section ordering matches the structure specification (revision 2)
- Insufficient confidence collapses sections 2-4 with explicit notes
- Repeatability is rendered as evidence, not as ranking
- All chart references use forward slashes (renderable on any OS)
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .report import (
    ConditionalParameterStat, DesignEnvelope, Event,
    IntegrityExclusionStat, IntegritySubsetFlag,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_num(v: Optional[float], dp: int = 2) -> str:
    """Format a number with given decimal places, or '—' for None."""
    if v is None:
        return "—"
    try:
        f = float(v)
    except (ValueError, TypeError):
        return "—"
    return f"{f:.{dp}f}"


def _fmt_shift(stat: ConditionalParameterStat) -> str:
    """Format the 'Shift vs overall' column."""
    if stat.shift_direction == "stable" or stat.significance == "None":
        return "stable"
    if stat.shift_magnitude_pct is None:
        return stat.shift_direction
    sign = "+" if stat.shift_magnitude_pct > 0 else ""
    return f"{stat.shift_direction} {sign}{stat.shift_magnitude_pct:.1f}% ({stat.significance})"


def _fmt_event_shift(shift) -> str:
    """Format an event parameter shift (event vs baseline)."""
    if shift.shift_pct is None or shift.shift_significance == "None":
        return "stable"
    sign = "+" if shift.shift_pct > 0 else ""
    return f"{sign}{shift.shift_pct:.1f}% ({shift.shift_significance})"


def _decimals_for_param(param_name: str) -> int:
    """Pick a sensible decimal-place count for a parameter."""
    if "load" in param_name:
        return 0
    if "_to_" in param_name or param_name.endswith(("_to_bod", "_to_tkn", "_to_cod")):
        return 2
    if param_name == "ph":
        return 2
    return 1


def _event_summary_line(event: Event) -> str:
    """
    Generate a one-line natural-language summary of an event.

    Looks at the strongest shifts and emits a descriptive line.
    """
    if not event.parameter_shifts:
        return ""
    # Top three by absolute shift
    sorted_shifts = sorted(event.parameter_shifts,
                                key=lambda s: -abs(s.shift_pct or 0))
    parts = []
    for s in sorted_shifts[:3]:
        if s.shift_significance in ("Strong", "Moderate") and s.shift_pct is not None:
            sign = "up" if s.shift_pct > 0 else "down"
            parts.append(f"{s.parameter} {sign} {abs(s.shift_pct):.0f}%")
    if not parts:
        return "Event detected but parameter shifts are mild (event triggered detection threshold but lacks strong signal)."
    return "Strongest shifts: " + ", ".join(parts) + "."


# ── Section renderers ───────────────────────────────────────────────────────

def _render_section_1(env: DesignEnvelope) -> List[str]:
    """Section 1 — Framing."""
    f = env.framing
    lines: List[str] = []
    lines.append(f"# Design envelope: {f.label}")
    lines.append("")
    period_str = f"{f.period_start} to {f.period_end}" if f.period_start else "period not available"
    n_years_str = f" ({f.n_complete_years:.2f} complete years)" if f.n_complete_years else ""
    lines.append(f"*Generated {env.generation_timestamp} "
                   f"from `{f.dataset_filename}`. "
                   f"Period covered: {period_str}{n_years_str}. "
                   f"{f.n_total_observations} total observations.*")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Framing")
    lines.append("")
    if f.parse_error:
        lines.append(f"**Envelope cannot be produced:** {f.parse_error}")
        lines.append("")
        return lines
    lines.append(f"**What this envelope characterises.** {f.what_characterised}")
    lines.append("")
    lines.append("**Condition specification:**")
    lines.append("")
    cond_list = ", ".join(f"`{k} {v}`" for k, v in f.condition_machine.items())
    lines.append(f"- Machine: {cond_list}")
    lines.append(f"- Plain: {f.condition_plain}")
    lines.append("")
    lines.append(f"**Focus parameters:** {len(f.focus_parameters)} — "
                   + ", ".join(f"`{p}`" for p in f.focus_parameters))
    lines.append("")
    lines.append(f"**Why this framing.** {f.why_framing}")
    lines.append("")
    return lines


def _render_section_2(env: DesignEnvelope, chart_relpath_fn) -> List[str]:
    """Section 2 — Observed envelope (population-level)."""
    p = env.population
    lines: List[str] = []
    lines.append("---")
    lines.append("")
    lines.append("## 2. Observed envelope (population-level)")
    lines.append("")
    # Aggregation-scope disclaimer (Addition A)
    lines.append("**Aggregation-scope note.**")
    lines.append("")
    lines.append(f"> {p.aggregation_scope_note}")
    lines.append("")
    # Sample-size gate
    lines.append(f"**Matching observations:** {p.n_matching} of {p.n_total} "
                   f"({p.matching_pct:.1f}%).")
    lines.append(f"**Sample-size confidence:** {p.sample_confidence}.")
    lines.append(f"*{p.sample_rationale}*")
    lines.append("")

    if p.sample_confidence == "Insufficient":
        lines.append("**Not characterisable from this dataset** because the matching subset "
                       "is too small. The subsequent population-level tables and charts "
                       "cannot be produced. See sections 5 and 6 for integrity and limits.")
        lines.append("")
        return lines

    # Coverage statement
    if p.conditioning_range_note:
        lines.append(f"- {p.conditioning_range_note}")
    if p.period_coverage_note:
        lines.append(f"- {p.period_coverage_note}")
    if p.concentration_note:
        lines.append(f"- {p.concentration_note}")
    lines.append("")

    # Concentration envelope table
    if p.concentration_stats:
        lines.append("### Concentration envelope")
        lines.append("")
        # Decide if integrity column is needed for concentrations
        excl_map = {x.parameter: x for x in p.integrity_exclusions}
        has_excl_in_section = any(s.parameter in excl_map for s in p.concentration_stats)
        if has_excl_in_section:
            lines.append("| Parameter | Overall median | Conditional median | "
                           "Cond. median (excl. flagged) | P5 | P95 | Shift vs overall |")
            lines.append("|---|---:|---:|---:|---:|---:|---|")
            for s in p.concentration_stats:
                dp = _decimals_for_param(s.parameter)
                excl = excl_map.get(s.parameter)
                excl_str = (_fmt_num(excl.conditional_median_excluded, dp)
                              + f" (n−{excl.n_excluded})" if excl else "—")
                lines.append(f"| {s.parameter} | "
                              f"{_fmt_num(s.overall_median, dp)} | "
                              f"{_fmt_num(s.conditional_median, dp)} | "
                              f"{excl_str} | "
                              f"{_fmt_num(s.conditional_p05, dp)} | "
                              f"{_fmt_num(s.conditional_p95, dp)} | "
                              f"{_fmt_shift(s)} |")
        else:
            lines.append("| Parameter | Overall median | Conditional median | "
                           "P5 | P95 | Shift vs overall |")
            lines.append("|---|---:|---:|---:|---:|---|")
            for s in p.concentration_stats:
                dp = _decimals_for_param(s.parameter)
                lines.append(f"| {s.parameter} | "
                              f"{_fmt_num(s.overall_median, dp)} | "
                              f"{_fmt_num(s.conditional_median, dp)} | "
                              f"{_fmt_num(s.conditional_p05, dp)} | "
                              f"{_fmt_num(s.conditional_p95, dp)} | "
                              f"{_fmt_shift(s)} |")
        lines.append("")

    # Load envelope table
    if p.load_stats:
        lines.append("### Load envelope")
        lines.append("")
        excl_map = {x.parameter: x for x in p.integrity_exclusions}
        has_excl = any(s.parameter in excl_map for s in p.load_stats)
        if has_excl:
            lines.append("| Parameter | Overall median (kg/d) | Conditional median | "
                           "Cond. median (excl. flagged) | P5 | P95 | Shift vs overall |")
            lines.append("|---|---:|---:|---:|---:|---:|---|")
            for s in p.load_stats:
                dp = _decimals_for_param(s.parameter)
                excl = excl_map.get(s.parameter)
                excl_str = (_fmt_num(excl.conditional_median_excluded, dp)
                              + f" (n−{excl.n_excluded})" if excl else "—")
                lines.append(f"| {s.parameter} | "
                              f"{_fmt_num(s.overall_median, dp)} | "
                              f"{_fmt_num(s.conditional_median, dp)} | "
                              f"{excl_str} | "
                              f"{_fmt_num(s.conditional_p05, dp)} | "
                              f"{_fmt_num(s.conditional_p95, dp)} | "
                              f"{_fmt_shift(s)} |")
        else:
            lines.append("| Parameter | Overall median (kg/d) | Conditional median | "
                           "P5 | P95 | Shift vs overall |")
            lines.append("|---|---:|---:|---:|---:|---|")
            for s in p.load_stats:
                dp = _decimals_for_param(s.parameter)
                lines.append(f"| {s.parameter} | "
                              f"{_fmt_num(s.overall_median, dp)} | "
                              f"{_fmt_num(s.conditional_median, dp)} | "
                              f"{_fmt_num(s.conditional_p05, dp)} | "
                              f"{_fmt_num(s.conditional_p95, dp)} | "
                              f"{_fmt_shift(s)} |")
        lines.append("")

    # Ratio table (with priority labels — Addition B)
    if p.ratio_stats:
        lines.append("### Key ratios")
        lines.append("")
        if p.ratio_priority_note:
            lines.append(f"*{p.ratio_priority_note}*")
            lines.append("")
        lines.append("| Ratio | Priority | Overall median | Conditional median | Shift |")
        lines.append("|---|---|---:|---:|---|")
        for s in p.ratio_stats:
            dp = _decimals_for_param(s.parameter)
            priority = p.ratio_priority_map.get(s.parameter, "")
            priority_str = f"**{priority}**" if priority == "diagnostic" else priority
            lines.append(f"| {s.parameter} | {priority_str} | "
                          f"{_fmt_num(s.overall_median, dp)} | "
                          f"{_fmt_num(s.conditional_median, dp)} | "
                          f"{_fmt_shift(s)} |")
        lines.append("")

    # Chart references
    if p.heatmap_path:
        lines.append(f"![Figure 2.1 — Correlation heatmap]({chart_relpath_fn(p.heatmap_path)})")
        lines.append("")
        lines.append("*Figure 2.1. Spearman correlation matrix. Coefficients labelled "
                       "where |ρ| ≥ 0.6.*")
        lines.append("")
    if p.scatters_path:
        lines.append(f"![Figure 2.2 — Pairwise scatters]({chart_relpath_fn(p.scatters_path)})")
        lines.append("")
        lines.append(f"*Figure 2.2. Pairwise relationships where |ρ| ≥ 0.6 "
                       f"({p.scatters_pair_count} pairs shown). Matched subset highlighted "
                       f"in red. Pairs marked 'expected coupling' are mathematically "
                       f"structural relationships.*")
        lines.append("")
    return lines


def _render_section_3(env: DesignEnvelope, chart_relpath_fn) -> List[str]:
    """Section 3 — Observed events."""
    e = env.events
    lines: List[str] = []
    lines.append("---")
    lines.append("")
    lines.append("## 3. Observed events (event-level)")
    lines.append("")

    if not e.events:
        lines.append(f"*{e.no_events_note}*")
        lines.append("")
        # Still render the time series if available — useful for context
        if e.time_series_path:
            lines.append(f"![Figure 3.1 — Time series]({chart_relpath_fn(e.time_series_path)})")
            lines.append("")
            lines.append("*Figure 3.1. Focus parameters across the record. "
                           "No events of relevant type were detected.*")
            lines.append("")
        return lines

    # Event inventory
    lines.append(f"**Events of relevant type within the matched subset:** {len(e.events)}.")
    lines.append("")
    lines.append("| ID | Type | Start | End | Days | Peak date | Repeatability | Confidence |")
    lines.append("|---|---|---|---|---:|---|---|---|")
    for ev in e.events:
        rep = e.repeatability_notes.get(ev.event_id, "—")
        # Shorten the repeatability for the table
        rep_short = rep.split(".")[0]    # take only the first sentence
        if len(rep_short) > 50:
            rep_short = rep_short[:50] + "..."
        lines.append(f"| {ev.event_id} | {ev.event_type} | {ev.start_date} | {ev.end_date} | "
                       f"{ev.duration_days} | {ev.peak_date or '—'} | "
                       f"{rep_short} | {ev.confidence} |")
    lines.append("")

    # Time series chart
    if e.time_series_path:
        lines.append(f"![Figure 3.1 — Time series with events]({chart_relpath_fn(e.time_series_path)})")
        lines.append("")
        lines.append("*Figure 3.1. Focus parameters across the record with detected events "
                       "highlighted. Bands shaded by event type; only Strong-confidence events "
                       "are labelled with their event IDs at the top.*")
        lines.append("")

    # Per-event detail blocks for Strong/Acceptable confidence
    detail_events = [ev for ev in e.events if ev.confidence in ("Strong", "Acceptable")]
    if detail_events:
        lines.append("### Event detail")
        lines.append("")
        for ev in detail_events:
            lines.append(f"#### {ev.event_id}: {ev.event_type} — "
                           f"{ev.start_date} to {ev.end_date} ({ev.duration_days} days)")
            lines.append("")
            lines.append(f"- **Detection rule:** {ev.detection_rule}")
            lines.append(f"- **Confidence:** {ev.confidence}. *{ev.confidence_rationale}*")
            if ev.baseline:
                lines.append(f"- **Baseline:** preceding 30 days "
                               f"({ev.baseline.window_start} to {ev.baseline.window_end}), "
                               f"{ev.baseline.n_samples} samples")
            if ev.antecedent_context:
                lines.append(f"- **Antecedent context:** {ev.antecedent_context}")
            for note in ev.notes:
                if "Co-occurring" in note:
                    lines.append(f"- **{note}**")
                else:
                    lines.append(f"- {note}")
            rep = e.repeatability_notes.get(ev.event_id, "")
            if rep:
                lines.append(f"- **Repeatability:** {rep} *(evidence-of-recurrence indicator, "
                               "not a ranking of importance)*")
            lines.append("")

            # Parameter shifts table
            if ev.parameter_shifts:
                lines.append("| Parameter | Event median | Event peak (date) | "
                               "Baseline median | Shift |")
                lines.append("|---|---:|---:|---:|---|")
                # Sort by absolute shift
                sorted_shifts = sorted(ev.parameter_shifts,
                                            key=lambda s: -abs(s.shift_pct or 0))
                for s in sorted_shifts:
                    dp = _decimals_for_param(s.parameter)
                    peak_str = (f"{_fmt_num(s.event_peak, dp)} ({s.event_peak_date})"
                                  if s.event_peak is not None else "—")
                    lines.append(f"| {s.parameter} | "
                                  f"{_fmt_num(s.event_median, dp)} | "
                                  f"{peak_str} | "
                                  f"{_fmt_num(s.baseline_median, dp)} | "
                                  f"{_fmt_event_shift(s)} |")
                lines.append("")

            # Summary
            summary = _event_summary_line(ev)
            if summary:
                lines.append(f"**Summary.** {summary}")
                lines.append("")

    # Events flagged but not characterised
    limited_events = [ev for ev in e.events if ev.confidence == "Limited"]
    if limited_events:
        lines.append("### Events flagged but not characterised in detail")
        lines.append("")
        lines.append("The following events triggered detection but were not characterised "
                       "because their duration is insufficient for trajectory analysis:")
        lines.append("")
        lines.append("| ID | Type | Date | Most-shifted parameter |")
        lines.append("|---|---|---|---|")
        for ev in limited_events:
            top_shift = ""
            if ev.parameter_shifts:
                sorted_shifts = sorted(ev.parameter_shifts,
                                            key=lambda s: -abs(s.shift_pct or 0))
                if sorted_shifts and sorted_shifts[0].shift_pct is not None:
                    s = sorted_shifts[0]
                    sign = "+" if s.shift_pct > 0 else ""
                    top_shift = f"{s.parameter} {sign}{s.shift_pct:.0f}%"
            lines.append(f"| {ev.event_id} | {ev.event_type} | "
                           f"{ev.start_date} | {top_shift or '—'} |")
        lines.append("")

    return lines


def _render_section_4(env: DesignEnvelope, chart_relpath_fn) -> List[str]:
    """Section 4 — Over-design comparison."""
    o = env.over_design
    lines: List[str] = []
    lines.append("---")
    lines.append("")
    lines.append("## 4. Over-design comparison")
    lines.append("")
    lines.append(o.framing)
    lines.append("")

    if o.comparison and o.comparison.coincident_parameters:
        lines.append(f"**Governing event:** `{o.comparison.governing_parameter}` ≥ "
                       f"P{o.comparison.governing_percentile:.0f} "
                       f"({o.comparison.governing_value:.2f})")
        lines.append("")
        lines.append("| Parameter | Naive P95 | Observed joint median | Δ | Over-design % |")
        lines.append("|---|---:|---:|---:|---:|")
        # Sort by over-design % desc
        rows = []
        for param, (naive, joint) in o.comparison.coincident_parameters.items():
            if naive == 0:
                continue
            pct = 100.0 * (naive - joint) / naive
            rows.append((param, naive, joint, naive - joint, pct))
        rows.sort(key=lambda r: -r[4])
        for param, naive, joint, diff, pct in rows:
            dp = _decimals_for_param(param)
            lines.append(f"| {param} | {_fmt_num(naive, dp)} | "
                          f"{_fmt_num(joint, dp)} | "
                          f"{_fmt_num(diff, dp)} | "
                          f"{pct:+.1f}% |")
        lines.append("")

    if o.over_design_chart_path:
        lines.append(f"![Figure 4.1 — Over-design margin]({chart_relpath_fn(o.over_design_chart_path)})")
        lines.append("")
        lines.append("*Figure 4.1. Over-design margin by parameter. Positive values "
                       "indicate over-design by naive stacking (parameters that dilute "
                       "or stay stable under the condition); negative values indicate "
                       "the joint median exceeds naive P95 (parameters that elevate under "
                       "the condition, where naive stacking may under-design).*")
        lines.append("")

    return lines


def _render_section_5(env: DesignEnvelope) -> List[str]:
    """Section 5 — Integrity."""
    i = env.integrity
    lines: List[str] = []
    lines.append("---")
    lines.append("")
    lines.append("## 5. Integrity check on the matched subset")
    lines.append("")
    if i.is_clean:
        lines.append(i.clean_message)
        lines.append("")
        return lines
    lines.append("The following integrity flags affect rows within the matched subset. "
                   "Numbers in sections 2 through 4 may be biased. See section 2 for "
                   "secondary medians computed with flagged rows excluded.")
    lines.append("")
    lines.append("| Flag | Severity | Parameter | Rows in subset | First dates affected | Effect on envelope |")
    lines.append("|---|---|---|---:|---|---|")
    for flag in i.flags_affecting_subset:
        dates_short = ", ".join(flag.dates_affected[:5])
        if len(flag.dates_affected) > 5:
            dates_short += f", ... ({len(flag.dates_affected)} total)"
        lines.append(f"| {flag.rule_id} | {flag.severity} | {flag.parameter} | "
                       f"{flag.n_rows_affected} | {dates_short} | "
                       f"{flag.effect_on_envelope} |")
    lines.append("")
    return lines


def _render_section_6(env: DesignEnvelope) -> List[str]:
    """Section 6 — Limits."""
    l = env.limits
    lines: List[str] = []
    lines.append("---")
    lines.append("")
    lines.append("## 6. Limits of this envelope")
    lines.append("")
    lines.append("**Period covered.**")
    lines.append("")
    lines.append(f"> {l.period_statement}")
    lines.append("")
    if l.under_represented:
        lines.append("**What's likely under-represented:**")
        lines.append("")
        for item in l.under_represented:
            lines.append(f"- {item}")
        lines.append("")
    if l.does_not_address:
        lines.append("**What this envelope does not address:**")
        lines.append("")
        for item in l.does_not_address:
            lines.append(f"- {item}")
        lines.append("")
    if l.recommended_steps:
        lines.append("**Recommended next steps for the engineer using this envelope:**")
        lines.append("")
        for item in l.recommended_steps:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*End of envelope. All numbers traceable to dates listed in sections 2 and 3.*")
    return lines


# ── Public API ───────────────────────────────────────────────────────────────

def render_envelope_markdown(envelope: DesignEnvelope,
                                  markdown_path: str) -> str:
    """
    Render the envelope as a markdown file at the given path.

    Charts are referenced by relative path from the markdown file's directory.
    The markdown file should be placed in the same directory as (or a sibling
    of) the charts directory written by envelope_charts.

    Returns the absolute path to the markdown file.
    """
    md_path = Path(markdown_path).resolve()
    md_path.parent.mkdir(parents=True, exist_ok=True)

    # Compute chart relpath function
    charts_dir = Path(envelope.charts_directory).resolve() if envelope.charts_directory else None

    def chart_relpath(chart_relative_str: str) -> str:
        """
        Given a chart path (might be absolute or relative), produce a markdown-
        friendly relative path from the markdown file.
        """
        if charts_dir is None:
            return chart_relative_str
        # Charts directory was stored with absolute path; the stored chart_path
        # is just the filename (or includes the dir name)
        # Normalize: figure out the actual chart file
        chart_filename = Path(chart_relative_str).name
        chart_full = charts_dir / chart_filename
        if not chart_full.exists():
            return chart_relative_str
        try:
            return chart_full.relative_to(md_path.parent).as_posix()
        except ValueError:
            return str(chart_full.as_posix())

    sections: List[List[str]] = [
        _render_section_1(envelope),
        _render_section_2(envelope, chart_relpath),
        _render_section_3(envelope, chart_relpath),
        _render_section_4(envelope, chart_relpath),
        _render_section_5(envelope),
        _render_section_6(envelope),
    ]
    lines: List[str] = []
    for section in sections:
        lines.extend(section)

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(md_path)
