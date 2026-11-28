"""Calculate frozen R10 trajectories, changing the minute only in the paired run."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory
from zoneinfo import TZPATH, ZoneInfo

import numpy as np

from .common import REGISTRATION, R10, digest, registered, require, source_seal, write_json
from .datasets import add_paths, datasets
from run_profiles import init_worker, score_record


def hour_offset(row):
    when = datetime.fromisoformat(row["birth_local"])
    require(when.second == when.microsecond == 0, "An input is outside the recorded minute frame")
    zone = ZoneInfo(row["timezone_id"])
    rounded = when.replace(minute=0)
    offsets = set()
    for fold in (0, 1):
        event = rounded.replace(tzinfo=zone, fold=fold)
        if event.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == rounded:
            offsets.add(int(event.utcoffset().total_seconds()))
    return -when.minute if offsets == {row["source_offset_seconds"]} else None


def audit_sample(rows, cfg):
    p = cfg["inference"]
    return sorted(rows, key=lambda r: sha256((p["replay_seed"] + "|" + r["study_id"]).encode()).digest())[
        :p["replay_per_group"]]


def tasks_for(rows, mode, clock):
    for row in rows:
        if mode in ("base", "audit"):
            yield row, "base", 0, None
        if mode in ("hour", "audit"):
            change = clock[row["study_id"]]
            if change:
                yield row, "hour", change, None


def runtime(cfg):
    require(platform.system() == "Linux" and platform.machine() == "x86_64"
            and platform.python_version() == "3.12.14" and np.__version__ == "2.3.5"
            and subprocess.check_output(["node", "--version"], text=True).strip() == "v24.22.3",
            "Use the frozen R10 Linux scoring runtime")
    for folder in TZPATH:
        version_file = Path(folder) / "tzdata.zi"
        if version_file.is_file():
            with version_file.open() as stream:
                require(stream.readline().strip() == "# version " + cfg["brazil2009"]["tzdb"],
                        "Use the registered IANA tzdb")
            break
    else:
        raise ValueError("No IANA database with version metadata")


def run_score(args, cfg, group, entry):
    ordering = entry.births()
    require(len(ordering) == cfg["groups"][group]["n"], "Birth count differs from registration")
    rows = audit_sample(ordering, cfg) if args.mode == "audit" else ordering
    clock = {row["study_id"]: hour_offset(row) for row in rows} if args.mode != "base" else {}
    tasks = list(tasks_for(rows, args.mode, clock))
    folder = args.job / group / "scores"
    folder.mkdir(parents=True, exist_ok=True)
    result = folder / (args.mode + ".jsonl")
    receipt = folder / (args.mode + "_receipt.json")
    require(not result.exists() and not receipt.exists(), "Use an unused score destination")
    keys = ("study_id", "source", "status", "variant", "calendar_years", "chart_input_key", "primary_scores")
    with TemporaryDirectory(dir=folder) as temp:
        stage = Path(temp)
        partial = stage / result.name
        with partial.open("x", encoding="utf-8") as out, multiprocessing.Pool(
                args.jobs, initializer=init_worker) as pool:
            for index, (task, profile) in enumerate(zip(
                    tasks, pool.imap(score_record, tasks, chunksize=6), strict=True), 1):
                require(profile["status"] == "computed", f"{group} trajectory failed: {profile.get('reason')}")
                require(profile["study_id"] == task[0]["study_id"] and profile["variant"] == task[1],
                        "Score worker returned a different record or clock variant")
                out.write(json.dumps({key: profile[key] for key in keys}, allow_nan=False, separators=(",", ":"))+"\n")
                if index % 400 == 0 or index == len(tasks):
                    print(f"{group} {args.mode} {index}/{len(tasks)}", flush=True)
        variant_counts = Counter(task[1] for task in tasks)
        write_json(stage / receipt.name, dict(registration=REGISTRATION, group=group, mode=args.mode, n=len(rows),
                   source=source_seal(entry.sample), completed=dict(variant_counts),
                   source_clocks_already_on_hour=sum(shift == 0 for shift in clock.values()),
                   rounded_offset_not_resolved=sum(shift is None for shift in clock.values()),
                   score_sha256=digest(partial), engine_runner_sha256=digest(R10 / "methods/run_profiles.py"),
                   runtime="Linux x86_64 Python 3.12.14 Node 24.22.3"))
        partial.rename(result)
        (stage / receipt.name).rename(receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_paths(parser)
    parser.add_argument("--mode", choices=("base", "hour", "audit"), required=True)
    parser.add_argument("--groups", nargs="+", required=True)
    parser.add_argument("--jobs", type=int, default=4, choices=range(1, 5))
    args = parser.parse_args()
    require(args.job.stat().st_mode & 0o077 == 0, "Use a private score folder")
    cfg = registered()
    inventory = datasets(args, cfg)
    runtime(cfg)
    allowed = {"br2009", "mx2009"} if args.mode == "base" else set(cfg["groups"])
    require(set(args.groups) <= allowed and len(set(args.groups)) == len(args.groups), "Unknown or duplicated group")
    for group in args.groups:
        run_score(args, cfg, group, inventory[group])


if __name__ == "__main__":
    main()
