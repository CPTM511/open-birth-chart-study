#!/usr/bin/env python3
"""Reread selected birth fields directly from the pinned original DBF archive."""
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile
from zoneinfo import ZoneInfo
from audit_mexico2015 import dbf_header, BIRTH_FIELDS, EXPECTED_SHA256


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--sample-dir", type=Path, required=True)
    args = ap.parse_args()
    with args.archive.open("rb") as f:
        assert hashlib.file_digest(f, "sha256").hexdigest() == EXPECTED_SHA256
    metadata = [json.loads(x) for x in (args.sample_dir / "birth_metadata.jsonl").read_text().splitlines()]
    models = {r["study_id"]: r for r in map(json.loads, (args.sample_dir / "birth_inputs.jsonl").read_text().splitlines())}
    manifest = json.loads((args.sample_dir / "sampling_manifest.json").read_text())
    selected = {int(row["source_row_id"]): row for row in metadata}
    assert len(selected) == len(metadata) == len(models) == manifest["sample_n"]
    errors, checked = [], 0
    with zipfile.ZipFile(args.archive) as z, z.open("NACIM15.dbf") as f:
        count, width, fields, encoding = dbf_header(f)
        for ordinal in range(1, count + 1):
            raw = f.read(width)
            if len(raw) != width:
                raise ValueError("Truncated source")
            if ordinal not in selected:
                continue
            r = {key: int(raw[fields[key][0]:fields[key][0] + fields[key][1]].decode(encoding).strip()) for key in BIRTH_FIELDS}
            expected_local = datetime(r["ANO_NAC"], r["MES_NACIM"], r["DIA_NAC"], r["HORA_NAC"], r["MINUTO_NAC"]).isoformat()
            expected_sex = {1: "M", 2: "F"}[r["SEXO"]]
            expected_geo = f'{r["ENT_OCURR"]:02}{r["MUN_OCURR"]:03}{r["LOC_OCURR"]:04}'
            m = selected[ordinal]
            tests = {
                "source_not_deleted": raw[0:1] == b" ",
                "birth_local": m["birth_local"] == expected_local,
                "sex": m["sex_resolved"] == expected_sex,
                "locality_code": m["source_cvegeo_2015"] == expected_geo,
                "source_id": m["source_id"] == f"INEGI-NACIM15-{ordinal:08d}",
                "model_metadata_agreement": all(m[k] == v for k, v in models[m["study_id"]].items()),
            }
            utc = datetime.fromisoformat(m["birth_utc"].replace("Z", "+00:00"))
            local = utc.astimezone(ZoneInfo(m["timezone_id"]))
            tests["utc_to_source_local_roundtrip"] = local.replace(tzinfo=None).isoformat() == expected_local
            tests["offset_matches_iana"] = int(local.utcoffset().total_seconds()) == m["source_offset_seconds"]
            if not all(tests.values()):
                errors.append({"ordinal": ordinal, "failed": [k for k, v in tests.items() if not v]})
            checked += 1
    actual = collections.Counter(r["stratum_id"] for r in metadata)
    allocation_errors = [s["stratum_id"] for s in manifest["strata"] if actual[s["stratum_id"]] != s["n_h"]]
    weight_error = sum(r["sample_weight"] for r in metadata) - manifest["eligible_frame_N"]
    result = {"source_archive_sha256": EXPECTED_SHA256, "selected_records": len(metadata),
              "reread_from_original_DBF": checked, "field_comparisons_per_record": 8,
              "mismatches": errors, "allocation_mismatches": allocation_errors,
              "weight_total_error": weight_error,
              "status": "passed" if checked == len(metadata) and not errors and not allocation_errors and abs(weight_error) < 1e-5 else "failed"}
    (args.sample_dir / "independent_source_reread.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
