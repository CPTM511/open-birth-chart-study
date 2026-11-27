"""Check the earliest and latest frozen sampling ranks in each slot using fresh engine state."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys

R10 = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R10 / "methods"))
from r10_io import jsonlines, load_source, sha256
from run_profiles import init_worker, score_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--aggregation-ready", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    release = json.loads(args.aggregation_ready.read_bytes())
    config = json.loads(args.config.read_bytes())
    if release["stage"] != "AGGREGATION_READY" or args.output.exists():
        raise ValueError("Require a completed replay and a new output")
    selected = {}
    profile_files = set()
    for target in config["targets"]:
        cohort, _ = load_source(target["sample_dir"])
        ordered = sorted(cohort, key=lambda r: (r["sampling_sha256"], r["study_id"]))
        for row in (ordered[0], ordered[-1]):
            selected[row["study_id"]] = row
        profile_files.update(target["profile_files"])
    if len(selected) != 12 or len(profile_files) != 1:
        raise ValueError("Expected two prespecified records per cohort and one combined profile file")
    source = Path(profile_files.pop())
    digest = sha256(source)
    if digest != release["profile_file_sha256"]:
        raise ValueError("Completed profile digest changed")
    stored = {p["study_id"]: p for p in jsonlines(source) if p["study_id"] in selected}
    if set(stored) != set(selected):
        raise ValueError("Selected review profiles missing")
    # A new process per record avoids shared engine state from the 12,000-record execution.
    ctx = multiprocessing.get_context("spawn")
    for row in selected.values():
        with ProcessPoolExecutor(max_workers=1, mp_context=ctx, initializer=init_worker) as pool:
            recomputed = pool.submit(score_record, (row, "base", 0, None)).result()
        if recomputed["status"] != "computed" or recomputed != stored[row["study_id"]]:
            raise ValueError("Fresh-worker replay differs from a completed profile")
    report = {"status": "passed", "source_profile_sha256": digest, "config_sha256": sha256(args.config),
              "review_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "selection": "Smallest and largest prespecified sampling rank in each of six slots; ID tie-break.",
              "distinct_records_replayed": len(selected), "record_years_replayed": 40 * len(selected),
              "primary_scores_replayed": 160 * len(selected), "entire_profile_objects_equal": True,
              "scope": "Fresh Linux worker per case, including a new Ziwei engine. Uses the same locked engines and birth inputs."}
    with args.output.open("x", encoding="utf-8") as dest:
        dest.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
