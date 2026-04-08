"""
AquaPoint Reasoning Engine — Gate 5
Residuals and Side-Stream Assessment

Residuals are part of the treatment system, not an afterthought.
For each archetype/train, this module:
- Identifies what residuals are generated
- Characterises volume, handling, dewaterability
- Applies the problem-transfer test
- Flags where residuals drive or constrain treatment selection
"""

from dataclasses import dataclass, field
from .classifier import SourceWaterInputs


# ─── Residual Stream Library ──────────────────────────────────────────────────

RESIDUAL_STREAMS = {
    "clarifier_sludge": {
        "label": "Conventional Clarifier Sludge",
        "volume_class": "high",
        "solids_content": "0.5–2% TS typically; thickens to 4–8%",
        "dewaterability": "Moderate — centrifuge or belt press to 18–25% DS",
        "generation": "Continuous",
        "disposal_options": ["sewer (if consented)", "dewatering → landfill", "beneficial reuse (limited)"],
        "special_considerations": [],
        "biopoint_relevant": True,
    },
    "daf_float": {
        "label": "DAF Float",
        "volume_class": "low_moderate",
        "solids_content": "2–5% TS concentrated float",
        "dewaterability": "Moderate — higher TS than clarifier sludge",
        "generation": "Continuous / intermittent",
        "disposal_options": ["sewer (if consented)", "dewatering → landfill"],
        "special_considerations": [
            "Float contains concentrated algal material — may be odorous",
            "If cyanobacteria present, float may contain toxins — handle carefully",
        ],
        "biopoint_relevant": True,
    },
    "lime_sludge": {
        "label": "Lime / Softening Sludge",
        "volume_class": "very_high",
        "solids_content": "5–15% TS as generated; difficult to thicken further",
        "dewaterability": "Poor — centrifuge to 35–45% DS, but voluminous",
        "generation": "Continuous",
        "disposal_options": ["lagoon storage", "land application (agricultural lime — if suitable)", "landfill"],
        "special_considerations": [
            "Very high volume — often the single largest residuals challenge for softening plants",
            "High pH — corrosive handling",
            "Calcium carbonate sludge can re-dissolve at low pH",
            "Magnesium hydroxide sludge is gelatinous and very difficult to dewater",
        ],
        "biopoint_relevant": True,
    },
    "filter_backwash": {
        "label": "Filter Backwash Water",
        "volume_class": "low_moderate",
        "solids_content": "0.05–0.2% TS — dilute",
        "dewaterability": "Easy after recovery/settling — gravity thickening effective",
        "generation": "Intermittent (every 24–72 hours per filter)",
        "disposal_options": ["recycle to inlet (if consented — check pathogens)", "DAF recovery", "sewer"],
        "special_considerations": [
            "Recycling backwash can accumulate Cryptosporidium if not managed carefully",
            "Recycle should go ahead of coagulation, not after filtration",
        ],
        "biopoint_relevant": False,
    },
    "spent_gac_bac": {
        "label": "Spent GAC / BAC Media",
        "volume_class": "low",
        "solids_content": "Solid media — mass-based, not slurry",
        "dewaterability": "N/A — solid media handling",
        "generation": "Periodic (every 5–15 years for GAC; 1–5 years for PAC)",
        "disposal_options": ["thermal reactivation (off-site)", "landfill (if not PFAS-bearing)", "incineration"],
        "special_considerations": [
            "If PFAS-impacted source water, spent GAC is a PFAS-bearing waste — classified disposal required",
            "Regeneration returns some carbon to use but changes performance characteristics",
            "Long replacement intervals mean significant one-off cost events",
        ],
        "biopoint_relevant": False,
    },
    "spent_ix_resin": {
        "label": "Spent Ion Exchange Resin",
        "volume_class": "low",
        "solids_content": "Solid resin beads",
        "dewaterability": "N/A — solid handling",
        "generation": "Periodic or with regeneration brine",
        "disposal_options": ["regeneration in-situ (brine then waste brine handling)", "off-site disposal"],
        "special_considerations": [
            "PFAS-selective IX resin: spent resin or brine is a highly concentrated PFAS stream",
            "Brine from PFAS-IX requires high-temperature treatment, incineration, or specialist disposal",
            "Non-regenerable PFAS resins: classified waste at end of life",
        ],
        "biopoint_relevant": False,
    },
    "arsenic_bearing_media": {
        "label": "Arsenic-Bearing Spent Media (GFH, Fe-oxide)",
        "volume_class": "low",
        "solids_content": "Solid media with adsorbed arsenic",
        "dewaterability": "N/A — solid handling",
        "generation": "Periodic (2–5 year media life)",
        "disposal_options": ["classified waste disposal (arsenic-bearing)", "stabilisation + landfill"],
        "special_considerations": [
            "Spent media is classified as arsenic-bearing waste in most jurisdictions",
            "Cannot be landfilled without stabilisation / encapsulation",
            "Leachate from spent media landfill is a risk",
            "Confirm waste classification with regulator before specifying process",
        ],
        "biopoint_relevant": False,
    },
    "membrane_concentrate_ro": {
        "label": "RO / NF Membrane Concentrate (Brine)",
        "volume_class": "high",
        "solids_content": "Dissolved — not filterable; high TDS",
        "dewaterability": "Not applicable — liquid concentrate",
        "generation": "Continuous (typically 15–25% of feed flow)",
        "disposal_options": [
            "surface water discharge (requires environmental licence — difficult)",
            "sewer (if consented — TDS limits apply)",
            "deep well injection (geological dependent — not common in Australia)",
            "evaporation pond (arid regions)",
            "ZLD systems (very high capital)",
        ],
        "special_considerations": [
            "Concentrate concentrates ALL dissolved contaminants: PFAS, arsenic, TDS, heavy metals",
            "If PFAS present in feed, concentrate is a classified PFAS waste",
            "Discharge to surface water typically requires dilution factor assessment and environmental approval",
            "Concentrate disposal is often the most complex and costly aspect of RO systems",
        ],
        "biopoint_relevant": False,
    },
    "membrane_cleaning_waste": {
        "label": "Membrane CIP / Cleaning Waste",
        "volume_class": "low",
        "solids_content": "Variable — acid, caustic, biocide wash",
        "dewaterability": "N/A — liquid, pH-adjusted before disposal",
        "generation": "Intermittent (weeks to months)",
        "disposal_options": ["sewer after pH adjustment", "neutralisation and sewer"],
        "special_considerations": [
            "CIP chemicals must be pH-neutralised before discharge",
            "If PFAS-impacted system, CIP waste may also carry PFAS",
        ],
        "biopoint_relevant": False,
    },
    "pfas_concentrate": {
        "label": "PFAS-Bearing Residual Stream",
        "volume_class": "variable",
        "solids_content": "Depends on pathway (spent media vs. liquid concentrate)",
        "dewaterability": "Variable",
        "generation": "Continuous (concentrate) or periodic (spent media)",
        "disposal_options": [
            "High-temperature incineration (>850°C for PFAS destruction)",
            "Off-site classified waste management",
            "Specialist electrochemical treatment (emerging)",
        ],
        "special_considerations": [
            "⚠ PFAS removal DOES NOT destroy PFAS — it transfers it to a concentrated residual",
            "All PFAS treatment creates a concentrated PFAS waste stream",
            "Destruction requires high-temperature incineration or specialist technology",
            "This is a critical decision — confirm residuals handling pathway before committing to PFAS treatment",
        ],
        "biopoint_relevant": False,
    },
    "pac_slurry": {
        "label": "Powdered Activated Carbon (PAC) Sludge",
        "volume_class": "low_moderate",
        "solids_content": "Mixed with clarifier sludge — dilute carbon slurry",
        "dewaterability": "Moderate — carbon in sludge can hinder dewatering",
        "generation": "Intermittent (event-based) or seasonal",
        "disposal_options": ["dewater with clarifier sludge", "landfill"],
        "special_considerations": [
            "If source water contains PFAS, PAC sludge may be PFAS-bearing",
            "PAC affects sludge colour and may affect land application options",
        ],
        "biopoint_relevant": True,
    },
}

