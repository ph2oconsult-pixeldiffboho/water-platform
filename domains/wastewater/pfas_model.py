"""
domains/wastewater/pfas_model.py

PFAS Mass Balance and Fate Model for Biosolids  (v1.1)
=======================================================
Screening-level PFAS assessment for biosolids strategy planning.

AUDIT FIXES (v1.1)
------------------
  FIX 1 — Concentration calculation inconsistency
      The v1.0 model used raw_ds for mass but cake_ds for concentration,
      creating an inconsistency. The corrected model tracks PFAS through two
      explicit partitioning steps: (a) digestion → reject water, then
      (b) dewatering → filtrate. Concentration is computed at each step
      from the correct denominator.

  FIX 2 — Land application "after pathway" concentration
      v1.0 reported 757 µg/kg for land application (using mass reduced by
      filtrate loss) vs cake concentration of 842 µg/kg. These should be
      equal for a non-destructive pathway. Fixed: 'after pathway' equals
      the cake concentration for all non-destructive pathways.

  FIX 3 — concentration_factor_in_solid was dead code
      The parameter was defined in PFASFateAssumptions but never used in
      calculations. Removed from pathway assumptions; solid output
      concentrations are now computed from mass balance directly.

  FIX 4 — Environmental release fraction labelling
      The 'environmental_release_fraction' was presented as a direct annual
      release rate, which is physically incorrect for landfill (leaching
      occurs over decades). Renamed to 'leachate_pathway_fraction' with
      correct description: fraction of cake PFAS with a leaching pathway,
      not an annual release quantity.

  FIX 5 — Incineration destruction efficiency 95% → 99%
      95% was a conservative low-end estimate; literature supports >99%
      at >850°C/2s (US EPA 2020) and >99.999% at >1000°C. Updated to 99%
      with the caveat that this requires confirmed operating conditions.
      Short-chain PFAS harder to destroy is documented.

  FIX 6 — HEPA NEMP 5 µg/kg label was a category error
      That value is for drinking water source protection, not biosolids.
      Relabelled correctly. The biosolids triggers are the NSW/VIC
      100 µg/kg ∑PFAS values.

  FIX 7 — Tier defaults updated to Australian survey data
      Low tier: 50 → 100 µg/kg (P10 of published Australian WWTP survey).
      Moderate: 500 µg/kg retained (close to survey P50 of 520 µg/kg).
      High: 5,000 µg/kg retained. Added explicit note that even 'low'
      tier will exceed regulatory triggers in most cases.

  FIX 8 — PFAS to liquid line now explicitly tracked and reported
      Two liquid-line PFAS outputs are now calculated and displayed:
      (a) reject water from digestion, (b) filtrate from dewatering.
      These return PFAS to the liquid treatment line and ultimately to
      the treated effluent — a pathway that must be flagged to users.

IMPORTANT LIMITATIONS — READ BEFORE USE
-----------------------------------------
  1. SCREENING-LEVEL ONLY. Not a quantitative risk assessment.
  2. PFAS is a class of ~12,000 compounds. Inputs should specify
     the compound class (∑PFAS, PFAS-10, PFOS+PFOA, etc.).
  3. Digestion and dewatering do NOT destroy PFAS — they
     redistribute it between solid and liquid phases and concentrate
     it as water/VS is removed.
  4. Thermal destruction requires specific operating conditions
     (temperature, residence time, flue gas treatment) — the
     efficiencies in this model assume correctly operated facilities.
  5. Regulatory values are 2024-2025 and will change.

References
----------
  - NSW EPA (2023) — PFAS in Biosolids: Interim Guidance
  - EPA Victoria (2024) — Biosolids PFAS Management Guidance
  - HEPA PFAS NEMP 2.0 (2020) — National Environmental Management Plan
  - AECOM/GHD (2022) — PFAS in Australian Biosolids Survey (83 WWTPs)
  - Hamid et al. (2018) — PFAS fate in wastewater treatment plants
  - Higgins et al. (2005) — PFAS partitioning during biosolids dewatering
  - US EPA (2020) — PFAS Destruction and Disposal Guidance
  - Crimi et al. (2022) — Thermal treatment of PFAS in biosolids
  - Venkatesan & Halden (2013) — PFAS in US biosolids
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
# ENUMERATIONS
# ─────────────────────────────────────────────────────────────────────────────

class PFASRiskTier(str, Enum):
    """
    Catchment-based PFAS risk tier for use when measured data is unavailable.
    Defaults are calibrated to the AECOM/GHD 2022 Australian biosolids survey
    (n=83 WWTPs): P10=90, P25=180, P50=520, P75=1,500, P90=5,800 µg/kg ∑PFAS.
    """
    LOW      = "low"
    MODERATE = "moderate"
    HIGH     = "high"
    MEASURED = "measured"

    @property
    def display_name(self) -> str:
        return {
            self.LOW:      "Low (rural/peri-urban, no known PFAS sources — ~P10 of Aus survey)",
            self.MODERATE: "Moderate (mixed urban, some industrial history — ~P50 of Aus survey)",
            self.HIGH:     "High (industrial catchment or known AFFF use — ~P90 of Aus survey)",
            self.MEASURED: "Measured data provided",
        }[self]


class PFASCompoundClass(str, Enum):
    """Specifies which PFAS compound class the concentration represents."""
    PFOS_PFOA  = "pfos_pfoa"
    PFAS6      = "pfas6"
    PFAS10     = "pfas10"
    TOTAL_PFAS = "total_pfas"
    UNKNOWN    = "unknown"

    @property
    def display_name(self) -> str:
        return {
            self.PFOS_PFOA:  "PFOS + PFOA sum only",
            self.PFAS6:      "PFAS-6 sum (US EPA Method 533)",
            self.PFAS10:     "PFAS-10 sum (Aus reporting basis)",
            self.TOTAL_PFAS: "Total ∑PFAS (all detected)",
            self.UNKNOWN:    "Compound class not specified",
        }[self]


# ─────────────────────────────────────────────────────────────────────────────
# TIER DEFAULTS  (v1.1 — calibrated to Australian survey data)
# ─────────────────────────────────────────────────────────────────────────────

PFAS_TIER_DEFAULTS_UG_KG: Dict[str, Dict[str, Any]] = {
    PFASRiskTier.LOW.value: {
        "pfas_sum_ug_kg":    100.0,     # ~P10 of AECOM/GHD 2022 (was 50 in v1.0)
        "pfas_sum_range_lo":  20.0,
        "pfas_sum_range_hi": 400.0,
        "basis": (
            "Peri-urban or rural catchment, no known PFAS point sources. "
            "Even at this tier, concentrations may exceed Australian regulatory triggers. "
            "This tier represents the lower end of measured Australian biosolids — "
            "it does NOT imply negligible PFAS."
        ),
    },
    PFASRiskTier.MODERATE.value: {
        "pfas_sum_ug_kg":    500.0,     # Close to survey P50 of 520 µg/kg
        "pfas_sum_range_lo": 100.0,
        "pfas_sum_range_hi": 2_000.0,
        "basis": (
            "Mixed urban/light industrial catchment, typical Australian metropolitan WWTP. "
            "Will exceed 100 µg/kg NSW/VIC trigger in almost all cases."
        ),
    },
    PFASRiskTier.HIGH.value: {
        "pfas_sum_ug_kg":   5_000.0,    # ~P90 of survey
        "pfas_sum_range_lo": 1_000.0,
        "pfas_sum_range_hi": 50_000.0,
        "basis": (
            "Industrial catchment, AFFF-impacted area, or catchment with known PFAS "
            "manufacturing or heavy use. Confirmed cases in Australia exceed 100,000 µg/kg."
        ),
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# REGULATORY REFERENCE VALUES  (v1.1 — corrected labels)
# ─────────────────────────────────────────────────────────────────────────────

PFAS_REGULATORY_REFS: Dict[str, Any] = {
    # Biosolids land application triggers
    "nsw_epa_biosolids_trigger_ug_kg":    100.0,   # NSW EPA interim (2023), ∑PFAS 10 compounds
    "vic_epa_biosolids_trigger_ug_kg":    100.0,   # EPA Victoria (2024), same basis
    # Drinking water source protection — NOT a biosolids limit
    "hepa_nemp2_drinking_water_source_pfos_pfoa_ug_kg": 5.0,
    "note_hepa": (
        "The HEPA NEMP 2.0 value of 5 µg/kg (PFOS+PFOA) applies to drinking water source "
        "protection areas. It is NOT a biosolids land application trigger. "
        "The relevant Australian biosolids limits are the NSW EPA and EPA Victoria "
        "interim values of 100 µg/kg ∑PFAS (10 named compounds)."
    ),
    "us_epa_proposed_pfos_pfoa_ug_kg": 0.071,   # US EPA proposed (2023) — not AUS law
    "regulatory_caveat": (
        "All regulatory values are indicative as of 2024-2025 and subject to rapid change. "
        "Verify current requirements in your jurisdiction before any planning decisions. "
        "The trajectory in all Australian jurisdictions is toward stricter limits."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# PFAS FATE ASSUMPTIONS BY PATHWAY  (v1.1 — removed dead parameter)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PFASFateAssumptions:
    """
    PFAS fate assumptions for a single disposal/treatment pathway.
    Applied AFTER digestion and dewatering (i.e., to the dewatered cake).
    All values are screening-level estimates only.
    """
    pathway: str
    display_name: str

    # Fraction of cake PFAS mass remaining in the solid output after pathway treatment
    # For thermal pathways, this = (1 - destruction_efficiency) × solid_fraction
    pfas_fraction_in_solid_output: float = 1.0

    # Thermal destruction efficiency (0.0 = none; 0.99 = 99% destroyed)
    # Applies ONLY to correctly operated thermal facilities — see caveats
    pfas_destruction_efficiency: float = 0.0

    # Fraction of cake PFAS with a leachate/liquid release pathway
    # NOTE: This is a fate characterisation, NOT an annual release rate.
    # Leaching from landfill occurs over decades to centuries.
    leachate_pathway_fraction: float = 0.0

    # Solid mass reduction factor in thermal pathways
    # (ash/char is a fraction of the input cake DS)
    solid_mass_reduction_factor: float = 1.0
    # 1.0 = no mass reduction (land app, composting, landfill)
    # 0.25 = incineration ash (~25% of input DS)
    # 0.35 = pyrolysis char (~35% of input DS)
    # 0.20 = gasification slag (~20% of input DS)

    caveats: List[str] = field(default_factory=list)
    regulatory_restriction_flag: str = "check_jurisdiction"
    pfas_viable: bool = True
    pfas_viability_note: str = ""


PFAS_PATHWAY_ASSUMPTIONS: Dict[str, PFASFateAssumptions] = {

    "land_application": PFASFateAssumptions(
        pathway="land_application",
        display_name="Land Application",
        pfas_fraction_in_solid_output=1.0,
        pfas_destruction_efficiency=0.0,
        leachate_pathway_fraction=0.10,
        solid_mass_reduction_factor=1.0,
        caveats=[
            "PFAS is NOT destroyed during land application. The full cake PFAS mass is applied to soil.",
            "Concentration in applied biosolids equals the dewatered cake concentration.",
            "Once applied, PFAS persists indefinitely in the soil and can leach to groundwater.",
            "Leaching rate is highly site-specific: depends on compound class (short-chain leaches faster), "
            "soil type, pH, organic matter content, and rainfall.",
            "PFAS can bioaccumulate in crops grown on treated land and in livestock — food-chain risk not assessed here.",
            "The leachate_pathway_fraction of 10% represents the fraction of applied PFAS with a credible "
            "groundwater leaching exposure pathway over time. It is NOT an annual release rate.",
            "⚠ REGULATORY: Land application of biosolids with ∑PFAS >100 µg/kg is restricted or banned "
            "in NSW and Victoria (2024). This threshold is exceeded by most Australian urban biosolids. "
            "Regulatory requirements are evolving rapidly.",
        ],
        regulatory_restriction_flag="restricted",
        pfas_viable=False,
        pfas_viability_note=(
            "Land application is NOT RECOMMENDED for biosolids with ∑PFAS above 100 µg/kg DS "
            "(NSW EPA, EPA Victoria 2024). Concentrations from moderate-to-high catchments will "
            "routinely exceed this. Even for low-tier estimates, land application should not "
            "proceed without measured data and regulatory confirmation."
        ),
    ),

    "composting": PFASFateAssumptions(
        pathway="composting",
        display_name="Composting",
        pfas_fraction_in_solid_output=0.97,
        pfas_destruction_efficiency=0.02,
        leachate_pathway_fraction=0.05,
        solid_mass_reduction_factor=0.60,  # composting reduces wet mass; DS ~60% retained after moisture loss
        caveats=[
            "Composting temperatures (55–70°C windrow, 65°C in-vessel) are well below PFAS "
            "thermal destruction thresholds (>850°C). PFAS transformation in composting is <5%.",
            "PFAS mass is largely conserved through composting. As the organic matrix decomposes "
            "and moisture is lost, the concentration per kg DS in the compost product may increase.",
            "The PFAS risk of composting depends almost entirely on the end-use of the compost product. "
            "If compost is applied to land, the risk profile is equivalent to direct land application.",
            "Compost sold commercially with detectable PFAS poses product liability and certification risks.",
            "⚠ REGULATORY: Same land application restrictions apply to compost derived from "
            "PFAS-containing biosolids.",
        ],
        regulatory_restriction_flag="restricted",
        pfas_viable=False,
        pfas_viability_note=(
            "Composting does not destroy PFAS. The compost product carries the same regulatory restrictions "
            "as the source biosolids for land application. This pathway is not recommended where PFAS "
            "exceeds regulatory triggers unless the compost product is landfilled (not land-applied)."
        ),
    ),

    "landfill": PFASFateAssumptions(
        pathway="landfill",
        display_name="Landfill Disposal",
        pfas_fraction_in_solid_output=1.0,
        pfas_destruction_efficiency=0.0,
        leachate_pathway_fraction=0.20,
        solid_mass_reduction_factor=1.0,
        caveats=[
            "PFAS is NOT destroyed in landfill. The total PFAS mass is emplaced and persists.",
            "PFAS leaches into landfill leachate over decades to centuries — leaching is not instantaneous.",
            "The leachate_pathway_fraction of 20% characterises the fraction of landfilled PFAS with "
            "a credible leachate migration pathway. It is NOT an annual release rate.",
            "Modern engineered landfills with leachate collection can capture and treat PFAS-containing "
            "leachate (via GAC, nanofiltration), significantly reducing environmental release.",
            "Older or unlined landfills have substantially higher environmental release risk.",
            "Landfill leachate treatment produces a PFAS concentrate that itself requires disposal.",
            "Some landfill operators are declining PFAS-impacted biosolids or requiring pre-characterisation.",
            "Long-term liability for legacy PFAS contamination from landfill is an emerging financial risk.",
        ],
        regulatory_restriction_flag="conditional",
        pfas_viable=True,
        pfas_viability_note=(
            "Landfill is currently the pragmatic default pathway for PFAS-impacted biosolids in most "
            "Australian jurisdictions. Landfill operator acceptance and long-term liability are "
            "increasing risks. Engineered landfills with leachate management are preferred."
        ),
    ),

    "incineration": PFASFateAssumptions(
        pathway="incineration",
        display_name="Incineration",
        pfas_fraction_in_solid_output=0.01,     # ~1% remaining in ash if correctly operated
        pfas_destruction_efficiency=0.99,        # FIX: 95% → 99% (literature consensus)
        leachate_pathway_fraction=0.005,
        solid_mass_reduction_factor=0.25,
        caveats=[
            "⚠ CRITICAL: The 99% destruction efficiency assumes sustained combustion at >850°C "
            "with ≥2 second residence time AND effective flue gas treatment (EPA Australia 2023; US EPA 2020).",
            "At temperatures >1000°C with ≥2s, destruction efficiency can exceed 99.999% for "
            "long-chain PFAS (PFOS, PFOA). Short-chain PFAS (C4–C6) require higher temperatures "
            "and are more resistant to thermal destruction.",
            "Sub-optimal combustion (process upsets, cold spots, inadequate residence time) can "
            "result in PFAS reforming in cooler flue gas zones — particularly PFOA from precursor compounds.",
            "Ash residuals may contain concentrated PFAS from incompletely destroyed material "
            "or sorbed onto fly ash. Ash must be characterised before disposal.",
            "Air pollution control systems (activated carbon injection, wet scrubbing) are essential "
            "to prevent PFAS emissions to atmosphere.",
            "Operating temperature and residence time records must be maintained for regulatory compliance.",
            "This model assumes a modern, correctly operated biosolids incinerator. "
            "Do not apply this efficiency to non-dedicated or poorly controlled facilities.",
        ],
        regulatory_restriction_flag="conditional",
        pfas_viable=True,
        pfas_viability_note=(
            "Incineration at correctly operated, approved facilities is the most effective currently "
            "available PFAS destruction pathway for biosolids at scale. "
            "Operating conditions and ash management must be confirmed."
        ),
    ),

    "pyrolysis": PFASFateAssumptions(
        pathway="pyrolysis",
        display_name="Pyrolysis",
        pfas_fraction_in_solid_output=0.45,     # ~45% remains in char (at mid-range temperature)
        pfas_destruction_efficiency=0.50,        # Central estimate; actual range 20–90%+
        leachate_pathway_fraction=0.05,
        solid_mass_reduction_factor=0.35,
        caveats=[
            "⚠ PFAS fate in pyrolysis is HIGHLY VARIABLE and temperature-dependent.",
            "At <400°C: PFAS predominantly transfers to char with minimal destruction (<30%).",
            "At 500–700°C: Partial destruction (50–70% typical) with PFAS concentrated in char.",
            "At >700°C with sufficient residence time: Destruction may approach 80–95%.",
            "Pyrolysis oils and condensate may contain volatile PFAS precursor compounds.",
            "Char from PFAS-containing biosolids MUST be characterised (PFAS analysis) before "
            "any beneficial use (soil amendment, carbon sequestration credit claims).",
            "Char with elevated PFAS cannot be beneficially applied to land — it becomes a "
            "PFAS-contaminated waste requiring landfill disposal.",
            "This model uses a central estimate (50% destruction at ~600°C). "
            "Actual performance depends on specific reactor design, temperature profile, and retention time.",
            "PFAS fate in pyrolysis of biosolids is an active research area — "
            "see Crimi et al. (2022) and Ross et al. (2022) for current literature.",
        ],
        regulatory_restriction_flag="check_jurisdiction",
        pfas_viable=True,
        pfas_viability_note=(
            "Pyrolysis may reduce PFAS mass by 50%+ depending on operating temperature. "
            "Char product MUST be characterised for PFAS before any beneficial use. "
            "Higher operating temperatures (>650°C) are recommended for PFAS-impacted feedstocks."
        ),
    ),

    "gasification": PFASFateAssumptions(
        pathway="gasification",
        display_name="Gasification",
        pfas_fraction_in_solid_output=0.25,     # ~25% remains in slag/ash
        pfas_destruction_efficiency=0.75,
        leachate_pathway_fraction=0.02,
        solid_mass_reduction_factor=0.20,
        caveats=[
            "Gasification operates at higher temperatures (700–1100°C) than pyrolysis, "
            "generally achieving better PFAS destruction (estimated 70–90%).",
            "Residual PFAS concentrates in vitrified slag or ash — characterisation required.",
            "Syngas cooling condensate (quench water) may contain PFAS — treatment required.",
            "Full-scale PFAS destruction data for gasification of biosolids is limited compared "
            "to incineration. Operating parameters are facility-specific.",
            "If plasma gasification (>1400°C) is used, destruction efficiency may approach "
            "that of incineration.",
        ],
        regulatory_restriction_flag="check_jurisdiction",
        pfas_viable=True,
        pfas_viability_note=(
            "Higher-temperature gasification achieves better PFAS destruction than pyrolysis. "
            "Slag/ash and quench water must be characterised. Plasma gasification provides "
            "higher destruction efficiency but at higher capital and operating cost."
        ),
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# INPUT DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PFASInputs:
    pfas_risk_tier: str = PFASRiskTier.MODERATE.value
    pfas_concentration_ug_kg: Optional[float] = None   # Overrides tier if set
    pfas_compound_class: str = PFASCompoundClass.TOTAL_PFAS.value
    pfas_uncertainty_factor: float = 3.0

    known_pfas_source_in_catchment: bool = False
    afff_use_history: bool = False
    industrial_pfas_dischargers: bool = False

    disposal_pathway: str = "landfill"

    # User overrides for pathway fate assumptions
    user_pfas_destruction_efficiency: Optional[float] = None
    user_pfas_fraction_solid: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PFASLiquidStreamLoad:
    """PFAS carried in liquid streams returned to the liquid treatment line."""
    reject_water_g_yr: float = 0.0          # From digestion (to headworks)
    filtrate_g_yr: float = 0.0              # From dewatering centrate/filtrate
    total_to_liquid_line_g_yr: float = 0.0
    pct_of_feed: float = 0.0
    note: str = ""


@dataclass
class PFASMassBalance:
    """PFAS mass balance through the full sludge treatment train."""

    # ── Concentrations ────────────────────────────────────────────────────
    pfas_concentration_feed_ug_kg: float = 0.0       # In raw feed sludge
    pfas_concentration_digested_ug_kg: float = 0.0   # After digestion (concentrates)
    pfas_concentration_cake_ug_kg: float = 0.0       # In dewatered cake (= applied product)
    pfas_concentration_after_pathway_ug_kg: float = 0.0  # In final solid output
    pfas_concentration_basis: str = ""

    # Uncertainty range (when using tier defaults)
    pfas_concentration_lo_ug_kg: float = 0.0
    pfas_concentration_hi_ug_kg: float = 0.0

    # ── Annual PFAS masses (g/yr) ─────────────────────────────────────────
    pfas_mass_in_feed_g_yr: float = 0.0
    pfas_mass_after_digestion_g_yr: float = 0.0
    pfas_mass_in_cake_g_yr: float = 0.0
    pfas_mass_destroyed_g_yr: float = 0.0
    pfas_mass_in_final_solid_g_yr: float = 0.0

    # ── Liquid stream loads (NEW — v1.1) ──────────────────────────────────
    liquid_streams: PFASLiquidStreamLoad = field(default_factory=PFASLiquidStreamLoad)

    # ── Land loading (for land application pathway) ───────────────────────
    pfas_loading_g_ha_yr: Optional[float] = None     # At assumed application rate
    application_rate_t_ds_ha: float = 2.0

    # ── Leachate pathway characterisation ────────────────────────────────
    # Fraction of cake PFAS with a leachate migration pathway (NOT an annual rate)
    pfas_leachate_pathway_g: float = 0.0
    leachate_pathway_label: str = ""

    # ── Regulatory comparison ─────────────────────────────────────────────
    pfas_exceeds_nsw_trigger: bool = False
    pfas_exceeds_vic_trigger: bool = False
    regulatory_trigger_nsw_ug_kg: float = 100.0

    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def note(self, s: str) -> None: self.notes.append(s)
    def warn(self, s: str) -> None: self.warnings.append(s)

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "PFAS in feed sludge (µg/kg DS)":          f"{self.pfas_concentration_feed_ug_kg:,.0f}",
            "PFAS in digested sludge (µg/kg DS)":      f"{self.pfas_concentration_digested_ug_kg:,.0f}",
            "PFAS in dewatered cake (µg/kg DS)":       f"{self.pfas_concentration_cake_ug_kg:,.0f}",
            "PFAS compound class":                     self.pfas_concentration_basis,
            "Annual PFAS mass in feed (g/yr)":         f"{self.pfas_mass_in_feed_g_yr:,.0f}",
            "Annual PFAS mass in cake (g/yr)":         f"{self.pfas_mass_in_cake_g_yr:,.0f}",
            "Annual PFAS to liquid line (g/yr)":       f"{self.liquid_streams.total_to_liquid_line_g_yr:,.0f}",
            "PFAS in final solid output (µg/kg DS)":   f"{self.pfas_concentration_after_pathway_ug_kg:,.1f}",
            "Exceeds NSW EPA trigger (100 µg/kg)":     "YES ⚠" if self.pfas_exceeds_nsw_trigger else "No",
        }


# ─────────────────────────────────────────────────────────────────────────────
# PFAS MODEL  (v1.1)
# ─────────────────────────────────────────────────────────────────────────────

class PFASModel:
    """
    PFAS mass balance and fate model for biosolids (v1.1).

    Tracks PFAS through four explicit steps:
      1. Raw sludge (feed concentration × raw DS)
      2. Digestion  (PFAS concentrates as VS destroyed; 10% to reject water)
      3. Dewatering (10% to filtrate/centrate; concentration in cake)
      4. Disposal pathway (destruction or redistribution)
    """

    # Fraction of PFAS retained in solids through each processing step
    # Based on Hamid et al. (2018) and Higgins et al. (2005)
    PFAS_RETENTION_DIGESTION  = 0.90   # 90% stays with solids; 10% to reject water
    PFAS_RETENTION_DEWATERING = 0.90   # 90% stays in cake; 10% to filtrate

    def calculate(
        self,
        pfas_inputs: PFASInputs,
        raw_ds_t_yr: float,
        cake_ds_t_yr: float,
        cake_wet_t_yr: float,
        digested_ds_t_yr: Optional[float] = None,
    ) -> PFASMassBalance:
        """
        Parameters
        ----------
        raw_ds_t_yr     : Raw dry solids fed to treatment train (t DS/yr)
        cake_ds_t_yr    : Dewatered cake dry solids (t DS/yr)
                          NOTE: equals digested_ds_t_yr — dewatering removes water, not DS
        cake_wet_t_yr   : Dewatered cake wet tonnes (t wet/yr)
        digested_ds_t_yr: Digested sludge DS (t DS/yr). If None, uses cake_ds_t_yr.
        """
        r = PFASMassBalance()

        # If digested DS not provided, default to cake DS (conservative)
        dig_ds = digested_ds_t_yr if digested_ds_t_yr is not None else cake_ds_t_yr

        # ── Step 1: Resolve feed PFAS concentration ────────────────────────
        if pfas_inputs.pfas_concentration_ug_kg is not None:
            feed_conc = pfas_inputs.pfas_concentration_ug_kg
        else:
            tier_data = PFAS_TIER_DEFAULTS_UG_KG.get(
                pfas_inputs.pfas_risk_tier,
                PFAS_TIER_DEFAULTS_UG_KG[PFASRiskTier.MODERATE.value]
            )
            feed_conc = tier_data["pfas_sum_ug_kg"]
            r.pfas_concentration_lo_ug_kg = feed_conc / pfas_inputs.pfas_uncertainty_factor
            r.pfas_concentration_hi_ug_kg = feed_conc * pfas_inputs.pfas_uncertainty_factor

        r.pfas_concentration_feed_ug_kg = feed_conc
        r.pfas_concentration_basis = pfas_inputs.pfas_compound_class

        # ── Step 2: PFAS mass in raw feed ─────────────────────────────────
        # mass (g/yr) = DS (t/yr) × conc (µg/kg DS) × 1e-3
        # because: t/yr × 1000 kg/t × µg/kg × 1e-6 g/µg = t × µg/kg × 1e-3 g
        r.pfas_mass_in_feed_g_yr = raw_ds_t_yr * feed_conc * 1e-3

        r.note(
            f"Feed: {raw_ds_t_yr:.0f} t DS/yr × {feed_conc:,.0f} µg/kg × 1e-3 = "
            f"{r.pfas_mass_in_feed_g_yr:,.1f} g PFAS/yr"
        )

        # ── Step 3: Digestion — PFAS concentrates, 10% to reject water ────
        #   Physical basis: PFAS is non-volatile and thermally stable at 37°C.
        #   It partitions predominantly to solids. ~10% moves to the liquid phase
        #   (reject water / centrate) — short-chain PFAS partition more.
        #   As VS is destroyed, the same PFAS mass is in fewer kg of DS → concentration rises.
        pfas_after_digestion = r.pfas_mass_in_feed_g_yr * self.PFAS_RETENTION_DIGESTION
        pfas_to_reject_water = r.pfas_mass_in_feed_g_yr * (1.0 - self.PFAS_RETENTION_DIGESTION)
        r.pfas_mass_after_digestion_g_yr = pfas_after_digestion

        # Concentration in digested sludge — divide by digested DS (smaller than raw DS)
        if dig_ds > 0:
            r.pfas_concentration_digested_ug_kg = pfas_after_digestion / (dig_ds * 1e-3)
        else:
            r.pfas_concentration_digested_ug_kg = feed_conc

        r.note(
            f"After digestion: {pfas_after_digestion:,.1f} g in {dig_ds:.0f} t DS → "
            f"{r.pfas_concentration_digested_ug_kg:,.0f} µg/kg DS "
            f"(↑ concentration as VS destroyed). "
            f"Reject water: {pfas_to_reject_water:,.1f} g/yr → liquid line."
        )

        # ── Step 4: Dewatering — 10% to filtrate, rest in cake ────────────
        #   Cake DS = digested DS (dewatering removes water, not DS).
        #   Cake concentration = mass in cake / cake DS.
        pfas_in_cake = pfas_after_digestion * self.PFAS_RETENTION_DEWATERING
        pfas_to_filtrate = pfas_after_digestion * (1.0 - self.PFAS_RETENTION_DEWATERING)
        r.pfas_mass_in_cake_g_yr = pfas_in_cake

        if cake_ds_t_yr > 0:
            r.pfas_concentration_cake_ug_kg = pfas_in_cake / (cake_ds_t_yr * 1e-3)
        else:
            r.pfas_concentration_cake_ug_kg = r.pfas_concentration_digested_ug_kg

        r.note(
            f"After dewatering: {pfas_in_cake:,.1f} g in {cake_ds_t_yr:.0f} t cake DS → "
            f"{r.pfas_concentration_cake_ug_kg:,.0f} µg/kg DS. "
            f"Filtrate: {pfas_to_filtrate:,.1f} g/yr → liquid line."
        )

        # ── Step 5: Liquid stream tracking (NEW v1.1) ─────────────────────
        total_liquid = pfas_to_reject_water + pfas_to_filtrate
        r.liquid_streams = PFASLiquidStreamLoad(
            reject_water_g_yr=pfas_to_reject_water,
            filtrate_g_yr=pfas_to_filtrate,
            total_to_liquid_line_g_yr=total_liquid,
            pct_of_feed=total_liquid / r.pfas_mass_in_feed_g_yr * 100 if r.pfas_mass_in_feed_g_yr > 0 else 0.0,
            note=(
                "PFAS in liquid streams returns to the liquid treatment line. "
                "It passes through biological treatment largely intact and reports to "
                "the treated effluent or accumulates in secondary sludge."
            ),
        )
        r.warn(
            f"⚠ {total_liquid:,.1f} g PFAS/yr ({r.liquid_streams.pct_of_feed:.0f}% of feed) "
            f"is returned to the liquid treatment line via reject water and filtrate. "
            f"This PFAS cannot be removed by conventional biological treatment and will "
            f"report to the treated effluent or recycle back to the sludge stream."
        )

        # ── Step 6: Disposal pathway fate ─────────────────────────────────
        pathway_key = pfas_inputs.disposal_pathway
        fate = PFAS_PATHWAY_ASSUMPTIONS.get(pathway_key, PFAS_PATHWAY_ASSUMPTIONS["landfill"])

        dest_eff = (pfas_inputs.user_pfas_destruction_efficiency
                    if pfas_inputs.user_pfas_destruction_efficiency is not None
                    else fate.pfas_destruction_efficiency)
        solid_frac = (pfas_inputs.user_pfas_fraction_solid
                      if pfas_inputs.user_pfas_fraction_solid is not None
                      else fate.pfas_fraction_in_solid_output)

        r.pfas_mass_destroyed_g_yr = pfas_in_cake * dest_eff
        pfas_remaining = pfas_in_cake * (1.0 - dest_eff)
        r.pfas_mass_in_final_solid_g_yr = pfas_remaining * solid_frac

        # Leachate pathway characterisation (NOT an annual rate — see caveat)
        r.pfas_leachate_pathway_g = pfas_remaining * fate.leachate_pathway_fraction
        r.leachate_pathway_label = (
            f"{fate.leachate_pathway_fraction*100:.0f}% of remaining PFAS has a "
            f"leachate/liquid migration pathway (not an annual release rate)"
        )

        # ── Step 7: Concentration in final solid output ───────────────────
        # For non-destructive pathways: concentration = cake concentration (no change)
        # For thermal pathways: concentration rises because DS mass is reduced to ash/char
        output_ds_t_yr = cake_ds_t_yr * fate.solid_mass_reduction_factor

        if dest_eff == 0.0:
            # Non-destructive: applied product IS the cake, so concentration = cake conc
            r.pfas_concentration_after_pathway_ug_kg = r.pfas_concentration_cake_ug_kg
        elif output_ds_t_yr > 0 and pfas_remaining > 0:
            # Thermal: remaining PFAS concentrates in reduced-mass ash/char
            r.pfas_concentration_after_pathway_ug_kg = (
                r.pfas_mass_in_final_solid_g_yr / (output_ds_t_yr * 1e-3)
            )
        else:
            r.pfas_concentration_after_pathway_ug_kg = 0.0

        r.note(
            f"Pathway ({pathway_key}): destruction {dest_eff*100:.0f}% | "
            f"Destroyed: {r.pfas_mass_destroyed_g_yr:,.1f} g/yr | "
            f"In final solid: {r.pfas_mass_in_final_solid_g_yr:,.1f} g/yr @ "
            f"{r.pfas_concentration_after_pathway_ug_kg:,.0f} µg/kg DS"
        )

        # ── Step 8: Land application loading rate ─────────────────────────
        if pathway_key == "land_application":
            # g/ha/yr at typical agronomic N application rate
            # Typical Class B rate: 2 t DS/ha/yr for Australian conditions
            r.application_rate_t_ds_ha = 2.0
            r.pfas_loading_g_ha_yr = (
                r.pfas_concentration_cake_ug_kg * 1e-3 * r.application_rate_t_ds_ha * 1000
            )
            r.note(
                f"Land application: PFAS loading = "
                f"{r.pfas_loading_g_ha_yr:,.0f} mg/ha/yr "
                f"at {r.application_rate_t_ds_ha} t DS/ha/yr application rate"
            )

        # ── Step 9: Regulatory comparison ────────────────────────────────
        r.regulatory_trigger_nsw_ug_kg = PFAS_REGULATORY_REFS["nsw_epa_biosolids_trigger_ug_kg"]
        r.pfas_exceeds_nsw_trigger = r.pfas_concentration_cake_ug_kg > r.regulatory_trigger_nsw_ug_kg
        r.pfas_exceeds_vic_trigger = r.pfas_concentration_cake_ug_kg > PFAS_REGULATORY_REFS["vic_epa_biosolids_trigger_ug_kg"]

        # ── Warnings ──────────────────────────────────────────────────────
        if pfas_inputs.pfas_concentration_ug_kg is None:
            tier_data = PFAS_TIER_DEFAULTS_UG_KG.get(pfas_inputs.pfas_risk_tier, {})
            r.warn(
                f"⚠ PFAS concentration estimated from '{pfas_inputs.pfas_risk_tier}' tier default "
                f"({feed_conc:,.0f} µg/kg ∑PFAS). "
                f"Actual values vary by 2–3 orders of magnitude between sites. "
                f"Basis: {tier_data.get('basis','See tier documentation')} "
                f"Obtain measured data before any planning or regulatory decisions."
            )

        if r.pfas_exceeds_nsw_trigger:
            r.warn(
                f"⚠ Cake concentration ({r.pfas_concentration_cake_ug_kg:,.0f} µg/kg DS) "
                f"exceeds NSW EPA and EPA Victoria interim triggers "
                f"({r.regulatory_trigger_nsw_ug_kg:.0f} µg/kg ∑PFAS). "
                f"Land application is likely prohibited."
            )

        if not fate.pfas_viable:
            r.warn(f"⚠ PATHWAY NOT RECOMMENDED: {fate.pfas_viability_note}")

        if pfas_inputs.afff_use_history or pfas_inputs.industrial_pfas_dischargers:
            r.warn(
                "⚠ Known high-concentration PFAS sources in catchment (AFFF or industrial discharger). "
                "Biosolids PFAS testing is essential. Concentrations may be "
                "10–100× higher than tier defaults."
            )

        for caveat in fate.caveats:
            r.note(caveat)

        return r


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def pfas_inputs_from_scenario(
    domain_inputs: dict,
    pfas_overrides: dict = None,
) -> PFASInputs:
    ov = pfas_overrides or {}
    return PFASInputs(
        pfas_risk_tier            = ov.get("pfas_risk_tier", PFASRiskTier.MODERATE.value),
        pfas_concentration_ug_kg  = ov.get("pfas_concentration_ug_kg"),
        pfas_compound_class       = ov.get("pfas_compound_class", PFASCompoundClass.TOTAL_PFAS.value),
        pfas_uncertainty_factor   = float(ov.get("pfas_uncertainty_factor", 3.0)),
        known_pfas_source_in_catchment = bool(ov.get("known_pfas_source_in_catchment", False)),
        afff_use_history          = bool(ov.get("afff_use_history", False)),
        industrial_pfas_dischargers = bool(ov.get("industrial_pfas_dischargers", False)),
        disposal_pathway          = ov.get("disposal_pathway",
                                           domain_inputs.get("disposal_pathway", "landfill")),
    )
