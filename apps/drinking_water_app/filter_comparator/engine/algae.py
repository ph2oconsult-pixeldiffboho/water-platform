"""filter_comparator.engine.algae

Forward algae clogging model for the Filter Performance Comparator.

The rest of the engine derives solids-holding capacity K by back-calculating
from an observed backwash frequency. It has no forward run-length from an
algae-driven headloss rate, and treats residual solids as inert mass. This
module supplies that missing piece: given the residual algae load and its
morphology, it routes the mass into specific cake resistance, compressibility
and surface blinding, accumulates headloss dH/dt, and returns the time for the
filter to reach its available clogging head.

Mass is conserved. Algae are never inflated to an "effective mg/L"; morphology
enters only through (alpha, s, eta, w*, B_max). Resistances are RGF-scale
effective values calibrated for a coarse granular bed, not membrane/dewatering
cakes. Outputs are RISK-SCREENING run times (about +/-30%), not predictions.

Pure standard library plus the engine's own water-property functions.
"""

import math

from .physics import water_dynamic_viscosity, water_density

G = 9.81

# =========================================================================
# CALIBRATION PARAMETERS  (anchor to bench CST/SRF, particle counts, column)
# Stream order: mineral, bound (algae in floc), free cells, EPS / mucilage
#   ad  = alpha_depth        [m/kg]   low depth-filtration resistance
#   ac0 = alpha_cake0 @dPref [m/kg]   cake resistance at dP_ref
#   s   = compressibility index       alpha_cake = ac0 * (dP/dP_ref)^s
#   eta = capture efficiency          fraction of arriving mass retained
#   ws  = w_star [kg/m2]               blinding scale (small = blinds early)
#   bm  = B_max                        max blinding fraction
# =========================================================================
MATERIALS = [
    {"key": "mineral", "ad": 1.5e9, "ac0": 5.0e9,  "s": 0.20, "eta": 0.95, "ws": 5.0,  "bm": 0.10},
    {"key": "bound",   "ad": 3.0e9, "ac0": 1.5e10, "s": 0.40, "eta": 0.95, "ws": 1.0,  "bm": 0.60},
    {"key": "free",    "ad": 6.0e9, "ac0": 6.0e10, "s": 0.60, "eta": 0.60, "ws": 0.4,  "bm": 0.60},
    {"key": "eps",     "ad": 2.0e10,"ac0": 4.0e11, "s": 0.85, "eta": 0.95, "ws": 0.15, "bm": 0.95},
]

# Scenario partitions: fraction of the ALGAE mass that is bound / free / EPS.
# (Mineral is the separate background solids load, not part of this split.)
PARTITIONS = {
    "A": {"label": "Predominantly mineral floc",      "fb": 0.70, "ff": 0.25, "fe": 0.05},
    "B": {"label": "Mixed algae",                     "fb": 0.50, "ff": 0.35, "fe": 0.15},
    "C": {"label": "Colonial",                        "fb": 0.45, "ff": 0.35, "fe": 0.20},
    "D": {"label": "Filamentous",                     "fb": 0.30, "ff": 0.45, "fe": 0.25},
    "E": {"label": "EPS-rich cyanobacterial bloom",   "fb": 0.15, "ff": 0.35, "fe": 0.50},
    "W": {"label": "Well-coagulated bloom",           "fb": 0.80, "ff": 0.15, "fe": 0.05},
}

T_REF_H_DEFAULT = 24.0
DP_REF_PA_DEFAULT = 9800.0
PG_PER_CELL_DEFAULT = 100.0
NEWTON_ITERS = 40

NA_BANDS = (
    (0.1, "negligible"),
    (0.5, "moderate"),
    (1.0, "significant"),
    (float("inf"), "algae-dominated"),
)


def na_band(n_a):
    for ceiling, label in NA_BANDS:
        if n_a < ceiling:
            return label
    return "algae-dominated"


