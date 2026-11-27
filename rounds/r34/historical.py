"""Retrieve historical e-Stat birth-hour sources and audit the digital editions."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from rounds.r18.japanese_birth_hours import VENUES, clean
from rounds.r25.holiday_hours import load_year
from rounds.r27.archive_source import require, write_json
from .source import HERE, fetch_verified, read_json


HISTORICAL = read_json(HERE / "historical_sources.json")
MONTH = r"(?:総数|[0-9]+月)"
GROUP_MARKER = re.compile(r"(?:" + "|".join(VENUES) + r")[;:*]" + MONTH)


def clean_headings(path, output):
    """Adapt old venue/month separators to the schema audited by R25."""
    with path.open(encoding="cp932", newline="") as src, output.open("w", encoding="cp932", newline="") as out:
        writer = csv.writer(out)
        for row in csv.reader(src):
            if not any(row):
                continue
            label = clean(row[0])
            if not any(row[1:]) and GROUP_MARKER.fullmatch(label):
                writer.writerow([label.replace(";", "*").replace(":", "*")])
            elif len(row) > 1 and label in VENUES and re.fullmatch(MONTH, clean(row[1])) and not any(row[2:]):
                writer.writerow([f"{label}*{clean(row[1])}"])
            else:
                writer.writerow(row)


def verify_history(directory, include_scans):
    directory.mkdir(parents=True, exist_ok=True)
    scan_totals = read_json(HERE / "historical_annual_hours.json")
    for year, summary in scan_totals.items():
        hours = summary["hours_00_through_23"]
        require(summary["file"] in HISTORICAL["scanned_publisher_files"]
                and len(hours) == 24 and sum(hours) == summary["publisher_total"],
                f"Transcribed {year} annual hours do not reconcile")
    results = {}
    if include_scans:
        for file, info in HISTORICAL["scanned_publisher_files"].items():
            fetch_verified(directory / file, info)
            with (directory / file).open("rb") as stream:
                require(stream.read(5) == b"%PDF-", f"{file} is missing the publisher PDF header")
    with TemporaryDirectory() as converted:
        for year, item in HISTORICAL["digital_tables"].items():
            path = directory / f"jp{year}.csv"
            fetch_verified(path, item)
            normalized = Path(converted) / path.name
            clean_headings(path, normalized)
            _, coverage = load_year(normalized, int(year), list(range(9, 18)))
            require(coverage["births"] == item["births"], f"Historical {year} counts differ")
            results[year] = coverage
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--include-scans", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    write_json(args.output, verify_history(args.directory, args.include_scans))


if __name__ == "__main__":
    main()
