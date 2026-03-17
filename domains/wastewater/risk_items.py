"""
domains/wastewater/risk_items.py

Wastewater-domain risk item definitions.
Risk scores are technology-specific, reflecting maturity, operational complexity,
and regulatory acceptance. Uses a 5×5 matrix: Score = Likelihood × Consequence.

References:
  IWA Technology Maturity Ratings (2022)
  WEF MOP 35 — Risk-Based Decision Making
  Metcalf & Eddy 5th Ed, Chapter 10 (Risk)
"""

from __future__ import annotations
from typing import Any, Dict, List

from core.project.project_model import RiskItem


# ── Technology maturity and profile lookup ───────────────────────────────
# (likelihood, consequence) tuples per risk dimension
_TECH_PROFILES = {
    # code:  maturity_L  maturity_C  ops_L  ops_C  reg_L  reg_C  impl_L  impl_C
    "bnr":             (1, 2,   1, 3,   2, 4,   2, 2),  # >5000 plants globally
    "granular_sludge": (3, 3,   3, 3,   2, 3,   3, 3),  # ~200 full-scale, granule instability
    "mabr_bnr":        (4, 3,   2, 3,   3, 3,   3, 3),  # <50 full-scale, novel gas supply
    "bnr_mbr":         (2, 2,   3, 4,   2, 3,   2, 2),  # Mature but high ops complexity
    "ifas_mbbr":       (2, 3,   2, 3,   2, 3,   2, 2),  # Established retrofit technology
    "anmbr":           (4, 3,   3, 4,   4, 4,   3, 3),  # Emerging, few full-scale refs
    "ad_chp":          (2, 3,   2, 3,   2, 3,   2, 3),  # Mature, common in large plants
    "sidestream_pna":  (3, 3,   3, 4,   3, 3,   3, 3),  # Growing adoption, strict DO control
    "mob":             (4, 3,   3, 3,   3, 3,   3, 3),  # Very limited full-scale data
    "thermal_biosolids":(2, 3,  2, 3,   2, 4,   3, 3),  # Odour and emissions complexity
    "adv_reuse":       (2, 2,   3, 4,   2, 3,   2, 2),  # Mature technology, high public risk
    "cpr":             (1, 2,   1, 2,   2, 3,   1, 2),  # Very simple, well established
    "tertiary_filt":   (1, 2,   1, 2,   2, 3,   1, 2),  # Simple, well established
}

# Default profile for unknown technologies
_DEFAULT_PROFILE = (2, 3,   2, 3,   2, 3,   2, 3)


