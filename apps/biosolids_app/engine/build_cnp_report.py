"""Build the CNP Resource Fate section for BioPoint PDF reports."""
import sys, io
sys.path.insert(0, '/mnt/user-data/outputs')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from cnp_fate import (run_cnp_fate, run_cnp_comparison, cnp_summary_table,
                       carbon_sankey_data, CNPInput, CNPFateResult)

TECH_COLOURS = {
    "base":         "#546e7a",   # grey-blue
    "pre_thp":      "#1565c0",   # dark blue
    "solidstream":  "#2e7d32",   # dark green
    "separate":     "#6a1b9a",   # purple
    "separate_thp": "#4a148c",   # deep purple
    "recup":        "#00695c",   # teal
    "pyrolysis":    "#bf360c",   # burnt orange
    "htl":          "#e65100",   # orange
    "incineration": "#b71c1c",   # red
}
STREAM_COLOURS = {
    "energy":      "#f57f17",   # amber
    "atmospheric": "#b71c1c",   # red
    "product":     "#1b5e20",   # green
    "liquid":      "#0277bd",   # blue
    "storage":     "#004d40",   # teal
    "input":       "#37474f",   # dark grey
}


def _carbon_sankey_matplotlib(result: CNPFateResult,
                               figsize=(10, 5)) -> io.BytesIO:
    """
    Render a simplified Carbon Fate bar chart (Sankey-style proportional bars).
    Returns PNG bytes.

    Note: matplotlib.sankey is very limited for complex flows.
    We use a stacked horizontal bar chart that conveys the same information
    more reliably at PDF resolution.
    """
    fig, axes = plt.subplots(1, 3, figsize=figsize, facecolor='white')
    fig.suptitle(
        f"Carbon Fate Analysis — {result.config_label}\n"
        f"Total C in: {result.c_in:,.0f} kg C/day",
        fontsize=11, fontweight='bold', y=1.02, color='#1a3a5c'
    )

    # Colour map
    cat_colours = {
        "energy":      "#f57f17",
        "atmospheric": "#c62828",
        "product":     "#2e7d32",
        "storage":     "#004d40",
        "liquid":      "#0277bd",
    }
    cat_labels = {
        "energy":      "Energy (CH₄ to CHP)",
        "atmospheric": "To Atmosphere (CO₂/CH₄)",
        "product":     "In Product (cake/char)",
        "storage":     "Soil Sequestration",
        "liquid":      "Centrate DOC",
    }

    # Aggregate C streams by category
    cats = ["energy","product","storage","atmospheric","liquid"]
    cat_c = {cat: 0.0 for cat in cats}
    for s in result.streams:
        if s.c_kg_d > 0 and s.category in cat_c:
            cat_c[s.category] += s.c_kg_d
    # Add land application soil sequestration
    for s in result.streams:
        if s.name == "land_app_soil" and s.c_kg_d > 0:
            cat_c["storage"] += s.c_kg_d

    total_c = result.c_in

    # Panel 1: Stacked bar — C fate by category
    ax1 = axes[0]
    bottoms = 0.0
    for cat in cats:
        val = cat_c[cat] / total_c * 100
        if val > 0.5:
            ax1.bar(0.5, val, bottom=bottoms, color=cat_colours[cat],
                    width=0.7, label=cat_labels[cat], alpha=0.9)
            if val > 3:
                ax1.text(0.5, bottoms + val/2, f"{val:.0f}%",
                         ha='center', va='center', fontsize=8.5,
                         color='white', fontweight='bold')
            bottoms += val
    ax1.set_xlim(0, 1); ax1.set_ylim(0, 105)
    ax1.set_xticks([]); ax1.set_ylabel("% of incoming carbon", fontsize=8)
    ax1.set_title("Carbon Fate", fontsize=9, color='#1a3a5c', fontweight='bold')
    ax1.legend(loc='upper right', fontsize=6.5, framealpha=0.8)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # Panel 2: Key indices — horizontal bars
    ax2 = axes[1]
    indices = [
        ("C Utilised\n(CHP)",      result.c_utilised_pct,    "#f57f17"),
        ("C Sequestered\n(soil)",  result.c_sequestered_pct, "#004d40"),
        ("C Retained\n(product)",  result.c_retained_pct,    "#2e7d32"),
        ("C to\nAtmosphere",       result.c_destroyed_pct,   "#c62828"),
        ("Recovery\nIndex",        result.c_recovery_index,  "#1565c0"),
    ]
    ys    = range(len(indices))
    vals  = [x[1] for x in indices]
    cols  = [x[2] for x in indices]
    lbls  = [x[0] for x in indices]
    bars  = ax2.barh(list(ys), vals, color=cols, alpha=0.85, height=0.6)
    ax2.set_yticks(list(ys)); ax2.set_yticklabels(lbls, fontsize=7.5)
    ax2.set_xlim(0, 105); ax2.set_xlabel("% of incoming C", fontsize=8)
    ax2.set_title("C Recovery Indices", fontsize=9, color='#1a3a5c', fontweight='bold')
    for bar, val in zip(bars, vals):
        ax2.text(val + 1, bar.get_y() + bar.get_height()/2,
                 f"{val:.1f}%", va='center', fontsize=7.5)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)

    # Panel 3: Absolute flows in kg C/day
    ax3 = axes[2]
    stream_names = []
    stream_vals  = []
    stream_cols  = []
    for s in sorted(result.streams, key=lambda x: -x.c_kg_d):
        if s.c_kg_d > total_c * 0.005:   # only show >0.5% of total
            stream_names.append(s.label)
            stream_vals.append(s.c_kg_d)
            stream_cols.append(STREAM_COLOURS.get(s.category, "#90a4ae"))
    if stream_names:
        ys3 = range(len(stream_names))
        ax3.barh(list(ys3), stream_vals, color=stream_cols, alpha=0.85, height=0.6)
        ax3.set_yticks(list(ys3)); ax3.set_yticklabels(stream_names, fontsize=7)
        ax3.set_xlabel("kg C/day", fontsize=8)
        ax3.set_title("C by Destination", fontsize=9, color='#1a3a5c', fontweight='bold')
        for i, val in enumerate(stream_vals):
            ax3.text(val * 1.01, i, f"{val:,.0f}", va='center', fontsize=7)
        ax3.spines['top'].set_visible(False)
        ax3.spines['right'].set_visible(False)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


