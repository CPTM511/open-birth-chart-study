"""Verify historical releases while allowing a maintained repository homepage."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
R8_RELEASE = "210bb7bdab85a9f3672f19241e9ef66eb22021a2"
R9_RELEASE = "8c74a1883404002132dfa82d218a69106c344369"
VERIFIER = Path("rounds/r9/verification/verify_release.py")
MANIFESTS = (
    Path("rounds/r9/verification/r8_baseline_manifest.json"),
    Path("rounds/r9/release_manifest.json"),
    Path("rounds/r9/public_freeze_receipt.json"),
)
HISTORICAL_PATHS = {
    Path("README.md"): R8_RELEASE,
    Path("README.zh.md"): R8_RELEASE,
    Path(".github/workflows/r9-checks.yml"): R9_RELEASE,
}


def historical_bytes(commit: str, path: Path) -> bytes:
    try:
        return subprocess.check_output(["git", "show", f"{commit}:{path.as_posix()}"], cwd=ROOT)
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Could not read {path} at {commit}. Use a checkout with full release history.") from error


def main() -> None:
    paths = set(MANIFESTS)
    for manifest in MANIFESTS:
        original = historical_bytes(R9_RELEASE, manifest)
        if (ROOT / manifest).read_bytes() != original:
            raise SystemExit(f"Frozen release manifest differs: {manifest}")
        paths.update(Path(item["path"]) for item in json.loads(original)["files"])
    if not HISTORICAL_PATHS.keys() <= paths or VERIFIER not in paths:
        raise SystemExit("The frozen manifests do not cover the expected release files.")
    if (ROOT / VERIFIER).read_bytes() != historical_bytes(R9_RELEASE, VERIFIER):
        raise SystemExit(f"Frozen release verifier differs: {VERIFIER}")
    paths.update(path.relative_to(ROOT) for path in (ROOT / "rounds/r9").rglob("*.py"))

    with TemporaryDirectory(prefix="obc-release-verification-") as directory:
        view = Path(directory)
        for path in sorted(paths):
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit(f"Invalid frozen release path: {path}")
            destination = view / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            if path in HISTORICAL_PATHS:
                destination.write_bytes(historical_bytes(HISTORICAL_PATHS[path], path))
            else:
                copyfile(ROOT / path, destination)
        print("Verifying two archived R8 homepages and the archived R9 workflow. "
              "All remaining protected bytes come from the current checkout.", flush=True)
        subprocess.run([sys.executable, str(view / VERIFIER)], cwd=view, check=True)


if __name__ == "__main__":
    main()
