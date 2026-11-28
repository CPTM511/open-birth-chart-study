"""Read clock marginals from the specified public-use birth files."""

from __future__ import annotations

import argparse
from calendar import monthrange
from collections import Counter
import csv
from datetime import date
import io
from pathlib import Path
import re
import subprocess
import zipfile

from rounds.r27.archive_source import digest, read_json, require, write_json


HERE = Path(__file__).resolve().parent
DESIGN = read_json(HERE / "design.json")
EXCLUSIONS = ("unparseable_date", "outside_year", "unknown_clock", "invalid_clock")


def civil_year(token):
    token = token.strip()
    if re.fullmatch(r"[0-9]{8}", token):
        year, month, day = int(token[4:]), int(token[2:4]), int(token[:2])
    elif re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", token):
        day, month, year = map(int, token.split("/"))
    elif re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", token):
        year, month, day = map(int, token.split("-"))
    else:
        return None
    try:
        return date(year, month, day).year
    except ValueError:
        return None


def source_clock(token, unknown, *, variable_width):
    token = token.strip() if variable_width else token
    if variable_width and token.endswith(".0"):
        token = token[:-2]
    if not token.strip() or token == unknown:
        return "unknown_clock"
    width = r"[0-9]{1,4}" if variable_width else r"[0-9]{4}"
    if not re.fullmatch(width, token):
        return "invalid_clock"
    hour, minute = divmod(int(token), 100)
    if hour >= 24 or minute >= 60:
        return "invalid_clock"
    return hour, minute


def us_fields(config):
    fields = {}
    for name in ("year", "clock"):
        start, last = config[f"{name}_field_1_based_inclusive"]
        fields[name] = slice(start - 1, last)
    return fields


def project_fields(stream, key, config):
    if key == "brazil2006":
        reader = csv.reader(io.TextIOWrapper(stream, encoding=config["encoding"], newline=""),
                            delimiter=config["separator"], strict=True)
        header = [cell.strip() for cell in next(reader)]
        dob, clock = (header.index(config[k]) for k in ("date_column", "clock_column"))
        for row in reader:
            yield civil_year(row[dob]), row[clock]
    else:
        fields = us_fields(config)
        for row in stream:
            year = row[fields["year"]].decode("ascii")
            yield int(year) if len(year) == 4 and year.isdigit() else None, row[fields["clock"]].decode("ascii")


def original_count(stream, key, config):
    tally = Counter()
    for year, clock in project_fields(stream, key, config):
        if year is None:
            tally["unparseable_date"] += 1
        elif year != config["year"]:
            tally["outside_year"] += 1
        else:
            tally[source_clock(clock, config["unknown_clock"], variable_width=key == "brazil2006")] += 1
    return tally


def alternate_brazil_year(raw):
    raw = raw.strip()
    if len(raw) == 8 and raw.isascii() and raw.isdecimal():
        day, month, year = raw[:2], raw[2:4], raw[4:]
    elif len(raw) == 10 and raw[2] == raw[5] == "/":
        day, month, year = raw.split("/", 2)
        if (len(day), len(month), len(year)) != (2, 2, 4):
            return None
    elif len(raw) == 10 and raw[4] == raw[7] == "-":
        year, month, day = raw.split("-", 2)
        if (len(year), len(month), len(day)) != (4, 2, 2):
            return None
    else:
        return None
    if not all(t.isascii() and t.isdecimal() for t in (year, month, day)):
        return None
    y, m, d = int(year), int(month), int(day)
    return y if y >= 1 and 1 <= m <= 12 and 1 <= d <= monthrange(y, m)[1] else None


