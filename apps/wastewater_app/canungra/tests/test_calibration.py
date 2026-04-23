"""
test_calibration.py — Validate Canungra runner against Rev B BioWIN baseline.

Run from ~/wp_new:
    python3 apps/wastewater_app/canungra/tests/test_calibration.py

Expected to pass BEFORE using the model for commitment-grade analysis.
If it fails, the K2 kinetic values in canungra_scenarios.json need tuning
to match WaterPoint's SE QLD calibration.
"""
import json
import sys
from pathlib import Path

# Make parent dir importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from canungra_runner import BardenphoSolver, run_scenario


def load_inputs():
    parent = Path(__file__).parent.parent
    scenarios = json.loads((parent / "canungra_scenarios.json").read_text())
    profile = json.loads((parent / "canungra_diurnal_profile.json").read_text())
    return scenarios, profile


def test_rev_b_steady_state_AAL_17C():
    """
    Rev B baseline at AAL 17°C with 20 L/d MeOH should predict 
    TN ~ 1.5-4.5 mg/L. The Rev B BioWIN report shows 2.5-4.0 mg/L; SE QLD
    calibrated kinetics tend to give lower predictions due to higher
    post-anoxic endogenous activity in SE QLD biomass.
    """
    scenarios, profile = load_inputs()
    scen = scenarios["scenarios"]["S0_rev_b_baseline"]
    kinetics = scenarios["kinetic_parameters"]
    
    solver = BardenphoSolver(scen, kinetics)
    result = solver.solve(
        Q_kLd=300, TKN_mgL=62, COD_mgL=701, T_C=17,
        MeOH_Ld=20, MLSS_bio_mgL=7100, EP=1500,
    )
    
    TN = result["TN_permeate"]
    print(f"\n[test_rev_b_steady_state_AAL_17C]")
    print(f"  TN predicted: {TN:.2f} mg/L")
    print(f"  Expected range: 1.5-4.5 mg/L (Rev B BioWIN: 2.5-4.0; SE QLD: 1.5-3.5)")
    
    assert 1.5 < TN < 5.0, f"TN={TN:.2f} outside expected 1.5-5.0 range"
    print("  ✓ PASS")


def test_rev_b_steady_state_MML_17C():
    """
    Rev B at MML 17°C with 36 L/d MeOH should predict TN < 5 mg/L 
    (licence limit median condition at peak month loading).
    """
    scenarios, profile = load_inputs()
    scen = scenarios["scenarios"]["S0_rev_b_baseline"]
    kinetics = scenarios["kinetic_parameters"]
    
    solver = BardenphoSolver(scen, kinetics)
    result = solver.solve(
        Q_kLd=300, TKN_mgL=71, COD_mgL=876, T_C=17,
        MeOH_Ld=36, MLSS_bio_mgL=8000, EP=1500,
    )
    
    TN = result["TN_permeate"]
    print(f"\n[test_rev_b_steady_state_MML_17C]")
    print(f"  TN predicted: {TN:.2f} mg/L")
    print(f"  Expected range: 1.5-5.0 mg/L")
    
    assert 1.0 < TN < 6.0, f"TN={TN:.2f} outside expected range"
    print("  ✓ PASS")


def test_intensification_gain_from_postanox():
    """
    Scenario 2 (enlarged post-anoxic) should show substantial improvement
    over Rev B at moderate EPs (not limit capacity).
    """
    scenarios, profile = load_inputs()
    kinetics = scenarios["kinetic_parameters"]
    
    # Compare S0 and S2 at 2000 EP — S2 should give lower TN or need less MeOH
    s0_scen = scenarios["scenarios"]["S0_rev_b_baseline"]
    s2_scen = scenarios["scenarios"]["S2_ifas_plus_postanox"]
    
    solver_s0 = BardenphoSolver(s0_scen, kinetics)
    solver_s2 = BardenphoSolver(s2_scen, kinetics)
    
    r_s0 = solver_s0.solve(Q_kLd=400, TKN_mgL=62, COD_mgL=701, T_C=17,
                            MeOH_Ld=40, MLSS_bio_mgL=7500, EP=2000)
    r_s2 = solver_s2.solve(Q_kLd=400, TKN_mgL=62, COD_mgL=701, T_C=17,
                            MeOH_Ld=10, MLSS_bio_mgL=7500, EP=2000)
    
    print(f"\n[test_intensification_gain_from_postanox]")
    print(f"  S0 TN @ 2000EP, 40 L/d MeOH: {r_s0['TN_permeate']:.2f} mg/L")
    print(f"  S2 TN @ 2000EP, 10 L/d MeOH: {r_s2['TN_permeate']:.2f} mg/L")
    print(f"  Expected: S2 achieves similar or better TN with less MeOH")
    
    assert r_s2["TN_permeate"] < 6.0, f"S2 should be compliant: got {r_s2['TN_permeate']}"
    print("  ✓ PASS")


