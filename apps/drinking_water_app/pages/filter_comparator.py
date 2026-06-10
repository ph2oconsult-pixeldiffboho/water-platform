"""
AquaPoint — Page 11: Filter Performance Comparator

Generalised two-design rapid gravity filter comparison. Produces the
~20-page governance-grade PDF assessment via the vendored
``filter_comparator`` package.

Integration notes
------------------
* This file is the AquaPoint-dependent UI layer. The AquaPoint-independent
  engine, charts and PDF builder live in the ``filter_comparator`` package,
  which is expected to be vendored at
  ``apps/drinking_water_app/filter_comparator/``.
* Register in ``apps/drinking_water_app/app.py`` by adding to PAGES:
      "filter_comparator": {
          "label": "Filter Comparator", "icon": "🪣",
          "render": render_filter_comparator, "number": 11,
      }
  and in ``apps/drinking_water_app/pages/__init__.py``:
      from .filter_comparator import render as render_filter_comparator
  Wrap the import in app.py in the same try/except used for
  render_design_envelope so a missing dependency degrades gracefully.
* Requires ``reportlab`` and ``matplotlib`` in the AquaPoint environment.
* Inputs default to the Wyaralong basis; the operator can edit every field
  to assess an arbitrary two-design comparison (Option B).

This module uses only the four platform ui_helpers confirmed by existing
AquaPoint pages (section_header, info_box, success_box, warning_box); all
other markup is inline, matching the house style of pages 2 and 5.
"""
import copy
from datetime import date

import streamlit as st

from ..ui_helpers import section_header, info_box, success_box, warning_box

# ── Vendored engine import (guarded so a missing dependency is friendly) ──────
try:
    from ..filter_comparator.engine.report_model import (
        build_report_model, REPORT_MODES, REPORT_PROJECT, REPORT_ROUTES,
        REPORT_FLOW,
    )
    from ..filter_comparator.engine.defaults import (
        DESIGNER_DEFAULTS, DESIGNER_FEED_DEFAULTS,
    )
    from ..filter_comparator.engine.physics import (
        UNDERDRAIN_LIBRARY, MEDIA_CONFIGURATIONS, MEDIA_LIBRARY,
        CLEAN_BED_EQ_LABELS,
    )
    from ..filter_comparator.report.pdf_report import build_pdf
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - import-environment dependent
    _IMPORT_ERROR = str(exc)


# ── Session-state keys owned by this page (namespaced 'fc_') ──────────────────
_SS = "fc_inputs"


def _coag_precip(coagulant):
    """Map a coagulant choice to a precipitate dict + chem label."""
    if coagulant == "ferric":
        return {"ferric": 1}, "ferric coagulation"
    return {"alum": 1}, "alum coagulation"


def _soft_precip(mg_removal):
    """Softening precipitate composition implied by the route.

    A magnesium-removal route carries a magnesium hydroxide fraction; a
    calcium-carbonate-dominant route does not.
    """
    if mg_removal:
        return {"caco3": 0.9, "mgoh2": 0.05, "other": 0.05}
    return {"caco3": 0.95, "other": 0.05}


def _design_defaults(dk):
    """Deep copies of the filter + feed default dicts for design D1/D2."""
    return (copy.deepcopy(DESIGNER_DEFAULTS[dk]["filter"]),
            copy.deepcopy(DESIGNER_FEED_DEFAULTS[dk]))


def _media_stack_caption(layers):
    """One-line human-readable media stack summary."""
    parts = ["%s %.2f m (%.2f mm)" % (l["media"], l["depth"], l["d_mm"])
             for l in layers]
    return "  ·  ".join(parts)


