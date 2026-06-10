"""filter_comparator.engine.report_model

Python port of lib/reportBuilder.js.

Computes the full dual-mode assessment (coagulation + lime softening) used
by the PDF report. ``build_report_model`` is the top-level entry point: it
returns the complete assessment model (a nested dict) that the report
renders from.
"""

import math

from .physics import (
    clean_bed_headloss, underdrain_headloss, filtration_velocity,
    total_filter_area, total_bed_depth,
)
from .calculations import effective_k_multiplier
from .backwash import total_sequence_min
from .validation import validate_derived, worst_severity
from .algae import assess_algae, validate_algae_inputs

K_CAP = 6.0          # pragmatic breakthrough cap, kg/m2/run
REPORT_FLOW = 120    # ML/d, plant design flow
REPORT_TEMP_MIN = 15  # degC, minimum design water temperature (SEQ basis)
APPURT_DEFAULT = 0.15  # m, appurtenance headloss if not on the filter

# Designer-documented operating points for the two modes.
REPORT_MODES = {
    "coag": {
        "key": "coag",
        "label": "Coagulation (maximum turbidity)",
        "short": "Coagulation",
        "D1": {"tss": 10.9, "run": 44, "removal": 97, "precip": {"ferric": 1},
               "chem": "ferric coagulation"},
        "D2": {"tss": 9.98, "run": 24, "removal": 90, "precip": {"alum": 1},
               "chem": "alum coagulation"},
    },
    "soft": {
        "key": "soft",
        "label": "100% lime softening at pH 10",
        "short": "Lime softening",
        "D1": {"tss": 11.6, "run": 44, "removal": 97,
               "precip": {"caco3": 0.90, "mgoh2": 0.05, "other": 0.05},
               "chem": "lime softening"},
        "D2": {"tss": 42.4, "run": 16, "removal": 90,
               "precip": {"caco3": 0.90, "mgoh2": 0.05, "other": 0.05},
               "chem": "lime softening"},
    },
}

# Project descriptors that appear in the report prose. These are NOT
# calculation inputs — they are the named, project-specific facts the report
# states. Defaults reproduce the original assessment; supply a custom dict to
# build the same report for a different project.
REPORT_PROJECT = {
    "plant": "Wyaralong Water Treatment Plant",
    "temperature_basis": "South East Queensland",
    "algal_cells_ml": 200000,
}

# Per-design softening-route descriptions, operator-supplied. The report no
# longer hard-codes a causal chemistry narrative; instead it states the feed
# TSS difference as a fact and attributes the basis to these descriptions.
#   text       — a short phrase describing the design's softening route
#   mg_removal — True if the route includes a magnesium-removal step; gates the
#                Section 11 magnesium-hydroxide sensitivity subsection
REPORT_ROUTES = {
    "D1": {
        "text": ("a calcium-carbonate-dominant lime-softening route that does "
                 "not include a dedicated magnesium-removal step"),
        "mg_removal": False,
    },
    "D2": {
        "text": ("a lime-softening route that removes magnesium to meet the "
                 "hardness and CCPP goals, which generates additional "
                 "precipitate including magnesium hydroxide"),
        "mg_removal": True,
    },
}


def _kmult_of(precip):
    full = {"alum": 0, "ferric": 0, "caco3": 0, "mgoh2": 0, "other": 0}
    full.update(precip or {})
    return effective_k_multiplier(full)["multiplier"]


def _pore_fill_k(filt):
    """anthracite 7.0 kg/m3, sand 1.0 kg/m3 pore-fill capacity ratios."""
    anth = next((l for l in filt["mediaLayers"] if l["media"] == "anthracite"), None)
    sand = next((l for l in filt["mediaLayers"] if l["media"] == "sand"), None)
    return ((anth["depth"] * 7.0 if anth else 0)
            + (sand["depth"] * 1.0 if sand else 0))


def _appurt_of(filt):
    v = filt.get("appurtenanceLoss_m")
    return v if v is not None else APPURT_DEFAULT