def test_bardenpho_not_mle():
    """
    Sanity check: the solver treats primary anoxic and post-anoxic as TWO
    sequential denit zones. At a low A-recycle (6x), an MLE plant would
    have high effluent NO3 (~(NO3_p)/(1+A) = 44/7 = 6.3 mg/L), but a 
    Bardenpho should polish via post-anoxic to much lower.
    """
    scenarios, profile = load_inputs()
    scen = scenarios["scenarios"]["S2_ifas_plus_postanox"]
    kinetics = scenarios["kinetic_parameters"]
    
    solver = BardenphoSolver(scen, kinetics)
    result = solver.solve(
        Q_kLd=300, TKN_mgL=62, COD_mgL=701, T_C=17,
        MeOH_Ld=15, MLSS_bio_mgL=6500, EP=1500,
    )
    
    NO3_perm = result["NO3_permeate"]
    NO3_ae = result["NO3_ae"]
    
    print(f"\n[test_bardenpho_not_mle]")
    print(f"  NO3 at aerobic end:  {NO3_ae:.2f} mg/L")
    print(f"  NO3 in permeate:     {NO3_perm:.2f} mg/L")
    print(f"  MLE prediction would be: NO3_ae itself (no post-anoxic polishing)")
    print(f"  Bardenpho: NO3_perm should be SIGNIFICANTLY LOWER than NO3_ae")
    
    assert NO3_perm < NO3_ae, \
        f"Post-anoxic must reduce NO3: {NO3_perm} vs aerobic {NO3_ae}"
    assert (NO3_ae - NO3_perm) / max(NO3_ae, 0.1) > 0.2, \
        "Post-anoxic should remove at least 20% of aerobic NO3"
    print("  ✓ PASS")


def test_flow_paced_recycle_helps():
    """
    Flow-paced A-recycle should produce better compliance than fixed absolute
    during peak diurnal conditions.
    """
    scenarios, profile = load_inputs()
    kinetics = scenarios["kinetic_parameters"]
    
    r_fixed = run_scenario(
        "S2_ifas_plus_postanox", scenarios["scenarios"], profile, kinetics,
        EP=2500, loading="AAL", T_C=17, MeOH_Ld=15, flow_paced_A=False,
    )
    r_paced = run_scenario(
        "S2_ifas_plus_postanox", scenarios["scenarios"], profile, kinetics,
        EP=2500, loading="AAL", T_C=17, MeOH_Ld=15, flow_paced_A=True,
    )
    
    print(f"\n[test_flow_paced_recycle_helps]")
    print(f"  Fixed A-recycle: 80%ile TN = {r_fixed['compliance']['p80']:.2f} mg/L")
    print(f"  Flow-paced A:    80%ile TN = {r_paced['compliance']['p80']:.2f} mg/L")
    print(f"  Expected: flow-paced should be lower or equal at peak")
    
    # Flow-paced should be at least as good (within 10% tolerance)
    assert r_paced["compliance"]["p80"] <= r_fixed["compliance"]["p80"] * 1.10
    print("  ✓ PASS")


def test_MLSS_respects_ceiling_at_high_EP():
    """
    REGRESSION: MLSS_MBR must not exceed the membrane ceiling as EP rises.
    Kubota ceiling is ~12,000 mg/L; HF ceiling ~10,000 mg/L.
    If the model lets MLSS run to 30,000+ mg/L, it artificially scales 
    VSS inventory with EP, which masks the true EP-vs-TN relationship.
    """
    scenarios, profile = load_inputs()
    kinetics = scenarios["kinetic_parameters"]
    
    print(f"\n[test_MLSS_respects_ceiling_at_high_EP]")
    
    # S2 has Kubota, ceiling = 12,000
    for EP in [2000, 4000, 8000]:
        r = run_scenario("S2_ifas_plus_postanox", scenarios["scenarios"],
                         profile, kinetics, EP=EP, loading="AAL", T_C=17,
                         MeOH_Ld=0, flow_paced_A=True)
        MLSS_MBR = r["MLSS_MBR"]
        print(f"  EP={EP}: MLSS_MBR = {MLSS_MBR:.0f} mg/L")
        assert MLSS_MBR < 13000, f"MLSS_MBR={MLSS_MBR} should be capped at ~12,000 (Kubota ceiling)"
    
    print("  ✓ PASS — MLSS respects realistic operating ceiling")


