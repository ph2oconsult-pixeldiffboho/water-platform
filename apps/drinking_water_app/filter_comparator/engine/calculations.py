"""filter_comparator.engine.calculations

Python port of lib/filterCalculations.js.

Core filter performance calculations:
  - Solids load (kg/d) into the filter from feed TSS and flow
  - Filter loading rate at N, N-1, N-2 (kg/m2/d)
  - Filter run length (h) derived from observed BW frequency
  - K (solids holding capacity, kg/m2/run) derived from run length and loading
  - K-multiplier from precipitate composition
"""

import math

from .physics import (
    total_bed_depth, total_filter_area, filtration_velocity,
    clean_bed_headloss, underdrain_headloss,
)
from .defaults import PRECIPITATE_MULTIPLIERS, SCENARIOS, pick_feed_scenario, pick_scenario_value

INF = float("inf")


# =========================================================================
# SOLIDS LOAD INTO FILTER
#   Mass into filter (kg/d) = feed TSS (mg/L) * flow (ML/d)
# =========================================================================
def solids_load_kg_per_day(feed_tss_mgL, flow_MLD):
    return feed_tss_mgL * flow_MLD


def solids_captured_kg_per_day(feed_tss_mgL, flow_MLD, filter_tss_removal_pct):
    return solids_load_kg_per_day(feed_tss_mgL, flow_MLD) * (filter_tss_removal_pct / 100)


# =========================================================================
# FILTER LOADING RATE BY REDUNDANCY CONDITION
# =========================================================================
def filter_loading_by_condition(feed_tss_mgL, flow_MLD, filter_tss_removal_pct, filt):
    N = filt["numFilters"]
    area_each = filt["areaPerFilter_m2"]
    captured = solids_captured_kg_per_day(feed_tss_mgL, flow_MLD, filter_tss_removal_pct)

    conditions = [
        {"key": "N", "filtersInService": N, "label": "N = %d (all in service)" % N},
        {"key": "N-1", "filtersInService": N - 1, "label": "N-1 = %d (1 offline)" % (N - 1)},
        {"key": "N-2", "filtersInService": N - 2, "label": "N-2 = %d (2 offline)" % (N - 2)},
    ]

    out = []
    for c in conditions:
        nis = c["filtersInService"]
        row = dict(c)
        row["areaInService_m2"] = nis * area_each if nis > 0 else 0
        row["loading_kg_per_m2_per_d"] = (captured / (nis * area_each)) if nis > 0 else INF
        row["flowPerFilter_MLd"] = (flow_MLD / nis) if nis > 0 else INF
        row["hydraulicLoading_m_per_h"] = (
            (flow_MLD * 1e6 / (24 * 3600 * 1000)) / (nis * area_each) * 3600
            if nis > 0 else INF
        )
        out.append(row)
    return out


# =========================================================================
# FILTER RUN LENGTH FROM OBSERVED BW VOLUMES
# =========================================================================
def derive_filter_run_length(total_bw_volume_MLd, volume_per_bw_m3, num_filters,
                             sequence_hr=34 / 60):
    total_m3_per_day = total_bw_volume_MLd * 1000
    bws_per_day_bank = total_m3_per_day / volume_per_bw_m3
    bws_per_filter_per_day = bws_per_day_bank / num_filters
    if bws_per_filter_per_day <= 0:
        return {"bws_per_day_bank": bws_per_day_bank,
                "bws_per_filter_per_day": bws_per_filter_per_day, "run_hours": INF}
    run_hours = 24 / bws_per_filter_per_day - sequence_hr
    return {"bws_per_day_bank": bws_per_day_bank,
            "bws_per_filter_per_day": bws_per_filter_per_day, "run_hours": run_hours}


# =========================================================================
# K (SOLIDS HOLDING CAPACITY) DERIVED FROM RUN LENGTH
# =========================================================================
def derive_k(loading_kg_per_m2_per_d, run_hours, media_layers):
    K_kg_per_m2 = loading_kg_per_m2_per_d * (run_hours / 24)
    L = total_bed_depth(media_layers)
    sigma_g_per_L = K_kg_per_m2 / L if L > 0 else 0
    return {"K_kg_per_m2": K_kg_per_m2, "sigma_g_per_L": sigma_g_per_L, "bedDepth_m": L}


