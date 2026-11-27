"""Check the published aggregate calculation using the model grid and source files."""

from __future__ import annotations

import argparse
import csv
from datetime import date
import gzip
from pathlib import Path

import numpy as np

from rounds.r27.archive_source import read_json, require
from .analyze import SYSTEMS, analyze_rates
from .profiles import SEXES, VARIANTS, keys_for, sensitivity_dates
from .source import HERE, YEARS, dates_for, digest, read_counts


def check_release(source, result, archive):
    report = read_json(result)
    require(report["profile_grid_sha256"] == digest(archive), "Released model grid checksum differs")
    require(report["source_definition_sha256"] == digest(HERE / "sources.json")
            and report["registration_sha256"] == digest(HERE / "REGISTRATION.zh.md")
            and report["sex_margins_sha256"] == digest(HERE / "sex_margins.json"), "Release inputs have drifted")
    grids = {year: np.full((len(VARIANTS), len(dates_for(year)), 24, len(SEXES), 8), -1, dtype=np.int16)
             for year in YEARS}
    declared = {year: {key for month in range(1, 13) for key in keys_for(year, month)} for year in YEARS}
    with gzip.open(archive, "rt", encoding="ascii", newline="") as stream:
        reader = csv.reader(stream)
        require(next(reader) == ["date", "hour", "variant", "parameter", "joint_20_29", "joint_30_39",
                                 "joint_40_49", "joint_50_59", *SYSTEMS], "Model grid column order changed")
        for instant, hour, scenario, group, *values in reader:
            day = date.fromisoformat(instant)
            index = (day - date(day.year, 1, 1)).days
            key = index, VARIANTS.index(scenario), int(hour), SEXES.index(group)
            require(day.year in declared and key in declared[day.year], "Unexpected or duplicate standard input")
            declared[day.year].remove(key)
            counts = list(map(int, values))
            require(len(counts) == 8 and all(0 <= v <= cap for v, cap in zip(counts, [10] * 4 + [40] * 4, strict=True)),
                    "A model-year count lies outside the registered range")
            index, variant, hour, sex = key
            grids[day.year][variant, index, hour, sex] = counts
    margins = read_json(HERE / "sex_margins.json")
    for year, grid in grids.items():
        require(not declared[year], "The released grid has missing inputs")
        selected = sensitivity_dates(year)
        days = dates_for(year)
        sensitivity = np.array([day in selected for day in days])
        counts, observed = read_counts(source, year)
        expected = report["years"][str(year)]
        require(expected["source"] == observed, f"The source count receipt for {year} differs")
        replayed = analyze_rates(counts, grid, days, sensitivity, report["reference"]["joint_rate"], margins[str(year)])
        require(all(expected[key] == value for key, value in replayed.items()),
                f"One or more aggregate rates differ for {year}")
        print(f"{year}: released model grid and all aggregate comparisons agree")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--result", type=Path, default=HERE / "results.json")
    parser.add_argument("--grid", type=Path, default=HERE / "model_year_grid.csv.gz")
    args = parser.parse_args()
    check_release(args.source, args.result, args.grid)


if __name__ == "__main__":
    main()
