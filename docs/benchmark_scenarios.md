# Benchmark Scenario Pack — Wastewater Planning Platform

## Purpose

This document defines the engineering benchmark scenarios used to validate and protect the calculation integrity of the wastewater planning platform.

The benchmark suite acts as the **engineering truth set** for the platform. Every time code changes, the suite must pass in full before the change is accepted.

---

## How to Run

```bash
# All benchmarks (standalone, no pytest required)
python3 tests/benchmark/run_benchmarks.py

# With pytest (CI)
pytest tests/benchmark/ -v

# Subsets
python3 tests/benchmark/run_benchmarks.py --smoke       # sanity only
python3 tests/benchmark/run_benchmarks.py --ranges      # numeric ranges
python3 tests/benchmark/run_benchmarks.py --behaviour   # engineering relationships
python3 tests/benchmark/run_benchmarks.py --lcc         # lifecycle cost formula
python3 tests/benchmark/run_benchmarks.py --id S5       # single scenario
```

---

## Tolerance Philosophy

Outputs have different physical certainty at concept stage. Three tolerance tiers are defined:

| Tier | Tolerance | Applied to | Rationale |
|------|-----------|------------|-----------|
| **tight** | ±10% | Effluent quality, mass balances | First-principles equations; drift indicates a code error |
| **moderate** | ±30% | CAPEX, OPEX, LCC, energy, sludge | Concept estimate uncertainty is real (±40% CAPEX) but 50% drift flags a bug |
| **wide** | ±55% | Carbon, footprint | N₂O has a ×10 IPCC range; footprint depends on layout assumptions |

Ranges are set from actual platform outputs at calibration time, then widened by the tier multiplier. They are **not design targets** — they are regression sentinels.

---

## Scenario Definitions

### S1 — Medium Municipal BNR Baseline

**Purpose:** Reference scenario. All other scenarios deviate from S1 in one dimension.

| Parameter | Value |
|-----------|-------|
| Flow | 10 MLD |
| Temperature | 20°C |
| BOD / TKN | 250 / 45 mg/L |
| Effluent TN / TP | 10 / 1 mg/L |
| Technologies | BNR, AGS, IFAS, MABR |

**Expected behaviour:** BNR delivers 377 kWh/ML, AGS delivers lower footprint (838 m² vs 1307 m²), MABR delivers lower energy (320 kWh/ML).

**Failure indicators:** If BNR energy moves outside 264–490 kWh/ML, check `bnr.py` O₂ demand calculation. If AGS footprint exceeds BNR, check `granular_sludge.py` clarifier removal logic.

---

### S2 — Cold Climate Nitrification

**Purpose:** Tests cold-temperature physics — SRT extension, NH₄ penalty, AGS energy penalty.

| Parameter | Value |
|-----------|-------|
| Flow | 8 MLD |
| Temperature | **12°C** |
| BOD / TKN | 220 / 48 mg/L |
| Technologies | BNR, AGS, MABR, IFAS |

**Expected behaviour:**
- BNR: reactor volume increases (SRT extended per Metcalf Fig 7-42), effluent NH₄ ≤8 mg/L (×4 penalty at ≤12°C)
- AGS: energy increases vs warm (explicit cold penalty in `granular_sludge.py`)
- MABR: relatively less affected by cold temperature

**Failure indicators:**
- `B02_cold_bnr_reactor_increases` fails → cold SRT extension removed from `bnr.py`
- `B03_cold_bnr_nh4_increases` fails → cold NH₄ penalty removed from `bnr.py`
- `B01_cold_ags_energy_increases` fails → cold energy penalty removed from `granular_sludge.py`

---

### S3 — Tight Ammonia Compliance

**Purpose:** All technologies must achieve NH₄ < 1 mg/L at 18°C with adequate SRT.

| Parameter | Value |
|-----------|-------|
| Flow | 12 MLD |
| Temperature | 18°C |
| Effluent NH₄ | **< 1 mg/L** |
| Technologies | BNR, MABR, IFAS, MBR |

**Expected behaviour:** All technologies achieve NH₄ ≤ 1.5 mg/L at 18°C (marginally achievable). MABR energy advantage: 317 vs 379 kWh/ML for BNR.

**Failure indicators:** If any technology shows NH₄ > 2 mg/L at 18°C, nitrification logic has regressed.

