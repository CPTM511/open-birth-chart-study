"""Rebuild the portable reference and compare it with the sealed R49 release."""

import argparse
from collections import defaultdict
from fractions import Fraction
from itertools import combinations, product
import json
from math import sqrt
from pathlib import Path
import subprocess

import numpy as np

from rounds.r27.verify import weighted_rank_tables
from rounds.r45.common import digest, fractions, read_json, require, write_json
from rounds.r45.review import centered, check_equal, classify_exact, exact_mean_columns, integral_weights, points
from rounds.r49.analyze import load_study
from rounds.r49.common import protocol

from .compare import AGE_STARTS, MAIN_AGE, SYSTEMS, WINDOW_COUNT, WINDOW_WIDTH
from .compare import centered_gap_integers, classify_scores, cutoff_rule, fixed_age_contrast


HERE = Path(__file__).resolve().parent
R49 = HERE.parent / "r49"
R49_RELEASE = "3a57e87227e81b4437f410d04752473c41c56fb3"
R50_REGISTRATION = "60fbd1850a3db8ca671ca79bd1f902bbb279b4c2"
P75 = Fraction(3, 4)
MAIN_INDEX = AGE_STARTS.index(MAIN_AGE)


def released_path(directory, commit, name):
    path = directory / name
    root = HERE.parents[1]
    original = subprocess.check_output(["git", "show", f"{commit}:{path.relative_to(root)}"], cwd=root)
    require(path.read_bytes() == original, f"Published evidence differs for {path.name}")
    return path


def build_cutoffs(tables):
    cutoffs = []
    for (band, system), table in sorted(tables.items()):
        value, operator = cutoff_rule(*table)
        cutoffs.append({"age_from": AGE_STARTS[band * WINDOW_WIDTH],
                        "system": SYSTEMS[system], "score": value, "operator": operator})
    return cutoffs


def check_boundaries(cutoffs, tables):
    probes = np.zeros((3, 40, 4))
    count = 0
    for rule in cutoffs:
        start = rule["age_from"] - AGE_STARTS[0]
        system = SYSTEMS.index(rule["system"])
        value = rule["score"]
        neighbors = np.clip([np.nextafter(value, -np.inf), value, np.nextafter(value, np.inf)], 0, 1)
        probes[:, start:start + WINDOW_WIDTH, system] = neighbors[:, None]
        count += len(set(neighbors))
    require(np.array_equal(classify_scores(probes, cutoffs), classify_exact(probes, tables, P75)),
            "Portable reference changes a P75 boundary classification")
    return count


def check_scores(scores, cutoffs, tables, name):
    flags = classify_scores(scores, cutoffs)
    expected_flags = classify_exact(scores, tables, P75)
    require(np.array_equal(flags, expected_flags), f"Portable classifications differ for {name}")
    values = centered_gap_integers(flags)
    _, _, gaps = points(expected_flags, 3, WINDOW_WIDTH)
    require(np.array_equal(values, centered(gaps)), f"Portable centered windows differ for {name}")
    return values


def sample_moments(rows, values):
    frame = {}
    by_stratum = defaultdict(list)
    for row, value in zip(rows, values, strict=True):
        key = row["stratum_id"]
        sizes = (row["N_h"], row["n_h"])
        require(frame.setdefault(key, sizes) == sizes, "Inconsistent sealed stratum counts")
        by_stratum[key].append(int(value))
    for key, entries in by_stratum.items():
        population, expected_n = frame[key]
        require(len(entries) == expected_n, "Incomplete sealed stratum")
        yield population, expected_n, sum(entries), sum(value ** 2 for value in entries)


def check_enumerated_variance():
    populations = ((-8, 1, 3, 16), (-5, 5, 22), (10,))
    draws = [combinations(frame, n) for frame, n in zip(populations, (2, 2, 1), strict=True)]
    truth = Fraction(sum(map(sum, populations)), WINDOW_COUNT * sum(map(len, populations)))
    estimates, variances = [], []
    for selections in product(*draws):
        sample = [(len(frame), len(rows), sum(rows), sum(x ** 2 for x in rows))
                  for frame, rows in zip(populations, selections, strict=True)]
        estimate, variance = fixed_age_contrast(sample, Fraction(0))
        estimates.append(estimate)
        variances.append(variance)
    actual_variance = sum((estimate - truth) ** 2 for estimate in estimates) / len(estimates)
    require(sum(estimates) / len(estimates) == truth and sum(variances) / len(variances) == actual_variance,
            "Finite-population variance disagrees with enumeration")
    return {"equiprobable_stratified_draws": len(estimates), "true_design_variance": str(actual_variance)}


