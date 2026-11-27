"""Prepare and score the Colombian archives with the frozen R10 engines."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

from rounds.r27.study import age_years, chart_key
from rounds.r29.clock_pairs import score, work_units
from .date_extension import activate
from .source import BIRTH_FIELDS, CONFIG, HERE, digest, fields, private_job, read_json, require, write_json


DATE_FORMAT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?")
CLOCK_ANCHOR = date(1899, 12, 31)
SEX = {"FEMENINO": "F", "MASCULINO": "M"}
OFFSET = timedelta(seconds=CONFIG["source_offset_seconds"])
ZONE = ZoneInfo(CONFIG["timezone"])


def label(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.upper()) if c.isalnum())


def local_stamp(source):
    if not DATE_FORMAT.fullmatch(source.strip()):
        return None
    try:
        return datetime.fromisoformat(source.strip())
    except ValueError:
        return None


def in_window(day, window):
    start, end = window
    return start <= day.isoformat() <= end


def decide(row, site):
    if not any(value.strip() for value in row.values()):
        return "blank", None
    date_val, time_val, sex_val = (row[key] for key in BIRTH_FIELDS)
    birth = local_stamp(date_val)
    if birth is None or birth.time() != time(0) or not in_window(birth.date(), site["birth_window"]):
        return "birth_date", None
    if any(label(row[key]) != value for key, value in site["area_fields"].items()):
        return "birth_place", None
    sex = SEX.get(label(sex_val))
    if sex is None:
        return "sex", None
    clock = local_stamp(time_val)
    if clock is None or clock.second or clock.microsecond:
        return "invalid_clock", None
    if clock.date() != CLOCK_ANCHOR:
        return "nonstandard_clock_day", None
    return "eligible", (datetime.combine(birth.date(), clock.time()), sex)


def make_input(site_name, site, line_no, values):
    civil, sex = values
    aware = civil.replace(tzinfo=ZONE)
    require(aware.utcoffset() == OFFSET, f"The registered UTC offset differs for {site_name}")
    result = {
        "study_id": sha256(f"OBS-R30|{site['id']}|{line_no}".encode()).hexdigest(),
        "source": site_name,
        "birth_local": civil.isoformat(),
        "birth_utc": aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_offset_seconds": CONFIG["source_offset_seconds"],
        "latitude": site["latitude"],
        "longitude": site["longitude"],
        "sex": sex,
        "calendar": "gregorian",
        "birth_country": "CO",
        "geo_precision": site["geo_precision"],
    }
    result["calendar_years"] = age_years(result["birth_local"])
    result["chart_input_key"] = chart_key(result)
    return result


def report_period(label_text, birth):
    groups = re.fullmatch(r"(IV|III|II|I)TRIMESTRE(20[0-9]{2})", label(label_text))
    if groups is None:
        return "period_unparseable"
    quarter, year = groups.groups()
    quarters = ("I", "II", "III", "IV")
    matches = int(year) == birth.year and quarters.index(quarter) == (birth.month - 1) // 3
    return "period_matches_birth" if matches else "period_differs_from_birth"


def load_site(path, site_name, site):
    rows = []
    statuses, periods = Counter(), Counter()
    selected = set(fields(site))
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            source = json.loads(line)
            require(set(source) == selected, f"Sealed projection schema differs for {site_name}")
            status, values = decide(source, site)
            statuses[status] += 1
            if values is not None:
                rows.append(make_input(site_name, site, line_no, values))
                if "period_field" in site:
                    periods[report_period(source[site["period_field"]], values[0])] += 1

    datetimes = [datetime.fromisoformat(row["birth_local"]) for row in rows]
    dates = {civil.date() for civil in datetimes}
    ties = Counter((row["birth_local"], row["sex"]) for row in rows)
    require(sum(statuses.values()) == site["published_rows"], f"Unaccounted source rows for {site_name}")
    require(len(rows) >= 100 and len(dates) >= 30, f"Insufficient registered record or date coverage for {site_name}")
    return rows, {
        "raw_rows": sum(statuses.values()),
        "location_eligible_before_sex_and_clock": sum(statuses[k] for k in (
            "eligible", "sex", "invalid_clock", "nonstandard_clock_day")),
        "first_disposition": {k: statuses[k] for k in ("blank", "birth_date", "birth_place", "sex",
                                                      "invalid_clock", "nonstandard_clock_day", "eligible")},
        "distinct_birth_dates": len(dates),
        "months_with_eligible_births": len({(v.year, v.month) for v in datetimes}),
        "first_last_birth_month": [min(dates).isoformat()[:7], max(dates).isoformat()[:7]],
        "reported_sex_counts": dict(Counter(row["sex"] for row in rows)),
        "whole_hour_clocks": sum(civil.minute == 0 for civil in datetimes),
        "five_minute_clocks": sum(civil.minute % 5 == 0 for civil in datetimes),
        "midnight_clocks": sum(civil.time() == time(0) for civil in datetimes),
        "coincident_clock_and_sex_groups": sum(n > 1 for n in ties.values()),
        "coincident_clock_and_sex_excess_rows": sum(n - 1 for n in ties.values()),
        "reporting_period_check": dict(periods),
    }


def inputs(job):
    receipt = read_json(job / "source_receipt.json")
    require(receipt["registration_sha256"] == digest(HERE / "REGISTRATION.zh.md")
            and receipt["definition_sha256"] == digest(HERE / "sources.json"), "The source registration seal differs")
    groups, coverage = {}, {}
    for name, site in CONFIG["sites"].items():
        canonical = job / f"{name}.jsonl"
        require(digest(canonical) == receipt["sites"][name]["private_projection_sha256"], f"Projection hash differs for {name}")
        rows, coverage[name] = load_site(canonical, name, site)
        groups[name] = (rows, [Fraction(1)] * len(rows))
    return groups, coverage


def scoring_groups(groups, selected):
    return {name: ([row for row in rows if row["study_id"] in selected], ()) for name, (rows, _) in groups.items()}


def work_index(groups):
    return {(name, row["study_id"], variant): row for name, (row, variant, _, _) in work_units(groups)}


def load_runs(path, expected):
    values = {}
    with path.open(encoding="utf-8") as stream:
        for record in map(json.loads, stream):
            key = (record["cohort"], record["study_id"], record["variant"])
            require(key in expected and key not in values, "Unexpected repeated or unknown scoring task")
            row = expected[key]
            require(all(row[field] == record[field] for field in ("chart_input_key", "calendar_years")),
                    "Scoring checkpoint does not match the registered birth input")
            values[key] = record
    return values


def finish_with_extension(job, groups, jobs):
    expected = work_index(groups)
    frozen_expected = {key: row for key, row in expected.items() if row["birth_local"][:4] <= "2025"}
    frozen = load_runs(job / "profiles-frozen.jsonl", frozen_expected)
    audit_rows = {}
    for (site, study_id, _), row in frozen_expected.items():
        audit_rows.setdefault((site, row["birth_local"][:4]), study_id)
    audit_ids = set(audit_rows.values())
    require(all(key in frozen for key in frozen_expected if key[1] in audit_ids), "Missing the registered frozen audit rows")
    new_ids = {key[1] for key in expected if key not in frozen}
    extra_groups = scoring_groups(groups, audit_ids | new_ids)
    extension = activate(job / "extended_engine")
    extra_path = job / "profiles-extended.jsonl"
    score(extra_groups, extra_path, jobs)
    upgraded = load_runs(extra_path, work_index(extra_groups))
    require(all(frozen[key] == upgraded[key] for key in frozen.keys() & upgraded.keys()),
            "A completed in-range trajectory changes in the extended entry point")
    complete = frozen | upgraded
    require(set(complete) == set(expected), "The date extension did not complete every score")
    with (job / "profiles.jsonl").open("x", encoding="utf-8") as stream:
        for key in expected:
            stream.write(json.dumps(complete[key], ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
    write_json(job / "date_extension_receipt.json", {
        "amendment_sha256": digest(HERE / "DATE_RANGE_AMENDMENT.zh.md"),
        "frozen_in_range_trajectories": len(frozen),
        "additional_in_range_trajectories": len(frozen_expected.keys() - frozen.keys()),
        "earlier_birth_records_recheck": len(audit_ids),
        "exact_overlap_trajectories": len(frozen.keys() & upgraded.keys()),
        "birth_year_2026_trajectories": len(expected) - len(frozen_expected),
        "changed_engine_files": extension,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--frozen-only", action="store_true")
    phase.add_argument("--finish-year-expansion", action="store_true")
    args = parser.parse_args()
    job = private_job(args.job)
    groups, _ = inputs(job)
    if args.frozen_only:
        before_2026 = {row["study_id"] for rows, _ in groups.values() for row in rows if row["birth_local"][:4] <= "2025"}
        score(scoring_groups(groups, before_2026), job / "profiles-frozen.jsonl", args.jobs)
    else:
        finish_with_extension(job, groups, args.jobs)
