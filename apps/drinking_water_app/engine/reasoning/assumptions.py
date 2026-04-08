"""
AquaPoint Load-Bearing Assumption Engine
Identifies and surfaces assumptions that materially govern the preferred recommendation.
If a load-bearing assumption proves false, the preferred treatment philosophy changes.
"""
from dataclasses import dataclass, field
from typing import List
from .classifier import SourceWaterInputs, ClassificationResult


@dataclass
class LoadBearingAssumption:
    assumption: str
    why_it_matters: str
    dependent_element: str
    failure_consequence: str
    validation_required: str
    severity: str  # "critical" | "significant" | "moderate"
    triggered_by: str = ""  # which source parameter triggered this


def identify_load_bearing_assumptions(
    inputs: SourceWaterInputs,
    classification: ClassificationResult,
    preferred_archetype_key: str,
    contaminant_modules: dict,
) -> List[LoadBearingAssumption]:
    """
    Identify all load-bearing assumptions for the current source and preferred philosophy.
    Returns list sorted by severity (critical first).
    """
    assumptions = []

    # ── Arsenic speciation ────────────────────────────────────────────────────
    if inputs.arsenic_ug_l > 5:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                f"Arsenic is predominantly As(V) arsenate (anionic form), not As(III) arsenite. "
                f"Source arsenic: {inputs.arsenic_ug_l:.1f} μg/L (median)."
            ),
            why_it_matters=(
                "Ferric co-precipitation achieves 80–95% removal of As(V) at pH 6.5–7.0. "
                "As(III) is neutral at this pH range and is NOT removed by coagulation without "
                "prior oxidation to As(V). If As(III) comprises >30% of total arsenic, "
                "co-precipitation efficiency drops to 60–70% — potentially insufficient for compliance."
            ),
            dependent_element=(
                "Entire arsenic removal strategy — ferric co-precipitation and GFH polishing "
                "are both more effective for As(V). If As(III) dominates, pre-oxidation is "
                "mandatory before any coagulation-based removal."
            ),
            failure_consequence=(
                "Arsenic exceedance of ADWG 7 μg/L at P95 conditions. "
                "GFH polishing alone may not compensate if pre-oxidation for As(III) is absent. "
                "Treatment philosophy must be redesigned to include dedicated As(III) oxidation step."
            ),
            validation_required=(
                "Arsenic speciation analysis (As(III) vs As(V) fraction) on source water samples "
                "across seasonal range — minimum 4 samples over different flow conditions. "
                "This is the highest priority data gap for any arsenic-bearing groundwater source."
            ),
            severity="critical",
            triggered_by="arsenic_ug_l",
        ))

    # ── Bromate suppression ───────────────────────────────────────────────────
    if (preferred_archetype_key in ["G", "E"] and
            hasattr(inputs, 'bromide_mg_l') and getattr(inputs, 'bromide_mg_l', 0) > 0.05):
        bromide = getattr(inputs, 'bromide_mg_l', 0)
        assumptions.append(LoadBearingAssumption(
            assumption=(
                f"Bromate suppression strategy (H2O2 co-injection ± pH depression ± NH3 addition) "
                f"achieves <10 μg/L bromate at Br- {bromide:.2f} mg/L with proposed ozone dose."
            ),
            why_it_matters=(
                "ADWG bromate health guideline: 10 μg/L. "
                f"At Br- {bromide:.2f} mg/L without suppression, bromate formation is typically "
                f"{int(bromide * 100)}-{int(bromide * 300)} μg/L — potentially far above the limit. "
                "If suppression cannot achieve <10 μg/L, ozone cannot be legally operated at this source."
            ),
            dependent_element=(
                "Entire T&O control strategy — ozone/BAC is the preferred T&O pathway. "
                "If ozone must be removed, T&O control falls to PAC and UV/H2O2 AOP. "
                "At severe T&O loading, this may not achieve the same performance."
            ),
            failure_consequence=(
                "Ozone must be suspended or operated at severely reduced dose. "
                "T&O compliance at peak MIB/geosmin events becomes uncertain. "
                "The treatment philosophy changes from ozone/BAC to PAC or UV/H2O2 AOP."
            ),
            validation_required=(
                "Bench-scale bromate formation potential tests at source Br- P95 and P99 "
                "with proposed suppression chemistry before pilot. "
                "Continuous bromide monitoring at intake is a load-bearing operational requirement."
            ),
            severity="critical",
            triggered_by="ozone + bromide",
        ))

    # ── UV performance at P99 conditions ──────────────────────────────────────
    if inputs.turbidity_p99_ntu > 5 or inputs.toc_p95_mg_l > 5:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                f"UV transmittance (UVT) at P99 source conditions (turbidity {inputs.turbidity_p99_ntu:.0f} NTU, "
                f"TOC {inputs.toc_p95_mg_l:.1f} mg/L P95) remains ≥72% — sufficient for validated "
                "dose delivery at the design UV intensity."
            ),
            why_it_matters=(
                "UV dose delivery is UVT-dependent. At UVT <72%, LP UV reactors require significantly "
                "higher lamp intensity or reduced flow to maintain dose. If UVT drops below design basis "
                "during P99 turbidity events, the 4 log protozoa credit is not delivered."
            ),
            dependent_element=(
                "UV disinfection as the primary protozoan inactivation barrier. "
                "If UV credit is lost, no other barrier in the train provides adequate protozoa LRV."
            ),
            failure_consequence=(
                "Loss of protozoan inactivation credit during P99 turbidity events. "
                "Filter-to-waste protocol and UV intensity monitoring must trigger a response. "
                "Consider UV reactor sizing for worst-case UVT, not median UVT."
            ),
            validation_required=(
                "UVT measurement at P95 and P99 turbidity and TOC conditions. "
                "UV reactor sizing must use worst-case UVT from the dataset, not median. "
                "Online UVT monitoring is a load-bearing instrument."
            ),
            severity="critical" if inputs.turbidity_p99_ntu > 20 else "significant",
            triggered_by="turbidity + TOC → UVT",
        ))

    # ── Filtration performance at design turbidity ────────────────────────────
    if inputs.turbidity_p99_ntu > 10:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                f"Rapid gravity filtration produces effluent turbidity <0.1 NTU at P99 inlet "
                f"turbidity of {inputs.turbidity_p99_ntu:.0f} NTU with optimised coagulation. "
                "This is the condition for claiming 1.5–2.5 log protozoa filtration credit."
            ),
            why_it_matters=(
                "The protozoa LRV credit for rapid gravity filtration (1.5–2.5 log) is conditional "
                "on filter effluent turbidity <0.1 NTU. "
                "At P99 inlet turbidity, coagulation optimisation and filter run management "
                "are more demanding — coagulant dose must ramp up correctly with turbidity."
            ),
            dependent_element=(
                "Filtration LRV credit — contributes 1.5–2.5 log protozoa and 0.5–1.5 log bacteria. "
                "Loss of filtration credit tightens the overall barrier margin."
            ),
            failure_consequence=(
                "Filtration LRV credit reduced or lost during turbidity events. "
                "Filter-to-waste protocol must be activated. "
                "If direct filtration is the architecture, extreme events may require plant shutdown."
            ),
            validation_required=(
                "Direct filtration pilot study at P95/P99 source water conditions. "
                "Continuous turbidity monitoring at each filter outlet — alarm at 0.2 NTU, "
                "filter-to-waste at 0.5 NTU."
            ),
            severity="significant",
            triggered_by="turbidity_p99_ntu",
        ))

    # ── Chlorine Ct for virus inactivation ────────────────────────────────────
    assumptions.append(LoadBearingAssumption(
        assumption=(
            "Free chlorine Ct contact (post-UV) achieves 2.0–3.5 log virus inactivation "
            "at the design pH and minimum water temperature. "
            f"Source pH range: {inputs.ph_min:.1f}–{inputs.ph_median:.1f}."
        ),
        why_it_matters=(
            "LP UV at 40 mJ/cm2 provides only 0.5–1.0 log virus inactivation (adenovirus governs). "
            "The remaining 5.0–5.5 log virus LRV must come from chlorine Ct. "
            "This makes Ct the load-bearing virus barrier. "
            f"At pH {inputs.ph_median:.1f}, Ct efficiency is {'good' if inputs.ph_median < 7.5 else 'reduced — pH correction may be needed'}."
        ),
        dependent_element=(
            "Virus LRV target (6–7 log). Without adequate Ct, the virus target is not met. "
            "This cannot be compensated by increasing UV dose — adenovirus LP UV resistance "
            "means 168 mJ/cm2 would be required for 4 log virus from UV alone."
        ),
        failure_consequence=(
            "Virus LRV target not met. Requires either: (1) larger Ct contact basin, "
            "(2) higher chlorine dose, (3) lower pH for improved Ct efficiency, "
            "or (4) addition of ozone for virus inactivation credit."
        ),
        validation_required=(
            "Ct verification at maximum design pH and minimum design temperature. "
            "Online Ct monitoring (flow × time × chlorine residual) is a load-bearing instrument. "
            "Contact basin must be sized for P95 conditions, not median."
        ),
        severity="critical",
        triggered_by="virus_lrv_gap + UV_adenovirus_caveat",
    ))

    # ── Ammonia and disinfection interaction ──────────────────────────────────
    ammonia_val = getattr(inputs, 'ammonia_mg_l_nh3n', None) or 0.0
    if ammonia_val > 0.1:
        if True:  # block
            assumptions.append(LoadBearingAssumption(
                assumption=(
                    f"Breakpoint chlorination at P95 ammonia_val (~{ammonia_val * 2.3:.2f} mg/L NH3-N estimated from median {ammonia_val:.2f} mg/L) "
                    "is consistently achieved before free Cl2 Ct contact, "
                    "ensuring Ct calculations are valid."
                ),
                why_it_matters=(
                    "If breakpoint is not achieved, chlorine exists as combined chloramines "
                    "rather than free chlorine. Chloramine Ct for virus inactivation is "
                    "orders of magnitude less effective than free chlorine Ct. "
                    "The virus LRV target would not be met."
                ),
                dependent_element=(
                    "Free chlorine Ct for virus inactivation — the load-bearing virus barrier."
                ),
                failure_consequence=(
                    "Chloramines rather than free Cl2 in the Ct basin — "
                    "virus inactivation credit is negligible. "
                    "The entire virus LRV strategy fails if breakpoint is not reliably achieved."
                ),
                validation_required=(
                    "Continuous ammonia_val monitoring at filter outlet (before chlorine dosing). "
                    "Automated chlorine dose controller responding to measured NH3-N. "
                    "Online Ct verification instrument."
                ),
                severity="critical",
                triggered_by="ammonia_nh3n",
            ))

    # ── Manganese oxidation completeness ──────────────────────────────────────
    if inputs.manganese_median_mg_l > 0.05:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                f"KMnO4 pre-oxidation at dose 0.4–1.1 mg/L achieves complete Mn2+ oxidation "
                f"at P95 manganese ({inputs.manganese_median_mg_l * 4:.2f} mg/L estimated). "
                "Filter effluent contains <0.02 mg/L soluble Mn2+."
            ),
            why_it_matters=(
                "Soluble Mn2+ passing through the filter is invisible to turbidity monitoring. "
                "In distribution, residual chloramine slowly oxidises Mn2+ to MnO2 — "
                "producing black water deposits and customer complaints. "
                "The treatment target is <0.05 mg/L Mn in treated water, effectively <0.02 mg/L "
                "to prevent distribution accumulation."
            ),
            dependent_element=(
                "KMnO4 pre-oxidation dose control and greensand filter conditioning. "
                "Black water risk is entirely dependent on correct Mn2+ oxidation before filtration."
            ),
            failure_consequence=(
                "Black water events in distribution — customer complaints, loss of confidence. "
                "Excess KMnO4 causes pink water — dose control must be precise. "
                "Under-dose leaves soluble Mn2+ in treated water."
            ),
            validation_required=(
                "Automated KMnO4 dosing with online Mn2+ monitoring at filter inlet. "
                "Filter effluent Mn2+ monitoring (not total Mn — must be the soluble fraction). "
                "Greensand conditioning protocol — filter media must be properly charged."
            ),
            severity="significant",
            triggered_by="manganese_median_mg_l",
        ))

    # ── Low alkalinity coagulation ────────────────────────────────────────────
    if inputs.alkalinity_median_mg_l < 50:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                f"Alkali supplementation (lime or caustic) successfully maintains coagulation "
                f"pH in the 6.2–7.0 range at the design coagulant dose, "
                f"despite low source alkalinity ({inputs.alkalinity_median_mg_l:.0f} mg/L as CaCO3)."
            ),
            why_it_matters=(
                f"At alkalinity {inputs.alkalinity_median_mg_l:.0f} mg/L, ferric coagulant at typical "
                "doses (8–20 mg/L) will suppress pH below 6.0 without alkali addition. "
                "NOM removal by coagulation is strongly pH-dependent — below pH 6.0, "
                "coagulation efficiency drops significantly and colour compliance may be at risk."
            ),
            dependent_element=(
                "Coagulation chemistry and NOM removal. "
                "CCPP correction post-treatment — low alkalinity water is corrosive."
            ),
            failure_consequence=(
                "Poor NOM removal — colour exceedance and elevated THM/HAA precursors. "
                "pH instability in distribution — corrosive water without CCPP correction."
            ),
            validation_required=(
                "Jar testing across the range of source alkalinity and coagulant dose. "
                "Online pH monitoring at coagulation stage. "
                "Automated alkali dosing — manual pH correction is not adequate for this sensitivity."
            ),
            severity="significant",
            triggered_by="alkalinity_median_mg_l",
        ))

    # ── CCPP correction ───────────────────────────────────────────────────────
    if inputs.alkalinity_median_mg_l < 80:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                f"Post-treatment pH and alkalinity correction achieves CCPP of -5 to 0 mg/L CaCO3 "
                f"at the distribution entry point. Source alkalinity: {inputs.alkalinity_median_mg_l:.0f} mg/L."
            ),
            why_it_matters=(
                "CCPP of -5 to 0 mg/L is the target for corrosion control without scale formation. "
                f"At alkalinity {inputs.alkalinity_median_mg_l:.0f} mg/L and typical post-treatment pH, "
                "the water is likely corrosive (negative CCPP) without correction. "
                "Corrosive water attacks pipe materials, increases lead and copper leaching, "
                "and causes structural damage to distribution infrastructure."
            ),
            dependent_element=(
                "Distribution system integrity and compliance with lead/copper guidelines. "
                "Also affects chloramine stability — corrosive water accelerates nitrification."
            ),
            failure_consequence=(
                "Corrosion damage to distribution pipes and fittings. "
                "Lead and copper leaching from service connections — potential health compliance issue. "
                "Increased maintenance costs."
            ),
            validation_required=(
                "CCPP calculation using actual post-treatment pH, alkalinity, calcium, TDS, "
                "and temperature. Distribution system pipe material audit. "
                "Real-time CCPP monitoring at distribution entry point recommended."
            ),
            severity="significant",
            triggered_by="alkalinity_low + CCPP",
        ))

    # ── GFH disposal pathway ──────────────────────────────────────────────────
    if inputs.arsenic_ug_l > 5:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                "A confirmed disposal pathway exists for spent GFH media "
                "(arsenic-bearing classified solid waste) before plant commissioning."
            ),
            why_it_matters=(
                "Spent GFH is an arsenic-bearing classified solid waste. "
                "If no confirmed disposal pathway exists, GFH contactors cannot be commissioned. "
                "The arsenic polishing barrier is absent — the preferred treatment philosophy cannot proceed."
            ),
            dependent_element=(
                "GFH polishing as the secondary arsenic barrier. "
                "Without GFH, arsenic compliance relies solely on ferric co-precipitation — "
                "a single mechanism for a health-based parameter."
            ),
            failure_consequence=(
                "GFH cannot be commissioned. The secondary arsenic barrier is absent. "
                "Plant must operate on ferric co-precipitation alone — "
                "defensibility is reduced."
            ),
            validation_required=(
                "Confirm approved arsenic waste disposal facility, contract, and cost "
                "BEFORE commissioning. This is a non-negotiable pre-commissioning requirement. "
                "TCLP testing of dewatered ferric sludge is also required."
            ),
            severity="significant",
            triggered_by="arsenic + GFH residuals",
        ))

    # ── Direct filtration storm events ────────────────────────────────────────
    if classification.direct_filtration_eligible:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                f"Storm-driven turbidity events exceeding 15 NTU occur fewer than 10 times "
                f"per year AND each event duration is less than 48 hours. "
                f"Source P99 turbidity: {inputs.turbidity_p99_ntu:.0f} NTU."
            ),
            why_it_matters=(
                "Direct filtration is defensible for P99 20 NTU if events are short-lived. "
                "If events regularly persist for multiple days, continuous filter-to-waste "
                "operation reduces effective plant capacity and stresses the filter — "
                "the direct filtration architecture is no longer practical."
            ),
            dependent_element=(
                "Direct filtration as the treatment architecture. "
                "If events are frequent and prolonged, lamella clarification must be added — "
                "changing the treatment philosophy and capital cost significantly."
            ),
            failure_consequence=(
                "Direct filtration is replaced by conventional clarification. "
                "Capital cost increases by approximately $5–10M. "
                "Footprint and sludge management complexity increase substantially."
            ),
            validation_required=(
                "Minimum 3-year turbidity dataset at intake with event frequency and duration analysis. "
                "Define: how many events per year exceed 15 NTU? "
                "What is the typical event duration? "
                "This is the single most important data gap for the direct filtration decision."
            ),
            severity="critical",
            triggered_by="direct_filtration_eligible + turbidity_p99",
        ))

    # ── Cyanobacteria dissolved toxin phase ───────────────────────────────────
    if inputs.cyanobacteria_confirmed or inputs.cyanotoxin_detected:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                "Cyanotoxins are primarily intracellular during design events — "
                "cell removal before oxidation controls the primary toxin pathway. "
                "Dissolved (extracellular) toxin concentrations remain below treatment thresholds "
                "when intact cells are removed efficiently."
            ),
            why_it_matters=(
                "If bloom collapse occurs upstream or cells lyse before removal, "
                "dissolved toxin concentrations spike 10–100× compared to intact-cell events. "
                "Cell removal alone does not address dissolved toxins — "
                "oxidation (ozone/chlorine) or adsorption (PAC/GAC) must control dissolved toxins."
            ),
            dependent_element=(
                "The cyanotoxin management strategy — sequencing rule (cell removal before oxidation). "
                "If dissolved toxins become governing, the strategy must expand to include "
                "dedicated dissolved-phase destruction."
            ),
            failure_consequence=(
                "Dissolved toxin breakthrough to distribution. "
                "Microcystin-LR health guideline: 1 μg/L (ADWG). "
                "Bloom collapse events may require source suspension."
            ),
            validation_required=(
                "Cyanotoxin fractionation monitoring (total vs filtered) during bloom events. "
                "Dissolved toxin monitoring at filter outlet during bloom periods. "
                "Defined source suspension trigger if dissolved toxins approach 1 μg/L."
            ),
            severity="critical" if inputs.cyanotoxin_detected else "significant",
            triggered_by="cyanobacteria + dissolved_toxins",
        ))

    # ── PFAS / Membrane concentrate ──────────────────────────────────────────
    if inputs.pfas_detected or inputs.pfas_concentration_ng_l > 0:
        pfas_conc = inputs.pfas_concentration_ng_l
        assumptions.append(LoadBearingAssumption(
            assumption=(
                "PFAS concentrate / spent media disposal pathway exists and can be licensed "                "before plant commissioning."
            ),
            why_it_matters=(
                f"Source PFAS: {pfas_conc:.0f} ng/L. GAC, IX resin, and RO all concentrate PFAS "                "into a secondary waste stream. Spent GAC/IX is classified waste in all Australian "                "jurisdictions. RO concentrate containing PFAS requires specific licensed disposal — "                "no universal pathway exists. Without a confirmed disposal route, the selected "                "PFAS treatment technology cannot proceed."
            ),
            dependent_element=(
                "Entire PFAS treatment pathway (GAC adsorption / PFAS-selective IX / RO concentrate)."
            ),
            failure_consequence=(
                "No confirmed disposal pathway means the PFAS treatment technology cannot be "                "commissioned — the preferred archetype fails at the residuals stage. "                "Plant cannot achieve PFAS compliance without an alternative pathway."
            ),
            validation_required=(
                "Confirm licensed PFAS waste disposal facility before detailed design. "                "Obtain in-principle agreement from waste contractor. "                "If RO: characterise concentrate volume and PFAS load; confirm disposal contract. "                "If GAC/IX: confirm spent media disposal facility, cost, and long-term contract."
            ),
            severity="critical",
            triggered_by="pfas_detected",
        ))
        assumptions.append(LoadBearingAssumption(
            assumption=(
                "Selected PFAS removal technology achieves the required removal across all PFAS "                "species present at source."
            ),
            why_it_matters=(
                "PFAS removal efficiency varies strongly between technologies and PFAS species. "                "GAC effectively removes long-chain PFAS (PFOS, PFOA) but has limited efficacy "                "for short-chain PFAS (PFBS, PFPeA, PFHxA) with EBCT <20 min. "                "PFAS-selective IX resin removes short-chain better than GAC. "                "RO provides non-selective high rejection but generates concentrate. "                "Without species-level data, removal adequacy cannot be confirmed."
            ),
            dependent_element="PFAS compliance — all species must be below health-based guidance values.",
            failure_consequence=(
                "Short-chain PFAS breakthrough renders treatment non-compliant. "                "Technology must be re-selected or supplemented."
            ),
            validation_required=(
                f"Full PFAS species analysis (including C4-C7 PFAS). "                "Bench-scale or pilot-scale treatability testing with actual source water. "                "Confirm target removal for each species before design."
            ),
            severity="critical",
            triggered_by="pfas_detected",
        ))

    # ── High TDS / RO membrane ────────────────────────────────────────────────
    if inputs.tds_median_mg_l > 1000 or inputs.source_type == "desalination":
        assumptions.append(LoadBearingAssumption(
            assumption=(
                "RO membrane achieves required TDS rejection at the design recovery rate and "                "source water scaling indices."
            ),
            why_it_matters=(
                f"Source TDS: {inputs.tds_median_mg_l:.0f} mg/L. RO rejection efficiency depends on "                "membrane selection, operating pressure, temperature, and scaling potential. "                "At high recovery (>70%), concentration polarisation and scaling risk increase. "                "Antiscalant selection must be validated for specific ion chemistry (CaCO3, CaSO4, SiO2)."
            ),
            dependent_element="TDS compliance in product water; RO recovery rate; concentrate volume.",
            failure_consequence=(
                "If rejection is lower than assumed: TDS exceedance in product water or reduced "                "recovery required, increasing concentrate volume and operating cost. "                "If scaling occurs: membrane fouling, flux decline, increased cleaning frequency."
            ),
            validation_required=(
                "Scaling indices (Langelier, Ryznar) at design recovery. "                "Antiscalant treatability testing. "                "Membrane selection based on source ion chemistry. "                "Pilot testing at design recovery before final design."
            ),
            severity="critical",
            triggered_by="high_tds",
        ))
        assumptions.append(LoadBearingAssumption(
            assumption=(
                "A technically feasible and licensed concentrate / brine disposal pathway "                "can be established prior to plant commissioning."
            ),
            why_it_matters=(
                f"At {inputs.tds_median_mg_l:.0f} mg/L TDS source and 75% recovery, concentrate TDS "                "is approximately {int(inputs.tds_median_mg_l * 4):.0f} mg/L at 4× concentration. "                "Inland concentrate disposal options are severely limited: "                "sewer acceptance (TDS limits typically 1000-2000 mg/L), deep well injection "                "(geology-dependent), evaporation ponds (large land area, licensing). "                "Concentrate disposal is frequently the site-controlling constraint for inland RO."
            ),
            dependent_element=(
                "Entire RO treatment philosophy — without concentrate disposal, RO cannot operate."
            ),
            failure_consequence=(
                "No viable concentrate disposal pathway means RO is not feasible at this site. "                "Treatment philosophy must revert to non-membrane alternatives or partial-flow blending."
            ),
            validation_required=(
                "Early-stage concentrate disposal pathway assessment (pre-feasibility). "                "Sewer authority TDS acceptance limits. "                "Hydrogeological assessment for deep well injection if considered. "                "Evaporation pond sizing, land availability, and licensing timeline if considered."
            ),
            severity="critical",
            triggered_by="high_tds + concentrate",
        ))

    # ── Softening / high hardness ─────────────────────────────────────────────
    if preferred_archetype_key == "F" or inputs.hardness_median_mg_l > 300:
        assumptions.append(LoadBearingAssumption(
            assumption=(
                "Lime sludge disposal pathway exists and can be operated on a continuous basis."
            ),
            why_it_matters=(
                f"Hardness {inputs.hardness_median_mg_l:.0f} mg/L CaCO3. Lime softening generates "                "10-30x the sludge volume of equivalent conventional coagulation treatment. "                "Lime sludge is gelatinous (particularly at high Mg content), poorly dewaterable, "                "and typically requires lagoon storage or significant dewatering infrastructure. "                "Lagoons require significant land area and long-term management."
            ),
            dependent_element=(
                "Softening treatment philosophy — lime dosing cannot continue without sludge outlet."
            ),
            failure_consequence=(
                "Lagoon capacity exceeded: plant must reduce throughput or shut down. "                "No alternative lime sludge outlet = softening plant cannot operate continuously."
            ),
            validation_required=(
                "Lime sludge volume estimate at design flow. "                "Lagoon sizing and land availability assessment. "                "Agricultural lime reuse assessment (chemistry must be suitable). "                "Dewatering equipment feasibility (CaCO3 vs Mg(OH)2 fraction determines approach)."
            ),
            severity="critical" if inputs.hardness_median_mg_l > 350 else "significant",
            triggered_by="softening_residuals",
        ))

    # ── Sort by severity ──────────────────────────────────────────────────────
    severity_order = {"critical": 0, "significant": 1, "moderate": 2}
    assumptions.sort(key=lambda a: severity_order.get(a.severity, 3))

    return assumptions


