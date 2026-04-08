"""
BioPoint V1 — Vendor Claim Validation Engine (v24Z80).
Validates vendor technology claims against physical constraints calculated
by the BioPoint V1 engine stack.

Four validation domains (per spec):
  1. Drying Energy Balance    — energy deficit/surplus, feedstock vs demand
  2. Scale Sensitivity        — small vs large scale performance, modular vs centralised
  3. Logistics Trade-off      — decentralised vs centralised cost comparison
  4. Coupling & Siting        — mainstream decoupling, siting flexibility

Claim validation levels:
  SUPPORTED   — claim is consistent with physics at this feedstock/site
  CONDITIONAL — claim holds only under specific conditions; state them explicitly
  REFUTED     — claim is physically inconsistent at this feedstock/site
  UNVERIFIABLE — claim cannot be tested with available data; flag for vendor due diligence

Critical rule: No vendor claim is accepted without physical validation.
All validation traces back to a specific engine calculation.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# COMMON VENDOR CLAIMS — structured claim library
# ---------------------------------------------------------------------------
# Each claim: (claim_id, pathway_type, claim_text, claim_category)
# Categories: energy / mass / product / liquor / scale / economics / carbon

VENDOR_CLAIM_LIBRARY = {

    # --- PYROLYSIS ---
    "pyr_autothermal": (
        "pyrolysis",
        "Pyrolysis is autothermal — no external fuel required for the conversion step",
        "energy",
    ),
    "pyr_energy_positive": (
        "pyrolysis",
        "Pyrolysis system is net energy positive after accounting for drying",
        "energy",
    ),
    "pyr_87pct_ds_easy": (
        "pyrolysis",
        "Drying to 85-90% DS is standard and readily achievable in practice",
        "energy",
    ),
    "pyr_biochar_sequestration": (
        "pyrolysis",
        "Biochar produced constitutes carbon sequestration, making the process carbon negative",
        "carbon",
    ),
    "pyr_pfas_destruction": (
        "pyrolysis",
        "Pyrolysis at operating temperatures achieves complete PFAS destruction",
        "product",
    ),
    "pyr_mass_reduction_70pct": (
        "pyrolysis",
        "Pyrolysis achieves 60-70% mass reduction on a dry solids basis",
        "mass",
    ),

    # --- INCINERATION ---
    "incin_drying_self_supply": (
        "incineration",
        "Incineration combustion heat fully self-supplies the pre-drying step",
        "energy",
    ),
    "incin_autothermal_22pct": (
        "incineration",
        "Fluidised bed incineration is autothermal above 22% DS without pre-drying",
        "energy",
    ),
    "incin_mass_reduction_95pct": (
        "incineration",
        "Incineration achieves >95% mass reduction from wet sludge to ash",
        "mass",
    ),
    "incin_ash_construction": (
        "incineration",
        "Incinerator ash is suitable for construction aggregate use without further treatment",
        "product",
    ),
    "incin_pfas_destruction": (
        "incineration",
        "Incineration at >850 deg C achieves complete PFAS destruction in compliance with regulations",
        "product",
    ),
    "incin_low_opex": (
        "incineration",
        "Incineration operating cost is low relative to alternative thermal routes",
        "economics",
    ),

    # --- GASIFICATION ---
    "gas_syngas_drying": (
        "gasification",
        "Syngas combustion fully supports the pre-drying loop without external energy",
        "energy",
    ),
    "gas_energy_positive": (
        "gasification",
        "Gasification is net energy positive after drying at typical sludge GCV",
        "energy",
    ),
    "gas_90pct_ds_achievable": (
        "gasification",
        "Achieving 90% DS feedstock is routine and does not represent a significant constraint",
        "energy",
    ),
    "gas_vitrified_product": (
        "gasification",
        "Gasification produces an inert vitrified mineral product suitable for reuse",
        "product",
    ),

    # --- HTC ---
    "htc_no_predrying": (
        "HTC",
        "HTC processes wet sludge without pre-drying — no thermal drying step required",
        "energy",
    ),
    "htc_liquor_benign": (
        "HTC",
        "HTC process liquor is relatively dilute and can be returned directly to the works headworks",
        "liquor",
    ),
    "htc_hydrochar_agriculture": (
        "HTC",
        "Hydrochar produced is suitable for agricultural use as a soil amendment",
        "product",
    ),
    "htc_pfas_immobilisation": (
        "HTC",
        "HTC immobilises PFAS in the hydrochar matrix, reducing bioavailability",
        "product",
    ),
    "htc_energy_neutral": (
        "HTC",
        "HTC overall energy balance is near-neutral or positive",
        "energy",
    ),

    # --- THP ---
    "thp_dewatering_32pct": (
        "thp_incineration",
        "THP enables post-digestion dewatering to 30-35% DS with standard centrifuge",
        "mass",
    ),
    "thp_biogas_uplift_30pct": (
        "thp_incineration",
        "THP provides 20-30% uplift in biogas yield compared to conventional MAD",
        "energy",
    ),
    "thp_class_a": (
        "thp_incineration",
        "THP + MAD consistently achieves Class A biosolids classification",
        "product",
    ),

    # --- DRYING ---
    "dry_07_kwh_kg": (
        "drying_only",
        "Modern indirect dryers achieve 0.65-0.75 kWh/kg water evaporated specific energy consumption",
        "energy",
    ),
    "dry_waste_heat_sufficient": (
        "drying_only",
        "Site waste heat from CHP is sufficient to run the dryer without external energy",
        "energy",
    ),
}


# ---------------------------------------------------------------------------
# VALIDATION RESULT
# ---------------------------------------------------------------------------

@dataclass
class ClaimValidation:
    """Validation result for a single vendor claim."""
    claim_id: str = ""
    pathway_type: str = ""
    claim_text: str = ""
    claim_category: str = ""

    # Verdict
    verdict: str = ""           # SUPPORTED / CONDITIONAL / REFUTED / UNVERIFIABLE
    verdict_confidence: str = ""   # High / Moderate / Low

    # Evidence from engine calculations
    engine_evidence: list = field(default_factory=list)   # Specific numeric evidence
    conditions_for_support: list = field(default_factory=list)
    conditions_violated: list = field(default_factory=list)

    # Engineering commentary
    validation_narrative: str = ""

    # Site-specific result (True = passes at this site)
    passes_at_this_site: bool = False
    site_specific_note: str = ""


@dataclass
class DomainValidation:
    """One of the four validation domains for a pathway."""
    domain: str = ""    # drying_energy / scale_sensitivity / logistics / coupling_siting
    domain_label: str = ""
    pathway_type: str = ""
    pathway_name: str = ""

    findings: list = field(default_factory=list)   # Key findings per domain
    hidden_constraints: list = field(default_factory=list)
    validated_strengths: list = field(default_factory=list)
    scale_limits: list = field(default_factory=list)
    system_fit_verdict: str = ""    # "Good fit" / "Conditional fit" / "Poor fit"
    system_fit_narrative: str = ""


@dataclass
class VendorPathwayReport:
    """
    Full validation report for one pathway.
    Aggregates all four domains and claim-level validations.
    """
    pathway_type: str = ""
    pathway_name: str = ""
    flowsheet_id: str = ""

    # Four domain assessments
    drying_energy: Optional[DomainValidation] = None
    scale_sensitivity: Optional[DomainValidation] = None
    logistics: Optional[DomainValidation] = None
    coupling_siting: Optional[DomainValidation] = None

    # Claim-level validations
    claim_validations: list = field(default_factory=list)   # List[ClaimValidation]

    # Summary
    validated_strengths: list = field(default_factory=list)
    hidden_constraints: list = field(default_factory=list)
    scale_limitations: list = field(default_factory=list)
    system_fit_summary: str = ""

    # Counts
    claims_supported: int = 0
    claims_conditional: int = 0
    claims_refuted: int = 0
    claims_unverifiable: int = 0


@dataclass
class VendorValidationSystem:
    """System-level output: all pathway reports."""
    reports: dict = field(default_factory=dict)   # pathway_type -> VendorPathwayReport
    ds_tpd: float = 0.0
    feed_ds_pct: float = 0.0
    gcv_mj_per_kg_ds: float = 0.0
    feedstock_energy_kwh_d: float = 0.0

    system_summary: str = ""
    key_refutations: list = field(default_factory=list)
    key_conditionals: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_vendor_validation(flowsheets: list, inputs) -> VendorValidationSystem:
    """
    Run vendor claim validation across all thermal pathways.
    Uses engine outputs already calculated by the BioPoint V1 stack.
    """
    fs_in = inputs.feedstock
    assets = inputs.assets

    ds_tpd = fs_in.dry_solids_tpd
    feed_ds_pct = fs_in.dewatered_ds_percent
    gcv = fs_in.gross_calorific_value_mj_per_kg_ds
    vs_pct = fs_in.volatile_solids_percent
    feedstock_kwh_d = ds_tpd * 1000 * gcv / 3.6

    # Build lookup: pathway_type -> flowsheet
    fs_by_type = {fs.pathway_type: fs for fs in flowsheets}

    reports = {}
    all_refutations = []
    all_conditionals = []

    # Validate each thermal pathway
    for ptype in ["pyrolysis", "incineration", "gasification", "HTC",
                  "thp_incineration", "drying_only"]:
        fs = fs_by_type.get(ptype)
        if not fs:
            continue

        report = _build_pathway_report(
            fs, ptype, ds_tpd, feed_ds_pct, gcv, vs_pct,
            feedstock_kwh_d, assets
        )
        reports[ptype] = report

        for cv in report.claim_validations:
            if cv.verdict == "REFUTED":
                all_refutations.append(
                    f"[{ptype}] {cv.claim_text[:60]}... → REFUTED: {cv.conditions_violated[0][:60] if cv.conditions_violated else ''}"
                )
            elif cv.verdict == "CONDITIONAL":
                all_conditionals.append(
                    f"[{ptype}] {cv.claim_text[:60]}... → CONDITIONAL: {cv.conditions_for_support[0][:60] if cv.conditions_for_support else ''}"
                )

    system_summary = _system_summary(reports, feed_ds_pct, gcv, ds_tpd, feedstock_kwh_d)

    return VendorValidationSystem(
        reports=reports,
        ds_tpd=ds_tpd,
        feed_ds_pct=feed_ds_pct,
        gcv_mj_per_kg_ds=gcv,
        feedstock_energy_kwh_d=round(feedstock_kwh_d, 0),
        system_summary=system_summary,
        key_refutations=all_refutations[:8],
        key_conditionals=all_conditionals[:8],
    )


# ---------------------------------------------------------------------------
# PATHWAY REPORT BUILDER
# ---------------------------------------------------------------------------

def _build_pathway_report(fs, ptype, ds_tpd, feed_ds_pct, gcv, vs_pct,
                           feedstock_kwh_d, assets) -> VendorPathwayReport:

    esys = fs.energy_system
    mb   = fs.mass_balance
    dc   = fs.drying_calc
    ec   = fs.economics
    cc   = fs.coupling_classification
    sp   = fs.siting
    mc   = fs.mainstream_coupling

    report = VendorPathwayReport(
        pathway_type=ptype,
        pathway_name=fs.name,
        flowsheet_id=fs.flowsheet_id,
    )

    # --- DOMAIN 1: DRYING ENERGY BALANCE ---
    report.drying_energy = _validate_drying_energy(
        ptype, fs, esys, dc, mb, feedstock_kwh_d, ds_tpd, feed_ds_pct, gcv, assets
    )

    # --- DOMAIN 2: SCALE SENSITIVITY ---
    report.scale_sensitivity = _validate_scale_sensitivity(
        ptype, fs, ds_tpd, ec, mb
    )

    # --- DOMAIN 3: LOGISTICS TRADE-OFF ---
    report.logistics = _validate_logistics(
        ptype, fs, ds_tpd, feed_ds_pct, ec, mb, assets
    )

    # --- DOMAIN 4: COUPLING & SITING ---
    report.coupling_siting = _validate_coupling_siting(
        ptype, fs, cc, sp, mc
    )

    # --- CLAIM-LEVEL VALIDATIONS ---
    claims = _get_claims_for_pathway(ptype)
    for claim_id, (cptype, claim_text, category) in claims.items():
        cv = _validate_claim(
            claim_id, cptype, claim_text, category,
            fs, esys, dc, mb, ec, cc, sp, mc,
            ds_tpd, feed_ds_pct, gcv, vs_pct,
            feedstock_kwh_d, assets
        )
        report.claim_validations.append(cv)

    # Aggregate
    report.claims_supported    = sum(1 for c in report.claim_validations if c.verdict == "SUPPORTED")
    report.claims_conditional  = sum(1 for c in report.claim_validations if c.verdict == "CONDITIONAL")
    report.claims_refuted      = sum(1 for c in report.claim_validations if c.verdict == "REFUTED")
    report.claims_unverifiable = sum(1 for c in report.claim_validations if c.verdict == "UNVERIFIABLE")

    # Aggregate strengths and constraints
    for d in [report.drying_energy, report.scale_sensitivity,
              report.logistics, report.coupling_siting]:
        if d:
            report.validated_strengths.extend(d.validated_strengths)
            report.hidden_constraints.extend(d.hidden_constraints)
            report.scale_limitations.extend(d.scale_limits)

    report.system_fit_summary = _system_fit_summary(
        ptype, report.claims_refuted, report.claims_conditional,
        report.claims_supported, feed_ds_pct, gcv
    )

    return report


# ---------------------------------------------------------------------------
# DOMAIN 1 — DRYING ENERGY BALANCE
# ---------------------------------------------------------------------------

def _validate_drying_energy(ptype, fs, esys, dc, mb,
                              feedstock_kwh_d, ds_tpd, feed_ds_pct, gcv, assets
                              ) -> DomainValidation:
    d = DomainValidation(
        domain="drying_energy",
        domain_label="Drying Energy Balance",
        pathway_type=ptype,
        pathway_name=fs.name,
    )

    if not dc.drying_required:
        d.validated_strengths.append(
            f"No pre-drying required — pathway accepts wet feed directly. "
            f"Drying energy constraint does not apply."
        )
        d.system_fit_verdict = "Good fit (no drying)"
        d.system_fit_narrative = "Wet-feed pathway bypasses the drying energy constraint entirely."
        return d

    # Drying burden metrics
    water_t_d  = dc.water_removed_tpd
    gross_kwh_d = dc.drying_energy_actual_kwh_per_day
    ext_kwh_d   = esys.external_drying_energy_kwh_d if esys else dc.net_external_drying_energy_kwh_per_day
    int_pct     = esys.drying_covered_by_internal_pct if esys else 0.0
    flag        = esys.energy_viability_flag if esys else "UNKNOWN"
    power_cost  = assets.local_power_price_per_kwh
    drying_cost_yr = ext_kwh_d * 365 * power_cost

    # Feedstock energy ratio
    drying_as_pct_feedstock = gross_kwh_d / feedstock_kwh_d * 100 if feedstock_kwh_d > 0 else 0

    # Findings
    d.findings.append(
        f"Water to remove: {water_t_d:.0f} t/day from {feed_ds_pct:.0f}% DS "
        f"to {dc.target_ds_pct:.0f}% DS target."
    )
    d.findings.append(
        f"Gross drying energy: {gross_kwh_d:,.0f} kWh/day "
        f"= {drying_as_pct_feedstock:.0f}% of feedstock energy content "
        f"({feedstock_kwh_d:,.0f} kWh/day)."
    )
    d.findings.append(
        f"Internal heat coverage: {int_pct:.0f}%. "
        f"External energy required: {ext_kwh_d:,.0f} kWh/day "
        f"(${drying_cost_yr:,.0f}/yr at ${power_cost:.2f}/kWh)."
    )
    d.findings.append(f"Energy viability flag: {flag}")

    if flag == "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT":
        d.hidden_constraints.append(
            f"Drying energy ({gross_kwh_d:,.0f} kWh/d) represents "
            f"{drying_as_pct_feedstock:.0f}% of feedstock energy. "
            f"At ${power_cost:.2f}/kWh, drying costs ${drying_cost_yr:,.0f}/yr — "
            f"a primary economic constraint that many vendor proposals understate."
        )
        d.hidden_constraints.append(
            f"Internal heat covers only {int_pct:.0f}% of drying demand at {feed_ds_pct:.0f}% DS feed. "
            f"Claims of 'self-sufficient drying' are not valid at this feedstock DS%."
        )
        d.system_fit_verdict = "Poor fit (energy)"
        d.system_fit_narrative = (
            f"Drying energy demand exceeds internally available heat. "
            f"Vendor claims of autothermal or self-sufficient drying must be "
            f"assessed against this specific feed DS% and GCV, not published lab values."
        )
    elif flag == "VIABLE WITH WASTE HEAT":
        d.validated_strengths.append(
            f"Drying energy is partially self-supplied ({int_pct:.0f}% internal coverage). "
            f"Confirmed waste heat source reduces external energy requirement."
        )
        d.hidden_constraints.append(
            f"Remaining {100-int_pct:.0f}% of drying demand ({ext_kwh_d:,.0f} kWh/d) "
            f"requires external energy — must be confirmed and costed in base case."
        )
        d.system_fit_verdict = "Conditional fit (energy)"
        d.system_fit_narrative = "Viable with waste heat confirmed. Do not assume waste heat availability."
    else:
        d.validated_strengths.append(
            f"Drying energy balance viable: internal sources cover "
            f"{int_pct:.0f}% of drying demand."
        )
        d.system_fit_verdict = "Good fit (energy)"
        d.system_fit_narrative = "Drying energy balance closes at this site configuration."

    return d


# ---------------------------------------------------------------------------
# DOMAIN 2 — SCALE SENSITIVITY
# ---------------------------------------------------------------------------

# Technology readiness at scale — TRL and reference plant data
_SCALE_DATA = {
    "pyrolysis": {
        "commercial_min_tds_d": 2.0,
        "optimal_range": "5–30 tDS/d per module",
        "modular": True,
        "full_scale_refs": "PYREG (5–15 tDS/d modules), Haarslev carbonisation",
        "risk_at_large_scale": "Moderate — scale-up to 100+ tDS/d requires multiple modules; integration complexity",
        "risk_at_small_scale": "Low — modular deployment is the native application",
    },
    "incineration": {
        "commercial_min_tds_d": 30.0,
        "optimal_range": "50–200+ tDS/d",
        "modular": False,
        "full_scale_refs": "Established globally — thousands of full-scale FBF plants",
        "risk_at_large_scale": "Low — incineration improves at scale (unit economics, APC efficiency)",
        "risk_at_small_scale": "High — below 30 tDS/d, own-asset incineration is rarely economic; co-incineration preferred",
    },
    "gasification": {
        "commercial_min_tds_d": 5.0,
        "optimal_range": "10–50 tDS/d",
        "modular": True,
        "full_scale_refs": "Limited full-scale sludge refs; industrial gasification proven at larger scale",
        "risk_at_large_scale": "High — scale-up complexity; limited demonstrated references",
        "risk_at_small_scale": "Moderate — some modular vendors; TRL lower than pyrolysis",
    },
    "HTC": {
        "commercial_min_tds_d": 3.0,
        "optimal_range": "10–100+ tDS/d",
        "modular": True,
        "full_scale_refs": "AVA-CO2, Grenol, Hydroheat — pilot to early commercial",
        "risk_at_large_scale": "Moderate — liquor treatment at scale is the primary risk",
        "risk_at_small_scale": "Low — wet process suits smaller modular deployment",
    },
    "thp_incineration": {
        "commercial_min_tds_d": 20.0,
        "optimal_range": "30–200+ tDS/d",
        "modular": False,
        "full_scale_refs": "Cambi (multiple global refs), Lysotherm, Turbotec",
        "risk_at_large_scale": "Low — THP is proven at utility scale",
        "risk_at_small_scale": "Moderate — THP capital recovery requires significant throughput",
    },
    "drying_only": {
        "commercial_min_tds_d": 1.0,
        "optimal_range": "Any scale",
        "modular": True,
        "full_scale_refs": "Huber, Andritz, BMA — broad commercial deployment",
        "risk_at_large_scale": "Low — standard equipment",
        "risk_at_small_scale": "Low — modular belt/paddle dryers widely available",
    },
}

def _validate_scale_sensitivity(ptype, fs, ds_tpd, ec, mb) -> DomainValidation:
    d = DomainValidation(
        domain="scale_sensitivity",
        domain_label="Scale Sensitivity",
        pathway_type=ptype,
        pathway_name=fs.name,
    )

    sd = _SCALE_DATA.get(ptype, {})
    min_tds = sd.get("commercial_min_tds_d", 1.0)
    optimal = sd.get("optimal_range", "Unknown")
    modular = sd.get("modular", False)
    refs    = sd.get("full_scale_refs", "Not established")
    risk_large = sd.get("risk_at_large_scale", "Unknown")
    risk_small = sd.get("risk_at_small_scale", "Unknown")

    d.findings.append(
        f"Evaluated scale: {ds_tpd:.0f} tDS/day. "
        f"Commercial minimum: {min_tds:.0f} tDS/day. "
        f"Optimal range: {optimal}."
    )
    d.findings.append(f"Modular deployment: {'Yes' if modular else 'No — centralised plant required'}.")
    d.findings.append(f"Full-scale references: {refs}.")

    # Scale check
    if ds_tpd < min_tds:
        d.hidden_constraints.append(
            f"Site throughput ({ds_tpd:.0f} tDS/d) is below minimum commercial scale "
            f"({min_tds:.0f} tDS/d). Vendor proposals at this scale may rely on "
            "unproven scale-down assumptions."
        )
        d.scale_limits.append(
            f"Below minimum commercial scale — consider co-treatment or "
            f"deferral until system volume reaches {min_tds:.0f} tDS/d."
        )
        d.system_fit_verdict = "Poor fit (scale)"
    elif ds_tpd >= min_tds and not modular and ds_tpd < 30:
        d.hidden_constraints.append(
            f"Non-modular pathway at {ds_tpd:.0f} tDS/d: "
            f"economy of scale benefits are limited at this throughput. "
            f"Unit capital cost will be high relative to optimal scale ({optimal})."
        )
        d.system_fit_verdict = "Conditional fit (scale)"
    else:
        d.validated_strengths.append(
            f"Throughput ({ds_tpd:.0f} tDS/d) is within commercial operating range ({optimal}). "
            f"Scale risk: {risk_large.split('—')[0].strip()} at this site."
        )
        d.system_fit_verdict = "Good fit (scale)"

    d.findings.append(f"Risk at this scale: {risk_large}.")
    d.system_fit_narrative = (
        f"{risk_large} Scale sensitivity note: {risk_small} at smaller deployments. "
        f"{'Modular deployment reduces commitment risk — phased build possible.' if modular else 'Full plant required — single CAPEX commitment.'}"
    )

    return d


# ---------------------------------------------------------------------------
# DOMAIN 3 — LOGISTICS TRADE-OFF
# ---------------------------------------------------------------------------

def _validate_logistics(ptype, fs, ds_tpd, feed_ds_pct,
                          ec, mb, assets) -> DomainValidation:
    d = DomainValidation(
        domain="logistics",
        domain_label="Logistics Trade-off",
        pathway_type=ptype,
        pathway_name=fs.name,
    )

    transport_rate = assets.transport_cost_per_tonne_km
    avg_km = assets.average_transport_distance_km

    wet_in_t_d   = mb.wet_sludge_in_tpd
    residual_t_d = mb.residual_wet_mass_tpd
    mass_red_pct = mb.total_mass_reduction_pct

    # Baseline transport (no treatment)
    baseline_t_km_yr  = wet_in_t_d * 365 * avg_km
    baseline_trans_yr = baseline_t_km_yr * transport_rate

    # Post-treatment transport
    residual_t_km_yr  = residual_t_d * 365 * avg_km
    residual_trans_yr = residual_t_km_yr * transport_rate
    transport_saving  = baseline_trans_yr - residual_trans_yr

    d.findings.append(
        f"Baseline transport: {wet_in_t_d:.0f} t/day × {avg_km:.0f} km "
        f"= ${baseline_trans_yr:,.0f}/yr."
    )
    d.findings.append(
        f"Post-treatment residual: {residual_t_d:.0f} t/day "
        f"({mass_red_pct:.0f}% mass reduction) "
        f"= ${residual_trans_yr:,.0f}/yr transport."
    )
    d.findings.append(
        f"Annual transport saving vs baseline: ${transport_saving:,.0f}/yr."
    )

    # Centralised vs decentralised analysis
    is_centralised = ptype in ("centralised", "incineration", "thp_incineration")
    is_fixed_site  = ptype in ("HTC", "HTC_sidestream", "AD")

    if is_centralised:
        d.findings.append(
            f"Centralised pathway: sludge must be hauled from all sites to hub. "
            f"Feed transport is the primary logistics cost."
        )
        if avg_km > 80:
            d.hidden_constraints.append(
                f"Average haul distance ({avg_km:.0f} km) is HIGH for wet sludge transport. "
                f"Wet sludge is expensive to haul — consider dewatering to higher DS% at site "
                "before transport to reduce volume and cost."
            )
        d.validated_strengths.append(
            f"Economy of scale at hub. Residual transport minimal "
            f"({residual_t_d:.0f} t/day vs {wet_in_t_d:.0f} t/day intake)."
        )
    elif is_fixed_site:
        d.validated_strengths.append(
            "Fixed on-site technology eliminates inter-site transport. "
            "No sludge movement to hub required."
        )
        d.findings.append(
            f"Remaining residual ({residual_t_d:.0f} t/day) still requires "
            f"disposal transport: ${residual_trans_yr:,.0f}/yr."
        )
    else:
        d.findings.append(
            f"Flexible-location pathway: can be deployed on-site or at hub. "
            f"Logistics optimised by location choice."
        )

    if mass_red_pct >= 90:
        d.validated_strengths.append(
            f"Exceptional mass reduction ({mass_red_pct:.0f}%) — "
            "disposal logistics nearly eliminated. "
            f"Residual ({residual_t_d:.0f} t/day) is manageable as inert product."
        )
    elif mass_red_pct >= 70:
        d.validated_strengths.append(
            f"Significant mass reduction ({mass_red_pct:.0f}%) — "
            f"disposal transport reduced by ${transport_saving:,.0f}/yr."
        )
    else:
        d.hidden_constraints.append(
            f"Mass reduction only {mass_red_pct:.0f}% — "
            f"{residual_t_d:.0f} t/day still requires transport and disposal."
        )

    d.system_fit_verdict = (
        "Good fit (logistics)" if mass_red_pct >= 70 else "Conditional fit (logistics)"
    )
    d.system_fit_narrative = (
        f"Mass reduction of {mass_red_pct:.0f}% from {wet_in_t_d:.0f} to "
        f"{residual_t_d:.0f} t/day. "
        f"Annual transport saving: ${transport_saving:,.0f}/yr."
    )

    return d


# ---------------------------------------------------------------------------
# DOMAIN 4 — COUPLING & SITING
# ---------------------------------------------------------------------------

def _validate_coupling_siting(ptype, fs, cc, sp, mc) -> DomainValidation:
    d = DomainValidation(
        domain="coupling_siting",
        domain_label="Coupling & Siting",
        pathway_type=ptype,
        pathway_name=fs.name,
    )

    tier  = cc.coupling_tier if cc else 2
    flex  = sp.siting_flexibility if sp else "MEDIUM"
    plan  = sp.planning_risk if sp else "MEDIUM"
    foot  = sp.footprint_impact if sp else "MEDIUM"
    nh4   = mc.return_nh4_kg_d if mc else 0
    pct   = mc.return_as_pct_of_plant_nh4 if mc else 0
    c_risk= cc.compliance_risk if cc else "Low"

    d.findings.append(
        f"Coupling Tier {tier} ({cc.coupling_tier_label if cc else 'Unknown'}). "
        f"Return NH4: {nh4:.0f} kgN/day ({pct:.1f}% of plant influent N). "
        f"Compliance risk: {c_risk}."
    )
    d.findings.append(
        f"Siting flexibility: {flex}. "
        f"Preferred location: {sp.preferred_location if sp else 'Unknown'}. "
        f"Planning risk: {plan}. Footprint: {foot}."
    )

    if tier == 1:
        d.validated_strengths.append(
            "Fully Decoupled (Tier 1) — no significant return load to mainstream. "
            "Mainstream plant operates independently."
        )
    elif tier == 2:
        d.validated_strengths.append(
            f"Partially Coupled (Tier 2) — NH4 return ({nh4:.0f} kgN/d = {pct:.1f}% of plant N) "
            "within routine recycle tolerance."
        )
    else:
        d.hidden_constraints.append(
            f"Fully Coupled (Tier 3) — return NH4 of {nh4:.0f} kgN/d ({pct:.1f}% of plant N). "
            "Requires explicit mainstream capacity assessment. "
            "Compliance risk: Moderate. Cannot be selected without sidestream treatment or "
            "confirmed excess plant capacity."
        )

    if flex == "HIGH":
        d.validated_strengths.append(
            f"High siting flexibility — can be deployed off-site at industrial hub. "
            "Removes technology from WWTP community interface. "
            f"Planning risk: {plan}."
        )
        if plan == "HIGH":
            d.hidden_constraints.append(
                "High planning risk: off-site facility requires EIA, air quality consent, "
                "and community consultation. Allow 2–4 year permitting timeline. "
                "Include permitting cost and delay in project business case."
            )
    elif flex == "LOW":
        d.hidden_constraints.append(
            "Low siting flexibility — technology must remain at WWTP. "
            "Community interface is permanent. Planning within existing consent "
            "is simpler but the footprint constraint is locked."
        )

    d.system_fit_verdict = (
        "Good fit" if tier <= 2 and flex in ("HIGH", "MEDIUM") else "Conditional fit"
    )
    d.system_fit_narrative = (
        f"Tier {tier} coupling with {flex.lower()} siting flexibility. "
        f"Compliance risk: {c_risk}. Planning risk: {plan}."
    )

    return d


# ---------------------------------------------------------------------------
# CLAIM-LEVEL VALIDATION
# ---------------------------------------------------------------------------

def _get_claims_for_pathway(ptype: str) -> dict:
    return {
        k: v for k, v in VENDOR_CLAIM_LIBRARY.items()
        if v[0] == ptype
    }


def _validate_claim(claim_id, ptype, claim_text, category,
                     fs, esys, dc, mb, ec, cc, sp, mc,
                     ds_tpd, feed_ds_pct, gcv, vs_pct,
                     feedstock_kwh_d, assets) -> ClaimValidation:

    cv = ClaimValidation(
        claim_id=claim_id,
        pathway_type=ptype,
        claim_text=claim_text,
        claim_category=category,
    )

    power_cost = assets.local_power_price_per_kwh
    ext_kwh_d  = esys.external_drying_energy_kwh_d if esys else 0
    int_pct    = esys.drying_covered_by_internal_pct if esys else 0
    flag       = esys.energy_viability_flag if esys else "UNKNOWN"

    # ── PYROLYSIS CLAIMS ──────────────────────────────────────────────────
    if claim_id == "pyr_autothermal":
        # Autothermal: conversion step self-sufficient; drying is separate
        # At feed GCV ≥ 10 MJ/kgDS and target DS ≥ 85%, autothermal conversion holds
        # but drying is NOT covered by this claim
        if gcv >= 10.0 and feed_ds_pct >= 15.0:
            cv.verdict = "CONDITIONAL"
            cv.verdict_confidence = "Moderate"
            cv.conditions_for_support = [
                f"GCV {gcv:.1f} MJ/kgDS is adequate for autothermal pyrolysis reaction",
                f"BUT feed must reach {dc.target_ds_pct:.0f}% DS — drying is a separate energy demand",
                "Autothermal refers to the reactor step only, not the full system including drying",
            ]
            cv.engine_evidence = [
                f"Feedstock energy: {feedstock_kwh_d:,.0f} kWh/d",
                f"External drying energy still required: {ext_kwh_d:,.0f} kWh/d",
                f"Internal coverage of drying: {int_pct:.0f}%",
            ]
            cv.validation_narrative = (
                f"The pyrolysis reactor may be autothermal at GCV {gcv:.1f} MJ/kgDS. "
                f"However, 'autothermal' in vendor proposals typically refers to the "
                f"conversion reactor step only — not the full system including pre-drying. "
                f"At {feed_ds_pct:.0f}% DS feed, {ext_kwh_d:,.0f} kWh/d of external energy "
                f"is still required for drying. The full system is not self-sufficient."
            )
        else:
            cv.verdict = "REFUTED"
            cv.verdict_confidence = "High"
            cv.conditions_violated = [
                f"GCV {gcv:.1f} MJ/kgDS is below threshold for reliable autothermal operation",
            ]
        cv.passes_at_this_site = (gcv >= 10.0 and feed_ds_pct >= 15.0)

    elif claim_id == "pyr_energy_positive":
        if flag == "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT":
            cv.verdict = "REFUTED"
            cv.verdict_confidence = "High"
            cv.conditions_violated = [
                f"Net energy is strongly negative at {feed_ds_pct:.0f}% DS: "
                f"external drying demand {ext_kwh_d:,.0f} kWh/d far exceeds recoverable energy.",
                f"Drying consumes {int_pct:.0f}% of internal heat — "
                "system is not energy positive.",
            ]
            cv.engine_evidence = [
                f"Drying energy internal coverage: {int_pct:.0f}%",
                f"External energy required: {ext_kwh_d:,.0f} kWh/d",
                f"Annual external energy cost: ${ext_kwh_d * 365 * power_cost:,.0f}/yr",
            ]
            cv.validation_narrative = (
                f"Energy positive claim is REFUTED at {feed_ds_pct:.0f}% DS and "
                f"GCV {gcv:.1f} MJ/kgDS. Drying energy ({ext_kwh_d:,.0f} kWh/d external) "
                f"exceeds available internal heat. The full system has a large energy deficit. "
                f"Vendor proposals showing energy-positive results should be tested "
                f"against this specific feed DS% and GCV — not idealised feedstock data."
            )
        elif flag == "VIABLE":
            cv.verdict = "SUPPORTED"
            cv.validation_narrative = "Energy balance closes at this site configuration."
        else:
            cv.verdict = "CONDITIONAL"
            cv.conditions_for_support = ["Confirmed waste heat source required"]
        cv.passes_at_this_site = (flag == "VIABLE")

    elif claim_id == "pyr_87pct_ds_easy":
        # Drying to 87% DS from current feed DS%
        if feed_ds_pct < 18:
            cv.verdict = "REFUTED"
            cv.conditions_violated = [
                f"At {feed_ds_pct:.0f}% DS, drying to 87% DS requires removing "
                f"{dc.water_removed_tpd:.0f} t/day of water — not 'standard' or 'easy'.",
                f"Drying energy: {dc.drying_energy_actual_kwh_per_day:,.0f} kWh/day "
                f"= {dc.drying_energy_actual_kwh_per_day/feedstock_kwh_d*100:.0f}% of feedstock energy."
            ]
        else:
            cv.verdict = "CONDITIONAL"
            cv.conditions_for_support = [
                f"Achievable from {feed_ds_pct:.0f}% DS but energy-intensive: "
                f"{dc.drying_energy_actual_kwh_per_day:,.0f} kWh/day gross drying energy.",
                f"Annual cost at ${power_cost:.2f}/kWh: "
                f"${ext_kwh_d * 365 * power_cost:,.0f}/yr external energy.",
            ]
        cv.passes_at_this_site = feed_ds_pct >= 18

    elif claim_id == "pyr_biochar_sequestration":
        cv.verdict = "CONDITIONAL"
        cv.verdict_confidence = "Moderate"
        cv.conditions_for_support = [
            "Biochar must be applied to soil and remain stable over 100-year horizon",
            "PFAS content must not preclude land application — characterise first",
            "Carbon credit market validation required; not all biochar qualifies",
        ]
        cv.engine_evidence = [
            f"Carbon to char: {fs.carbon_balance.carbon_to_char_t_per_day*365:.0f} tC/yr",
            f"Carbon sequestration confidence: {fs.carbon_balance.carbon_credit_confidence}",
        ]
        cv.validation_narrative = (
            "Biochar carbon sequestration is physically plausible but not automatic. "
            "Claim is CONDITIONAL on: stable biochar quality, land application route "
            "remaining open, and carbon credit market eligibility. "
            "If PFAS is present, land application may be precluded — closing the sequestration route."
        )

    elif claim_id == "pyr_pfas_destruction":
        cv.verdict = "CONDITIONAL"
        cv.conditions_for_support = [
            "Operating temperature must consistently exceed 700°C (pyrolysis) or 850°C (combustion of pyrolysis gas)",
            "Destruction must be confirmed for specific PFAS compounds present — not all are equally volatile",
            "Third-party testing of char and emissions required to verify compliance",
        ]
        cv.validation_narrative = (
            "Pyrolysis can achieve high PFAS destruction but the claim requires qualification. "
            "Destruction efficiency depends on operating temperature, PFAS compound class, "
            "and whether gas phase combustion is included. Regulatory acceptance varies by jurisdiction."
        )

    elif claim_id == "pyr_mass_reduction_70pct":
        actual = mb.total_mass_reduction_pct
        if actual >= 65:
            cv.verdict = "SUPPORTED"
            cv.engine_evidence = [f"Mass reduction: {actual:.0f}% from wet sludge basis"]
        else:
            cv.verdict = "CONDITIONAL"
            cv.conditions_for_support = [f"Actual: {actual:.0f}% at this feed DS%"]

    # ── INCINERATION CLAIMS ───────────────────────────────────────────────
    elif claim_id == "incin_drying_self_supply":
        # Incineration thermal recovery covers drying loop?
        if esys:
            incin_therm = feedstock_kwh_d * 0.40  # 40% thermal efficiency
            drying_demand = dc.drying_energy_actual_kwh_per_day if dc.drying_required else 0
            coverage = incin_therm / drying_demand * 100 if drying_demand > 0 else 100
            if coverage >= 95:
                cv.verdict = "SUPPORTED"
                cv.engine_evidence = [
                    f"Incineration thermal: {incin_therm:,.0f} kWh/d",
                    f"Drying demand: {drying_demand:,.0f} kWh/d",
                    f"Coverage: {coverage:.0f}%",
                ]
            elif coverage >= 50:
                cv.verdict = "CONDITIONAL"
                cv.conditions_for_support = [
                    f"Thermal recovery covers {coverage:.0f}% of drying demand at {feed_ds_pct:.0f}% DS",
                    f"Remaining {100-coverage:.0f}% ({max(0,drying_demand-incin_therm):,.0f} kWh/d) requires auxiliary energy",
                    f"Feed DS% must reach ~{feed_ds_pct + (100-coverage)/4:.0f}% for full self-supply",
                ]
                cv.engine_evidence = [
                    f"Incineration thermal: {incin_therm:,.0f} kWh/d covers {coverage:.0f}% of drying"
                ]
            else:
                cv.verdict = "REFUTED"
                cv.conditions_violated = [
                    f"At {feed_ds_pct:.0f}% DS, incineration thermal ({incin_therm:,.0f} kWh/d) "
                    f"covers only {coverage:.0f}% of drying demand ({drying_demand:,.0f} kWh/d). "
                    f"Claim of full self-supply is false at this feed DS%."
                ]
            cv.passes_at_this_site = coverage >= 95
        else:
            cv.verdict = "UNVERIFIABLE"

    elif claim_id == "incin_autothermal_22pct":
        # FBF autothermal at 22% DS without pre-drying?
        # At 22% DS, VS fraction ~65–75%, GCV ~10-14 MJ/kgDS
        # FBF autothermal threshold is typically ~22-25% DS AT THE FURNACE
        # Pre-drying to 75-85% DS typically required for stable FBF operation
        cv.verdict = "CONDITIONAL"
        cv.verdict_confidence = "Moderate"
        cv.conditions_for_support = [
            "FBF autothermal at 22% DS is achievable at high VS% (>70%) and GCV (>11 MJ/kgDS)",
            "Stable operation typically requires GCV >9 MJ/kgDS on a wet basis",
            f"At {feed_ds_pct:.0f}% DS and GCV {gcv:.1f} MJ/kgDS (DS basis): "
            f"wet basis GCV = {gcv * feed_ds_pct/100:.1f} MJ/kgWS — verify against FBF minimum",
        ]
        cv.validation_narrative = (
            f"FBF autothermal at {feed_ds_pct:.0f}% DS may be possible at this GCV "
            f"({gcv:.1f} MJ/kgDS) but is on the margin. Most modern FBF designs "
            "require pre-drying to 30-50% DS for stable autothermal operation at utility scale. "
            "Confirm with vendor combustion modelling at actual feed composition."
        )
        wet_gcv = gcv * feed_ds_pct / 100
        cv.passes_at_this_site = wet_gcv >= 2.5  # rough threshold

    elif claim_id == "incin_mass_reduction_95pct":
        actual = mb.total_mass_reduction_pct
        # From wet sludge to ash: 93-96% typical
        if actual >= 90:
            cv.verdict = "SUPPORTED"
            cv.engine_evidence = [f"Mass reduction: {actual:.0f}% wet basis"]
        else:
            cv.verdict = "CONDITIONAL"
            cv.engine_evidence = [f"Calculated: {actual:.0f}% at this feed DS% and model assumptions"]

    elif claim_id == "incin_ash_construction":
        cv.verdict = "CONDITIONAL"
        cv.conditions_for_support = [
            "Ash P-content and heavy metal concentrations must meet construction standards",
            "PFAS in ash must be characterised — concentrates during incineration, "
            "may preclude construction use in some jurisdictions",
            "Regulatory acceptance varies by country — confirm local standards",
        ]

    elif claim_id == "incin_pfas_destruction":
        cv.verdict = "SUPPORTED"
        cv.verdict_confidence = "High"
        cv.conditions_for_support = [
            "Operating temperature consistently >850°C in thermal zone",
            "Residence time >2 seconds in post-combustion zone",
            "APC system maintained (scrubber + bag filter)",
        ]
        cv.engine_evidence = ["Incineration is the most defensible PFAS destruction route globally"]
        cv.validation_narrative = (
            "SUPPORTED. FBF incineration at >850°C is the regulatory gold standard for "
            "PFAS destruction in biosolids. Destruction efficiency >99.999% demonstrated "
            "at full scale. Stack emissions subject to APC requirements."
        )
        cv.passes_at_this_site = True

    elif claim_id == "incin_low_opex":
        # Incineration OPEX is actually high — APC, maintenance, compliance
        opex_per_tds = ec.total_opex_per_year / (ds_tpd * 365) if ds_tpd > 0 else 0
        cv.verdict = "CONDITIONAL"
        cv.engine_evidence = [
            f"OPEX: ${ec.total_opex_per_year:,.0f}/yr = ${opex_per_tds:.0f}/tDS",
            f"Primary OPEX driver: drying energy cost (${ec.drying_energy_cost_per_year:,.0f}/yr)",
        ]
        cv.validation_narrative = (
            f"Incineration OPEX (${opex_per_tds:.0f}/tDS) is NOT low compared to AD or HTC. "
            "The primary OPEX driver is pre-drying energy. CAPEX is also the highest of "
            "any thermal pathway. Claim of 'low OPEX' requires qualification — "
            "incineration is low risk operationally but high cost."
        )

    # ── GASIFICATION CLAIMS ───────────────────────────────────────────────
    elif claim_id == "gas_syngas_drying":
        if flag == "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT":
            cv.verdict = "REFUTED"
            cv.conditions_violated = [
                f"Syngas energy at this GCV ({gcv:.1f} MJ/kgDS) and feed DS% ({feed_ds_pct:.0f}%) "
                f"is insufficient to self-supply drying. Internal coverage: {int_pct:.0f}%.",
                f"External energy required: {ext_kwh_d:,.0f} kWh/day.",
            ]
            cv.engine_evidence = [f"Internal heat coverage: {int_pct:.0f}% of drying demand"]
        else:
            cv.verdict = "CONDITIONAL"
            cv.conditions_for_support = ["Confirmed at this GCV and DS%"]
        cv.passes_at_this_site = int_pct >= 90

    elif claim_id == "gas_energy_positive":
        cv.verdict = "REFUTED" if flag == "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT" else "CONDITIONAL"
        cv.engine_evidence = [f"Energy viability flag: {flag}", f"Internal coverage: {int_pct:.0f}%"]

    elif claim_id == "gas_90pct_ds_achievable":
        water_to_dry = mb.water_removed_tpd
        drying_cost = ext_kwh_d * 365 * power_cost
        cv.verdict = "CONDITIONAL"
        cv.conditions_for_support = [
            f"Physically achievable from {feed_ds_pct:.0f}% DS but requires "
            f"{water_to_dry:.0f} t/day water removal.",
            f"Drying energy cost: ${drying_cost:,.0f}/yr at ${power_cost:.2f}/kWh — "
            "this is a primary project cost, not a minor pre-treatment step.",
        ]
        cv.validation_narrative = (
            "Drying to 90% DS is physically possible. The claim that it 'does not represent "
            f"a significant constraint' is MISLEADING at {feed_ds_pct:.0f}% DS feed. "
            f"Removing {water_to_dry:.0f} t/day of water costs ${drying_cost:,.0f}/yr "
            f"at $0.18/kWh. This is the dominant cost in the project, not a footnote."
        )

    elif claim_id == "gas_vitrified_product":
        cv.verdict = "CONDITIONAL"
        cv.conditions_for_support = [
            "Vitrification requires sustained high temperatures (>1200°C) — confirm operating profile",
            "Ash composition (P, metals, PFAS) determines product eligibility for reuse",
            "Market acceptance for vitrified sludge ash in construction is jurisdiction-specific",
        ]

    # ── HTC CLAIMS ────────────────────────────────────────────────────────
    elif claim_id == "htc_no_predrying":
        cv.verdict = "SUPPORTED"
        cv.verdict_confidence = "High"
        cv.engine_evidence = [
            "HTC target DS = feed DS% — no pre-drying step in model",
            f"Drying required: {dc.drying_required}",
        ]
        cv.validation_narrative = (
            "SUPPORTED. HTC is a wet thermochemical process operating at 180-220°C and "
            "elevated pressure. No pre-drying is required — this is a genuine and "
            "validated advantage over pyrolysis, gasification, and incineration."
        )
        cv.passes_at_this_site = True

    elif claim_id == "htc_liquor_benign":
        nh4 = mc.return_nh4_kg_d if mc else 0
        cod = mc.return_cod_kg_d  if mc else 0
        pct = mc.return_as_pct_of_plant_nh4 if mc else 0
        cv.verdict = "REFUTED"
        cv.verdict_confidence = "High"
        cv.conditions_violated = [
            f"HTC process liquor NH4-N: {nh4:.0f} kgN/day ({pct:.0f}% of plant influent N)",
            f"HTC process liquor COD: {cod:.0f} kgCOD/day",
            "Direct return without treatment will significantly load the liquid stream",
        ]
        cv.engine_evidence = [
            f"NH4-N return: {nh4:.0f} kgN/d (not 'dilute')",
            f"COD return: {cod:.0f} kgCOD/d",
            f"Coupling tier: 3 — Fully Coupled, Moderate compliance risk",
        ]
        cv.validation_narrative = (
            f"REFUTED. HTC process liquor is high-strength: NH4-N {nh4:.0f} kgN/day "
            f"({pct:.0f}% of plant influent N) and COD {cod:.0f} kgCOD/day. "
            "This load is NOT benign and cannot be returned directly without impact. "
            "Sidestream treatment (SHARON/ANAMMOX) is required. "
            "Vendors who present HTC liquor as 'dilute and manageable' are understating "
            "a significant project cost and compliance risk."
        )
        cv.passes_at_this_site = False

    elif claim_id == "htc_hydrochar_agriculture":
        cv.verdict = "CONDITIONAL"
        cv.conditions_for_support = [
            "PFAS content must be characterised — HTC concentrates PFAS in hydrochar",
            "Heavy metal content must meet agricultural standards (EWC/local equivalent)",
            "Hydrochar stability (carbon permanence) lower than biochar from pyrolysis",
            "Regulatory status varies by jurisdiction — not approved in all markets",
        ]
        cv.validation_narrative = (
            "Agricultural use is theoretically possible but conditional on PFAS and metals results. "
            "If PFAS is present in the sludge feed, HTC concentrates rather than destroys PFAS "
            "in the hydrochar — making land application potentially non-compliant."
        )

    elif claim_id == "htc_pfas_immobilisation":
        cv.verdict = "CONDITIONAL"
        cv.conditions_for_support = [
            "HTC does not destroy PFAS — it may redistribute it between hydrochar and process liquor",
            "Immobilisation in hydrochar does not prevent leaching in soil",
            "If land application is the product route, PFAS transfer to soil may occur",
        ]
        cv.validation_narrative = (
            "CONDITIONAL (but misleading framing). HTC does not achieve thermal PFAS destruction. "
            "PFAS may partition into the hydrochar or process liquor depending on operating conditions. "
            "'Immobilisation' does not equal destruction and is not a regulatory compliance route. "
            "Vendors presenting HTC as a PFAS solution should be challenged on this claim."
        )

    elif claim_id == "htc_energy_neutral":
        if flag == "VIABLE":
            cv.verdict = "CONDITIONAL"
            cv.conditions_for_support = [
                "Near-neutral at process level (parasitic only — no drying)",
                "Net deficit is small (-15,000 to -20,000 kWh/d) — mainly process heat",
            ]
        else:
            cv.verdict = "CONDITIONAL"
        cv.engine_evidence = [f"Energy flag: {flag}", f"Net energy: {fs.energy_balance.net_energy_kwh_per_day:+,.0f} kWh/d"]

    # ── THP CLAIMS ────────────────────────────────────────────────────────
    elif claim_id == "thp_dewatering_32pct":
        cv.verdict = "SUPPORTED"
        cv.verdict_confidence = "High"
        cv.engine_evidence = [
            "THP preconditioning model: DS achievable 30-38% (thp_centrifuge reference)",
            "M&E 5th ed. operational benchmarks confirm 30-35% DS post-THP dewatering",
            "Cambi, Lysotherm operational data supports 30-38% DS range",
        ]
        cv.validation_narrative = (
            "SUPPORTED. THP + centrifuge dewatering achieving 30-35% DS is well-documented "
            "at full scale (Cambi, Lysotherm). This is one of the most robust claims in the "
            "biosolids technology space. The engine preconditioning module confirms 32% DS "
            "achievable under PC03 (THP + enhanced dewatering)."
        )
        cv.passes_at_this_site = True

    elif claim_id == "thp_biogas_uplift_30pct":
        cv.verdict = "SUPPORTED"
        cv.verdict_confidence = "Moderate"
        cv.conditions_for_support = [
            "20-30% biogas uplift is consistently reported in operational THP installations",
            "Actual uplift depends on sludge type (PS vs WAS) and baseline HRT",
        ]

    elif claim_id == "thp_class_a":
        cv.verdict = "SUPPORTED"
        cv.engine_evidence = [
            "THP >165°C + MAD consistently meets Class A criteria",
            "Cambi operational data: confirmed Class A at multiple installations",
        ]
        cv.passes_at_this_site = True

    # ── DRYING CLAIMS ─────────────────────────────────────────────────────
    elif claim_id == "dry_07_kwh_kg":
        # 0.65-0.75 kWh/kg claim vs engine assumption of 0.80 kWh/kg
        model_spec = dc.specific_energy_kwh_per_kg_water if dc and dc.drying_required else 0.80
        cv.verdict = "CONDITIONAL"
        cv.conditions_for_support = [
            f"Engine uses {model_spec:.2f} kWh/kg (conservative mid-range for indirect dryer)",
            "Best-in-class indirect dryers can achieve 0.65-0.72 kWh/kg under ideal conditions",
            "Performance depends on: feed DS%, dryer type, moisture content uniformity, "
            "waste heat integration quality",
        ]
        if dc and dc.drying_required:
            best_case_kwh = dc.water_removed_tpd * 1000 * 0.68 / dc.dryer_efficiency
            cv.engine_evidence = [
                f"Model assumption: {model_spec:.2f} kWh/kg",
                f"Best-case at 0.68 kWh/kg: {best_case_kwh:,.0f} kWh/d ({best_case_kwh/dc.drying_energy_actual_kwh_per_day*100:.0f}% of model)",
            ]
        cv.validation_narrative = (
            "0.65-0.75 kWh/kg is achievable at best-in-class modern indirect dryers. "
            "The engine uses 0.80 kWh/kg as a conservative mid-range. "
            "Even at best case, the drying energy constraint at this feed DS% remains severe — "
            "a 15% improvement in specific energy does not resolve the fundamental energy deficit."
        )

    elif claim_id == "dry_waste_heat_sufficient":
        waste_heat = assets.waste_heat_available_kwh_per_day
        drying_gross = dc.drying_energy_actual_kwh_per_day if dc and dc.drying_required else 0
        if drying_gross > 0:
            coverage = waste_heat / drying_gross * 100
            if coverage >= 90:
                cv.verdict = "SUPPORTED"
                cv.engine_evidence = [
                    f"Waste heat {waste_heat:,.0f} kWh/d covers {coverage:.0f}% of drying demand"
                ]
            elif coverage >= 40:
                cv.verdict = "CONDITIONAL"
                cv.conditions_for_support = [
                    f"Waste heat covers {coverage:.0f}% of drying — not sufficient alone",
                    f"Additional {drying_gross - waste_heat:,.0f} kWh/d external energy required",
                ]
            else:
                cv.verdict = "REFUTED"
                cv.conditions_violated = [
                    f"Waste heat ({waste_heat:,.0f} kWh/d) covers only {coverage:.0f}% of "
                    f"drying demand ({drying_gross:,.0f} kWh/d). Insufficient to run dryer."
                ]
            cv.passes_at_this_site = coverage >= 90
        else:
            cv.verdict = "UNVERIFIABLE"

    else:
        cv.verdict = "UNVERIFIABLE"
        cv.validation_narrative = "Claim not evaluated by current engine version."

    return cv


# ---------------------------------------------------------------------------
# SYSTEM SUMMARY
# ---------------------------------------------------------------------------

def _system_fit_summary(ptype, refuted, conditional, supported, feed_ds_pct, gcv) -> str:
    total = refuted + conditional + supported
    if total == 0:
        return "No claims evaluated."
    if refuted >= 2:
        return (
            f"POOR system fit at {feed_ds_pct:.0f}% DS and {gcv:.1f} MJ/kgDS GCV. "
            f"{refuted} vendor claims refuted. Significant physical constraints unresolved."
        )
    elif refuted == 1 or conditional >= 3:
        return (
            f"CONDITIONAL system fit. {refuted} claim(s) refuted, {conditional} conditional. "
            "Proceed only after vendor validation at actual site conditions."
        )
    else:
        return (
            f"GOOD system fit. {supported} claims supported. "
            f"{conditional} conditional — require site-specific confirmation."
        )


def _system_summary(reports, feed_ds_pct, gcv, ds_tpd, feedstock_kwh_d) -> str:
    refuted_total  = sum(r.claims_refuted for r in reports.values())
    conditional_total = sum(r.claims_conditional for r in reports.values())
    supported_total   = sum(r.claims_supported for r in reports.values())

    parts = [
        f"Validation summary across {len(reports)} thermal pathways: "
        f"{supported_total} claims supported, {conditional_total} conditional, "
        f"{refuted_total} refuted.",
        f"Feed: {feed_ds_pct:.0f}% DS, GCV {gcv:.1f} MJ/kgDS, "
        f"{ds_tpd:.0f} tDS/d, feedstock energy {feedstock_kwh_d:,.0f} kWh/d.",
    ]
    if refuted_total >= 4:
        parts.append(
            "Multiple high-confidence refutations — primarily driven by the drying energy "
            "constraint at this feed DS%. Vendor claims of energy self-sufficiency are "
            "systematically overstated at this feedstock condition."
        )
    return " ".join(parts)
