"""Registration and pre-scoring input receipts for R49."""

from pathlib import Path
import subprocess

from rounds.r45.common import ROOT, R10, digest, load_source, read_json, require, write_json
from rounds.r46.common import GROUPS, private, verify_files


HERE = Path(__file__).resolve().parent
REGISTRATION = "1d8e59ea9e1d5b22ce5b253f3c64ec0246cfaae5"


def protocol():
    for name in ("protocol.json", "REGISTRATION.zh.md"):
        original = subprocess.check_output(
            ["git", "show", f"{REGISTRATION}:rounds/r49/{name}"], cwd=ROOT
        )
        require((HERE / name).read_bytes() == original, f"R49 registration changed: {name}")
    settings = read_json(HERE / "protocol.json")
    require(digest(ROOT / "rounds/r46/results.json") == settings["r46_aggregate_sha256"],
            "R46 published aggregate changed")
    return settings


def input_receipt(job, group):
    local = job / group / "input_seal.json"
    published = read_json(HERE / "seals" / f"{group}.json")
    require(published["input_seal_sha256"] == digest(local), "R49 input commitment differs")
    observed = read_json(local)
    require(published == dict(observed, input_seal_sha256=digest(local))
            and observed["registration"] == REGISTRATION and observed["group"] == group,
            "R49 published input receipt differs from its protected source")
    return published


def inputs(job, group):
    seal = input_receipt(job, group)
    require(seal["records"] > 0, f"No admissible {group} sample")
    sample = job / group / "sample"
    verify_files(sample, seal["sha256"])
    rows, manifest = load_source(sample)
    require(len(rows) == seal["records"]
            and all(int(row["birth_local"][:4]) == int(group[2:]) for row in rows)
            and manifest["eligible_frame_N"] == seal["eligible_frame_N"], "Wrong R49 input frame")
    return rows, manifest, seal
