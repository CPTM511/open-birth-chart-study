"""Build and score the protected R27 extracts with the frozen R10 engines."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import multiprocessing
from pathlib import Path
import platform
import re
import subprocess
import sys

import numpy as np

from .archive_source import HERE, ROOT, digest, private_job, read_json, require, write_json


R10 = ROOT / "rounds/r10"
sys.path.insert(0, str(R10 / "methods"))

from r10_io import age_years, chart_key
from run_profiles import init_worker, score_record


YEAR = 1901
AMSTERDAM_LATITUDE = 52.37403
AMSTERDAM_LONGITUDE = 4.88969
AMSTERDAM_OFFSET = 1172
VARIANTS = {"base": 0, "clock_-30": -30, "clock_+30": 30}
EXCLUDED = {"ack", "year", "place", "unreadable", "repeat"}


def transcription(path, pages, *, reverse=False):
    readings = {}
    seen_pages = set()
    seen_acts = set()
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        page, *entries = line.split()
        require(page in pages and page not in seen_pages, f"Unexpected or repeated image at line {line_no}")
        seen_pages.add(page)
        if reverse:
            entries.reverse()
        for position, token in enumerate(entries, 1):
            act, *values = token.split(":")
            require(re.fullmatch(r"[1-9][0-9]*", act) and act not in seen_acts,
                    f"Missing or nonunique sequential act number at line {line_no}")
            seen_acts.add(act)
            if len(values) == 1:
                require(values[0] in EXCLUDED, f"Undeclared exclusion at line {line_no}")
                readings[page, position] = (act, values[0])
                continue
            require(re.fullmatch(r"[0-9]{4}:[0-9]{4}:[MF]", ":".join(values)), f"Invalid birth at line {line_no}")
            day, time, sex = values
            civil = datetime.strptime(f"{YEAR}{day}{time}", "%Y%m%d%H%M")
            readings[page, position] = (act, (civil, sex))
    require(seen_pages == pages, "A transcription omits at least one selected image")
    return readings


def resolve(job):
    source = read_json(job / "source_receipt.json")
    require(source["registration_sha256"] == digest(HERE / "REGISTRATION.zh.md"), "Registration bytes differ")
    pages = {}
    for volume in source["volumes"].values():
        for sample in volume["selected"]:
            name = sample["local_name"]
            require(digest(job / "scans" / name) == sample["sha256"], "Selected image bytes differ")
            pages[Path(name).stem] = volume["scans_in_frame"]
    require(len(pages) == source["scans_selected_total"] == 42, "Wrong primary sample size")
    primary = transcription(job / "read-a.txt", set(pages))
    review = transcription(job / "read-b.txt", set(pages), reverse=True)
    final = transcription(job / "adjudicated.txt", set(pages))
    require(set(primary) == set(review) == set(final), "The review must resolve document coverage before scoring")
    disputed = {key for key in primary if primary[key] != review[key]}
    require(all(primary[key] == final[key] for key in primary.keys() - disputed),
            "Adjudication changed a value on which both transcriptions agreed")
    counts = Counter(value if isinstance(value, str) else "eligible" for _, value in final.values())
    ordinary = len(final) - counts["ack"]
    require(ordinary > 0 and (ordinary - counts["unreadable"]) / ordinary >= .85
            and counts["eligible"] >= 70, "Registered data feasibility condition failed")
    rows = {}
    for (page, _), (act, value) in sorted(final.items()):
        if isinstance(value, str):
            continue
        key = sha256(f"OBS-R27|{page}|{act}".encode()).hexdigest()
        rows[key] = birth_row(key, page, *value)
    return pages, rows, {
        "record_counts": dict(counts),
        "images_read": len(pages),
        "documents_read": len(final),
        "ordinary_birth_acts": ordinary,
        "two_read_disagreements": len(disputed),
        "two_read_disagreements_act_number": sum(primary[key][0] != review[key][0] for key in disputed),
        "two_read_disagreements_record_fields": sum(primary[key][1] != review[key][1] for key in disputed),
        "ambiguous_ordinary_acts_after_adjudication": counts["unreadable"],
        "same_transcriber": True,
        "source_sha256": digest(job / "source_receipt.json"),
        "private_input_sha256": {name: digest(job / name) for name in ("read-a.txt", "read-b.txt", "adjudicated.txt")},
    }


def birth_row(key, page, civil, sex):
    utc = (civil - timedelta(seconds=AMSTERDAM_OFFSET)).replace(tzinfo=timezone.utc)
    row = {
        "study_id": key, "source": "amsterdam5009_1901",
        "birth_local": civil.isoformat(), "birth_utc": utc.isoformat().replace("+00:00", "Z"),
        "source_offset_seconds": AMSTERDAM_OFFSET, "utc_offset_seconds": AMSTERDAM_OFFSET,
        "timezone_offset_minutes": AMSTERDAM_OFFSET / 60,
        "latitude": AMSTERDAM_LATITUDE, "longitude": AMSTERDAM_LONGITUDE,
        "sex": sex, "calendar": "gregorian", "birth_country": "NL", "geo_precision": "municipality_reference",
        "scan_unit": page,
    }
    row["calendar_years"] = age_years(row["birth_local"])
    row["chart_input_key"] = chart_key(row)
    return row


def score(job, jobs):
    _, rows, input_receipt = resolve(job)
    output = job / "profiles.json"
    require(not output.exists(), "Use a separate run directory for newly computed profiles")
    tasks = [(row, variant, shift, None) for row in rows.values() for variant, shift in VARIANTS.items()]
    require(1 <= jobs <= 4, "Use one to four local scoring workers")
    records = []
    with multiprocessing.Pool(jobs, initializer=init_worker) as pool:
        for result in pool.imap(score_record, tasks, chunksize=6):
            if result["status"] == "computed":
                result = {key: result[key] for key in ("study_id", "source", "variant", "status", "calendar_years",
                                                        "chart_input_key", "primary_scores")}
            else:
                result = {key: result[key] for key in ("study_id", "variant", "status", "reason")}
            records.append(result)

    write_json(output, {"input": input_receipt, "records": records})
    engines = R10 / "methods/open_birth_chart_r10"
    write_json(job / "scoring_receipt.json", {
        "input": input_receipt,
        "work_units": len(tasks),
        "status_counts": dict(Counter(record["status"] for record in records)),
        "profiles_sha256": digest(output),
        "frozen_scoring_files_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in [R10 / "methods/run_profiles.py", R10 / "methods/r10_io.py",
                         *sorted(p for p in engines.iterdir() if p.is_file())]
        },
        "python": platform.python_version(), "numpy": np.__version__, "os_arch": platform.platform(),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
    })
    if any(record["status"] != "computed" for record in records):
        raise ValueError("At least one record or sensitivity run could not be scored. See the private run.")


def load_target(job):
    pages, rows, receipt = resolve(job)
    profiles = read_json(job / "profiles.json")
    scoring_receipt = read_json(job / "scoring_receipt.json")
    require(profiles["input"] == scoring_receipt["input"] == receipt
            and digest(job / "profiles.json") == scoring_receipt["profiles_sha256"], "Results do not match sealed inputs")
    by_variant = {key: {} for key in VARIANTS}
    for record in profiles["records"]:
        identity = record["study_id"]
        row = rows[identity]
        variant = record["variant"]
        require(identity not in by_variant[variant] and record["status"] == "computed", "Missing or repeated trajectory")
        for field in ("chart_input_key", "source", "calendar_years"):
            require(record[field] == row[field], "Trajectory does not match selected act or modeled age")
        by_variant[variant][identity] = record["primary_scores"]
    require(all(set(group) == set(rows) for group in by_variant.values()), "Incomplete four-system scoring coverage")
    scores = {key: np.asarray([group[identity] for identity in rows], dtype=float) for key, group in by_variant.items()}
    require(all(array.shape == (len(rows), 40, 4) and np.isfinite(array).all()
                and array.min() >= 0 and array.max() <= 1 for array in scores.values()), "Invalid trajectory shape or score")
    return pages, list(rows.values()), scores, scoring_receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    score(private_job(args.job), args.jobs)