def _stream_concentrations(conc_cells_per_mL, partition, mineral_mgL, pg_per_cell):
    """Return [C_mineral, C_bound, C_free, C_eps] in mg/L (mass conserved)."""
    c_algae = conc_cells_per_mL * pg_per_cell * 1e-6
    return [
        mineral_mgL,
        c_algae * partition["fb"],
        c_algae * partition["ff"],
        c_algae * partition["fe"],
    ]


def _rates(concs, J_mh):
    """Areal deposit rate per stream [kg/m2/h] = C * eta * J * 1e-3."""
    return [c * m["eta"] * J_mh * 1e-3 for c, m in zip(concs, MATERIALS)]


def _alpha_cake_op(E_m, dP_ref, mu, rho):
    dP_op = rho * G * E_m
    return [m["ac0"] * (dP_op / dP_ref) ** m["s"] for m in MATERIALS]


def _hdep(t, rates, ac_op, murhog, J_s):
    """Closed-form deposit headloss at time t (m), integral of dH/dt."""
    total = 0.0
    for r, m, ac in zip(rates, MATERIALS, ac_op):
        if r <= 0:
            continue
        W = r * t
        total += m["ad"] * W + (ac - m["ad"]) * m["bm"] * (
            W - m["ws"] + m["ws"] * math.exp(-W / m["ws"]))
    return murhog * J_s * total


def _hprime(t, rates, ac_op, murhog, J_s):
    """Instantaneous dH/dt at time t (m/h)."""
    total = 0.0
    for r, m, ac in zip(rates, MATERIALS, ac_op):
        if r <= 0:
            continue
        a_eff = m["ad"] + (ac - m["ad"]) * m["bm"] * (1 - math.exp(-(r * t) / m["ws"]))
        total += a_eff * r
    return murhog * J_s * total


def _hprime_instant(rates, ac_op, murhog, J_s):
    """dH/dt with full blinding (B = B_max) from t = 0."""
    total = 0.0
    for r, m, ac in zip(rates, MATERIALS, ac_op):
        if r <= 0:
            continue
        total += (m["ad"] + (ac - m["ad"]) * m["bm"]) * r
    return murhog * J_s * total


def run_time(J_mh, E_m, conc_cells_per_mL, partition,
             mineral_mgL=8.0, pg_per_cell=PG_PER_CELL_DEFAULT,
             temp_C=20.0, mu=None, rho=None,
             t_ref_h=T_REF_H_DEFAULT, dP_ref=DP_REF_PA_DEFAULT):
    """Risk-screening run time (h) and the instant-blinding stress case (h).

    J_mh           filtration rate, m/h
    E_m            available clogging head (deposit budget), m
    partition      a PARTITIONS entry (dict with fb, ff, fe)
    Returns dict: run_h, instant_h, N_A, na_band, dHdt0_m_per_h.
    """
    if mu is None:
        mu = water_dynamic_viscosity(temp_C)
    if rho is None:
        rho = water_density(temp_C)
    murhog = mu / (rho * G)
    J_s = J_mh / 3600.0

    concs = _stream_concentrations(conc_cells_per_mL, partition, mineral_mgL, pg_per_cell)
    rates = _rates(concs, J_mh)
    ac_op = _alpha_cake_op(E_m, dP_ref, mu, rho)

    hp_inst = _hprime_instant(rates, ac_op, murhog, J_s)
    if hp_inst <= 0:
        return {"run_h": float("inf"), "instant_h": float("inf"),
                "N_A": 0.0, "na_band": "negligible", "dHdt0_m_per_h": 0.0}

    instant_h = E_m / hp_inst

    # Newton on H_dep(t) = E, starting from the instant-blinding time (a lower bound)
    t = instant_h
    for _ in range(NEWTON_ITERS):
        hp = _hprime(t, rates, ac_op, murhog, J_s)
        if hp <= 0:
            break
        t = max(0.05, t - (_hdep(t, rates, ac_op, murhog, J_s) - E_m) / hp)
    run_h = t

    # Algae Clogging Number (cake-potential hazard index, ranking only)
    n_a = murhog * J_s * sum(ac * r for ac, r in zip(ac_op, rates)) * t_ref_h / E_m
    dhdt0 = _hprime(1e-6, rates, ac_op, murhog, J_s)

    return {"run_h": run_h, "instant_h": instant_h, "N_A": n_a,
            "na_band": na_band(n_a), "dHdt0_m_per_h": dhdt0}