def render():
    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
        <div style="margin-bottom:1.5rem">
            <h2 style="color:#1a1a2e;font-size:1.4rem;font-weight:600;margin-bottom:0.3rem">
                Filter Performance Comparator
            </h2>
            <p style="color:#555;font-size:0.9rem;margin:0">
                Compare two rapid gravity filter designs across coagulation and
                lime-softening duty, and export a governance-grade PDF assessment.
            </p>
        </div>
    """, unsafe_allow_html=True)

    if _IMPORT_ERROR:
        warning_box(
            "The filter_comparator engine could not be loaded: %s. "
            "Confirm the package is vendored at "
            "apps/drinking_water_app/filter_comparator/ and that reportlab "
            "and matplotlib are installed." % _IMPORT_ERROR)
        return

    # Working input store, seeded once from the Wyaralong defaults.
    if _SS not in st.session_state:
        st.session_state[_SS] = {
            "seeded": True,
            "filters": {dk: _design_defaults(dk)[0] for dk in ("D1", "D2")},
            "feeds": {dk: _design_defaults(dk)[1] for dk in ("D1", "D2")},
        }
    store = st.session_state[_SS]

    # ── Project descriptors (ii) ──────────────────────────────────────────────
    section_header("Project descriptors", "📋")
    info_box(
        "These descriptors appear in the report prose. They default to the "
        "built-in basis; edit them so the report is truthful for your project.")

    sw = st.session_state.get("source_water", {})
    col1, col2 = st.columns(2)
    with col1:
        plant = st.text_input(
            "Plant / project name",
            value=st.session_state.get("project_name") or REPORT_PROJECT["plant"],
            key="fc_plant")
        temp_basis = st.text_input(
            "Temperature basis (location descriptor)",
            value=REPORT_PROJECT["temperature_basis"], key="fc_temp_basis",
            help="Short phrase, e.g. 'South East Queensland'. Appears as "
                 "'(a <basis> basis)' in the report.")
    with col2:
        flow = st.number_input(
            "Design flow (ML/d)",
            min_value=1.0, max_value=2000.0,
            value=float(st.session_state.get("flow_ML_d") or REPORT_FLOW),
            step=5.0, format="%.1f", key="fc_flow")
        algal = st.number_input(
            "Algal design basis (cells/mL)",
            min_value=0.0, max_value=5_000_000.0,
            value=float(sw.get("algal_cells_ml") or REPORT_PROJECT["algal_cells_ml"]),
            step=10_000.0, format="%.0f", key="fc_algal",
            help="Pre-filled from Source Water Quality where available.")
    prepared_by = st.text_input(
        "Prepared by",
        value=st.session_state.get("author") or "", key="fc_prepared_by")

    project = {
        "plant": plant.strip() or REPORT_PROJECT["plant"],
        "temperature_basis": temp_basis.strip(),
        "algal_cells_ml": int(algal),
    }

    # ── Designs compared ──────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Designs compared", "🔧")
    info_box(
        "Geometry and hydraulics for the two filter designs. Every field here "
        "feeds the head-budget calculation in the report.")

    underdrain_keys = list(UNDERDRAIN_LIBRARY.keys())
    eq_keys = list(CLEAN_BED_EQ_LABELS.keys())
    media_keys = list(MEDIA_CONFIGURATIONS.keys())

    names = {}
    cols = st.columns(2)
    for idx, dk in enumerate(("D1", "D2")):
        filt = store["filters"][dk]
        with cols[idx]:
            st.markdown(
                f"<div style='font-weight:600;color:#1a56a0;margin-bottom:0.4rem'>"
                f"Design {dk}</div>", unsafe_allow_html=True)
            names[dk] = st.text_input(
                "Designer name", value="Designer %s" % dk[-1],
                key="fc_name_%s" % dk)
            filt["numFilters"] = int(st.number_input(
                "Number of filters", min_value=1, max_value=60,
                value=int(filt["numFilters"]), step=1, key="fc_nf_%s" % dk))
            filt["areaPerFilter_m2"] = float(st.number_input(
                "Area per filter (m²)", min_value=1.0, max_value=400.0,
                value=float(filt["areaPerFilter_m2"]), step=1.0,
                format="%.1f", key="fc_area_%s" % dk))
            st.caption("Total filter area: %.1f m²"
                       % (filt["numFilters"] * filt["areaPerFilter_m2"]))
            filt["drivingHead_m"] = float(st.number_input(
                "Driving head (m)", min_value=0.5, max_value=12.0,
                value=float(filt["drivingHead_m"]), step=0.05,
                format="%.2f", key="fc_dh_%s" % dk))
            filt["appurtenanceLoss_m"] = float(st.number_input(
                "Appurtenance loss (m)", min_value=0.0, max_value=3.0,
                value=float(filt["appurtenanceLoss_m"]), step=0.05,
                format="%.2f", key="fc_app_%s" % dk))
            ud_idx = (underdrain_keys.index(filt["underdrain"])
                      if filt.get("underdrain") in underdrain_keys else 0)
            filt["underdrain"] = st.selectbox(
                "Underdrain", underdrain_keys, index=ud_idx,
                format_func=lambda k: UNDERDRAIN_LIBRARY[k]["name"],
                key="fc_ud_%s" % dk)
            eq_idx = (eq_keys.index(filt["cleanBedEquation"])
                      if filt.get("cleanBedEquation") in eq_keys else 0)
            filt["cleanBedEquation"] = st.selectbox(
                "Clean-bed headloss equation", eq_keys, index=eq_idx,
                format_func=lambda k: CLEAN_BED_EQ_LABELS[k],
                key="fc_eq_%s" % dk)

    # ── Media stacks (per-layer editable table) ───────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Media stacks", "🪨")
    info_box(
        "Each design's media stack, top to bottom. Edit cells directly, add "
        "or delete layers, or load a preset configuration. Media type must be "
        "one of: " + ", ".join(MEDIA_LIBRARY.keys()) + ".")

    media_opts = list(MEDIA_LIBRARY.keys())
    for dk in ("D1", "D2"):
        filt = store["filters"][dk]
        st.markdown(
            f"<div style='font-weight:600;color:#1a56a0;margin:0.6rem 0 0.2rem'>"
            f"{names[dk]} — media stack</div>", unsafe_allow_html=True)

        # Preset loader: on change, reseed the layers and bump the editor nonce
        # so st.data_editor re-initialises from the new stack.
        nonce_key = "fc_media_nonce_%s" % dk
        st.session_state.setdefault(nonce_key, 0)
        pcols = st.columns([3, 1])
        with pcols[0]:
            preset = st.selectbox(
                "Load preset configuration (optional)",
                ["(keep current stack)"] + media_keys,
                index=0, key="fc_preset_%s" % dk,
                format_func=lambda k: (k if k == "(keep current stack)"
                                       else MEDIA_CONFIGURATIONS[k]["name"]))
        if preset != "(keep current stack)":
            filt["mediaLayers"] = copy.deepcopy(
                MEDIA_CONFIGURATIONS[preset]["layers"])
            filt["mediaConfig"] = preset
            st.session_state[nonce_key] += 1
            st.session_state["fc_preset_%s" % dk] = "(keep current stack)"
            st.rerun()

        edited = st.data_editor(
            filt["mediaLayers"], num_rows="dynamic",
            key="fc_media_tbl_%s_%d" % (dk, st.session_state[nonce_key]),
            use_container_width=True,
            column_config={
                "media": st.column_config.SelectboxColumn(
                    "Media", options=media_opts, required=True),
                "depth": st.column_config.NumberColumn(
                    "Depth (m)", min_value=0.05, max_value=3.0, step=0.05,
                    format="%.3f", required=True),
                "d_mm": st.column_config.NumberColumn(
                    "d_e (mm)", min_value=0.1, max_value=5.0, step=0.05,
                    format="%.2f", required=True),
                "uc": st.column_config.NumberColumn(
                    "UC", min_value=1.0, max_value=2.5, step=0.05,
                    format="%.2f", required=True),
                "porosity": st.column_config.NumberColumn(
                    "Porosity", min_value=0.25, max_value=0.65, step=0.01,
                    format="%.2f", required=True),
            })
        # Normalise editor output back to a clean list of layer dicts.
        layers = []
        for row in edited:
            try:
                layers.append({
                    "media": row["media"],
                    "depth": float(row["depth"]),
                    "d_mm": float(row["d_mm"]),
                    "uc": float(row["uc"]),
                    "porosity": float(row["porosity"]),
                })
            except (KeyError, TypeError, ValueError):
                continue  # skip an incomplete in-progress row
        if layers:
            filt["mediaLayers"] = layers
        st.caption("Bed depth: %.2f m  ·  %d layer(s)"
                   % (sum(l["depth"] for l in filt["mediaLayers"]),
                      len(filt["mediaLayers"])))

    # ── Backwash & washwater volumes ──────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Backwash & washwater volumes", "💧")
    info_box(
        "Per-cycle washwater volumes for each design. These drive the "
        "backwash and washwater-balance section of the report.")
    bwcols = st.columns(2)
    for idx, dk in enumerate(("D1", "D2")):
        feed = store["feeds"][dk]
        with bwcols[idx]:
            st.markdown(
                f"<div style='font-weight:600;color:#1a56a0;margin-bottom:0.4rem'>"
                f"{names[dk]}</div>", unsafe_allow_html=True)
            feed["drainVolume_m3"] = float(st.number_input(
                "Drain-down volume (m³/cycle)", min_value=0.0, max_value=5000.0,
                value=float(feed.get("drainVolume_m3", 0.0)), step=5.0,
                format="%.0f", key="fc_drain_%s" % dk))
            feed["backwashVolume_m3"] = float(st.number_input(
                "Backwash volume (m³/cycle)", min_value=0.0, max_value=5000.0,
                value=float(feed.get("backwashVolume_m3", 0.0)), step=5.0,
                format="%.0f", key="fc_bw_%s" % dk))
            feed["ftwVolume_m3"] = float(st.number_input(
                "Filter-to-waste volume (m³/cycle)", min_value=0.0,
                max_value=5000.0, value=float(feed.get("ftwVolume_m3", 0.0)),
                step=5.0, format="%.0f", key="fc_ftw_%s" % dk))
            st.caption("Total washwater: %.0f m³/cycle"
                       % (feed["drainVolume_m3"] + feed["backwashVolume_m3"]
                          + feed["ftwVolume_m3"]))

    # ── Algae loading & clogging ──────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Algae loading & clogging", "🦠")
    info_box(
        "Residual algal load reaching the filters and how the available "
        "clogging head is set. Run-length estimates are risk-screening only "
        "(about plus or minus 30 percent) and depend far more on algal "
        "morphology than on the cell count.")
    _HEAD_BASES = ["Calculated (from head budget)", "Manual single value",
                   "Manual per mode (N, N-1, N-2)", "Driving-head override",
                   "From hydraulic profile (upload)"]
    _MORPHS = ["(run all, no highlight)", "W well-coagulated", "A mineral floc",
               "B mixed algae", "C colonial", "D filamentous", "E EPS-rich bloom"]
    acols = st.columns(2)
    for idx, dk in enumerate(("D1", "D2")):
        feed = store["feeds"][dk]
        with acols[idx]:
            st.markdown(
                f"<div style='font-weight:600;color:#1a56a0;margin-bottom:0.4rem'>"
                f"{names[dk]}</div>", unsafe_allow_html=True)
            feed["residualAlgae_cells_per_mL"] = float(st.number_input(
                "Residual algae (cells/mL)", min_value=0.0, max_value=2000000.0,
                value=float(feed.get("residualAlgae_cells_per_mL") or 0.0),
                step=1000.0, format="%.0f", key="fc_alg_cells_%s" % dk))
            feed["mineralBackground_mgL"] = float(st.number_input(
                "Mineral background (mg/L)", min_value=0.0, max_value=50.0,
                value=float(feed.get("mineralBackground_mgL", 8.0)),
                step=0.5, format="%.1f", key="fc_alg_min_%s" % dk))
            feed["massPerCell_pg"] = float(st.number_input(
                "Mass per cell (pg)", min_value=10.0, max_value=1000.0,
                value=float(feed.get("massPerCell_pg", 100.0)),
                step=10.0, format="%.0f", key="fc_alg_pg_%s" % dk))
            feed["densadegRecycle"] = bool(st.checkbox(
                "Clarifier supernatant recycle (biases residual to EPS)",
                value=bool(feed.get("densadegRecycle")),
                key="fc_alg_recyc_%s" % dk))
            _mi = st.selectbox("Highlight morphology", _MORPHS, index=0,
                               key="fc_alg_morph_%s" % dk)
            feed["morphologyScenario"] = None if _mi == _MORPHS[0] else _mi.split()[0]

            # Available clogging head source (maps onto assess_algae arguments)
            hb = st.selectbox("Available head basis", _HEAD_BASES, index=0,
                              key="fc_alg_hb_%s" % dk)
            feed["availableHead_m"] = None
            feed["headSource"] = None
            feed["drivingHeadOverride_m"] = None
            if hb == _HEAD_BASES[1]:            # manual single value
                feed["availableHead_m"] = float(st.number_input(
                    "Available head E (m)", min_value=0.1, max_value=10.0,
                    value=2.0, step=0.1, format="%.2f", key="fc_alg_E_%s" % dk))
                feed["headSource"] = "manual"
            elif hb == _HEAD_BASES[2]:          # manual per mode
                _ec = st.columns(3)
                _heads = {}
                for _j, _mk in enumerate(("N", "N-1", "N-2")):
                    with _ec[_j]:
                        _heads[_mk] = float(st.number_input(
                            "E %s (m)" % _mk, min_value=0.1, max_value=10.0,
                            value=2.0, step=0.1, format="%.2f",
                            key="fc_alg_E_%s_%s" % (_mk, dk)))
                feed["availableHead_m"] = _heads
                feed["headSource"] = "manual"
            elif hb == _HEAD_BASES[3]:          # driving-head override
                feed["drivingHeadOverride_m"] = float(st.number_input(
                    "Driving head (m)", min_value=0.5, max_value=10.0,
                    value=float(store["filters"][dk].get("drivingHead_m", 3.0)),
                    step=0.1, format="%.2f", key="fc_alg_dh_%s" % dk))
            elif hb == _HEAD_BASES[4]:          # from uploaded hydraulic profile
                _up = st.file_uploader(
                    "Hydraulic profile (CSV lines: mode,head_m)",
                    type=["csv", "txt"], key="fc_alg_prof_%s" % dk)
                if _up is not None:
                    try:
                        _heads = {}
                        for _ln in _up.getvalue().decode("utf-8", "ignore").splitlines():
                            _p = _ln.replace("\t", ",").split(",")
                            if len(_p) >= 2 and _p[0].strip() in ("N", "N-1", "N-2"):
                                _heads[_p[0].strip()] = float(_p[1])
                        if _heads:
                            feed["availableHead_m"] = _heads
                            feed["headSource"] = "profile"
                            st.caption("Parsed: " + ", ".join(
                                "%s=%.2f m" % (k, v) for k, v in _heads.items()))
                        else:
                            info_box("No N / N-1 / N-2 rows found; using the "
                                     "calculated head budget instead.")
                    except Exception as _exc:
                        info_box("Could not read the profile (%s); using the "
                                 "calculated head budget instead." % _exc)

    # ── Softening routes (a) ──────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Softening routes", "🧪")
    info_box(
        "Describe each design's lime-softening route. The report states the "
        "feed-TSS difference as a fact and attributes the basis to these "
        "descriptions. Tick magnesium removal if the route includes a "
        "dedicated magnesium-removal step — this enables the magnesium "
        "hydroxide sensitivity section of the report.")

    routes = {}
    rcols = st.columns(2)
    for idx, dk in enumerate(("D1", "D2")):
        with rcols[idx]:
            st.markdown(
                f"<div style='font-weight:600;color:#1a56a0;margin-bottom:0.4rem'>"
                f"{names[dk]} — softening route</div>", unsafe_allow_html=True)
            text = st.text_area(
                "Route description", value=REPORT_ROUTES[dk]["text"],
                key="fc_route_%s" % dk, height=90)
            mg = st.checkbox(
                "Route includes a magnesium-removal step",
                value=bool(REPORT_ROUTES[dk]["mg_removal"]),
                key="fc_mg_%s" % dk)
            routes[dk] = {"text": text.strip(), "mg_removal": bool(mg)}

    # ── Operating points ──────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Operating points", "⚗️")
    info_box(
        "Feed TSS, run length and removal for each design in each operating "
        "mode. Defaults are the documented values; edit to assess a different "
        "operating basis.")

    modes = copy.deepcopy(REPORT_MODES)
    for mk, mlabel in (("coag", "Coagulation (maximum turbidity)"),
                       ("soft", "Lime softening")):
        st.markdown(
            f"<div style='font-weight:600;color:#1a1a2e;margin:0.6rem 0 0.2rem'>"
            f"{mlabel}</div>", unsafe_allow_html=True)
        mcols = st.columns(2)
        for idx, dk in enumerate(("D1", "D2")):
            md = modes[mk][dk]
            with mcols[idx]:
                st.markdown(
                    f"<div style='font-size:0.82rem;color:#555'>{names[dk]}"
                    f"</div>", unsafe_allow_html=True)
                md["tss"] = float(st.number_input(
                    "Feed TSS (mg/L)", min_value=0.1, max_value=500.0,
                    value=float(md["tss"]), step=0.5, format="%.1f",
                    key="fc_tss_%s_%s" % (mk, dk)))
                md["run"] = float(st.number_input(
                    "Run length (h)", min_value=1.0, max_value=200.0,
                    value=float(md["run"]), step=1.0, format="%.0f",
                    key="fc_run_%s_%s" % (mk, dk)))
                md["removal"] = float(st.number_input(
                    "TSS removal (%)", min_value=10.0, max_value=100.0,
                    value=float(md["removal"]), step=1.0, format="%.0f",
                    key="fc_rem_%s_%s" % (mk, dk)))
                if mk == "coag":
                    cg = st.selectbox(
                        "Coagulant", ["ferric", "alum"],
                        index=0 if "ferric" in md.get("precip", {}) else 1,
                        format_func=str.capitalize,
                        key="fc_coag_%s" % dk)
                    md["precip"], md["chem"] = _coag_precip(cg)
                else:
                    md["precip"] = _soft_precip(routes[dk]["mg_removal"])
                    md["chem"] = "lime softening"

    # ── Build & export ────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Generate assessment report", "📄")

    if st.button("⚙ Build report", type="primary", use_container_width=True):
        try:
            model = build_report_model(
                store["filters"]["D1"], store["filters"]["D2"],
                store["feeds"]["D1"], store["feeds"]["D2"],
                name_d1=names["D1"], name_d2=names["D2"],
                prepared_by=prepared_by, modes=modes, flow=flow,
                project=project, routes=routes)
        except Exception as exc:
            warning_box("Could not build the assessment model: %s" % exc)
            return

        sev = model.get("validation", {}).get("severity", "ok")
        issues = model.get("validation", {}).get("issues", [])
        if sev == "error":
            warning_box(
                "Input validation found physically impossible values. The "
                "report can still be generated but is not decision-ready "
                "until these are corrected:")
            for it in issues:
                st.markdown("- %s" % it.get("message", it))
        elif sev == "warning":
            info_box("Input validation flagged values outside typical ranges; "
                     "review the flagged inputs before relying on the result.")

        try:
            pdf_bytes = build_pdf(model)
        except Exception as exc:
            warning_box("Could not render the PDF: %s" % exc)
            return

        st.session_state["fc_last_pdf"] = pdf_bytes
        st.session_state["fc_last_model"] = model
        success_box("Report generated — %d KB." % (len(pdf_bytes) // 1024))

        try:
            alg = model.get("algae") or {}
            if alg:
                with st.expander("Algae-clogging screening (risk-screening, about +/-30%)"):
                    for dk in ("D1", "D2"):
                        nmode = (alg.get(dk, {}).get("modes", {}) or {}).get("N", {})
                        if not nmode or nmode.get("infeasible"):
                            st.caption("%s: no feasible head at N" % names[dk])
                            continue
                        sc = nmode.get("scenarios", {})
                        st.caption(
                            "%s at N (%s head, E=%.2f m): well-coagulated %.0f h, "
                            "EPS bloom %.0f h, no-algae baseline %.0f h" % (
                                names[dk], nmode.get("E_source", "?"),
                                nmode.get("E_m", 0.0),
                                sc.get("W", {}).get("run_h", 0.0),
                                sc.get("E", {}).get("run_h", 0.0),
                                nmode.get("baseline_run_h", 0.0)))
        except Exception:
            pass

    # Offer the most recently built report for download.
    if st.session_state.get("fc_last_pdf"):
        proj_slug = (st.session_state.get("project_name")
                     or project["plant"]).replace(" ", "_")
        fname = "%s_FilterComparator_%s.pdf" % (
            proj_slug, date.today().strftime("%Y%m%d"))
        st.download_button(
            "⬇ Download assessment report (PDF)",
            data=st.session_state["fc_last_pdf"],
            file_name=fname, mime="application/pdf",
            type="primary", use_container_width=True)
        info_box("The report covers filter design, solids holding capacity, "
                 "head budget, redundancy, backwash and washwater balance, "
                 "feed-deterioration sensitivity and a risk register.")

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    left, _ = st.columns([1, 3])
    with left:
        if st.button("← Back to Analysis Results", use_container_width=True):
            st.session_state["current_page"] = "results"
            st.rerun()
