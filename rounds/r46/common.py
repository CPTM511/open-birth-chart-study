"""R46 registration and commitments."""

from pathlib import Path
import subprocess

from rounds.r45.common import ROOT, R10, digest, read_json, require, write_json

HERE = Path(__file__).resolve().parent
REGISTRATION = "f7ce5f927111b5e50ff6496de3b929e941fc00f5"
GROUPS = ("br1999", "mx1999", "br2009", "mx2009")


def protocol():
    for name in ("REGISTRATION.zh.md", "protocol.json"):
        original = subprocess.check_output(["git", "show", f"{REGISTRATION}:rounds/r46/{name}"], cwd=ROOT)
        require((HERE / name).read_bytes() == original, "R46 registration was altered")
    spec = read_json(HERE / "protocol.json")
    require(digest(ROOT / "rounds/r45/results.json") == spec["r45_aggregate_sha256"], "Wrong public R45 results")
    return spec


def private(path):
    require(path.is_dir() and path.stat().st_mode & 0o077 == 0
            and not path.resolve().is_relative_to(ROOT), "Use a restricted folder outside the checkout")
    return path


def verify_files(directory, expected):
    require(all(digest(directory/name) == sha for name, sha in expected.items()), "Source seal mismatch")