# =========================================================================
# HOST-FACING ASSESSMENT
# The available clogging head E can come from any of three sources, kept
# generic so the model never assumes one:
#   1. calculated - derived from the comparator's filter dict and physics
#                   (E = driving head - clean bed - underdrain - appurtenance)
#   2. manual     - a single value, or a per-mode dict, supplied by the caller
#   3. profile    - the host parses an uploaded hydraulic profile into a
#                   per-mode value (dict) or a callable and passes it in
# run_time() itself only ever takes J and E, so it is already source-agnostic;
# this wrapper resolves E before calling it.
# =========================================================================
def _mode_budget(filt, flow_MLD, n_in_service, appurt_m, driving_head_m=None):
    """Velocity and the *calculated* head budget for one redundancy mode."""
    from .physics import (filtration_velocity, total_filter_area,
                          clean_bed_headloss, underdrain_headloss)
    if n_in_service <= 0:
        return None
    area = total_filter_area(n_in_service, filt["areaPerFilter_m2"])
    v = filtration_velocity(flow_MLD, area)
    J_mh = v * 3600.0
    cb = clean_bed_headloss(
        filt["mediaLayers"], v, equation=filt.get("cleanBedEquation", "kozeny-carman"),
        apply_uc_correction=filt.get("applyUCCorrection") is not False,
        temp_C=filt.get("temp_C", 10))
    ud = underdrain_headloss(filt["underdrain"], v)
    dh = driving_head_m if driving_head_m is not None else filt["drivingHead_m"]
    E_calc = dh - cb["total_m"] - ud - appurt_m
    return {"J_mh": J_mh, "driving_head_m": dh, "cleanbed_m": cb["total_m"],
            "underdrain_m": ud, "appurt_m": appurt_m, "E_calculated_m": E_calc}


def resolve_available_head(available_head, mode, J_mh, calc_budget):
    """Resolve the available clogging head E (m) and a source label.

    available_head may be:
      None                       use the calculated head budget
      a number                   manual, same E for every mode
      a dict {mode: E}           manual per mode; a missing/None mode falls
                                 back to the calculated budget
      a callable(mode,J,calc)    custom / profile-derived; returns E in m
    Returns (E_m, source_label).
    """
    if available_head is None:
        return calc_budget["E_calculated_m"], "calculated"
    if callable(available_head):
        return float(available_head(mode, J_mh, calc_budget)), "profile"
    if isinstance(available_head, dict):
        val = available_head.get(mode)
        if val is not None:
            return float(val), "manual"
        return calc_budget["E_calculated_m"], "calculated (fallback)"
    return float(available_head), "manual"