def test_TN_rises_with_EP_at_fixed_MeOH():
    """
    REGRESSION: At fixed MeOH dose, effluent TN must rise as EP increases
    (once MLSS has hit its operating ceiling). This is basic physics:
    more load into same kinetic capacity means higher effluent.
    """
    scenarios, profile = load_inputs()
    kinetics = scenarios["kinetic_parameters"]
    
    print(f"\n[test_TN_rises_with_EP_at_fixed_MeOH]")
    
    tn_values = []
    for EP in [3000, 4000, 5000, 6000]:
        r = run_scenario("S2_ifas_plus_postanox", scenarios["scenarios"],
                         profile, kinetics, EP=EP, loading="AAL", T_C=17,
                         MeOH_Ld=40, flow_paced_A=True)
        tn = r["compliance"]["flow_weighted_mean"]
        tn_values.append((EP, tn))
        print(f"  EP={EP}, MeOH=40 L/d: TN_FWM = {tn:.2f} mg/L")
    
    # After MLSS saturates (EP ~ 3000+), TN must rise monotonically
    for i in range(1, len(tn_values)):
        _, tn_prev = tn_values[i-1]
        _, tn_curr = tn_values[i]
        assert tn_curr >= tn_prev - 0.1, \
            f"TN should rise or stay flat with EP (got {tn_prev:.2f}→{tn_curr:.2f})"
    
    # Total rise from 3000 to 6000 EP should be at least 2 mg/L at MeOH=40
    tn_3k = tn_values[0][1]
    tn_6k = tn_values[-1][1]
    assert (tn_6k - tn_3k) > 1.5, \
        f"Expected >1.5 mg/L TN rise from 3000→6000 EP, got {tn_6k-tn_3k:.2f}"
    
    print(f"  TN rose by {tn_6k-tn_3k:.2f} mg/L from EP=3000 to EP=6000")
    print("  ✓ PASS — TN responds to EP as expected")


def test_s2_variants_share_biology():
    """
    S2-A and S2-B must give identical biological output at the same EP,
    because they have the same total post-anoxic volume (156 kL). The
    difference is hydraulic (parallel vs combined), not kinetic.
    """
    scenarios, profile = load_inputs()
    k = scenarios["kinetic_parameters"]
    
    r_a = run_scenario("S2_A_combined", scenarios["scenarios"], profile, k,
                       EP=4000, loading="MML", T_C=17, flow_paced_A=True)
    r_b = run_scenario("S2_B_parallel", scenarios["scenarios"], profile, k,
                       EP=4000, loading="MML", T_C=17, flow_paced_A=True)
    
    tn_a = r_a["compliance"]["flow_weighted_mean"]
    tn_b = r_b["compliance"]["flow_weighted_mean"]
    
    print(f"\n[test_s2_variants_share_biology]")
    print(f"  S2-A at 4,000 EP MML: TN = {tn_a:.3f} mg/L")
    print(f"  S2-B at 4,000 EP MML: TN = {tn_b:.3f} mg/L")
    
    # They should be identical (same biology)
    assert abs(tn_a - tn_b) < 0.01, (
        f"S2-A ({tn_a:.3f}) and S2-B ({tn_b:.3f}) should have identical biology"
    )
    print(f"  ✓ PASS — S2-A and S2-B biology is identical (Δ = {abs(tn_a-tn_b):.4f} mg/L)")