def _np_fate_bar(result: CNPFateResult, figsize=(10, 4)) -> io.BytesIO:
    """Nitrogen and Phosphorus fate side-by-side bar charts."""
    fig, axes = plt.subplots(1, 2, figsize=figsize, facecolor='white')
    fig.suptitle(
        f"Nitrogen & Phosphorus Fate — {result.config_label}",
        fontsize=11, fontweight='bold', y=1.02, color='#1a3a5c'
    )

    # N fate
    ax1 = axes[0]
    n_data = [
        ("Cake\n(fertiliser value)", result.n_recovered_pct,   "#2e7d32"),
        ("Centrate\n(recycle burden)", result.n_recycled_pct, "#0277bd"),
        ("Atmosphere\n(N₂O/NH₃)",   result.n_lost_pct,       "#c62828"),
    ]
    labs1 = [x[0] for x in n_data]
    vals1 = [x[1] for x in n_data]
    cols1 = [x[2] for x in n_data]
    bars1 = ax1.bar(labs1, vals1, color=cols1, alpha=0.85, width=0.5)
    for bar, val in zip(bars1, vals1):
        ax1.text(bar.get_x() + bar.get_width()/2, val + 0.5,
                 f"{val:.1f}%", ha='center', va='bottom', fontsize=8)
    ax1.set_ylabel("% of incoming nitrogen", fontsize=8)
    ax1.set_title(f"Nitrogen Fate\nCentrate burden: {result.n_burden_kg_d:,.0f} kg N/day",
                  fontsize=9, color='#1a3a5c', fontweight='bold')
    ax1.set_ylim(0, max(vals1) * 1.15 if vals1 else 100)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # P fate
    ax2 = axes[1]
    p_data = [
        ("Cake / Char\n(recoverable)", result.p_recovered_pct,    "#2e7d32"),
        ("Centrate\n(recycled)",        result.p_recycled_pct,    "#0277bd"),
        ("P Circularity\nIndex",         result.p_circularity_pct, "#f57f17"),
    ]
    labs2 = [x[0] for x in p_data]
    vals2 = [x[1] for x in p_data]
    cols2 = [x[2] for x in p_data]
    bars2 = ax2.bar(labs2, vals2, color=cols2, alpha=0.85, width=0.5)
    for bar, val in zip(bars2, vals2):
        ax2.text(bar.get_x() + bar.get_width()/2, val + 0.5,
                 f"{val:.1f}%", ha='center', va='bottom', fontsize=8)
    ax2.set_ylabel("% of incoming phosphorus", fontsize=8)
    ax2.set_title("Phosphorus Fate", fontsize=9, color='#1a3a5c', fontweight='bold')
    ax2.set_ylim(0, max(vals2) * 1.15 if vals2 else 100)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