# ─── Archetype Residuals Mapping ──────────────────────────────────────────────

ARCHETYPE_RESIDUALS = {
    "A": ["filter_backwash"],
    "B": ["clarifier_sludge", "filter_backwash"],
    "C": ["clarifier_sludge", "filter_backwash"],
    "D": ["daf_float", "filter_backwash"],
    "E": ["clarifier_sludge", "filter_backwash", "spent_gac_bac"],
    "F": ["lime_sludge", "filter_backwash"],
    "G": ["clarifier_sludge", "filter_backwash", "spent_gac_bac"],
    "H": ["membrane_concentrate_ro", "membrane_cleaning_waste", "filter_backwash"],
    "I": [],  # determined by contaminant module
}

CONTAMINANT_MODULE_RESIDUALS = {
    "arsenic":     ["arsenic_bearing_media", "clarifier_sludge"],
    "pfas":        ["pfas_concentrate", "spent_gac_bac", "spent_ix_resin"],
    "taste_odour": ["spent_gac_bac", "pac_slurry"],
    "cyanotoxins": ["daf_float"],
    "algae":       ["daf_float"],
    "iron_manganese": ["clarifier_sludge", "filter_backwash"],
    "lrv_advanced": ["membrane_concentrate_ro", "membrane_cleaning_waste"],
}


