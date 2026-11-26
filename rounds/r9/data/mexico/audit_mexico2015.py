#!/usr/bin/env python3
"""Audit INEGI natality 2015 without projecting or reading outcome fields.

This operates on the pinned official public ZIP. The output CSV is a PRIVATE
birth-only candidate frame, not sampled inputs and not a population claim.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

EXPECTED_SHA256 = "995c451db513f19641c1e28032d0164e3e5a2c5a0b210b49e0754fde15f4f6c7"
BIRTH_FIELDS = (
    "ENT_OCURR", "MUN_OCURR", "LOC_OCURR", "SEXO", "DIA_NAC",
    "MES_NACIM", "ANO_NAC", "DIA_REG", "MES_REG", "ANO_REG",
    "HORA_NAC", "MINUTO_NAC",
)


def dbf_header(handle):
    header = handle.read(32)
    count = struct.unpack("<I", header[4:8])[0]
    hlen, rlen = struct.unpack("<HH", header[8:12])
    descriptors = handle.read(hlen - 32)
    fields, offset = {}, 1
    for i in range(0, len(descriptors), 32):
        b = descriptors[i:i + 32]
        if not b or b[0] == 13:
            break
        if len(b) != 32:
            raise ValueError("Truncated DBF descriptor")
        name = b[:11].split(b"\0")[0].decode("ascii")
        fields[name] = (offset, b[16], chr(b[11]))
        offset += b[16]
    assert offset == rlen
    encoding = {0x02: "cp850", 0x03: "cp1252"}.get(header[29])
    if encoding is None:
        raise ValueError(f"Unsupported DBF language driver {header[29]}")
    return count, rlen, fields, encoding


def dbf_rows(z, member, selected_fields):
    with z.open(member) as handle:
        count, rlen, fields, encoding = dbf_header(handle)
        specs = [(key, *fields[key][:2]) for key in selected_fields]
        for ordinal in range(1, count + 1):
            record = handle.read(rlen)
            if len(record) != rlen:
                raise ValueError(f"Truncated DBF record {ordinal}")
            flag = record[0:1]
            if flag not in (b" ", b"*"):
                raise ValueError(f"Unexpected DBF deletion flag {flag!r}")
            yield ordinal, flag == b"*", {
                key: record[offset:offset + width].decode(encoding).strip()
                for key, offset, width in specs
            }


def integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def date_or_none(year, month, day):
    try:
        return dt.date(year, month, day)
    except (TypeError, ValueError):
        return None


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with args.archive.open("rb") as handle:
        archive_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    if archive_hash != EXPECTED_SHA256:
        raise ValueError("Pinned archive SHA256 mismatch")
    counts = collections.Counter()
    hist = {key: collections.Counter() for key in (
        "birth_year", "registration_year", "sex", "hour", "minute",
        "birth_state", "target_hour", "target_minute", "target_sex",
        "target_state", "target_registration_delay_days", "candidate_stratum",
        "candidate_birth_month", "candidate_locality",
    )}
    with zipfile.ZipFile(args.archive) as z:
        locality_names = {}
        for _, deleted, row in dbf_rows(z, "CATEMLNA15.dbf", ("CVE_ENT", "CVE_MUN", "CVE_LOC", "NOM_LOC")):
            if not deleted:
                key = row["CVE_ENT"] + row["CVE_MUN"] + row["CVE_LOC"]
                if key in locality_names and locality_names[key] != row["NOM_LOC"]:
                    raise ValueError("Conflicting locality catalog key")
                locality_names[key] = row["NOM_LOC"]
        save_json(args.output_dir / "locality_catalog_2015.json", locality_names)
        csv_path = args.output_dir / "private_birth2015_candidates.csv"
        with csv_path.open("w", encoding="utf8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=(
                "source_id", "source_ordinal", "birth_local", "sex",
                "state_code", "municipality_code", "locality_code", "cvegeo",
                "locality_name_2015", "registration_date", "registration_delay_days",
            ))
            writer.writeheader()
            for ordinal, deleted, raw in dbf_rows(z, "NACIM15.dbf", BIRTH_FIELDS):
                counts["physical_records"] += 1
                if deleted:
                    counts["deleted_records"] += 1
                    continue
                counts["active_records"] += 1
                r = {key: integer(value) for key, value in raw.items()}
                by, bm, bd = r["ANO_NAC"], r["MES_NACIM"], r["DIA_NAC"]
                birth = date_or_none(by, bm, bd)
                reg = date_or_none(r["ANO_REG"], r["MES_REG"], r["DIA_REG"])
                hour, minute = r["HORA_NAC"], r["MINUTO_NAC"]
                clock_valid = hour is not None and minute is not None and 0 <= hour <= 23 and 0 <= minute <= 59
                sex_valid = r["SEXO"] in (1, 2)
                domestic = r["ENT_OCURR"] is not None and 1 <= r["ENT_OCURR"] <= 32
                municipality_valid = r["MUN_OCURR"] is not None and 1 <= r["MUN_OCURR"] < 999
                locality_valid = r["LOC_OCURR"] is not None and 1 <= r["LOC_OCURR"] < 9999
                cvegeo = f'{r["ENT_OCURR"]:02}{r["MUN_OCURR"]:03}{r["LOC_OCURR"]:04}' if domestic and municipality_valid and locality_valid else None
                catalog_match = cvegeo in locality_names if cvegeo else False
                delay = (reg - birth).days if reg and birth else None
                for name, key in (("birth_year", "ANO_NAC"), ("registration_year", "ANO_REG"), ("sex", "SEXO"), ("hour", "HORA_NAC"), ("minute", "MINUTO_NAC"), ("birth_state", "ENT_OCURR")):
                    hist[name][str(r[key])] += 1
                for name, ok in (("valid_birth_date", bool(birth)), ("valid_birth_clock", clock_valid), ("valid_sex", sex_valid), ("domestic_birth_state", domestic), ("valid_registration_date", bool(reg)), ("birth_place_in_2015_catalog", catalog_match)):
                    counts[name] += int(ok)
                if delay is not None and delay < 0:
                    counts["negative_registration_delay"] += 1
                if clock_valid:
                    counts["valid_clock_minute_multiple_5"] += int(minute % 5 == 0)
                    counts["valid_clock_minute_zero"] += int(minute == 0)
                if by != 2015:
                    continue
                counts["target_year_records"] += 1
                for name, val in (("target_hour", hour), ("target_minute", minute), ("target_sex", r["SEXO"]), ("target_state", r["ENT_OCURR"])):
                    hist[name][str(val)] += 1
                for name, ok in (("target_valid_date", bool(birth)), ("target_valid_clock", clock_valid), ("target_valid_sex", sex_valid), ("target_domestic", domestic), ("target_catalog_match", catalog_match)):
                    counts[name] += int(ok)
                if delay is not None:
                    hist["target_registration_delay_days"][str(delay)] += 1
                if clock_valid:
                    counts["target_valid_clock_minute_multiple_5"] += int(minute % 5 == 0)
                    counts["target_valid_clock_minute_zero"] += int(minute == 0)
                # Birth-only field eligibility. Date and sex are not inferred.
                # Registration delay is audited but not used to select outcomes.
                if not (birth and clock_valid and sex_valid and domestic and municipality_valid):
                    continue
                counts["target_complete_birth_fields_domestic_municipality"] += 1
                if not catalog_match:
                    counts["target_complete_no_exact_locality_catalog_match"] += 1
                    continue
                counts["candidate_records_pre_geographic_coordinates_timezone"] += 1
                state = f'{r["ENT_OCURR"]:02}'
                sex = "M" if r["SEXO"] == 1 else "F"
                hist["candidate_stratum"][f"{state}|{sex}"] += 1
                hist["candidate_birth_month"][str(bm)] += 1
                hist["candidate_locality"][cvegeo] += 1
                writer.writerow({
                    "source_id": f"INEGI-NACIM15-{ordinal:08d}",
                    "source_ordinal": ordinal,
                    "birth_local": f"{birth.isoformat()}T{hour:02}:{minute:02}:00",
                    "sex": sex, "state_code": state,
                    "municipality_code": f'{r["MUN_OCURR"]:03}',
                    "locality_code": f'{r["LOC_OCURR"]:04}', "cvegeo": cvegeo,
                    "locality_name_2015": locality_names[cvegeo],
                    "registration_date": reg.isoformat() if reg else "",
                    "registration_delay_days": delay if delay is not None else "",
                })
                if ordinal % 500000 == 0:
                    print(f"audited {ordinal:,} source records", flush=True)
    output = {
        "source_archive_sha256": archive_hash,
        "source_file": "NACIM15.dbf",
        "source_record_count_expected": 2353596,
        "selected_fields_only": BIRTH_FIELDS,
        "outcome_fields_projected_or_used": False,
        "target_birth_year": 2015,
        "source_registration_year": 2015,
        "counts": dict(sorted(counts.items())),
        "histograms": {k: dict(sorted(v.items())) for k, v in hist.items()},
        "private_candidate_file": csv_path.name,
        "private_candidate_sha256": hashlib.file_digest(csv_path.open("rb"), "sha256").hexdigest(),
        "candidate_is_final_eligible_frame": False,
        "remaining_requirements": ["official coordinate reference", "historically defensible timezone assignment", "DST fold/gap screening", "frozen sample selection"],
        "cautions": ["Registry-year frame excludes births not registered in that year", "Minute field is recorded precision, not measured accuracy", "Same birth inputs are not deduplicated because legitimate coincident births/twins may share them", "No record is treated as a verified independent person"],
    }
    assert counts["physical_records"] == output["source_record_count_expected"]
    save_json(args.output_dir / "birth_field_audit.json", output)
    print(json.dumps({"counts": output["counts"], "candidate_sha256": output["private_candidate_sha256"], "candidate_localities": len(hist["candidate_locality"])}, indent=2))


if __name__ == "__main__":
    main()
