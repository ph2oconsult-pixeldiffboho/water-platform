"""
BioPoint core dataclasses.
All platform data flows through these structures.

ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional


# ===========================================================================
# INPUTS
# ===========================================================================

@dataclass
class PlantSizingInputs:
    """
    Dual-mode plant sizing.
    User selects either sludge_volume_mode or vs_load_mode.
    Engine resolves both regardless of which is primary.
    """
    sizing_mode: str = "VOLUME"          # "VOLUME" | "VS_LOAD"

    # --- VOLUME MODE ---
    sludge_volume_m3_d: Optional[float] = None   # m³/d feed sludge
    ts_feed_pct: Optional[float] = None           # Feed TS %
    vs_ts_ratio: Optional[float] = None           # VS/TS (dimensionless)

    # --- VS LOAD MODE ---
    vs_load_kg_d: Optional[float] = None          # kg VS/d direct input

    # --- RESOLVED (populated by engine regardless of mode) ---
    resolved_vs_load_kg_d: float = 0.0
    resolved_sludge_volume_m3_d: float = 0.0
    resolved_ts_load_kg_d: float = 0.0


@dataclass
class FeedstockInputs:
    feedstock_type: str = "PS_WAS"       # "WAS" | "PS" | "PS_WAS"
    blend_ratio_ps: float = 0.50         # Fraction PS by mass (0–1); ignored if not blend

    # Optional overrides — if None, engine uses M&E defaults
    ts_pct_override: Optional[float] = None
    vs_ts_ratio_override: Optional[float] = None


@dataclass
class StabilisationInputs:
    stabilisation: str = "MAD"           # "MAD" | "MAD_THP" | "NONE"
    hrt_days: float = 30.0               # User-adjustable; engine warns if <15 or >50
    digester_temp_C: float = 35.0        # Mesophilic default

    # THP parameters — active only if stabilisation == "MAD_THP"
    thp_hrt_override: Optional[float] = None   # If None, engine auto-reduces HRT
    thp_temp_C: float = 165.0
    thp_pressure_bar: float = 6.0


@dataclass
class CHPInputs:
    """Auto-sized to biogas supply — user can override efficiencies."""
    electrical_efficiency: float = 0.35
    thermal_efficiency_jacket: float = 0.25
    thermal_efficiency_exhaust: float = 0.20
    parasitic_fraction: float = 0.08


@dataclass
class ContextInputs:
    climate_zone: str = "TEMPERATE"      # "TROPICAL"|"SUBTROPICAL"|"TEMPERATE"|"COOL_TEMPERATE"
    pfas_flag: bool = False
    drying_route: str = "NONE"           # "SOLAR" | "THERMAL" | "NONE"
    thermal_route: str = "NONE"          # "INCINERATION"|"GASIFICATION"|"PYROLYSIS"|"NONE"


@dataclass
class BioPointInputs:
    """Master input container passed to all engine modules."""
    sizing: PlantSizingInputs = field(default_factory=PlantSizingInputs)
    feedstock: FeedstockInputs = field(default_factory=FeedstockInputs)
    stabilisation: StabilisationInputs = field(default_factory=StabilisationInputs)
    chp: CHPInputs = field(default_factory=CHPInputs)
    context: ContextInputs = field(default_factory=ContextInputs)
    # Production and logistics — optional, engine uses sizing defaults if absent
    production_mode: str = "DIRECT"          # "DIRECT" | "COD"
    growth_rate_pct_yr: float = 2.0
    projection_years: int = 20
    flow_ML_d: Optional[float] = None
    cod_influent_mg_L: Optional[float] = None
    haul_distance_km: float = 50.0
    truck_payload_t: float = 20.0
    storage_days: float = 7.0
    disposal_unit_cost_per_t_DS: Optional[float] = None
    # Trigger engine inputs
    contract_renewal_years: Optional[float] = None
    infrastructure_age_years: Optional[float] = None
    disposal_cost_escalation_pct_yr: float = 5.0


# ===========================================================================
# FEEDSTOCK CHARACTERISATION OUTPUTS
# ===========================================================================

@dataclass
class FeedstockProfile:
    """Resolved feedstock properties — blend-weighted where applicable."""
    feedstock_type: str = ""
    blend_ratio_ps: float = 0.0

    ts_pct: float = 0.0
    vs_ts_ratio: float = 0.0
    vs_pct: float = 0.0                  # VS as % of wet mass = TS% × VS/TS

    vs_load_kg_d: float = 0.0
    ts_load_kg_d: float = 0.0
    sludge_volume_m3_d: float = 0.0

    methane_content_pct: float = 0.0     # Blend-weighted CH₄ %
    biogas_yield_m3_per_kgVSd: float = 0.0  # Blend-weighted
    cake_ds_pct_baseline: float = 0.0    # Pre-digestion baseline

    pfas_risk_tier: str = "LOW"          # "LOW" | "MEDIUM" | "HIGH"
    pathogen_class_raw: str = ""
    density_kg_m3: float = 1015.0


# ===========================================================================
# MAD OUTPUTS
# ===========================================================================

@dataclass
class MADOutputs:
    """Mesophilic anaerobic digestion performance."""
    hrt_days: float = 30.0
    digester_temp_C: float = 35.0
    thp_applied: bool = False

    # VSR
    vsr_pct: float = 0.0                 # Volatile solids reduction %
    vs_destroyed_kg_d: float = 0.0
    vs_effluent_kg_d: float = 0.0

    # Biogas
    biogas_yield_m3_per_kgVSd: float = 0.0
    methane_content_pct: float = 0.0
    biogas_total_m3_d: float = 0.0
    methane_total_m3_d: float = 0.0
    biogas_energy_MJ_d: float = 0.0      # Lower heating value basis

    # Digested cake (pre-dewatering)
    ts_digested_kg_d: float = 0.0        # TS remaining after digestion
    cake_ds_pct: float = 0.0             # Dewatered cake DS %
    cake_mass_kg_d: float = 0.0          # Wet cake mass
    filtrate_volume_m3_d: float = 0.0    # Return liquor


# ===========================================================================
# THP DELTA OUTPUTS
# ===========================================================================

@dataclass
class THPDelta:
    """Incremental benefit of THP over base MAD."""
    applied: bool = False

    # HRT
    hrt_base_days: float = 30.0
    hrt_post_thp_days: float = 15.0
    hrt_reduction_pct: float = 0.0

    # VSR
    delta_vsr_pct: float = 0.0          # Absolute percentage point improvement
    vsr_with_thp_pct: float = 0.0

    # Biogas
    delta_biogas_pct: float = 0.0       # % uplift in total biogas
    delta_methane_content_pct: float = 0.0

    # Cake
    delta_cake_ds_pct: float = 0.0      # Absolute pp improvement in dewatered DS

    # THP energy demand
    steam_demand_MJ_d: float = 0.0
    steam_demand_kWh_d: float = 0.0


# ===========================================================================
# MASS BALANCE
# ===========================================================================

@dataclass
class MassBalance:
    """
    Full mass balance across the stabilisation + dewatering boundary.
    All values in kg/d unless noted.
    """
    # --- INPUTS ---
    ts_in_kg_d: float = 0.0
    vs_in_kg_d: float = 0.0
    water_in_kg_d: float = 0.0
    total_mass_in_kg_d: float = 0.0

    # --- DESTRUCTION ---
    vs_destroyed_kg_d: float = 0.0
    fsi_in_kg_d: float = 0.0            # Fixed (inorganic) solids in
    fsi_out_kg_d: float = 0.0           # FSI largely conserved

    # --- BIOGAS ---
    biogas_mass_kg_d: float = 0.0       # Mass equivalent (biogas as gas)
    methane_mass_kg_d: float = 0.0
    co2_mass_kg_d: float = 0.0

    # --- DIGESTED SLUDGE ---
    ts_digested_kg_d: float = 0.0
    vs_digested_kg_d: float = 0.0
    total_digested_mass_kg_d: float = 0.0
    digested_volume_m3_d: float = 0.0

    # --- DEWATERED CAKE ---
    cake_ts_kg_d: float = 0.0
    cake_ds_pct: float = 0.0
    cake_wet_mass_kg_d: float = 0.0
    cake_volume_m3_d: float = 0.0       # Approximate

    # --- FILTRATE / RETURN LIQUOR ---
    filtrate_volume_m3_d: float = 0.0
    filtrate_ts_kg_d: float = 0.0       # ~5–8% of cake TS rejected

    # --- CLOSURE CHECK ---
    mass_balance_error_pct: float = 0.0  # Should be <1%


# ===========================================================================
# HEAT BALANCE
# ===========================================================================

@dataclass
class HeatBalance:
    """
    Digester heat demand vs available recovery from CHP.
    All values in MJ/d unless noted.
    """
    # --- DEMAND ---
    feed_heating_MJ_d: float = 0.0      # Heat to raise feed to digester temp
    digester_wall_loss_MJ_d: float = 0.0
    digester_floor_loss_MJ_d: float = 0.0
    digester_cover_loss_MJ_d: float = 0.0
    thp_steam_demand_MJ_d: float = 0.0  # 0 if no THP
    total_heat_demand_MJ_d: float = 0.0

    # --- SUPPLY (from CHP) ---
    chp_jacket_heat_MJ_d: float = 0.0
    chp_exhaust_heat_MJ_d: float = 0.0
    total_heat_recovered_MJ_d: float = 0.0

    # --- BALANCE ---
    heat_surplus_deficit_MJ_d: float = 0.0   # +ve = surplus, -ve = shortfall
    heat_self_sufficient: bool = False
    auxiliary_heat_required_MJ_d: float = 0.0  # Gas boiler top-up if needed

    # --- DIGESTER GEOMETRY (auto-sized) ---
    digester_volume_m3: float = 0.0
    digester_diameter_m: float = 0.0
    digester_height_m: float = 0.0
    wall_area_m2: float = 0.0
    floor_area_m2: float = 0.0
    cover_area_m2: float = 0.0


# ===========================================================================
# ENERGY BALANCE / CHP
# ===========================================================================

@dataclass
class EnergyBalance:
    """
    CHP electrical and thermal outputs vs plant demand.
    All values in kWh/d unless noted.
    """
    # --- BIOGAS INPUT ---
    biogas_total_m3_d: float = 0.0
    methane_total_m3_d: float = 0.0
    biogas_energy_MJ_d: float = 0.0
    biogas_energy_kWh_d: float = 0.0

    # --- CHP SIZING ---
    chp_capacity_kWe: float = 0.0       # Auto-sized
    chp_runtime_h_d: float = 22.0       # Allow 2h/d maintenance

    # --- CHP ELECTRICAL ---
    gross_electrical_kWh_d: float = 0.0
    parasitic_kWh_d: float = 0.0
    net_electrical_kWh_d: float = 0.0

    # --- CHP THERMAL ---
    jacket_heat_kWh_d: float = 0.0
    exhaust_heat_kWh_d: float = 0.0
    total_heat_kWh_d: float = 0.0

    # --- PLANT DEMAND (estimated from VS load) ---
    estimated_plant_demand_kWh_d: float = 0.0   # Aeration + ancillaries simplified
    digester_mixing_kWh_d: float = 0.0
    dewatering_kWh_d: float = 0.0
    total_parasitic_process_kWh_d: float = 0.0

    # --- NET POSITION ---
    net_electrical_export_kWh_d: float = 0.0    # +ve = export, -ve = import
    electrical_self_sufficiency_pct: float = 0.0
    energy_self_sufficient: bool = False

    # --- EFFICIENCIES ---
    electrical_efficiency: float = 0.35
    thermal_efficiency: float = 0.45
    overall_efficiency: float = 0.80


# ===========================================================================
# PFAS CONSTRAINT
# ===========================================================================

@dataclass
class PFASConstraint:
    flagged: bool = False
    risk_tier: str = "LOW"               # "LOW" | "MEDIUM" | "HIGH"
    route_status: str = "OPEN"           # "OPEN" | "CONSTRAINED" | "CLOSED"
    constraint_narrative: str = ""
    affected_routes: list = field(default_factory=list)


# ===========================================================================
# PATHWAY RESULT — MASTER OUTPUT
# ===========================================================================

@dataclass
class PathwayResult:
    """Master output container — assembles all engine outputs."""
    inputs: Optional[BioPointInputs] = None
    feedstock_profile: Optional[FeedstockProfile] = None
    mad_outputs: Optional[MADOutputs] = None
    thp_delta: Optional[THPDelta] = None
    mass_balance: Optional[MassBalance] = None
    heat_balance: Optional[HeatBalance] = None
    energy_balance: Optional[EnergyBalance] = None
    pfas_constraint: Optional[PFASConstraint] = None
    drying_result: Optional[object] = None    # DryingResult — typed loosely to avoid circular
    thermal_result: Optional[object] = None   # ThermalResult
    production_result: Optional[object] = None  # ProductionResult
    logistics_result: Optional[object] = None   # LogisticsResult
    decision_spine: Optional[object] = None     # DecisionSpine
    sludge_character: Optional[object] = None   # SludgeCharacter
    trigger_assessment: Optional[object] = None # TriggerAssessment
    adaptive_pathway: Optional[object] = None   # AdaptivePathway

    # --- PATHWAY CLASSIFICATION ---
    stabilisation_class: str = ""        # "CLASS_A" | "CLASS_B" | "NONE"
    recommended_route: str = ""
    route_confidence: str = ""           # "HIGH" | "MEDIUM" | "LOW"

    # --- NARRATIVE ---
    causal_narrative: str = ""
    deferral_consequences: str = ""
    key_flags: list = field(default_factory=list)

    # --- WATERPOINT BRIDGE ---
    waterpoint_handoff: dict = field(default_factory=dict)

    # --- VALIDATION ---
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
