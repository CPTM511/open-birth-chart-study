"""Run R10 on the fixed, nonpersonal birth-date and hour configurations."""

from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
from multiprocessing import Pool
from pathlib import Path
import platform
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo

import numpy as np

from rounds.r27.study import age_years, chart_key, init_worker, private_job, require, score_record
from .source import CONFIG, HERE, YEARS, dates_for, digest


VARIANTS = tuple(CONFIG["clock_variants"])
SEXES = ("F", "M")
JST = ZoneInfo(CONFIG["timezone"])
OFFSET = CONFIG["source_offset_seconds"]


def sensitivity_dates(year):
    picked = set()
    for month in range(1, 13):
        days = [day for day in dates_for(year) if day.month == month]
        order = sorted(days, key=lambda day: sha256(f"{CONFIG['date_sensitivity_seed']}|{day.isoformat()}".encode()).digest())
        picked.update(order[:2])
    return picked


def keys_for(year, month):
    days = dates_for(year)
    if month == 0:
        return [(index, 0, hour, sex) for index, day in enumerate(days) if day.day == 1
                for hour in (0, 12) for sex in range(len(SEXES))]
    require(1 <= month <= 12, "Choose a calendar month")
    picked = sensitivity_dates(year)
    return [(index, variant, hour, sex) for index, day in enumerate(days) if day.month == month
            for variant in range(len(VARIANTS) if day in picked else 1)
            for hour in range(24) for sex in range(len(SEXES))]


def row_for(day, variant, hour, sex):
    minute, latitude, longitude = CONFIG["clock_variants"][VARIANTS[variant]]
    local = datetime.combine(day, time(hour, minute), tzinfo=JST)
    require(local.utcoffset() == timedelta(seconds=OFFSET), "The registered Japan offset differs")
    row = {
        "study_id": sha256(f"OBS-R34|{day.isoformat()}|{variant}|{hour}|{sex}".encode()).hexdigest(),
        "source": "r34_standard_input",
        "birth_local": local.replace(tzinfo=None).isoformat(),
        "birth_utc": local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_offset_seconds": OFFSET,
        "latitude": latitude,
        "longitude": longitude,
        "sex": SEXES[sex],
        "calendar": "gregorian",
        "birth_country": "JP",
    }
    row["calendar_years"] = age_years(row["birth_local"])
    row["chart_input_key"] = chart_key(row)
    return row


def signature():
    return "|".join([digest(HERE / "sources.json"), digest(HERE / "REGISTRATION.zh.md"),
                     digest(Path(__file__)), platform.system(), platform.machine(), platform.python_version()])


def scores_file(directory, year, month):
    return directory / f"jp{year}-{month:02d}.npz"


def load_scores(path, keys, *, same_environment):
    with np.load(path, allow_pickle=False) as archive:
        require(np.array_equal(archive["keys"], keys), f"Scoring keys differ in {path.name}")
        saved = str(archive["signature"])
        valid = saved == signature() if same_environment else saved.split("|")[:3] == signature().split("|")[:3]
        require(valid, f"Scoring definition or environment differs in {path.name}")
        scores = archive["scores"]
    require(scores.shape == (len(keys), 40, 4) and np.isfinite(scores).all() and (scores >= 0).all()
            and (scores <= 1).all(), f"Incomplete R10 trajectories in {path.name}")
    return scores


def run_month(pool, directory, year, month):
    keys = keys_for(year, month)
    path = scores_file(directory, year, month)
    if path.exists():
        load_scores(path, keys, same_environment=True)
        print(f"{year}-{month:02d} verified existing {len(keys)} model runs", flush=True)
        return
    days = dates_for(year)
    rows = [row_for(days[index], variant, hour, sex) for index, variant, hour, sex in keys]
    outputs = pool.imap(score_record, ((row, "base", 0, None) for row in rows), chunksize=8)
    scores = []
    for row, result in zip(rows, outputs, strict=True):
        require(result.get("status") == "computed", f"R10 stopped for {year}-{month:02d}: {result.get('reason')}")
        require(all(result[k] == row[k] for k in ("study_id", "chart_input_key", "calendar_years")),
                "A score was paired to the wrong standardized input")
        scores.append(result["primary_scores"])
    with NamedTemporaryFile(dir=directory) as temporary:
        np.savez_compressed(temporary, keys=keys, scores=np.asarray(scores), signature=signature())
        temporary.flush()
        path.hardlink_to(temporary.name)
    print(f"{year}-{month:02d} verified {len(keys)} model runs", flush=True)


def run(directory, year, months, workers):
    require(1 <= workers <= 4, "Use one to four workers in each scoring process")
    with Pool(workers, initializer=init_worker) as pool:
        for month in months:
            run_month(pool, directory, year, month)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--year", required=True, choices=YEARS, type=int)
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--probe", action="store_true", help="cross-runtime checks on the first day of each month")
    parser.add_argument("--first-month", type=int, default=1)
    parser.add_argument("--last-month", type=int, default=12)
    a = parser.parse_args()
    require(1 <= a.first_month <= a.last_month <= 12, "Choose an ordered date window")
    months = [0] if a.probe else range(a.first_month, a.last_month + 1)
    run(private_job(a.directory), a.year, months, a.workers)


if __name__ == "__main__":
    main()
