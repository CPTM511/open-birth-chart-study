"""Run frozen R10 scores for the R41 Tokyo minute grid."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from functools import cache
from hashlib import sha256
from multiprocessing import Pool
from pathlib import Path
import platform
import subprocess
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo

import numpy as np

from rounds.r27.archive_source import digest, private_job, read_json, require
from rounds.r27.study import R10, age_years, chart_key, init_worker, score_record
from rounds.r34.profiles import sensitivity_dates
from rounds.r34.source import HERE as R34


HERE = Path(__file__).resolve().parent
DESIGN = read_json(HERE / "design.json")
YEARS = tuple(DESIGN["years"])
SEXES = tuple(DESIGN["parameter_values"])
MINUTES = range(DESIGN["minutes_inclusive"][0], DESIGN["minutes_inclusive"][1] + 1)
ZONE = ZoneInfo(DESIGN["time_zone"])
OFFSET = DESIGN["offset_seconds"]


def study_dates(year):
    selected = sorted(sensitivity_dates(year))
    require(len(selected) == DESIGN["dates_per_year"], f"R34 date count differs for {year}")
    return selected


def scoring_keys(day, probe=False):
    if probe:
        seed = DESIGN["probe_seed"]
        chosen = int.from_bytes(sha256(f"{seed}|{day.isoformat()}".encode()).digest(), "big") % 24
        hours, minutes = (chosen,), DESIGN["probe_minutes"]
    else:
        hours, minutes = range(24), MINUTES
    return [(hour, minute, sex) for hour in hours for minute in minutes for sex in range(len(SEXES))]


def row_for(day, hour, minute, sex):
    clock = datetime.combine(day, time(hour, minute, DESIGN["seconds"]), tzinfo=ZONE)
    require(clock.utcoffset() == timedelta(seconds=OFFSET), "Historical timezone offset differs")
    row = {
        "study_id": sha256(f"OBS-R41|{day.isoformat()}|{hour}|{minute}|{sex}".encode()).hexdigest(),
        "source": "r41_standard_input",
        "birth_local": clock.replace(tzinfo=None).isoformat(),
        "birth_utc": clock.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_offset_seconds": OFFSET,
        "latitude": DESIGN["latitude"],
        "longitude": DESIGN["longitude"],
        "sex": SEXES[sex],
        "calendar": "gregorian",
        "birth_country": "JP",
    }
    row["calendar_years"] = age_years(row["birth_local"])
    row["chart_input_key"] = chart_key(row)
    return row


@cache
def study_signature():
    method_dir = R10 / "methods"
    method_files = [method_dir / "r10_io.py", method_dir / "run_profiles.py"]
    method_files.extend(sorted(path for path in (method_dir / "open_birth_chart_r10").iterdir() if path.is_file()))
    files = [HERE / "design.json", HERE / "REGISTRATION.zh.md", Path(__file__),
             R34 / "sources.json", R34 / "profiles.py", R10 / "protocol.json", *method_files]
    return "|".join(digest(path) for path in files)


@cache
def runtime_signature():
    node = subprocess.check_output(["node", "--version"], text=True).strip()
    return (platform.system(), platform.machine(), *platform.libc_ver(), platform.python_version(), node)


def score_primary(row):
    result = score_record((row, "base", 0, None))
    require(result["status"] == "computed",
            f"R10 stopped for {row['birth_local']} {row['sex']}: {result.get('reason')}")
    require(all(result[key] == row[key] for key in ("study_id", "chart_input_key", "calendar_years")),
            "The output belongs to a different grid input")
    return result["primary_scores"]


def score_path(directory, day):
    return directory / f"tokyo-{day.isoformat()}.npz"


def load_scores(directory, day, probe=False, *, restrict_runtime=False):
    path = score_path(directory, day)
    keys = scoring_keys(day, probe)
    with np.load(path, allow_pickle=False) as archive:
        require(np.array_equal(archive["keys"], keys), f"Grid keys differ for {day}")
        require(str(archive["study_signature"]) == study_signature(), f"Grid definition differs for {day}")
        if restrict_runtime:
            require(tuple(archive["runtime_signature"]) == runtime_signature(), f"Runtime differs for {day}")
        scores = archive["scores"]
    require(scores.shape == (len(keys), 40, 4) and np.isfinite(scores).all()
            and (scores >= 0).all() and (scores <= 1).all(), f"Missing or invalid R10 trajectories for {day}")
    return scores


def run_date(pool, directory, day, probe):
    path = score_path(directory, day)
    keys = scoring_keys(day, probe)
    if not path.exists():
        rows = (row_for(day, *key) for key in keys)
        scores = np.asarray(list(pool.imap(score_primary, rows, chunksize=12)), dtype=np.float64)
        require(scores.shape == (len(keys), 40, 4) and np.isfinite(scores).all()
                and (scores >= 0).all() and (scores <= 1).all(), f"Incomplete grid for {day}")
        with NamedTemporaryFile(dir=directory) as temporary:
            np.savez_compressed(temporary, keys=keys, scores=scores, study_signature=study_signature(),
                                runtime_signature=runtime_signature())
            temporary.flush()
            path.hardlink_to(temporary.name)
    load_scores(directory, day, probe, restrict_runtime=True)
    print(f"{day.isoformat()} verified {len(keys)} profiles {digest(path)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--year", required=True, choices=YEARS, type=int)
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--first-date", type=date.fromisoformat)
    parser.add_argument("--last-date", type=date.fromisoformat)
    parser.add_argument("--probe", action="store_true", help="Compute the independently selected minute probes")
    args = parser.parse_args()
    expected_runtime = ("Linux", "x86_64", "glibc", "2.36", "3.12.14", "v24.22.3")
    require(runtime_signature() == expected_runtime, "Use the frozen R10 Linux x86-64 runtime")
    require(args.workers >= 1, "At least one scoring process is required")
    dates = [day for day in study_dates(args.year)
             if (args.first_date is None or args.first_date <= day) and (args.last_date is None or day <= args.last_date)]
    require(dates, "The requested window contains no registered date")
    directory = private_job(args.directory)
    with Pool(args.workers, initializer=init_worker) as pool:
        for day in dates:
            run_date(pool, directory, day, args.probe)


if __name__ == "__main__":
    main()
