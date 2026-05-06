"""
tests/test_mad.py

Regression test suite for engine/mad.py — 50 tests.
Mirrors regression-suite.js / regression-baseline.json from RecupModelV3.

Run: python tests/test_mad.py
"""

import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mad import (
    MADInputs, run_mad, run_mad_dict,
    _f_diff_base, _f_diff_effective, _f_mix, _NH3_fraction,
    MIXING_SYSTEM_PARAMS, _geometric_feasibility,
)

failures = []
passed  = 0

def chk(name, condition, detail=""):
    global passed
    if condition:
        print(f"  ok  {name}")
        passed += 1
    else:
        msg = f"  FAIL {name}" + (f": {detail}" if detail else "")
        print(msg)
        failures.append(name)

def approx(a, b, tol):
    return abs(a - b) <= tol

# ── Baseline inputs ────────────────────────────────────────────────────────
BASELINE = dict(
    psV=65000.0, wasV=25000.0,
    psDS=137.5, wasDS=38.4,
    psTS=4.0, wasTS=4.0,
    psVS=75.0, wasVS=70.0,
    psN=3.0, wasN=8.5,
    mode="separate", sepBenefit=1.10,
    pretreatment="none", reactorType="conventional",
    recup=True, psCap=85.0, wasCap=85.0,
    psBeta=1.5, wasBeta=2.5, finalDewateringCap=92.0,
    mixingSystemType="mechanical", mixingPower=15.0, mixingScale=1.00,
    digester_pH=7.25, pHControl="off",
    nh3Mode="acclimated", KI_NH3=0.7, n_NH3=1.0, tradeWaste="normal",
    psK=0.25, wasK=0.15, psVSmax=70.0, wasVSmax=60.0,
    chpE=40.0, chpAvail=88.0,
)

def make(**overrides):
    return MADInputs(**{**BASELINE, **overrides})

def baseline():
    return run_mad(make())

# ============================================================
# UNIT TESTS — physics functions
# ============================================================
print("\nPHYSICS FUNCTIONS")

chk("f_diff_base at TS=4.0 == 1.0",
    _f_diff_base(4.0) == 1.0)
chk("f_diff_base at TS=3.5 == 1.0",
    _f_diff_base(3.5) == 1.0)
chk("f_diff_base at TS=2.0 == 1.0",
    _f_diff_base(2.0) == 1.0)
chk("f_diff_base at TS=6.0 ≈ 0.741",
    approx(_f_diff_base(6.0), 0.7408, 0.001))
chk("f_diff_eff = 1.0 when f_diff_base = 1.0 (any f_mix)",
    _f_diff_effective(1.0, 0.5) == 1.0
    and _f_diff_effective(1.0, 0.95) == 1.0)
chk("f_diff_eff couples when diffusion limited: better mixing → less derate",
    _f_diff_effective(0.74, 0.80) > _f_diff_effective(0.74, 0.40))
chk("NH3 fraction at pH 7.25 ≈ 1.96%",
    approx(_NH3_fraction(7.25), 0.01963, 0.001))
chk("NH3 fraction increases with pH",
    _NH3_fraction(7.50) > _NH3_fraction(7.25))
chk("NH3 fraction pH 7.50 > 1.5× pH 7.25",
    _NH3_fraction(7.50) > 1.5 * _NH3_fraction(7.25))
chk("f_mix mechanical TS=4, P=15, scale=1 ≈ 0.82",
    approx(_f_mix(4.0, 15.0, "mechanical", 1.0, False), 0.82, 0.01))
chk("f_mix floors at zero power (mechanical)",
    approx(_f_mix(4.0, 0.0, "mechanical", 1.0, False), 0.40, 0.01))
chk("f_mix floors at zero power (gas)",
    approx(_f_mix(4.0, 0.0, "gas", 1.0, False), 0.30, 0.01))
chk("f_mix ceiling ≤ 0.95 at very high power",
    _f_mix(4.0, 100.0, "mechanical", 1.0, False) <= 0.95)
chk("f_mix ceiling ≥ 0.90 at very high power",
    _f_mix(4.0, 100.0, "mechanical", 1.0, False) >= 0.90)
geo_small = _geometric_feasibility(13.6, 5.56, "acclimated")
chk("geometric: small WAS (5.56d HRT) → INFEASIBLE",
    geo_small.wasFeasibility == "INFEASIBLE")
chk("geometric: small WAS overall → INFEASIBLE",
    geo_small.overall == "INFEASIBLE")
