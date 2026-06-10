"""filter_comparator.report.charts

Matplotlib re-implementation of lib/reportCharts.js.

The JavaScript original draws three charts on an off-screen HTML canvas and
returns PNG data URLs. This module draws the same three charts with
matplotlib and returns them as in-memory PNG buffers ready to embed in the
reportlab PDF:

  1. chart_capacity      - solids holding capacity, grouped bars (Figure 1)
  2. chart_head_budget   - as-built head budget, stacked bars (Figure 2)
  3. chart_sensitivity   - run length retained, grouped bars (Figure 3)

Layout and colours follow the source so the report is reproduced as-is.
"""

import io

import matplotlib
matplotlib.use("Agg")  # headless / no display
import matplotlib.pyplot as plt  # noqa: E402

# Colour palette from reportCharts.js
COL = {
    "rust": "#B0451F", "slate": "#3F5870", "sage": "#5A7359", "ochre": "#C8961A",
    "ink": "#0E1116", "ink500": "#5B5F66", "rule": "#C8C2B4",
    "appt": "#2B2A26", "cb": "#4A7BA6", "ud": "#6FA052", "load": "#E0A21C",
}

# Canvas sizes mirror the JS makeCanvas(wCss, hCss) calls; rendered at high DPI.
_DPI = 200


def _layer_depth(filt, media):
    layer = next((x for x in filt["mediaLayers"] if x["media"] == media), None)
    return layer["depth"] if layer else 0


def _new_fig(w_css, h_css):
    """Create a white figure sized to match the JS canvas aspect ratio."""
    fig = plt.figure(figsize=(w_css / 72.0, h_css / 72.0), dpi=_DPI)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.085, 0.20, 0.885, 0.70])
    ax.set_facecolor("white")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(COL["ink500"])
        ax.spines[spine].set_linewidth(0.8)
    ax.tick_params(colors=COL["ink500"], labelsize=7, length=2)
    ax.grid(axis="y", color=COL["rule"], linewidth=0.4)
    ax.set_axisbelow(True)
    return fig, ax


def _save(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


# ---- Chart 1: solids holding capacity, grouped bars ----
def chart_capacity(model):
    """Figure 1. Solids holding capacity by measure (grouped bars, D1 vs D2)."""
    measures = [
        ("Pore-fill\nceiling", model["poreFill"]["D1"], model["poreFill"]["D2"]),
        ("Kawamura\n(upper)",
         _layer_depth(model["filters"]["D1"], "anthracite") * 1.5,
         _layer_depth(model["filters"]["D2"], "anthracite") * 1.5),
        ("AWWA M37\n(upper)", 5.0, 5.0),
        ("K cap", model["kCap"], model["kCap"]),
    ]
    v_max = 12
    fig, ax = _new_fig(560, 220)

    labels = [m[0] for m in measures]
    d1_vals = [m[1] for m in measures]
    d2_vals = [m[2] for m in measures]
    x = list(range(len(measures)))
    bw = 0.30

    b1 = ax.bar([i - bw / 2 - 0.02 for i in x], d1_vals, bw,
                color=COL["rust"], label="D1")
    b2 = ax.bar([i + bw / 2 + 0.02 for i in x], d2_vals, bw,
                color=COL["slate"], label="D2")
    for bars, col in ((b1, COL["rust"]), (b2, COL["slate"])):
        for rect in bars:
            ax.annotate("%.1f" % rect.get_height(),
                        (rect.get_x() + rect.get_width() / 2, rect.get_height()),
                        ha="center", va="bottom", fontsize=6, color=col,
                        xytext=(0, 1.5), textcoords="offset points")

    ax.set_ylim(0, v_max)
    ax.set_xlim(-0.6, len(measures) - 0.4)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7, color=COL["ink500"])
    ax.set_ylabel("K  (kg/m2/run)", fontsize=8, color=COL["ink"])
    ax.legend(loc="upper right", fontsize=7, frameon=False)
    return _save(fig)


# ---- Chart 2: as-built head budget, four stacked bars ----
def chart_head_budget(model):
    """Figure 2. As-built head budget, stacked components against driving head."""
    pts = [
        ("D1 coag", model["modes"]["coag"]["D1"], model["filters"]["D1"]),
        ("D2 coag", model["modes"]["coag"]["D2"], model["filters"]["D2"]),
        ("D1 soft", model["modes"]["soft"]["D1"], model["filters"]["D1"]),
        ("D2 soft", model["modes"]["soft"]["D2"], model["filters"]["D2"]),
    ]
    v_max = max(model["filters"]["D1"]["drivingHead_m"],
                model["filters"]["D2"]["drivingHead_m"]) + 0.9
    fig, ax = _new_fig(560, 250)

    # slot positions mirror the JS [0, 1, 2.4, 3.4] grouping (coag pair | soft pair)
    slots = [0, 1, 2.4, 3.4]
    bw = 0.62
    components = [("appurt", COL["appt"]), ("cb", COL["cb"]),
                  ("ud", COL["ud"]), ("load", COL["load"])]

    for (lab, r, filt), slot in zip(pts, slots):
        base = 0.0
        for comp_key, col in components:
            val = r[comp_key]
            ax.bar(slot, val, bw, bottom=base, color=col)
            base += val
        # driving head line
        head = filt["drivingHead_m"]
        ax.plot([slot - bw / 2 - 0.06, slot + bw / 2 + 0.06], [head, head],
                color=COL["rust"], linewidth=1.6)

    ax.set_ylim(0, v_max)
    ax.set_xlim(-0.7, 4.1)
    ax.set_xticks(slots)
    ax.set_xticklabels([p[0] for p in pts], fontsize=7, color=COL["ink500"])
    ax.set_ylabel("Head (m)", fontsize=8, color=COL["ink"])

    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=COL["appt"]),
        plt.Rectangle((0, 0), 1, 1, color=COL["cb"]),
        plt.Rectangle((0, 0), 1, 1, color=COL["ud"]),
        plt.Rectangle((0, 0), 1, 1, color=COL["load"]),
    ]
    ax.legend(legend_handles,
              ["Appurtenances", "Clean bed", "Underdrain", "Solids load"],
              loc="upper center", ncol=4, fontsize=6.5, frameon=False,
              bbox_to_anchor=(0.5, 1.16), columnspacing=1.2, handlelength=1.2)
    return _save(fig)


