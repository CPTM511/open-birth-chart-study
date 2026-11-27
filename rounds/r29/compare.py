"""Compare the paired clocks with floating and independently integer-ranked classifications."""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
from math import isclose
from pathlib import Path
import platform
import subprocess

import numpy as np

from .clock_pairs import HERE, R10, digest, inputs, private_job, read_json, read_pairs, require, rounding_shift
from rounds.r27.archive_source import write_json
from rounds.r27.verify import weighted_rank_tables
from analyze_cohorts import PrecisionReference


def paired_metrics(flags, weights):
    original, rounded = flags
    high_original = original.sum(axis=2) >= 3
    high_rounded = rounded.sum(axis=2) >= 3
    lost = high_original & ~high_rounded
    gained = ~high_original & high_rounded
    changed = lost | gained

    def rate(cells):
        return float(np.average(cells.mean(axis=1), weights=weights))

    lost_rate, gained_rate = rate(lost), rate(gained)
    return {
        "joint_rate_original": rate(high_original),
        "joint_rate_rounded": rate(high_rounded),
        "rounded_minus_original_pp": 100 * (gained_rate - lost_rate),
        "joint_lost_rate": lost_rate,
        "joint_gained_rate": gained_rate,
        "joint_reversal_rate": rate(changed),
        "records_with_any_reversal_rate": float(np.average(changed.any(axis=1), weights=weights)),
        "system_reversal_rates": np.average((original != rounded).mean(axis=1), weights=weights, axis=0).tolist(),
    }


def integer_flags(scores, tables):
    flags = np.zeros(scores.shape, dtype=bool)
    for band in range(4):
        window = range(10 * band, 10 * band + 10)
        for system in range(4):
            ordered, prefix = tables[band, system]
            for record, trajectory in enumerate(scores):
                for age in window:
                    score = trajectory[age, system]
                    below, at_or_below = bisect_left(ordered, score), bisect_right(ordered, score)
                    flags[record, age, system] = 5 * (prefix[below] + prefix[at_or_below]) >= 8 * prefix[-1]
    return flags


def check_transitions(flags, weights, metrics):
    total_weight = sum(weights)
    old, new = (branch.sum(axis=2) >= 3 for branch in flags)
    annual_counts = {
        "joint_rate_original": old.sum(axis=1),
        "joint_rate_rounded": new.sum(axis=1),
        "joint_lost_rate": (old & ~new).sum(axis=1),
        "joint_gained_rate": (new & ~old).sum(axis=1),
        "joint_reversal_rate": (old != new).sum(axis=1),
        "records_with_any_reversal_rate": 40 * (old != new).any(axis=1),
    }
    for i in range(4):
        annual_counts[f"system_{i}"] = (flags[0, :, :, i] != flags[1, :, :, i]).sum(axis=1)
    expected_metrics = dict(metrics)
    expected_metrics.update({f"system_{i}": value for i, value in enumerate(metrics["system_reversal_rates"])})
    exact = {key: sum(weight * int(count) for weight, count in zip(weights, counts, strict=True)) / (40 * total_weight)
             for key, counts in annual_counts.items()}
    exact["rounded_minus_original_pp"] = 100 * (exact["joint_rate_rounded"] - exact["joint_rate_original"])
    require(all(isclose(float(rate), expected_metrics[key], rel_tol=0, abs_tol=1e-12) for key, rate in exact.items()),
            "Separate integer rank and exact-weight result differs")
    return {key: str(rate) for key, rate in exact.items()}


def run(job, replay_job, r10_job, data, second_data, output):
    require(job != replay_job and data.resolve() != second_data.resolve(), "Independently reacquire and replay in distinct paths")
    require(digest(data) == digest(second_data), "The two downloads differ")
    groups, reference = inputs(r10_job, data)
    profiles = job / "profiles.jsonl"
    profile_sha = digest(profiles)
    require(profile_sha == digest(replay_job / profiles.name), "The fresh scoring replay differs")
    pairing = read_pairs(groups, profiles)
    _, ref_weights = groups["brazil2006"]
    reference_weights = np.asarray([float(weight) for weight in ref_weights])
    calibration = PrecisionReference(reference, reference_weights, ref_weights)
    rank_tables = weighted_rank_tables(reference, ref_weights)
    released_reference = read_json(R10 / "independent_replay/results/structural_comparison.json")
    expected_reference = released_reference["reference"]["joint_rate"]
    require(isclose(calibration.joint_rate, expected_reference, rel_tol=0, abs_tol=1e-13), "Frozen R10 rate differs")
    brazil_scores = pairing["brazil2006"][0][0]
    raw_max_difference = float(np.max(np.abs(brazil_scores - reference)))
    require(raw_max_difference <= 1e-12 and np.array_equal(calibration.flags(brazil_scores), calibration.flags(reference)),
            "Recomputed Brazil baseline differs in score or classification")

    estimates = {}
    checked = {}
    for cohort, (arrays, shifted) in pairing.items():
        flags = np.asarray([calibration.flags(variant) for variant in arrays])
        exact_flags = np.asarray([integer_flags(variant, rank_tables) for variant in arrays])
        require(np.array_equal(flags, exact_flags), "Threshold decisions differ in the second classification")
        rows, weights = groups[cohort]
        estimate = paired_metrics(flags, np.asarray([float(weight) for weight in weights]))
        civil = [datetime.fromisoformat(row["birth_local"]) for row in rows]
        estimates[cohort] = {
            "records": len(rows), "changed_clocks": shifted, "whole_hour_original": len(rows) - shifted,
            "rounded_across_midnight": sum(
                value.date() != (value + timedelta(minutes=rounding_shift(value))).date() for value in civil
            ),
            "record_years": len(rows) * 40, **estimate,
        }
        checked[cohort] = check_transitions(exact_flags, weights, estimate)
    write_json(output, {
        "round": "R29",
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "source_sha256": digest(data),
        "reference_rate": calibration.joint_rate,
        "system_order": ["bazi", "ziwei_doushu", "qizheng_siyu", "western_astrology"],
        "fixed_sample_no_population_inference": True,
        "estimate": estimates,
        "verification": {
            "different_downloads_byte_match": True,
            "rerun_score_file_sha256": profile_sha,
            "actual_four_system_trajectories_per_run": sum(len(rows) + pairing[name][1] for name, (rows, _) in groups.items()),
            "brazil_original_vs_frozen_max_score_difference": raw_max_difference,
            "all_threshold_decisions_byte_match_integer_ranks": True,
            "exact_paired_estimates": checked,
            "software": {"platform": platform.platform(), "python": platform.python_version(), "numpy": np.__version__,
                         "node": subprocess.check_output(["node", "--version"], text=True).strip()},
        },
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--replay-job", type=Path, required=True)
    parser.add_argument("--r10-job", type=Path, required=True)
    parser.add_argument("--jse-data", type=Path, required=True)
    parser.add_argument("--second-jse-data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(private_job(args.job), private_job(args.replay_job), args.r10_job, args.jse_data, args.second_jse_data, args.output)
