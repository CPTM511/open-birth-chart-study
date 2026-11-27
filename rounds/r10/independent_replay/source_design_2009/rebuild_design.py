"""Reconstruct the Mexico 2009 selection evidence from the INEGI source archives."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import sys
from zipfile import ZipFile

R10 = Path(__file__).resolve().parents[2]
SAMPLE_REPLAY = R10 / "recovery/mexico2009"
sys.path[:0] = [str(SAMPLE_REPLAY), str(R10.parent / "r9/data")]
from rebuild_inputs import ITER_MEMBER, model_bytes, municipal_points, require_hash, sample_archive
from audit_mexico2015 import dbf_header, dbf_rows
from build_locality_references import dms, normalize
from common import quotas
from sample_mexico2015 import tz_version, valid_offsets

SOURCE_FIELDS = ("ANO_NAC", "MES_NAC", "DIA_NAC", "HORA_NAC", "MINUTO_NAC", "SEXO",
                 "ENT_OCURR", "MUN_OCURR", "ANO_REG", "MES_REG", "DIA_REG")


def select_records(archives, manifest, receipt, points):
    quotas_by_stratum = {s["stratum_id"]: s["n_h"] for s in manifest["strata"]}
    pools, frame = defaultdict(list), Counter()
    for year, path in archives.items():
        digest = manifest["archive_sha256"][str(year)]
        require_hash(path, digest)
        observed = sample_archive(year, path, points, quotas_by_stratum, manifest["seed"], pools, frame)
        if {"sha256": digest, **observed} != receipt["archives"][str(year)]:
            raise ValueError(f"Registration and eligibility counts changed for {year}")
    if frame != {s["stratum_id"]: s["N_h"] for s in manifest["strata"]}:
        raise ValueError("Historical stratum counts differ")
    if quotas(frame, manifest["sample_n"]) != quotas_by_stratum:
        raise ValueError("Stratum quotas differ from the historical allocation")
    model = model_bytes(pools)
    if hashlib.sha256(model).hexdigest() != manifest["model_input_sha256"]:
        raise ValueError("Selected model input differs from the frozen file")
    births = {r["study_id"]: r for r in map(json.loads, model.splitlines())}
    selected = defaultdict(dict)
    for cell, pool in pools.items():
        ordered = sorted(pool, key=lambda entry: -entry[0])
        if len(ordered) != quotas_by_stratum[cell] or len({entry[0] for entry in ordered}) != len(ordered):
            raise ValueError("Unexpected number of selections or duplicate rank")
        for place, (negative_rank, sid, *_) in enumerate(ordered, 1):
            archive, ordinal = sid.rsplit("-", 1)
            year = int(archive.removeprefix("INEGI-NACIM"))
            study_id = "R10-" + hashlib.sha256(sid.encode()).hexdigest()[:24]
            rank = f"{-negative_rank:064x}"
            if study_id not in births or int(ordinal) in selected[year]:
                raise ValueError("Selected model key or physical ordinal mismatch")
            selected[year][int(ordinal)] = (sid, births[study_id], cell, place, rank)
    return selected, frame, quotas_by_stratum


def design_rows(year, path, selected, manifest, frame, sample_sizes):
    """Read only the selected physical records and their archive's municipality names."""
    rows = []
    member = f"NACIM{year % 100:02}.dbf"
    with ZipFile(path) as z:
        names = {r["CVE_ENT"] + r["CVE_MUN"]: r["NOMBRE"] for _, deleted, r in
                 dbf_rows(z, "ENTMUN.dbf", ("CVE_ENT", "CVE_MUN", "NOMBRE")) if not deleted}
        with z.open(member) as f:
            count, width, schema, encoding = dbf_header(f)
            start = f.tell()
            slices = {k: slice(schema[k][0], schema[k][0] + schema[k][1]) for k in SOURCE_FIELDS}
            for ordinal, (sid, birth, cell, place, rank) in sorted(selected.items()):
                if not 1 <= ordinal <= count:
                    raise ValueError("Invalid historical DBF ordinal")
                f.seek(start + (ordinal - 1) * width)
                record = f.read(width)
                if len(record) != width or record[:1] != b" ":
                    raise ValueError("Selected DBF record is incomplete or deleted")
                raw = {k: record[span].decode(encoding).strip() for k, span in slices.items()}
                local = datetime(*(int(raw[k]) for k in SOURCE_FIELDS[:5]))
                registration = date(*(int(raw[k]) for k in ("ANO_REG", "MES_REG", "DIA_REG")))
                code = raw["ENT_OCURR"].zfill(2) + raw["MUN_OCURR"].zfill(3)
                sex = {"1": "M", "2": "F"}[raw["SEXO"]]
                offsets = valid_offsets(local.isoformat(), birth["timezone_id"])
                offset = birth["source_offset_seconds"]
                if (registration.year != year or local.year != manifest["actual_birth_year"]
                        or registration < local.date() or cell != code[:2] + "|" + sex
                        or sex != birth["sex_resolved"] or local.isoformat() != birth["birth_local"]
                        or offsets != (offset,) or
                        (local - timedelta(seconds=offset)).isoformat() + "Z" != birth["birth_utc"]):
                    raise ValueError("A selected source record differs from its verified model input")
                N, n = frame[cell], sample_sizes[cell]
                rows.append({
                    "study_id": birth["study_id"], "source_id": sid, "source": manifest["source"], "birth_country": "MX",
                    "registration_archive_year": year, "archive_sha256": manifest["archive_sha256"][str(year)],
                    "dbf_member": member, "physical_record_ordinal_1based": ordinal, "stratum_id": cell,
                    "N_h": N, "n_h": n, "sample_weight": N/n, "inclusion_probability": n/N, "sampling_sha256": rank,
                    "within_stratum_ascending_rank_1based": place, "registration_date": registration.isoformat(),
                    "registration_delay_days": (registration - local.date()).days, "official_archived_dbf_fields": raw,
                    "birth_input": birth, "occurrence_municipality_code": code, "historical_municipality_name": names[code],
                })
    return rows