geo_large = _geometric_feasibility(18.9, 26.0, "acclimated")
chk("geometric: metro 450 WAS (26d HRT) → FEASIBLE",
    geo_large.wasFeasibility == "FEASIBLE")
chk("geometric: metro 450 overall → FEASIBLE",
    geo_large.overall == "FEASIBLE")

# ============================================================
# REGRESSION SCENARIOS
# ============================================================
print("\nREGRESSION SCENARIOS")

# S01 — default Mod S1
r = baseline()
chk("S01: status SAFE", r.status == "SAFE", r.status)
chk("S01: biogas ≈ 63044", approx(r.biogas_m3_per_d, 63044, 250), f"{r.biogas_m3_per_d:.0f}")
chk("S01: was.f_eff ≈ 0.817", approx(r.was.f_eff, 0.817, 0.01), f"{r.was.f_eff:.3f}")
chk("S01: was.inhibition ≈ 10%", approx(r.was.inhibition_pct, 10.0, 1.5), f"{r.was.inhibition_pct:.1f}")
chk("S01: ps.f_diff = 1.0 (TS=4%)", approx(r.ps.f_diff_eff, 1.0, 1e-9))
chk("S01: was.f_diff = 1.0 (TS=4%)", approx(r.was.f_diff_eff, 1.0, 1e-9))

# S02 — efficient mixing
r = run_mad(make(mixingScale=0.75))
chk("S02: efficient mixing status SAFE", r.status == "SAFE")
chk("S02: was.f_eff ≈ 0.856", approx(r.was.f_eff, 0.856, 0.01), f"{r.was.f_eff:.3f}")

# S03 — pessimistic mixing
r = run_mad(make(mixingScale=1.25))
chk("S03: pessimistic mixing was.f_eff ≈ 0.780", approx(r.was.f_eff, 0.780, 0.01))

# S04 — TS 4% no diffusion penalty (critical Finding 3)
r = run_mad(make(psTS=4.0, wasTS=4.0))
chk("S04: ps.f_diff_base == 1.0", r.ps.f_diff_base == 1.0)
chk("S04: was.f_diff_base == 1.0", r.was.f_diff_base == 1.0)
chk("S04: ps.f_diff_eff == 1.0", approx(r.ps.f_diff_eff, 1.0, 1e-9))
chk("S04: was.f_diff_eff == 1.0", approx(r.was.f_diff_eff, 1.0, 1e-9))

# S05 — TS 6% diffusion kicks in
r = run_mad(make(psTS=6.0, wasTS=6.0))
chk("S05: TS=6% → FAILURE", r.status == "FAILURE", r.status)
chk("S05: was.f_diff_base ≈ 0.741", approx(r.was.f_diff_base, 0.7408, 0.005))
chk("S05: f_diff_eff < f_diff_base (coupling)", r.was.f_diff_eff < r.was.f_diff_base)
chk("S05: was.f_eff ≈ 0.406", approx(r.was.f_eff, 0.406, 0.01), f"{r.was.f_eff:.3f}")

# S06 — TS 8%
r = run_mad(make(psTS=8.0, wasTS=8.0))
chk("S06: TS=8% → FAILURE", r.status == "FAILURE")
chk("S06: was.f_eff ≈ 0.172", approx(r.was.f_eff, 0.172, 0.01), f"{r.was.f_eff:.3f}")

# S07 — low-risk envelope
r = run_mad(make(digester_pH=7.10, wasN=6.0, KI_NH3=1.0))
chk("S07: low risk was.inhib ≈ 4%", approx(r.was.inhibition_pct, 4.0, 1.5))
chk("S07: low risk SAFE", r.status == "SAFE")

# S08 — high-risk envelope
r = run_mad(make(digester_pH=7.50, wasN=12.0, KI_NH3=0.5))
chk("S08: high risk was.inhib ≈ 27%", approx(r.was.inhibition_pct, 27.0, 2.5), f"{r.was.inhibition_pct:.1f}")
chk("S08: high risk FAILURE", r.status == "FAILURE")

# S09 — pH +0.20
r = run_mad(make(digester_pH=7.45))
chk("S09: pH 7.45 was.inhib ≈ 14%", approx(r.was.inhibition_pct, 14.0, 2.0), f"{r.was.inhibition_pct:.1f}")

