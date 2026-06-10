"""filter_comparator.engine.physics

Python port of lib/filterPhysics.js.

Filter design physics: media properties, underdrains, clean-bed headloss
(Kozeny-Carman / Ergun / Rose), terminal head, redundancy matrix.

Ported faithfully from the JavaScript source — function names and structure
are kept close to the original so the two can be checked against each other.
This module is pure calculation: no UI, no I/O, no AquaPoint imports.
"""

import math

G = 9.81

# =========================================================================
# WATER PROPERTIES vs TEMPERATURE
# =========================================================================
# Default temp = 10 degC (cold-water conservative design).
DEFAULT_TEMP_C = 10


def water_density(T_C):
    """Density of pure water vs temperature (kg/m3). Tanaka et al. 2001."""
    T = T_C
    return 999.974950 * (
        1 - ((T - 3.98315) ** 2) * (T + 283.1505) / (503570 * (T + 67.26889))
    )


def water_dynamic_viscosity(T_C):
    """Dynamic viscosity of pure water vs temperature (Pa.s).

    Standard form: mu = 2.414e-5 * 10^(247.8 / (T_K - 140)) with T_K in Kelvin.
    Coefficients from Korson, Drost-Hansen & Millero (1969).
    """
    A = 2.414e-5
    B = 247.8
    T_K = T_C + 273.15
    return A * math.pow(10, B / (T_K - 140))


def water_kinematic_viscosity(T_C):
    """Kinematic viscosity (m2/s)."""
    return water_dynamic_viscosity(T_C) / water_density(T_C)


# Reference values at 10 degC (retained for backwards compatibility)
NU_WATER_REF = water_kinematic_viscosity(DEFAULT_TEMP_C)
RHO_WATER_REF = water_density(DEFAULT_TEMP_C)
MU_WATER_REF = water_dynamic_viscosity(DEFAULT_TEMP_C)

# =========================================================================
# MEDIA LIBRARY
# =========================================================================
MEDIA_LIBRARY = {
    "anthracite": {"name": "Anthracite", "d_mm_default": 1.20, "uc_default": 1.5,
                   "sphericity": 0.65, "porosity": 0.50, "density": 1600},
    "sand":       {"name": "Silica sand", "d_mm_default": 0.55, "uc_default": 1.5,
                   "sphericity": 0.80, "porosity": 0.42, "density": 2650},
    "garnet":     {"name": "Garnet", "d_mm_default": 0.30, "uc_default": 1.6,
                   "sphericity": 0.75, "porosity": 0.45, "density": 4100},
    "gac":        {"name": "GAC", "d_mm_default": 1.30, "uc_default": 1.7,
                   "sphericity": 0.75, "porosity": 0.50, "density": 1450},
}

# =========================================================================
# MEDIA CONFIGURATIONS (preset stacks)
# =========================================================================
MEDIA_CONFIGURATIONS = {
    "mono-sand": {"name": "Mono-media sand",
                  "layers": [{"media": "sand", "depth": 0.75, "d_mm": 0.55,
                              "uc": 1.5, "porosity": 0.42}]},
    "mono-anthracite": {"name": "Mono-media anthracite",
                        "layers": [{"media": "anthracite", "depth": 1.50, "d_mm": 1.20,
                                    "uc": 1.5, "porosity": 0.50}]},
    "dual": {"name": "Dual media (anthracite + sand)",
             "layers": [
                 {"media": "anthracite", "depth": 0.60, "d_mm": 1.20, "uc": 1.5, "porosity": 0.50},
                 {"media": "sand", "depth": 0.30, "d_mm": 0.55, "uc": 1.5, "porosity": 0.42},
             ]},
    "tri-media": {"name": "Tri-media (anthracite + sand + garnet)",
                  "layers": [
                      {"media": "anthracite", "depth": 0.45, "d_mm": 1.20, "uc": 1.5, "porosity": 0.50},
                      {"media": "sand", "depth": 0.25, "d_mm": 0.55, "uc": 1.5, "porosity": 0.42},
                      {"media": "garnet", "depth": 0.10, "d_mm": 0.30, "uc": 1.6, "porosity": 0.45},
                  ]},
    "gac-cap": {"name": "GAC cap on sand",
                "layers": [
                    {"media": "gac", "depth": 0.60, "d_mm": 1.30, "uc": 1.7, "porosity": 0.50},
                    {"media": "sand", "depth": 0.30, "d_mm": 0.55, "uc": 1.5, "porosity": 0.42},
                ]},
}

