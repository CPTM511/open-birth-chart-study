"""Score sealed R49 inputs at the recorded minute, with an exact restart audit."""

import argparse
import json
from multiprocessing import Pool
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from rounds.r45.score import init_worker, runtime
from rounds.r45.trajectories import Cohort
from rounds.r46.score import BATCH_SIZE, selected, verify_batch, worker

from .common import GROUPS, R10, REGISTRATION, digest, inputs, private, protocol, require, write_json


def batches(rows, settings, mode):
    records = selected(rows, settings, mode)
    for start in range(0, len(records), BATCH_SIZE):
        yield start, [(row, 0) for row in records[start:start + BATCH_SIZE]]


def batch_signature(seal, group, mode, start, tasks):
    return dict(registration=REGISTRATION, input_seal_sha256=seal["input_seal_sha256"], group=group, mode=mode,
                first_record=start, records=len(tasks), runner_sha256=digest(R10 / "methods/run_profiles.py"),
                score_module_sha256=digest(Path(__file__)))


def run(job, settings, group, mode, jobs):
    rows, _, seal = inputs(job, group)
    folder = job / group / mode
    folder.mkdir(exist_ok=True)
    total = len(rows) if mode == "full" else min(len(rows), settings["engine_replay"]["n_per_group"])
    with Pool(jobs, initializer=init_worker) as pool:
        for start, tasks in batches(rows, settings, mode):
            target = folder / f"{start:05d}"
            signature = batch_signature(seal, group, mode, start, tasks)
            if target.exists():
                list(verify_batch(target, signature, tasks))
                continue
            with TemporaryDirectory(dir=folder) as temporary:
                stage = Path(temporary) / target.name
                stage.mkdir()
                path = stage / "scores.jsonl"
                with path.open("x", encoding="utf-8") as stream:
                    for profile in pool.imap(worker, tasks, chunksize=4):
                        stream.write(json.dumps(profile, separators=(",", ":"), allow_nan=False) + "\n")
                write_json(stage / "receipt.json", dict(signature, scores_sha256=digest(path)))
                list(verify_batch(stage, signature, tasks))
                stage.rename(target)
            if start // BATCH_SIZE % 4 == 3 or start + len(tasks) == total:
                print(group, mode, f"{start + len(tasks)}/{total}", flush=True)


def read_group(job, settings, group):
    rows, manifest, seal = inputs(job, group)
    profiles, receipts = {}, {}
    for mode in ("full", "audit"):
        expected = set()
        profiles[mode], receipts[mode] = [], []
        for start, tasks in batches(rows, settings, mode):
            index = f"{start:05d}"
            expected.add(index)
            folder = job / group / mode / index
            signature = batch_signature(seal, group, mode, start, tasks)
            profiles[mode].extend(verify_batch(folder, signature, tasks))
            receipts[mode].append(digest(folder / "receipt.json"))
        actual = {item.name for item in (job / group / mode).iterdir() if item.name.isdecimal()}
        require(actual == expected, "Extra or missing score batches")
    saved = {row["study_id"]: row for row in profiles["full"]}
    require(len(saved) == len(rows) and all(audit == saved[audit["study_id"]] for audit in profiles["audit"]),
            "The independent engine restart did not reproduce the complete trajectory")
    scores = np.asarray([report["scores"]["base"] for report in profiles["full"]], dtype=float)
    restart_n = len(profiles["audit"])
    return Cohort(rows, scores, {}), {
        "sample_n": len(rows), "eligible_frame_n": manifest["eligible_frame_N"],
        "full_system_year_scores": len(rows) * 40 * 4, "restarted_records": restart_n,
        "restarted_system_year_scores": restart_n * 40 * 4, "input_seal_sha256": seal["input_seal_sha256"],
        "full_receipts_sha256": receipts["full"], "audit_receipts_sha256": receipts["audit"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--groups", choices=GROUPS, nargs="+", required=True)
    parser.add_argument("--mode", choices=("full", "audit"), required=True)
    parser.add_argument("--jobs", type=int, default=3, choices=range(1, 9))
    args = parser.parse_args()
    require(len(set(args.groups)) == len(args.groups), "Use distinct scoring groups")
    settings = protocol()
    runtime({"brazil2009": {"tzdb": settings["sampling"]["timezone_database"]}})
    for group in args.groups:
        run(private(args.job), settings, group, args.mode, args.jobs)


if __name__ == "__main__":
    main()
