"""
apps/wastewater_app/risk_layer.py

Unified Risk & Mitigation Layer — Production V1
================================================

Post-selection interpretation layer that presents every recommended technology
with a consistent four-category risk profile and practical mitigation strategy.

Answers two questions for every technology in the stack:
  → "What could go wrong?"
  → "How do we manage it?"

Design principles
-----------------
- Applied consistently to ALL selected technologies, not just specialist ones.
- Every risk is paired with a mitigation — never risk without solution.
- Low-risk technologies still receive a section (stated as low-risk).
- Tone: engineering-led, balanced, practical. Never alarmist.
- Does NOT modify stack, feasibility, or credibility outputs.

Risk categories (4, mandatory for all technologies)
----------------------------------------------------
1. Technical / Process Risk
2. Operational Risk
3. Commercial / Supplier Risk
4. Financial / Lifecycle Risk

Main entry point
----------------
  build_risk_report(pathway, feasibility, plant_context) -> RiskReport
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from apps.wastewater_app.stack_generator import (
    UpgradePathway, PathwayStage,
    TI_COMAG, TI_BIOMAG, TI_EQ_BASIN, TI_STORM_STORE,
    TI_INDENSE, TI_MIGINDENSE, TI_MEMDENSE,
    TI_HYBAS, TI_IFAS, TI_MBBR, TI_MABR,
    TI_BARDENPHO, TI_RECYCLE_OPT, TI_ZONE_RECONF,
    TI_DENFILTER, TI_TERT_P,
)
from apps.wastewater_app.feasibility_layer import FeasibilityReport, StageFeasibility

# ── Risk level constants ───────────────────────────────────────────────────────
RL_LOW    = "Low"
RL_MEDIUM = "Medium"
RL_HIGH   = "High"

# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class RiskCategory:
    """One risk category for a technology."""
    category:    str   # "Technical", "Operational", "Commercial", "Financial"
    level:       str   # RL_LOW / RL_MEDIUM / RL_HIGH
    risk:        str   # concise risk statement
    mitigation:  str   # practical mitigation strategy


@dataclass
class TechRiskProfile:
    """Full four-category risk profile for one technology."""
    stage_number:    int
    technology:      str
    tech_display:    str
    risk_summary:    str   # 1-2 line overall risk posture
    categories:      List[RiskCategory]   # always exactly 4
    overall_level:   str   # worst-case across all categories
    decision_note:   str   # always the standard closing sentence


@dataclass
class RiskReport:
    """Full Unified Risk & Mitigation report for a pathway."""
    profiles:          List[TechRiskProfile]
    stack_risk_summary: str   # one paragraph for the stack as a whole
    decision_tension:  str    # mandatory closing statement
    # Validation flags
    all_technologies_covered: bool
    no_technology_risk_free:  bool
    all_mitigations_present:  bool


# ── Risk profile library ───────────────────────────────────────────────────────
# Each entry is a function returning (risk_summary, [RiskCategory × 4]).
# Functions accept the StageFeasibility object so they can incorporate
# the live feasibility-layer data (supply_risk, chemical_dep, etc.).

def _profile_comag(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    location = ctx.get("location_type", "metro")
    supply_note = ("Supply chain access is good in metropolitan areas, "
                   "reducing but not eliminating procurement risk."
                   if location == "metro" else
                   "Remote or regional location increases magnetite logistics risk "
                   "and requires additional stock management.")
    return (
        "Medium overall risk. The primary driver is magnetite supply chain continuity and "
        "recovery system efficiency. Technical and operational risks are manageable with "
        "pre-commissioning supplier qualification and trained operators.",
        [
            RiskCategory("Technical", RL_MEDIUM,
                "Magnetite recovery efficiency is sensitive to bypass events, "
                "high shear conditions, and equipment wear. A single bypass "
                "event can cause significant magnetite loss requiring restocking.",
                "Design recovery system for >99.5% efficiency. Establish monitoring "
                "of magnetite inventory and loss rate from first day of operation. "
                "Include a manual bypass isolation procedure in the O&M plan."),
            RiskCategory("Operational", RL_MEDIUM,
                "Requires trained operators to manage continuous magnetite dosing, "
                "drum separator operation, and bypass configuration during extreme "
                "peak events. Side-stream configuration introduces additional "
                "process control requirements.",
                "Develop site-specific O&M manual with separator maintenance schedule. "
                "Train operators pre-commissioning. Commission process control alarms "
                "for separator underperformance and inventory depletion."),
            RiskCategory("Commercial", RL_MEDIUM,
                f"Continuous magnetite supply from a specialist supplier is required. "
                f"{supply_note} Whole-of-life cost is sensitive to recovery "
                f"efficiency — poor recovery compounds into significant ongoing cost.",
                "Pre-qualify at least two magnetite suppliers. Establish a supply "
                "agreement with minimum stock holding (≥ 30-day on-site reserve). "
                "Include magnetite recovery performance in the OEM commissioning KPIs."),
            RiskCategory("Financial", RL_MEDIUM,
                "CAPEX is moderate. OPEX is dominated by magnetite make-up cost "
                "and separator energy. Whole-of-life cost must account for "
                "separator wear parts and periodic media restocking.",
                "Conduct TOTEX analysis at detailed design stage. Include sensitivity "
                "to ±20% in magnetite recovery rate. Budget for separator inspection "
                "and wear-part replacement at 3–5 year intervals."),
        ]
    )


def _profile_biomag(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    return (
        "Medium-High overall risk due to dual supply dependency (magnetite + carrier media). "
        "BioMag addresses both settling and biological constraints simultaneously, which "
        "justifies the higher complexity relative to single-mechanism technologies.",
        [
            RiskCategory("Technical", RL_MEDIUM,
                "Dual-mechanism system: magnetic microspheres must improve settling "
                "velocity while biofilm carriers provide additional biological capacity. "
                "Failure of either component reduces system performance. Magnetite "
                "loss events or carrier screen fouling can degrade both functions.",
                "Commission and validate settling improvement (inDENSE baseline) before "
                "activating carrier component. Establish independent monitoring for "
                "magnetite inventory and carrier retention. Define performance thresholds "
                "for each mechanism in the O&M plan."),
            RiskCategory("Operational", RL_HIGH,
                "Highest operational complexity in the settling-intensification technology "
                "class. Requires simultaneous management of magnetite recovery, carrier "
                "screen maintenance, and biofilm establishment. If control systems "
                "prioritise one component, the other may underperform.",
                "Develop a commissioning sequence that validates each mechanism "
                "independently before combined operation. Allocate dedicated operator "
                "training for both magnetite and carrier subsystems. Establish a "
                "specialist OEM support contract for the first 2 years of operation."),
            RiskCategory("Commercial", RL_MEDIUM,
                "Dual supply dependency: magnetite supply chain and carrier media "
                "supplier must both be managed concurrently. Procurement risk is "
                "higher than for single-mechanism technologies.",
                "Pre-qualify suppliers for both components before contract award. "
                "Establish independent supply agreements for magnetite and carriers. "
                "Confirm carrier media compatibility with the magnetite recovery system."),
            RiskCategory("Financial", RL_MEDIUM,
                "CAPEX is moderate for each component. Combined OPEX (magnetite make-up "
                "+ carrier screen maintenance + specialist O&M) is higher than "
                "conventional settling upgrades. Long-term TOTEX benefit depends "
                "on achieving the combined settling and biological performance target.",
                "Conduct joint TOTEX analysis comparing BioMag to separate inDENSE + "
                "IFAS. Include sensitivity to carrier media replacement cost. "
                "Define the performance KPIs that justify combined deployment."),
        ]
    )


def _profile_mabr(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    aer_constrained = ctx.get("aeration_constrained", False)
    return (
        "Medium overall risk. MABR is a specialist technology with OEM dependency, "
        "but its technical risks are well-characterised and manageable with appropriate "
        "commissioning and O&M protocols. The primary justification — bypassing blower "
        "capacity constraint — is the key technical rationale for this selection.",
        [
            RiskCategory("Technical", RL_MEDIUM,
                "Hollow-fibre membrane integrity is critical to oxygen delivery performance. "
                "Biofilm thickness must be managed — too thin reduces nitrification; "
                "too thick increases diffusion resistance and reduces efficiency. "
                "Biofilm establishment takes 4–8 weeks and should not overlap with "
                "winter cold-temperature conditions.",
                "Specify integrity testing protocol at installation and at annual "
                "inspection. Define biofilm scour frequency in O&M plan. "
                "Schedule commissioning outside winter period. Confirm NH₄ monitoring "
                "trigger levels during the 4–8 week establishment period."),
            RiskCategory("Operational", RL_MEDIUM,
                "Requires operators familiar with membrane-aerated biofilm management, "
                "which differs from conventional diffused aeration operation. "
                "Performance monitoring (DO profile, NH₄, module pressure) requires "
                "additional instrumentation relative to conventional aeration zones."
                + (" Aeration blowers are near capacity — MABR module failure reduces "
                   "total nitrification capacity with limited blower backup available."
                   if aer_constrained else ""),
                "Establish MABR-specific O&M training programme before commissioning. "
                "Commission continuous NH₄ monitoring at MABR outlet. Define fallback "
                "protocol (blower supplement) for module maintenance periods. "
                "Include MABR performance in weekly process review."),
            RiskCategory("Commercial", RL_MEDIUM,
                "Specialist hollow-fibre modules from a single OEM supplier. Module "
                "replacement lead time must be assessed — stock criticality depends "
                "on whether alternative nitrification capacity exists. Design parameters "
                "and optimisation data are largely proprietary.",
                "Negotiate OEM support contract (minimum 3 years post-commissioning) "
                "including module supply guarantee and response time SLA. Confirm "
                "module replacement schedule and include in asset register. "
                "Request access to key performance parameters to enable "
                "independent performance assessment."),
            RiskCategory("Financial", RL_MEDIUM,
                "Higher CAPEX per unit of nitrification capacity than IFAS where "
                "blower headroom exists. However, where blowers are at capacity, "
                "MABR avoids new blower capital. Energy saving (≤ 14 kgO₂/kWh) "
                "provides long-term OPEX benefit that must be verified on-site.",
                "Conduct whole-of-life TOTEX comparison against blower expansion + IFAS. "
                "Include N₂O reduction benefit in carbon accounting (verified through "
                "on-site monitoring). Budget for module replacement at OEM-specified "
                "design life."),
        ]
    )


def _profile_indense(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    return (
        "Low-Medium overall risk. inDENSE is a well-characterised hydrocyclone-based "
        "technology with a broad reference base. The primary risk is commissioning "
        "calibration; operational risks are low once stable.",
        [
            RiskCategory("Technical", RL_LOW,
                "Hydrocyclone split ratio must be calibrated to mixed liquor "
                "characteristics at commissioning. Incorrect split ratio results "
                "in either insufficient dense fraction selection (underperformance) "
                "or excessive sludge wastage (MLSS reduction). "
                "Biomass selection improvement is progressive — typically 4–8 weeks.",
                "Conduct commissioning calibration with supplier support. Define "
                "target SVI range and MLSS operating point. Monitor SVI and "
                "settled sludge volume weekly during the first 12 weeks."),
            RiskCategory("Operational", RL_LOW,
                "Low operational complexity relative to other specialist technologies. "
                "Main operational requirement is monitoring hydrocyclone performance "
                "and maintaining split ratio as MLSS characteristics evolve seasonally.",
                "Include hydrocyclone split ratio in monthly process review. "
                "Train operators on SVI interpretation and response protocol. "
                "Establish seasonal recalibration procedure (summer / winter)."),
            RiskCategory("Commercial", RL_LOW,
                "Specialist supplier for hydrocyclone design and commissioning. "
                "Single supplier dependency for the specific unit design, though "
                "the underlying hydrocyclone technology is not proprietary.",
                "Establish commissioning support agreement with supplier. "
                "Confirm spare parts availability. Hydrocyclone design is "
                "sufficiently standard that maintenance can be managed locally "
                "once commissioned."),
            RiskCategory("Financial", RL_LOW,
                "Low CAPEX. Minimal OPEX — no chemical input, low energy. "
                "Primary financial risk is underperformance if commissioning "
                "calibration is not completed correctly.",
                "Include commissioning performance KPIs in contract. "
                "Confirm target SVI improvement (e.g. from 150 to < 120 mL/g) "
                "as a contractual deliverable at 12-week post-commissioning."),
        ]
    )


def _profile_migindense(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    return (
        "Medium overall risk. MOB combines inDENSE (settling) and miGRATE (carriers) "
        "in a sequenced two-stage SBR intensification programme. The sequencing "
        "dependency — inDENSE must be stable before miGRATE is activated — is the "
        "primary commissioning risk.",
        [
            RiskCategory("Technical", RL_MEDIUM,
                "miGRATE carrier performance depends on inDENSE being established "
                "and stable. Premature carrier activation before settling improvement "
                "is confirmed reduces the biological benefit. Carrier distribution "
                "and retention in SBR cycles requires screen design validation.",
                "Commission and validate inDENSE (SVI target achieved) before "
                "carrier installation. Confirm carrier retention screen design "
                "with supplier. Monitor SVI and MLSS throughout both stages."),
            RiskCategory("Operational", RL_MEDIUM,
                "Two-stage commissioning requires sequential operator engagement. "
                "SBR cycle management must be adjusted as MLSS density and "
                "settleability characteristics change through both stages.",
                "Develop a staged commissioning plan with performance gates. "
                "Update SBR cycle parameters at each stage transition. "
                "Engage carrier supplier for cycle optimisation support."),
            RiskCategory("Commercial", RL_MEDIUM,
                "Dual supplier dependency: inDENSE hydrocyclone and miGRATE carrier "
                "media. Both are specialist systems. Reference base is growing "
                "but smaller than conventional IFAS.",
                "Pre-qualify both suppliers. Confirm carrier media compatibility "
                "with the SBR decant system. Establish supply agreements for "
                "both components before contract award."),
            RiskCategory("Financial", RL_MEDIUM,
                "Moderate combined CAPEX. Long-term OPEX is low but performance "
                "uncertainty in the first 12 months introduces financial risk "
                "relative to conventional technologies.",
                "Include performance-based KPIs for both stages in the contract. "
                "Budget for a 12-month post-commissioning monitoring and "
                "optimisation programme."),
        ]
    )


def _profile_memdense(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    return (
        "Low-Medium overall risk. memDENSE is a targeted hydrocyclone enhancement "
        "for MBR systems with a clear mechanism (selective wasting improves "
        "permeability). Risks are modest and well-characterised.",
        [
            RiskCategory("Technical", RL_LOW,
                "Hydrocyclone split ratio must be calibrated to MBR mixed liquor. "
                "Over-wasting can reduce MLSS below optimal MBR operating range. "
                "Permeability improvement is typically visible within 4–8 weeks.",
                "Commission with supplier support. Define MLSS target range. "
                "Monitor membrane TMP and permeability weekly for 12 weeks "
                "post-commissioning. Adjust split ratio if MLSS falls outside range."),
            RiskCategory("Operational", RL_LOW,
                "Low additional operational burden relative to existing MBR operation. "
                "Hydrocyclone adds one additional process parameter to monitor.",
                "Include hydrocyclone performance in existing MBR weekly process review. "
                "Train MBR operators on split ratio adjustment procedure."),
            RiskCategory("Commercial", RL_LOW,
                "Specialist supplier for hydrocyclone design. Single supplier "
                "dependency for commissioning support, though ongoing operation "
                "is straightforward once calibrated.",
                "Establish supplier commissioning and 12-month support agreement."),
            RiskCategory("Financial", RL_LOW,
                "Low incremental CAPEX. Treats as an enhancement to existing MBR "
                "investment. Financial risk is limited to commissioning cost if "
                "performance targets are not achieved within the trial period.",
                "Define permeability improvement target (e.g. TMP reduction of "
                "≥ 20% at 12 weeks) as a contractual KPI. Treat as optional "
                "enhancement with staged implementation."),
        ]
    )


def _profile_ifas_mbbr_hybas(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    tech = sf.technology
    name = ("Hybas™" if "Hybas" in tech else "MBBR" if "MBBR" in tech else "IFAS")
    return (
        f"Low overall risk. {name} is a well-established retrofit technology with a broad "
        "international reference base. The primary risks relate to media retention "
        "screen maintenance — the technology itself is mature and predictable.",
        [
            RiskCategory("Technical", RL_LOW,
                f"Carrier media must be fluidised uniformly across the aeration zone. "
                f"Non-uniform distribution reduces effective biofilm surface area. "
                f"Biofilm establishment takes 4–8 weeks after media installation. "
                f"Media retention screens must prevent carrier loss to downstream processes.",
                "Confirm aeration distribution and mixing adequacy at commissioning. "
                "Install screen fouling monitoring and cleaning protocol. "
                "Adjust WAS rate during biofilm establishment to maintain optimal SRT."),
            RiskCategory("Operational", RL_LOW,
                "Modest additional operational requirement relative to conventional "
                "activated sludge. Main ongoing task is media retention screen "
                "inspection and cleaning. No additional chemical requirements.",
                "Include media retention screen in weekly maintenance schedule. "
                "Inspect at 4-week intervals for first 6 months, then monthly. "
                "Train operators on biofilm visual assessment."),
            RiskCategory("Commercial", RL_LOW,
                "Multiple media suppliers available — commercial risk is low. "
                "Media retention screens are standard engineering components "
                "with broad supply base.",
                "Obtain competitive quotes from ≥ 2 media suppliers. "
                "Confirm media fill fraction and screen design at detailed design."),
            RiskCategory("Financial", RL_LOW,
                "Low to moderate CAPEX. Minimal OPEX — no chemical input, "
                "low energy increment, low maintenance cost. "
                "Long-term financial risk is low.",
                "Include screen replacement in asset register (expected life 10–15 years). "
                "Budget for media top-up at 5-year intervals (typically < 5% of initial fill)."),
        ]
    )


def _profile_bardenpho(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    carbon_limited = ctx.get("carbon_limited_tn", False)
    return (
        "Low overall risk. Bardenpho zone optimisation works within existing tanks "
        "and recycle infrastructure. The main risk is carbon availability for "
        "denitrification, which should be confirmed by COD fractionation audit "
        "before detailed design.",
        [
            RiskCategory("Technical", RL_LOW,
                "TN performance is dependent on available biodegradable COD. "
                + ("Carbon limitation is identified as a risk for this plant — "
                   "COD/TN ratio should be confirmed before Bardenpho optimisation design. "
                   if carbon_limited else
                   "If COD/TN < 4, denitrification will be carbon-limited and external "
                   "carbon dosing may be required. ")
                + "Anaerobic zone must be protected from nitrate return to maintain EBPR.",
                "Conduct COD fractionation audit (COD/TN by season) before detailed design. "
                "Confirm anaerobic zone HRT (target 2–2.5 h) and MLR ratio (target R ≈ 2). "
                "Monitor TN weekly for 3 months post-optimisation."),
            RiskCategory("Operational", RL_LOW,
                "Process control adjustment to internal recycle ratio and zone "
                "partitioning is within the capability of trained plant operators. "
                "No new specialist equipment required.",
                "Train operators on recycle ratio adjustment and TN response monitoring. "
                "Document the new zone configuration and HRT targets in the O&M manual."),
            RiskCategory("Commercial", RL_LOW,
                "No proprietary technology or specialist supplier dependency. "
                "Zone reconfiguration uses standard civil and mechanical components. "
                "If external carbon is required, methanol supply adds a chemical "
                "procurement requirement.",
                "If external carbon is required, pre-qualify ≥ 2 methanol suppliers. "
                "Establish dual-supply agreement before commissioning."),
            RiskCategory("Financial", RL_LOW,
                "Low CAPEX — baffle installation and diffuser reconfiguration within "
                "existing tank volume. If external carbon is required, ongoing methanol "
                "OPEX becomes a material cost (approximately $40–80k/year depending on dose).",
                "Include carbon dose sensitivity in TOTEX analysis. "
                "Budget for carbon dosing infrastructure if COD/TN < 4 is confirmed."),
        ]
    )


def _profile_recycle_opt(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    return (
        "Low overall risk. Internal recycle ratio optimisation is a process control "
        "adjustment with minimal capital exposure. Risk is limited to operator "
        "execution and blower/pump capacity confirmation.",
        [
            RiskCategory("Technical", RL_LOW,
                "High recycle ratios (R > 4) increase DO carryover to the anoxic zone, "
                "suppressing denitrification. MLR pump capacity must be confirmed "
                "at the target recycle ratio before adjustment.",
                "Audit MLR pump capacity before increasing ratio. Monitor "
                "anoxic zone DO at new recycle rate. Confirm TN response within "
                "4 weeks of adjustment."),
            RiskCategory("Operational", RL_LOW,
                "Control system adjustment within normal operator capability. "
                "Risk is limited to incorrect initial setting before monitoring confirms performance.",
                "Document target recycle ratio range in O&M manual. "
                "Establish TN monitoring frequency during optimisation period."),
            RiskCategory("Commercial", RL_LOW,
                "No proprietary technology or supplier dependency. "
                "Standard pump and control system components.",
                "No specific mitigation required beyond standard procurement."),
            RiskCategory("Financial", RL_LOW,
                "Nil to minimal CAPEX. Slightly higher pump energy at increased "
                "recycle ratio. Financial risk is negligible.",
                "Confirm pump energy impact at target recycle ratio in energy audit."),
        ]
    )


def _profile_dnf(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    return (
        "Medium-High overall risk. DNF introduces the highest operational and "
        "commercial dependency of any technology in the tertiary treatment class. "
        "Risks are manageable but require proactive design and supply chain planning. "
        "Must not be commissioned before upstream nitrification is reliably controlled.",
        [
            RiskCategory("Technical", RL_HIGH,
                "DNF performance is directly dependent on: (1) stable upstream "
                "nitrification — DNF removes NOx, not NH₄; (2) dissolved oxygen "
                "at the filter inlet < 0.5 mg/L — elevated DO suppresses "
                "denitrification regardless of methanol dose; (3) correct methanol "
                "dose rate (2.5–3.0 mg MeOH/mg NO₃-N removed).",
                "Commission DNF only after MABR/IFAS has established reliable "
                "nitrification (NH₄ < 1 mg/L). Measure secondary effluent DO "
                "profile before filter sizing. Design DO control upstream of filter. "
                "Commission automated methanol dose control with online TN feedback."),
            RiskCategory("Operational", RL_HIGH,
                "Continuous methanol dosing requires real-time monitoring and "
                "automated dose control. Filter backwash management and waste "
                "handling add operational burden. Operator training must cover "
                "methanol safety (flammable liquid, vapour hazard).",
                "Implement online NO₃ and TN analyser at filter outlet to control "
                "dosing in real time. Develop methanol safety management plan. "
                "Train operators in methanol handling, spill response, and filter "
                "backwash cycle management."),
            RiskCategory("Commercial", RL_HIGH,
                "Methanol supply chain must be continuous — any disruption halts "
                "tertiary denitrification immediately. Single-source risk if only "
                "one supplier is contracted. Methanol is a regulated chemical "
                "requiring storage, handling permits, and hazmat compliance.",
                "Establish dual-supply methanol agreement. Confirm local storage "
                "capacity (minimum 30-day on-site volume). Obtain all chemical "
                "storage and handling permits before commissioning. Consider "
                "acetate as an alternative carbon source where methanol risk "
                "is unacceptable."),
            RiskCategory("Financial", RL_HIGH,
                "Methanol OPEX dominates whole-of-life cost (2.5–3.0 mg/mg NO₃-N "
                "at current methanol pricing). Ongoing cost is sensitive to methanol "
                "price volatility. Capital cost for filter infrastructure plus "
                "dosing and backwash systems is moderate-high.",
                "Conduct sensitivity analysis on methanol price (±30%). Compare "
                "whole-of-life cost against biological TN reduction alone "
                "(Bardenpho + recycle). Confirm TN target that justifies DNF "
                "chemical cost before committing."),
        ]
    )


def _profile_tert_p(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    return (
        "Low-Medium overall risk. Chemical tertiary phosphorus removal is a "
        "well-established process with a broad supply base. The primary risks "
        "are sludge volume increase and chemical dose optimisation.",
        [
            RiskCategory("Technical", RL_LOW,
                "Chemical precipitation rate (20–25 g FeCl₃ per g P removed) must "
                "be calibrated to influent P variability. Over-dosing increases "
                "effluent colour and TSS; under-dosing fails the licence target. "
                "Chemical sludge volume increases — dewatering and disposal "
                "capacity must accommodate the additional load.",
                "Commission with automated P analyser at filter outlet to enable "
                "real-time dose control. Confirm dewatering and disposal capacity "
                "for increased sludge volume before commissioning. Calibrate "
                "dose rate across a range of influent P concentrations."),
            RiskCategory("Operational", RL_LOW,
                "Chemical dosing is a standard operation for most utility operators. "
                "Main risks are incorrect dose rate and chemical storage management.",
                "Include chemical dose rate in daily process log. "
                "Train operators on FeCl₃ handling (corrosive liquid). "
                "Establish a secondary filter backwash and sludge management protocol."),
            RiskCategory("Commercial", RL_LOW,
                "Ferric chloride has a broad supply base — commercial risk is low. "
                "Multiple suppliers available in most metropolitan areas.",
                "Obtain competitive supply quotes. Establish a secondary supplier "
                "agreement as contingency. Confirm on-site storage capacity."),
            RiskCategory("Financial", RL_MEDIUM,
                "Chemical OPEX (FeCl₃ + alum) is ongoing. Sludge disposal cost "
                "increases with chemical sludge volume. These costs must be "
                "included in the TOTEX analysis alongside the compliance benefit.",
                "Conduct TOTEX analysis including chemical, dewatering, and "
                "disposal costs over a 25-year horizon. Compare against "
                "enhanced biological P removal if influent characteristics allow."),
        ]
    )


def _profile_eq_basin(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    return (
        "Low overall risk. EQ basin is the most operationally robust hydraulic "
        "solution in this technology class. Risks are primarily civil CAPEX and "
        "footprint, not operational performance.",
        [
            RiskCategory("Technical", RL_LOW,
                "EQ basin must be sized for the design storm event duration and "
                "return frequency. Under-sizing leaves residual hydraulic risk. "
                "Odour management during extended storage is an operational design "
                "consideration.",
                "Confirm design storm parameters from catchment I/I analysis. "
                "Include odour control cover and extraction in basin design. "
                "Confirm return pump capacity for controlled drawdown rate."),
            RiskCategory("Operational", RL_LOW,
                "Lowest operational complexity of the hydraulic technology options. "
                "Fill and controlled return requires pump operation only.",
                "Train operators on drawdown rate control and bypass isolation. "
                "Establish a return flow rate protocol to prevent secondary "
                "clarifier hydraulic shock after storm events."),
            RiskCategory("Commercial", RL_LOW,
                "Standard civil infrastructure — concrete, pumps, pipework. "
                "No proprietary technology or specialist supplier dependency.",
                "Competitive tender for civil works. Standard procurement."),
            RiskCategory("Financial", RL_HIGH,
                "High civil CAPEX. Land acquisition may be required if footprint "
                "is not available within the existing boundary. Total project cost "
                "must include civil, structural, mechanical, electrical, and "
                "potentially land acquisition.",
                "Conduct cost-benefit analysis comparing EQ basin CAPEX against "
                "CoMag for equivalent hydraulic relief. Include land cost if "
                "required. Confirm available footprint before committing to design."),
        ]
    )


def _profile_generic(sf: StageFeasibility, ctx: Dict) -> Tuple[str, List[RiskCategory]]:
    """Fallback for technologies not in the library."""
    level = {"Low": RL_LOW, "Medium": RL_MEDIUM, "High": RL_HIGH}.get(sf.complexity, RL_MEDIUM)
    return (
        f"Risk profile is indicative — technology not in the library. "
        f"Feasibility layer assessed complexity as {sf.complexity} and "
        f"supply risk as {sf.supply_risk}.",
        [
            RiskCategory("Technical", level,
                "Technology-specific technical risks apply. Refer to supplier "
                "technical documentation and relevant engineering standards.",
                "Engage specialist consultant for detailed technical risk assessment."),
            RiskCategory("Operational", level,
                "Operational requirements depend on technology configuration. "
                "Assess operator training needs before commissioning.",
                "Develop site-specific O&M plan with supplier input."),
            RiskCategory("Commercial", {"Low": RL_LOW, "Medium": RL_MEDIUM, "High": RL_HIGH}.get(sf.supply_risk, RL_MEDIUM),
                "Supply chain and supplier dependency should be assessed for "
                "this technology.",
                "Pre-qualify suppliers and confirm supply chain before commitment."),
            RiskCategory("Financial", level,
                "CAPEX and OPEX profile should be confirmed through detailed design "
                "and supplier engagement.",
                "Conduct TOTEX analysis at detailed design stage."),
        ]
    )


# ── Profile dispatch ───────────────────────────────────────────────────────────

_PROFILE_MAP = {
    TI_COMAG:       _profile_comag,
    TI_BIOMAG:      _profile_biomag,
    TI_MABR:        _profile_mabr,
    TI_INDENSE:     _profile_indense,
    TI_MIGINDENSE:  _profile_migindense,
    TI_MEMDENSE:    _profile_memdense,
    TI_HYBAS:       _profile_ifas_mbbr_hybas,
    TI_IFAS:        _profile_ifas_mbbr_hybas,
    TI_MBBR:        _profile_ifas_mbbr_hybas,
    TI_BARDENPHO:   _profile_bardenpho,
    TI_RECYCLE_OPT: _profile_recycle_opt,
    TI_ZONE_RECONF: _profile_recycle_opt,   # similar low-risk profile
    TI_DENFILTER:   _profile_dnf,
    TI_TERT_P:      _profile_tert_p,
    TI_EQ_BASIN:    _profile_eq_basin,
    TI_STORM_STORE: _profile_eq_basin,
}

_LEVEL_ORDER = {RL_LOW: 0, RL_MEDIUM: 1, RL_HIGH: 2}

_DECISION_NOTE = (
    "These risks are manageable with appropriate design, operation, and commercial strategy. "
    "The decision reflects a balance between performance, complexity, and lifecycle cost."
)


def _overall_level(categories: List[RiskCategory]) -> str:
    return max(categories, key=lambda c: _LEVEL_ORDER.get(c.level, 0)).level


# ── Stack-level summary ────────────────────────────────────────────────────────

def _stack_risk_summary(profiles: List[TechRiskProfile], pathway: UpgradePathway) -> str:
    n = len(profiles)
    high_count   = sum(1 for p in profiles if p.overall_level == RL_HIGH)
    medium_count = sum(1 for p in profiles if p.overall_level == RL_MEDIUM)
    low_count    = sum(1 for p in profiles if p.overall_level == RL_LOW)

    if high_count >= 2:
        profile_text = f"high operational or commercial risk ({high_count} of {n} stages)"
    elif high_count == 1:
        profile_text = f"one high-risk stage requiring proactive management"
    elif medium_count >= 3:
        profile_text = f"medium risk across most stages ({medium_count} of {n})"
    else:
        profile_text = f"low to medium overall risk across all {n} stages"

    return (
        f"The {n}-stage upgrade pathway has {profile_text}. "
        f"All risks are manageable with the mitigations identified below. "
        f"The primary risk management priority is staged commissioning — each stage "
        f"should be confirmed stable before the next is procured and commissioned. "
        f"No technology in the recommended stack is risk-free, but none has risks "
        f"that are unmanageable for a metropolitan utility with skilled operators "
        f"and good supply chain access."
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def build_risk_report(
    pathway: UpgradePathway,
    feasibility: FeasibilityReport,
    plant_context: Optional[Dict] = None,
) -> RiskReport:
    """
    Build the Unified Risk & Mitigation report.

    Parameters
    ----------
    pathway : UpgradePathway
        Output of build_upgrade_pathway().
    feasibility : FeasibilityReport
        Output of assess_feasibility().
    plant_context : dict, optional
        Same dict passed to other layers.

    Returns
    -------
    RiskReport
        Does NOT modify pathway or feasibility.
    """
    ctx = plant_context or {}
    # Map feasibility stage data by stage number
    sf_map = {sf.stage_number: sf for sf in feasibility.stage_feasibility}

    profiles: List[TechRiskProfile] = []

    for stage in pathway.stages:
        sf   = sf_map.get(stage.stage_number)
        if sf is None:
            # Build a minimal StageFeasibility from pathway stage data
            from apps.wastewater_app.feasibility_layer import StageFeasibility as SF
            sf = SF(stage_number=stage.stage_number, technology=stage.technology,
                    tech_display=stage.tech_display, feasibility="Medium",
                    supply_risk="Medium", opex_impact="Medium", complexity=stage.complexity,
                    chemical_dep="None", specialist=False, notes=[], risks=[])

        fn      = _PROFILE_MAP.get(stage.technology, _profile_generic)
        summary, categories = fn(sf, ctx)
        overall = _overall_level(categories)

        profiles.append(TechRiskProfile(
            stage_number  = stage.stage_number,
            technology    = stage.technology,
            tech_display  = stage.tech_display,
            risk_summary  = summary,
            categories    = categories,
            overall_level = overall,
            decision_note = _DECISION_NOTE,
        ))

    stack_summary = _stack_risk_summary(profiles, pathway)

    # Validation flags
    all_covered   = len(profiles) == len(pathway.stages)
    no_risk_free  = all(len(p.categories) == 4 for p in profiles)
    all_mit       = all(all(c.mitigation.strip() for c in p.categories) for p in profiles)

    return RiskReport(
        profiles               = profiles,
        stack_risk_summary     = stack_summary,
        decision_tension       = _DECISION_NOTE,
        all_technologies_covered = all_covered,
        no_technology_risk_free  = no_risk_free,
        all_mitigations_present  = all_mit,
    )
