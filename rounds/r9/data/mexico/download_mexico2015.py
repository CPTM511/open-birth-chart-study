#!/usr/bin/env python3
"""Download one pinned official INEGI public natality archive; no login required.

The URL is grounded in the official 2066/4 download catalogue, not an inferred
CSV naming grid. The 2015 release is DBF; the current CSV catalogue starts 2017.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

URL = "https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/2015/natalidad_base_datos_2015_dbf.zip"
SHA256 = "995c451db513f19641c1e28032d0164e3e5a2c5a0b210b49e0754fde15f4f6c7"
SIZE = 39143088


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / "natalidad_base_datos_2015_dbf.zip"
    if target.exists():
        with target.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if target.stat().st_size == SIZE and digest == SHA256:
            print(json.dumps({"status": "verified_existing", "sha256": digest, "bytes": SIZE}))
            return
        raise ValueError("Existing archive differs from pinned input; preserve it for review")
    partial = target.with_suffix(".zip.part")
    sha, count = hashlib.sha256(), 0
    with urllib.request.urlopen(URL, timeout=45) as response, partial.open("wb") as handle:
        status = response.status
        final_url = response.url
        content_type = response.headers.get("content-type")
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            count += len(block)
            if count > 100_000_000:
                raise ValueError("Download exceeded the 100 MB bound")
            handle.write(block)
            sha.update(block)
    if status != 200 or count != SIZE or sha.hexdigest() != SHA256 or not zipfile.is_zipfile(partial):
        raise ValueError("Source response does not match the pinned archive; do not silently replace inputs")
    partial.rename(target)
    receipt = {"url": URL, "final_url": final_url, "status": status, "content_type": content_type,
               "bytes": count, "sha256": sha.hexdigest(), "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    (args.output_dir / "download_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
