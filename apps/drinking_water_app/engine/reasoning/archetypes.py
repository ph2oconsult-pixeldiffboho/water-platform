"""
AquaPoint Reasoning Engine — Gate 4
Treatment Archetype Selection and Exclusion Logic

Selects viable treatment archetypes based on source classification,
primary constraints, and direct filtration assessment.
Explains WHY each archetype is included or excluded.
"""

from dataclasses import dataclass, field
from typing import Optional
from .classifier import SourceWaterInputs, ClassificationResult


# ─── Archetype Definitions ────────────────────────────────────────────────────

ARCHETYPES = {
    "A": {
        "label": "Direct Filtration",
        "philosophy": (
            "Omit clarification. Coagulate and filter directly. "
            "Only viable for consistently low-turbidity, low-NOM, low-algae sources."
        ),
        "strengths": [
            "Lowest capital cost",
            "Smallest footprint",
            "Lowest sludge production",
        ],
        "weaknesses": [
            "No surge capacity for turbidity events",
            "Limited NOM removal",
            "Filter performance highly sensitive to feed quality",
            "Cannot handle algae-impacted sources",
        ],
        "residuals": "Filter backwash only — low volume, low solids",
        "lrv_profile": {
            "protozoa": (1.0, 2.0),   # (credited low, credited high)
            "bacteria": (2.0, 3.0),
            "virus": (1.0, 2.0),
        },
        "operability": "Low complexity — few moving parts, simple chemical programme",
        "energy_class": "low",
        "chemical_class": "low",
        "footprint_class": "very_low",
    },
    "B": {
        "label": "Conventional Clarification + Filtration",
        "philosophy": (
            "Full coagulation, flocculation, sedimentation, and granular media filtration. "
            "The industry workhorse. Robust across a wide range of source water conditions."
        ),
        "strengths": [
            "Proven across wide source water variability",
            "Robust NOM and solids removal",
            "Established operational knowledge base",
            "Good LRV credit for protozoa",
            "Handles moderate turbidity events",
        ],
        "weaknesses": [
            "Large footprint (sedimentation basins)",
            "Higher sludge production",
            "Limited performance on very low-density particles (algae)",
            "Does not address dissolved organics, PFAS, or trace contaminants",
        ],
        "residuals": "Clarifier sludge + filter backwash — moderate volume, moderate solids",
        "lrv_profile": {
            "protozoa": (2.0, 3.0),
            "bacteria": (2.0, 3.0),
            "virus": (1.0, 2.5),
        },
        "operability": "Moderate — requires coagulant control, sludge management",
        "energy_class": "low_moderate",
        "chemical_class": "moderate",
        "footprint_class": "high",
    },
    "C": {
        "label": "Intensified Clarification + Filtration",
        "philosophy": (
            "Higher-rate clarification (lamella / sand-ballasted / chemically-ballasted) "
            "followed by granular filtration. Smaller footprint than conventional "
            "sedimentation with comparable solids removal."
        ),
        "strengths": [
            "Reduced footprint vs. conventional sedimentation",
            "Higher hydraulic loading rates",
            "Faster response to load changes (ballasted systems)",
            "Suitable for retrofit and capacity upgrade",
        ],
        "weaknesses": [
            "Higher capital cost per unit area than horizontal flow clarifiers",
            "More mechanical complexity (recirculation, ballast recovery)",
            "Ballasted systems may underperform in very cold water",
            "Less effective for algae than DAF",
        ],
        "residuals": "Clarifier sludge + filter backwash — comparable to conventional",
        "lrv_profile": {
            "protozoa": (2.0, 3.0),
            "bacteria": (2.0, 3.0),
            "virus": (1.0, 2.5),
        },
        "operability": "Moderate-high — mechanical systems require more maintenance",
        "energy_class": "moderate",
        "chemical_class": "moderate",
        "footprint_class": "moderate",
    },
    "D": {
        "label": "DAF-Led Treatment",
        "philosophy": (
            "Dissolved air flotation as primary clarification step. "
            "Superior for algae, low-density particles, and NOM flotation. "
            "Followed by granular media filtration."
        ),
        "strengths": [
            "Best in class for algal and cyanobacterial removal",
            "Effective NOM skimming in many source waters",
            "Lower clarifier footprint than conventional sedimentation",
            "Captures low-density particles that sink poorly in conventional clarifiers",
        ],
        "weaknesses": [
            "Higher energy than gravity sedimentation",
            "Float handling requires attention (concentrated sludge/float)",
            "Performance sensitive to coagulation conditions",
            "Not always superior for mineral / high-density solids",
        ],
        "residuals": "DAF float (concentrated, low volume) + filter backwash",
        "lrv_profile": {
            "protozoa": (2.0, 3.0),
            "bacteria": (2.0, 3.0),
            "virus": (1.0, 2.0),
        },
        "operability": "Moderate — pressurisation system, float removal",
        "energy_class": "moderate",
        "chemical_class": "moderate",
        "footprint_class": "moderate",
    },
    "E": {
        "label": "Enhanced Coagulation + Biofiltration",
        "philosophy": (
            "Optimise coagulation for NOM removal, not just turbidity removal. "
            "Follow with biological filtration (BAC) to mineralise biodegradable NOM. "
            "Primary driver: DBP precursor control and organics management."
        ),
        "strengths": [
            "Strong NOM and DBP precursor removal",
            "Biofiltration reduces assimilable organic carbon for distribution",
            "Reduces downstream chemical oxidant demand",
            "Lower DBP formation across distribution system",
        ],
        "weaknesses": [
            "Requires careful coagulation pH control for NOM-targeted removal",
            "BAC requires biological establishment period",
            "More complex chemical programme",
            "Does not address PFAS, arsenic, or inorganic dissolved contaminants",
        ],
        "residuals": "Higher sludge volume (enhanced coagulation generates more sludge) + BAC backwash",
        "lrv_profile": {
            "protozoa": (2.0, 3.0),
            "bacteria": (2.5, 3.5),
            "virus": (1.0, 2.5),
        },
        "operability": "Moderate — biological system management required",
        "energy_class": "low_moderate",
        "chemical_class": "moderate_high",
        "footprint_class": "high",
    },
    "F": {
        "label": "Softening-Led Treatment",
        "philosophy": (
            "Lime or lime + sodium carbonate softening as primary treatment step. "
            "Removes carbonate and non-carbonate hardness. "
            "Requires recarbonation for pH stabilisation."
        ),
        "strengths": [
            "Effective hardness reduction (calcium and magnesium)",
            "pH elevation inactivates some pathogens",
            "Reduces scaling in distribution system",
            "Can improve downstream filtration by precipitation of colloidal matter",
        ],
        "weaknesses": [
            "Very high sludge production (lime sludge is voluminous and poorly dewaterable)",
            "High chemical demand (lime, CO₂ for recarbonation, Na₂CO₃ for non-carbonate hardness)",
            "pH swings require careful control",
            "High sodium introduction if NaOH or Na₂CO₃ used",
            "Complex chemical handling",
        ],
        "residuals": "Lime sludge — HIGH volume, difficult to dewater, may require lagoons",
        "lrv_profile": {
            "protozoa": (1.0, 2.0),
            "bacteria": (2.0, 3.0),
            "virus": (1.0, 2.0),
        },
        "operability": "High complexity — lime slaking, multiple pH control points, sludge handling",
        "energy_class": "moderate",
        "chemical_class": "high",
        "footprint_class": "very_high",
    },
    "G": {
        "label": "Oxidation + Biofiltration / Adsorption Train",
        "philosophy": (
            "Ozone or AOP followed by BAC or GAC. "
            "Primary driver: taste and odour control, trace organics, "
            "or NOM polishing after conventional treatment."
        ),
        "strengths": [
            "Effective MIB, geosmin, and taste/odour compound removal",
            "Broad-spectrum organic oxidation / polishing",
            "Ozone + BAC produces stable, biologically stable effluent",
            "AOP (UV/H₂O₂, O₃/H₂O₂) addresses refractory compounds",
        ],
        "weaknesses": [
            "Ozone generates bromate where bromide present",
            "High energy for ozone generation",
            "Ozone must not be applied before cell removal in cyanobacterial waters",
            "Spent GAC/BAC media requires periodic replacement — significant residuals cost",
            "Requires robust pre-treatment to protect GAC/BAC from fouling",
        ],
        "residuals": "Spent GAC / BAC media (significant cost for regeneration or replacement)",
        "lrv_profile": {
            "protozoa": (1.0, 2.0),  # ozone credits for Cryptosporidium require CT-verified
            "bacteria": (2.0, 3.0),
            "virus": (2.0, 4.0),
        },
        "operability": "High — ozone system management, media monitoring, H₂O₂ if AOP",
        "energy_class": "high",
        "chemical_class": "moderate_high",
        "footprint_class": "moderate",
    },
    "H": {
        "label": "Membrane Barrier System",
        "philosophy": (
            "MF/UF as primary or secondary barrier for particle and pathogen removal. "
            "RO/NF for dissolved contaminant control or advanced purification. "
            "Required where LRV credits, PFAS, TDS, or recycled water context demand it."
        ),
        "strengths": [
            "Very high LRV credit for protozoa and bacteria (MF/UF)",
            "Absolute barrier for particles above membrane pore size",
            "RO/NF removes dissolved contaminants, PFAS, TDS, metals",
            "Compact footprint",
        ],
        "weaknesses": [
            "Membrane concentrate / brine is a major residuals challenge",
            "High energy for RO systems",
            "Fouling and cleaning chemical demand",
            "Membrane replacement cost",
            "Pre-treatment requirements to protect membranes",
        ],
        "residuals": "Membrane concentrate / brine (HIGH concern for PFAS, TDS systems); cleaning waste",
        "lrv_profile": {
            "protozoa": (3.0, 4.0),   # MF/UF validated credit
            "bacteria": (3.0, 4.0),
            "virus": (0.0, 2.0),      # MF/UF limited virus removal; RO higher
        },
        "operability": "High — membrane integrity, CIP systems, concentrate management",
        "energy_class": "high",
        "chemical_class": "moderate_high",
        "footprint_class": "low_moderate",
    },
    "I": {
        "label": "Contaminant-Specific Treatment Train",
        "philosophy": (
            "A specific dissolved contaminant (arsenic, PFAS, nitrate, fluoride, etc.) "
            "governs train selection. The contaminant module determines the core process. "
            "Conventional treatment is typically still required upstream."
        ),
        "strengths": [
            "Targeted removal of the governing contaminant",
            "Can be integrated into or appended to conventional trains",
            "Specific media / processes optimised for the contaminant",
        ],
        "weaknesses": [
            "Typically does not address broad water quality improvements",
            "Residuals often contain concentrated form of the target contaminant",
            "Long-term media/resin management is an ongoing cost and risk",
        ],
        "residuals": "Contaminant-bearing spent media, resin, or concentrate — may require special disposal",
        "lrv_profile": {
            "protozoa": (0.0, 1.0),
            "bacteria": (0.0, 1.0),
            "virus": (0.0, 1.0),
        },
        "operability": "Variable — depends on specific contaminant train",
        "energy_class": "variable",
        "chemical_class": "variable",
        "footprint_class": "low_moderate",
    },
}


