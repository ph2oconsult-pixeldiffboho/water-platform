# Water Utility Planning Platform

Integrated concept-stage planning platform for water utilities and consultants.

## Applications

| App | Domain | Entry Point |
|-----|--------|-------------|
| Wastewater Treatment Planner | Activated sludge, BNR, MBR | `streamlit run apps/wastewater_app/app.py` |
| Drinking Water Treatment Planner | Coagulation, DAF, GAC, RO, UV | `streamlit run apps/drinking_water_app/app.py` |
| Purified Recycled Water Planner | AWT, LRV, QMRA, HACCP | `streamlit run apps/prw_app/app.py` |
| Biosolids & Sludge Management | Digestion, dewatering, disposal | `streamlit run apps/biosolids_app/app.py` |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the wastewater application (Stage 1 reference implementation)
streamlit run apps/wastewater_app/app.py

# 3. Run the test suite
python3 -m pytest tests/ -v
# or without pytest:
python3 run_tests.py
```

## Platform Structure

```
water_platform/
├── core/                    # Shared core engine (domain-agnostic)
│   ├── project/             # ProjectModel, ProjectManager, ScenarioManager
│   ├── assumptions/         # AssumptionsManager + YAML defaults per domain
│   ├── costing/             # CostingEngine: CAPEX, OPEX, lifecycle cost
│   ├── carbon/              # CarbonEngine: Scope 1/2/3, avoided emissions
│   ├── risk/                # RiskEngine: scoring, aggregation, narrative
│   ├── validation/          # ValidationEngine: core + domain hook system
│   └── reporting/           # ReportEngine: structured report objects
│
├── domains/                 # Domain-specific modules (engineering science)
│   ├── wastewater/          # BNR, MBR plugins + domain interface
│   ├── drinking_water/      # (stub — ready to build)
│   ├── prw/                 # (stub — ready to build)
│   └── biosolids/           # (stub — ready to build)
│
├── apps/                    # Streamlit user interfaces
│   ├── shared/              # Shared UI components and session state
│   ├── wastewater_app/      # 6-page wastewater application (complete)
│   ├── drinking_water_app/  # (stub — ready to build)
│   ├── prw_app/             # (stub — ready to build)
│   └── biosolids_app/       # (stub — ready to build)
│
├── data/                    # YAML data libraries
│   ├── cost_libraries/      # CAPEX/OPEX unit costs
│   ├── carbon_libraries/    # Emission factors
│   └── benchmark_data/      # Industry benchmark ranges
│
├── storage/projects/        # Saved project JSON files
├── tests/                   # Unit + integration tests (35 tests)
└── config/                  # Platform configuration
```

## Architecture Principles

**Share the framework. Separate the science.**

- The shared core handles: costing, carbon, risk, validation, reporting
- Domain modules handle: engineering calculations, process science
- Technology plugins are isolated: add a new technology by adding one file
- All assumptions are in YAML: editable, versioned, auditable

## Adding a New Treatment Technology (Wastewater Example)

1. Create `domains/wastewater/technologies/my_technology.py`
2. Inherit from `BaseTechnology` and implement `calculate()`
3. Add to `TECHNOLOGY_REGISTRY` in `domains/wastewater/domain_interface.py`
4. Add default assumptions to `core/assumptions/defaults/wastewater_defaults.yaml`
5. Write unit tests in `tests/domains/wastewater/`

No other files need to change.

## Adding a New Domain Application

1. Copy the stub from `domains/drinking_water/` and implement the domain interface
2. Copy the app structure from `apps/drinking_water_app/` and adapt the pages
3. Add domain defaults YAML to `core/assumptions/defaults/`
4. The shared core engines work unchanged

## Key Engineering Modules Implemented

### Wastewater Domain
- **BNRTechnology**: Activated sludge with biological N and P removal
  - A2O, modified Bardenpho, UCT configurations
  - Sludge yield via endogenous decay model (Metcalf & Eddy)
  - Oxygen demand (carbonaceous + nitrification − denitrification credit)
  - N₂O and CH₄ Scope 1 process emissions (IPCC factors)
  - Secondary clarifier sizing
  - Chemical P removal (ferric chloride / alum)

- **MBRTechnology**: Submerged hollow-fibre/flat-sheet MBR
  - Membrane area from design flux and net/gross factor
  - Scour aeration energy (SAD-based)
  - CIP chemical demand (NaOCl, citric acid)
  - N₂O Scope 1 emissions
  - LRV credits for pathogen removal

### Shared Core
- **CostingEngine**: CAPEX/OPEX with library lookup + user override
- **CarbonEngine**: Scope 1/2/3 + avoided emissions + carbon pricing
- **RiskEngine**: 5×5 matrix, weighted categories, automated narrative
- **ValidationEngine**: Core checks + domain hook registration system
- **ReportEngine**: Structured report objects → Streamlit / JSON / future PDF

## Project Data Model

Every project stores:
- `ProjectMetadata`: name, domain, plant, author, dates, version
- `ScenarioModel[]`: inputs, treatment pathway, assumptions, all results
- `CostResult`: CAPEX/OPEX breakdown, lifecycle cost, specific cost
- `CarbonResult`: Scope 1/2/3, avoided, net, carbon cost
- `RiskResult`: category scores, item register, narrative
- `ValidationResult`: pass/warn/fail messages per field

Projects are saved as JSON and support full round-trip serialisation.

## Version History

| Version | Date | Notes |
|---------|------|-------|
| 1.0.0 | 2024 | Initial release — shared core + wastewater domain |

