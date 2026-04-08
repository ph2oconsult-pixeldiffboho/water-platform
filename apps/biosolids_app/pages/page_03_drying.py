"""
apps/biosolids_app/pages/page_03_drying.py
BioPoint V1 — Drying Dominance, Coupling & Siting.
"""
import streamlit as st
import pandas as pd


def _get_result():
    if "bp_result" not in st.session_state:
        st.warning("Run the analysis first (Inputs page).")
        return None
    return st.session_state["bp_result"]


def render():
    st.header("🔥 Drying, Coupling & Siting")

    result = _get_result()
    if not result:
        return

    fss = result["flowsheets"]
    dd  = result["drying_dominance"]
    cc  = result["coupling_classification"]
    sa  = result["siting_assessment"]
    pc  = result["preconditioning"]

    # ── Drying dominance ──────────────────────────────────────────────────
    st.subheader("Drying feasibility gate")

    if dd.system_water_constrained:
        st.error(dd.system_water_constrained_label)
    else:
        st.info(dd.drying_dominance_narrative[:300])

    dry_rows = []
    for fs in fss:
        ddr = fs.drying_dominance
        if not ddr:
            continue
        dry_rows.append({
            "Pathway": fs.pathway_type,
            "Drying / feedstock": f"{ddr.drying_as_pct_of_feedstock_energy:.0f}%",
            "Dominance": ddr.drying_dominance_label,
            "Ext. kWh/tDS": f"{ddr.external_energy_kwh_per_tds:,.0f}",
            "Neutrality DS%": (
                f"{ddr.ds_for_energy_neutrality_pct:.0f}%"
                if ddr.ds_for_energy_neutrality_pct else "N/A"
            ),
            "Gate": "✅ PASS" if ddr.can_rank_as_preferred else "❌ FAIL",
            "DS viability": ddr.ds_viability_label[:70] if ddr.ds_viability_label else "",
            "Penalty": f"{ddr.score_penalty:+.0f}",
        })
    st.dataframe(pd.DataFrame(dry_rows), use_container_width=True, hide_index=True)

    # ── Preconditioning ───────────────────────────────────────────────────
    st.subheader("📐 Preconditioning pathways")
    st.caption(
        f"Base DS: {pc.base_ds_pct:.0f}% — "
        f"28% reachable: {'✅' if pc.any_scenario_reaches_28pct else '❌'} — "
        f"30% reachable: {'✅' if pc.any_scenario_reaches_30pct else '❌'}"
    )
    pc_rows = []
    for s in pc.scenarios:
        pc_rows.append({
            "Scenario": s.scenario_name,
            "DS%": f"{s.feed_ds_pct:.0f}%",
            "Reaches 28%": "✅" if s.threshold_28pct_reached else "—",
            "Reaches 30%": "✅" if s.threshold_30pct_reached else "—",
            "Drying energy saving (kWh/d)": f"+{s.drying_energy_reduction_kwh_d:,.0f}",
        })
    st.dataframe(pd.DataFrame(pc_rows), use_container_width=True, hide_index=True)

    st.info(
        "💡 The DS% uplift from preconditioning is the critical path to thermal viability. "
        "THP + filter press (PC05) delivers the largest drying energy saving."
    )

    # ── Coupling ──────────────────────────────────────────────────────────
    st.subheader("🔗 System coupling classification")
    st.caption(
        f"Tier 1 (Decoupled): {cc.tier1_count} — "
        f"Tier 2 (Partial): {cc.tier2_count} — "
        f"Tier 3 (Fully Coupled): {cc.tier3_count}"
    )
    cc_rows = []
    for c in cc.classifications:
        fs2 = next((f for f in fss if f.flowsheet_id == c.flowsheet_id), None)
        nh4pct = (fs2.mainstream_coupling.return_as_pct_of_plant_nh4
                  if fs2 and fs2.mainstream_coupling else 0)
        cc_rows.append({
            "Pathway": c.flowsheet_name,
            "Tier": c.coupling_tier_label,
            "Impact": c.mainstream_impact,
            "NH4 % plant N": f"{nh4pct:.1f}%",
            "Compliance risk": c.compliance_risk,
            "Score adj.": f"{c.net_coupling_score_adjustment:+.0f}",
        })
    st.dataframe(pd.DataFrame(cc_rows), use_container_width=True, hide_index=True)

    # ── Siting ────────────────────────────────────────────────────────────
    st.subheader("📍 Siting flexibility")
    modifiers = "Active — score adjustments applied" if sa.modifiers_applied else "Inactive"
    drivers = []
    if sa.land_constrained:   drivers.append("land constraint")
    if sa.social_licence_sensitive: drivers.append("social licence")
    if sa.multi_site_system:  drivers.append("multi-site system")
    st.caption(
        f"Siting modifiers: {modifiers}"
        + (f" ({', '.join(drivers)})" if drivers else "")
    )
    sit_rows = []
    for sp in sa.profiles:
        sit_rows.append({
            "Pathway": sp.flowsheet_name,
            "Flexibility": sp.flexibility_badge,
            "Location": sp.preferred_location[:30],
            "Planning risk": sp.planning_risk,
            "Footprint": sp.footprint_impact,
            "Score adj.": f"{sp.siting_score_adjustment:+.1f}",
        })
    st.dataframe(pd.DataFrame(sit_rows), use_container_width=True, hide_index=True)