@dataclass
class ArchetypeAssessment:
    """Assessment of a single treatment archetype."""
    key: str = ""
    label: str = ""
    viable: bool = True
    exclusion_reasons: list = field(default_factory=list)
    inclusion_rationale: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    archetype_data: dict = field(default_factory=dict)


@dataclass
class ArchetypeSelectionResult:
    """Output of Gate 4."""
    viable_archetypes: list = field(default_factory=list)   # list of ArchetypeAssessment
    excluded_archetypes: list = field(default_factory=list)
    primary_recommendation: str = ""
    recommendation_rationale: str = ""
    requires_advanced_treatment: bool = False
    requires_membrane: bool = False
    ozone_viable: bool = True
    ozone_bromide_warning: bool = False


# ─── Archetype Evaluation Logic ───────────────────────────────────────────────

def _evaluate_archetype_A(inputs: SourceWaterInputs, classification: ClassificationResult) -> ArchetypeAssessment:
    aa = ArchetypeAssessment(key="A", label=ARCHETYPES["A"]["label"],
                             archetype_data=ARCHETYPES["A"])
    if not classification.direct_filtration_eligible:
        aa.viable = False
        aa.exclusion_reasons = classification.direct_filtration_exclusion_reasons
    else:
        aa.inclusion_rationale.append(
            "Source water quality and variability are consistent with direct filtration. "
            "Omitting clarification is justifiable and reduces capital, footprint, and sludge."
        )
    return aa


