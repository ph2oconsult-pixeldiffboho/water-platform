"""
core/project/project_model.py

Central data model for the Water Utility Planning Platform.
All four domain applications share this model structure.
Domain-specific content is contained within typed extension fields.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


# ─────────────────────────────────────────────────────────────────────────────
# ENUMERATIONS
# ─────────────────────────────────────────────────────────────────────────────

class DomainType(str, Enum):
    WASTEWATER = "wastewater"
    DRINKING_WATER = "drinking_water"
    PRW = "prw"
    BIOSOLIDS = "biosolids"

    @classmethod
    def display_names(cls) -> Dict[str, str]:
        return {
            cls.WASTEWATER: "Wastewater Treatment",
            cls.DRINKING_WATER: "Drinking Water Treatment",
            cls.PRW: "Purified Recycled Water",
            cls.BIOSOLIDS: "Biosolids & Sludge Management",
        }

    @property
    def display_name(self) -> str:
        return self.display_names()[self]


class ScenarioType(str, Enum):
    BASE_CASE = "base_case"
    OPTION_A = "option_a"
    OPTION_B = "option_b"
    OPTION_C = "option_c"
    OPTION_D = "option_d"
    SENSITIVITY = "sensitivity"
    PREFERRED = "preferred"

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title()



class PlanningScenario(str, Enum):
    """
    The high-level planning objective for this project.
    Influences recommended pathways, highlighted metrics, and risk weighting.
    """
    CAPACITY_EXPANSION       = "capacity_expansion"
    NUTRIENT_LIMIT_TIGHTENING = "nutrient_limit_tightening"
    ENERGY_OPTIMISATION      = "energy_optimisation"
    CARBON_REDUCTION         = "carbon_reduction"
    BIOSOLIDS_CONSTRAINTS    = "biosolids_constraints"
    REUSE_PRW_INTEGRATION    = "reuse_prw_integration"

    @property
    def display_name(self) -> str:
        return {
            self.CAPACITY_EXPANSION:        "Capacity Expansion",
            self.NUTRIENT_LIMIT_TIGHTENING: "Nutrient Limit Tightening",
            self.ENERGY_OPTIMISATION:       "Energy Optimisation",
            self.CARBON_REDUCTION:          "Carbon Reduction",
            self.BIOSOLIDS_CONSTRAINTS:     "Biosolids Constraints",
            self.REUSE_PRW_INTEGRATION:     "Reuse / Future PRW Integration",
        }[self]

    @property
    def primary_metric(self) -> str:
        """The metric most important for this planning scenario."""
        return {
            self.CAPACITY_EXPANSION:        "capex",
            self.NUTRIENT_LIMIT_TIGHTENING: "effluent_quality",
            self.ENERGY_OPTIMISATION:       "energy",
            self.CARBON_REDUCTION:          "carbon",
            self.BIOSOLIDS_CONSTRAINTS:     "sludge",
            self.REUSE_PRW_INTEGRATION:     "effluent_quality",
        }[self]

class ValidationLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATACLASSES  (produced by core engines, consumed by reporting)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CostItem:
    """
    A single line item passed from a domain technology plugin to the
    CostingEngine.  The engine resolves the unit cost from the assumptions
    library unless unit_cost_override is supplied.
    """
    name: str = ""
    cost_basis_key: str = ""            # Key into assumptions cost library
    quantity: float = 0.0               # Physical quantity (m², kW, m³, etc.)
    unit: str = ""                      # Unit label for display
    unit_cost_override: Optional[float] = None   # If set, bypasses library lookup
    contingency_factor: float = 1.0     # Multiplier (e.g. 1.20 for 20% contingency)
    notes: str = ""


@dataclass
class CostResult:
    """Standardised cost output — consumed by the reporting engine."""
    capex_total: float = 0.0
    capex_breakdown: Dict[str, float] = field(default_factory=dict)
    opex_annual: float = 0.0
    opex_breakdown: Dict[str, float] = field(default_factory=dict)
    lifecycle_cost_annual: float = 0.0
    lifecycle_cost_total: float = 0.0
    specific_cost_per_kl: Optional[float] = None
    specific_cost_per_tonne_ds: Optional[float] = None
    analysis_period_years: int = 30
    discount_rate: float = 0.07
    cost_confidence: str = "±30%"
    currency: str = "AUD"
    price_base_year: int = 2024


@dataclass
class CarbonResult:
    """Standardised carbon output — consumed by the reporting engine."""
    scope_1_tco2e_yr: float = 0.0       # Direct process emissions
    scope_2_tco2e_yr: float = 0.0       # Electricity emissions
    scope_3_tco2e_yr: float = 0.0       # Chemicals, transport, embodied (annualised)
    avoided_tco2e_yr: float = 0.0       # Credits: energy recovery, avoided disposal
    net_tco2e_yr: float = 0.0           # = scope1+2+3 - avoided
    embodied_carbon_tco2e: float = 0.0  # Construction-phase embodied carbon
    carbon_cost_annual: float = 0.0     # $ at assumed carbon price
    specific_kg_co2e_per_kl: Optional[float] = None
    specific_kg_co2e_per_tonne_ds: Optional[float] = None
    grid_emission_factor_used: float = 0.0
    emission_factor_source: str = "Platform defaults"


@dataclass
class RiskItem:
    """A single risk item for scoring."""
    risk_id: str = ""
    category: str = ""          # technical / implementation / operational / regulatory / domain
    name: str = ""
    description: str = ""
    likelihood: int = 3         # 1–5
    consequence: int = 3        # 1–5
    score: float = 0.0          # likelihood × consequence (calculated)
    mitigation: str = ""

    def calculate_score(self) -> float:
        self.score = float(self.likelihood * self.consequence)
        return self.score


@dataclass
class RiskResult:
    """Standardised risk output — consumed by the reporting engine."""
    overall_score: float = 0.0
    overall_level: str = ""             # Low / Medium / High / Very High
    technical_score: float = 0.0
    implementation_score: float = 0.0
    operational_score: float = 0.0
    regulatory_score: float = 0.0
    domain_specific_score: float = 0.0
    risk_items: List[RiskItem] = field(default_factory=list)
    risk_narrative: str = ""


@dataclass
class ValidationMessage:
    """A single validation message."""
    level: ValidationLevel = ValidationLevel.INFO
    field: str = ""
    message: str = ""
    value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "field": self.field,
            "message": self.message,
            "value": self.value,
        }


@dataclass
class ValidationResult:
    """Validation status and messages for a scenario."""
    is_valid: bool = True
    has_warnings: bool = False
    message_count_critical: int = 0
    message_count_warning: int = 0
    message_count_info: int = 0
    messages: List[Dict[str, Any]] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# ASSUMPTIONS SET
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AssumptionsSet:
    """
    Versioned set of assumptions for a scenario.
    Domain defaults are loaded at project creation and merged with shared defaults.
    User overrides are stored separately and tracked for auditability.
    """
    assumptions_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain: DomainType = DomainType.WASTEWATER
    base_version: str = "default"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    cost_assumptions: Dict[str, Any] = field(default_factory=dict)
    carbon_assumptions: Dict[str, Any] = field(default_factory=dict)
    risk_assumptions: Dict[str, Any] = field(default_factory=dict)
    engineering_assumptions: Dict[str, Any] = field(default_factory=dict)

    # User overrides tracked separately for auditability
    user_overrides: Dict[str, Any] = field(default_factory=dict)
    override_log: List[Dict[str, Any]] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# TREATMENT PATHWAY
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TreatmentPathway:
    """
    Represents the selected treatment train for a scenario.
    Technology parameters are stored as a dict and interpreted by the
    domain module — the core has no knowledge of their meaning.
    """
    pathway_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pathway_name: str = ""
    technology_sequence: List[str] = field(default_factory=list)
    # e.g. ["bnr", "mbr"] or ["coagulation", "daf", "rsf", "gac", "uv", "chlorination"]
    technology_parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # e.g. {"mbr": {"design_flux_lmh": 25, "srt_days": 15}}


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO MODEL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScenarioModel:
    """
    A single scenario (planning option) within a project.
    Contains inputs, the selected treatment pathway, and all calculated results.
    """
    scenario_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario_name: str = ""
    scenario_type: ScenarioType = ScenarioType.BASE_CASE
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_modified: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_preferred: bool = False

    # Design inputs
    design_flow_mld: Optional[float] = None
    peak_flow_mld: Optional[float] = None
    planning_horizon_years: int = 30
    domain_inputs: Dict[str, Any] = field(default_factory=dict)
    economic_inputs: Dict[str, Any] = field(default_factory=dict)
    # Domain-specific structured inputs, serialised to dict at storage time

    # Treatment pathway selection
    treatment_pathway: Optional[TreatmentPathway] = None

    # Assumptions applied to this scenario
    assumptions: Optional[AssumptionsSet] = None

    # Calculated results (populated by domain interface + core engines)
    cost_result: Optional[CostResult] = None
    carbon_result: Optional[CarbonResult] = None
    risk_result: Optional[RiskResult] = None
    validation_result: Optional[ValidationResult] = None
    domain_specific_outputs: Dict[str, Any] = field(default_factory=dict)
    # Domain outputs: sludge mass balance, LRV summary, energy balance, etc.

    # Calculation state
    last_calculated_at: Optional[str] = None
    calculation_version: str = "1.0.0"
    is_stale: bool = True  # True when inputs have changed since last calculation

    def mark_stale(self) -> None:
        self.is_stale = True
        self.last_modified = datetime.now(timezone.utc).isoformat()

    def mark_calculated(self) -> None:
        self.is_stale = False
        self.last_calculated_at = datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT METADATA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProjectMetadata:
    """Administrative and descriptive metadata for a project."""
    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str = ""
    domain: DomainType = DomainType.WASTEWATER
    plant_name: str = ""
    plant_location: str = ""
    project_number: str = ""
    client_name: str = ""
    author: str = ""
    reviewer: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_modified: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "1.0.0"
    planning_scenario: Optional[str] = None  # PlanningScenario value
    notes: str = ""
    tags: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# ROOT PROJECT MODEL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProjectModel:
    """
    The root project object.  Shared across all four domain applications.
    Domain-specific content lives inside ScenarioModel.domain_inputs and
    ScenarioModel.domain_specific_outputs — the ProjectModel itself is
    domain-agnostic.
    """
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    scenarios: Dict[str, ScenarioModel] = field(default_factory=dict)
    active_scenario_id: Optional[str] = None
    portfolio_id: Optional[str] = None
    report_metadata: Dict[str, Any] = field(default_factory=dict)
    version_history: List[Dict[str, Any]] = field(default_factory=list)

    # ── Scenario accessors ────────────────────────────────────────────────

    def get_active_scenario(self) -> Optional[ScenarioModel]:
        if self.active_scenario_id:
            return self.scenarios.get(self.active_scenario_id)
        return None

    def get_all_scenarios(self) -> List[ScenarioModel]:
        return list(self.scenarios.values())

    def get_scenario(self, scenario_id: str) -> Optional[ScenarioModel]:
        return self.scenarios.get(scenario_id)

    def add_scenario(self, scenario: ScenarioModel) -> None:
        self.scenarios[scenario.scenario_id] = scenario
        if self.active_scenario_id is None:
            self.active_scenario_id = scenario.scenario_id
        self.metadata.last_modified = datetime.now(timezone.utc).isoformat()

    def set_active_scenario(self, scenario_id: str) -> None:
        if scenario_id not in self.scenarios:
            raise KeyError(f"Scenario '{scenario_id}' not found in project.")
        self.active_scenario_id = scenario_id

    def remove_scenario(self, scenario_id: str) -> None:
        if scenario_id in self.scenarios:
            del self.scenarios[scenario_id]
            if self.active_scenario_id == scenario_id:
                remaining = list(self.scenarios.keys())
                self.active_scenario_id = remaining[0] if remaining else None

    # ── Version history ───────────────────────────────────────────────────

    def log_change(self, description: str, author: str = "") -> None:
        self.version_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "description": description,
            "author": author,
            "version": self.metadata.version,
        })
        self.metadata.last_modified = datetime.now(timezone.utc).isoformat()

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-compatible dict for file storage."""
        import dataclasses
        return _dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectModel":
        """Deserialise from a stored dict."""
        return _dict_to_project(data)


