# Filter Performance Comparator — Python engine & report

AquaPoint-independent core of the **Filter Performance Comparator** module:
a faithful Python port of the JavaScript engine, the three report charts
(matplotlib), and the ~20-page governance-grade PDF report (reportlab).

This package contains **no Streamlit and no AquaPoint imports**. It is the
half of the module that can be built and verified on its own. The remaining
AquaPoint-dependent piece — `ui.py`, which wires the Streamlit widgets,
project/scenario persistence and the document store — is intentionally not
included here and should be built in a session that has the AquaPoint
codebase loaded. The integration seam between the two is four function
calls, documented below.

## Package layout

```
filter_comparator/
  engine/
    physics.py        port of filterPhysics.js      (hydraulics, media, headloss)
    defaults.py       port of filterDefaults.js     (D1/D2 designs, feed defaults)
    calculations.py   port of filterCalculations.js (assess, head budget, K cap)
    backwash.py       port of backwashDynamics.js   (sequence, redundancy, timeline)
    validation.py     port of validation.js         (physical-bounds checks)
    report_model.py   port of reportBuilder.js      -> build_report_model()
  report/
    charts.py         port of reportCharts.js       -> build_all_charts()
    pdf_report.py     port of pdfReport.js          -> build_pdf()
verify_engine.py      acceptance check vs. the handoff reference numbers
```

## Requirements

Python 3.10+, with `matplotlib` and `reportlab`:

```
pip install matplotlib reportlab
```

The engine itself (everything under `engine/`) is pure standard-library
Python; `matplotlib`/`reportlab` are only needed for the `report/` modules.

## The integration interface — four touchpoints

`ui.py` (the AquaPoint-dependent file built later) only needs these:

1. **Collect inputs into two pairs of plain dicts.**
   `engine/defaults.py` provides ready-made templates:
   `DESIGNER_DEFAULTS['D1'|'D2']['filter']` for filter geometry, and
   `DESIGNER_FEED_DEFAULTS['D1'|'D2']` for feed conditions / backwash
   volumes. Streamlit widgets edit copies of these dicts.

2. **Build the assessment model.**

   ```python
   from filter_comparator.engine.report_model import build_report_model

   model = build_report_model(
       filter_d1, filter_d2,        # filter geometry dicts
       feed_d1, feed_d2,            # feed condition dicts
       name_d1="SJHJV", name_d2="Acciona",
       prepared_by="Independent Engineering Review",
   )
   ```

   `model` is a nested dict with every derived number the report uses
   (`modes`, `lfl`, `redundancy`, `coldWater`, `opportunityD2`,
   `validation`, ...).

3. **Render the PDF.**

   ```python
   from filter_comparator.report.pdf_report import build_pdf

   pdf_bytes = build_pdf(model)                       # -> bytes
   # or: build_pdf(model, output_path="report.pdf")
   ```

   `build_pdf` builds the charts internally; pass `charts=` only if you
   already have them from `build_all_charts(model)`.

4. **Hand the bytes to AquaPoint.** `ui.py` passes `pdf_bytes` to
   AquaPoint's project/scenario persistence and document store, and offers
   a download. That step is AquaPoint-specific and lives in `ui.py`.

`build_all_charts(model)` (in `report/charts.py`) is also available on its
own — it returns a dict of three in-memory PNG buffers (`capacity`,
`headBudget`, `sensitivity`) if the charts are needed outside the PDF, e.g.
for on-screen display in the Streamlit UI.

## Verification

`verify_engine.py` builds the model from the default D1/D2 designs and
checks the derived numbers against the reference values in the handoff:

```
$ python3 verify_engine.py
  D1 coagulation margin (m)      computed  +0.309   ref ~+0.31   OK
  D2 coagulation margin (m)      computed  +1.985   ref ~+1.99   OK
  D1 softening margin (m)        computed  +0.433   ref ~+0.43   OK
  D2 softening margin (m)        computed  +1.653   ref ~+1.65   OK
  D1 N-1 head-for-load (m)       computed  +1.222   ref ~+1.22   OK
  D2 N-1 head-for-load (m)       computed  +2.251   ref ~+2.25   OK
  RESULT: ALL REFERENCE CHECKS PASSED
```

All values are evaluated at 120 ML/d and the 15 degC minimum design water
temperature, as the report basis specifies.

## Notes on the port

* The port is faithful to the JavaScript source: function and structure
  names track the originals so the two can be cross-checked. Logic was not
  re-derived.
* The report wording in `pdf_report.py` reproduces `pdfReport.js`
  verbatim, including its even-handed framing — the report presents a
  genuine tradeoff between the two configurations and recommends neither.
* "Deposit structure factor" is the user-facing term for the precipitate
  K-multiplier and is used consistently in the report text.
* Precipitate names are kept as plain ASCII (`CaCO3`, `Mg(OH)2`) exactly as
  in the source.