def _evaluate_archetype_B(inputs: SourceWaterInputs, classification: ClassificationResult) -> ArchetypeAssessment:
    aa = ArchetypeAssessment(key="B", label=ARCHETYPES["B"]["label"],
                             archetype_data=ARCHETYPES["B"])
    excl = []
    incl = []

    if inputs.algae_risk in ["high", "confirmed_bloom"]:
        excl.append(
            "Conventional sedimentation is poorly suited to algal-dominated source waters. "
            "Low-density algal cells are difficult to settle and lead to filter blinding. "
            "DAF (Archetype D) is strongly preferred in algae-risk conditions."
        )

    if inputs.land_constrained:
        aa.flags.append(
            "Conventional sedimentation requires large footprint. "
            "Intensified clarification (Archetype C) may be preferred given land constraint."
        )

    if not excl:
        incl.append("Conventional clarification and filtration is viable and appropriate for this source water.")
    if inputs.turbidity_p95_ntu > 10:
        incl.append(
            f"95th percentile turbidity of {inputs.turbidity_p95_ntu} NTU confirms that "
            f"clarification is required. Direct filtration is not appropriate."
        )

    aa.exclusion_reasons = excl
    aa.inclusion_rationale = incl
    aa.viable = len(excl) == 0
    return aa


def _evaluate_archetype_C(inputs: SourceWaterInputs, classification: ClassificationResult) -> ArchetypeAssessment:
    aa = ArchetypeAssessment(key="C", label=ARCHETYPES["C"]["label"],
                             archetype_data=ARCHETYPES["C"])
    incl = []
    flags = []

    if inputs.land_constrained:
        incl.append(
            "Land constraint identified: intensified clarification provides comparable "
            "solids removal to conventional sedimentation in a significantly smaller footprint."
        )
    if inputs.is_retrofit:
        incl.append(
            "Retrofit context: ballasted or lamella clarification can often be inserted "
            "into existing civil structures to increase hydraulic capacity."
        )
    # Hard cell count limit for high-rate ballasted clarifiers (Densadeg / Actiflo)
    # Above 200,000 cells/mL the ballast/floc system is overwhelmed.
    # This is a technology performance exclusion, not a preference.
    BALLASTED_CELL_LIMIT = 200_000  # cells/mL

    if inputs.algal_cells_per_ml > 0 and inputs.algal_cells_per_ml > BALLASTED_CELL_LIMIT:
        aa.exclusion_reasons = [
            f"EXCLUDED: Algal cell count {inputs.algal_cells_per_ml:,.0f} cells/mL exceeds "
            f"the upper performance limit for high-rate ballasted clarifiers "
            f"(Densadeg / Actiflo upper limit: {BALLASTED_CELL_LIMIT:,} cells/mL). "
            "At this loading the ballast recirculation system is overwhelmed, floc structure "
            "is disrupted, and algal carry-through into filtration is unacceptable. "
            "DAF (Archetype D) is the appropriate clarification technology above this threshold."
        ]
        aa.viable = False
        aa.inclusion_rationale = []
        aa.flags = []
        return aa

    if inputs.algae_risk in ["high", "confirmed_bloom"]:
        flags.append(
            "Intensified clarification (lamella / ballasted) performance degrades above "
            "200,000 cells/mL. Enter algal_cells_per_ml if cell count data is available "
            "to apply the hard exclusion threshold. Consider DAF in preference."
        )

    if not incl:
        incl.append(
            "Intensified clarification is a viable option offering reduced footprint. "
            "Most advantageous where land is constrained or hydraulic capacity is the primary driver."
        )

    aa.inclusion_rationale = incl
    aa.flags = flags
    return aa