# =========================================================================
# UNDERDRAIN LIBRARY
# Empirical headloss at reference velocity v_ref = 5 m/h (1.39e-3 m/s),
# scaled with v^2 ratio.
# =========================================================================
V_REF_UNDERDRAIN_M_S = 5 / 3600  # retained for compatibility

# Headloss model (calibrated to manufacturer curves):
#   h(v) = sum_k  h_ref_k * (v / v_ref_k) ** exp_k        [m head, v in m/s]
# The 'block' entry is the SJHJV underdrain: Leopold Type XA underdrain plus
# I.M.S 200 media retainer, fitted to the Nov-2015 / 02-14 product headloss
# curves. XA is orifice-dominated (exp 2.0); the IMS retainer is a part-viscous
# porous-plate loss (exp ~1.53, tested at 18 C). Other entries are orifice-type
# devices anchored at a backwash reference flux; they are typical values, not
# manufacturer-calibrated.
_GPM_SF = 2.4448 / 3600.0   # 1 gpm/ft2 in m/s
_IN = 0.0254                # 1 inch water in m

UNDERDRAIN_LIBRARY = {
    "block": {
        "name": "Block underdrain + IMS cap (Leopold Type XA + I.M.S 200)",
        "terms": [
            {"label": "Type XA underdrain", "h_ref_m": 2.0 * _IN,
             "v_ref_m_s": 5 * _GPM_SF, "exp": 2.0},
            {"label": "I.M.S 200 retainer", "h_ref_m": 1.0 * _IN,
             "v_ref_m_s": 5 * _GPM_SF, "exp": 1.53},
        ],
        "typical_headloss_m": 0.045,   # representative at filtration flux (~3 gpm/sf)
        "notes": ("Calibrated to Leopold/Xylem Type XA underdrain and I.M.S 200 media "
                  "retainer headloss curves. XA orifice loss ~v^2 (2 in at 5 gpm/sf); "
                  "IMS retainer ~v^1.53 (1 in at 5 gpm/sf, 18 C)."),
        "source": ("Leopold (a Xylem brand) Product Engineering Data: Type XA Underdrain "
                   "Headloss (Nov 2015) and I.M.S 200 Media Retainer Hydraulic Flow Test "
                   "(PMEDI02, 02/14)."),
    },
    "block-gravel": {
        "name": "Block underdrain + support gravel",
        "terms": [
            {"label": "Type XA underdrain", "h_ref_m": 2.0 * _IN,
             "v_ref_m_s": 5 * _GPM_SF, "exp": 2.0},
            {"label": "Support gravel", "h_ref_m": 1.5 * _IN,
             "v_ref_m_s": 5 * _GPM_SF, "exp": 1.0},
        ],
        "typical_headloss_m": 0.05,
        "notes": "XA orifice loss plus a linear gravel allowance (gravel term uncalibrated).",
        "source": "XA curve as above; gravel term is a typical allowance, not measured.",
    },
    "nozzle": {
        "name": "Nozzle (false floor)",
        "terms": [{"label": "Nozzle orifice", "h_ref_m": 0.30,
                   "v_ref_m_s": 15 * _GPM_SF, "exp": 2.0}],
        "typical_headloss_m": 0.30,
        "notes": "Strainer-nozzle orifice loss, anchored at a 15 gpm/sf backwash flux (typical).",
        "source": "Kawamura (2000) Table 7-6; Degremont Handbook (2007) - typical, uncalibrated.",
    },
    "pipe-lateral": {
        "name": "Pipe lateral with orifices",
        "terms": [{"label": "Lateral orifice", "h_ref_m": 0.55,
                   "v_ref_m_s": 15 * _GPM_SF, "exp": 2.0}],
        "typical_headloss_m": 0.55,
        "notes": "Manifold/orifice laterals, anchored at a 15 gpm/sf backwash flux (typical).",
        "source": "Kawamura (2000) Table 7-6; AWWA M37 - typical, uncalibrated.",
    },
    "wheeler": {
        "name": "Wheeler bottom",
        "terms": [{"label": "Wheeler orifice", "h_ref_m": 0.45,
                   "v_ref_m_s": 15 * _GPM_SF, "exp": 2.0}],
        "typical_headloss_m": 0.45,
        "notes": "Porcelain-sphere false bottom, anchored at a 15 gpm/sf backwash flux (typical).",
        "source": "Cleasby & Logsdon (1999); Crittenden et al. (2012) - typical, uncalibrated.",
    },
}

# =========================================================================
# CLEAN BED HEADLOSS EQUATIONS (m head per m bed)
# =========================================================================