def _resource_destiny_heatmap(results: list[CNPFateResult],
                               figsize=(12, 6)) -> io.BytesIO:
    """
    Resource Destiny Dashboard — heatmap comparison of all configs.
    Higher = better for C utilised, recovery indices, P circularity.
    Higher = worse for C to atmosphere, N centrate burden.
    """
    fig, ax = plt.subplots(figsize=figsize, facecolor='white')

    metrics_def = [
        # (attr,                 label,                      higher_better)
        ("c_utilised_pct",    "C Utilised (CHP) %",         True),
        ("c_sequestered_pct", "C Sequestered (soil) %",     True),
        ("c_destroyed_pct",   "C to Atmosphere %",           False),
        ("c_recovery_index",  "Carbon Recovery Index %",     True),
        ("n_recovered_pct",   "N in Cake (fertiliser) %",   True),
        ("n_recycled_pct",    "N in Centrate (burden) %",    False),
        ("n_lost_pct",        "N to Atmosphere %",           False),
        ("p_recovered_pct",   "P in Cake %",                 True),
        ("p_circularity_pct", "P Circularity Index %",       True),
        ("pfas_destroyed_pct","PFAS Destroyed %",            True),
    ]

    ylabels = [m[1] for m in metrics_def]
    # Shorten labels for heatmap axes
    def _shorten(lbl):
        return lbl.replace(" †","\u2020").replace("Conventional AD","Conv. MAD")
    xlabels = [_shorten(r.config_label) for r in results]

    data = np.zeros((len(metrics_def), len(results)))
    for j, result in enumerate(results):
        for i, (attr, _, higher_better) in enumerate(metrics_def):
            val = getattr(result, attr, 0)
            data[i, j] = val if higher_better else -val

    # Normalise row-wise for colouring
    data_norm = np.zeros_like(data)
    for i in range(data.shape[0]):
        row = data[i, :]
        rmin, rmax = row.min(), row.max()
        if rmax > rmin:
            data_norm[i, :] = (row - rmin) / (rmax - rmin)
        else:
            data_norm[i, :] = 0.5

    im = ax.imshow(data_norm, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)

    # Annotate with actual values
    for i in range(len(metrics_def)):
        for j in range(len(results)):
            val = getattr(results[j], metrics_def[i][0], 0)
            ax.text(j, i, f"{val:.0f}{'%' if 'kg' not in metrics_def[i][1] else ''}",
                    ha='center', va='center', fontsize=8,
                    color='black' if 0.2 < data_norm[i,j] < 0.8 else 'white',
                    fontweight='bold')

    ax.set_xticks(range(len(xlabels)))
    ax.set_xticklabels(xlabels, fontsize=8.5, rotation=15, ha='right')
    ax.set_yticks(range(len(ylabels)))
    ax.set_yticklabels(ylabels, fontsize=8)
    ax.set_title("Resource Destiny Dashboard\n"
                 "Green = better outcome for that metric   |   "
                 "Red = worse outcome",
                 fontsize=10, fontweight='bold', color='#1a3a5c', pad=10)

    plt.colorbar(im, ax=ax, shrink=0.8, label='Relative performance (row-normalised)')
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


# Self-test
if __name__ == "__main__":
    inp = CNPInput(ps_ds_tpd=120.7, was_ds_tpd=98.8,
                   ps_vs_pct=65, was_vs_pct=65,
                   ps_n_pct=3.5, was_n_pct=8.5)

    configs = [
        ("base",         "Conv. MAD"),
        ("pre_thp",      "Pre-THP"),
        ("separate",     "Separate"),
        ("separate_thp", "Sep+THP"),
        ("incineration", "Incineration"),
    ]
    results = run_cnp_comparison(inp, configs)

    # Test chart generation
    buf1 = _carbon_sankey_matplotlib(results[2])  # Separate config
    buf2 = _np_fate_bar(results[2])
    buf3 = _resource_destiny_heatmap(results)
    print(f"Carbon chart:    {len(buf1.read()):,} bytes")
    print(f"N/P chart:       {len(buf2.read()):,} bytes")
    print(f"Destiny heatmap: {len(buf3.read()):,} bytes")
    print("✓ All charts generated")