def _evaluate_archetype_D(inputs: SourceWaterInputs, classification: ClassificationResult) -> ArchetypeAssessment:
    aa = ArchetypeAssessment(key="D", label=ARCHETYPES["D"]["label"],
                             archetype_data=ARCHETYPES["D"])
    incl = []
    flags = []
    excl = []

    if inputs.algae_risk in ["high", "confirmed_bloom"]:
        incl.append(
            "DAF is the preferred clarification technology for algae-dominated and high-NOM "
            "source waters. Flotation is far more effective than sedimentation for low-density "
            "algal cells and associated organic matter."
        )
    if inputs.algae_risk == "moderate":
        incl.append(
            "Moderate algae risk supports DAF consideration. DAF provides a performance buffer "
            "during bloom events that conventional sedimentation cannot match."
        )
    if inputs.toc_median_mg_l > 8:
        incl.append(
            "High TOC favours DAF: flotation can skim surface-active NOM fractions that "
            "settle poorly in conventional clarifiers."
        )

    if inputs.tds_median_mg_l > 3000:
        flags.append(
            "High TDS can reduce DAF bubble stability and efficiency. "
            "Verify DAF applicability with treatability testing at this salinity."
        )

    if not incl:
        incl.append(
            "DAF is a viable clarification option. Most advantageous for low-density particle "
            "removal, algae, and NOM-rich source waters."
        )

    aa.inclusion_rationale = incl
    aa.flags = flags
    aa.exclusion_reasons = excl
    aa.viable = len(excl) == 0
    return aa


