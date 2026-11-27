"""Validate the registered method on synthetic trajectories before opening any profiles."""
from __future__ import annotations

import argparse
from fractions import Fraction
from itertools import permutations, product
from pathlib import Path
from statistics import mean

import numpy as np

from calendar_controls import (
    Cell,
    check_registration,
    holm,
    permutation_summary,
    require,
    summarize_cells,
    write_json,
)


def exhaustive_fixture():
    trajectories = np.array([
        [[1, 1, 0, 1], [0, 0, 1, 1], [1, 0, 1, 1]],
        [[1, 0, 1, 0], [1, 1, 1, 1], [0, 1, 0, 0]],
        [[0, 1, 1, 0], [0, 0, 0, 1], [1, 1, 1, 0]],
    ], dtype=bool)
    cells = [Cell(trajectories, Fraction(15, 7)), Cell(trajectories[1:2], Fraction(1, 3))]
    observed, expected, support = summarize_cells(cells)
    donor_orders = tuple(permutations(range(3)))
    scores = []
    for perms in product(donor_orders, repeat=3):
        randomized = trajectories.copy()
        for s, donors in enumerate(perms, start=1):
            randomized[:, :, s] = trajectories[list(donors), :, s]
        scores.append(int(np.count_nonzero(randomized.sum(axis=2) >= 3)))
    singleton_total = int(np.count_nonzero(trajectories[1:2].sum(axis=2) >= 3))
    denom = (3 * Fraction(15, 7) + Fraction(1, 3)) * 3
    exact = (mean(Fraction(k) for k in scores) * Fraction(15, 7) + singleton_total * Fraction(1, 3)) / denom
    require(expected == exact, "Analytical expectation differs from exhaustive donor permutations")
    require(support["singleton_records"] == 1, "Singleton coverage was lost")
    require(holm([1, 5, 78], 99) == [0.06, 0.12, 0.79], "Holm arithmetic failed")
    zero = [Cell(np.ones((2, 3, 4), dtype=bool), Fraction(1))]
    same, same_expected, _ = summarize_cells(zero)
    tie = permutation_summary(zero, same, same_expected, 99, 1, 7)
    require(tie["p"] == 1 and tie["two_sided_tail_including_ties"] == 99, "Exact ties must count in the tail")
    return {"permutations_enumerated": len(scores), "expected_fraction": str(exact),
            "observed_fraction": str(observed), "singleton_retained": True,
            "holm_exercised": True, "ties_include_observed_in_tail": True}


def simulated_panel(rng, coupling):
    small_sizes = (3, 6, 10, 18, 24, 35)
    groups, states = [], {}
    periods = np.arange(20) // 5
    for i in range(32):
        n = small_sizes[i % len(small_sizes)]
        state, quarter = divmod(i, 4)
        high_season = (periods + quarter) % 4 < 2
        p = np.where(high_season, 0.45, 0.08)
        flags = rng.random((n, 20, 4)) < p[None, :, None]
        if coupling:
            couple = rng.random((n, 20)) < coupling
            shared = rng.random((n, 20)) < p
            flags[couple] = shared[couple, None]
        age_flags = flags.repeat(2, axis=1)
        weight = Fraction(2000 + 113 * state, 29 + 2 * state)
        groups.append(Cell(age_flags, weight))
        states.setdefault(state, []).append(age_flags)
    broad = [Cell(np.concatenate(arrays), Fraction(2000 + 113 * state, 29 + 2 * state))
             for state, arrays in sorted(states.items())]
    return groups, broad


def calibrate(protocol, registered_sha):
    settings = protocol["synthetic_gate"]
    rng = np.random.Generator(np.random.PCG64(settings["seed"]))
    fixture = exhaustive_fixture()
    p = (Fraction(8, 100), Fraction(45, 100))
    mixing = float(Fraction(1, 100) / mean(q - 4 * q**3 + 3 * q**4 for q in p))
    counts = {}
    for name, strength in (("seasonal_null", 0.0), ("shared_flag_injection", mixing)):
        raw_hits, family_hits = 0, 0
        differences, broad_differences = [], []
        for _ in range(settings["panels_each"]):
            cells, broad = simulated_panel(rng, strength)
            obs, exp, _ = summarize_cells(cells)
            _, broad_mean, _ = summarize_cells(broad)
            result = permutation_summary(
                cells, obs, exp, settings["draws_per_panel"], int(rng.integers(0, 2**32)), 0)
            raw_hits += result["p"] <= 0.05
            family_hits += result["p"] <= 0.05 / len(protocol["cohorts"])
            differences.append(float((obs - exp) * 100))
            broad_differences.append(float((obs - broad_mean) * 100))
        counts[name] = {"raw_05_rejections": raw_hits, "bonferroni_05_over_7_rejections": family_hits,
                        "mean_season_matched_excess_pp": mean(differences),
                        "mean_calendar_only_excess_pp": mean(broad_differences)}
    passed = (counts["seasonal_null"]["raw_05_rejections"] <= settings["max_false_rejections"]
              and counts["shared_flag_injection"]["bonferroni_05_over_7_rejections"] >= settings["min_injection_detections"])
    return {
        "id": protocol["id"], "registration_sha256": registered_sha, "parameters": settings,
        "status": "passed" if passed else "failed",
        "finite_sample_exact_fixture": fixture,
        "synthetic_truth": {"quarter_matched_null_excess_pp": 0, "injected_population_excess_pp": 1,
                            "coupling_probability": mixing, "ages": 40, "distinct_bernoulli_periods": 20,
                            "sample_records_per_panel": sum((3, 6, 10, 18, 24, 35)[i % 6] for i in range(32)),
                            "shared_age_quarter_rates": [0.08, 0.45]},
        "results": counts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = check_registration(args.registration_sha256)
    calibration = calibrate(protocol, args.registration_sha256)
    write_json(args.output, calibration)
    print(calibration["status"], calibration["results"])
    if calibration["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
