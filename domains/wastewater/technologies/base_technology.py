"""
domains/wastewater/technologies/base_technology.py

Treatment Pathway Module Framework
====================================
Every treatment pathway in the wastewater planning platform — biological,
physical, chemical, solids, tertiary, or reuse — inherits from BaseTechnology
and returns a TechnologyResult.

ARCHITECTURE PRINCIPLES
------------------------
1.  One file per technology.  No logic lives in the domain interface.
2.  Every module is self-contained.  It reads assumptions from the
    AssumptionsSet it receives; it never imports from other technology modules.
3.  Inputs are a typed dataclass.  Never a plain dict.
    Field names are lowercase_snake_case. Units are in the docstring.
4.  Outputs are a TechnologyResult.  Every typed sub-result (SludgeOutputs,
    EnergyOutputs, etc.) must be populated before returning.
5.  Engineering transparency: every non-trivial step writes a note via
    self._note(result, "..."). Notes appear in reports unchanged.
6.  Constants embedded in the module are engineering defaults, not magic
    numbers. Each has an inline comment citing the source or rationale.
7.  Assumptions sourced from AssumptionsSet are read via self._get_eng() /
    self._get_cost() so they remain calibratable via the digital-twin pipeline.
8.  Adding a new technology:
      a. Create a new .py file in the technologies/ (or sub-directory) folder.
      b. Define a Inputs dataclass and a Technology class that inherits BaseTechnology.
      c. Register the class in TECHNOLOGY_REGISTRY in domain_interface.py.
      Nothing else needs to change.

OUTPUT STRUCTURE
-----------------
TechnologyResult contains six typed sub-results:

    performance : PerformanceOutputs   — treatment quality, physical sizing
    energy      : EnergyOutputs        — consumption, generation, intensity
    sludge      : SludgeOutputs        — production, characteristics
    carbon      : CarbonOutputs        — scope 1/2/3, intensity
    risk        : RiskOutputs          — qualitative risk flags
    notes       : calculation_notes    — engineering audit trail

Plus two engine-facing lists:

    capex_items : List[CostItem]       — consumed by CostingEngine
    opex_items  : List[CostItem]       — consumed by CostingEngine

FOLDER STRUCTURE
-----------------
domains/wastewater/technologies/
├── base_technology.py          ← this file (framework + base class)
├── bnr.py                      ← Conventional BNR
├── ifas_mbbr.py                ← IFAS / MBBR Retrofit
├── granular_sludge.py          ← Aerobic Granular Sludge
├── mbr.py                      ← Membrane Bioreactor
├── anmbr.py                    ← Anaerobic Treatment (UASB / AnMBR)
├── sidestream_pna.py           ← Sidestream PN/A (Anammox)
├── mob_biofilm.py              ← Mobile Organic Biofilm         [NEW]
├── tertiary/
│   ├── __init__.py
│   ├── chemical_p_removal.py   ← Chemical Phosphorus Removal    [NEW]
│   └── tertiary_filtration.py  ← Tertiary Filtration            [NEW]
├── reuse/
│   ├── __init__.py
│   └── advanced_reuse.py       ← Advanced Reuse Preparation     [NEW]
└── solids/
    ├── __init__.py
    ├── ad_chp.py               ← Anaerobic Digestion + CHP      [NEW]
    └── thermal_biosolids.py    ← Thermal Biosolids Treatment     [NEW]

HOW THE SCENARIO COMPARISON ENGINE CALLS THESE MODULES
--------------------------------------------------------
The domain interface (domain_interface.py) is the only caller.
It holds TECHNOLOGY_REGISTRY = {code: TechnologyClass}.

For each scenario:
  1. domain_interface.run_scenario(inputs, technology_sequence, tech_params)
  2. For each code in technology_sequence:
       tech = TECHNOLOGY_REGISTRY[code](assumptions)
       inputs_obj = tech.input_class()(**tech_params.get(code, {}))
       result = tech.calculate(design_flow_mld, inputs_obj)
  3. All TechnologyResult objects are aggregated:
       - capex_items and opex_items → CostingEngine
       - energy_kwh_per_day, chemical_consumption → CarbonEngine
       - process_emissions_tco2e_yr → CarbonEngine (Scope 1)
       - risk flags → RiskEngine
  4. The scenario comparison engine receives ScenarioModel objects,
     each containing a CostResult, CarbonResult, and RiskResult,
     plus the raw TechnologyResult for per-technology display.

The comparison engine NEVER calls technology modules directly.
It compares pre-computed scenario outputs.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type


# ─────────────────────────────────────────────────────────────────────────────
# COST ITEM
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CostItem:
    """
    Single line item for the CostingEngine.

    cost_basis_key references a unit rate in the assumptions YAML.
    The CostingEngine resolves: total_cost = quantity × unit_rate × contingency.

    unit_cost_override bypasses the assumptions lookup — use only when the
    cost is genuinely site-specific (e.g. equipment with a vendor quote).
    """
    name: str = ""
    cost_basis_key: str = ""
    quantity: float = 0.0
    unit: str = ""
    unit_cost_override: Optional[float] = None
    contingency_factor: float = 1.0
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# TYPED SUB-RESULTS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PerformanceOutputs:
    """
    Treatment quality, physical sizing, and hydraulic outputs.

    Effluent quality fields use NaN convention: None means "not calculated
    by this module", not "zero removal". The domain interface checks for
    None before aggregating.
    """
    # Effluent quality (mg/L unless noted)
    effluent_bod_mg_l: Optional[float] = None
    effluent_tss_mg_l: Optional[float] = None
    effluent_tn_mg_l: Optional[float] = None
    effluent_nh4_mg_l: Optional[float] = None
    effluent_tp_mg_l: Optional[float] = None
    effluent_cod_mg_l: Optional[float] = None

    # Physical sizing
    reactor_volume_m3: Optional[float] = None
    footprint_m2: Optional[float] = None
    hydraulic_retention_time_hr: Optional[float] = None

    # Technology-specific key performance metrics (free-form, displayed in UI)
    # Use snake_case keys with units as suffix, e.g. "sludge_vol_index_ml_g"
    additional: Dict[str, Any] = field(default_factory=dict)

    # Influent concentrations — set from WastewaterInputs in calculate() for removal % calcs
    _influent_bod_mg_l: float = field(default=250.0, repr=False)
    _influent_nh4_mg_l: float = field(default=35.0,  repr=False)
    _influent_tn_mg_l:  float = field(default=45.0,  repr=False)
    _influent_tp_mg_l:  float = field(default=7.0,   repr=False)

    @property
    def bod_removal_pct(self) -> Optional[float]:
        if self.effluent_bod_mg_l is None or self._influent_bod_mg_l <= 0:
            return None
        return max(0.0, (1 - self.effluent_bod_mg_l / self._influent_bod_mg_l) * 100)

    @property
    def nh4_removal_pct(self) -> Optional[float]:
        if self.effluent_nh4_mg_l is None or self._influent_nh4_mg_l <= 0:
            return None
        return max(0.0, (1 - self.effluent_nh4_mg_l / self._influent_nh4_mg_l) * 100)

    @property
    def tn_removal_pct(self) -> Optional[float]:
        if self.effluent_tn_mg_l is None or self._influent_tn_mg_l <= 0:
            return None
        return max(0.0, (1 - self.effluent_tn_mg_l / self._influent_tn_mg_l) * 100)

    @property
    def tp_removal_pct(self) -> Optional[float]:
        if self.effluent_tp_mg_l is None or self._influent_tp_mg_l <= 0:
            return None
        return max(0.0, (1 - self.effluent_tp_mg_l / self._influent_tp_mg_l) * 100)


@dataclass
class EnergyOutputs:
    """
    All energy flows in and out of this technology module.

    Units: kWh/day unless noted.
    The CarbonEngine uses total_consumption_kwh_day and generation_kwh_day.
    """
    # Consumption by sub-system
    aeration_kwh_day: float = 0.0
    mixing_kwh_day: float = 0.0
    pumping_kwh_day: float = 0.0
    membrane_kwh_day: float = 0.0      # MBR, AnMBR membrane scour
    uv_kwh_day: float = 0.0            # UV disinfection
    other_kwh_day: float = 0.0

    # Generation (biogas CHP, solar, etc.)
    generation_kwh_day: float = 0.0
    biogas_m3_day: float = 0.0         # Raw biogas (for reporting)
    ch4_m3_day: float = 0.0            # Methane component

    @property
    def total_consumption_kwh_day(self) -> float:
        return (self.aeration_kwh_day + self.mixing_kwh_day + self.pumping_kwh_day
                + self.membrane_kwh_day + self.uv_kwh_day + self.other_kwh_day)

    @property
    def net_kwh_day(self) -> float:
        """Net demand = consumption – generation (negative = net exporter)."""
        return self.total_consumption_kwh_day - self.generation_kwh_day

    @property
    def intensity_kwh_per_kl(self) -> Optional[float]:
        """Set by TechnologyResult.finalise() — do not assign directly."""
        return self._intensity_kwh_per_kl if hasattr(self, '_intensity_kwh_per_kl') else None

    @intensity_kwh_per_kl.setter
    def intensity_kwh_per_kl(self, value: Optional[float]) -> None:
        self._intensity_kwh_per_kl = value

    @property
    def annual_consumption_kwh_yr(self) -> float:
        """Total annual electricity consumption (kWh/year)."""
        return self.total_consumption_kwh_day * 365

    @property
    def annual_generation_kwh_yr(self) -> float:
        """Total annual electricity generated on-site (kWh/year)."""
        return self.generation_kwh_day * 365


@dataclass
class SludgeOutputs:
    """
    Sludge production and characteristics.

    All mass flows are kg dry solids per day.
    These values feed into the sludge/biosolids modules downstream.
    """
    primary_sludge_kgds_day: float = 0.0       # Primary sludge (if primary treatment)
    biological_sludge_kgds_day: float = 0.0    # WAS from biological process
    chemical_sludge_kgds_day: float = 0.0      # Chemical precipitation sludge
    membrane_concentrate_kgds_day: float = 0.0 # Membrane reject solids

    vs_fraction: float = 0.80       # Volatile fraction of biological sludge (typical WAS)
    feed_ts_pct: float = 1.5        # Total solids % in raw WAS

    @property
    def total_kgds_day(self) -> float:
        return (self.primary_sludge_kgds_day + self.biological_sludge_kgds_day
                + self.chemical_sludge_kgds_day + self.membrane_concentrate_kgds_day)

    @property
    def total_tds_yr(self) -> float:
        """Total annual dry solids production (t DS/year)."""
        return self.total_kgds_day * 365 / 1000

    @property
    def volatile_solids_tds_yr(self) -> float:
        """Annual volatile solids (t VS/year)."""
        return self.total_tds_yr * self.vs_fraction


@dataclass
class CarbonOutputs:
    """
    Greenhouse gas emissions attributable to this technology module.

    Scope 1: Direct process emissions (N2O, CH4 fugitive)
    Scope 2: Indirect from grid electricity — calculated by CarbonEngine
             using total_consumption_kwh_day × grid emission factor.
             Do NOT populate this field in the technology module.
    Scope 3: Upstream chemicals, imported materials, transport.

    All values: tCO2e/year.
    """
    # Scope 1 — populate in the technology module
    n2o_biological_tco2e_yr: float = 0.0       # Biological treatment N2O
    ch4_fugitive_tco2e_yr: float = 0.0         # Fugitive methane (anaerobic, digestion)
    process_co2_tco2e_yr: float = 0.0          # Direct CO2 (incineration fossil fraction)
    other_scope1_tco2e_yr: float = 0.0

    # Scope 3 upstream chemicals — calculated from chemical_consumption dict
    # by CarbonEngine; do NOT populate manually
    upstream_chemicals_tco2e_yr: float = 0.0   # Filled by CarbonEngine

    # Scope 2 and cost — populated by finalise() from grid EF and carbon price
    scope2_tco2e_yr: float = 0.0
    carbon_cost_yr: float = 0.0     # $ = (scope1 + scope2) × carbon_price_per_tonne

    @property
    def total_scope1_tco2e_yr(self) -> float:
        return (self.n2o_biological_tco2e_yr + self.ch4_fugitive_tco2e_yr
                + self.process_co2_tco2e_yr + self.other_scope1_tco2e_yr)

    @property
    def total_tco2e_yr(self) -> float:
        """Total Scope 1 + Scope 2 (tCO2e/year)."""
        return self.total_scope1_tco2e_yr + self.scope2_tco2e_yr

    def to_emissions_dict(self) -> Dict[str, float]:
        """Returns the dict format consumed by CarbonEngine."""
        return {
            "n2o_biological_treatment": self.n2o_biological_tco2e_yr,
            "ch4_fugitive":             self.ch4_fugitive_tco2e_yr,
            "process_co2":              self.process_co2_tco2e_yr,
            "other_scope1":             self.other_scope1_tco2e_yr,
        }


@dataclass
class RiskOutputs:
    """
    Qualitative risk flags for this technology.

    All fields are strings from the set: "Low" | "Moderate" | "High" | "Very High".
    An empty string means "not assessed" — not "Low".

    These are technology-specific risk flags. The RiskEngine aggregates them
    with process-type risk items to produce a scenario-level risk score.
    """
    reliability_risk: str = ""          # Process reliability / uptime risk
    regulatory_risk: str = ""           # Permit compliance / regulatory restriction risk
    technology_maturity: str = ""       # Technology readiness level
    operational_complexity: str = ""    # Operator skill requirement
    site_constraint_risk: str = ""      # Footprint / site suitability risk
    implementation_risk: str = ""       # Construction complexity, supply chain, lead times

    # Free-form risk flags for technology-specific issues
    # e.g. {"pfas_pathway_risk": "High", "membrane_fouling_risk": "Moderate"}
    additional_flags: Dict[str, str] = field(default_factory=dict)

    @property
    def risk_score(self) -> float:
        """
        Composite risk score 1–4 (Low=1, Moderate=2, High=3, Very High=4).
        Only scored dimensions are included in the average.
        """
        mapping = {"Low": 1, "Moderate": 2, "High": 3, "Very High": 4}
        vals = [
            mapping[v] for v in [
                self.reliability_risk, self.regulatory_risk,
                self.technology_maturity, self.operational_complexity,
                self.site_constraint_risk,
            ] if v in mapping
        ]
        return sum(vals) / len(vals) if vals else 0.0


@dataclass
class NotesOutput:
    """
    Human-readable notes section for every technology result.

    All three lists contain plain English strings — they are displayed
    verbatim in reports and the UI without further formatting.

    assumptions  : Key design assumptions made in the calculation.
                   Quote the value AND the engineering basis where possible.
                   e.g. "Alpha factor = 0.55 (typical municipal fine bubble, Metcalf 5th ed.)"

    limitations  : Things the model does NOT calculate or where the result
                   is known to be approximate.
                   e.g. "CAPEX does not include land acquisition costs."

    warnings     : Active flags that need user attention before relying on results.
                   e.g. "⚠ Operating temperature (12°C) is below nitrification optimum."
    """
    assumptions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    warnings:    List[str] = field(default_factory=list)

    def add_assumption(self, msg: str) -> None:
        self.assumptions.append(msg)

    def add_limitation(self, msg: str) -> None:
        self.limitations.append(msg)

    def warn(self, msg: str) -> None:
        if not msg.startswith("⚠"):
            msg = "⚠ " + msg
        self.warnings.append(msg)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY RESULT (top-level output)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TechnologyResult:
    """
    Standardised output from any treatment technology plugin.

    This is what the domain interface aggregates and what the core engines consume.
    The core engines (CostingEngine, CarbonEngine, RiskEngine) only see this object.

    USAGE PATTERN
    -------------
    In calculate():
        result = TechnologyResult(
            technology_name="Conventional BNR",
            technology_code="bnr",
            technology_category="Biological Treatment",
            description="Activated sludge with BNR for N and P removal.",
        )
        result.energy.aeration_kwh_day = aeration_kwh_day
        result.sludge.biological_sludge_kgds_day = sludge_kg_day
        result.carbon.n2o_biological_tco2e_yr = n2o_tco2e_yr
        result.performance.effluent_tn_mg_l = eff_tn
        result.risk.reliability_risk = "Moderate"
        result.notes.assumptions.append("Alpha factor = 0.55 (default)")
        result.finalise(design_flow_mld)
        return result
    """
    # ── Metadata ──────────────────────────────────────────────────────────
    technology_name: str = ""
    technology_code: str = ""
    technology_category: str = ""   # e.g. "Biological Treatment", "Solids", "Tertiary"
    description: str = ""           # One-sentence summary for UI and reports

    # ── Typed sub-results ─────────────────────────────────────────────────
    performance: PerformanceOutputs = field(default_factory=PerformanceOutputs)
    energy:      EnergyOutputs      = field(default_factory=EnergyOutputs)
    sludge:      SludgeOutputs      = field(default_factory=SludgeOutputs)
    carbon:      CarbonOutputs      = field(default_factory=CarbonOutputs)
    risk:        RiskOutputs        = field(default_factory=RiskOutputs)
    notes:       NotesOutput        = field(default_factory=NotesOutput)

    # ── Engine-facing lists ───────────────────────────────────────────────
    capex_items: List[CostItem] = field(default_factory=list)
    opex_items:  List[CostItem] = field(default_factory=list)

    # ── Chemical consumption (for CarbonEngine Scope 3) ──────────────────
    chemical_consumption: Dict[str, float] = field(default_factory=dict)
    # {chemical_name: kg/day}  — names must match carbon_assumptions emission factors

    # ── Convenience derived fields (set by finalise()) ────────────────────
    design_flow_mld: float = 0.0
    energy_intensity_kwh_kl: Optional[float] = None
    net_energy_kwh_day: Optional[float] = None

    # ── Legacy compatibility fields (still read by existing engines) ──────
    # These mirror values from the typed sub-results so existing code continues
    # to work without modification during the transition period.
    energy_kwh_per_day: float = 0.0           # = energy.total_consumption_kwh_day
    energy_generated_kwh_per_day: float = 0.0 # = energy.generation_kwh_day
    footprint_m2: Optional[float] = None       # = performance.footprint_m2
    volume_m3: Optional[float] = None          # = performance.reactor_volume_m3
    process_emissions_tco2e_yr: Dict[str, float] = field(default_factory=dict)
    # = carbon.to_emissions_dict()
    performance_outputs: Dict[str, Any] = field(default_factory=dict)
    # = performance.additional + key metrics
    assumptions_used: Dict[str, Any] = field(default_factory=dict)
    calculation_notes: List[str] = field(default_factory=list)

    def finalise(
        self,
        design_flow_mld: float,
        grid_ef_kg_co2e_per_kwh: float = 0.79,
        carbon_price_per_tonne: float = 35.0,
        influent_bod_mg_l: float = 250.0,
        influent_nh4_mg_l: float = 35.0,
        influent_tn_mg_l:  float = 45.0,
        influent_tp_mg_l:  float = 7.0,
    ) -> "TechnologyResult":
        """
        Call this as the last line of calculate() before returning.

        Parameters
        ----------
        design_flow_mld         : Plant design flow (ML/day)
        grid_ef_kg_co2e_per_kwh : Grid emission factor for Scope 2
        carbon_price_per_tonne  : Carbon price ($/tCO2e) for carbon cost
        influent_*_mg_l         : Influent concentrations for removal % properties
        """
        self.design_flow_mld = design_flow_mld

        # Set influent references on PerformanceOutputs for removal %
        self.performance._influent_bod_mg_l = influent_bod_mg_l
        self.performance._influent_nh4_mg_l = influent_nh4_mg_l
        self.performance._influent_tn_mg_l  = influent_tn_mg_l
        self.performance._influent_tp_mg_l  = influent_tp_mg_l

        # Derived energy
        self.net_energy_kwh_day = self.energy.net_kwh_day
        if design_flow_mld > 0:
            self.energy_intensity_kwh_kl = (
                self.energy.total_consumption_kwh_day / (design_flow_mld * 1000)
            )
            self.energy.intensity_kwh_per_kl = self.energy_intensity_kwh_kl

        # Scope 2 and carbon cost
        net_grid_kwh_day = max(
            0.0, self.energy.total_consumption_kwh_day - self.energy.generation_kwh_day
        )
        self.carbon.scope2_tco2e_yr = net_grid_kwh_day * 365 * grid_ef_kg_co2e_per_kwh / 1000
        self.carbon.carbon_cost_yr  = self.carbon.total_tco2e_yr * carbon_price_per_tonne

        # Sync legacy flat fields
        self.energy_kwh_per_day           = self.energy.total_consumption_kwh_day
        self.energy_generated_kwh_per_day = self.energy.generation_kwh_day
        self.footprint_m2                 = self.performance.footprint_m2
        self.volume_m3                    = self.performance.reactor_volume_m3
        self.process_emissions_tco2e_yr   = self.carbon.to_emissions_dict()

        # Build performance_outputs dict
        self.performance_outputs.update({
            "effluent_bod_mg_l":          self.performance.effluent_bod_mg_l,
            "effluent_tss_mg_l":          self.performance.effluent_tss_mg_l,
            "effluent_tn_mg_l":           self.performance.effluent_tn_mg_l,
            "effluent_nh4_mg_l":          self.performance.effluent_nh4_mg_l,
            "effluent_tp_mg_l":           self.performance.effluent_tp_mg_l,
            "bod_removal_pct":            self.performance.bod_removal_pct,
            "nh4_removal_pct":            self.performance.nh4_removal_pct,
            "tn_removal_pct":             self.performance.tn_removal_pct,
            "tp_removal_pct":             self.performance.tp_removal_pct,
            "sludge_production_kgds_day": self.sludge.total_kgds_day,
            "sludge_production_tds_yr":   self.sludge.total_tds_yr,
            "energy_intensity_kwh_kl":    self.energy_intensity_kwh_kl,
            "net_energy_kwh_day":         self.net_energy_kwh_day,
            "aeration_energy_kwh_day":    self.energy.aeration_kwh_day,   # for aeration page cross-check
            "scope1_tco2e_yr":            self.carbon.total_scope1_tco2e_yr,
            "scope2_tco2e_yr":            self.carbon.scope2_tco2e_yr,
            "total_tco2e_yr":             self.carbon.total_tco2e_yr,
            "carbon_cost_yr":             self.carbon.carbon_cost_yr,
            "risk_score":                 self.risk.risk_score,
            "footprint_m2":               self.performance.footprint_m2,
            "reactor_volume_m3":          self.performance.reactor_volume_m3,
        })
        self.performance_outputs.update(self.performance.additional)

        # Merge notes.assumptions into calculation_notes (backward compat)
        for msg in self.notes.assumptions + self.notes.limitations + self.notes.warnings:
            if msg not in self.calculation_notes:
                self.calculation_notes.append(msg)

        return self

    def note(self, msg: str) -> None:
        """Append a calculation note for engineering transparency."""
        self.calculation_notes.append(msg)


# ─────────────────────────────────────────────────────────────────────────────
# BASE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class BaseTechnology(ABC):
    """
    Abstract base class for all treatment pathway modules.

    Every pathway — biological, solids, tertiary, reuse — inherits from this
    class and implements the three abstract members below.

    Constructor
    -----------
    BaseTechnology(assumptions: AssumptionsSet)

    The assumptions object is the ONLY way a module should read configuration.
    Never hard-code plant-specific values; use self._get_eng() / self._get_cost().

    Abstract members
    ----------------
    technology_code  : str         — unique registry key, e.g. "bnr"
    technology_name  : str         — display name, e.g. "Conventional BNR"
    input_class()    : Type        — dataclass for technology-specific parameters
    calculate()      : TechnologyResult

    Optional overrides
    ------------------
    technology_category : str      — "biological" | "solids" | "tertiary" | "reuse"
    applicable_scales   : list     — ["small", "medium", "large"]
    requires_upstream   : list     — technology codes that must precede this one
    """

    def __init__(self, assumptions: Any) -> None:
        self.assumptions = assumptions

    # ── Abstract interface ────────────────────────────────────────────────

    @property
    @abstractmethod
    def technology_code(self) -> str:
        """Unique short identifier. Matches TECHNOLOGY_REGISTRY key."""

    @property
    @abstractmethod
    def technology_name(self) -> str:
        """Human-readable name for UI and reports."""

    @classmethod
    @abstractmethod
    def input_class(cls) -> Type:
        """
        Return the Inputs dataclass for this technology.
        The domain interface instantiates this with user-provided parameters.
        """

    @abstractmethod
    def calculate(
        self,
        design_flow_mld: float,
        inputs: Any,
    ) -> TechnologyResult:
        """
        Perform all engineering calculations.

        IMPLEMENTATION PATTERN
        ----------------------
        def calculate(self, design_flow_mld, inputs):
            r = TechnologyResult(
                technology_name=self.technology_name,
                technology_code=self.technology_code,
            )
            flow = design_flow_mld * 1000  # m³/day

            # --- 1. Load influent characteristics ---
            bod_in = self._get_eng("influent_bod_mg_l", 250.0)

            # --- 2. Calculate performance ---
            # ... engineering calculations ...
            r.performance.effluent_tn_mg_l = eff_tn
            r.note(f"TN removal: {tn_removed:.0f} kg/day")

            # --- 3. Sludge ---
            r.sludge.biological_sludge_kgds_day = sludge_kg_day

            # --- 4. Energy ---
            r.energy.aeration_kwh_day = aeration_energy
            r.energy.generation_kwh_day = biogas_kwh if applicable

            # --- 5. Carbon (Scope 1 only; Scope 2 done by CarbonEngine) ---
            r.carbon.n2o_biological_tco2e_yr = n2o

            # --- 6. Risk flags ---
            r.risk.reliability_risk = "Moderate"
            r.risk.technology_maturity = "Established"

            # --- 7. CAPEX / OPEX ---
            r.capex_items = [CostItem(...), ...]
            r.opex_items  = [CostItem(...), ...]

            # --- 8. Assumptions log ---
            r.assumptions_used = {"srt_days": inputs.srt_days, ...}

            # --- 9. Finalise (ALWAYS last) ---
            return r.finalise(design_flow_mld)
        """

    # ── Optional metadata ─────────────────────────────────────────────────

    @property
    def technology_category(self) -> str:
        """Override in subclass: "biological" | "solids" | "tertiary" | "reuse"."""
        return "biological"

    @property
    def applicable_scales(self) -> List[str]:
        """Override to restrict which plant scales this technology suits."""
        return ["small", "medium", "large"]

    @property
    def requires_upstream(self) -> List[str]:
        """
        List of technology codes that should precede this one.
        Used by the UI to warn about invalid pathways, not to enforce order.
        """
        return []

    # ── Protected helpers (do not override) ──────────────────────────────

    def _get_eng(self, key: str, default: Any = None) -> Any:
        """Read an engineering assumption. Falls back to default if key absent."""
        return self.assumptions.engineering_assumptions.get(key, default)

    def _get_cost(self, key: str, default: Any = None) -> Any:
        """Read a cost assumption from any nested cost dict or top level."""
        cost = self.assumptions.cost_assumptions
        for sub_key in ("capex_unit_costs", "opex_unit_rates", "chemical_prices"):
            nested = cost.get(sub_key, {})
            if key in nested:
                return nested[key]
        return cost.get(key, default)

    def _get_carbon(self, key: str, default: Any = None) -> Any:
        """Read a carbon/emission factor assumption."""
        return self.assumptions.carbon_assumptions.get(key, default)

    def _note(self, result: TechnologyResult, msg: str) -> None:
        """Append a calculation note (convenience alias for result.note())."""
        result.note(msg)

    def _load_influent(self) -> Dict[str, float]:
        """
        Return a dict of influent quality parameters from assumptions.
        Convenience method used by all biological treatment modules.
        """
        return {
            "bod_mg_l":  self._get_eng("influent_bod_mg_l", 250.0),
            "cod_mg_l":  self._get_eng("influent_cod_mg_l", 500.0),
            "tn_mg_l":   self._get_eng("influent_tn_mg_l",  45.0),
            "tp_mg_l":   self._get_eng("influent_tp_mg_l",  7.0),
            "tss_mg_l":  self._get_eng("influent_tss_mg_l", 280.0),
        }