# =========================================================================
# PRECIPITATE-WEIGHTED K MULTIPLIER
# =========================================================================
def effective_k_multiplier(composition):
    if not composition:
        return {"multiplier": 1.0, "normalised": None, "total": 0}
    total = sum((v or 0) for v in composition.values())
    if total <= 0:
        return {"multiplier": 1.0, "normalised": None, "total": 0}
    normalised = {}
    weighted = 0
    for key, fraction in composition.items():
        f_norm = (fraction or 0) / total
        normalised[key] = f_norm
        mult = PRECIPITATE_MULTIPLIERS.get(key, {}).get("multiplier", 1.0)
        weighted += f_norm * mult
    return {"multiplier": weighted, "normalised": normalised, "total": total}


# =========================================================================
# COMPLETE FILTER ASSESSMENT
# =========================================================================
def assess_filter(feed_tss_mgL, design_flow_MLD, filter_tss_removal_pct,
                  total_bw_volume_MLd, volume_per_bw_m3,
                  filt, precipitate,
                  drain_volume_m3=0, backwash_volume_m3=None, ftw_volume_m3=0,
                  net_loss_per_bw_m3=None,
                  drain_destination="waste", backwash_destination="waste",
                  ftw_destination="waste"):
    # Backwards compatibility: if components are missing, treat full
    # volumePerBW_m3 as backwash water to waste
    _drain = drain_volume_m3 or 0
    if backwash_volume_m3 is not None:
        _bw = backwash_volume_m3
    else:
        _bw = volume_per_bw_m3 - _drain - (ftw_volume_m3 or 0)
    _ftw = ftw_volume_m3 or 0
    _total_per_bw = _drain + _bw + _ftw
    if net_loss_per_bw_m3 is not None:
        _net_loss = net_loss_per_bw_m3
    else:
        _net_loss = (
            (_drain if drain_destination == "waste" else 0)
            + (_bw if backwash_destination == "waste" else 0)
            + (_ftw if ftw_destination == "waste" else 0)
        )

    captured = solids_captured_kg_per_day(feed_tss_mgL, design_flow_MLD, filter_tss_removal_pct)
    load_by_condition = filter_loading_by_condition(
        feed_tss_mgL, design_flow_MLD, filter_tss_removal_pct, filt)

    bw_seq = filt.get("bwSequence")
    if bw_seq:
        sequence_hr = (bw_seq["drainDown_min"] + bw_seq["backwashWater_min"]
                       + bw_seq["fillUp_min"] + bw_seq["filterToWaste_min"]
                       + bw_seq["returnToService_min"]) / 60
    else:
        sequence_hr = 34 / 60

    derived_run = derive_filter_run_length(
        total_bw_volume_MLd, _total_per_bw, filt["numFilters"], sequence_hr)
    bws_per_day_bank = derived_run["bws_per_day_bank"]
    bws_per_filter_per_day = derived_run["bws_per_filter_per_day"]
    run_hours = derived_run["run_hours"]

    # K_implied - derived from the user-supplied BW frequency.
    n_loading = next(c for c in load_by_condition if c["key"] == "N")["loading_kg_per_m2_per_d"]
    derived_k = derive_k(n_loading, run_hours, filt["mediaLayers"])
    K_observed = derived_k["K_kg_per_m2"]
    sigma_g_per_L = derived_k["sigma_g_per_L"]
    bed_depth_m = derived_k["bedDepth_m"]

    k_mult = effective_k_multiplier(precipitate)
    K_alum_equivalent = (K_observed / k_mult["multiplier"]
                         if k_mult["multiplier"] > 0 else K_observed)
    sigma_eff_g_per_L = (sigma_g_per_L / k_mult["multiplier"]
                         if k_mult["multiplier"] > 0 else sigma_g_per_L)

    # ---- Optional MANUAL RUN-TIME OVERRIDE ----
    run_hours_override_raw = filt.get("runHours_override_hr")
    run_hours_override = (run_hours_override_raw
                          if (run_hours_override_raw is not None
                              and math.isfinite(run_hours_override_raw)
                              and run_hours_override_raw > 0)
                          else None)
    K_operator = None
    sigma_operator_g_per_L = None
    sigma_operator_eff_g_per_L = None
    if run_hours_override is not None:
        derived = derive_k(n_loading, run_hours_override, filt["mediaLayers"])
        K_operator = derived["K_kg_per_m2"]
        sigma_operator_g_per_L = derived["sigma_g_per_L"]
        sigma_operator_eff_g_per_L = (
            sigma_operator_g_per_L / k_mult["multiplier"]
            if k_mult["multiplier"] > 0 else sigma_operator_g_per_L)

    # ---- DESIGN BASIS K - from the designer's stated run length at max TSS ----
    design_run_hours_raw = filt.get("designRunHours_at_maxTSS_hr")
    design_run_hours = (design_run_hours_raw
                        if (design_run_hours_raw is not None
                            and math.isfinite(design_run_hours_raw)
                            and design_run_hours_raw > 0)
                        else None)
    K_design = None
    sigma_design_g_per_L = None
    sigma_design_eff_g_per_L = None
    bws_per_filter_per_day_design = None
    total_bw_MLd_design = None
    if design_run_hours is not None:
        derived_design = derive_k(n_loading, design_run_hours, filt["mediaLayers"])
        K_design = derived_design["K_kg_per_m2"]
        sigma_design_g_per_L = derived_design["sigma_g_per_L"]
        sigma_design_eff_g_per_L = (
            sigma_design_g_per_L / k_mult["multiplier"]
            if k_mult["multiplier"] > 0 else sigma_design_g_per_L)
        cycle_hr_design = design_run_hours + sequence_hr
        bws_per_filter_per_day_design = 24 / cycle_hr_design
        total_bw_MLd_design = (
            bws_per_filter_per_day_design * filt["numFilters"] * _total_per_bw) / 1000

    # Daily water usage breakdown (bank-wide)
    daily_drain_m3 = _drain * bws_per_day_bank
    daily_backwash_m3 = _bw * bws_per_day_bank
    daily_ftw_m3 = _ftw * bws_per_day_bank
    daily_total_m3 = _total_per_bw * bws_per_day_bank
    daily_net_loss_m3 = _net_loss * bws_per_day_bank

    return {
        "capturedKgPerDay": captured,
        "totalLoad_kg_per_day": solids_load_kg_per_day(feed_tss_mgL, design_flow_MLD),
        "loadByCondition": load_by_condition,
        "bws_per_day_bank": bws_per_day_bank,
        "bws_per_filter_per_day": bws_per_filter_per_day,
        "run_hours": run_hours,
        "sequence_hr": sequence_hr,
        "K_kg_per_m2": K_observed,
        "K_alum_equivalent": K_alum_equivalent,
        "K_multiplier": k_mult["multiplier"],
        "precipitate_normalised": k_mult["normalised"],
        "sigma_g_per_L": sigma_g_per_L,
        "sigma_eff_g_per_L": sigma_eff_g_per_L,
        "bedDepth_m": bed_depth_m,
        "isMintsTienValid": sigma_g_per_L < 4.0,
        "runHours_override_hr": run_hours_override,
        "K_operator": K_operator,
        "sigma_operator_g_per_L": sigma_operator_g_per_L,
        "sigma_operator_eff_g_per_L": sigma_operator_eff_g_per_L,
        "designRunHours_at_maxTSS_hr": design_run_hours,
        "K_design": K_design,
        "sigma_design_g_per_L": sigma_design_g_per_L,
        "sigma_design_eff_g_per_L": sigma_design_eff_g_per_L,
        "bws_per_filter_per_day_design": bws_per_filter_per_day_design,
        "total_BW_MLd_design": total_bw_MLd_design,
        "bwVolumes": {
            "drainVolume_m3": _drain,
            "backwashVolume_m3": _bw,
            "ftwVolume_m3": _ftw,
            "totalPerBW_m3": _total_per_bw,
            "netLossPerBW_m3": _net_loss,
            "drainDestination": drain_destination,
            "backwashDestination": backwash_destination,
            "ftwDestination": ftw_destination,
            "daily_drain_m3": daily_drain_m3,
            "daily_backwash_m3": daily_backwash_m3,
            "daily_ftw_m3": daily_ftw_m3,
            "daily_total_m3": daily_total_m3,
            "daily_netLoss_m3": daily_net_loss_m3,
            "daily_netLoss_pct": ((daily_net_loss_m3 / (design_flow_MLD * 1000)) * 100
                                  if design_flow_MLD > 0 else 0),
        },
    }