def _evaluate_archetype_E(inputs: SourceWaterInputs, classification: ClassificationResult) -> ArchetypeAssessment:
    aa = ArchetypeAssessment(key="E", label=ARCHETYPES["E"]["label"],
                             archetype_data=ARCHETYPES["E"])
    incl = []
    excl = []
    flags = []

    if classification.primary_constraint == "nom_dbp" or inputs.dbp_concern:
        incl.append(
            "NOM / DBP precursor control is the primary driver: enhanced coagulation "
            "specifically targets NOM removal (not just turbidity). Biofiltration downstream "
            "removes biodegradable NOM produced by coagulation, stabilising the distribution system."
        )
    if inputs.toc_median_mg_l > 8:
        incl.append(
            f"TOC {inputs.toc_median_mg_l} mg/L: at this NOM loading, standard coagulation "
            f"for turbidity alone is insufficient. Enhanced coagulation targets are warranted."
        )
    if inputs.colour_median_hu > 30:
        incl.append(
            f"Colour {inputs.colour_median_hu} HU: high colour indicates humic NOM fraction "
            f"that responds well to enhanced coagulation."
        )

    if inputs.alkalinity_median_mg_l < 30:
        flags.append(
            "Low alkalinity limits the pH depression used in enhanced coagulation — "
            "may require alkalinity supplementation or modified approach."
        )

    if not incl:
        aa.viable = False
        excl.append(
            "Enhanced coagulation + biofiltration is most justified where NOM/DBP control "
            "is a primary treatment driver. Not indicated as primary archetype at this source water quality."
        )

    aa.inclusion_rationale = incl
    aa.exclusion_reasons = excl
    aa.flags = flags
    aa.viable = len(excl) == 0
    return aa


def _evaluate_archetype_F(inputs: SourceWaterInputs, classification: ClassificationResult) -> ArchetypeAssessment:
    aa = ArchetypeAssessment(key="F", label=ARCHETYPES["F"]["label"],
                             archetype_data=ARCHETYPES["F"])
    incl = []
    excl = []

    if inputs.hardness_median_mg_l > 300:
        incl.append(
            f"Hardness {inputs.hardness_median_mg_l} mg/L CaCO₃: lime softening is "
            f"the primary technology for hardness reduction at this level. "
            f"Carbonate and non-carbonate hardness must be distinguished — "
            f"soda ash addition required if non-carbonate hardness is significant."
        )
    elif inputs.hardness_median_mg_l > 150:
        incl.append(
            f"Hardness {inputs.hardness_median_mg_l} mg/L CaCO₃: softening may be warranted "
            f"depending on finished water target and scaling risk. "
            f"Compare full softening vs. partial softening vs. blending strategies."
        )
    else:
        excl.append(
            f"Hardness {inputs.hardness_median_mg_l} mg/L CaCO₃ does not indicate softening "
            f"as a primary treatment requirement."
        )
        aa.viable = False

    if incl:
        aa.flags.append(
            "Softening sludge (lime sludge) is voluminous, poorly dewaterable, "
            "and may require lagoons or significant dewatering infrastructure. "
            "Residuals handling is a major cost driver for softening plants."
        )

    aa.inclusion_rationale = incl
    aa.exclusion_reasons = excl
    return aa


