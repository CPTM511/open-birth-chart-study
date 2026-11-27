"""Download the registered municipal-archive images to a private directory."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re
import subprocess

from rounds.r27.archive_source import digest, private_job, read_json, require, write_json


HERE = Path(__file__).resolve().parent
DOMAIN = "https://recherches.archives-lyon.fr"
SEED = "OBS-R37-LYON-1901-V1"


def get_file(url, path):
    require(url.startswith(DOMAIN + "/iiif/ark:/18811/"), "Unexpected publication domain or collection")
    if not path.is_file():
        partial = path.with_suffix(".part")
        subprocess.run(["curl", "-fsSL", "--retry", "2", "--max-time", "40",
                        "-o", str(partial), url], check=True)
        partial.replace(path)


def selected_positions(number, pages):
    eligible = range(3, pages - 1)
    require(len(eligible) >= 3, "Too few frames in the identified volume")
    by_digest = sorted(eligible, key=lambda pos: sha256(f"{SEED}|{number}|{pos}".encode()).digest())
    return sorted(by_digest[:3])


def image_list(archive, prefix):
    require(archive["type"] == "Manifest" and archive["id"] == prefix + "/group/0/manifest.json",
            "The public manifest identifies another record or group")
    images = []
    for position, canvas in enumerate(archive["items"], 1):
        label, = canvas["label"]["fr"]
        page, = canvas["items"]
        annotation, = page["items"]
        body = annotation["body"]
        require(annotation["target"] == canvas["id"] and body["format"] == "image/jpeg"
                and label == f"Image n°{position}", f"Unstable archive labels at position {position}")
        url = body["id"]
        require(re.fullmatch(re.escape(prefix) + r"/[0-9a-f-]{36}/full/max/0/default\.jpg", url) is not None,
                "The image URL points to a different register or format")
        images.append((canvas["id"], label, url))
    require(len({item[2] for item in images}) == len(images), "Repeated frame in publisher listing")
    return images


def acquire_volume(job, source):
    cote, info = source
    require(re.fullmatch(r"2E/[0-9]+", cote) is not None, "Invalid official catalogue identifier")
    number = int(cote.split("/")[1])
    pattern = re.escape(DOMAIN) + r"/ark:/18811/([0-9a-z]{12})"
    match = re.fullmatch(pattern, info["notice"])
    require(match is not None, "Unexpected archival notice identity")
    prefix = f"{DOMAIN}/iiif/ark:/18811/{match[1]}"
    require(info["manifest"] == prefix + "/manifest.json", "Incorrect catalogue manifest")
    manifest = job / "metadata" / f"{number}.json"
    get_file(info["manifest"], manifest)
    images = image_list(read_json(manifest), prefix)
    selected = []
    for position in selected_positions(number, len(images)):
        canvas, label, url = images[position - 1]
        local_name = f"{number}-{position:03}.jpg"
        destination = job / "scans" / local_name
        get_file(url, destination)
        with destination.open("rb") as stream:
            require(stream.read(3) == b"\xff\xd8\xff", f"Invalid JPEG: {local_name}")
        selected.append({"position": position, "canvas": canvas, "label": label, "image": url,
                         "record_page": f"{info['notice']}/{url.split('/')[-5]}", "local_name": local_name,
                         "sha256": digest(destination)})
    order = json.dumps(images, ensure_ascii=False, separators=(",", ":")).encode()
    return cote, {
        **info, "source_order_sha256": sha256(order).hexdigest(), "scan_count": len(images),
        "sample_frame_count": len(images) - 4, "selected": selected,
    }


def get_sample(job, output):
    for name in ("metadata", "scans"):
        (job / name).mkdir(mode=0o700, exist_ok=True)
    index = read_json(HERE / "volumes.json")
    require(len(index["volumes"]) == 13, "Source volume count differs from the preregistration")
    with ThreadPoolExecutor(max_workers=4) as pool:
        documents = dict(pool.map(lambda volume: acquire_volume(job, volume), index["volumes"].items()))
    selected = sum(len(volume["selected"]) for volume in documents.values())
    require(selected == 39, "Incomplete registered scan sample")
    write_json(output, {
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "volume_index_sha256": digest(HERE / "volumes.json"),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "archive_attribution": index["archive_attribution"],
        "eligible_scan_positions": sum(volume["sample_frame_count"] for volume in documents.values()),
        "scans_selected": selected,
        "volumes": documents,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    get_sample(private_job(args.job), args.output)
