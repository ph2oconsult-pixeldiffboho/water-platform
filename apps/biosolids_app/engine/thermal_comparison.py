"""
BioPoint V1 — Thermal Comparison Engine.
Explicit head-to-head benchmarking of incineration vs pyrolysis vs gasification vs HTC.
Produces a structured verdict on incineration relative to alternatives.

Per spec: Do NOT treat incineration as inferior by default.
Explicitly state why it wins or loses on each dimension.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# COMPARISON DIMENSIONS (spec-mandated)
# ---------------------------------------------------------------------------

THERMAL_PATHWAYS = ["incineration", "thp_incineration", "pyrolysis", "gasification", "HTC"]

DIMENSION_LABELS = {
    "energy_balance":       "Energy balance",
    "drying_burden":        "Drying burden",
    "feedstock_tolerance":  "Feedstock tolerance / variability",
    "operability":          "Operability & technology maturity",
    "carbon_outcome":       "Carbon outcome",
    "cost":                 "Economics (net annual value)",
}


@dataclass
class ThermalComparisonRow:
    """One row of the comparison table — one pathway across all dimensions."""
    pathway_type: str = ""
    pathway_name: str = ""
    is_incineration: bool = False
    mandatory_benchmark: bool = False

    energy_balance:      str = ""   # e.g. "Surplus — combustion supports drying loop"
    drying_burden:       str = ""
    feedstock_tolerance: str = ""
    operability:         str = ""
    carbon_outcome:      str = ""
    cost:                str = ""

    # Traffic lights per dimension: G/A/R
    energy_rag:      str = "A"
    drying_rag:      str = "A"
    tolerance_rag:   str = "A"
    operability_rag: str = "A"
    carbon_rag:      str = "A"
    cost_rag:        str = "A"

    overall_rag: str = "A"
    rank_in_thermal_set: int = 0


@dataclass
class ThermalComparisonResult:
    """Full thermal comparison output."""
    rows: list = field(default_factory=list)          # List[ThermalComparisonRow]
    incineration_verdict: str = ""                    # Explicit verdict per spec
    incineration_preferred: bool = False
    incineration_preferred_reason: str = ""
    incineration_not_preferred_reason: str = ""
    preferred_thermal_pathway: str = ""
    comparison_narrative: str = ""
    large_scale_note: str = ""


def _rag(score: float, invert: bool = False) -> str:
    """Convert numeric score to RAG. invert=True for 'lower is better' dimensions."""
    if invert:
        score = 100 - score
    if score >= 65:
        return "G"
    elif score >= 40:
        return "A"
    else:
        return "R"


def run_thermal_comparison(all_flowsheets: list) -> Optional[ThermalComparisonResult]:
    """
    Compare all thermal pathways (incineration/pyrolysis/gasification/HTC)
    head-to-head across spec-mandated dimensions.
    Returns None if fewer than 2 thermal pathways are present.
    """
    thermal_fss = [
        fs for fs in all_flowsheets
        if fs.pathway_type in THERMAL_PATHWAYS
        and fs.mass_balance is not None
    ]
    if len(thermal_fss) < 2:
        return None

    rows = []
    for fs in thermal_fss:
        mb = fs.mass_balance
        dc = fs.drying_calc
        eb = fs.energy_balance
        cb = fs.carbon_balance
        econ = fs.economics
        risk = fs.risk
        compat = fs.compatibility
        ptype = fs.pathway_type

        # --- ENERGY BALANCE ---
        if eb.energy_status == "surplus":
            energy_str = f"Surplus ({eb.net_energy_kwh_per_day:+,.0f} kWh/d)"
            energy_rag = "G"
        elif eb.energy_status == "near-neutral":
            energy_str = f"Near-neutral ({eb.net_energy_kwh_per_day:+,.0f} kWh/d)"
            energy_rag = "A"
        else:
            energy_str = f"Deficit ({eb.net_energy_kwh_per_day:+,.0f} kWh/d)"
            energy_rag = "R"
        if eb.energy_closure_risk:
            energy_rag = "R"
            energy_str += " ⚠ closure risk"

        # Incineration note: combustion heat actively supports drying loop
        if ptype in ("incineration", "thp_incineration"):
            energy_str += ". Combustion heat supports drying — reduces external energy."

        # --- DRYING BURDEN ---
        if not dc.drying_required:
            drying_str = "None required"
            drying_rag = "G"
        else:
            net_ext = dc.net_external_drying_energy_kwh_per_day
            target = dc.target_ds_pct
            drying_str = f"To {target:.0f}% DS. External: {net_ext:,.0f} kWh/d"
            feedstock_kwh = eb.feedstock_energy_kwh_per_day
            burden_frac = net_ext / feedstock_kwh if feedstock_kwh > 0 else 0
            if burden_frac < 0.20:
                drying_rag = "G"
                drying_str += " (manageable)"
            elif burden_frac < 0.45:
                drying_rag = "A"
                drying_str += " (significant)"
            else:
                drying_rag = "R"
                drying_str += " (high — verify energy closure)"

        # --- FEEDSTOCK TOLERANCE ---
        compat_score = compat.score_numeric if compat else 50.0
        if ptype in ("incineration", "thp_incineration"):
            # Incineration has inherently high tolerance to variability
            fs_var = fs.inputs.feedstock.feedstock_variability
            var_bonus = {"high": 20, "moderate": 10, "low": 0}.get(fs_var, 0)
            tolerance_score = min(100, compat_score + var_bonus)
            tolerance_str = (
                f"High tolerance to variability ({fs_var}). "
                "Handles mixed/variable feed — key operational advantage."
            )
        else:
            tolerance_score = compat_score
            tolerance_str = compat.explanation[:80] if compat else "Not assessed"
        tolerance_rag = _rag(tolerance_score)

        # --- OPERABILITY ---
        op_map = {"Low": 80, "Moderate": 55, "High": 25}
        op_score = op_map.get(risk.process_operability_risk, 50)
        maturity = {
            "incineration":    "Established full-scale — thousands of operating plants globally.",
            "thp_incineration":"Established (THP) + established (incineration) — combined pathway proven.",
            "pyrolysis":       "Commercial-scale emerging — limited full-scale sewage sludge references.",
            "gasification":    "Emerging — full-scale sludge gasification limited; vendor selection critical.",
            "HTC":             "Commercial-scale pilots — limited full-scale utility references.",
            "HTC_sidestream":  "HTC + sidestream treatment — adds N removal maturity (SHARON/ANAMMOX proven).",
        }.get(ptype, "")
        operability_str = f"{risk.process_operability_risk} risk. {maturity}"
        operability_rag = _rag(op_score)

        # --- CARBON OUTCOME ---
        net_seq = cb.co2e_sequestered_t_per_day
        net_avoid = cb.co2e_avoided_t_per_day
        net_emit = cb.co2e_emitted_t_per_day
        net_carbon = net_seq + net_avoid - net_emit
        if net_carbon > 0.01:
            carbon_str = f"Net positive: +{net_carbon*365:.0f} tCO₂e/yr sequestered/avoided"
            carbon_rag = "G"
        elif net_carbon > -0.01:
            carbon_str = "Near neutral carbon outcome"
            carbon_rag = "A"
        else:
            carbon_str = f"Net emissions: {net_carbon*365:.0f} tCO₂e/yr"
            carbon_rag = "R"
        # Discount carbon RAG if sequestration is unvalidated (low confidence)
        if cb.carbon_credit_confidence == "low" and cb.co2e_sequestered_t_per_day > 0:
            if carbon_rag == "G":
                carbon_rag = "A"   # Downgrade — sequestration not yet marketable
            carbon_str += " (sequestration confidence: LOW — treat as potential, not base case)"
        if ptype in ("incineration", "thp_incineration"):
            carbon_str += ". All C oxidised — no sequestration; carbon avoidance vs landfill baseline."
        elif ptype == "pyrolysis":
            carbon_str += f". Biochar sequesters {cb.carbon_to_char_t_per_day*365:.0f} tC/yr."

        # --- COST ---
        net_val = econ.net_annual_value
        cost_str = f"Net annual: ${net_val:,.0f}/yr. Cost/tDS: ${econ.cost_per_tds_treated:.0f}"
        # Cost RAG: higher (less negative) net annual value = better
        # Normalise across thermal set
        all_net = [fs2.economics.net_annual_value for fs2 in thermal_fss if fs2.economics]
        if all_net:
            min_nv, max_nv = min(all_net), max(all_net)
            cost_score = (net_val - min_nv) / (max_nv - min_nv) * 100 if max_nv > min_nv else 50
        else:
            cost_score = 50.0
        cost_rag = _rag(cost_score)

        # --- OVERALL RAG ---
        rag_scores = {"G": 3, "A": 2, "R": 1}
        all_rags = [energy_rag, drying_rag, tolerance_rag, operability_rag, carbon_rag, cost_rag]
        avg_rag = sum(rag_scores[r] for r in all_rags) / len(all_rags)
        overall_rag = "G" if avg_rag >= 2.5 else ("A" if avg_rag >= 1.7 else "R")

        rows.append(ThermalComparisonRow(
            pathway_type=ptype,
            pathway_name=fs.name,
            is_incineration=(ptype in ("incineration", "thp_incineration")),
            mandatory_benchmark=fs.mandatory_benchmark,
            energy_balance=energy_str,
            drying_burden=drying_str,
            feedstock_tolerance=tolerance_str,
            operability=operability_str,
            carbon_outcome=carbon_str,
            cost=cost_str,
            energy_rag=energy_rag,
            drying_rag=drying_rag,
            tolerance_rag=tolerance_rag,
            operability_rag=operability_rag,
            carbon_rag=carbon_rag,
            cost_rag=cost_rag,
            overall_rag=overall_rag,
        ))

    # --- SORT BY OVERALL RAG + COST ---
    rag_order = {"G": 0, "A": 1, "R": 2}
    rows.sort(key=lambda r: (rag_order[r.overall_rag], -_get_net(thermal_fss, r.pathway_type)))
    for i, r in enumerate(rows):
        r.rank_in_thermal_set = i + 1

    # --- INCINERATION VERDICT ---
    incin_row = next((r for r in rows if r.is_incineration), None)
    preferred_row = rows[0] if rows else None

    incin_preferred = (incin_row and preferred_row and
                       incin_row.pathway_type == preferred_row.pathway_type)

    fs_input = thermal_fss[0].inputs.feedstock if thermal_fss else None
    ds_tpd = fs_input.dry_solids_tpd if fs_input else 0

    if incin_preferred:
        verdict = (
            "Incineration provides the most robust pathway under these feedstock conditions. "
            "High tolerance to variability, established operability, and positive energy balance "
            "with drying heat integration make it the strongest thermal option in this evaluation."
        )
        pref_reason = (
            f"Ranked #{incin_row.rank_in_thermal_set} of {len(rows)} thermal pathways. "
            f"Operability: {incin_row.operability_rag}. Energy: {incin_row.energy_rag}. "
            f"Feedstock tolerance: {incin_row.tolerance_rag}."
        )
        not_pref_reason = ""
    else:
        # Incineration is not preferred — state why specifically
        pref_type = preferred_row.pathway_type if preferred_row else "unknown"
        losing_dims = []
        if incin_row:
            if rag_order.get(incin_row.cost_rag, 1) > rag_order.get(preferred_row.cost_rag, 1):
                losing_dims.append("higher capital cost at this scale")
            if rag_order.get(incin_row.carbon_rag, 1) > rag_order.get(preferred_row.carbon_rag, 1):
                losing_dims.append("no carbon sequestration pathway (all carbon oxidised)")
        losing_str = "; ".join(losing_dims) if losing_dims else "lower overall score"
        pref_name = preferred_row.pathway_name if preferred_row else "alternative pathway"
        verdict = (
            f"Incineration is not preferred due to: {losing_str}. "
            f"{pref_name} scores higher under the current "
            "optimisation objective. Incineration remains viable as a fallback or "
            "co-treatment route — particularly if feedstock variability increases or "
            "PFAS is confirmed."
        )
        pref_reason = ""
        not_pref_reason = losing_str

    # Large-scale note
    if ds_tpd >= 50:
        large_scale_note = (
            f"At {ds_tpd:.0f} tDS/d this is a large-scale scenario. "
            "Incineration is a mandatory benchmark — its economics and operability "
            "are most competitive at this scale. Do not proceed to detailed design "
            "without a full incineration feasibility assessment."
        )
    else:
        large_scale_note = (
            f"At {ds_tpd:.0f} tDS/d, incineration CAPEX per tonne is high. "
            "Consider co-incineration at a regional facility before own-asset investment. "
            f"Incineration becomes more competitive above {50:.0f} tDS/d."
        )

    narrative = _build_comparison_narrative(rows, incin_row, incin_preferred)

    return ThermalComparisonResult(
        rows=rows,
        incineration_verdict=verdict,
        incineration_preferred=incin_preferred,
        incineration_preferred_reason=pref_reason,
        incineration_not_preferred_reason=not_pref_reason,
        preferred_thermal_pathway=preferred_row.pathway_name if preferred_row else "",
        comparison_narrative=narrative,
        large_scale_note=large_scale_note,
    )


def _get_net(thermal_fss, ptype):
    fs = next((f for f in thermal_fss if f.pathway_type == ptype), None)
    return fs.economics.net_annual_value if fs and fs.economics else -1e9


def _build_comparison_narrative(rows, incin_row, incin_preferred) -> str:
    if not rows:
        return ""
    parts = []
    for row in rows[:3]:
        icon = "🟢" if row.overall_rag == "G" else ("🟡" if row.overall_rag == "A" else "🔴")
        parts.append(
            f"{icon} {row.pathway_name} (#{row.rank_in_thermal_set}): "
            f"energy {row.energy_rag}, operability {row.operability_rag}, "
            f"tolerance {row.tolerance_rag}, carbon {row.carbon_rag}, cost {row.cost_rag}."
        )
    return " | ".join(parts)
