"""
WaterPoint Concept Study Template — section structure generator

This Python module takes project-specific parameters and generates the
skeleton .js file that, when run with Node, produces the final .docx.

Usage:
    from template_structure import ConceptStudyReport
    
    report = ConceptStudyReport(
        plant_name="Canungra STP",
        client="Queensland Urban Utilities",
        author="ph2o Consulting",
        revision=20,
        date="April 2026",
        ...
    )
    report.generate_js_file(output_path="./my_project_report.js")

Template version: v1.0 (derived from Canungra STP Rev 20)
"""

from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


@dataclass
class LicenceLimit:
    """Effluent licence parameter."""
    parameter: str   # e.g., "TN"
    median: float    # mg/L
    p80: float       # mg/L
    peak: float      # mg/L
    annual_mass_kg_yr: Optional[float] = None  # kg/yr (if applicable)


@dataclass
class PlantConfiguration:
    """Basic plant configuration."""
    plant_type: str  # e.g., "5-stage Bardenpho MBR"
    design_ep: int
    design_adwf_mld: float
    temperature_C: float  # winter design temperature
    tkn_mgL_AAL: float
    cod_mgL_AAL: float
    tkn_mgL_MML: Optional[float] = None
    cod_mgL_MML: Optional[float] = None
    mlss_range_mgL: tuple = (7500, 12000)
    
    # Zone volumes (kL)
    anaerobic_kL: float = 0.0
    anoxic_kL: float = 0.0
    aerobic_kL: float = 0.0
    de_aeration_kL: float = 0.0
    post_anoxic_kL: float = 0.0
    mbr_kL: float = 0.0


@dataclass
class Scenario:
    """A single intensification scenario."""
    code: str        # e.g., "S1A", "S2_C3"
    name: str        # e.g., "Controls and operational upgrades"
    description: str
    max_ep: int
    capex_aud_m: float
    binding_constraint: str
    pfd_image_path: Optional[str] = None
    advantages: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    capex_breakdown: List[tuple] = field(default_factory=list)  # (item, AUD k)


@dataclass
class RFC:
    """A Request For Confirmation — Phase 2 verification item."""
    number: int
    title: str
    scope: str
    activities: List[str]
    cost_aud: str    # e.g., "15-25k"
    timeline: str    # e.g., "8-12 weeks"
    priority: str    # HIGH/MEDIUM/LOW/CONDITIONAL/STAGE_0_GATEWAY
    impact: str


@dataclass
class RiskItem:
    """A 'what could break' risk flag for Section 6."""
    number: int       # F1, F2, ...
    title: str
    description: str
    mitigation: str
    related_rfc: Optional[int] = None  # e.g., 2 for RFC-02


@dataclass
class ConceptStudyReport:
    """Top-level concept study report configuration."""
    plant_name: str
    client: str
    author: str = "ph2o Consulting"
    revision: int = 1
    date: str = "2026"
    
    # Plant context
    location: str = ""
    plant: PlantConfiguration = None
    licence_limits: List[LicenceLimit] = field(default_factory=list)
    
    # Scenario set
    scenarios: List[Scenario] = field(default_factory=list)
    
    # Verification workstream
    rfcs: List[RFC] = field(default_factory=list)
    
    # Risk register
    risks: List[RiskItem] = field(default_factory=list)
    
    # Key findings for exec summary (3-6 bullets)
    key_findings: List[str] = field(default_factory=list)
    
    # Recommended variant (concept-study language)
    preferred_concept: str = ""
    preferred_concept_rationale: str = ""
    
    # Licence interpretation (if dual interpretation applies)
    dual_licence_interpretation: bool = False
    licence_interpretation_A_summary: str = ""
    licence_interpretation_B_summary: str = ""
    adopted_basis: str = "B"  # 'A', 'B', or 'tested as planning basis'
    
    def generate_js_file(self, output_path: str, charts_dir: str = "./charts"):
        """Emit the .js file that builds the final docx."""
        # This method would emit the full JavaScript template, populated
        # with project-specific data. See example_canungra_rev20.js for
        # the output structure.
        #
        # Implementation is straightforward but verbose — each section
        # becomes a block of content.push(...) calls.
        #
        # For v1.0 of the template, we provide the structure spec here
        # and users copy/adapt example_canungra_rev20.js as their starting
        # point.
        raise NotImplementedError(
            "v1.0: use example_canungra_rev20.js as a copy-and-modify starting "
            "point. Future versions will auto-generate from ConceptStudyReport."
        )


# ============================================================================
# STANDARD SECTION STRUCTURE (for reference when hand-building a project)
# ============================================================================

STANDARD_SECTIONS = [
    ("Document status and scope", [
        "Confidence level of this study",
        "What this document establishes",
        "What this document does NOT establish",
    ]),
    ("Executive summary", [
        "Key findings",
        "Recommended path forward",
    ]),
    ("1. Introduction", [
        "1.1 Background",
        "1.2 Scope boundaries",
        "1.3 Approach",
    ]),
    ("2. Plant background and baseline", [
        "2.1 As-built process configuration",
        "2.2 Licence limits",
        "2.3 Mass load basis (if dual interpretation)",
        "2.4 Diurnal loading profile",
        "2.5 Process flow diagram",
        "2.6 Alternating operating modes (if applicable)",
    ]),
    ("3. Modelling approach and limitations", [
        "3.1 Process kinetics",
        "3.2 Kinetic parameters",
        "3.3 Sensitivity on most important parameter",
        "3.4 Other model limitations",
        "3.5 Alkalinity balance",
        "3.6 Supplementary sensitivity (e.g., IFAS flux)",
    ]),
    ("4. Intensification scenarios", [
        "4.1 S1A — Controls and operational upgrades",
        "4.2 S1B — Intermediate technology (if applicable)",
        "4.3 S2 — Reconfiguration with variants",
        "4.4+ S2-A through S2-N individual variants",
        "4.M Decision tree by growth horizon",
        "4.M+1 Recycle optimisation",
        "4.M+2 Capex band summary",
    ]),
    ("5. Modelled process results", [
        "5.1 Capacity and binding constraints",
        "5.2 Annual mass load framing",
        "5.3 Effluent quality response to loading",
        "5.4 Increased annual discharge load",
    ]),
    ("6. What could break this scheme", []),
    ("7. Phase 2 verification package", []),
    ("8. Recommendations", [
        "8.1 Immediate action — no regret",
        "8.2 Pre-feasibility verification required",
        "8.3 Intensification pathway — dependent on verification",
        "8.4 Decision gate for capital commitment",
        "8.5 Regulatory parallel track (if applicable)",
    ]),
    ("9. Caveats and limitations", [
        "9.1 Model limitations",
        "9.2 Scope exclusions",
        "9.3 Commercial and planning caveats",
        "9.4 Status of key statements",
    ]),
]


if __name__ == "__main__":
    print("WaterPoint Concept Study Template — v1.0")
    print()
    print("Standard section structure:")
    for title, subs in STANDARD_SECTIONS:
        print(f"\n{title}")
        for s in subs:
            print(f"    {s}")
