"""
AquaPoint Reasoning Engine — Gate 1 & 2
Source Classification and Primary Controlling Constraint Identification

Gate 1: Classify source type
Gate 2: Identify primary and secondary controlling constraints
"""

from dataclasses import dataclass, field
from typing import Optional


# ─── Source Types ─────────────────────────────────────────────────────────────

SOURCE_TYPES = {
    "river":        "Surface water — river or stream (variable, event-driven)",
    "reservoir":    "Surface water — reservoir or lake (buffered, stratifiable)",
    "groundwater":  "Groundwater — bore or aquifer (stable, dissolved chemistry dominated)",
    "blended":      "Blended or conjunctive supply (multiple source characteristics)",
    "recycled":     "Recycled water polishing (advanced barrier, LRV-driven)",
    "desalination": "Desalination / high-salinity source (TDS-dominated, RO-led)",
}

# ─── Controlling Constraint Taxonomy ─────────────────────────────────────────

CONSTRAINTS = {
    "solids_events":    "Solids / turbidity / event-driven variability",
    "nom_dbp":          "NOM / TOC / colour / DBP precursor control",
    "algae_cyanobact":  "Algae / cyanobacteria / taste and odour / toxin risk",
    "hardness":         "Hardness / mineral control (calcium, magnesium)",
    "low_alkalinity":   "Low alkalinity / pH instability / corrosivity",
    "pathogen_lrv":     "Pathogen barrier (LRV deficit — protozoa, virus, bacteria)",
    "arsenic":          "Arsenic / metals / metalloids",
    "pfas_troc":        "PFAS / trace organic contaminants",
    "salinity_tds":     "Dissolved salts / TDS / salinity",
    "iron_manganese":   "Iron and manganese (aesthetic and operational)",
    "residuals":        "Residuals or waste handling as primary system constraint",
    "taste_odour":      "Taste and odour (MIB / geosmin / anthropogenic)",
    "cyanotoxins":      "Cyanotoxins (microcystin, cylindrospermopsin, saxitoxin)",
}

# ─── Threshold Logic for Auto-Classification ─────────────────────────────────

@dataclass
class SourceWaterInputs:
    """Structured source water characterisation for reasoning engine."""
    source_type: str = "river"

    # Turbidity
    turbidity_median_ntu: float = 5.0
    turbidity_p95_ntu: float = 20.0
    turbidity_p99_ntu: float = 80.0
    turbidity_event_max_ntu: Optional[float] = None

    # Organics / NOM
    toc_median_mg_l: float = 5.0
    toc_p95_mg_l: float = 10.0
    colour_median_hu: float = 15.0
    uv254_median_cm: Optional[float] = None          # abs units if measured
    dbp_concern: bool = False                         # operator flag

    # Algae
    algae_risk: str = "low"                          # low / moderate / high / confirmed_bloom
    cyanobacteria_confirmed: bool = False
    cyanotoxin_detected: bool = False
    mib_geosmin_issue: bool = False
    algal_cells_per_ml: float = 0.0                  # peak / adverse cell count (cells/mL)
                                                      # 0 = not measured / use algae_risk qualitative
                                                      # Densadeg/Actiflo upper limit: 200,000 cells/mL

    # Inorganics
    hardness_median_mg_l: float = 150.0
    alkalinity_median_mg_l: float = 80.0
    iron_median_mg_l: float = 0.1
    manganese_median_mg_l: float = 0.02
    arsenic_ug_l: float = 0.0
    tds_median_mg_l: float = 300.0
    ph_median: float = 7.5
    ph_min: float = 7.0

    # Bromide (for ozone bromate risk assessment)
    bromide_ug_l: float = -1.0          # -1 = not measured / unknown; 0+ = measured value

    # Ammonia (for disinfection doctrine — breakpoint chlorination, Mn pre-oxidation conflict)
    ammonia_mg_l_nh3n: float = 0.0      # NH3-N median mg/L; 0 = not detected / not measured

    # PFAS / TrOC
    pfas_detected: bool = False
    pfas_concentration_ng_l: float = 0.0
    troc_concern: bool = False

    # Pathogen / LRV context
    catchment_risk: str = "moderate"                 # low / moderate / high / very_high
    # Set to -1 to use framework-derived targets (recommended).
    # Set to a positive value ONLY to explicitly override the framework target.
    pathogen_lrv_required_protozoa: float = -1.0     # -1 = use framework target
    pathogen_lrv_required_bacteria: float = -1.0
    pathogen_lrv_required_virus: float = -1.0

    # Operational context
    is_retrofit: bool = False
    land_constrained: bool = False
    remote_operation: bool = False
    design_flow_ML_d: float = 10.0
    treatment_objective: str = "potable"             # potable / recycled / industrial

    # Variability descriptor
    variability_class: str = "moderate"              # low / moderate / high / extreme