def format_assumptions_for_report(assumptions: List[LoadBearingAssumption]) -> str:
    """Format load-bearing assumptions as structured markdown for report output."""
    if not assumptions:
        return "No load-bearing assumptions identified for this source and preferred philosophy."

    lines = []
    critical = [a for a in assumptions if a.severity == "critical"]
    significant = [a for a in assumptions if a.severity == "significant"]
    moderate = [a for a in assumptions if a.severity == "moderate"]

    if critical:
        lines.append(f"### Critical Assumptions ({len(critical)})")
        lines.append("*These assumptions must be validated before the preferred philosophy can be finalised.*")
        lines.append("")
        for i, a in enumerate(critical, 1):
            lines.append(f"**CRITICAL {i}: {a.assumption[:80]}...**" if len(a.assumption) > 80
                        else f"**CRITICAL {i}:** {a.assumption}")
            lines.append(f"- **Why it matters:** {a.why_it_matters}")
            lines.append(f"- **Dependent element:** {a.dependent_element}")
            lines.append(f"- **If false:** {a.failure_consequence}")
            lines.append(f"- **Validation required:** {a.validation_required}")
            lines.append("")

    if significant:
        lines.append(f"### Significant Assumptions ({len(significant)})")
        for i, a in enumerate(significant, 1):
            lines.append(f"**SIGNIFICANT {i}:** {a.assumption}")
            lines.append(f"- **Why it matters:** {a.why_it_matters}")
            lines.append(f"- **Validation required:** {a.validation_required}")
            lines.append("")

    return "\n".join(lines)