def run(job, r10_job, output):
    for name in ("REGISTRATION.md", "REGISTRATION.zh.md"):
        released_path(HERE, R50_REGISTRATION, name)
    settings = protocol()
    require(tuple(settings["ages"]) == (20, 59)
            and tuple(settings["window_starts"]) == (20, 50)
            and settings["window_width"] == WINDOW_WIDTH and settings["minimum_systems"] == 3
            and Fraction(*settings["threshold_percentile"]) == P75
            and settings["gap_threshold"] == 0.05
            and settings["primary"]["lower_start_age"] == MAIN_AGE, "R50 and R49 definitions differ")
    result_path = released_path(R49, R49_RELEASE, "results.json")
    public = read_json(result_path)
    reference, cohorts, _ = load_study(job, r10_job, settings)
    require(tuple(public["age_starts"]) == AGE_STARTS and set(cohorts) == set(public["groups"]),
            "The complete R49 comparison release is required")
    tables = weighted_rank_tables(reference.scores, fractions(reference.rows))
    # Exercise the JSON representation exactly as it will be read by a custodian.
    cutoffs = json.loads(json.dumps(build_cutoffs(tables), allow_nan=False))
    boundary_checks = check_boundaries(cutoffs, tables)
    reference_values = check_scores(reference.scores, cutoffs, tables, "Brazil 2006")
    centers = exact_mean_columns(reference_values.tolist(), integral_weights(reference.rows), WINDOW_COUNT)
    reference_delta = check_equal(centers, public["fixed_reference_center"], "Fixed reference centers")
    exact_centers = [str(value) for value in centers]
    center = Fraction(exact_centers[MAIN_INDEX])

    reports = {}
    for name, cohort in cohorts.items():
        values = check_scores(cohort.scores, cutoffs, tables, name)
        effect, variance = fixed_age_contrast(sample_moments(cohort.rows, values[:, MAIN_INDEX]), center)
        claimed = public["groups"][name]
        standard_error = sqrt(variance)
        effect_delta = check_equal(effect, claimed["effect_curve"][MAIN_INDEX], f"{name} age-34 effect")
        se_delta = check_equal(standard_error, claimed["conditional_standard_error"][MAIN_INDEX],
                               f"{name} age-34 design standard error")
        reports[name] = {"records": len(cohort.rows), "age_34_effect": float(effect),
                         "conditional_design_se": standard_error, "effect_abs_difference": effect_delta,
                         "se_abs_difference": se_delta}

    records = len(reference.rows) + sum(report["records"] for report in reports.values())
    proof = {"registration_commit": R50_REGISTRATION, "r49_release_commit": R49_RELEASE,
             "r49_results_sha256": digest(result_path)}
    portable = dict(proof, reference="R10 fixed Brazil 2006", percentile=str(P75),
                    score_cutoffs=cutoffs, age_starts=list(AGE_STARTS), window_years=WINDOW_WIDTH,
                    minimum_high_systems=3, main_start_age=MAIN_AGE, effect_threshold="1/20",
                    fixed_reference_center_proportions=exact_centers)
    review = dict(proof, boundary_values_checked=boundary_checks, reference_records=len(reference.rows),
                  total_binary_score_flags_compared=records * 40 * len(SYSTEMS),
                  total_centered_integer_windows_compared=records * WINDOW_COUNT,
                  largest_absolute_reference_center_difference=reference_delta,
                  groups=reports, toy_population=check_enumerated_variance(), new_external_records_scored=0)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "reference.json", portable)
    write_json(output / "review.json", review)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("job", "r10-job", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.job, args.r10_job, args.output)


if __name__ == "__main__":
    main()