@dataclass
class ResidualsResult:
    """Residuals assessment for a treatment archetype."""
    archetype_key: str = ""
    residual_streams: list = field(default_factory=list)   # list of stream keys
    stream_details: dict = field(default_factory=dict)     # key → RESIDUAL_STREAMS entry
    problem_transfer_flags: list = field(default_factory=list)
    biopoint_handoff_required: bool = False
    classified_waste_streams: list = field(default_factory=list)
    complexity_rating: str = ""   # low / moderate / high / very_high
    key_messages: list = field(default_factory=list)


@dataclass
class ResidualsComparisonResult:
    """Comparison of residuals across all viable archetypes."""
    archetype_assessments: dict = field(default_factory=dict)  # archetype_key → ResidualsResult
    most_complex_residuals: str = ""
    simplest_residuals: str = ""
    problem_transfer_warnings: list = field(default_factory=list)
    biopoint_scope: list = field(default_factory=list)


# ─── Problem Transfer Test ────────────────────────────────────────────────────

def _apply_problem_transfer_test(inputs: SourceWaterInputs,
                                  stream_keys: list) -> list:
    """
    Test whether any treatment option merely transfers a contaminant
    into a more concentrated residual stream rather than removing it.
    Returns list of flags.
    """
    flags = []

    if "pfas_concentrate" in stream_keys or ("membrane_concentrate_ro" in stream_keys and inputs.pfas_detected):
        flags.append(
            "⚠ PROBLEM TRANSFER — PFAS: Membrane or adsorption treatment does not destroy PFAS. "
            "It concentrates PFAS into a smaller-volume residual stream (spent media or concentrate) "
            "that must be destroyed (high-temperature incineration) or managed as a classified waste. "
            "Confirm destruction/disposal pathway before committing to this treatment train."
        )

    if "arsenic_bearing_media" in stream_keys:
        flags.append(
            "⚠ PROBLEM TRANSFER — ARSENIC: Iron-based adsorption media removes arsenic from water "
            "but concentrates it in the spent media, which is an arsenic-bearing classified waste. "
            "Disposal requires stabilisation and regulated landfill or classified waste management."
        )

    if "daf_float" in stream_keys and inputs.cyanobacteria_confirmed:
        flags.append(
            "⚠ PROBLEM TRANSFER — CYANOTOXINS IN FLOAT: DAF float will contain concentrated "
            "cyanobacterial cells and associated intracellular toxins. "
            "Float handling, storage, and disposal must account for toxin content. "
            "Avoid float recycle to inlet without assessment."
        )

    if "membrane_concentrate_ro" in stream_keys and inputs.tds_median_mg_l > 1000:
        flags.append(
            "⚠ CONCENTRATE DISPOSAL: RO concentrate contains all rejected dissolved solids at "
            "elevated concentration. Discharge to surface water requires environmental licensing. "
            "In water-scarce regions, evaporation or ZLD may be required — significantly increasing cost."
        )

    if "lime_sludge" in stream_keys:
        flags.append(
            "⚠ SOFTENING SLUDGE BURDEN: Lime softening generates very high volumes of sludge "
            "relative to throughput. This is a primary cost and operability driver — "
            "land for lagoons or significant dewatering infrastructure is required. "
            "Do not underestimate this residuals burden in cost assessment."
        )

    return flags


# ─── Residuals Complexity Rating ─────────────────────────────────────────────

