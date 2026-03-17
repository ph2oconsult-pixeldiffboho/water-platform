"""
docs/architecture/multi_domain_readiness.md

MULTI-DOMAIN ARCHITECTURE READINESS
=====================================
Documents how the current platform supports future domains:
- Purified Recycled Water (PRW) planning
- Biosolids strategy planning  
- Drinking water treatment planning

ADDING A NEW DOMAIN — CHECKLIST
--------------------------------
The platform uses a domain plugin architecture. To add a new domain:

1. Create domains/<domain_name>/
   ├── __init__.py
   ├── domain_interface.py        # Inherits from BaseDomainInterface
   ├── input_model.py             # Domain-specific inputs dataclass
   ├── result_model.py            # Domain result schema (reuse from core)
   ├── validation_rules.py        # Domain plausibility checks
   ├── technologies/
   │   ├── __init__.py
   │   ├── base_technology.py     # Reuse from wastewater or import directly
   │   └── <tech>.py              # Technology plugins

2. Add to core/assumptions/defaults/
   └── <domain>_defaults.yaml    # Economic, engineering, carbon assumptions

3. Register in core/project/project_model.py
   DomainType enum: add new value

4. Create apps/<domain>_app/
   └── app.py + pages/           # Streamlit UI pages

5. Register in apps/main_app.py
   Add domain card and routing

REUSABLE COMPONENTS (no changes needed)
-----------------------------------------
✅ CostingEngine         — domain-agnostic; takes CostItem lists
✅ CarbonEngine          — domain-agnostic; takes energy + emissions dicts  
✅ RiskEngine            — domain-agnostic; takes RiskItem lists
✅ ValidationEngine      — domain-agnostic; register domain hooks
✅ ReportEngine          — domain-agnostic; builds from ReportObject
✅ ReportExporter        — domain-agnostic; PDF + Word from ReportObject
✅ ProjectManager        — domain-agnostic; saves/loads ProjectModel JSON
✅ AssumptionsManager    — loads domain-specific YAML by DomainType
✅ CostResult            — shared result schema
✅ CarbonResult          — shared result schema
✅ RiskResult            — shared result schema
✅ ComparisonTable       — shared; builds from scenario list
✅ BenchmarkScenario     — pattern reusable for new domain benchmark packs

DOMAIN-SPECIFIC COMPONENTS (new code per domain)
--------------------------------------------------
• domain_interface.py    — orchestrates the calculation chain
• input_model.py         — influent/target inputs specific to domain
• validation_rules.py    — plausibility checks for the domain
• technology modules     — process calculations per treatment type
• risk_items.py          — technology-specific risk profiles
• technology_fit.py      — fit indicators (pattern from wastewater)

RESULT SCHEMA COMPATIBILITY
-----------------------------
TechnologyResult (base_technology.py) is the common output:
  .performance           — effluent quality + physical sizing
  .energy                — aeration, pumping, total kWh/day
  .sludge                — sludge production
  .carbon                — process emissions
  .risk                  — risk flags
  .capex_items           — list of CostItem
  .opex_items            — list of CostItem
  .notes                 — warnings, assumptions, limitations

This schema works for PRW (trains produce permeate not effluent),
biosolids (trains produce cake/gas not effluent), and drinking water
(trains produce potable water from raw water).

COMPARISON ENGINE DOMAIN-AGNOSTICISM
--------------------------------------
_build_comparison_table() in report_engine.py pulls from:
  s.cost_result       → CostResult (shared schema)
  s.carbon_result     → CarbonResult (shared schema)
  s.risk_result       → RiskResult (shared schema)
  s.domain_specific_outputs → domain-specific dict

The comparison table is agnostic to domain. New domains automatically
get CAPEX, OPEX, LCC, carbon, and risk columns. Domain-specific metrics
(e.g. permeate recovery %, log reduction, specific energy per m³ product)
are added by populating domain_specific_outputs.

PRW DOMAIN — DESIGN NOTES (not implemented)
---------------------------------------------
Input model: raw water quality (TOC, turbidity, pathogens, NDMA precursors),
production target (MLD), log reduction targets, distribution pressure.

Technologies: MF/UF, RO, UV/AOP, OZONE, BAC, chloramination.

Key outputs: permeate recovery %, specific energy (kWh/m³), 
log reduction achieved, NDMA formation potential, brine volume.

Risk additions: pathogen breakthrough risk, membrane integrity,
regulatory acceptance (novel technology), public perception.

BIOSOLIDS DOMAIN — DESIGN NOTES (not implemented)
---------------------------------------------------
Input model: sludge flow (kgDS/day), VS%, dewatered cake %, 
pathogen class target, disposal pathway options.

Technologies: anaerobic digestion, thermal hydrolysis, drying,
composting, incineration, pyrolysis, land application.

Key outputs: biogas/energy yield, final cake volume, PFAS fate,
disposal pathway suitability, biosolids classification.

DRINKING WATER DOMAIN — DESIGN NOTES (not implemented)
--------------------------------------------------------
Input model: raw water quality (turbidity, TOC, colour, iron, manganese,
algae risk, PFAS), production target, distribution pressure.

Technologies: coagulation/flocculation/sedimentation, filtration,
membrane filtration, ozonation, GAC, UV, chlorination.

Key outputs: treated water quality vs guidelines, filter run times,
backwash volume, sludge/residuals, disinfection by-product risk.
"""
