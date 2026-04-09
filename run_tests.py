#!/usr/bin/env python3
"""
run_tests.py — Full platform test suite runner (no pytest required).

Usage:
    python3 run_tests.py              # all tests
    python3 run_tests.py --fast       # smoke tests only (skips benchmarks)
    python3 run_tests.py --benchmark  # benchmark suite only

Exit code 0 = all pass, 1 = any failure.
"""
import sys, subprocess, argparse
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

def _run_file(path):
    r = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    lines = [l.strip() for l in (r.stdout + r.stderr).splitlines() if l.strip()]
    summary = next(
        (l for l in reversed(lines) if any(x in l for x in
            ["passed", "PASS", "FAIL", "failed", "Error"])),
        lines[-1] if lines else "(no output)"
    )
    return r.returncode == 0, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast",      action="store_true", help="Skip benchmarks")
    parser.add_argument("--benchmark", action="store_true", help="Benchmark suite only")
    args = parser.parse_args()

    print()
    print("=" * 70)
    print("  WATER UTILITY PLANNING PLATFORM — FULL TEST SUITE")
    print("=" * 70)

    # (path, label, skip_when_fast)
    test_files = [
        (ROOT / "tests/core/test_costing_engine.py",
         "Costing engine (12 tests)", False),
        (ROOT / "tests/core/test_carbon_engine.py",
         "Carbon engine (7 tests)", False),
        (ROOT / "tests/domains/wastewater/test_engineering_calculations.py",
         "Engineering calculations (30 tests)", False),
        (ROOT / "tests/domains/wastewater/test_bnr_mbr.py",
         "BNR + MBR technology (16 tests)", False),
        (ROOT / "tests/domains/wastewater/test_decision_engine.py",
         "Decision engine — hierarchy, fields, two-pathway, consistency (81 tests)", False),
        (ROOT / "tests/integration/test_wastewater_full_run.py",
         "Full pipeline integration (8 tests)", False),
        (ROOT / "tests/core/test_qa_engine.py",
         "QA engine — model, input, cost, sludge, energy, report (30 tests)", False),
        (ROOT / "tests/domains/wastewater/test_benchmark_scenarios.py",
         "Legacy benchmark scenarios (57 checks)", True),
        (ROOT / "tests/benchmark/run_benchmarks.py",
         "Benchmark regression suite (282 checks)", True),
        (ROOT / "tests/test_decision_intelligence.py",
         "Decision Intelligence Layer (5 tests)", False),
        (ROOT / "tests/test_biosolids_dil.py",
         "BioPoint Decision Intelligence Layer (4 tests)", False),
        (ROOT / "tests/test_release_readiness.py",
         "Release readiness gate (60 checks)", False),
    ]

    if args.benchmark:
        test_files = [(ROOT / "tests/benchmark/run_benchmarks.py",
                       "Benchmark regression suite (282 checks)", False)]
    elif args.fast:
        print("  ⚡ Fast mode — skipping benchmark suite\n")

    passed_count = failed_count = 0
    failures = []

    for path, label, skip_in_fast in test_files:
        if args.fast and skip_in_fast and not args.benchmark:
            print(f"  ⏭️  {label:<58} [skipped]")
            continue
        if not path.exists():
            print(f"  ⚠️  {label:<58} [not found]")
            continue
        ok, summary = _run_file(path)
        print(f"  {'✅' if ok else '❌'} {label:<58} {summary[:30]}")
        if ok: passed_count += 1
        else:
            failed_count += 1
            failures.append((label, summary))

    print()
    print("=" * 70)
    total = passed_count + failed_count
    print(f"  {passed_count}/{total} test files passed  ({failed_count} failed)")
    if failures:
        print("\n  FAILURES:")
        for label, summary in failures:
            print(f"    ❌ {label}\n       {summary[:80]}")
    else:
        print("  ✅ ALL TESTS PASSED")
        if not args.fast:
            print("  Platform is release-ready.")
            print("  Run: streamlit run apps/wastewater_app/app.py")
    print("=" * 70 + "\n")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
