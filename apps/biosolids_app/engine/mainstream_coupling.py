"""
BioPoint V1 — Mainstream Coupling Engine.
Evaluates the interaction between biosolids pathways and the liquid treatment plant.

For each pathway calculates:
  - Return liquor volume (m³/day)
  - Return COD load (kg/day)
  - Return NH4-N load (kg/day)
  - Return TP load (kg/day)
  - Impact on aeration demand (kWh/day additional)
  - Impact on nitrogen removal capacity (%)
  - Mainstream impact rating: Low / Moderate / High
  - Risk statements and mitigation requirements

HTC-specific rule:
  - Return liquor from HTC is high-strength (COD 5,000–15,000 mg/L, NH4 500–2,000 mg/L)
  - Sidestream treatment may be required before return to works
  - Without sidestream treatment, mainstream impact may be HIGH

References:
  - M&E 5th ed. Tables 13-23, 14-3, 16-5
  - HTC liquor characteristics: Funke & Ziegler (2010); Urban et al. (2015)
  - Centrate characteristics: WEF MOP 8

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# RETURN LIQUOR CHARACTERISTICS BY PATHWAY
# All values are per tonne DS input to the process
# ---------------------------------------------------------------------------

# COD return load (kg COD per tDS treated)
# Sources: M&E Table 13-23; operational surveys
RETURN_COD_KG_PER_TDS = {
    "baseline":        0.0,    # No treatment — no centrate
    "AD":              18.0,   # Centrate from dewatering post-AD (~1,500 mg/L × vol)
    "drying_only":     12.0,   # Condensate from drying (lower strength)
    "pyrolysis":        8.0,   # Condensate only — low volume
    "gasification":     5.0,   # Minimal — syngas scrubber water
    "HTC":            120.0,   # HIGH: HTC process water 5,000–15,000 mg/L COD
    "HTC_sidestream":  15.0,   # Post sidestream: COD largely removed; treated effluent
    "centralised":     15.0,   # Centrate + condensate
    "decentralised":   12.0,   # Condensate
    "incineration":     3.0,   # Scrubber water — low organic load
    "thp_incineration":20.0,   # THP condensate + centrate
}

# NH4-N return load (kg NH4-N per tDS treated)
# High in all dewatering centrates; very high in HTC liquor
RETURN_NH4_KG_PER_TDS = {
    "baseline":         0.0,
    "AD":              12.0,   # Centrate ~800–1,200 mg/L NH4-N (M&E Table 13-23)
    "drying_only":      6.0,   # Condensate lower N
    "pyrolysis":        4.0,
    "gasification":     3.0,
    "HTC":             35.0,   # HIGH: HTC liquor 500–2,000 mg/L NH4-N
    "HTC_sidestream":   3.0,   # Post SHARON/ANAMMOX: >90% N removal → low return
    "centralised":     12.0,
    "decentralised":    6.0,
    "incineration":     1.0,   # Scrubber water — near zero organic N
    "thp_incineration":16.0,   # THP liquor high N
}

RETURN_TP_KG_PER_TDS = {
    "baseline":         0.0,
    "AD":               2.5,
    "drying_only":      1.5,
    "pyrolysis":        1.0,
    "gasification":     0.5,
    "HTC":              8.0,   # HIGH: P release during HTC
    "HTC_sidestream":   2.0,   # Post sidestream: partial P removal
    "centralised":      2.5,
    "decentralised":    1.5,
    "incineration":     0.2,
    "thp_incineration": 3.0,
}

RETURN_VOLUME_M3_PER_TDS = {
    "baseline":         0.0,
    "AD":               8.0,   # Centrate volume
    "drying_only":      6.0,   # Condensate
    "pyrolysis":        3.0,
    "gasification":     2.0,
    "HTC":             10.0,   # HIGH: HTC process water is substantial
    "HTC_sidestream":  10.0,   # Same volume — treated before return
    "centralised":      8.0,
    "decentralised":    6.0,
    "incineration":     1.0,   # Scrubber water only
    "thp_incineration": 9.0,
}

# Aeration demand uplift factor (kWh additional per kg COD returned)
# Biological oxidation: ~0.5 kWh/kg COD; nitrification uplift: ~4.6 kWh/kg NH4-N
COD_AERATION_KWH_PER_KG  = 0.50   # kWh per kg COD (carbonaceous BOD oxidation)
NH4_AERATION_KWH_PER_KG  = 4.60   # kWh per kg NH4-N (nitrification)


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class MainstreamCouplingResult:
    """
    Mainstream coupling assessment for one flowsheet.
    All loads are per day (total system).
    """
    flowsheet_id: str = ""
    flowsheet_name: str = ""
    pathway_type: str = ""

    # --- RETURN LOADS ---
    return_volume_m3_d: float = 0.0
    return_cod_kg_d: float = 0.0
    return_nh4_kg_d: float = 0.0
    return_tp_kg_d: float = 0.0

    # Return as % of assumed influent load
    # (allows assessment of relative significance without knowing plant size)
    return_cod_kg_per_tds: float = 0.0
    return_nh4_kg_per_tds: float = 0.0

    # --- ENERGY IMPACT ---
    additional_aeration_kwh_d: float = 0.0    # Additional aeration demand on mainstream

    # --- NITROGEN IMPACT ---
    nitrogen_load_uplift_pct: float = 0.0     # Relative to assumed plant N load
    # Assumed plant N influent basis: 50 mg/L × plant flow (derived from DS load)
    plant_flow_estimate_ML_d: float = 0.0
    plant_nh4_influent_kg_d: float = 0.0
    return_as_pct_of_plant_nh4: float = 0.0

    # --- IMPACT RATING ---
    mainstream_impact: str = ""     # "Low" / "Moderate" / "High"
    impact_basis: str = ""

    # --- RISK STATEMENTS ---
    risk_statements: list = field(default_factory=list)
    mitigation_required: bool = False
    mitigation_actions: list = field(default_factory=list)

    # --- HTC-SPECIFIC ---
    htc_liquor_flag: bool = False
    sidestream_treatment_required: bool = False
    sidestream_capex_estimate_m: float = 0.0   # $M for SHARON/ANAMMOX sidestream

    # --- RANKING ADJUSTMENT ---
    ranking_downgrade: bool = False
    ranking_downgrade_reason: str = ""

    # --- NOTES ---
    notes: str = ""


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_mainstream_coupling(flowsheet, ds_tpd: float,
                             plant_flow_estimate_ML_d: Optional[float] = None
                             ) -> MainstreamCouplingResult:
    """
    Evaluate mainstream coupling for one flowsheet.

    Parameters
    ----------
    flowsheet      : evaluated Flowsheet object
    ds_tpd         : dry solids throughput (tDS/day)
    plant_flow_ML_d: influent flow estimate (ML/d).
                     If None, estimated from DS load at 35 gDS/EP/d and 250 L/EP/d
    """
    ptype = flowsheet.pathway_type

    # --- ESTIMATE PLANT FLOW IF NOT PROVIDED ---
    if plant_flow_estimate_ML_d is None:
        # Back-calculate: 35 gDS/EP/d → EP = ds_tpd × 1e6 / 35
        # Plant flow at 250 L/EP/d
        ep_equiv = ds_tpd * 1_000_000 / 35.0
        plant_flow_ML_d = ep_equiv * 250 / 1_000_000

    # --- RETURN LOADS ---
    cod_per_tds = RETURN_COD_KG_PER_TDS.get(ptype, 10.0)
    nh4_per_tds = RETURN_NH4_KG_PER_TDS.get(ptype, 8.0)
    tp_per_tds  = RETURN_TP_KG_PER_TDS.get(ptype, 2.0)
    vol_per_tds = RETURN_VOLUME_M3_PER_TDS.get(ptype, 5.0)

    return_cod  = cod_per_tds * ds_tpd
    return_nh4  = nh4_per_tds * ds_tpd
    return_tp   = tp_per_tds  * ds_tpd
    return_vol  = vol_per_tds * ds_tpd

    # --- AERATION IMPACT ---
    aeration_uplift = (return_cod * COD_AERATION_KWH_PER_KG +
                       return_nh4 * NH4_AERATION_KWH_PER_KG)

    # --- NITROGEN IMPACT ---
    # Plant influent NH4 load: 40 mg/L × plant_flow_ML_d ML/d × 1000 m³/ML ÷ 1000 g/kg = kg/d
    # Simplifies to: 40 × plant_flow_ML_d kg/d
    plant_nh4_kg_d = 40.0 * plant_flow_ML_d   # kg/d NH4-N in plant influent
    return_pct_of_plant = (return_nh4 / plant_nh4_kg_d * 100
                           if plant_nh4_kg_d > 0 else 0.0)

    # --- IMPACT CLASSIFICATION ---
    # Thresholds are plant-relative only — raw NH4 mass without plant-size context is meaningless.
    # A 600 kgN/d centrate return is routine at a 320 MLD plant (4.7% of influent N)
    # but catastrophic at a 15 MLD plant (100%+ of influent N).
    risk_statements = []
    mitigation = []
    downgrade  = False
    downgrade_reason = ""
    htc_flag   = (ptype == "HTC")
    sidestream_required = False
    sidestream_capex    = 0.0

    if return_pct_of_plant >= 15:
        impact = "High"
        impact_basis = (
            f"Return NH₄-N load ({return_nh4:.0f} kgN/d) represents "
            f"{return_pct_of_plant:.0f}% of estimated plant influent N load — "
            f"above the 15% threshold for significant compliance risk. "
            f"Additional aeration demand: {aeration_uplift:,.0f} kWh/d."
        )
        risk_statements.append(
            "HIGH mainstream impact — return N load exceeds 15% of influent. "
            "May trigger nitrogen compliance failure if return load is not managed."
        )
        risk_statements.append(
            f"Return NH₄-N of {return_nh4:.0f} kgN/d will require nitrification "
            "capacity assessment and may need sidestream treatment."
        )
        mitigation.append("Sidestream nitrogen treatment (SHARON/ANAMMOX) strongly recommended.")
        mitigation.append("Return during off-peak periods; monitor effluent TN continuously.")
        downgrade = True
        downgrade_reason = (
            f"Mainstream impact HIGH: return NH₄-N = {return_pct_of_plant:.0f}% of plant influent N. "
            "Ranking downgraded pending mitigation confirmation."
        )
        sidestream_required = (return_pct_of_plant >= 20)
        if sidestream_required:
            sidestream_capex = return_nh4 / 100.0 * 0.5

    elif return_pct_of_plant >= 7:
        impact = "Moderate"
        impact_basis = (
            f"Return NH₄-N load ({return_nh4:.0f} kgN/d) represents "
            f"{return_pct_of_plant:.0f}% of estimated plant influent N. "
            f"Manageable with return flow scheduling and monitoring."
        )
        risk_statements.append(
            "MODERATE mainstream impact — nitrogen return load requires "
            "scheduling control to avoid peak-load coincidence with high-flow events."
        )
        mitigation.append("Return liquor during off-peak periods (night/weekend).")
        mitigation.append("Monitor effluent N weekly after any operational change.")

    else:
        impact = "Low"
        impact_basis = (
            f"Return NH₄-N load ({return_nh4:.0f} kgN/d) is {return_pct_of_plant:.1f}% "
            "of estimated plant influent N — within normal recycle tolerance for this plant size."
        )

    # --- HTC-SPECIFIC ASSESSMENT ---
    notes_parts = []
    if ptype == "HTC":
        risk_statements.insert(0,
            "HTC process liquor is HIGH-STRENGTH: COD 5,000–15,000 mg/L, "
            "NH₄-N 500–2,000 mg/L. Direct return to works without treatment "
            "will significantly impact mainstream plant performance."
        )
        mitigation.insert(0,
            "Sidestream treatment of HTC liquor is ESSENTIAL before return. "
            "Options: SHARON (stripping/nitritation), ANAMMOX, or aerobic MBR."
        )
        notes_parts.append(
            f"HTC liquor: {return_vol:.0f} m³/d at estimated {return_cod/return_vol*1000:.0f} mg/L COD "
            f"and {return_nh4/return_vol*1000:.0f} mg/L NH₄-N."
        )
        if not sidestream_required:
            sidestream_required = True
            sidestream_capex = max(sidestream_capex, return_nh4 / 100.0 * 0.5)
            mitigation.append(
                f"Estimated sidestream CAPEX: ${sidestream_capex:.1f}M (SHARON/ANAMMOX). "
                "Include in HTC total project CAPEX."
            )

    if ptype in ("AD", "thp_incineration"):
        notes_parts.append(
            f"AD centrate: {return_vol:.0f} m³/d. High NH₄-N is characteristic of "
            "anaerobic digestion centrate — standard in plants with AD."
        )

    if ptype == "incineration":
        notes_parts.append(
            "Incineration scrubber water has negligible organic load. "
            "Lowest mainstream impact of all thermal pathways."
        )

    if ptype == "HTC_sidestream":
        notes_parts.append(
            f"HTC liquor treated by sidestream (SHARON/ANAMMOX) before return. "
            f"Raw HTC liquor: ~{ds_tpd*35:.0f} kgN/d → post-sidestream: {return_nh4:.0f} kgN/d (>90% removal). "
            "Mainstream impact reduced to Low. Sidestream CAPEX must be included in project total."
        )

    return MainstreamCouplingResult(
        flowsheet_id=flowsheet.flowsheet_id,
        flowsheet_name=flowsheet.name,
        pathway_type=ptype,
        return_volume_m3_d=round(return_vol, 1),
        return_cod_kg_d=round(return_cod, 1),
        return_nh4_kg_d=round(return_nh4, 1),
        return_tp_kg_d=round(return_tp, 1),
        return_cod_kg_per_tds=cod_per_tds,
        return_nh4_kg_per_tds=nh4_per_tds,
        additional_aeration_kwh_d=round(aeration_uplift, 0),
        plant_flow_estimate_ML_d=round(plant_flow_ML_d, 1),
        plant_nh4_influent_kg_d=round(plant_nh4_kg_d, 0),
        return_as_pct_of_plant_nh4=round(return_pct_of_plant, 1),
        mainstream_impact=impact,
        impact_basis=impact_basis,
        risk_statements=risk_statements,
        mitigation_required=bool(mitigation),
        mitigation_actions=mitigation,
        htc_liquor_flag=htc_flag,
        sidestream_treatment_required=sidestream_required,
        sidestream_capex_estimate_m=round(sidestream_capex, 2),
        ranking_downgrade=downgrade,
        ranking_downgrade_reason=downgrade_reason,
        notes=" ".join(notes_parts),
    )


# ---------------------------------------------------------------------------
# SYSTEM-LEVEL SUMMARY
# ---------------------------------------------------------------------------

@dataclass
class MainstreamCouplingSystem:
    """Aggregated coupling assessment across all flowsheets."""
    per_flowsheet: list = field(default_factory=list)  # List[MainstreamCouplingResult]

    # Flowsheets with HIGH mainstream impact
    high_impact_flowsheets: list = field(default_factory=list)
    # Flowsheets requiring ranking downgrade
    downgraded_flowsheets: list = field(default_factory=list)
    # Flowsheets requiring sidestream treatment
    sidestream_required: list = field(default_factory=list)

    system_narrative: str = ""


def run_mainstream_coupling_system(flowsheets: list, ds_tpd: float,
                                    plant_flow_ML_d: Optional[float] = None
                                    ) -> MainstreamCouplingSystem:
    """Run mainstream coupling for all flowsheets."""
    results = []
    high_impact = []
    downgraded  = []
    sidestream  = []

    for fs in flowsheets:
        r = run_mainstream_coupling(fs, ds_tpd, plant_flow_ML_d)
        results.append(r)
        if r.mainstream_impact == "High":
            high_impact.append(r.flowsheet_name)
        if r.ranking_downgrade:
            downgraded.append(r.flowsheet_name)
        if r.sidestream_treatment_required:
            sidestream.append(r.flowsheet_name)

    # Attach to flowsheet objects for downstream use
    for fs, r in zip(flowsheets, results):
        fs.mainstream_coupling = r

    narrative_parts = []
    if high_impact:
        narrative_parts.append(
            f"HIGH mainstream impact pathways: {', '.join(high_impact)}. "
            "These pathways require nitrogen load management or sidestream treatment "
            "before mainstream plant impact can be accepted."
        )
    if sidestream:
        narrative_parts.append(
            f"Sidestream treatment required: {', '.join(sidestream)}. "
            "Add sidestream CAPEX to total project cost."
        )
    if not high_impact:
        narrative_parts.append(
            "No pathway creates HIGH mainstream impact — all return loads are "
            "within manageable range at this scale."
        )

    return MainstreamCouplingSystem(
        per_flowsheet=results,
        high_impact_flowsheets=high_impact,
        downgraded_flowsheets=downgraded,
        sidestream_required=sidestream,
        system_narrative=" ".join(narrative_parts),
    )