def headloss_kozeny_carman(layer, v_m_s, temp_C=DEFAULT_TEMP_C):
    """Kozeny-Carman (Crittenden 2012 Eq 11-39)."""
    eps = layer["porosity"]
    phi = MEDIA_LIBRARY[layer["media"]]["sphericity"]
    d = layer["d_mm"] / 1000
    mu = water_dynamic_viscosity(temp_C)
    rho = water_density(temp_C)
    return (180 * mu * (1 - eps) ** 2 * v_m_s) / (rho * G * eps ** 3 * phi ** 2 * d ** 2)


def headloss_ergun(layer, v_m_s, temp_C=DEFAULT_TEMP_C):
    """Ergun (Crittenden 2012 Eq 11-40)."""
    eps = layer["porosity"]
    phi = MEDIA_LIBRARY[layer["media"]]["sphericity"]
    d = layer["d_mm"] / 1000
    mu = water_dynamic_viscosity(temp_C)
    rho = water_density(temp_C)
    viscous = (150 * mu * (1 - eps) ** 2 * v_m_s) / (rho * G * eps ** 3 * phi ** 2 * d ** 2)
    inertial = (1.75 * (1 - eps) * v_m_s ** 2) / (G * eps ** 3 * phi * d)
    return viscous + inertial


def headloss_rose(layer, v_m_s, temp_C=DEFAULT_TEMP_C):
    """Rose (Cleasby & Logsdon 1999)."""
    eps = layer["porosity"]
    phi = MEDIA_LIBRARY[layer["media"]]["sphericity"]
    d = layer["d_mm"] / 1000
    nu = water_kinematic_viscosity(temp_C)
    Re = (v_m_s * d) / (eps * nu)
    C_D = 24 / max(Re, 1e-3) + 3 / math.sqrt(max(Re, 1e-3)) + 0.34
    return (1.067 * C_D * v_m_s ** 2 * (1 - eps)) / (phi * G * eps ** 4 * d)


CLEAN_BED_EQS = {
    "kozeny-carman": headloss_kozeny_carman,
    "ergun": headloss_ergun,
    "rose": headloss_rose,
}

CLEAN_BED_EQ_LABELS = {
    "kozeny-carman": "Kozeny-Carman",
    "ergun": "Ergun",
    "rose": "Rose",
}

# =========================================================================
# SUPPLIER MEASURED-MEDIA CLEAN-BED HEADLOSS
# Manufacturer headloss curves (headloss per metre of bed vs filtration
# velocity) digitised from the SJHJV media datasheets. Where a layer carries
# a "supplier_grade" key, the curve is interpolated and Kozeny-Carman + UC
# correction are bypassed, since the curve already reflects the real grading
# and grain shape. Each grade stores points = [(v_mh, mbar/m), ...] read at
# the chart gridlines; curves are linear through the origin over 0-30 m/h.
# Grades used by the SJHJV (D1) and Acciona (D2) beds are anchored to clear
# datasheet reads; the remaining grades are provisional single-anchor reads
# included so any media selection is covered, and should be confirmed against
# the source charts. Temperature basis of the curves (ref_temp_C) is assumed
# and should be confirmed; headloss is scaled to operating temperature by the
# dynamic-viscosity ratio (laminar).
# =========================================================================
MBAR_TO_M = 0.0102            # 1 mbar of water column = 0.0102 m
SUPPLIER_REF_TEMP_C = 10.0    # assumed datasheet test temperature (confirm)

