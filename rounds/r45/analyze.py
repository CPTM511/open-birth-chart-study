"""Run the frozen cross-source analysis and prepare public aggregate results."""

import argparse
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import numpy as np

from .common import REGISTRATION, fractions, registered, require, write_json
from .controls import calibration, pairing_control
from .datasets import add_paths, datasets, verify_profile
from .estimate import (Layout, curve_summary, describe, design_vectors, intervals, ranges, reference_curves,
                       residuals, weight_means, windows)
from .trajectories import load_all, paired_scores
from precision_reference import PrecisionReference


def alternate_flags(scores, fixed, reference, probability):
    values = fixed.transform(scores)
    flags = values >= float(probability)
    weights = fractions(reference.rows)
    total = sum(weights) * 10
    for band in range(4):
        age = slice(band*10, band*10+10)
        for system in range(4):
            results, points = values[:, age, system], scores[:, age, system]
            targets = np.unique(points[np.abs(results-float(probability)) < 2e-11])
            raw = reference.scores[:, age, system]
            for target in targets:
                counts = 2*(raw < target).sum(axis=1) + (raw == target).sum(axis=1)
                rank = sum(w*int(k) for k, w in zip(counts, weights, strict=True))/(2*total)
                flags[:, age, system][points == target] = rank >= probability
    return flags


def calendar_raw(win, cohort, layout):
    positions = layout.positions(cohort.anchors)
    select = lambda values: np.take_along_axis(values, positions, axis=1)
    return {"calendar_ten_year_gap_rates": weight_means(select(win.absent), cohort.weights).tolist(),
            "calendar_ten_year_joint_rates": (weight_means(select(win.totals), cohort.weights)/layout.width).tolist()}


def run_family(cohorts, flags, layout, cfg):
    cutoff = cfg["recorded_rule"]["minimum_high_systems"]
    joint = {g: score.sum(axis=2) >= cutoff for g, score in flags.items()}
    wins = {g: windows(years, layout) for g, years in joint.items()}
    reference = reference_curves(wins["reference"], cohorts["reference"].weights)
    design, curves, groups = {}, {}, {}
    for group, info in cfg["groups"].items():
        cohort = cohorts[group]
        values = residuals(wins[group], cohort.anchors, reference, layout)
        curves[group] = weight_means(values, cohort.weights)
        design[group] = design_vectors(values, cohort.rows, ranges(reference, info["birth_year"], layout))
        groups[group] = describe(joint[group], wins[group], cohort.weights) | calendar_raw(wins[group], cohort, layout)
    critical, standard, margins = intervals(design, cfg["inference"])
    for name, item in groups.items():
        item.update(effect_curve=curves[name].tolist(), conditional_standard_error=standard[name].tolist(),
                    simultaneous_margin=margins[name].tolist(), singleton_bound=design[name][1].tolist())
    ref = cohorts["reference"]
    summary = dict(reference=describe(joint["reference"], wins["reference"], ref.weights),
                   reference_centers=reference.tolist(), groups=groups, critical_value=critical,
                   peaks=curve_summary(curves, layout, cfg["thresholds"], margins))
    return summary, wins, joint, reference


def selection_controls(cohorts, wins, reference, layout, cfg):
    result = {}
    for variant in ("equally_weighted", "non_hour_only", "brazil1999_alagoas_only"):
        curves, audit = {}, {}
        for name in cfg["groups"]:
            cohort = cohorts[name]
            n = len(cohort.rows)
            keep = np.ones(n, dtype=bool)
            weight = np.ones(n) if variant == "equally_weighted" else cohort.weights
            if variant == "non_hour_only":
                keep = np.array([datetime.fromisoformat(r["birth_local"]).minute != 0 for r in cohort.rows])
            if variant == "brazil1999_alagoas_only" and name == "br1999":
                keep = np.array([row["stratum_id"].split("|")[1] == "27" for row in cohort.rows])
            values = residuals(wins[name], cohort.anchors, reference, layout)
            curves[name] = weight_means(values[keep], weight[keep])
            audit[name] = {"retained_records": int(keep.sum()), "retained_weight_share":
                           float(cohort.weights[keep].sum()/cohort.weights.sum())}
        result[variant] = dict(coverage=audit, peaks=curve_summary(curves, layout, cfg["thresholds"]))
    return result


