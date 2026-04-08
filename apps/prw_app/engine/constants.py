"""
PurePoint — engine constants
All fixed parameters: classes, LRV requirements, barrier credits,
treatment trains, chemical groups, CCP framework.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Product classes
# ---------------------------------------------------------------------------

CLASSES = ["C", "A", "A+", "PRW"]

CLASS_LABELS = {
    "C":   "Class C — Non-potable reuse",
    "A":   "Class A — Unrestricted urban reuse",
    "A+":  "Class A+ — High-exposure / food-crop reuse",
    "PRW": "Purified Recycled Water — Indirect potable",
}

CLASS_COLOURS = {
    "C":   "#22c87a",
    "A":   "#00b4d8",
    "A+":  "#a78bfa",
    "PRW": "#f5a623",
}

# ---------------------------------------------------------------------------
# LRV requirements by class  [protozoa, bacteria, virus]
# ---------------------------------------------------------------------------

LRV_REQUIRED: Dict[str, Dict[str, float]] = {
    "C":   {"protozoa": 3.0, "bacteria": 4.0, "virus": 2.0},
    "A":   {"protozoa": 4.0, "bacteria": 5.0, "virus": 4.0},
    "A+":  {"protozoa": 5.0, "bacteria": 6.0, "virus": 6.0},
    "PRW": {"protozoa": 6.0, "bacteria": 6.0, "virus": 8.0},
}

# ---------------------------------------------------------------------------
# Barrier LRV credits  {name: (protozoa, bacteria, virus)}
# ---------------------------------------------------------------------------

BARRIER_CREDITS: Dict[str, Tuple[float, float, float]] = {
    "Coagulation + clarification": (1.0, 0.5, 0.5),
    "MF/UF membrane":              (4.0, 2.0, 1.0),
    "RO":                          (2.0, 2.0, 2.0),
    "Ozone":                       (0.5, 2.0, 2.0),
    "UV-AOP":                      (2.0, 3.0, 3.0),
    "UV (40 mJ/cm²)":              (3.0, 4.0, 3.0),
    "Cl₂ disinfection":            (0.5, 3.0, 4.0),
    "BAC/GAC":                     (0.0, 0.5, 0.0),
    "Chloramine residual":         (0.0, 0.5, 0.0),
}

# ---------------------------------------------------------------------------
# Treatment trains by class
# steps: ordered list of process steps
# key_barriers: steps that carry primary LRV credit
# lrv_barriers: steps included in LRV calculation
# note: design rationale
# ---------------------------------------------------------------------------

TREATMENT_TRAINS: Dict[str, dict] = {
    "C": {
        "steps": [
            "Secondary effluent",
            "Coagulation + clarification",
            "Dual-media filtration",
            "Cl₂ disinfection",
            "Class C storage",
        ],
        "key_barriers": ["Coagulation + clarification", "Cl₂ disinfection"],
        "lrv_barriers": ["Coagulation + clarification", "Cl₂ disinfection"],
        "note": (
            "Minimum-sufficient train for non-potable reuse. "
            "No membrane or advanced oxidation required. "
            "Disinfection provides primary microbial barrier. "
            "Not appropriate for food-crop irrigation or potable applications."
        ),
    },
    "A": {
        "steps": [
            "Secondary effluent",
            "MF/UF membrane",
            "Ozone or UV-AOP",
            "BAC polishing",
            "Cl₂ disinfection",
            "Class A storage",
        ],
        "key_barriers": ["MF/UF membrane", "Ozone or UV-AOP"],
        "lrv_barriers": ["MF/UF membrane", "Ozone", "UV-AOP", "Cl₂ disinfection"],
        "note": (
            "Membrane filtration provides absolute protozoan and TSS barrier. "
            "Ozone or UV-AOP required for PPCP partial removal and virus supplementation. "
            "BAC reduces AOC and disinfection by-product precursors. "
            "Suitable for unrestricted urban reuse, parks, road irrigation."
        ),
    },
    "A+": {
        "steps": [
            "Secondary effluent",
            "MF/UF membrane",
            "Ozone-AOP",
            "BAC/GAC",
            "UV (40 mJ/cm²)",
            "Cl₂ disinfection",
            "Class A+ storage",
        ],
        "key_barriers": ["MF/UF membrane", "Ozone-AOP", "UV (40 mJ/cm²)"],
        "lrv_barriers": [
            "MF/UF membrane", "Ozone", "BAC/GAC",
            "UV (40 mJ/cm²)", "Cl₂ disinfection",
        ],
        "note": (
            "Enhanced chemical barrier via ozone-AOP. "
            "GAC polishing for CEC and PFAS management. "
            "Independent UV barrier provides protozoa and virus redundancy. "
            "Two independent oxidation steps required. "
            "Suitable for food-crop irrigation, high-exposure applications."
        ),
    },
    "PRW": {
        "steps": [
            "Secondary effluent",
            "MF/UF membrane",
            "RO",
            "UV-AOP",
            "Cl₂ CT disinfection",
            "Re-mineralisation",
            "Environmental buffer / indirect potable",
        ],
        "key_barriers": ["MF/UF membrane", "RO", "UV-AOP"],
        "lrv_barriers": [
            "MF/UF membrane", "RO", "UV-AOP", "Cl₂ disinfection",
        ],
        "note": (
            "Full potable reuse train. "
            "RO provides absolute chemical and ionic barrier — PFAS, nitrate, CECs. "
            "UV-AOP provides final pathogen kill and residual organic oxidation. "
            "Re-mineralisation required post-RO for corrosion control and aesthetics. "
            "Environmental buffer (aquifer, reservoir) provides additional attenuation "
            "and residence time before extraction."
        ),
    },
}

# ---------------------------------------------------------------------------
# Chemical contaminant matrix
# Structure: group → {risk, mechanism, credit, surrogate, residual_risk} × class
# ---------------------------------------------------------------------------

CHEMICAL_GROUPS = [
    "PFAS",
    "Nitrosamines",
    "PPCPs",
    "Pesticides",
    "Endocrine-active compounds",
    "Industrial organics",
    "Bulk organic toxicity",
]

CHEMICAL_MATRIX: Dict[str, Dict[str, Dict[str, str]]] = {
    "PFAS": {
        "C": {
            "risk": "Low",
            "mechanism": "Dilution only — no removal mechanism",
            "credit": "None",
            "surrogate": "N/A",
            "residual_risk": "High",
        },
        "A": {
            "risk": "Medium",
            "mechanism": "Limited GAC at adequate EBCT",
            "credit": "Partial",
            "surrogate": "DOC trend; periodic PFAS analytics",
            "residual_risk": "Medium-High",
        },
        "A+": {
            "risk": "High",
            "mechanism": "GAC/BAC polishing — long-chain addressed",
            "credit": "Good (long-chain); partial (short-chain)",
            "surrogate": "DOC + periodic PFAS suite monitoring",
            "residual_risk": "Low-Medium",
        },
        "PRW": {
            "risk": "High",
            "mechanism": "RO — >99% removal all chain lengths",
            "credit": "Definitive",
            "surrogate": "Conductivity + periodic PFAS spot check",
            "residual_risk": "Very Low",
        },
    },
    "Nitrosamines": {
        "C": {
            "risk": "Low",
            "mechanism": "Cl₂ partial oxidation",
            "credit": "Partial",
            "surrogate": "Cl₂ CT",
            "residual_risk": "Medium",
        },
        "A": {
            "risk": "Medium",
            "mechanism": "UV-AOP photolysis and hydroxyl oxidation",
            "credit": "Good",
            "surrogate": "UV dose + Cl₂ CT",
            "residual_risk": "Low-Medium",
        },
        "A+": {
            "risk": "Medium",
            "mechanism": "Ozone-AOP oxidation",
            "credit": "Strong",
            "surrogate": "O₃/TOC ratio + UV dose",
            "residual_risk": "Low",
        },
        "PRW": {
            "risk": "High",
            "mechanism": "UV-AOP destruction + RO rejection",
            "credit": "Definitive",
            "surrogate": "UV dose + conductivity",
            "residual_risk": "Very Low",
        },
    },
    "PPCPs": {
        "C": {
            "risk": "Low",
            "mechanism": "Minimal — no targeted removal",
            "credit": "None",
            "surrogate": "N/A",
            "residual_risk": "High",
        },
        "A": {
            "risk": "Medium",
            "mechanism": "Ozone partial / UV-AOP oxidation",
            "credit": "Moderate",
            "surrogate": "UV254 removal %",
            "residual_risk": "Medium",
        },
        "A+": {
            "risk": "High",
            "mechanism": "Ozone-AOP + BAC biological degradation",
            "credit": "Good",
            "surrogate": "UV254 + O₃ CT",
            "residual_risk": "Low",
        },
        "PRW": {
            "risk": "High",
            "mechanism": "RO rejection + UV-AOP oxidation",
            "credit": "Strong",
            "surrogate": "Conductivity + UV254",
            "residual_risk": "Very Low",
        },
    },
    "Pesticides": {
        "C": {
            "risk": "Low",
            "mechanism": "None",
            "credit": "None",
            "surrogate": "N/A",
            "residual_risk": "Low-Medium",
        },
        "A": {
            "risk": "Low-Medium",
            "mechanism": "Ozone / UV partial oxidation",
            "credit": "Partial",
            "surrogate": "O₃ CT",
            "residual_risk": "Low",
        },
        "A+": {
            "risk": "Medium",
            "mechanism": "Ozone-AOP + GAC adsorption",
            "credit": "Good",
            "surrogate": "O₃ CT + GAC EBCT",
            "residual_risk": "Very Low",
        },
        "PRW": {
            "risk": "Medium",
            "mechanism": "RO rejection + AOP",
            "credit": "Strong",
            "surrogate": "Conductivity",
            "residual_risk": "Very Low",
        },
    },
    "Endocrine-active compounds": {
        "C": {
            "risk": "Medium",
            "mechanism": "Cl₂ partial oxidation",
            "credit": "Partial",
            "surrogate": "Cl₂ CT",
            "residual_risk": "Medium",
        },
        "A": {
            "risk": "Medium",
            "mechanism": "Ozone / UV-AOP oxidation",
            "credit": "Good",
            "surrogate": "Bioassay (ER-CALUX); O₃ CT",
            "residual_risk": "Low-Medium",
        },
        "A+": {
            "risk": "High",
            "mechanism": "Ozone-AOP + BAC biodegradation",
            "credit": "Strong",
            "surrogate": "Bioassay panel + O₃ CT",
            "residual_risk": "Very Low",
        },
        "PRW": {
            "risk": "High",
            "mechanism": "RO rejection + UV-AOP",
            "credit": "Definitive",
            "surrogate": "Bioassay + conductivity",
            "residual_risk": "Very Low",
        },
    },
    "Industrial organics": {
        "C": {
            "risk": "Low",
            "mechanism": "Dilution",
            "credit": "None",
            "surrogate": "N/A",
            "residual_risk": "Medium",
        },
        "A": {
            "risk": "Medium",
            "mechanism": "Ozone + BAC/GAC",
            "credit": "Moderate",
            "surrogate": "DOC + TOC",
            "residual_risk": "Low",
        },
        "A+": {
            "risk": "Medium",
            "mechanism": "Ozone-AOP + GAC",
            "credit": "Good",
            "surrogate": "DOC + TOC + UV254",
            "residual_risk": "Very Low",
        },
        "PRW": {
            "risk": "High",
            "mechanism": "RO — definitive removal",
            "credit": "Definitive",
            "surrogate": "Conductivity + TOC",
            "residual_risk": "Very Low",
        },
    },
    "Bulk organic toxicity": {
        "C": {
            "risk": "Low",
            "mechanism": "Minimal",
            "credit": "None",
            "surrogate": "N/A",
            "residual_risk": "Medium",
        },
        "A": {
            "risk": "Medium",
            "mechanism": "Bioassay-guided treatment screening",
            "credit": "Screening only",
            "surrogate": "Bioassay (DR-CALUX)",
            "residual_risk": "Low-Medium",
        },
        "A+": {
            "risk": "Medium",
            "mechanism": "Ozone-AOP + bioassay confirmation",
            "credit": "Moderate",
            "surrogate": "Multi-endpoint bioassay panel",
            "residual_risk": "Low",
        },
        "PRW": {
            "risk": "High",
            "mechanism": "Full train + multi-bioassay verification",
            "credit": "Strong",
            "surrogate": "Multi-bioassay + TOC",
            "residual_risk": "Very Low",
        },
    },
}

# ---------------------------------------------------------------------------
# CCP / surrogate framework
# ---------------------------------------------------------------------------

CCP_FRAMEWORK = [
    {
        "barrier": "MF/UF membrane",
        "mechanism": "Physical size exclusion — protozoa, TSS, turbidity",
        "ccp": "Transmembrane pressure (TMP); PDT / vacuum hold integrity test",
        "envelope": "TMP within design range; PDT holding time per membrane spec",
        "failure": "TMP spike; PDT fail → isolate rack, divert, investigate",
    },
    {
        "barrier": "RO",
        "mechanism": "Ionic separation — dissolved salts, PFAS, organics, nitrate",
        "ccp": "Permeate conductivity; normalised salt rejection; SDI",
        "envelope": "Salt rejection ≥98%; permeate conductivity <50 µS/cm; SDI <3",
        "failure": "Conductivity rise >10% above baseline → O-ring/membrane investigation",
    },
    {
        "barrier": "Ozone",
        "mechanism": "Oxidation — PPCPs, nitrosamines, EACs, colour, taste/odour",
        "ccp": "O₃ dose / TOC ratio; CT (mg·min/L); residual at contactor outlet",
        "envelope": "O₃:TOC ≥0.5 mg/mg; CT per target compound; residual ≥0.1 mg/L",
        "failure": "CT below threshold → increase dose or reduce flow rate",
    },
    {
        "barrier": "UV-AOP (UV + H₂O₂)",
        "mechanism": "Hydroxyl radical oxidation — trace organics, nitrosamines, pathogens",
        "ccp": "Validated UV dose (mJ/cm²); UVT; H₂O₂ residual",
        "envelope": "UV dose ≥500 mJ/cm² for AOP; UVT ≥65%; H₂O₂ ≥5 mg/L",
        "failure": "UVT drop or lamp output alarm → dose monitoring → divert",
    },
    {
        "barrier": "UV (40 mJ/cm²)",
        "mechanism": "DNA damage — Cryptosporidium, viruses, bacteria",
        "ccp": "Validated UV dose; UVT; lamp output / sensor signal",
        "envelope": "Validated dose ≥40 mJ/cm²; UVT ≥75%; lamp within calibration",
        "failure": "Dose below validation → alarm → lamp replacement or flow reduction",
    },
    {
        "barrier": "BAC/GAC",
        "mechanism": "Biological and adsorptive organic removal — DOC, AOC, CECs",
        "ccp": "DOC removal %; UV254 removal %; EBCT",
        "envelope": "DOC reduction ≥30%; EBCT ≥10 min (BAC), ≥15 min (GAC for PFAS)",
        "failure": "DOC/UV254 breakthrough → media exhaustion check; increase EBCT",
    },
    {
        "barrier": "Cl₂ disinfection",
        "mechanism": "Chemical inactivation — bacteria, viruses",
        "ccp": "CT (mg·min/L); pH; temperature; free Cl₂ residual",
        "envelope": "CT per target table; free Cl₂ residual ≥0.5 mg/L; pH ≤8.0",
        "failure": "CT below target → increase dose; check pH; verify contact time",
    },
]

# ---------------------------------------------------------------------------
# Effluent type presets
# ---------------------------------------------------------------------------

EFFLUENT_PRESETS = {
    "cas": {
        "label": "Conventional Activated Sludge (CAS)",
        "turb_med": 2.0, "turb_p95": 6.0,  "turb_p99": 12.0,
        "tss_med":  5.0, "tss_p95":  12.0, "tss_p99":  20.0,
        "doc_med":  10.0,"doc_p95":  16.0, "doc_p99":  22.0,
        "uv254_med":0.15,"uv254_p95":0.25, "uv254_p99":0.35,
        "ecoli_med":5000,"ecoli_p95":50000,"ecoli_p99":200000,
        "aoc": 300, "nh3": 25, "no3": 8,
        "cond": 900, "pfas": 50,
    },
    "bnr": {
        "label": "BNR (Biological Nutrient Removal)",
        "turb_med": 1.8, "turb_p95": 5.0,  "turb_p99": 10.0,
        "tss_med":  4.0, "tss_p95":  10.0, "tss_p99":  18.0,
        "doc_med":  9.0, "doc_p95":  14.0, "doc_p99":  20.0,
        "uv254_med":0.13,"uv254_p95":0.22, "uv254_p99":0.30,
        "ecoli_med":2000,"ecoli_p95":20000,"ecoli_p99":100000,
        "aoc": 200, "nh3": 5, "no3": 12,
        "cond": 850, "pfas": 40,
    },
    "mbr": {
        "label": "MBR Effluent",
        "turb_med": 0.2, "turb_p95": 0.5,  "turb_p99": 1.0,
        "tss_med":  1.0, "tss_p95":  2.0,  "tss_p99":  4.0,
        "doc_med":  7.0, "doc_p95":  11.0, "doc_p99":  16.0,
        "uv254_med":0.10,"uv254_p95":0.18, "uv254_p99":0.25,
        "ecoli_med":10,  "ecoli_p95":100,  "ecoli_p99":500,
        "aoc": 150, "nh3": 2, "no3": 10,
        "cond": 800, "pfas": 35,
    },
    "tertiary": {
        "label": "Tertiary Treated (Sand / Cloth Filter)",
        "turb_med": 0.5, "turb_p95": 1.5,  "turb_p99": 3.0,
        "tss_med":  2.0, "tss_p95":  5.0,  "tss_p99":  8.0,
        "doc_med":  8.0, "doc_p95":  12.0, "doc_p99":  18.0,
        "uv254_med":0.11,"uv254_p95":0.20, "uv254_p99":0.28,
        "ecoli_med":500, "ecoli_p95":5000, "ecoli_p99":20000,
        "aoc": 180, "nh3": 8, "no3": 9,
        "cond": 870, "pfas": 45,
    },
    "custom": {
        "label": "Custom / Manual Entry",
        "turb_med": 1.5, "turb_p95": 4.0,  "turb_p99": 8.0,
        "tss_med":  3.0, "tss_p95":  8.0,  "tss_p99":  15.0,
        "doc_med":  8.0, "doc_p95":  14.0, "doc_p99":  20.0,
        "uv254_med":0.12,"uv254_p95":0.22, "uv254_p99":0.32,
        "ecoli_med":1000,"ecoli_p95":10000,"ecoli_p99":50000,
        "aoc": 200, "nh3": 25, "no3": 8,
        "cond": 900, "pfas": 50,
    },
}

# ---------------------------------------------------------------------------
# Failure mode scenarios
# ---------------------------------------------------------------------------

FAILURE_SCENARIOS = [
    {
        "scenario": "Single barrier failure — MF/UF membrane (integrity breach)",
        "key": "uf_failure",
    },
    {
        "scenario": "Ozone system failure / dose drop below CT target",
        "key": "ozone_failure",
    },
    {
        "scenario": "Poor WaterPoint effluent event — TSS / turbidity spike",
        "key": "influent_spike",
    },
    {
        "scenario": "UV lamp degradation — dose below validated minimum",
        "key": "uv_failure",
    },
]

FAILURE_RESPONSES: Dict[str, Dict[str, dict]] = {
    "uf_failure": {
        "C":   {"lrv": "Not in train — no impact", "chem": "No impact", "action": "Continue"},
        "A":   {"lrv": "Protozoa barrier lost — LRV shortfall", "chem": "Turbidity load to ozone increases", "action": "Divert — restore membrane integrity"},
        "A+":  {"lrv": "Protozoa LRV deficit", "chem": "Ozone demand increases with TSS", "action": "Divert — restore UF before resuming"},
        "PRW": {"lrv": "RO fouling risk elevated", "chem": "Particle load to RO — SDI rises", "action": "Divert — restore UF, check RO performance"},
    },
    "ozone_failure": {
        "C":   {"lrv": "Not in train — no impact", "chem": "No impact", "action": "Continue"},
        "A":   {"lrv": "Virus LRV reduced", "chem": "PPCPs unoxidised — breakthrough risk", "action": "Increase Cl₂ CT; verify UV dose covers virus target"},
        "A+":  {"lrv": "LRV deficit possible — ozone contributes to virus/bacteria", "chem": "CEC removal reduced", "action": "Divert — restore ozone before resuming A+ classification"},
        "PRW": {"lrv": "UV-AOP covers primary oxidation", "chem": "RO handles organics — limited impact", "action": "Continue — flag event, restore ozone, increase monitoring"},
    },
    "influent_spike": {
        "C":   {"lrv": "Cl₂ demand elevated", "chem": "Colloidal load increases", "action": "Increase coagulant dose; verify Cl₂ CT maintained"},
        "A":   {"lrv": "UF TMP rising — integrity risk window", "chem": "UV254 increases — ozone demand rises", "action": "Reduce flow; monitor TMP; increase ozone dose"},
        "A+":  {"lrv": "UF/ozone burden increased", "chem": "DOC spike drives ozone demand — may underdose", "action": "Increase O₃ dose; reduce flow; monitor UV254"},
        "PRW": {"lrv": "RO fouling accelerated — SDI critical", "chem": "MF load elevated — clean more frequently", "action": "Divert — reduce flow; trigger MF cleaning; monitor RO"},
    },
    "uv_failure": {
        "C":   {"lrv": "UV not in train — no impact", "chem": "No impact", "action": "N/A"},
        "A":   {"lrv": "Virus and protozoa LRV reduced", "chem": "AOP credit lost if UV-AOP configured", "action": "Alarm — replace lamp; increase Cl₂ CT to compensate"},
        "A+":  {"lrv": "Protozoa margin reduced; redundancy consumed", "chem": "AOP lost — CEC breakthrough possible", "action": "Divert — replace lamp before resuming A+ production"},
        "PRW": {"lrv": "AOP lost — RO covers organics but pathogen margin reduced", "chem": "Nitrosamine destruction impaired", "action": "Divert — replace lamp urgently; increase Cl₂ CT"},
    },
}
