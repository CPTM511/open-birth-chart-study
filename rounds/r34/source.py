"""Retrieve and reconcile the archived Japanese date-by-hour birth counts."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile

import numpy as np

from rounds.r18.japanese_birth_hours import source_blocks
from rounds.r25.holiday_hours import load_year
from rounds.r27.archive_source import digest, read_json, require


HERE = Path(__file__).resolve().parent
CONFIG = read_json(HERE / "sources.json")
YEARS = tuple(map(int, CONFIG["years"]))


def dates_for(year):
    start = date(year, 1, 1)
    return tuple(start + timedelta(days=offset) for offset in range((date(year + 1, 1, 1) - start).days))


def fetch_verified(destination, source):
    if destination.exists():
        require(digest(destination) == source["sha256"], f"Existing file differs from the release: {destination.name}")
        return
    with NamedTemporaryFile(dir=destination.parent) as temporary:
        path = Path(temporary.name)
        subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "110",
                        "--output", str(path), source["url"]], check=True)
        require(digest(path) == source["sha256"], f"Publisher bytes differ: {destination.name}")
        destination.hardlink_to(path)


def fetch(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for year, source in CONFIG["years"].items():
        fetch_verified(directory / f"jp{year}.csv", source)


def read_counts(directory, year):
    path = directory / f"jp{year}.csv"
    source = CONFIG["years"][str(year)]
    require(digest(path) == source["sha256"], f"Mismatched {year} publisher source")
    _, audit = load_year(path, year, list(range(9, 18)))
    days = dates_for(year)
    vectors = source_blocks(path)
    counts = np.array([vectors["総数", day.month, day.day][1:] for day in days], dtype=np.int64)
    require(audit["births"] == source["publisher_table_total"] and int(counts.sum()) == audit["known"],
            f"The compiled {year} data do not match the registered source total")
    independent = read_json(HERE / "sex_margins.json")[str(year)]
    require(independent["male"] + independent["female"] == independent["publisher_total"],
            f"The independent national margins do not add up for {year}")
    quality = {
        **audit,
        "published_national_comparison_total": independent["publisher_total"],
        "table_minus_national_total": audit["births"] - independent["publisher_total"],
        "joint_date_and_hour_cells": counts.size,
        "zero_count_cells": int((counts == 0).sum()),
        "source_sha256": source["sha256"],
    }
    return counts, quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    fetch(args.directory)
    for year in YEARS:
        _, audit = read_counts(args.directory, year)
        print(f"{year}: {audit['known']} dated birth-hour counts verified")


if __name__ == "__main__":
    main()
