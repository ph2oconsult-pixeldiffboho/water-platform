"""
AquaPoint Reasoning Engine — Contaminant-Specific Modules
Conditional activation based on Gate 2 classification.

Modules:
- Arsenic removal pathway selection
- PFAS removal pathway assessment
- Taste and odour (MIB/geosmin) management
- Cyanotoxin treatment strategy
- Iron and manganese removal
"""

from dataclasses import dataclass, field
from typing import Optional
from .classifier import SourceWaterInputs


@dataclass
class ContaminantModuleResult:
    module: str = ""
    contaminant_summary: str = ""
    preferred_pathway: str = ""
    preferred_pathway_rationale: str = ""
    alternative_pathways: list = field(default_factory=list)
    residuals_implications: list = field(default_factory=list)
    critical_preconditions: list = field(default_factory=list)
    key_risks: list = field(default_factory=list)
    problem_transfer_flag: str = ""
    next_steps: list = field(default_factory=list)


# ─── ARSENIC MODULE ───────────────────────────────────────────────────────────

def assess_arsenic(inputs: SourceWaterInputs) -> ContaminantModuleResult:
    result = ContaminantModuleResult(module="arsenic")
    conc = inputs.arsenic_ug_l

    result.contaminant_summary = (
        f"Arsenic: {conc} μg/L detected. "
        f"Australian Drinking Water Guideline: 7 μg/L (health, 2022). "
        f"Arsenic speciation (As(III) vs As(V)) is critical — As(III) does not adsorb well "
        f"to iron-based media or co-precipitate with ferric coagulant without prior oxidation."
    )

    # Speciation assessment
    speciation_notes = []
    if inputs.source_type == "groundwater":
        speciation_notes.append(
            "Groundwater is typically anaerobic — As(III) is likely to dominate. "
            "Pre-oxidation (aeration, chlorination, or permanganate) will be required "
            "to convert As(III) to As(V) before adsorption or co-precipitation."
        )
    else:
        speciation_notes.append(
            "Surface water is typically aerobic — As(V) is likely to dominate. "
            "Confirm with speciation testing. If As(III) is present, pre-oxidation is required."
        )

    # Iron context
    iron_context = ""
    if inputs.iron_median_mg_l > 0.5:
        iron_context = (
            f"Elevated iron ({inputs.iron_median_mg_l} mg/L): iron and arsenic are co-occurring. "
            "Iron removal process (aeration + filtration or greensand) may achieve "
            "partial arsenic removal via co-precipitation with iron hydroxides. "
            "Combined iron/arsenic removal should be assessed."
        )

    # Pathway selection
    if conc > 50:
        result.preferred_pathway = "RO (Reverse Osmosis)"
        result.preferred_pathway_rationale = (
            f"Arsenic {conc} μg/L is very high. RO provides reliable, high-efficiency removal "
            "across both As(III) and As(V) without speciation uncertainty. "
            "RO concentrate management becomes the primary residuals challenge."
        )
    elif conc > 20:
        result.preferred_pathway = "Iron-based adsorptive media (GFH / Fe-oxide) with pre-oxidation"
        result.preferred_pathway_rationale = (
            f"Arsenic {conc} μg/L: iron-based adsorptive media (GFH, ferric oxide) "
            "provides reliable, targeted removal at this concentration. "
            "Pre-oxidation is required to ensure As(V) speciation. "
            "Simpler and more cost-effective than RO for standalone arsenic at this level."
        )
    elif conc > 7:
        result.preferred_pathway = "Enhanced coagulation / co-precipitation with ferric coagulant + pre-oxidation"
        result.preferred_pathway_rationale = (
            f"Arsenic {conc} μg/L (slightly above guideline): enhanced coagulation with ferric "
            "coagulant can achieve co-precipitation of As(V) within the existing clarification process. "
            "Simpler and lower capital than dedicated media. "
            "Monitor arsenic in clarifier effluent to confirm removal target is reliably achieved."
        )
    else:
        result.preferred_pathway = "Monitoring — treatment not currently required"
        result.preferred_pathway_rationale = (
            f"Arsenic {conc} μg/L is below the ADWG 7 μg/L guideline. "
            "Treatment is not required, but trend monitoring is recommended."
        )

    result.alternative_pathways = [
        "Activated alumina (pH-sensitive — operates best at pH 5.5–6.0; requires pH adjustment)",
        "Ion exchange (anion IX) — effective for As(V); competing ions (phosphate, silicate) reduce performance",
        "RO — reliable across speciation but significant residuals and energy cost",
    ]

    result.residuals_implications = [
        "⚠ Spent adsorptive media (GFH, ferric oxide) is arsenic-bearing classified waste. "
        "Disposal requires stabilisation and regulated landfill. Confirm waste classification before design.",
        "Coagulation/co-precipitation: arsenic is captured in clarifier sludge — which must also be managed as potentially arsenic-bearing.",
        "RO concentrate: arsenic is rejected and concentrated. Concentrate is a classified waste where arsenic exceeds regulatory thresholds.",
    ]

    result.problem_transfer_flag = (
        "Arsenic removal transfers arsenic from the water into a concentrated solid or liquid residual. "
        "It does not destroy arsenic. Confirm disposal pathway before finalising treatment approach."
    )

    result.critical_preconditions = speciation_notes
    if iron_context:
        result.critical_preconditions.append(iron_context)

    result.key_risks = [
        "Speciation not confirmed: if As(III) dominates and pre-oxidation is not included, adsorption efficiency will be very low.",
        "Competing ions (phosphate, silicate, DOC) can severely reduce adsorption performance — test with site water.",
        "Regulatory waste classification for spent media — confirm before procurement.",
    ]

    result.next_steps = [
        "Confirm As(III)/As(V) speciation by sampling and testing",
        "Test competing ion concentrations (phosphate, silicate, TOC) in source water",
        "Undertake column trial or batch adsorption testing with site water",
        "Engage waste regulator on disposal classification before specifying media type",
    ]

    return result


