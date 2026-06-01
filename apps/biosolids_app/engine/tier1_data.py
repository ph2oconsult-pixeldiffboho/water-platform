"""
engine/tier1_data.py
BioPoint V1 — Tier 1 Report Data Assembly & Gate Checking.
ph2o Consulting — v25B02
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple


# ── Regulatory context registry ───────────────────────────────────────────

REGULATORY_CONTEXTS = {
    "epa_vic": {
        "label":       "EPA Victoria",
        "class_a_req": "EPA Victoria Publication 891.4 (2004) requires Class A biosolids "
                       "for unrestricted land application. Class B permits restricted "
                       "application only. THP operating at 165°C for minimum 20 minutes is expected to support "
                       "Class A classification, subject to process validation, "
                       "pathogen verification, and EPA Victoria acceptance "
                       "under Publication 891.4 (2004). Not a guarantee of compliance.",
        "pfas_note":   "EPA Victoria Interim Position Statement on PFAS (2021) applies. "
                       "Biosolids from sites with PFAS-impacted influent require "
                       "characterisation and may require ITS destruction pathway.",
        "n_discharge": "EPA Victoria discharge licence conditions apply to centrate "
                       "return liquor. Sidestream treatment may be required if TKN "
                       "consent conditions are tight.",
        "stockpile":   "EPA Victoria requires 3-year stockpiling for Class B biosolids "
                       "before land application — Class A eliminates this requirement.",
    },
    "sydney_water": {
        "label":       "Sydney Water / NSW EPA",
        "class_a_req": "NSW EPA Biosolids Guidelines (2000, updated 2022) require Grade A "
                       "biosolids for unrestricted land application. Time-temperature "
                       "treatment (THP equivalent) achieves Grade A classification.",
        "pfas_note":   "NSW EPA PFAS Management Framework applies. Sites with known PFAS "
                       "contamination in catchment require biosolids PFAS characterisation.",
        "n_discharge": "NSW EPA licence conditions and POEO Act discharge limits apply. "
                       "Centrate TN loads should be assessed against licence headroom.",
        "stockpile":   "NSW Grade B biosolids require storage management plan. "
                       "Grade A allows unrestricted beneficial reuse.",
    },
    "sa_water": {
        "label":       "SA Water / EPA South Australia",
        "class_a_req": "EPA SA Biosolids Guidelines require Class A equivalence for "
                       "unrestricted beneficial reuse. Thermal hydrolysis or equivalent "
                       "pathogen reduction technology required.",
        "pfas_note":   "EPA SA PFAS Management Policy applies. Biosolids PFAS assessment "
                       "required for sites with potential PFAS sources in catchment.",
        "n_discharge": "EPA SA Environment Protection (Water Quality) Policy applies. "
                       "Centrate nitrogen management plan may be required.",
        "stockpile":   "Class B biosolids require restricted application and management plan.",
    },
    "wa_water": {
        "label":       "Water Corporation WA / DWER",
        "class_a_req": "DWER Biosolids Management Policy requires Grade A equivalent "
                       "for unrestricted land application. THP is accepted as a "
                       "proven Grade A pathway.",
        "pfas_note":   "DWER PFAS Management Framework applies. Biosolids from PFAS-impacted "
                       "catchments require characterisation before beneficial reuse.",
        "n_discharge": "DWER licence conditions apply to return liquor discharges. "
                       "Nitrogen load assessment required against licence.",
        "stockpile":   "Grade B biosolids require management plan and restricted application.",
    },
    "nz": {
        "label":       "Watercare / NZ EPA",
        "class_a_req": "NZ Biosolids Guidelines (WasteMINZ 2022) require Grade A "
                       "classification for unrestricted land application. "
                       "THP achieves Grade A via Log 6 pathogen reduction criteria.",
        "pfas_note":   "NZ EPA PFAS guidelines under development (2024). "
                       "Precautionary PFAS assessment recommended for catchments "
                       "with industrial or fire-fighting foam sources.",
        "n_discharge": "RMA consenting conditions apply to return liquor nitrogen. "
                       "Sidestream treatment may be required under water quality objectives.",
        "stockpile":   "Grade B biosolids require consent conditions and restricted use.",
    },
    "qld_des": {
        "label":       "Queensland DES (Dept. of Environment and Science)",
        "class_a_req": "Queensland Environmental Protection Act 1994 and associated guidelines "
                       "apply. Class A equivalent required for unrestricted beneficial use. "
                       "THP time-temperature conditions expected to achieve this, "
                       "subject to validation and DES acceptance.",
        "pfas_note":   "Queensland DES PFAS Management Framework applies. "
                       "Biosolids from catchments with known PFAS sources require "
                       "characterisation per DES PFAS guidelines for land application.",
        "n_discharge": "Queensland DES environmental authority conditions apply. "
                       "Centrate TN return loads to be assessed against licence headroom "
                       "and nutrient management plan requirements.",
        "stockpile":   "Queensland biosolids management requirements apply. "
                       "Confirm Class A/B land application conditions with DES.",
    },
    "custom": {
        "label":       "Custom / Specify",
        "class_a_req": "Regulatory requirements to be confirmed with the relevant authority. "
                       "Class A or equivalent pathogen classification requirement assumed.",
        "pfas_note":   "PFAS regulatory position to be confirmed with relevant authority.",
        "n_discharge": "Discharge licence conditions to be confirmed.",
        "stockpile":   "Biosolids management requirements to be confirmed.",
    },
}

CAPEX_BANDS = {
    "base":        ("Minimal",      "No new capital required — operational optimisation only.",        1),
    "recup":       ("Low",          "Equipment upgrade only — centrifuge + polymer system.",           2),
    "solidstream": ("Moderate-High","New THP equipment, boiler, centrifuges, civil works.",            3),
    "pre_thp":     ("High",         "New THP plant, steam boiler, building, major civil works.",       4),
    "expansion":   ("Very High",    "SolidStream THP + new 8,000 m³ digester — highest capital scope.", 4),
}
CAPEX_STARS = {1: "★☆☆☆", 2: "★★☆☆", 3: "★★★☆", 4: "★★★★"}
# Note: expansion uses rank 4 (Very High) — same stars as pre_thp but label differs


# ── Data gate ─────────────────────────────────────────────────────────────

@dataclass
class GateResult:
    passed:         bool
    missing:        List[str] = field(default_factory=list)
    warnings:       List[str] = field(default_factory=list)
    available:      Dict[str, bool] = field(default_factory=dict)


def check_data_gate(ss: dict) -> GateResult:
    """
    Hard gate: check all mandatory data is present.
    Returns GateResult with passed=True only if all mandatory items exist.
    """
    missing  = []
    warnings = []
    avail    = {}

    # ── Mandatory: MAD Analyser ───────────────────────────────────────────
    # MAD considered run if: widget keys exist (page visited + widgets rendered),
    # OR mad_result saved, OR cmp_result exists (comparison implies MAD was run)
    mad_run = (
        any(k in ss for k in ["mad_psV", "mad_psDS", "mad_psTS", "mad_result",
                              "mad_inputs"])
        or "cmp_result" in ss
    )
    if not mad_run:
        missing.append("MAD Analyser has not been run — navigate to 🔬 MAD Analyser "
                        "and run at least one configuration.")
    avail["mad"] = mad_run

    # ── Mandatory: Config Comparison ─────────────────────────────────────
    cmp_run = "cmp_result" in ss and ss["cmp_result"] is not None
    if not cmp_run:
        missing.append("Config Comparison has not been run — navigate to ⚖️ Config "
                        "Comparison and run all four configurations.")
    avail["comparison"] = cmp_run

    # ── Mandatory: plant inputs (from MAD or comparison) ─────────────────
    has_inputs = any(k in ss for k in ["cmp_ps_ds", "mad_psDS", "cmp_result"])
    if not has_inputs:
        missing.append("Plant feed data not found — run MAD Analyser or Config Comparison "
                        "to populate site inputs.")
    avail["inputs"] = has_inputs

    # ── Optional sections ─────────────────────────────────────────────────
    avail["pathway_rankings"] = "pathway_results" in ss
    avail["drying"]           = "drying_result"   in ss
    avail["its_pfas"]         = "its_result"       in ss
    avail["pyrolysis"]        = "pyrolysis_result" in ss
    avail["carbon_ghg"]       = "carbon_result"    in ss
    avail["sankey"]           = "cmp_result"       in ss  # sankey uses same data

    # ── Warnings for missing optional sections ────────────────────────────
    optional_map = {
        "pathway_rankings": ("Pathway Rankings",  "📊 Pathway Rankings"),
        "drying":           ("Drying & Coupling", "🔥 Drying & Coupling"),
        "its_pfas":         ("ITS & PFAS",        "🛡️ ITS & PFAS"),
        "pyrolysis":        ("Pyrolysis",          "📈 Pyrolysis Envelope"),
        "carbon_ghg":       ("Carbon & GHG",       "🌍 Carbon & GHG"),
    }
    missing_optional = []
    for key, (label, page) in optional_map.items():
        if not avail[key]:
            missing_optional.append(f"{label} ({page})")

    if missing_optional:
        warnings.append(
            "The following optional analyses have not been run and will be omitted "
            "from the report: " + "; ".join(missing_optional) + ". "
            "Run these pages before generating if you want full coverage."
        )

    # Config comparison completeness check
    if cmp_run:
        result = ss["cmp_result"]
        if len(result.included_ids) < 3:
            warnings.append(
                f"Config Comparison only includes {len(result.included_ids)} configuration(s). "
                "For a complete Tier 1 assessment all four configurations should be compared. "
                "Re-run with Base Case, Recup, Pre-THP and SolidStream all selected."
            )

    return GateResult(
        passed   = len(missing) == 0,
        missing  = missing,
        warnings = warnings,
        available= avail,
    )


# ── Report data assembly ──────────────────────────────────────────────────

@dataclass
class Tier1ReportData:
    # Report metadata
    project_name:    str = "BioPoint Analysis"
    prepared_by:     str = "ph2o Consulting"
    prepared_for:    str = ""
    project_number:  str = ""
    revision:        str = "A"
    regulatory_key:  str = "epa_vic"
    regulatory:      dict = field(default_factory=dict)

    # Plant inputs (from MAD session state)
    ps_ds_tpd:      float = 0.0
    was_ds_tpd:     float = 0.0
    ps_ts_pct:      float = 4.0
    was_ts_pct:     float = 4.0
    ps_vs_pct:      float = 75.0
    was_vs_pct:     float = 70.0
    ps_n_pct:       float = 3.0
    was_n_pct:      float = 8.5
    ps_volume_m3:   float = 0.0
    was_volume_m3:  float = 0.0
    plant_tkn_kgd:  float = 500.0
    n2o_ef:         float = 0.010  # N2O emission factor kg N2O-N/kg N applied (IPCC default)
    # PFAS site characterisation inputs
    pfas_risk_level:      str   = "unknown"  # unknown / low / medium / high / critical
    pfas_land_app_viable: bool  = True       # can biosolids still be land-applied?
    pfas_ng_per_g_ds:     float = 0.0        # total PFAS in biosolids ng/g DS (0=not tested)
    pfas_catchment_risk:  str   = "unknown"  # catchment PFAS risk: unknown/low/medium/high

    # MAD result (single config — from MAD Analyser page)
    mad_result:     Any = None
    mad_inputs:     dict = field(default_factory=dict)
    mad_pretreat:   str = "none"

    # Comparison result (all configs)
    cmp_result:     Any = None

    # Optional analyses
    pathway_results: Any = None
    drying_result:   Any = None
    its_result:      Any = None
    pyrolysis_result:Any = None
    carbon_result:   Any = None

    # Data availability
    available:      Dict[str, bool] = field(default_factory=dict)

    # Report config
    include_sankey:  bool = True
    client_context:  str  = ""    # free-text project background


def assemble_report_data(ss: dict, report_cfg: dict) -> Tier1ReportData:
    """Assemble Tier1ReportData from Streamlit session state."""

    reg_key = report_cfg.get("regulatory_key", "epa_vic")

    d = Tier1ReportData(
        project_name   = report_cfg.get("project_name",   ss.get("cmp_project",      ss.get("mad_project_name", "BioPoint Analysis"))),
        prepared_by    = report_cfg.get("prepared_by",    ss.get("cmp_prepby",        ss.get("mad_prepared_by",  "ph2o Consulting"))),
        prepared_for   = report_cfg.get("prepared_for",   ""),
        project_number = report_cfg.get("project_number", ""),
        revision       = report_cfg.get("revision",       "A"),
        regulatory_key = reg_key,
        regulatory     = REGULATORY_CONTEXTS.get(reg_key, REGULATORY_CONTEXTS["custom"]),
        client_context = report_cfg.get("client_context", ""),
    )

    # Plant inputs — prefer comparison inputs, fall back to MAD session state
    d.ps_ds_tpd    = ss.get("cmp_ps_ds",  ss.get("mad_psDS",  6.0))
    d.was_ds_tpd   = ss.get("cmp_was_ds", ss.get("mad_wasDS", 4.0))
    d.ps_ts_pct    = ss.get("cmp_ps_ts",  ss.get("mad_psTS",  4.0))
    d.was_ts_pct   = ss.get("cmp_was_ts", ss.get("mad_wasTS", 4.0))
    d.ps_vs_pct    = ss.get("cmp_ps_vs",  ss.get("mad_psVS",  75.0))
    d.was_vs_pct   = ss.get("cmp_was_vs", ss.get("mad_wasVS", 70.0))
    d.ps_n_pct     = ss.get("cmp_ps_n",   ss.get("mad_psN",   3.0))
    d.was_n_pct    = ss.get("cmp_was_n",  ss.get("mad_wasN",  8.5))
    d.ps_volume_m3 = ss.get("cmp_ps_vol", ss.get("mad_psV",   3000.0))
    d.was_volume_m3= ss.get("cmp_was_vol",ss.get("mad_wasV",  1200.0))
    d.plant_tkn_kgd= ss.get("cmp_plant_tkn", 500.0)
    d.n2o_ef       = float(report_cfg.get("n2o_ef", 0.010))

    # MAD result
    d.mad_result  = ss.get("mad_result")
    d.mad_inputs  = {k: ss[k] for k in ss if k.startswith("mad_")}
    d.mad_pretreat= ss.get("mad_pretreatment", "none")

    # Comparison result
    d.cmp_result  = ss.get("cmp_result")

    # Optional
    d.pathway_results = ss.get("pathway_results")
    d.drying_result   = ss.get("drying_result")
    d.its_result      = ss.get("its_result")
    d.pyrolysis_result= ss.get("pyrolysis_result")
    d.carbon_result   = ss.get("carbon_result")

    d.include_sankey  = report_cfg.get("include_sankey", True)

    # PFAS site characterisation
    d.pfas_risk_level     = report_cfg.get("pfas_risk_level",     "unknown")
    d.pfas_land_app_viable= bool(report_cfg.get("pfas_land_app_viable", True))
    d.pfas_ng_per_g_ds    = float(report_cfg.get("pfas_ng_per_g_ds",    0.0))
    d.pfas_catchment_risk = report_cfg.get("pfas_catchment_risk",  "unknown")

    d.available = {
        "mad":             d.mad_result   is not None,
        "comparison":      d.cmp_result   is not None,
        "pathway_rankings":d.pathway_results is not None,
        "drying":          d.drying_result   is not None,
        "its_pfas":        d.its_result      is not None,
        "pyrolysis":       d.pyrolysis_result is not None,
        "carbon_ghg":      d.carbon_result   is not None,
    }

    return d


# ── Pathway system ────────────────────────────────────────────────────────

# Pathway IDs and metadata — order determines display order in report
PATHWAY_DEFINITIONS = [
    {
        "id":        "energy",
        "label":     "Pathway A — Maximum Energy Recovery",
        "objective": "Maximise biogas yield and net electricity export. "
                     "Minimise grid electricity import.",
        "icon":      "⚡",
        "confidence":"high",   # engine can calculate this well at Tier 1
    },
    {
        "id":        "carbon",
        "label":     "Pathway B — Carbon Optimisation",
        "objective": "Maximise stable carbon to soil or long-term sequestration. "
                     "Minimise carbon released to atmosphere.",
        "icon":      "🌱",
        "confidence":"amber",  # Tier 1 screening — full Sankey in V2
    },
    {
        "id":        "nutrient",
        "label":     "Pathway C — Nutrient Recovery",
        "objective": "Maximise nitrogen and phosphorus recovered from centrate and cake. "
                     "Minimise nutrient return load to liquid treatment.",
        "icon":      "♻️",
        "confidence":"amber",  # Tier 1 screening — full fate engine in V2
    },
    {
        "id":        "pfas",
        "label":     "Pathway D — PFAS Resilience",
        "objective": "Select the pathway viable regardless of PFAS outcome. "
                     "Avoid lock-in to land application where PFAS risk is uncharacterised.",
        "icon":      "🛡️",
        "confidence":"high",
    },
]


@dataclass
class PathwayResult:
    """Result for a single strategic pathway."""
    pathway_id:         str
    label:              str
    icon:               str
    objective:          str
    confidence:         str          # high / amber / low
    recommended_id:     str          # config_id of recommended config for this pathway
    recommended_label:  str
    key_metric:         str          # the one number that drives this pathway
    rationale:          str          # 1–2 sentence explanation
    trade_offs:         str          # what is accepted/sacrificed
    critical_assumption:str          # the one assumption that could change this
    override:           bool = False # True if engineer manually overrode engine choice


@dataclass
class ThickeningUplift:
    """Quantified biogas and HRT gain from WAS pre-thickening alone."""
    was_ts_current_pct:  float   # current WAS feed TS%
    was_ts_target_pct:   float   # target TS% to meet HRT criterion
    was_hrt_current_d:   float   # current WAS HRT
    was_hrt_target_d:    float   # WAS HRT at target TS%
    hrt_criterion_d:     float   # adopted screening criterion
    biogas_current_m3d:  float   # biogas at current TS%
    biogas_target_m3d:   float   # biogas at target TS%
    biogas_uplift_m3d:   float   # absolute uplift
    biogas_uplift_pct:   float   # % uplift
    ts_meets_criterion:  bool    # does target TS% achieve HRT criterion?
    capex_note:          str     # qualitative capital note


@dataclass
class ConstraintChain:
    """Structured constraint chain for the recommendation section."""
    root_constraint:     str
    root_detail:         str
    secondary:           List[str]
    symptoms:            List[str]
    consequences:        List[str]
    intervention_note:   str
    thickening_uplift:   Optional[ThickeningUplift] = None


def _pathway_energy(configs, result) -> PathwayResult:
    """Maximum energy recovery pathway — highest net biogas/electricity."""
    defn = next(p for p in PATHWAY_DEFINITIONS if p["id"] == "energy")

    # Rank by net electricity export (or biogas if electricity not available)
    best = max(configs,
               key=lambda c: getattr(c, "net_elec_export_kwh_d",
                                     getattr(c, "biogas_m3_per_d", 0)))
    base = next((c for c in configs if c.config_id == "base"), None)
    bg_uplift = ""
    if base:
        bg_base  = getattr(base,  "biogas_m3_per_d", 0)
        bg_best  = getattr(best,  "biogas_m3_per_d", 0)
        if bg_base > 0:
            pct = (bg_best - bg_base) / bg_base * 100
            bg_uplift = f"+{pct:.0f}% biogas vs base ({bg_best:,.0f} m\u00b3/d)"

    # Capacity vs performance classifier
    cap_vs_perf = {
        "base":        "Baseline",
        "recup":       "Capacity enhancement",
        "solidstream": "Performance enhancement",
        "pre_thp":     "Performance enhancement",
        "expansion":   "Capacity + Performance",
    }.get(best.config_id, "Performance enhancement")

    return PathwayResult(
        pathway_id          = "energy",
        label               = defn["label"],
        icon                = defn["icon"],
        objective           = defn["objective"],
        confidence          = defn["confidence"],
        recommended_id      = best.config_id,
        recommended_label   = best.config_label,
        key_metric          = bg_uplift or f"Biogas: {getattr(best,'biogas_m3_d',0):,.0f} m³/d",
        rationale           = (
            f"{best.config_label} produces the highest biogas yield of all assessed "
            f"configurations ({cap_vs_perf}). Higher VS destruction delivers more methane "
            f"per tonne of feed, reducing grid electricity import and improving energy "
            f"self-sufficiency."
        ),
        trade_offs          = (
            "Higher biogas from THP raises Scope 1 fugitive CH4 risk if gas handling "
            "is inadequate. CAPEX and operational complexity are higher than baseline. "
            "Centrate NH4-N return load increases significantly."
        ),
        critical_assumption = (
            "Fugitive CH4 rate ≤1.5% of biogas CH4. Gas capture and flaring systems "
            "must be adequate — if not upgraded, net GHG benefit is reduced."
        ),
    )


def _pathway_carbon(configs, result) -> PathwayResult:
    """Carbon optimisation pathway — maximise stable carbon, minimise atmospheric loss."""
    defn = next(p for p in PATHWAY_DEFINITIONS if p["id"] == "carbon")

    # At Tier 1: proxy = highest VSR (more organic destruction = less residual carbon
    # to soil but more converted to CH4 captured). Best carbon outcome = high VSR
    # + thermal endpoint compatible (pyrolysis/HTL for biochar/biocrude).
    # For now: prefer configs with THP (higher VSR) and note thermal endpoint needed.
    thp_configs = [c for c in configs
                   if c.config_id in ("solidstream", "pre_thp", "expansion")]
    best = (max(thp_configs, key=lambda c: getattr(c, "vsr_pct", 0))
            if thp_configs else
            max(configs, key=lambda c: getattr(c, "vsr_pct", 0)))

    vsr = getattr(best, "vsr_pct", None)
    vsr_str = f"VSR {vsr:.0f}%" if vsr else "highest VSR of assessed configs"

    return PathwayResult(
        pathway_id          = "carbon",
        label               = defn["label"],
        icon                = defn["icon"],
        objective           = defn["objective"],
        confidence          = defn["confidence"],
        recommended_id      = best.config_id,
        recommended_label   = best.config_label,
        key_metric          = vsr_str + " — thermal endpoint study required",
        rationale           = (
            f"{best.config_label} achieves the highest volatile solids reduction, "
            f"converting more organic carbon to captured biogas (carbon to energy) "
            f"rather than residual biosolids. Combined with a thermal endpoint "
            f"(pyrolysis or HTL), carbon can be directed to biochar or biocrude "
            f"rather than landfill or atmosphere."
        ),
        trade_offs          = (
            "Higher VSR reduces carbon in biosolids — which reduces soil carbon "
            "sequestration potential from land application. The net carbon benefit "
            "depends on the thermal endpoint selected and whether biochar is produced. "
            "Full carbon Sankey analysis required (BioPoint V2)."
        ),
        critical_assumption = (
            "Carbon fate modelling is screening grade only. Full Carbon Fate Engine "
            "(Sankey diagrams tracking carbon to methane / atmosphere / biosolids / "
            "soil / biochar) is deferred to BioPoint V2. "
            "Thermal endpoint study is a prerequisite for this pathway."
        ),
    )


def _pathway_nutrient(configs, result) -> PathwayResult:
    """Nutrient recovery pathway — maximise N/P recovered, minimise return load."""
    defn = next(p for p in PATHWAY_DEFINITIONS if p["id"] == "nutrient")

    # At Tier 1: prefer configs with lower centrate return (separate digestion
    # produces higher centrate N but also enables struvite recovery more effectively).
    # Proxy: prefer THP (higher solubilisation = better struvite crystallisation
    # conditions) but note centrate load trade-off.
    # Without full nutrient fate data, use centrate_nh4_kg_per_d as the key metric.
    best_n = max(configs, key=lambda c: getattr(c, "centrate_nh4_kg_per_d", 0))
    # Highest centrate N = most N available for recovery (PN/A + struvite)
    n_load = getattr(best_n, "centrate_nh4_kg_per_d", None)
    n_str = f"{n_load:,.0f} kg NH4-N/d available for recovery" if n_load else ""

    return PathwayResult(
        pathway_id          = "nutrient",
        label               = defn["label"],
        icon                = defn["icon"],
        objective           = defn["objective"],
        confidence          = defn["confidence"],
        recommended_id      = best_n.config_id,
        recommended_label   = best_n.config_label,
        key_metric          = n_str + " (struvite + PN/A)",
        rationale           = (
            f"{best_n.config_label} produces the highest centrate NH4-N concentration, "
            f"creating the strongest conditions for struvite crystallisation and "
            f"partial nitritation/anammox (PN/A) treatment. "
            f"This converts a return-load liability into a recoverable resource — "
            f"struvite as fertiliser and nitrogen removed via PN/A rather than "
            f"burdening the liquid treatment train."
        ),
        trade_offs          = (
            "Higher centrate N requires investment in struvite crystallisation and/or "
            "PN/A reactor. Capital cost is additional to digestion configuration. "
            "Nutrient recovery revenue (~$2.7–3.2M/yr at ETP scale) partially offsets "
            "digestion OPEX savings. Full nutrient fate modelling required (BioPoint V2)."
        ),
        critical_assumption = (
            "Nutrient recovery economics are screening grade (±30%). "
            "Centrate characterisation (sampling campaign) required before sizing "
            "struvite or PN/A systems. Full Nutrient Fate Engine deferred to BioPoint V2."
        ),
    )


def _pathway_pfas(configs, result, pfas_risk="unknown") -> PathwayResult:
    """PFAS resilience pathway — viable regardless of PFAS outcome."""
    defn = next(p for p in PATHWAY_DEFINITIONS if p["id"] == "pfas")

    # PFAS resilience = prefer thermal endpoint compatible configurations.
    # At Tier 1: THP is PFAS-neutral (doesn't destroy PFAS but produces
    # a cake amenable to thermal treatment). Thermal endpoint (incineration,
    # pyrolysis, HTL) is the ultimate PFAS-resilient pathway.
    # Prefer configs that don't lock into land application.
    thp_configs = [c for c in configs
                   if c.config_id in ("solidstream", "pre_thp", "expansion")]
    best = thp_configs[0] if thp_configs else configs[0]

    risk_label = {
        "unknown":  "PFAS catchment risk uncharacterised — worst case assumed",
        "low":      "Low PFAS catchment risk — land application likely viable",
        "medium":   "Medium PFAS catchment risk — characterisation required",
        "high":     "High PFAS catchment risk — thermal endpoint strongly indicated",
        "critical": "Critical PFAS risk — thermal endpoint mandatory",
    }.get(pfas_risk, "PFAS risk uncharacterised")

    return PathwayResult(
        pathway_id          = "pfas",
        label               = defn["label"],
        icon                = defn["icon"],
        objective           = defn["objective"],
        confidence          = defn["confidence"],
        recommended_id      = best.config_id,
        recommended_label   = best.config_label,
        key_metric          = risk_label,
        rationale           = (
            f"{best.config_label} produces a dewatered cake with characteristics "
            f"suitable for thermal treatment (incineration, pyrolysis, or HTL) "
            f"if land application is constrained by PFAS. "
            f"This pathway avoids lock-in to land application and preserves strategic "
            f"flexibility as the PFAS regulatory position evolves."
        ),
        trade_offs          = (
            "Thermal treatment endpoint adds significant capital cost and operational "
            "complexity beyond the digestion configuration. The thermal treatment "
            "study (Tier 1) must be commissioned in parallel — it cannot wait until "
            "after the digestion decision is made."
        ),
        critical_assumption = (
            "PFAS characterisation of biosolids and catchment has not been completed. "
            "Until characterised, land application viability is unknown. "
            "The PFAS Resilience pathway is recommended where characterisation is "
            "absent or where catchment risk is medium or above."
        ),
    )


def compute_pathways(d: "Tier1ReportData",
                     overrides: Optional[Dict[str, str]] = None) -> List[PathwayResult]:
    """
    Compute all four strategic pathways from comparison results.
    overrides: dict of pathway_id -> config_id to manually override engine choice.
    Returns list of PathwayResult in display order.
    """
    if not d.cmp_result:
        return []

    result  = d.cmp_result
    configs = [result.configs[k] for k in result.included_ids]
    overrides = overrides or {}

    pathways = [
        _pathway_energy(configs, result),
        _pathway_carbon(configs, result),
        _pathway_nutrient(configs, result),
        _pathway_pfas(configs, result, pfas_risk=d.pfas_risk_level),
    ]

    # Apply engineer overrides
    for pw in pathways:
        if pw.pathway_id in overrides:
            override_id = overrides[pw.pathway_id]
            if override_id in result.configs:
                pw.recommended_id    = override_id
                pw.recommended_label = result.configs[override_id].config_label
                pw.override          = True

    return pathways


def _compute_thickening_uplift(d: "Tier1ReportData",
                               hrt_criterion: float = 15.0) -> Optional[ThickeningUplift]:
    """
    Calculate the biogas and HRT gain from WAS pre-thickening alone.
    Uses Mangere-calibrated first-order kinetics (k_PS=0.18/d, k_WAS=0.08/d).
    This isolates the thickening intervention from architecture or technology changes.
    """
    from math import exp
    if d.was_ds_tpd <= 0 or d.was_ts_pct <= 0 or d.was_volume_m3 <= 0:
        return None

    # Mangere-calibrated kinetics (full-scale validated)
    k_ps, k_was       = 0.18, 0.08
    vsrmax_ps         = 0.60
    vsrmax_was        = 0.50
    gas_yield_nm3_kgVS= 0.995   # Nm³/kg VS destroyed (Mangere calibration)

    def _was_hrt(was_ts_pct: float) -> float:
        """WAS hydrolysis HRT at a given feed TS%."""
        was_flow_m3d = (d.was_ds_tpd / (was_ts_pct / 100)) * 1000 / 1000
        # was_ds_tpd in t/d, TS% fraction → volume in m³/d
        was_flow_m3d = d.was_ds_tpd / (was_ts_pct / 100)
        return d.was_volume_m3 / max(was_flow_m3d, 1e-9)

    def _biogas(was_ts_pct: float) -> float:
        """Screening biogas estimate at a given WAS feed TS%."""
        ps_flow   = d.ps_ds_tpd / (d.ps_ts_pct / 100)
        ps_hrt    = d.ps_volume_m3 / max(ps_flow, 1e-9)
        was_hrt   = _was_hrt(was_ts_pct)
        ps_vsr    = vsrmax_ps  * (1 - exp(-k_ps  * ps_hrt))
        was_vsr   = vsrmax_was * (1 - exp(-k_was * was_hrt))
        ps_vs_dest  = d.ps_ds_tpd  * (d.ps_vs_pct  / 100) * ps_vsr  * 1000  # kg/d
        was_vs_dest = d.was_ds_tpd * (d.was_vs_pct / 100) * was_vsr * 1000  # kg/d
        return (ps_vs_dest + was_vs_dest) * gas_yield_nm3_kgVS

    # Current state
    was_hrt_current = _was_hrt(d.was_ts_pct)
    biogas_current  = _biogas(d.was_ts_pct)

    # Find target TS% that meets HRT criterion (scan 0.5% steps up to 10%)
    target_ts = d.was_ts_pct
    meets      = False
    for ts_step in range(int(d.was_ts_pct * 10) + 1, 101):
        ts = ts_step / 10
        if _was_hrt(ts) >= hrt_criterion:
            target_ts = ts
            meets     = True
            break

    if not meets:
        target_ts = min(d.was_ts_pct * 2.0, 10.0)  # cap at 10% if criterion unreachable

    was_hrt_target = _was_hrt(target_ts)
    biogas_target  = _biogas(target_ts)
    uplift_m3d     = biogas_target - biogas_current
    uplift_pct     = uplift_m3d / max(biogas_current, 1) * 100

    # CAPEX note based on magnitude of TS% step
    ts_step = target_ts - d.was_ts_pct
    if ts_step <= 1.0:
        capex_note = (f"Low capital — target TS% increase of {ts_step:.1f} percentage points "
                      f"achievable by thickener optimisation or polymer dosing adjustment. "
                      f"No new major equipment likely required.")
    elif ts_step <= 2.0:
        capex_note = (f"Low-moderate capital — {ts_step:.1f} percentage point TS% increase "
                      f"may require gravity belt thickener (GBT) upgrade or additional "
                      f"thickening stage. Estimated order-of-magnitude: $0.5–3M.")
    else:
        capex_note = (f"Moderate capital — {ts_step:.1f} percentage point TS% increase "
                      f"likely requires new or upgraded thickening equipment. "
                      f"Estimated order-of-magnitude: $2–8M.")

    return ThickeningUplift(
        was_ts_current_pct  = d.was_ts_pct,
        was_ts_target_pct   = target_ts,
        was_hrt_current_d   = was_hrt_current,
        was_hrt_target_d    = was_hrt_target,
        hrt_criterion_d     = hrt_criterion,
        biogas_current_m3d  = biogas_current,
        biogas_target_m3d   = biogas_target,
        biogas_uplift_m3d   = uplift_m3d,
        biogas_uplift_pct   = uplift_pct,
        ts_meets_criterion  = meets,
        capex_note          = capex_note,
    )


def build_constraint_chain(d: "Tier1ReportData") -> ConstraintChain:
    """
    Build the constraint chain from plant data.
    Root → Secondary → Symptoms → Consequences.
    Now diagnoses WAS feed TS% as the root cause of HRT deficiency where applicable,
    and quantifies the biogas uplift from thickening alone (Mangere-calibrated kinetics).
    """
    result  = d.cmp_result
    base    = result.configs.get("base") if result else None
    hrt_was = getattr(base, "hrt_was_d", d.was_volume_m3 /
                      (d.was_ds_tpd / (d.was_ts_pct / 100) * 1000 / 86400) / 86400
                      if d.was_ds_tpd > 0 else 0)

    was_limited = hrt_was < 15.0

    # Compute thickening uplift regardless — shows opportunity even when not primary constraint
    tu = _compute_thickening_uplift(d, hrt_criterion=15.0)

    # Is the WAS TS% the root cause of the HRT deficiency?
    # Low TS% means high volumetric flow → short HRT despite adequate digester volume.
    # Mangere reference: 6.1%TS → 20d HRT. ETP: 4%TS → 11.7d HRT.
    # Flag as TS%-driven if current WAS TS% < 5.5% AND thickening alone could fix it.
    ts_is_root_cause = (
        was_limited
        and d.was_ts_pct < 5.5
        and tu is not None
        and tu.ts_meets_criterion
    )

    if was_limited:
        if ts_is_root_cause:
            root = "WAS Feed Concentration (TS%) Driving HRT Deficiency"
            root_det = (
                f"WAS hydrolysis HRT ({hrt_was:.1f} d) is below the 15 d minimum — but "
                f"the root cause is WAS feed concentration, not digester volume. "
                f"At {d.was_ts_pct:.1f}%TS, the WAS volumetric flow is "
                f"{d.was_ds_tpd/(d.was_ts_pct/100):,.0f} m³/d, consuming digester volume "
                f"faster than the kinetics require. "
                f"Mangere WWTP (NZ, full-scale calibration anchor) operates at 6.1%TS "
                f"and achieves 20 d HRT and 52% VSR from the same digester configuration. "
                f"Thickening WAS feed from {d.was_ts_pct:.1f}% to "
                f"{tu.was_ts_target_pct:.1f}%TS would extend WAS HRT to "
                f"{tu.was_hrt_target_d:.1f} d and add "
                f"{tu.biogas_uplift_m3d:,.0f} Nm³/d biogas (+{tu.biogas_uplift_pct:.1f}%) "
                f"— before any architecture or technology change."
            )
            secondary = [
                f"WAS HRT deficiency ({hrt_was:.1f} d < 15 d) — consequence of low feed "
                f"TS%, not insufficient digester volume.",
                "Co-digestion suppression — blended PS/WAS digestion compounds the kinetic "
                "constraint; PS lipid hydrolysis suppressed by slower WAS kinetics.",
                "PFAS uncertainty — biosolids cannot be characterised for thermal endpoint "
                "planning until digestion architecture is resolved.",
                "Centrate nitrogen load — inadequate WAS hydrolysis reduces ammonia release "
                "to centrate, masking the true return load.",
            ]
            symptoms = [
                f"WAS HRT = {hrt_was:.1f} d (minimum 15 d) — below criterion",
                f"VSR below potential — WAS at {d.was_ts_pct:.1f}%TS vs Mangere 6.1%TS reference",
                "Biogas yield lower than digester volume and DS load would suggest",
                "Dewatered cake TS% at lower end of achievable range",
            ]
            consequences = [
                "Thickening optimisation should be evaluated first — it is the lowest-capital "
                "intervention and may resolve the HRT constraint without new digesters.",
                "Any technology investment (THP, SolidStream) before resolving WAS TS% "
                "will underperform against vendor projections.",
                f"Biogas uplift from thickening alone ({tu.biogas_uplift_pct:.1f}%) may "
                f"exceed some technology uplift claims at lower capital cost.",
                "Capital expenditure risk: procurement before thickening assessment and "
                "BMP testing exposes the client to performance guarantee disputes.",
            ]
            intervention = (
                f"Step 1 — Evaluate WAS thickening improvement to {tu.was_ts_target_pct:.1f}%TS "
                f"({tu.capex_note}). "
                f"Step 2 — If thickening resolves HRT, evaluate Optimised MAD as baseline. "
                f"Step 3 — Only then evaluate architecture (separate digestion) and "
                f"technology (THP). "
                f"This is the correct intervention sequence: thickening → architecture → technology."
            )
        else:
            root = "WAS Kinetic HRT Deficiency"
            root_det = (
                f"WAS hydraulic retention time ({hrt_was:.1f} d) is below the minimum "
                f"required for adequate cell-mass hydrolysis (15 d). "
                f"This is not a digester volume problem — it is a volume allocation problem. "
                f"PS and WAS are competing for digester volume designed for a different split."
            )
            secondary = [
                "Co-digestion suppression — blended PS/WAS digestion compounds the WAS "
                "kinetic constraint; PS lipid hydrolysis suppressed by slower WAS kinetics.",
                "PFAS uncertainty — biosolids cannot be characterised for thermal endpoint "
                "planning until digestion architecture is resolved.",
                "Centrate nitrogen load — inadequate WAS hydrolysis reduces ammonia release "
                "to centrate, masking the true nitrogen return load.",
            ]
            symptoms = [
                f"WAS HRT = {hrt_was:.1f} d (minimum 15 d) — below criterion",
                "VS destruction rate below potential",
                "Lower biogas yield than plant capacity would suggest",
                "Dewatered cake TS% at lower end of achievable range",
            ]
            consequences = [
                "Any technology investment (THP, SolidStream) made before resolving WAS HRT "
                "will underperform against vendor projections.",
                "OPEX saving from advanced configurations is overstated until root constraint "
                "is resolved — the 22.5% separate digestion uplift requires ≥15 d WAS HRT.",
                "Biosolids strategy (land application vs thermal) cannot be finalised until "
                "PFAS characterisation is completed.",
                "Capital expenditure risk: procurement before BMP testing and HRT confirmation "
                "exposes the client to performance guarantee disputes.",
            ]
            intervention = (
                "Resolving the WAS HRT deficiency is the prerequisite for all other "
                "interventions. Options: volume redistribution (no capital), WAS pre-thickening "
                "(low capital), or physical digester separation (moderate capital). "
                "Evaluate Optimised MAD as the baseline — what does fixing the root cause "
                "achieve before new technology is introduced?"
            )
    else:
        root = "Digestion Configuration Sub-optimal"
        root_det = (
            f"WAS hydrolysis HRT ({hrt_was:.1f} d) meets the minimum criterion. "
            f"The primary constraint is digestion architecture — PS and WAS are "
            f"co-digested despite having fundamentally different hydrolysis kinetics, "
            f"suppressing overall system performance."
        )
        secondary = [
            "Co-digestion suppression — WAS proteins and ammonia suppress PS lipid "
            "hydrolysis yield when blended.",
            "Technology selection premature — digestion architecture should be optimised "
            "before advanced technology (THP) is introduced.",
        ]
        symptoms = [
            "Biogas yield below separate-digestion potential",
            "PS methane yield suppressed by blended WAS kinetics",
        ]
        consequences = [
            "THP investment may be solving the wrong problem — separation alone may "
            "recover most of the available uplift at lower capital cost.",
            "Site-specific BMP testing required to isolate mechanism from HRT effect.",
        ]
        intervention = (
            "Evaluate separate PS/WAS digestion as the primary intervention before "
            "committing to THP. BMP testing will distinguish the co-digestion suppression "
            "benefit from the HRT restoration benefit."
        )

    return ConstraintChain(
        root_constraint   = root,
        root_detail       = root_det,
        secondary         = secondary,
        symptoms          = symptoms,
        consequences      = consequences,
        intervention_note = intervention,
        thickening_uplift = tu,
    )


# ── Narrative helper functions ─────────────────────────────────────────────

def narrative_feed(d: Tier1ReportData) -> str:
    """Generate feed characterisation narrative paragraph."""
    ds_total = d.ps_ds_tpd + d.was_ds_tpd
    ps_frac  = d.ps_ds_tpd / ds_total * 100 if ds_total > 0 else 0
    vol_total= d.ps_volume_m3 + d.was_volume_m3
    hrt_ps   = d.ps_volume_m3 / (d.ps_ds_tpd / (d.ps_ts_pct/100) * 1000 / 86400) / 86400 \
               if d.ps_ds_tpd > 0 else 0

    return (
        f"The plant processes a combined dry solids load of {ds_total:.1f} tDS/day, "
        f"comprising {d.ps_ds_tpd:.1f} tDS/day primary sludge (PS, {ps_frac:.0f}% of feed) "
        f"and {d.was_ds_tpd:.1f} tDS/day waste activated sludge (WAS). "
        f"The combined digester volume is {vol_total:,.0f} m³ "
        f"({d.ps_volume_m3:,.0f} m³ PS / {d.was_volume_m3:,.0f} m³ WAS). "
        f"Feed volatile solids content is {d.ps_vs_pct:.0f}% DS for PS and "
        f"{d.was_vs_pct:.0f}% DS for WAS, reflecting {'a well-stabilised primary sludge' if d.ps_vs_pct < 65 else 'a high-VS primary sludge with good biogas potential'}. "
        f"WAS nitrogen content of {d.was_n_pct:.1f}% DS is "
        f"{'elevated and will drive significant centrate NH4-N return loads' if d.was_n_pct > 7 else 'within typical range'}."
    )


def narrative_comparison_executive(d: Tier1ReportData) -> str:
    """Generate executive summary paragraph from comparison results."""
    if not d.cmp_result:
        return "Config Comparison results not available."

    result = d.cmp_result
    winner = result.configs.get(result.winner_id) if result.winner_id else None
    is_tie = getattr(result, "is_tie", False)
    configs = [result.configs[k] for k in result.included_ids]

    # Find OPEX savings vs base
    base_cr = result.configs.get("base")
    winner_opex_saving = ""
    if base_cr and winner and winner.config_id != "base":
        saving = base_cr.opex_total_per_yr - winner.opex_total_per_yr
        if saving > 0:
            winner_opex_saving = (
                f"Compared with the base case, {winner.config_label} delivers "
                f"an estimated annual OPEX saving of ${saving/1000:.0f}k/yr, "
                f"primarily from reduced cake disposal volume. "
            )

    # Biosolids quality driver
    class_a_needed = True  # assumed — from regulatory context

    if is_tie:
        tie_labels = " and ".join(
            result.configs[k].config_label for k in getattr(result, "tie_ids", [])
        )
        rec_text = (
            f"The assessment identifies {tie_labels} as effectively tied on the "
            f"current driver weightings, with a weighted score of "
            f"{winner.weighted_score:.0f}/100 each. "
            f"Both configurations deliver Class A biosolids classification. "
            f"The preferred option should be determined by detailed site assessment "
            f"and vendor quotation."
        )
    elif winner:
        rec_text = (
            f"Based on the configured driver priorities, <b>{winner.config_label}</b> "
            f"is the recommended configuration with a weighted score of "
            f"{winner.weighted_score:.0f}/100. "
        )
        if winner.config_id == "solidstream":
            rec_text += (
                "SolidStream offers the best balance of dewatering performance, "
                "Class A pathogen compliance, and retrofit compatibility with "
                "existing digesters. The hot centrate recycle to digesters provides "
                "a heat integration benefit that improves energy self-sufficiency."
            )
        elif winner.config_id == "pre_thp":
            # Check if another config saves more OPEX — if so, explain the trade-off
            runner_cr = next((c for c in configs
                if c.config_id not in ("base", "pre_thp")
                and c.included), None)
            w_opex = getattr(winner, "opex_delta_whole_plant_per_yr",
                            winner.opex_delta_vs_base_per_yr)
            r_opex = getattr(runner_cr, "opex_delta_whole_plant_per_yr",
                            runner_cr.opex_delta_vs_base_per_yr) if runner_cr else 0
            opex_penalty = abs(r_opex - w_opex)
            rec_text += (
                "Pre-digestion THP delivers the highest biogas uplift and Class A "
                "biosolids classification. It is the preferred option where new "
                "digester capacity is being planned, as THP can be incorporated "
                "into the new facility scope. "
            )
            if runner_cr and r_opex < w_opex and opex_penalty > 100000:
                rec_text += (
                    f"<b>Note: {runner_cr.config_label} delivers a stronger "
                    f"OPEX outcome (${opex_penalty/1e6:.1f}M/yr additional saving). "
                    "Pre-THP is preferred despite this because the scoring model "
                    "places higher value on digester headroom, energy recovery, "
                    "and suitability where new digestion capacity is being planned. "
                    "The Board should confirm this trade-off explicitly.</b> "
                )
        elif winner.config_id == "recup":
            rec_text += (
                "Recuperative thickening offers the best risk-adjusted outcome — "
                "meaningful performance improvement at low capital cost and without "
                "the operational complexity of thermal hydrolysis."
            )
        elif winner.config_id == "expansion":
            rec_text += (
                "While Conventional AD remains the lowest-risk operational baseline, "
                "SolidStream with digester expansion achieves the highest weighted score "
                "under the configured project drivers. "
                "This configuration delivers Class A pathogen compliance, 38%DS dewatered "
                "cake, and a 22.7% biogas uplift, while the additional digester restores "
                "the hydraulic retention time above Cambi's 15-day minimum and provides "
                "capacity headroom for future throughput growth to 60,000 tDS/yr."
            )
        else:
            rec_text += (
                "While Conventional AD remains the lowest-risk operational baseline, "
                "the weighted assessment indicates a THP-based option would better "
                "serve the project drivers. "
                "Review driver weightings if the capital investment case is not supported."
            )
    else:
        rec_text = "Insufficient comparison data to determine recommendation."

    return rec_text + " " + winner_opex_saving


def narrative_ghg(d: Tier1ReportData) -> str:
    """Generate GHG narrative paragraph."""
    if not d.cmp_result:
        return ""

    configs = [d.cmp_result.configs[k] for k in d.cmp_result.included_ids]
    base_cr = d.cmp_result.configs.get("base")

    if not base_cr:
        return ""

    best_ghg = min(configs, key=lambda c: c.net_ghg_kg_co2e_per_d)
    worst_ghg= max(configs, key=lambda c: c.net_ghg_kg_co2e_per_d)

    return (
        f"From a greenhouse gas perspective, the base case produces "
        f"{base_cr.net_ghg_kg_co2e_per_d:,.0f} kg CO2e/day "
        f"({base_cr.net_ghg_t_co2e_per_yr:,.0f} t CO2e/yr). "
        f"THP configurations show higher net GHG at screening grade, primarily "
        f"because increased biogas production raises Scope 1 fugitive CH4 emissions "
        f"by more than the Scope 2 electricity export credit offsets. "
        f"This counterintuitive result is sensitive to the assumed fugitive CH4 rate "
        f"(1.5% of biogas CH4) — if gas capture and flaring controls are upgraded, "
        f"Scope 1a emissions reduce significantly and THP configurations improve "
        f"their GHG position relative to base case. "
        f"All GHG figures are screening-grade (±20%) and should not be used for "
        f"carbon accounting without independent verification."
    )


def narrative_next_steps(d: Tier1ReportData, reg_key: str) -> List[str]:
    """Return list of next-steps bullet points based on available data."""
    steps = []
    result = d.cmp_result
    winner_id = result.winner_id if result else None

    if winner_id in ("pre_thp", "solidstream"):
        steps.append(
            "Obtain vendor budgetary quotations for THP equipment scope "
            "(Cambi, Lysotherm, or equivalent) to develop Stage 2 CAPEX estimates."
        )
        steps.append(
            "Commission site-specific geotechnical and civil assessment to confirm "
            "THP building and foundation requirements."
        )
    if winner_id == "solidstream":
        steps.append(
            "Confirm minimum HRT adequacy (>15 days) across all digesters under "
            "peak loading scenarios before committing to SolidStream."
        )
    if d.available.get("its_pfas"):
        steps.append(
            "Progress PFAS characterisation of biosolids per "
            + d.regulatory.get("pfas_note", "relevant authority guidance") + "."
        )
    steps.append(
        "Assess centrate nitrogen return load against liquid treatment train "
        "TKN headroom and licence conditions."
    )
    steps.append(
        "Commission independent process modelling for pre-THP and SolidStream "
        "at site-specific conditions — vendor figures are conceptual and require "
        "independent engineer verification."
    )
    steps.append(
        "Assess sidestream NH4-N impact on ETP liquid treatment train — the increase "
        "from 3,164 to 4,645 kg NH4-N/day (SolidStream) requires assessment against "
        "TKN licence headroom and biological nutrient removal capacity."
    )
    steps.append(
        "Confirm site space availability for THP building footprint "
        "(approximately 29.5 m × 22.5 m from Cambi layout drawing, plus "
        "dewatering block 16.4 m × 12.3 m)."
    )
    steps.append(
        "Develop long-term thermal treatment business case — assess fluidised bed "
        "incineration and pyrolysis as the ultimate biosolids endpoint, "
        "consistent with client net zero objectives."  # "
        "to zero by 2035-2040 strategic objectives."
    )
    steps.append(
        f"Engage {d.regulatory.get('label', 'the relevant authority')} on Class A "
        "compliance timeline, requirements, and whether THP "
        "at 165\u00b0C for minimum 20 minutes will be accepted. "
        "Obtain in-principle position before committing to capital."
    )
    if winner_id in ("solidstream", "expansion"):
        steps.append(
            "Obtain THP vendor performance guarantee terms and pre-contract testing "
            "protocol. Confirm minimum HRT adequacy and digester capacity "
            "before committing to procurement."
        )
    steps.append(
        "Review driver weightings with the client and project engineer — update "
        "comparison if priorities change (regulatory deadline, budget, programme)."
    )
    return steps


# ── Calibration Library ───────────────────────────────────────────────────
# Full-scale operating reference cases for BioPoint screening validation.
# Source: Mangere WWTP (NZ) evidence package and associated THP investigations.
# Use these to validate model outputs against real plant performance before
# using BioPoint results for design or procurement decisions.

CALIBRATION_LIBRARY = {
    # ── Conventional MAD ──────────────────────────────────────────────────
    "mangere_conventional": {
        "description":    "Mangere WWTP conventional MAD — long-term operating baseline",
        "source":         "Hillis & Taylor, Ozwater\u201917; Mangere WWTP operating data",
        "plant":          "Mangere WWTP, Auckland, New Zealand",
        "technology":     "Conventional MAD (blended PS/WAS)",
        "total_tds_d":    165.0,
        "ps_tds_d":       105.0,
        "was_tds_d":      60.0,
        "feed_ts_pct":    6.1,
        "hrt_d":          20.0,
        "vsr_pct":        52.0,
        "biogas_nm3_d":   62_385,
        "cake_ds_pct":    None,   # not confirmed in operating data
        "nh4_n_kg_d":     3_118,
        "k_ps":           0.18,   # Mangere-calibrated (conservative vs literature 0.25)
        "k_was":          0.08,   # Mangere-calibrated (conservative vs literature 0.12)
        "confidence":     "high",
        "note": (
            "Validated against 5+ years of operating data. "
            "k values are more conservative than literature defaults (Bolzonella 2005; WEF MOP 8). "
            "At long HRT (>18d) both models converge; gap is largest at short HRT (<12d). "
            "BioPoint uses Mangere k values for conservative screening."
        ),
    },
    # ── THP — Full Hydrolysis ─────────────────────────────────────────────
    "mangere_2015_full_thp": {
        "description":    "Mangere WWTP 2015 THP mass balance (Cambi reference case)",
        "source":         "Cambi indicative mass balance for Mangere 2015",
        "plant":          "Mangere WWTP, Auckland, New Zealand",
        "technology":     "Full THP (Cambi) — all feed hydrolysed",
        "total_tds_d":    156.8,
        "ps_tds_d":       105.0,
        "was_tds_d":      60.0,
        "feed_ts_pct":    10.0,   # after pre-dewatering
        "hrt_d":          20.0,
        "vsr_pct":        55.7,
        "biogas_nm3_d":   63_151,
        "methane_nm3_d":  39_785,
        "cake_ds_pct":    30.0,
        "nh4_n_kg_d":     3_134,
        "steam_kg_h":     6_111,
        "confidence":     "high",
        "note": (
            "Key THP calibration anchor. "
            "Biogas uplift vs conventional: +1.2% (63,151 vs 62,385 Nm\u00b3/d). "
            "Primary benefit is cake DS improvement (30% vs ~22% conventional) and "
            "Class A pathogen classification — not primarily biogas. "
            "THP HRT-VSR saturation: VSR gains are rapid to ~10d HRT then flatten. "
            "Going from 10d to 20d adds only ~5% more VSR — diminishing returns above ~10d."
        ),
    },
    "mangere_2040_full_thp": {
        "description":    "Mangere WWTP 2040 full THP projection",
        "source":         "Mangere 2015 solids strategy — 2040 growth scenario",
        "plant":          "Mangere WWTP, Auckland, New Zealand",
        "technology":     "Full THP (Cambi) — future growth case",
        "total_tds_d":    148.0,
        "ps_tds_d":       84.0,
        "was_tds_d":      64.0,
        "feed_ts_pct":    10.0,
        "hrt_d":          23.0,
        "vsr_pct":        59.5,
        "biogas_nm3_d":   66_212,
        "methane_nm3_d":  41_714,
        "cake_ds_pct":    30.0,
        "nh4_n_kg_d":     3_423,
        "steam_kg_h":     5_132,
        "confidence":     "medium",   # modelled projection, not operating data
        "note": (
            "2040 growth scenario — higher WAS fraction, longer HRT. "
            "Note steam demand falls despite higher total load: "
            "lower PS fraction reduces steam demand per tDS. "
            "Confirms HRT-VSR saturation: VSR rises from 55.7% to 59.5% (+3.8pp) "
            "with HRT from 20d to 23d — diminishing returns clearly visible."
        ),
    },
    "mangere_2040_was_only": {
        "description":    "Mangere WWTP 2040 WAS-only THP scenario",
        "source":         "Mangere 2015 solids strategy — WAS-only option",
        "plant":          "Mangere WWTP, Auckland, New Zealand",
        "technology":     "WAS-only THP — primary sludge bypasses hydrolysis",
        "total_tds_d":    148.0,
        "ps_tds_d":       84.0,
        "was_tds_d":      64.0,
        "feed_ts_pct":    5.5,
        "hrt_d":          19.5,
        "vsr_pct":        56.7,
        "biogas_nm3_d":   64_948,
        "methane_nm3_d":  40_917,
        "cake_ds_pct":    30.0,
        "nh4_n_kg_d":     3_366,
        "confidence":     "medium",
        "note": (
            "WAS-only THP delivers 97.8% of the biogas of full THP "
            "(64,948 vs 66,212 Nm\u00b3/d) at lower steam demand. "
            "Relevant where PS fraction is dominant and full THP capital is hard to justify. "
            "BioPoint uses this as the SolidStream reference case basis."
        ),
    },
    # ── THP — Secondary-only ─────────────────────────────────────────────
    "malabar_was_only": {
        "description":    "Malabar WWTP WAS-only THP (secondary-stream only plant)",
        "source":         "Published performance data — Malabar WWTP",
        "plant":          "Malabar WWTP, Sydney, Australia",
        "technology":     "WAS-only THP (no primary sludge)",
        "total_tds_d":    140.0,
        "ps_tds_d":       0.0,
        "was_tds_d":      140.0,
        "hrt_d":          18.0,
        "vsr_pct":        51.0,
        "biogas_nm3_d":   42_292,
        "cake_ds_pct":    30.0,
        "nh4_n_kg_d":     3_788,
        "confidence":     "medium",
        "note": (
            "WAS-only plant — no primary sludge contribution to biogas. "
            "Lower VSR than blended plants (51% vs 55-57%) reflects absence of "
            "readily-degradable primary lipids. "
            "High NH4-N load per tDS confirms WAS-heavy feeds require "
            "sidestream treatment assessment."
        ),
    },
}

# ── THP HRT saturation constants (from model calibration) ─────────────────
# Based on THP screening model v0.2 calibrated against Mangere and Malabar data.
# Used by _compute_thickening_uplift() and report narrative.
THP_HRT_SATURATION = {
    "base_vsr_max":  0.555,   # VSR asymptote for full THP at reference conditions
    "k_thp":         0.27,    # saturation rate constant (per day)
    "sweet_spot_hrt":10.0,    # HRT beyond which VSR gains become marginal
    "note": (
        "THP VSR gains are rapid from 3-10d HRT, then flatten. "
        "Doubling HRT from 10d to 20d adds only ~3-5% additional VSR. "
        "Beyond ~10-12d HRT, longer digestion time reduces cake DS "
        "(dewaterability deteriorates through digestion) while VSR gains are minimal. "
        "The optimal THP HRT is typically 8-12d, not the 15-20d assumed for conventional MAD."
    ),
}


# ── THP Configuration Library ──────────────────────────────────────────────
# Full-scale reference KPIs per THP configuration mode.
# Sources: Thames Water, United Utilities, DC Water, Davyhulme, Ringsend, Mangere.

THP_CONFIG_LIBRARY = {
    "conventional_mad": {
        "label":              "Conventional MAD",
        "description":        "Blended PS/WAS mesophilic anaerobic digestion. No pre-treatment.",
        "reference_count":    "10,000+",
        "confidence":         "very_high",
        "vsr_range_pct":      (42, 55),
        "cake_ds_range_pct":  (20, 25),
        "steam_kg_per_tds":   0,
        "methane_nm3_per_tds":180,    # typical range 150-220
        "electricity_mwh_per_tds": 0.45,
        "olr_max_kg_vs_m3_d": 3.0,
        "complexity_score":   2,
        "complexity_factors": [
            "Standard mesophilic digesters",
            "No specialist systems required",
            "Well-understood O&M",
        ],
        "opex_premium_pct":   0,      # baseline
        "capex_premium_pct":  0,
    },
    "was_only_thp": {
        "label":              "WAS-only THP (SolidStream)",
        "description":        "Thermal hydrolysis of secondary stream only. PS bypasses THP.",
        "reference_count":    "5-10",
        "confidence":         "medium",
        "vsr_range_pct":      (52, 60),
        "cake_ds_range_pct":  (30, 35),
        "steam_kg_per_tds":   450,    # lower than full THP — WAS fraction only
        "methane_nm3_per_tds":210,
        "electricity_mwh_per_tds": 0.61,
        "olr_max_kg_vs_m3_d": 5.0,
        "complexity_score":   7,
        "complexity_factors": [
            "THP pressure vessels on WAS stream",
            "Hot centrate recycle system",
            "Boiler / steam generation",
            "Specialist O&M for thermal pressure systems",
        ],
        "opex_premium_pct":   25,
        "capex_premium_pct":  35,
    },
    "full_thp": {
        "label":              "Full THP (Conventional)",
        "description":        "All feed pre-dewatered and thermally hydrolysed before digestion.",
        "reference_count":    "100+",
        "confidence":         "high",
        "vsr_range_pct":      (52, 65),
        "cake_ds_range_pct":  (28, 35),
        "steam_kg_per_tds":   861,    # Davyhulme validated: 861 kg/tDS
        "methane_nm3_per_tds":259,    # Davyhulme validated: 259 Nm³/tDS
        "electricity_mwh_per_tds": 0.68,
        "olr_max_kg_vs_m3_d": 6.0,
        "complexity_score":   8,
        "complexity_factors": [
            "Full-stream pressure vessels and autoclave",
            "Steam boiler (gas-fired)",
            "High-pressure safety systems",
            "Specialist THP operators required",
            "Significant maintenance overhead",
        ],
        "opex_premium_pct":   35,
        "capex_premium_pct":  60,
        "calibration_anchor": "Davyhulme WWTP (United Utilities, UK): "
                              "steam 861 kg/tDS, methane 259 Nm³/tDS, cake 31.3%DS. "
                              "Thames Water fleet: VSR 52-65%, cake DS 35-45%.",
    },
    "intermediate_thp": {
        "label":              "Intermediate THP",
        "description":        "THP applied between two digestion stages. Higher VSR potential.",
        "reference_count":    "2-5",
        "confidence":         "low",
        "vsr_range_pct":      (60, 70),
        "cake_ds_range_pct":  (30, 36),
        "steam_kg_per_tds":   600,
        "methane_nm3_per_tds":280,
        "electricity_mwh_per_tds": 0.78,
        "olr_max_kg_vs_m3_d": 6.0,
        "complexity_score":   9,
        "complexity_factors": [
            "Two-stage digestion train",
            "Interstage THP pressure vessels",
            "Complex hydraulic routing",
            "Very limited reference plant experience",
        ],
        "opex_premium_pct":   45,
        "capex_premium_pct":  80,
    },
    "separate_digestion": {
        "label":              "Separate PS/WAS Digestion",
        "description":        "PS and WAS digested in separate dedicated digesters. No THP.",
        "reference_count":    "10-30",
        "confidence":         "medium",   # limited full-scale separate digestion data
        "vsr_range_pct":      (48, 58),
        "cake_ds_range_pct":  (20, 25),
        "steam_kg_per_tds":   0,
        "methane_nm3_per_tds":210,        # higher than blended due to PS optimisation
        "electricity_mwh_per_tds": 0.52,
        "olr_max_kg_vs_m3_d": 3.0,
        "complexity_score":   3,
        "complexity_factors": [
            "Two separate digestion trains",
            "Separate thickening for each stream",
            "Volume redistribution or new digesters",
        ],
        "opex_premium_pct":   10,
        "capex_premium_pct":  15,
    },
}

# ── Operational Complexity Scores ──────────────────────────────────────────
# Based on: boilers, pressure vessels, automation, maintenance, specialist ops.
# Scale: 1 (simple, standard O&M) to 10 (specialist, high-risk, complex).
# Sources: Thames Water O&M experience, Ringsend reports, industry consensus.

OPERATIONAL_COMPLEXITY = {
    "base":         {
        "score": 2,
        "label": "Low",
        "factors": ["Standard mesophilic digesters", "No specialist systems", "Well-understood O&M"],
        "note":  "Benchmark technology. Available skill sets in most utilities.",
    },
    "recup":        {
        "score": 3,
        "label": "Low-Moderate",
        "factors": ["Centrifuge upgrade", "Additional polymer dosing", "No new pressure systems"],
        "note":  "Marginal increase. Same operator competency as base case.",
    },
    "pre_thp":      {
        "score": 8,
        "label": "High",
        "factors": [
            "Full-stream pressure vessels and autoclaves",
            "Gas-fired steam boiler",
            "High-pressure safety systems (PED/PSSR compliance)",
            "Specialist THP maintenance regime",
            "Dedicated operator training programme required",
        ],
        "note":  "Thames Water and United Utilities report this as a major "
                 "operational step-change requiring 2-3 years to embed.",
    },
    "solidstream":  {
        "score": 7,
        "label": "High",
        "factors": [
            "WAS-stream THP pressure vessels",
            "Hot centrate recycle system",
            "Boiler / steam generation",
            "Specialist thermal system O&M",
        ],
        "note":  "Lower than full THP (PS stream bypasses). "
                 "Still requires specialist operators and safety systems.",
    },
    "separate":     {
        "score": 3,
        "label": "Low-Moderate",
        "factors": ["Two-train digestion management", "Separate stream monitoring"],
        "note":  "No new specialist technology. Manageable with existing operator competency.",
    },
    "separate_thp": {
        "score": 7,
        "label": "High",
        "factors": [
            "Separation infrastructure complexity",
            "WAS-stream THP pressure vessels",
            "Combined train management",
        ],
        "note":  "Combined complexity of separation and THP systems.",
    },
    "optimised_mad":{
        "score": 3,
        "label": "Low-Moderate",
        "factors": ["WAS pre-thickening equipment", "Polymer dosing optimisation"],
        "note":  "No new pressure systems. Lowest complexity uplift of any option.",
    },
}

# ── Digester Capacity Value Calculator ─────────────────────────────────────
# THP's primary benefit for most utilities is capacity intensification,
# not methane production. This is the most commonly cited THP justification
# in full-scale case studies (Thames, United Utilities, DC Water).

def compute_capacity_value(
    ds_total_tpd: float,
    ps_ts_pct: float,
    was_ts_pct: float,
    ps_ds_tpd: float,
    was_ds_tpd: float,
    digester_vol_m3: float,
    thp_feed_ds_pct: float = 10.0,
    target_hrt_conv_d: float = 18.0,
    target_hrt_thp_d: float = 20.0,
    capex_per_m3: float = 2000.0,
    growth_factor: float = 1.0,
) -> dict:
    """
    Compute digester capacity value from THP.

    Three outputs:
    1. Capacity intensification: additional tDS/day the existing digesters
       can handle at THP feed concentration vs conventional.
    2. Avoided digester volume: volume that would be needed at conv. AD feed
       concentration to achieve target HRT at current + growth DS load.
    3. Avoided CAPEX: financial value of avoided digester construction.

    References: Thames Water fleet, DC Water Blue Plains, United Utilities.
    """
    # Current hydraulic loading (conv AD feed concentration)
    q_ps_conv   = ps_ds_tpd  / max(ps_ts_pct  / 100.0, 1e-9)
    q_was_conv  = was_ds_tpd / max(was_ts_pct / 100.0, 1e-9)
    q_conv      = q_ps_conv + q_was_conv

    # THP hydraulic loading (all feed pre-dewatered to thp_feed_ds_pct)
    q_thp = ds_total_tpd / max(thp_feed_ds_pct / 100.0, 1e-9)

    # Current HRTs
    hrt_conv = digester_vol_m3 / max(q_conv, 1e-9)
    hrt_thp  = digester_vol_m3 / max(q_thp,  1e-9)

    # Capacity intensification: max DS at THP concentration for target HRT
    max_flow_thp   = digester_vol_m3 / target_hrt_thp_d
    max_ds_thp     = max_flow_thp * (thp_feed_ds_pct / 100.0)
    capacity_uplift_tpd = max(0.0, max_ds_thp - ds_total_tpd)

    # Growth scenario: volume needed at conv AD to handle ds * growth_factor
    ds_future = ds_total_tpd * growth_factor
    q_conv_future = (ds_future * ps_ds_tpd / max(ds_total_tpd,1) / max(ps_ts_pct/100,1e-9)
                    + ds_future * was_ds_tpd / max(ds_total_tpd,1) / max(was_ts_pct/100,1e-9))
    vol_needed_conv = q_conv_future * target_hrt_conv_d

    # Volume needed at THP for same growth
    q_thp_future    = ds_future / max(thp_feed_ds_pct / 100.0, 1e-9)
    vol_needed_thp  = q_thp_future * target_hrt_thp_d

    avoided_vol_m3  = max(0.0, vol_needed_conv - vol_needed_thp)
    avoided_vol_m3  = max(0.0, avoided_vol_m3 - max(0.0, vol_needed_thp - digester_vol_m3))
    # More precisely: additional volume THP avoids building vs conv AD
    extra_vol_conv  = max(0.0, vol_needed_conv - digester_vol_m3)
    extra_vol_thp   = max(0.0, vol_needed_thp  - digester_vol_m3)
    avoided_build_m3 = max(0.0, extra_vol_conv - extra_vol_thp)

    avoided_capex   = avoided_build_m3 * capex_per_m3

    # Equivalent digesters avoided (8,000m³ each as ETP reference)
    digester_unit_m3 = 8000.0
    digesters_avoided = avoided_build_m3 / digester_unit_m3

    return {
        "hrt_conv_d":             round(hrt_conv, 1),
        "hrt_thp_d":              round(hrt_thp,  1),
        "capacity_uplift_tpd":    round(capacity_uplift_tpd, 0),
        "capacity_uplift_pct":    round(capacity_uplift_tpd / max(ds_total_tpd,1) * 100, 0),
        "vol_needed_conv_m3":     round(vol_needed_conv, 0),
        "vol_needed_thp_m3":      round(vol_needed_thp,  0),
        "avoided_build_m3":       round(avoided_build_m3, 0),
        "digesters_avoided":      round(digesters_avoided, 1),
        "avoided_capex_aud":      round(avoided_capex, 0),
        "growth_factor":          growth_factor,
        "note": (
            "Capacity value is the primary THP justification at most full-scale "
            "plants (Thames Water, United Utilities, DC Water Blue Plains). "
            "Methane uplift is secondary. This calculation uses hydraulic intensification "
            f"from pre-dewatering ({thp_feed_ds_pct:.0f}%DS vs {(ps_ts_pct+was_ts_pct)/2:.1f}%DS "
            "blended feed) to show additional throughput capacity in existing digesters."
        ),
    }


# ── THP Configuration Library ─────────────────────────────────────────────
# Full-scale operating KPIs by THP mode.
# Source: Thames Water, United Utilities, DC Water, Davyhulme, Mangere, Ringsend.
# Use these for calibration and reference plant confidence scoring.

THP_CONFIG_LIBRARY = {
    "full_thp": {
        "label":         "Full THP (Cambi / Lysotherm)",
        "description":   "All feed thermally hydrolysed. Highest VSR and dewatering. "
                         "Highest steam demand and capital cost.",
        "hydrolysis_factor": 1.00,
        "vsr_range_pct": (52, 65),
        "cake_ds_range_pct": (28, 35),
        "steam_kg_per_tds": 861,        # Davyhulme reference
        "ch4_nm3_per_tds": 259,         # Davyhulme reference (WAS-heavy)
        "elec_mwh_per_tds": 0.68,       # Thames Water reference
        "olr_max_kg_vs_m3_d": 6.0,
        "capex_relative": 4,            # 1=lowest, 4=highest
        "references": [
            "Mangere WWTP NZ (20d HRT, 55.7% VSR, 63,151 Nm³/d)",
            "Davyhulme WWTW UK (steam 861 kg/tDS, CH4 259 Nm³/tDS, cake 31.3%)",
            "Thames Water Long Reach (cake 35-45% DS)",
            "DC Water Blue Plains (cake >29% DS)",
            "Ringsend WWTP IE (12%DS feed, 62% VSR, 34% cake DS)",
        ],
        "n_references": 100,
        "maturity": "Commercial — 100+ installations worldwide",
        "confidence": "high",
    },
    "was_only": {
        "label":         "WAS-only THP (Secondary stream)",
        "description":   "Secondary sludge only hydrolysed. PS bypasses THP. "
                         "Lower steam demand. Suitable where PS fraction is dominant.",
        "hydrolysis_factor": 0.88,
        "vsr_range_pct": (52, 60),
        "cake_ds_range_pct": (28, 33),
        "steam_kg_per_tds": 450,        # ~50% of full THP (WAS fraction only)
        "ch4_nm3_per_tds": None,        # site-specific
        "elec_mwh_per_tds": 0.61,       # Thames Water reference
        "olr_max_kg_vs_m3_d": 5.0,
        "capex_relative": 3,
        "references": [
            "Mangere 2040 WAS-only scenario (19.5d HRT, 56.7% VSR)",
            "Malabar WWTP Sydney (WAS-only, 51% VSR, 30% cake)",
        ],
        "n_references": 5,
        "maturity": "Commercial — limited references (3-5 full-scale)",
        "confidence": "medium",
    },
    "solidstream": {
        "label":         "SolidStream (WAS-only THP, hot centrate recycle)",
        "description":   "Cambi SolidStream: WAS hydrolysed, hot centrate recycled "
                         "to digester inlet for heat integration. Highest cake DS.",
        "hydrolysis_factor": 0.88,
        "vsr_range_pct": (54, 62),
        "cake_ds_range_pct": (36, 43),
        "steam_kg_per_tds": 420,
        "ch4_nm3_per_tds": None,
        "elec_mwh_per_tds": 0.65,
        "olr_max_kg_vs_m3_d": 5.0,
        "capex_relative": 3,
        "references": [
            "Amperverband WWTP Germany (40-43% cake DS confirmed)",
            "Cambi vendor data (38% DS guarantee basis)",
        ],
        "n_references": 3,
        "maturity": "Commercial — emerging (3 full-scale references)",
        "confidence": "medium",
    },
    "none": {
        "label":         "Conventional MAD",
        "description":   "Mesophilic anaerobic digestion, no pre-treatment. "
                         "Lowest capital and operational complexity.",
        "hydrolysis_factor": 0.0,
        "vsr_range_pct": (40, 55),
        "cake_ds_range_pct": (18, 25),
        "steam_kg_per_tds": 0,
        "ch4_nm3_per_tds": 220,         # typical range
        "elec_mwh_per_tds": 0.45,
        "olr_max_kg_vs_m3_d": 3.0,
        "capex_relative": 1,
        "references": ["10,000+ installations worldwide"],
        "n_references": 10000,
        "maturity": "Fully mature — universal reference base",
        "confidence": "high",
    },
}


# ── Operational Complexity Score ──────────────────────────────────────────
# Score 1–10 based on: boilers, pressure vessels, automation,
# maintenance frequency, specialist operator requirements, safety systems.
# Source: Thames Water operational assessment, Panter (AD fundamentals).

OPERATIONAL_COMPLEXITY = {
    "base":         {"score": 2, "label": "Low",
                     "notes": "Standard mesophilic AD. Proven technology, standard O&M."},
    "recup":        {"score": 3, "label": "Low-moderate",
                     "notes": "Centrifuge upgrade. Slightly higher polymer and maintenance."},
    "pre_thp":      {"score": 7, "label": "High",
                     "notes": "Steam boiler, pressure vessels (165°C/6 bar), "
                               "specialist operators required. Safety-critical systems. "
                               "Significant maintenance and compliance overhead."},
    "solidstream":  {"score": 7, "label": "High",
                     "notes": "Same as pre-THP plus hot centrate recycle management. "
                               "Additional heat integration complexity."},
    "separate":     {"score": 4, "label": "Moderate",
                     "notes": "Separate digestion trains. More complex but proven configuration. "
                               "Higher instrumentation and control requirements."},
    "separate_thp": {"score": 8, "label": "High-very high",
                     "notes": "Separate digestion PLUS THP steam systems. "
                               "Highest operational complexity of standard configurations. "
                               "Requires significant operator capability uplift."},
    "optimised_mad":{"score": 3, "label": "Low-moderate",
                     "notes": "WAS pre-thickening. Incremental complexity increase only."},
}


# ── THP Capacity Value Calculator ────────────────────────────────────────

# ── THP Configuration Library ──────────────────────────────────────────────
# Full-scale reference KPIs per THP configuration mode.
# Sources: Thames Water, United Utilities, DC Water, Davyhulme, Ringsend, Mangere.

THP_CONFIG_LIBRARY = {
    "conventional_mad": {
        "label":              "Conventional MAD",
        "description":        "Blended PS/WAS mesophilic anaerobic digestion. No pre-treatment.",
        "reference_count":    "10,000+",
        "confidence":         "very_high",
        "vsr_range_pct":      (42, 55),
        "cake_ds_range_pct":  (20, 25),
        "steam_kg_per_tds":   0,
        "methane_nm3_per_tds":180,    # typical range 150-220
        "electricity_mwh_per_tds": 0.45,
        "olr_max_kg_vs_m3_d": 3.0,
        "complexity_score":   2,
        "complexity_factors": [
            "Standard mesophilic digesters",
            "No specialist systems required",
            "Well-understood O&M",
        ],
        "opex_premium_pct":   0,      # baseline
        "capex_premium_pct":  0,
    },
    "was_only_thp": {
        "label":              "WAS-only THP (SolidStream)",
        "description":        "Thermal hydrolysis of secondary stream only. PS bypasses THP.",
        "reference_count":    "5-10",
        "confidence":         "medium",
        "vsr_range_pct":      (52, 60),
        "cake_ds_range_pct":  (30, 35),
        "steam_kg_per_tds":   450,    # lower than full THP — WAS fraction only
        "methane_nm3_per_tds":210,
        "electricity_mwh_per_tds": 0.61,
        "olr_max_kg_vs_m3_d": 5.0,
        "complexity_score":   7,
        "complexity_factors": [
            "THP pressure vessels on WAS stream",
            "Hot centrate recycle system",
            "Boiler / steam generation",
            "Specialist O&M for thermal pressure systems",
        ],
        "opex_premium_pct":   25,
        "capex_premium_pct":  35,
    },
    "full_thp": {
        "label":              "Full THP (Conventional)",
        "description":        "All feed pre-dewatered and thermally hydrolysed before digestion.",
        "reference_count":    "100+",
        "confidence":         "high",
        "vsr_range_pct":      (52, 65),
        "cake_ds_range_pct":  (28, 35),
        "steam_kg_per_tds":   861,    # Davyhulme validated: 861 kg/tDS
        "methane_nm3_per_tds":259,    # Davyhulme validated: 259 Nm³/tDS
        "electricity_mwh_per_tds": 0.68,
        "olr_max_kg_vs_m3_d": 6.0,
        "complexity_score":   8,
        "complexity_factors": [
            "Full-stream pressure vessels and autoclave",
            "Steam boiler (gas-fired)",
            "High-pressure safety systems",
            "Specialist THP operators required",
            "Significant maintenance overhead",
        ],
        "opex_premium_pct":   35,
        "capex_premium_pct":  60,
        "calibration_anchor": "Davyhulme WWTP (United Utilities, UK): "
                              "steam 861 kg/tDS, methane 259 Nm³/tDS, cake 31.3%DS. "
                              "Thames Water fleet: VSR 52-65%, cake DS 35-45%.",
    },
    "intermediate_thp": {
        "label":              "Intermediate THP",
        "description":        "THP applied between two digestion stages. Higher VSR potential.",
        "reference_count":    "2-5",
        "confidence":         "low",
        "vsr_range_pct":      (60, 70),
        "cake_ds_range_pct":  (30, 36),
        "steam_kg_per_tds":   600,
        "methane_nm3_per_tds":280,
        "electricity_mwh_per_tds": 0.78,
        "olr_max_kg_vs_m3_d": 6.0,
        "complexity_score":   9,
        "complexity_factors": [
            "Two-stage digestion train",
            "Interstage THP pressure vessels",
            "Complex hydraulic routing",
            "Very limited reference plant experience",
        ],
        "opex_premium_pct":   45,
        "capex_premium_pct":  80,
    },
    "separate_digestion": {
        "label":              "Separate PS/WAS Digestion",
        "description":        "PS and WAS digested in separate dedicated digesters. No THP.",
        "reference_count":    "10-30",
        "confidence":         "medium",   # limited full-scale separate digestion data
        "vsr_range_pct":      (48, 58),
        "cake_ds_range_pct":  (20, 25),
        "steam_kg_per_tds":   0,
        "methane_nm3_per_tds":210,        # higher than blended due to PS optimisation
        "electricity_mwh_per_tds": 0.52,
        "olr_max_kg_vs_m3_d": 3.0,
        "complexity_score":   3,
        "complexity_factors": [
            "Two separate digestion trains",
            "Separate thickening for each stream",
            "Volume redistribution or new digesters",
        ],
        "opex_premium_pct":   10,
        "capex_premium_pct":  15,
    },
}

# ── Operational Complexity Scores ──────────────────────────────────────────
# Based on: boilers, pressure vessels, automation, maintenance, specialist ops.
# Scale: 1 (simple, standard O&M) to 10 (specialist, high-risk, complex).
# Sources: Thames Water O&M experience, Ringsend reports, industry consensus.

OPERATIONAL_COMPLEXITY = {
    "base":         {
        "score": 2,
        "label": "Low",
        "factors": ["Standard mesophilic digesters", "No specialist systems", "Well-understood O&M"],
        "note":  "Benchmark technology. Available skill sets in most utilities.",
    },
    "recup":        {
        "score": 3,
        "label": "Low-Moderate",
        "factors": ["Centrifuge upgrade", "Additional polymer dosing", "No new pressure systems"],
        "note":  "Marginal increase. Same operator competency as base case.",
    },
    "pre_thp":      {
        "score": 8,
        "label": "High",
        "factors": [
            "Full-stream pressure vessels and autoclaves",
            "Gas-fired steam boiler",
            "High-pressure safety systems (PED/PSSR compliance)",
            "Specialist THP maintenance regime",
            "Dedicated operator training programme required",
        ],
        "note":  "Thames Water and United Utilities report this as a major "
                 "operational step-change requiring 2-3 years to embed.",
    },
    "solidstream":  {
        "score": 7,
        "label": "High",
        "factors": [
            "WAS-stream THP pressure vessels",
            "Hot centrate recycle system",
            "Boiler / steam generation",
            "Specialist thermal system O&M",
        ],
        "note":  "Lower than full THP (PS stream bypasses). "
                 "Still requires specialist operators and safety systems.",
    },
    "separate":     {
        "score": 3,
        "label": "Low-Moderate",
        "factors": ["Two-train digestion management", "Separate stream monitoring"],
        "note":  "No new specialist technology. Manageable with existing operator competency.",
    },
    "separate_thp": {
        "score": 7,
        "label": "High",
        "factors": [
            "Separation infrastructure complexity",
            "WAS-stream THP pressure vessels",
            "Combined train management",
        ],
        "note":  "Combined complexity of separation and THP systems.",
    },
    "optimised_mad":{
        "score": 3,
        "label": "Low-Moderate",
        "factors": ["WAS pre-thickening equipment", "Polymer dosing optimisation"],
        "note":  "No new pressure systems. Lowest complexity uplift of any option.",
    },
}

# ── Digester Capacity Value Calculator ─────────────────────────────────────
# THP's primary benefit for most utilities is capacity intensification,
# not methane production. This is the most commonly cited THP justification
# in full-scale case studies (Thames, United Utilities, DC Water).

# ── THP Configuration Library ─────────────────────────────────────────────
# Full-scale operating KPIs by THP mode.
# Source: Thames Water, United Utilities, DC Water, Davyhulme, Mangere, Ringsend.
# Use these for calibration and reference plant confidence scoring.

THP_CONFIG_LIBRARY = {
    "full_thp": {
        "label":         "Full THP (Cambi / Lysotherm)",
        "description":   "All feed thermally hydrolysed. Highest VSR and dewatering. "
                         "Highest steam demand and capital cost.",
        "hydrolysis_factor": 1.00,
        "vsr_range_pct": (52, 65),
        "cake_ds_range_pct": (28, 35),
        "steam_kg_per_tds": 861,        # Davyhulme reference
        "ch4_nm3_per_tds": 259,         # Davyhulme reference (WAS-heavy)
        "elec_mwh_per_tds": 0.68,       # Thames Water reference
        "olr_max_kg_vs_m3_d": 6.0,
        "capex_relative": 4,            # 1=lowest, 4=highest
        "references": [
            "Mangere WWTP NZ (20d HRT, 55.7% VSR, 63,151 Nm³/d)",
            "Davyhulme WWTW UK (steam 861 kg/tDS, CH4 259 Nm³/tDS, cake 31.3%)",
            "Thames Water Long Reach (cake 35-45% DS)",
            "DC Water Blue Plains (cake >29% DS)",
            "Ringsend WWTP IE (12%DS feed, 62% VSR, 34% cake DS)",
        ],
        "n_references": 100,
        "maturity": "Commercial — 100+ installations worldwide",
        "confidence": "high",
    },
    "was_only": {
        "label":         "WAS-only THP (Secondary stream)",
        "description":   "Secondary sludge only hydrolysed. PS bypasses THP. "
                         "Lower steam demand. Suitable where PS fraction is dominant.",
        "hydrolysis_factor": 0.88,
        "vsr_range_pct": (52, 60),
        "cake_ds_range_pct": (28, 33),
        "steam_kg_per_tds": 450,        # ~50% of full THP (WAS fraction only)
        "ch4_nm3_per_tds": None,        # site-specific
        "elec_mwh_per_tds": 0.61,       # Thames Water reference
        "olr_max_kg_vs_m3_d": 5.0,
        "capex_relative": 3,
        "references": [
            "Mangere 2040 WAS-only scenario (19.5d HRT, 56.7% VSR)",
            "Malabar WWTP Sydney (WAS-only, 51% VSR, 30% cake)",
        ],
        "n_references": 5,
        "maturity": "Commercial — limited references (3-5 full-scale)",
        "confidence": "medium",
    },
    "solidstream": {
        "label":         "SolidStream (WAS-only THP, hot centrate recycle)",
        "description":   "Cambi SolidStream: WAS hydrolysed, hot centrate recycled "
                         "to digester inlet for heat integration. Highest cake DS.",
        "hydrolysis_factor": 0.88,
        "vsr_range_pct": (54, 62),
        "cake_ds_range_pct": (36, 43),
        "steam_kg_per_tds": 420,
        "ch4_nm3_per_tds": None,
        "elec_mwh_per_tds": 0.65,
        "olr_max_kg_vs_m3_d": 5.0,
        "capex_relative": 3,
        "references": [
            "Amperverband WWTP Germany (40-43% cake DS confirmed)",
            "Cambi vendor data (38% DS guarantee basis)",
        ],
        "n_references": 3,
        "maturity": "Commercial — emerging (3 full-scale references)",
        "confidence": "medium",
    },
    "none": {
        "label":         "Conventional MAD",
        "description":   "Mesophilic anaerobic digestion, no pre-treatment. "
                         "Lowest capital and operational complexity.",
        "hydrolysis_factor": 0.0,
        "vsr_range_pct": (40, 55),
        "cake_ds_range_pct": (18, 25),
        "steam_kg_per_tds": 0,
        "ch4_nm3_per_tds": 220,         # typical range
        "elec_mwh_per_tds": 0.45,
        "olr_max_kg_vs_m3_d": 3.0,
        "capex_relative": 1,
        "references": ["10,000+ installations worldwide"],
        "n_references": 10000,
        "maturity": "Fully mature — universal reference base",
        "confidence": "high",
    },
}


# ── Operational Complexity Score ──────────────────────────────────────────
# Score 1–10 based on: boilers, pressure vessels, automation,
# maintenance frequency, specialist operator requirements, safety systems.
# Source: Thames Water operational assessment, Panter (AD fundamentals).

OPERATIONAL_COMPLEXITY = {
    "base":         {"score": 2, "label": "Low",
                     "notes": "Standard mesophilic AD. Proven technology, standard O&M."},
    "recup":        {"score": 3, "label": "Low-moderate",
                     "notes": "Centrifuge upgrade. Slightly higher polymer and maintenance."},
    "pre_thp":      {"score": 7, "label": "High",
                     "notes": "Steam boiler, pressure vessels (165°C/6 bar), "
                               "specialist operators required. Safety-critical systems. "
                               "Significant maintenance and compliance overhead."},
    "solidstream":  {"score": 7, "label": "High",
                     "notes": "Same as pre-THP plus hot centrate recycle management. "
                               "Additional heat integration complexity."},
    "separate":     {"score": 4, "label": "Moderate",
                     "notes": "Separate digestion trains. More complex but proven configuration. "
                               "Higher instrumentation and control requirements."},
    "separate_thp": {"score": 8, "label": "High-very high",
                     "notes": "Separate digestion PLUS THP steam systems. "
                               "Highest operational complexity of standard configurations. "
                               "Requires significant operator capability uplift."},
    "optimised_mad":{"score": 3, "label": "Low-moderate",
                     "notes": "WAS pre-thickening. Incremental complexity increase only."},
}


# ── THP Capacity Value Calculator ────────────────────────────────────────