def archived_checks(cohorts, fixed, reference, layout, cfg, main):
    old_point = {}
    for group in ("mx1990_1998", "mx2009_r10"):
        cohort = cohorts[group]
        win = windows(fixed.flags(cohort.scores).sum(axis=2) >= cfg["recorded_rule"]["minimum_high_systems"], layout)
        age = win.gap - reference[0]
        adjust = residuals(win, cohort.anchors, reference, layout) if group == "mx2009_r10" else age
        split_year = np.asarray([int(row["birth_local"][:4]) for row in cohort.rows])
        same_year_case = "born_1999" if group == "mx1990_1998" else "born_2009"
        by_metric = {}
        for name, (axis, ix, sign) in layout.metrics().items():
            if group == "mx1990_1998" and name != "age_gap":
                continue
            checks = {}
            for choice in ("all_four", same_year_case):
                window = main["peaks"][name][choice]
                start = window["start"]
                scores = sign * adjust[:, ix][:, axis.index(start)]
                checks[choice] = {
                    "start": start, "n": len(scores), "effect": float(weight_means(scores, cohort.weights)),
                    "by_birth_year": {str(y): {"n": int((split_year == y).sum()),
                                               "effect": float(weight_means(scores[split_year == y],
                                                                            cohort.weights[split_year == y]))}
                                      for y in sorted(set(split_year))},
                }
            by_metric[name] = checks
        old_point[group] = by_metric
    return old_point


def clock_changes(original, rounded, weights):
    distinct = original != rounded
    return {"record_year_reversal_rate": float(weight_means(distinct.mean(axis=1), weights)),
            "records_with_at_least_one_reversal": float(weight_means(distinct.any(axis=1), weights)),
            "mean_joint_rate_change": float(weight_means(rounded.mean(axis=1)-original.mean(axis=1), weights))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_paths(parser)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = registered()
    layout = Layout.from_protocol(cfg)
    controls = calibration(layout, cfg)
    catalog = datasets(args, cfg)
    cohorts = load_all(args, cfg)
    ref = cohorts["reference"]
    groups = {g: cohorts[g] for g in ("reference", *cfg["groups"])}
    fixed = PrecisionReference(ref.scores, ref.weights, fractions(ref.rows))
    main_flags = {g: fixed.flags(c.scores) for g, c in groups.items()}
    rounded_flags, arithmetic = {}, {}
    for group, c in groups.items():
        if group == "reference":
            rounded_flags[group] = main_flags[group]
            continue
        scores, arithmetic[group] = paired_scores(c, catalog[group], args.job, group, cfg)
        rounded_flags[group] = fixed.flags(scores)
    alternative = Fraction(*cfg["recorded_rule"]["sensitivity_percentile"])
    alternative_flags = {g: alternate_flags(c.scores, fixed, ref, alternative) for g, c in groups.items()}
    main_result, main_windows, main_joint, centers = run_family(groups, main_flags, layout, cfg)
    rounded_result, _, rounded_joint, _ = run_family(groups, rounded_flags, layout, cfg)
    sensitivity_result, _, _, _ = run_family(groups, alternative_flags, layout, cfg)
    for g in cfg["groups"]:
        rounded_result["groups"][g]["paired_clock_change"] = clock_changes(main_joint[g], rounded_joint[g], groups[g].weights)
    permutations = pairing_control(groups, main_flags, layout, cfg, main_result["peaks"])
    require(abs(main_result["reference"]["joint_year_rate"]-fixed.joint_rate) < 1e-14, "Fixed reference rate differs")
    if args.output.exists():
        raise FileExistsError("Use a new aggregate output file")
    write_json(args.output, dict(
        registration=REGISTRATION, age_starts=list(layout.ages), calendar_starts=list(layout.years),
        window_years=layout.width, primary=main_result, clock_compressed=rounded_result,
        percentile_75=sensitivity_result, input_coverage={name: c.publication for name, c in cohorts.items()},
        raw_engine_verification=arithmetic, main_counts_disjoint=True,
        sampling_diagnostics=selection_controls(groups, main_windows, centers, layout, cfg),
        prior_archived_checks=archived_checks(cohorts, fixed, centers, layout, cfg, main_result),
        pairing_control=permutations, synthetic_controls=controls, biological_or_life_outcomes_used=False,
    ))


if __name__ == "__main__":
    main()
