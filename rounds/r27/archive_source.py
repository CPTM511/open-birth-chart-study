"""Fetch the registered IIIF sample to a private directory and seal its provenance."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256, file_digest
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = "OBS-R27-AMSTERDAM-1901-V1"
DOMAIN = "https://id.archief.amsterdam/"
POSITIONS_PER_VOLUME = 3


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, obj):
    serialized = json.dumps(obj, indent=2, allow_nan=False, ensure_ascii=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(serialized)


def private_job(path):
    directory = path.resolve()
    require(directory != ROOT and ROOT not in directory.parents, "Use a private directory outside the checkout")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(directory.stat().st_mode & 0o077 == 0, "Use a directory readable only by its custodian")
    return directory


def positions(volume, count):
    interior = range(3, count - 1)
    require(len(interior) >= POSITIONS_PER_VOLUME, "Too few interior images in the source volume")
    ordered = sorted(interior, key=lambda n: sha256(f"{SEED}|{volume}|{n}".encode()).digest())
    return sorted(ordered[:POSITIONS_PER_VOLUME])


def fetch(url, path):
    require(url.startswith(DOMAIN), "The source supplied an unexpected archive host")
    if not path.exists():
        partial = path.with_suffix(path.suffix + ".part")
        subprocess.run(["curl", "-fsSL", "--retry", "2", "--max-time", "35", "-o", str(partial), url], check=True)
        partial.replace(path)


def volume_receipt(job, item):
    number, identifier = item
    api = f"{DOMAIN}resources/records/media/{identifier}/iiif/3/"
    metadata = job / "metadata"
    collection_path = metadata / f"{number}-collection.json"
    fetch(api + "collection.json", collection_path)
    members = read_json(collection_path)["items"]
    require(bool(members), f"No public manifests in volume {number}")
    pages = []
    for index, member in enumerate(members):
        url = member["id"]
        require(url in {api + "manifest.json", api + f"manifest/{index}.json"}, "Unexpected manifest order")
        manifest = metadata / f"{number}-{index}.json"
        fetch(url, manifest)
        document = read_json(manifest)
        require(document["id"] == url, "Wrong manifest returned")
        for canvas in document["items"]:
            body = canvas["items"][0]["items"][0]["body"]
            pages.append((canvas["id"], body["id"], canvas["label"]["none"][0]))
    require(len({page[0] for page in pages}) == len(pages), f"Repeated image canvas in volume {number}")
    selected = []
    for position in positions(number, len(pages)):
        _, url, label = pages[position - 1]
        name = f"{number}-{position:03d}.jpg"
        destination = job / "scans" / name
        fetch(url, destination)
        with destination.open("rb") as stream:
            require(stream.read(3) == b"\xff\xd8\xff", f"Image download is incomplete or invalid: {name}")
        selected.append({"position": position, "local_name": name, "iiif_image": url, "archival_scan": label,
                         "sha256": digest(destination)})
    pages_encoded = json.dumps(pages, ensure_ascii=False, separators=(",", ":")).encode()
    return number, {
        "inventory_id": identifier,
        "iiif_collection": api + "collection.json",
        "manifest_count": len(members),
        "scans_total": len(pages),
        "scans_in_frame": len(pages) - 4,
        "ordered_canvas_metadata_sha256": sha256(pages_encoded).hexdigest(),
        "selected": selected,
    }


def run(job, output):
    for folder in ("metadata", "scans"):
        (job / folder).mkdir(mode=0o700, exist_ok=True)
    catalog = read_json(HERE / "volumes.json")
    volumes = catalog["volumes"]
    require(list(volumes) == [str(n) for n in range(4686, 4700)], "Volume inventory differs from registration")
    with ThreadPoolExecutor(max_workers=4) as pool:
        snapshots = dict(pool.map(lambda row: volume_receipt(job, row), volumes.items()))
    write_json(output, {
        "archive": catalog["archive"], "fonds": catalog["fonds"], "year": catalog["year"],
        "catalog_record": catalog["catalog_record"], "seed": SEED,
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "receipt_created_utc": datetime.now(timezone.utc).isoformat(),
        "scans_in_frame_total": sum(row["scans_in_frame"] for row in snapshots.values()),
        "scans_selected_total": sum(len(row["selected"]) for row in snapshots.values()),
        "volumes": snapshots,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(private_job(args.job), args.output)
