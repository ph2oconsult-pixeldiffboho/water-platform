"""
domains/wastewater/pfas_risk_model.py

PFAS Risk Scoring for Biosolids Management Pathways
=====================================================
Qualitative risk scoring system for biosolids strategy planning.

IMPORTANT: These are QUALITATIVE risk scores for comparative planning only.
They are NOT a site-specific risk assessment and do not replace
professional environmental risk assessment, contaminated land assessment,
or regulatory advice.

Risk dimensions scored:
  1. Environmental risk     — PFAS release to soil, groundwater, air
  2. Regulatory risk        — Current and future regulatory compliance risk
  3. Public perception risk — Community and stakeholder acceptance risk
  4. Long-term liability    — Future remediation or legal liability exposure

Scoring approach:
  Each dimension is scored 1–4 (Low / Moderate / High / Very High).
  Scores are qualitative and reflect current regulatory environment (2024–2025).
  They will need updating as PFAS regulation evolves.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


class RiskLevel(str, Enum):
    LOW       = "Low"
    MODERATE  = "Moderate"
    HIGH      = "High"
    VERY_HIGH = "Very High"

    @property
    def score(self) -> int:
        return {"Low": 1, "Moderate": 2, "High": 3, "Very High": 4}[self.value]

    @property
    def colour(self) -> str:
        return {
            "Low":       "#2ca02c",
            "Moderate":  "#ff7f0e",
            "High":      "#d62728",
            "Very High": "#7b0000",
        }[self.value]


@dataclass
class PFASRiskScore:
    """Risk scores for a single biosolids management pathway."""

    pathway: str = ""
    display_name: str = ""

    # Four risk dimensions
    environmental_risk: RiskLevel = RiskLevel.MODERATE
    regulatory_risk: RiskLevel = RiskLevel.MODERATE
    public_perception_risk: RiskLevel = RiskLevel.MODERATE
    long_term_liability_risk: RiskLevel = RiskLevel.MODERATE

    # Rationale strings for each dimension
    environmental_rationale: str = ""
    regulatory_rationale: str = ""
    public_perception_rationale: str = ""
    long_term_liability_rationale: str = ""

    # Overall composite (average of four dimensions)
    composite_score: float = 0.0
    composite_level: RiskLevel = RiskLevel.MODERATE

    # Context-adjusted scores (higher if PFAS concentration above trigger)
    pfas_elevated: bool = False     # True if concentration exceeds regulatory trigger

    def calculate_composite(self) -> None:
        avg = (
            self.environmental_risk.score +
            self.regulatory_risk.score +
            self.public_perception_risk.score +
            self.long_term_liability_risk.score
        ) / 4.0
        self.composite_score = round(avg, 2)
        if avg < 1.5:
            self.composite_level = RiskLevel.LOW
        elif avg < 2.5:
            self.composite_level = RiskLevel.MODERATE
        elif avg < 3.5:
            self.composite_level = RiskLevel.HIGH
        else:
            self.composite_level = RiskLevel.VERY_HIGH

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "Pathway":                    self.display_name,
            "Environmental Risk":         self.environmental_risk.value,
            "Regulatory Risk":            self.regulatory_risk.value,
            "Public Perception Risk":     self.public_perception_risk.value,
            "Long-term Liability Risk":   self.long_term_liability_risk.value,
            "Composite Score (1–4)":      self.composite_score,
            "Overall Risk Level":         self.composite_level.value,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PATHWAY RISK PROFILES
# ─────────────────────────────────────────────────────────────────────────────
# Scores reflect 2024–2025 Australian regulatory environment.
# All scores assume biosolids with detectable ∑PFAS (>10 µg/kg DS).
# For negligible PFAS (<10 µg/kg), scores would be one tier lower across all dimensions.

BASE_PATHWAY_RISK_PROFILES: Dict[str, Dict] = {

    "land_application": {
        "display_name": "Land Application",
        "environmental_risk": RiskLevel.VERY_HIGH,
        "regulatory_risk":    RiskLevel.VERY_HIGH,
        "public_perception_risk": RiskLevel.VERY_HIGH,
        "long_term_liability_risk": RiskLevel.VERY_HIGH,
        "environmental_rationale": (
            "PFAS applied to land persists indefinitely. Leaching to groundwater is a "
            "well-documented pathway. Bioaccumulation in crops and livestock is an additional "
            "exposure pathway. No destruction of PFAS mass occurs."
        ),
        "regulatory_rationale": (
            "Land application of PFAS-containing biosolids is restricted or banned in most "
            "Australian states (NSW, VIC, QLD) as of 2024. HEPA NEMP 2.0 and state-specific "
            "guidance are progressively tightening. Trend is toward stricter regulation."
        ),
        "public_perception_rationale": (
            "PFAS contamination of farmland and food crops is a high-profile public issue. "
            "Community opposition to biosolids land application in PFAS-affected areas is strong. "
            "Affected landowners face property devaluation and market access issues."
        ),
        "long_term_liability_rationale": (
            "Utilities, councils, and farmers who have applied PFAS-containing biosolids are "
            "facing class action litigation and remediation orders. This is now a material "
            "long-term financial liability risk for any organisation involved."
        ),
    },

    "composting": {
        "display_name": "Composting",
        "environmental_risk": RiskLevel.HIGH,
        "regulatory_risk":    RiskLevel.HIGH,
        "public_perception_risk": RiskLevel.HIGH,
        "long_term_liability_risk": RiskLevel.HIGH,
        "environmental_rationale": (
            "PFAS passes through composting with <5% transformation. Compost product "
            "retains ~97% of input PFAS mass. Environmental risk depends critically on "
            "compost product end-use: if applied to land, risk equals direct land application. "
            "If landfilled, risk is similar to landfill. The HIGH rating assumes compost "
            "is used as a soil amendment (the intended and common commercial use)."
        ),
        "regulatory_rationale": (
            "Compost product faces the same land application restrictions as biosolids. "
            "In practice, compost from PFAS-impacted biosolids will not meet product "
            "certification standards under current PFAS guidance."
        ),
        "public_perception_rationale": (
            "Commercial compost contaminated with PFAS creates brand and market risk "
            "for the compost producer. Consumer awareness of 'forever chemicals' in garden "
            "products is growing."
        ),
        "long_term_liability_rationale": (
            "Same liability exposure as land application, potentially distributed over "
            "a wider geographic area via compost product distribution."
        ),
    },

    "landfill": {
        "display_name": "Landfill Disposal",
        "environmental_risk": RiskLevel.MODERATE,
        "regulatory_risk":    RiskLevel.MODERATE,
        "public_perception_risk": RiskLevel.LOW,
        "long_term_liability_risk": RiskLevel.MODERATE,
        "environmental_rationale": (
            "Modern lined landfills with leachate collection and treatment provide "
            "significant PFAS containment. PFAS leachate treatment is technically feasible "
            "(GAC, nanofiltration). Risk is reduced but not eliminated — long-term liner "
            "integrity is uncertain, and leachate treatment creates a PFAS concentrate "
            "that itself requires management."
        ),
        "regulatory_rationale": (
            "Landfill is the current default pathway for PFAS-impacted biosolids. "
            "Regulatory acceptance is generally current, but landfill operators are "
            "increasingly imposing acceptance conditions. Some landfills are refusing "
            "PFAS-impacted biosolids or requiring prior characterisation."
        ),
        "public_perception_rationale": (
            "Landfill is generally accepted by community as interim management for "
            "PFAS-impacted material. Less community opposition than land application."
        ),
        "long_term_liability_rationale": (
            "Liability is partially transferred to landfill operator under waste contract. "
            "However, the waste generator (utility) may retain residual liability for "
            "historic PFAS content. Landfill liner failure is a long-term risk."
        ),
    },

    "incineration": {
        "display_name": "Incineration",
        "environmental_risk": RiskLevel.LOW,
        "regulatory_risk":    RiskLevel.LOW,
        "public_perception_risk": RiskLevel.MODERATE,
        "long_term_liability_risk": RiskLevel.LOW,
        "environmental_rationale": (
            "Correctly operated incineration (>850°C, ≥2s residence time, flue gas treatment) "
            "achieves >99% PFAS destruction. Residual environmental risk is from: "
            "(1) ash residuals which may contain concentrated PFAS from incompletely destroyed "
            "material and must be characterised before disposal; "
            "(2) process upsets where sub-optimal combustion conditions allow PFAS to pass through. "
            "This LOW rating is CONDITIONAL on confirmed correct operating conditions."
        ),
        "regulatory_rationale": (
            "Incineration at approved biosolids facilities is the most regulatorily defensible "
            "pathway for PFAS-impacted material in Australia. Operating temperature, residence time, "
            "and flue gas treatment records must be maintained. Ash characterisation may be required."
        ),
        "public_perception_rationale": (
            "Community concern about air emissions (PFAS in flue gas, dioxins) generates moderate "
            "opposition risk even where operational monitoring supports safety. "
            "'Not in my backyard' opposition to siting new incinerators is common. "
            "Existing permitted facilities avoid this risk."
        ),
        "long_term_liability_rationale": (
            "Correctly documented incineration with confirmed operating conditions provides "
            "effective termination of PFAS liability for the treated material. "
            "Liability is LOW conditional on ash characterisation and compliant disposal. "
            "Process upsets without documentation would increase this rating."
        ),
    },

    "pyrolysis": {
        "display_name": "Pyrolysis",
        "environmental_risk": RiskLevel.MODERATE,
        "regulatory_risk":    RiskLevel.MODERATE,
        "public_perception_risk": RiskLevel.LOW,
        "long_term_liability_risk": RiskLevel.MODERATE,
        "environmental_rationale": (
            "PFAS fate in pyrolysis is variable and temperature-dependent. At adequate "
            "temperatures (>600°C), significant destruction is achievable. At lower temperatures, "
            "PFAS concentrates in char. Char from PFAS-containing biosolids requires "
            "characterisation before any beneficial use."
        ),
        "regulatory_rationale": (
            "Pyrolysis is emerging as a PFAS management pathway but regulatory framework "
            "is still developing. Facility approval requirements vary. Char product "
            "regulatory status depends on PFAS characterisation result."
        ),
        "public_perception_rationale": (
            "Pyrolysis is generally perceived as a more 'sustainable' technology than "
            "landfill. Limited public familiarity means lower community opposition "
            "than incineration, though this may change as awareness grows."
        ),
        "long_term_liability_rationale": (
            "Liability depends on operating temperature and char characterisation outcome. "
            "If char contains elevated PFAS, its disposal pathway creates further liability. "
            "Liability is lower than land application/landfill but higher than incineration."
        ),
    },

    "gasification": {
        "display_name": "Gasification",
        "environmental_risk": RiskLevel.LOW,
        "regulatory_risk":    RiskLevel.MODERATE,
        "public_perception_risk": RiskLevel.LOW,
        "long_term_liability_risk": RiskLevel.LOW,
        "environmental_rationale": (
            "Higher operating temperatures than pyrolysis generally achieve better PFAS "
            "destruction. Residual risk from ash/slag PFAS concentration and syngas "
            "condensate. Environmental performance similar to or better than pyrolysis "
            "at adequate operating conditions."
        ),
        "regulatory_rationale": (
            "Similar regulatory position to pyrolysis. Less common than incineration "
            "so regulatory precedent is more limited. Facility-specific approval required."
        ),
        "public_perception_rationale": (
            "Similar to pyrolysis — relatively low public familiarity, generally positive "
            "framing as energy recovery technology."
        ),
        "long_term_liability_rationale": (
            "If operated correctly with adequate temperature, liability profile is "
            "similar to incineration — effective mass destruction reduces long-term exposure."
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# RISK SCORING MODEL
# ─────────────────────────────────────────────────────────────────────────────

class PFASRiskModel:
    """
    Generates PFAS risk scores for biosolids management pathways.

    Scores are context-adjusted based on:
    - Whether PFAS concentration exceeds regulatory triggers
    - Whether there are known PFAS sources in the catchment
    - User-specified site context
    """

    def score_pathway(
        self,
        pathway: str,
        pfas_mass_balance: "PFASMassBalance",
        pfas_inputs: "PFASInputs",
    ) -> PFASRiskScore:
        """
        Calculate risk score for a single pathway.
        Context-adjusts based on actual PFAS concentration and site factors.
        """
        profile = BASE_PATHWAY_RISK_PROFILES.get(
            pathway,
            BASE_PATHWAY_RISK_PROFILES["landfill"]
        )

        r = PFASRiskScore(
            pathway=pathway,
            display_name=profile["display_name"],
            environmental_risk=profile["environmental_risk"],
            regulatory_risk=profile["regulatory_risk"],
            public_perception_risk=profile["public_perception_risk"],
            long_term_liability_risk=profile["long_term_liability_risk"],
            environmental_rationale=profile["environmental_rationale"],
            regulatory_rationale=profile["regulatory_rationale"],
            public_perception_rationale=profile["public_perception_rationale"],
            long_term_liability_rationale=profile["long_term_liability_rationale"],
            pfas_elevated=pfas_mass_balance.pfas_exceeds_nsw_trigger,
        )

        # Context adjustment: if PFAS concentration is very low (<10 µg/kg)
        # reduce risk scores by one tier for non-thermal pathways
        if (pfas_mass_balance.pfas_concentration_cake_ug_kg < 10.0 and
                pathway in ("land_application", "composting", "landfill")):
            r.environmental_risk    = self._downgrade(r.environmental_risk)
            r.regulatory_risk       = self._downgrade(r.regulatory_risk)
            r.long_term_liability_risk = self._downgrade(r.long_term_liability_risk)

        # Context adjustment: known AFFF or industrial sources — upgrade land app risk
        if pfas_inputs.afff_use_history or pfas_inputs.industrial_pfas_dischargers:
            if pathway in ("land_application", "composting"):
                r.environmental_risk    = self._upgrade(r.environmental_risk)
                r.long_term_liability_risk = self._upgrade(r.long_term_liability_risk)

        r.calculate_composite()
        return r

    def score_all_pathways(
        self,
        pfas_mass_balance: "PFASMassBalance",
        pfas_inputs: "PFASInputs",
    ) -> Dict[str, PFASRiskScore]:
        """Score all six pathways for comparison."""
        return {
            pathway: self.score_pathway(pathway, pfas_mass_balance, pfas_inputs)
            for pathway in BASE_PATHWAY_RISK_PROFILES
        }

    @staticmethod
    def _downgrade(level: RiskLevel) -> RiskLevel:
        order = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.VERY_HIGH]
        idx = order.index(level)
        return order[max(0, idx - 1)]

    @staticmethod
    def _upgrade(level: RiskLevel) -> RiskLevel:
        order = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.VERY_HIGH]
        idx = order.index(level)
        return order[min(len(order)-1, idx + 1)]