@dataclass
class ClassificationResult:
    """Output of Gate 1 + Gate 2."""
    source_type: str = ""
    source_description: str = ""
    variability_class: str = ""

    primary_constraint: str = ""
    primary_constraint_description: str = ""
    secondary_constraints: list = field(default_factory=list)

    governing_conditions: list = field(default_factory=list)
    direct_filtration_eligible: bool = False
    direct_filtration_exclusion_reasons: list = field(default_factory=list)

    contaminant_modules_required: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# ─── Gate 1: Source Classification ───────────────────────────────────────────

def classify_source(inputs: SourceWaterInputs) -> str:
    """Return source type key — validated against known types."""
    if inputs.source_type in SOURCE_TYPES:
        return inputs.source_type
    return "river"  # safe default


# ─── Gate 2: Primary Controlling Constraint ───────────────────────────────────

def _score_constraints(inputs: SourceWaterInputs) -> dict:
    """
    Score each constraint category 0–10 based on input parameters.
    Higher = more dominant.
    """
    scores = {}

    # Solids / events
    sol = 0
    if inputs.turbidity_p95_ntu > 50: sol += 3
    elif inputs.turbidity_p95_ntu > 20: sol += 2
    elif inputs.turbidity_p95_ntu > 10: sol += 1
    if inputs.turbidity_p99_ntu and inputs.turbidity_p99_ntu > 100: sol += 3
    elif inputs.turbidity_p99_ntu and inputs.turbidity_p99_ntu > 50: sol += 2
    if inputs.turbidity_event_max_ntu and inputs.turbidity_event_max_ntu > 500: sol += 2
    if inputs.source_type in ["river"]: sol += 1
    # Stable groundwater with low median turbidity: reduce solids_events score
    # Default p95/p99 values inflate this constraint for GW sources that are not event-driven
    if inputs.source_type == "groundwater" and inputs.turbidity_median_ntu < 5:
        sol = max(0, sol - 2)
    scores["solids_events"] = min(sol, 10)

    # NOM / DBP
    nom = 0
    if inputs.toc_median_mg_l > 15: nom += 4
    elif inputs.toc_median_mg_l > 8: nom += 3
    elif inputs.toc_median_mg_l > 5: nom += 2
    elif inputs.toc_median_mg_l > 3: nom += 1
    if inputs.colour_median_hu > 50: nom += 3
    elif inputs.colour_median_hu > 20: nom += 2
    elif inputs.colour_median_hu > 10: nom += 1
    if inputs.dbp_concern: nom += 2
    if inputs.uv254_median_cm and inputs.uv254_median_cm > 0.2: nom += 1
    scores["nom_dbp"] = min(nom, 10)

    # Algae / cyanobacteria
    # When cyanobacteria is confirmed, this constraint MUST dominate solids_events
    # (turbidity variability), because the treatment response is fundamentally
    # different — DAF + cell-removal-before-ozone — not just more clarification.
    alg = 0
    alg_risk_map = {"low": 0, "moderate": 2, "high": 4, "confirmed_bloom": 6}
    alg += alg_risk_map.get(inputs.algae_risk, 0)
    if inputs.cyanobacteria_confirmed: alg += 4   # ensures dominance over solids_events
    if inputs.cyanotoxin_detected: alg += 2
    if inputs.mib_geosmin_issue: alg += 1
    scores["algae_cyanobact"] = min(alg, 10)

    # Taste and odour (can overlap with algae)
    # mib_geosmin_issue is a confirmed operational problem — it must win over
    # general NOM/DBP concern because ozone+BAC is the only reliable continuous fix.
    # Score decisively above nom_dbp when confirmed (8 vs max 7 for NOM alone).
    tao = 0
    if inputs.mib_geosmin_issue: tao += 8
    if inputs.algae_risk in ["high", "confirmed_bloom"]: tao += 2
    scores["taste_odour"] = min(tao, 10)

    # Cyanotoxins (specific)
    cyt = 0
    if inputs.cyanotoxin_detected: cyt += 8
    elif inputs.cyanobacteria_confirmed: cyt += 4
    elif inputs.algae_risk in ["high", "confirmed_bloom"]: cyt += 2
    scores["cyanotoxins"] = min(cyt, 10)

    # Hardness
    hard = 0
    if inputs.hardness_median_mg_l > 400: hard += 7
    elif inputs.hardness_median_mg_l > 300: hard += 5
    elif inputs.hardness_median_mg_l > 250: hard += 3
    elif inputs.hardness_median_mg_l > 150: hard += 1
    # Groundwater and blended sources: hardness is a more significant treatment driver
    # than for surface water where turbidity/NOM dominate
    if inputs.source_type in ["groundwater", "blended"] and inputs.hardness_median_mg_l > 200:
        hard += 2
    scores["hardness"] = min(hard, 10)

    # Low alkalinity
    alk = 0
    if inputs.alkalinity_median_mg_l < 20: alk += 5
    elif inputs.alkalinity_median_mg_l < 50: alk += 3
    elif inputs.alkalinity_median_mg_l < 80: alk += 1
    if inputs.ph_min < 6.5: alk += 3
    elif inputs.ph_min < 7.0: alk += 1
    scores["low_alkalinity"] = min(alk, 10)

    # Iron and manganese
    fem = 0
    if inputs.iron_median_mg_l > 2.0: fem += 4
    elif inputs.iron_median_mg_l > 0.5: fem += 2
    elif inputs.iron_median_mg_l > 0.3: fem += 1
    if inputs.manganese_median_mg_l > 0.3: fem += 3
    elif inputs.manganese_median_mg_l > 0.1: fem += 2
    elif inputs.manganese_median_mg_l > 0.05: fem += 1
    scores["iron_manganese"] = min(fem, 10)

    # Arsenic
    ars = 0
    if inputs.arsenic_ug_l > 50: ars += 8
    elif inputs.arsenic_ug_l > 10: ars += 6
    elif inputs.arsenic_ug_l > 7: ars += 4
    elif inputs.arsenic_ug_l > 0: ars += 2
    scores["arsenic"] = min(ars, 10)

    # PFAS / TrOC
    pfas = 0
    if inputs.pfas_detected:
        if inputs.pfas_concentration_ng_l > 100: pfas += 8
        elif inputs.pfas_concentration_ng_l > 20: pfas += 6
        elif inputs.pfas_concentration_ng_l > 0: pfas += 4
        else: pfas += 3  # detected but unquantified
    if inputs.troc_concern: pfas += 3
    scores["pfas_troc"] = min(pfas, 10)

    # Salinity / TDS
    sal = 0
    if inputs.tds_median_mg_l > 5000: sal += 8
    elif inputs.tds_median_mg_l > 2000: sal += 6
    elif inputs.tds_median_mg_l > 1000: sal += 4
    elif inputs.tds_median_mg_l > 600: sal += 2
    if inputs.source_type == "desalination": sal += 3
    scores["salinity_tds"] = min(sal, 10)

    # Pathogen LRV
    lrv = 0
    if inputs.treatment_objective == "recycled": lrv += 5
    if inputs.catchment_risk == "very_high": lrv += 4
    elif inputs.catchment_risk == "high": lrv += 2
    elif inputs.catchment_risk == "moderate": lrv += 1
    scores["pathogen_lrv"] = min(lrv, 10)

    return scores


