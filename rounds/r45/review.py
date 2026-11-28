"""Recompute R45 results through exact weighted ranks and integer window masks."""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from fractions import Fraction
from functools import cache
from math import ceil, lcm, sqrt
from pathlib import Path

import numpy as np

from .analyze import alternate_flags
from .common import REGISTRATION, digest, fractions, read_json, registered, require, write_json
from .datasets import add_paths, datasets
from .trajectories import load_all, paired_scores
from precision_reference import PrecisionReference
from rounds.r27.verify import weighted_rank_tables


def classify_exact(scores, tables, cutoff):
    @cache
    def high(band, system, value):
        values, prefix = tables[band, system]
        before, through = bisect_left(values, value), bisect_right(values, value)
        return cutoff.denominator*(prefix[before]+prefix[through]) >= 2*cutoff.numerator*prefix[-1]

    return np.asarray([[[high(age//10, s, float(score)) for s, score in enumerate(yr)]
                        for age, yr in enumerate(record)] for record in scores], dtype=bool)


def check_equal(expected, claimed, name):
    error = float(np.max(np.abs(np.asarray(expected, dtype=float)-np.asarray(claimed, dtype=float))))
    require(error < 5e-12, f"{name} differs by {error}")
    return error


def points(flags, cutoff, width):
    ones = flags.sum(axis=2) >= cutoff
    packed = [sum(1 << a for a, hit in enumerate(record) if hit) for record in ones]
    mask = (1 << width)-1
    counts = [[((row >> shift) & mask).bit_count() for shift in range(41-width)] for row in packed]
    no_hits = [[int(n == 0) for n in row] for row in counts]
    return ones, counts, no_hits


def integral_weights(rows):
    weights = fractions(rows)
    scale = lcm(*(f.denominator for f in weights))
    return [int(x*scale) for x in weights]


def exact_mean_columns(vectors, weights, denominator):
    total = sum(weights)*denominator
    return [Fraction(sum(w*x for w, x in zip(weights, column, strict=True)), total) for column in zip(*vectors)]


def centered(matrix):
    return [[len(values)*n-sum(values) for n in values] for values in matrix]


def demographics(claim, ones, counts, no_hits, weights, width):
    longest = [max(map(len, "".join("1" if hit else "0" for hit in row).split("1"))) for row in ones]
    table = Counter(longest)
    weighted = Counter()
    for n, w in zip(longest, weights, strict=True):
        weighted[n] += w
    total = sum(weights)
    require(claim["longest_gap_unweighted_histogram"] == [table[n] for n in range(41)],
            "Longest observed gaps or histogram counts differ")
    check_equal([Fraction(weighted[n], total) for n in range(41)], claim["longest_gap_weighted_histogram"],
                "Weighted longest gap distribution")
    for length, value in claim["at_least_gap_years"].items():
        check_equal(Fraction(sum(w for gap, w in weighted.items() if gap >= int(length)), total),
                    value, "Longest gap share")
    age_year_rates = exact_mean_columns([[int(x) for x in row] for row in ones], weights, 1)
    check_equal(age_year_rates, claim["age_joint_year_rates"], "Raw age joint-high rates")
    check_equal(sum(age_year_rates)/40, claim["joint_year_rate"], "Mean joint-high rate")
    age_gap_rates = exact_mean_columns(no_hits, weights, 1)
    check_equal(age_gap_rates, claim["age_ten_year_gap_rates"], "Raw age window gap rates")
    check_equal(sum(age_gap_rates)/len(age_gap_rates), claim["mean_ten_year_gap_probability"], "Mean gap share")
    require(all(x <= width for row in counts for x in row), "Window count outside its support")


def census_adjustments(claim, group, anchors, width, years, counts, no_hits, centers):
    weights = integral_weights(group.rows)
    starts = [[y-a for y in years] for a in anchors]
    m = len(counts[0])
    gap, density = centered(no_hits), centered(counts)
    raw_year_gap = [[bits[p] for p in indices] for bits, indices in zip(no_hits, starts, strict=True)]
    raw_year_density = [[hits[p] for p in indices] for hits, indices in zip(counts, starts, strict=True)]
    check_equal(exact_mean_columns(raw_year_gap, weights, 1), claim["calendar_ten_year_gap_rates"],
                "Raw calendar window gap rates")
    check_equal(exact_mean_columns(raw_year_density, weights, width), claim["calendar_ten_year_joint_rates"],
                "Raw calendar window joint-high rates")
    exact_rows = []
    for no, scores, indices in zip(gap, density, starts, strict=True):
        age = [Fraction(n, m)-r for n, r in zip(no, centers[0], strict=True)]
        cal_density = [Fraction(scores[p], m*width)-centers[1][p] for p in indices]
        exact_rows.append(age+[age[p] for p in indices]+cal_density)
    exact_effect = [sum(w*v for v, w in zip(column, weights, strict=True))/sum(weights)
                    for column in zip(*exact_rows)]
    error = check_equal(exact_effect, claim["effect_curve"], "Exact age/calendar residual")
    return np.asarray(exact_rows, dtype=float), exact_effect, error


def spread(values, rows, draws, seed):
    cells = defaultdict(list)
    for index, row in enumerate(rows):
        cells[row["stratum_id"]].append(index)
    frame = sum(rows[cell[0]]["N_h"] for cell in cells.values())
    sigma = np.zeros((values.shape[1], values.shape[1]))
    contributions = np.zeros(values.shape)
    uncovered = 0
    for cell in cells.values():
        population, n = rows[cell[0]]["N_h"], len(cell)
        if population == n:
            continue
        if n == 1:
            uncovered += population
            continue
        centered_cell = values[cell]-values[cell[0]]
        weight = population*(population-n)/(frame*frame*n)
        sigma += weight*np.cov(centered_cell, rowvar=False)
        deviations = centered_cell - centered_cell.mean(axis=0)
        contributions[cell] = deviations * sqrt(weight/(n-1))
    se = np.sqrt(np.diag(sigma))
    if not np.any(se):
        return se, np.zeros(draws), uncovered/frame
    positive = se > 0
    rng = np.random.default_rng(seed)
    maxima = []
    for i in range(0, draws, 127):
        normals = rng.standard_normal((min(draws-i,127), len(rows)))
        simulated = normals @ contributions[:, positive]
        maxima.extend(np.max(np.abs(simulated)/se[positive], axis=1))
    return se, np.asarray(maxima), uncovered/frame


def verify_peaks(summary, exact_curves, ages, years, margins, cfg):
    subsets = {"all_four": list(exact_curves), "born_1999": ["br1999", "mx1999"],
               "born_2009": ["br2009", "mx2009"]}
    k, n = len(ages), len(years)
    sizes = {"age_gap": (ages, 0, 1), "calendar_gap": (years, k, 1),
             "calendar_density_up": (years, k+n, 1), "calendar_density_down": (years, k+n, -1)}
    for metric, (axis, offset, sign) in sizes.items():
        limit = cfg["thresholds"][metric]
        for subset, groups in subsets.items():
            row = summary[metric][subset]
            positions = range(offset, offset+len(axis))
            lower, upper, points = [], [], []
            for p in positions:
                points.append(min(sign*exact_curves[g][p] for g in groups))
                lower.append(min(sign*float(exact_curves[g][p])-margins[g][p] for g in groups))
                upper.append(min(sign*float(exact_curves[g][p])+margins[g][p] for g in groups))
            peak = points.index(max(points))
            require(row["start"] == axis[peak] and row["threshold"] == limit, "Common peak position or threshold differs")
            check_equal(points[peak], row["estimate"], "Common peak estimate")
            check_equal([max(lower),max(upper)], row["simultaneous_interval"], "Simultaneous band projection")
            decision = "unresolved"
            if max(lower) > limit:
                decision = "supported"
            elif max(upper) < limit:
                decision = "excluded"
            require(decision == row["decision"], "Common effect classification differs")


def verify_family(report, groups, flags, ages, years, cfg):
    settings = cfg["inference"]
    cutoff, width = (cfg["recorded_rule"][k] for k in ("minimum_high_systems", "window_years"))
    draws = settings["normal_draws"]
    errors = Counter()
    joint, counts, empty = points(flags["reference"], cutoff, width)
    ref_weights = integral_weights(groups["reference"].rows)
    centers = [exact_mean_columns(centered(empty), ref_weights, len(ages)),
               exact_mean_columns(centered(counts), ref_weights, len(ages)*width)]
    demographics(report["reference"], joint, counts, empty, ref_weights, width)
    errors["reference"] = check_equal(centers, report["reference_centers"], "Reference age curves")
    peak = np.zeros(draws)
    curves, uncertainty, margins, gaps = {}, {}, {}, {}
    for i, (name, info) in enumerate(cfg["groups"].items()):
        cohort = groups[name]
        claim = report["groups"][name]
        raw, counts, absent = points(flags[name], cutoff, width)
        demographics(claim, raw, counts, absent, integral_weights(cohort.rows), width)
        # Re-derive the July 1 mapping instead of reusing the per-profile anchor.
        anchor = [int(row["birth_local"][:4])+20+int(row["birth_local"][5:10] > "07-01") for row in cohort.rows]
        values, curves[name], errors[name] = census_adjustments(
            claim, cohort, anchor, width, years, counts, absent, centers)
        sigma, extremes, weight = spread(values, cohort.rows, draws, settings["normal_seed"]+i)
        uncertainty[name] = sigma
        check_equal(sigma, claim["conditional_standard_error"], "Design-based standard error")
        gap_width, density_width = [np.asarray([2+abs(float(ref[t-info["birth_year"]-20] -
                               ref[t-info["birth_year"]-21])) for t in years]) for ref in centers]
        gaps[name] = weight*np.r_[np.full(len(ages),2.), gap_width, density_width]
        check_equal(gaps[name], claim["singleton_bound"], "Unobserved part of singleton stratum")
        peak = np.maximum(peak, extremes)
    q = sorted(peak)[ceil((draws-1)*settings["confidence"])]
    check_equal(q, report["critical_value"], "Simultaneous critical value")
    for name, item in report["groups"].items():
        margins[name] = q*uncertainty[name]+gaps[name]
        check_equal(margins[name], item["simultaneous_margin"], "Simultaneous margins")
    verify_peaks(report["peaks"], curves, ages, years, margins, cfg)
    return dict(critical_value=float(q), exact_age_and_calendar_effect_cells=len(ages)+2*len(years),
                verified_cross_group_peaks=12, largest_exact_curve_error=float(max(errors.values())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_paths(parser)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = registered()
    report = read_json(args.aggregate)
    require(report["registration"] == REGISTRATION, "Aggregate registration mismatch")
    catalog, all_inputs = datasets(args, cfg), load_all(args, cfg)
    cohorts = {name: all_inputs[name] for name in ("reference", *cfg["groups"])}
    ref = cohorts["reference"]
    ref_tables = weighted_rank_tables(ref.scores, fractions(ref.rows))
    fixed = PrecisionReference(ref.scores, ref.weights, fractions(ref.rows))
    probability_keys = {"primary": "high_percentile", "clock_compressed": "high_percentile",
                        "percentile_75": "sensitivity_percentile"}
    checked = {}
    planes = {"primary": {g: c.scores for g, c in cohorts.items()}}
    planes["clock_compressed"] = {"reference": ref.scores}
    for group in cfg["groups"]:
        scores, checks = paired_scores(cohorts[group], catalog[group], args.job, group, cfg)
        require(checks == report["raw_engine_verification"][group], "Paired receipt changed")
        planes["clock_compressed"][group] = scores
    planes["percentile_75"] = planes["primary"]
    for variant, plane in planes.items():
        cutoff = Fraction(*cfg["recorded_rule"][probability_keys[variant]])
        flags = {name: classify_exact(scores, ref_tables, cutoff) for name, scores in plane.items()}
        for name, scores in plane.items():
            expected = (fixed.flags(scores) if cutoff == Fraction(4,5) else
                        alternate_flags(scores, fixed, ref, cutoff))
            require(np.array_equal(flags[name], expected), f"Exact classification differs in {variant}")
        checked[variant] = verify_family(report[variant], cohorts, flags, report["age_starts"],
                                         report["calendar_starts"], cfg)
        checked[variant]["checked_threshold_decisions"] = sum(x.size for x in flags.values())
    holds = {}
    for group in cfg["holdout"]:
        member = all_inputs[group]
        flags = classify_exact(member.scores, ref_tables, Fraction(4,5))
        require(np.array_equal(flags, fixed.flags(member.scores)), "Archived sample threshold decisions differ")
        holds[group] = int(flags.size)
    write_json(args.output, dict(registration=REGISTRATION, aggregate_sha256=digest(args.aggregate),
                                 calculations=checked, archived_sample_threshold_decisions=holds,
                                 engine_probes_same_runtime_and_frozen_engine=True,
                                 separate_aggregate_implementation="integer masks, Fraction means and direct covariance",
                                 independently_replayed_multiplier_draws=cfg["inference"]["normal_draws"]))


if __name__ == "__main__":
    main()