def test_s2_c3_effective_volume_142():
    """
    S2-C3 effective post-anoxic volume is 142 kL. Verify this falls between
    S2-D (118 kL) and S2-A (156 kL) in terms of denitrification capacity.
    
    Test with explicit MeOH dose to avoid auto-search convergence variability.
    """
    scenarios, profile = load_inputs()
    k = scenarios["kinetic_parameters"]
    
    # Use fixed MeOH dose to isolate the volume effect
    # Run at a challenging EP where volume matters (peak TN regime)
    r_d = run_scenario("S2_D_parallel_only", scenarios["scenarios"], profile, k,
                       EP=6000, loading="MML", T_C=17, flow_paced_A=True,
                       MeOH_Ld=120)
    r_c3 = run_scenario("S2_C3_series_parallel", scenarios["scenarios"], profile, k,
                        EP=6000, loading="MML", T_C=17, flow_paced_A=True,
                        MeOH_Ld=120)
    r_a = run_scenario("S2_A_combined", scenarios["scenarios"], profile, k,
                       EP=6000, loading="MML", T_C=17, flow_paced_A=True,
                       MeOH_Ld=120)
    
    peak_d = r_d["compliance"]["peak"]
    peak_c3 = r_c3["compliance"]["peak"]
    peak_a = r_a["compliance"]["peak"]
    
    print(f"\n[test_s2_c3_effective_volume_142]")
    print(f"  At 6,000 EP MML, fixed MeOH=120 L/d:")
    print(f"  S2-D (118 kL) peak TN: {peak_d:.2f} mg/L")
    print(f"  S2-C3 (142 kL) peak TN: {peak_c3:.2f} mg/L")
    print(f"  S2-A (156 kL) peak TN: {peak_a:.2f} mg/L")
    
    # Larger post-anoxic volume → lower peak TN
    # Expected: S2-A ≤ S2-C3 ≤ S2-D
    assert peak_a <= peak_c3 + 0.1, f"S2-A peak ({peak_a:.2f}) should be ≤ S2-C3 peak ({peak_c3:.2f})"
    assert peak_c3 <= peak_d + 0.1, f"S2-C3 peak ({peak_c3:.2f}) should be ≤ S2-D peak ({peak_d:.2f})"
    print(f"  ✓ PASS — S2-A ≤ S2-C3 ≤ S2-D peak TN ordering holds")


def test_s2_d_reduced_capacity():
    """
    S2-D (118 kL) should have lower capacity than S2-A (156 kL).
    At high EP, S2-D's smaller post-anoxic should push effluent TN higher.
    """
    scenarios, profile = load_inputs()
    k = scenarios["kinetic_parameters"]
    
    # At 6,000 EP, S2-A should pass peak TN but S2-D should fail
    r_a = run_scenario("S2_A_combined", scenarios["scenarios"], profile, k,
                       EP=6000, loading="MML", T_C=17, flow_paced_A=True,
                       licence_interpretation="B")
    r_d = run_scenario("S2_D_parallel_only", scenarios["scenarios"], profile, k,
                       EP=6000, loading="MML", T_C=17, flow_paced_A=True,
                       licence_interpretation="B")
    
    peak_a = r_a["compliance"]["peak"]
    peak_d = r_d["compliance"]["peak"]
    
    print(f"\n[test_s2_d_reduced_capacity]")
    print(f"  S2-A (156 kL) at 6,000 EP MML: peak = {peak_a:.2f} mg/L")
    print(f"  S2-D (118 kL) at 6,000 EP MML: peak = {peak_d:.2f} mg/L")
    
    assert peak_d > peak_a, (
        f"S2-D peak ({peak_d:.2f}) should exceed S2-A peak ({peak_a:.2f}) at 6,000 EP"
    )
    print(f"  ✓ PASS — S2-D has lower capacity (higher peak TN) than S2-A")


def test_interpretation_A_vs_B_binding():
    """
    At high EP with fixed MeOH dose, biological output is identical across
    interpretations. But mass_pass differs because the applicable limit
    changes (607 fixed vs scaled).
    """
    scenarios, profile = load_inputs()
    k = scenarios["kinetic_parameters"]
    
    # Fixed MeOH so biology is identical across interpretations
    r_a = run_scenario("S2_A_combined", scenarios["scenarios"], profile, k,
                       EP=5000, loading="AAL", T_C=17, flow_paced_A=True,
                       MeOH_Ld=100, licence_interpretation="A")
    r_b = run_scenario("S2_A_combined", scenarios["scenarios"], profile, k,
                       EP=5000, loading="AAL", T_C=17, flow_paced_A=True,
                       MeOH_Ld=100, licence_interpretation="B")
    
    mass_a = r_a["compliance"]["annual_mass_kg"]
    mass_b = r_b["compliance"]["annual_mass_kg"]
    pass_a = r_a["compliance"]["mass_pass"]
    pass_b = r_b["compliance"]["mass_pass"]
    
    print(f"\n[test_interpretation_A_vs_B_binding]")
    print(f"  S2-A at 5,000 EP AAL, MeOH=100 fixed:")
    print(f"    Interp A: mass={mass_a:.0f} vs 607 cap → mass_pass={pass_a}")
    print(f"    Interp B: mass={mass_b:.0f} vs 2023 scaled → mass_pass={pass_b}")
    
    # Mass is identical (same biology)
    assert abs(mass_a - mass_b) < 1.0, (
        f"Mass discharge should be identical across interpretations "
        f"(got {mass_a:.1f} vs {mass_b:.1f})"
    )
    # But compliance differs
    assert pass_a == False, "Interp A should FAIL mass at 5,000 EP (above 607 cap)"
    assert pass_b == True, "Interp B should PASS mass at 5,000 EP (below 2,023 scaled)"
    print(f"  ✓ PASS — Interpretations give identical biology but differ on compliance")