def get_wastewater_risk_items(
    inputs: Any,
    tech_results: Dict[str, Any],
) -> List[RiskItem]:
    """
    Build the wastewater-specific risk item list for a scenario.
    Risk scores are differentiated by technology type.

    Parameters
    ----------
    inputs : WastewaterInputs
    tech_results : dict of {tech_code: TechnologyResult}
    """
    items = []
    tech_codes = list(tech_results.keys())
    primary_code = tech_codes[0] if tech_codes else "bnr"

    has_mbr    = any("mbr" in c for c in tech_codes)
    has_mabr   = "mabr_bnr" in tech_codes
    has_ags    = "granular_sludge" in tech_codes
    has_ifas   = "ifas_mbbr" in tech_codes
    has_memb   = has_mbr or has_mabr
    flow       = inputs.design_flow_mld or 1.0

    prof = _TECH_PROFILES.get(primary_code, _DEFAULT_PROFILE)
    mat_L, mat_C, ops_L, ops_C, reg_L, reg_C, impl_L, impl_C = prof

    # ── Scenario-specific likelihood modifiers ────────────────────────────
    # These adjust the base technology profile based on actual operating conditions.
    # Ref: WEF MOP 35 Risk Framework; AS/NZS ISO 31000 likelihood definitions.
    T_design   = getattr(inputs, "influent_temperature_celsius", 20.0) or 20.0
    peak_fac   = getattr(inputs, "peak_flow_factor", 2.5) or 2.5
    eff_tn_tgt = getattr(inputs, "effluent_tn_mg_l", 10.0) or 10.0

    # Cold climate increases operational risk for all biological techs
    cold_ops_adj = 1 if T_design < 15 else 0

    # High peak flow increases implementation risk
    high_peak_adj = 1 if peak_fac > 3.0 else 0

    # Tight TN target increases regulatory risk
    tight_tn_reg_adj = 1 if eff_tn_tgt < 8.0 else 0


    # ── Technical risks ───────────────────────────────────────────────────

    items.append(RiskItem(
        risk_id="ww_tech_01",
        category="technical",
        name="Biological process instability",
        description=(
            "Risk of process upset from toxic influent, temperature shock, "
            "or nutrient imbalance."
        ),
        likelihood=2,
        consequence=4,
        mitigation="Online NH4/DO monitoring, equalization upstream.",
    ))

    items.append(RiskItem(
        risk_id="ww_tech_02",
        category="technical",
        name="Technology maturity and reference plant availability",
        description=(
            f"Availability of full-scale reference plants and long-term performance data "
            f"for {primary_code.upper()}."
        ),
        likelihood=mat_L,
        consequence=mat_C,
        mitigation=(
            "Pilot testing and vendor performance guarantee recommended."
            if mat_L >= 3 else
            "Well-proven technology; reference plant visits recommended."
        ),
    ))

    if has_mbr:
        items.append(RiskItem(
            risk_id="ww_tech_03",
            category="technical",
            name="MBR membrane fouling",
            description="Irreversible fouling increases TMP, requiring early replacement.",
            likelihood=3,
            consequence=3,
            mitigation="Pre-screening, optimised SAD, regular CIP, online TMP monitoring.",
        ))
        items.append(RiskItem(
            risk_id="ww_tech_04",
            category="technical",
            name="MBR membrane integrity failure",
            description="Membrane breach allows pathogen passage to permeate.",
            likelihood=1,
            consequence=5,
            mitigation="Continuous pressure decay testing, turbidity monitoring.",
        ))

    if has_ags:
        items.append(RiskItem(
            risk_id="ww_tech_05",
            category="technical",
            name="Aerobic granule stability",
            description=(
                "Granule structural integrity sensitive to influent composition, "
                "high lipid/fat loads, and sub-optimal feeding strategy."
            ),
            likelihood=3,
            consequence=3,
            mitigation=(
                "Pilot or demonstration plant recommended. Proprietary process control "
                "(Nereda®). Fat/oil/grease monitoring at headworks."
            ),
        ))

    if has_mabr:
        items.append(RiskItem(
            risk_id="ww_tech_06",
            category="technical",
            name="MABR membrane gas-side fouling",
            description=(
                "Biofilm overgrowth on gas side of hollow fibre reduces O₂ transfer "
                "efficiency over time."
            ),
            likelihood=3,
            consequence=3,
            mitigation="Periodic gas-side backwash protocol; loading rate < 4 g NH4/m²/d.",
        ))

    if flow > 50:
        items.append(RiskItem(
            risk_id="ww_tech_07",
            category="technical",
            name="Large plant operational complexity",
            description="Multiple treatment trains increase coordination and control demands.",
            likelihood=2,
            consequence=3,
            mitigation="Comprehensive SCADA, clear SOPs, adequate operator training.",
        ))

    # ── Implementation risks ──────────────────────────────────────────────

    items.append(RiskItem(
        risk_id="ww_impl_01",
        category="implementation",
        name="Odour management during construction",
        description="Excavation and sewer diversions may cause community odour complaints.",
        likelihood=3 if getattr(inputs, "odour_sensitive", False) else 2,
        consequence=3 if getattr(inputs, "odour_sensitive", False) else 2,
        mitigation="Construction odour management plan, community liaison.",
    ))

    items.append(RiskItem(
        risk_id="ww_impl_02",
        category="implementation",
        name="Construction programme overrun",
        description=(
            "Commissioning delays, particularly for novel biological systems."
            + (f" High peak factor ({peak_fac:.1f}×) increases infrastructure complexity." if peak_fac > 3.0 else "")
        ),
        likelihood=min(5, impl_L + high_peak_adj),
        consequence=impl_C,
        mitigation="Allow adequate commissioning period; phased commissioning plan.",
    ))

    items.append(RiskItem(
        risk_id="ww_impl_03",
        category="implementation",
        name="Site constraints and available land",
        description="Limited footprint may constrain technology selection.",
        likelihood=1 if not getattr(inputs, "available_land_m2", None) else 2,
        consequence=3,
        mitigation="Compact technologies (MBR, AGS) if footprint is constrained.",
    ))

    if has_mabr or has_ags:
        items.append(RiskItem(
            risk_id="ww_impl_04",
            category="implementation",
            name="Supplier/licensor dependency",
            description=(
                "Proprietary technology requires ongoing licensor support for "
                "process control, spare parts, and performance guarantees."
            ),
            likelihood=3,
            consequence=3,
            mitigation="Long-term service agreement; confirm local supplier capability.",
        ))

    # ── Operational risks ─────────────────────────────────────────────────

    items.append(RiskItem(
        risk_id="ww_ops_01",
        category="operational",
        name="Operator skill and training requirements",
        description=(
            "Advanced biological processes require higher operator skill levels."
            + (f" Cold climate ({T_design:.0f}°C) adds process complexity." if T_design < 15 else "")
        ),
        likelihood=min(5, ops_L + cold_ops_adj),
        consequence=ops_C,
        mitigation="Operator training programme, O&M manual, supplier support contract.",
    ))

    items.append(RiskItem(
        risk_id="ww_ops_02",
        category="operational",
        name="Chemical supply reliability",
        description="Dependence on chemical supply for P removal or carbon dosing.",
        likelihood=2,
        consequence=3,
        mitigation="Dual supplier contracts, minimum 30-day onsite storage.",
    ))

    items.append(RiskItem(
        risk_id="ww_ops_03",
        category="operational",
        name="Energy cost exposure",
        description="Aeration is energy-intensive; electricity price rises increase OPEX.",
        likelihood=3,
        consequence=2,
        mitigation="Energy efficiency programme, renewable energy procurement.",
    ))

    if has_mbr:
        items.append(RiskItem(
            risk_id="ww_ops_04",
            category="operational",
            name="Membrane replacement lifecycle cost",
            description=(
                "MBR membranes require replacement every 8–12 years at significant cost, "
                "creating uneven lifecycle OPEX profile."
            ),
            likelihood=4,
            consequence=3,
            mitigation="Sinking fund for membrane replacement; negotiate long-term supply.",
        ))

    # ── Regulatory risks ──────────────────────────────────────────────────

    items.append(RiskItem(
        risk_id="ww_reg_01",
        category="regulatory",
        name="Effluent licence compliance",
        description=(
            "Risk of exceeding consent conditions for TN, TP, BOD, or TSS, "
            "particularly during start-up or wet weather."
            + (f" Tight TN target ({eff_tn_tgt:.0f} mg/L) increases regulatory risk." if eff_tn_tgt < 8.0 else "")
        ),
        likelihood=min(5, reg_L + tight_tn_reg_adj),
        consequence=reg_C,
        mitigation=(
            "Conservative design to licence limits, wet weather strategy, "
            "effluent storage contingency."
        ),
    ))

    items.append(RiskItem(
        risk_id="ww_reg_02",
        category="regulatory",
        name="Biosolids classification and disposal approval",
        description=(
            "Biosolids must meet pathogen reduction requirements for land application."
        ),
        likelihood=2,
        consequence=3,
        mitigation="Confirm biosolids classification early; design sludge treatment accordingly.",
    ))

    items.append(RiskItem(
        risk_id="ww_reg_03",
        category="regulatory",
        name="Future licence tightening",
        description="Regulatory tightening (nutrient limits) may require upgrade.",
        likelihood=2,
        consequence=3,
        mitigation="Design for upgrade pathway; modular process configuration.",
    ))

    if has_mabr:
        items.append(RiskItem(
            risk_id="ww_reg_04",
            category="regulatory",
            name="Novel technology regulatory acceptance",
            description=(
                "MABR has limited track record for regulatory sign-off in Australia/NZ. "
                "Regulator may require demonstration data or additional monitoring."
            ),
            likelihood=3,
            consequence=3,
            mitigation="Early regulator engagement; provide vendor performance data.",
        ))

    if has_ags:
        items.append(RiskItem(
            risk_id="ww_reg_05",
            category="regulatory",
            name="AGS process control and compliance demonstration",
            description=(
                "SBR operating mode requires demonstration of consistent compliance "
                "under variable load conditions."
            ),
            likelihood=2,
            consequence=3,
            mitigation="Pilot data for regulator; SCADA logging for compliance reporting.",
        ))

    return items
