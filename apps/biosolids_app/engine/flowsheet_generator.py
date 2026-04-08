"""
BioPoint V1 — Flowsheet Generator.
Generates the 8 candidate pathway objects from a single set of inputs.
Each flowsheet is an independent calculation object with its own assumptions.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional
from engine.input_schema import BioPointV1Inputs


# ---------------------------------------------------------------------------
# FLOWSHEET DEFINITION
# ---------------------------------------------------------------------------

@dataclass
class FlowsheetAssumptions:
    """
    Per-flowsheet adjustable assumptions.
    All defaults are conservative engineering midpoints.
    User can override any value.
    """
    # Drying
    target_ds_percent: float = 85.0
    dryer_type: str = "indirect"             # direct/indirect/solar
    drying_specific_energy_kwh_per_kg_water: float = 0.80
    dryer_efficiency: float = 0.75

    # Thermal conversion
    mass_reduction_factor: float = 0.0      # fraction of DS destroyed
    energy_recovery_efficiency: float = 0.0
    autothermal: bool = False               # can process sustain itself?

    # Carbon
    carbon_to_char_fraction: float = 0.0
    carbon_to_gas_fraction: float = 0.0
    carbon_to_emissions_fraction: float = 0.0

    # Product
    product_type: str = "none"              # biochar/hydrochar/syngas/ash/heat/none
    product_market_confidence: str = "low"

    # Economics
    capex_m_dollars: float = 0.0            # Total project CAPEX $M
    opex_fixed_per_year: float = 0.0        # Fixed OPEX $/yr
    labour_cost_per_year: float = 0.0
    maintenance_fraction_of_capex: float = 0.025
    parasitic_power_kwh_per_tds: float = 50.0

    # CAPEX annualisation
    discount_rate_pct: float = 7.0
    asset_life_years: int = 20

    def annualisation_factor(self) -> float:
        """Capital recovery factor (CRF) for CAPEX annualisation."""
        r = self.discount_rate_pct / 100.0
        n = self.asset_life_years
        if r == 0:
            return 1.0 / n
        return r * (1 + r)**n / ((1 + r)**n - 1)

    def annualised_capex(self) -> float:
        """$/year annualised CAPEX."""
        return self.capex_m_dollars * 1_000_000 * self.annualisation_factor()


@dataclass
class Flowsheet:
    """
    A single candidate pathway — the atomic unit of BioPoint V1.
    All calculation engines operate on this object.
    """
    flowsheet_id: str = ""
    name: str = ""
    description: str = ""
    pathway_type: str = ""      # baseline/AD/drying/pyrolysis/gasification/HTC/centralised/decentralised/incineration
    assumptions: FlowsheetAssumptions = field(default_factory=FlowsheetAssumptions)
    inputs: Optional[BioPointV1Inputs] = None
    mandatory_benchmark: bool = False   # True for incineration at >50 tDS/d

    # Populated by calculation engines
    mass_balance: Optional[object] = None
    drying_calc: Optional[object] = None
    energy_balance: Optional[object] = None
    compatibility: Optional[object] = None
    carbon_balance: Optional[object] = None
    product_pathway: Optional[object] = None
    economics: Optional[object] = None
    risk: Optional[object] = None
    energy_system: Optional[object] = None        # EnergySystemResult
    mainstream_coupling: Optional[object] = None  # MainstreamCouplingResult
    coupling_classification: Optional[object] = None  # CouplingClassification
    siting: Optional[object] = None               # SitingProfile
    drying_dominance: Optional[object] = None     # DryingDominanceResult
    its_classification: Optional[object] = None   # ITSClassificationResult
    thermal_biochar: Optional[object] = None       # ThermalBiocharResult
    pyrolysis_envelope: Optional[object] = None    # PyrolysisOperatingEnvelope
    pyrolysis_tradeoff: Optional[object] = None    # TradeOffCurve

    # Scoring
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    decision_status: str = ""   # Preferred/Viable but conditional/Not recommended
    rank: int = 0

    # Output card
    output_card: Optional[object] = None


# ---------------------------------------------------------------------------
# FLOWSHEET GENERATOR
# ---------------------------------------------------------------------------

# Default assumptions per pathway type
_PATHWAY_DEFAULTS = {

    "baseline": dict(
        target_ds_percent=22.0,        # No drying — transport as-is
        dryer_type="none",
        drying_specific_energy_kwh_per_kg_water=0.0,
        mass_reduction_factor=0.0,
        energy_recovery_efficiency=0.0,
        autothermal=False,
        carbon_to_char_fraction=0.0,
        carbon_to_gas_fraction=0.0,
        carbon_to_emissions_fraction=0.02,   # Fugitive/decomposition
        product_type="none",
        product_market_confidence="low",
        capex_m_dollars=0.0,
        opex_fixed_per_year=0.0,
        parasitic_power_kwh_per_tds=5.0,
    ),

    "AD": dict(
        target_ds_percent=22.0,        # Post-digestion dewatered cake
        dryer_type="none",
        drying_specific_energy_kwh_per_kg_water=0.0,
        mass_reduction_factor=0.45,    # ~45% VS destruction at 30d HRT
        energy_recovery_efficiency=0.35,
        autothermal=False,
        carbon_to_char_fraction=0.0,
        carbon_to_gas_fraction=0.45,   # Biogas (ultimately combusted)
        carbon_to_emissions_fraction=0.05,
        product_type="heat",
        product_market_confidence="moderate",
        capex_m_dollars=5.0,           # Scaled to 1 tDS/d reference; engine scales
        opex_fixed_per_year=150_000,
        parasitic_power_kwh_per_tds=80.0,
    ),

    "drying_only": dict(
        target_ds_percent=82.0,
        dryer_type="indirect",
        drying_specific_energy_kwh_per_kg_water=0.80,
        dryer_efficiency=0.75,
        mass_reduction_factor=0.0,
        energy_recovery_efficiency=0.0,
        autothermal=False,
        carbon_to_char_fraction=0.0,
        carbon_to_gas_fraction=0.0,
        carbon_to_emissions_fraction=0.01,
        product_type="dried_sludge",
        product_market_confidence="low",
        capex_m_dollars=3.5,
        opex_fixed_per_year=100_000,
        parasitic_power_kwh_per_tds=60.0,
    ),

    "pyrolysis": dict(
        target_ds_percent=87.0,        # UKWIR: typically 85-90% DS
        dryer_type="indirect",
        drying_specific_energy_kwh_per_kg_water=0.80,
        dryer_efficiency=0.75,
        mass_reduction_factor=0.55,    # 40-70% DS destruction; mid 55%
        energy_recovery_efficiency=0.30,
        autothermal=True,              # Near-autothermal at adequate GCV + DS
        carbon_to_char_fraction=0.35,  # Biochar sequesters ~35% input C
        carbon_to_gas_fraction=0.40,   # Pyrolysis gas / bio-oil combusted
        carbon_to_emissions_fraction=0.25,
        product_type="biochar",
        product_market_confidence="low",
        capex_m_dollars=8.0,
        opex_fixed_per_year=200_000,
        parasitic_power_kwh_per_tds=120.0,
    ),

    "gasification": dict(
        target_ds_percent=90.0,        # Gasification spec: ~90% DS
        dryer_type="direct",
        drying_specific_energy_kwh_per_kg_water=1.0,
        dryer_efficiency=0.55,
        mass_reduction_factor=0.80,    # 70-92% mass reduction
        energy_recovery_efficiency=0.25,
        autothermal=True,
        carbon_to_char_fraction=0.05,  # Residual char/ash
        carbon_to_gas_fraction=0.70,   # Syngas
        carbon_to_emissions_fraction=0.25,
        product_type="syngas",
        product_market_confidence="low",
        capex_m_dollars=12.0,
        opex_fixed_per_year=300_000,
        parasitic_power_kwh_per_tds=150.0,
    ),

    "HTC": dict(
        target_ds_percent=22.0,        # No thermal pre-drying required
        dryer_type="none",
        drying_specific_energy_kwh_per_kg_water=0.0,
        mass_reduction_factor=0.35,    # Hydrochar yield: ~35-50% DS
        energy_recovery_efficiency=0.0,
        autothermal=False,
        carbon_to_char_fraction=0.50,  # Hydrochar retains ~50% input C
        carbon_to_gas_fraction=0.10,   # Process CO2
        carbon_to_emissions_fraction=0.15,
        product_type="hydrochar",
        product_market_confidence="low",
        capex_m_dollars=7.0,
        opex_fixed_per_year=180_000,
        parasitic_power_kwh_per_tds=100.0,
    ),

    "centralised": dict(
        # Multi-site import hub — drying + pyrolysis assumed
        target_ds_percent=87.0,
        dryer_type="indirect",
        drying_specific_energy_kwh_per_kg_water=0.80,
        dryer_efficiency=0.75,
        mass_reduction_factor=0.55,
        energy_recovery_efficiency=0.30,
        autothermal=True,
        carbon_to_char_fraction=0.35,
        carbon_to_gas_fraction=0.40,
        carbon_to_emissions_fraction=0.25,
        product_type="biochar",
        product_market_confidence="low",
        capex_m_dollars=15.0,          # Hub scale — higher absolute but lower per-tonne
        opex_fixed_per_year=350_000,
        parasitic_power_kwh_per_tds=120.0,
    ),

    "decentralised": dict(
        # Site-based treatment — drying only or small pyrolysis
        target_ds_percent=82.0,
        dryer_type="indirect",
        drying_specific_energy_kwh_per_kg_water=0.80,
        dryer_efficiency=0.75,
        mass_reduction_factor=0.0,
        energy_recovery_efficiency=0.0,
        autothermal=False,
        carbon_to_char_fraction=0.0,
        carbon_to_gas_fraction=0.0,
        carbon_to_emissions_fraction=0.01,
        product_type="dried_sludge",
        product_market_confidence="low",
        capex_m_dollars=2.5,
        opex_fixed_per_year=80_000,
        parasitic_power_kwh_per_tds=55.0,
    ),

    "incineration": dict(
        # Mandatory benchmark at >50 tDS/d; included for all scales for comparison.
        # Reference: M&E 5th ed. Ch.15; WEF MOP 8; IEA CHP guidelines.
        # DS target: autothermal above ~30% DS (FBF); thermal drying to 75-85% DS
        # enables positive energy balance and eliminates auxiliary fuel.
        target_ds_percent=78.0,            # Mid of 75-85% DS range — autothermal with recovery
        dryer_type="indirect",
        drying_specific_energy_kwh_per_kg_water=0.80,
        dryer_efficiency=0.75,
        # Mass reduction: incineration is highest — 85-95% of original wet mass
        # DS residual as ash: ~25-35% of DS in (inorganic fraction)
        mass_reduction_factor=0.70,        # 70% DS destruction (VS + partial inorganic)
        # Energy recovery: FBF → steam → turbine → electricity
        # Gross electrical efficiency ~15-22% on feedstock LHV basis at utility scale
        energy_recovery_efficiency=0.18,
        autothermal=True,                  # Self-sustaining above ~30% DS (confirmed full-scale)
        # Carbon: all VS carbon oxidised to CO2 — no sequestration
        carbon_to_char_fraction=0.0,
        carbon_to_gas_fraction=0.85,       # Combustion gas (CO2 + H2O)
        carbon_to_emissions_fraction=0.15, # Stack CO2 after energy recovery
        product_type="ash",
        product_market_confidence="moderate",  # Ash → construction / P-recovery where permitted
        # CAPEX: FBF + APC + drying is the most capital-intensive thermal route at scale
        # Reference: £150-250M for 50-150 tDS/d UK plants; mid-point scaled to 5 tDS/d
        capex_m_dollars=20.0,              # At 5 tDS/d reference — scales strongly
        opex_fixed_per_year=400_000,
        parasitic_power_kwh_per_tds=200.0, # Higher parasitic: APC, fans, ID fans
        # Incineration-specific fields (stored in assumptions, used by engines)
        # These use the standard FlowsheetAssumptions fields — extra context in description
    ),

    "thp_incineration": dict(
        # Key distinction: THP improves dewatering to ~32% DS, reducing drying burden
        # and moving toward the incineration energy neutrality threshold (28-30% DS).
        target_ds_percent=78.0,
        dryer_type="indirect",
        drying_specific_energy_kwh_per_kg_water=0.80,
        dryer_efficiency=0.75,
        mass_reduction_factor=0.70,        # Same as incineration (post-THP+AD VS destruction)
        energy_recovery_efficiency=0.18,
        autothermal=True,
        carbon_to_char_fraction=0.0,
        carbon_to_gas_fraction=0.85,
        carbon_to_emissions_fraction=0.15,
        product_type="ash",
        product_market_confidence="moderate",
        # CAPEX: incineration + THP capital
        capex_m_dollars=27.0,              # ~35% premium on incineration for THP + enhanced dewatering
        opex_fixed_per_year=550_000,
        parasitic_power_kwh_per_tds=220.0,
    ),

    "HTC_sidestream": dict(
        # HTC pathway with dedicated sidestream treatment of return liquor.
        # Sidestream: SHARON (nitritation) or ANAMMOX reactor treating HTC process water
        # before return to mainstream — eliminates the HIGH mainstream coupling impact.
        # HTC process assumptions unchanged; sidestream adds CAPEX and OPEX.
        target_ds_percent=22.0,        # No pre-drying — same as HTC
        dryer_type="none",
        drying_specific_energy_kwh_per_kg_water=0.0,
        mass_reduction_factor=0.35,
        energy_recovery_efficiency=0.0,
        autothermal=False,
        carbon_to_char_fraction=0.50,
        carbon_to_gas_fraction=0.10,
        carbon_to_emissions_fraction=0.15,
        product_type="hydrochar",
        product_market_confidence="low",
        # CAPEX: HTC + sidestream treatment (SHARON/ANAMMOX ~$0.5M per 100 kgN/d)
        # Sidestream CAPEX is calculated dynamically from NH4 load in coupling engine
        # Base HTC CAPEX + fixed sidestream increment
        capex_m_dollars=10.5,          # HTC ~$7M + sidestream ~$3.5M (at 5 tDS/d ref)
        opex_fixed_per_year=280_000,   # HTC OPEX + sidestream OPEX
        parasitic_power_kwh_per_tds=130.0,  # Slightly higher: sidestream aeration
    ),
}

# Threshold above which incineration is a mandatory benchmark
INCINERATION_MANDATORY_THRESHOLD_TDS_D = 50.0

# CAPEX scaling: reference point calibrated to 5 tDS/d (typical utility scale)
_CAPEX_SCALE_REFERENCE_TDS_D = 5.0   # All defaults calibrated to 5 tDS/d
_CAPEX_SCALE_EXPONENT = 0.65          # Economy of scale factor (0.6 rule)


def generate_flowsheets(inputs: BioPointV1Inputs) -> list:
    """
    Generate all 8 candidate flowsheets from a single set of inputs.
    Returns list[Flowsheet] — each independently populated with assumptions.
    """
    inputs.resolve()
    ds_tpd = inputs.feedstock.dry_solids_tpd

    flowsheets = []
    configs = [
        ("FS01", "Baseline disposal",              "baseline",      "Dewatered sludge → transport → disposal. No treatment upgrade."),
        ("FS02", "AD-led conventional",             "AD",            "Anaerobic digestion → dewatering → land application or disposal."),
        ("FS03", "Drying only",                     "drying_only",   "Dewatered sludge → drying → reduced transport/disposal."),
        ("FS04", "Drying + pyrolysis",              "pyrolysis",     "Dewatered sludge → drying → pyrolysis → biochar + energy → reuse/disposal."),
        ("FS05", "Drying + gasification",           "gasification",  "Dewatered sludge → drying → gasification → syngas/ash → product."),
        ("FS06", "HTC pathway",                     "HTC",           "Wet sludge/digestate → HTC → hydrochar + liquor → reuse/disposal."),
        ("FS07", "Centralised hub",                 "centralised",   "Multi-site import → drying/conversion hub → product/disposal."),
        ("FS08", "Decentralised site-based",        "decentralised", "Site-based drying → local product/disposal."),
        ("FS09", "AD → drying → incineration",          "incineration",      "AD → dewatering → thermal drying → fluidised bed incineration → ash → energy recovery."),
        ("FS10", "AD → THP → dewatering → incineration", "thp_incineration",  "AD → THP → enhanced dewatering (32% DS) → thermal drying → incineration. Closes energy gap."),
        ("FS11", "HTC → sidestream → discharge",         "HTC_sidestream",    "HTC + dedicated sidestream treatment of return liquor (SHARON/ANAMMOX). Eliminates HIGH mainstream impact."),
    ]

    for fid, name, ptype, desc in configs:
        defaults = _PATHWAY_DEFAULTS[ptype].copy()

        # Scale CAPEX to actual DS load using economy-of-scale
        capex_base = defaults.pop("capex_m_dollars")
        if ds_tpd > 0 and capex_base > 0:
            scale_factor = (ds_tpd / _CAPEX_SCALE_REFERENCE_TDS_D) ** _CAPEX_SCALE_EXPONENT
            capex_scaled = capex_base * scale_factor
        else:
            capex_scaled = capex_base

        # Scale fixed OPEX similarly (labour-intensive components don't scale as strongly)
        opex_base = defaults.pop("opex_fixed_per_year")
        opex_scaled = opex_base * max(1.0, (ds_tpd / _CAPEX_SCALE_REFERENCE_TDS_D) ** 0.50)

        # Apply strategic finance parameters
        defaults["discount_rate_pct"] = inputs.strategic.discount_rate_pct
        defaults["asset_life_years"] = inputs.strategic.asset_life_years

        assumptions = FlowsheetAssumptions(
            capex_m_dollars=round(capex_scaled, 2),
            opex_fixed_per_year=round(opex_scaled, 0),
            **defaults,
        )

        is_mandatory_benchmark = (
            ptype == "incineration"
            and ds_tpd >= INCINERATION_MANDATORY_THRESHOLD_TDS_D
        )

        flowsheets.append(Flowsheet(
            flowsheet_id=fid,
            name=name,
            description=desc,
            pathway_type=ptype,
            assumptions=assumptions,
            inputs=inputs,
            mandatory_benchmark=is_mandatory_benchmark,
        ))

    return flowsheets
