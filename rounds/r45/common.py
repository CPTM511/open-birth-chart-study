"""Shared R45 configuration, file seals and frozen scoring adapters."""

from fractions import Fraction
from hashlib import file_digest
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
R10 = ROOT / "rounds/r10"
REGISTRATION = "b0b2db959c52d56151635568615afab742bd22f6"
FILES = ("birth_inputs.jsonl", "birth_metadata.jsonl", "sampling_manifest.json")

sys.path.insert(0, str(R10 / "methods"))
from r10_io import load_source


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def registered():
    for name in ("protocol.json", "REGISTRATION.zh.md"):
        path = HERE / name
        old = subprocess.check_output(["git", "show", f"{REGISTRATION}:rounds/r45/{name}"], cwd=ROOT)
        require(path.read_bytes() == old, f"Modified research registration file {name}")
    return read_json(HERE / "protocol.json")


def fractions(rows):
    return [Fraction(row["N_h"], row["n_h"]) for row in rows]


def source_seal(directory):
    rows, manifest = load_source(directory)
    require(sum(fractions(rows)) == manifest["eligible_frame_N"], "Invalid exact sampling weight")
    return {
        "records": len(rows),
        "eligible_frame_N": manifest["eligible_frame_N"],
        "strata": len(manifest["strata"]),
        "sha256": {name: digest(directory / name) for name in FILES},
    }