# ─── PFAS MODULE ─────────────────────────────────────────────────────────────

def assess_pfas(inputs: SourceWaterInputs) -> ContaminantModuleResult:
    result = ContaminantModuleResult(module="pfas")
    conc = inputs.pfas_concentration_ng_l

    # Australian PFAS guideline (PFAS NEMP 2020, drinking water)
    # Health-based guidance values vary by compound — sum PFAS guidance emerging
    result.contaminant_summary = (
        f"PFAS detected: {conc if conc > 0 else 'concentration not quantified'} ng/L. "
        "PFAS (per- and polyfluoroalkyl substances) are a large and diverse chemical family. "
        "Long-chain PFAS (PFOS, PFOA) are better adsorbed by GAC than short-chain compounds. "
        "Treatment transfers PFAS into a residual stream — it does not destroy it. "
        "Confirm PFAS profile (compound list and concentrations) before selecting treatment."
    )

    # Pathway selection
    toc = inputs.toc_median_mg_l

    if conc > 200 or inputs.tds_median_mg_l > 1000:
        result.preferred_pathway = "Reverse Osmosis (RO)"
        result.preferred_pathway_rationale = (
            "High PFAS concentration or TDS: RO provides the most reliable PFAS removal "
            "across all chain lengths, including short-chain PFAS that break through GAC and IX. "
            "Concentrate management is the critical downstream challenge."
        )
    elif toc > 8:
        result.preferred_pathway = "PFAS-selective ion exchange resin"
        result.preferred_pathway_rationale = (
            f"High TOC ({toc} mg/L) will rapidly exhaust GAC capacity for PFAS removal "
            "as NOM competes for adsorption sites. PFAS-selective IX resin is far less affected "
            "by NOM competition and is preferred in high-TOC source waters. "
            "Confirm resin type (single-use vs. regenerable) and brine/waste management."
        )
    else:
        result.preferred_pathway = "Granular Activated Carbon (GAC)"
        result.preferred_pathway_rationale = (
            "GAC is the most widely deployed PFAS treatment for lower-concentration source waters "
            "with moderate NOM. Most effective for long-chain PFAS. "
            "Monitor breakthrough and establish a media replacement schedule. "
            "PFAS-selective IX resin is an alternative with longer run times between replacements."
        )

    result.alternative_pathways = [
        "PFAS-selective ion exchange resin — longer run times, higher capital, effective at low PFAS levels",
        "GAC — established technology; compromised by high TOC and short-chain PFAS",
        "RO — highest confidence removal; significant concentrate management required",
        "Nanofiltration — partial PFAS removal; less effective for shorter chain compounds",
    ]

    result.residuals_implications = [
        "⚠ GAC pathway: spent GAC is PFAS-bearing waste. Off-site reactivation returns PFAS to "
        "the reactivation facility waste stream. Landfill of PFAS-bearing GAC is not acceptable in most jurisdictions.",
        "⚠ IX pathway: brine from regeneration or spent non-regenerable resin is a highly concentrated "
        "PFAS stream. High-temperature incineration (>850°C) or specialist electrochemical treatment required.",
        "⚠ RO pathway: concentrate is a concentrated PFAS liquid. Disposal requires specialist handling.",
        "Confirm downstream destruction or disposal pathway before finalising PFAS treatment selection.",
    ]

    result.problem_transfer_flag = (
        "⚠ PFAS REMOVAL = PFAS TRANSFER, NOT DESTRUCTION. "
        "All PFAS treatment options concentrate PFAS into a smaller-volume residual "
        "(spent media, brine, or concentrate). Destruction requires high-temperature incineration "
        "or specialist emerging technologies. Do not select a PFAS treatment process without "
        "confirming the downstream destruction or disposal pathway."
    )

    result.critical_preconditions = [
        "Obtain full PFAS compound profile (not just PFOS/PFOA) — short-chain PFAS behave differently",
        "Quantify NOM/TOC competition — critical for GAC sizing and IX resin selection",
        "Assess background TDS and hardness — affects IX resin loading and RO scaling",
    ]

    result.key_risks = [
        "Short-chain PFAS (C4–C6) break through GAC rapidly — GAC treatment may not be sufficient if short-chain compounds are dominant",
        "NOM competition reduces GAC and IX effectiveness — high-TOC water dramatically shortens media life",
        "Concentrate / spent media disposal pathway not arranged — treatment cannot legally proceed without it",
        "Regulatory framework for PFAS is evolving — confirm current guidance values before design",
    ]

    result.next_steps = [
        "Full PFAS compound analysis (target list including short-chain compounds)",
        "TOC / NOM characterisation to assess competition",
        "Column/pilot testing with site water to establish media loading rates",
        "Engage waste authority on PFAS residuals classification and destruction options",
        "Review current PFAS NEMP guidance values for the intended supply use",
    ]

    return result


