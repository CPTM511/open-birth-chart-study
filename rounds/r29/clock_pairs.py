"""Run original-minute and nearest-hour profiles on the same birth records."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import numpy as np

from rounds.r27.study import R10, age_years, chart_key, digest, init_worker, private_job, read_json, require, score_record
from analyze_cohorts import load_profiles


HERE = Path(__file__).resolve().parent


def rounding_shift(civil):
    require(civil.second == 0 and civil.microsecond == 0, "The registered transformation expects recorded minutes")
    return -civil.minute if civil.minute < 30 else 60 - civil.minute


def load_brisbane(path):
    config = read_json(HERE / "sources.json")["brisbane"]
    require(digest(path) == config["download_sha256"], "Published JSE data file hash differs")
    day = date.fromisoformat(config["birth_date"])
    local_zone = ZoneInfo(config["timezone"])
    rows = []
    for index, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        clock, sex_code, _, since_midnight = line.split()
        require(re.fullmatch(r"[0-9]{4}", clock) and sex_code in config["sex_code"], "Invalid JSE row")
        when = time(int(clock[:2]), int(clock[2:]))
        require(when.hour * 60 + when.minute == int(since_midnight), "JSE minute labels disagree")
        civil = datetime.combine(day, when, tzinfo=local_zone)
        require(civil.utcoffset() == timedelta(seconds=config["offset_seconds"]), "Brisbane offset differs")
        row = {
            "study_id": sha256(f"OBS-R29|JSE|{index}".encode()).hexdigest(),
            "source": "brisbane1997_jse",
            "birth_local": civil.replace(tzinfo=None).isoformat(),
            "birth_utc": civil.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_offset_seconds": config["offset_seconds"],
            "latitude": config["city_latitude"],
            "longitude": config["city_longitude"],
            "sex": config["sex_code"][sex_code],
        }
        row["calendar_years"] = age_years(row["birth_local"])
        row["chart_input_key"] = chart_key(row)
        rows.append(row)
    require(len(rows) == config["expected_records"]
            and Counter(row["sex"] for row in rows) == config["expected_sex_counts"], "JSE coverage differs")
    return rows


def inputs(r10_job, jse_data):
    seal = read_json(R10 / "independent_replay/registration.json")
    for filename, expected in seal["reference_files_sha256"].items():
        require(digest(r10_job / filename) == expected, "The Brazil 2006 reference files differ from the R10 freeze")
    brazil, _, frozen_scores, _, _, _, _ = load_profiles(
        r10_job / "reference/brazil2006",
        [r10_job / "reference/full-frozen-r8-baseline_profiles.jsonl"],
    )
    require(len(brazil) == 2000, "The Brazil sample is incomplete")
    weights = [Fraction(row["N_h"], row["n_h"]) for row in brazil]
    brisbane = load_brisbane(jse_data)
    return {"brazil2006": (brazil, weights), "brisbane1997": (brisbane, [Fraction(1)] * len(brisbane))}, frozen_scores


def work_units(groups):
    for cohort, (rows, _) in groups.items():
        for row in rows:
            shift = rounding_shift(datetime.fromisoformat(row["birth_local"]))
            yield cohort, (row, "original", 0, None)
            if shift:
                yield cohort, (row, "rounded", shift, None)


def score(groups, destination, jobs):
    require(1 <= jobs <= 4, "Use one to four local scoring workers")
    tasks = list(work_units(groups))
    source = (task for _, task in tasks)
    with destination.open("x", encoding="utf-8") as stream, multiprocessing.Pool(jobs, initializer=init_worker) as pool:
        for index, ((cohort, _), candidate) in enumerate(zip(tasks, pool.imap(score_record, source, chunksize=6), strict=True), 1):
            if candidate["status"] != "computed":
                raise ValueError(f"Paired scoring failed for {cohort}. Private error: {candidate['reason']}")
            result = {key: candidate[key] for key in ("study_id", "variant", "calendar_years", "chart_input_key", "primary_scores")}
            result["cohort"] = cohort
            stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
            if index % 400 == 0 or index == len(tasks):
                print(f"{index}/{len(tasks)} trajectories", flush=True)


def read_pairs(groups, path):
    present = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            key = item["cohort"], item["study_id"], item["variant"]
            require(key not in present, "Repeated trajectory")
            present[key] = item
    pairs = {}
    for cohort, (rows, _) in groups.items():
        baseline, rounded = [], []
        shifted = 0
        for row in rows:
            def take(variant):
                item = present.pop((cohort, row["study_id"], variant))
                require(all(item[field] == row[field] for field in ("calendar_years", "chart_input_key")),
                        "Trajectory does not match the published birth input")
                return item["primary_scores"]

            original = take("original")
            baseline.append(original)
            if rounding_shift(datetime.fromisoformat(row["birth_local"])):
                rounded.append(take("rounded"))
                shifted += 1
            else:
                rounded.append(original)
        arrays = np.asarray([baseline, rounded], dtype=float)
        require(arrays.shape == (2, len(rows), 40, 4) and np.isfinite(arrays).all()
                and arrays.min() >= 0 and arrays.max() <= 1, "Scoring output is incomplete or outside 0–1")
        pairs[cohort] = arrays, shifted
    require(not present, "Unmatched trajectories")
    return pairs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--r10-job", type=Path, required=True)
    parser.add_argument("--jse-data", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    group_rows, _ = inputs(args.r10_job, args.jse_data)
    score(group_rows, private_job(args.job) / "profiles.jsonl", args.jobs)
