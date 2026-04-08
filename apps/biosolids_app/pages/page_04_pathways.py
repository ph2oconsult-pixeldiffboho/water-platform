"""
apps/biosolids_app/pages/page_04_pathways.py
BioPoint V1 — ITS Classification & Thermal Pathway Detail.
"""
import streamlit as st
import pandas as pd


def _get_result():
    if "bp_result" not in st.session_state:
        st.warning("Run the analysis first (Inputs page).")
        return None
    return st.session_state["bp_result"]


def render():
    st.header("🛡️ ITS Classification & Thermal Pathways")

    result = _get_result()
    if not result:
        return

    fss   = result["flowsheets"]
    its   = result["its_classification"]
    tb    = result["thermal_biochar"]
    vv    = result["vendor_validation"]

    # ── System statement ──────────────────────────────────────────────────
    st.info(its.system_statement)

    # ── ITS levels ────────────────────────────────────────────────────────
    st.subheader("PFAS destruction classification — all pathways")

    # Level summary
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("L1 Transfer", its.level1_count, help="PFAS transferred — NOT ACCEPTABLE")
    with c2:
        st.metric("L2 Partial Thermal", its.level2_count,
                  help="PFAS uncertain — CONDITIONAL")
    with c3:
        st.metric("L3 ITS", its.level3_count,
                  help="Design-based destruction — ACCEPTABLE with validation")
    with c4:
        st.metric("L4 Incineration", its.level4_count,
                  help="Validated destruction — HIGH CONFIDENCE")

    its_rows = []
    for c in its.classifications:
        its_rows.append({
            "Pathway": c.flowsheet_name,
            "Level": c.its_level_short,
            "PFAS outcome": c.pfas_outcome,
            "Status": c.pfas_status,
            "Evidence": c.pfas_evidence_type,
        })
    st.dataframe(pd.DataFrame(its_rows), use_container_width=True, hide_index=True)

    # Upgrade paths for L2 pathways
    l2_paths = [c for c in its.classifications if c.its_level == 2]
    if l2_paths:
        with st.expander("ITS upgrade path — how to reach Level 3"):
            for c in l2_paths:
                st.markdown(f"**{c.flowsheet_name}**")
                st.markdown(c.upgrade_to_l3)
                st.divider()

    # ── Thermal biochar detail ────────────────────────────────────────────
    if tb and tb.results:
        st.subheader("Thermal pathway detail — product, energy & trade-off")

        target_ptypes = ["pyrolysis", "incineration", "gasification", "HTC", "HTC_sidestream"]
        for ptype in target_ptypes:
            res = tb.results.get(ptype)
            if not res:
                continue

            with st.expander(f"{res.pathway_name} — {res.system_classification}"):
                b1, b2, b3, b4, b5 = st.columns(5)
                with b1:
                    st.metric("PFAS destroyed?", res.board_pfas_destroyed)
                with b2:
                    st.metric("Drying achievable?",
                              res.board_drying_achievable[:12])
                with b3:
                    st.metric("Biochar marketable?", res.board_biochar_marketable)
                with b4:
                    st.metric("Classification", res.system_classification)
                with b5:
                    st.metric("Green finance", "✅" if res.green_finance_eligible else "—")

                st.markdown(f"**Dominant value:** {res.board_dominant_value}")
                st.markdown(f"**Strategy:** {res.board_recommended_strategy[:200]}")

                if res.product:
                    prod = res.product
                    st.markdown(
                        f"**Product:** {prod.product_label} | "
                        f"Yield: {prod.biochar_yield_pct_ds:.0f}% DS "
                        f"= {prod.biochar_yield_t_per_day:.1f} t/day | "
                        f"Fixed C: {prod.fixed_carbon_pct:.0f}% | "
                        f"Market: ${prod.market_value_low:.0f}–${prod.market_value_high:.0f}/t"
                    )
                    st.caption(prod.marketability_note[:200])

    # ── Vendor claim validation ────────────────────────────────────────────
    if vv:
        st.subheader("Vendor claim validation")
        st.caption(vv.system_summary[:250])

        if vv.key_refutations:
            st.markdown("**Claims refuted at this feedstock condition:**")
            for ref in vv.key_refutations[:5]:
                st.error(f"❌ {ref[:120]}")

        for ptype, rpt in vv.reports.items():
            refuted = [c for c in rpt.claim_validations if c.verdict == "REFUTED"]
            supported = [c for c in rpt.claim_validations if c.verdict == "SUPPORTED"]
            if not refuted and not supported:
                continue
            with st.expander(
                f"{ptype} — S:{rpt.claims_supported} C:{rpt.claims_conditional} "
                f"R:{rpt.claims_refuted} — {rpt.system_fit_summary[:50]}"
            ):
                for c in rpt.claim_validations:
                    icon = {"SUPPORTED": "✅", "CONDITIONAL": "🟡",
                            "REFUTED": "❌", "UNVERIFIABLE": "⬜"}.get(c.verdict, "")
                    st.markdown(f"{icon} **{c.verdict}** — {c.claim_text[:80]}")
                    if c.validation_narrative:
                        st.caption(c.validation_narrative[:200])