# ─── TASTE AND ODOUR MODULE ───────────────────────────────────────────────────

def assess_taste_odour(inputs: SourceWaterInputs) -> ContaminantModuleResult:
    result = ContaminantModuleResult(module="taste_odour")

    result.contaminant_summary = (
        "MIB (2-methylisoborneol) and/or geosmin confirmed as taste and odour drivers. "
        "These are secondary metabolites from cyanobacteria and actinobacteria. "
        "They are detectable by consumers at extremely low concentrations (MIB ~5–10 ng/L; geosmin ~4 ng/L). "
        "Taste-and-odour events are primarily aesthetic and do not directly indicate a public health risk, "
        "but they drive significant consumer complaints and loss of trust. "
        "Note: cyanobacteria presence does not automatically mean cyanotoxins are present — "
        "toxin testing is required separately."
    )

    toc = inputs.toc_median_mg_l

    if toc > 8:
        result.preferred_pathway = "Ozone + BAC (with pre-treatment)"
        result.preferred_pathway_rationale = (
            "High TOC competes strongly with MIB/geosmin for PAC and GAC adsorption sites, "
            "dramatically increasing carbon demand and reducing effectiveness. "
            "Ozone + BAC provides reliable MIB/geosmin control without NOM competition effects — "
            "ozone oxidises the compounds and BAC provides biological polishing. "
            "This is the preferred long-term strategy for continuous protection in high-TOC waters."
        )
    else:
        result.preferred_pathway = "PAC (event response) + Ozone or GAC (strategic polishing)"
        result.preferred_pathway_rationale = (
            "For episodic MIB/geosmin events in lower-TOC source waters, PAC provides "
            "a cost-effective event-response tool. However, PAC alone is not reliable for "
            "high-intensity events or high-NOM waters. A GAC or ozone + BAC system provides "
            "the more robust long-term solution, particularly where bloom events are recurring."
        )

    result.alternative_pathways = [
        "PAC dosing (powdered activated carbon) — event-responsive, low capital, but dose-sensitive and NOM-competitive",
        "GAC contactors — continuous protection, good for episodic events, media replacement every 5–15 years",
        "AOP (O₃/H₂O₂ or UV/H₂O₂) — for refractory compounds or enhanced oxidation where ozone alone is insufficient",
        "Ozone + GAC — both oxidation and adsorption, slightly less biological than Ozone + BAC",
    ]

    result.critical_preconditions = [
        "If cyanobacteria are present: ozone placement MUST follow cell removal. "
        "Do not pre-ozonate before cells are removed — risk of releasing intracellular toxins.",
        "Bromide assessment is required before finalising ozone dose — bromate formation risk.",
        "PAC type matters: coal-based or wood-based activated carbon have different MIB/geosmin affinity — confirm with testing.",
    ]

    result.residuals_implications = [
        "PAC: spent carbon mixes with clarifier sludge — increases sludge volume and carbon content.",
        "GAC/BAC: spent media requires off-site reactivation or disposal every 5–15 years.",
        "If PFAS is also present: PAC, GAC, and BAC will also concentrate PFAS — residuals classification changes.",
    ]

    result.key_risks = [
        "Relying on PAC alone for a recurring MIB/geosmin source: PAC is event-responsive but not reliable for sustained bloom events",
        "Applying pre-ozone before cyanobacterial cell removal: risk of toxin release",
        "High NOM out-competing MIB/geosmin for available adsorption sites at practical PAC doses",
    ]

    result.next_steps = [
        "Quantify MIB/geosmin by GC-MS at source and treated water",
        "Measure bromide in source water (for ozone risk assessment)",
        "Conduct PAC dose-response testing with site water at peak TOC conditions",
        "Assess seasonal bloom risk and link to off-take management strategy",
    ]

    return result