---

### S4 — Capacity Expansion, Footprint Constrained

**Purpose:** Tests footprint calculation. AGS must show materially smaller footprint than BNR.

| Parameter | Value |
|-----------|-------|
| Flow | **20 MLD** |
| Temperature | 19°C |
| Technologies | BNR, AGS, MBR, IFAS |

**Expected behaviour:** AGS footprint (1642 m²) is ~35% less than BNR (2418 m²) because no secondary clarifiers are required. BNR+MBR footprint is similar to BNR at this scale (BNR zone dominates).

**Failure indicators:** `B07_ags_footprint_lt_bnr` fails → clarifier area inclusion/exclusion logic changed in `granular_sludge.py` or `bnr.py`.

---

### S5 — Carbon-Limited Denitrification

**Purpose:** Tests carbon limitation detection. At BOD=120/TKN=45 (COD/TKN≈5.3), the platform must recognise that denitrification cannot achieve TN=10 mg/L.

| Parameter | Value |
|-----------|-------|
| Flow | 10 MLD |
| BOD | **120 mg/L** (low) |
| TKN | 45 mg/L |
| COD/TKN | **≈5.3** (threshold: 7.0) |
| Technologies | BNR, IFAS |

**Expected behaviour:** BNR effluent TN ≈ 18 mg/L (target 10 mg/L). IFAS effluent TN ≈ 20 mg/L (worse than BNR — limited anoxic zone). Low BOD also means low energy (262 kWh/ML) and low sludge (741 kgDS/d) vs S1.

**Failure indicators:**
- `B05_carbon_limited_tn_exceeds` fails → carbon-limited TN logic removed from `bnr.py` (COD/TKN thresholds from Metcalf Table 7-32)
- `S5/bnr/eff_tn` range fails with TN < 12 → TN target being incorrectly achieved

---

### S6 — Energy and Carbon Reduction

**Purpose:** Tests electricity price sensitivity. At $0.22/kWh, MABR and AGS energy advantages become material in lifecycle cost.

| Parameter | Value |
|-----------|-------|
| Flow | 12 MLD |
| Electricity | **$0.22/kWh** |
| Carbon price | **$80/tCO₂e** |
| Technologies | BNR, MABR, AGS |

**Expected behaviour:** BNR OPEX at $0.22/kWh is ~40% higher than at $0.14/kWh. MABR delivers 329 vs 384 kWh/ML for BNR.

**Failure indicators:** `B14_electricity_price_lifts_opex` fails → electricity price override not reaching costing engine.

---

### S7 — Biosolids Disposal Cost Pressure

**Purpose:** Tests sludge cost propagation. At $450/t DS, AGS lower yield shifts LCC.

| Parameter | Value |
|-----------|-------|
| Flow | **25 MLD** |
| Sludge disposal | **$450/t DS** |
| Technologies | BNR, AGS, MBR |

**Expected behaviour:**
- AGS produces ~18% less sludge than BNR (3356 vs 4083 kgDS/d)
- AGS LCC ($2716k) < BNR LCC ($3165k) despite higher CAPEX
- BNR OPEX at $450/t DS is $2053k (vs $1006k at base $280/t)

**Failure indicators:**
- `B09_high_sludge_ags_lcc_lt_bnr` fails → sludge disposal cost not reflected in LCC
- `B10_ags_sludge_lt_bnr` fails → AGS sludge yield regressed to BNR levels

---

### S8 — Reuse-Ready Effluent Polishing

**Purpose:** Tests tight effluent targets for indirect potable reuse pre-treatment.

| Parameter | Value |
|-----------|-------|
| Flow | 10 MLD |
| Effluent BOD | < 5 mg/L |
| Effluent TSS | < 5 mg/L |
| Effluent TN  | < 5 mg/L |
| Effluent TP  | < 0.3 mg/L |
| Technologies | BNR+MBR, AGS, BNR |

**Expected behaviour:**
- BNR+MBR: TSS < 1 mg/L (membrane retention), BOD 2–5 mg/L (soluble fraction passes)
- AGS: TP ≤ 0.5 mg/L with ferric chloride polishing

**Failure indicators:**
- `B11_mbr_reuse_tss_lt_2` fails → MBR TSS model changed (membrane no longer acting as absolute barrier)
- `S8/bnr_mbr/eff_tss` range fails → check `bnr_mbr.py` effluent TSS assignment

