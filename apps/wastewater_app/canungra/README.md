# Canungra STP Intensification — WaterPoint Scenario Package

**Version:** Rev 20 (April 2026)
**Location:** `apps/wastewater_app/canungra/`

## What's in this package

```
canungra/
├── canungra_diurnal_profile.json    # Rev B Figure 3.1 profile (30-min resolution)
├── canungra_scenarios.json           # 8 scenarios: S0, S1A, S1B, S2-A/B/C3/D/E
├── canungra_runner.py                # Bardenpho solver with dual-interpretation licence
├── canungra_streamlit.py             # WaterPoint-compatible UI module
├── tests/
│   └── test_calibration.py           # 14 tests: calibration + S2 variants + S2-E
└── README.md                         # This file
```

## Capacity ladder (Rev 20, Interpretation B strategic planning basis)

| Scenario | Max EP | Capex (AUD) | Binding constraint |
|---|---|---|---|
| S0 Rev B baseline | 1,500 | — | Current licence |
| S1A Controls only | 1,900 | ~280k | Peak TN (MML) |
| S1B S1A + IFAS | 2,100 | ~900k | Peak TN (MML) |
| S2-D Parallel-only (118 kL) | 4,500 | ~3.30M | Peak TN (MML) ~14.6 mg/L |
| **S2-C3 ★ Series-parallel (eff 142 kL)** | **5,500** | **~3.56M** | **Peak TN (MML) ~14.9 mg/L** |
| S2-A/B Full 156 kL | 6,000 | 3.36M / 3.62M | Peak TN (MML) ~14.7 mg/L |
| **S2-E ★ Aerobic-shifted (NEW Rev 20)** | **5,500–6,000** | **~3.5–3.8M** | **Peak TN; depends on RFC-12 flow balancing** |

**Interpretation B** is tested as the strategic planning basis (see Section 2.3 of the report). Under **Interpretation A** (hard 607 kg/yr cap), S2 reverts to 4,000 EP maximum. See `canungra_runner.py::LicenceLimits` for implementation of the `get_mass_limit(EP)` toggle.

## The five S2 configuration variants

All five share the same upstream and downstream architecture. They differ in how the MBR bay and existing post-anoxic tank are reconfigured, how flow is distributed, and whether flow balancing is incorporated.

- **S2-A** Combined post-anoxic (wall removed): 156 kL, single MeOH dose, needs RFC-05 structural review
- **S2-B** Parallel 38+59+59: 156 kL total, 3-point proportional MeOH, wall retained
- **S2-C3 ★** Series-parallel: 38 kL endo pre-stage, 2 parallel 59 kL cells with MeOH (eff 142 kL)
- **S2-D** Parallel-only: 38 kL decommissioned, two 59 kL cells only (118 kL)
- **S2-E ★** Aerobic-shifted with flow balancing: existing 38 kL post-anoxic CONVERTED to aerobic (155 kL aerobic), former MBR bay becomes post-anoxic (118 kL), new MBR structure with integrated flow balancing

**Two preferred concepts** sit alongside each other for Phase 2 pre-feasibility development:
- **S2-C3** — conservative post-anoxic sizing, simpler dosing
- **S2-E** — simpler process flow, no wall removal, flow balancing adds operational robustness

Choice between them depends on RFC-04 (S2-C3 hydraulics) and RFC-12 (S2-E flow balancing dynamic simulation).

## Decision tree for S2 variant selection

| Growth horizon | Wall removal? | Preferred concept |
|---|---|---|
| ≤ 4,000 EP | Either | S2-D (lowest cost) |
| **4,000 – 5,500 EP** | **Either** | **S2-C3 ★ or S2-E ★ (parallel preferred concepts)** |
| 5,500 – 6,000 EP | No | S2-E ★ (flow balancing) or S2-B (parallel) |
| 5,500 – 6,000 EP | Yes | S2-A (combined) or S2-E |
| > 6,000 EP | Either | S2 exceeded — external post-anoxic or new aerobic |

## Licence interpretation (Rev 16+ key concept)

The 607 kg TN/yr annual mass limit is a derived quantity from Rev B Table 2.1 fn 1:

```
Annual Mass Load = Median Concentration × ADWF × 365 × 1.10 (wet weather)
At 1,500 EP: 5 mg/L × 300 kL/d × 365 × 1.10 = 603 kg/yr → rounded to 607
```

Two interpretations apply at re-licensing:

- **Interpretation A (hard cap):** 607 kg/yr fixed regardless of EP (conservative)
- **Interpretation B (scales, Rev 18+ strategic planning basis):** Mass limit re-scales with design EP via the Rev B formula. At 5,500 EP → 2,226 kg/yr cap.

Use `LicenceLimits(interpretation='A')` or `'B'`. Default is `'B'`.
`get_mass_limit(EP)` returns the applicable limit for the design population.

**RFC-10 is the Stage 0 gateway** — regulator consultation should precede any capital commitment or organisational commitment to S2 as a 5,500+ EP strategy. Rev 18 reframed this from "one of many verification items" to "the gateway question that determines whether the strategic narrative is defensible at all".

## Environmental context (Rev 17 Section 5.4)

| Scenario | EP | TN discharge (kg/yr) | × vs baseline |
|---|---|---|---|
| S0 Rev B | 1,500 | 578 | 1.00× |
| S1A | 1,900 | 587 | 1.02× |
| S1B | 2,100 | 583 | 1.01× |
| S2-D | 4,500 | 744 | 1.29× |
| **S2-C3 ★** | **5,500** | **1,171** | **2.03×** |
| S2-A/B | 6,000 | 1,338 | 2.31× |