# ---- Chart 3: run length retained, as-built vs feed doubled ----
def chart_sensitivity(model):
    """Figure 3. Run length retained, as-built feed against feed doubled."""
    pts = [
        ("D1 coag", model["modes"]["coag"]["D1"]["modeDesign"]["run"],
         model["modes"]["coag"]["D1"]["sens"]["runRet"]),
        ("D2 coag", model["modes"]["coag"]["D2"]["modeDesign"]["run"],
         model["modes"]["coag"]["D2"]["sens"]["runRet"]),
        ("D1 soft", model["modes"]["soft"]["D1"]["modeDesign"]["run"],
         model["modes"]["soft"]["D1"]["sens"]["runRet"]),
        ("D2 soft", model["modes"]["soft"]["D2"]["modeDesign"]["run"],
         model["modes"]["soft"]["D2"]["sens"]["runRet"]),
    ]
    v_max = 48
    fig, ax = _new_fig(560, 220)

    labels = [p[0] for p in pts]
    as_built = [p[1] for p in pts]
    doubled = [p[2] for p in pts]
    x = list(range(len(pts)))
    bw = 0.30

    b1 = ax.bar([i - bw / 2 - 0.02 for i in x], as_built, bw,
                color=COL["sage"], label="As-built feed")
    b2 = ax.bar([i + bw / 2 + 0.02 for i in x], doubled, bw,
                color=COL["ochre"], label="Feed doubled")
    for bars, col in ((b1, COL["sage"]), (b2, COL["ochre"])):
        for rect in bars:
            ax.annotate("%.0f" % rect.get_height(),
                        (rect.get_x() + rect.get_width() / 2, rect.get_height()),
                        ha="center", va="bottom", fontsize=6, color=col,
                        xytext=(0, 1.5), textcoords="offset points")

    ax.set_ylim(0, v_max)
    ax.set_xlim(-0.6, len(pts) - 0.4)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7, color=COL["ink500"])
    ax.set_ylabel("Run length (h)", fontsize=8, color=COL["ink"])
    ax.legend(loc="upper right", fontsize=7, frameon=False)
    return _save(fig)


def build_all_charts(model):
    """Return the charts as a dict of in-memory PNG buffers."""
    out = {
        "capacity": chart_capacity(model),
        "headBudget": chart_head_budget(model),
        "sensitivity": chart_sensitivity(model),
    }
    if model.get("algae"):
        out["algae"] = chart_algae(model)
    return out


# ---- Chart 4: algae run length by morphology scenario (D1 vs D2, mode N) ----
_ALGAE_SCENARIOS = [
    ("W", "Well-\ncoag"), ("A", "Mineral"), ("B", "Mixed"),
    ("C", "Colonial"), ("D", "Filament"), ("E", "EPS\nbloom"),
]


def _algae_run(block, scen):
    """Run length (h) for a scenario at mode N, or 0 if unavailable."""
    try:
        n = block["modes"]["N"]
        if n.get("infeasible"):
            return 0.0
        return n["scenarios"][scen]["run_h"] or 0.0
    except (KeyError, TypeError):
        return 0.0


def chart_algae(model):
    """Figure 4. Algae run length by morphology scenario at mode N (D1 vs D2),
    against a 24 h reference. Risk-screening estimates."""
    a1, a2 = model["algae"]["D1"], model["algae"]["D2"]
    labels = [s[1] for s in _ALGAE_SCENARIOS]
    d1_vals = [_algae_run(a1, s[0]) for s in _ALGAE_SCENARIOS]
    d2_vals = [_algae_run(a2, s[0]) for s in _ALGAE_SCENARIOS]
    v_max = max(48.0, max(d1_vals + d2_vals) * 1.15)
    fig, ax = _new_fig(560, 230)

    x = list(range(len(_ALGAE_SCENARIOS)))
    bw = 0.30
    b1 = ax.bar([i - bw / 2 - 0.02 for i in x], d1_vals, bw, color=COL["rust"], label="D1")
    b2 = ax.bar([i + bw / 2 + 0.02 for i in x], d2_vals, bw, color=COL["slate"], label="D2")
    for bars, col in ((b1, COL["rust"]), (b2, COL["slate"])):
        for rect in bars:
            ax.annotate("%.0f" % rect.get_height(),
                        (rect.get_x() + rect.get_width() / 2, rect.get_height()),
                        ha="center", va="bottom", fontsize=6, color=col,
                        xytext=(0, 1.5), textcoords="offset points")

    ax.axhline(24, color=COL["ochre"], linewidth=1.0, linestyle="--")
    ax.annotate("24 h", (len(x) - 0.5, 24), fontsize=6, color=COL["ochre"],
                va="bottom", ha="right", xytext=(0, 1), textcoords="offset points")

    ax.set_ylim(0, v_max)
    ax.set_xlim(-0.6, len(x) - 0.4)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=6.5, color=COL["ink500"])
    ax.set_ylabel("Run length (h)", fontsize=8, color=COL["ink"])
    ax.legend(loc="upper right", fontsize=7, frameon=False)
    return _save(fig)