# ─── CYANOTOXIN MODULE ────────────────────────────────────────────────────────

def assess_cyanotoxins(inputs: SourceWaterInputs) -> ContaminantModuleResult:
    result = ContaminantModuleResult(module="cyanotoxins")

    result.contaminant_summary = (
        "Cyanobacteria confirmed or cyanotoxins detected. "
        "Cyanotoxins include microcystins (hepatotoxic), cylindrospermopsin (genotoxic/hepatotoxic), "
        "and saxitoxins (neurotoxic). Treatment strategy depends critically on whether the primary "
        "challenge is intracellular toxin (within intact cells) or extracellular toxin (dissolved). "
        "The cardinal rule: remove cells intact BEFORE applying oxidants. "
        "Pre-oxidation before cell removal risks lysing cells and dramatically increasing "
        "dissolved toxin concentrations."
    )

    result.preferred_pathway = "Cell removal first (DAF or clarification + filtration), then oxidative polishing"
    result.preferred_pathway_rationale = (
        "The treatment sequence is critical. "
        "Step 1: Remove intact cyanobacterial cells by DAF (preferred) or well-operated clarification + filtration. "
        "Step 2: Apply oxidation (ozone or chlorine at appropriate dose) to destroy extracellular dissolved toxins. "
        "Step 3: GAC or BAC for polishing of oxidation by-products and any residual dissolved toxins. "
        "This sequence avoids the risk of lysing cells and releasing additional dissolved toxin load."
    )

    result.alternative_pathways = [
        "For extracellular toxins only (cells already removed): ozone is highly effective for microcystins at practical doses",
        "Chlorination: effective for microcystins at high Ct (>20 mg·min/L at pH <8) — less effective at high pH",
        "GAC/BAC polishing: useful downstream barrier for dissolved toxins after oxidation",
        "Off-take management: avoiding bloom-impacted depths by using deep intake or selective off-take is often the most cost-effective strategy",
    ]

    result.critical_preconditions = [
        "⚠ SEQUENCE RULE: Never apply chlorine or ozone before intact cyanobacterial cell removal. "
        "Cell lysis releases intracellular toxins — this can increase dissolved toxin concentration by 10–100×.",
        "Identify toxin class — microcystins, cylindrospermopsins, and saxitoxins respond differently to treatment.",
        "Determine whether the main challenge is intracellular (cells intact) or extracellular (bloom senescence / cells already lysed).",
        "Assess bloom pattern and seasonality to design both treatment response and source management strategy.",
    ]

    result.residuals_implications = [
        "DAF float will contain concentrated cyanobacterial cells and associated toxins — handle as contaminated waste.",
        "Filter backwash during bloom events will contain concentrated cyanobacteria — assess recycle risk carefully.",
        "Avoid returning backwash water to inlet during active bloom events without prior assessment.",
    ]

    result.key_risks = [
        "Pre-oxidation before cell removal: this is the highest-risk operational mistake in cyanotoxin management",
        "Assuming taste/odour events indicate toxin risk (or vice versa) — T&O and toxins are not correlated",
        "Inadequate monitoring: not distinguishing between cell counts, intracellular, and extracellular toxin loads",
        "Applying standard disinfection Ct design to cyanotoxin scenarios without specific toxin-class assessment",
    ]

    result.problem_transfer_flag = (
        "DAF float and filter backwash during bloom events are cyanotoxin-bearing waste streams. "
        "Treatment or safe disposal of these streams must be considered during bloom periods."
    )

    result.next_steps = [
        "Implement phycocyanin / chlorophyll monitoring at intake and reservoir",
        "Establish cyanotoxin monitoring programme (cell count triggers, toxin type testing)",
        "Develop bloom response protocol with defined treatment and source management actions",
        "Assess off-take depth management options to avoid bloom layers",
        "Test dissolved toxin removal efficiency with ozone and chlorine at site-specific conditions",
    ]

    return result