---

## Behavioural Checks

These 14 checks verify *engineering relationships*, not absolute numbers. They must hold regardless of scale.

| Check | Physical Principle | Reference |
|-------|--------------------|-----------|
| B01 | Cold AGS energy increases | van Dijk 2020 — granule stability |
| B02 | Cold BNR reactor volume increases | Metcalf Fig 7-42 — SRT vs T |
| B03 | Cold BNR effluent NH₄ increases | Metcalf Eq 7-98 — nitrif rate vs T |
| B04 | Cold increases risk score | WEF MOP 35 — operational risk |
| B05 | Carbon-limited TN exceeds target | Metcalf Table 7-32 — COD/TKN |
| B06 | IFAS TN ≥ BNR TN (C-limited) | Limited IFAS anoxic zone |
| B07 | AGS footprint < BNR | Pronk 2015 — no secondary clarifiers |
| B08 | MABR energy < BNR | GE/Ovivo 2017, Syron & Casey 2008 |
| B09 | High sludge → AGS LCC < BNR | Sludge quantity × disposal rate |
| B10 | AGS sludge < BNR | de Kreuk 2007 — longer SRT |
| B11 | MBR TSS < 2 mg/L | Membrane size exclusion |
| B12 | BNR risk < AGS < MABR | IWA 2022 — technology maturity |
| B13 | CAPEX/MLD decreases with scale | WEF — Six-Tenths Rule |
| B14 | Higher electricity price → higher OPEX | Direct cost propagation |

---

## Technology Mapping

| Scenario | BNR | AGS | MABR | MBR | IFAS |
|----------|-----|-----|------|-----|------|
| S1 Baseline | ✅ | ✅ | ✅ | — | ✅ |
| S2 Cold climate | ✅ | ✅ | ✅ | — | ✅ |
| S3 Tight NH₄ | ✅ | — | ✅ | ✅ | ✅ |
| S4 Footprint | ✅ | ✅ | — | ✅ | ✅ |
| S5 Carbon-limited | ✅ | — | — | — | ✅ |
| S6 Energy/carbon | ✅ | ✅ | ✅ | — | — |
| S7 Sludge cost | ✅ | ✅ | — | ✅ | — |
| S8 Reuse | ✅ | ✅ | — | ✅ | — |

Technologies not included in a scenario are not relevant to its primary engineering question.

---

## Extending the Suite

### Adding a new scenario

1. Add a `Scenario(...)` entry to `tests/benchmark/scenarios.py`
2. Set `technologies` to the relevant codes
3. Run the platform once to capture actual outputs
4. Set `expected` ranges using `_m(centre, Tol.MODERATE)` for costs/energy, `_rng(lo, hi, "tight")` for effluent quality
5. Run `python3 tests/benchmark/run_benchmarks.py --ranges` to confirm all pass

### Adding a new behavioural check

1. Add a method to `TestBehaviour` in `test_benchmark_regression.py`
2. Document the physical principle and reference
3. Add the equivalent check to `run_behaviour()` in `run_benchmarks.py`

### Updating ranges after an intentional code change

If a calculation improvement deliberately changes outputs, update the ranges:

```python
# Old (pre-change calibration)
"capex_m": _m(7.81, Tol.MODERATE),   # centre $7.81M

# New (post-change calibration)
"capex_m": _m(8.12, Tol.MODERATE),   # centre updated
```

Always add a comment explaining what changed and why.

---

## References

| Reference | Used for |
|-----------|----------|
| Metcalf & Eddy 5th Ed | O₂ demand, SRT, sludge yield, cold T corrections |
| WEF Cost Estimating Manual 2018 | CAPEX/OPEX unit rates, economy of scale |
| de Kreuk 2007 | AGS energy and sludge production |
| van Dijk 2020 | AGS cold temperature granule stability |
| Pronk 2015 | AGS full-scale footprint vs BNR |
| GE/Ovivo 2017 | MABR energy benchmarks |
| Syron & Casey 2008 | MABR oxygen transfer theory |
| IWA 2022 | Technology maturity ratings |
| IPCC 2019 Tier 1 | N₂O emission factors (EF=0.016, range 0.005–0.050) |
| AU Water Association | Utility OPEX benchmarks, AUD 2024 |
