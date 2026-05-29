"""
apps/biosolids_app/pages/page_10_sankey.py
BioPoint V1 — Mass & Energy Sankey Diagrams.
ph2o Consulting — BioPoint V1 — v25B02
"""
import sys, json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


# ── Sankey data builders ───────────────────────────────────────────────────

def _mass_sankey(cfg_id, cr, site):
    """Build Sankey nodes/links for mass balance (wet t/day)."""
    ps_wet  = site.ps_ds_tpd  / (site.ps_ts_pct  / 100)
    was_wet = site.was_ds_tpd / (site.was_ts_pct / 100)
    total_feed = ps_wet + was_wet

    # Biogas mass: ~1.2 kg/m³ (mixed CH4/CO2 at ~STP)
    biogas_t = cr.biogas_m3_per_d * 1.2 / 1000
    cake_t   = cr.wet_cake_t_per_day

    # Centrate volume: feed - cake - biogas evap losses (~2%)
    evap_t     = total_feed * 0.02
    centrate_t = max(0.1, total_feed - cake_t - biogas_t - evap_t)

    has_thp = cfg_id in ("pre_thp", "solidstream")

    # Build nodes list — order matters for layout
    if cfg_id == "pre_thp":
        nodes = [
            {"id": 0,  "name": f"PS Feed\n{ps_wet:.1f} t/d",       "col": 0},
            {"id": 1,  "name": f"WAS Feed\n{was_wet:.1f} t/d",      "col": 0},
            {"id": 2,  "name": "Pre-dewatering\n(THP feed prep)",    "col": 1},
            {"id": 3,  "name": "THP\nReactor",                       "col": 2},
            {"id": 4,  "name": f"Digester\n{total_feed:.1f} t/d",   "col": 3},
            {"id": 5,  "name": f"Biogas\n{cr.biogas_m3_per_d:,.0f} m³/d", "col": 4},
            {"id": 6,  "name": "Dewatering",                         "col": 4},
            {"id": 7,  "name": f"Dewatered Cake\n{cake_t:.1f} t/d\n({cr.cake_ds_pct:.0f}% DS)", "col": 5},
            {"id": 8,  "name": f"Centrate\n{centrate_t:.1f} t/d",   "col": 5},
        ]
        links = [
            {"source": 0, "target": 2, "value": ps_wet},
            {"source": 1, "target": 2, "value": was_wet},
            {"source": 2, "target": 3, "value": total_feed},
            {"source": 3, "target": 4, "value": total_feed},
            {"source": 4, "target": 5, "value": round(biogas_t, 2)},
            {"source": 4, "target": 6, "value": round(total_feed - biogas_t, 2)},
            {"source": 6, "target": 7, "value": round(cake_t, 2)},
            {"source": 6, "target": 8, "value": round(centrate_t, 2)},
        ]

    elif cfg_id == "solidstream":
        nodes = [
            {"id": 0,  "name": f"PS Feed\n{ps_wet:.1f} t/d",        "col": 0},
            {"id": 1,  "name": f"WAS Feed\n{was_wet:.1f} t/d",       "col": 0},
            {"id": 2,  "name": f"Digester\n{total_feed:.1f} t/d",    "col": 1},
            {"id": 3,  "name": f"Biogas\n{cr.biogas_m3_per_d:,.0f} m³/d", "col": 2},
            {"id": 4,  "name": "SolidStream\nTHP Reactor",            "col": 2},
            {"id": 5,  "name": "Dewatering",                          "col": 3},
            {"id": 6,  "name": f"Dewatered Cake\n{cake_t:.1f} t/d\n(≥38% DS)", "col": 4},
            {"id": 7,  "name": f"Hot Centrate\n(77°C recycle)",       "col": 4},
            {"id": 8,  "name": f"Final Centrate\n{centrate_t:.1f} t/d", "col": 4},
        ]
        hot_centrate_t = total_feed * 0.12  # ~12% of feed recycled hot
        links = [
            {"source": 0, "target": 2, "value": ps_wet},
            {"source": 1, "target": 2, "value": was_wet},
            {"source": 2, "target": 3, "value": round(biogas_t, 2)},
            {"source": 2, "target": 4, "value": round(total_feed - biogas_t, 2)},
            {"source": 4, "target": 5, "value": round(total_feed - biogas_t, 2)},
            {"source": 5, "target": 6, "value": round(cake_t, 2)},
            {"source": 5, "target": 7, "value": round(hot_centrate_t, 2)},
            {"source": 5, "target": 8, "value": round(max(0.1, centrate_t - hot_centrate_t), 2)},
            {"source": 7, "target": 2, "value": round(hot_centrate_t, 2)},  # recycle arrow
        ]

    else:  # base / recup
        nodes = [
            {"id": 0, "name": f"PS Feed\n{ps_wet:.1f} t/d",         "col": 0},
            {"id": 1, "name": f"WAS Feed\n{was_wet:.1f} t/d",        "col": 0},
            {"id": 2, "name": f"Digester\n{total_feed:.1f} t/d",     "col": 1},
            {"id": 3, "name": f"Biogas\n{cr.biogas_m3_per_d:,.0f} m³/d", "col": 2},
            {"id": 4, "name": "Dewatering",                           "col": 2},
            {"id": 5, "name": f"Dewatered Cake\n{cake_t:.1f} t/d\n({cr.cake_ds_pct:.0f}% DS)", "col": 3},
            {"id": 6, "name": f"Centrate\n{centrate_t:.1f} t/d",     "col": 3},
        ]
        links = [
            {"source": 0, "target": 2, "value": ps_wet},
            {"source": 1, "target": 2, "value": was_wet},
            {"source": 2, "target": 3, "value": round(biogas_t, 2)},
            {"source": 2, "target": 4, "value": round(total_feed - biogas_t, 2)},
            {"source": 4, "target": 5, "value": round(cake_t, 2)},
            {"source": 4, "target": 6, "value": round(centrate_t, 2)},
        ]

    return nodes, links, "t/day (wet mass)"