def _evaluate_archetype_G(inputs: SourceWaterInputs, classification: ClassificationResult) -> ArchetypeAssessment:
    aa = ArchetypeAssessment(key="G", label=ARCHETYPES["G"]["label"],
                             archetype_data=ARCHETYPES["G"])
    incl = []
    flags = []
    excl = []

    if inputs.mib_geosmin_issue:
        incl.append(
            "MIB / geosmin confirmed: ozone and BAC/GAC are the most effective treatment "
            "strategy for taste-and-odour control. PAC is a useful event-response tool "
            "but does not provide continuous reliable protection at high cell concentrations."
        )
    if inputs.dbp_concern or inputs.toc_median_mg_l > 8:
        incl.append(
            "High TOC / DBP precursor concern: ozone + BAC provides biologically stable "
            "water and reduces DBP precursor concentration entering disinfection."
        )
    if inputs.troc_concern:
        incl.append(
            "Trace organic concern: AOP (UV/H₂O₂ or O₃/H₂O₂) provides oxidation of "
            "refractory compounds not addressed by standard ozone alone."
        )

    # High catchment risk: ozone is required to meet elevated virus LRV targets
    # Conventional trains (B, C, D) cannot achieve 8 log virus without ozone.
    # Include G as a viable option so it can compete in scoring.
    if inputs.catchment_risk == "very_high":
        incl.append(
            "Very high catchment risk: elevated pathogen LRV targets (8 log virus) cannot be met "
            "by conventional treatment + UV + chlorination alone (maximum ~6.5 log virus). "
            "Ozone provides an additional 2.0–3.5 log virus inactivation at practical Ct values. "
            "Ozone + BAC is required to meet the elevated virus LRV requirement for this source."
        )

    # Ozone bromide warning — calibrated to whether bromide has been measured
    if inputs.bromide_ug_l < 0:
        # Bromide not measured — require measurement before proceeding
        flags.append(
            "⚠ Bromide not measured: bromide data is required before finalising ozone. "
            "If bromide exceeds 50 μg/L, ozone doses above 1 mg/L risk bromate formation "            "above the 10 μg/L ADWG limit. Measure bromide across seasons before detailed design."
        )
    elif inputs.bromide_ug_l > 100:
        flags.append(
            f"⚠ HIGH BROMIDE ({inputs.bromide_ug_l:.0f} μg/L): bromate formation at practical "            f"ozone doses is likely to exceed the 10 μg/L ADWG limit. "            "Bromate suppression is mandatory — pH depression, H₂O₂ co-dosing, or ammonia "            "addition must be incorporated into the ozone system design. "            "Consider whether ozone remains viable at this bromide concentration."
        )
    elif inputs.bromide_ug_l > 50:
        flags.append(
            f"⚠ ELEVATED BROMIDE ({inputs.bromide_ug_l:.0f} μg/L): bromate formation risk is "            f"significant at typical ozone doses. "            "Bromate suppression strategy (pH depression, H₂O₂, ammonia) is required. "            "Confirm bromate compliance in treatability testing before design."
        )
    else:
        flags.append(
            f"Bromide measured at {inputs.bromide_ug_l:.0f} μg/L — below 50 μg/L threshold. "            "Bromate formation at practical ozone doses is unlikely to exceed 10 μg/L ADWG limit "            "but should be verified in pilot or bench-scale testing."
        )

    if inputs.cyanobacteria_confirmed:
        flags.append(
            "⚠ Cyanobacteria confirmed: ozone must NOT be applied before intact cell removal. "
            "Pre-ozonation risks lysing cyanobacterial cells, releasing intracellular toxins "
            "that are far harder to remove than cells. "
            "Sequence: cell removal (DAF or clarification + filtration) THEN ozone/BAC."
        )

    if not incl:
        excl.append(
            "Ozone + biofiltration is most warranted where taste/odour, NOM polishing, "
            "or trace organics are primary treatment drivers. "
            "Not indicated as primary archetype at this source water quality without these drivers."
        )
        aa.viable = False

    aa.inclusion_rationale = incl
    aa.flags = flags
    aa.exclusion_reasons = excl
    aa.viable = len(excl) == 0
    return aa


def _evaluate_archetype_H(inputs: SourceWaterInputs, classification: ClassificationResult) -> ArchetypeAssessment:
    aa = ArchetypeAssessment(key="H", label=ARCHETYPES["H"]["label"],
                             archetype_data=ARCHETYPES["H"])
    incl = []
    flags = []
    excl = []

    if inputs.treatment_objective == "recycled":
        incl.append(
            "Recycled water polishing: membrane barrier is typically mandatory to achieve "
            "required LRV credits and provide a validated independent barrier. "
            "MF/UF provides protozoa and bacteria LRV; RO adds dissolved contaminant control."
        )
    if inputs.pfas_detected:
        incl.append(
            "PFAS detected: RO or NF provides the highest confidence PFAS removal, "
            "particularly for short-chain PFAS that may break through GAC or IX. "
            "However, concentrate management becomes the critical downstream issue."
        )
    if inputs.tds_median_mg_l > 2000 or inputs.source_type == "desalination":
        incl.append(
            f"TDS {inputs.tds_median_mg_l} mg/L: RO is required for TDS reduction to "
            f"potable water standards. Full membrane train with pretreatment is required."
        )
    if inputs.pathogen_lrv_required_protozoa > 4.0:
        incl.append(
            f"High protozoan LRV requirement ({inputs.pathogen_lrv_required_protozoa} log): "
            f"MF/UF provides a validated, independent protozoan barrier that cannot be "
            f"reliably achieved through conventional treatment alone."
        )
    if inputs.arsenic_ug_l > 20:
        incl.append(
            f"Arsenic {inputs.arsenic_ug_l} μg/L: RO provides reliable arsenic removal "
            f"across both As(III) and As(V) species, avoiding speciation uncertainty."
        )

    if incl:
        flags.append(
            "Membrane concentrate / brine disposal must be assessed before finalising "
            "membrane archetype. Where PFAS or arsenic are present, concentrate is a "
            "classified waste stream requiring specific handling, treatment, or off-site management."
        )
        flags.append(
            "Membrane systems require pretreatment to protect membranes. "
            "Conventional treatment upstream is typically required, not replaced."
        )
    else:
        excl.append(
            "Membrane barrier system is not indicated as a primary treatment archetype. "
            "LRV requirements, dissolved contaminant targets, TDS, and recycled water "
            "context do not require a membrane train at this source."
        )
        aa.viable = False

    aa.inclusion_rationale = incl
    aa.flags = flags
    aa.exclusion_reasons = excl
    aa.viable = len(excl) == 0
    return aa


