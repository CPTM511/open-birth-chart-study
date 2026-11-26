#!/usr/bin/env python3
"""Run existing synthetic/published-fixture checks without source cohort data.

This is a thin test-suite entry point. It does not alter models or statistics,
download data, inspect private profiles, or validate mortality prediction.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

SMOKE_TESTS = [
    "test_bazi_ziwei.BaziTests.test_qiyun_minute_conversion_and_no_decadal_gaps",
    "test_bazi_ziwei.BaziTests.test_invalid_data_abstain_not_zero",
    "test_bazi_ziwei.ZiweiTests.test_golden_2026_transformations_and_year_palace",
    "test_bazi_ziwei.ZiweiTests.test_40_years_cycle_coverage_and_compact_scores",
    "test_qizheng_western.AstronomicalChecks.test_time_offset_and_missing_clock",
    "test_qizheng_western.WorkflowChecks.test_compact_full_equal_and_twelve_samples",
    "test_analysis.ReferenceTests.test_independent_phase_mean_matches_enumeration",
    "test_analysis.ReferenceTests.test_column_vector_weights_rejected",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Run all existing test_*.py suites instead of the eight-check smoke subset")
    parser.add_argument("--output", type=Path, help="Optional JSON verification report")
    args = parser.parse_args()
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py") if args.full else loader.loadTestsFromNames(SMOKE_TESTS)
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "full_existing_suites" if args.full else "eight_check_smoke",
        "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "successful": result.wasSuccessful(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "input_scope": "Existing synthetic and fixed published fixtures only; no private or source-cohort birth records",
        "downloads": False, "mortality_validation": False,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