S1A/S1B achieve higher EP with essentially flat total discharge (improved concentration offsets increased flow). S2 variants double or triple total annual TN discharge to the receiving waterway.

**Treatment efficiency actually improves:** 91% TN removal at S0 → 95% at S2-C3. Higher total discharge reflects serving more people, not degraded treatment.

The receiving water assessment and regulator engagement are **QUU's workstream** (Rev 19 clarification). Our engineering role is to quantify and minimise within process constraints; we do not make environmental judgements on the utility's behalf.

## Calibrated kinetics (SE QLD subtropical, 17°C winter)

| Parameter | 20°C value | Source |
|---|---|---|
| K2 primary anoxic (RBCOD-driven) | 0.11 gN/gVSS/d | SE QLD confirmed |
| K3 endogenous post-anoxic | 0.05 gN/gVSS/d | Standard |
| K3 MeOH-acclimated | 0.12 gN/gVSS/d | Baseline (RFC-01 to verify on Canungra biomass) |
| θ for denitrification | 1.08 | Standard |
| θ for endogenous | 1.10 | Standard |
| Kn ammonia half-sat | 0.3 mgN/L | Rev B explicit |
| IFAS biofilm nit flux (17°C) | 0.7 g NH4-N/m²·d base | 0.5–1.1 envelope tested (Section 3.6) |

## Running the tests

```bash
cd ~/wp_new
python3 apps/wastewater_app/canungra/tests/test_calibration.py
```

All **14 tests** should pass:
- 7 calibration tests (Rev B BioWIN baseline validation)
- 3 S2 variant regression tests (S2-A/B biology, S2-C3 effective volume, S2-D reduced capacity)
- 2 interpretation toggle tests (A vs B divergence at high EP, convergence at 1,500 EP)
- **2 S2-E tests (NEW Rev 20)** — volume reallocation, and variant comparison (S2-D >> S2-E ≈ S2-A at 5,500 EP)

## Phase 2 verification workstream

The following RFCs may need to close before S2 capital commitment (scope depends on preferred concept):

| RFC | Scope | Cost (AUD) | Timeline | Applies to |
|---|---|---|---|---|
| RFC-01 | K3 methanol-acclimated denit bench testing | 15–25k | 8–12 weeks | All S2 |
| RFC-02 | Aeration capacity and alpha-factor (for S1B IFAS) | 20–40k | 6–8 weeks | S1B only |
| RFC-03 | HF MBR vendor specifications and footprint | 10–20k | 4–6 weeks | All S2 |
| RFC-04 | Post-anoxic hydraulics and mixing (dye tests) | 15–30k | 6–10 weeks | S2-A/B/C3 |
| RFC-05 | MBR internal wall structural review | 30–50k | 4–6 weeks | **S2-A only** |
| RFC-06 | Phosphorus compliance at intensified loading | 20–40k | 6–8 weeks | All S2 |
| RFC-07 | Solids handling capacity at 4,500–6,000 EP | 25–50k | 6–10 weeks | All S2 |
| RFC-08 | Influent alkalinity confirmation + NaOH dosing | 10–20k | 4–6 weeks | All S2 |
| RFC-09 | Carrier retention and MBR protection (S1B) | 15–30k | 6–8 weeks | S1B only |
| **RFC-10** | **Licence mass load basis — Stage 0 gateway** | **5–15k** | **4–8 weeks** | **ALL scenarios (gateway)** |
| **RFC-12** | **Flow balancing dynamic simulation** | **20–35k** | **4–6 weeks** | **S2-E only (conditional)** |

Note: RFC-11 (receiving water assessment) was removed in Rev 19 — it sits with QUU's environmental workstream, not ours.

## Change log

| Rev | Date | Change |
|---|---|---|
| Rev 4 | April 2026 | Original Assessment (red-team flagged overclaiming) |
| Rev 5-8 | April 2026 | Repositioned as Concept Study, alkalinity F8 elevated, IFAS repositioned |
| Rev 9 | April 2026 | K3 MeOH sensitivity extended to 0.05–0.15 gN/gVSS/d |
| Rev 10 | April 2026 | 5 charts added for tipping points |
| Rev 11 | April 2026 | S2 resolved into 4 variants (A/B/C3/D), 7 PFDs, decision tree |
| Rev 12 | April 2026 | PFDs redrawn in Rev B Tyr Group visual style |
| Rev 13 | April 2026 | IFAS nitrification flux sensitivity 0.5–1.1 g NH4-N/m²·d at 17°C |
| Rev 14 | April 2026 | PFD recycle lines redrawn as orthogonal piping |
| Rev 15 | April 2026 | Mass load dual-interpretation Section 2.3 + RFC-10 added |
| Rev 16 | April 2026 | Interpretation B tested as strategic planning basis |
| Rev 17 | April 2026 | Section 5.4 discharge load environmental context |
| Rev 18 | April 2026 | Red-team response: framing recalibrated, S2-C3 "preferred concept" not "recommended", RFC-10 as Stage 0 gateway |
| Rev 19 | April 2026 | Environmental scope clarified — RFC-11 removed (QUU workstream) |
| **Rev 20** | **April 2026** | **S2-E aerobic-shifted variant added, RFC-12 (flow balancing simulation)** |

## Bundle history

- `canungra_v4.bundle` — April 2026, prepared but never deployed
- `canungra_v5.bundle` — April 2026, Rev 17 state, deployed to origin/main
- `canungra_v6.bundle` — April 2026, **Rev 20 state (this package)**, supersedes v5
