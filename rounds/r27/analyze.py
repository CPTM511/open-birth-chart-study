"""Estimate the fixed-reference rate and account for whole-scan sampling."""

from __future__ import annotations

import argparse
from collections import defaultdict
from fractions import Fraction
from math import fsum, sqrt
from pathlib import Path
from statistics import variance

import numpy as np
from scipy.stats import t

from .study import R10, digest, load_target, private_job, read_json, require, write_json
from analyze_cohorts import PrecisionReference, load_profiles


def load_reference(job):
    replay = R10 / "independent_replay"
    registration = read_json(replay / "registration.json")
    for relative, expected in registration["reference_files_sha256"].items():
        require(digest(job / relative) == expected, "The fixed Brazil 2006 reference differs from R10")
    rows, _, scores, weights, _, _, _ = load_profiles(
        job / "reference/brazil2006", [job / "reference/full-frozen-r8-baseline_profiles.jsonl"]
    )
    require(len(rows) == 2000 and all(row["birth_local"].startswith("2006-") for row in rows),
            "Fixed reference cohort size or year differs")
    fractions = [Fraction(row["N_h"], row["n_h"]) for row in rows]
    return scores, weights, fractions


def frame_strata(pages, rows, person_hits):
    """Use a zero total for every sampled image without an eligible record."""
    values = {page: [0, 0] for page in pages}
    for row, count in zip(rows, person_hits, strict=True):
        totals = values[row["scan_unit"]]
        totals[0] += int(count)
        totals[1] += 40
    strata = defaultdict(list)
    for page, population_units in pages.items():
        strata[page.split("-")[0]].append((population_units, *values[page]))
    for units in strata.values():
        require(len(units) == 3 and len({unit[0] for unit in units}) == 1, "Invalid scan sampling design")
    return dict(strata)


def estimate(strata, reference_rate):
    weighted_hits = fsum(unit[0] * unit[1] / len(units) for units in strata.values() for unit in units)
    weighted_years = fsum(unit[0] * unit[2] / len(units) for units in strata.values() for unit in units)
    require(weighted_years > 0, "No eligible records in the scanned sample")
    rate = weighted_hits / weighted_years
    terms = []
    for units in strata.values():
        population = units[0][0]
        selected = len(units)
        residuals = [hits - rate * total for _, hits, total in units]
        terms.append(population ** 2 * (1 - selected / population) * variance(residuals) / selected)
    standard_error = sqrt(fsum(terms)) / weighted_years
    df = sum(len(units) - 1 for units in strata.values())
    delta = (rate - reference_rate) * 100
    margin = float(t.ppf(.975, df)) * standard_error * 100
    return {
        "joint_rate": rate,
        "delta_pp": delta,
        "joint_rate_unweighted": (sum(unit[1] for units in strata.values() for unit in units)
                                  / sum(unit[2] for units in strata.values() for unit in units)),
        "conditional_ci95_delta_pp": [delta - margin, delta + margin],
        "design_se_pp": standard_error * 100,
        "degrees_of_freedom": df,
    }


def run(job, r10_job, output):
    pages, rows, scores, scoring_receipt = load_target(job)
    reference, weights, exact_weights = load_reference(r10_job)
    calibration = PrecisionReference(reference, weights, exact_weights)
    published = read_json(R10 / "independent_replay/results/structural_comparison.json")["reference"]["joint_rate"]
    require(abs(calibration.joint_rate - published) < 2e-13, "Reference rate fails to reproduce R10")
    record_weights = np.array([pages[row["scan_unit"]] / 3 for row in rows])
    estimates = {}
    for variant, array in scores.items():
        joint = np.count_nonzero(calibration.flags(array), axis=2) >= 3
        strata = frame_strata(pages, rows, joint.sum(axis=1))
        point = estimate(strata, calibration.joint_rate)
        if variant == "base":
            point.update(
                age_band_joint_rates=[float(np.average(joint[:, age:age + 10].mean(axis=1), weights=record_weights))
                                      for age in range(0, 40, 10)],
                system_raw_means=np.average(array.mean(axis=1), weights=record_weights, axis=0).tolist(),
                unweighted_joint_years=int(joint.sum()),
                interval_excludes_0_30pp_absolute_difference=(
                    point["conditional_ci95_delta_pp"][0] >= -.30
                    and point["conditional_ci95_delta_pp"][1] <= .30
                ),
            )
        else:
            point = {"joint_rate": point["joint_rate"], "delta_to_brazil_pp": point["delta_pp"],
                     "change_from_base_pp": (point["joint_rate"] - estimates["base"]["joint_rate"]) * 100}
        estimates[variant] = point
    write_json(output, {
        "round": "R27", "reference": "Brazil 2006, frozen weighted R10 profiles",
        "reference_rate": calibration.joint_rate, "sample_records": len(rows),
        "modeled_years_per_record": 40,
        "modeled_calendar_years": [min(row["calendar_years"][0] for row in rows),
                                  max(row["calendar_years"][-1] for row in rows)],
        "systems": ["bazi", "ziwei_doushu", "qizheng_siyu", "western_astrology"],
        "input_resolution": {
            "whole_clock_hours": sum(row["birth_local"].endswith(":00:00") for row in rows),
            "different_minute_from_whole_hour": sum(not row["birth_local"].endswith(":00:00") for row in rows),
            "same_city_birth_clock_and_sex_extra_records": len(rows) - len({row["chart_input_key"] for row in rows}),
            "location": "Amsterdam city reference point",
        },
        "estimate": estimates,
        "scoring_receipt": scoring_receipt,
        "external_outcomes_used": False,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--r10-job", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(private_job(args.job), args.r10_job, args.output)
