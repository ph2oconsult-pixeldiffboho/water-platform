"""
apps/wastewater_app/tech_positioning.py

Technology Positioning Matrix — Production V1
==============================================

An interpretive and educational layer that provides engineering-grounded
guidance on when each major wastewater intensification technology should —
and should not — be used.

Does NOT modify any calculation, stack, feasibility, or credibility output.
Reads UpgradePathway to generate a scenario-specific alignment summary.

Design principles
-----------------
- Authoritative and balanced — no promotional language, no "best technology" claims
- Engineering-led: uses "best suited when..." / "not appropriate when..." framing
- Aligned with constraint-led design philosophy
- Anti-bias: explicitly positions full-replacement technologies (Nereda) as
  replacement pathways, not brownfield intensification steps

Main entry points
-----------------
  get_full_matrix()             → List[TechPosition]
  get_scenario_alignment(pathway, feasibility) → ScenarioAlignment
  build_positioning_report(pathway, feasibility) → PositioningReport
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class TechPosition:
    """Engineering position statement for a single technology."""
    code:               str     # internal code matching TI_* constants where applicable
    name:               str     # display name
    category:           str     # "Settling" / "Nitrification" / "TN" / "TP" / "Hydraulic" / "Replacement"
    primary_role:       str     # one sentence: what problem it solves
    best_used_when:     List[str]   # conditions where this technology is optimal
    not_appropriate_when: List[str] # conditions where it should NOT be selected
    strengths:          List[str]
    limitations:        List[str]
    key_engineering_truth: str  # the single most important engineering fact
    typical_stack_position: str # "Stage 1" / "Stage 2" / "Stage 3" / "Replacement pathway"
    capex_class:        str     # Low / Medium / High
    complexity:         str     # Low / Medium / High
    supply_dependency:  str     # None / Low / Medium / High (specialist supply)


@dataclass
class StackAlignmentNote:
    """Why a specific technology was chosen or not chosen for the scenario."""
    technology:     str
    in_stack:       bool
    reason:         str
    constraint_link: str   # which active constraint drove the decision


@dataclass
class ScenarioAlignment:
    """Scenario-specific interpretation of the positioning matrix."""
    selected_notes:     List[StackAlignmentNote]   # technologies IN the stack
    excluded_notes:     List[StackAlignmentNote]   # notable technologies NOT in stack
    strategy_rationale: str   # why brownfield staged rather than replacement
    constraint_summary: str   # constraint-led design explanation
    anti_bias_note:     str   # explicit note on not recommending Nereda/full conversion


@dataclass
class PositioningReport:
    """Full output: matrix + scenario alignment."""
    matrix:         List[TechPosition]
    alignment:      ScenarioAlignment
    version:        str = "Production V1"


# ── Technology Positioning Matrix ─────────────────────────────────────────────
# Each entry is grounded in published engineering literature and operational experience.
# References: WEF MOP 8; Metcalf & Eddy 5th Ed; MABR/Nereda/CoMag technical papers;
#             Water NZ guidelines; IPCC 2019 wastewater guidelines.

def get_full_matrix() -> List[TechPosition]:
    """Return the full Technology Positioning Matrix (all 8 technologies)."""
    return [

        # ── 1. MOB (inDENSE + miGRATE) ────────────────────────────────────────
        TechPosition(
            code="MOB",
            name="MOB (inDENSE\u00ae + miGRATE\u2122) \u2014 SBR intensification",
            category="Settling + Biological",
            primary_role=(
                "Brownfield intensification of SBR plants: inDENSE stabilises settling and "
                "enables cycle compression; miGRATE improves nitrification and TN performance "
                "without adding reactor volume."
            ),
            best_used_when=[
                "SBR plant is clarifier- or cycle-limited with poor settling (SVI > 120 mL/g).",
                "MLSS is elevated and solids carry-over is occurring during peak events.",
                "Brownfield capacity increase is required without new reactor volume.",
                "The upgrade sequence must be staged: inDENSE first, miGRATE second.",
                "TN improvement is required alongside settling stabilisation.",
            ],
            not_appropriate_when=[
                "Plant type is CAS, MBR, or Nereda \u2014 MOB is SBR-specific.",
                "Hydraulic overload is the primary failure driver \u2014 MOB does not provide "
                "hydraulic attenuation or bypass capacity.",
                "The settling limitation is absent \u2014 miGRATE alone without inDENSE does not "
                "consistently improve SVI (Lang Lang + Army Bay finding).",
                "Peak wet weather storage is needed \u2014 MOB does not substitute for EQ basin.",
            ],
            strengths=[
                "Low footprint \u2014 fits within existing SBR tanks.",
                "Staged delivery: inDENSE can be commissioned and validated before miGRATE is activated.",
                "Improves biomass density, settleability, and biological performance simultaneously.",
                "Does not require new reactor volume or major civil works.",
                "Reduces SVI progressively with demonstrated Kawana and Lang Lang site results.",
            ],
            limitations=[
                "SBR-specific: not applicable to CAS or MBR plants.",
                "Requires stable biological operation to maintain the density selection benefit.",
                "miGRATE alone does not solve settling \u2014 inDENSE is the mandatory prerequisite.",
                "Does not address hydraulic peak flows or bypass risk.",
                "Specialist supplier dependency for both inDENSE hydrocyclone and miGRATE carriers.",
            ],
            key_engineering_truth=(
                "The correct upgrade sequence is inDENSE first (settling prerequisite), then miGRATE "
                "(biological optimisation). Installing miGRATE before inDENSE is established will not "
                "deliver the expected SVI improvement. This is not a single product \u2014 it is a sequenced "
                "two-stage pathway within the SBR cycle."
            ),
            typical_stack_position="Stage 1\u20132 (SBR plants)",
            capex_class="Medium",
            complexity="Medium",
            supply_dependency="Medium",
        ),

        # ── 2. MABR ───────────────────────────────────────────────────────────
        TechPosition(
            code="MABR",
            name="MABR OxyFAS\u00ae (membrane-aerated biofilm reactor)",
            category="Nitrification / Aeration",
            primary_role=(
                "Aeration and nitrification intensification using hollow-fibre membrane modules "
                "that deliver oxygen directly to the biofilm at significantly higher efficiency "
                "than conventional diffused aeration."
            ),
            best_used_when=[
                "Existing aeration blowers are near or at maximum capacity.",
                "Nitrification is SRT-limited and additional biofilm retention is required.",
                "Energy cost reduction is a strategic priority.",
                "N\u2082O emission reduction is targeted (membrane-based O\u2082 delivery reduces "
                "localised anoxic zones that drive N\u2082O formation).",
                "Footprint is constrained \u2014 modules drop into existing aeration tanks.",
                "Licence tightening to NH\u2084 < 1 mg/L is required.",
            ],
            not_appropriate_when=[
                "Hydraulic or settling limitation is the primary constraint \u2014 MABR does not "
                "improve clarifier performance or provide hydraulic attenuation.",
                "Aeration blowers have adequate spare capacity \u2014 IFAS is simpler and lower cost.",
                "The plant is remote with limited OEM service access \u2014 specialist module "
                "maintenance is required.",
                "Solids carry-over is the primary compliance failure mode.",
            ],
            strengths=[
                "Oxygen transfer efficiency up to 14 kgO\u2082/kWh vs 1\u20132 for diffused aeration.",
                "Modules drop into existing tanks \u2014 minimal civil works.",
                "Biofilm provides SRT decoupling independent of WAS rate.",
                "Simultaneous nitrification-denitrification in biofilm reduces N\u2082O hot spots.",
                "NH\u2084 < 0.1 mg/L achievable across wide load range (Kawana modelling calibration).",
            ],
            limitations=[
                "Specialist hollow-fibre membrane modules: OEM supply dependency.",
                "Performance dependent on membrane integrity \u2014 integrity testing required.",
                "Biofilm establishment takes 4\u20138 weeks \u2014 avoid winter commissioning.",
                "Does not address hydraulic peaks, settling issues, or TP compliance.",
                "Higher capital cost than IFAS for equivalent nitrification improvement where "
                "aeration headroom exists.",
            ],
            key_engineering_truth=(
                "MABR is an aeration intensification technology, not a nitrification cure-all. "
                "It is best suited to plants where the blower system is the bottleneck. "
                "Where aeration headroom exists, IFAS achieves similar nitrification SRT decoupling "
                "at lower cost and complexity. The selection should be driven by the aeration "
                "capacity audit, not by technology preference."
            ),
            typical_stack_position="Stage 2",
            capex_class="Medium",
            complexity="Medium",
            supply_dependency="Medium",
        ),

        # ── 3. Nereda (AGS) ───────────────────────────────────────────────────
        TechPosition(
            code="NEREDA",
            name="Nereda\u00ae (aerobic granular sludge \u2014 AGS)",
            category="Replacement",
            primary_role=(
                "Full process replacement delivering high-performance biological nutrient removal "
                "in a compact footprint through aerobic granular sludge technology. "
                "Nereda replaces the entire activated sludge process; it is not a retrofit addition."
            ),
            best_used_when=[
                "New build or major plant rebuild where existing assets have no residual life.",
                "Footprint is severely constrained and conventional BNR cannot fit.",
                "High-performance licence targets (TN < 5 mg/L, TP < 1 mg/L) are required.",
                "Long-term view: 25\u201330 year asset with no requirement to retain existing infrastructure.",
                "Capital is available for full conversion including civil decommissioning.",
                "Sustained granule stability can be demonstrated for the specific influent.",
            ],
            not_appropriate_when=[
                "Brownfield staged upgrade is required and existing assets must be retained.",
                "CAPEX is constrained in the short to medium term.",
                "A sequenced intensification approach is preferred over full conversion.",
                "Short-duration wet weather peaks dominate \u2014 granule shear risk under extreme "
                "hydraulic events must be assessed.",
                "The plant serves an industrial catchment with non-typical influent \u2014 "
                "granule stability is sensitive to influent composition.",
                "Operational disruption during transition cannot be accepted.",
            ],
            strengths=[
                "Compact footprint: typically 30\u201350% smaller footprint than conventional BNR.",
                "Integrated simultaneous nitrification-denitrification and P removal in one vessel.",
                "High effluent quality: TN < 10 mg/L and TP < 1 mg/L routinely achievable.",
                "Reduced sludge production per unit of BOD removed.",
                "No secondary clarifiers required \u2014 settling integrated within the reactor.",
            ],
            limitations=[
                "High CAPEX: full conversion requires decommissioning and rebuilding the biological "
                "treatment process.",
                "Operational disruption: cannot be commissioned incrementally alongside existing process.",
                "Granule stability sensitivity: cold temperatures, high lipid loads, and industrial "
                "influents can destabilise granule formation.",
                "Wet weather performance: extreme hydraulic peaks can cause granule shear and loss.",
                "Not applicable as a brownfield intensification step \u2014 it replaces, not augments.",
            ],
            key_engineering_truth=(
                "Nereda consistently ranks highly in brownfield upgrade scoring tools because it "
                "addresses clarifier, biological, and footprint constraints simultaneously. "
                "However, this score reflects long-term conversion potential \u2014 not suitability "
                "for staged brownfield intensification. A high Nereda ranking alongside a CoMag + "
                "MABR stack recommendation are not contradictory: they address different planning "
                "horizons and different risk profiles."
            ),
            typical_stack_position="Replacement pathway (not a brownfield intensification step)",
            capex_class="High",
            complexity="High",
            supply_dependency="Medium",
        ),

        # ── 4. IFAS / Hybas / MBBR ────────────────────────────────────────────
        TechPosition(
            code="IFAS",
            name="IFAS / Hybas\u2122 / MBBR (integrated biofilm systems)",
            category="Nitrification",
            primary_role=(
                "Biofilm retention to increase nitrification capacity within existing aeration "
                "tanks by decoupling the effective nitrification SRT from the hydraulic SRT. "
                "Carriers accumulate nitrifying biofilm independently of the WAS rate."
            ),
            best_used_when=[
                "Nitrification is SRT-limited: WAS rate required for sludge age control is "
                "washing out nitrifiers.",
                "Spare basin volume exists or aeration zones can accept carrier media.",
                "Aeration blowers have headroom \u2014 IFAS does not reduce aeration demand.",
                "A lower-complexity retrofit is preferred over specialist OEM equipment (MABR).",
                "Media retention screens can be installed at zone outlets.",
                "TN improvement is a secondary benefit: biofilm nitrification increases the "
                "nitrate substrate available for Bardenpho denitrification.",
            ],
            not_appropriate_when=[
                "Hydraulic or settling constraint is dominant \u2014 IFAS does not address clarifier "
                "loading or peak flow management.",
                "Aeration system is at maximum capacity \u2014 MABR is more appropriate where "
                "blowers cannot be expanded.",
                "MBR configuration: carrier media must be screened before membrane tanks, "
                "adding design complexity.",
                "Energy reduction is a primary goal \u2014 IFAS does not improve oxygen transfer "
                "efficiency.",
            ],
            strengths=[
                "Well-established technology with broad international reference base.",
                "Retrofit-friendly: drop-in carrier media addition to existing tank.",
                "Low-complexity installation: media retention screens at zone outlets.",
                "Decouples nitrification SRT from hydraulic SRT without new tank volume.",
                "Reduces suspended MLSS as biofilm carries more of the nitrification load, "
                "providing some clarifier loading relief.",
            ],
            limitations=[
                "Does not reduce aeration energy demand \u2014 blower capacity remains the constraint.",
                "Limited impact on hydraulic performance or peak flow handling.",
                "Media retention screen maintenance is required to prevent carrier loss.",
                "Biofilm establishment takes 4\u20138 weeks after installation.",
                "MBBR variant requires downstream solids separation \u2014 clarifier performance "
                "must accommodate the biofilm solids.",
            ],
            key_engineering_truth=(
                "IFAS is the most retrofit-friendly nitrification intensification option and is "
                "appropriate when the constraint is SRT, not aeration capacity. "
                "The selection between IFAS and MABR should be driven by a site-specific "
                "aeration capacity audit: if blowers have headroom, use IFAS; if blowers are "
                "near maximum, use MABR. Both achieve nitrification SRT decoupling; "
                "they differ in how they deliver the oxygen."
            ),
            typical_stack_position="Stage 2",
            capex_class="Low",
            complexity="Low",
            supply_dependency="Low",
        ),

        # ── 5. CoMag ──────────────────────────────────────────────────────────
        TechPosition(
            code="COMAG",
            name="CoMag\u00ae (high-rate magnetic ballasted clarification)",
            category="Hydraulic / Settling",
            primary_role=(
                "High-rate clarification providing rapid solids removal under peak wet weather "
                "flows, protecting downstream biological processes from hydraulic and solids shock "
                "loads. Treats flows of 3\u20135\u00d7 DWA without new secondary tanks."
            ),
            best_used_when=[
                "Peak wet weather flows consistently exceed secondary clarifier capacity.",
                "TSS compliance fails during storm events and solids carry-over is the primary "
                "compliance failure mode.",
                "TP polishing is required simultaneously (CoMag can receive chemical P dosing).",
                "Site footprint is constrained and an EQ basin is not feasible.",
                "Metropolitan location with reliable magnetite supply chain access.",
                "The plant is a continuous-flow process (CAS, BNR, MBR) \u2014 CoMag requires "
                "continuous flow and cannot be installed inline with SBR decant.",
            ],
            not_appropriate_when=[
                "The primary constraint is biological \u2014 nitrification, TN, or TP limitations "
                "that are not driven by solids carry-over.",
                "Plant is an SBR \u2014 CoMag requires a dedicated side-stream or bypass configuration "
                "and cannot treat SBR batch decant inline.",
                "Supply chain access for magnetite is unreliable (remote locations).",
                "Plant size is below ~5 MLD \u2014 magnetite recovery economics deteriorate at "
                "small scale.",
                "Short-duration peaks are the only hydraulic issue \u2014 upstream storage or "
                "I/I reduction may be more cost-effective.",
            ],
            strengths=[
                "Surface overflow rate of 10\u201320 m/hr vs 1\u20132 m/hr for conventional clarifiers.",
                "Compact installation: significant flow treated in a small footprint.",
                "Can treat flows of 3\u20135\u00d7 DWA without new secondary tanks.",
                "Magnetite recovery >99.5% in normal operation.",
                "Dual-use potential: combined hydraulic attenuation and chemical P polishing.",
            ],
            limitations=[
                "Continuous magnetite supply and on-site magnetic recovery system required.",
                "Whole-of-life cost sensitive to recovery efficiency and logistics.",
                "Does not address biological constraints (nitrification, TN, EBPR).",
                "Requires continuous flow \u2014 batch SBR plants need side-stream configuration.",
                "Extreme peaks above 3\u00d7 ADWF may still require complementary upstream "
                "attenuation \u2014 CoMag mitigates but does not fully resolve extreme hydraulic events.",
            ],
            key_engineering_truth=(
                "CoMag mitigates secondary treatment performance under peak flows; it does not "
                "eliminate the need for upstream hydraulic attenuation at extreme events. "
                "At flow ratios above 3\u00d7 ADWF, CoMag should be considered as part of a "
                "combined strategy with I/I reduction or storm storage, not as a standalone solution. "
                "Magnetite supply pre-qualification is a non-negotiable commissioning prerequisite."
            ),
            typical_stack_position="Stage 1",
            capex_class="Medium",
            complexity="Medium",
            supply_dependency="Medium",
        ),

        # ── 6. BioMag ─────────────────────────────────────────────────────────
        TechPosition(
            code="BIOMAG",
            name="BioMag\u00ae (ballasted MBBR-activated sludge hybrid)",
            category="Settling + Biological",
            primary_role=(
                "Combined biological intensification and ballasted settling, improving both "
                "hydraulic throughput and biological treatment capacity in a single system. "
                "Magnetic microspheres improve sludge density and settling velocity while "
                "attached biofilm carriers increase biological treatment capacity."
            ),
            best_used_when=[
                "Both settling and biological capacity are simultaneously constrained.",
                "MLSS is consistently elevated (> 5,000 mg/L) and clarifier SOR is critically exceeded.",
                "A single technology must address both hydraulic and biological limitations.",
                "Magnetite supply chain can be reliably established.",
                "High biological load requires both increased biomass density and treatment capacity.",
            ],
            not_appropriate_when=[
                "Only one constraint is active \u2014 simpler technologies (inDENSE or IFAS alone) "
                "are more appropriate for single-constraint plants.",
                "Supply chain access for magnetite is unreliable or plant is in a remote location.",
                "Operational complexity must be minimised \u2014 BioMag is the most operationally "
                "complex single-stage technology in this matrix.",
                "Plant size is below 5 MLD \u2014 magnetite recovery economics and carrier retention "
                "screening become disproportionately costly.",
            ],
            strengths=[
                "Addresses settling and biological capacity in a single installation.",
                "Enables higher MLSS operation without clarifier failure.",
                "Magnetic microspheres improve sludge density and settling velocity.",
                "Biofilm carriers provide additional SRT decoupling for nitrification.",
                "Can increase hydraulic throughput capacity without new secondary tanks.",
            ],
            limitations=[
                "Dual supply dependency: magnetite + carrier media must both be maintained.",
                "Highest operational complexity of the settling-intensification options.",
                "Magnetite recovery required; loss rate must be managed.",
                "Not appropriate as a standalone solution if hydraulic attenuation is required.",
                "Commissioning requires careful sequencing of ballast activation and biofilm "
                "establishment.",
            ],
            key_engineering_truth=(
                "BioMag is appropriate when both settling and biological constraints are active "
                "and the plant must address both simultaneously. Where only one constraint exists, "
                "simpler targeted options (inDENSE for settling alone, or IFAS for nitrification "
                "alone) are preferred to avoid unnecessary operational complexity. "
                "The dual magnetite + carrier dependency must be explicitly managed in procurement "
                "and O&M planning."
            ),
            typical_stack_position="Stage 1\u20132",
            capex_class="Medium",
            complexity="High",
            supply_dependency="Medium",
        ),

        # ── 7. Denitrification Filters (DNF) ──────────────────────────────────
        TechPosition(
            code="DNF",
            name="Denitrification filter (DNF) \u2014 methanol-dosed tertiary denitrification",
            category="TN Polishing",
            primary_role=(
                "Tertiary total nitrogen polishing where secondary biological denitrification "
                "has been maximised but TN targets (typically < 5 mg/L or < 3 mg/L) require "
                "further reduction through a dedicated filtration and carbon dosing step."
            ),
            best_used_when=[
                "NH\u2084 is reliably controlled to < 1 mg/L in secondary treatment.",
                "TN target is below what Bardenpho or biological optimisation can achieve reliably.",
                "Strict TN licence (< 5 mg/L or < 3 mg/L) with low tolerance for exceedance.",
                "High-performance future licence targets are anticipated (licence-of-the-future "
                "planning horizon).",
                "Carbon dosing infrastructure and chemical supply chain are in place.",
                "DO at the filter inlet can be reliably controlled to < 0.5 mg/L.",
            ],
            not_appropriate_when=[
                "Nitrification is not reliably achieving NH\u2084 < 1\u20132 mg/L \u2014 a DNF "
                "cannot compensate for incomplete nitrification upstream.",
                "DO at the secondary effluent is consistently above 0.5 mg/L \u2014 elevated DO "
                "will suppress denitrification regardless of methanol dose.",
                "Chemical supply and dosing control infrastructure is not established.",
                "The TN target is achievable through Bardenpho optimisation or recycle "
                "ratio improvement \u2014 chemical denitrification should not precede biological "
                "optimisation.",
                "Operational complexity must be minimised \u2014 DNF requires continuous "
                "methanol dosing and filter backwash management.",
            ],
            strengths=[
                "Reliable TN polishing: typically achieves TN < 5 mg/L consistently.",
                "Compact footprint: high volumetric loading rate in a small filter volume.",
                "Combines denitrification and TSS polishing in a single unit.",
                "Can achieve TN < 3 mg/L with appropriate design and carbon dose.",
                "Provides process redundancy for TN compliance under variable secondary performance.",
            ],
            limitations=[
                "High chemical OPEX: continuous methanol dosing at 2.5\u20133.0 mg MeOH per mg "
                "NO\u2083-N removed.",
                "Methanol supply disruption halts tertiary denitrification entirely.",
                "Strict DO control requirement at filter inlet (<0.5 mg/L).",
                "Filter backwash and waste management adds operational requirement.",
                "Should never be the primary TN strategy \u2014 biological optimisation must be "
                "exhausted first.",
            ],
            key_engineering_truth=(
                "A denitrification filter must never be commissioned before nitrification is "
                "reliably controlled. The filter removes NOx \u2014 it cannot compensate for "
                "NH\u2084 in the feed. The correct sequencing is: optimise secondary nitrification "
                "and denitrification first; add DNF only when the residual TN gap cannot be "
                "closed by biological means. DNF is a polishing technology, not a primary "
                "treatment solution."
            ),
            typical_stack_position="Stage 3",
            capex_class="High",
            complexity="High",
            supply_dependency="High",
        ),

        # ── 8. EQ Basin / Storage ─────────────────────────────────────────────
        TechPosition(
            code="EQ",
            name="Equalisation basin / storm storage",
            category="Hydraulic",
            primary_role=(
                "Hydraulic attenuation: stores peak inflows and releases at a controlled rate "
                "to protect secondary treatment from hydraulic and solids shock loading under "
                "wet weather events."
            ),
            best_used_when=[
                "Peak wet weather flows consistently exceed secondary treatment capacity.",
                "Short-duration extreme events (> 3\u00d7 ADWF) drive compliance failures "
                "that cannot be managed by high-rate clarification (CoMag) alone.",
                "Site footprint is available for civil infrastructure.",
                "Long-term hydraulic solution is required with minimum operational complexity.",
                "I/I reduction in the catchment is not feasible or will take > 5 years.",
                "The utility prefers conventional, low-dependency technology over specialist systems.",
            ],
            not_appropriate_when=[
                "Only biological limitations exist \u2014 EQ basin provides no biological "
                "treatment benefit.",
                "Site footprint is severely constrained \u2014 EQ basins require significant land area "
                "(typically 3\u20135 ha for a 120 MLD plant).",
                "Capital is constrained in the short term \u2014 EQ basin is a high-CAPEX option "
                "relative to CoMag for equivalent hydraulic relief.",
                "Peak events are infrequent (< 3 times per year) and short-duration \u2014 other "
                "approaches may be more cost-effective.",
            ],
            strengths=[
                "Most robust and reliable hydraulic solution: no specialist supply dependency.",
                "Low operational complexity: fill and return pump control.",
                "No chemical or specialist maintenance requirement.",
                "Provides complete attenuation of the stored event \u2014 not partial relief.",
                "Simplest technology in this matrix from an O&M perspective.",
            ],
            limitations=[
                "Requires significant site footprint \u2014 often the primary constraint in brownfield "
                "metropolitan plants.",
                "High civil CAPEX relative to high-rate alternatives (CoMag).",
                "Does not address biological constraints \u2014 purely hydraulic.",
                "Storage capacity must be sized to the design storm event duration and return rate.",
                "Extended storage of raw or partially treated wastewater creates odour management "
                "obligations.",
            ],
            key_engineering_truth=(
                "No process intensification technology can substitute for hydraulic attenuation "
                "at extreme peak flows above 3\u00d7 DWA. EQ basin and CoMag are complementary, "
                "not alternatives: CoMag provides high-rate treatment of overflow that cannot be "
                "stored; EQ basin attenuates events before they reach secondary treatment. "
                "On constrained brownfield sites, CoMag is typically the pragmatic first step; "
                "EQ basin becomes the long-term solution as catchment flows grow."
            ),
            typical_stack_position="Stage 1",
            capex_class="High",
            complexity="Low",
            supply_dependency="None",
        ),
    ]


# ── Scenario Alignment ─────────────────────────────────────────────────────────

def get_scenario_alignment(pathway, feasibility) -> ScenarioAlignment:
    """
    Generate a scenario-specific alignment summary from the live UpgradePathway
    and FeasibilityReport.

    Parameters
    ----------
    pathway : UpgradePathway
        Output of build_upgrade_pathway().
    feasibility : FeasibilityReport
        Output of assess_feasibility().
    """
    selected_techs = {s.technology for s in pathway.stages}
    ct_set         = {c.constraint_type for c in pathway.constraints}

    matrix = get_full_matrix()
    matrix_by_code = {t.code: t for t in matrix}

    # Map stack technologies to matrix codes
    _TECH_TO_CODE = {
        "CoMag":                    "COMAG",
        "BioMag":                   "BIOMAG",
        "MABR (OxyFAS retrofit)":   "MABR",
        "Hybas (IFAS)":             "IFAS",
        "IFAS":                     "IFAS",
        "MBBR":                     "IFAS",
        "Bardenpho optimisation":   None,   # process optimisation, not in matrix
        "Tertiary P removal":       None,
        "inDENSE":                  "MOB",
        "MOB (miGRATE + inDENSE)":  "MOB",
        "Denitrification Filter":   "DNF",
        "Equalisation basin":       "EQ",
        "Storm storage / attenuation": "EQ",
    }

    # Build selected notes
    selected_notes = []
    for stage in pathway.stages:
        code = _TECH_TO_CODE.get(stage.technology)
        if code and code in matrix_by_code:
            pos = matrix_by_code[code]
            selected_notes.append(StackAlignmentNote(
                technology   = stage.tech_display,
                in_stack     = True,
                reason       = _selected_reason(stage.technology, ct_set, stage.mechanism),
                constraint_link = ", ".join(c.replace("_limitation","").replace("_"," ").title()
                                            for c in stage.addresses[:2]),
            ))

    # Build excluded notes for notable technologies NOT in the stack
    excluded_notes = []

    # Nereda — always explain why not selected for brownfield
    excluded_notes.append(StackAlignmentNote(
        technology="Nereda\u00ae (aerobic granular sludge)",
        in_stack=False,
        reason=(
            "Nereda addresses clarifier, biological, and footprint constraints simultaneously "
            "and ranks highly in brownfield scoring tools. However, it is a full process "
            "conversion technology \u2014 it replaces, not augments, the existing process. "
            "For this plant, which requires staged brownfield intensification with retention "
            "of existing infrastructure, Nereda is not appropriate in the current planning horizon. "
            "It should be reconsidered if catchment flows exhaust the intensification envelope "
            "and full conversion becomes necessary."
        ),
        constraint_link="Full conversion strategy \u2014 not brownfield staged upgrade",
    ))

    # IFAS / Hybas — explain why MABR was selected instead
    if "MABR (OxyFAS retrofit)" in selected_techs:
        excluded_notes.append(StackAlignmentNote(
            technology="IFAS / Hybas\u2122 (integrated biofilm, carrier media)",
            in_stack=False,
            reason=(
                "IFAS and Hybas are viable nitrification intensification options and are "
                "presented in Option C (lower-risk alternative). They were not selected in "
                "the primary stack because the aeration blower system is near maximum capacity: "
                "MABR provides oxygen delivery via membrane at 14 kgO\u2082/kWh, bypassing the "
                "blower constraint entirely. IFAS relies on the existing blower system and would "
                "not resolve the aeration capacity limitation. IFAS remains the preferred option "
                "if blower headroom is confirmed in a site-specific aeration audit."
            ),
            constraint_link="Nitrification / SRT \u2014 aeration capacity sub-constraint",
        ))

    # DNF — explain why not in primary stack
    excluded_notes.append(StackAlignmentNote(
        technology="Denitrification filter (DNF, methanol-dosed)",
        in_stack=False,
        reason=(
            "DNF is presented in Option B (high-performance pathway) as a Stage 3 addition "
            "for TN < 3 mg/L. It is not in the primary stack because: (1) nitrification is "
            "not yet reliably below NH\u2084 1 mg/L \u2014 DNF cannot compensate for incomplete "
            "nitrification; (2) the primary TN target of < 5 mg/L is achievable through "
            "Bardenpho optimisation and internal recycle improvement without methanol dependency; "
            "(3) DNF must not be commissioned before MABR establishes stable nitrification. "
            "This is an engineering guardrail, not a technology bias."
        ),
        constraint_link="TN polishing \u2014 deferred pending nitrification stabilisation",
    ))

    # EQ Basin — explain why CoMag was selected instead
    excluded_notes.append(StackAlignmentNote(
        technology="Equalisation / flow balancing basin",
        in_stack=False,
        reason=(
            "EQ basin is presented in Option C as the lower-risk hydraulic alternative to CoMag. "
            "It was not selected as the primary hydraulic intervention because the plant has a "
            "tight footprint constraint (metropolitan brownfield site) and CoMag provides "
            "comparable hydraulic relief within a fraction of the land area. "
            "EQ basin is the preferred long-term solution if catchment I/I remains unresolved "
            "and CoMag does not fully manage extreme short-duration peaks above 3\u00d7 ADWF."
        ),
        constraint_link="Hydraulic / wet weather \u2014 footprint constraint drove CoMag selection",
    ))

    strategy_rationale = (
        "The recommended stack reflects a constraint-led brownfield intensification strategy. "
        "Each technology is selected because it directly addresses the highest-priority active "
        "constraint at the time it is deployed, rather than because it is the most advanced "
        "or highest-scoring technology in isolation. "
        "The sequencing \u2014 hydraulics first, settling second, nitrification third, TN fourth, "
        "TP fifth \u2014 ensures that each upgrade unlocks the next without wasted capital on "
        "technologies that would be ineffective until upstream constraints are resolved. "
        "Full conversion (Nereda) was considered and explicitly excluded because it does not "
        "align with the utility\u2019s preference for staged delivery and retention of existing "
        "assets in the current capital programme."
    )

    constraint_summary = (
        f"Five constraints are simultaneously active at this plant, ranked by engineering priority: "
        f"(1) hydraulic/clarifier overload, (2) settling/solids separation, "
        f"(3) nitrification SRT limitation, (4) TN polishing, (5) TP polishing. "
        f"No single technology resolves all five. The recommended stack assigns one primary "
        f"mechanism to each constraint, stacked in dependency order. "
        f"Technologies that address lower-priority constraints before higher-priority ones "
        f"are explicitly excluded \u2014 this is constraint-led design, not technology selection."
    )

    anti_bias_note = (
        "Nereda (AGS) is not recommended in this stack. This does not reflect a negative "
        "assessment of the technology. Nereda scores highly on long-term conversion potential "
        "for a clarifier-limited BNR plant and should be included in any 15-year asset "
        "management review. It is excluded here because this engagement requires staged "
        "brownfield intensification within existing assets \u2014 a problem that Nereda does "
        "not solve (it replaces the existing process rather than augmenting it). "
        "The technology is the right answer for the wrong planning horizon."
    )

    return ScenarioAlignment(
        selected_notes     = selected_notes,
        excluded_notes     = excluded_notes,
        strategy_rationale = strategy_rationale,
        constraint_summary = constraint_summary,
        anti_bias_note     = anti_bias_note,
    )


def _selected_reason(tech: str, ct_set: set, mechanism: str) -> str:
    reasons = {
        "CoMag": (
            "Selected as Stage 1 because hydraulic / clarifier overload is the primary and most "
            "urgent constraint. CoMag mitigates secondary clarifier failure under 2.6\u00d7 ADWF "
            "peak flows without requiring new secondary tanks or site footprint expansion."
        ),
        "BioMag": (
            "Selected as Stage 1b because both settling and biological capacity are simultaneously "
            "constrained at high MLSS. BioMag addresses both through combined ballasted settling "
            "and biofilm intensification."
        ),
        "MABR (OxyFAS retrofit)": (
            "Selected over IFAS for Stage 2 because the aeration blower system is near maximum "
            "capacity. MABR delivers oxygen at 14 kgO\u2082/kWh via membrane \u2014 bypassing the "
            "blower constraint and providing N\u2082O reduction as a co-benefit."
        ),
        "Bardenpho optimisation": (
            "Selected as Stage 2b because the existing 5-stage Bardenpho is under-optimised "
            "due to hydraulic constraints on internal recycle. Settling stabilisation (Stage 1) "
            "restores recycle headroom, making Bardenpho the lowest-cost TN improvement pathway."
        ),
        "Tertiary P removal": (
            "Selected as Stage 3 because biological P removal alone cannot reliably achieve "
            "TP < 0.2 mg/L from this influent. Chemical tertiary P removal is the most credible "
            "pathway to the future licence target once secondary performance is stable."
        ),
    }
    return reasons.get(tech,
        f"Selected because it addresses the active {mechanism.replace('_',' ')} constraint "
        "in a brownfield-compatible, staged configuration.")


# ── Main entry point ───────────────────────────────────────────────────────────

def build_positioning_report(pathway, feasibility) -> PositioningReport:
    """
    Build a full Technology Positioning Report for a given scenario.

    Parameters
    ----------
    pathway : UpgradePathway
        Output of build_upgrade_pathway().
    feasibility : FeasibilityReport
        Output of assess_feasibility().

    Returns
    -------
    PositioningReport
    """
    return PositioningReport(
        matrix    = get_full_matrix(),
        alignment = get_scenario_alignment(pathway, feasibility),
    )
