"""Registered paths and integrity checks shared by the R12 stages."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
R10 = ROOT / "rounds/r10"
R11 = ROOT / "rounds/r11"
REPLAY = R10 / "independent_replay"
sys.path[:0] = [str(R11), str(R10 / "methods")]

from calendar_controls import digest, read_json, require, write_json
from r10_io import load_source


def read_registration(sha):
    path = HERE / "protocol.json"
    require(digest(path) == sha, "Supply the registration digest verified on GitHub")
    registration = read_json(path)
    for file, expected in registration["file_sha256"].items():
        require(digest(ROOT / file) == expected, "Registered data or code changed: " + file)
    return registration


def checked_samples(job, registration, registration_sha, input_sha):
    receipt_path = job / "prepared/receipt.json"
    require(digest(receipt_path) == input_sha, "Supply the sealed sampling receipt verified on GitHub")
    receipt = read_json(receipt_path)
    require(receipt["status"] == "two_source_passes_match" and receipt["registration_sha256"] == registration_sha,
            "Wrong or unverified sampling receipt")
    require(list(receipt["samples"]) == list(registration["samples"]), "Missing or reordered sample")
    directories = {}
    for slot, spec in registration["samples"].items():
        directory = job / "prepared" / slot
        evidence = receipt["samples"][slot]
        for filename, expected in evidence["private_file_sha256"].items():
            require(digest(directory / filename) == expected, "Sealed input changed: " + slot + "/" + filename)
        records, manifest = load_source(directory)
        require(len(records) == spec["sample_n"] and manifest["eligible_frame_N"] == spec["frame_N"],
                "Sample or eligible frame differs: " + slot)
        require(all(row["birth_country"] == "MX" and int(row["birth_local"][:4]) == spec["birth_year"]
                    for row in records), "Sample contains the wrong cohort: " + slot)
        directories[slot] = directory
    return directories


def checked_historical(r10_job):
    registration = read_json(REPLAY / "registration.json")
    published = read_json(REPLAY / "results/release.json")
    prepared = read_json(REPLAY / "prepared_receipt.json")
    marker = r10_job / "aggregation_ready.json"
    require(digest(marker) == published["artifact_sha256"]["aggregation_ready.json"], "Wrong R10 completion receipt")
    for name, expected in registration["reference_files_sha256"].items():
        require(digest(r10_job / name) == expected, "Fixed reference mismatch: " + name)
    early = r10_job / "prepared/samples/mexico2020"
    design = next(g for g in prepared["groups"] if g["slot"] == "mexico2020")
    for name, key in (("birth_inputs.jsonl", "input_sha256"), ("birth_metadata.jsonl", "metadata_used_sha256"),
                      ("sampling_manifest.json", "manifest_used_sha256")):
        require(digest(early / name) == design[key], "R10 Mexico 2020 sample differs: " + name)
    profiles = r10_job / "profiles/baseline_profiles.jsonl"
    require(digest(profiles) == read_json(marker)["profile_file_sha256"], "Wrong R10 target profiles")
    return {
        "brazil2006": (r10_job / "reference/brazil2006", r10_job / "reference/full-frozen-r8-baseline_profiles.jsonl"),
        "mexico2020_early": (early, profiles),
    }