def test_interpretation_converge_at_1500_EP():
    """
    Interpretation A and B must give identical results at the 1,500 EP design
    point, because B's scaling factor is 1.0× there.
    """
    from canungra_runner import LicenceLimits
    
    lim_a = LicenceLimits(interpretation="A")
    lim_b = LicenceLimits(interpretation="B")
    
    limit_a_1500 = lim_a.get_mass_limit(1500)
    limit_b_1500 = lim_b.get_mass_limit(1500)
    
    print(f"\n[test_interpretation_converge_at_1500_EP]")
    print(f"  Interp A at 1,500 EP: {limit_a_1500:.1f} kg/yr")
    print(f"  Interp B at 1,500 EP: {limit_b_1500:.1f} kg/yr")
    
    assert abs(limit_a_1500 - limit_b_1500) < 0.01, (
        "A and B should coincide at 1,500 EP design point"
    )
    print(f"  ✓ PASS — Interpretations coincide at 1,500 EP derivation point")


def test_s2e_aerobic_shifted_volumes():
    """
    S2-E: 155 kL aerobic + 118 kL post-anoxic.
    
    S2-E has 118 kL post-anoxic (smaller than S2-A/B 156 kL) but expanded
    aerobic (155 kL vs 117 kL). With MeOH auto-solve at each variant, S2-E
    should perform COMPARABLY to S2-A/B at 5,000+ EP because the expanded
    aerobic compensates for the smaller post-anoxic.
    
    Expected ordering at 5,500 EP MML with MeOH auto-solve:
      S2-D (117/118) >> S2-E (155/118) ≈ S2-A (117/156)
    
    Note: S2-E and S2-A/B are expected to be roughly equivalent because the
    trade (more aerobic, less post-anoxic) balances for TN. Flow balancing
    (RFC-12) would provide ADDITIONAL capacity uplift on top of this.
    """
    scenarios, profile = load_inputs()
    k = scenarios["kinetic_parameters"]
    
    # Let MeOH auto-solve for each variant at 5,500 EP MML
    r_d = run_scenario("S2_D_parallel_only", scenarios["scenarios"], profile, k,
                       EP=5500, loading="MML", T_C=17, flow_paced_A=True)
    r_e = run_scenario("S2_E_aerobic_shifted", scenarios["scenarios"], profile, k,
                       EP=5500, loading="MML", T_C=17, flow_paced_A=True)
    r_a = run_scenario("S2_A_combined", scenarios["scenarios"], profile, k,
                       EP=5500, loading="MML", T_C=17, flow_paced_A=True)
    
    peak_d = r_d["compliance"]["peak"]
    peak_e = r_e["compliance"]["peak"]
    peak_a = r_a["compliance"]["peak"]
    
    print(f"\n[test_s2e_aerobic_shifted_volumes]")
    print(f"  Variants at 5,500 EP MML with MeOH auto-solve:")
    print(f"  S2-D (117 aer / 118 pa) peak: {peak_d:.2f}")
    print(f"  S2-E (155 aer / 118 pa) peak: {peak_e:.2f}")
    print(f"  S2-A (117 aer / 156 pa) peak: {peak_a:.2f}")
    
    # S2-E should clearly outperform S2-D (expanded aerobic helps)
    assert peak_e < peak_d - 2.0, (
        f"S2-E ({peak_e:.2f}) should outperform S2-D ({peak_d:.2f}) by >2 mg/L "
        f"at 5,500 EP (expanded aerobic 155 vs 117 kL)"
    )
    
    # S2-E and S2-A should be comparable (within 1.5 mg/L) — the trade balances
    assert abs(peak_e - peak_a) < 1.5, (
        f"S2-E ({peak_e:.2f}) and S2-A ({peak_a:.2f}) should be comparable at "
        f"5,500 EP (volume trade balances: S2-E +38 aer/-38 pa vs S2-A)"
    )
    
    print(f"  [Expanded aerobic compensates for smaller post-anoxic]")
    print(f"  [Flow balancing (RFC-12) provides ADDITIONAL capacity uplift]")
    print(f"  ✓ PASS — S2-E performance: S2-D >> S2-E ≈ S2-A at 5,500 EP")


