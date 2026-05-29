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
            rec_text += (
                "Pre-digestion THP delivers the highest biogas uplift and Class A "
                "biosolids classification. It is the preferred option where new "
                "digester capacity is being planned, as THP can be incorporated "
                "into the new facility scope."
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
        "at ETP-specific conditions — Cambi figures are conceptual and require "
        "Aurecon / independent engineer verification."
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
        "consistent with Melbourne Water net zero Scope 1 by 2030 and methane "
        "to zero by 2035-2040 strategic objectives."
    )
    steps.append(
        "Engage EPA Victoria on Class A compliance timeline, requirements, and "
        "whether THP at 165°C for 20 minutes satisfies the log reduction criteria "
        "under Publication 891.4 (2004)."
    )
    if winner_id in ("solidstream", "expansion"):
        steps.append(
            "Obtain Cambi performance guarantee terms and pre-contract testing "
            "protocol. Confirm minimum HRT adequacy and digester space for "
            "9th digester (expansion option) before committing to procurement."
        )
    steps.append(
        "Review driver weightings with Melbourne Water and Aurecon — update "
        "comparison if priorities change (regulatory deadline, budget, programme)."
    )
    return steps
