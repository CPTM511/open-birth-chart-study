"""Estimate the Lyon clock transitions and verify the stratified ratios."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
from math import isclose
from pathlib import Path
import platform
import subprocess

import numpy as np

from rounds.r27.analyze import estimate, frame_strata, load_reference
from rounds.r27.study import R10, write_json
from rounds.r27.verify import check_toy, exact_ratio_and_se, weighted_rank_tables, year_hits
from rounds.r29.clock_pairs import read_pairs, rounding_shift
from rounds.r29.compare import check_transitions, integer_flags, paired_metrics
from analyze_cohorts import PrecisionReference

from .study import COHORT, HERE, LATITUDE, LONGITUDE, OFFSET_SECONDS, digest, private_job, read_json, require, resolve


SYSTEMS = ("bazi", "ziwei_doushu", "qizheng_siyu", "western_astrology")
PRACTICAL_PP = .30


def design_metric(pages, rows, counts, reference=0):
    strata = frame_strata(pages, rows, counts)
    point = estimate(strata, reference)
    exact, se = exact_ratio_and_se(strata)
    require(isclose(float(exact), point["joint_rate"], rel_tol=0, abs_tol=1e-14)
            and isclose(100 * se, point["design_se_pp"], rel_tol=0, abs_tol=1e-12)
            and point["degrees_of_freedom"] == 26, "The two scan design calculations disagree")
    return {
        "estimate_pp": point["delta_pp"],
        "conditional_ci95_pp": point["conditional_ci95_delta_pp"],
        "design_se_pp": point["design_se_pp"],
        "unweighted_estimate_pp": (point["joint_rate_unweighted"] - reference) * 100,
        "unweighted_numerator": int(sum(counts)),
        "exact_weighted_ratio_before_reference_subtraction": str(exact),
    }


def analyze(source, source_recheck, first_run, replay_run, r10_job, output):
    check_toy()
    require(first_run != replay_run, "The score replay must use a different run directory")
    primary = first_run / "profiles.jsonl"
    profile_sha = digest(primary)
    require(profile_sha == digest(replay_run / primary.name), "The repeated four-system score files differ")
    pages, groups, transcription = resolve(source, source_recheck)
    rows, weights = groups[COHORT]
    scores, shifted = read_pairs(groups, primary)[COHORT]
    reference, reference_weights, exact_reference_weights = load_reference(r10_job)
    weighted = PrecisionReference(reference, reference_weights, exact_reference_weights)
    tables = weighted_rank_tables(reference, exact_reference_weights)
    reference_exact = sum(weight * hits for weight, hits in zip(
        exact_reference_weights, year_hits(reference, tables), strict=True
    )) / (40 * sum(exact_reference_weights))
    reference_published = read_json(R10 / "independent_replay/results/structural_comparison.json")["reference"]["joint_rate"]
    require(isclose(weighted.joint_rate, reference_published, rel_tol=0, abs_tol=1e-13)
            and isclose(float(reference_exact), reference_published, rel_tol=0, abs_tol=1e-13),
            "Frozen reference rate differs from the release")

    flags = np.asarray([weighted.flags(branch) for branch in scores])
    exact_flags = np.asarray([integer_flags(branch, tables) for branch in scores])
    require(np.array_equal(flags, exact_flags), "Rank implementations yield different high-score decisions")
    transitions = paired_metrics(flags, np.asarray([float(weight) for weight in weights]))
    exact_transitions = check_transitions(exact_flags, weights, transitions)

    original, rounded = flags.sum(axis=-1) >= 3
    lost = original & ~rounded
    gained = ~original & rounded
    changed = original != rounded
    civil = [datetime.fromisoformat(row["birth_local"]) for row in rows]
    nonhour = np.asarray([when.minute != 0 for when in civil])
    require(shifted == int(nonhour.sum()) and not changed[~nonhour].any(), "An unchanged clock changed the joint result")
    counts = {
        "original_joint": original.sum(axis=1),
        "rounded_joint": rounded.sum(axis=1),
        "net_change": gained.sum(axis=1) - lost.sum(axis=1),
        "joint_reversal": changed.sum(axis=1),
        "joint_loss": lost.sum(axis=1),
        "joint_gain": gained.sum(axis=1),
        "records_with_reversal": changed.any(axis=1) * 40,
        "records_with_nonhour_clock": nonhour * 40,
    }
    metrics = {name: design_metric(pages, rows, values) for name, values in counts.items()}
    metrics["original_minus_frozen_brazil"] = design_metric(pages, rows, counts["original_joint"], weighted.joint_rate)
    per_system = {name: design_metric(pages, rows, (flags[0, :, :, index] != flags[1, :, :, index]).sum(axis=1))
                  for index, name in enumerate(SYSTEMS)}
    require(isclose(metrics["net_change"]["estimate_pp"], transitions["rounded_minus_original_pp"],
                    rel_tol=0, abs_tol=1e-12)
            and isclose(metrics["joint_reversal"]["estimate_pp"], transitions["joint_reversal_rate"] * 100,
                        rel_tol=0, abs_tol=1e-12)
            and all(isclose(item["estimate_pp"], rate * 100, rel_tol=0, abs_tol=1e-12)
                    for item, rate in zip(per_system.values(), transitions["system_reversal_rates"], strict=True)),
            "Scan totals differ from independently weighted record totals")

    record_count_metrics = ("records_with_reversal", "records_with_nonhour_clock")
    for name in record_count_metrics:
        metrics[name]["unweighted_numerator"] //= 40
    source_seal = read_json(HERE / "source_receipt.json")
    engines = R10 / "methods/open_birth_chart_r10"
    root = HERE.parents[1]
    net_low, net_high = metrics["net_change"]["conditional_ci95_pp"]
    flip_low, _ = metrics["joint_reversal"]["conditional_ci95_pp"]
    write_json(output, {
        "round": "R37",
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "transcription": transcription,
        "design": {
            "archive_year": 1901,
            "municipal_districts": len({volume["district"] for volume in source_seal["volumes"].values()}),
            "register_volumes": len(source_seal["volumes"]),
            "eligible_scans_in_frame": source_seal["eligible_scan_positions"],
            "selected_scans": len(pages),
            "variance_df": 26,
            "unweighted_birth_records": len(rows),
            "model_years_per_record": 40,
            "unweighted_record_years": 40 * len(rows),
            "design_weighted_record_years_exact": str(40 * sum(weights)),
            "distinct_actual_birth_dates": len({when.date() for when in civil}),
            "historical_civil_offset_seconds": OFFSET_SECONDS,
            "city_reference_latitude": LATITUDE,
            "city_reference_longitude": LONGITUDE,
            "pointwise_conditional_intervals": True,
        },
        "input_precision": {
            "recorded_precision_counts": dict(sorted(Counter(row["recorded_clock_precision"] for row in rows).items())),
            "nonhour_clocks_shifted": shifted,
            "rounded_across_civil_midnight": sum(
                when.date() != (when + timedelta(minutes=rounding_shift(when))).date() for when in civil
            ),
        },
        "brazil_2006_fixed_reference": {"records": len(reference), "joint_rate": weighted.joint_rate,
                                       "exact_joint_rate": str(reference_exact)},
        "system_order": list(SYSTEMS),
        "estimates": metrics,
        "system_reversal_estimates": per_system,
        "practical_thresholds": {
            "percentage_points": PRACTICAL_PP,
            "net_change_interval_within_plus_or_minus_threshold": -PRACTICAL_PP <= net_low and net_high <= PRACTICAL_PP,
            "joint_reversal_interval_entirely_above_threshold": flip_low > PRACTICAL_PP,
        },
        "verification": {
            "source_receipt_sha256": digest(HERE / "source_receipt.json"),
            "source_orders_and_selected_scans_byte_verified_separately": True,
            "fresh_profiles_per_run": len(rows) + shifted,
            "matching_rerun_profiles_sha256": profile_sha,
            "exact_integer_rank_matches_all_lyon_decisions": True,
            "exact_pair_transitions": exact_transitions,
            "independent_pairwise_scan_variance_matches": True,
            "empty_scan_and_finite_population_fixtures": "passed",
            "frozen_scoring_files_sha256": {
                str(path.relative_to(root)): digest(path)
                for path in [R10 / "methods/run_profiles.py", R10 / "methods/r10_io.py",
                             *sorted(file for file in engines.iterdir() if file.is_file())]
            },
            "software": {"platform": platform.platform(), "python": platform.python_version(),
                         "numpy": np.__version__, "node": subprocess.check_output(["node", "--version"], text=True).strip()},
        },
        "external_outcomes_used": False,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "source-recheck", "job", "replay-job", "r10-job", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    analyze(private_job(args.source), private_job(args.source_recheck), private_job(args.job),
            private_job(args.replay_job), args.r10_job, args.output)
