"""Run the preregistered R49 test and its two explanatory comparisons."""

import argparse
from fractions import Fraction
from pathlib import Path
from statistics import NormalDist

import numpy as np

from rounds.r45.analyze import alternate_flags
from rounds.r45.common import fractions
from rounds.r45.estimate import describe, design_vectors, intervals, weight_means, windows
from rounds.r46.analyze import decide, directional, family_band, layout
from rounds.r46.read_profiles import load_reference
from precision_reference import PrecisionReference

from .common import GROUPS, REGISTRATION, input_receipt, private, protocol, require, write_json
from .diagnose_r46 import replay
from .score import read_group


def primary_bounds(curves, errors, ages, settings):
    rule = settings["primary"]
    normal = NormalDist()
    upper_z = normal.inv_cdf(1 - rule["upper_alpha"] / rule["upper_group_divisor"])
    lower_z = normal.inv_cdf(1 - rule["lower_alpha"])
    effects = np.asarray(list(curves.values()))
    se = np.asarray([errors[g] for g in curves])
    require(effects.shape == se.shape == (len(curves), len(ages)) and np.all(se >= 0), "Wrong R49 group curves")
    adjusted = effects + upper_z * se
    smallest_upper = adjusted.min(axis=0)
    upper_idx = int(np.argmax(smallest_upper))
    upper = float(smallest_upper[upper_idx])
    upper_group = min(zip(adjusted[:, upper_idx], curves, strict=True))[1]
    result = dict(upper=upper, upper_attaining_age=ages[upper_idx], upper_z=upper_z, lower_z=lower_z,
                  upper_attaining_group=upper_group, threshold=settings["gap_threshold"], upper_curve=smallest_upper.tolist())
    if tuple(curves) != GROUPS:
        require(tuple(curves) == ("br1999", "br2009", "mx2009"), "Unexpected partial group composition")
        return dict(result, decision="incomplete_four_group")

    lower_idx = ages.index(rule["lower_start_age"])
    lower_values = effects[:, lower_idx] - lower_z * se[:, lower_idx]
    lower, lower_group = min(zip(lower_values, curves, strict=True))
    lower = float(lower)
    common = effects.min(axis=0)
    point = float(common.max())
    point_idx = int(np.flatnonzero(common >= point - 1e-14)[0])
    require(lower <= point + 1e-14 and point <= upper + 1e-14, "The R49 interval failed to bracket its peak")
    return dict(result, point=point, start_age=ages[point_idx], point_curve=common.tolist(), lower=lower,
                lower_start_age=ages[lower_idx], lower_attaining_group=lower_group,
                decision=decide(lower, upper, settings["gap_threshold"]))


def calibrate(settings):
    grid = layout(settings)
    ages = list(grid.ages)
    control = np.random.default_rng(49028).random((2000, 40)) < 0.12
    base = windows(control, grid).gap.mean(axis=0)
    start = ages.index(settings["primary"]["lower_start_age"])
    injected = control.copy()
    injected[:800, start:start + grid.width] = False
    errors = {g: np.zeros(len(ages)) for g in GROUPS}
    findings = {}
    for label, cases in (("matched_negative", control), ("common_gap_injected", injected)):
        curve = windows(cases, grid).gap.mean(axis=0) - base
        summary = primary_bounds({g: curve for g in GROUPS}, errors, ages, settings)
        findings[label] = {k: summary[k] for k in ("point", "start_age", "lower", "upper", "decision")}
    hit = findings["common_gap_injected"]
    require(findings["matched_negative"]["decision"] == "excluded" and findings["matched_negative"]["point"] == 0
            and hit["decision"] == "supported" and hit["start_age"] == ages[start], "R49 calibration failed")
    alpha = settings["primary"]["upper_alpha"]
    choices = settings["primary"]["upper_group_divisor"]
    findings["fixed_age_four_independent_boundary_groups"] = {
        "without_group_adjustment": 1 - (1 - alpha) ** choices,
        "with_registered_group_adjustment": 1 - (1 - alpha / choices) ** choices,
        "dependence_robust_union_bound": alpha,
    }
    return findings


def load_study(job, r10, settings):
    admitted = {g: input_receipt(job, g) for g in GROUPS}
    samples, coverage = {}, {}
    all_ids = set()
    for g, seal in admitted.items():
        if not seal["records"]:
            require(g == "mx1999", "A required sampled frame is missing")
            coverage[g] = dict(sample_n=0, eligible_frame_n=0, input_seal_sha256=seal["input_seal_sha256"])
            continue
        cohort, report = read_group(job, settings, g)
        ids = {row["source_id"] for row in cohort.rows}
        require(len(ids) == len(cohort.rows) and not (ids & all_ids), "R49 physical IDs overlap")
        all_ids.update(ids)
        samples[g], coverage[g] = cohort, report
    return load_reference(r10), samples, coverage


def estimates(reference, cohorts, settings, old_witness):
    grid = layout(settings)
    ages = list(grid.ages)
    quantile = Fraction(*settings["threshold_percentile"])
    at_least = settings["minimum_systems"]
    fixed = PrecisionReference(reference.scores, reference.weights, fractions(reference.rows))
    flags = alternate_flags(reference.scores, fixed, reference, quantile).sum(axis=2) >= at_least
    baseline = weight_means(windows(flags, grid).gap, reference.weights)
    effects, design, groups = {}, {}, {}
    for g, cohort in cohorts.items():
        joint = alternate_flags(cohort.scores, fixed, reference, quantile).sum(axis=2) >= at_least
        win = windows(joint, grid)
        residuals = win.gap - baseline
        effects[g] = weight_means(residuals, cohort.weights)
        design[g] = design_vectors(residuals, cohort.rows, np.full(len(ages), 2.))
        require(not design[g][1].any(), "Unexpected noncensused singleton stratum in R49")
        sizes = {row["stratum_id"]: (row["N_h"], row["n_h"]) for row in cohort.rows}.values()
        total_weight = sum(population for population, _ in sizes)
        squared_weights = sum(Fraction(population ** 2, sample) for population, sample in sizes)
        effective_n = float(Fraction(total_weight ** 2) / squared_weights)
        groups[g] = dict(describe(joint, win, cohort.weights), effect_curve=effects[g].tolist(), weight_effective_n=effective_n)

    critical, errors, margins = intervals(design, settings["simultaneous_bands"])
    for g in groups:
        require(g == "mx1999" or np.all(errors[g] > 0), "Unexpected zero variance in an R49 sampled group")
        groups[g].update(conditional_standard_error=errors[g].tolist(), simultaneous_margin=margins[g].tolist())
    primary = primary_bounds(effects, errors, ages, settings)
    interest = settings["gap_threshold"]
    auxiliary = {}
    if tuple(groups) == GROUPS:
        auxiliary = {
            "r46_fixed_witness": directional(effects, errors, old_witness, ages, interest),
            "r49_full_simultaneous": family_band(effects, margins, ages, interest),
        }
    return dict(age_starts=ages, fixed_reference_center=baseline.tolist(), groups=groups,
                primary=primary, auxiliary=auxiliary, simultaneous_critical=critical)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("job", "r10-job", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    settings = protocol()
    calibration = calibrate(settings)
    _, old_witness = replay(settings)
    reference, cohorts, coverage = load_study(private(args.job), args.r10_job, settings)
    findings = estimates(reference, cohorts, settings, old_witness)
    write_json(args.output, dict(registration=REGISTRATION, coverage=coverage, calibration=calibration, **findings))


if __name__ == "__main__":
    main()
