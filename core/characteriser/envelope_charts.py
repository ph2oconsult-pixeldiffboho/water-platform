"""
core/characteriser/envelope_charts.py

Chart rendering for design envelopes (layer 5).

Produces four chart types as PNG files:
  Figure 2.1: Correlation heatmap (Spearman, catchment-wide; matched-subset
              alongside if n ≥ 100)
  Figure 2.2: Pairwise scatters for |ρ| ≥ 0.6 pairs, matched subset highlighted
  Figure 3.1: Full-record time series with detected events highlighted
  Figure 4.1: Over-design margin horizontal bar chart

All figures are saved to a working directory and referenced by path from the
DesignEnvelope. The orchestrator does not call this module directly; the user
calls render_envelope_charts after build_design_envelope.

Design choices
--------------
- matplotlib for static PNG output; no interactivity
- Spearman correlation (handles monotonic non-linearity better than Pearson)
- Heatmap threshold: |ρ| ≥ 0.6 (configurable; coefficients labelled only on
  cells above threshold to reduce clutter)
- Event-type colour palette consistent within an envelope's figures
- All figures cleaned up with plt.close() to avoid memory leaks
- Auto-redundancy rule for scatter pairs (per structure spec):
    * concentration vs derived load: EXCLUDED (arithmetic, not informative)
    * concentration vs component (COD vs sCOD, etc.): INCLUDED with
      "expected coupling" annotation
    * parameter vs itself: EXCLUDED
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")    # headless backend
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from .report import DesignEnvelope


# ── Event-type colour palette ────────────────────────────────────────────────
EVENT_COLOURS: Dict[str, str] = {
    "First-flush":                     "#d4a017",   # gold/amber
    "Septic episode":                  "#8b4513",   # saddle brown
    "Industrial soluble COD":          "#1f77b4",   # blue
    "Low-carbon nitrification stress": "#9467bd",   # purple
    "TP-rich coincident":              "#2ca02c",   # green
    "_default":                        "#7f7f7f",   # grey for unknown
}


# ── Auto-redundancy logic ────────────────────────────────────────────────────

# Component pairs — these are NOT excluded but labelled "expected coupling"
EXPECTED_COUPLING_PAIRS: Set[Tuple[str, str]] = {
    tuple(sorted(p)) for p in [
        ("cod_mg_l", "scod_mg_l"),
        ("cod_mg_l", "rbcod_mg_l"),
        ("scod_mg_l", "rbcod_mg_l"),
        ("tkn_mg_l", "nh4_mg_l"),
        ("tss_mg_l", "vss_mg_l"),
        ("tp_mg_l",  "orthop_mg_l"),
        ("bod_mg_l", "cod_mg_l"),
    ]
}


def _is_concentration_vs_its_load(a: str, b: str) -> bool:
    """
    Check if a-b is a concentration-vs-derived-load pair (arithmetic, excluded).
    Heuristic: BOD vs BOD_load, COD vs COD_load, etc.
    """
    base_a = a.replace("_mg_l", "")
    base_b = b.replace("_load_kg_d", "").replace("_load", "")
    if a.endswith("_mg_l") and b.endswith("_load_kg_d"):
        return base_a == base_b or base_a.startswith(base_b) or base_b.startswith(base_a)
    # Try the other ordering
    base_a2 = a.replace("_load_kg_d", "").replace("_load", "")
    base_b2 = b.replace("_mg_l", "")
    if a.endswith("_load_kg_d") and b.endswith("_mg_l"):
        return base_a2 == base_b2 or base_a2.startswith(base_b2) or base_b2.startswith(base_a2)
    return False


def _is_expected_coupling(a: str, b: str) -> bool:
    """Check if a-b is a known structural component pair."""
    pair = tuple(sorted([a, b]))
    return pair in EXPECTED_COUPLING_PAIRS


def _should_exclude_pair(a: str, b: str) -> bool:
    """Should this pair be excluded from scatter rendering entirely?"""
    if a == b:
        return True
    if _is_concentration_vs_its_load(a, b):
        return True
    return False


# ── Figure 2.1 — Correlation heatmap ─────────────────────────────────────────

def _compute_correlation_matrix(df: pd.DataFrame, parameters: List[str],
                                    method: str = "spearman") -> pd.DataFrame:
    """Compute correlation matrix on the given parameters."""
    avail = [p for p in parameters if p in df.columns
             and pd.api.types.is_numeric_dtype(df[p])]
    if len(avail) < 2:
        return pd.DataFrame()
    return df[avail].corr(method=method)


def _render_heatmap_panel(ax, corr: pd.DataFrame, title: str,
                             threshold: float = 0.6) -> None:
    """Render one heatmap panel onto the given axes."""
    if corr.empty:
        ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center",
                transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title)
        return

    n = len(corr)
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="equal")

    # Label coefficients only on |ρ| ≥ threshold
    for i in range(n):
        for j in range(n):
            v = corr.iloc[i, j]
            if abs(v) >= threshold and i != j:
                colour = "white" if abs(v) > 0.7 else "black"
                ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                        color=colour, fontsize=7)

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(corr.index, fontsize=8)
    ax.set_title(title, fontsize=10)


def render_figure_2_1(df: pd.DataFrame,
                         envelope: DesignEnvelope,
                         output_dir: Path,
                         threshold: float = 0.6) -> Optional[Path]:
    """
    Render Figure 2.1 — correlation heatmap.

    Single panel (catchment-wide) by default. If matched subset has n ≥ 100,
    render two panels side-by-side.
    """
    focus = envelope.framing.focus_parameters
    if len(focus) < 3:
        return None    # heatmap not meaningful with < 3 parameters

    # Catchment-wide correlation
    corr_full = _compute_correlation_matrix(df, focus)
    if corr_full.empty:
        return None

    # Determine if we render two panels or one
    n_matching = envelope.population.n_matching
    render_subset = n_matching >= 100

    if render_subset:
        # Need to recompute mask to get the subset
        from .coincidence import _build_mask
        cond_spec = {k: v for k, v in envelope.framing.condition_machine.items()}
        # Note: condition_machine values are strings; _build_mask handles parsing
        mask, _ = _build_mask(df, cond_spec)
        if mask is not None:
            subset_df = df[mask]
            corr_subset = _compute_correlation_matrix(subset_df, focus)
        else:
            corr_subset = pd.DataFrame()
        n_panels = 2 if not corr_subset.empty else 1
    else:
        n_panels = 1

    fig, axes = plt.subplots(1, n_panels,
                                  figsize=(7 * n_panels, 6),
                                  constrained_layout=True)
    if n_panels == 1:
        axes = [axes]

    _render_heatmap_panel(axes[0], corr_full, "Catchment-wide (all observations)",
                              threshold=threshold)
    if n_panels == 2:
        _render_heatmap_panel(axes[1], corr_subset,
                                  f"Under condition: {envelope.framing.condition_plain}",
                                  threshold=threshold)

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap="RdBu_r",
                                    norm=plt.Normalize(vmin=-1, vmax=1))
    sm.set_array([])
    fig.colorbar(sm, ax=axes, shrink=0.6, label="Spearman ρ")

    fig.suptitle(f"Figure 2.1 — Correlation heatmap "
                   f"(coefficients labelled where |ρ| ≥ {threshold})",
                   fontsize=11)

    output_path = output_dir / "figure_2_1_heatmap.png"
    fig.savefig(output_path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ── Figure 2.2 — Pairwise scatters for |ρ| ≥ 0.6 pairs ───────────────────────

def _find_significant_pairs(corr: pd.DataFrame, threshold: float
                                ) -> List[Tuple[str, str, float]]:
    """
    Find pairs of parameters with |ρ| ≥ threshold, applying auto-redundancy rule.
    Returns list of (param_a, param_b, ρ).
    """
    if corr.empty:
        return []
    params = corr.columns.tolist()
    pairs = []
    for i, a in enumerate(params):
        for b in params[i + 1:]:
            if _should_exclude_pair(a, b):
                continue
            rho = corr.loc[a, b]
            if abs(rho) >= threshold:
                pairs.append((a, b, float(rho)))
    # Sort by absolute correlation descending
    pairs.sort(key=lambda x: -abs(x[2]))
    return pairs


def render_figure_2_2(df: pd.DataFrame,
                         envelope: DesignEnvelope,
                         output_dir: Path,
                         threshold: float = 0.6,
                         max_pairs: int = 12) -> Optional[Path]:
    """
    Render Figure 2.2 — pairwise scatters for |ρ| ≥ threshold pairs.

    Cap at max_pairs to avoid unwieldy figures. Pairs sorted by |ρ| desc.
    """
    focus = envelope.framing.focus_parameters
    corr = _compute_correlation_matrix(df, focus)
    if corr.empty:
        envelope.population.scatters_pair_count = 0
        return None

    pairs = _find_significant_pairs(corr, threshold)
    if not pairs:
        envelope.population.scatters_pair_count = 0
        return None

    # Cap at max_pairs
    if len(pairs) > max_pairs:
        pairs = pairs[:max_pairs]
    envelope.population.scatters_pair_count = len(pairs)

    # Get the matched subset for highlighting
    from .coincidence import _build_mask
    cond_spec = {k: v for k, v in envelope.framing.condition_machine.items()}
    mask, _ = _build_mask(df, cond_spec)
    if mask is None:
        mask = pd.Series([False] * len(df), index=df.index)

    # Grid layout: 3 columns
    n = len(pairs)
    n_cols = min(3, n)
    n_rows = (n + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols,
                                  figsize=(4.5 * n_cols, 3.8 * n_rows),
                                  constrained_layout=True)
    if n == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = axes.reshape(1, -1)
    elif n_cols == 1:
        axes = axes.reshape(-1, 1)

    for idx, (a, b, rho) in enumerate(pairs):
        r, c = idx // n_cols, idx % n_cols
        ax = axes[r, c]

        all_vals = df[[a, b]].dropna()
        subset_vals = df.loc[mask, [a, b]].dropna()

        # Plot all observations as grey
        ax.scatter(all_vals[a], all_vals[b], s=10, c="#cccccc",
                       alpha=0.5, edgecolors="none", label=f"All (n={len(all_vals)})")
        # Highlight matched subset
        if len(subset_vals) > 0:
            ax.scatter(subset_vals[a], subset_vals[b], s=14, c="#d62728",
                           alpha=0.8, edgecolors="none",
                           label=f"Matched (n={len(subset_vals)})")

        ax.set_xlabel(a, fontsize=8)
        ax.set_ylabel(b, fontsize=8)
        ax.tick_params(labelsize=7)

        # Annotations
        annot_text = f"ρ = {rho:+.2f}"
        if _is_expected_coupling(a, b):
            annot_text += "\n(expected coupling)"
        ax.text(0.05, 0.95, annot_text, transform=ax.transAxes,
                    fontsize=8, va="top", ha="left",
                    bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=2))

        ax.legend(loc="lower right", fontsize=7, framealpha=0.9)
        ax.grid(True, alpha=0.2)

    # Hide unused axes
    for idx in range(n, n_rows * n_cols):
        r, c = idx // n_cols, idx % n_cols
        axes[r, c].set_visible(False)

    fig.suptitle(f"Figure 2.2 — Pairwise scatters for |ρ| ≥ {threshold} "
                   f"(matched subset highlighted)", fontsize=11)

    output_path = output_dir / "figure_2_2_scatters.png"
    fig.savefig(output_path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ── Figure 3.1 — Time series with detected events ────────────────────────────

def render_figure_3_1(df: pd.DataFrame,
                         envelope: DesignEnvelope,
                         output_dir: Path,
                         max_panels: int = 6) -> Optional[Path]:
    """
    Render Figure 3.1 — time series with detected events highlighted.

    One panel per focus parameter, stacked vertically. Detected events
    shown as shaded bands coloured by type. Up to max_panels parameters
    rendered (top-priority parameters in focus list).
    """
    if "_date" not in df.columns:
        return None
    focus = envelope.framing.focus_parameters
    if not focus:
        return None

    # Pick which parameters to render — favour key signals
    # Order: flow first, then concentrations, then loads
    panel_order_priority = [
        "flow_mld",
        "bod_mg_l", "cod_mg_l", "tss_mg_l",
        "tkn_mg_l", "nh4_mg_l", "tp_mg_l",
        "rainfall_mm", "temperature_c",
        "bod_load_kg_d", "cod_load_kg_d", "tss_load_kg_d",
    ]
    chosen = [p for p in panel_order_priority if p in focus and p in df.columns]
    if not chosen:
        chosen = [p for p in focus if p in df.columns][:max_panels]
    chosen = chosen[:max_panels]

    if not chosen:
        return None

    df_sorted = df.sort_values("_date").reset_index(drop=True)
    dates = df_sorted["_date"]

    fig, axes = plt.subplots(len(chosen), 1,
                                  figsize=(13, 1.6 * len(chosen)),
                                  sharex=True, constrained_layout=True)
    if len(chosen) == 1:
        axes = [axes]

    for ax, param in zip(axes, chosen):
        vals = df_sorted[param]
        ax.plot(dates, vals, linewidth=0.8, color="#444444")
        ax.set_ylabel(param, fontsize=8, rotation=0, ha="right", va="center")
        ax.tick_params(labelsize=8)
        ax.grid(True, alpha=0.2)

    # Add event bands
    for event in envelope.events.events:
        try:
            start = pd.Timestamp(event.start_date)
            end = pd.Timestamp(event.end_date)
        except (ValueError, TypeError):
            continue
        colour = EVENT_COLOURS.get(event.event_type, EVENT_COLOURS["_default"])
        for ax in axes:
            ax.axvspan(start, end, alpha=0.18, color=colour, zorder=0)

    # Label only Strong-confidence events at the top of the chart (to reduce clutter)
    strong_events = [e for e in envelope.events.events if e.confidence == "Strong"]
    if strong_events:
        # Add a legend strip at the top via the first axis
        top_ax = axes[0]
        for event in strong_events[:8]:  # cap labels
            try:
                start = pd.Timestamp(event.start_date)
                colour = EVENT_COLOURS.get(event.event_type, EVENT_COLOURS["_default"])
                # Annotate with event ID at the top
                ylim = top_ax.get_ylim()
                top_ax.annotate(event.event_id[:12], xy=(start, ylim[1]),
                                  xytext=(0, 2), textcoords="offset points",
                                  fontsize=6, color=colour, ha="left", va="bottom",
                                  rotation=90)
            except (ValueError, TypeError):
                continue

    # Legend for event types
    handles = []
    seen_types = set(e.event_type for e in envelope.events.events)
    for event_type in seen_types:
        colour = EVENT_COLOURS.get(event_type, EVENT_COLOURS["_default"])
        handles.append(Rectangle((0, 0), 1, 1, fc=colour, alpha=0.4,
                                       label=event_type))
    if handles:
        fig.legend(handles=handles, loc="upper right",
                       bbox_to_anchor=(0.99, 1.0), fontsize=8, framealpha=0.95)

    axes[-1].set_xlabel("Date")
    fig.suptitle(f"Figure 3.1 — Focus parameters across the record. "
                    f"Detected events shown as shaded bands.",
                    fontsize=11)

    output_path = output_dir / "figure_3_1_timeseries.png"
    fig.savefig(output_path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ── Figure 4.1 — Over-design margin bar chart ───────────────────────────────

def render_figure_4_1(envelope: DesignEnvelope,
                         output_dir: Path) -> Optional[Path]:
    """
    Render Figure 4.1 — over-design margin horizontal bar chart.
    """
    comparison = envelope.over_design.comparison
    if comparison is None or not comparison.coincident_parameters:
        return None

    # Compute per-parameter over-design percent
    rows = []
    for param, (naive, joint) in comparison.coincident_parameters.items():
        if naive == 0:
            continue
        pct = 100.0 * (naive - joint) / naive
        rows.append((param, pct, naive - joint))
    if not rows:
        return None
    # Sort descending by percent
    rows.sort(key=lambda r: -r[1])

    fig, ax = plt.subplots(figsize=(9, max(3, 0.4 * len(rows) + 1)),
                                constrained_layout=True)

    params = [r[0] for r in rows]
    pcts   = [r[1] for r in rows]
    diffs  = [r[2] for r in rows]

    # Colour: green for over-design avoided, red for negative (rare)
    colors = ["#2ca02c" if p > 0 else "#d62728" for p in pcts]
    y_pos = np.arange(len(params))
    bars = ax.barh(y_pos, pcts, color=colors, alpha=0.85, edgecolor="black", linewidth=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(params, fontsize=9)
    ax.invert_yaxis()    # largest at top
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Over-design margin (%)", fontsize=10)
    ax.grid(True, axis="x", alpha=0.2)

    # Annotate each bar with its percent and absolute Δ
    for bar, pct, diff in zip(bars, pcts, diffs):
        width = bar.get_width()
        label = f"{pct:+.0f}% (Δ {diff:+.1f})"
        x_text = width + (0.5 if width >= 0 else -0.5)
        ax.text(x_text, bar.get_y() + bar.get_height() / 2,
                    label, va="center", fontsize=8,
                    ha="left" if width >= 0 else "right")

    fig.suptitle(f"Figure 4.1 — Over-design margin by parameter\n"
                   f"Governing event: {comparison.governing_parameter} ≥ "
                   f"P{comparison.governing_percentile:.0f}",
                   fontsize=11)

    output_path = output_dir / "figure_4_1_overdesign.png"
    fig.savefig(output_path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ── Public entry point ───────────────────────────────────────────────────────

def render_envelope_charts(df: pd.DataFrame,
                              envelope: DesignEnvelope,
                              output_dir: str,
                              threshold: float = 0.6) -> DesignEnvelope:
    """
    Render all four chart types for an envelope.

    Modifies the envelope in-place, populating chart_path fields on the
    relevant sections. Returns the envelope for chaining.

    output_dir is created if it doesn't exist. Charts are saved as PNGs.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    envelope.charts_directory = str(out.resolve())

    # Skip charts entirely if the envelope is Insufficient
    if envelope.population.sample_confidence == "Insufficient":
        return envelope

    # Figure 2.1 — heatmap
    p = render_figure_2_1(df, envelope, out, threshold=threshold)
    if p is not None:
        envelope.population.heatmap_path = str(p.relative_to(out.parent)) if out.parent != out else p.name

    # Figure 2.2 — scatters
    p = render_figure_2_2(df, envelope, out, threshold=threshold)
    if p is not None:
        envelope.population.scatters_path = str(p.relative_to(out.parent)) if out.parent != out else p.name

    # Figure 3.1 — time series
    p = render_figure_3_1(df, envelope, out)
    if p is not None:
        envelope.events.time_series_path = str(p.relative_to(out.parent)) if out.parent != out else p.name

    # Figure 4.1 — over-design bar
    p = render_figure_4_1(envelope, out)
    if p is not None:
        envelope.over_design.over_design_chart_path = str(p.relative_to(out.parent)) if out.parent != out else p.name

    return envelope
