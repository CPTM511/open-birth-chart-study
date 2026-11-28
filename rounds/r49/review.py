"""Recompute R49 with exact ranks, rational windows and a separate covariance path."""

import argparse
from decimal import Decimal
from fractions import Fraction
from math import ceil, erfc, sqrt
from pathlib import Path

import numpy as np

from rounds.r27.verify import weighted_rank_tables
from rounds.r45.common import fractions
from rounds.r45.review import (centered, check_equal, classify_exact, demographics,
                               exact_mean_columns, integral_weights, points, spread)

from .analyze import load_study
from .common import GROUPS, REGISTRATION, ROOT, digest, private, protocol, read_json, require, write_json


def label(lower, upper, threshold):
    if upper < threshold:
        return "excluded"
    if lower > threshold:
        return "supported"
    return "unresolved"


def review_history(diagnostic, settings):
    source = ROOT / "rounds/r46/results.json"
    require(diagnostic["registration"] == REGISTRATION
            and diagnostic["old_aggregate_sha256"] == settings["r46_aggregate_sha256"] == digest(source),
            "R46 comparison source changed")
    old = read_json(source)
    r46 = old["primary"]["four_p75"]
    rule = r46["preselected_witnesses"]
    groups = old["families"]["p75_recorded"]["groups"]
    number = lambda x: Decimal(str(x))
    z = number(rule["z"])
    wide_z = number(old["critical"])
    narrow, wide = [], []
    for i, (age, witness, claimed) in enumerate(zip(old["age_starts"], rule["groups_by_age"], diagnostic["per_age"], strict=True)):
        point = {g: number(item["effect_curve"][i]) for g, item in groups.items()}
        se = {g: number(item["conditional_standard_error"][i]) for g, item in groups.items()}
        narrow.append(point[witness] + z * se[witness])
        next_upper, next_group = min((point[g] + wide_z * se[g], g) for g in groups)
        wide.append(next_upper)
        require(claimed["age"] == age and claimed["r46_fixed_group"] == witness
                and claimed["r46_simultaneous_group"] == next_group, "R46 witness identity differs")
        check_equal([narrow[-1], wide[-1], point[witness] + wide_z * se[witness]],
                    [claimed["fixed_upper"], claimed["simultaneous_upper"], claimed["same_group_with_simultaneous_margin"]],
                    "Decimal R46 upper-bound construction")
    projected = old["families"]["p75_recorded"]["peaks"]["all_groups"]
    check_equal([max(narrow), max(wide)], [r46["interval"][1], projected["simultaneous_interval"][1]], "Published R46 maxima")
    indices = [narrow.index(max(narrow)), wide.index(max(wide))]
    require([old["age_starts"][i] for i in indices] == [34, 34]
            and rule["groups_by_age"][indices[0]] == "br2009"
            and diagnostic["per_age"][indices[1]]["r46_simultaneous_group"] == "mx2009"
            and max(wide) < number(settings["gap_threshold"]) < max(narrow), "R46 difference did not reproduce")
    return rule


def verify_bounds(report, effects, errors, ages, settings):
    registered = settings["primary"]
    upper_z, lower_z = report["upper_z"], report["lower_z"]
    check_equal([erfc(upper_z / sqrt(2)) / 2, erfc(lower_z / sqrt(2)) / 2],
                [registered["upper_alpha"] / registered["upper_group_divisor"], registered["lower_alpha"]],
                "Registered one-sided tail probabilities")
    upper_curve = [min((float(effects[g][i]) + upper_z * errors[g][i], g) for g in effects) for i in range(len(ages))]
    upper_index = max(range(len(ages)), key=lambda i: upper_curve[i][0])
    up, up_group = upper_curve[upper_index]
    check_equal([value for value, _ in upper_curve], report["upper_curve"], "Adjusted upper curve")
    check_equal(up, report["upper"], "Adjusted joint upper bound")
    require(report["upper_attaining_age"] == ages[upper_index] and report["upper_attaining_group"] == up_group
            and report["threshold"] == settings["gap_threshold"], "Wrong R49 limiting upper group, age or threshold")
    if tuple(effects) != GROUPS:
        require(report["decision"] == "incomplete_four_group" and "point" not in report and "lower" not in report,
                "Partial group result appeared as a complete test")
        return

    min_curves = [min(curve[i] for curve in effects.values()) for i in range(len(ages))]
    check_equal(min_curves, report["point_curve"], "R49 exact common shape")
    true_peak = max(min_curves)
    earliest = min(i for i, value in enumerate(min_curves) if abs(float(value - true_peak)) <= 1e-14)
    require(report["start_age"] == ages[earliest], "R49 peak age differs")
    index = ages.index(registered["lower_start_age"])
    down, down_group = min((float(effects[g][index]) - lower_z * errors[g][index], g) for g in effects)
    check_equal([true_peak, down], [report["point"], report["lower"]], "R49 common peak and lower bound")
    require(report["lower_attaining_group"] == down_group and report["lower_start_age"] == ages[index]
            and report["decision"] == label(down, up, settings["gap_threshold"]), "Wrong registered R49 decision")


