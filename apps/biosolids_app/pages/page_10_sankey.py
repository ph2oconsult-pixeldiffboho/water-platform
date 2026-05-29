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


# ── Sankey HTML generator ──────────────────────────────────────────────────

SANKEY_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3-sankey/0.12.3/d3-sankey.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: transparent; }
svg { width: 100%; }
.link { fill: none; stroke-opacity: 0.30; transition: stroke-opacity 0.2s; }
.link:hover { stroke-opacity: 0.60; cursor: pointer; }
.node-label { font-size: 11px; fill: #1a3a5c; }
.node-label.bold { font-weight: 600; }
.node-label.small { font-size: 10px; fill: #546e7a; }
.annotation { font-size: 10px; fill: #78909c; font-style: italic; }
.recycle-label { font-size: 10px; fill: #e65100; font-style: italic; }
</style>
</head>
<body>
<svg id="sk"></svg>
<script>
(function() {
  const NODES  = __NODES__;
  const LINKS  = __LINKS__;
  const UNIT   = "__UNIT__";
  const TITLE  = "__TITLE__";
  const RECYCLE_LABEL = "__RECYCLE__";

  const W = 900, H = __HEIGHT__;
  const M = { top: 54, right: 170, bottom: 16, left: 8 };
  const iW = W - M.left - M.right;
  const iH = H - M.top  - M.bottom;

  const palette = [
    "#1a3a5c","#0077b6","#2e86ab","#457b9d","#023e8a",
    "#52b788","#40916c","#2d6a4f","#74c69d","#b7e4c7",
    "#e07b39","#c45e1e","#ffb703","#fb8500","#a8dadc",
  ];

  const svg = d3.select("#sk")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("preserveAspectRatio", "xMidYMid meet");

  // Title
  svg.append("text")
    .attr("x", M.left).attr("y", 20)
    .style("font-size","14px").style("font-weight","700").style("fill","#1a3a5c")
    .text(TITLE);
  svg.append("text")
    .attr("x", W - M.right + 5).attr("y", 20)
    .style("font-size","10px").style("fill","#78909c")
    .text("Values: " + UNIT);

  const g = svg.append("g").attr("transform", `translate(${M.left},${M.top})`);

  const sk = d3.sankey()
    .nodeId(d => d.id)
    .nodeWidth(20)
    .nodePadding(12)
    .nodeSort(null)
    .extent([[0,0],[iW,iH]]);

  const graph = sk({
    nodes: NODES.map(d => ({...d})),
    links: LINKS.map(d => ({...d})),
  });

  // Links
  g.append("g").selectAll("path")
    .data(graph.links)
    .join("path")
    .attr("class","link")
    .attr("d", d3.sankeyLinkHorizontal())
    .attr("stroke", d => palette[d.source.index % palette.length])
    .attr("stroke-width", d => Math.max(1.5, d.width))
    .append("title")
    .text(d => `${d.source.name.replace(/\\n/g," ")} → ${d.target.name.replace(/\\n/g," ")}: ${d.value.toFixed(1)} ${UNIT}`);

  // Nodes
  const node = g.append("g").selectAll("g")
    .data(graph.nodes)
    .join("g");

  node.append("rect")
    .attr("x", d => d.x0).attr("y", d => d.y0)
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => Math.max(2, d.y1 - d.y0))
    .attr("fill", (d,i) => palette[i % palette.length])
    .attr("rx", 2)
    .append("title")
    .text(d => `${d.name.replace(/\\n/g," ")}: ${(d.value||0).toFixed(1)} ${UNIT}`);

  // Labels — right of node if in left half, left if in right half
  node.each(function(d) {
    const el = d3.select(this);
    const lines = d.name.split("\\n");
    const rightSide = d.x0 < iW * 0.55;
    const x = rightSide ? d.x1 + 7 : d.x0 - 7;
    const anchor = rightSide ? "start" : "end";
    const yMid = (d.y0 + d.y1) / 2 - (lines.length - 1) * 7;
    lines.forEach((line, i) => {
      el.append("text")
        .attr("class", i === 0 ? "node-label bold" : "node-label small")
        .attr("x", x).attr("y", yMid + i * 13)
        .attr("dy","0.35em")
        .attr("text-anchor", anchor)
        .text(line);
    });
  });

  // Recycle annotation if present
  if (RECYCLE_LABEL) {
    svg.append("text")
      .attr("class","recycle-label")
      .attr("x", M.left + iW * 0.5)
      .attr("y", H - 4)
      .attr("text-anchor","middle")
      .text("↩ " + RECYCLE_LABEL);
  }
})();
</script>
</body>
</html>"""


def _render_sankey(nodes, links, unit, title, height=520, recycle_label=""):
    html = (SANKEY_HTML
        .replace("__NODES__",   json.dumps(nodes))
        .replace("__LINKS__",   json.dumps(links))
        .replace("__UNIT__",    unit)
        .replace("__TITLE__",   title)
        .replace("__HEIGHT__",  str(height))
        .replace("__RECYCLE__", recycle_label))
    components.html(html, height=height + 20, scrolling=False)


# ── Mass balance data builders ─────────────────────────────────────────────

def _mass_nodes_links(cfg_id, cr, site):
    ps_wet  = site.ps_ds_tpd  / (site.ps_ts_pct  / 100)
    was_wet = site.was_ds_tpd / (site.was_ts_pct / 100)
    total   = ps_wet + was_wet
    biogas_t = cr.biogas_m3_per_d * 1.2 / 1000   # ~1.2 kg/m³ mixed biogas
    cake_t   = cr.wet_cake_t_per_day
    evap_t   = total * 0.02
    centrate_t = max(0.1, total - cake_t - biogas_t - evap_t)
    r = lambda v: max(0.1, round(v, 2))

    if cfg_id == "base" or cfg_id == "recup":
        nodes = [
            {"id":0, "name":f"PS Feed\n{ps_wet:.1f} t/d"},
            {"id":1, "name":f"WAS Feed\n{was_wet:.1f} t/d"},
            {"id":2, "name":f"Digester\n{total:.1f} t/d feed"},
            {"id":3, "name":f"Biogas\n{cr.biogas_m3_per_d:,.0f} m³/d\n({biogas_t:.1f} t/d)"},
            {"id":4, "name":"Dewatering"},
            {"id":5, "name":f"Cake\n{cake_t:.1f} t/d\n{cr.cake_ds_pct:.0f}% DS"},
            {"id":6, "name":f"Centrate\n{centrate_t:.1f} t/d"},
        ]
        links = [
            {"source":0,"target":2,"value":r(ps_wet)},
            {"source":1,"target":2,"value":r(was_wet)},
            {"source":2,"target":3,"value":r(biogas_t)},
            {"source":2,"target":4,"value":r(total - biogas_t)},
            {"source":4,"target":5,"value":r(cake_t)},
            {"source":4,"target":6,"value":r(centrate_t)},
        ]
        recycle = ""

    elif cfg_id == "pre_thp":
        nodes = [
            {"id":0, "name":f"PS Feed\n{ps_wet:.1f} t/d"},
            {"id":1, "name":f"WAS Feed\n{was_wet:.1f} t/d"},
            {"id":2, "name":"Pre-dewatering\n(THP feed prep)"},
            {"id":3, "name":"THP Reactor\n(165°C, 6 bar)"},
            {"id":4, "name":f"Digester\n{total:.1f} t/d feed"},
            {"id":5, "name":f"Biogas\n{cr.biogas_m3_per_d:,.0f} m³/d"},
            {"id":6, "name":"Dewatering"},
            {"id":7, "name":f"Cake\n{cake_t:.1f} t/d\n~32% DS"},
            {"id":8, "name":f"Centrate\n{centrate_t:.1f} t/d"},
        ]
        links = [
            {"source":0,"target":2,"value":r(ps_wet)},
            {"source":1,"target":2,"value":r(was_wet)},
            {"source":2,"target":3,"value":r(total)},
            {"source":3,"target":4,"value":r(total)},
            {"source":4,"target":5,"value":r(biogas_t)},
            {"source":4,"target":6,"value":r(total - biogas_t)},
            {"source":6,"target":7,"value":r(cake_t)},
            {"source":6,"target":8,"value":r(centrate_t)},
        ]
        recycle = ""

    else:  # solidstream — NO cycle, show centrate recycle as annotation only
        # Centrate recycle: ~12% of digested feed is hot centrate returned
        hot_c_t  = (total - biogas_t) * 0.12
        final_c  = max(0.1, centrate_t - hot_c_t)
        # Show recycle as a separate output node with annotation
        nodes = [
            {"id":0, "name":f"PS Feed\n{ps_wet:.1f} t/d"},
            {"id":1, "name":f"WAS Feed\n{was_wet:.1f} t/d"},
            {"id":2, "name":f"Digester\n{total:.1f} t/d feed"},
            {"id":3, "name":f"Biogas\n{cr.biogas_m3_per_d:,.0f} m³/d"},
            {"id":4, "name":"SolidStream\nTHP (post-dig)"},
            {"id":5, "name":"Dewatering\n(hot centrifuge)"},
            {"id":6, "name":f"Cake\n{cake_t:.1f} t/d\n≥38% DS"},
            {"id":7, "name":f"Hot Centrate\n{hot_c_t:.1f} t/d\n↩ 77°C recycle"},
            {"id":8, "name":f"Centrate\n{final_c:.1f} t/d"},
        ]
        links = [
            {"source":0,"target":2,"value":r(ps_wet)},
            {"source":1,"target":2,"value":r(was_wet)},
            {"source":2,"target":3,"value":r(biogas_t)},
            {"source":2,"target":4,"value":r(total - biogas_t)},
            {"source":4,"target":5,"value":r(total - biogas_t)},
            {"source":5,"target":6,"value":r(cake_t)},
            {"source":5,"target":7,"value":r(hot_c_t)},
            {"source":5,"target":8,"value":r(final_c)},
        ]
        recycle = f"Hot centrate ({hot_c_t:.1f} t/d at 77°C) recycled to digester inlet — shown as terminal node; reduces digester heating demand by {site.ps_ds_tpd + site.was_ds_tpd:.0f} × 10.5 kW/tDS = {(site.ps_ds_tpd + site.was_ds_tpd)*10.5:.0f} kW"

    return nodes, links, recycle


# ── Energy balance data builders ───────────────────────────────────────────

def _energy_nodes_links(cfg_id, cr, site):
    chp_eff   = site.chp_eff_pct / 100.0
    ds_total  = site.ps_ds_tpd + site.was_ds_tpd
    fuel_kw   = cr.elec_gross_kw / max(chp_eff, 0.01)
    heat_kw   = round(fuel_kw * 0.45, 1)
    losses_kw = round(fuel_kw * 0.15, 1)
    biogas_kw = round(cr.biogas_gj_per_d * 1000 / 86.4, 1)
    gross_kw  = cr.elec_gross_kw
    mixing_kw = round(gross_kw - cr.elec_net_kw, 1)
    net_kw    = cr.elec_net_kw
    thp_kw    = round(getattr(cr, "thp_steam_demand_kw", 0.0), 1)
    dig_gross = round(ds_total * 26.7, 1)
    centc_kw  = round(ds_total * 10.5, 1) if cfg_id == "solidstream" else 0.0
    dig_net   = round(max(0.0, dig_gross - centc_kw), 1)
    surplus   = round(getattr(cr, "heat_surplus_kw", heat_kw - thp_kw - dig_net), 1)
    deficit   = round(max(0.0, -surplus), 1)
    r = lambda v: max(0.1, round(v, 1))

    if cfg_id in ("pre_thp", "solidstream"):
        if cfg_id == "solidstream":
            nodes = [
                {"id":0, "name":f"Biogas Energy\n{biogas_kw:,.0f} kW LHV"},
                {"id":1, "name":"CHP Engine"},
                {"id":2, "name":f"Gross Electricity\n{gross_kw:,.0f} kW"},
                {"id":3, "name":f"CHP Waste Heat\n{heat_kw:,.0f} kW"},
                {"id":4, "name":f"Engine Losses\n{losses_kw:,.0f} kW\n(radiated)"},
                {"id":5, "name":f"Mixing\n{mixing_kw:,.0f} kW"},
                {"id":6, "name":f"Net Export\n{net_kw:,.0f} kW"},
                {"id":7, "name":f"THP Steam\n{thp_kw:,.0f} kW"},
                {"id":8, "name":f"Digester Heat\n{dig_net:,.0f} kW net"},
                {"id":9, "name":f"Centrate Credit\n{centc_kw:,.0f} kW\n(77°C recycle)"},
                {"id":10,"name":f"Heat Surplus\n{max(0,surplus):,.0f} kW"},
            ]
            links = [
                {"source":0,"target":1,"value":r(biogas_kw)},
                {"source":1,"target":2,"value":r(gross_kw)},
                {"source":1,"target":3,"value":r(heat_kw)},
                {"source":1,"target":4,"value":r(losses_kw)},
                {"source":2,"target":5,"value":r(mixing_kw)},
                {"source":2,"target":6,"value":r(net_kw)},
                {"source":3,"target":7,"value":r(min(thp_kw, heat_kw * 0.55))},
                {"source":3,"target":8,"value":r(min(dig_net, heat_kw * 0.35))},
                {"source":3,"target":10,"value":r(max(0.1, surplus))},
                {"source":9,"target":8,"value":r(centc_kw)},
            ]
        else:  # pre_thp
            nodes = [
                {"id":0, "name":f"Biogas Energy\n{biogas_kw:,.0f} kW LHV"},
                {"id":1, "name":"CHP Engine"},
                {"id":2, "name":f"Gross Electricity\n{gross_kw:,.0f} kW"},
                {"id":3, "name":f"CHP Waste Heat\n{heat_kw:,.0f} kW"},
                {"id":4, "name":f"Engine Losses\n{losses_kw:,.0f} kW\n(radiated)"},
                {"id":5, "name":f"Mixing\n{mixing_kw:,.0f} kW"},
                {"id":6, "name":f"Net Export\n{net_kw:,.0f} kW"},
                {"id":7, "name":f"THP Steam\n{thp_kw:,.0f} kW"},
                {"id":8, "name":f"Digester Heat\n{dig_net:,.0f} kW"},
                {"id":9, "name":f"Heat Surplus\n{max(0,surplus):,.0f} kW"
                          if surplus >= 0 else f"Heat Deficit\n{deficit:,.0f} kW\n(boiler reqd)"},
            ]
            links = [
                {"source":0,"target":1,"value":r(biogas_kw)},
                {"source":1,"target":2,"value":r(gross_kw)},
                {"source":1,"target":3,"value":r(heat_kw)},
                {"source":1,"target":4,"value":r(losses_kw)},
                {"source":2,"target":5,"value":r(mixing_kw)},
                {"source":2,"target":6,"value":r(net_kw)},
                {"source":3,"target":7,"value":r(min(thp_kw, heat_kw))},
                {"source":3,"target":8,"value":r(min(dig_net, max(0.1, heat_kw - thp_kw)))},
                {"source":3,"target":9,"value":r(max(0.1, surplus))},
            ] if surplus >= 0 else [
                {"source":0,"target":1,"value":r(biogas_kw)},
                {"source":1,"target":2,"value":r(gross_kw)},
                {"source":1,"target":3,"value":r(heat_kw)},
                {"source":1,"target":4,"value":r(losses_kw)},
                {"source":2,"target":5,"value":r(mixing_kw)},
                {"source":2,"target":6,"value":r(net_kw)},
                {"source":3,"target":7,"value":r(heat_kw * 0.52)},
                {"source":3,"target":8,"value":r(heat_kw * 0.48)},
            ]

    else:  # base / recup
        nodes = [
            {"id":0, "name":f"Biogas Energy\n{biogas_kw:,.0f} kW LHV"},
            {"id":1, "name":"CHP Engine"},
            {"id":2, "name":f"Gross Electricity\n{gross_kw:,.0f} kW"},
            {"id":3, "name":f"CHP Waste Heat\n{heat_kw:,.0f} kW"},
            {"id":4, "name":f"Engine Losses\n{losses_kw:,.0f} kW\n(radiated)"},
            {"id":5, "name":f"Mixing\n{mixing_kw:,.0f} kW"},
            {"id":6, "name":f"Net Export\n{net_kw:,.0f} kW"},
            {"id":7, "name":f"Digester Heat\n{dig_gross:,.0f} kW"},
            {"id":8, "name":f"Heat Surplus\n{max(0,surplus):,.0f} kW"},
        ]
        links = [
            {"source":0,"target":1,"value":r(biogas_kw)},
            {"source":1,"target":2,"value":r(gross_kw)},
            {"source":1,"target":3,"value":r(heat_kw)},
            {"source":1,"target":4,"value":r(losses_kw)},
            {"source":2,"target":5,"value":r(mixing_kw)},
            {"source":2,"target":6,"value":r(net_kw)},
            {"source":3,"target":7,"value":r(min(dig_gross, heat_kw * 0.65))},
            {"source":3,"target":8,"value":r(max(0.1, heat_kw * 0.35))},
        ]

    return nodes, links


# ── Page ──────────────────────────────────────────────────────────────────

def render():
    st.header("🔀 Mass & Energy Flow")
    st.caption(
        "Sankey diagrams showing mass balance (wet t/day) and energy balance (kW) "
        "for each configuration. Run Config Comparison first to populate data."
    )

    result = st.session_state.get("cmp_result")
    if not result:
        st.info(
            "No comparison data found. Run **⚖️ Config Comparison** first, "
            "then return here to view Sankey diagrams.",
            icon="💡",
        )
        return

    site     = result.site
    cfg_ids  = result.included_ids
    cfg_map  = {k: result.configs[k].config_label for k in cfg_ids}

    # Config selector
    selected = st.selectbox(
        "Select configuration",
        options=cfg_ids,
        format_func=lambda k: cfg_map[k],
        key="sankey_cfg",
    )
    cr = result.configs[selected]

    st.divider()

    # ── Two tabs: Mass and Energy ─────────────────────────────────────────
    tab_mass, tab_energy = st.tabs(["⚖️ Mass Balance", "⚡ Energy Balance"])

    with tab_mass:
        st.subheader(f"Mass Balance — {cr.config_label}")
        st.caption("Wet mass flows in t/day through the process train.")

        ps_wet  = site.ps_ds_tpd / (site.ps_ts_pct / 100)
        was_wet = site.was_ds_tpd / (site.was_ts_pct / 100)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total feed",     f"{ps_wet + was_wet:.1f} t/d wet")
        m2.metric("Biogas",         f"{cr.biogas_m3_per_d:,.0f} m³/d")
        m3.metric("Dewatered cake", f"{cr.wet_cake_t_per_day:.1f} t/d",
                  delta=f"{cr.cake_ds_pct:.0f}% DS")
        m4.metric("VS destruction", f"{cr.vsr_pct:.1f}%")

        nodes, links, recycle_lbl = _mass_nodes_links(selected, cr, site)
        _render_sankey(
            nodes, links,
            unit="t/day",
            title=f"Mass Balance — {cr.config_label}",
            height=500,
            recycle_label=recycle_lbl,
        )

        if selected == "solidstream":
            st.info(
                "**SolidStream note:** Hot centrate recycle (77°C) is shown as a terminal "
                "output node rather than a loop, as D3 Sankey does not support cycles. "
                "In reality this stream returns to the digester inlet, reducing digester "
                "heating demand by the amount shown.",
                icon="ℹ️",
            )

        st.caption(
            "Mass balance closed at digester system boundary. "
            "Moisture evaporation (~2% of feed) excluded from centrate/cake split. "
            "Biogas density assumed 1.2 kg/m³. All values screening-grade ±15%."
        )

    with tab_energy:
        st.subheader(f"Energy Balance — {cr.config_label}")
        st.caption("Energy flows in kW through CHP, waste heat recovery, and process heat sinks.")

        chp_eff = site.chp_eff_pct / 100
        fuel_kw = cr.elec_gross_kw / max(chp_eff, 0.01)
        heat_kw = fuel_kw * 0.45
        biogas_kw = cr.biogas_gj_per_d * 1000 / 86.4

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Biogas LHV",    f"{biogas_kw:,.0f} kW")
        e2.metric("CHP gross",     f"{cr.elec_gross_kw:,.0f} kW",
                  delta=f"{site.chp_eff_pct:.0f}% efficiency")
        e3.metric("Net export",    f"{cr.elec_net_kw:,.0f} kW")
        surplus = getattr(cr, "heat_surplus_kw", 0.0)
        e4.metric("Heat balance",  f"{surplus:+,.0f} kW",
                  delta="self-sufficient" if surplus >= 0 else "boiler required",
                  delta_color="normal" if surplus >= 0 else "inverse")

        e_nodes, e_links = _energy_nodes_links(selected, cr, site)
        _render_sankey(
            e_nodes, e_links,
            unit="kW",
            title=f"Energy Balance — {cr.config_label}",
            height=520,
        )

        if selected in ("pre_thp", "solidstream"):
            thp_kw = getattr(cr, "thp_steam_demand_kw", 0.0)
            ds_total = site.ps_ds_tpd + site.was_ds_tpd
            st.caption(
                f"THP steam demand: {thp_kw:,.0f} kW (from Cambi Melbourne ETP memo, scaled to {ds_total:.0f} tDS/day). "
                f"CHP waste heat available: {heat_kw:,.0f} kW. "
                + ("SolidStream hot centrate recycle reduces digester demand by "
                   f"{ds_total * 10.5:,.0f} kW. " if selected == "solidstream" else "")
                + ("**Self-sufficient on heat — no gas boiler required.**"
                   if surplus >= 0 else
                   f"**Supplementary boiler required: {abs(surplus):,.0f} kW deficit.**")
            )
        else:
            st.caption(
                f"CHP waste heat available: {heat_kw:,.0f} kW. "
                f"Digester heating demand: {(site.ps_ds_tpd + site.was_ds_tpd) * 26.7:,.0f} kW. "
                f"Heat surplus available for other uses: {max(0, surplus):,.0f} kW. "
                "All values screening-grade ±15%."
            )
