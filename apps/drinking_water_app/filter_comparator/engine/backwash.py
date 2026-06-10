"""filter_comparator.engine.backwash

Python port of lib/backwashDynamics.js.

Backwash sequence physics:
  - Sequence durations: drain-down, BW, fill, FTW, return-to-service
  - Steady-state offline fraction per filter
  - Headloss development rate dHL/dt (two models)
  - 24-h timeline simulation: filter states, instantaneous loading
  - Plant capacity impact: water lost to BW & FTW, production deficit

Sequencing policy: ONE filter in any BW phase at any moment (bank-wide).
"""

import math

from .physics import (
    clean_bed_headloss, underdrain_headloss, filtration_velocity,
    v_to_m_per_hr, mints_tien_load,
)

INF = float("inf")

# =========================================================================
# SEQUENCE DEFAULTS (minutes) - editable per designer
# =========================================================================
DEFAULT_BW_SEQUENCE = {
    "drainDown_min": 5,
    "backwashWater_min": 8,
    "fillUp_min": 4,
    "filterToWaste_min": 15,
    "returnToService_min": 2,
}


def total_sequence_min(seq):
    return (seq["drainDown_min"] + seq["backwashWater_min"] + seq["fillUp_min"]
            + seq["filterToWaste_min"] + seq["returnToService_min"])


def offline_minutes_per_sequence(seq):
    return total_sequence_min(seq)


def sequence_water_consumption(seq, backwash_per_cycle_m3, filter_area_m2, post_bw_velocity_m_s):
    ftw_s = seq["filterToWaste_min"] * 60
    ftw_m3 = post_bw_velocity_m_s * filter_area_m2 * ftw_s
    return {
        "backwash_m3": backwash_per_cycle_m3,
        "FTW_m3": ftw_m3,
        "total_m3": backwash_per_cycle_m3 + ftw_m3,
    }


# =========================================================================
# STEADY-STATE OFFLINE FRACTION
# =========================================================================
def steady_state_offline_metrics(run_hours, seq, num_filters):
    t_seq_h = total_sequence_min(seq) / 60
    t_run_h = run_hours
    cycles_per_filter_per_day = 24 / (t_run_h + t_seq_h)
    bank_bw_hours_per_day = num_filters * cycles_per_filter_per_day * t_seq_h
    fraction_time_one_filter_offline = min(1.0, bank_bw_hours_per_day / 24)
    avg_filters_in_service = num_filters - fraction_time_one_filter_offline
    return {
        "sequenceMin": total_sequence_min(seq),
        "sequenceHr": t_seq_h,
        "runHours": t_run_h,
        "cyclesPerFilterPerDay": cycles_per_filter_per_day,
        "bankBWHoursPerDay": bank_bw_hours_per_day,
        "fractionTimeOneFilterOffline": fraction_time_one_filter_offline,
        "avgFiltersInService": avg_filters_in_service,
        "isSequencingFeasible": bank_bw_hours_per_day <= 24,
    }


# =========================================================================
# RATE OF HEADLOSS DEVELOPMENT (dHL/dt)
# =========================================================================
def dhl_dt_linear(d_h_clean_m, d_h_terminal_m, run_hours):
    if run_hours <= 0:
        return INF
    return (d_h_terminal_m - d_h_clean_m) / run_hours


def dhl_dt_mints_at_t(sigma_max_g_per_L, run_hours, t_hours):
    if run_hours <= 0 or t_hours <= 0:
        return INF
    sigma_t = sigma_max_g_per_L * (t_hours / run_hours)
    d_sigma_dt = sigma_max_g_per_L / run_hours
    return (2 / 3) * 0.92 * math.pow(max(sigma_t, 1e-6), -1 / 3) * d_sigma_dt


def headloss_development_rate(model, d_h_clean_m, d_h_terminal_m, run_hours, sigma_max_g_per_L):
    if model == "linear":
        rate = dhl_dt_linear(d_h_clean_m, d_h_terminal_m, run_hours)
        return {"model": model, "average_m_per_h": rate, "instantaneous_m_per_h": rate}
    if model == "mints":
        mid_t = run_hours / 2
        avg_rate = dhl_dt_mints_at_t(sigma_max_g_per_L, run_hours, mid_t)
        end_rate = dhl_dt_mints_at_t(sigma_max_g_per_L, run_hours, run_hours)
        return {"model": model, "average_m_per_h": avg_rate,
                "instantaneous_m_per_h": end_rate, "sigmaAtMidT": sigma_max_g_per_L / 2}
    raise ValueError("Unknown dHL/dt model: " + str(model))


