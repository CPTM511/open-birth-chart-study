"""Validate the independent registration, run the frozen baseline, then release aggregation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys

from prepare_inputs import HERE, R10, ROOT, REPLAY_ID, check, historical_records, jsonlines, load_source, sha256, write_json


def check_prepared(registry):
    available, _ = historical_records()
    check(registry["id"] == REPLAY_ID, "Unexpected independent registration")
    for filename, digest in registry["files_sha256"].items():
        check(sha256(ROOT / filename) == digest, "Registration dependency mismatch: " + filename)
    prepared = Path("prepared")
    check(sha256(prepared / "receipt.json") == registry["prepared_receipt_sha256"], "Prepared release differs")
    config = json.loads((HERE / "analysis_config.json").read_bytes())
    check(config["reference"] == {"sample_dir": "reference/brazil2006",
          "profile_files": ["reference/full-frozen-r8-baseline_profiles.jsonl"]}, "Reference configuration differs")
    for path, digest in registry["reference_files_sha256"].items():
        check(sha256(path) == digest, "Frozen reference file mismatch: " + path)
    groups = json.loads((prepared / "receipt.json").read_bytes())["groups"]
    check([g["slot"] for g in groups] == list(available) == [t["slot"] for t in config["targets"]],
          "Public source decisions, registered configuration and prepared order differ")
    expected, sample_dirs = {}, []
    for group, target in zip(groups, config["targets"], strict=True):
        slot = target["slot"]
        sample_dir = Path(target["sample_dir"])
        check(group["input_sha256"] == available[slot]["input_sha256"] and
              group["input_sha256"] == sha256(sample_dir / "birth_inputs.jsonl"), "Frozen model input differs: " + slot)
        check(sha256(sample_dir / "birth_metadata.jsonl") == group["metadata_used_sha256"], "Metadata changed: " + slot)
        check(sha256(sample_dir / "sampling_manifest.json") == group["manifest_used_sha256"], "Manifest changed: " + slot)
        check(sha256(target["input_seal"]) == group["seal_sha256"], "Input seal changed: " + slot)
        rows, manifest = load_source(sample_dir)
        seal = json.loads(Path(target["input_seal"]).read_bytes())
        check(manifest == seal["input_manifest"] and seal["id"] == REPLAY_ID and seal["slot"] == slot, "Seal mismatch")
        check(seal["historical_metadata_sha256"] == available[slot]["metadata_sha256"], "Historical commitment mismatch")
        check(len(rows) == available[slot]["sample_n"] == 2000, "Group size")
        for r in rows:
            ident = r["study_id"]
            check(ident not in expected, "Repeated study identifier")
            expected[ident] = (slot, r["source"], r["chart_input_key"], r["calendar_years"])
        sample_dirs.append(str(sample_dir))
    check(len(expected) == 12000, "Incomplete prepared release")
    return expected, sample_dirs


def run(registration_sha256, jobs):
    path = HERE / "registration.json"
    check(sha256(path) == registration_sha256, "Supply the registration digest verified on GitHub")
    registry = json.loads(path.read_bytes())
    expected, sample_dirs = check_prepared(registry)
    profiles = Path("profiles")
    check(not profiles.exists() and not Path("aggregation_ready.json").exists(), "Use a new run directory")
    start = datetime.now(timezone.utc).isoformat()
    print(json.dumps({"stage": "all_independent_replay_inputs_verified", "records": len(expected), "started_utc": start}), flush=True)
    subprocess.run([sys.executable, str(R10/"methods/run_profiles.py"), "--samples", *sample_dirs,
                    "--output", str(profiles), "--jobs", str(jobs), "--mode", "baseline"], check=True)
    summary = json.loads((profiles / "baseline_summary.json").read_bytes())
    profile_file = profiles / "baseline_profiles.jsonl"
    check(summary["status_counts"] == {"computed": 12000} and summary["input_records"] == summary["tasks"] == 12000,
          "Incomplete baseline run")
    check(summary["result_sha256"] == sha256(profile_file), "Completed file digest failed")
    counts = Counter()
    for profile in jsonlines(profile_file):
        slot, source, key, years = expected.pop(profile["study_id"])
        check(profile["variant"] == "base" and profile["status"] == "computed", "Incomplete base profile")
        check(profile["source"] == source and profile["chart_input_key"] == key and profile["calendar_years"] == years,
              "Profile differs from registered record, source or age years")
        scores = profile["primary_scores"]
        check(len(scores) == len(years) == 40 and all(len(row) == 4 for row in scores), "Incomplete four-system trajectory")
        check(all(math.isfinite(x) and 0 <= x <= 1 for row in scores for x in row), "Out-of-scope model score")
        counts[slot] += 1
    check(not expected and len(counts) == 6 and set(counts.values()) == {2000}, "Incomplete slot coverage")
    evidence = {"id": REPLAY_ID, "stage": "AGGREGATION_READY", "registration_sha256": registration_sha256,
                "prepared_receipt_sha256": registry["prepared_receipt_sha256"], "started_utc": start,
                "scoring_completed_utc": summary["completed_utc"], "validated_utc": datetime.now(timezone.utc).isoformat(),
                "counts_by_slot": dict(counts), "distinct_records": 12000, "ages_per_record": 40, "systems": 4,
                "record_years": 480000, "finite_system_scores": 1920000, "profile_file_sha256": summary["result_sha256"],
                "profile_summary_sha256": sha256(profiles/"baseline_summary.json"),
                "profile_run_seal_sha256": sha256(profiles/"baseline_run_seal.json"),
                "historical_mexican_metadata_files_recovered": 0, "external_outcomes_used": False}
    write_json(Path("aggregation_ready.json"), evidence)
    print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    run(args.registration_sha256, args.jobs)
