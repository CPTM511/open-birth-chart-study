"""Re-score fixed sampling-rank extrema in isolated Linux workers."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

from study import checked_samples, digest, load_source, read_json, read_registration, require, write_json
from r10_io import jsonlines
from run_profiles import init_worker, score_record


def check(args):
    registration = read_registration(args.registration_sha256)
    samples = checked_samples(args.job, registration, args.registration_sha256, args.input_sha256)
    marker = read_json(args.job / "aggregation_ready.json")
    require(marker["stage"] == "AGGREGATION_READY", "Require a complete run")
    baseline = args.job / "profiles/baseline_profiles.jsonl"
    checksum = digest(baseline)
    require(checksum == marker["profiles_sha256"], "Profile file changed")
    chosen = {}
    for path in samples.values():
        rows, _ = load_source(path)
        ordered = sorted(rows, key=lambda row: (row["sampling_sha256"], row["study_id"]))
        for row in (ordered[0], ordered[-1]):
            chosen[row["study_id"]] = row
    stored = {p["study_id"]: p for p in jsonlines(baseline) if p["study_id"] in chosen}
    require(len(stored) == len(chosen) == 6, "Expected two unique profiles per new sample")
    ctx = get_context("spawn")
    for key, row in chosen.items():
        with ProcessPoolExecutor(max_workers=1, mp_context=ctx, initializer=init_worker) as pool:
            computed = pool.submit(score_record, (row, "base", 0, None)).result()
        require(computed["status"] == "computed" and computed == stored[key], "Fresh scoring worker differs")
    write_json(args.output, {"status": "passed", "profile_file_sha256": checksum,
                             "entire_profile_objects_equal": 6, "record_years_recomputed": 240,
                             "system_year_scores_recomputed": 960,
                             "selection": "Lowest and highest sampling rank in each new group, with study ID tie-break.",
                             "scope": "Fresh Linux process and R10 engines for each selected record."})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True, type=Path)
    p.add_argument("--registration-sha256", required=True)
    p.add_argument("--input-sha256", required=True)
    p.add_argument("--output", required=True, type=Path)
    check(p.parse_args())