def assess(filt, tss, removal, run_hours, kmult, flow=REPORT_FLOW):
    """Core assessment: a design at a feed TSS / removal / run length / chemistry."""
    area = total_filter_area(filt["numFilters"], filt["areaPerFilter_m2"])
    bed = total_bed_depth(filt["mediaLayers"])
    loading = (tss * flow * removal) / 100 / area     # kg/m2/d
    K = (loading * run_hours) / 24                     # kg/m2/run
    sigma_obs = K / bed                                # g/L
    sigma_eff = sigma_obs / (kmult or 1)
    v = filtration_velocity(flow, area)                # m/s
    cb = clean_bed_headloss(
        filt["mediaLayers"], v, equation=filt["cleanBedEquation"],
        apply_uc_correction=True, temp_C=REPORT_TEMP_MIN)["total_m"]
    ud = underdrain_headloss(filt["underdrain"], v)
    load = 0.92 * math.pow(max(0, sigma_eff), 2 / 3)
    appurt = _appurt_of(filt)
    total_dh = cb + ud + load + appurt
    head = filt["drivingHead_m"]
    return {
        "area": area, "bed": bed, "loading": loading, "K": K,
        "sigmaObs": sigma_obs, "sigmaEff": sigma_eff, "v_mh": v * 3600,
        "cb": cb, "ud": ud, "load": load, "appurt": appurt,
        "totalDH": total_dh, "head": head, "margin": head - total_dh,
        "feasible": head - total_dh >= 0, "runHours": run_hours,
        "tss": tss, "removal": removal,
        "poreFill": _pore_fill_k(filt),
    }


def head_limited_k(filt, kmult, flow=REPORT_FLOW):
    """Maximum K the head budget allows at the given flow."""
    area = total_filter_area(filt["numFilters"], filt["areaPerFilter_m2"])
    bed = total_bed_depth(filt["mediaLayers"])
    v = filtration_velocity(flow, area)
    cb = clean_bed_headloss(
        filt["mediaLayers"], v, equation=filt["cleanBedEquation"],
        apply_uc_correction=True, temp_C=REPORT_TEMP_MIN)["total_m"]
    ud = underdrain_headloss(filt["underdrain"], v)
    avail_load = filt["drivingHead_m"] - cb - ud - _appurt_of(filt)
    if avail_load <= 0:
        return 0
    sigma_eff = math.pow(avail_load / 0.92, 1.5)
    return sigma_eff * (kmult or 1) * bed


def backwash_daily(filt, feed, run_hours, flow=REPORT_FLOW):
    """Backwash water as ML/d and % of plant flow."""
    seq_h = total_sequence_min(filt["bwSequence"]) / 60 if filt.get("bwSequence") else 0
    bws_bank = (24 / (run_hours + seq_h)) * filt["numFilters"]
    per_cycle = (feed.get("drainVolume_m3") or 0) + (feed.get("backwashVolume_m3") or 0)
    ftw_per_cycle = feed.get("ftwVolume_m3") or 0
    daily = (bws_bank * per_cycle) / 1000
    ftw_daily = (bws_bank * ftw_per_cycle) / 1000
    return {
        "bwsBank": bws_bank, "perCycle": per_cycle, "daily": daily,
        "pctFlow": (daily / flow) * 100,
        "ftwPerCycle": ftw_per_cycle, "ftwDaily": ftw_daily,
        "ftwPctFlow": (ftw_daily / flow) * 100,
        "totalPerCycle": per_cycle + ftw_per_cycle,
        "totalDaily": daily + ftw_daily,
        "totalPctFlow": ((daily + ftw_daily) / flow) * 100,
    }


def cold_water_sensitivity(filt, flow=REPORT_FLOW):
    """Clean-bed headloss sensitivity to water temperature, evaluated at N and N-2."""
    appurt = _appurt_of(filt)

    def calc(in_service, T):
        if in_service <= 0:
            return {"v_mh": None, "cb": None, "ud": None, "headForLoad": None}
        area = in_service * filt["areaPerFilter_m2"]
        v = filtration_velocity(flow, area)
        cb = clean_bed_headloss(
            filt["mediaLayers"], v, equation=filt["cleanBedEquation"],
            apply_uc_correction=True, temp_C=T)["total_m"]
        ud = underdrain_headloss(filt["underdrain"], v)
        return {"v_mh": v * 3600, "cb": cb, "ud": ud,
                "headForLoad": filt["drivingHead_m"] - cb - ud - appurt}

    return [
        {"temp_C": T,
         "N": calc(filt["numFilters"], T),
         "N1": calc(filt["numFilters"] - 1, T),
         "N2": calc(filt["numFilters"] - 2, T)}
        for T in (15, 21, 28)
    ]


