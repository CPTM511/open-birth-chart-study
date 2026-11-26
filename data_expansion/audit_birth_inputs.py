#!/usr/bin/env python3
"""Verify record integrity, design accounting and raw-source transcription.

This does not run or inspect astrological scores or real-world outcomes.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

from build_birth_inputs import DEFAULT_CACHE, DEFAULT_OUTPUT


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, h)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", "--output", dest="input_dir", type=Path, default=DEFAULT_OUTPUT,
                   help="Generated cohort directory to validate (--output is a legacy alias)")
    p.add_argument("--output-dir", type=Path,
                   help="Audit report directory (default: <input-dir>/audits)")
    p.add_argument("--raw-dir", type=Path, default=DEFAULT_CACHE,
                   help="Original pinned ZIP cache, used only for source verification")
    p.add_argument("--verify-brazil-source", action="store_true")
    a = p.parse_args()
    result = {}
    all_rows = {}
    for source in ("brazil2006", "ogdb2023", "adb_z2026"):
        d = a.input_dir / "samples" / source
        if not d.exists():
            continue
        records = rows(d / "birth_metadata.jsonl")
        model = rows(d / "birth_inputs.jsonl")
        manifest = json.loads((d / "sampling_manifest.json").read_text())
        all_rows[source] = records
        c = Counter(r["stratum_id"] for r in records)
        assert len({r["study_id"] for r in records}) == len(records) == len(model) == manifest["sample_n"]
        assert len({r["source_id"] for r in records}) == len(records)
        assert all(c[h["stratum_id"]] == h["n_h"] for h in manifest["strata"])
        assert abs(sum(r["sample_weight"] for r in records) - manifest["eligible_frame_N"]) < 1e-5
        assert all(r["sex_resolved"] in {"M", "F"} and
                   -90 <= r["latitude"] <= 90 and -180 <= r["longitude"] <= 180 and
                   (r["latitude"], r["longitude"]) != (0, 0) for r in records)
        residual = [abs((datetime.fromisoformat(r["birth_local"]) - datetime.fromisoformat(r["birth_utc"].rstrip("Z"))).total_seconds() - r["source_offset_seconds"]) for r in records]
        assert max(residual) <= 1
        actual_hash = hashlib.sha256((d / "birth_inputs.jsonl").read_bytes()).hexdigest()
        assert actual_hash == manifest["model_input_sha256"]
        by_id = {r["study_id"]: r for r in records}
        assert all(all(by_id[r["study_id"]].get(k) == v for k, v in r.items()) for r in model)
        result[source] = dict(n=len(records), N=manifest["eligible_frame_N"], strata=len(c),
            birth_year_min=min(r["birth_year"] for r in records),
            birth_year_max=max(r["birth_year"] for r in records),
            sex=dict(Counter(r["sex"] for r in records)),
            countries=dict(Counter(r["birth_country"] for r in records)),
            modern_1980_2019_countries=dict(Counter(r["birth_country"] for r in records if 1980 <= r["birth_year"] <= 2019)),
            max_offset_residual_seconds=max(residual),
            weighted_total=sum(r["sample_weight"] for r in records), sha256=actual_hash)
    if not all_rows:
        raise ValueError("No generated sample directories found; supply --input-dir with reconstructed cohorts")
    if a.verify_brazil_source:
        wanted = {int(r["source_row_id"]): r for r in all_rows["brazil2006"]}
        checked = 0
        with zipfile.ZipFile(a.raw_dir / "brazil2006.zip") as z:
            with z.open("DNBR2006.csv") as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";")
                for ordinal, raw in enumerate(reader, 1):
                    if ordinal not in wanted:
                        continue
                    record = wanted[ordinal]
                    ds, ts = raw["DTNASC"], raw["HORANASC"]
                    expected_local = f"{ds[4:8]}-{ds[2:4]}-{ds[:2]}T{ts[:2]}:{ts[2:]}:00"
                    assert expected_local == record["birth_local"]
                    assert raw["SEXO"] == {"M": "1", "F": "2"}[record["sex"]]
                    assert raw["CODMUNNASC"] == record["municipality_code"]
                    assert raw["contador"] == record["source_record_counter"]
                    assert record["source_id"] == "SINASC2006:row:" + str(ordinal).zfill(7)
                    checked += 1
        assert checked == len(wanted)
        result["brazil2006"]["independent_raw_row_transcriptions_verified"] = checked
    # Birth-only candidate matching is not identity validation and does not
    # remove records. It explains why source sample sizes are not summed as
    # independent people. No names or outcomes are inspected.
    if "ogdb2023" in all_rows and "adb_z2026" in all_rows:
        matched_pairs = 0
        adb_matched = set()
        ogdb_matched = set()
        for r in all_rows["adb_z2026"]:
            for s in all_rows["ogdb2023"]:
                if r["birth_local"][:10] == s["birth_local"][:10] and r["sex"] == s["sex"] and distance_km(r, s) <= 25:
                    matched_pairs += 1
                    adb_matched.add(r["study_id"])
                    ogdb_matched.add(s["study_id"])
        result["cross_source_birth_only_candidate_overlap"] = {
            "rule": "same local birth date and explicit sex, locality points within 25 km",
            "matched_pairs": matched_pairs, "adb_records_in_candidate_pairs": len(adb_matched),
            "ogdb_records_in_candidate_pairs": len(ogdb_matched),
            "identity_verified": False, "rows_removed": 0,
            "interpretation": "Candidates can be coincidental and incomplete; do not claim independent unique people by summing source sample sizes."}
    result["union_of_source_country_labels"] = sorted({r["birth_country"] for records in all_rows.values() for r in records})
    result["country_label_union_is_global_representativity"] = False
    audit_dir = a.output_dir or a.input_dir / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / "sample_integrity_validation.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
