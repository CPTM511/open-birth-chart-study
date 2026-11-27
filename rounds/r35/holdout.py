"""Run the registered holiday comparison on the frozen source table."""

from __future__ import annotations

import argparse
from datetime import date
from fractions import Fraction
from pathlib import Path

from rounds.r25.holiday_hours import (
    NAME_ALIASES, as_counts, contrast, matched_dates, mean_exact, numeric, parse_holidays,
)
from rounds.r27.archive_source import digest, read_json, require, write_json

from .freeze_counts import CALENDAR, HERE, VENUES, check_counts, load_table
from .reconcile import YEARS, source_anchors


PRIMARY_NAMES = ("海の日", "敬老の日", "体育の日", "スポーツの日")
HOURS = list(range(9, 18))
OFFSETS = [-14, -7, 7, 14]
SENSITIVITY_OFFSETS = [-7, 7]
THRESHOLD = -5
ALL = "all_venues"
CLINICAL = "hospital_and_clinic"
METRICS = ("daytime_share_difference_pp", "daytime_count_change_pct", "other_hours_count_change_pct")


def verify_frozen(directory):
    receipt = read_json(directory / "source_receipt.json")
    hashes = {
        HERE / "REGISTRATION.zh.md": "registration_sha256",
        HERE / "visual_review.json": "visual_review_sha256",
        HERE / "tesseract_reads.json": "tesseract_reads_sha256",
        HERE / "released_scan_scope.json": "released_scan_scope_sha256",
        directory / "historical_counts.csv.gz": "public_counts_sha256",
        directory / "reconciliation.json": "public_reconciliation_sha256",
    }
    for path, key in hashes.items():
        require(digest(path) == receipt[key], f"R35 frozen file has changed: {path.name}")
    tables = load_table(directory / "historical_counts.csv.gz")
    require(sorted(tables) == list(range(1993, 2000)), "Frozen data must include all seven years")
    for year, counts in tables.items():
        summary = receipt["years"][str(year)]
        venues = tuple(VENUES.index(label) for label in summary["release_venues"])
        checked, unknown = check_counts(year, counts, venues)
        require(checked == summary["reconciled_equalities_or_known_hour_bounds"]
                and unknown == summary["births_unknown_hour"]
                and counts[0, 0, 0, 0] == summary["publisher_births"]
                and len(counts) // 25 == summary["published_row_vectors"], "Release receipt differs from source totals")
        if year in YEARS:
            require(all(counts[k] == v for k, v in source_anchors(year).items()),
                    f"{year}: R34 independent annual-hour totals disagree")
    return tables, receipt


def study_days(tables):
    dates = {}
    for year, counts in tables.items():
        for place, month, day, column in counts:
            if place or not month or not day or column:
                continue
            all_births = tuple(counts[0, month, day, f] for f in range(25))
            volumes = {ALL: as_counts(all_births, HOURS)}
            if (1, month, day, 0) in counts and (2, month, day, 0) in counts:
                clinics = tuple(counts[1, month, day, f] + counts[2, month, day, f] for f in range(25))
                require(all(0 <= v <= w for v, w in zip(clinics, all_births, strict=True)),
                        f"Clinical subset exceeds the national count on {year}-{month}-{day}")
                volumes[CLINICAL] = as_counts(clinics, HOURS)
            dates[date(year, month, day)] = volumes
    return dates


def comparison(target, holidays, dates, offsets):
    controls = matched_dates(target, holidays, dates, offsets)
    if not controls:
        return None
    result = {"controls": [day.isoformat() for day in controls]}
    for scope in (ALL, CLINICAL):
        if all(scope in dates[d] for d in (target, *controls)):
            controls_in_scope = [dates[d][scope] for d in controls]
            result[scope] = contrast(dates[target][scope], controls_in_scope)
            result[scope]["control_counts"] = {
                d.isoformat(): counts.as_dict() for d, counts in zip(controls, controls_in_scope, strict=True)
            }
    return result


def summarize_comparisons(rows, design, scope):
    supported = [row[design][scope] for row in rows if row[design] is not None and scope in row[design]]
    result = {"matched_holidays": len(supported)}
    for field in METRICS:
        result[field] = mean_exact(row[field] for row in supported) if supported else None
    result["target_counts"] = {field: sum(row["target_counts"][field] for row in supported)
                               for field in ("births", "known", "daytime", "other_known_hours", "unknown")}
    result["control_date_occurrences"] = sum(len(row["control_counts"]) for row in supported)
    result["control_counts_by_occurrence"] = {
        field: sum(counts[field] for row in supported for counts in row["control_counts"].values())
        for field in result["target_counts"]
    }
    return result


def summarize_study(cases):
    main_scope = summarize_comparisons(cases, "main", ALL)
    clinical_cases = [row for row in cases if row["main"] and CLINICAL in row["main"]]
    return {
        "candidate_holidays": len(cases),
        "national": main_scope,
        "national_adjacent_week": summarize_comparisons(cases, "adjacent_week", ALL),
        "clinic_and_hospital": summarize_comparisons(clinical_cases, "main", CLINICAL),
        "national_same_pairs_as_clinic_and_hospital": summarize_comparisons(clinical_cases, "main", ALL),
        "national_by_year": {
            str(y): summarize_comparisons([row for row in cases if row["date"][:4] == str(y)], "main", ALL)
            for y in sorted({int(row["date"][:4]) for row in cases})
        },
        "national_by_holiday": {
            label: summarize_comparisons([row for row in cases if row["holiday"] == label], "main", ALL)
            for label in sorted({row["holiday"] for row in cases})
        },
    }


def calculate(tables, holidays):
    dates = study_days(tables)
    cases = []
    for day, official in sorted(holidays.items()):
        label = NAME_ALIASES.get(official, official)
        if day.year not in tables or day.weekday() >= 5 or label not in PRIMARY_NAMES:
            continue
        cases.append({
            "date": day.isoformat(), "holiday": label, "publisher_holiday_label": official,
            "is_monday": day.weekday() == 0,
            "main": comparison(day, holidays, dates, OFFSETS) if day in dates else None,
            "adjacent_week": comparison(day, holidays, dates, SENSITIVITY_OFFSETS) if day in dates else None,
        })
    mondays = [row for row in cases if row["is_monday"]]
    primary = summarize_study(mondays)
    n_matched = primary["national"]["matched_holidays"]
    require(tuple(row["date"] for row in mondays) == ("1994-10-10", "1997-09-15", "1998-07-20"),
            "Registered Monday candidate set changed")
    if n_matched < len(mondays):
        threshold_status = "incomplete_calendar_support"
    elif primary["national"]["daytime_share_difference_pp"] <= THRESHOLD:
        threshold_status = "met"
    else:
        threshold_status = "not_met"
    return {
        "primary_mondays": {**primary, "practical_threshold_pp": THRESHOLD, "threshold_status": threshold_status},
        "secondary_all_weekdays": summarize_study(cases),
        "weekday_holiday_cases": cases,
    }


def json_ready(value):
    if isinstance(value, Fraction):
        return numeric(value)
    if isinstance(value, list):
        return [json_ready(x) for x in value]
    if isinstance(value, dict):
        return {key: json_ready(x) for key, x in value.items()}
    return value


def analyze(directory, calendar, output):
    tables, receipt = verify_frozen(directory)
    require(receipt["official_holiday_csv"] == CALENDAR and digest(calendar) == CALENDAR["sha256"],
            "The calendar differs from the preregistration")
    holidays = parse_holidays(calendar)
    result = calculate(tables, holidays)
    result["registration_sha256"] = receipt["registration_sha256"]
    result["source_receipt_sha256"] = digest(directory / "source_receipt.json")
    result["source_years"] = sorted(tables)
    result["source_births"] = sum(item["publisher_births"] for item in receipt["years"].values())
    result["source_births_unknown_hour"] = sum(item["births_unknown_hour"] for item in receipt["years"].values())
    write_json(output, json_ready(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "calendar", "output"):
        parser.add_argument(name, type=Path)
    analyze(**vars(parser.parse_args()))


if __name__ == "__main__":
    main()