def _evaluate_archetype_I(inputs: SourceWaterInputs, classification: ClassificationResult) -> ArchetypeAssessment:
    aa = ArchetypeAssessment(key="I", label=ARCHETYPES["I"]["label"],
                             archetype_data=ARCHETYPES["I"])
    incl = []
    excl = []

    contaminants = classification.contaminant_modules_required
    if "arsenic" in contaminants:
        incl.append(
            f"Arsenic {inputs.arsenic_ug_l} μg/L: a specific arsenic removal module is required "
            f"and will govern the treatment process selection for dissolved contaminant control. "
            f"See Arsenic module for pathway assessment."
        )
    if "pfas" in contaminants:
        incl.append(
            "PFAS confirmed: a specific PFAS removal pathway is required. "
            "The PFAS module governs selection between GAC, PFAS-selective IX, and RO. "
            "Residuals from all three pathways require explicit downstream management."
        )

    if not incl:
        excl.append(
            "No specific contaminant-specific treatment modules are required at this source water quality. "
            "Conventional or advanced treatment archetypes are appropriate without a dedicated contaminant train."
        )
        aa.viable = False

    aa.inclusion_rationale = incl
    aa.exclusion_reasons = excl
    aa.viable = len(excl) == 0
    return aa


# ─── Gate 4 Master Runner ─────────────────────────────────────────────────────

