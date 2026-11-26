"""Download three pinned official geography/timezone reference sources."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--catalog", type=Path, default=Path(__file__).with_name("geo_source_catalog.json"))
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source in json.loads(args.catalog.read_text()):
        record = {"filename": source["filename"], "url": source["url"], "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
        with urllib.request.urlopen(source["url"], timeout=45) as response:
            body = response.read(source["max_bytes"] + 1)
            if len(body) > source["max_bytes"]:
                raise RuntimeError("Source exceeds byte cap: " + source["filename"])
            digest = hashlib.sha256(body).hexdigest()
            if digest != source["expected_sha256"]:
                raise RuntimeError("Upstream source changed; review as a new version: " + source["filename"])
            (args.out_dir / source["filename"]).write_bytes(body)
            record.update(http_status=response.status, bytes=len(body), sha256=digest)
        manifest.append(record)
        print(record["filename"], record["bytes"])
    with tarfile.open(args.out_dir / "tzdata2026c.tar.gz") as archive:
        for member in ("northamerica", "zone1970.tab", "zone.tab", "version"):
            (args.out_dir / member).write_bytes(archive.extractfile(member).read())
    (args.out_dir / "geo_reproduction_retrievals.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
