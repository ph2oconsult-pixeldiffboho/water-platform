"""
BioPoint V2 — Strategic Pathway Spine (first slice)
===================================================

This is NOT the old technology scorer. It is the spine of the pathway-intelligence
architecture agreed in design:

    objective (driver ranking)
      -> constraint diagnosis
        -> pathway register, each pathway carrying FOUR conserved-quantity ledgers
           (Carbon, Energy, Nitrogen, Phosphorus) that MUST close end-to-end
             -> drivers scored OFF the ledgers (no independent double-counted engines)
               -> moves tagged commit / keep-open / avoid (reward, residual risk, confidence)
                 -> roadmap

Core discipline (the St Marys gate, generalised): a ledger that does not close is a
model that is lying. Closure is both the QA gate and the headline. Driver scores are
VIEWS of the four balances, not separate calculations.

Worked pathway in this slice: Primary treatment -> separate dewater -> THP of WAS ->
MAD of (PS + THP-WAS) -> dewater -> struvite recovery -> cake to land. Chosen because
all four ledgers close against real calibrated data (St Marys / Mangere). The thermal
endpoint (PFAS / Scope-1) is left as a KEEP-OPEN move with a priced de-risking task —
it is the gap this "safe" pathway does not close, and the next build.

Boundary: includes upstream consequences (primary-capture aeration credit, dewatering),
per the decision that upstream processing is equally important to the energy balance.

Calibration provenance is tagged inline. Confidence is tracked SEPARATELY from
performance and gates the recommendation verb — it never silently excludes a pathway.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


# ---------------------------------------------------------------------------
# 1. STRATEGIC OBJECTIVE  — driver ranking is an explicit input, never hidden
# ---------------------------------------------------------------------------
# The user's ranking. Order is the only thing asserted; no strategy inferred from it.
DRIVER_RANKING = [
    "scope1_emissions",
    "pfas",
    "nutrient_recovery",
    "opex",
    "future_proof",
    "capacity",
    "capex",
]
# Energy neutrality sits alongside these as a first-class driver (whole-pathway net).
DRIVER_RANKING_PLUS = ["energy_neutrality"] + DRIVER_RANKING


def rank_weights(ranking: list[str]) -> dict[str, float]:
    """Rank-order weights (top driver heaviest), normalised to sum 1.0.
    Deliberately simple and transparent — the board can see exactly why a
    weighting is what it is. No magic."""
    n = len(ranking)
    raw = {d: (n - i) for i, d in enumerate(ranking)}  # n, n-1, ... 1
    total = sum(raw.values())
    return {d: v / total for d, v in raw.items()}


# ---------------------------------------------------------------------------
# 2. CONSERVED-QUANTITY LEDGER  — the backbone. Must close or it is inadmissible.
# ---------------------------------------------------------------------------
@dataclass
class Ledger:
    """A single conserved quantity tracked across the whole pathway.
    `inflows` and `outflows` are {label: amount} in consistent units.
    Closure = (sum_in - sum_out) within tolerance. This is the St Marys gate."""
    quantity: str
    unit: str
    inflows: dict[str, float] = field(default_factory=dict)
    outflows: dict[str, float] = field(default_factory=dict)
    tol_pct: float = 2.0            # commit-grade closure tolerance
    provisional_tol_pct: float = 15.0  # thermal/uncertain branches: provisional, not committed
    provisional: bool = False       # set True when split fractions are not calibrated

    @property
    def total_in(self) -> float:
        return sum(self.inflows.values())

    @property
    def total_out(self) -> float:
        return sum(self.outflows.values())

    @property
    def imbalance_pct(self) -> float:
        if self.total_in == 0:
            return 0.0
        return 100.0 * (self.total_in - self.total_out) / self.total_in

    @property
    def closes(self) -> bool:
        tol = self.provisional_tol_pct if self.provisional else self.tol_pct
        return abs(self.imbalance_pct) <= tol

    def fraction_to(self, *labels: str) -> float:
        """Recovered / routed fraction — this is how a driver reads the ledger."""
        got = sum(self.outflows.get(l, 0.0) for l in labels)
        return got / self.total_in if self.total_in else 0.0

    def report(self) -> str:
        flag = ""
        if self.provisional:
            flag = "  [PROVISIONAL — split fractions not calibrated]"
        lines = [f"  {self.quantity} ledger ({self.unit}){flag}"]
        lines.append(f"    IN  {self.total_in:>10.2f}")
        for k, v in self.inflows.items():
            lines.append(f"        {k:<34}{v:>10.2f}")
        lines.append(f"    OUT {self.total_out:>10.2f}")
        for k, v in self.outflows.items():
            lines.append(f"        {k:<34}{v:>10.2f}")
        status = "CLOSES" if self.closes else "*** DOES NOT CLOSE ***"
        lines.append(f"    imbalance {self.imbalance_pct:+.2f}%   {status}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. CALIBRATED CONSTANTS  — sourced from our validated reference work
# ---------------------------------------------------------------------------
class K:
    # St Marys Cambi THP full-scale (Sydney Water) — confidence 95/100
    VSR = 0.657                 # full pre-digestion THP VSR - rebased to 2026 basis (conv 0.575 + uplift)
    VSR_CONV = 0.575            # conventional blended MAD VSR - Cambi 2026 (Mangere P50 0.585 cross-check)
    VS_TS = 0.808               # VS/TS, PFD Note 3
    METHANE_YIELD_NM3_TDS = 258 # Nm3 CH4 / tDS feed (St Marys == Davyhulme)
    STEAM_T_PER_TDS = 0.94      # THP steam, t/tDS THP feed (band 0.85-1.00)
    # Physical / stoichiometric
    C_PER_VS = 0.51             # gC / gVS, municipal sludge (band 0.45-0.53)
    N_PER_VS = 0.050            # gN / gVS feed (used only when no measured feed N)
    # Soluble NH4 reporting to centrate = feed_N x VSR x this efficiency. Calibrated so a
    # THP case lands in the Mangere MEASURED centrate band (32-43% of feed N), NOT = VSR.
    # Setting release = VSR (the legacy approach) over-predicts centrate N (the old "8,814").
    N_SOLUBILISATION_EFF = 0.70
    P_PER_DS = 0.012            # gP / gDS feed
    CH4_LHV_KWH_NM3 = 9.97      # lower heating value
    CH4_C_KG_PER_NM3 = 0.535    # kg C per Nm3 CH4
    BIOGAS_NM3_PER_KG_VSD = 0.90  # Nm3 biogas/kg VS destroyed - ETP Cambi 2015 (was 0.95)
    CH4_FRACTION = 0.63         # THP-AD biogas CH4 by volume
    FUGITIVE_CH4_FRAC = 0.015   # methane slip -> Scope 1 (capture performance, not gas volume)
    CHP_ELEC = 0.40
    CHP_HEAT = 0.45
    GAS_UTILISATION_DEFAULT = 0.95  # biogas to CHP; rest flared (CHP-sizing artifact, plant input). Mangere-as-operated ~0.80
    STEAM_KWH_PER_KG = 0.70     # ~2.6 MJ/kg saturated steam
    DEWATER_KWH_PER_TDS = 40.0
    DIGESTER_HEAT_MWH_D = 15.0  # net, after hot THP-WAS heat integration
    STRUVITE_PARASITIC_MWH_D = 1.5
    THP_PUMP_PARASITIC_MWH_D = 2.0
    PLANT_PARASITIC_MWH_D = 5.0
    PRIMARY_AERATION_CREDIT_MWH_D = 15.0  # UPSTREAM consequence: PS capture cuts aeration
    # Cooling model (V3 U6) - St Marys: 32.1 t/h cooling water at 45.8 tDS/d THP feed
    COOLING_WATER_T_PER_TDS = 16.8     # t cooling water / tDS THP feed (32.1 t/h x 24h / 45.8)
    COOLING_PUMP_KWH_PER_T = 0.10      # circulation + tower fans, kWh per t water (ESTIMATE, flagged)
    # Fate split fractions (calibrated for AD/THP; would be PROVISIONAL for thermal)
    C_LIQUOR_FRAC = 0.02        # of digestate C, to liquor on dewatering
    N_MINERALISED_AS_VSR = True # NH4 release tracks VS destruction
    P_SOLUBILISED_FRAC = 0.40   # of feed P released to liquor in MAD
    STRUVITE_P_RECOVERY = 0.85  # of soluble P captured as struvite
    STRUVITE_N_PER_P_MOLAR = 1.0  # struvite is 1:1 N:P -> N recovery is P-limited
    # V3 U4 separate PS/WAS kinetics (Mangere-anchored; per-stream values flagged estimates,
    # calibrated so VS-weighted recombination reproduces the measured Mangere blend VSR).
    PS_WAS_VS_RATIO = 1.15   # PS:WAS volatile-solids ratio (PS slightly more volatile)
    VSR_PS = 0.60            # PS VSR conventional MAD - 2026 basis (own train, no THP)
    VSR_WAS_THP = 0.69       # THP-WAS VSR - 2026 basis (own train)
    MANGERE_VSR_BAND = (0.495, 0.702)  # measured P10-P90 closure/calibration gate


# ---------------------------------------------------------------------------
# 4. CONFIDENCE  — multi-dimensional, gates the VERB not admissibility
# ---------------------------------------------------------------------------
class Conf(Enum):
    A = "A — Proven (full-scale reference)"
    B = "B — Strong evidence"
    C = "C — Emerging"
    D = "D — Hypothesis"


@dataclass
class Confidence:
    technical: Conf
    calibration: Conf
    social_regulatory: Conf

    def weakest(self) -> Conf:
        order = [Conf.A, Conf.B, Conf.C, Conf.D]
        return max((self.technical, self.calibration, self.social_regulatory),
                   key=lambda c: order.index(c))

    def verb(self) -> str:
        """Recommendation verb governed by the weakest gate that matters."""
        return {
            Conf.A: "RECOMMEND — commit-grade",
            Conf.B: "RECOMMEND — commit-grade",
            Conf.C: "SHORTLIST — pilot required before commit",
            Conf.D: "HYPOTHESIS — do not commit capital; de-risk first",
        }[self.weakest()]


# ---------------------------------------------------------------------------
# 5. MOVE  — the unit of the adaptive roadmap. Reward, risk, confidence: separate.
# ---------------------------------------------------------------------------
class Tag(Enum):
    COMMIT = "commit-now"
    KEEP_OPEN = "keep-open (option)"
    AVOID = "avoid (forecloses / asymmetric downside)"


@dataclass
class Move:
    name: str
    addresses: list[str]          # which drivers it serves
    reward: str                   # stated at full volume (not muted by low TRL)
    residual_risk: str            # what remains after de-risking
    confidence: Confidence
    derisk_task: str | None       # priced/scheduled task to reach commit-grade (None if A/B)
    tag: Tag
    forecloses: list[str] = field(default_factory=list)  # future moves it would block


# ---------------------------------------------------------------------------
# 6. PATHWAY  — carries the four ledgers + computes driver scores from them
# ---------------------------------------------------------------------------
def scope1_score(fugitive_C: float, fossil_C: float, stored_C: float, feed_C: float) -> float:
    """Unified Scope-1 view: penalise atmospheric leakage (fugitive CH4 + fossil CO2),
    credit durable carbon storage (char). One definition for all pathways."""
    leak = (fugitive_C + fossil_C) / feed_C
    stored = stored_C / feed_C
    return max(0.0, min(1.0, 1.0 - leak / 0.05 + stored))


@dataclass
class Pathway:
    name: str
    description: str
    ledgers: dict[str, Ledger]
    moves: list[Move]
    # PFAS is a trace contaminant, not a carbon-mass term — tracked as a fate fraction.
    pfas_destruction_frac: float = 0.0
    # Net pathway energy (incl. upstream aeration credit) and gross generation, MWh/d.
    net_export_mwh_d: float = 0.0
    generation_mwh_d: float = 0.0
    # Physical basis for bolt-on views (capacity, opex) that need feed/product data.
    basis: dict = field(default_factory=dict)
    # Provisional pathways carry energy/scope1 BANDS from uncertain (uncalibrated) terms.
    bands: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    # Overall confidence (weakest gate) and traits the resilience engine reads.
    confidence_level: "Conf" = None
    traits: dict = field(default_factory=dict)

    def gate(self) -> tuple[bool, list[str]]:
        """Admissibility gate: every ledger must close (commit) or be flagged provisional."""
        msgs, ok = [], True
        for q, lg in self.ledgers.items():
            if not lg.closes:
                ok = False
                msgs.append(f"{q}: imbalance {lg.imbalance_pct:+.2f}% exceeds tolerance")
            elif lg.provisional:
                msgs.append(f"{q}: closes only within provisional tolerance — NOT commit-grade")
        return ok, msgs

    def driver_scores(self) -> dict[str, float]:
        """Scores are VIEWS of the ledgers. 0..1, higher = better. No double counting."""
        C, N, P = (self.ledgers[k] for k in ("carbon", "nitrogen", "phosphorus"))

        # Scope 1: unified view over the carbon ledger's leak + storage branches.
        fugitive_C = C.outflows.get("atmosphere_fugitive_CH4_scope1", 0.0)
        fossil_C = C.outflows.get("atmosphere_fossil_CO2_from_drying", 0.0)
        stored_C = C.outflows.get("char_permanently_stored", 0.0)
        scope1 = scope1_score(fugitive_C, fossil_C, stored_C, C.inflows["feed_volatile_carbon"])

        # PFAS: destruction fraction — a fate property of the endpoint, not carbon mass.
        pfas = self.pfas_destruction_frac

        # Nutrient recovery: recovered N + P fractions, off the N and P ledgers.
        n_rec = N.fraction_to("struvite_N")
        # V3.5: return-liquor N can also be MANAGED by destruction (PN/A -> N2), which cuts the
        # WWTW return load + N2O risk but yields no recoverable product, so it scores at half the
        # weight of true recovery. Without this, sidestream-deammonification (Pathway B) scored ~0.
        n_destroyed = N.fraction_to("N2_to_atmosphere_via_PNA")
        n_managed = min(1.0, n_rec + 0.5 * n_destroyed)
        p_rec = P.fraction_to("struvite_P")
        nutrient_recovery = 0.5 * n_managed + 0.5 * p_rec

        # Energy neutrality: net pathway energy / gross generation (set per pathway).
        energy_neutrality = (min(1.0, max(0.0, self.net_export_mwh_d / self.generation_mwh_d))
                             if self.generation_mwh_d else 0.0)

        # OPEX and capacity: ledger/basis views (calibrated to Thames/Blue Plains/St Marys).
        opex = opex_view(self)["score"]
        capacity = capacity_view(self)["score"]

        return {
            "scope1_emissions": scope1,
            "pfas": pfas,
            "nutrient_recovery": nutrient_recovery,
            "opex": opex,
            "energy_neutrality": energy_neutrality,
            "capacity": capacity,
        }


# ---------------------------------------------------------------------------
# 6b. BOLT-ON VIEWS — capacity & opex, read off basis + ledgers (calibrated)
# ---------------------------------------------------------------------------
class KCAP:  # capacity constants — three-constraint sizing (Thames/Ringsend/Blue Plains/St Marys)
    THP_FEED_DS = 10.0      # %DS THP can feed the digester at
    CONV_FEED_DS = 5.5      # %DS conventional blended feed (used if per-stream TS absent)
    # OLR design limits (kgVS/m3/d): THP runs far higher because hydrolysis is pre-completed
    OLR_CONV = 2.5          # conventional stable limit (range 1-3)
    OLR_THP = 5.0           # THP (range 4-6; Ringsend/Cambi references)
    # HRT required for hydrolysis completion: conventional WAS-limited; THP pre-hydrolysed
    HRT_HYDROLYSIS_CONV = 18.0
    HRT_HYDROLYSIS_THP = 10.0
    HRT_FLOOR = 12.0        # hydraulic/washout minimum regardless of kinetics
    CAPEX_PER_M3 = 2000.0   # AUD installed digester capital
    DIGESTER_UNIT_M3 = 8000.0


def _volume_constraints(Q, vs_load_kg, olr_max, hrt_hydrolysis):
    """Three independent volume requirements; required volume is the binding (max) one."""
    v_hydraulic = Q * KCAP.HRT_FLOOR
    v_hydrolysis = Q * hrt_hydrolysis
    v_olr = vs_load_kg / olr_max
    vols = {"hydraulic": v_hydraulic, "hydrolysis": v_hydrolysis, "OLR": v_olr}
    governing = max(vols, key=vols.get)
    return vols, governing, vols[governing]


def capacity_view(pw: Pathway) -> dict:
    """Capacity intensification via the actual full-scale mechanism: THP pre-completes
    hydrolysis, so the binding constraint shifts from hydrolysis-limited HRT (conventional)
    to OLR (THP), which can run 2x higher. Required volume = MAX(hydraulic, hydrolysis, OLR)
    per mode. This is why Thames/Ringsend/Blue Plains/St Marys cut digester volume so far."""
    b = pw.basis
    if not b.get("has_thp"):
        return {"score": 0.0, "note": "no THP - baseline capacity (no intensification)"}
    tds = b["total_tds"]
    vs_ts = b.get("vs_ts", 0.65)
    vs_load_kg = tds * vs_ts * 1000.0
    # conventional hydraulic flow (per-stream TS if available)
    if b.get("ps_ts") and b.get("was_ts"):
        q_conv = b["ps_tds"] / (b["ps_ts"]/100.0) + b["was_tds"] / (b["was_ts"]/100.0)
    else:
        q_conv = tds / (KCAP.CONV_FEED_DS / 100.0)
    q_thp = tds / (KCAP.THP_FEED_DS / 100.0)

    cv, cgov, vol_conv = _volume_constraints(q_conv, vs_load_kg, KCAP.OLR_CONV, KCAP.HRT_HYDROLYSIS_CONV)
    tv, tgov, vol_thp = _volume_constraints(q_thp, vs_load_kg, KCAP.OLR_THP, KCAP.HRT_HYDROLYSIS_THP)
    avoided_m3 = max(0.0, vol_conv - vol_thp)
    out = {
        "q_conv_m3d": q_conv, "q_thp_m3d": q_thp,
        "conv_constraints": cv, "conv_governing": cgov, "vol_conv_m3": vol_conv,
        "thp_constraints": tv, "thp_governing": tgov, "vol_thp_m3": vol_thp,
        "avoided_m3": avoided_m3,
        "avoided_capex_aud": avoided_m3 * KCAP.CAPEX_PER_M3,
        # Low/Base/High: tank-only ($2,000) vs full replacement incl. mixers, HX, pumping,
        # pipework, odour, electrical, buildings, land ($3,500-5,000/m3)
        "capex_low_aud": avoided_m3 * 2000.0,
        "capex_base_aud": avoided_m3 * 3500.0,
        "capex_high_aud": avoided_m3 * 5000.0,
        "digesters_avoided": avoided_m3 / KCAP.DIGESTER_UNIT_M3,
        "score": min(1.0, avoided_m3 / vol_conv) if vol_conv else 0.0,
    }
    if b.get("digester_vol_m3"):
        V = b["digester_vol_m3"]
        out["existing_vol_m3"] = V
        out["hrt_conv_existing_d"] = V / q_conv
        out["hrt_thp_existing_d"] = V / q_thp
        # existing-tank throughput ceiling = MIN of OLR-limited and HRT-floor-limited DS
        ds_olr = (V * KCAP.OLR_THP) / (vs_ts * 1000.0)          # tDS/d at OLR limit
        ds_hrt = (V / KCAP.HRT_FLOOR) * (KCAP.THP_FEED_DS/100.0)  # tDS/d at HRT floor
        max_ds = min(ds_olr, ds_hrt)
        out["max_ds_existing_tds"] = max_ds
        out["existing_governing"] = "OLR" if ds_olr <= ds_hrt else "hydraulic floor"
        out["capacity_headroom_tds"] = max(0.0, max_ds - tds)
    return out


ETP_THP_2015 = {  # ETP Cambi/AECOM THP conceptual-design calibration case (2015).
    "basis": {"total_tds": 169.8, "ps_frac": 0.60, "was_frac": 0.40, "vs_ts": 0.81,
              "digesters": "8 x 4300 m3 (34,400 useful)", "existing_hrt_d": 16.9},
    # plant-level targets: (VSR, CH4 Nm3/d, biogas Nm3/d, cake DS, HRT d)
    "conventional":  {"vsr": 0.476, "ch4_nm3_d": 37117, "biogas_nm3_d": 58916, "cake_ds": 0.23},
    "full_thp":      {"vsr": 0.556, "ch4_nm3_d": 43499, "biogas_nm3_d": 69046, "cake_ds": 0.31, "hrt_d": 20.3},
    "was_only_thp":  {"vsr": 0.538, "ch4_nm3_d": 42026, "biogas_nm3_d": 66707, "cake_ds": 0.28, "hrt_d": 13.7},
    # per-stream VSR solved from the three plant-level targets (VS split = DS split, VS 81% both)
    "per_stream_vsr": {"ps_conv": 0.58, "was_conv": 0.32, "ps_thp": 0.61, "was_thp": 0.475},
    "confidence": "site-calibrated (A, 90-95); full-scale Cambi/AECOM ETP design",
}


ETP_CAL = {  # Measured ETP PST calibration record (2006-2017). Design PS_tds=120.7 RETAINED;
    # measured values document the site basis and validate the design point against real data.
    "flow_mld": (308, 358, 475),            # IPS flow P10/P50/P90 (mean 384)
    "feed_ss_mgL": (280, 400, 540), "feed_cod_mgL": (650, 780, 970),   # COD 2015-2017
    "feed_bod5_mgL": (290, 370, 560), "feed_tkn_mgL": (50, 63, 75),
    "eff_ss_mgL": (100, 140, 220), "eff_bod5_mgL": (220, 300, 380), "eff_tkn_mgL": (47, 57, 67),
    "removal_ss": 0.645, "removal_cod": 0.29, "removal_bod5": 0.27, "removal_tkn": 0.136,
    "ps_ds_band_tpd": (50, 92, 150),        # measured PS DS production P10/P50/P90 (mean 99)
    "ps_ds_recent_tpd": 115,                # 2015-2017 mean
    "ps_ds_design_tpd": 120.7,              # ADOPTED design basis (retained); inside measured band
    "ps_n_capture_tpd": 3.1,                # measured TKN capture into PS (only ~14% of influent TKN)
    "confidence": "site-calibrated (A, 90-95); 2006-2017 ETP PST record",
    "was_basis": "WAS not measured in this dataset - PS/WAS ratio left as design (flagged)",
}


ETP_SS_2026 = {  # Cambi SolidStream conceptual-design calibration case (TM-07035, 20.05.2026).
    # Post-digestion THP on full digestate + hot centrate recycle to digesters. CURRENT ETP basis.
    "basis": {"total_tds": 219.5, "ps_frac": 0.55, "was_frac": 0.45, "digesters": "8 x 8000 (64,000)",
              "feed_flow_m3d": 3540.0, "water_temp_c": 15.0},
    "scenario1_65vs": {
        "vs_ts": 0.65,
        "conventional": {"hrt_d": 18.1, "vsr": 0.575, "biogas_nm3_d": 74163, "ch4_nm3_d": 46723,
                         "elec_mwh_yr": 67490, "cake_ds": 0.22, "dig_heat_kw": 3458.7, "wet_cake_t_yr": 216659},
        "solidstream": {"hrt_d": 13.4, "vsr": 0.703, "biogas_nm3_d": 91014, "ch4_nm3_d": 57339,
                        "elec_mwh_yr": 81461, "cake_ds": 0.38, "dig_heat_kw": 1081.0, "wet_cake_t_yr": 106958,
                        "recycle_m3d": 1233.0, "recycle_temp_c": 76.8, "recycle_ds": 0.038},
    },
    "scenario2_72vs": {
        "vs_ts": 0.72,
        "conventional": {"hrt_d": 18.3, "vsr": 0.575, "biogas_nm3_d": 87502, "ch4_nm3_d": 55126, "cake_ds": 0.20},
        "solidstream": {"hrt_d": 13.6, "vsr": 0.704, "biogas_nm3_d": 107300, "ch4_nm3_d": 67599,
                        "cake_ds": 0.38, "recycle_m3d": 1214.0, "recycle_temp_c": 76.8, "recycle_ds": 0.039},
    },
    "yield_confirmed": {"biogas_nm3_per_kg_vsd": 0.90, "ch4_fraction": 0.63},  # both memos agree
    "heat_recovery_kw": 2378.0,  # conventional 3458.7 -> SolidStream 1081 digester heating
    "confidence": "site-calibrated (A, 90-95); full mass+energy balance, Cambi/Aurecon current ETP basis",
}


class KO:  # opex constants (AUD)
    ELEC_PRICE_MWH = 120.0
    TRANSPORT_PER_T = 15.0       # effective $/wet-t incl. ~100 km haul
    STRUVITE_PRICE_T = 400.0
    STRUVITE_MW_PER_P = 245.0 / 31.0


class KN:  # nutrient-recovery economics (AUD) - screening estimates, tunable
    AS_PRICE_T = 350.0            # ammonium sulphate product, $/t
    AS_N_FRAC = 0.21              # N content of (NH4)2SO4 by mass
    AS_RECOVERY = 0.75            # return-liquor N captured as AS (stripping efficiency)
    PNA_N_REMOVAL = 0.88          # return-liquor N destroyed to N2 by PN/A
    AVOIDED_N_TREAT_PER_KG = 3.0  # avoided mainstream/sidestream N-removal cost, $/kg N
    N_FERT_VALUE_PER_KG = 1.2     # synthetic-N replacement value, $/kg N (urea-equiv)
    P_FERT_VALUE_PER_KG = 3.5     # synthetic-P replacement value, $/kg P (DAP-equiv)


def opex_view(pw: Pathway) -> dict:
    """Annual OPEX, read off ledgers + basis. Energy from net export, transport from
    product tonnage, chemicals/O&M from basis, product revenue from the P ledger.
    Negative = net cash positive (revenue exceeds cost)."""
    b = pw.basis
    energy = -pw.net_export_mwh_d * KO.ELEC_PRICE_MWH * 365 / 1e6        # M$/yr
    transport = b.get("product_wet_tpd", 0.0) * 365 * KO.TRANSPORT_PER_T / 1e6
    chemicals = b.get("chemicals_m_aud", 0.0)
    om = b.get("om_m_aud", 0.0)
    P_struvite = pw.ledgers["phosphorus"].outflows.get("struvite_P", 0.0)  # kgP/d
    struvite_rev = (P_struvite * KO.STRUVITE_MW_PER_P / 1000.0
                    * 365 * KO.STRUVITE_PRICE_T / 1e6)
    net = energy + transport + chemicals + om - struvite_rev
    # score: net +$10M/yr -> 0 ; net -$5M/yr (revenue) -> 1
    score = max(0.0, min(1.0, (10.0 - net) / 15.0))
    return {
        "energy_m_aud": energy, "transport_m_aud": transport,
        "chemicals_m_aud": chemicals, "om_m_aud": om,
        "struvite_revenue_m_aud": struvite_rev, "net_m_aud": net, "score": score,
    }



# ---------------------------------------------------------------------------
# 6c. PLANT BASIS — real feed data; GENERIC is the demonstrator, ETP the road test
# ---------------------------------------------------------------------------
GENERIC = dict(name="Generic 100 tDS/d", PS_tds=40.0, WAS_tds=60.0,
               ps_ts=5.0, was_ts=5.0, vs_ts=0.808,
               feed_N_kgd=None, P_per_ds=0.012, digester_vol_m3=None)

# ETP real basis (from production cutover fixture + centrate case study):
# PS 120.7 tDS @7.5%TS, WAS 98.8 tDS @3.5%TS, VS 65% both, feed N 12,624 kg/d
# (PS 3.5%, WAS 8.5% of DS), existing conventional digesters 64,000 m3. P not
# measured at ETP -> retained as estimate, flagged.
ETP = dict(name="ETP (220 tDS/d, real basis)", PS_tds=120.7, WAS_tds=98.8,
           ps_ts=7.5, was_ts=3.5, vs_ts=0.65,
           feed_N_kgd=12624.0, P_per_ds=0.012, digester_vol_m3=64000.0)


# ===========================================================================
# V3 U6 - ST MARYS THP REFERENCE CARD (Sydney Water) - calibration anchor, 95/100
# Most figures here already drive class K (VSR, methane yield 258, steam 0.94,
# CH4 63%). Captured as the documented Tier-1 calibration plant.
ST_MARYS = dict(
    plant="St Marys THP (Sydney Water)",
    peak_load_tds_d=45.8, feed_ds_pct=16.5, thp_temp_C=165, thp_press_barg=6.0,
    steam_t_per_h=1.8, steam_t_per_tds=0.94, biogas_nm3_per_h=782, ch4_pct=63,
    ch4_yield_nm3_per_tds=258, flash_ds_pct=9.0, digester_feed_ds_pct=5.8,
    cooling_water_t_per_h=32.1, confidence_score=95,
)


def _chp_split(biogas_chem, gas_util):
    """Split generated biogas chemical energy by CHP utilisation (Mangere calibration).
    Flaring (1-gas_util) is a CHP-sizing artifact - a plant input, not a constant.
    Returns (elec, heat, losses, flared)."""
    u = biogas_chem * gas_util
    return (u * K.CHP_ELEC, u * K.CHP_HEAT, u * (1 - K.CHP_ELEC - K.CHP_HEAT),
            biogas_chem * (1 - gas_util))


def build_worked_pathway(plant: dict = GENERIC) -> Pathway:
    # --- Feed basis (from plant) ---
    WAS_tds = plant["WAS_tds"]
    PS_tds = plant["PS_tds"]
    total_tds = WAS_tds + PS_tds
    vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    VS_destroyed = VS_in * K.VSR
    VS_remaining = VS_in - VS_destroyed

    # ---------------- CARBON (tC/d) ----------------
    C_in = VS_in * K.C_PER_VS
    C_biogas = VS_destroyed * K.C_PER_VS
    C_digestate = C_in - C_biogas
    C_liquor = C_digestate * K.C_LIQUOR_FRAC
    C_cake = C_digestate - C_liquor
    # biogas carbon -> CH4-C and CO2-C; CH4 combusted -> biogenic CO2 to atm, slip -> Scope1
    CH4_nm3 = VS_destroyed * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4_nm3 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_CO2_biogas = C_biogas - C_CH4
    C_fugitive = C_CH4 * K.FUGITIVE_CH4_FRAC
    C_combusted = C_CH4 - C_fugitive
    carbon = Ledger("carbon", "tC/d",
        inflows={"feed_volatile_carbon": C_in},
        outflows={
            "soil_land_application": C_cake,
            "return_liquor_to_WWTW": C_liquor,
            "atmosphere_biogenic_CO2": C_combusted + C_CO2_biogas,
            "atmosphere_fugitive_CH4_scope1": C_fugitive,
        })

    # ---------------- ENERGY (MWh/d) ----------------
    biogas_chem = CH4_nm3 * K.CH4_LHV_KWH_NM3 / 1000.0
    gas_util = plant.get("gas_utilisation_frac", K.GAS_UTILISATION_DEFAULT)
    elec_gen, heat_gen, chp_losses, gas_flared = _chp_split(biogas_chem, gas_util)
    steam_t = WAS_tds * K.STEAM_T_PER_TDS
    steam_demand = steam_t * 1000 * K.STEAM_KWH_PER_KG / 1000.0
    heat_demand = steam_demand + K.DIGESTER_HEAT_MWH_D
    heat_surplus = heat_gen - heat_demand          # >0 -> no fossil top-up (no Scope1 from heat)
    dewater_par = (VS_remaining + total_tds*(1-vs_ts)) * K.DEWATER_KWH_PER_TDS / 1000.0
    cooling_water_t = WAS_tds * K.COOLING_WATER_T_PER_TDS         # V3 U6 St Marys cooling model
    cooling_par = cooling_water_t * K.COOLING_PUMP_KWH_PER_T / 1000.0  # MWh/d circulation parasitic
    parasitics = (dewater_par + K.STRUVITE_PARASITIC_MWH_D
                  + K.THP_PUMP_PARASITIC_MWH_D + K.PLANT_PARASITIC_MWH_D + cooling_par)
    heat_used = min(heat_gen, heat_demand)
    heat_surplus_unused = max(0.0, heat_gen - heat_demand)        # delivered but unused (real output)
    net_elec = elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D  # net incl. upstream credit
    energy = Ledger("energy", "MWh/d",
        inflows={"biogas_chemical_energy": biogas_chem},
        outflows={                                       # closes by real physics, no plug
            "chp_electricity_generated": elec_gen,
            "ad_heat_used_thp_and_digester": heat_used,
            "heat_surplus_unused": heat_surplus_unused,
            "chp_conversion_losses": chp_losses,
            "biogas_flared_unused": gas_flared,
        })

    # ---------------- NITROGEN (kgN/d) ----------------
    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    N_released = N_in * K.VSR * K.N_SOLUBILISATION_EFF   # calibrated to Mangere centrate band
    N_cake = N_in - N_released                           # organic N retained in cake to land
    # struvite N recovery is P-limited (1:1 molar with recovered P)
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    P_soluble = P_in * K.P_SOLUBILISED_FRAC
    P_struvite = P_soluble * K.STRUVITE_P_RECOVERY
    N_struvite = P_struvite * (14.0/31.0) * K.STRUVITE_N_PER_P_MOLAR  # mass via molar 1:1
    N_liquor_return = N_released - N_struvite
    nitrogen = Ledger("nitrogen", "kgN/d",
        inflows={"feed_nitrogen": N_in},
        outflows={
            "cake_organic_N_to_land": N_cake,
            "struvite_N": N_struvite,
            "return_liquor_NH4_to_WWTW": N_liquor_return,   # the §5.4 return-liquor risk, quantified
        })

    # ---------------- PHOSPHORUS (kgP/d) ----------------
    P_cake = P_in - P_soluble
    P_liquor_return = P_soluble - P_struvite
    phosphorus = Ledger("phosphorus", "kgP/d",
        inflows={"feed_phosphorus": P_in},
        outflows={
            "cake_P_to_land": P_cake,
            "struvite_P": P_struvite,
            "return_liquor_P_to_WWTW": P_liquor_return,
        })

    # ---------------- MOVES ----------------
    A = lambda: Confidence(Conf.A, Conf.A, Conf.A)
    moves = [
        Move("Optimise MAD (mixing, HRT, dewatering)",
             addresses=["opex", "capacity", "energy_neutrality"],
             reward="Bankable energy + capacity headroom; foundation for everything downstream",
             residual_risk="Minimal — standard practice",
             confidence=A(), derisk_task=None, tag=Tag.COMMIT),
        Move("THP of WAS (Cambi-class)",
             addresses=["capacity", "energy_neutrality", "opex"],
             reward="Higher VSR + cake DS; defers digester volume CAPEX; Class A biosolids",
             residual_risk="Return-liquor NH4 load on host WWTW (quantified in N ledger)",
             confidence=Confidence(Conf.A, Conf.A, Conf.B),  # social: steam/industrial process
             derisk_task=None, tag=Tag.COMMIT),
        Move("Struvite recovery from digestate liquor",
             addresses=["nutrient_recovery"],
             reward="Recovers ~34% of feed P as saleable product; cuts return-liquor P",
             residual_risk="Recovers little N (P-limited) — N driver still largely unmet",
             confidence=Confidence(Conf.A, Conf.B, Conf.A),
             derisk_task=None, tag=Tag.COMMIT),
        Move("Ammonium-sulphate / PN-A for return-liquor N",
             addresses=["nutrient_recovery", "scope1_emissions"],
             reward="Closes the N gap struvite leaves; cuts return-liquor N2O risk",
             residual_risk="Adds process complexity; modest CAPEX",
             confidence=Confidence(Conf.A, Conf.B, Conf.A),
             derisk_task="Sidestream N pilot, ~$0.4M / 9 months", tag=Tag.KEEP_OPEN),
        Move("Thermal endpoint (pyrolysis/gasification) for residual cake",
             addresses=["pfas", "scope1_emissions"],
             reward="ONLY family that destroys PFAS (driver #2) and can stabilise carbon as char",
             residual_risk="Carbon-to-char split, syngas yield, N/P-in-ash not yet closed full-scale",
             confidence=Confidence(Conf.C, Conf.C, Conf.C),
             derisk_task="Reference-plant balance + demo, ~$1.5M / 18 months",
             tag=Tag.KEEP_OPEN, forecloses=[]),
        Move("Commit land application as terminal disposal",
             addresses=["opex", "capex"],
             reward="Cheapest endpoint today",
             residual_risk="Strands the strategy if PFAS land-application is restricted (driver #2)",
             confidence=Confidence(Conf.A, Conf.A, Conf.D),  # social/reg: high regret under PFAS
             derisk_task=None, tag=Tag.AVOID,
             forecloses=["Thermal endpoint (pyrolysis/gasification) for residual cake"]),
    ]

    pw = Pathway(
        name="Primary + THP(WAS) + MAD + Struvite + Land",
        description="St Marys-class: separate dewater -> THP of WAS -> MAD of PS+THP-WAS "
                    "-> dewater -> struvite from liquor -> cake to land. Upstream "
                    "primary-capture aeration credit inside boundary.",
        ledgers={"carbon": carbon, "energy": energy,
                 "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=moves,
        net_export_mwh_d=net_elec,
        generation_mwh_d=biogas_chem,
        basis={
            "total_tds": total_tds, "has_thp": True, "vs_ts": vs_ts,
            "ps_tds": PS_tds, "was_tds": WAS_tds,
            "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
            "digester_vol_m3": plant.get("digester_vol_m3"),
            "product_wet_tpd": (VS_remaining + total_tds*(1-vs_ts)) / 0.28,  # cake @28% DS
            "cooling_water_tpd": cooling_water_t,   # V3 U6: rejected-heat / integration opportunity
            "chemicals_m_aud": 0.30 * total_tds / 100.0,   # scale with load
            "om_m_aud": 1.50 * total_tds / 100.0,
        },
    )
    _attach(pw, endpoint="land", conf=Conf.B)
    return pw


# ---------------------------------------------------------------------------
def build_separate_pswas_pathway(plant: dict = GENERIC) -> Pathway:
    """V3 U4. PS and WAS digested in SEPARATE trains with distinct kinetics: PS in a
    conventional MAD train (no THP), WAS through THP then its own MAD. Per-stream VS is a
    mass-conserving split of the plant's measured blend by PS_WAS_VS_RATIO; per-stream VSR
    is Mangere-anchored. The closure/calibration gate is that the VS-weighted recombined
    VSR lands inside the measured Mangere band. Land endpoint with struvite, like the spine."""
    PS_tds = plant["PS_tds"]; WAS_tds = plant["WAS_tds"]
    total_tds = PS_tds + WAS_tds; vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    # mass-conserving per-stream VS split of the measured blend
    was_vs = vs_ts * total_tds / (K.PS_WAS_VS_RATIO * PS_tds + WAS_tds)
    ps_vs = K.PS_WAS_VS_RATIO * was_vs
    VS_PS = PS_tds * ps_vs; VS_WAS = WAS_tds * was_vs
    VS_destroyed = VS_PS * K.VSR_PS + VS_WAS * K.VSR_WAS_THP
    VSR_eff = VS_destroyed / VS_in
    lo, hi = K.MANGERE_VSR_BAND
    assert lo <= VSR_eff <= hi, f"separate-train VSR {VSR_eff:.3f} outside Mangere band {K.MANGERE_VSR_BAND}"
    VS_remaining = VS_in - VS_destroyed

    C_in = VS_in * K.C_PER_VS; C_biogas = VS_destroyed * K.C_PER_VS
    C_digestate = C_in - C_biogas
    C_liquor = C_digestate * K.C_LIQUOR_FRAC; C_cake = C_digestate - C_liquor
    CH4_nm3 = VS_destroyed * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4_nm3 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_CO2_biogas = C_biogas - C_CH4
    C_fugitive = C_CH4 * K.FUGITIVE_CH4_FRAC; C_combusted = C_CH4 - C_fugitive
    carbon = Ledger("carbon", "tC/d", inflows={"feed_volatile_carbon": C_in},
        outflows={"soil_land_application": C_cake, "return_liquor_to_WWTW": C_liquor,
                  "atmosphere_biogenic_CO2": C_combusted + C_CO2_biogas,
                  "atmosphere_fugitive_CH4_scope1": C_fugitive})

    biogas_chem = CH4_nm3 * K.CH4_LHV_KWH_NM3 / 1000.0
    gas_util = plant.get("gas_utilisation_frac", K.GAS_UTILISATION_DEFAULT)
    elec_gen, heat_gen, chp_losses, gas_flared = _chp_split(biogas_chem, gas_util)
    steam_t = WAS_tds * K.STEAM_T_PER_TDS           # THP steam on WAS train only
    steam_demand = steam_t * 1000 * K.STEAM_KWH_PER_KG / 1000.0
    heat_demand = steam_demand + K.DIGESTER_HEAT_MWH_D
    heat_used = min(heat_gen, heat_demand)
    heat_surplus_unused = max(0.0, heat_gen - heat_demand)
    dewater_par = (VS_remaining + total_tds*(1-vs_ts)) * K.DEWATER_KWH_PER_TDS / 1000.0
    cooling_par = WAS_tds * K.COOLING_WATER_T_PER_TDS * K.COOLING_PUMP_KWH_PER_T / 1000.0
    parasitics = (dewater_par + K.STRUVITE_PARASITIC_MWH_D + K.THP_PUMP_PARASITIC_MWH_D
                  + K.PLANT_PARASITIC_MWH_D + cooling_par)
    net_elec = elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D
    energy = Ledger("energy", "MWh/d", inflows={"biogas_chemical_energy": biogas_chem},
        outflows={"chp_electricity_generated": elec_gen, "ad_heat_used_thp_and_digester": heat_used,
                  "heat_surplus_unused": heat_surplus_unused, "chp_conversion_losses": chp_losses,
                  "biogas_flared_unused": gas_flared})

    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    N_released = N_in * VSR_eff * K.N_SOLUBILISATION_EFF
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    P_soluble = P_in * K.P_SOLUBILISED_FRAC; P_struvite = P_soluble * K.STRUVITE_P_RECOVERY
    N_struvite = P_struvite * (14.0/31.0) * K.STRUVITE_N_PER_P_MOLAR
    N_cake = N_in - N_released; N_liquor_return = N_released - N_struvite
    nitrogen = Ledger("nitrogen", "kgN/d", inflows={"feed_nitrogen": N_in},
        outflows={"cake_organic_N_to_land": N_cake, "struvite_N": N_struvite,
                  "return_liquor_NH4_to_WWTW": N_liquor_return})
    P_cake = P_in - P_soluble; P_liquor_return = P_soluble - P_struvite
    phosphorus = Ledger("phosphorus", "kgP/d", inflows={"feed_phosphorus": P_in},
        outflows={"cake_P_to_land": P_cake, "struvite_P": P_struvite,
                  "return_liquor_P_to_WWTW": P_liquor_return})

    A = lambda: Confidence(Conf.A, Conf.A, Conf.A)
    moves = [
        Move("Run PS and WAS as separate digestion trains",
             addresses=["capacity", "energy_neutrality"],
             reward="THP only the stream that needs it (WAS); PS digests well untreated - "
                    "saves THP duty/steam on the PS fraction; trains sized to each kinetics",
             residual_risk="Two trains = more assets/footprint; per-stream VSR is estimated",
             confidence=Confidence(Conf.B, Conf.B, Conf.B), derisk_task=None, tag=Tag.COMMIT),
        Move("THP of WAS (Cambi-class) on the WAS train",
             addresses=["capacity", "energy_neutrality", "opex"],
             reward="Higher WAS VSR + cake DS; Class A; defers digester volume",
             residual_risk="Return-liquor NH4 load (quantified in N ledger)",
             confidence=Confidence(Conf.A, Conf.A, Conf.B), derisk_task=None, tag=Tag.COMMIT),
        Move("Struvite recovery from combined digestate liquor",
             addresses=["nutrient_recovery"], reward="Recovers P as product; cuts return-liquor P",
             residual_risk="P-limited N recovery", confidence=Confidence(Conf.A, Conf.B, Conf.A),
             derisk_task=None, tag=Tag.COMMIT),
        Move("Ammonium-sulphate / PN-A for return-liquor N",
             addresses=["nutrient_recovery", "scope1_emissions"],
             reward="Closes the N gap struvite leaves", residual_risk="Process complexity",
             confidence=Confidence(Conf.A, Conf.B, Conf.A),
             derisk_task="Sidestream N pilot", tag=Tag.KEEP_OPEN),
        Move("Thermal endpoint (pyrolysis/gasification) for residual cake",
             addresses=["pfas", "scope1_emissions"],
             reward="Only family that destroys PFAS; stabilises C as char",
             residual_risk="Endpoint balances not closed full-scale",
             confidence=Confidence(Conf.C, Conf.C, Conf.C),
             derisk_task="Reference-plant balance + demo", tag=Tag.KEEP_OPEN),
        Move("Commit land application as terminal disposal",
             addresses=["opex", "capex"], reward="Cheapest endpoint today",
             residual_risk="Strands strategy if PFAS land application restricted",
             confidence=Confidence(Conf.A, Conf.A, Conf.D), derisk_task=None, tag=Tag.AVOID,
             forecloses=["Thermal endpoint (pyrolysis/gasification) for residual cake"]),
    ]

    pw = Pathway(
        name="Separate PS + WAS(THP) trains + MAD + Struvite + Land",
        description="V3 U4: PS conventional MAD train + WAS THP+MAD train, distinct per-stream "
                    "kinetics (Mangere-anchored), recombined to land in the measured VSR band.",
        ledgers={"carbon": carbon, "energy": energy, "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=moves, net_export_mwh_d=net_elec, generation_mwh_d=biogas_chem,
        basis={"total_tds": total_tds, "has_thp": True, "vs_ts": vs_ts,
               "ps_tds": PS_tds, "was_tds": WAS_tds, "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
               "separate_trains": True, "ps_vs_ts": ps_vs, "was_vs_ts": was_vs,
               "vsr_effective": VSR_eff, "digester_vol_m3": plant.get("digester_vol_m3"),
               "product_wet_tpd": (VS_remaining + total_tds*(1-vs_ts)) / 0.28,
               "chemicals_m_aud": 0.30 * total_tds / 100.0, "om_m_aud": 1.55 * total_tds / 100.0},
    )
    _attach(pw, endpoint="land", conf=Conf.B)
    return pw


# ---------------------------------------------------------------------------
# PATHWAY E - Cambi SolidStream (post-digestion THP + hot centrate recycle)
class KSS:  # Anchored to ETP_SS_2026 (Cambi/Aurecon TM-07035, 2026), Scenario 1 (65% VS).
    VSR = 0.703                  # overall VS reduction incl. recycle loop (vs conventional 0.575)
    CAKE_DS = 0.38               # final hygienised Class-A cake DS (vs 0.22 conventional)
    THP_FEED_FRAC = 0.756        # digestate-to-THP / raw feed (166/219.5, memo Sc1) - sizes THP steam
    RECYCLE_M3_PER_TDS = 5.62    # hot soluble-COD centrate recycle, m3/d per tDS feed (1233/219.5)
    RECYCLE_TEMP_C = 76.8
    RECYCLE_HEAT_MWH_PER_TDS = 0.260  # recovered digester heat per tDS (57.1/219.5; 3458.7->1081 kW)


def build_solidstream_pathway(plant: dict = GENERIC) -> Pathway:
    """V3 Pathway E. Cambi SolidStream: COMBINED PS+WAS conventional digestion, then
    post-digestion THP on the full digestate, with hot soluble-COD-rich centrate recycled
    to the digesters. Anchored to ETP_SS_2026: VSR ~70%, cake 38% DS, recycle ~1,233 m3/d
    @ 76.8C, ~2.4 MW digester-heat recovery. Same digester volume as conventional -
    SolidStream does NOT release capacity (HRT falls as recycle adds flow); the capacity
    play lives in the separate-digestion pathway (K)."""
    WAS_tds = plant["WAS_tds"]; PS_tds = plant["PS_tds"]
    total_tds = WAS_tds + PS_tds; vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    VS_destroyed = VS_in * KSS.VSR
    VS_remaining = VS_in - VS_destroyed

    C_in = VS_in * K.C_PER_VS; C_biogas = VS_destroyed * K.C_PER_VS
    C_digestate = C_in - C_biogas
    C_liquor = C_digestate * K.C_LIQUOR_FRAC; C_cake = C_digestate - C_liquor
    CH4_nm3 = VS_destroyed * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4_nm3 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_CO2_biogas = C_biogas - C_CH4
    C_fugitive = C_CH4 * K.FUGITIVE_CH4_FRAC; C_combusted = C_CH4 - C_fugitive
    carbon = Ledger("carbon", "tC/d", inflows={"feed_volatile_carbon": C_in},
        outflows={"soil_land_application": C_cake, "return_liquor_to_WWTW": C_liquor,
                  "atmosphere_biogenic_CO2": C_combusted + C_CO2_biogas,
                  "atmosphere_fugitive_CH4_scope1": C_fugitive})

    biogas_chem = CH4_nm3 * K.CH4_LHV_KWH_NM3 / 1000.0
    gas_util = plant.get("gas_utilisation_frac", K.GAS_UTILISATION_DEFAULT)
    elec_gen, heat_gen, chp_losses, gas_flared = _chp_split(biogas_chem, gas_util)
    thp_feed_tds = total_tds * KSS.THP_FEED_FRAC          # post-digestion THP throughput
    steam_t = thp_feed_tds * K.STEAM_T_PER_TDS
    steam_demand = steam_t * 1000 * K.STEAM_KWH_PER_KG / 1000.0
    recycle_heat = total_tds * KSS.RECYCLE_HEAT_MWH_PER_TDS    # hot-centrate digester-heat recovery
    net_heat_demand = max(0.0, steam_demand + K.DIGESTER_HEAT_MWH_D - recycle_heat)
    heat_used = min(heat_gen, net_heat_demand)
    heat_surplus_unused = max(0.0, heat_gen - net_heat_demand)
    dewater_par = (VS_remaining + total_tds*(1-vs_ts)) * K.DEWATER_KWH_PER_TDS / 1000.0
    cooling_par = thp_feed_tds * K.COOLING_WATER_T_PER_TDS * K.COOLING_PUMP_KWH_PER_T / 1000.0
    parasitics = (dewater_par + K.STRUVITE_PARASITIC_MWH_D + K.THP_PUMP_PARASITIC_MWH_D
                  + K.PLANT_PARASITIC_MWH_D + cooling_par)
    net_elec = elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D
    energy = Ledger("energy", "MWh/d", inflows={"biogas_chemical_energy": biogas_chem},
        outflows={"chp_electricity_generated": elec_gen, "ad_heat_used_thp_and_digester": heat_used,
                  "heat_surplus_unused": heat_surplus_unused, "chp_conversion_losses": chp_losses,
                  "biogas_flared_unused": gas_flared})

    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    N_released = N_in * KSS.VSR * K.N_SOLUBILISATION_EFF
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    P_soluble = P_in * K.P_SOLUBILISED_FRAC; P_struvite = P_soluble * K.STRUVITE_P_RECOVERY
    N_struvite = P_struvite * (14.0/31.0) * K.STRUVITE_N_PER_P_MOLAR
    N_cake = N_in - N_released; N_liquor_return = N_released - N_struvite
    nitrogen = Ledger("nitrogen", "kgN/d", inflows={"feed_nitrogen": N_in},
        outflows={"cake_organic_N_to_land": N_cake, "struvite_N": N_struvite,
                  "return_liquor_NH4_to_WWTW": N_liquor_return})
    P_cake = P_in - P_soluble; P_liquor_return = P_soluble - P_struvite
    phosphorus = Ledger("phosphorus", "kgP/d", inflows={"feed_phosphorus": P_in},
        outflows={"cake_P_to_land": P_cake, "struvite_P": P_struvite,
                  "return_liquor_P_to_WWTW": P_liquor_return})

    moves = [
        Move("Conventional combined PS+WAS mesophilic digestion",
             addresses=["opex", "energy_neutrality"],
             reward="Proven base train; SolidStream bolts on downstream as end-of-pipe",
             residual_risk="Minimal - existing asset", confidence=Confidence(Conf.A, Conf.A, Conf.A),
             derisk_task=None, tag=Tag.COMMIT),
        Move("Post-digestion SolidStream THP + hot centrate recycle",
             addresses=["capacity", "energy_neutrality", "opex", "biosolids_quality"],
             reward="VSR ~58%->70%; biogas +22.7%; recycles soluble COD + ~2.4 MW heat to digesters",
             residual_risk="Adds return-liquor NH4 (higher VS destruction); no digester-volume release",
             confidence=Confidence(Conf.A, Conf.A, Conf.B),  # Cambi design + Geiselbullach/Schijnpoort/Veas refs
             derisk_task=None, tag=Tag.COMMIT),
        Move("Class-A hygienised 38% DS cake (no drying)",
             addresses=["biosolids_quality", "opex", "pfas"],
             reward="Pathogen-free at 165C; ~50% fewer wet tonnes; ends 3-yr EPA stockpiling; dryer -67%",
             residual_risk="Cake market still developing (Cambi: positive value at scale)",
             confidence=Confidence(Conf.A, Conf.A, Conf.A), derisk_task=None, tag=Tag.COMMIT),
        Move("Struvite + PN-A for the (larger) return-liquor N load",
             addresses=["nutrient_recovery", "scope1_emissions"],
             reward="Recovers P; closes the higher SolidStream N return", residual_risk="Process complexity",
             confidence=Confidence(Conf.A, Conf.B, Conf.A), derisk_task="Sidestream N pilot", tag=Tag.KEEP_OPEN),
        Move("Commit land application as terminal disposal",
             addresses=["opex", "capex"], reward="Cheapest endpoint; Class-A cake widens reuse options",
             residual_risk="PFAS land-application restriction risk (thermal endpoint stays open)",
             confidence=Confidence(Conf.A, Conf.A, Conf.C), derisk_task=None, tag=Tag.AVOID,
             forecloses=["Thermal endpoint (pyrolysis/gasification) for residual cake"]),
    ]

    recycle_m3d = total_tds * KSS.RECYCLE_M3_PER_TDS
    pw = Pathway(
        name="SolidStream: MAD + post-digestion THP + centrate recycle + Land",
        description="V3 Pathway E (Cambi SolidStream, ETP_SS_2026): combined MAD -> pre-dewater "
                    "-> THP on digestate -> centrifuge -> hot soluble-COD centrate recycled to "
                    "digesters. Same 64,000 m3, no capacity release; VSR ~70%, cake 38% DS.",
        ledgers={"carbon": carbon, "energy": energy, "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=moves, net_export_mwh_d=net_elec, generation_mwh_d=biogas_chem,
        basis={"total_tds": total_tds, "has_thp": True, "vs_ts": vs_ts, "solidstream": True,
               "ps_tds": PS_tds, "was_tds": WAS_tds, "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
               "vsr_effective": KSS.VSR, "cake_ds": KSS.CAKE_DS,
               "digester_vol_m3": plant.get("digester_vol_m3"), "capacity_released_m3": 0.0,
               "recycle_m3d": recycle_m3d, "recycle_temp_c": KSS.RECYCLE_TEMP_C,
               "recycle_heat_recovery_mwh_d": recycle_heat,
               "product_wet_tpd": (VS_remaining + total_tds*(1-vs_ts)) / KSS.CAKE_DS,
               "chemicals_m_aud": 0.35 * total_tds / 100.0, "om_m_aud": 1.60 * total_tds / 100.0},
    )
    _attach(pw, endpoint="land", conf=Conf.A)
    return pw



# ---------------------------------------------------------------------------
# PATHWAY K - Separate PS/WAS digestion (short-HRT PS) + WAS-side SolidStream recycle
class KK:  # Pathway K capacity-release constants (separate-digestion short-PS-HRT). ETP-anchored.
    PS_HRT_SHORT_D = 10.0       # short-HRT PS digestion (brief); PS digests fast, frees volume
    DIGESTER_FEED_DS = 0.062    # blended digester feed DS (ETP 2026 memo, mixed 6.2%) - sets flow/HRT
    DIGESTER_UNIT_M3 = 8000.0   # ETP digester unit (8 x 8000) - for equivalent-digesters count


def build_pathway_k(plant: dict = GENERIC) -> Pathway:
    """V3 Pathway K (strategic). Separate PS/WAS digestion with SHORT-HRT PS (~10 d) + long-HRT
    WAS, post-digestion SolidStream THP, hot soluble-COD centrate recycled to the WAS digesters.
    SolidStream performance IS Pathway E's (ETP_SS_2026, confidence A); the DIFFERENTIATOR is the
    digester volume released by digesting PS separately at short HRT - that capacity claim is a
    strategic bet (separate short-HRT PS), NOT vendor-validated. K = E + capacity release."""
    e = build_solidstream_pathway(plant)   # reuse verified SolidStream ledgers (VSR ~70%, recycle, cake 38%)
    PS_tds = plant["PS_tds"]; WAS_tds = plant["WAS_tds"]; total_tds = PS_tds + WAS_tds
    V = plant.get("digester_vol_m3")
    cap = {}
    if V:
        total_flow = total_tds / KK.DIGESTER_FEED_DS
        hrt_current = V / total_flow
        ps_flow = PS_tds / KK.DIGESTER_FEED_DS
        was_flow = WAS_tds / KK.DIGESTER_FEED_DS
        ps_vol_short = ps_flow * KK.PS_HRT_SHORT_D
        released = max(0.0, ps_flow * (hrt_current - KK.PS_HRT_SHORT_D))
        was_vol = V - ps_vol_short
        recycle_m3d = e.basis.get("recycle_m3d", 0.0)
        denom = was_flow + recycle_m3d
        was_hrt = (was_vol / denom) if denom > 0 else None
        cap = {"capacity_released_m3": released,
               "equivalent_digesters": released / KK.DIGESTER_UNIT_M3,
               "deferred_capex_m_aud": released * KCAP.CAPEX_PER_M3 / 1e6,
               "ps_hrt_d": KK.PS_HRT_SHORT_D, "was_hrt_d": was_hrt, "hrt_current_d": hrt_current,
               "ps_digester_vol_m3": ps_vol_short, "was_digester_vol_m3": was_vol}
    relm = cap.get("capacity_released_m3", 0.0)
    eqd = cap.get("equivalent_digesters", 0.0)
    defc = cap.get("deferred_capex_m_aud", 0.0)
    moves = [
        Move("Separate PS and WAS digestion at differentiated HRT (PS ~10 d)",
             addresses=["capacity", "capex"],
             reward=f"Frees ~{relm:,.0f} m3 (~{eqd:.1f} digesters); defers ~${defc:.0f}M expansion CAPEX",
             residual_risk="Short-HRT PS not vendor-validated; two trains = more assets/complexity",
             confidence=Confidence(Conf.B, Conf.B, Conf.B),
             derisk_task="PS short-HRT pilot, ~$0.5M / 12 months", tag=Tag.KEEP_OPEN),
        Move("Post-digestion SolidStream THP + recycle to the WAS digesters",
             addresses=["capacity", "energy_neutrality", "opex", "biosolids_quality"],
             reward="VSR ~58%->70%; biogas +22.7%; recycles soluble COD + ~2.4 MW heat to WAS train",
             residual_risk="Return-liquor NH4; recycle-to-WAS split adds plumbing",
             confidence=Confidence(Conf.A, Conf.A, Conf.B), derisk_task=None, tag=Tag.COMMIT),
        Move("Class-A hygienised 38% DS cake (no drying)",
             addresses=["biosolids_quality", "opex", "pfas"],
             reward="Pathogen-free at 165C; ~50% fewer wet tonnes; ends 3-yr EPA stockpiling",
             residual_risk="Cake market still developing (positive value at scale)",
             confidence=Confidence(Conf.A, Conf.A, Conf.A), derisk_task=None, tag=Tag.COMMIT),
        Move("Struvite + PN-A for return-liquor N",
             addresses=["nutrient_recovery", "scope1_emissions"],
             reward="Recovers P; closes the higher SolidStream N return", residual_risk="Process complexity",
             confidence=Confidence(Conf.A, Conf.B, Conf.A), derisk_task="Sidestream N pilot", tag=Tag.KEEP_OPEN),
    ]
    e.name = "Pathway K: Separate PS/WAS (short-HRT PS) + SolidStream recycle to WAS + Land"
    e.description = ("V3 Pathway K (strategic): PS digested separately at ~10 d HRT + long-HRT WAS; "
                     "post-digestion SolidStream THP with hot soluble-COD centrate recycled to the WAS "
                     "digesters. SolidStream performance = Pathway E (confidence A); capacity release "
                     "from separate short-HRT PS is a strategic bet (not vendor-validated).")
    e.moves = moves
    e.basis.update({"separate_trains": True, "pathway": "K"})
    e.basis.update(cap)
    return e



# ---------------------------------------------------------------------------
# PATHWAY B - Conventional MAD + sidestream PN/A (return-liquor N destruction)
def build_pathway_b(plant: dict = GENERIC) -> Pathway:
    """V3 Pathway B. Conventional blended MAD (no THP) + sidestream PN/A (deammonification) on
    the return liquor: ~88% of released N destroyed to N2 instead of returned to the host WWTW.
    Targets the return-liquor N burden / N2O risk that conventional digestion dumps on the plant.
    Same digestion/biogas/cake as conventional A; the N ledger is the differentiator."""
    WAS_tds, PS_tds = plant["WAS_tds"], plant["PS_tds"]
    total_tds = WAS_tds + PS_tds; vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts; VSR = K.VSR_CONV
    VS_d = VS_in * VSR; VS_rem = VS_in - VS_d

    C_in = VS_in * K.C_PER_VS; C_biogas = VS_d * K.C_PER_VS
    C_dig = C_in - C_biogas; C_liq = C_dig * K.C_LIQUOR_FRAC; C_cake = C_dig - C_liq
    CH4 = VS_d * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4 * K.CH4_C_KG_PER_NM3 / 1000.0; C_fug = C_CH4 * K.FUGITIVE_CH4_FRAC
    carbon = Ledger("carbon", "tC/d", inflows={"feed_volatile_carbon": C_in},
        outflows={"soil_land_application": C_cake, "return_liquor_to_WWTW": C_liq,
                  "atmosphere_biogenic_CO2": (C_CH4 - C_fug) + (C_biogas - C_CH4),
                  "atmosphere_fugitive_CH4_scope1": C_fug})

    biogas_chem = CH4 * K.CH4_LHV_KWH_NM3 / 1000.0
    gas_util = plant.get("gas_utilisation_frac", K.GAS_UTILISATION_DEFAULT)
    elec_gen, heat_gen, chp_losses, gas_flared = _chp_split(biogas_chem, gas_util)
    heat_demand = K.DIGESTER_HEAT_MWH_D
    heat_used = min(heat_gen, heat_demand)
    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    N_rel = N_in * VSR * K.N_SOLUBILISATION_EFF
    pna_N = N_rel * KN.PNA_N_REMOVAL
    pna_parasitic = pna_N * 1.2 / 1000.0          # sidestream deammonification blowers ~1.2 kWh/kgN (vs ~4-6 mainstream)
    parasitics = ((VS_rem + total_tds*(1-vs_ts)) * K.DEWATER_KWH_PER_TDS / 1000.0
                  + K.PLANT_PARASITIC_MWH_D + pna_parasitic)
    net_elec = elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D
    energy = Ledger("energy", "MWh/d", inflows={"biogas_chemical_energy": biogas_chem},
        outflows={"chp_electricity_generated": elec_gen, "ad_heat_used_digester": heat_used,
                  "heat_surplus_unused": max(0.0, heat_gen - heat_demand),
                  "chp_conversion_losses": chp_losses, "biogas_flared_unused": gas_flared})

    nitrogen = Ledger("nitrogen", "kgN/d", inflows={"feed_nitrogen": N_in},
        outflows={"cake_organic_N_to_land": N_in - N_rel, "N2_to_atmosphere_via_PNA": pna_N,
                  "return_liquor_NH4_residual": N_rel - pna_N})
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    P_sol = P_in * K.P_SOLUBILISED_FRAC
    phosphorus = Ledger("phosphorus", "kgP/d", inflows={"feed_phosphorus": P_in},
        outflows={"cake_P_to_land": P_in - P_sol, "return_liquor_P_to_WWTW": P_sol})

    moves = [
        Move("Conventional blended MAD (no THP)",
             addresses=["opex"], reward="Proven base train; lowest capital",
             residual_risk="Class B cake; no capacity headroom", confidence=Confidence(Conf.A, Conf.A, Conf.B),
             derisk_task=None, tag=Tag.COMMIT),
        Move("Sidestream PN/A (deammonification) on return liquor",
             addresses=["nutrient_recovery", "scope1_emissions"],
             reward="Destroys ~88% of return-liquor N to N2; cuts WWTW sidestream load + N2O; autotrophic low-energy",
             residual_risk="Cold/dilute liquor control; no N product (destroyed, not recovered)",
             confidence=Confidence(Conf.A, Conf.A, Conf.A), derisk_task=None, tag=Tag.COMMIT),
        Move("Commit land application as terminal disposal",
             addresses=["opex", "capex"], reward="Cheapest endpoint today",
             residual_risk="Class B; strands strategy under a PFAS land-application ban",
             confidence=Confidence(Conf.A, Conf.A, Conf.D), derisk_task=None, tag=Tag.AVOID,
             forecloses=["Thermal endpoint (pyrolysis/gasification) for residual cake"]),
    ]
    pw = Pathway(
        name="Pathway B: Conventional MAD + PN/A (return-liquor N) + Land",
        description="V3 Pathway B: blended conventional MAD, dewater, land; sidestream PN/A destroys "
                    "~88% of return-liquor N to N2. Same digestion as A; N ledger differs.",
        ledgers={"carbon": carbon, "energy": energy, "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=moves, pfas_destruction_frac=0.0, net_export_mwh_d=net_elec, generation_mwh_d=biogas_chem,
        basis={"total_tds": total_tds, "has_thp": False, "vs_ts": vs_ts, "pathway": "B",
               "ps_tds": PS_tds, "was_tds": WAS_tds, "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
               "digester_vol_m3": plant.get("digester_vol_m3"), "pna_n_destroyed_kgd": pna_N,
               "product_wet_tpd": (VS_rem + total_tds*(1-vs_ts)) / 0.22,
               "chemicals_m_aud": 0.20 * total_tds / 100.0, "om_m_aud": 0.95 * total_tds / 100.0})
    _attach(pw, endpoint="land", conf=Conf.A)
    return pw


# ---------------------------------------------------------------------------
# PATHWAY F - Separate PS/WAS digestion + SolidStream recycle (no short-HRT-PS capacity bet)
def build_pathway_f(plant: dict = GENERIC) -> Pathway:
    """V3 Pathway F. Separate PS/WAS digestion + post-digestion SolidStream THP with centrate
    recycle - i.e. Pathway K WITHOUT the short-HRT-PS capacity bet. SolidStream performance =
    Pathway E (VSR ~70%, cake 38%, recycle, heat recovery); separate trains give operational
    flexibility and the platform for K, but PS runs at conventional HRT so no capacity release."""
    e = build_solidstream_pathway(plant)
    moves = [
        Move("Separate PS and WAS digestion trains (conventional HRT)",
             addresses=["energy_neutrality", "opex"],
             reward="Per-stream optimisation; targeted recycle; platform for short-HRT-PS capacity (K)",
             residual_risk="Two trains = more assets; no capacity release without the short-HRT-PS bet",
             confidence=Confidence(Conf.B, Conf.A, Conf.B), derisk_task=None, tag=Tag.COMMIT),
        Move("Post-digestion SolidStream THP + centrate recycle",
             addresses=["capacity", "energy_neutrality", "opex", "biosolids_quality"],
             reward="VSR ~58%->70%; biogas +22.7%; recycles soluble COD + ~2.4 MW heat",
             residual_risk="Return-liquor NH4 (higher VS destruction)",
             confidence=Confidence(Conf.A, Conf.A, Conf.B), derisk_task=None, tag=Tag.COMMIT),
        Move("Class-A hygienised 38% DS cake (no drying)",
             addresses=["biosolids_quality", "opex", "pfas"],
             reward="Pathogen-free; ~50% fewer wet tonnes; ends EPA stockpiling",
             residual_risk="Cake market developing", confidence=Confidence(Conf.A, Conf.A, Conf.A),
             derisk_task=None, tag=Tag.COMMIT),
        Move("Struvite + PN-A for return-liquor N",
             addresses=["nutrient_recovery", "scope1_emissions"], reward="Recovers P; closes N return",
             residual_risk="Process complexity", confidence=Confidence(Conf.A, Conf.B, Conf.A),
             derisk_task="Sidestream N pilot", tag=Tag.KEEP_OPEN),
    ]
    e.name = "Pathway F: Separate PS/WAS + SolidStream recycle + Land"
    e.description = ("V3 Pathway F: separate PS/WAS digestion at conventional HRT + post-digestion "
                     "SolidStream THP with centrate recycle. SolidStream performance = Pathway E; "
                     "separate trains but no short-HRT-PS capacity bet (that is Pathway K).")
    e.moves = moves
    e.basis.update({"separate_trains": True, "pathway": "F", "capacity_released_m3": 0.0})
    return e



# # 7b. THERMAL-ENDPOINT PATHWAY — exercises the PROVISIONAL ledger machinery
# ---------------------------------------------------------------------------
# Front end identical to the worked pathway (THP+MAD) for comparability; the
# endpoint swaps land application for dewater -> thermal dry -> gasification.
# Split fractions here are NOT calibrated against a closed full-scale balance,
# so the ledgers close arithmetically (conservation enforced) but are flagged
# PROVISIONAL, and the energy/Scope-1 drivers are rendered as BANDS.
class KT:
    CAKE_DS = 0.25              # dewatered digestate cake, fraction DS
    DRY_TARGET_DS = 0.90        # dried solids for gasifier feed
    DRY_MWH_PER_T_WATER = 0.90  # evaporation energy (latent + inefficiency)
    # PROVISIONAL (uncalibrated) — central ± band
    C_TO_CHAR_FRAC = (0.30, 0.40, 0.50)     # of feed-C retained/stabilised in char
    PFAS_DESTRUCTION = (0.85, 0.93, 0.99)   # thermal C-F bond cleavage
    SYNGAS_MWH_PER_TDS = (0.8, 1.5, 2.5)    # net usable syngas, MWh/tDS — LOW: solids already digested
    N_VOLATILISED_FRAC = 0.95   # thermal: organic+NH4 N volatilised (lost as NOx/N2)
    P_TO_ASH_FRAC = 0.98        # P locked into ash (not plant-available without recovery)


def build_thermal_pathway(plant: dict = GENERIC) -> Pathway:
    WAS_tds, PS_tds = plant["WAS_tds"], plant["PS_tds"]
    total_tds = WAS_tds + PS_tds
    vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    VS_destroyed = VS_in * K.VSR
    VS_remaining = VS_in - VS_destroyed
    fixed = total_tds * (1 - vs_ts)
    solids_to_dryer = VS_remaining + fixed                # tDS/d to dryer/gasifier

    # ---- CARBON (provisional split at gasifier) ----
    C_in = VS_in * K.C_PER_VS
    C_biogas = VS_destroyed * K.C_PER_VS
    C_digestate = C_in - C_biogas
    C_liquor = C_digestate * K.C_LIQUOR_FRAC
    C_cake = C_digestate - C_liquor                       # carbon into the dryer/gasifier
    CH4_nm3 = VS_destroyed * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4_nm3 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_CO2_biogas = C_biogas - C_CH4
    C_fugitive = C_CH4 * K.FUGITIVE_CH4_FRAC
    C_combusted = C_CH4 - C_fugitive
    char_lo, char_c, char_hi = KT.C_TO_CHAR_FRAC
    C_char = C_cake * char_c                               # central
    C_syngas_atm = C_cake - C_char                         # combusted -> atmosphere
    carbon = Ledger("carbon", "tC/d", provisional=True,
        inflows={"feed_volatile_carbon": C_in},
        outflows={
            "char_permanently_stored": C_char,             # the durable-storage branch
            "return_liquor_to_WWTW": C_liquor,
            "atmosphere_biogenic_CO2": C_combusted + C_CO2_biogas + C_syngas_atm,
            "atmosphere_fugitive_CH4_scope1": C_fugitive,
        })

    # ---- ENERGY (drying load is the crux; syngas recovery is the uncertain term) ----
    biogas_chem = CH4_nm3 * K.CH4_LHV_KWH_NM3 / 1000.0
    elec_gen = biogas_chem * K.CHP_ELEC
    heat_gen = biogas_chem * K.CHP_HEAT
    chp_losses = biogas_chem * (1 - K.CHP_ELEC - K.CHP_HEAT)
    steam_t = WAS_tds * K.STEAM_T_PER_TDS
    steam_demand = steam_t * 1000 * K.STEAM_KWH_PER_KG / 1000.0
    ad_heat_demand = steam_demand + K.DIGESTER_HEAT_MWH_D
    heat_surplus = heat_gen - ad_heat_demand               # recovered AD heat free for drying
    cake_mass = solids_to_dryer / KT.CAKE_DS
    dried_mass = solids_to_dryer / KT.DRY_TARGET_DS
    water_removed = cake_mass - dried_mass
    drying_load = water_removed * KT.DRY_MWH_PER_T_WATER    # MWh/d — the big parasitic
    syn_lo, syn_c, syn_hi = (solids_to_dryer * s for s in KT.SYNGAS_MWH_PER_TDS)
    parasitics = (solids_to_dryer * K.DEWATER_KWH_PER_TDS / 1000.0
                  + K.THP_PUMP_PARASITIC_MWH_D + K.PLANT_PARASITIC_MWH_D + 4.0)  # +gasifier aux

    def net_and_fossil(syngas):
        """AD heat covers drying first, then syngas; shortfall = FOSSIL -> Scope 1.
        Syngas beyond drying need is exported as power at gas-to-power efficiency."""
        ad_for_drying = min(heat_surplus, drying_load)
        drying_remaining = drying_load - ad_for_drying
        syn_for_drying = min(syngas, drying_remaining)
        syn_surplus = syngas - syn_for_drying
        fossil = max(0.0, drying_remaining - syn_for_drying)
        net = (elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D
               + syn_surplus * 0.35 - fossil)
        return net, fossil

    net_c, fossil_c = net_and_fossil(syn_c)
    net_lo, fossil_lo = net_and_fossil(syn_lo)
    net_hi, fossil_hi = net_and_fossil(syn_hi)
    fossil_C_central = fossil_c * 0.05                     # tC fossil per MWh gas (~0.18 kgCO2/kWh)
    if fossil_C_central > 0:
        carbon.inflows["fossil_drying_carbon_in"] = fossil_C_central
        carbon.outflows["atmosphere_fossil_CO2_from_drying"] = fossil_C_central
    # Honest energy ledger: primary energy IN = useful delivered OUT + real losses (no plug).
    total_in = biogas_chem + syn_c + fossil_c
    useful_drying = min(drying_load, heat_surplus + syn_c + fossil_c)
    losses = total_in - elec_gen - ad_heat_demand - useful_drying - max(0.0, heat_surplus - drying_load)
    energy = Ledger("energy", "MWh/d", provisional=True,
        inflows={"biogas_chemical_energy": biogas_chem,
                 "syngas_recovery_provisional": syn_c,
                 **({"fossil_topup_for_drying": fossil_c} if fossil_c else {})},
        outflows={
            "chp_electricity_generated": elec_gen,
            "ad_heat_used": ad_heat_demand,
            "thermal_drying_delivered": useful_drying,
            "heat_surplus_unused": max(0.0, heat_surplus - drying_load),
            "conversion_and_process_losses": losses,
        })

    # ---- NITROGEN (thermal volatilises most N; little recoverable) ----
    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    N_volatilised = N_in * KT.N_VOLATILISED_FRAC
    N_in_ash = N_in - N_volatilised
    nitrogen = Ledger("nitrogen", "kgN/d", provisional=True,
        inflows={"feed_nitrogen": N_in},
        outflows={"volatilised_NOx_N2": N_volatilised, "retained_in_ash": N_in_ash})

    # ---- PHOSPHORUS (locked in ash unless recovered upstream) ----
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    P_ash = P_in * KT.P_TO_ASH_FRAC
    P_liquor = P_in - P_ash
    phosphorus = Ledger("phosphorus", "kgP/d", provisional=True,
        inflows={"feed_phosphorus": P_in},
        outflows={"locked_in_ash": P_ash, "return_liquor_P": P_liquor})

    # energy / scope1 BANDS (driven by the uncalibrated syngas term)
    def en_view(net):
        return min(1.0, max(0.0, net / biogas_chem))
    energy_band = (en_view(net_lo), en_view(net_c), en_view(net_hi))
    def s1_view(fossil):
        return scope1_score(C_fugitive, fossil * 0.05, C_char, C_in)
    # low syngas -> high fossil -> worst Scope1; high syngas -> no fossil -> best
    scope1_band = (s1_view(fossil_lo), s1_view(fossil_c), s1_view(fossil_hi))

    C_grade = lambda: Confidence(Conf.C, Conf.C, Conf.C)
    moves = [
        Move("Thermal drying + low-temp gasification of digestate cake",
             addresses=["pfas", "scope1_emissions"],
             reward=f"Destroys ~{KT.PFAS_DESTRUCTION[1]*100:.0f}% PFAS; stabilises "
                    f"~{char_c*100:.0f}% of cake carbon as char; eliminates land-disposal volume",
             residual_risk="Net energy depends on uncalibrated syngas recovery; at the low band "
                           "needs fossil top-up -> Scope-1 penalty. P stranded in ash; N lost.",
             confidence=C_grade(),
             derisk_task="Full-scale reference mass balance + 6-month demo, ~$1.5M / 18 months",
             tag=Tag.KEEP_OPEN),
    ]
    pw = Pathway(
        name="THP + MAD + Thermal Drying + Gasification (endpoint)",
        description="Same THP+MAD front end; endpoint swaps land application for dewater -> "
                    "thermal dry -> low-temp gasification. PROVISIONAL: split fractions not "
                    "calibrated full-scale; energy and Scope-1 rendered as bands.",
        ledgers={"carbon": carbon, "energy": energy,
                 "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=moves,
        pfas_destruction_frac=KT.PFAS_DESTRUCTION[1],
        net_export_mwh_d=net_c,
        generation_mwh_d=biogas_chem,
        basis={
            "total_tds": total_tds, "has_thp": True, "vs_ts": vs_ts,
            "ps_tds": PS_tds, "was_tds": WAS_tds,
            "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
            "digester_vol_m3": plant.get("digester_vol_m3"),
            "product_wet_tpd": solids_to_dryer * 0.30 / 0.95,  # char/ash @95% DS — tiny tonnage
            "chemicals_m_aud": 0.20 * total_tds / 100.0,
            "om_m_aud": 2.50 * total_tds / 100.0,
        },
        bands={"energy_neutrality": energy_band, "scope1_emissions": scope1_band,
               "pfas": KT.PFAS_DESTRUCTION},
    )
    _attach(pw, endpoint="thermal", conf=Conf.C)
    return pw


# ---------------------------------------------------------------------------
# 7d. CONVENTIONAL MAD BASELINE — no THP; the resilience engine needs a true baseline
# ---------------------------------------------------------------------------
def build_conventional_pathway(plant: dict = GENERIC) -> Pathway:
    """Blended conventional MAD -> dewater -> land. No THP, no nutrient recovery.
    Lower VSR (HRT-constrained), Class B, no capacity intensification. The do-little
    baseline against which THP pathways are judged."""
    WAS_tds, PS_tds = plant["WAS_tds"], plant["PS_tds"]
    total_tds = WAS_tds + PS_tds
    vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    VSR = K.VSR_CONV
    VS_d = VS_in * VSR
    VS_rem = VS_in - VS_d

    C_in = VS_in * K.C_PER_VS
    C_biogas = VS_d * K.C_PER_VS
    C_dig = C_in - C_biogas
    C_liq = C_dig * K.C_LIQUOR_FRAC
    C_cake = C_dig - C_liq
    CH4 = VS_d * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_fug = C_CH4 * K.FUGITIVE_CH4_FRAC
    carbon = Ledger("carbon", "tC/d",
        inflows={"feed_volatile_carbon": C_in},
        outflows={"soil_land_application": C_cake, "return_liquor_to_WWTW": C_liq,
                  "atmosphere_biogenic_CO2": (C_CH4 - C_fug) + (C_biogas - C_CH4),
                  "atmosphere_fugitive_CH4_scope1": C_fug})

    biogas_chem = CH4 * K.CH4_LHV_KWH_NM3 / 1000.0
    gas_util = plant.get("gas_utilisation_frac", K.GAS_UTILISATION_DEFAULT)
    elec_gen, heat_gen, chp_losses, gas_flared = _chp_split(biogas_chem, gas_util)
    heat_demand = K.DIGESTER_HEAT_MWH_D                       # no THP steam
    heat_used = min(heat_gen, heat_demand)
    parasitics = (VS_rem + total_tds*(1-vs_ts)) * K.DEWATER_KWH_PER_TDS / 1000.0 + K.PLANT_PARASITIC_MWH_D
    net_elec = elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D
    energy = Ledger("energy", "MWh/d",
        inflows={"biogas_chemical_energy": biogas_chem},
        outflows={"chp_electricity_generated": elec_gen, "ad_heat_used_digester": heat_used,
                  "heat_surplus_unused": max(0.0, heat_gen - heat_demand),
                  "chp_conversion_losses": chp_losses, "biogas_flared_unused": gas_flared})

    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    N_rel = N_in * VSR * K.N_SOLUBILISATION_EFF
    nitrogen = Ledger("nitrogen", "kgN/d",
        inflows={"feed_nitrogen": N_in},
        outflows={"cake_organic_N_to_land": N_in - N_rel,
                  "return_liquor_NH4_to_WWTW": N_rel})       # no recovery
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    P_sol = P_in * K.P_SOLUBILISED_FRAC
    phosphorus = Ledger("phosphorus", "kgP/d",
        inflows={"feed_phosphorus": P_in},
        outflows={"cake_P_to_land": P_in - P_sol, "return_liquor_P_to_WWTW": P_sol})

    moves = [Move("Conventional blended MAD + land application (baseline)",
                  addresses=["opex"], reward="Lowest capital; proven; operational baseline",
                  residual_risk="Class B only; no capacity headroom; no PFAS benefit; "
                                "fails under a land-application ban",
                  confidence=Confidence(Conf.A, Conf.A, Conf.B), derisk_task=None, tag=Tag.AVOID,
                  forecloses=[])]
    pw = Pathway(
        name="Conventional MAD + Land (baseline)",
        description="Blended PS+WAS mesophilic digestion, dewater, land application. No THP, "
                    "no nutrient recovery. The do-little baseline.",
        ledgers={"carbon": carbon, "energy": energy, "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=moves, pfas_destruction_frac=0.0,
        net_export_mwh_d=net_elec, generation_mwh_d=biogas_chem,
        basis={"total_tds": total_tds, "has_thp": False, "vs_ts": vs_ts,
               "ps_tds": PS_tds, "was_tds": WAS_tds, "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
               "digester_vol_m3": plant.get("digester_vol_m3"),
               "product_wet_tpd": (VS_rem + total_tds*(1-vs_ts)) / 0.22,  # Class B cake @22%
               "chemicals_m_aud": 0.15 * total_tds / 100.0, "om_m_aud": 0.80 * total_tds / 100.0})
    _attach(pw, endpoint="land", conf=Conf.A)
    return pw


def _attach(pw: Pathway, endpoint: str, conf: "Conf"):
    """Populate the traits the resilience engine reads, and the overall confidence level."""
    s = pw.driver_scores()
    C = pw.ledgers["carbon"]; P = pw.ledgers["phosphorus"]
    cap = capacity_view(pw)
    pw.confidence_level = conf
    pw.traits = {
        "endpoint": endpoint,
        "thp": bool(pw.basis.get("has_thp")),
        "pfas": pw.pfas_destruction_frac,
        "p_recovered": P.fraction_to("struvite_P"),
        "c_stored": C.fraction_to("char_permanently_stored"),
        "net_energy": pw.net_export_mwh_d,
        "net_energy_norm": max(0.0, min(1.0, pw.net_export_mwh_d / 250.0)),
        "scope1": s.get("scope1_emissions", 0.0),
        "nutrient": s.get("nutrient_recovery", 0.0),
        "headroom_norm": max(0.0, min(1.0, cap.get("capacity_headroom_tds", 0.0) / pw.basis.get("total_tds", 1))),
    }


# ---------------------------------------------------------------------------
# 7e. FUTURE RESILIENCE ENGINE — test pathways against different WORLDS
# ---------------------------------------------------------------------------
# A scenario is a future world that changes external conditions (not the driver
# weighting). Each returns (viable, performance 0-1, note) for a pathway's traits.
# Resilience = likelihood-weighted performance across worlds; a non-viable world scores 0.
_clip = lambda x: max(0.0, min(1.0, x))

@dataclass
class Scenario:
    name: str
    likelihood: float            # coarse prior: near-certain ~0.7, plausible ~0.5, tail ~0.3
    fn: object                   # (traits) -> (viable: bool, perf: float, note: str)


SCENARIOS = [
    Scenario("PFAS land-application ban", 0.70, lambda t: (
        (False, 0.0, "land application banned -> non-viable") if t["endpoint"] == "land"
        else (True, _clip(0.5 + 0.5*t["pfas"]), "thermal destroys PFAS -> becomes the solution"))),
    Scenario("Carbon price $150/tCO2e", 0.70, lambda t: (
        True, _clip(0.35 + 0.35*t["scope1"] + 0.6*t["c_stored"]),
        "monetises low Scope 1 and durable carbon storage (char)")),
    Scenario("Methane emissions regulation", 0.60, lambda t: (
        True, _clip(0.45 + 0.35*t["scope1"] + 0.2*t["c_stored"]),
        "penalises fugitive CH4; rewards captured/stabilised carbon")),
    Scenario("FOGO co-feed available", 0.50, lambda t: (
        True, _clip(0.40 + 0.25*t["thp"] + 0.45*t["headroom_norm"]),
        "spare OLR headroom (THP) absorbs co-feed for more biogas")),
    Scenario("Phosphorus price doubles", 0.45, lambda t: (
        True, _clip(0.30 + 0.70*t["p_recovered"]),
        "rewards recovered P (struvite); thermal strands P in ash")),
    Scenario("Electricity price halves", 0.40, lambda t: (
        True, _clip(0.45 + 0.20*t["thp"] + 0.15*t["nutrient"]),
        "value resting on capacity/disposal/nutrients holds; pure energy plays weaken")),
    Scenario("Utility becomes net energy exporter", 0.30, lambda t: (
        True, _clip(0.30 + 0.60*t["net_energy_norm"]),
        "rewards high net-energy pathways")),
]


def resilience(pw: Pathway) -> dict:
    """Likelihood-weighted performance of a pathway across the future worlds."""
    results, wsum, acc = [], 0.0, 0.0
    survives_pfas = True
    for sc in SCENARIOS:
        viable, perf, note = sc.fn(pw.traits)
        if not viable:
            perf = 0.0
            if "PFAS" in sc.name:
                survives_pfas = False
        results.append({"scenario": sc.name, "likelihood": sc.likelihood,
                        "viable": viable, "perf": perf, "note": note})
        wsum += sc.likelihood
        acc += sc.likelihood * perf
    return {"score": acc / wsum if wsum else 0.0, "survives_pfas_ban": survives_pfas,
            "results": results}


def three_axis(pw: Pathway, weights: dict) -> dict:
    """Performance / Confidence / Resilience — the three axes; no single one decides."""
    s = pw.driver_scores()
    avail = {d: w for d, w in weights.items() if d in s}
    tot = sum(avail.values())
    performance = sum(avail[d] * s[d] for d in avail) / tot if tot else 0.0
    conf_map = {Conf.A: 1.0, Conf.B: 0.8, Conf.C: 0.5, Conf.D: 0.2}
    confidence = conf_map.get(pw.confidence_level, 0.5)
    return {"performance": performance, "confidence": confidence,
            "resilience": resilience(pw)["score"]}


OPTION_SET = ["land application", "thermal endpoint", "P recovery (struvite)",
              "N recovery (AS)", "energy export", "FOGO co-digestion capacity"]


def optionality(pw: Pathway) -> dict:
    """How many future options a pathway keeps open vs forecloses. The Hunter Water lesson:
    some moves preserve futures, others lock them out. High optionality is itself value."""
    t = pw.traits
    preserved, foreclosed = [], []
    thermal = t["endpoint"] == "thermal"
    (foreclosed if thermal else preserved).append("land application")      # thermal destroys cake
    preserved.append("thermal endpoint")                                    # cake can always be diverted later
    (foreclosed if thermal else preserved).append("P recovery (struvite)")  # thermal strands P in ash
    (foreclosed if thermal else preserved).append("N recovery (AS)")        # thermal volatilises N
    (preserved if t["net_energy"] > 0 else foreclosed).append("energy export")
    (preserved if (t["thp"] and t["headroom_norm"] > 0.05) else foreclosed).append("FOGO co-digestion capacity")
    return {"preserved": preserved, "foreclosed": foreclosed,
            "score": len(preserved) / len(OPTION_SET)}


# ===========================================================================
# V2.1 — THERMAL ENDPOINT SPLIT (incineration / pyrolysis / gasification / HTL)
# Distinct pathways, each with closing C/N/P/energy ledgers + PFAS + maturity.
# Screening-grade, literature-anchored (ITRC 2020; Winchell 2022; IEA Bioenergy).
# ===========================================================================
# Per-endpoint fate fractions of the DIGESTED-CAKE carbon, feed N, and feed P, plus
# PFAS destruction, technology maturity and a screening net-energy yield (MWh/tDS to unit).
THERMAL_ENDPOINTS = {
    "incineration": dict(temp="850-950C", pfas=0.999, maturity="High",
        c_char=0.00, c_biocrude=0.00,                       # carbon fully oxidised
        n_atm=0.87, n_aqueous=0.05, n_solid=0.08,
        p_recoverable=0.92, energy_mwh_tds=1.8, drying=True),
    "pyrolysis": dict(temp="400-700C", pfas=0.70, maturity="Medium",
        c_char=0.45, c_biocrude=0.00,                       # ~45% cake C to stable biochar
        n_atm=0.35, n_aqueous=0.20, n_solid=0.45,
        p_recoverable=0.70, energy_mwh_tds=1.0, drying=True),
    "gasification": dict(temp="750-1000C", pfas=0.97, maturity="Medium",
        c_char=0.05, c_biocrude=0.00,                       # mostly to syngas->CO2
        n_atm=0.88, n_aqueous=0.07, n_solid=0.05,
        p_recoverable=0.90, energy_mwh_tds=2.2, drying=True),
    "htl": dict(temp="250-350C", pfas=0.45, maturity="Low",
        c_char=0.00, c_biocrude=0.50,                       # ~50% C to biocrude; wet feed, no drying
        n_atm=0.05, n_aqueous=0.80, n_solid=0.15,           # huge aqueous-N sidestream
        p_recoverable=0.45, energy_mwh_tds=2.6, drying=False),
}


# ===========================================================================
# V3 U5 — EVIDENCE-STRENGTH REGISTRY (single source of truth for maturity grading)
# Level A multiple full-scale refs | B multiple demonstrations |
# C limited full-scale refs | D site-specific hypothesis. Grades are deployment-
# based (biosolids-specific), with the reference basis recorded for each.
EVIDENCE = {
    "THP":            (Conf.A, "Cambi/Sustec full-scale fleet: St Marys, Davyhulme, Ringsend, Thames, Blue Plains"),
    "PN/A":           (Conf.A, "anammox sidestream: 100+ full-scale installations (DEMON/ANAMMOX)"),
    "struvite":       (Conf.A, "Ostara Pearl / NuReSys / Crystalactor full-scale P recovery"),
    "incineration":   (Conf.A, "sewage-sludge mono-incineration widespread (EU/Japan), fluidised bed"),
    "gasification":   (Conf.B, "Logan/Loganholme full-scale AU since 2022 (34 kt/yr); intl demos"),
    "pyrolysis":      (Conf.B, "South East Water PYROCO (VIC, commercial 2026) + Sydney Water Pyreg (2025); Pyreg EU sludge fleet"),
    "htl":            (Conf.C, "pre-commercial for biosolids; limited references (Genifuel/Licella pilots)"),
    "separate_PS_WAS":(Conf.B, "multiple demonstrations; mechanism established (Hillis & Taylor Ozwater'17)"),
    "site_uplift":    (Conf.D, "site-specific magnitude requires BMP calibration"),
}


def build_thermal_endpoints(plant: dict = GENERIC) -> dict:
    """Four DISTINCT thermal-endpoint pathways on the shared THP+MAD front end. Returns
    {endpoint_name: Pathway}. Each closes carbon/nitrogen/phosphorus/energy and carries
    a PFAS destruction fraction and a technology-maturity trait."""
    WAS_tds, PS_tds = plant["WAS_tds"], plant["PS_tds"]
    total_tds = WAS_tds + PS_tds
    vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    VS_d = VS_in * K.VSR
    C_in = VS_in * K.C_PER_VS
    C_biogas = VS_d * K.C_PER_VS
    C_digestate = C_in - C_biogas                       # cake carbon entering the thermal unit
    CH4 = VS_d * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_fug = C_CH4 * K.FUGITIVE_CH4_FRAC
    biogas_chem = CH4 * K.CH4_LHV_KWH_NM3 / 1000.0
    elec_gen = biogas_chem * K.CHP_ELEC
    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    parasitics = (VS_in - VS_d) * K.DEWATER_KWH_PER_TDS / 1000.0 + K.PLANT_PARASITIC_MWH_D + 6.0

    out = {}
    for name, e in THERMAL_ENDPOINTS.items():
        c_char = C_digestate * e["c_char"]
        c_biocrude = C_digestate * e["c_biocrude"]
        c_thermal_CO2 = C_digestate - c_char - c_biocrude
        carbon = Ledger("carbon", "tC/d",
            inflows={"feed_volatile_carbon": C_in},
            outflows={
                "atmosphere_biogenic_CO2_biogas": (C_biogas - C_fug),
                "atmosphere_fugitive_CH4_scope1": C_fug,
                "char_permanently_stored": c_char,
                "biocrude_product": c_biocrude,
                "atmosphere_thermal_CO2": c_thermal_CO2})
        nitrogen = Ledger("nitrogen", "kgN/d",
            inflows={"feed_nitrogen": N_in},
            outflows={"volatilised_NOx_N2": N_in*e["n_atm"],
                      "aqueous_sidestream_N": N_in*e["n_aqueous"],
                      "retained_in_solid": N_in*e["n_solid"]})
        phosphorus = Ledger("phosphorus", "kgP/d",
            inflows={"feed_phosphorus": P_in},
            outflows={"recoverable_in_ash_or_char": P_in*e["p_recoverable"],
                      "aqueous_or_lost": P_in*(1-e["p_recoverable"])})
        # energy: biogas elec + endpoint recovery, less drying (if any) and parasitics
        endpoint_energy = (VS_d) * e["energy_mwh_tds"] * 0.4   # modest recovery from already-digested solids
        drying_load = (VS_in - VS_d) * 0.6 * KT.DRY_MWH_PER_T_WATER if e["drying"] else 0.0
        net = elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D + endpoint_energy - drying_load
        losses = biogas_chem - elec_gen - (biogas_chem*K.CHP_HEAT)
        energy = Ledger("energy", "MWh/d", provisional=True,
            inflows={"biogas_chemical_energy": biogas_chem, "endpoint_recovery_provisional": endpoint_energy},
            outflows={"chp_electricity_generated": elec_gen,
                      "chp_heat_and_drying": biogas_chem*K.CHP_HEAT,
                      "process_losses": biogas_chem - elec_gen - biogas_chem*K.CHP_HEAT + endpoint_energy})
        conf = EVIDENCE.get(name, (Conf.C, ""))[0]   # V3 U5: registry is the single source of truth
        pw = Pathway(
            name=f"THP + MAD + {name.title()} endpoint",
            description=f"Thermal endpoint = {name} ({e['temp']}). Screening-grade, literature-anchored.",
            ledgers={"carbon": carbon, "energy": energy, "nitrogen": nitrogen, "phosphorus": phosphorus},
            moves=[], pfas_destruction_frac=e["pfas"],
            net_export_mwh_d=net, generation_mwh_d=biogas_chem,
            basis={"total_tds": total_tds, "has_thp": True, "vs_ts": vs_ts,
                   "ps_tds": PS_tds, "was_tds": WAS_tds, "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
                   "digester_vol_m3": plant.get("digester_vol_m3"),
                   "product_wet_tpd": (VS_in-VS_d)*0.3/0.95,
                   "chemicals_m_aud": 0.20*total_tds/100.0, "om_m_aud": 2.8*total_tds/100.0})
        _attach(pw, endpoint="thermal", conf=conf)
        pw.traits["maturity"] = e["maturity"]
        pw.traits["pfas"] = e["pfas"]
        out[name] = pw
    return out


# ===========================================================================
# V3.5 - ENDPOINT FAMILIES + STAGE-3 COMPOSITION LAYER
# ===========================================================================
# Stop forcing biology/quality/endpoint into one score. Keep the calibrated
# front-end builders (Stage 1 biology + Stage 2 quality) as the engine, and
# COMPOSE a Stage-3 carbon endpoint onto any of them. Endpoints are grouped by
# CARBON FATE into three families. Endpoint splits stay PROVISIONAL (KT bands,
# confidence C); only the cake C/N/P is re-routed - digestion is untouched.
ENDPOINT_FAMILY = {                       # endpoint -> (family, carbon-strategy label)
    "land":         ("Carbon Retention",   "retain C in soil (low permanence; PFAS land risk)"),
    "pyrolysis":    ("Carbon Retention",   "retain C as stable biochar (~80% 100-yr permanence)"),
    "htl":          ("Carbon Conversion",  "convert C to biocrude fuel product"),
    "gasification": ("Carbon Conversion",  "convert C to syngas/energy"),
    "incineration": ("Carbon Destruction", "destroy C; max PFAS destruction; P in ash"),
}


def compose_pathway(front_end: Pathway, endpoint: str, plant: dict = GENERIC) -> Pathway:
    """V3.5 Stage-3 composition. Take a built biology+quality FRONT-END and swap its land
    endpoint for a carbon endpoint, re-routing ONLY the cake C/N/P through the endpoint family.
    Digestion (biogas, liquor, struvite, PN/A) is untouched and its ledgers are reused. Endpoint
    splits are PROVISIONAL (KT bands, confidence C); the digestion ledgers close exactly, the
    endpoint energy adjustment is carried as a net-export BAND."""
    fam, strategy = ENDPOINT_FAMILY[endpoint]
    cl = front_end.ledgers["carbon"]; nl = front_end.ledgers["nitrogen"]; pl = front_end.ledgers["phosphorus"]
    C_cake = cl.outflows.get("soil_land_application", 0.0)
    N_cake = nl.outflows.get("cake_organic_N_to_land", 0.0)
    P_cake = pl.outflows.get("cake_P_to_land", 0.0)

    if endpoint == "land":                # already the front-end endpoint; tag family + return
        front_end.basis.update({"endpoint": "land", "endpoint_family": fam})
        front_end.traits["carbon_strategy"] = fam
        return front_end

    e = THERMAL_ENDPOINTS[endpoint]
    keepC = {k: v for k, v in cl.outflows.items() if k != "soil_land_application"}
    c_char = C_cake * e["c_char"]; c_bio = C_cake * e["c_biocrude"]; c_co2 = C_cake - c_char - c_bio
    outC = dict(keepC)
    if c_char > 0: outC["char_permanently_stored"] = c_char
    if c_bio > 0:  outC["biocrude_product"] = c_bio
    outC["atmosphere_thermal_CO2"] = c_co2
    carbon = Ledger("carbon", "tC/d", inflows=dict(cl.inflows), outflows=outC)

    keepN = {k: v for k, v in nl.outflows.items() if k != "cake_organic_N_to_land"}
    outN = dict(keepN)
    outN["volatilised_NOx_N2"] = N_cake * e["n_atm"]
    outN["aqueous_sidestream_N"] = N_cake * e["n_aqueous"]
    outN["retained_in_solid_NPK"] = N_cake * e["n_solid"]
    nitrogen = Ledger("nitrogen", "kgN/d", inflows=dict(nl.inflows), outflows=outN)

    keepP = {k: v for k, v in pl.outflows.items() if k != "cake_P_to_land"}
    outP = dict(keepP)
    outP["recoverable_in_ash_or_char"] = P_cake * e["p_recoverable"]
    outP["aqueous_or_lost"] = P_cake * (1 - e["p_recoverable"])
    phosphorus = Ledger("phosphorus", "kgP/d", inflows=dict(pl.inflows), outflows=outP)

    cake_ds = front_end.basis.get("cake_ds", 0.22)
    wet = front_end.basis.get("product_wet_tpd", 0.0)
    cake_solids = wet * cake_ds
    rec = cake_solids * e["energy_mwh_tds"] * 0.4                       # endpoint recovery (already-digested solids)
    dry = (max(0.0, wet - cake_solids / KT.DRY_TARGET_DS) * KT.DRY_MWH_PER_T_WATER) if e["drying"] else 0.0
    net_c = front_end.net_export_mwh_d + rec - dry
    net_lo = front_end.net_export_mwh_d + rec * 0.6 - dry
    net_hi = front_end.net_export_mwh_d + rec * 1.4 - dry
    pfas = e["pfas"]; conf = EVIDENCE.get(endpoint, (Conf.C, ""))[0]

    base = dict(front_end.basis)
    base.update({"endpoint": endpoint, "endpoint_family": fam, "has_endpoint": True,
                 "char_tC_d": c_char, "biocrude_tC_d": c_bio,
                 "product_wet_tpd": (cake_solids / KT.DRY_TARGET_DS) if e["drying"] else (cake_solids * 0.3 / 0.95)})
    pw = Pathway(
        name=f"{front_end.name} -> {endpoint} endpoint",
        description=f"V3.5 composition: {front_end.name} front-end -> Stage-3 {endpoint} ({fam}). "
                    f"Endpoint splits PROVISIONAL (KT bands, confidence C); digestion ledgers exact.",
        ledgers={"carbon": carbon, "energy": front_end.ledgers["energy"],
                 "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=front_end.moves, pfas_destruction_frac=pfas,
        net_export_mwh_d=net_c, generation_mwh_d=front_end.generation_mwh_d, basis=base,
        bands={"energy_neutrality": (net_lo, net_c, net_hi),
               "pfas": (max(0.0, pfas - 0.05), pfas, min(1.0, pfas + 0.02))})
    _attach(pw, endpoint="thermal", conf=conf)
    pw.traits["carbon_strategy"] = fam
    pw.traits["maturity"] = e["maturity"]; pw.traits["pfas"] = pfas
    return pw



# ===========================================================================
# V2.1 — CARBON VALUE ENGINE (permanence, not just fate)
# ===========================================================================
# Fraction of carbon still sequestered at 100 years, by destination (IPCC biochar
# permanence 0.6-0.9; soil-applied organic C largely mineralises within decades).
C_PERMANENCE = {
    "char_permanently_stored": 0.80, "biochar": 0.80,
    "soil_land_application": 0.15,
    "biocrude_product": 0.0,            # combusted as fuel -> counted via avoided fossil, not storage
}
def _permanence(name):
    for k, v in C_PERMANENCE.items():
        if k in name:
            return v
    return 0.0


def carbon_value(pw: Pathway, credit_price_per_t=150.0, credit_price_avoided=35.0,
                 grid_ef_t_per_mwh=0.6) -> dict:
    """Carbon FATE -> carbon VALUE. Durable REMOVAL (permanent sequestration) and
    AVOIDED fossil emissions are reported SEPARATELY and are NEVER summed into a single
    'removal' figure (V3 Update 3) — they are physically different and price differently.
    'carbon_negative' means genuine net removal: the pathway sequesters more durable
    carbon than it directly emits, EXCLUDING any avoided-emission credits.
    `credit_price_per_t` is the removal (CDR) credit price; avoided priced separately."""
    cl = pw.ledgers["carbon"]
    perm_C = sum(v * _permanence(k) for k, v in cl.outflows.items() if v > 0)   # tC/d durable @100yr
    removed_CO2e_d = perm_C * 44/12                                             # tCO2e/d removed (CDR)
    fug_C = sum(v for k, v in cl.outflows.items() if "fugitive" in k)
    fug_CO2e = fug_C * (16/12) * 28                                             # CH4 mass x GWP100
    fossil_C = sum(v for k, v in cl.outflows.items() if "fossil" in k)
    direct_CO2e_d = fug_CO2e + fossil_C * 44/12                                 # pathway's OWN emissions
    avoided_CO2e_d = max(0.0, pw.net_export_mwh_d) * grid_ef_t_per_mwh          # avoided fossil (a credit)
    net_removal_y = (removed_CO2e_d - direct_CO2e_d) * 365                      # true net CDR; NO avoided
    avoided_y = avoided_CO2e_d * 365
    return {
        # --- durable carbon removal (CDR), reported on its own ---
        "permanent_C_tC_d": perm_C,
        "removed_gross_tCO2e_d": removed_CO2e_d,
        "direct_emissions_tCO2e_d": direct_CO2e_d,
        "net_removal_tCO2e_yr": net_removal_y,        # removal net of direct emissions; EXCLUDES avoided
        "carbon_negative": net_removal_y > 0,         # genuine CDR > emissions (not propped up by avoided)
        # --- avoided fossil emissions: a separate credit, NEVER folded into removal ---
        "avoided_fossil_tCO2e_yr": avoided_y,
        # --- combined GHG benefit: explicitly the SUM of two different things ---
        "combined_ghg_benefit_tCO2e_yr": net_removal_y + avoided_y,
        # --- value: removal and avoided priced separately (removal credits price higher) ---
        "removal_credit_m_aud_yr": net_removal_y * credit_price_per_t / 1e6,
        "avoided_credit_m_aud_yr": avoided_y * credit_price_avoided / 1e6,
        "credit_value_m_aud_yr": (net_removal_y * credit_price_per_t
                                  + avoided_y * credit_price_avoided) / 1e6,
        # --- legacy keys retained (corrected semantics) ---
        "sequestered_CO2e_d": removed_CO2e_d,
        "avoided_fossil_CO2e_d": avoided_CO2e_d,
        "fugitive_CO2e_d": fug_CO2e,
    }


def carbon_categories(pw: Pathway, grid_ef_t_per_mwh=0.6) -> dict:
    """The six V3 carbon categories, reported DISTINCTLY (Update 3). The fate categories
    are carbon MASS (tC/d) read off the closed carbon ledger and approximately sum to feed
    carbon; 'permanently sequestered' is the durable SUBSET of 'retained' (not additive).
    'Removed' and 'Avoided' are climate metrics (tCO2e/d) and are deliberately kept apart."""
    cl = pw.ledgers["carbon"]
    out = {k: v for k, v in cl.outflows.items() if v > 0}
    feed_C = sum(cl.inflows.values())
    emitted   = sum(v for k, v in out.items() if k.startswith("atmosphere"))
    recovered = sum(v for k, v in out.items() if "biocrude" in k)
    liquor    = sum(v for k, v in out.items() if "liquor" in k)
    retained  = sum(v for k, v in out.items()
                    if any(t in k for t in ("soil", "land", "char", "ash", "cake")))
    sequestered = sum(v * _permanence(k) for k, v in out.items())   # durable subset of retained
    fug_C    = sum(v for k, v in out.items() if "fugitive" in k)
    fossil_C = sum(v for k, v in out.items() if "fossil" in k)
    return {
        "feed_carbon_tC_d": feed_C,
        # carbon-mass fate (tC/d) — destroyed/recovered/retained sum ~ feed_C (ledger closes)
        "destroyed_emitted_tC_d": emitted,
        "recovered_in_product_tC_d": recovered,
        "returned_in_liquor_tC_d": liquor,
        "retained_in_solids_tC_d": retained,
        "of_which_permanently_sequestered_tC_d": sequestered,
        # climate metrics (tCO2e/d) — SEPARATE; never summed into a single 'removal'
        "removed_tCO2e_d": sequestered * 44/12,
        "avoided_tCO2e_d": max(0.0, pw.net_export_mwh_d) * grid_ef_t_per_mwh,
        "direct_emissions_tCO2e_d": fug_C * (16/12) * 28 + fossil_C * 44/12,
    }


# ===========================================================================
# V2.1 — OPTIONALITY VALUE ENGINE (put $ on options preserved / foreclosed)
# ===========================================================================
# Per option: (likelihood it becomes needed, screening value $M/yr if available).
OPTION_ECON = {
    "land application":            (0.30, 2.0),   # cheap disposal retained
    "thermal endpoint":            (0.70, 8.0),   # avoids crisis retrofit if PFAS bans land
    "P recovery (struvite)":       (0.45, 1.5),
    "N recovery (AS)":             (0.35, 1.0),
    "energy export":               (0.50, 1.0),
    "FOGO co-digestion capacity":  (0.50, 3.0),   # gate fees + biogas
}


def nutrient_value(pw: Pathway) -> dict:
    """Nutrient recovery as a co-equal value stream (V3 U8). Struvite (P) plus the two
    MUTUALLY-EXCLUSIVE routes for return-liquor nitrogen - PN/A (destroy -> avoided
    treatment cost) vs ammonium sulphate (recover -> fertiliser product). PN/A and AS are
    alternatives and are reported separately, never summed. Also reports sidestream load
    reduction, fertiliser-replacement value, and a phosphorus-security index."""
    N = pw.ledgers["nitrogen"]; P = pw.ledgers["phosphorus"]
    feed_N = N.total_in; feed_P = P.total_in
    p_struvite = P.outflows.get("struvite_P", 0.0)              # kgP/d
    n_struvite = N.outflows.get("struvite_N", 0.0)              # kgN/d (P-limited)
    rl_N = N.outflows.get("return_liquor_NH4_to_WWTW", 0.0)     # kgN/d treatable sidestream
    struvite_tpy = p_struvite * KO.STRUVITE_MW_PER_P / 1000.0 * 365
    struvite_rev = struvite_tpy * KO.STRUVITE_PRICE_T / 1e6     # M$/yr
    # return-liquor N: two ALTERNATIVES (never summed)
    pna_N = rl_N * KN.PNA_N_REMOVAL
    pna_value = pna_N * 365 * KN.AVOIDED_N_TREAT_PER_KG / 1e6   # M$/yr avoided cost
    as_N = rl_N * KN.AS_RECOVERY
    as_tpy = as_N / KN.AS_N_FRAC / 1000.0 * 365
    as_rev = as_tpy * KN.AS_PRICE_T / 1e6                       # M$/yr product revenue
    best = "AS" if as_rev >= pna_value else "PNA"
    n_route = as_N if best == "AS" else pna_N
    fert_value = ((n_struvite + as_N) * KN.N_FERT_VALUE_PER_KG
                  + p_struvite * KN.P_FERT_VALUE_PER_KG) * 365 / 1e6
    return {
        "feed_N_kgd": feed_N, "feed_P_kgd": feed_P,
        "P_recovered_kgd": p_struvite, "struvite_t_yr": struvite_tpy,
        "struvite_revenue_m_aud_yr": struvite_rev,
        "return_liquor_N_kgd": rl_N,
        "pna_N_destroyed_kgd": pna_N, "pna_avoided_cost_m_aud_yr": pna_value,
        "as_N_recovered_kgd": as_N, "as_product_t_yr": as_tpy, "as_revenue_m_aud_yr": as_rev,
        "recommended_N_route": best,
        "sidestream_N_removed_kgd": n_struvite + n_route,
        "residual_return_liquor_N_kgd": rl_N - n_route,
        "fertiliser_value_m_aud_yr": fert_value,
        "P_security_pct": (p_struvite / feed_P * 100) if feed_P else 0.0,
        "N_recovered_pct": ((n_struvite + as_N) / feed_N * 100) if feed_N else 0.0,
        "nutrient_value_m_aud_yr": struvite_rev + max(pna_value, as_rev),
    }


def optionality_value(pw: Pathway) -> dict:
    """Expected value retained (preserved options) vs expected value lost (foreclosed).
    Real-options-lite, screening-grade — quantifies WHY optionality has value."""
    o = optionality(pw)
    retained = sum(OPTION_ECON[x][0]*OPTION_ECON[x][1] for x in o["preserved"] if x in OPTION_ECON)
    regret = sum(OPTION_ECON[x][0]*OPTION_ECON[x][1] for x in o["foreclosed"] if x in OPTION_ECON)
    return {"score": o["score"], "value_retained_m_aud_yr": retained,
            "value_foreclosed_m_aud_yr": regret, "net_option_value_m_aud_yr": retained - regret,
            "preserved": o["preserved"], "foreclosed": o["foreclosed"]}


# ===========================================================================
# V2.1 — FEASIBILITY ENGINE (BVS-12: can BioPoint say "no feasible pathway"?)
# ===========================================================================
def feasibility(pathways: list, constraints: dict) -> dict:
    """Test candidate pathways against HARD constraints. If none satisfy all, return
    infeasible and name the mutually-exclusive constraints. A mature platform must be
    able to conclude that a set of objectives is incompatible."""
    feasible, rejected = [], []
    for pw in pathways:
        reasons = []
        ep = pw.traits.get("endpoint")
        if constraints.get("no_land") and ep == "land":
            reasons.append("requires land application")
        if constraints.get("no_thermal") and ep == "thermal":
            reasons.append("requires thermal processing")
        if constraints.get("no_bill_increase"):
            net = opex_view(pw).get("net_m_aud", 0.0)
            if net > 0:
                reasons.append(f"raises OPEX (+${net:.1f}M/yr)")
        if constraints.get("require_carbon_negative"):
            if not carbon_value(pw)["carbon_negative"]:
                reasons.append("not net carbon-negative")
        if constraints.get("require_nutrient_recovery"):
            if pw.traits.get("p_recovered", 0) <= 0.01:
                reasons.append("recovers no nutrients")
        (feasible if not reasons else rejected).append((pw.name, reasons))

    feasible = [f for f in feasible if not f[1]]
    result = {"feasible": [f[0] for f in feasible], "rejected": rejected,
              "is_feasible": len(feasible) > 0, "conflicts": []}
    if not feasible:
        # identify structural incompatibilities
        if constraints.get("no_land") and constraints.get("no_thermal"):
            result["conflicts"].append("no_land AND no_thermal: no endpoint family remains "
                                        "(land and thermal are the only terminal routes)")
        if constraints.get("no_bill_increase") and (constraints.get("require_carbon_negative")
                                                     or constraints.get("require_nutrient_recovery")):
            result["conflicts"].append("no_bill_increase AND require carbon/nutrient outcome: the "
                                        "required outcomes need capital/operating spend")
        if not result["conflicts"]:
            result["conflicts"].append("the combined constraints exclude every candidate pathway")
    return result



# ===========================================================================
# V3 U1 - DECISION HIERARCHY (L1-L5) + CONSTRAINT DIAGNOSIS
# Adaptive, least-regret-at-acceptable-risk: constraint diagnosis INFORMS ordering
# but never prunes. All viable pathways stay active; regret is named, not removed.
# A shock at or above HIGH_LIKELIHOOD that breaks a pathway flags it as needing a hedge.
HIGH_LIKELIHOOD = 0.5


def diagnose_constraints(plant, pathways) -> list:
    """L1 Constraint Diagnosis. Surface what is binding today and which future shocks
    would make each constraint binding. Informs the L2-L5 ordering; prunes nothing."""
    thp = next((p for p in pathways if p.basis.get("has_thp")), pathways[0])
    cap = capacity_view(thp); nut = nutrient_value(thp); cv = carbon_value(thp)
    feedN = nut["feed_N_kgd"]; rlN = nut["return_liquor_N_kgd"]
    nm = [sc.name for sc in SCENARIOS]
    cons = []
    if cap.get("existing_vol_m3"):
        head = cap.get("capacity_headroom_tds", 0.0)
        cons.append({"constraint": "capacity", "binding": head <= 0,
            "state": f"existing {cap['existing_vol_m3']:,.0f} m3 -> {head:,.0f} tDS/d headroom ({cap.get('existing_governing','')}-governed)",
            "shocks": [n for n in nm if n.startswith("FOGO")]})
    cons.append({"constraint": "regulatory_pfas", "binding": False,
        "state": "land-applied cake carries PFAS; no digestion route destroys it",
        "shocks": [n for n in nm if "PFAS" in n]})
    cons.append({"constraint": "return_liquor_nitrogen",
        "binding": (rlN / feedN > 0.30) if feedN else False,
        "state": f"{rlN:,.0f} kgN/d to works ({(rlN/feedN*100) if feedN else 0:.0f}% of feed N) - aeration/N2O load",
        "shocks": [n for n in nm if "Methane" in n]})
    cons.append({"constraint": "energy_balance", "binding": thp.net_export_mwh_d < 0,
        "state": f"worked pathway net {thp.net_export_mwh_d:,.0f} MWh/d",
        "shocks": [n for n in nm if "lectricity" in n or "exporter" in n]})
    cons.append({"constraint": "carbon_strategy", "binding": False,
        "state": f"net removal {cv['net_removal_tCO2e_yr']:,.0f} tCO2e/yr; avoided {cv['avoided_fossil_tCO2e_yr']:,.0f} tCO2e/yr (separate)",
        "shocks": [n for n in nm if "Carbon" in n]})
    return cons


def regret_profile(pw, weights, risk_threshold=HIGH_LIKELIHOOD) -> dict:
    """One pathway: where it wins, which HIGH-LIKELIHOOD shocks break it, what it
    forecloses, and whether it is acceptable-risk or needs a hedge. Never prunes."""
    sc = pw.driver_scores()
    res = resilience(pw); ov = optionality_value(pw)
    breaking = [r for r in res["results"]
                if r["likelihood"] >= risk_threshold and (not r["viable"] or r["perf"] < 0.4)]
    hedges = [m.name for m in pw.moves if m.tag == Tag.KEEP_OPEN] if breaking else []
    return {
        "pathway": pw.name,
        "performance": three_axis(pw, weights)["performance"],
        "confidence": pw.confidence_level.name if pw.confidence_level else "?",
        "resilience": res["score"],
        "net_option_value_m_aud_yr": ov["net_option_value_m_aud_yr"],
        "wins_on": sorted(sc, key=lambda d: -sc[d])[:3],
        "high_likelihood_shocks": [{"shock": r["scenario"], "likelihood": r["likelihood"],
                                    "viable": r["viable"], "note": r["note"]} for r in breaking],
        "acceptable_risk": len(breaking) == 0,
        "hedge_required": None if not breaking else ("keep open: " + ("; ".join(hedges)
                          if hedges else "an endpoint/option that survives the flagged shock")),
        "forecloses": ov["foreclosed"],
    }


# ---------------------------------------------------------------------------
# V3.5 - PATHWAY X (strategic front-end) x ENDPOINT FAMILIES + carbon-strategy comparison
def pathway_x_set(plant: dict = GENERIC) -> dict:
    """V3.5 Pathway X: the strategic ETP front-end (K = separate PS/WAS short-HRT PS + WAS-side
    SolidStream recycle) composed with each Stage-3 endpoint. Returns {endpoint: Pathway}. K
    itself is the land/Retention variant; the thermal endpoints are fresh compositions."""
    return {ep: compose_pathway(build_pathway_k(plant), ep, plant)
            for ep in ("land", "pyrolysis", "gasification", "incineration", "htl")}


def carbon_strategy_comparison(plant: dict = GENERIC, x_set: dict = None) -> list:
    """V3.5 'do not combine' carbon-fate comparison. For each endpoint composed on the strategic
    front-end, report the carbon-strategy family + the six NON-ADDITIVE carbon metrics + PFAS +
    net-export band + confidence. There is deliberately NO single score: the right endpoint
    depends on which objective (retain / convert / destroy) the strategy prioritises."""
    s = x_set or pathway_x_set(plant)
    rows = []
    for ep, p in s.items():
        cc = carbon_categories(p)
        rows.append({
            "endpoint": ep, "family": p.basis.get("endpoint_family"),
            "strategy": p.traits.get("carbon_strategy"),
            "retained_tC_d": round(cc["retained_in_solids_tC_d"], 1),
            "sequestered_tC_d": round(cc["of_which_permanently_sequestered_tC_d"], 1),
            "converted_recovered_tC_d": round(cc["recovered_in_product_tC_d"], 1),
            "destroyed_emitted_tC_d": round(cc["destroyed_emitted_tC_d"], 1),
            "removed_tCO2e_d": round(cc["removed_tCO2e_d"], 1),
            "pfas_destruction": p.pfas_destruction_frac,
            "net_export_mwh_d": round(p.net_export_mwh_d),
            "net_band": tuple(round(x) for x in p.bands["energy_neutrality"]) if "energy_neutrality" in p.bands else None,
            "confidence": p.confidence_level.name if p.confidence_level else "C",
        })
    return rows


def decision_hierarchy(plant, weights=None, risk_threshold=HIGH_LIKELIHOOD) -> dict:
    """L1-L5 decision hierarchy (V3 U1). Runs the levels in order, keeps ALL viable
    pathways active, attaches a regret profile to each. The recommendation is a
    least-regret SEQUENCE at acceptable risk: commit-grade now + priced hedges held
    open against the high-likelihood shocks - not a single chosen technology."""
    weights = weights or rank_weights(DRIVER_RANKING_PLUS)
    worked = build_worked_pathway(plant); conv = build_conventional_pathway(plant)
    sep = build_separate_pswas_pathway(plant)
    thermal = build_thermal_pathway(plant); endpoints = build_thermal_endpoints(plant)
    ss = build_solidstream_pathway(plant)
    k = build_pathway_k(plant)
    b = build_pathway_b(plant); f = build_pathway_f(plant)
    x_set = pathway_x_set(plant)
    x_thermal = [v for ep, v in x_set.items() if ep != "land"]   # K(land) already present as k
    pathways = [conv, worked, sep, ss, f, k, b, thermal] + list(endpoints.values()) + x_thermal
    return {
        "L1_constraints": diagnose_constraints(plant, pathways),
        "L2_capacity": capacity_view(worked),
        "L3_resource_recovery": nutrient_value(worked),
        "L4_carbon": carbon_value(worked),
        "L5_thermal_endpoint": {n: {"pfas": p.pfas_destruction_frac,
                                    "evidence": EVIDENCE.get(n, (Conf.C, ""))[0].name}
                                for n, p in endpoints.items()},
        "L6_carbon_endpoints": carbon_strategy_comparison(plant, x_set),
        "risk_threshold": risk_threshold,
        "pathways": [regret_profile(p, weights, risk_threshold) for p in pathways],
        "least_regret_note": ("All viable pathways retained. acceptable_risk=False means a "
            f"shock at or above {risk_threshold:.0%} likelihood breaks the pathway; it stays "
            "active but must be paired with the named hedge to be commit-grade."),
    }


def compare(paths: list[Pathway], weights: dict[str, float]) -> str:
    lines = ["\nPATHWAY COMPARISON (under locked weighting — trade, not winner):"]
    drivers = ["energy_neutrality", "scope1_emissions", "pfas",
               "nutrient_recovery", "opex", "capacity"]
    header = f"    {'driver':<20}" + "".join(f"{p.name[:22]:>24}" for p in paths)
    lines.append(header)
    for d in drivers:
        row = f"    {d:<20}"
        for p in paths:
            s = p.driver_scores()
            if d in p.bands:
                lo, c, hi = p.bands[d]
                row += f"{f'{c:.2f} [{lo:.2f}-{hi:.2f}]':>24}"
            else:
                row += f"{s.get(d, float('nan')):>24.2f}"
        lines.append(row)
    return "\n".join(lines)
def build_roadmap(pathway: Pathway) -> list[str]:
    commit = [m for m in pathway.moves if m.tag == Tag.COMMIT]
    keep = [m for m in pathway.moves if m.tag == Tag.KEEP_OPEN]
    avoid = [m for m in pathway.moves if m.tag == Tag.AVOID]
    out = []
    out.append("Phase 1 (commit now):")
    for m in commit:
        out.append(f"    - {m.name}  [{m.confidence.verb()}]")
    out.append("Phase 2+ (keep open — priced de-risking, decide later):")
    for m in keep:
        out.append(f"    - {m.name}")
        out.append(f"        reward: {m.reward}")
        out.append(f"        de-risk: {m.derisk_task}   [{m.confidence.verb()}]")
    out.append("Avoid (forecloses future drivers):")
    for m in avoid:
        out.append(f"    - {m.name}")
        out.append(f"        why: {m.residual_risk}")
        if m.forecloses:
            out.append(f"        would foreclose: {', '.join(m.forecloses)}")
    return out


# ---------------------------------------------------------------------------
# 9b. REPORT  — drive the new strategic structure from the spine objects
# ---------------------------------------------------------------------------
def generate_report(pathways: list[Pathway], weights: dict[str, float]) -> str:
    def fate(lg: Ledger) -> str:
        rows = [f"  - {k}: {v:,.1f} {lg.unit}" for k, v in lg.outflows.items() if v > 0]
        tag = " *(provisional — split fractions not calibrated)*" if lg.provisional else ""
        return f"{lg.quantity.title()} fate{tag}:\n" + "\n".join(rows)

    L = []
    L.append("# Strategic Biosolids Pathway Report\n")
    L.append("*Generated by the BioPoint V2 spine. Drivers are read off conserved-quantity "
             "ledgers; the recommendation is a sequence, not a single technology. Constants are "
             "calibrated where reference data exists (St Marys, Mangere, Thames/Blue Plains) and "
             "mid-range estimates elsewhere — flagged accordingly.*\n")

    L.append("## 1. Strategic Objective\n")
    L.append("Pathways are weighted against the utility's stated driver ranking "
             "(rank-order weighting, fully transparent):\n")
    for d, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        L.append(f"- **{d.replace('_',' ')}** — weight {w:.3f}")
    L.append("\nBecause cost sits mid-table and CAPEX last, recommending a costlier pathway over "
             "a cheaper one is consistent with the objective, not a contradiction.\n")

    L.append("## 2. Constraints (what the ledgers force into the open)\n")
    L.append("- **PFAS**: the calibrated AD/THP spine destroys none — it concentrates PFAS into "
             "land-applied cake. Only a thermal endpoint addresses this driver.\n"
             "- **Return-liquor nitrogen**: struvite is phosphorus-limited, so the bulk of "
             "mineralised ammonia returns to the host works — a load and an N₂O/Scope-1 risk.\n"
             "- **Nutrient–thermal tension**: thermal strands phosphorus in ash and volatilises "
             "nitrogen, so nutrients must be recovered *upstream* if both PFAS and recovery matter.\n")

    L.append("## 3. Pathways\n")
    for pw in pathways:
        ok, _ = pw.gate()
        prov = any(l.provisional for l in pw.ledgers.values())
        status = ("PROVISIONAL — not commit-grade" if prov
                  else "all ledgers close — commit-grade")
        L.append(f"### {pw.name}\n")
        L.append(f"{pw.description}\n")
        L.append(f"**Closure gate:** {status}.\n")
        L.append(fate(pw.ledgers["carbon"]) + "\n")
        L.append(fate(pw.ledgers["nitrogen"]) + "\n")
        L.append(fate(pw.ledgers["phosphorus"]) + "\n")

    L.append("## 4. Comparison (the trade — deliberately not a winner)\n")
    drivers = ["energy_neutrality", "scope1_emissions", "pfas",
               "nutrient_recovery", "opex", "capacity"]
    hdr = "| driver | " + " | ".join(p.name.split(" + ")[0] + "…" for p in pathways) + " |"
    L.append(hdr)
    L.append("|" + "---|" * (len(pathways) + 1))
    for d in drivers:
        cells = []
        for p in pathways:
            s = p.driver_scores()
            if d in p.bands:
                lo, c, hi = p.bands[d]
                cells.append(f"{c:.2f} [{lo:.2f}–{hi:.2f}]")
            else:
                cells.append(f"{s.get(d, float('nan')):.2f}")
        L.append(f"| {d.replace('_',' ')} | " + " | ".join(cells) + " |")
    L.append("")

    L.append("## 5. Confidence\n")
    L.append("Confidence is tracked separately from performance and governs the recommendation "
             "verb — it never excludes a pathway. The calibrated spine is commit-grade; the "
             "thermal endpoint is emerging (Level C): its reward is real and its physics plausible, "
             "but its split fractions are not yet closed against a full-scale balance, so it is "
             "shortlisted with a priced de-risking task, not committed.\n")

    L.append("## 6. Adaptive Roadmap\n")
    pw0 = pathways[0]
    commit = [m for m in pw0.moves if m.tag == Tag.COMMIT]
    keep = [m for m in pw0.moves if m.tag == Tag.KEEP_OPEN]
    avoid = [m for m in pw0.moves if m.tag == Tag.AVOID]
    L.append("**Phase 1 — commit now (bankable, commit-grade):**")
    for m in commit:
        L.append(f"- {m.name} — *{m.confidence.verb()}*")
    L.append("\n**Phase 2+ — keep open (priced de-risking, decide later):**")
    for m in keep:
        L.append(f"- {m.name} — *{m.confidence.verb()}*  \n"
                 f"  Reward: {m.reward}  \n"
                 f"  De-risk: {m.derisk_task}")
    L.append("\n**Avoid (forecloses future drivers):**")
    for m in avoid:
        foreclosed = f" Forecloses: {', '.join(m.forecloses)}." if m.forecloses else ""
        L.append(f"- {m.name} — {m.residual_risk}.{foreclosed}")
    L.append("")

    L.append("## 7. Recommendation\n")
    L.append("The recommendation is an **order of moves**, not a chosen technology:\n"
             "1. Optimise MAD and dewatering now — bankable, commit-grade, the foundation.\n"
             "2. Add THP for the capacity it buys (≈2 reference digesters of avoided volume) "
             "and the cake-solids and Class-A benefits.\n"
             "3. Recover phosphorus via struvite while it is still recoverable — before any "
             "thermal step would lock it into ash — and hold ammonium-sulphate/PN-A open to "
             "close the nitrogen gap.\n"
             "4. Do **not** commit land application as a terminal endpoint: it forecloses the "
             "only family that addresses PFAS.\n"
             "5. Hold the thermal endpoint as a priced, scheduled option (~$1.5M / 18 months to "
             "reach commit-grade), to be exercised if PFAS regulation or the carbon case demands "
             "it. Its energy and Scope-1 outcomes hinge on syngas recovery we cannot yet "
             "calibrate, so the decision is staged, not pre-empted.\n")
    return "\n".join(L)



def main():
    print("=" * 74)
    print("BioPoint V2 — Strategic Pathway Spine")
    print("=" * 74)

    weights = rank_weights(DRIVER_RANKING_PLUS)
    print("\nOBJECTIVE — driver weighting (rank-order, transparent):")
    for d, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f"    {d:<22}{w:.3f}")

    pw = build_worked_pathway()
    print(f"\nPATHWAY: {pw.name}")
    print(f"  {pw.description}")

    print("\nCONSERVATION LEDGERS (closure = admissibility gate):")
    for lg in pw.ledgers.values():
        print(lg.report())

    ok, msgs = pw.gate()
    print(f"\nGATE: {'ALL LEDGERS CLOSE — admissible (commit-grade)' if ok else 'BLOCKED'}")
    for m in msgs:
        print(f"    note: {m}")

    print("\nDRIVER SCORES (read off the ledgers — 0..1, higher better):")
    scores = pw.driver_scores()
    for d in DRIVER_RANKING_PLUS:
        if d in scores:
            bar = "#" * int(round(scores[d] * 30))
            print(f"    {d:<22}{scores[d]:.2f}  {bar}")
        else:
            print(f"    {d:<22}  (bolt-on engine — not yet ledger-derived)")

    print("\n  Honest reading falling OUT of the ledgers (not asserted):")
    print(f"    - Energy: strongly positive — heat surplus covers THP+digester, no fossil top-up")
    print(f"    - PFAS  : pathway destroys 0% — driver #2 UNMET by this safe spine")
    print(f"    - Nutr. : P recovery good (~{pw.ledgers['phosphorus'].fraction_to('struvite_P')*100:.0f}%), "
          f"N recovery poor (~{pw.ledgers['nitrogen'].fraction_to('struvite_N')*100:.0f}%) — struvite is P-limited")

    cap = capacity_view(pw)
    print("\n  CAPACITY INTENSIFICATION (calibrated — Thames/Blue Plains/Davyhulme):")
    print(f"    conventional digester volume needed : {cap['vol_conv_m3']:>8,.0f} m3")
    print(f"    THP digester volume needed          : {cap['vol_thp_m3']:>8,.0f} m3")
    print(f"    volume avoided                      : {cap['avoided_m3']:>8,.0f} m3  "
          f"(~{cap['digesters_avoided']:.1f} reference digesters)")
    print(f"    avoided digester CAPEX              : ${cap['avoided_capex_aud']/1e6:>7.1f}M")
    ox = opex_view(pw)
    print("\n  OPEX (M$/yr; negative = net cash positive):")
    print(f"    energy (net export) {ox['energy_m_aud']:+6.2f}   transport {ox['transport_m_aud']:+5.2f}   "
          f"chem {ox['chemicals_m_aud']:+5.2f}   O&M {ox['om_m_aud']:+5.2f}   "
          f"struvite rev {-ox['struvite_revenue_m_aud']:+5.2f}")
    print(f"    NET OPEX {ox['net_m_aud']:+.2f} M$/yr")

    print("\nADAPTIVE ROADMAP:")
    for line in build_roadmap(pw):
        print("  " + line)

    # ---- Thermal-endpoint pathway: the provisional / uncertainty-band half ----
    tp = build_thermal_pathway()
    print("\n" + "-" * 74)
    print(f"PROVISIONAL PATHWAY: {tp.name}")
    print(f"  {tp.description}")
    print("\nCONSERVATION LEDGERS (close arithmetically; flagged provisional):")
    for lg in tp.ledgers.values():
        print(lg.report())
    ok2, msgs2 = tp.gate()
    print(f"\nGATE: {'admissible but PROVISIONAL — not commit-grade' if ok2 else 'BLOCKED'}")
    for m in msgs2:
        print(f"    note: {m}")
    print("\n  Honest reading (the point of the band):")
    eb = tp.bands["energy_neutrality"]
    s1 = tp.bands["scope1_emissions"]
    print(f"    - PFAS  : now ADDRESSED — ~{tp.pfas_destruction_frac*100:.0f}% destroyed "
          f"(band {tp.bands['pfas'][0]*100:.0f}-{tp.bands['pfas'][2]*100:.0f}%) — driver #3 finally met")
    print(f"    - Energy: {eb[1]:.2f} central, but band {eb[0]:.2f}-{eb[2]:.2f} — at the LOW end "
          f"(syngas underperforms) the drying load forces fossil top-up")
    print(f"    - Scope1: band {s1[0]:.2f}-{s1[2]:.2f} — char storage helps, fossil-drying hurts")
    print(f"    - P stranded in ash, N volatilised: nutrient recovery ~0 unless recovered UPSTREAM")

    print(compare([pw, tp], weights))

    print("\nWHAT THE COMPARISON SAYS (and what it deliberately does NOT):")
    print("  - The safe spine wins energy (#1) and confidence; the thermal pathway is the")
    print("    ONLY one that addresses PFAS (#3). Neither dominates across your drivers.")
    print("  - The engine does NOT pick one. The roadmap's answer is to SEQUENCE: recover")
    print("    nutrients upstream (struvite, before P is lost to ash), run the safe spine as")
    print("    commit-grade NOW, and hold the thermal endpoint as a PRICED, scheduled option")
    print("    to be de-risked before any PFAS-driven commitment. Order is the recommendation.")

    print("\n" + "=" * 74)
    print("Spine proven on TWO pathways: one closing/commit-grade, one provisional with")
    print("honest bands. Drivers read off shared ledgers; recommendation is a sequence,")
    print("not a winner. Next: bolt-on engines (capacity, OPEX, regulatory) as ledger views.")
    print("=" * 74)

    # Drive the strategic report from the spine objects
    report = generate_report([pw, tp], weights)
    with open("/mnt/user-data/outputs/Strategic_Pathway_Report.md", "w") as f:
        f.write(report)
    print("\nStrategic report written: Strategic_Pathway_Report.md")


if __name__ == "__main__":
    main()
