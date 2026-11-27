"""Retrieve the exact official R25 snapshot into a local directory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile

HERE = Path(__file__).resolve().parent


def download(directory: Path, item: tuple[str, dict]) -> None:
    name, record = item
    dst = directory / name
    if dst.exists():
        if sha256(dst.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Existing file differs from the frozen release: {name}")
        return
    with NamedTemporaryFile(dir=directory, delete=False) as peer:
        temp = Path(peer.name)
    try:
        subprocess.run(
            ["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "60",
             "--output", str(temp), record["url"]], check=True,
        )
        if sha256(temp.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Publisher bytes differ from the frozen release: {name}")
        os.replace(temp, dst)
    finally:
        temp.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(exist_ok=True, parents=True)
    snapshot = json.loads((HERE / "source-snapshot.json").read_text())
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda item: download(args.directory, item), snapshot["files"].items()))
    print(f"Verified {len(snapshot['files'])} publisher files.")


if __name__ == "__main__":
    main()