def identify_constraints(inputs: SourceWaterInputs) -> tuple:
    """
    Return (primary_constraint, secondary_constraints[]) based on scored ranking.
    """
    scores = _score_constraints(inputs)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    primary_score = ranked[0][1]

    # If all constraints score 0 (very clean/simple source), default to solids_events
    # as the primary driver — avoids alphabetically-arbitrary tie-breaking that can
    # route clean groundwater to DAF or other inappropriate archetypes.
    if primary_score == 0:
        primary = "solids_events"
    else:
        primary = ranked[0][0]

    # Secondary: any other constraint scoring >= 3 or within 3 points of primary
    secondary = [
        k for k, v in ranked[1:]
        if v >= 3 or (primary_score > 0 and v >= primary_score - 3)
    ]
    # Cap at 4 secondary constraints for clarity
    secondary = secondary[:4]

    return primary, secondary


# ─── Governing Conditions Assessment ─────────────────────────────────────────

def assess_governing_conditions(inputs: SourceWaterInputs) -> list:
    """
    Identify which conditions actually govern design (not average conditions).
    Returns list of governing condition descriptors.
    """
    conditions = []

    turb_ratio = inputs.turbidity_p99_ntu / max(inputs.turbidity_median_ntu, 0.1)
    if turb_ratio > 20:
        conditions.append(
            f"Extreme turbidity variability (median {inputs.turbidity_median_ntu} NTU → "
            f"99th pctile {inputs.turbidity_p99_ntu} NTU, ratio {turb_ratio:.0f}×): "
            f"event conditions likely govern front-end solids removal design."
        )
    elif turb_ratio > 5:
        conditions.append(
            f"High turbidity variability (median {inputs.turbidity_median_ntu} NTU → "
            f"99th pctile {inputs.turbidity_p99_ntu} NTU, ratio {turb_ratio:.0f}×): "
            f"95th pctile conditions are likely design-governing."
        )

    if inputs.toc_p95_mg_l > inputs.toc_median_mg_l * 1.5:
        conditions.append(
            f"TOC increases significantly at high flow (median {inputs.toc_median_mg_l} → "
            f"P95 {inputs.toc_p95_mg_l} mg/L): coagulant demand and DBP precursor load "
            f"will vary significantly. Design coagulation for peak NOM, not average."
        )

    if inputs.algae_risk in ["high", "confirmed_bloom"]:
        conditions.append(
            "Algal bloom conditions represent a distinct operational mode, not just elevated baseline: "
            "front-end treatment philosophy, chemical programme, and off-take management "
            "must be evaluated specifically for bloom conditions."
        )

    if inputs.cyanobacteria_confirmed:
        conditions.append(
            "Cyanobacteria confirmed: cell integrity during treatment is a critical design constraint. "
            "Pre-oxidation before cell removal risks lysing cells and releasing intracellular toxins. "
            "Cell removal must precede oxidative treatment in the train sequence."
        )

    if inputs.alkalinity_median_mg_l < 50:
        conditions.append(
            f"Low alkalinity ({inputs.alkalinity_median_mg_l} mg/L CaCO₃) limits coagulation pH buffer: "
            f"coagulant dose and pH correction must be co-designed. Alkalinity supplementation "
            f"(lime or NaHCO₃) may be required to achieve adequate coagulation."
        )

    if inputs.turbidity_event_max_ntu and inputs.turbidity_event_max_ntu > 500:
        conditions.append(
            f"Extreme turbidity events recorded (max {inputs.turbidity_event_max_ntu} NTU): "
            f"plant must either handle these loads or have a defined source management "
            f"strategy (storage, intake management, bypass). This may be the single most "
            f"important design-governing condition."
        )

    if inputs.source_type == "river" and inputs.variability_class in ["high", "extreme"]:
        conditions.append(
            "High-variability river source: average-based design will be inadequate. "
            "Treatment system must perform across the full variability envelope, "
            "not just at median or design-day conditions."
        )

    return conditions


