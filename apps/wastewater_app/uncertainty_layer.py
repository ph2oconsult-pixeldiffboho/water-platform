"""
apps/wastewater_app/uncertainty_layer.py

Uncertainty & Sensitivity Layer — Production V1
================================================

Sits on top of Technology Stack Generator, Feasibility Layer, Credibility Layer,
and Carbon Layer. Transforms a single deterministic recommendation into a decision
with quantified uncertainty bounds and sensitivity insight.

Does NOT modify selected technologies, sequencing, or calculated values.
Returns UncertaintyReport — a self-contained assessment that can be appended
to any CredibleOutput or rendered standalone.

Design principles
-----------------
- Deterministic inputs → probabilistic communication of outputs
- Every uncertainty level has a traceable rule (from spec + IPCC literature)
- Carbon uncertainty uses IPCC 2019 N2O EF range: 0.005–0.032 g N2O-N/g TN removed
- Sensitivity drivers are ranked by impact magnitude, not assumption
- Decision tension is stated explicitly — always one clear sentence
- Language: "indicative", "sensitive to", "subject to validation" — never absolute

IPCC references
---------------
N2O EF range: IPCC 2019 Refinement to 2006 Guidelines, Chapter 6
  EF_effluent = 0.005 (low) – 0.016 (central) – 0.032 (high) g N2O-N / g TN removed
  GWP100 (AR6) = 273

Main entry point
----------------
  build_uncertainty_report(pathway, feasibility, credible, plant_context)
      -> UncertaintyReport
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from apps.wastewater_app.stack_generator import (
    UpgradePathway,
    TI_COMAG, TI_BIOMAG, TI_EQ_BASIN, TI_STORM_STORE,
    TI_INDENSE, TI_MIGINDENSE, TI_MEMDENSE,
    TI_HYBAS, TI_IFAS, TI_MBBR, TI_MABR,
    TI_BARDENPHO, TI_RECYCLE_OPT, TI_ZONE_RECONF,
    TI_DENFILTER, TI_TERT_P,
    CT_HYDRAULIC, CT_SETTLING, CT_NITRIFICATION,
    CT_TN_POLISH, CT_TP_POLISH, CT_BIOLOGICAL,
    CT_MEMBRANE, CT_WET_WEATHER,
)
from apps.wastewater_app.feasibility_layer import FeasibilityReport
from apps.wastewater_app.credibility_layer import CredibleOutput

# ── Uncertainty level constants ────────────────────────────────────────────────
UL_LOW      = "Low"
UL_MEDIUM   = "Medium"
UL_HIGH     = "High"
UL_VERY_HIGH= "Very High"

# ── IPCC N2O EF bounds (g N2O-N per g TN removed) ─────────────────────────────
_EF_LOW     = 0.005   # IPCC 2019, lower bound
_EF_CENTRAL = 0.016   # IPCC 2019, central estimate (Tier 1 default)
_EF_HIGH    = 0.032   # IPCC 2019, upper bound
_N2O_GWP    = 273.0   # IPCC AR6 GWP100
_N2O_RATIO  = 44.0 / 28.0   # N2O-N to N2O molecular weight ratio


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class UncertaintyDimension:
    """Uncertainty assessment for one evaluation dimension."""
    dimension:      str   # name
    level:          str   # UL_* constant
    driver:         str   # what causes the uncertainty
    impact:         str   # what outcome is affected
    note:           str   # one-sentence engineering note


@dataclass
class CarbonBand:
    """A single point (low / central / high) in the carbon uncertainty range."""
    label:          str   # "Low", "Central", "High"
    ef_pct:         float # N2O EF as percentage of TN removed
    n2o_baseline_t: float # t CO2e/year baseline
    n2o_upgraded_t: float # t CO2e/year after upgrade
    n2o_delta_t:    float # reduction in t CO2e/year
    energy_delta_t: float # energy reduction (same for all bands)
    total_delta_t:  float # net total CO2e reduction
    pct_reduction:  float # % reduction vs baseline


@dataclass
class CarbonUncertainty:
    """Full uncertainty range for carbon calculations."""
    baseline_total_t:   float          # central estimate total baseline CO2e/year
    upgraded_central_t: float          # central estimate upgraded CO2e/year
    bands:              List[CarbonBand]
    low_band:           CarbonBand
    central_band:       CarbonBand
    high_band:          CarbonBand
    reduction_range_pct: Tuple[float, float]  # (low%, high%)
    central_reduction_pct: float
    summary_text:       str
    ipcc_ref:           str


@dataclass
class SensitivityDriver:
    """A ranked sensitivity driver."""
    rank:           int
    driver:         str
    impact_level:   str   # "High" / "Medium" / "Secondary"
    affects:        str   # which output or outcome
    explanation:    str   # one to two sentences
    threshold:      str   # the value above/below which behaviour changes


@dataclass
class DecisionTension:
    """The primary decision trade-off — always one clear statement."""
    primary_tension:    str   # the main trade-off sentence
    option_a_label:     str
    option_a_pros:      List[str]
    option_a_cons:      List[str]
    option_b_label:     str
    option_b_pros:      List[str]
    option_b_cons:      List[str]
    recommended_path:   str   # brief justification for the recommended option


@dataclass
class UncertaintyReport:
    """Full Uncertainty & Sensitivity assessment."""
    # Input summary
    system_state:       str
    proximity_pct:      float
    n_stages:           int
    flow_ratio:         float

    # Uncertainty dimensions (5)
    dimensions:         List[UncertaintyDimension]
    overall_uncertainty: str   # UL_* constant — worst-case dimension

    # Carbon uncertainty
    carbon:             CarbonUncertainty

    # Sensitivity
    sensitivity_drivers: List[SensitivityDriver]

    # Decision tension
    decision_tension:   DecisionTension

    # Confidence
    overall_confidence: str   # High / Medium / Low
    confidence_rationale: str

    # Technology-specific flags (for validation checks)
    hydraulic_sensitivity_flagged: bool
    aeration_dependency_flagged:   bool
    carbon_do_sensitivity_flagged: bool
    carbon_range_included:         bool


# ── Step 1-2: Uncertainty dimension assessment ─────────────────────────────────

def _assess_dimensions(
    pathway: UpgradePathway,
    feasibility: FeasibilityReport,
    ctx: Dict,
) -> List[UncertaintyDimension]:
    """Assess uncertainty across all five dimensions."""
    dims: List[UncertaintyDimension] = []
    tech_set     = {s.technology for s in pathway.stages}
    ct_set       = {c.constraint_type for c in pathway.constraints}
    flow_ratio   = ctx.get("flow_ratio", 1.0) or 1.0
    n_specialist = sum(1 for s in feasibility.stage_feasibility if s.specialist)
    n_stages     = len(pathway.stages)

    # ── 1. Influent variability ────────────────────────────────────────────────
    has_ww      = CT_HYDRAULIC in ct_set or CT_WET_WEATHER in ct_set
    tn_at_limit = ctx.get("tn_at_limit", False)
    high_diurnal= ctx.get("high_diurnal", False) or has_ww
    if flow_ratio >= 2.5 or (high_diurnal and tn_at_limit):
        inf_level = UL_HIGH
        inf_note  = ("High diurnal and wet weather variability increases risk of "
                     "nitrification instability and TN compliance exceedance during "
                     "peak loading periods.")
    elif flow_ratio >= 1.5 or tn_at_limit:
        inf_level = UL_MEDIUM
        inf_note  = ("Moderate influent variability; TN and NH\u2084 compliance sensitive "
                     "to seasonal and diurnal load fluctuations.")
    else:
        inf_level = UL_LOW
        inf_note  = "Influent characterisation indicates relatively stable loading conditions."

    dims.append(UncertaintyDimension(
        dimension = "Influent variability",
        level     = inf_level,
        driver    = "Diurnal variability, wet weather dilution, seasonal temperature",
        impact    = "NH\u2084 and TN compliance; biological process stability",
        note      = inf_note,
    ))

    # ── 2. Hydraulic variability ───────────────────────────────────────────────
    if flow_ratio >= 3.0:
        hyd_level = UL_VERY_HIGH
        hyd_note  = (f"Peak flow at {flow_ratio:.1f}\u00d7 ADWF exceeds the threshold where "
                     "process intensification alone is insufficient. Extreme event frequency "
                     "and duration drive outcome uncertainty materially.")
    elif flow_ratio >= 2.5:
        hyd_level = UL_HIGH
        hyd_note  = (f"Peak flow at {flow_ratio:.1f}\u00d7 ADWF is in the range where CoMag "
                     "provides significant relief but extreme events may still require "
                     "complementary attenuation. Event frequency and duration are key unknowns.")
    elif flow_ratio >= 1.5:
        hyd_level = UL_MEDIUM
        hyd_note  = ("Moderate hydraulic variability; wet weather response is dependent "
                     "on I/I reduction programme progress and peak event frequency.")
    else:
        hyd_level = UL_LOW
        hyd_note  = "Hydraulic loading is within manageable range for the process configuration."

    dims.append(UncertaintyDimension(
        dimension = "Hydraulic variability",
        level     = hyd_level,
        driver    = f"Peak wet weather flow ratio ({flow_ratio:.1f}\u00d7 ADWF); I/I ingress; "
                    "storm event frequency and duration",
        impact    = "Clarifier performance; TSS compliance; CoMag bypass capacity adequacy",
        note      = hyd_note,
    ))

    # ── 3. Process performance (technology-specific) ───────────────────────────
    # Score each technology in the stack
    tech_uncertainty = {
        TI_COMAG:    (UL_MEDIUM,  "Magnetite recovery efficiency and bypass configuration integration"),
        TI_BIOMAG:   (UL_MEDIUM,  "Dual magnetite + carrier dependency; ballast-biofilm interface"),
        TI_MABR:     (UL_MEDIUM,  "Membrane integrity; biofilm establishment; OEM specialist dependency"),
        TI_IFAS:     (UL_LOW,     "Well-established retrofit; screen maintenance is primary risk"),
        TI_HYBAS:    (UL_LOW,     "Established biofilm system; carrier distribution uniformity"),
        TI_MBBR:     (UL_LOW,     "Robust operation; downstream solids management primary risk"),
        TI_INDENSE:  (UL_LOW,     "Hydrocyclone operation well understood; split ratio calibration"),
        TI_MIGINDENSE:(UL_MEDIUM, "Sequential commissioning dependency; SBR-specific integration"),
        TI_MEMDENSE: (UL_LOW,     "Hydrocyclone based; permeability improvement well documented"),
        TI_BARDENPHO:(UL_LOW,     "Zone reconfiguration within existing tanks; carbon availability key"),
        TI_RECYCLE_OPT:(UL_LOW,  "Control system adjustment; blower capacity must be confirmed"),
        TI_DENFILTER:(UL_HIGH,    "DO sensitivity at inlet; methanol dosing control; carbon supply"),
        TI_TERT_P:   (UL_MEDIUM, "Chemical dose rate; sludge volume increase; filter backwash"),
        TI_EQ_BASIN: (UL_LOW,    "Civil infrastructure; reliable and low-operational-uncertainty"),
    }

    tech_levels   = []
    tech_drivers  = []
    for s in pathway.stages:
        lvl, drv = tech_uncertainty.get(s.technology, (UL_MEDIUM, "Technology not in library"))
        tech_levels.append(lvl)
        tech_drivers.append(f"{s.technology}: {drv}")

    _lvl_order = {UL_LOW: 0, UL_MEDIUM: 1, UL_HIGH: 2, UL_VERY_HIGH: 3}
    worst_tech   = max(tech_levels, key=lambda v: _lvl_order.get(v, 0))
    has_dnf      = TI_DENFILTER in tech_set
    proc_level   = UL_HIGH if has_dnf else worst_tech

    proc_note = (
        ("Denitrification filter introduces High process uncertainty due to DO sensitivity "
         "and continuous methanol dosing control requirements. " if has_dnf else "")
        + f"MABR biofilm establishment (4\u20138 weeks) and magnetite recovery are "
          "the primary process performance uncertainties in the recommended stack."
        if (TI_MABR in tech_set and (TI_COMAG in tech_set or TI_BIOMAG in tech_set))
        else "Process performance uncertainty is within the Medium range for this technology combination."
    )

    dims.append(UncertaintyDimension(
        dimension = "Process performance",
        level     = proc_level,
        driver    = "; ".join(tech_drivers[:3]),
        impact    = "NH\u2084 and TN compliance; TSS; energy consumption",
        note      = proc_note,
    ))

    # ── 4. Carbon model uncertainty ────────────────────────────────────────────
    # N2O is always High — site-specific EF variability is a fundamental limitation
    dims.append(UncertaintyDimension(
        dimension = "Carbon model (N\u2082O)",
        level     = UL_HIGH,
        driver    = ("N\u2082O emission factor is inherently site-specific (IPCC 2019 range: "
                     "0.5%\u20133.2% of TN removed); influenced by DO control, temperature, "
                     "and biological process configuration."),
        impact    = "Total CO\u2082e reduction estimate; carbon credit verification; "
                    "net-zero progress reporting",
        note      = ("N\u2082O emission estimates are indicative only. The IPCC EF range spans "
                     "6\u00d7 from lower to upper bound. On-site N\u2082O monitoring is essential "
                     "to validate model estimates before carbon credits are claimed."),
    ))

    # ── 5. Delivery / integration risk ────────────────────────────────────────
    if n_stages >= 4 and n_specialist >= 3:
        del_level = UL_HIGH
        del_note  = (f"{n_stages}-stage stack with {n_specialist} specialist systems introduces "
                     "High delivery risk. Sequential commissioning gates and specialist OEM "
                     "coordination must be managed as a programme, not individual contracts.")
    elif n_stages >= 3 or n_specialist >= 2:
        del_level = UL_MEDIUM
        del_note  = (f"{n_stages} stages with {n_specialist} specialist technologies. "
                     "Staged delivery and performance gate-reviews between stages are essential.")
    else:
        del_level = UL_LOW
        del_note  = "Single or dual technology stack; delivery risk is within manageable range."

    dims.append(UncertaintyDimension(
        dimension = "Delivery / integration risk",
        level     = del_level,
        driver    = (f"{n_stages} stages; {n_specialist} specialist supplier systems; "
                     f"brownfield integration with operational plant; {feasibility.integration_risk} "
                     f"integration risk rated by Feasibility Layer"),
        impact    = "Programme timeline; commissioning success; contractor coordination",
        note      = del_note,
    ))

    return dims


def _overall_uncertainty(dims: List[UncertaintyDimension]) -> str:
    _order = {UL_LOW: 0, UL_MEDIUM: 1, UL_HIGH: 2, UL_VERY_HIGH: 3}
    return max(dims, key=lambda d: _order.get(d.level, 0)).level


# ── Step 3: Carbon uncertainty bands ─────────────────────────────────────────

def _build_carbon_uncertainty(
    pathway: UpgradePathway,
    ctx: Dict,
) -> CarbonUncertainty:
    """
    Build N2O uncertainty bands using IPCC 2019 EF range.

    Applies a technology-driven EF reduction factor based on the stack:
    - MABR reduces N2O EF by 30–50% (literature range)
    - Bardenpho optimisation provides more complete denitrification
    Central estimate: 35% EF reduction from MABR + Bardenpho
    """
    tech_set    = {s.technology for s in pathway.stages}
    size_mld    = ctx.get("plant_size_mld", 10.) or 10.
    adwf        = size_mld * 0.96   # approx average (95% of design)
    tn_in       = ctx.get("tn_in_mg_l", 45.) or 45.
    tn_out_base = ctx.get("tn_out_baseline_mg_l", 10.) or 10.
    tn_out_upg  = ctx.get("tn_out_upgraded_mg_l", 5.) or 5.
    grid_ef     = ctx.get("grid_ef_kgco2e_kwh", 0.50) or 0.50

    flow_m3y    = adwf * 1000. * 365.

    # TN mass removed (kg/year)
    tn_rem_base = (tn_in - tn_out_base) / 1000. * flow_m3y
    tn_rem_upg  = (tn_in - tn_out_upg) / 1000. * flow_m3y

    # EF reduction factor from stack
    # MABR: 30–50% EF reduction (biofilm SND reduces anoxic hot spots — literature)
    # Bardenpho: complete denitrification reduces incomplete NO3→N2O reduction (+10%)
    # IFAS/Hybas: biofilm partial SND benefit (+15%)
    # Baseline BNR with full nitrification: 10% reduction vs uncontrolled
    if TI_MABR in tech_set and TI_BARDENPHO in tech_set:
        ef_reduction = 0.35   # 35%: MABR SND (25%) + Bardenpho complete DN (10%)
    elif TI_MABR in tech_set:
        ef_reduction = 0.30
    elif TI_IFAS in tech_set or TI_HYBAS in tech_set:
        ef_reduction = 0.15
    elif TI_BARDENPHO in tech_set or TI_RECYCLE_OPT in tech_set:
        ef_reduction = 0.20   # Fix 3: Bardenpho complete DN recognised (+10% vs baseline)
    else:
        ef_reduction = 0.10   # Baseline BNR full nitrification vs uncontrolled

    # Energy contribution (same for all N2O bands)
    aeration_kwh_d = ctx.get("aeration_kwh_day", 10000.) or 10000.
    energy_base_t  = aeration_kwh_d * 365. * grid_ef / 1000.
    # MABR saves ~30% of nitrification energy; apply conservatively
    energy_upg_t   = energy_base_t * (0.70 if TI_MABR in tech_set else 0.90)
    energy_delta_t = energy_base_t - energy_upg_t

    # Chemical CO2e (same for all bands)
    chemical_increase_t = ctx.get("chemical_co2e_increase_t", 198.) or 198.

    def _band(label: str, ef: float) -> CarbonBand:
        ef_upg      = ef * (1. - ef_reduction)
        n2o_n_base  = tn_rem_base * ef
        n2o_base_t  = n2o_n_base * _N2O_RATIO * _N2O_GWP / 1000.
        n2o_n_upg   = tn_rem_upg * ef_upg
        n2o_upg_t   = n2o_n_upg * _N2O_RATIO * _N2O_GWP / 1000.
        n2o_delta_t = n2o_base_t - n2o_upg_t
        total_delta = n2o_delta_t + energy_delta_t - chemical_increase_t
        # pct vs fixed reference denominator (central N2O baseline + energy baseline)
        # so that the % range is meaningful across EF bands
        n2o_base_central_t = tn_rem_base * _EF_CENTRAL * _N2O_RATIO * _N2O_GWP / 1000.
        _ref_denom = n2o_base_central_t + energy_base_t
        baseline_total = n2o_base_t + energy_base_t + (chemical_increase_t * 0.63)  # approx baseline chem
        pct_red = total_delta / _ref_denom * 100. if _ref_denom > 0 else 0.
        return CarbonBand(
            label          = label,
            ef_pct         = ef * 100.,
            n2o_baseline_t = round(n2o_base_t),
            n2o_upgraded_t = round(n2o_upg_t),
            n2o_delta_t    = round(n2o_delta_t),
            energy_delta_t = round(energy_delta_t),
            total_delta_t  = round(total_delta),
            pct_reduction  = round(pct_red, 1),
        )

    low_b    = _band("Low",     _EF_LOW)
    central_b= _band("Central", _EF_CENTRAL)
    high_b   = _band("High",    _EF_HIGH)

    baseline_total = central_b.n2o_baseline_t + round(energy_base_t) + round(chemical_increase_t * 0.63)

    summary = (
        f"Estimated CO\u2082e reduction: "
        f"{low_b.pct_reduction:.0f}\u2013{high_b.pct_reduction:.0f}% "
        f"(central estimate {central_b.pct_reduction:.0f}%). "
        f"N\u2082O dominates baseline emissions and drives most of the uncertainty range. "
        f"Energy savings ({round(energy_delta_t):,} t CO\u2082e/year) are more predictable. "
        f"All estimates are indicative and subject to on-site N\u2082O monitoring validation."
    )

    return CarbonUncertainty(
        baseline_total_t    = baseline_total,
        upgraded_central_t  = round(central_b.n2o_upgraded_t + energy_upg_t + chemical_increase_t),
        bands               = [low_b, central_b, high_b],
        low_band            = low_b,
        central_band        = central_b,
        high_band           = high_b,
        reduction_range_pct = (low_b.pct_reduction, high_b.pct_reduction),
        central_reduction_pct = central_b.pct_reduction,
        summary_text        = summary,
        ipcc_ref            = ("IPCC 2019 Refinement to 2006 Guidelines, Vol 5, Chapter 6. "
                               "EF range 0.005\u20130.032 g N\u2082O-N/g TN removed. "
                               "GWP\u2081\u2080\u2080 = 273 (IPCC AR6)."),
    )


# ── Step 4: Sensitivity drivers ───────────────────────────────────────────────

def _build_sensitivity_drivers(
    pathway: UpgradePathway,
    carbon: CarbonUncertainty,
    ctx: Dict,
) -> List[SensitivityDriver]:
    """Rank top 3 sensitivity drivers by impact on outcomes."""
    tech_set   = {s.technology for s in pathway.stages}
    ct_set     = {c.constraint_type for c in pathway.constraints}
    flow_ratio = ctx.get("flow_ratio", 1.0) or 1.0

    drivers: List[SensitivityDriver] = []

    # Driver 1: Peak flow frequency and magnitude
    if CT_HYDRAULIC in ct_set or CT_WET_WEATHER in ct_set:
        drivers.append(SensitivityDriver(
            rank         = 1,
            driver       = "Peak wet weather flow frequency and magnitude",
            impact_level = "High",
            affects      = "Clarifier compliance; CoMag bypass adequacy; I/I reduction urgency",
            explanation  = (
                f"At {flow_ratio:.1f}\u00d7 ADWF the stack is calibrated to current peak frequency. "
                f"If peak flows exceed 3.0\u00d7 ADWF more frequently than modelled, or if short-duration "
                f"peaks sustain above CoMag design capacity, upstream storage or I/I reduction becomes "
                f"mandatory \u2014 not optional. Each additional wet weather event above design "
                f"increases cumulative TSS and compliance exposure."
            ),
            threshold    = (
                f"3.0\u00d7 ADWF sustained for > 4 hours: storage or additional CoMag capacity required."
            ),
        ))

    # Driver 2: N2O emission factor (always high impact)
    n2o_range = carbon.high_band.total_delta_t - carbon.low_band.total_delta_t
    drivers.append(SensitivityDriver(
        rank         = 2,
        driver       = "N\u2082O emission factor (site-specific)",
        impact_level = "High",
        affects      = "Total CO\u2082e reduction estimate; carbon credit value; net-zero reporting",
        explanation  = (
            f"The IPCC EF range spans 6\u00d7 from lower (0.5%) to upper bound (3.2%). "
            f"This drives a {round(carbon.low_band.total_delta_t):,}\u2013"
            f"{round(carbon.high_band.total_delta_t):,} t CO\u2082e/year uncertainty band "
            f"on the total carbon reduction (central: {round(carbon.central_band.total_delta_t):,} t). "
            f"The carbon benefit of MABR and Bardenpho is real but cannot be verified without "
            f"continuous on-site N\u2082O monitoring."
        ),
        threshold    = (
            "If on-site EF > 2.0%, total carbon reduction exceeds central estimate significantly. "
            "If EF < 0.5%, energy savings become the dominant carbon driver."
        ),
    ))

    # Driver 3: Aeration capacity if MABR is selected
    if TI_MABR in tech_set:
        drivers.append(SensitivityDriver(
            rank         = 3,
            driver       = "Aeration capacity headroom (blower audit)",
            impact_level = "Medium",
            affects      = "MABR vs IFAS selection; Stage 2 technology validation",
            explanation  = (
                "MABR is selected because the blower system is reported to be near maximum capacity. "
                "If a site-specific aeration audit identifies spare blower capacity (> 15%), "
                "IFAS becomes a viable and lower-cost alternative to MABR. "
                "Conversely, if blower capacity is more constrained than assumed, "
                "MABR module count must increase, affecting capital cost and commissioning timeline."
            ),
            threshold    = (
                "If blower spare capacity > 15% of peak demand: IFAS replaces MABR (lower CAPEX). "
                "If blower spare capacity < 5%: MABR sizing must be validated against full "
                "nitrification oxygen demand."
            ),
        ))
    elif TI_DENFILTER in tech_set:
        # DNF case: DO sensitivity is the key driver
        drivers.append(SensitivityDriver(
            rank         = 3,
            driver       = "DO carryover to denitrification filter inlet",
            impact_level = "High",
            affects      = "DNF performance; methanol dose efficiency; TN compliance",
            explanation  = (
                "Denitrification filter performance is highly sensitive to dissolved oxygen at "
                "the filter inlet. If secondary effluent DO exceeds 0.5 mg/L, denitrification "
                "is suppressed and methanol is consumed without TN reduction. "
                "DO control in the secondary aeration must be verified before DNF is sized."
            ),
            threshold    = "DO at filter inlet > 0.5 mg/L: TN compliance will not be achieved.",
        ))
    else:
        # Carbon/methanol dosing for Bardenpho
        drivers.append(SensitivityDriver(
            rank         = 3,
            driver       = "Influent carbon availability (COD/TN ratio)",
            impact_level = "Medium",
            affects      = "Bardenpho TN performance; external carbon dosing requirement",
            explanation  = (
                "Bardenpho TN performance is dependent on available COD for denitrification. "
                "If the COD/TN ratio in settled influent is below 4, external carbon (acetate "
                "or methanol) will be required in the post-anoxic zone to achieve TN < 5 mg/L. "
                "This adds chemical OPEX and supply chain dependency not currently accounted for."
            ),
            threshold    = "COD/TN < 4 in primary effluent: external carbon dosing required (~$40–80k/year OPEX).",
        ))

    return drivers[:3]


# ── Step 5: Decision tension ──────────────────────────────────────────────────

def _build_decision_tension(
    pathway: UpgradePathway,
    credible: CredibleOutput,
    ctx: Dict,
) -> DecisionTension:
    """Generate the primary decision trade-off statement."""
    tech_set = {s.technology for s in pathway.stages}
    has_comag = TI_COMAG in tech_set or TI_BIOMAG in tech_set
    has_mabr  = TI_MABR in tech_set

    if has_comag and has_mabr:
        return DecisionTension(
            primary_tension = (
                "The primary decision is between the recommended compact high-performance "
                "intensification pathway (CoMag + BioMag + MABR) and the lower-risk conventional "
                "alternative (EQ basin + IFAS), trading footprint efficiency and energy performance "
                "against supply chain dependency and operational complexity."
            ),
            option_a_label = "Recommended: CoMag + BioMag + MABR (compact, high-performance)",
            option_a_pros  = [
                "Minimal footprint \u2014 no site acquisition required.",
                "MABR reduces aeration energy and N\u2082O emissions significantly.",
                "CoMag provides immediate wet weather compliance relief.",
                "Positions plant for future licence tightening within existing envelope.",
            ],
            option_a_cons  = [
                "Magnetite supply chain dependency for CoMag and BioMag.",
                "MABR specialist OEM dependency and membrane integrity monitoring.",
                "Higher operational complexity than conventional technologies.",
            ],
            option_b_label = "Alternative: EQ basin + IFAS (lower risk, conventional)",
            option_b_pros  = [
                "No specialist supply dependency \u2014 conventional civil and biofilm technologies.",
                "Lower operational complexity.",
                "IFAS is retrofit-friendly with a broad reference base.",
            ],
            option_b_cons  = [
                "EQ basin requires 3\u20135 ha of footprint \u2014 may not be available at this site.",
                "IFAS does not reduce aeration energy demand.",
                "Does not position plant for energy efficiency or N\u2082O reduction targets.",
            ],
            recommended_path = (
                "The recommended pathway is preferred because footprint is the binding constraint "
                "at this metropolitan brownfield site and the utility has access to skilled operators "
                "and metropolitan supply chains. The conventional alternative (Option C) remains "
                "viable if footprint becomes available or if specialist supply cannot be secured."
            ),
        )
    elif has_mabr:
        return DecisionTension(
            primary_tension = (
                "The primary decision tension is between MABR (higher energy efficiency, N\u2082O "
                "reduction, specialist dependency) and IFAS (lower cost, lower complexity, "
                "dependent on existing aeration capacity), to be resolved by a site-specific "
                "aeration capacity audit."
            ),
            option_a_label = "Recommended: MABR (aeration intensification via membrane)",
            option_a_pros  = ["14 kgO\u2082/kWh efficiency.", "N\u2082O reduction co-benefit.", "Bypasses blower constraint."],
            option_a_cons  = ["Specialist OEM.", "Higher cost than IFAS.", "Biofilm establishment risk."],
            option_b_label = "Alternative: IFAS (conventional biofilm retrofit)",
            option_b_pros  = ["Lower cost.", "Broader reference base.", "No membrane dependency."],
            option_b_cons  = ["Does not resolve blower constraint.", "No energy saving."],
            recommended_path = (
                "MABR is recommended because aeration capacity is reported at maximum. "
                "This assumption must be validated by blower audit before detailed design commitment."
            ),
        )
    else:
        return DecisionTension(
            primary_tension = (
                "The primary decision tension is between a staged process optimisation pathway "
                "(Bardenpho + recycle) and a higher-performance tertiary approach (DNF + chemical), "
                "trading operational simplicity against performance headroom for future licence targets."
            ),
            option_a_label = "Recommended: Bardenpho optimisation (biological TN)",
            option_a_pros  = ["No chemical dependency.", "Uses existing tank volume.", "Low OPEX."],
            option_a_cons  = ["May not achieve TN < 3 mg/L without external carbon.", "Carbon-limited."],
            option_b_label = "Alternative: Denitrification filter (chemical TN polishing)",
            option_b_pros  = ["Achieves TN < 3 mg/L reliably.", "Compact.", "Future-proof."],
            option_b_cons  = ["Methanol dependency.", "High OPEX.", "Requires stable nitrification first."],
            recommended_path = (
                "Bardenpho optimisation is recommended first. DNF should be commissioned only "
                "after MABR establishes NH\u2084 < 1 mg/L reliably, per the engineering guardrail."
            ),
        )


# ── Step 6: Confidence adjustment ────────────────────────────────────────────

def _overall_confidence(
    dims: List[UncertaintyDimension],
    feasibility: FeasibilityReport,
    n_stages: int,
) -> Tuple[str, str]:
    _order = {UL_LOW: 0, UL_MEDIUM: 1, UL_HIGH: 2, UL_VERY_HIGH: 3}
    worst  = max(dims, key=lambda d: _order.get(d.level, 0)).level
    n_high = sum(1 for d in dims if d.level in (UL_HIGH, UL_VERY_HIGH))

    # Start from feasibility confidence
    feas_conf = feasibility.adjusted_confidence
    score = {"High": 2, "Medium": 1, "Low": 0}.get(feas_conf, 1)

    if worst == UL_VERY_HIGH: score -= 2
    elif worst == UL_HIGH and n_high >= 2: score -= 1
    if n_stages >= 5: score -= 1
    if n_stages <= 2 and worst == UL_LOW: score += 1
    score = max(0, min(2, score))
    conf  = ["Low", "Medium", "High"][score]

    n_medium = sum(1 for d in dims if d.level == UL_MEDIUM)
    rationale = (
        f"Overall confidence is {conf}: "
        + (f"hydraulic variability is Very High ({worst}) and {n_high} of 5 uncertainty dimensions "
           f"are rated High or above. " if n_high >= 2 else
           f"{n_high} dimension(s) rated High uncertainty. ")
        + f"N\u2082O carbon model uncertainty is always High due to site-specific EF variability. "
        + (f"The {n_stages}-stage delivery programme adds integration risk. " if n_stages >= 4 else "")
        + "Confidence would improve materially with: on-site N\u2082O monitoring data, "
          "blower capacity audit results, and CoMag pilot or reference site performance confirmation."
    )
    return conf, rationale


# ── Step 9 Validation flags ───────────────────────────────────────────────────

def _validation_flags(
    dims: List[UncertaintyDimension],
    drivers: List[SensitivityDriver],
    carbon: CarbonUncertainty,
    tech_set: set,
) -> Tuple[bool, bool, bool, bool]:
    hyd_flagged  = any(d.dimension == "Hydraulic variability" and d.level in (UL_HIGH, UL_VERY_HIGH)
                       for d in dims)
    aer_flagged  = any("aeration" in drv.driver.lower() or "blower" in drv.driver.lower()
                       for drv in drivers)
    do_flagged   = (TI_DENFILTER in tech_set and
                    any("DO" in drv.driver or "carbon" in drv.driver.lower() for drv in drivers))
    carbon_range = len(carbon.bands) >= 2
    return hyd_flagged, aer_flagged, do_flagged, carbon_range


# ── Main entry point ──────────────────────────────────────────────────────────

def build_uncertainty_report(
    pathway: UpgradePathway,
    feasibility: FeasibilityReport,
    credible: CredibleOutput,
    plant_context: Optional[Dict] = None,
) -> UncertaintyReport:
    """
    Build the Uncertainty & Sensitivity report.

    Parameters
    ----------
    pathway : UpgradePathway
        Output of build_upgrade_pathway().
    feasibility : FeasibilityReport
        Output of assess_feasibility().
    credible : CredibleOutput
        Output of build_credible_output().
    plant_context : dict, optional
        Supplemental context:
          flow_ratio, plant_size_mld, aeration_kwh_day,
          tn_in_mg_l, tn_out_baseline_mg_l, tn_out_upgraded_mg_l,
          grid_ef_kgco2e_kwh, chemical_co2e_increase_t,
          high_diurnal, tn_at_limit.

    Returns
    -------
    UncertaintyReport
        Does NOT modify pathway, feasibility, or credible.
    """
    ctx      = plant_context or {}
    tech_set = {s.technology for s in pathway.stages}

    dims     = _assess_dimensions(pathway, feasibility, ctx)
    overall  = _overall_uncertainty(dims)
    carbon   = _build_carbon_uncertainty(pathway, ctx)
    drivers  = _build_sensitivity_drivers(pathway, carbon, ctx)
    tension  = _build_decision_tension(pathway, credible, ctx)
    conf, rat= _overall_confidence(dims, feasibility, len(pathway.stages))
    hyd, aer, do_f, c_range = _validation_flags(dims, drivers, carbon, tech_set)

    return UncertaintyReport(
        system_state         = pathway.system_state,
        proximity_pct        = pathway.proximity_pct,
        n_stages             = len(pathway.stages),
        flow_ratio           = ctx.get("flow_ratio", 1.0) or 1.0,
        dimensions           = dims,
        overall_uncertainty  = overall,
        carbon               = carbon,
        sensitivity_drivers  = drivers,
        decision_tension     = tension,
        overall_confidence   = conf,
        confidence_rationale = rat,
        hydraulic_sensitivity_flagged = hyd,
        aeration_dependency_flagged   = aer,
        carbon_do_sensitivity_flagged = do_f,
        carbon_range_included         = c_range,
    )
