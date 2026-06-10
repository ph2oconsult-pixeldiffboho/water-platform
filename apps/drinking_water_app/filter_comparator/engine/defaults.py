"""filter_comparator.engine.defaults

Python port of lib/filterDefaults.js.

Filter design defaults for D1 and D2. Operational inputs (TSS, flow,
removal %, BW volumes, precipitate fractions) are user-supplied as a
min/avg/max envelope so all downstream outputs can be computed for three
scenarios. Filter geometry and clean-bed equation remain single values.
"""


def envelope(min_, avg, max_):
    """Construct a min/avg/max triplet."""
    return {"min": min_, "avg": avg, "max": max_}


# =========================================================================
# SCENARIO PICKERS
# =========================================================================
SCENARIOS = ["min", "avg", "max"]
SCENARIO_LABELS = {
    "min": "Min (low envelope)",
    "avg": "Avg (central estimate)",
    "max": "Max (high envelope)",
}
SCENARIO_SHORT = {"min": "Min", "avg": "Avg", "max": "Max"}
SCENARIO_COLOURS = {
    "min": "#5A7359",  # sage
    "avg": "#3F5870",  # slate
    "max": "#B0451F",  # rust
}


def pick_scenario_value(envelope_or_scalar, scenario="avg"):
    """Given a value that may be a scalar or an envelope, return the value
    for the requested scenario."""
    if envelope_or_scalar is None:
        return 0
    if isinstance(envelope_or_scalar, (int, float)):
        return envelope_or_scalar
    if isinstance(envelope_or_scalar, dict) and "avg" in envelope_or_scalar:
        v = envelope_or_scalar.get(scenario)
        if v is not None:
            return v
        v = envelope_or_scalar.get("avg")
        return v if v is not None else 0
    return 0


def pick_feed_scenario(feed, scenario="avg"):
    """Resolve a feed envelope object into concrete values for one scenario."""
    precipitate = None
    if feed.get("precipitate"):
        precipitate = {
            k: pick_scenario_value(v, scenario)
            for k, v in feed["precipitate"].items()
        }
    # Three-component BW volumes (each design-fixed scalar)
    drain_volume_m3 = feed.get("drainVolume_m3") or 0
    backwash_volume_m3 = feed.get("backwashVolume_m3")
    if backwash_volume_m3 is None:
        backwash_volume_m3 = feed.get("volumePerBW_m3") or 0  # legacy fallback
    ftw_volume_m3 = feed.get("ftwVolume_m3") or 0
    drain_destination = feed.get("drainDestination") or "waste"
    backwash_destination = feed.get("backwashDestination") or "waste"
    ftw_destination = feed.get("ftwDestination") or "waste"
    volume_per_bw_m3 = drain_volume_m3 + backwash_volume_m3 + ftw_volume_m3  # derived total

    def is_loss(dest):
        return dest == "waste"

    net_loss_per_bw_m3 = (
        (drain_volume_m3 if is_loss(drain_destination) else 0)
        + (backwash_volume_m3 if is_loss(backwash_destination) else 0)
        + (ftw_volume_m3 if is_loss(ftw_destination) else 0)
    )
    return {
        "feedTSS_mgL": pick_scenario_value(feed.get("feedTSS_mgL"), scenario),
        "filterTSSRemoval_pct": pick_scenario_value(feed.get("filterTSSRemoval_pct"), scenario),
        "totalBWVolume_MLd": pick_scenario_value(feed.get("totalBWVolume_MLd"), scenario),
        "drainVolume_m3": drain_volume_m3,
        "backwashVolume_m3": backwash_volume_m3,
        "ftwVolume_m3": ftw_volume_m3,
        "volumePerBW_m3": volume_per_bw_m3,
        "netLossPerBW_m3": net_loss_per_bw_m3,
        "drainDestination": drain_destination,
        "backwashDestination": backwash_destination,
        "ftwDestination": ftw_destination,
        "precipitate": precipitate,
    }


BW_VOLUME_DESTINATIONS = {
    "waste": "Waste (lost to drain / sludge)",
    "recycle": "Recycle to clarifier inlet",
    "reuse": "Reuse (e.g. internal BW supply)",
}

