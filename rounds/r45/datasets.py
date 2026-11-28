"""Resolve sealed R10/R13/R15 inputs and the new R45 private run."""

from dataclasses import dataclass
from pathlib import Path

from .common import HERE, R10, ROOT, REGISTRATION, digest, load_source, read_json, require, source_seal


@dataclass(frozen=True)
class Dataset:
    sample: Path
    profile: Path
    expected_hash: str | None
    years: tuple[int, ...]
    country: str

    def includes(self, row):
        return int(row["birth_local"][:4]) in self.years

    def births(self):
        rows, _ = load_source(self.sample)
        require(all(row["birth_country"] == self.country for row in rows), "Wrong data source country")
        return [row for row in rows if self.includes(row)]


def add_paths(parser):
    for name in ("job", "r10-job", "r13-job", "r15-job"):
        parser.add_argument("--" + name, required=True, type=Path)


def check_inputs(path, commits):
    for name, value in commits.items():
        require(digest(path / name) == value, "Private input differs from published commitment")


def datasets(args, cfg):
    replay = R10 / "independent_replay"
    reference = read_json(replay / "registration.json")["reference_files_sha256"]
    check_inputs(args.r10_job, reference)

    old_mx = args.r10_job / "prepared/samples/mexico_2000s"
    old_receipt = next(row for row in read_json(replay / "prepared_receipt.json")["groups"]
                       if row["slot"] == "mexico_2000s")
    check_inputs(old_mx, {"birth_inputs.jsonl": old_receipt["input_sha256"],
                         "birth_metadata.jsonl": old_receipt["metadata_used_sha256"],
                         "sampling_manifest.json": old_receipt["manifest_used_sha256"]})
    old_hash = read_json(replay / "results/baseline_summary.json")["result_sha256"]
    r13, r15 = args.r13_job, args.r15_job
    for prior, folder in (("r13", r13), ("r15", r15)):
        check_inputs(folder / "sample", read_json(ROOT / f"rounds/{prior}/INPUT_SEAL.json")["private_input_sha256"])
    r13_profile = r13 / "profiles/baseline_profiles.jsonl"
    r13_hash = read_json(ROOT / "rounds/r13/results.json")["complete_run"]["baseline_sha256"]
    r15_hash = read_json(ROOT / "rounds/r15/results.json")["baseline_sha256"]

    inventory = {
        "reference": Dataset(args.r10_job / "reference/brazil2006",
                             args.r10_job / "reference/full-frozen-r8-baseline_profiles.jsonl",
                             reference["reference/full-frozen-r8-baseline_profiles.jsonl"], (2006,), "BR"),
        "br1999": Dataset(r15 / "sample", r15 / "profiles/baseline_profiles.jsonl", r15_hash, (1999,), "BR"),
        "mx1999": Dataset(r13 / "sample", r13_profile, r13_hash, (1999,), "MX"),
        "mx1990_1998": Dataset(r13 / "sample", r13_profile, r13_hash, tuple(range(1990, 1999)), "MX"),
        "mx2009_r10": Dataset(old_mx, args.r10_job / "profiles/baseline_profiles.jsonl", old_hash, (2009,), "MX"),
    }
    published = read_json(HERE / "SOURCE_SEALS.json")
    require(published["registration"] == REGISTRATION, "Published input seal uses another design")
    for group in ("br2009", "mx2009"):
        folder = args.job / group
        seal = read_json(folder / "input_seal.json")
        require(seal["registration"] == REGISTRATION and seal["profile_inputs_sealed"], "New input seal differs")
        require(digest(folder / "input_seal.json") == published["draws"][group]["input_seal_sha256"],
                "New input seal differs from publication")
        check_inputs(folder / "sample", seal["sha256"])
        inventory[group] = Dataset(folder / "sample", folder / "scores/base.jsonl",
                                   None, (2009,), cfg["groups"][group]["country"])
    return inventory


def verify_profile(item, job, group):
    if item.expected_hash is not None:
        require(digest(item.profile) == item.expected_hash, "Earlier frozen profile differs")
        return
    seal = read_json(job / group / "scores/base_receipt.json")
    require(seal["registration"] == REGISTRATION and seal["group"] == group
            and seal["mode"] == "base" and seal["source"] == source_seal(item.sample)
            and seal["score_sha256"] == digest(item.profile), "New baseline profile / scoring receipt differs")