# =========================================================================
# ENVELOPE ASSESSMENT - runs assessFilter once per scenario (min/avg/max)
# =========================================================================
def assess_filter_envelope(feed, flow_env, filt):
    out = {}
    for scen in SCENARIOS:
        feed_scen = pick_feed_scenario(feed, scen)
        flow = pick_scenario_value(flow_env["designFlow_MLD"], scen)
        result = assess_filter(
            feed_tss_mgL=feed_scen["feedTSS_mgL"],
            design_flow_MLD=flow,
            filter_tss_removal_pct=feed_scen["filterTSSRemoval_pct"],
            total_bw_volume_MLd=feed_scen["totalBWVolume_MLd"],
            volume_per_bw_m3=feed_scen["volumePerBW_m3"],
            drain_volume_m3=feed_scen["drainVolume_m3"],
            backwash_volume_m3=feed_scen["backwashVolume_m3"],
            ftw_volume_m3=feed_scen["ftwVolume_m3"],
            net_loss_per_bw_m3=feed_scen["netLossPerBW_m3"],
            drain_destination=feed_scen["drainDestination"],
            backwash_destination=feed_scen["backwashDestination"],
            ftw_destination=feed_scen["ftwDestination"],
            filt=filt,
            precipitate=feed_scen["precipitate"],
        )
        result["_scenarioFlow_MLD"] = flow
        result["_scenarioFeed"] = feed_scen
        out[scen] = result
    return out