# =========================================================================
# REDUNDANCY MATRIX (N, N-1, N-2 across design/peak/BW)
# =========================================================================
def redundancy_matrix(filt, design_flow_MLD, peak_flow_MLD,
                      sigma_eff_g_per_L=None, sigma_g_per_L=None, k_multiplier=None):
    # Accept either sigma_eff_g_per_L (preferred) or legacy sigma_g_per_L + K_multiplier.
    if sigma_eff_g_per_L is not None:
        sigma_eff = sigma_eff_g_per_L
    elif sigma_g_per_L is not None:
        sigma_eff = sigma_g_per_L / (k_multiplier or 1.0)
    else:
        sigma_eff = 0

    conditions = [
        {"key": "N", "filtersInService": filt["numFilters"],
         "label": "N = %d (all)" % filt["numFilters"]},
        {"key": "N-1", "filtersInService": filt["numFilters"] - 1,
         "label": "N-1 = %d (1 offline)" % (filt["numFilters"] - 1)},
        {"key": "N-2", "filtersInService": filt["numFilters"] - 2,
         "label": "N-2 = %d (2 offline)" % (filt["numFilters"] - 2)},
    ]
    scenarios = [
        {"key": "design", "flow": design_flow_MLD, "label": "Design flow", "duringBW": False},
        {"key": "peak", "flow": peak_flow_MLD, "label": "Peak flow", "duringBW": False},
        {"key": "bw", "flow": design_flow_MLD, "label": "Design + BW in progress",
         "duringBW": True},
    ]

    results = []
    for cond in conditions:
        for scen in scenarios:
            effective_n = (cond["filtersInService"] - 1
                           if scen["duringBW"] else cond["filtersInService"])
            if effective_n <= 0:
                results.append({
                    "condition": cond["key"], "conditionLabel": cond["label"],
                    "scenario": scen["key"], "scenarioLabel": scen["label"],
                    "filtersInService": effective_n, "pass": False, "infeasible": True,
                    "note": "Insufficient filters in service",
                })
                continue
            area_in_service = effective_n * filt["areaPerFilter_m2"]
            v_m_s = filtration_velocity(scen["flow"], area_in_service)
            v_m_h = v_to_m_per_hr(v_m_s)

            clean_bed = clean_bed_headloss(
                filt["mediaLayers"], v_m_s, equation=filt["cleanBedEquation"],
                apply_uc_correction=filt.get("applyUCCorrection") is not False,
                temp_C=filt.get("temp_C", 10))
            d_h_under = underdrain_headloss(filt["underdrain"], v_m_s)
            d_h_load = mints_tien_load(sigma_eff)
            d_h_app = filt.get("appurtenanceLoss_m")
            if d_h_app is None:
                d_h_app = 0.30
            d_h_total = clean_bed["total_m"] + d_h_under + d_h_load + d_h_app
            margin = filt["drivingHead_m"] - d_h_total

            results.append({
                "condition": cond["key"], "conditionLabel": cond["label"],
                "scenario": scen["key"], "scenarioLabel": scen["label"],
                "filtersInService": effective_n,
                "velocity_m_s": v_m_s, "velocity_m_h": v_m_h,
                "dH_clean_m": clean_bed["total_m"], "dH_clean_layers": clean_bed["layers"],
                "dH_underdrain_m": d_h_under,
                "dH_load_m": d_h_load,
                "dH_appurtenance_m": d_h_app,
                "dH_total_m": d_h_total,
                "drivingHead_m": filt["drivingHead_m"],
                "margin_m": margin,
                "sigma_eff_g_per_L": sigma_eff,
                "pass": margin >= 0,
                "infeasible": False,
            })
    return results