# ─── Direct Filtration Eligibility ───────────────────────────────────────────

def assess_direct_filtration(inputs: SourceWaterInputs) -> tuple:
    """
    Assess whether direct filtration is eligible.
    Returns (eligible: bool, exclusion_reasons: list).
    Direct filtration is OPT-IN ONLY — requires positive evidence of suitability.
    """
    exclusions = []

    if inputs.turbidity_p95_ntu > 5:
        exclusions.append(
            f"95th percentile turbidity {inputs.turbidity_p95_ntu} NTU exceeds direct "
            f"filtration threshold (~5 NTU): clarification required for reliable filter performance."
        )

    if inputs.turbidity_event_max_ntu and inputs.turbidity_event_max_ntu > 20:
        exclusions.append(
            f"Recorded turbidity events up to {inputs.turbidity_event_max_ntu} NTU: "
            f"filter loading at these conditions would compromise performance and filter run length."
        )

    if inputs.toc_median_mg_l > 5:
        exclusions.append(
            f"TOC {inputs.toc_median_mg_l} mg/L: direct filtration does not provide adequate "
            f"NOM removal for DBP precursor control at this loading without enhanced coagulation "
            f"and clarification."
        )

    if inputs.algae_risk in ["moderate", "high", "confirmed_bloom"]:
        exclusions.append(
            f"Algae risk ({inputs.algae_risk}): algal cells and associated NOM rapidly blind "
            f"direct filtration systems. Clarification required."
        )

    if inputs.colour_median_hu > 15:
        exclusions.append(
            f"Colour {inputs.colour_median_hu} HU: high colour indicates NOM loading incompatible "
            f"with direct filtration without upstream clarification."
        )

    if inputs.source_type == "river" and inputs.variability_class in ["high", "extreme"]:
        exclusions.append(
            "High-variability river source: direct filtration requires stable, consistently "
            "low-turbidity feed that this source cannot reliably provide."
        )

    if inputs.cyanobacteria_confirmed:
        exclusions.append(
            "Cyanobacteria confirmed: direct filtration cannot reliably remove cyanobacterial "
            "cells and risks filter breakthrough during bloom events."
        )

    # ── New critical exclusions ───────────────────────────────────────────────

    if inputs.alkalinity_median_mg_l < 40:
        exclusions.append(
            f"Low alkalinity ({inputs.alkalinity_median_mg_l} mg/L CaCO₃): insufficient pH buffer "
            f"for stable coagulation. Direct filtration requires at least 40 mg/L alkalinity "
            f"to maintain coagulation pH control without upstream pH correction infrastructure. "
            f"Alkalinity supplementation and full coagulation pH management require clarification stage."
        )

    if inputs.ph_min < 6.5:
        exclusions.append(
            f"Minimum pH {inputs.ph_min}: coagulation is unreliable below pH 6.5. "
            f"Alum is ineffective and ferric coagulants require careful control. "
            f"A clarification stage with pH correction is required before filtration."
        )

    if inputs.iron_median_mg_l > 0.5 and inputs.source_type == "groundwater":
        exclusions.append(
            f"Dissolved iron {inputs.iron_median_mg_l} mg/L in groundwater: dissolved Fe²⁺ oxidises "
            f"on the filter medium, causing rapid filter blinding and unworkable run times. "
            f"Pre-oxidation and clarification are required before filtration. "
            f"Direct filtration is not viable for this source."
        )

    if inputs.manganese_median_mg_l > 0.1 and inputs.source_type == "groundwater":
        exclusions.append(
            f"Dissolved manganese {inputs.manganese_median_mg_l} mg/L in groundwater: dissolved Mn²⁺ "
            f"deposits as MnO₂ on filter media, causing head loss accumulation and shortened run times. "
            f"Pre-oxidation and dedicated manganese removal are required before granular filtration."
        )

    eligible = len(exclusions) == 0
    return eligible, exclusions