# S10 — WAS N +30%
r = run_mad(make(wasN=8.5 * 1.30))
chk("S10: wasN +30% was.inhib ≈ 12%", approx(r.was.inhibition_pct, 12.0, 2.0), f"{r.was.inhibition_pct:.1f}")
chk("S10: wasN +30% SAFE", r.status == "SAFE")

# S11 — capture drop 75%
r = run_mad(make(psCap=75.0, wasCap=75.0))
chk("S11: cap 75% SAFE", r.status == "SAFE")

# S12 — beta 2.0
r = run_mad(make(wasBeta=2.0))
chk("S12: beta 2.0 was.f_eff ≈ 0.817", approx(r.was.f_eff, 0.817, 0.01))
chk("S12: beta 2.0 SAFE", r.status == "SAFE")

# S13 — beta 2.5 (default)
r = run_mad(make(wasBeta=2.5))
chk("S13: beta 2.5 SAFE", r.status == "SAFE")

# S14 — combined severe
r = run_mad(make(psCap=70.0, wasCap=70.0, wasN=15.0, digester_pH=7.6, KI_NH3=0.5))
chk("S14: combined severe FAILURE", r.status == "FAILURE")
chk("S14: was.inhib ≈ 31%", approx(r.was.inhibition_pct, 31.0, 3.0), f"{r.was.inhibition_pct:.1f}")

# S15 — capture drift 70%
r = run_mad(make(psCap=70.0, wasCap=70.0))
chk("S15: cap 70% SAFE", r.status == "SAFE")

# S16 — gas mixing
r = run_mad(make(mixingSystemType="gas"))
chk("S16: gas mixing was.f_eff ≈ 0.721", approx(r.was.f_eff, 0.721, 0.01), f"{r.was.f_eff:.3f}")
chk("S16: gas mixing SAFE", r.status == "SAFE")

# S17 — draft tube
r = run_mad(make(mixingSystemType="draftTube"))
chk("S17: draftTube was.f_eff ≈ 0.905", approx(r.was.f_eff, 0.905, 0.01), f"{r.was.f_eff:.3f}")
chk("S17: draftTube SAFE", r.status == "SAFE")

# S18 — staged
r = run_mad(make(mixingSystemType="staged"))
chk("S18: staged was.f_eff ≈ 0.923", approx(r.was.f_eff, 0.923, 0.01), f"{r.was.f_eff:.3f}")

# S19 — gas at TS 6%
r = run_mad(make(mixingSystemType="gas", psTS=6.0, wasTS=6.0))
chk("S19: gas TS=6% was.f_eff ≈ 0.303", approx(r.was.f_eff, 0.303, 0.01), f"{r.was.f_eff:.3f}")
chk("S19: gas TS=6% FAILURE", r.status == "FAILURE")

# S20 — mechanical at TS 6%
r = run_mad(make(mixingSystemType="mechanical", psTS=6.0, wasTS=6.0))
chk("S20: mech TS=6% was.f_eff ≈ 0.406", approx(r.was.f_eff, 0.406, 0.01))
chk("S20: mech TS=6% FAILURE", r.status == "FAILURE")

# S21 — draft-tube at TS 6%
r = run_mad(make(mixingSystemType="draftTube", psTS=6.0, wasTS=6.0))
chk("S21: draftTube TS=6% was.f_eff ≈ 0.501", approx(r.was.f_eff, 0.501, 0.01), f"{r.was.f_eff:.3f}")
chk("S21: draftTube TS=6% FAILURE", r.status == "FAILURE")
chk("S21: failure is mixing-driven not chemistry", r.was.inhibition_pct < 20.0)

# ============================================================
# DIAGNOSTIC TESTS
# ============================================================
print("\nDIAGNOSTIC BEHAVIOUR")

# S22 — geometric infeasibility
r = run_mad(make(psV=13000, wasV=6500, psDS=38.25, wasDS=46.75,
                 psVS=78.0, wasVS=73.0, psN=3.2, wasN=11.0,
                 digester_pH=7.35, mixingPower=12.0))
chk("S22: geometric infeasibility banner fires", r.feasibility_warning is True)
chk("S22: feasibility.overall INFEASIBLE", r.feasibility.overall == "INFEASIBLE")
chk("S22: feasibility.wasFeasibility INFEASIBLE", r.feasibility.wasFeasibility == "INFEASIBLE")
chk("S22: diagnostic_flags geometric_infeasibility True", r.diagnostic_flags["geometric_infeasibility"])

# S23 — corrected geometry
r = run_mad(make(psV=6500, wasV=13000, psDS=38.25, wasDS=46.75,
                 psN=3.2, wasN=11.0, digester_pH=7.35, mixingPower=12.0))