def attach_geography(rows, seats_dir, iter_path):
    selected_codes = {r["occurrence_municipality_code"] for r in rows}
    seats = {}
    for state in range(1, 33):
        catalogue = json.loads((seats_dir / f"seats-{state:02}.json").read_bytes())
        for item in catalogue["datos"]:
            if item["cvegeo"] in selected_codes:
                seats[item["cvegeo"] + item["cve_cab"]] = item
    places = {}
    with ZipFile(iter_path) as z, io.TextIOWrapper(z.open(ITER_MEMBER), encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            municipality = row["ENTIDAD"].zfill(2) + row["MUN"].zfill(3)
            locality = municipality + row["LOC"].zfill(4)
            if locality not in seats:
                continue
            item = seats[locality]
            if (municipality in places or normalize(item["nomgeo"]) != normalize(row["NOM_MUN"])
                    or (item.get("nom_cab") and normalize(item["nom_cab"]) != normalize(row["NOM_LOC"]))):
                raise ValueError("Ambiguous or incompatible municipal seat")
            places[municipality] = {
                "official_2026_seat_code": item["cve_cab"], "official_2026_municipality_name": item["nomgeo"],
                "official_2026_seat_name_when_reported": item.get("nom_cab"), "census_2020_9_digit_locality_code": locality,
                "census_2020_municipality_name": row["NOM_MUN"], "census_2020_seat_name": row["NOM_LOC"],
                "census_2020_latitude_dms": row["LATITUD"], "census_2020_longitude_dms": row["LONGITUD"],
            }
    if set(places) != selected_codes:
        raise ValueError("A selected municipality lacks a verified seat")
    for row in rows:
        place = places[row["occurrence_municipality_code"]]
        birth = row["birth_input"]
        if (normalize(row["historical_municipality_name"]) != normalize(place["official_2026_municipality_name"])
                or birth["latitude"] != dms(place["census_2020_latitude_dms"])
                or birth["longitude"] != dms(place["census_2020_longitude_dms"])):
            raise ValueError("Historical name or census coordinates differ from the verified model input")
        row["official_geographic_evidence"] = place
    return len(places)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", required=True, type=Path, help="Directory with YEAR/natalidad_base_datos_YEAR_dbf.zip")
    parser.add_argument("--iter", required=True, type=Path, help="INEGI national 2020 census ITER ZIP")
    parser.add_argument("--seats", required=True, type=Path, help="Directory with 32 seats-NN.json responses")
    parser.add_argument("--private-design", type=Path, help="Optional new private file for verified design rows")
    args = parser.parse_args()
    manifest = json.loads((R10 / "mexico/samples/mexico_2000s/sampling_manifest.json").read_bytes())
    receipt = json.loads((SAMPLE_REPLAY / "replay_receipt.json").read_bytes())
    design_receipt = json.loads((R10 / "recovery/input_and_design_receipt.json").read_bytes())
    expected = next(g["verified_design_file_sha256"] for g in design_receipt["groups"] if g["slot"] == manifest["slot"])
    if tz_version() != manifest["tzdb"]:
        raise ValueError(f"Expected IANA {manifest['tzdb']}; check PYTHONTZPATH")
    points, hashes = municipal_points(args.seats, args.iter)
    if hashes != receipt["seat_catalog_sha256"]:
        raise ValueError("Municipal-seat catalogue differs from the recorded edition")
    archives = {y: args.archives / str(y) / f"natalidad_base_datos_{y}_dbf.zip" for y in manifest["registration_archive_years"]}
    selected, frame, quotas_by_stratum = select_records(archives, manifest, receipt, points)
    rows = []
    for year, path in archives.items():
        rows.extend(design_rows(year, path, selected[year], manifest, frame, quotas_by_stratum))
    municipalities = attach_geography(rows, args.seats, args.iter)
    rows.sort(key=lambda r: r["study_id"])
    weight = sum(Fraction(r["N_h"], r["n_h"]) for r in rows)
    if weight != manifest["eligible_frame_N"] or len(rows) != manifest["sample_n"]:
        raise ValueError("Selected count or exact sum of weights differs from the frozen design")
    data = b"".join((json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n").encode() for r in rows)
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError(f"Reconstructed design byte sequence differs from recovery receipt: {digest}")
    if args.private_design:
        with args.private_design.open("xb") as f:
            f.write(data)
    print(json.dumps({
        "slot": manifest["slot"], "records": len(rows), "strata": len(frame), "sum_exact_weights": int(weight),
        "selected_by_registration_year": {str(year): len(records) for year, records in selected.items()},
        "selected_municipalities": municipalities, "frozen_model_input_sha256": manifest["model_input_sha256"],
        "reconstructed_design_sha256": digest, "original_metadata_status": "unrecovered",
    }, indent=2))


if __name__ == "__main__":
    main()