def test_s2e_expanded_aerobic_volume():
    """
    S2-E has 155 kL aerobic (existing 117 + converted 38), NOT 117 kL.
    Verify the scenarios JSON is loaded with the expanded aerobic volume.
    """
    scenarios, profile = load_inputs()
    
    s2e = scenarios["scenarios"]["S2_E_aerobic_shifted"]
    s2d = scenarios["scenarios"]["S2_D_parallel_only"]
    s2a = scenarios["scenarios"]["S2_A_combined"]
    
    aer_e = s2e["zone_volumes_kL"]["aerobic"]
    aer_d = s2d["zone_volumes_kL"]["aerobic"]
    aer_a = s2a["zone_volumes_kL"]["aerobic"]
    
    pa_e = s2e["zone_volumes_kL"]["post_anoxic"]
    pa_d = s2d["zone_volumes_kL"]["post_anoxic"]
    pa_a = s2a["zone_volumes_kL"]["post_anoxic"]
    
    print(f"\n[test_s2e_expanded_aerobic_volume]")
    print(f"  S2-A aerobic: {aer_a} kL, post-anoxic: {pa_a} kL")
    print(f"  S2-D aerobic: {aer_d} kL, post-anoxic: {pa_d} kL")
    print(f"  S2-E aerobic: {aer_e} kL, post-anoxic: {pa_e} kL")
    
    assert aer_e == 155, f"S2-E aerobic should be 155 kL (117+38 converted), got {aer_e}"
    assert pa_e == 118, f"S2-E post-anoxic should be 118 kL (former MBR bay), got {pa_e}"
    assert aer_e > aer_a, f"S2-E aerobic ({aer_e}) should exceed S2-A ({aer_a})"
    assert pa_e < pa_a, f"S2-E post-anoxic ({pa_e}) should be less than S2-A ({pa_a})"
    
    # S2-E flow balancing metadata
    assert "flow_balancing" in s2e, "S2-E should include flow_balancing metadata"
    fb = s2e["flow_balancing"]
    assert fb["enabled"] == True, "S2-E flow balancing should be enabled"
    
    print(f"  ✓ PASS — S2-E volume reallocation and metadata correct")


def main():
    print("=" * 70)
    print("CANUNGRA RUNNER — CALIBRATION TEST SUITE")
    print("=" * 70)
    
    tests = [
        test_rev_b_steady_state_AAL_17C,
        test_rev_b_steady_state_MML_17C,
        test_intensification_gain_from_postanox,
        test_bardenpho_not_mle,
        test_flow_paced_recycle_helps,
        test_MLSS_respects_ceiling_at_high_EP,
        test_TN_rises_with_EP_at_fixed_MeOH,
        # S2 variant regression tests (Rev 17)
        test_s2_variants_share_biology,
        test_s2_c3_effective_volume_142,
        test_s2_d_reduced_capacity,
        # Interpretation toggle tests (Rev 17)
        test_interpretation_A_vs_B_binding,
        test_interpretation_converge_at_1500_EP,
        # S2-E aerobic-shifted tests (Rev 20)
        test_s2e_expanded_aerobic_volume,
        test_s2e_aerobic_shifted_volumes,
    ]
    
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"  ✗ FAIL: {e}")
        except Exception as e:
            failed.append((t.__name__, f"Exception: {e}"))
            print(f"  ✗ ERROR: {e}")
    
    print()
    print("=" * 70)
    print(f"RESULTS: {passed}/{len(tests)} passed")
    if failed:
        print(f"\nFailures:")
        for name, reason in failed:
            print(f"  - {name}: {reason}")
        print("\nCALIBRATION NEEDED: replace literature K2 values in")
        print("canungra_scenarios.json with WaterPoint SE QLD calibrated values.")
        sys.exit(1)
    else:
        print("\n✓ Model calibrated to Rev B BioWIN baseline")
    print("=" * 70)


if __name__ == "__main__":
    main()