def _energy_sankey(cfg_id, cr, site):
    """Build Sankey nodes/links for energy balance (kW)."""
    chp_eff   = site.chp_eff_pct / 100
    ds_total  = site.ps_ds_tpd + site.was_ds_tpd
    fuel_kw   = cr.elec_gross_kw / max(chp_eff, 0.01)
    heat_kw   = fuel_kw * 0.45
    losses_kw = fuel_kw * 0.15
    biogas_kw = cr.biogas_gj_per_d * 1000 / 86.4   # GJ/day → kW

    thp_steam  = getattr(cr, "thp_steam_demand_kw", 0.0)
    dig_gross  = ds_total * 26.7
    centrate_c = ds_total * 10.5 if cfg_id == "solidstream" else 0.0
    dig_net    = max(0.0, dig_gross - centrate_c)
    surplus    = getattr(cr, "heat_surplus_kw", heat_kw - dig_net)

    net_elec   = cr.elec_net_kw
    mixing     = cr.elec_gross_kw - net_elec

    def r(v): return max(0.1, round(v, 1))

    if cfg_id in ("pre_thp", "solidstream"):
        nodes = [
            {"id": 0, "name": f"Biogas\n{biogas_kw:,.0f} kW LHV",       "col": 0},
            {"id": 1, "name": "CHP Engine",                               "col": 1},
            {"id": 2, "name": f"Electricity\n{cr.elec_gross_kw:,.0f} kW gross", "col": 2},
            {"id": 3, "name": f"CHP Waste Heat\n{heat_kw:,.0f} kW",      "col": 2},
            {"id": 4, "name": f"Engine Losses\n{losses_kw:,.0f} kW",     "col": 2},
            {"id": 5, "name": f"Mixing\n{mixing:,.0f} kW",               "col": 3},
            {"id": 6, "name": f"Net Export\n{net_elec:,.0f} kW",         "col": 3},
            {"id": 7, "name": f"THP Steam\n{thp_steam:,.0f} kW",         "col": 3},
            {"id": 8, "name": f"Digester Heating\n{dig_net:,.0f} kW",    "col": 3},
            {"id": 9, "name": f"Heat Surplus\n{max(0,surplus):,.0f} kW", "col": 3},
        ]
        links = [
            {"source": 0, "target": 1, "value": r(biogas_kw)},
            {"source": 1, "target": 2, "value": r(cr.elec_gross_kw)},
            {"source": 1, "target": 3, "value": r(heat_kw)},
            {"source": 1, "target": 4, "value": r(losses_kw)},
            {"source": 2, "target": 5, "value": r(mixing)},
            {"source": 2, "target": 6, "value": r(net_elec)},
            {"source": 3, "target": 7, "value": r(min(thp_steam, heat_kw * 0.52))},
            {"source": 3, "target": 8, "value": r(min(dig_net, heat_kw * 0.40))},
            {"source": 3, "target": 9, "value": r(max(0.1, surplus))},
        ]
        if cfg_id == "solidstream" and centrate_c > 0:
            nodes.append({"id": 10, "name": f"Centrate Heat\nCredit\n{centrate_c:,.0f} kW", "col": 2})
            nodes[8]["name"] = f"Digester Heating\n(net {dig_net:,.0f} kW)"
            links.append({"source": 10, "target": 8, "value": r(centrate_c)})
    else:
        nodes = [
            {"id": 0, "name": f"Biogas\n{biogas_kw:,.0f} kW LHV",        "col": 0},
            {"id": 1, "name": "CHP Engine",                                "col": 1},
            {"id": 2, "name": f"Electricity\n{cr.elec_gross_kw:,.0f} kW", "col": 2},
            {"id": 3, "name": f"CHP Waste Heat\n{heat_kw:,.0f} kW",       "col": 2},
            {"id": 4, "name": f"Engine Losses\n{losses_kw:,.0f} kW",      "col": 2},
            {"id": 5, "name": f"Mixing\n{mixing:,.0f} kW",                "col": 3},
            {"id": 6, "name": f"Net Export\n{net_elec:,.0f} kW",          "col": 3},
            {"id": 7, "name": f"Digester Heating\n{dig_net:,.0f} kW",     "col": 3},
            {"id": 8, "name": f"Heat Surplus\n{max(0,surplus):,.0f} kW",  "col": 3},
        ]
        links = [
            {"source": 0, "target": 1, "value": r(biogas_kw)},
            {"source": 1, "target": 2, "value": r(cr.elec_gross_kw)},
            {"source": 1, "target": 3, "value": r(heat_kw)},
            {"source": 1, "target": 4, "value": r(losses_kw)},
            {"source": 2, "target": 5, "value": r(mixing)},
            {"source": 2, "target": 6, "value": r(net_elec)},
            {"source": 3, "target": 7, "value": r(min(dig_net, heat_kw))},
            {"source": 3, "target": 8, "value": r(max(0.1, surplus))},
        ]

    return nodes, links, "kW"