chk("S23: corrected geometry WAS FEASIBLE", r.feasibility.wasFeasibility == "FEASIBLE")

# S24 — metro 450 always feasible
r = baseline()
chk("S24: metro 450 overall FEASIBLE", r.feasibility.overall == "FEASIBLE")
chk("S24: metro 450 feasibility_warning False", r.feasibility_warning is False)

# S25 — biogas blind warning
r = baseline()
if r.was.SRT_eff_d > 30.0:
    chk("S25: biogas_blind_warning fires at WAS SRT > 30d",
        r.diagnostic_flags["biogas_blind_warning"])

# S26 — pH control
r = run_mad(make(digester_pH=7.45, pHControl="on"))
chk("S26: pH_control_engaged flag fires", r.diagnostic_flags["pH_control_engaged"])
chk("S26: effective_pH clamped to 7.30", approx(r.effective_pH, 7.30, 0.001))

# S27 — THP flag
r = run_mad(make(pretreatment="thp"))
chk("S27: thp_active flag fires", r.diagnostic_flags["thp_active"])

# S28 — industrial trade waste
r = run_mad(make(tradeWaste="industrial"))
chk("S28: industrial_trade_waste flag fires", r.diagnostic_flags["industrial_trade_waste"])

# ============================================================
# PROPERTY INVARIANTS
# ============================================================
print("\nINVARIANTS")

for sys_type in ["gas", "mechanical", "draftTube", "staged"]:
    r = run_mad(make(mixingSystemType=sys_type))
    floor = MIXING_SYSTEM_PARAMS[sys_type]["floor"]
    chk(f"f_eff in [floor, 0.95] — {sys_type}",
        floor <= r.ps.f_eff <= 0.95 and floor <= r.was.f_eff <= 0.95)

r = baseline()
chk("VS destruction never exceeds psVSmax", r.ps.VS_destruction_pct <= 70.0)
chk("VS destruction never exceeds wasVSmax", r.was.VS_destruction_pct <= 60.0)
chk("inhibition in [0, 100]",
    0 <= r.ps.inhibition_pct <= 100 and 0 <= r.was.inhibition_pct <= 100)
chk("biogas positive", r.biogas_m3_per_d > 0)

# N mass balance closure (within 5%)
feed_N_kg = (BASELINE["psDS"] * BASELINE["psN"] / 100
             + BASELINE["wasDS"] * BASELINE["wasN"] / 100) * 1000.0
out_N_kg  = r.centrate_N_kg_per_d + r.cake_N_kg_per_d
chk("N mass balance closure < 5%",
    abs(out_N_kg - feed_N_kg) / feed_N_kg < 0.05,
    f"feed={feed_N_kg:.0f} out={out_N_kg:.0f}")

if r.ps.status == "SAFE" and r.was.status == "SAFE":
    chk("if both streams SAFE, overall SAFE", r.status == "SAFE")

low = run_mad(make(digester_pH=7.10))
high = run_mad(make(digester_pH=7.50))
chk("higher pH → higher NH3", high.was.NH3_g_per_L > low.was.NH3_g_per_L)
chk("higher pH → higher inhibition", high.was.inhibition_pct > low.was.inhibition_pct)

lo_cap = run_mad(make(psCap=70.0, wasCap=70.0))
hi_cap = run_mad(make(psCap=85.0, wasCap=85.0))
chk("higher capture → longer PS SRT", hi_cap.ps.SRT_eff_d > lo_cap.ps.SRT_eff_d)

no_thp = run_mad(make(pretreatment="none"))
thp    = run_mad(make(pretreatment="thp"))
chk("THP → higher NH4 (more N release)", thp.was.NH4_g_per_L > no_thp.was.NH4_g_per_L)

# Dict wrapper
result_dict = run_mad_dict(BASELINE)
chk("dict wrapper: status present", "status" in result_dict)
chk("dict wrapper: biogas_m3_per_d present", "biogas_m3_per_d" in result_dict)
chk("dict wrapper: ps and was present", "ps" in result_dict and "was" in result_dict)
chk("dict wrapper: status == SAFE", result_dict["status"] == "SAFE")

# ============================================================
# SUMMARY
# ============================================================
print()
total = passed + len(failures)
print(f"MAD test suite: {passed}/{total} passed")
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    raise SystemExit(1)
else:
    print("ALL MAD TESTS PASSED ✓")
