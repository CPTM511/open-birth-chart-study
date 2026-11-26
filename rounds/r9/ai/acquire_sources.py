"""Acquire bounded public primary sources. Python standard library only.

Raw website snapshots stay outside the repository. This script does not call
model APIs, query personal records, or estimate any AI-risk probability.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--catalog", type=Path, default=Path(__file__).with_name("source_catalog.json"))
    args = ap.parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source in json.loads(args.catalog.read_text()):
        row = {"source_id": source["source_id"], "requested_url": source["url"],
               "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "read_cap_bytes": source["max_bytes"]}
        try:
            request = urllib.request.Request(source["url"], headers={"User-Agent": "OpenBirthChartStudy-R9/0.1 (public-data-research)"})
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(source["max_bytes"] + 1)
                complete = len(body) <= source["max_bytes"]
                body = body[:source["max_bytes"]]
                filename = source["filename"]
                (args.raw_dir / filename).write_bytes(body)
                row.update(status_code=response.status, final_url=response.url,
                           content_type=response.headers.get("Content-Type"),
                           bytes=len(body), sha256=hashlib.sha256(body).hexdigest(),
                           snapshot_complete=complete, private_snapshot_filename=filename)
        except Exception as error:
            row.update(status_code=getattr(error, "code", None), error_type=type(error).__name__, error=str(error)[:250])
        manifest.append(row)
        print(source["source_id"], row.get("status_code"), row.get("bytes"))
    (args.raw_dir / "http_retrievals.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
