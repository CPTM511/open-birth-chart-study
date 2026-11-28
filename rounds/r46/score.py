"""Score a sealed R46 sample and replay it in resumable whole-record batches."""

import argparse
from hashlib import sha256
import json
from multiprocessing import Pool
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from rounds.r45.common import load_source
from rounds.r45.score import hour_offset, init_worker, runtime, score_record
from r10_io import jsonlines

from .common import GROUPS, HERE, R10, REGISTRATION, digest, private, protocol, read_json, require, verify_files, write_json

BATCH_SIZE = 256


def inputs(job, group):
    folder = job / group
    published = read_json(HERE / "seals" / f"{group}.json")
    seal_file = folder / "input_seal.json"
    require(published["registration"] == REGISTRATION and published["group"] == group
            and digest(seal_file) == published["input_seal_sha256"], "The input commitment differs from publication")
    local = read_json(seal_file)
    require(all(published[key] == item for key, item in local.items()), "Published input receipt fields differ")
    verify_files(folder / "sample", local["sha256"])
    rows, manifest = load_source(folder / "sample")
    require(len(rows) == local["records"] and all(int(r["birth_local"][:4]) == int(group[2:]) for r in rows),
            "Registered birth year or group coverage differs")
    return rows, manifest, published["input_seal_sha256"]


def selected(rows, cfg, mode):
    if mode == "full":
        return rows
    rule = cfg["engine_replay"]
    return sorted(rows, key=lambda r: sha256((rule["seed"]+"|"+r["study_id"]).encode()).digest())[
        :rule["n_per_group"]]


def tasks(rows, group):
    for row in rows:
        shift = hour_offset(row) if group.endswith("2009") else 0
        yield row, shift


def worker(task):
    row, shift = task
    requested = [("base", 0)]
    if shift:
        requested.append(("hour", shift))
    scores = {}
    for variant, delta in requested:
        result = score_record((row, variant, delta, None))
        require(result["status"] == "computed", f"Trajectory scoring failed: {result.get('reason')}")
        require(result["chart_input_key"] == row["chart_input_key"]
                and result["calendar_years"] == row["calendar_years"], "Unexpected score worker record")
        scores[variant] = result["primary_scores"]
    return {"study_id": row["study_id"], "chart_input_key": row["chart_input_key"],
            "calendar_years": row["calendar_years"], "clock_shift_minutes": shift, "scores": scores}


def signature(source_digest, group, mode, start, configs):
    return dict(registration=REGISTRATION, input_seal_sha256=source_digest, group=group, mode=mode,
                first_record=start, records=len(configs), runner_sha256=digest(R10 / "methods/run_profiles.py"))


def verify_batch(folder, commit, configs):
    receipt = read_json(folder / "receipt.json")
    require(all(receipt[key] == value for key, value in commit.items())
            and digest(folder / "scores.jsonl") == receipt["scores_sha256"], "Protected batch bytes differ")
    for (row, shift), report in zip(configs, jsonlines(folder / "scores.jsonl"), strict=True):
        require(all(report[k] == row[k] for k in ("study_id", "chart_input_key", "calendar_years"))
                and report["clock_shift_minutes"] == shift, "Protected profile mismatch")
        supported = {"base", "hour"} if shift else {"base"}
        require(set(report["scores"]) == supported, "Protected clock branches differ")
        for trajectory in report["scores"].values():
            values = np.asarray(trajectory)
            require(values.shape == (40,4) and np.all((0 <= values) & (values <= 1)), "Incomplete score trajectory")
        yield report


def run(job, group, cfg, mode, jobs):
    rows, _, source_digest = inputs(job, group)
    configs = list(tasks(selected(rows, cfg, mode), group))
    folder = job / group / mode
    folder.mkdir(exist_ok=True)
    with Pool(jobs, initializer=init_worker) as pool:
        for start in range(0, len(configs), BATCH_SIZE):
            current = configs[start:start+BATCH_SIZE]
            target = folder / f"{start:05d}"
            commit = signature(source_digest, group, mode, start, current)
            if target.exists():
                list(verify_batch(target, commit, current))
                continue
            with TemporaryDirectory(dir=folder) as temporary:
                stage = Path(temporary) / target.name
                stage.mkdir()
                path = stage / "scores.jsonl"
                with path.open("x", encoding="utf-8") as stream:
                    for item in pool.imap(worker, current, chunksize=4):
                        stream.write(json.dumps(item, separators=(",",":"), allow_nan=False)+"\n")
                write_json(stage / "receipt.json", dict(commit, scores_sha256=digest(path)))
                list(verify_batch(stage, commit, current))
                stage.rename(target)
            if start//BATCH_SIZE % 4 == 3 or start+len(current) == len(configs):
                print(group, mode, f"{start+len(current)}/{len(configs)}", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", type=Path, required=True)
    p.add_argument("--groups", required=True, nargs="+", choices=GROUPS)
    p.add_argument("--mode", required=True, choices=("full","audit"))
    p.add_argument("--jobs", type=int, default=4, choices=range(1,5))
    args = p.parse_args()
    require(len(set(args.groups)) == len(args.groups), "Choose distinct groups")
    cfg = protocol()
    runtime({"brazil2009": {"tzdb": cfg["sampling"]["timezone_database"]}})
    for group in args.groups:
        run(private(args.job), group, cfg, args.mode, args.jobs)


if __name__ == "__main__":
    main()