SUPPLIER_MEDIA = {
    # Aqua-cite anthracite (EN 12909)
    "aqua-cite-0.8-1.6":  {"label": "Aqua-cite anthracite 0.8-1.6 mm",
        "datasheet": "Aqua-cite EN 12909 (GBH21211_2)", "ref_temp_C": 10.0,
        "anchored": True,  "points": [(0, 0.0), (10, 13.6), (20, 27.2), (30, 41.0)]},
    "aqua-cite-1.2-2.0":  {"label": "Aqua-cite anthracite 1.2-2.0 mm",
        "datasheet": "Aqua-cite EN 12909 (GBH21211_2)", "ref_temp_C": 10.0,
        "anchored": True,  "points": [(0, 0.0), (10, 7.8), (20, 15.6), (30, 23.5)]},
    "aqua-cite-1.4-2.5":  {"label": "Aqua-cite anthracite 1.4-2.5 mm",
        "datasheet": "Aqua-cite EN 12909 (GBH21211_2)", "ref_temp_C": 10.0,
        "anchored": False, "points": [(0, 0.0), (30, 17.0)]},
    "aqua-cite-2.5-4.0":  {"label": "Aqua-cite anthracite 2.5-4.0 mm",
        "datasheet": "Aqua-cite EN 12909 (GBH21211_2)", "ref_temp_C": 10.0,
        "anchored": False, "points": [(0, 0.0), (30, 9.0)]},
    "aqua-cite-4.0-8.0":  {"label": "Aqua-cite anthracite 4.0-8.0 mm",
        "datasheet": "Aqua-cite EN 12909 (GBH21211_2)", "ref_temp_C": 10.0,
        "anchored": False, "points": [(0, 0.0), (30, 4.0)]},
    # Aqua-sand (EN 12904)
    "aqua-sand-0.4-0.8":  {"label": "Aqua-sand 0.4-0.8 mm",
        "datasheet": "Aqua-sand EN 12904 (GBH22211_2)", "ref_temp_C": 10.0,
        "anchored": True,  "points": [(0, 0.0), (10, 61.0), (20, 122.0), (30, 183.0)]},
    "aqua-sand-0.63-1.0": {"label": "Aqua-sand 0.63-1.0 mm",
        "datasheet": "Aqua-sand EN 12904 (GBH22211_2)", "ref_temp_C": 10.0,
        "anchored": False, "points": [(0, 0.0), (30, 96.0)]},
    "aqua-sand-0.71-1.25":{"label": "Aqua-sand 0.71-1.25 mm",
        "datasheet": "Aqua-sand EN 12904 (GBH22211_2)", "ref_temp_C": 10.0,
        "anchored": False, "points": [(0, 0.0), (30, 84.0)]},
    "aqua-sand-1.0-1.6":  {"label": "Aqua-sand 1.0-1.6 mm",
        "datasheet": "Aqua-sand EN 12904 (GBH22211_2)", "ref_temp_C": 10.0,
        "anchored": False, "points": [(0, 0.0), (30, 47.0)]},
    "aqua-sand-1.0-2.0":  {"label": "Aqua-sand 1.0-2.0 mm",
        "datasheet": "Aqua-sand EN 12904 (GBH22211_2)", "ref_temp_C": 10.0,
        "anchored": False, "points": [(0, 0.0), (30, 40.0)]},
    # Aqua-garco garnet (EN 12910)
    "aqua-garco-0.3-0.6": {"label": "Aqua-garco garnet 0.3-0.6 mm",
        "datasheet": "Aqua-garco EN 12910 (GBH24211_2)", "ref_temp_C": 10.0,
        "anchored": True,  "points": [(0, 0.0), (10, 105.0), (20, 210.0), (30, 318.0)]},
    "aqua-garco-0.5-0.95":{"label": "Aqua-garco garnet 0.5-0.95 mm",
        "datasheet": "Aqua-garco EN 12910 (GBH24211_2)", "ref_temp_C": 10.0,
        "anchored": False, "points": [(0, 0.0), (30, 135.0)]},
    "aqua-garco-1.4-2.3": {"label": "Aqua-garco garnet 1.4-2.3 mm",
        "datasheet": "Aqua-garco EN 12910 (GBH24211_2)", "ref_temp_C": 10.0,
        "anchored": True,  "points": [(0, 0.0), (10, 8.3), (20, 16.6), (30, 25.0)]},
}


def _interp_points(points, x):
    """Piecewise-linear interpolation over (x, y) point pairs, with linear
    extrapolation beyond either end using the nearest segment slope."""
    if x <= points[0][0]:
        (x0, y0), (x1, y1) = points[0], points[1]
    elif x >= points[-1][0]:
        (x0, y0), (x1, y1) = points[-2], points[-1]
    else:
        (x0, y0), (x1, y1) = points[0], points[1]
        for a, b in zip(points, points[1:]):
            if x <= b[0]:
                (x0, y0), (x1, y1) = a, b
                break
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def supplier_headloss_per_m(grade, v_m_s, temp_C=DEFAULT_TEMP_C):
    """Clean-bed headloss per metre of bed (m/m) from a digitised supplier
    curve, scaled from the datasheet reference temperature to temp_C
    (laminar; headloss proportional to dynamic viscosity)."""
    g = SUPPLIER_MEDIA[grade]
    v_mh = v_m_s * 3600.0
    ref_T = g.get("ref_temp_C", SUPPLIER_REF_TEMP_C)
    temp_factor = water_dynamic_viscosity(temp_C) / water_dynamic_viscosity(ref_T)
    return _interp_points(g["points"], v_mh) * MBAR_TO_M * temp_factor

# =========================================================================
# CLEASBY-LOGSDON UC CORRECTION
#   dH_corrected = dH(d_10) * [1 + 1.3 * (UC - 1)]
# Source: Cleasby, J.L., Logsdon, G.S. (1999). Granular bed and precoat
# filtration. In: Water Quality and Treatment, 5th ed., AWWA.
# =========================================================================