# =========================================================================
# 24-HOUR TIMELINE SIMULATION (single-BW policy)
# =========================================================================
def timeline_simulation(num_filters, run_hours, seq, step_min=5, duration_hr=24):
    t_seq_min = total_sequence_min(seq)
    t_run_min = run_hours * 60
    if t_run_min <= 0:
        return {"steps": [], "summary": {"error": "Run length non-positive"}}

    # Stagger initial run-end times so filters don't all backwash simultaneously
    filters = [
        {"id": i + 1, "state": "producing",
         "runEndsAt": ((i + 1) / num_filters) * t_run_min,
         "bwEndsAt": None, "bwPhase": None, "bwQueuedAt": None}
        for i in range(num_filters)
    ]

    steps = []
    total_min = duration_hr * 60
    bw_busy = False

    t = 0
    while t <= total_min:
        for f in filters:
            # If producing and run is complete - try to start BW
            if f["state"] == "producing" and t >= f["runEndsAt"]:
                if not bw_busy:
                    f["state"] = "bw"
                    f["bwPhase"] = "drainDown"
                    f["bwEndsAt"] = t + t_seq_min
                    bw_busy = True
                else:
                    f["state"] = "queued"
                    f["bwQueuedAt"] = t
            # If in BW and finished - return to service
            if f["state"] == "bw" and t >= f["bwEndsAt"]:
                f["state"] = "producing"
                f["bwPhase"] = None
                f["bwEndsAt"] = None
                f["runEndsAt"] = t + t_run_min
                bw_busy = False
                queued = next((q for q in filters if q["state"] == "queued"), None)
                if queued:
                    queued["state"] = "bw"
                    queued["bwPhase"] = "drainDown"
                    queued["bwEndsAt"] = t + t_seq_min
                    queued["bwQueuedAt"] = None
                    bw_busy = True

        producing = sum(1 for f in filters if f["state"] == "producing")
        in_bw = sum(1 for f in filters if f["state"] == "bw")
        queued_n = sum(1 for f in filters if f["state"] == "queued")
        steps.append({
            "t_min": t, "t_hr": t / 60,
            "filterStates": [{"id": f["id"], "state": f["state"]} for f in filters],
            "producing": producing, "inBW": in_bw, "queued": queued_n,
        })
        t += step_min

    min_with_bw = sum(1 for s in steps if s["inBW"] > 0) * step_min
    min_with_queue = sum(1 for s in steps if s["queued"] > 0) * step_min
    min_with_max = min(s["producing"] for s in steps)
    avg_producing = sum(s["producing"] for s in steps) / len(steps)
    completed_bws = sum(1 for f in filters if f["runEndsAt"] > t_run_min)

    return {
        "steps": steps,
        "summary": {
            "stepMin": step_min, "durationHr": duration_hr,
            "sequenceMin": t_seq_min,
            "runMin": t_run_min,
            "minWithBW": min_with_bw, "minWithQueue": min_with_queue,
            "minProducing": min_with_max,
            "avgProducingFilters": avg_producing,
            "bwScheduleFeasible": min_with_queue == 0,
            "completedBWs": completed_bws,
        },
    }


# =========================================================================
# PLANT CAPACITY IMPACT
# =========================================================================
def plant_capacity_impact(filt, design_flow_MLD, run_hours, seq, ss_metrics):
    n_bws_per_day = ss_metrics["cyclesPerFilterPerDay"] * filt["numFilters"]

    # Total per-cycle volume (drain + backwash + FTW) - already known
    bw_per_cycle = filt["backwashPerCycle_m3"]

    ftw_per_cycle = filt.get("ftwVolume_m3")
    # Velocity-based FTW estimate (display only)
    area_in_service = max(1, (filt["numFilters"] - 1) * filt["areaPerFilter_m2"])
    v_post_bw = filtration_velocity(design_flow_MLD, area_in_service)
    ftw_velocity_estimate = v_post_bw * filt["areaPerFilter_m2"] * (seq["filterToWaste_min"] * 60)
    ftw_per_cycle_val = ftw_per_cycle if ftw_per_cycle is not None else ftw_velocity_estimate

    total_lost_m3_per_day = n_bws_per_day * bw_per_cycle  # user-supplied total
    total_bw_m3_per_day = n_bws_per_day * max(0, bw_per_cycle - ftw_per_cycle_val)
    total_ftw_m3_per_day = n_bws_per_day * ftw_per_cycle_val
    total_lost_MLD = total_lost_m3_per_day / 1000

    design_m3_per_day = design_flow_MLD * 1000
    net_production_m3_per_day = design_m3_per_day - total_lost_m3_per_day
    net_production_MLD = net_production_m3_per_day / 1000
    capacity_deficit_pct = (
        (design_m3_per_day - net_production_m3_per_day) / design_m3_per_day) * 100

    return {
        "N_bws_per_day": n_bws_per_day,
        "bw_per_cycle_m3": bw_per_cycle,
        "FTW_per_cycle_m3": ftw_per_cycle_val,
        "total_BW_MLD": total_bw_m3_per_day / 1000,
        "total_FTW_MLD": total_ftw_m3_per_day / 1000,
        "total_lost_MLD": total_lost_MLD,
        "net_production_MLD": net_production_MLD,
        "capacity_deficit_pct": capacity_deficit_pct,
    }
