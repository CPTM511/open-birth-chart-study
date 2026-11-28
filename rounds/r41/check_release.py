"""Recompute R41's released bounds from its joint masks and publisher counts."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from fractions import Fraction
import gzip
from pathlib import Path
import re

from rounds.r27.archive_source import digest, read_json, require
from rounds.r34.source import read_counts

from .profiles import DESIGN, HERE, MINUTES, R10, R34, SEXES, YEARS, study_dates


def exact(value):
    return Fraction(value["exact"])


def check_rate(expected, actual, label):
    require(actual == exact(expected) and float(actual) == expected["value"], f"Exact calculation differs: {label}")


def compressed_panel(stream, year, source):
    official, receipt = read_counts(source, year)
    for day in study_dates(year):
        row = (day - date(year, 1, 1)).days
        for hour in range(24):
            raw = next(stream)
            count = int(official[row, hour])
            require(raw[:3] == [day.isoformat(), str(hour), str(count)], f"Grid key/count differs for {day} {hour}")
            masks = raw[3:]
            require(len(masks) == 2 * len(MINUTES) and all(re.fullmatch("[0-9a-f]{10}", mask) for mask in masks),
                    f"Invalid age mask row for {day} {hour}")
            numbers = tuple(int(mask, 16) for mask in masks)
            yield day, hour, count, tuple(zip(numbers[::2], numbers[1::2], strict=True))
    require(int(official.sum()) == receipt["known"], "Official year total changed")


def evaluate_year(cells, results, baseline):
    n = sum(count for _, _, count, _ in cells)
    require(n == results["cohort_birth_count"], "Grid and report use different birth counts")
    daily = {day: sum(count for key, _, count, _ in cells if key == day) for day, _, _, _ in cells}
    hourly = {hour: sum(count for _, key, count, _ in cells if key == hour) for hour in range(24)}
    values = [
        (
            Fraction(count, n),
            Fraction(daily[day], n) * Fraction(hourly[hour], n),
            minutes,
            [tuple(mask.bit_count() for mask in pair) for pair in minutes],
        )
        for day, hour, count, minutes in cells
    ]

    published = results["metrics"]
    fixed_a = []
    fixed_difference = []
    for minute in MINUTES:
        a = sum(weight * sum(hits[minute]) / 80 for weight, _, _, hits in values)
        b = sum(weight * sum(hits[minute]) / 80 for _, weight, _, hits in values)
        check_rate(published["fixed_minute_A_rates"][minute], a, f"fixed-minute A {minute}")
        check_rate(published["fixed_minute_A_minus_B_pp"][minute], 100 * (a - b), f"fixed-minute A-B {minute}")
        fixed_a.append(a)
        fixed_difference.append(100 * (a - b))
    uniform = sum(fixed_a) / 60
    check_rate(published["uniform_minute_A_rate"], uniform, "uniform-minute A")
    check_rate(published["uniform_minute_A_minus_B_pp"], sum(fixed_difference) / 60, "uniform-minute A-B")
    check_rate(published["uniform_minute_delta_to_brazil_pp"], 100 * (uniform - baseline), "uniform-minute A vs Brazil")
    threshold = Fraction(DESIGN["minimum_pp"])
    recomputed = {}
    for key, minutes in (("r34_three", DESIGN["r34_anchor_minutes"]), ("all_60", list(MINUTES))):
        subset = published["choice_sets"][key]
        require(subset["minutes"] == minutes, "The allowed minutes differ from the registered choice set")
        unpaired, fixed_pairs, contrasts = [Fraction(), Fraction()], [Fraction(), Fraction()], [Fraction(), Fraction()]
        flips = Fraction()
        for actual, margin, raw, hits in values:
            paired_rates = [Fraction(sum(hits[minute]), 80) for minute in minutes]
            rates_by_parameter = [Fraction(hit, 40) for minute in minutes for hit in hits[minute]]
            for index, finish in enumerate((min, max)):
                fixed_pairs[index] += finish(actual * rate for rate in paired_rates)
                contrasts[index] += finish((actual - margin) * rate for rate in paired_rates)
                unpaired[index] += finish(actual * rate for rate in rates_by_parameter)
            varying = sum(
                len({(raw[minute][sex] >> age) & 1 for minute in minutes}) == 2
                for sex in range(len(SEXES)) for age in range(40)
            )
            flips += actual * Fraction(varying, 80)
        global_rates = [fixed_a[minute] for minute in minutes]
        relative = [100 * (value - baseline) for value in fixed_pairs]
        linkage = [100 * value for value in contrasts]
        for name, pair in (
            ("fixed_minute_A_rate_bounds", [min(global_rates), max(global_rates)]),
            ("fixed_minute_delta_to_brazil_pp_bounds", [100 * (e - baseline) for e in (min(global_rates), max(global_rates))]),
            ("unrestricted_minute_A_rate_bounds", fixed_pairs),
            ("unrestricted_minute_delta_to_brazil_pp_bounds", relative),
            ("unrestricted_minute_A_minus_B_pp_bounds", linkage),
            ("unrestricted_minute_and_parameter_A_rate_bounds", unpaired),
        ):
            for output, actual in zip(subset[name], pair, strict=True):
                check_rate(output, actual, f"{key} {name}")
        check_rate(subset["synthetic_person_years_with_a_minute_flip_rate"], flips, f"{key} flip rate")
        require(subset["fixed_minutes_at_or_above_positive_attention_threshold"] ==
                sum(100 * (output - baseline) >= threshold for output in global_rates), f"{key} positive threshold")
        require(subset["fixed_minutes_at_or_below_negative_attention_threshold"] ==
                sum(100 * (output - baseline) <= -threshold for output in global_rates), f"{key} negative threshold")
        for name, (lo, hi) in (("unrestricted_minute_A_minus_B", linkage),
                                ("unrestricted_minute_delta_to_brazil", relative)):
            expected = {
                "can_include_zero": lo <= 0 <= hi,
                "can_reach_negative_attention_threshold": lo <= -threshold,
                "can_reach_positive_attention_threshold": hi >= threshold,
                "always_at_or_above_positive_attention_threshold": lo >= threshold,
            }
            require(subset[f"{name}_thresholds"] == expected, f"{key} decisions at the attention threshold")
        recomputed[key] = relative, linkage

    for index, name in enumerate(("unrestricted_minute_delta_to_brazil_pp_bounds",
                                  "unrestricted_minute_A_minus_B_pp_bounds")):
        old_min, old_max = recomputed["r34_three"][index]
        new_min, new_max = recomputed["all_60"][index]
        calculated = [old_min - new_min, new_max - old_max]
        for output, actual in zip(published["bounds_expansion_at_lower_and_upper_pp"][name], calculated, strict=True):
            check_rate(output, actual, f"bound expansion {name}")


def check_release(source, report_path, grid_path):
    report = read_json(report_path)
    require(digest(grid_path) == report["grid_sha256"], "Released model-year grid digest differs")
    for path, key in (
        (HERE / "design.json", "design_sha256"), (HERE / "REGISTRATION.zh.md", "registration_sha256"),
        (R34 / "model_year_grid.csv.gz", "r34_grid_sha256"),
    ):
        require(digest(path) == report[key], f"{path.name} differs from the released source")
    baseline = exact(report["reference_joint_rate"])
    published = read_json(R10 / "independent_replay/results/structural_comparison.json")["reference"]["joint_rate"]
    require(abs(float(baseline) - published) < 2e-13, "Released reference rate differs from R10")
    with gzip.open(grid_path, "rt", encoding="ascii", newline="") as stream:
        rows = csv.reader(stream)
        expected_header = ["date", "hour", "official_birth_count"]
        expected_header.extend(f"minute_{minute:02d}_{sex}" for minute in MINUTES for sex in SEXES)
        require(next(rows) == expected_header, "The released model-year grid has unexpected columns")
        for year in YEARS:
            cells = list(compressed_panel(rows, year, source))
            expected = report["years"][str(year)]
            dates = study_dates(year)
            require(len(cells) == expected["cohort_date_count"] * 24, "Released date or hour coverage differs")
            profiles = len(cells) * 60 * len(SEXES)
            require(expected["verification_counts"] == {
                "profiles": profiles, "score_count": profiles * 40 * 4,
                "anchor_count": len(cells) * len(DESIGN["r34_anchor_minutes"]) * len(SEXES),
                "probe_count": len(dates) * len(DESIGN["probe_minutes"]) * len(SEXES),
            }, f"Release verification counts differ for {year}")
            check = expected["first_date_ziwei_reuse_check"]
            require(check["date"] == dates[0].isoformat() and check["complete_profiles"] == 2880
                    and check["same_numeric_scores"] == 460800, f"First-date reuse check differs for {year}")
            require(set(expected["daily_receipts"]) == {day.isoformat() for day in dates},
                    f"Missing a daily score receipt for {year}")
            evaluate_year(cells, expected, baseline)
        require(next(rows, None) is None, "The released model-year grid contains unexpected rows")
    print("Both years and all recorded boundaries reproduce with an independent exact weighting calculation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--result", type=Path, default=HERE / "results.json")
    parser.add_argument("--grid", type=Path, default=HERE / "minute_grid.csv.gz")
    args = parser.parse_args()
    check_release(args.source, args.result, args.grid)