# =========================================================================
# PRECIPITATE TYPE - K MULTIPLIERS AND NARRATIVE DESCRIPTIONS
# (relative to alum baseline of 1.00x)
# =========================================================================
PRECIPITATE_MULTIPLIERS = {
    "alum": {
        "label": "Aluminium hydroxide (alum)",
        "short": "Alum floc",
        "multiplier": 1.00,
        "density_gcm3": 1.003,
        "drySolids_pct": "0.5-2%",
        "description": ("Alum (aluminium sulphate) hydrolyses to Al(OH)3, forming light, "
                        "gelatinous flocs with extensive water of hydration. Floc density is "
                        "only 1-5 kg/m3 above water and dry solids content is 0.5-2%."),
        "impact": ("These flocs occupy substantial pore volume per unit dry mass - they are "
                   "bulky relative to their mass. This is why alum is the K baseline (1.00x): "
                   "the headloss curve is dominated by pore-volume occupation, and the "
                   "sigma^(2/3) Mints-Tien relationship was originally calibrated on "
                   "alum-coagulated water. Alum flocs do compress under headloss buildup, "
                   "which slows late-run dHL/dt but caps the achievable K."),
        "practicalNote": ("Most predictable behaviour. Performance degrades at low temperature "
                          "(winter) due to slower floc formation. Charge-neutralisation "
                          "conditions (lower dose, pH 6.5-7.5) give the most filterable floc; "
                          "sweep coagulation (higher dose) gives more voluminous, harder-to-"
                          "filter floc."),
    },
    "ferric": {
        "label": "Ferric hydroxide (ferric coag.)",
        "short": "Ferric floc",
        "multiplier": 1.30,
        "density_gcm3": 1.010,
        "drySolids_pct": "1.5-4%",
        "description": ("Ferric chloride or ferric sulphate hydrolyses to Fe(OH)3, forming "
                        "smaller, denser, and more compact flocs than alum. Floc density is "
                        "5-15 kg/m3 above water with dry solids content of 1.5-4% - roughly "
                        "double the dry solids of alum at the same mass."),
        "impact": ("Ferric flocs are smaller and denser, so they penetrate deeper into the "
                   "bed before being captured. This distributes the solids deposit more "
                   "uniformly through the bed depth rather than caking the top - exactly the "
                   "deposition pattern that maximises K. SEM imaging shows ferric flocs form "
                   "compact, uniform deposits whereas alum flocs form larger but fewer surface "
                   "deposits. The result is a K multiplier of 1.2-1.4x relative to alum."),
        "practicalNote": ("Better cold-water performance than alum. More aggressive on pH "
                          "(drives pH down harder), so requires more alkalinity adjustment. "
                          "Slightly higher coagulant dose for equivalent NOM removal. The "
                          "denser, smaller flocs settle faster in the clarifier too - but if "
                          "any escape clarification, they filter better than alum carryover."),
    },
    "caco3": {
        "label": "Calcium carbonate (lime softening)",
        "short": "CaCO3 floc",
        "multiplier": 1.70,
        "density_gcm3": 1.15,
        "drySolids_pct": "5-15%",
        "description": ("Calcium carbonate from lime softening forms dense crystalline "
                        "precipitates. Pure calcite has a true density of 2.7 g/cm3; when "
                        "well-formed in a softening clarifier, the floc density is 1.05-1.20 "
                        "g/cm3 and dry solids content reaches 5-15%."),
        "impact": ("When CaCO3 arrives at the filter as well-formed dense particles from "
                   "clarifier carryover, it has the highest filterability of the four "
                   "precipitates. The crystalline particles pack tightly with minimal "
                   "pore-volume occupation per unit dry mass - essentially the opposite of "
                   "alum/Mg(OH)2 behaviour. K multipliers of 1.5-2.0x are typical."),
        "practicalNote": ("CRITICAL CAVEAT: this favourable behaviour only applies if the "
                          "softening reaction has FINISHED before water reaches the filter. "
                          "If recarbonation is incomplete or if pH stays above ~9.5, CaCO3 "
                          "will continue to precipitate INSIDE the filter - coating media and "
                          "underdrain laterals with crystalline scale. This collapses K toward "
                          "zero and is essentially irreversible without acid wash. CO2 "
                          "injection just upstream of the filter is essential when blend "
                          "ratios are high."),
    },
    "mgoh2": {
        "label": "Magnesium hydroxide (lime softening)",
        "short": "Mg(OH)2 floc",
        "multiplier": 0.50,
        "density_gcm3": 1.002,
        "drySolids_pct": "<1%",
        "description": ("Magnesium hydroxide is the most gelatinous of the four precipitates. "
                        "Floc density is only 1-3 kg/m3 above water and dry solids content "
                        "typically falls below 1% - even more dilute than alum floc. Forms at "
                        "high pH (>10.6) during lime softening when magnesium hardness is "
                        "present."),
        "impact": ("Pure Mg(OH)2 has the worst filterability of the four. The highly "
                   "gelatinous structure plugs pore throats aggressively because the floc "
                   "cannot deform without losing structural integrity. K multipliers of "
                   "0.4-0.6x relative to alum are typical when Mg(OH)2 dominates. Importantly, "
                   "the impact is non-linear: Mg(OH)2 fractions above ~20-30% start dragging "
                   "the effective K below alum baseline regardless of the rest of the mix."),
        "practicalNote": ("Mg(OH)2 rarely arrives at the filter alone - it usually "
                          "co-precipitates with CaCO3 in lime softening, and the combined floc "
                          "is much more filterable than pure Mg(OH)2. The library multiplier "
                          "assumes the pure-precipitate case; if the upstream clarifier "
                          "captures most of the Mg(OH)2, the effective fraction at the filter "
                          "may be much lower than the bulk-water composition implies."),
    },
    "other": {
        "label": "Other inert solids (raw TSS)",
        "short": "Inert TSS",
        "multiplier": 1.10,
        "density_gcm3": 1.30,
        "drySolids_pct": "5-25%",
        "description": ("Mineral particles (silica, clay, fine sand) and organic detritus "
                        "that pass through coagulation untreated - typically the small "
                        "fraction of raw water TSS that escapes the clarifier without being "
                        "incorporated into a coagulant floc."),
        "impact": ("Inert mineral solids are denser than any of the chemical precipitates and "
                   "have negligible water of hydration. They occupy little pore volume per "
                   "unit dry mass. However, they tend to be small and well-distributed (since "
                   "they weren't captured by the coagulant) and so penetrate deep into the "
                   "bed. Net K multiplier is around 1.1x - slightly better than alum but not "
                   "as good as ferric or CaCO3."),
        "practicalNote": ("The 'other' fraction is usually small in a well-coagulated plant "
                          "(under 20% of filter feed solids). If it grows above ~30%, it "
                          "indicates poor coagulation or a step-change in raw water quality. "
                          "Algae and algogenic organic carbon, if present, should be "
                          "classified here too but they behave more like alum/Mg(OH)2 - "
                          "better to treat them by adjusting the alum fraction upward."),
    },
}