# ── Sankey HTML renderer ───────────────────────────────────────────────────

def _sankey_html(nodes, links, unit, title, subtitle, height=520):
    nodes_j = json.dumps(nodes)
    links_j = json.dumps(links)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3-sankey/0.12.3/d3-sankey.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f8fafc; }}
  #chart {{ width: 100%; height: {height}px; }}
  .node rect {{ cursor: pointer; stroke: #fff; stroke-width: 1.5px; }}
  .node text {{ font-size: 11px; fill: #1a3a5c; font-weight: 500; }}
  .link {{ fill: none; stroke-opacity: 0.35; }}
  .link:hover {{ stroke-opacity: 0.65; }}
  .title {{ font-size: 14px; font-weight: 700; fill: #1a3a5c; }}
  .subtitle {{ font-size: 11px; fill: #546e7a; }}
  .unit-label {{ font-size: 10px; fill: #78909c; font-style: italic; }}
</style>
</head>
<body>
<svg id="chart"></svg>
<script>
const nodes = {nodes_j};
const links = {links_j};
const unit  = "{unit}";
const title = "{title}";
const sub   = "{subtitle}";

const W = document.getElementById('chart').clientWidth || 900;
const H = {height};
const margin = {{top: 50, right: 160, bottom: 20, left: 10}};
const innerW = W - margin.left - margin.right;
const innerH = H - margin.top  - margin.bottom;

const svg = d3.select("#chart")
  .attr("width", W).attr("height", H);

// Title
svg.append("text").attr("class","title")
  .attr("x", margin.left).attr("y", 22).text(title);
svg.append("text").attr("class","subtitle")
  .attr("x", margin.left).attr("y", 38).text(sub);
svg.append("text").attr("class","unit-label")
  .attr("x", W - margin.right - 5).attr("y", 22)
  .attr("text-anchor","end").text("Values: " + unit);

const g = svg.append("g")
  .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

// Colour palette — ph2o brand
const palette = [
  "#1a3a5c","#0077b6","#2e86ab","#a8dadc","#457b9d",
  "#1d3557","#48cae4","#90e0ef","#00b4d8","#023e8a",
  "#52b788","#74c69d","#40916c","#b7e4c7","#d8f3dc",
];
const colourOf = (i) => palette[i % palette.length];

const {{sankey, sankeyLinkHorizontal}} = d3;

const sk = sankey()
  .nodeId(d => d.id)
  .nodeWidth(18)
  .nodePadding(14)
  .extent([[0, 0], [innerW, innerH]]);

// Deep copy to avoid mutation
const graph = sk({{
  nodes: nodes.map(d => Object.assign({{}}, d)),
  links: links.map(d => Object.assign({{}}, d)),
}});

// Links
g.append("g").selectAll(".link")
  .data(graph.links)
  .join("path")
  .attr("class","link")
  .attr("d", sankeyLinkHorizontal())
  .attr("stroke", d => colourOf(d.source.index))
  .attr("stroke-width", d => Math.max(1, d.width))
  .append("title")
  .text(d => `${{d.source.name.split('\\n')[0]}} → ${{d.target.name.split('\\n')[0]}}: ${{d.value.toFixed(1)}} ${{unit}}`);

// Nodes
const node = g.append("g").selectAll(".node")
  .data(graph.nodes)
  .join("g").attr("class","node");

node.append("rect")
  .attr("x", d => d.x0).attr("y", d => d.y0)
  .attr("width", d => d.x1 - d.x0)
  .attr("height", d => Math.max(1, d.y1 - d.y0))
  .attr("fill", (d,i) => colourOf(i))
  .attr("rx", 2)
  .append("title")
  .text(d => `${{d.name.replace(/\\n/g,' ')}}: ${{d.value !== undefined ? d.value.toFixed(1) : ''}} ${{unit}}`);

// Node labels — multiline
node.each(function(d) {{
  const el = d3.select(this);
  const lines = d.name.split('\\n');
  const x = d.x1 < innerW / 2 ? d.x1 + 6 : d.x0 - 6;
  const anchor = d.x1 < innerW / 2 ? "start" : "end";
  const yMid = (d.y0 + d.y1) / 2 - (lines.length - 1) * 6;
  lines.forEach((line, li) => {{
    el.append("text")
      .attr("x", x).attr("y", yMid + li * 13)
      .attr("dy", "0.35em")
      .attr("text-anchor", anchor)
      .style("font-size", lines.length > 2 ? "10px" : "11px")
      .style("fill", "#1a3a5c")
      .style("font-weight", li === 0 ? "600" : "400")
      .text(line);
  }});
}});
</script>
</body>
</html>"""


# ── Page render ───────────────────────────────────────────────────────────

def render():
    st.header("🔀 Mass & Energy Flow")
    st.caption(
        "Sankey diagrams showing mass balance (wet t/day) and energy balance (kW) "
        "for each configuration. Run the Config Comparison first to populate results."
    )

    # Check if comparison results are available
    result = st.session_state.get("cmp_result")
    if not result:
        st.info(
            "No comparison results found. Run the **⚖️ Config Comparison** first, "
            "then return here to view Sankey diagrams for each configuration.",
            icon="💡",
        )
        return

    included_ids = result.included_ids
    site = result.site

    # Config selector
    config_labels = {k: result.configs[k].config_label for k in included_ids}
    selected_id = st.selectbox(
        "Configuration",
        options=included_ids,
        format_func=lambda k: config_labels[k],
        key="sankey_config",
    )

    cr = result.configs[selected_id]

    # Mass / Energy toggle
    mode = st.radio(
        "Diagram type",
        ["⚖️ Mass Balance (wet t/day)", "⚡ Energy Balance (kW)"],
        horizontal=True,
        key="sankey_mode",
    )

    st.divider()

    if "Mass" in mode:
        nodes, links, unit = _mass_sankey(selected_id, cr, site)
        title = f"Mass Balance — {cr.config_label}"
        subtitle = (
            f"Feed: {site.ps_ds_tpd + site.was_ds_tpd:.1f} tDS/day  |  "
            f"Cake: {cr.wet_cake_t_per_day:.1f} t/day ({cr.cake_ds_pct:.0f}% DS)  |  "
            f"Biogas: {cr.biogas_m3_per_d:,.0f} m³/day"
        )
    else:
        nodes, links, unit = _energy_sankey(selected_id, cr, site)
        chp_eff = site.chp_eff_pct / 100
        biogas_kw = cr.biogas_gj_per_d * 1000 / 86.4
        title = f"Energy Balance — {cr.config_label}"
        subtitle = (
            f"Biogas: {biogas_kw:,.0f} kW LHV  |  "
            f"CHP: {cr.elec_gross_kw:,.0f} kW gross  |  "
            f"Net export: {cr.elec_net_kw:,.0f} kW  |  "
            f"Heat self-sufficient: {'Yes ✓' if getattr(cr,'heat_self_sufficient',True) else 'No — supplementary boiler required'}"
        )

    html = _sankey_html(nodes, links, unit, title, subtitle, height=540)
    components.html(html, height=560, scrolling=False)

    # Key metrics below diagram
    st.divider()
    if "Mass" in mode:
        m1, m2, m3, m4 = st.columns(4)
        ps_wet  = site.ps_ds_tpd  / (site.ps_ts_pct  / 100)
        was_wet = site.was_ds_tpd / (site.was_ts_pct / 100)
        m1.metric("Total feed",     f"{ps_wet + was_wet:.1f} t/day wet")
        m2.metric("Dewatered cake", f"{cr.wet_cake_t_per_day:.1f} t/day",
                  delta=f"{cr.cake_ds_pct:.0f}% DS")
        m3.metric("Biogas",         f"{cr.biogas_m3_per_d:,.0f} m³/day")
        m4.metric("VS destruction", f"{cr.vsr_pct:.1f}%")
    else:
        e1, e2, e3, e4 = st.columns(4)
        biogas_kw = cr.biogas_gj_per_d * 1000 / 86.4
        e1.metric("Biogas energy",  f"{biogas_kw:,.0f} kW")
        e2.metric("CHP gross",      f"{cr.elec_gross_kw:,.0f} kW")
        e3.metric("Net export",     f"{cr.elec_net_kw:,.0f} kW")
        surplus = getattr(cr, "heat_surplus_kw", 0.0)
        e4.metric("Heat surplus",   f"{surplus:,.0f} kW",
                  delta="self-sufficient" if surplus >= 0 else "boiler needed",
                  delta_color="normal" if surplus >= 0 else "inverse")

    st.caption(
        "Mass balance: closed at digester boundary. Moisture evaporation (~2%) excluded from cake/centrate split. "
        "Energy balance: CHP fuel input calculated from gross electrical output ÷ efficiency. "
        "All values screening-grade ±15%."
    )
