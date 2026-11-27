"""Replay the INEGI 2020 input selection. Only aggregate evidence is printed."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta
import hashlib
import heapq
import io
import json
from pathlib import Path
import sys
from zipfile import ZipFile

R10 = Path(__file__).resolve().parents[2]
R9_MEXICO = R10.parent / "r9/data/mexico"
sys.path[:0] = [str(R9_MEXICO), str(R9_MEXICO / "geo")]
from audit_mexico2015 import dbf_rows
from build_locality_references import dms, normalize
from sample_mexico2015 import MODEL_KEYS, sha, tz_version, valid_offsets

ITER_SHA256 = "9342fdbd45bda5897f2b827a12904843b6f8fb85d4e72da299e09e4d2422ab60"
ITER_MEMBER = "iter_00_cpv2020/conjunto_de_datos/conjunto_de_datos_iter_00CSV20.csv"
BIRTH_FIELDS = ("ANO_NAC", "MES_NAC", "DIA_NAC", "HORA_NAC", "MINUTO_NAC",
                "ENT_OCURR", "MUN_OCURR", "LOC_OCURR", "SEXO", "ANO_REG", "MES_REG", "DIA_REG")
CATALOG_FIELDS = ("CVE_ENT", "CVE_MUN", "CVE_LOC", "NOM_LOC")


def reference_points(iter_path):
    if sha(iter_path) != ITER_SHA256:
        raise ValueError("Unexpected 2020 INEGI national census file")
    rules = json.loads((R9_MEXICO / "geo/timezone2015_conservative.json").read_bytes())
    points = {}
    with ZipFile(iter_path) as archive:
        with io.TextIOWrapper(archive.open(ITER_MEMBER), encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                key = row["ENTIDAD"].zfill(2) + row["MUN"].zfill(3) + row["LOC"].zfill(4)
                zone = rules["by_municipality"].get(key[:5], rules["by_state"].get(key[:2]))
                if not zone:
                    continue
                try:
                    lat, lon = dms(row["LATITUD"]), dms(row["LONGITUD"])
                except ValueError:
                    continue
                if not (14 <= lat <= 33 and -119 <= lon <= -86):
                    continue
                name = normalize(row["NOM_LOC"])
                if name:
                    if key in points:
                        raise ValueError("Duplicate census locality")
                    points[key] = (name, lat, lon, zone)
    return points


def audit_archive(archive, year, points, manifest, quotas, counts, selected):
    if sha(archive) != manifest["archive_sha256"][str(year)]:
        raise ValueError(f"Incorrect registration archive for {year}")
    totals = Counter()
    with ZipFile(archive) as z:
        members = {n.lower(): n for n in z.namelist()}
        catalog = {}
        for _, deleted, row in dbf_rows(z, members[f"catemlna{year % 100:02}.dbf"], CATALOG_FIELDS):
            if deleted:
                continue
            key = row["CVE_ENT"] + row["CVE_MUN"] + row["CVE_LOC"]
            name = normalize(row["NOM_LOC"])
            if key in catalog and catalog[key] != name:
                raise ValueError("Conflicting names in one registration archive")
            catalog[key] = name
        resolved = {k: points[k] for k, name in catalog.items() if k in points and points[k][0] == name}
        for ordinal, deleted, row in dbf_rows(z, members[f"nacim{year % 100:02}.dbf"], BIRTH_FIELDS):
            totals["physical_records"] += 1
            if deleted or row["ANO_NAC"] != "2020":
                continue
            totals["actual_2020_birth_records"] += 1
            key = row["ENT_OCURR"].zfill(2) + row["MUN_OCURR"].zfill(3) + row["LOC_OCURR"].zfill(4)
            point = resolved.get(key)
            if not point or row["SEXO"] not in ("1", "2") or row["ANO_REG"] != str(year):
                continue
            try:
                local = datetime(2020, int(row["MES_NAC"]), int(row["DIA_NAC"]),
                                 int(row["HORA_NAC"]), int(row["MINUTO_NAC"]))
                registration = date(year, int(row["MES_REG"]), int(row["DIA_REG"]))
            except ValueError:
                continue
            if registration < local.date():
                continue
            _, latitude, longitude, zone = point
            offsets = valid_offsets(local.isoformat(), zone)
            if len(offsets) != 1:
                continue
            sex = "M" if row["SEXO"] == "1" else "F"
            group = key[:2] + "|" + sex
            counts[group] += 1
            totals["eligible_records"] += 1
            source_id = f"INEGI-NACIM{year}-{ordinal:08d}"
            rank = int(hashlib.sha256((manifest["seed"] + "|" + source_id).encode()).hexdigest(), 16)
            pool = selected[group]
            if len(pool) == quotas[group] and rank >= -pool[0][0]:
                continue
            offset = offsets[0]
            birth = {
                "study_id": "R10-" + hashlib.sha256(source_id.encode()).hexdigest()[:24],
                "birth_local": local.isoformat(), "birth_utc": (local - timedelta(seconds=offset)).isoformat() + "Z",
                "source_offset_seconds": offset, "sex_resolved": sex, "latitude": latitude, "longitude": longitude,
                "calendar": "gregorian", "time_precision_seconds": 60, "time_uncertainty_seconds": None,
                "coordinate_precision_degrees": None, "timezone_id": zone, "instant_scale": "UT",
            }
            audit = {
                "study_id": birth["study_id"], "source_id": source_id, "registration_archive_year": year,
                "physical_record_ordinal": ordinal, "occurrence_code": key, "registration_date": registration.isoformat(),
                "registration_delay_days": (registration - local.date()).days, "source": manifest["source"],
                "birth_country": "MX", "stratum_id": group, "sampling_sha256": f"{rank:064x}",
            }
            entry = (-rank, source_id, birth, audit)
            if len(pool) == quotas[group]:
                heapq.heapreplace(pool, entry)
            else:
                heapq.heappush(pool, entry)
    return dict(totals)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", required=True, type=Path, help="Private directory with YEAR/natalidad_base_datos_YEAR_dbf.zip")
    parser.add_argument("--iter", required=True, type=Path, help="Official national ITER 2020 census ZIP")
    parser.add_argument("--private-inputs", type=Path, help="New private file for the hash-verified model input")
    parser.add_argument("--private-design", type=Path, help="New private file for recovered selection facts, separate from historical metadata")
    args = parser.parse_args()
    manifest = json.loads((R10 / "mexico/samples/mexico2020/sampling_manifest.json").read_bytes())
    if tz_version() != manifest["tzdb"]:
        raise ValueError("Use the registered IANA time-zone edition")
    quotas = {s["stratum_id"]: s["n_h"] for s in manifest["strata"]}
    expected = {s["stratum_id"]: s["N_h"] for s in manifest["strata"]}
    points = reference_points(args.iter)
    counts, selected, audits = Counter(), defaultdict(list), {}
    for year in manifest["registration_archive_years"]:
        archive = args.archives / str(year) / f"natalidad_base_datos_{year}_dbf.zip"
        result = audit_archive(archive, year, points, manifest, quotas, counts, selected)
        audits[str(year)] = {"sha256": manifest["archive_sha256"][str(year)], **result}
    if counts != expected or {g: len(v) for g, v in selected.items()} != quotas:
        raise ValueError("Eligible population or sample quota differs from the frozen register")
    entries = sorted((item for pool in selected.values() for item in pool), key=lambda e: e[2]["study_id"])
    if len(entries) != manifest["sample_n"] or len({item[2]["study_id"] for item in entries}) != len(entries):
        raise ValueError("Selected record count or identifier collision")
    data = b"".join((json.dumps({k: b[k] for k in MODEL_KEYS}, separators=(",", ":")) + "\n").encode() for _, _, b, _ in entries)
    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest["model_input_sha256"]:
        raise ValueError("Selected model inputs differ from the prescoring freeze")
    if args.private_inputs:
        with args.private_inputs.open("xb") as f:
            f.write(data)
    if args.private_design:
        with args.private_design.open("x", encoding="utf-8") as f:
            for _, _, _, audit in entries:
                group = audit["stratum_id"]
                full, drawn = counts[group], quotas[group]
                audit.update(N_h=full, n_h=drawn, sample_weight=full/drawn, inclusion_probability=drawn/full)
                f.write(json.dumps(audit, separators=(",", ":")) + "\n")
    print(json.dumps({
        "slot": manifest["slot"], "status": "verified_model_inputs", "tzdb": tz_version(),
        "archives": audits, "iter_2020_sha256": ITER_SHA256, "matching_strata": len(counts),
        "eligible_records": sum(counts.values()), "selected_records": len(entries), "model_input_sha256": digest,
        "scope": "Replays input selection and stratum sizes. Historical full metadata and target outcomes are outside this receipt.",
    }, indent=2))


if __name__ == "__main__":
    main()