# ─── IRON AND MANGANESE MODULE ────────────────────────────────────────────────

def assess_iron_manganese(inputs: SourceWaterInputs) -> ContaminantModuleResult:
    result = ContaminantModuleResult(module="iron_manganese")

    fe = inputs.iron_median_mg_l
    mn = inputs.manganese_median_mg_l

    result.contaminant_summary = (
        f"Iron: {fe} mg/L (ADWG aesthetic guideline 0.3 mg/L). "
        f"Manganese: {mn} mg/L (ADWG health guideline 0.1 mg/L). "
        "Iron in surface waters is typically colloidal / particulate and responds to coagulation. "
        "Groundwater iron is typically dissolved (Fe²⁺) and requires oxidation before removal. "
        "Manganese is typically dissolved (Mn²⁺) and requires oxidation to Mn⁴⁺ (MnO₂) before filtration. "
        "Manganese oxidation requires more precise pH and oxidant control than iron."
    )

    is_groundwater = inputs.source_type == "groundwater"

    if is_groundwater:
        result.preferred_pathway = "Aeration or oxidation (KMnO₄ or Cl₂) + greensand filtration or standard dual media"
        result.preferred_pathway_rationale = (
            "Groundwater iron and manganese are dissolved species requiring oxidation as the first step. "
            "Aeration oxidises Fe²⁺ to Fe³⁺ effectively. "
            "Manganese oxidation is slower and may require pH adjustment or catalytic greensand media. "
            "Greensand (glauconite coated with MnO₂) provides catalytic manganese oxidation and filtration in a single step. "
            "KMnO₄ is a reliable oxidant for manganese where pH > 7.5."
        )
    else:
        result.preferred_pathway = "Enhanced coagulation + clarification + filtration"
        result.preferred_pathway_rationale = (
            "Surface water iron is typically associated with NOM and present as colloidal complexes. "
            "Standard coagulation + clarification + filtration effectively removes iron and associated turbidity. "
            "Dissolved Mn requires pre-chlorination at pH > 7.5 or KMnO₄ addition before filtration."
        )

    result.alternative_pathways = [
        "Pre-chlorination for manganese (effective at pH 7.5–9; risk of DBP formation where TOC is present)",
        "KMnO₄ dosing for manganese (effective at pH 6–9; dose must be controlled to avoid pink water)",
        "Biological manganese filtration (slow, effective, no chemical requirement — requires long media maturation)",
        "Greensand filtration (catalytic, effective, requires periodic KMnO₄ regeneration)",
    ]

    result.residuals_implications = [
        "Iron removal generates iron-bearing clarifier sludge — higher iron content increases sludge density and improves dewaterability.",
        "If arsenic is also present, iron removal sludge may be arsenic-bearing — confirm before disposal.",
        "KMnO₄ dosing produces MnO₂ solids in filter — backwash management required.",
    ]

    result.critical_preconditions = [
        "Confirm speciation: dissolved vs. particulate Fe and Mn — governs whether oxidation is required",
        "Measure pH: manganese oxidation is pH-dependent. Below pH 7.0, chlorine manganese oxidation is unreliable.",
        "Where iron and arsenic co-occur: iron removal process may also achieve partial arsenic removal via co-precipitation — assess jointly.",
    ]

    result.key_risks = [
        "Manganese breakthrough after oxidation step: pink water complaints if Mn passes the filter in oxidised form",
        "Pre-chlorination DBP formation where TOC is high — consider alternative oxidants",
        "Over-dosing KMnO₄: excess KMnO₄ causes pink colouration — strict dose control required",
    ]

    result.next_steps = [
        "Confirm dissolved vs. particulate speciation for Fe and Mn at source",
        "Measure pH range at source — critical for oxidation strategy selection",
        "Check for arsenic co-occurrence — potential combined treatment opportunity",
    ]

    return result


# ─── MODULE DISPATCHER ────────────────────────────────────────────────────────

def run_contaminant_modules(inputs: SourceWaterInputs,
                             module_keys: list) -> dict:
    """Run all triggered contaminant modules. Returns {module_key: ContaminantModuleResult}."""
    results = {}
    dispatchers = {
        "arsenic":       assess_arsenic,
        "pfas":          assess_pfas,
        "taste_odour":   assess_taste_odour,
        "cyanotoxins":   assess_cyanotoxins,
        "iron_manganese": assess_iron_manganese,
    }
    for key in module_keys:
        if key in dispatchers:
            results[key] = dispatchers[key](inputs)
    return results