def verify_auxiliary(actual, effects, errors, critical, ages, rule, threshold):
    if tuple(effects) != GROUPS:
        require(not actual, "Auxiliary comparisons require four groups")
        return
    values = {g: [float(x) for x in curve] for g, curve in effects.items()}
    fixed_upper = [values[g][i] + rule["z"] * errors[g][i] for i, g in enumerate(rule["groups_by_age"])]
    index = ages.index(rule["lower_bound_start_age"])
    fixed = [min(values[g][index] - rule["z"] * errors[g][index] for g in values), max(fixed_upper)]
    projected = [max(min(values[g][i] + sign * critical * errors[g][i] for g in values) for i in range(len(ages)))
                 for sign in (-1, 1)]
    fixed_report, full_report = actual["r46_fixed_witness"], actual["r49_full_simultaneous"]
    check_equal(fixed, fixed_report["interval"], "Fixed-witness comparison")
    check_equal(projected, full_report["simultaneous_interval"], "Full-band projection")
    require(fixed_report["decision"] == label(*fixed, threshold) and full_report["decision"] == label(*projected, threshold),
            "Auxiliary projection decisions differ")


def recalculate(reference, cohorts, public, settings):
    ages = list(range(settings["window_starts"][0], settings["window_starts"][1] + 1))
    require(public["age_starts"] == ages and set(public["groups"]) == set(cohorts), "Unexpected R49 coverage")
    cut = Fraction(*settings["threshold_percentile"])
    width = settings["window_width"]
    minimum = settings["minimum_systems"]
    tables = weighted_rank_tables(reference.scores, fractions(reference.rows))
    ref_flags = classify_exact(reference.scores, tables, cut)
    _, _, ref_gaps = points(ref_flags, minimum, width)
    center = exact_mean_columns(centered(ref_gaps), integral_weights(reference.rows), len(ages))
    check_equal(center, public["fixed_reference_center"], "Fixed p75 Brazil 2006 reference")
    errors, curves = {}, {}
    n_checked, largest_error = ref_flags.size, 0.
    rules = settings["simultaneous_bands"]
    draws = rules["normal_draws"]
    maxima = np.zeros(draws)
    for order, (g, cohort) in enumerate(cohorts.items()):
        flags = classify_exact(cohort.scores, tables, cut)
        n_checked += flags.size
        ones, counts, gaps = points(flags, minimum, width)
        weights = integral_weights(cohort.rows)
        report = public["groups"][g]
        demographics(report, ones, counts, gaps, weights, width)
        check_equal(Fraction(sum(weights)**2, sum(w*w for w in weights)), report["weight_effective_n"], "Weight effective N")
        raw = centered(gaps)
        means = exact_mean_columns(raw, weights, len(ages))
        curves[g] = [value - base for value, base in zip(means, center, strict=True)]
        largest_error = max(largest_error, check_equal(curves[g], report["effect_curve"], "R49 rational shape"))
        matrix = np.asarray([[Fraction(x, len(ages)) - base for x, base in zip(row, center, strict=True)] for row in raw], dtype=float)
        se, extremes, missing = spread(matrix, cohort.rows, draws, rules["normal_seed"] + order)
        require(missing == 0, "Uncovered noncensused stratum")
        check_equal(se, report["conditional_standard_error"], "Independent stratified covariance")
        errors[g] = se
        maxima = np.maximum(maxima, extremes)
    critical = float(sorted(maxima)[ceil((draws - 1) * rules["confidence"])])
    check_equal(critical, public["simultaneous_critical"], "Independent R49 band critical value")
    for g, se in errors.items():
        check_equal(se * critical, public["groups"][g]["simultaneous_margin"], "R49 full simultaneous margins")
    return ages, curves, errors, critical, int(n_checked), largest_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("job", "r10-job", "results", "diagnostic", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    settings = protocol()
    public = read_json(args.results)
    require(public["registration"] == REGISTRATION, "R49 result registration differs")
    rule = review_history(read_json(args.diagnostic), settings)
    reference, cohorts, coverage = load_study(private(args.job), args.r10_job, settings)
    require(coverage == public["coverage"], "R49 release coverage differs from the score receipts")
    ages, curves, errors, critical, classifications, discrepancy = recalculate(reference, cohorts, public, settings)
    verify_bounds(public["primary"], curves, errors, ages, settings)
    verify_auxiliary(public["auxiliary"], curves, errors, critical, ages, rule, settings["gap_threshold"])
    write_json(args.output, dict(registration=REGISTRATION, results_sha256=digest(args.results),
                                r46_diagnostic_sha256=digest(args.diagnostic), source_curves_recalculated=len(curves),
                                weighted_threshold_classifications=classifications, maximum_effect_disagreement=discrepancy,
                                multiplier_draws_replayed=settings["simultaneous_bands"]["normal_draws"],
                                r46_directional_and_simultaneous_difference_verified=True,
                                r49_primary_calculation_verified=True, auxiliary_comparisons_replayed=len(public["auxiliary"])))


if __name__ == "__main__":
    main()