def _rate_complexity(stream_keys: list, inputs: SourceWaterInputs) -> str:
    score = 0
    complexity_map = {
        "filter_backwash": 1,
        "pac_slurry": 1,
        "daf_float": 2,
        "clarifier_sludge": 2,
        "spent_gac_bac": 3,
        "spent_ix_resin": 4,
        "arsenic_bearing_media": 4,
        "membrane_cleaning_waste": 2,
        "lime_sludge": 4,
        "membrane_concentrate_ro": 4,
        "pfas_concentrate": 5,
    }
    for key in stream_keys:
        score += complexity_map.get(key, 1)

    # Modifier for contaminants
    if inputs.pfas_detected: score += 2
    if inputs.arsenic_ug_l > 10: score += 2
    if inputs.cyanobacteria_confirmed: score += 1

    if score <= 3: return "low"
    elif score <= 6: return "moderate"
    elif score <= 10: return "high"
    else: return "very_high"


# ─── Single Archetype Residuals Assessment ───────────────────────────────────

def assess_archetype_residuals(archetype_key: str, inputs: SourceWaterInputs,
                                contaminant_modules: list = None) -> ResidualsResult:
    result = ResidualsResult(archetype_key=archetype_key)

    streams = list(ARCHETYPE_RESIDUALS.get(archetype_key, []))

    # Add contaminant module residuals
    if contaminant_modules:
        for module in contaminant_modules:
            for stream in CONTAMINANT_MODULE_RESIDUALS.get(module, []):
                if stream not in streams:
                    streams.append(stream)

    result.residual_streams = streams
    result.stream_details = {k: RESIDUAL_STREAMS[k] for k in streams if k in RESIDUAL_STREAMS}

    # Problem transfer test
    result.problem_transfer_flags = _apply_problem_transfer_test(inputs, streams)

    # Classified wastes
    classified = []
    if "arsenic_bearing_media" in streams:
        classified.append("Arsenic-bearing spent media — classified waste in most jurisdictions")
    if "pfas_concentrate" in streams or ("spent_gac_bac" in streams and inputs.pfas_detected):
        classified.append("PFAS-bearing residual — classified waste requiring specialist disposal or destruction")
    if "membrane_concentrate_ro" in streams and inputs.pfas_detected:
        classified.append("RO concentrate containing PFAS — classified waste")
    if "daf_float" in streams and inputs.cyanotoxin_detected:
        classified.append("DAF float with cyanotoxin content — handle with caution")

    result.classified_waste_streams = classified
    result.biopoint_handoff_required = any(
        RESIDUAL_STREAMS.get(k, {}).get("biopoint_relevant", False) for k in streams
    )
    result.complexity_rating = _rate_complexity(streams, inputs)

    # Key messages
    if result.complexity_rating in ["high", "very_high"]:
        result.key_messages.append(
            f"Residuals complexity is {result.complexity_rating.upper()}. "
            "Residuals handling should be treated as a co-equal design element, "
            "not a post-selection detail."
        )
    if result.biopoint_handoff_required:
        result.key_messages.append(
            "Sludge management scope should be passed to BioPoint for dewatering, "
            "disposal pathway, and resource recovery assessment."
        )

    return result


# ─── Comparison Across All Archetypes ────────────────────────────────────────

def compare_residuals(viable_archetype_keys: list, inputs: SourceWaterInputs,
                       contaminant_modules: list = None) -> ResidualsComparisonResult:
    result = ResidualsComparisonResult()

    complexity_order = {"low": 1, "moderate": 2, "high": 3, "very_high": 4}

    for key in viable_archetype_keys:
        assessment = assess_archetype_residuals(key, inputs, contaminant_modules)
        result.archetype_assessments[key] = assessment

        for flag in assessment.problem_transfer_flags:
            if flag not in result.problem_transfer_warnings:
                result.problem_transfer_warnings.append(flag)

        if assessment.biopoint_handoff_required and key not in result.biopoint_scope:
            result.biopoint_scope.append(key)

    # Rank by complexity
    if result.archetype_assessments:
        sorted_by_complexity = sorted(
            result.archetype_assessments.items(),
            key=lambda x: complexity_order.get(x[1].complexity_rating, 2)
        )
        result.simplest_residuals = sorted_by_complexity[0][0]
        result.most_complex_residuals = sorted_by_complexity[-1][0]

    return result