# =========================================================================
# HEAD BUDGET CURVE
# =========================================================================
def head_budget_curve(filt, flow_MLD, k_multiplier=1.0, k_max_kgm2=8.0):
    bed_depth = total_bed_depth(filt["mediaLayers"])
    conditions = [
        {"key": "N", "nServ": filt["numFilters"], "label": "N"},
        {"key": "N-1", "nServ": filt["numFilters"] - 1, "label": "N-1"},
        {"key": "N-2", "nServ": filt["numFilters"] - 2, "label": "N-2"},
    ]

    # Sample K values densely for a smooth curve
    k_samples = []
    K = 0.0
    while K <= k_max_kgm2 + 1e-9:
        k_samples.append(round(K, 10))
        K += 0.1
    if k_samples[-1] < k_max_kgm2:
        k_samples.append(k_max_kgm2)

    series = []
    for c in conditions:
        if c["nServ"] <= 0:
            series.append({**c, "infeasible": True, "points": [],
                            "fixed_m": None, "v_mh": None})
            continue
        area = total_filter_area(c["nServ"], filt["areaPerFilter_m2"])
        v = filtration_velocity(flow_MLD, area)
        cb = clean_bed_headloss(
            filt["mediaLayers"], v, equation=filt["cleanBedEquation"],
            apply_uc_correction=filt.get("applyUCCorrection") is not False,
            temp_C=filt.get("temp_C", 10))
        ud_h = underdrain_headloss(filt["underdrain"], v)
        fixed = cb["total_m"] + ud_h + (filt.get("appurtenanceLoss_m") or 0)

        points = []
        for K in k_samples:
            sigma_obs = K / bed_depth
            sigma_eff = sigma_obs / (k_multiplier if k_multiplier > 0 else 1.0)
            d_hl_load = 0.92 * math.pow(max(0, sigma_eff), 2 / 3)
            points.append({"K": K, "sigma_obs": sigma_obs, "sigma_eff": sigma_eff,
                            "dHL_load": d_hl_load, "total": fixed + d_hl_load})

        series.append({**c, "infeasible": False, "fixed_m": fixed,
                        "cb_m": cb["total_m"], "ud_m": ud_h,
                        "v_mh": v * 3600, "points": points})

    return {"bedDepth": bed_depth, "series": series}


# =========================================================================
# PRAGMATIC K CAP (BREAKTHROUGH LIMIT)
# =========================================================================
K_PRAGMATIC_CAP = 6.0  # kg/m2/run


def max_k_at_head(filt, flow_MLD, driving_head_m, k_multiplier=1.0,
                  k_search_max=20, k_cap=K_PRAGMATIC_CAP):
    curve = head_budget_curve(filt, flow_MLD, k_multiplier, k_max_kgm2=k_search_max)
    out = []
    for s in curve["series"]:
        if s.get("infeasible"):
            out.append({**s, "K_max": None, "K_max_hydraulic": None, "K_capped": False})
            continue
        if s["fixed_m"] >= driving_head_m:
            out.append({**s, "K_max": 0, "K_max_hydraulic": 0,
                        "deficitAtZeroK": s["fixed_m"] - driving_head_m, "K_capped": False})
            continue
        # Bisection for K such that total = driving_head_m
        lo, hi = 0.0, float(k_search_max)
        bed_depth = total_bed_depth(filt["mediaLayers"])
        fixed = s["fixed_m"]
        for _ in range(60):
            mid = (lo + hi) / 2
            sigma_eff = (mid / bed_depth) / (k_multiplier if k_multiplier > 0 else 1.0)
            d_hl = 0.92 * math.pow(max(0, sigma_eff), 2 / 3)
            if fixed + d_hl < driving_head_m:
                lo = mid
            else:
                hi = mid
        k_max_hydraulic = (lo + hi) / 2
        k_max = (min(k_max_hydraulic, k_cap)
                 if (k_cap is not None and k_cap > 0) else k_max_hydraulic)
        out.append({**s, "K_max": k_max, "K_max_hydraulic": k_max_hydraulic,
                    "K_capped": k_max_hydraulic > k_max})
    return out