# ─────────────────────────────────────────────────────────────────────────────
# SERIALISATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses and enums to plain dicts."""
    import dataclasses
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _dataclass_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, list):
        return [_dataclass_to_dict(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    return obj


def _dict_to_project(data: Dict[str, Any]) -> ProjectModel:
    """Reconstruct a ProjectModel from a stored dict."""
    metadata_data = data.get("metadata", {})
    metadata = ProjectMetadata(
        project_id=metadata_data.get("project_id", str(uuid.uuid4())),
        project_name=metadata_data.get("project_name", ""),
        domain=DomainType(metadata_data.get("domain", "wastewater")),
        plant_name=metadata_data.get("plant_name", ""),
        plant_location=metadata_data.get("plant_location", ""),
        project_number=metadata_data.get("project_number", ""),
        client_name=metadata_data.get("client_name", ""),
        author=metadata_data.get("author", ""),
        reviewer=metadata_data.get("reviewer", ""),
        created_at=metadata_data.get("created_at", datetime.now(timezone.utc).isoformat()),
        last_modified=metadata_data.get("last_modified", datetime.now(timezone.utc).isoformat()),
        version=metadata_data.get("version", "1.0.0"),
        planning_scenario=metadata_data.get("planning_scenario"),
        notes=metadata_data.get("notes", ""),
        tags=metadata_data.get("tags", []),
    )

    scenarios = {}
    for sid, sdata in data.get("scenarios", {}).items():
        scenario = _dict_to_scenario(sdata)
        scenarios[sid] = scenario

    return ProjectModel(
        metadata=metadata,
        scenarios=scenarios,
        active_scenario_id=data.get("active_scenario_id"),
        portfolio_id=data.get("portfolio_id"),
        report_metadata=data.get("report_metadata", {}),
        version_history=data.get("version_history", []),
    )


def _dict_to_scenario(data: Dict[str, Any]) -> ScenarioModel:
    pathway_data = data.get("treatment_pathway")
    pathway = None
    if pathway_data:
        pathway = TreatmentPathway(
            pathway_id=pathway_data.get("pathway_id", str(uuid.uuid4())),
            pathway_name=pathway_data.get("pathway_name", ""),
            technology_sequence=pathway_data.get("technology_sequence", []),
            technology_parameters=pathway_data.get("technology_parameters", {}),
        )

    assumptions_data = data.get("assumptions")
    assumptions = None
    if assumptions_data:
        assumptions = AssumptionsSet(
            assumptions_id=assumptions_data.get("assumptions_id", str(uuid.uuid4())),
            domain=DomainType(assumptions_data.get("domain", "wastewater")),
            base_version=assumptions_data.get("base_version", "default"),
            created_at=assumptions_data.get("created_at", datetime.now(timezone.utc).isoformat()),
            cost_assumptions=assumptions_data.get("cost_assumptions", {}),
            carbon_assumptions=assumptions_data.get("carbon_assumptions", {}),
            risk_assumptions=assumptions_data.get("risk_assumptions", {}),
            engineering_assumptions=assumptions_data.get("engineering_assumptions", {}),
            user_overrides=assumptions_data.get("user_overrides", {}),
            override_log=assumptions_data.get("override_log", []),
        )

    # Reconstruct result objects if present
    cost_data = data.get("cost_result")
    cost_result = CostResult(**cost_data) if cost_data else None

    carbon_data = data.get("carbon_result")
    carbon_result = CarbonResult(**carbon_data) if carbon_data else None

    risk_data = data.get("risk_result")
    risk_result = None
    if risk_data:
        items = [RiskItem(**ri) for ri in risk_data.get("risk_items", [])]
        risk_result = RiskResult(
            overall_score=risk_data.get("overall_score", 0.0),
            overall_level=risk_data.get("overall_level", ""),
            technical_score=risk_data.get("technical_score", 0.0),
            implementation_score=risk_data.get("implementation_score", 0.0),
            operational_score=risk_data.get("operational_score", 0.0),
            regulatory_score=risk_data.get("regulatory_score", 0.0),
            domain_specific_score=risk_data.get("domain_specific_score", 0.0),
            risk_items=items,
            risk_narrative=risk_data.get("risk_narrative", ""),
        )

    val_data = data.get("validation_result")
    validation_result = ValidationResult(**val_data) if val_data else None

    return ScenarioModel(
        scenario_id=data.get("scenario_id", str(uuid.uuid4())),
        scenario_name=data.get("scenario_name", ""),
        scenario_type=ScenarioType(data.get("scenario_type", "base_case")),
        description=data.get("description", ""),
        created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        last_modified=data.get("last_modified", datetime.now(timezone.utc).isoformat()),
        is_preferred=data.get("is_preferred", False),
        design_flow_mld=data.get("design_flow_mld"),
        planning_horizon_years=data.get("planning_horizon_years", 30),
        domain_inputs=data.get("domain_inputs", {}),
        treatment_pathway=pathway,
        assumptions=assumptions,
        cost_result=cost_result,
        carbon_result=carbon_result,
        risk_result=risk_result,
        validation_result=validation_result,
        domain_specific_outputs=data.get("domain_specific_outputs", {}),
        last_calculated_at=data.get("last_calculated_at"),
        calculation_version=data.get("calculation_version", "1.0.0"),
        is_stale=data.get("is_stale", True),
    )
