"""
apps/biosolids_app/pages/page_08_carbon.py
BioPoint V1 — Carbon & GHG Lifecycle View (Module C).

Five-way carbon destiny, Scope 1/2/3 GHG inventory, grid scenario band,
biogenic CO2 convention display, anti-greenwashing flags.

Reads from bp_result in session state — runs after the main pathway engine.
Carbon/GHG is computed on-demand and cached in session state.

ph2o Consulting — BioPoint V1 — v25B01
"""
import sys
from pathlib import Path
import streamlit as st
import pandas as pd

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


def _get_result():
    if "bp_result" not in st.session_state:
        st.warning("Run the BioPoint analysis first (Inputs page → ▶ Run BioPoint Analysis).")
        return None
    return st.session_state["bp_result"]


def _get_inputs():
    if "bp_inputs" not in st.session_state:
        return None
    return st.session_state["bp_inputs"]


def _run_carbon(result, inputs, ghg_inputs):
    """Build balances, run fate and GHG engines, return (balances, fates, ghgs)."""
    from engine.carbon_adapter import build_pathway_balances
    from engine.carbon_fate import run_carbon_fate_all
    from engine.carbon_ghg import run_ghg_all

    measured_c = st.session_state.get("bp_carbon_measured_pct")
    balances = build_pathway_balances(result, inputs, measured_c)
    fates    = run_carbon_fate_all(balances)
    ghgs     = run_ghg_all(balances, fates, ghg_inputs)
    return balances, fates, ghgs


def _build_ghg_inputs():
    """Build GHGInputs from sidebar/session state selections."""
    from engine.carbon_ghg import GHGInputs
    from engine.ghg_coefficients import GRID_INTENSITY_BY_STATE

    state    = st.session_state.get("bp_ghg_grid_state", "NSW")
    custom_i = st.session_state.get("bp_ghg_custom_intensity", 0.55)
    if state == "Custom":
        current_i = custom_i
    else:
        current_i = GRID_INTENSITY_BY_STATE.get(state, 0.55)

    return GHGInputs(
        grid_state=state,
        grid_intensity_current_kg_per_kwh=current_i,
        grid_intensity_2035_kg_per_kwh=st.session_state.get("bp_ghg_2035", 0.25),
        grid_intensity_net_zero_kg_per_kwh=st.session_state.get("bp_ghg_nz", 0.05),
        biogenic_co2_convention=st.session_state.get("bp_ghg_biogenic", "carbon_neutral"),
    )


# ── COLOUR MAP ────────────────────────────────────────────────────────────────
DESTINY_COLOURS = {
    "Sequestered (durable removal)":           "#2e7d32",   # dark green
    "Energy utilisation (fossil displacement)": "#1565c0",   # blue
    "Soil / delayed oxidation":                "#795548",   # brown
    "Oxidised to atmosphere (biogenic CO2)":   "#e0e0e0",   # light grey
    "Fugitive methane":                        "#ff6f00",   # amber
}

DESTINY_SHORT = {
    "Sequestered (durable removal)":           "Sequestered",
    "Energy utilisation (fossil displacement)": "Energy",
    "Soil / delayed oxidation":                "Soil/delayed",
    "Oxidised to atmosphere (biogenic CO2)":   "Oxidised",
    "Fugitive methane":                        "Fugitive CH₄",
}


def _destiny_bar_html(destiny: dict, carbon_feed: float) -> str:
    """
    Build a 100%-stacked horizontal bar as inline HTML.
    Each segment is proportional to its share of feed carbon.
    Shows removal vs displacement separation visually.
    """
    if carbon_feed <= 0:
        return "<p>No carbon feed.</p>"

    segs = []
    for cat, val in destiny.items():
        pct = val / carbon_feed * 100 if carbon_feed > 0 else 0
        if pct < 0.5:
            continue
        colour = DESTINY_COLOURS.get(cat, "#bdbdbd")
        short  = DESTINY_SHORT.get(cat, cat[:10])
        segs.append(
            f'<div style="display:inline-block;width:{pct:.1f}%;background:{colour};'
            f'height:32px;line-height:32px;text-align:center;font-size:11px;'
            f'color:{"#fff" if colour not in ("#e0e0e0",) else "#555"};'
            f'overflow:hidden;white-space:nowrap;" title="{cat}: {pct:.1f}%">'
            f'{short if pct > 8 else ""}</div>'
        )
    bar = "".join(segs)
    return (
        f'<div style="width:100%;font-family:sans-serif;border:1px solid #e0e0e0;'
        f'border-radius:4px;overflow:hidden;">{bar}</div>'
    )


