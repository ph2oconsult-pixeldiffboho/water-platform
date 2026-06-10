"""filter_comparator.engine.validation

Python port of lib/validation.js.

Sanity-check layer. A decision-support tool must not silently propagate an
implausible input into a physically impossible result. These checks flag
out-of-range inputs and physically impossible derived values so they are
never presented as merely "high" or "upper end".
"""

import math

PHYSICAL_BOUNDS = {
    "flow_MLD_min": 0.5,
    "flow_MLD_max": 600,
    "velocity_mh_typicalMax": 25,
    "velocity_mh_physicalMax": 40,
    "K_typicalMax": 6,
    "K_physicalMax": 15,
}


def _issue(severity, code, message):
    """severity 'error' = result not usable; 'warning' = plausible but verify."""
    return {"severity": severity, "code": code, "message": message}


def _is_finite_number(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def validate_flow_envelope(design_flow_MLD):
    """Validate a {min, avg, max} design-flow envelope."""
    out = []
    f = design_flow_MLD or {}
    min_, avg, max_ = f.get("min"), f.get("avg"), f.get("max")
    named = [("minimum", min_), ("average", avg), ("maximum", max_)]
    for k, v in named:
        if v is None or not _is_finite_number(v) or v <= 0:
            out.append(_issue("error", "flow-nonpositive",
                               "Design flow (%s) is not a valid positive number." % k))
        elif v > PHYSICAL_BOUNDS["flow_MLD_max"]:
            out.append(_issue("error", "flow-implausible",
                               "Design flow (%s) is %s ML/d, far outside the plausible "
                               "range for a filter plant. Check for an input error."
                               % (k, format(round(v), ","))))
        elif v < PHYSICAL_BOUNDS["flow_MLD_min"]:
            out.append(_issue("error", "flow-implausible",
                               "Design flow (%s) is %s ML/d, implausibly low for a "
                               "filter plant." % (k, v)))
    if all(v is not None and _is_finite_number(v) and v > 0 for _, v in named):
        if not (min_ <= avg <= max_):
            out.append(_issue("error", "flow-order",
                               "Flow envelope is inconsistent: average (%s ML/d) must sit "
                               "between minimum (%s) and maximum (%s)." % (avg, min_, max_)))
    return out


def validate_derived(velocity_mh=None, K=None, pore_fill_k=None, label=""):
    """Validate derived hydraulic quantities against physical limits."""
    out = []
    tag = ("%s: " % label) if label else ""
    if velocity_mh is not None and _is_finite_number(velocity_mh):
        if velocity_mh > PHYSICAL_BOUNDS["velocity_mh_physicalMax"]:
            out.append(_issue("error", "velocity-impossible",
                               "%sfiltration velocity %s m/h is physically impossible for "
                               "granular-media filtration. This indicates an input error, "
                               "most likely the design flow." % (tag, format(velocity_mh, ".0f"))))
        elif velocity_mh > PHYSICAL_BOUNDS["velocity_mh_typicalMax"]:
            out.append(_issue("warning", "velocity-high",
                               "%sfiltration velocity %s m/h is above typical high-rate "
                               "practice. Verify the design flow and filter area."
                               % (tag, format(velocity_mh, ".1f"))))
    if K is not None and _is_finite_number(K):
        if K > PHYSICAL_BOUNDS["K_physicalMax"]:
            out.append(_issue("error", "K-impossible",
                               "%ssolids holding capacity K = %s kg/m2/run is physically "
                               "impossible for granular media. It far exceeds the available "
                               "pore volume and indicates an input error, not a high-loading "
                               "design." % (tag, format(K, ".0f"))))
        elif pore_fill_k is not None and K > pore_fill_k:
            out.append(_issue("warning", "K-above-porefill",
                               "%sK = %s kg/m2/run exceeds the bed's pore-fill ceiling of "
                               "%s kg/m2/run and is not achievable without breakthrough."
                               % (tag, format(K, ".2f"), format(pore_fill_k, ".2f"))))
    return out


def worst_severity(issues):
    """Worst severity across a list of issues."""
    if not issues:
        return "ok"
    if any(i["severity"] == "error" for i in issues):
        return "error"
    if any(i["severity"] == "warning" for i in issues):
        return "warning"
    return "ok"


def classify_k(K, typical_low=2, typical_high=5):
    """Classify a K value for benchmark reporting. Honest about physically
    impossible values rather than calling them 'high'."""
    if K is None or not _is_finite_number(K):
        return {"band": "invalid", "label": "not a valid number"}
    if K > PHYSICAL_BOUNDS["K_physicalMax"]:
        return {"band": "impossible", "label": "physically impossible - check inputs"}
    if K > PHYSICAL_BOUNDS["K_typicalMax"]:
        return {"band": "above-cap", "label": "above the breakthrough cap"}
    if K > typical_high:
        return {"band": "above-typical", "label": "above typical range"}
    if K < typical_low:
        return {"band": "below-typical", "label": "below typical range"}
    return {"band": "typical", "label": "within typical range"}
