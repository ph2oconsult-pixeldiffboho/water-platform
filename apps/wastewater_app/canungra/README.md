# Water Utility Planning Platform

Capital planning decision support platform for water utilities and consultants.
Produces concept-level options studies aligned with how utilities make investment decisions.

## What it does

Given wastewater treatment options and site conditions, the platform:

1. **Calculates** engineering performance — energy, sludge, effluent quality, carbon
2. **Costs** each option — CAPEX, OPEX, lifecycle cost, $/kL treated
3. **Ranks** options using a strict compliance → cost → risk hierarchy
4. **Identifies** non-viable options with engineering reasons
5. **Generates** alternative pathways (e.g. BNR + thermal management instead of MABR)
6. **Frames** the decision for executives: two options, what you get, what you accept
7. **Produces** a full options study report in Word format

Current scope: wastewater treatment (activated sludge domain).
Stubs ready for drinking water, PRW, and biosolids.

---

## Quick Start

```bash
pip install -r requirements.txt
streamlit run apps/wastewater_app/app.py

python3 run_tests.py           # full test suite
python3 run_tests.py --fast    # skip benchmarks
python3 run_tests.py --benchmark  # benchmark suite only
```

---

## Platform Structure

```
water_platform/
├── core/                       # Domain-agnostic shared engines
│   ├── costing/                # CostingEngine: CAPEX, OPEX, LCC, $/kL
│   ├── carbon/                 # CarbonEngine: Scope 1/2/3, N2O, avoided
│   ├── risk/                   # RiskEngine: 5x5 matrix, category scores
│   ├── validation/             # ValidationEngine: hook system
│   ├── reporting/              # ReportEngine: structured report objects
│   ├── assumptions/            # AssumptionsManager: YAML defaults per domain
│   └── project/                # ProjectModel, ScenarioManager
│
├── domains/wastewater/         # Wastewater engineering science
│   ├── technologies/           # BNR, MBR, AGS, MABR+BNR, IFAS/MBBR, ...
│   ├── domain_interface.py     # Orchestrates run_scenario()
│   ├── decision_engine.py      # Capital planning decision logic
│   ├── technology_fit.py       # Green/amber/red fit ratings
│   └── risk_items.py           # Scenario-sensitive risk items
│
├── apps/wastewater_app/pages/  # 11-page Streamlit application
│   ├── page_01-04              # Setup, inputs, selection, results
│   ├── page_05                 # Multi-scenario comparison
│   ├── page_06                 # Report download
│   ├── page_09-10              # Assumptions viewer, sensitivity analysis
│   └── page_11_decision.py     # Decision Framework
│
├── tests/
│   ├── benchmark/              # 8-scenario regression suite (282 checks)
│   ├── core/                   # Engine unit tests
│   ├── domains/wastewater/     # Engineering + decision engine tests
│   ├── integration/            # Full pipeline integration
│   └── test_release_readiness.py
│
└── docs/benchmark_scenarios.md
```

---

## Decision Engine

`domains/wastewater/decision_engine.py`

### Selection hierarchy (strictly enforced)

```
1. COMPLIANCE   mandatory — non-compliant options excluded first
2. COST         lowest LCC among compliant options wins
3. RISK         tiebreaker only — never overrides cost
```

If only one option is compliant, it is recommended regardless of cost or risk.
Compliance is non-negotiable.

### Key outputs

| Field | Description |
|-------|-------------|
| `selection_basis` | Why chosen: "Sole compliant" / "Lowest LCC" / "All fail — reference only" |
| `non_viable` | Options that fail compliance with reasons |
| `regulatory_note` | Explains why low regulatory confidence does not block recommendation |
| `alternative_pathways` | Engineered interventions to make non-viable options viable |
| `client_framing` | Two-option executive framing: what you get / risks you accept |
| `confidence` | High / Moderate / Low with drivers and caveats |
| `profiles` | Delivery model, constructability, staging, ops complexity, failure modes, regulatory |

### Example: S2 Cold Climate Nitrification (12C)

```
Selection basis: Sole compliant option — compliance constraint forces selection
Recommended: MABR + BNR
Non-viable: BNR (NH4=6.0 > target 3.0), AGS (NH4=4.5, TP=1.5), IFAS (TN=14.4)

Alternative pathway: BNR + thermal management (>=15C) + supplemental carbon
  LCC: $1,324k/yr vs MABR $1,815k/yr  — $491k/yr cheaper
  CAPEX increment: +$0.8M
  Procurement: D&C viable
  Regulatory: High confidence

Recommendation confidence: Moderate
  Caveat: Alternative pathway available and cheaper — evaluate before committing to MABR
```

---

## Test Suite

| File | Tests | Covers |
|------|-------|--------|
| `test_costing_engine.py` | 12 | CAPEX/OPEX/LCC |
| `test_carbon_engine.py` | 7 | Scope 1/2/3 |
| `test_engineering_calculations.py` | 30 | O2 demand, SRT, sludge |
| `test_bnr_mbr.py` | 16 | BNR + MBR technology |
| `test_decision_engine.py` | 65 | Hierarchy, new fields, consistency |
| `test_wastewater_full_run.py` | 8 | Full pipeline |
| `run_benchmarks.py` | 282 | 8 scenarios x 17 metrics + 8 decision-tension checks |
| `test_release_readiness.py` | 60 | Release gate |

### Benchmark scenarios

| ID | Scenario | Key constraint |
|----|----------|----------------|
| S1 | Medium municipal BNR baseline | Reference — all compliant |
| S2 | Cold climate nitrification (12C) | Only MABR achieves NH4<3 |
| S3 | Tight ammonia compliance (NH4<1) | All achievable at 18C |
| S4 | Capacity expansion, footprint constrained | AGS footprint 32% less |
| S5 | Carbon-limited denitrification (COD/TKN=5.3) | All fail TN without carbon |
| S6 | High electricity ($0.22/kWh) | AGS wins LCC |
| S7 | High sludge disposal ($450/t DS) | Sludge = 33% of BNR OPEX |
| S8 | Reuse-ready polishing | MBR TSS<1 essential for RO |

---

## Engineering References

Metcalf & Eddy 5th Ed | WEF Cost Estimating Manual 2018 | de Kreuk 2007 |
GE/Ovivo 2017 | IWA 2022 | IPCC 2019 Tier 1 | AU Water Association benchmarks

All costs AUD 2024. CAPEX ±40% concept estimate.
Not for procurement, funding approval, or regulatory submission.

---

## Version History

| Version | Notes |
|---------|-------|
| 1.0 | Initial — shared core + wastewater domain |
| 1.1 | Engineering remediation (O2, sludge, cold T, N2O) |
| 1.2 | Benchmark pack, technology fit, sensitivity, report |
| 1.3 | Stabilisation sprint (costing, schema, datetime) |
| 1.4 | Benchmark regression framework (282 checks, decision-tension) |
| 1.5 | Decision engine (delivery, constructability, staging, failure modes) |
| 1.6 | Decision integrity (compliance hierarchy, alternative pathways, client framing) |
