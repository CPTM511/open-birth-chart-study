"""Check score classification with exact integers and variance with pairwise differences."""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
from fractions import Fraction
from itertools import combinations
from math import isclose, lcm, sqrt
from pathlib import Path

import numpy as np
from scipy.stats import t

from .analyze import estimate, load_reference
from .study import digest, load_target, private_job, read_json, require, write_json


def weighted_rank_tables(scores, weights):
    common_denominator = lcm(*(x.denominator for x in weights))
    integer_weights = [int(weight * common_denominator) for weight in weights]
    tables = {}
    for system in range(4):
        for band in range(4):
            score_weights = defaultdict(int)
            for person_scores, weight in zip(scores[:, band * 10:band * 10 + 10, system], integer_weights, strict=True):
                for value in person_scores:
                    score_weights[float(value)] += weight
            ordered = sorted(score_weights)
            cumulative = [0]
            for value in ordered:
                cumulative.append(cumulative[-1] + score_weights[value])
            tables[band, system] = ordered, cumulative
    return tables


def year_hits(scores, rank_tables):
    for person in scores:
        hits = 0
        for age, values in enumerate(person):
            high = 0
            for i, value in enumerate(values):
                scores_sorted, cumulative = rank_tables[age // 10, i]
                lt, le = bisect_left(scores_sorted, value), bisect_right(scores_sorted, value)
                high += 5 * (cumulative[lt] + cumulative[le]) >= 8 * cumulative[-1]
            hits += high >= 3
        yield hits


def exact_ratio_and_se(strata):
    denominator = sum(Fraction(pop * years, len(scans)) for scans in strata.values() for pop, _, years in scans)
    ratio = sum(Fraction(pop * hits, len(scans)) for scans in strata.values() for pop, hits, _ in scans) / denominator
    total = Fraction(0)
    for scans in strata.values():
        population = scans[0][0]
        count = len(scans)
        pair_terms = sum(((a[1] - b[1]) - ratio * (a[2] - b[2])) ** 2 for a, b in combinations(scans, 2))
        total += Fraction(population * (population - count), count * count * (count - 1)) * pair_terms
    return ratio, sqrt(total / denominator ** 2)


def check_toy():
    strata = {"a": [(9, 5, 20), (9, 0, 0), (9, 2, 10)], "b": [(3, 3, 10), (3, 2, 10), (3, 1, 10)]}
    point, se = exact_ratio_and_se(strata)
    expected = estimate(strata, .20)
    require(point == Fraction(27, 120) and isclose(expected["joint_rate"], float(point), abs_tol=1e-14),
            "Synthetic ratio or zero-record scan was handled incorrectly")
    require(isclose(expected["design_se_pp"], se * 100, abs_tol=1e-14) and expected["degrees_of_freedom"] == 4,
            "Synthetic design error or finite-population correction")
    whole_frame = {"c": [(3, 2, 10), (3, 1, 10), (3, 0, 10)]}
    require(exact_ratio_and_se(whole_frame) == (Fraction(1, 10), 0.0)
            and estimate(whole_frame, .10)["design_se_pp"] == 0, "A census should have no sampling error")


def run(job, r10_job, result, output, replay_job=None):
    check_toy()
    pages, rows, scores, _ = load_target(job)
    reference, _, reference_weights = load_reference(r10_job)
    tables = weighted_rank_tables(reference, reference_weights)
    ref = sum(weight * hits for weight, hits in zip(reference_weights, year_hits(reference, tables), strict=True))
    ref /= 40 * sum(reference_weights)
    released = read_json(result)
    require(isclose(ref, released["reference_rate"], rel_tol=0, abs_tol=1e-13), "Reference rate mismatch")
    variants = {}
    for key, array in scores.items():
        hits = list(year_hits(array, tables))
        scan_hits = defaultdict(int)
        scan_counts = defaultdict(int)
        for row, count in zip(rows, hits, strict=True):
            scan_hits[row["scan_unit"]] += count
            scan_counts[row["scan_unit"]] += 1
        strata = defaultdict(list)
        for scan, size in pages.items():
            strata[scan.split("-")[0]].append((size, scan_hits[scan], 40 * scan_counts[scan]))
        exact, se = exact_ratio_and_se(strata)
        reported = released["estimate"][key]
        require(isclose(exact, reported["joint_rate"], rel_tol=0, abs_tol=1e-13), "Joint high-score rate mismatch")
        if key == "base":
            delta = float((exact - ref) * 100)
            df = len(pages) - len(strata)
            margin = float(t.ppf(.975, df)) * se * 100
            expected = [delta - margin, delta + margin]
            require(isclose(delta, reported["delta_pp"], rel_tol=0, abs_tol=1e-11)
                    and np.allclose(expected, reported["conditional_ci95_delta_pp"], rtol=0, atol=1e-11)
                    and sum(hits) == reported["unweighted_joint_years"], "Primary contrast or interval differs")
        else:
            base = Fraction(variants["base"]["exact_joint_rate"])
            require(isclose(float((exact - ref) * 100), reported["delta_to_brazil_pp"], rel_tol=0, abs_tol=1e-11)
                    and isclose(float((exact - base) * 100), reported["change_from_base_pp"], rel_tol=0, abs_tol=1e-11),
                    "Clock sensitivity contrast differs")
        variants[key] = {"exact_joint_rate": str(exact)}
    review = {"reference_rate_exact": str(ref), "scoring_variants": variants,
              "candidate_records_checked": len(rows), "scans_checked": len(pages),
              "primary_whole_scan_variance_cross_check": True,
              "independent_calculation": "Separate Python integer rank and pairwise scan formulas",
              "shared_inputs": "Same source transcription and four-model scores",
              "finite_population_and_empty_scan_fixtures": "passed"}
    if replay_job is not None:
        require(job != replay_job, "Profile replay must be in a distinct directory")
        for name in ("profiles.json", "scoring_receipt.json"):
            require(digest(job / name) == digest(replay_job / name), "A complete profile replay differs")
        review["second_engine_run"] = {"profiles_and_scoring_receipt_byte_match": True,
                                       "trajectories": len(rows) * len(scores),
                                       "shared_inputs": "Same transcriptions, scoring engines and platform"}
    write_json(output, review)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--r10-job", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replay-job", type=Path)
    args = parser.parse_args()
    replay = private_job(args.replay_job) if args.replay_job is not None else None
    run(private_job(args.job), args.r10_job, args.results, args.output, replay)
