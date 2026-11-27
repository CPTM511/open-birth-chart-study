"""Classify the R41 standard inputs and compute conditional minute bounds."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from fractions import Fraction
import gzip
import io
from pathlib import Path

import numpy as np

from rounds.r27.analyze import PrecisionReference, load_reference
from rounds.r27.archive_source import digest, read_json, require, write_json
from rounds.r27.verify import weighted_rank_tables
from rounds.r29.compare import integer_flags
from rounds.r34.source import dates_for, read_counts

from .profiles import DESIGN, HERE, MINUTES, R10, R34, SEXES, YEARS, load_scores, score_path, scoring_keys, study_dates


THRESHOLD_PP = Fraction(DESIGN["minimum_pp"])
ANCHORS = tuple(DESIGN["r34_anchor_minutes"])
AGE_BANDS = ("joint_20_29", "joint_30_39", "joint_40_49", "joint_50_59")
CSV_HEADER = ["date", "hour", "official_birth_count", *(f"minute_{minute:02d}_{sex}" for minute in MINUTES for sex in SEXES)]


def dot_rate(weights, values, denominator):
    return Fraction(int(np.sum(weights * values, dtype=np.int64)), int(denominator))


def envelope(values, coefficients, denominator):
    low, high = values.min(axis=-1), values.max(axis=-1)
    lower_choice = np.where(coefficients >= 0, low, high)
    upper_choice = np.where(coefficients >= 0, high, low)
    return [dot_rate(coefficients, selected, denominator) for selected in (lower_choice, upper_choice)]


def percentage_points(values, reference=Fraction()):
    return [100 * (value - reference) for value in values]


def thresholds(bounds):
    return {
        "can_include_zero": bounds[0] <= 0 <= bounds[1],
        "can_reach_negative_attention_threshold": bounds[0] <= -THRESHOLD_PP,
        "can_reach_positive_attention_threshold": bounds[1] >= THRESHOLD_PP,
        "always_at_or_above_positive_attention_threshold": bounds[0] >= THRESHOLD_PP,
    }


def panel_metrics(counts, masks, baseline):
    require(masks.shape == (*counts.shape, len(MINUTES), len(SEXES)), "Incomplete minute mask dimensions")
    n = int(counts.sum())
    require(n > 0, "The selected dates have no official counts")
    counts = counts.astype(np.int64)
    day_totals = counts.sum(axis=1)
    hour_totals = counts.sum(axis=0)
    signed = n * counts - day_totals[:, None] * hour_totals[None, :]
    require(signed.sum() == 0, "Signed date/hour coefficients do not conserve mass")

    individual = np.bitwise_count(masks)
    paired = individual.sum(axis=-1, dtype=np.int64)
    choices = {}
    fixed_rates = [dot_rate(counts, paired[..., minute], 80 * n) for minute in MINUTES]
    fixed_linkage = percentage_points(
        [dot_rate(signed, paired[..., minute], 80 * n**2) for minute in MINUTES]
    )
    for key, minutes in (("r34_three", ANCHORS), ("all_60", tuple(MINUTES))):
        values = np.take(paired, minutes, axis=-1)
        a_bounds = envelope(values, counts, 80 * n)
        difference_bounds = percentage_points(a_bounds, baseline)
        linkage_bounds = percentage_points(envelope(values, signed, 80 * n**2))
        option_rates = [fixed_rates[minute] for minute in minutes]
        selected = np.take(masks, minutes, axis=2)
        can_change = np.bitwise_or.reduce(selected, axis=2) ^ np.bitwise_and.reduce(selected, axis=2)
        choices[key] = {
            "minutes": list(minutes),
            "fixed_minute_A_rate_bounds": [min(option_rates), max(option_rates)],
            "fixed_minute_delta_to_brazil_pp_bounds": percentage_points([min(option_rates), max(option_rates)], baseline),
            "fixed_minutes_at_or_above_positive_attention_threshold": sum(
                value >= baseline + THRESHOLD_PP / 100 for value in option_rates
            ),
            "fixed_minutes_at_or_below_negative_attention_threshold": sum(
                value <= baseline - THRESHOLD_PP / 100 for value in option_rates
            ),
            "unrestricted_minute_A_rate_bounds": a_bounds,
            "unrestricted_minute_delta_to_brazil_pp_bounds": difference_bounds,
            "unrestricted_minute_delta_to_brazil_thresholds": thresholds(difference_bounds),
            "unrestricted_minute_A_minus_B_pp_bounds": linkage_bounds,
            "unrestricted_minute_A_minus_B_thresholds": thresholds(linkage_bounds),
            "synthetic_person_years_with_a_minute_flip_rate": dot_rate(
                counts, np.bitwise_count(can_change).sum(axis=-1), 80 * n
            ),
            "unrestricted_minute_and_parameter_A_rate_bounds": envelope(
                np.take(individual, minutes, axis=2).reshape(*counts.shape, -1), counts, 40 * n
            ),
        }

    narrow = choices["r34_three"]
    wide = choices["all_60"]
    expansions = {}
    for key in ("unrestricted_minute_delta_to_brazil_pp_bounds", "unrestricted_minute_A_minus_B_pp_bounds"):
        old_lo, old_hi = narrow[key]
        new_lo, new_hi = wide[key]
        require(new_lo <= old_lo <= old_hi <= new_hi, "A larger set of allowable minutes narrowed a bound")
        expansions[key] = [old_lo - new_lo, new_hi - old_hi]
    return {
        "fixed_minute_A_rates": fixed_rates,
        "fixed_minute_A_minus_B_pp": fixed_linkage,
        "uniform_minute_A_rate": sum(fixed_rates) / len(fixed_rates),
        "uniform_minute_A_minus_B_pp": sum(fixed_linkage) / len(fixed_linkage),
        "uniform_minute_delta_to_brazil_pp": 100 * (sum(fixed_rates) / len(fixed_rates) - baseline),
        "choice_sets": choices,
        "bounds_expansion_at_lower_and_upper_pp": expansions,
    }


def serialize(value):
    if isinstance(value, Fraction):
        return {"value": float(value), "exact": str(value)}
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serialize(item) for item in value]
    return value


def classify_reference(directory):
    scores, floats, weights = load_reference(directory)
    calibrator = PrecisionReference(scores, floats, weights)
    tables = weighted_rank_tables(scores, weights)
    independent = integer_flags(scores, tables)
    require(np.array_equal(calibrator.flags(scores), independent), "Two reference high-flag methods differ")
    hits = np.count_nonzero(independent, axis=-1) >= 3
    exact_rate = sum(weight * int(row.sum()) for weight, row in zip(weights, hits, strict=True)) / (40 * sum(weights))
    published = read_json(R10 / "independent_replay/results/structural_comparison.json")["reference"]["joint_rate"]
    require(abs(float(exact_rate) - published) < 2e-13, "Rebuilt birth-cohort reference differs from R10")
    return calibrator, tables, exact_rate


def official_counts(first, second, year):
    counts, metadata = read_counts(first, year)
    other, other_metadata = read_counts(second, year)
    require(metadata == other_metadata and np.array_equal(counts, other), f"Raw archives differ for {year}")
    indices = [(day - date(year, 1, 1)).days for day in study_dates(year)]
    panel = counts[indices, :]
    require(int(panel.sum()) == DESIGN["expected_dated_birth_counts"][str(year)], "Registered date counts differ")
    return panel, metadata


def r34_anchors():
    selected = {day for year in YEARS for day in study_dates(year)}
    baseline = {}
    with gzip.open(R34 / "model_year_grid.csv.gz", "rt", encoding="ascii", newline="") as stream:
        for row in csv.DictReader(stream):
            day = date.fromisoformat(row["date"])
            if day in selected and row["variant"] in {f"tokyo_{minute:02d}" for minute in ANCHORS}:
                minute = int(row["variant"].split("_")[1])
                key = day, int(row["hour"]), minute, SEXES.index(row["parameter"])
                require(key not in baseline, "Duplicate Tokyo R34 anchor")
                baseline[key] = tuple(int(row[band]) for band in AGE_BANDS)
    require(len(baseline) == len(selected) * 24 * len(ANCHORS) * len(SEXES), "Incomplete Tokyo R34 anchors")
    return baseline


def compute_year(year, main_dir, probe_dir, calibration, tables, anchors):
    receipts = {}
    differences = []
    day_masks = []
    verified = {"profiles": 0, "score_count": 0, "anchor_count": 0, "probe_count": 0}
    for day in study_dates(year):
        scores = load_scores(main_dir, day)
        keys = scoring_keys(day)
        probe = load_scores(probe_dir, day, probe=True)
        index = {key: position for position, key in enumerate(keys)}
        verify_indices = [index[key] for key in scoring_keys(day, probe=True)]
        require(np.array_equal(scores[verify_indices], probe), f"The independent minute probe differs for {day}")
        verified["probe_count"] += len(probe)
        flags = calibration.flags(scores)
        require(np.array_equal(flags, integer_flags(scores, tables)), f"Two high-flag methods differ for {day}")
        joint = flags.sum(axis=-1) >= 3
        verified["profiles"] += len(scores)
        verified["score_count"] += scores.size
        for key in keys:
            hour, minute, sex = key
            if minute in ANCHORS:
                matching = tuple(joint[index[key]].reshape(4, 10).sum(axis=1).tolist())
                legacy = anchors[day, hour, minute, sex]
                if matching != legacy:
                    differences.append({"date": day.isoformat(), "hour": hour, "minute": minute,
                                        "parameter": SEXES[sex], "r34_band_counts": list(legacy),
                                        "r41_band_counts": list(matching)})
                verified["anchor_count"] += 1
        age_bits = np.left_shift(np.uint64(1), np.arange(40, dtype=np.uint64))
        day_masks.append((joint * age_bits).sum(axis=-1, dtype=np.uint64).reshape(24, len(MINUTES), len(SEXES)))
        receipts[day.isoformat()] = {"grid_sha256": digest(score_path(main_dir, day)),
                                    "probe_sha256": digest(score_path(probe_dir, day))}
    return np.stack(day_masks), {"verification_counts": verified, "r34_anchor_differences": differences,
                                 "daily_receipts": receipts}


def write_grid(path, panels):
    with path.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with io.TextIOWrapper(zipped, encoding="ascii", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(CSV_HEADER)
            for year in YEARS:
                counts, masks = panels[year]
                for row, day in enumerate(study_dates(year)):
                    for hour in range(24):
                        writer.writerow([day.isoformat(), hour, int(counts[row, hour]),
                                         *(f"{int(mask):010x}" for mask in masks[row, hour].ravel())])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-first", type=Path, required=True)
    parser.add_argument("--source-second", type=Path, required=True)
    parser.add_argument("--scoring-root", type=Path, required=True)
    parser.add_argument("--reference-job", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    args = parser.parse_args()

    calibrator, tables, baseline = classify_reference(args.reference_job)
    anchors = r34_anchors()
    report = {
        "round": "R41",
        "reference_joint_rate": serialize(baseline),
        "design_sha256": digest(HERE / "design.json"),
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "r34_grid_sha256": digest(R34 / "model_year_grid.csv.gz"),
        "years": {},
    }
    panels = {}
    for year in YEARS:
        counts, metadata = official_counts(args.source_first, args.source_second, year)
        masks, verification = compute_year(year, args.scoring_root / f"main-{year}",
                                           args.scoring_root / f"probe-{year}", calibrator, tables, anchors)
        panels[year] = counts, masks
        report["years"][str(year)] = {
            "entire_year_source": metadata, "cohort_date_count": len(study_dates(year)),
            "cohort_birth_count": int(counts.sum()), "metrics": serialize(panel_metrics(counts, masks, baseline)),
            **verification,
        }
    require(sum(result["verification_counts"]["profiles"] for result in report["years"].values())
            == DESIGN["expected_complete_profiles"], "Total profile count differs from the registered grid")
    write_grid(args.grid, panels)
    report["grid_sha256"] = digest(args.grid)
    write_json(args.output, report)


if __name__ == "__main__":
    main()
