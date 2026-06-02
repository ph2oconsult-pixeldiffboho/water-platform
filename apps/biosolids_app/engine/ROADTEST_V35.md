# BioPoint V3.5 - Road Test Report

**Basis:** ETP, Cambi 2026 (219.5 tDS/d, 64,000 m3, VS 65%)
**Date:** 2 June 2026
**Scope:** Full V3.5 stack - Pathways A-K front ends, Pathway X endpoint compositions,
carbon-strategy comparison (decision-hierarchy L6), regret profiles, sensitivity.

**Verdict: PASS** - calibrated, closing, physically coherent, decision-logic sound,
and robust to the provisional endpoint bands. One scoring gap found and fixed.

---

## 1. Closure and calibration

All 12 front-end pathways and all 5 Pathway-X compositions close on every ledger
(carbon / energy / nitrogen / phosphorus) to 0.000%. Feed carbon (72.8 tC/d) conserves
across every endpoint - composition re-routes only the cake. Calibration anchors land on
the source memo:

| Anchor | Model | Target (Cambi 2026 / Mangere) |
|---|---|---|
| Conventional VSR | 0.575 | 0.575 (Mangere P50 0.585) |
| SolidStream VSR | 0.703 | 0.703 |
| Conv -> SolidStream net export | 181 -> 217 MWh/d | +20% |
| K capacity released | 15,725 m3 | 15,000-16,000 |
| K WAS HRT (with recycle) | 15.8 d | 15.7 |
| K deferred CAPEX | $31M @ $2,000/m3 | - |

K's basis carries cake_ds = 0.38, so thermal drying loads are computed on the correct
(drier) SolidStream cake, not a default.

## 2. Key finding - the three stages compound

Thermal endpoints need ~90% DS feed, so the Stage-3 drying penalty depends on Stage-2
cake dryness:

| Endpoint feed | Wet cake | Water evaporated | Drying load |
|---|---|---|---|
| Conventional cake (22% DS) | 625 t/d | 472 t/d | 425 MWh/d |
| SolidStream cake (38% DS) | 314 t/d | 181 t/d | 163 MWh/d |

SolidStream (Stage 2) removes ~260 MWh/d of Stage-3 drying penalty - the interaction that
makes pyrolysis / gasification / incineration energy-viable. A single digestion score hides
this; the staged architecture exposes it. V3.5 thesis validated on real numbers.

## 3. Decision-logic sanity (regret output)

Ranked by performance, the top of the 16-pathway set is the high-PFAS thermal endpoints
(gasification 0.67 conf B; incineration 0.66 conf A). Every thermal-endpoint pathway is
acceptable-risk (OK); every land-ending pathway is flagged HEDGE - they break under the
high-likelihood PFAS land-application shock and must hold a thermal endpoint open.

- **Energy trap resisted.** HTL, despite the highest net export (341 MWh/d), ranks 8th -
  pulled down by confidence C and weaker resilience. Energy alone does not win.

## 4. Sensitivity - do family rankings survive the provisional bands?

Robust across the full band range:

- **Carbon removal:** biochar fraction 0.30 / 0.45 / 0.55 -> pyrolysis removal 18.6 / 28.0 /
  34.2 tCO2e/d, but pyrolysis stays the removal leader at every point (above land 11.6,
  gasification 3.1).
- **Energy:** endpoint energy density x0.6 / x1.0 / x1.4 -> net-export order never flips
  (htl > gasification > incineration > pyrolysis throughout).
- **PFAS:** structural, not band-driven (incin 100 > gas 97 > pyro 70 > htl 45 > land 0).

The "do not combine" separation reflects real family differences, not false precision.

## 5. Issue found and fixed

**Pathway B under-scored.** B (MAD + PN/A) destroys return-liquor N (5,081 -> 610 kgN/d)
but the nutrient score credited only recovery (struvite), not destruction, so B scored ~0
on nutrients and ranked last. Fixed: return-liquor N removed by PN/A now earns nutrient
credit at half the weight of true recovery (it cuts the return load + N2O but yields no
product). B's nutrient score 0.000 -> 0.089; performance 0.39 -> 0.402, now edging
conventional A. Non-PN/A pathways unchanged; all ledgers still close.

## 6. Confidence summary

| Layer | Confidence | Basis |
|---|---|---|
| Front-end biology + SolidStream | A | Cambi 2026 / Mangere calibrated |
| K capacity release | B | short-HRT-PS unvalidated; pilot named |
| Endpoint: incineration | A | mature mono-incineration fleet |
| Endpoint: pyrolysis / gasification | B | AU commercial + demos |
| Endpoint: HTL | C | pre-commercial |

## 7. Not yet tested (next)

- Actual PDF render of the carbon-strategy section (9-column table fit on A4).
- Independent third-dataset validation (beyond the two Cambi memos the model is calibrated to).

GENERIC-plant robustness: PASSED - full stack (builders, composition, carbon_strategy_comparison,
decision_hierarchy) runs without exception on a plant missing digester_vol_m3 and feed_N_kgd; the K
capacity claim self-suppresses to 0 rather than defaulting, and switches on when a volume is supplied.