# ─── Contaminant Module Triggers ─────────────────────────────────────────────

def identify_contaminant_modules(inputs: SourceWaterInputs) -> list:
    """Return list of contaminant-specific module keys that must be activated."""
    modules = []

    if inputs.arsenic_ug_l > 7:
        modules.append("arsenic")

    if inputs.pfas_detected or inputs.pfas_concentration_ng_l > 0:
        modules.append("pfas")

    if inputs.mib_geosmin_issue:
        modules.append("taste_odour")

    if inputs.cyanotoxin_detected or inputs.cyanobacteria_confirmed:
        modules.append("cyanotoxins")

    if inputs.algae_risk in ["high", "confirmed_bloom"]:
        modules.append("algae")

    if inputs.iron_median_mg_l > 0.3 or inputs.manganese_median_mg_l > 0.1:
        modules.append("iron_manganese")

    if inputs.treatment_objective == "recycled":
        modules.append("lrv_advanced")

    return modules


# ─── Master Gate 1+2 Runner ───────────────────────────────────────────────────

def run_classification(inputs: SourceWaterInputs) -> ClassificationResult:
    """Execute Gates 1 and 2. Returns ClassificationResult."""
    result = ClassificationResult()

    # Gate 1
    result.source_type = classify_source(inputs)
    result.source_description = SOURCE_TYPES.get(result.source_type, "")
    result.variability_class = inputs.variability_class

    # Gate 2
    primary, secondary = identify_constraints(inputs)
    result.primary_constraint = primary
    result.primary_constraint_description = CONSTRAINTS.get(primary, "")
    result.secondary_constraints = secondary

    # Governing conditions
    result.governing_conditions = assess_governing_conditions(inputs)

    # Direct filtration assessment
    eligible, exclusions = assess_direct_filtration(inputs)
    result.direct_filtration_eligible = eligible
    result.direct_filtration_exclusion_reasons = exclusions

    # Contaminant modules
    result.contaminant_modules_required = identify_contaminant_modules(inputs)

    # Warnings
    if not result.governing_conditions:
        result.governing_conditions.append(
            "Source water variability data appears limited. "
            "Ensure 95th and 99th percentile conditions are characterised before finalising design."
        )

    if inputs.arsenic_ug_l > 0 and inputs.arsenic_ug_l <= 7:
        result.flags.append(
            f"Arsenic {inputs.arsenic_ug_l} μg/L detected but below 7 μg/L guideline trigger. "
            f"Monitor trend — a rising arsenic signal warrants further investigation."
        )

    return result
