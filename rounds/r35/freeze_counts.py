"""Freeze the audited e-Stat aggregate table, before examining holiday contrasts."""

from __future__ import annotations

import argparse
import csv
import gzip
from io import TextIOWrapper
from pathlib import Path
from tempfile import TemporaryDirectory

from rounds.r18.japanese_birth_hours import VENUES, source_blocks
from rounds.r25.holiday_hours import verify_source_year
from rounds.r27.archive_source import digest, read_json, require, write_json
from rounds.r34.historical import HISTORICAL, clean_headings

from .reconcile import HERE, YEARS, accounting, source_slots, summarize


DIGITAL_YEARS = tuple(range(1996, 2000))
DIGITAL = {int(y): item for y, item in HISTORICAL["digital_tables"].items()}
R34_BASE = HERE.parent / "r34"
R34_1999 = read_json(R34_BASE / "sources.json")["years"]["1999"]
DIGITAL[1999] = {**R34_1999, "births": R34_1999["publisher_table_total"]}
CALENDAR = {
    "url": "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv",
    "sha256": "cec37a743c96995cdb9cb52b685c9003634682a9b0e1a640a6b9b96881fe964a",
}
ALL_PLACES = tuple(range(len(VENUES)))
COUNT_FIELDS = ("total", *(f"h{h:02}" for h in range(24)))
HEADER = ("year", "venue", "month", "day", *COUNT_FIELDS)


def check_counts(year, numbers, places):
    require(set(numbers) == source_slots(year, places), f"{year}: unstable date or venue support")
    require(all(type(n) is int and n >= 0 for n in numbers.values()), f"{year}: missing or invalid count")
    checks = 0
    unknown = 0
    for eq in accounting(year, places):
        delta = numbers[eq.total] - sum(numbers[key] for key in eq.parts)
        if eq.family == "hours" and year in DIGITAL_YEARS:
            require(delta >= 0, f"{year}: more known hours than births at {eq.total}")
            if eq.total[0] == 0 and eq.total[1] > 0 and eq.total[2] > 0:
                unknown += delta
        else:
            require(delta == 0, f"{year}: unmatched {eq.family} sum at {eq.total}")
        checks += 1
    require(unknown == numbers[0, 0, 0, 0] - sum(numbers[0, 0, 0, h] for h in range(1, 25)),
            f"{year}: inconsistent national unknown-hour count")
    if 1 < len(places) < len(ALL_PLACES):
        for p, month, day, field in numbers:
            if p == 0:
                require(sum(numbers[v, month, day, field] for v in places if v != 0)
                        <= numbers[0, month, day, field],
                        f"{year}: the included venues exceed the national count at {month}/{day}, column {field}")
                checks += 1
    return checks, unknown


def read_digital(source, year):
    require(digest(source) == DIGITAL[year]["sha256"], f"{year}: publisher digest changed")
    with TemporaryDirectory() as converted:
        path = Path(converted) / source.name
        if year < 1999:
            clean_headings(source, path)
        else:
            path = source
        verify_source_year(path, year)
        table = source_blocks(path)
    require(table[VENUES[0], 0, 0][0] == DIGITAL[year]["births"], f"{year}: publisher total changed")
    expected = source_slots(year, ALL_PLACES)
    numbers = {}
    for (v, m, d), row in table.items():
        place = VENUES.index(v)
        for field, n in enumerate(row):
            key = place, m, d, field
            if key in expected:
                numbers[key] = n
            else:
                require(n == 0, f"{year}: invalid calendar date has a published count")
    return numbers


def write_table(path, tables):
    with path.open("xb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped:
        with TextIOWrapper(zipped, encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(HEADER)
            for year, numbers in sorted(tables.items()):
                for place, month, day, k in sorted(numbers):
                    if k == 0:
                        writer.writerow((year, VENUES[place], month, day,
                                         *(numbers[place, month, day, f] for f in range(25))))


def load_table(path):
    by_year = {}
    with gzip.open(path, mode="rt", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        require(tuple(next(reader)) == HEADER, "Wrong date/hour fields or order")
        seen = set()
        for row in reader:
            require(len(row) == len(HEADER), "The public table has a truncated row")
            yr, venue, m, d, *counts = row
            year, month, day = int(yr), int(m), int(d)
            require(year in (*YEARS, *DIGITAL_YEARS) and venue in VENUES, "Unexpected year or venue")
            key = (year, VENUES.index(venue), month, day)
            require(key not in seen, "The public table repeats a row")
            seen.add(key)
            numbers = by_year.setdefault(year, {})
            for field, n in enumerate(counts):
                require(n.isascii() and n.isdigit(), "The public table contains a non-integer count")
                numbers[(*key[1:], field)] = int(n)
    return by_year


def assemble(archive, csv1999, pages, contacts, crops, calendar, scope, destination):
    scans = HISTORICAL["scanned_publisher_files"]
    for name, item in scans.items():
        require(digest(archive / name) == item["sha256"], f"PDF source digest changed: {name}")
    require(digest(calendar) == CALENDAR["sha256"], "The calendar differs from the registered vintage")
    tables, reports, year_receipts = {}, {}, {}
    coverage = read_json(scope)
    frozen_tesseract_path = HERE / "tesseract_reads.json"
    frozen_tesseract = read_json(frozen_tesseract_path)
    require(all(isinstance(v, str) and v.isascii() and v.isdigit() for v in frozen_tesseract.values()),
            "A frozen Tesseract reading is invalid")
    require(set(map(int, coverage)) == set(YEARS), "Record scope for all three scanned source years")
    for year in (*YEARS, *DIGITAL_YEARS):
        if year in YEARS:
            places = coverage[str(year)]
            require(places == sorted(set(places)) and 0 in places and set(places) <= set(ALL_PLACES),
                    f"{year}: invalid release venue support")
            numbers, report = summarize(year, places, pages, contacts, crops, HERE / "visual_review.json",
                                        frozen_tesseract)
            require(report["unequal_or_incomplete"] == 0 and report["empty"] == 0, f"{year}: scan did not reconcile")
            reports[str(year)] = report
        else:
            places = ALL_PLACES
            numbers = read_digital(archive / f"jp{year}.csv" if year < 1999 else csv1999, year)
        checks, unknown = check_counts(year, numbers, places)
        tables[year] = numbers
        year_receipts[str(year)] = {
            "release_venues": [VENUES[v] for v in places],
            "missing_venues": [v for v in VENUES if VENUES.index(v) not in places],
            "published_row_vectors": len(numbers) // 25,
            "reconciled_equalities_or_known_hour_bounds": checks,
            "publisher_births": numbers[0, 0, 0, 0],
            "births_unknown_hour": unknown,
        }
    table = destination / "historical_counts.csv.gz"
    write_table(table, tables)
    write_json(destination / "reconciliation.json", reports)
    write_json(destination / "source_receipt.json", {
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "official_scans": scans,
        "official_digital_tables": DIGITAL,
        "official_holiday_csv": CALENDAR,
        "public_counts_sha256": digest(table),
        "public_reconciliation_sha256": digest(destination / "reconciliation.json"),
        "visual_review_sha256": digest(HERE / "visual_review.json"),
        "tesseract_reads_sha256": digest(frozen_tesseract_path),
        "released_scan_scope_sha256": digest(scope),
        "years": year_receipts,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "csv1999", "pages", "contacts", "crops", "calendar", "scope", "destination"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    assemble(**vars(args))


if __name__ == "__main__":
    main()