def alternate_count(stream, key, config):
    expected = config["year"]
    allowed = {f"{hour:02}{minute:02}": (hour, minute) for hour in range(24) for minute in range(60)}
    values = Counter()
    if key == "brazil2006":
        reader = csv.DictReader(io.TextIOWrapper(stream, encoding=config["encoding"], newline=""),
                                delimiter=config["separator"], strict=True)
        reader.fieldnames = [cell.strip() for cell in reader.fieldnames]
        for row in reader:
            year = alternate_brazil_year(row[config["date_column"]])
            if year != expected:
                values["unparseable_date" if year is None else "outside_year"] += 1
                continue
            text = row[config["clock_column"]].strip().removesuffix(".0")
            if text in ("", config["unknown_clock"]):
                values["unknown_clock"] += 1
            else:
                values[allowed.get(text.zfill(4), "invalid_clock")] += 1
    else:
        valid_codes = {key.encode("ascii"): rate for key, rate in allowed.items()}
        blank = config["unknown_clock"].encode("ascii")
        fields = us_fields(config)
        encoded_year = str(expected).encode("ascii")
        for line in stream:
            year = line[fields["year"]]
            if year != encoded_year:
                values["outside_year" if len(year) == 4 and year.isdigit() else "unparseable_date"] += 1
                continue
            raw = line[fields["clock"]]
            values["unknown_clock" if raw == blank or not raw.strip() else valid_codes.get(raw, "invalid_clock")] += 1
    return values


def count_archive(path, key, config, count):
    if "expected_zip_sha256" in config:
        require(digest(path) == config["expected_zip_sha256"], f"{key} does not match the fixed source digest")
    if "expected_zip_bytes" in config:
        require(path.stat().st_size == config["expected_zip_bytes"], f"{key} does not match the published listing size")
    with zipfile.ZipFile(path) as bundle:
        files = [entry for entry in bundle.infolist()
                 if not entry.is_dir() and entry.filename.lower().endswith(config["archive_member_suffix"])]
        require(len(files) == 1, f"{key} requires exactly one eligible file in its ZIP")
        member = files[0]
        if member.compress_type == 9:
            # CDC uses Deflate64, which Python's zipfile cannot decode.
            with subprocess.Popen(["unzip", "-p", str(path.resolve()), member.filename],
                                  stdout=subprocess.PIPE) as reader:
                tally = count(reader.stdout, key, config)
                require(reader.wait() == 0, f"Could not decompress and CRC-check {key}")
        else:
            with bundle.open(member) as records:
                tally = count(records, key, config)
    return tally, {"zip_sha256": digest(path), "zip_bytes": path.stat().st_size, "member": files[0].filename,
                   "member_uncompressed_bytes": files[0].file_size, "member_crc32": f"{files[0].CRC:08x}"}


def summarize(tally):
    counts = [[tally[(hour, minute)] for minute in range(60)] for hour in range(24)]
    require(all(sum(row) > 0 for row in counts), "A donor hour has no usable time")
    valid = sum(map(sum, counts))
    exclusions = {label: tally[label] for label in EXCLUSIONS}
    require(valid + sum(exclusions.values()) == sum(tally.values()), "Clock counts do not exhaust the file")
    return {"archive_rows": sum(tally.values()), "exclusions_in_order": exclusions, "valid_times": valid,
            "minute_zero": sum(row[0] for row in counts),
            "multiple_of_five_minutes": sum(sum(row[::5]) for row in counts), "counts": counts}


def extract(first, second):
    result = {"design_sha256": digest(HERE / "design.json"),
              "registration_sha256": digest(HERE / "REGISTRATION.zh.md"), "donors": {}}
    for key, config in DESIGN["donors"].items():
        paths = [directory / f"{key}.zip" for directory in (first, second)]
        require(paths[0].resolve() != paths[1].resolve() and digest(paths[0]) == digest(paths[1]),
                f"Independent archive copies do not match for {key}")
        tally, provenance = count_archive(paths[0], key, config, original_count)
        replay, other_provenance = count_archive(paths[1], key, config, alternate_count)
        require(provenance == other_provenance and tally == replay, f"Independent clock decoding differs for {key}")
        result["donors"][key] = {**provenance, **summarize(tally)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", required=True, type=Path)
    parser.add_argument("--second", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    write_json(args.output, extract(args.first, args.second))


if __name__ == "__main__":
    main()