def uc_correction_factor(uc):
    if not uc or uc < 1.0:
        return 1.0
    return 1.0 + 1.3 * (uc - 1.0)


def clean_bed_headloss(layers, velocity_m_s, equation="kozeny-carman",
                       apply_uc_correction=True, temp_C=DEFAULT_TEMP_C):
    fn = CLEAN_BED_EQS.get(equation)
    if fn is None:
        raise ValueError("Unknown equation: %s" % equation)
    layer_results = []
    for layer in layers:
        grade = layer.get("supplier_grade")
        if grade and grade in SUPPLIER_MEDIA:
            d_h_per_l = supplier_headloss_per_m(grade, velocity_m_s, temp_C)
            d_h_per_l_uniform = d_h_per_l
            correction = 1.0
            source = "supplier:" + grade
        else:
            d_h_per_l_uniform = fn(layer, velocity_m_s, temp_C)
            uc = layer.get("uc")
            if uc is None:
                uc = 1.0
            correction = uc_correction_factor(uc) if apply_uc_correction else 1.0
            d_h_per_l = d_h_per_l_uniform * correction
            source = equation
        uc = layer.get("uc") or 1.0
        layer_results.append({
            "media": layer["media"], "depth_m": layer["depth"], "d_mm": layer["d_mm"],
            "uc": uc, "porosity": layer["porosity"], "ucCorrection": correction,
            "source": source,
            "dH_per_m_uniform": d_h_per_l_uniform,
            "dH_per_m": d_h_per_l,
            "dH_m_uniform": d_h_per_l_uniform * layer["depth"],
            "dH_m": d_h_per_l * layer["depth"],
        })
    return {
        "total_m": sum(l["dH_m"] for l in layer_results),
        "total_m_uniform": sum(l["dH_m_uniform"] for l in layer_results),
        "layers": layer_results,
        "ucCorrectionApplied": apply_uc_correction,
        "temp_C": temp_C,
        "mu_Pa_s": water_dynamic_viscosity(temp_C),
        "rho_kg_m3": water_density(temp_C),
    }


def underdrain_headloss(underdrain_key, v_m_s):
    """Underdrain headloss (m) at superficial velocity v_m_s, summing the
    calibrated power-law terms for the device. Same magnitude in the
    filtration and backwash directions for a given flux."""
    u = UNDERDRAIN_LIBRARY.get(underdrain_key)
    if u is None:
        raise ValueError("Unknown underdrain: %s" % underdrain_key)
    terms = u.get("terms")
    if terms:
        return sum(t["h_ref_m"] * math.pow(v_m_s / t["v_ref_m_s"], t["exp"])
                   for t in terms)
    # legacy fallback
    return u["typical_headloss_m"] * math.pow(v_m_s / V_REF_UNDERDRAIN_M_S, 2)


UNDERDRAIN_REF_VELOCITY_M_S = V_REF_UNDERDRAIN_M_S
UNDERDRAIN_REF_VELOCITY_M_H = 5


def underdrain_headloss_series(underdrain_key, velocity_range_mh=(2, 16), n_points=28):
    vmin, vmax = velocity_range_mh
    step = (vmax - vmin) / (n_points - 1)
    points = []
    for i in range(n_points):
        v_mh = vmin + i * step
        v_ms = v_mh / 3600
        points.append({"v_m_h": v_mh, "dH_m": underdrain_headloss(underdrain_key, v_ms)})
    return points


def all_underdrain_headloss_series(velocity_range_mh=(2, 16), n_points=28):
    return [
        {
            "key": key,
            "name": u["name"],
            "refHeadloss_m": u["typical_headloss_m"],
            "points": underdrain_headloss_series(key, velocity_range_mh, n_points),
        }
        for key, u in UNDERDRAIN_LIBRARY.items()
    ]


# =========================================================================
# HELPERS
# =========================================================================


def total_bed_depth(layers):
    return sum(l["depth"] for l in layers)


def total_filter_area(n, area_each):
    return n * area_each


def filtration_velocity(flow_MLD, area_in_service_m2):
    Q_m3s = (flow_MLD * 1e6) / (24 * 3600 * 1000)
    return Q_m3s / area_in_service_m2


def v_to_m_per_hr(v_m_s):
    return v_m_s * 3600


def mints_tien_load(sigma_g_per_L):
    """Mints-Tien load-dependent headloss."""
    return 0.92 * math.pow(max(0, sigma_g_per_L), 2 / 3)
