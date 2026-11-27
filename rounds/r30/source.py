"""Acquire only the registered birth fields from the two Colombian open datasets."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode

from rounds.r27.archive_source import digest, private_job, read_json, require, write_json


HERE = Path(__file__).resolve().parent
CONFIG = read_json(HERE / "sources.json")
BIRTH_FIELDS = ("fecha_nacimiento", "hora_nacimiento", "sexo")


def get(url):
    return subprocess.check_output(["curl", "-fsSL", "--proto", "=https", "--connect-timeout", "8",
                                    "--max-time", "60", "--retry", "1", url])


def fields(site):
    period = (site["period_field"],) if "period_field" in site else ()
    return (*BIRTH_FIELDS, *site["area_fields"], *period)


def source_row(row, selected):
    require(set(row) <= set(selected), "The portal returned an unrequested field")
    return {name: row.get(name) or "" for name in selected}


def retrieve(job, format_name, name, site):
    identifier = site["id"]
    portal = CONFIG["portal"]
    metadata_url = f"{portal}/api/views/{identifier}.json"
    selected = fields(site)

    def revision():
        metadata = json.loads(get(metadata_url))
        require(metadata["id"] == identifier and metadata["rowsUpdatedAt"] == site["rows_updated_unix"]
                and metadata["attribution"] == site["publisher"] and metadata["licenseId"] == CONFIG["license_id"],
                f"The registered version, source name or license differs for {name}")
        types = {column["fieldName"]: column["dataTypeName"] for column in metadata["columns"]}
        require(all(types.get(field) == ("calendar_date" if field in BIRTH_FIELDS[:2] else "text")
                    for field in selected), f"The registered field types differ for {name}")
        return metadata["rowsUpdatedAt"]

    before = revision()
    endpoint = f"{portal}/resource/{identifier}.{format_name}"
    query = {"$select": ",".join(selected), "$order": ":id", "$limit": 2500}
    payload = get(f"{endpoint}?{urlencode(query)}")
    if format_name == "csv":
        reader = csv.DictReader(StringIO(payload.decode("utf-8-sig"), newline=""))
        require(reader.fieldnames == list(selected), f"Unexpected CSV columns for {name}")
        parsed = list(reader)
    else:
        parsed = json.loads(payload)
    require(len(parsed) == site["published_rows"] and revision() == before, f"Snapshot changed for {name}")
    canonical = job / f"{name}.jsonl"
    with canonical.open("x", encoding="utf-8") as stream:
        for row in parsed:
            normalized = source_row(row, selected)
            require(all(isinstance(value, str) for value in normalized.values()), f"Unexpected value type for {name}")
            stream.write(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n")
    return {
        "provider": site["publisher"],
        "view_id": identifier,
        "rows_updated_unix": before,
        "projected_fields": list(selected),
        "source_rows": len(parsed),
        "publisher_rows_update_utc": datetime.fromtimestamp(before, timezone.utc).isoformat(),
        "publisher_license_id": CONFIG["license_id"],
        "metadata_url": metadata_url,
        "request": {"endpoint": endpoint, "query": query},
        "transport_sha256": sha256(payload).hexdigest(),
        "private_projection_sha256": digest(canonical),
    }


def fetch(job, format_name):
    job = private_job(job)
    with ThreadPoolExecutor(max_workers=2) as pool:
        submitted = {name: pool.submit(retrieve, job, format_name, name, site)
                     for name, site in CONFIG["sites"].items()}
        receipts = {name: result.result() for name, result in submitted.items()}
    write_json(job / "source_receipt.json", {
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "definition_sha256": digest(HERE / "sources.json"),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "format": format_name,
        "sites": receipts,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--format", choices=("csv", "json"), required=True)
    args = parser.parse_args()
    fetch(args.job, args.format)