# =========================================================================
# PLANT FLOW ENVELOPE
# =========================================================================
DEFAULT_FLOW_ENVELOPE = {
    "designFlow_MLD": envelope(60, 90, 120),
    "dHLModel": "mints",
    "treatedWaterCost_per_ML": 1500,  # $/ML, configurable on the inputs tab
}


def peak_flow_from_envelope(flow_env):
    """Peak flow (used only by hydraulic redundancy '+ peak' condition) is
    always the max of the envelope by convention."""
    return pick_scenario_value(flow_env["designFlow_MLD"], "max")


# =========================================================================
# FILTER GEOMETRY DEFAULTS (single-valued - fixed by design)
# =========================================================================
DESIGNER_DEFAULTS = {
    "D1": {
        "id": "D1",
        "name": "Designer 1",
        "fullName": "Designer 1 (RGMF)",
        "filter": {
            "type": "RGMF (multi-media)",
            "numFilters": 8,
            "areaPerFilter_m2": 80.7,
            "mediaConfig": "custom",
            "mediaLayers": [
                {"media": "anthracite", "depth": 1.000, "d_mm": 1.00, "uc": 1.30, "porosity": 0.49, "supplier_grade": "aqua-cite-0.8-1.6"},
                {"media": "sand", "depth": 0.400, "d_mm": 0.50, "uc": 1.40, "porosity": 0.40, "supplier_grade": "aqua-sand-0.4-0.8"},
                {"media": "garnet", "depth": 0.200, "d_mm": 0.45, "uc": 1.40, "porosity": 0.45, "supplier_grade": "aqua-garco-0.3-0.6"},
                {"media": "garnet", "depth": 0.075, "d_mm": 2.00, "uc": 1.60, "porosity": 0.45, "supplier_grade": "aqua-garco-1.4-2.3"},
            ],
            "underdrain": "block",
            "cleanBedEquation": "kozeny-carman",
            "applyUCCorrection": True,
            "temp_C": 10,
            "drivingHead_m": 3.87,
            "appurtenanceLoss_m": 0.15,
            "bwSequence": {"drainDown_min": 5.0, "backwashWater_min": 16.5,
                           "fillUp_min": 0, "filterToWaste_min": 15.0,
                           "returnToService_min": 1.0},
            "runHours_override_hr": 24,
            "designRunHours_at_maxTSS_hr": 44,
        },
    },
    "D2": {
        "id": "D2",
        "name": "Designer 2",
        "fullName": "Designer 2 (DMF)",
        "filter": {
            "type": "DMF (dual-media)",
            "numFilters": 6,
            "areaPerFilter_m2": 121.6,
            "mediaConfig": "dual",
            "mediaLayers": [
                {"media": "anthracite", "depth": 1.40, "d_mm": 1.50, "uc": 1.50, "porosity": 0.48, "supplier_grade": "aqua-cite-1.2-2.0"},
                {"media": "sand", "depth": 0.70, "d_mm": 0.55, "uc": 1.50, "porosity": 0.40, "supplier_grade": "aqua-sand-0.4-0.8"},
            ],
            "underdrain": "block",
            "cleanBedEquation": "kozeny-carman",
            "applyUCCorrection": True,
            "temp_C": 10,
            "drivingHead_m": 4.77,
            "appurtenanceLoss_m": 0.15,
            "bwSequence": {"drainDown_min": 7.0, "backwashWater_min": 20.0,
                           "fillUp_min": 29.0, "filterToWaste_min": 29.0,
                           "returnToService_min": 0},
            "runHours_override_hr": 24,
            "designRunHours_at_maxTSS_hr": 16,
        },
    },
}

