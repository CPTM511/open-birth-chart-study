"""Check the new sampling arithmetic on fixed toy data before the real run."""
import argparse
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from analyze import extended_frame, frame_bootstrap
from calibrate import exhaustive_fixture
from prepare_samples import allocate
from study import require, write_json
from verify_results import replay_bootstrap


def validate():
    require(allocate({"A": 5, "B": 1, "C": 9}, 10) == {"A": 4, "B": 1, "C": 5}, "Quota tie check")
    require(allocate({"A": 2, "B": 3}, 5) == {"A": 2, "B": 3}, "Census quota check")
    rows = [{"stratum_id": h} for h in ("A", "A", "A", "B", "B")]
    strata = np.array([r["stratum_id"] for r in rows])
    frame = {"A": 7, "B": 2}
    n, seed = 9999, 78
    hits = np.array([0, 2, 10, 4, 6], dtype=np.int64)
    point, draws, variance = frame_bootstrap(hits, strata, frame, seed=seed, draws=n)
    independently, again, exact_var = replay_bootstrap(hits, SimpleNamespace(rows=rows, frame=frame), seed, n)
    expected = Fraction(7, 9) * Fraction(12, 120) + Fraction(2, 9) * Fraction(10, 80)
    require(independently == expected and abs(float(expected) - point) < 1e-14, "Weighted toy estimate")
    require(abs(variance - float(exact_var)) < 1e-16 and np.allclose(draws, again, atol=4e-16, rtol=0),
            "Independent bootstrap arithmetic check")
    require(abs(float(draws.var(ddof=1)) / variance - 1) < 0.08, "Toy sampling variance differs")
    a, b = {"eligible_frame_records": 90, "joint_rate": 0.04}, {"eligible_frame_records": 10, "joint_rate": 0.02}
    e = extended_frame(a, b, np.full(10, 0.04), np.full(10, 0.02), 0.03)
    require(abs(e["expanded_joint_rate"] - 0.038) < 1e-16 and abs(e["expanded_minus_early"] + 0.002) < 1e-16,
            "Independent early/late benchmark")
    return {"status": "passed", "inputs": "synthetic_only", "quota_minima_ties_and_census_checked": True,
            "bootstrap_draws_compared": n, "weighted_toy_rate": str(expected), "design_variance": str(exact_var),
            "maximum_absolute_draw_mismatch": float(np.max(np.abs(draws - again))),
            "expanded_frame_rate": e["expanded_joint_rate"], "r11_pairing_fixture": exhaustive_fixture()}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    write_json(args.output, validate())
