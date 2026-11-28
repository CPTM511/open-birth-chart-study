"""Read the frozen date-hour grid and verified donor marginals for R43."""

from __future__ import annotations

import csv
from fractions import Fraction
import gzip
import re

from rounds.r27.archive_source import ROOT, digest, read_json, require

from .donors import DESIGN, EXCLUSIONS, HERE


R41 = ROOT / "rounds/r41"
REFERENCE = ROOT / "rounds/r10/independent_replay/results/structural_comparison.json"
GRID = R41 / "minute_grid.csv.gz"
PUBLISHED = R41 / "results.json"
HOURS = range(24)
MINUTES = range(60)
AGE_PARAMETER_COUNT = 80
YEARS = tuple(str(year) for year in DESIGN["japan_years"])
THRESHOLD = Fraction(DESIGN["attention_threshold_pp"])
MASK = re.compile(r"[0-9a-f]{10}")


def load_target():
    from rounds.r41.profiles import DESIGN as target_design, study_dates

    report = read_json(PUBLISHED)
    require(report["round"] == "R41" and digest(GRID) == report["grid_sha256"], "R41 release or grid digest differs")
    for name, key in (("design.json", "design_sha256"), ("REGISTRATION.zh.md", "registration_sha256")):
        require(digest(R41 / name) == report[key], f"R41 {name} differs from its release")
    reference = Fraction(report["reference_joint_rate"]["exact"])
    frozen_reference = read_json(REFERENCE)["reference"]["joint_rate"]
    require(abs(float(reference) - frozen_reference) < 2e-13, "The Brazil 2006 reference differs from R10")
    panels = {}
    with gzip.open(GRID, "rt", encoding="ascii", newline="") as handle:
        rows = csv.reader(handle)
        header = ["date", "hour", "official_birth_count"]
        header.extend(f"minute_{minute:02}_{sex}" for minute in MINUTES for sex in ("F", "M"))
        require(next(rows) == header, "Unexpected R41 model-year grid columns")
        for year in YEARS:
            dates = study_dates(int(year))
            require(len(dates) == DESIGN["japan_date_count_per_year"], "Target dates differ from registration")
            counts, hits = [[] for _ in HOURS], [[] for _ in HOURS]
            for day in dates:
                for hour in HOURS:
                    actual, time, count, *masks = next(rows)
                    require((actual, time) == (day.isoformat(), str(hour))
                            and count.isascii() and count.isdigit(), "Unexpected date/hour/count in R41")
                    require(len(masks) == 120 and all(MASK.fullmatch(mask) for mask in masks),
                            "Invalid 40-year mask in R41")
                    popcounts = [int(mask, 16).bit_count() for mask in masks]
                    counts[hour].append(int(count))
                    hits[hour].append([a + b for a, b in zip(popcounts[::2], popcounts[1::2], strict=True)])
            published = report["years"][year]
            total = sum(map(sum, counts))
            require(total == published["cohort_birth_count"] == target_design["expected_dated_birth_counts"][year],
                    f"Total weight for {year} differs from R41")
            unrestricted = [
                Fraction(item["exact"]) for item in published["metrics"]["choice_sets"]["all_60"]
                ["unrestricted_minute_delta_to_brazil_pp_bounds"]
            ]
            panels[year] = {"dates": [day.isoformat() for day in dates], "counts": counts, "hits": hits,
                            "total": total, "unrestricted": unrestricted}
        require(next(rows, None) is None, "Excess rows in R41 model-year grid")
    return reference, panels


def load_donors(path):
    receipt = read_json(path)
    for name, key in (("design.json", "design_sha256"), ("REGISTRATION.zh.md", "registration_sha256")):
        require(digest(HERE / name) == receipt[key], f"Donor counts do not use the R43 {name}")
    require(set(receipt["donors"]) == set(DESIGN["donors"]), "Unexpected donor keys")
    for key, source in receipt["donors"].items():
        config = DESIGN["donors"][key]
        if "expected_zip_sha256" in config:
            require(source["zip_sha256"] == config["expected_zip_sha256"], f"Source digest differs for {key}")
        if "expected_zip_bytes" in config:
            require(source["zip_bytes"] == config["expected_zip_bytes"], f"Source archive size differs for {key}")
        require(re.fullmatch(r"[0-9a-f]{64}", source["zip_sha256"]), f"Invalid source digest for {key}")
        counts = source["counts"]
        require(len(counts) == len(HOURS)
                and all(len(row) == len(MINUTES) and all(type(n) is int and n >= 0 for n in row) and sum(row) > 0
                        for row in counts), f"Malformed clock counts for {key}")
        excluded = source["exclusions_in_order"]
        require(set(excluded) == set(EXCLUSIONS) and all(type(n) is int and n >= 0 for n in excluded.values())
                and source["archive_rows"] == source["valid_times"] + sum(excluded.values())
                and source["valid_times"] == sum(map(sum, counts)), f"Invalid records accounting for {key}")
        require(source["minute_zero"] == sum(row[0] for row in counts)
                and source["multiple_of_five_minutes"] == sum(sum(row[::5]) for row in counts),
                f"Invalid heaping totals for {key}")
    return {key: source["counts"] for key, source in receipt["donors"].items()}


def provenance(donors_path):
    return {
        "design_sha256": digest(HERE / "design.json"),
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "donor_counts_sha256": digest(donors_path),
        "r41_results_sha256": digest(PUBLISHED),
        "r41_grid_sha256": digest(GRID),
        "r10_reference_report_sha256": digest(REFERENCE),
    }
