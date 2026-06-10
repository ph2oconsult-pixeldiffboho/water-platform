# Algae module integration — IMPLEMENTED

The algae-clogging model is now wired through the engine, the report and the
Streamlit page. This document records what was done so the package is
self-describing. All changes are additive; the existing acceptance numbers are
unchanged and both suites pass (`verify_engine.py`, `verify_algae.py`).

## What was implemented

1. **Engine model (engine/report_model.py).** `build_report_model` now calls
   `assess_algae` per design and returns an `"algae"` block:
   `model["algae"]["D1"|"D2"]` with per-mode `E_m`, `E_source`, the calculated
   `head_budget`, `scenarios` (W,A,B,C,D,E run times, instant, N_A, band),
   `baseline_run_h`, plus `highlightScenario` and `densadegRecycle`. Inputs are
   read from the feed dict; a missing residual falls back to ~10% of the
   project raw algal count (assumed clarifier removal).

2. **Pluggable available head.** `run_time(J, E, ...)` is the source-agnostic
   core. `assess_algae(..., available_head=, driving_head_m=, head_source=)`
   resolves E from: `None` (calculated), a number (manual, all modes), a
   `{mode: E}` dict (manual per mode), or a callable `(mode, J, calc)` for a
   profile-derived value. `resolve_available_head` is exposed for reuse.

3. **Feed defaults (engine/defaults.py).** Added to `DESIGNER_FEED_DEFAULTS`:
   `residualAlgae_cells_per_mL` (20000), `massPerCell_pg` (100),
   `mineralBackground_mgL` (8), `morphologyScenario` (None),
   `densadegRecycle` (D1 True / D2 False), `availableHead_m`, `headSource`,
   `drivingHeadOverride_m`.

4. **Validation (engine/algae.py).** `validate_algae_inputs` bounds cells
   0..2e6, mass/cell 10..1000 pg, mineral 0..50 mg/L; issues are folded into the
   model's validation block.

5. **Charts (report/charts.py).** `chart_algae` (Figure 4): run length by
   morphology scenario at N, D1 vs D2, with a 24 h reference line.
   `build_all_charts` adds it when the model carries an algae block.

6. **PDF (report/pdf_report.py).** Section 11 ("Algal loading and filter-
   clogging risk") now carries an "Algae-clogging screening model" subsection:
   a run-length-by-morphology table (D1 vs D2 at N, plus no-algae baseline),
   Figure 4, an interpretation paragraph and a risk-screening caveat.

7. **Page (filter_comparator_page.py).** An "Algae loading & clogging" section
   collects residual cells, mineral background, mass per cell, a recycle flag,
   a morphology highlight, and a head-source control (calculated / manual single
   / manual per mode / driving-head override / upload a hydraulic profile). A
   brief on-screen screening summary is shown after a successful build. All
   inputs write into the feed dicts already passed to `build_report_model`.

## Remaining (host app only, outside this package)

Registering the page in the AquaPoint shell, as already described in the
`filter_comparator_page.py` docstring: add it to `PAGES` in
`apps/drinking_water_app/app.py` and export `render` from
`apps/drinking_water_app/pages/__init__.py`, wrapped in the same guarded import
used by the other pages. Requires `reportlab` and `matplotlib`, and the four
`ui_helpers` (section_header, info_box, success_box, warning_box) already used
by the page. No other change is needed.

## Caveats surfaced in the output

Risk-screening run times (about +/-30%), not predictions. Resistances are
RGF-scale effective values; do not substitute membrane alpha. Mass is conserved.
The result depends far more on morphology than on cell count.
