"""
BioPoint V1 — Input Schema.
Structured input model covering feedstock, existing assets, and strategic drivers.
All inputs carry explicit units and defaults.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# PART 1A — FEEDSTOCK INPUTS
# ---------------------------------------------------------------------------

@dataclass
class FeedstockInputsV2:
    """
    Full feedstock characterisation for flowsheet generation.
    GCV and ash are core to energy and carbon calculations.
    """
    # --- REQUIRED ---
    dry_solids_tpd: float = 1.0             # Dry solids tonnes/day
    dewatered_ds_percent: float = 22.0      # DS% of dewatered feed
    volatile_solids_percent: float = 75.0   # VS as % of DS
    gross_calorific_value_mj_per_kg_ds: float = 12.0  # GCV on DS basis
    ash_percent: float = 25.0              # Ash as % of DS (= 100 - VS approx)

    sludge_type: str = "secondary"         # raw/primary/secondary/digested/
                                            # thp_digested/ags/blended
    feedstock_variability: str = "moderate" # low/moderate/high

    # --- OPTIONAL ---
    particle_size_class: Optional[str] = None       # fine/medium/coarse
    pfas_present: str = "unknown"                   # yes/no/unknown
    metals_risk: str = "low"                        # low/moderate/high

    # --- DERIVED (populated by engine) ---
    wet_sludge_tpd: float = 0.0
    water_in_feed_tpd: float = 0.0
    vs_tpd: float = 0.0
    carbon_fraction_of_ds: float = 0.0     # Estimated from VS%

    def resolve(self) -> "FeedstockInputsV2":
        """Resolve derived values from declared inputs."""
        self.wet_sludge_tpd = self.dry_solids_tpd / (self.dewatered_ds_percent / 100.0)
        self.water_in_feed_tpd = self.wet_sludge_tpd - self.dry_solids_tpd
        self.vs_tpd = self.dry_solids_tpd * (self.volatile_solids_percent / 100.0)
        # Carbon fraction: VS is ~50% carbon by mass (cellulose/protein basis)
        # Adjustable; default 0.50 × VS fraction
        self.carbon_fraction_of_ds = (self.volatile_solids_percent / 100.0) * 0.50
        return self


# ---------------------------------------------------------------------------
# PART 1B — EXISTING ASSET INPUTS
# ---------------------------------------------------------------------------

@dataclass
class AssetInputs:
    """
    Site infrastructure and operating cost context.
    Drives whether certain flowsheets are incremental or greenfield.
    """
    # --- REQUIRED ---
    anaerobic_digestion_present: bool = False
    thp_present: bool = False
    waste_heat_available_kwh_per_day: float = 0.0
    drying_system_present: bool = False
    local_power_price_per_kwh: float = 0.12        # $/kWh
    fuel_price_per_gj: float = 12.0                # $/GJ (natural gas)
    disposal_cost_per_tds: float = 300.0           # $/tonne DS
    transport_cost_per_tonne_km: float = 0.25      # $/tonne/km
    average_transport_distance_km: float = 50.0

    # --- OPTIONAL ---
    chp_present: bool = False
    existing_dryer_type: Optional[str] = None      # belt/drum/paddle/solar
    district_heat_export_possible: bool = False

    # --- DERIVED ---
    baseline_transport_cost_per_day: float = 0.0
    baseline_disposal_cost_per_day: float = 0.0

    def resolve(self, feedstock: FeedstockInputsV2) -> "AssetInputs":
        self.baseline_transport_cost_per_day = (
            feedstock.wet_sludge_tpd
            * self.average_transport_distance_km
            * self.transport_cost_per_tonne_km
        )
        self.baseline_disposal_cost_per_day = (
            feedstock.dry_solids_tpd * self.disposal_cost_per_tds
        )
        return self


# ---------------------------------------------------------------------------
# PART 1C — STRATEGIC DRIVER INPUTS
# ---------------------------------------------------------------------------

@dataclass
class StrategicInputs:
    """
    Optimisation priorities and market/regulatory context.
    Drives weighting in the optimisation engine.
    """
    # --- REQUIRED ---
    optimisation_priority: str = "balanced"
    # lowest_cost / lowest_carbon / highest_resilience /
    # lowest_disposal_dependency / balanced

    regulatory_pressure: str = "moderate"          # low/moderate/high
    carbon_credit_value_per_tco2e: float = 50.0    # $/tCO2e
    biochar_market_confidence: str = "low"         # low/moderate/high

    # --- OPTIONAL ---
    land_constraint: str = "low"                   # low/moderate/high
    social_licence_pressure: str = "low"           # low/moderate/high

    # --- FINANCE ---
    discount_rate_pct: float = 7.0                 # % for CAPEX annualisation
    asset_life_years: int = 20                     # CAPEX annualisation period


# ---------------------------------------------------------------------------
# MASTER INPUT CONTAINER
# ---------------------------------------------------------------------------

@dataclass
class BioPointV1Inputs:
    """
    Master input container for BioPoint V1 calculation engine.
    Pass to FlowsheetGenerator to produce candidate pathways.
    """
    feedstock: FeedstockInputsV2 = field(default_factory=FeedstockInputsV2)
    assets: AssetInputs = field(default_factory=AssetInputs)
    strategic: StrategicInputs = field(default_factory=StrategicInputs)

    def resolve(self) -> "BioPointV1Inputs":
        """Resolve all derived values. Call before passing to engine."""
        self.feedstock.resolve()
        self.assets.resolve(self.feedstock)
        return self