def assess_algae(filt, flow_MLD, residual_cells_per_mL,
                 mineral_mgL=8.0, pg_per_cell=PG_PER_CELL_DEFAULT,
                 scenarios=("W", "A", "B", "C", "D", "E"),
                 appurt_m=0.15, t_ref_h=T_REF_H_DEFAULT, dP_ref=DP_REF_PA_DEFAULT,
                 available_head=None, driving_head_m=None, head_source=None):
    """Full algae block for one design (filter dict), across N / N-1 / N-2.

    available_head  None -> calculated; number -> manual (all modes);
                    {mode: E} -> manual per mode; callable(mode,J,calc) ->
                    profile/custom. run_time only sees the resolved J and E.
    driving_head_m  optional override of filt['drivingHead_m'] on the
                    calculated path (e.g. to test 2.8 vs 3.87 m).
    head_source     optional label for the output (e.g. 'profile') when the
                    caller knows the provenance (such as a parsed profile dict).

    Each mode reports E_m, E_source and the calculated head_budget breakdown
    (always included, so a manual or profile E can be compared to the computed
    one).
    """
    n = filt["numFilters"]
    temp_C = filt.get("temp_C", 10)
    modes = [("N", n), ("N-1", n - 1), ("N-2", n - 2)]
    inferred = ("calculated" if available_head is None
                else "profile" if callable(available_head) else "manual")
    out = {"modes": {}, "meta": {
        "residual_cells_per_mL": residual_cells_per_mL,
        "mineral_mgL": mineral_mgL, "pg_per_cell": pg_per_cell, "temp_C": temp_C,
        "C_algae_mgL": residual_cells_per_mL * pg_per_cell * 1e-6,
        "head_source": head_source or inferred,
        "driving_head_override_m": driving_head_m,
    }}
    for key, n_serv in modes:
        calc = _mode_budget(filt, flow_MLD, n_serv, appurt_m, driving_head_m)
        if calc is None:
            out["modes"][key] = {"infeasible": True, "J_mh": None, "E_m": None,
                                 "E_source": None, "head_budget": None,
                                 "scenarios": {}, "baseline_run_h": None}
            continue
        J_mh = calc["J_mh"]
        E_m, src = resolve_available_head(available_head, key, J_mh, calc)
        if head_source:
            src = head_source
        if E_m is None or E_m <= 0:
            out["modes"][key] = {"infeasible": True, "J_mh": J_mh, "E_m": E_m,
                                 "E_source": src, "head_budget": calc,
                                 "scenarios": {}, "baseline_run_h": None}
            continue
        base = run_time(J_mh, E_m, 0.0, PARTITIONS["A"], mineral_mgL=mineral_mgL,
                        pg_per_cell=pg_per_cell, temp_C=temp_C, t_ref_h=t_ref_h, dP_ref=dP_ref)
        scen_out = {}
        for sk in scenarios:
            r = run_time(J_mh, E_m, residual_cells_per_mL, PARTITIONS[sk],
                         mineral_mgL=mineral_mgL, pg_per_cell=pg_per_cell, temp_C=temp_C,
                         t_ref_h=t_ref_h, dP_ref=dP_ref)
            r["label"] = PARTITIONS[sk]["label"]
            scen_out[sk] = r
        out["modes"][key] = {"infeasible": False, "J_mh": J_mh, "E_m": E_m,
                             "E_source": src, "head_budget": calc,
                             "baseline_run_h": base["run_h"], "scenarios": scen_out}
    return out


def validate_algae_inputs(cells_per_mL, pg_per_cell=PG_PER_CELL_DEFAULT,
                          mineral_mgL=8.0, label=""):
    """Range-check algae inputs. Returns a list of issue dicts
    {field, severity, message}; empty if all within bounds."""
    issues = []
    pre = (label + ": ") if label else ""
    if cells_per_mL is None or cells_per_mL < 0 or cells_per_mL > 2.0e6:
        issues.append({"field": "residualAlgae_cells_per_mL", "severity": "warn",
                       "message": pre + "residual algae outside 0 to 2,000,000 cells/mL"})
    if pg_per_cell is None or pg_per_cell < 10 or pg_per_cell > 1000:
        issues.append({"field": "massPerCell_pg", "severity": "warn",
                       "message": pre + "mass per cell outside 10 to 1000 pg"})
    if mineral_mgL is None or mineral_mgL < 0 or mineral_mgL > 50:
        issues.append({"field": "mineralBackground_mgL", "severity": "warn",
                       "message": pre + "mineral background outside 0 to 50 mg/L"})
    return issues
