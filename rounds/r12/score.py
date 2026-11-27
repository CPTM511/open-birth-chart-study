"""Run the frozen four-model scorer only after both R12 commitments are verified."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
import math
from pathlib import Path
import platform
import subprocess
import sys

from study import ROOT, R10, checked_samples, digest, load_source, read_json, read_registration, require, write_json
from r10_io import jsonlines


def audited_profiles(profile_path, directories):
    expected = {}
    for slot, path in directories.items():
        rows, _ = load_source(path)
        for row in rows:
            key = row["study_id"]
            require(key not in expected, "Repeated study identifier")
            expected[key] = slot, row
    counts = Counter()
    for profile in jsonlines(profile_path):
        require(profile["study_id"] in expected, "Unexpected or repeated profile")
        slot, row = expected.pop(profile["study_id"])
        require(profile["variant"] == "base" and profile["status"] == "computed", "Incomplete four-model profile")
        for key in ("source", "chart_input_key", "calendar_years"):
            require(profile[key] == row[key], "Stored trajectory does not match input")
        scores = profile["primary_scores"]
        require(len(scores) == 40 and all(len(values) == 4 and all(math.isfinite(x) and 0 <= x <= 1 for x in values)
                                         for values in scores), "Incomplete or invalid score array")
        counts[slot] += 1
    require(not expected, "Missing scored profiles")
    return dict(counts)


def run(args):
    registration = read_registration(args.registration_sha256)
    directories = checked_samples(args.job, registration, args.registration_sha256, args.input_sha256)
    runtime = registration["scoring_runtime"]
    require(platform.system() == "Linux" and platform.machine() == "x86_64"
            and platform.python_version() == runtime["python"], "Use the registered Linux x86-64 scoring environment")
    require(subprocess.check_output(["node", "--version"], text=True).strip() == "v" + runtime["node"],
            "Use the registered Node version")
    dependencies = dict(
        line.split("==") for line in (ROOT / "requirements.txt").read_text().splitlines() if "==" in line)
    require(all(version(package) == pinned for package, pinned in dependencies.items()), "Python dependencies differ")
    profile_dir = args.job / "profiles"
    require(not profile_dir.exists() and not (args.job / "aggregation_ready.json").exists(), "Use a new run directory")
    started = datetime.now(timezone.utc).isoformat()
    print(f"Verified R12 registration and sample seal. Scoring started {started}", flush=True)
    subprocess.run([sys.executable, str(R10 / "methods/run_profiles.py"),
                    "--samples", *map(str, directories.values()), "--output", str(profile_dir),
                    "--jobs", str(args.jobs), "--mode", "baseline"], check=True)
    summary = read_json(profile_dir / "baseline_summary.json")
    profile = profile_dir / "baseline_profiles.jsonl"
    expected_counts = {key: spec["sample_n"] for key, spec in registration["samples"].items()}
    count = sum(expected_counts.values())
    require(summary["status_counts"] == {"computed": count} and summary["input_records"] == summary["tasks"] == count,
            "Scoring did not finish all inputs")
    require(digest(profile) == summary["result_sha256"], "Profile digest differs from scorer receipt")
    counts = audited_profiles(profile, directories)
    require(counts == expected_counts, "Scoring coverage differs from samples")
    completed = {
        "id": registration["id"], "stage": "AGGREGATION_READY", "counts_by_sample": counts,
        "registration_sha256": args.registration_sha256, "prepared_receipt_sha256": args.input_sha256,
        "scoring_started_utc": started, "scoring_completed_utc": summary["completed_utc"],
        "profiles_sha256": summary["result_sha256"],
        "profile_summary_sha256": digest(profile_dir / "baseline_summary.json"),
        "private_run_seal_sha256": digest(profile_dir / "baseline_run_seal.json"),
        "complete_source_records": count, "complete_record_years": count * 40, "finite_system_scores": count * 160,
        "scoring_runtime": runtime, "observed_event_outcomes": False,
    }
    write_json(args.job / "aggregation_ready.json", completed)
    print(f"{count} complete four-system trajectories passed the integrity check.", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True, type=Path)
    p.add_argument("--registration-sha256", required=True)
    p.add_argument("--input-sha256", required=True)
    p.add_argument("--jobs", default=4, choices=range(1, 5), type=int)
    run(p.parse_args())