def run_archetype_selection(inputs: SourceWaterInputs,
                            classification: ClassificationResult) -> ArchetypeSelectionResult:
    result = ArchetypeSelectionResult()

    assessors = {
        "A": _evaluate_archetype_A,
        "B": _evaluate_archetype_B,
        "C": _evaluate_archetype_C,
        "D": _evaluate_archetype_D,
        "E": _evaluate_archetype_E,
        "F": _evaluate_archetype_F,
        "G": _evaluate_archetype_G,
        "H": _evaluate_archetype_H,
        "I": _evaluate_archetype_I,
    }

    for key, fn in assessors.items():
        aa = fn(inputs, classification)
        if aa.viable:
            result.viable_archetypes.append(aa)
        else:
            result.excluded_archetypes.append(aa)

    # Global flags
    result.requires_membrane = any(a.key == "H" for a in result.viable_archetypes)
    result.requires_advanced_treatment = any(a.key in ["G", "H"] for a in result.viable_archetypes)

    # Ozone bromide warning — always flag
    result.ozone_viable = True
    result.ozone_bromide_warning = True  # requires assessment regardless

    # Primary recommendation heuristic
    # Priority: mandatory archetypes first, then constraint-matched, then highest scorer.
    # IMPORTANT: The preferred archetype must address the PRIMARY CONSTRAINT.
    # A high-scoring archetype that does not address the governing constraint
    # is not the right recommendation.
    if result.requires_membrane and inputs.treatment_objective == "recycled":
        result.primary_recommendation = "H"
        result.recommendation_rationale = (
            "Membrane barrier is mandatory for the recycled water treatment objective."
        )
    elif inputs.catchment_risk == "very_high" and "G" in [a.key for a in result.viable_archetypes]:
        # Very high catchment risk requires 8 log virus — only ozone (G) or membrane (H) can meet this.
        # Prefer G (ozone+BAC) unless membrane is already indicated.
        # H may still be preferred if other triggers (PFAS, TDS) are present.
        if result.requires_membrane:
            result.primary_recommendation = "H"
            result.recommendation_rationale = (
                "Very high catchment risk combined with membrane-indicated source conditions: "
                "membrane barrier (MF/UF + RO or NF) is required to meet both the elevated "                "LRV targets (8 log virus) and the dissolved contaminant challenge."
            )
        else:
            result.primary_recommendation = "G"
            result.recommendation_rationale = (
                "Very high catchment risk requires 8 log virus LRV — not achievable by "                "conventional treatment + UV + chlorination alone (~6.5 log virus maximum). "                "Ozone + BAC provides 2.0–3.5 additional log virus inactivation at practical Ct, "                "achieving the required barrier. The ozone system must be designed with "                "verified Ct at minimum temperature, and bromide must be assessed for bromate control."
            )
    elif classification.primary_constraint == "algae_cyanobact":
        result.primary_recommendation = "D"
        result.recommendation_rationale = (
            "DAF-led treatment is the preferred primary archetype where algae and "
            "cyanobacteria are the dominant source water challenge. "
            "DAF provides superior removal of low-density algal cells and associated NOM "
            "compared to conventional sedimentation."
        )
    elif classification.primary_constraint == "nom_dbp":
        result.primary_recommendation = "E"
        result.recommendation_rationale = (
            "Enhanced coagulation + biofiltration targets NOM removal at the coagulation "
            "stage and stabilises the water biologically before disinfection. "
            "This is the appropriate primary philosophy where DBP precursor control is the "
            "governing treatment objective."
        )
    elif classification.primary_constraint == "hardness":
        # Softening is required to address hardness — regardless of its score relative
        # to other archetypes. DAF, conventional etc. do not remove hardness.
        if "F" in [a.key for a in result.viable_archetypes]:
            result.primary_recommendation = "F"
            result.recommendation_rationale = (
                "Softening-led treatment is required where hardness reduction is the primary "
                "objective. DAF, conventional sedimentation, and membrane systems (except RO/NF) "
                "do not reduce hardness. Lime or lime + soda ash softening is the appropriate "
                "primary philosophy. Note: softening generates high-volume lime sludge — "
                "residuals handling is a co-equal design element."
            )
        else:
            # Softening excluded (e.g. moderate hardness) — membrane may be next best
            result.primary_recommendation = "H"
            result.recommendation_rationale = (
                "Hardness is the primary constraint but softening (Archetype F) is not viable "
                "for this configuration. RO/NF membrane is the alternative for hardness reduction."
            )
    elif classification.primary_constraint == "salinity_tds":
        # High TDS / desalination: RO is the only pathway — route to H (membrane)
        result.primary_recommendation = "H"
        result.recommendation_rationale = (
            "High TDS / salinity governs the treatment objective. RO or NF membrane is the "            "only technology capable of dissolved salt reduction to potable water standards. "            "Conventional treatment (coagulation, DAF, filtration) does not remove dissolved TDS. "            "Pretreatment for membrane protection is required. Concentrate disposal is the "            "site-controlling constraint for inland sources."
        )
    elif classification.primary_constraint in ["pfas_troc", "arsenic"]:
        result.primary_recommendation = "I"
        result.recommendation_rationale = (
            "A contaminant-specific treatment train is required for the identified "            "dissolved contaminant challenge. Conventional treatment archetypes alone "
            "are insufficient to achieve the required removal targets."
        )
    elif classification.primary_constraint == "taste_odour":
        result.primary_recommendation = "G"
        result.recommendation_rationale = (
            "Ozone + BAC/GAC is the most effective continuous strategy for "
            "MIB/geosmin taste and odour control. PAC dosing provides event-response "
            "capability but is not reliable as the primary long-term strategy."
        )
    elif classification.primary_constraint in ["iron_manganese"]:
        # Fe/Mn in groundwater — conventional with oxidation is correct, not DAF
        if "B" in [a.key for a in result.viable_archetypes]:
            result.primary_recommendation = "B"
            result.recommendation_rationale = (
                "Iron and manganese removal governs the treatment train. Conventional treatment "
                "with pre-oxidation (aeration, chlorination, or KMnO₄) and filtration is the "
                "established approach. DAF is not the preferred front-end for dissolved Fe/Mn "
                "in groundwater — oxidation and granular filtration are the primary mechanisms."
            )
        else:
            result.primary_recommendation = "A"
            result.recommendation_rationale = (
                "Iron and manganese removal with oxidation and filtration. "
                "See iron/manganese contaminant module for pathway detail."
            )
    elif inputs.land_constrained or inputs.is_retrofit:
        result.primary_recommendation = "C"
        result.recommendation_rationale = (
            "Intensified clarification suits the retrofit or land-constrained context, "
            "providing comparable solids removal to conventional sedimentation in a "
            "significantly smaller footprint."
        )
    elif classification.direct_filtration_eligible:
        result.primary_recommendation = "A"
        result.recommendation_rationale = (
            "Source water quality is consistent with direct filtration. "
            "This is the simplest and most cost-effective option for this source, "
            "provided the source remains within the direct filtration operating envelope."
        )
    else:
        result.primary_recommendation = "B"
        result.recommendation_rationale = (
            "Conventional clarification and filtration is the most appropriate baseline "
            "treatment philosophy for this source water. "
            "It is robust, well-understood, and handles the range of conditions identified."
        )

    return result
