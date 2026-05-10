"""
tests/core/characteriser/run_characteriser_tests.py

Wrapper that invokes pytest on the design envelope engine test suite and
prints a summary in the format run_tests.py expects.

The Phase 5 tests use pytest (fixtures, parametrize, tmp_path) — this
wrapper bridges them into the platform's standalone-script test runner.

Run directly:
    python3 tests/core/characteriser/run_characteriser_tests.py
Or via:
    python3 run_tests.py --fast
"""
import subprocess
import sys
from pathlib import Path


def main():
    here = Path(__file__).resolve().parent
    root = here.parent.parent.parent  # repo root

    print()
    print("=" * 55)
    print("  Design envelope engine (131 tests)")
    print("=" * 55)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(here),
         "--tb=short", "-q", "--no-header"],
        capture_output=True, text=True, cwd=str(root),
    )

    output = result.stdout + result.stderr
    print(output)

    if result.returncode == 0:
        # pytest prints e.g. "131 passed in 70.82s"; extract the pass count
        last_line = [l for l in output.splitlines() if "passed" in l]
        if last_line:
            print(f"  ✅ {last_line[-1].strip()}")
        else:
            print("  ✅ ALL PASSED")
        return 0
    else:
        print("  ❌ FAILED — see output above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