def redundancy(filt, flow=REPORT_FLOW):
    """Hydraulic headroom at N, N-1 and N-2 filters in service, at max design flow."""
    levels = [
        {"key": "N", "label": "N, all filters in service", "offline": 0},
        {"key": "N-1", "label": "N-1, one filter offline", "offline": 1},
        {"key": "N-2", "label": "N-2, one offline plus one in backwash", "offline": 2},
    ]
    out = []
    for lv in levels:
        in_service = filt["numFilters"] - lv["offline"]
        if in_service <= 0:
            out.append({**lv, "inService": in_service, "feasible": False,
                        "v_mh": None, "headForLoad": None})
            continue
        area = in_service * filt["areaPerFilter_m2"]
        v = filtration_velocity(flow, area)
        cb = clean_bed_headloss(
            filt["mediaLayers"], v, equation=filt["cleanBedEquation"],
            apply_uc_correction=True, temp_C=REPORT_TEMP_MIN)["total_m"]
        ud = underdrain_headloss(filt["underdrain"], v)
        appurt = _appurt_of(filt)
        head_for_load = filt["drivingHead_m"] - cb - ud - appurt
        out.append({**lv, "inService": in_service, "v_mh": v * 3600,
                    "cb": cb, "ud": ud, "appurt": appurt,
                    "headForLoad": head_for_load, "feasible": head_for_load > 0})
    return out


def sensitivity(filt, mode_design, kmult, flow=REPORT_FLOW):
    """Sensitivity: feed solids doubled."""
    tss2 = mode_design["tss"] * 2
    a_design = assess(filt, tss2, mode_design["removal"], mode_design["run"], kmult, flow)
    k_head = head_limited_k(filt, kmult, flow)
    k_ach = min(k_head, K_CAP)
    area = total_filter_area(filt["numFilters"], filt["areaPerFilter_m2"])
    loading2 = (tss2 * flow * mode_design["removal"]) / 100 / area
    run_at_cap = (k_ach / loading2) * 24
    run_ret = min(mode_design["run"], run_at_cap)
    a_ach = assess(filt, tss2, mode_design["removal"], run_ret, kmult, flow)
    bind = "head budget" if k_head < K_CAP else "breakthrough cap"
    if a_design["K"] <= k_ach:
        bind = "none, run length retained"
    return {
        "tss2": tss2, "kReq": a_design["K"], "kHead": k_head, "kAch": k_ach,
        "runRet": run_ret, "runDesign": mode_design["run"],
        "margin": a_ach["margin"], "feasible": a_ach["feasible"], "bind": bind,
    }