# =========================================================================
# PER-DESIGNER FEED ENVELOPE DEFAULTS
# Every operational input is a {min, avg, max} triplet.
# =========================================================================
DESIGNER_FEED_DEFAULTS = {
    "D1": {
        "feedTSS_mgL": envelope(5, 8, 11.6),
        "filterTSSRemoval_pct": envelope(97, 97, 97),
        "totalBWVolume_MLd": envelope(1.30, 2.50, 3.44),
        "drainVolume_m3": 178,
        "backwashVolume_m3": 450,
        "ftwVolume_m3": 171,
        "drainDestination": "waste",
        "backwashDestination": "waste",
        "ftwDestination": "waste",
        "precipitate": {
            "alum": envelope(0.00, 0.00, 0.00),
            "ferric": envelope(1.00, 1.00, 1.00),
            "caco3": envelope(0.00, 0.00, 0.00),
            "mgoh2": envelope(0.00, 0.00, 0.00),
            "other": envelope(0.00, 0.00, 0.00),
        },
        # Algae-clogging inputs (see engine/algae.py). Residual is the count
        # reaching the filters after clarification; availableHead_m None means
        # the head budget is calculated from the filter dict and physics.
        "residualAlgae_cells_per_mL": 20000,
        "massPerCell_pg": 100,
        "mineralBackground_mgL": 8,
        "morphologyScenario": None,
        "densadegRecycle": True,
        "availableHead_m": None,
        "headSource": None,
        "drivingHeadOverride_m": None,
    },
    "D2": {
        "feedTSS_mgL": envelope(10, 15.3, 42.4),
        "filterTSSRemoval_pct": envelope(90, 90, 90),
        "totalBWVolume_MLd": envelope(7.86, 5.89, 23.58),
        "drainVolume_m3": 419,
        "backwashVolume_m3": 1100,
        "ftwVolume_m3": 1339,
        "drainDestination": "waste",
        "backwashDestination": "waste",
        "ftwDestination": "recycle",
        "precipitate": {
            "alum": envelope(1.00, 1.00, 1.00),
            "ferric": envelope(0.00, 0.00, 0.00),
            "caco3": envelope(0.00, 0.00, 0.00),
            "mgoh2": envelope(0.00, 0.00, 0.00),
            "other": envelope(0.00, 0.00, 0.00),
        },
        # Algae-clogging inputs (see engine/algae.py).
        "residualAlgae_cells_per_mL": 20000,
        "massPerCell_pg": 100,
        "mineralBackground_mgL": 8,
        "morphologyScenario": None,
        "densadegRecycle": False,
        "availableHead_m": None,
        "headSource": None,
        "drivingHeadOverride_m": None,
    },
}