# ── RENDER ────────────────────────────────────────────────────────────────────
def render():
    st.header("🌍 Carbon & GHG Lifecycle")
    st.caption(
        "Five-way carbon destiny, Scope 1/2/3 GHG inventory, and anti-greenwashing flags. "
        "Screening-grade — ±30% uncertainty. Run the BioPoint analysis first."
    )

    result = _get_result()
    if not result:
        return

    inputs = _get_inputs()
    if not inputs:
        # Reconstruct inputs from session state (same as page_02_results)
        try:
            from engine.input_schema import (
                BioPointV1Inputs, FeedstockInputsV2, AssetInputs, StrategicInputs
            )
            inputs = BioPointV1Inputs(
                feedstock=FeedstockInputsV2(
                    dry_solids_tpd=st.session_state.get("bp_ds_tpd", 10.0),
                    dewatered_ds_percent=st.session_state.get("bp_feed_ds_pct", 20.0),
                    volatile_solids_percent=st.session_state.get("bp_vs_pct", 70.0),
                    gross_calorific_value_mj_per_kg_ds=st.session_state.get("bp_gcv", 12.0),
                    sludge_type=st.session_state.get("bp_sludge_type", "blended"),
                    feedstock_variability=st.session_state.get("bp_variability", "moderate"),
                    pfas_present=st.session_state.get("bp_pfas", "unknown"),
                ),
                assets=AssetInputs(
                    anaerobic_digestion_present=st.session_state.get("bp_ad", True),
                    chp_present=st.session_state.get("bp_chp", False),
                    thp_present=st.session_state.get("bp_thp", False),
                    waste_heat_available_kwh_per_day=st.session_state.get("bp_waste_heat", 0.0),
                    local_power_price_per_kwh=st.session_state.get("bp_electricity", 0.18),
                    fuel_price_per_gj=st.session_state.get("bp_fuel", 14.0),
                    disposal_cost_per_tds=st.session_state.get("bp_disposal", 180.0),
                    transport_cost_per_tonne_km=st.session_state.get("bp_transport", 0.25),
                    average_transport_distance_km=st.session_state.get("bp_avg_km", 50.0),
                ),
                strategic=StrategicInputs(
                    optimisation_priority=st.session_state.get("bp_priority", "balanced"),
                    regulatory_pressure=st.session_state.get("bp_reg", "moderate"),
                    carbon_credit_value_per_tco2e=st.session_state.get("bp_carbon_price", 40.0),
                    biochar_market_confidence=st.session_state.get("bp_biochar_mkt", "low"),
                    land_constraint=st.session_state.get("bp_land", "low"),
                    social_licence_pressure=st.session_state.get("bp_social", "low"),
                    discount_rate_pct=st.session_state.get("bp_discount_rate", 7.0),
                    asset_life_years=int(st.session_state.get("bp_asset_life", 25)),
                ),
            )
        except Exception as ex:
            st.error(f"Could not reconstruct inputs: {ex}. Return to Inputs page and re-run.")
            return

    # ── GHG SCENARIO SETTINGS ───────────────────────────────────────────────
    with st.expander("⚙️ GHG scenario settings", expanded=False):
        from engine.ghg_coefficients import GRID_INTENSITY_BY_STATE

        c1, c2, c3 = st.columns(3)
        with c1:
            st.selectbox(
                "Grid state / territory",
                options=list(GRID_INTENSITY_BY_STATE.keys()),
                index=list(GRID_INTENSITY_BY_STATE.keys()).index(
                    st.session_state.get("bp_ghg_grid_state", "NSW")),
                key="bp_ghg_grid_state",
            )
            if st.session_state.get("bp_ghg_grid_state") == "Custom":
                st.number_input(
                    "Custom grid intensity (kgCO₂e/kWh)",
                    0.0, 2.0,
                    st.session_state.get("bp_ghg_custom_intensity", 0.55),
                    step=0.01, format="%.3f",
                    key="bp_ghg_custom_intensity",
                )
        with c2:
            st.number_input(
                "2035 grid intensity (kgCO₂e/kWh)",
                0.0, 1.0,
                st.session_state.get("bp_ghg_2035", 0.25),
                step=0.01, format="%.2f",
                key="bp_ghg_2035",
            )
            st.number_input(
                "Net-zero grid intensity (kgCO₂e/kWh)",
                0.0, 0.5,
                st.session_state.get("bp_ghg_nz", 0.05),
                step=0.01, format="%.3f",
                key="bp_ghg_nz",
            )
        with c3:
            st.selectbox(
                "Biogenic CO₂ convention",
                ["carbon_neutral", "count_all"],
                index=["carbon_neutral", "count_all"].index(
                    st.session_state.get("bp_ghg_biogenic", "carbon_neutral")),
                key="bp_ghg_biogenic",
                help=(
                    "carbon_neutral (IPCC default): biogenic CO₂ excluded from net GHG. "
                    "count_all: biogenic CO₂ included (conservative)."
                ),
            )
            st.caption(
                "🔵 Convention shown: **"
                + ("carbon_neutral — biogenic CO₂ excluded from net GHG total (IPCC default)"
                   if st.session_state.get("bp_ghg_biogenic", "carbon_neutral") == "carbon_neutral"
                   else "count_all — biogenic CO₂ counted in net GHG (conservative)")
                + "**"
            )
            st.number_input(
                "Measured carbon (% of DS) — optional",
                0.0, 60.0,
                st.session_state.get("bp_carbon_measured_pct", 0.0),
                step=0.5, format="%.1f",
                key="bp_carbon_measured_pct",
                help="If 0: carbon derived from VS% × 0.50 (default). Enter measured value from ultimate analysis to override.",
            )

    # ── RUN CARBON ENGINE ────────────────────────────────────────────────────
    run_carbon = st.button("▶ Run Carbon & GHG Analysis", type="primary")

    cache_key = "bp_carbon_result"
    if run_carbon or cache_key not in st.session_state:
        ghg_inputs = _build_ghg_inputs()
        measured_pct = st.session_state.get("bp_carbon_measured_pct", 0.0)
        measured_arg = measured_pct if measured_pct > 0 else None
        with st.spinner("Running carbon fate and GHG engine across all pathways..."):
            try:
                balances, fates, ghgs = _run_carbon(result, inputs, ghg_inputs)
                st.session_state[cache_key] = (balances, fates, ghgs, ghg_inputs)
            except Exception as ex:
                st.error(f"Carbon engine error: {ex}")
                st.exception(ex)
                return
    else:
        balances, fates, ghgs, ghg_inputs = st.session_state[cache_key]

    fss = result["flowsheets"]

    # Build lookup by pathway_type
    fate_by_type = {f.pathway_type: f for f in fates if not f.pathway_type.startswith("hybrid_")}
    ghg_by_type  = {g.pathway_type: g for g in ghgs  if not g.pathway_type.startswith("hybrid_")}
    bal_by_type  = {b.pathway_type: b for b in balances if not b.pathway_type.startswith("hybrid_")}

    # ── CONVENTION NOTICE ────────────────────────────────────────────────────
    convention = ghg_inputs.biogenic_co2_convention
    if convention == "carbon_neutral":
        st.info(
            "**Convention: carbon-neutral (IPCC default).** "
            "Biogenic CO₂ from decomposition of organic waste is excluded from the net GHG total. "
            "Biogenic CO₂ quantities are shown separately below and in each pathway detail. "
            "Change convention in the ⚙️ settings above."
        )
    else:
        st.warning(
            "**Convention: count-all.** "
            "Biogenic CO₂ is included in Scope 1 and net GHG totals. "
            "This is a conservative non-IPCC approach. "
            "Net GHG figures will be higher than under the carbon-neutral convention."
        )

    st.divider()

    # ── RANKED TABLE: NET GHG ADDED ──────────────────────────────────────────
    st.subheader("Pathway rankings — GHG added")
    st.caption(
        "Net GHG (current grid) per tDS. Negative = net sink at current grid intensity. "
        "Removal and displacement are shown separately. Uncertainty ±30%."
    )

    rows = []
    for fs in fss:
        ptype = fs.pathway_type
        fate  = fate_by_type.get(ptype)
        ghg   = ghg_by_type.get(ptype)
        if not fate or not ghg:
            continue
        net   = ghg.current.net_ghg_kg_co2e
        gross = ghg.current.gross_ghg_kg_co2e
        disp  = ghg.current.displacement_credits_kg_co2e
        rem   = ghg.current.removal_credits_kg_co2e
        seq_pct = (fate.carbon_sequestered / max(fate.carbon_feed_kg_per_tds, 1)) * 100

        # Flags
        flags = []
        if ghg.net_negative_is_displacement:
            flags.append("⚠️D")
        if ghg.grid_dependent:
            flags.append("⚡")
        if not fate.carbon_closure_passes:
            flags.append("❗C")

        rows.append({
            "Rank":        fs.rank,
            "Pathway":     fs.name,
            "Net GHG (kg CO₂e/tDS)": f"{net:+,.0f}",
            "Gross GHG":   f"{gross:+,.0f}",
            "Displacement": f"−{disp:,.0f}",
            "Removal":     f"−{rem:,.0f}",
            "Sequestered %": f"{seq_pct:.0f}%",
            "Flags":       " ".join(flags) if flags else "—",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption(
        "**Flags:** ⚠️D = net-negative driven by displacement not removal "
        "| ⚡ = Scope 2 grid-dependent "
        "| ❗C = carbon closure >5%"
    )

    st.divider()

    # ── CARBON DESTINY STRIPS ────────────────────────────────────────────────
    st.subheader("Carbon destiny — where does the feed carbon go?")
    st.caption(
        "100% stacked bars show the five-way split per pathway. "
        "🟢 Sequestered (durable removal) is always separate from 🔵 Energy (displacement)."
    )

    # Legend
    legend_html = " ".join([
        f'<span style="display:inline-block;width:14px;height:14px;background:{c};'
        f'border-radius:2px;margin-right:4px;vertical-align:middle;"></span>'
        f'<span style="font-size:12px;margin-right:12px;">{DESTINY_SHORT[cat]}</span>'
        for cat, c in DESTINY_COLOURS.items()
    ])
    st.markdown(
        f'<div style="margin-bottom:8px;">{legend_html}</div>',
        unsafe_allow_html=True
    )

    for fs in fss:
        ptype = fs.pathway_type
        fate  = fate_by_type.get(ptype)
        ghg   = ghg_by_type.get(ptype)
        if not fate:
            continue

        C_feed = fate.carbon_feed_kg_per_tds
        seq_pct = fate.carbon_sequestered / max(C_feed, 1) * 100
        en_pct  = fate.carbon_energy       / max(C_feed, 1) * 100

        # Pathway label with closure indicator
        closure_ok = "✅" if fate.carbon_closure_passes else f"⚠️ closure {fate.carbon_closure_error_pct:.0f}%"
        net_label = (
            f"{ghg.current.net_ghg_kg_co2e:+,.0f} kg CO₂e/tDS"
            if ghg else "—"
        )

        col_label, col_bar = st.columns([2, 5])
        with col_label:
            st.markdown(
                f"**#{fs.rank} {fs.name}**  \n"
                f"<span style='font-size:12px;color:#555;'>"
                f"Net GHG: {net_label} | {closure_ok}</span>",
                unsafe_allow_html=True
            )
        with col_bar:
            bar_html = _destiny_bar_html(fate.carbon_destiny, C_feed)
            st.markdown(bar_html, unsafe_allow_html=True)

        # Anti-greenwashing flag per pathway
        if ghg and ghg.net_negative_is_displacement:
            st.warning(
                f"⚠️ **{fs.name}: Net-negative is displacement, not removal.** "
                f"The beneficial GHG outcome is driven by fossil fuel displacement "
                f"(energy recovery, {en_pct:.0f}% of feed carbon as energy). "
                f"Only {seq_pct:.0f}% is durably sequestered. "
                "If the grid decarbonises, this credit will diminish."
            )

    st.divider()

    # ── PER-PATHWAY GHG DETAIL ───────────────────────────────────────────────
    st.subheader("GHG inventory — per pathway")

    pathway_names = {fs.pathway_type: fs.name for fs in fss}
    selected_ptype = st.selectbox(
        "Select pathway for detail",
        options=[fs.pathway_type for fs in fss if fs.pathway_type in ghg_by_type],
        format_func=lambda p: pathway_names.get(p, p),
        key="bp_carbon_selected_pathway",
    )

    fate = fate_by_type.get(selected_ptype)
    ghg  = ghg_by_type.get(selected_ptype)
    bal  = bal_by_type.get(selected_ptype)

    if not fate or not ghg:
        st.info("No carbon data for this pathway.")
    else:
        # ── Grid scenario band ───────────────────────────────────────────────
        st.markdown("#### Net GHG across grid scenarios")
        g1, g2, g3 = st.columns(3)
        with g1:
            net_c = ghg.current.net_ghg_kg_co2e
            st.metric(
                f"Current grid ({ghg_inputs.grid_intensity_current_kg_per_kwh:.2f} kgCO₂e/kWh)",
                f"{net_c:+,.0f} kg CO₂e/tDS",
                delta=f"±{abs(net_c)*0.30:,.0f} (±30%)",
                delta_color="off",
            )
        with g2:
            net_35 = ghg.scenario_2035.net_ghg_kg_co2e
            st.metric(
                f"2035 grid ({ghg_inputs.grid_intensity_2035_kg_per_kwh:.2f} kgCO₂e/kWh)",
                f"{net_35:+,.0f} kg CO₂e/tDS",
                delta=f"{net_35 - net_c:+,.0f} vs current",
                delta_color="inverse",
            )
        with g3:
            net_nz = ghg.net_zero.net_ghg_kg_co2e
            st.metric(
                f"Net-zero grid ({ghg_inputs.grid_intensity_net_zero_kg_per_kwh:.3f} kgCO₂e/kWh)",
                f"{net_nz:+,.0f} kg CO₂e/tDS",
                delta=f"{net_nz - net_c:+,.0f} vs current",
                delta_color="inverse",
            )

        # Grid-dependent flag
        if ghg.grid_dependent:
            st.info(
                "⚡ **Grid-dependent pathway:** Scope 2 electricity import or export "
                "accounts for >40% of the gross GHG figure. "
                "Results are sensitive to grid intensity — review the 2035 and net-zero scenarios."
            )

        # ── Five-way destiny ────────────────────────────────────────────────
        st.markdown("#### Carbon destiny (five-way split)")
        C_feed = fate.carbon_feed_kg_per_tds

        dest_rows = []
        for cat, val in fate.carbon_destiny.items():
            pct = val / C_feed * 100 if C_feed > 0 else 0
            dest_rows.append({
                "Category":        cat,
                "kg C / tDS":      f"{val:.1f}",
                "% of feed":       f"{pct:.1f}%",
                "Type":            "REMOVAL" if "Sequestered" in cat
                                   else ("DISPLACEMENT" if "Energy" in cat
                                         else "other"),
            })
        st.dataframe(
            pd.DataFrame(dest_rows),
            use_container_width=True,
            hide_index=True,
        )

        # Closure
        closure_colour = "success" if fate.carbon_closure_passes else "error"
        getattr(st, closure_colour)(
            f"Carbon balance closure: {fate.carbon_closure_error_pct:.1f}% error "
            f"({'within 5% tolerance ✓' if fate.carbon_closure_passes else 'EXCEEDS 5% — review partition coefficients'})"
        )

        # Biogenic CO2
        st.caption(
            f"**Biogenic CO₂:** {fate.biogenic_co2_kg_per_tds * 44/12:.1f} kg CO₂/tDS "
            f"({'excluded from net GHG' if convention == 'carbon_neutral' else 'INCLUDED in net GHG'} "
            f"under current convention)."
        )

        # ── Destiny statement ────────────────────────────────────────────────
        st.markdown("#### Plain-language destiny")
        st.markdown(fate.destiny_statement)

        # ── GHG line items ──────────────────────────────────────────────────
        with st.expander("Full GHG line-item breakdown (current grid)"):
            line_rows = []
            for li in ghg.current.line_items:
                val = li.kg_co2e_per_tds
                line_rows.append({
                    "Line item": li.label,
                    "Scope":     li.scope,
                    "kg CO₂e/tDS": f"{val:+,.2f}",
                    "Type":      "Credit" if li.is_credit else "Emission",
                    "Note":      li.note[:80] if li.note else "",
                })
            st.dataframe(
                pd.DataFrame(line_rows),
                use_container_width=True,
                hide_index=True,
            )

            # Scope totals
            s1 = ghg.current.scope1_kg_co2e
            s2 = ghg.current.scope2_kg_co2e
            s3 = ghg.current.scope3_kg_co2e
            disp = ghg.current.displacement_credits_kg_co2e
            rem  = ghg.current.removal_credits_kg_co2e
            net  = ghg.current.net_ghg_kg_co2e
            net_incl_rem = ghg.current.net_ghg_including_removal_kg_co2e

            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Scope 1", f"{s1:+,.1f}")
            sc2.metric("Scope 2", f"{s2:+,.1f}")
            sc3.metric("Scope 3", f"{s3:+,.1f}")
            sc4.metric("Displacement credits", f"−{disp:,.1f}")

            st.markdown(
                f"**Net GHG** (gross − displacement): **{net:+,.1f} kg CO₂e/tDS**  \n"
                f"**Net GHG including removal** (net − sequestration): **{net_incl_rem:+,.1f} kg CO₂e/tDS**  \n"
                f"*(Removal shown separately — never netted against displacement)*"
            )

        # ── N fate summary ──────────────────────────────────────────────────
        with st.expander("N fate summary"):
            nf = [
                ("N in product", fate.n_in_product_kg_per_tds),
                ("N in sidestream (centrate)", fate.n_in_sidestream_kg_per_tds),
                ("N volatilised (thermal)", fate.n_volatilised_kg_per_tds),
                ("N as N₂O", fate.n_as_n2o_kg_per_tds),
                ("N to atmosphere (denitrification)", fate.n_to_atmosphere_kg_per_tds),
                ("N in ash", fate.n_in_ash_kg_per_tds),
            ]
            nf_rows = [{"N fate": k, "kg N/tDS": f"{v:.2f}"} for k, v in nf if v > 0]
            st.dataframe(pd.DataFrame(nf_rows), use_container_width=True, hide_index=True)
            st.caption(
                f"N feed: {fate.n_feed_kg_per_tds:.1f} kg N/tDS | "
                f"N closure: {fate.n_closure_error_pct:.1f}% error "
                f"({'✓' if fate.n_closure_passes else '⚠️'})"
            )

        # ── Avoided emissions ────────────────────────────────────────────────
        with st.expander("Displacement credits detail"):
            st.markdown(
                "**DISPLACEMENT credits only** — not removal. "
                "These are fossil energy or fertiliser substitution benefits. "
                "They diminish as the grid decarbonises or as fossil fertiliser use is regulated."
            )
            av_rows = [
                {"Credit": "Avoided N fertiliser", "kg CO₂e/tDS": f"{fate.avoided_n_fertiliser_kg_co2e:.2f}"},
                {"Credit": "Avoided P fertiliser", "kg CO₂e/tDS": f"{fate.avoided_p_fertiliser_kg_co2e:.2f}"},
                {"Credit": "Avoided grid electricity (current)", "kg CO₂e/tDS": f"{ghg.current.displacement_credits_kg_co2e - fate.avoided_n_fertiliser_kg_co2e - fate.avoided_p_fertiliser_kg_co2e:.2f}"},
            ]
            st.dataframe(pd.DataFrame(av_rows), use_container_width=True, hide_index=True)
            st.caption(
                f"Total displacement credits: {ghg.current.displacement_credits_kg_co2e:.1f} kg CO₂e/tDS "
                f"| Removal credits (sequestration): {ghg.current.removal_credits_kg_co2e:.1f} kg CO₂e/tDS"
            )

    st.divider()

    # ── CROSS-PATHWAY COMPARISON ─────────────────────────────────────────────
    with st.expander("Cross-pathway GHG comparison table"):
        cmp_rows = []
        for fs in fss:
            ptype = fs.pathway_type
            fate  = fate_by_type.get(ptype)
            ghg   = ghg_by_type.get(ptype)
            if not fate or not ghg:
                continue
            cmp_rows.append({
                "Pathway":          fs.name,
                "Scope 1":          f"{ghg.current.scope1_kg_co2e:+,.0f}",
                "Scope 2":          f"{ghg.current.scope2_kg_co2e:+,.0f}",
                "Scope 3":          f"{ghg.current.scope3_kg_co2e:+,.0f}",
                "Displacement":     f"−{ghg.current.displacement_credits_kg_co2e:,.0f}",
                "Removal":          f"−{ghg.current.removal_credits_kg_co2e:,.0f}",
                "Net GHG":          f"{ghg.current.net_ghg_kg_co2e:+,.0f}",
                "Net incl. removal":f"{ghg.current.net_ghg_including_removal_kg_co2e:+,.0f}",
                "Biogenic CO₂":     f"{ghg.current.biogenic_co2_kg_co2e:,.0f}",
                "2035 net GHG":     f"{ghg.scenario_2035.net_ghg_kg_co2e:+,.0f}",
            })
        st.dataframe(pd.DataFrame(cmp_rows), use_container_width=True, hide_index=True)
        st.caption(
            "All figures in kg CO₂e per tDS. "
            f"GWP basis: AR5 100-yr (CH₄=28, N₂O=265). "
            f"Convention: {convention}. "
            "Uncertainty ±30% (screening-grade)."
        )