def build_report_model(filter_d1, filter_d2, feed_d1, feed_d2,
                        name_d1=None, name_d2=None, prepared_by=None,
                        modes=None, flow=None, project=None, routes=None):
    """Build the complete dual-mode assessment object the PDF renderer consumes.

    This is the top-level entry point (buildReportModel equivalent). It
    returns the complete assessment model as a nested dict.

    Parameters
    ----------
    filter_d1, filter_d2 : dict
        Filter geometry dicts (see DESIGNER_DEFAULTS[...]['filter']).
    feed_d1, feed_d2 : dict
        Feed condition dicts carrying the BW volume components
        (drainVolume_m3, backwashVolume_m3, ftwVolume_m3 ...).
    name_d1, name_d2 : str, optional
        Designer display names for D1 / D2. Default "Designer 1"/"Designer 2".
    prepared_by : str, optional
        "Prepared by" attribution for the report cover.
    modes : dict, optional
        Operating-point definitions for the two modes (``coag`` and ``soft``),
        each carrying D1/D2 entries with ``tss``, ``run``, ``removal``,
        ``precip`` and ``chem``. Defaults to ``REPORT_MODES``; supply a custom
        dict to assess operating points other than the built-in defaults.
    flow : float, optional
        Plant design flow (ML/d) the assessment is governed by. Defaults to
        ``REPORT_FLOW``.
    project : dict, optional
        Project descriptors that appear in the report prose — ``plant``,
        ``temperature_basis``, ``algal_cells_ml``. Defaults to
        ``REPORT_PROJECT``. Supply a custom dict so the report prose is
        truthful for a project other than the built-in default.
    routes : dict, optional
        Per-design softening-route descriptions (``D1``/``D2``), each a dict
        with ``text`` (a short phrase) and ``mg_removal`` (bool). Defaults to
        ``REPORT_ROUTES``. The report attributes the feed-TSS basis to these
        descriptions rather than asserting a fixed chemistry narrative;
        ``mg_removal`` gates the Section 11 magnesium-hydroxide subsection.

    Notes
    -----
    Called with no optional arguments the result is identical, value for
    value, to the built-in default assessment.
    """
    if modes is None:
        modes = REPORT_MODES
    if flow is None:
        flow = REPORT_FLOW
    if project is None:
        project = REPORT_PROJECT
    if routes is None:
        routes = REPORT_ROUTES
    d1 = name_d1.strip() if (name_d1 and name_d1.strip()) else "Designer 1"
    d2 = name_d2.strip() if (name_d2 and name_d2.strip()) else "Designer 2"
    filters = {"D1": filter_d1, "D2": filter_d2}
    feeds = {"D1": feed_d1, "D2": feed_d2}

    modes_out = {}
    for mk in ("coag", "soft"):
        m = modes[mk]
        out = {"key": mk, "label": m["label"], "short": m["short"]}
        for dk in ("D1", "D2"):
            md = m[dk]
            kmult = _kmult_of(md["precip"])
            a = assess(filters[dk], md["tss"], md["removal"], md["run"], kmult, flow)
            bw = backwash_daily(filters[dk], feeds[dk], md["run"], flow)
            sens = sensitivity(filters[dk], md, kmult, flow)
            out[dk] = {**a, "kmult": kmult, "chem": md["chem"],
                       "bw": bw, "sens": sens, "modeDesign": md}
        modes_out[mk] = out

    # Like-for-like at a common feed, per chemistry
    lfl = {}
    for mk in ("coag", "soft"):
        m = modes[mk]
        lfl[mk] = {
            "D1": assess(filter_d1, 20, 95, 24, _kmult_of(m["D1"]["precip"]), flow),
            "D2": assess(filter_d2, 20, 95, 24, _kmult_of(m["D2"]["precip"]), flow),
        }

    # D2 lime-softening utilisation opportunity.
    def _opp_d2():
        soft = modes["soft"]["D2"]
        kmult = _kmult_of(soft["precip"])
        area = total_filter_area(filter_d2["numFilters"], filter_d2["areaPerFilter_m2"])
        removal = soft["removal"]

        def point(tss, target_k, run_override=None):
            loading = (tss * flow * removal) / 100 / area
            run = run_override if run_override is not None else (target_k / loading) * 24
            a = assess(filter_d2, tss, removal, run, kmult, flow)
            bw = backwash_daily(filter_d2, feed_d2, run, flow)
            return {"tss": tss, "K": a["K"], "run": run, "margin": a["margin"],
                    "bwPct": bw["pctFlow"], "bwDaily": bw["daily"]}

        as_built = point(soft["tss"], None, soft["run"])
        run_to_cap = point(soft["tss"], K_CAP)
        half_tss = soft["tss"] * 0.5
        turb_cut = point(half_tss, as_built["K"])
        turb_cut_cap = point(half_tss, K_CAP)
        return {
            "asBuilt": as_built, "runToCap": run_to_cap,
            "turbCut": turb_cut, "turbCutCap": turb_cut_cap,
            "poreFill": _pore_fill_k(filter_d2),
            "capPctOfCeiling": (K_CAP / _pore_fill_k(filter_d2)) * 100,
            "asBuiltPctOfCeiling": (as_built["K"] / _pore_fill_k(filter_d2)) * 100,
            "bwSaveRunToCap": as_built["bwDaily"] - run_to_cap["bwDaily"],
            "bwSaveFull": as_built["bwDaily"] - turb_cut_cap["bwDaily"],
        }

    opp_d2 = _opp_d2()

    # D2 lime-softening removal-efficiency opportunity.
    def _removal_opp_d2():
        soft = modes["soft"]["D2"]
        kmult = _kmult_of(soft["precip"])

        def point(removal):
            a = assess(filter_d2, soft["tss"], removal, soft["run"], kmult, flow)
            return {
                "removal": removal,
                "capturedTSS": (soft["tss"] * removal) / 100,
                "filtrateTSS": soft["tss"] * (1 - removal / 100),
                "K": a["K"], "load": a["load"], "totalDH": a["totalDH"],
                "margin": a["margin"], "runHours": soft["run"], "feasible": a["feasible"],
            }

        pts = [point(r) for r in (90, 95, 98)]
        return {
            "asBuiltRemoval": soft["removal"], "feedTSS": soft["tss"],
            "poreFill": _pore_fill_k(filter_d2),
            "points": pts,
            "filtrateGain": pts[0]["filtrateTSS"] / pts[2]["filtrateTSS"],
            "marginCost": pts[0]["margin"] - pts[2]["margin"],
            "kRise": pts[2]["K"] - pts[0]["K"],
        }

    removal_opp_d2 = _removal_opp_d2()

    # Mg(OH)2 floc sensitivity for the D2 lime-softening duty.
    def _mg_floc_sens_d2():
        soft = modes["soft"]["D2"]
        other = 0.05

        def point(mg_frac):
            caco3 = max(0, 1 - mg_frac - other)
            precip = {"caco3": caco3, "mgoh2": mg_frac, "other": other}
            kmult = _kmult_of(precip)
            a = assess(filter_d2, soft["tss"], soft["removal"], soft["run"], kmult, flow)
            return {"mgFrac": mg_frac, "kmult": kmult, "load": a["load"],
                    "totalDH": a["totalDH"], "margin": a["margin"],
                    "K": a["K"], "feasible": a["feasible"]}

        pts = [point(mf) for mf in (0, 0.15, 0.30, 0.45)]
        return {
            "asBuiltMgFrac": soft["precip"].get("mgoh2", 0),
            "asBuiltKmult": _kmult_of(soft["precip"]),
            "points": pts,
            "marginSwing": pts[0]["margin"] - pts[-1]["margin"],
        }

    mg_floc_sens_d2 = _mg_floc_sens_d2()

    # Sanity-check every derived operating point against physical limits.
    issues = []
    for mk in ("coag", "soft"):
        for dk in ("D1", "D2"):
            r = modes_out[mk][dk]
            issues.extend(validate_derived(
                velocity_mh=r["v_mh"], K=r["K"], pore_fill_k=_pore_fill_k(filters[dk]),
                label="%s %s" % (dk, modes[mk]["short"].lower())))

    # Algae-driven clogging block per design. Inputs come from the feed dict;
    # the available clogging head defaults to the calculated budget but may be a
    # manual value, a per-mode dict, or a profile-derived value (see algae.py).
    def _algae_for(filt, feed, label):
        cells = feed.get("residualAlgae_cells_per_mL")
        if cells is None:
            # No residual supplied: assume ~90% clarifier removal of the
            # project's raw algal count as a default residual basis.
            cells = (project.get("algal_cells_ml") or 0) * 0.10
        pg = feed.get("massPerCell_pg", 100)
        mineral = feed.get("mineralBackground_mgL", 8)
        issues.extend(validate_algae_inputs(cells, pg, mineral, label=label))
        res = assess_algae(
            filt, flow, cells, mineral_mgL=mineral, pg_per_cell=pg,
            available_head=feed.get("availableHead_m"),
            driving_head_m=feed.get("drivingHeadOverride_m"),
            head_source=feed.get("headSource"))
        res["highlightScenario"] = feed.get("morphologyScenario")
        res["densadegRecycle"] = bool(feed.get("densadegRecycle"))
        return res

    algae = {"D1": _algae_for(filter_d1, feed_d1, d1),
             "D2": _algae_for(filter_d2, feed_d2, d2)}

    return {
        "names": {"d1": d1, "d2": d2},
        "preparedBy": prepared_by.strip() if (prepared_by and prepared_by.strip()) else None,
        "filters": {"D1": filter_d1, "D2": filter_d2},
        "poreFill": {"D1": _pore_fill_k(filter_d1), "D2": _pore_fill_k(filter_d2)},
        "modes": modes_out, "lfl": lfl,
        "opportunityD2": opp_d2,
        "removalOpportunityD2": removal_opp_d2,
        "mgFlocSensitivityD2": mg_floc_sens_d2,
        "tempMin": REPORT_TEMP_MIN,
        "algae": algae,
        "redundancy": {
            "D1": redundancy(filter_d1, flow),
            "D2": redundancy(filter_d2, flow),
        },
        "coldWater": {
            "D1": cold_water_sensitivity(filter_d1, flow),
            "D2": cold_water_sensitivity(filter_d2, flow),
        },
        "flow": flow, "kCap": K_CAP,
        "project": project,
        "routes": routes,
        "validation": {"issues": issues, "severity": worst_severity(issues)},
    }
