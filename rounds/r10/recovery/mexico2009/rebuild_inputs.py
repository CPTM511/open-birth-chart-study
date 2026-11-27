"""Rebuild the 2,000 frozen Mexico 2009 model inputs; emit only an aggregate receipt by default."""
import argparse
import csv
import hashlib
import heapq
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

R10 = Path(__file__).resolve().parents[2]
MEXICO_R9 = R10.parent / "r9/data/mexico"
sys.path[:0] = [str(MEXICO_R9), str(MEXICO_R9 / "geo")]
from audit_mexico2015 import dbf_rows
from build_locality_references import dms, normalize
from sample_mexico2015 import MODEL_KEYS, tz_version, valid_offsets

ITER_SHA256 = "9342fdbd45bda5897f2b827a12904843b6f8fb85d4e72da299e09e4d2422ab60"
ITER_MEMBER = "iter_00_cpv2020/conjunto_de_datos/conjunto_de_datos_iter_00CSV20.csv"
FIELDS = ("ANO_NAC", "MES_NAC", "DIA_NAC", "HORA_NAC", "MINUTO_NAC", "ENT_OCURR",
          "MUN_OCURR", "SEXO", "ANO_REG", "MES_REG", "DIA_REG")


def file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def require_hash(path, expected):
    if file_hash(path) != expected:
        raise ValueError(f"File verification failed for {path.name}")


def municipal_points(seats_dir, iter_archive):
    require_hash(iter_archive, ITER_SHA256)
    designations = {}
    hashes = {}
    for state in range(1, 33):
        filename = f"seats-{state:02}.json"
        path = seats_dir / filename
        hashes[filename] = file_hash(path)
        for item in json.loads(path.read_bytes())["datos"]:
            municipality, seat = item["cvegeo"], item.get("cve_cab") or ""
            if municipality != item["cve_ent"] + item["cve_mun"] or municipality[:2] != f"{state:02}":
                raise ValueError("Invalid municipality catalogue code")
            if seat.isdecimal() and 0 < int(seat) < 9998:
                designations[municipality + seat] = item
    rule = json.loads((MEXICO_R9 / "geo/timezone2015_conservative.json").read_bytes())
    points = {}
    with ZipFile(iter_archive) as source:
        with io.TextIOWrapper(source.open(ITER_MEMBER), encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                municipality = row["ENTIDAD"].zfill(2) + row["MUN"].zfill(3)
                designation = designations.get(municipality + row["LOC"].zfill(4))
                if not designation:
                    continue
                name = normalize(row["NOM_MUN"])
                if name != normalize(designation["nomgeo"]):
                    continue
                seat_name = designation.get("nom_cab")
                if seat_name and normalize(seat_name) != normalize(row["NOM_LOC"]):
                    continue
                zone = rule["by_municipality"].get(municipality, rule["by_state"].get(municipality[:2]))
                if not zone:
                    continue
                try:
                    latitude = dms(row["LATITUD"])
                    longitude = dms(row["LONGITUD"])
                except ValueError:
                    continue
                if not (14 <= latitude <= 33 and -119 <= longitude <= -86):
                    continue
                if municipality in points:
                    raise ValueError("Duplicate qualifying municipal seat")
                points[municipality] = (name, latitude, longitude, zone)
    return points, hashes


def sample_archive(year, archive, points, stratum_quotas, seed, pools, counts):
    totals = Counter()
    with ZipFile(archive) as source:
        old_names = {r["CVE_ENT"] + r["CVE_MUN"]: normalize(r["NOMBRE"])
                     for _, deleted, r in dbf_rows(source, "ENTMUN.dbf", ("CVE_ENT", "CVE_MUN", "NOMBRE"))
                     if not deleted}
        matches = {code: point for code, point in points.items() if old_names.get(code) == point[0]}
        for ordinal, deleted, r in dbf_rows(source, f"NACIM{year % 100:02}.dbf", FIELDS):
            totals["physical_records"] += 1
            if deleted or r["ANO_NAC"] != "2009":
                continue
            totals["actual_2009_birth_records"] += 1
            code = r["ENT_OCURR"].zfill(2) + r["MUN_OCURR"].zfill(3)
            point = matches.get(code)
            if point is None or r["SEXO"] not in ("1", "2") or r["ANO_REG"] != str(year):
                continue
            try:
                birth = datetime(2009, int(r["MES_NAC"]), int(r["DIA_NAC"]),
                                 int(r["HORA_NAC"]), int(r["MINUTO_NAC"]))
                registered = date(year, int(r["MES_REG"]), int(r["DIA_REG"]))
            except ValueError:
                continue
            if registered < birth.date():
                continue
            offsets = valid_offsets(birth.isoformat(), point[3])
            if len(offsets) != 1:
                continue
            sex = "M" if r["SEXO"] == "1" else "F"
            cell = code[:2] + "|" + sex
            totals["eligible_records"] += 1
            counts[cell] += 1
            source_id = f"INEGI-NACIM{year}-{ordinal:08d}"
            rank = int.from_bytes(hashlib.sha256((seed + "|" + source_id).encode()).digest(), "big")
            pool = pools[cell]
            if len(pool) == stratum_quotas[cell] and rank >= -pool[0][0]:
                continue
            entry = (-rank, source_id, birth, sex, point, offsets[0])
            if len(pool) < stratum_quotas[cell]:
                heapq.heappush(pool, entry)
            else:
                heapq.heapreplace(pool, entry)
    return dict(totals)


def model_bytes(pools):
    results = []
    for pool in pools.values():
        for _, source_id, local, sex, (_, lat, lon, zone), offset in pool:
            row = {
                "study_id": "R10-" + hashlib.sha256(source_id.encode()).hexdigest()[:24],
                "birth_local": local.isoformat(),
                "birth_utc": (local - timedelta(seconds=offset)).isoformat() + "Z",
                "source_offset_seconds": offset, "sex_resolved": sex,
                "latitude": lat, "longitude": lon, "calendar": "gregorian",
                "time_precision_seconds": 60, "time_uncertainty_seconds": None,
                "coordinate_precision_degrees": None, "timezone_id": zone, "instant_scale": "UT",
            }
            results.append(row)
    results.sort(key=lambda row: row["study_id"])
    if len({r["study_id"] for r in results}) != len(results):
        raise ValueError("Duplicate selected study identifier")
    return b"".join((json.dumps({k: row[k] for k in MODEL_KEYS}, separators=(",", ":")) + "\n").encode()
                    for row in results)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--archives", required=True, type=Path, help="Directory with YEAR/natalidad_base_datos_YEAR_dbf.zip")
    cli.add_argument("--iter", required=True, type=Path, help="National 2020 INEGI ITER ZIP")
    cli.add_argument("--seats", required=True, type=Path, help="Directory with 32 INEGI seats-NN.json files")
    cli.add_argument("--private-inputs", type=Path, help="Optional new private destination for the verified model input")
    args = cli.parse_args()
    manifest = json.loads((R10 / "mexico/samples/mexico_2000s/sampling_manifest.json").read_bytes())
    if tz_version() != manifest["tzdb"]:
        raise ValueError(f"Expected tzdb {manifest['tzdb']}; check PYTHONTZPATH")
    points, catalog_hashes = municipal_points(args.seats, args.iter)
    quotas = {row["stratum_id"]: row["n_h"] for row in manifest["strata"]}
    expected_counts = {row["stratum_id"]: row["N_h"] for row in manifest["strata"]}
    pools, counts, archives = defaultdict(list), Counter(), {}
    for year in manifest["registration_archive_years"]:
        archive = args.archives / str(year) / f"natalidad_base_datos_{year}_dbf.zip"
        expected = manifest["archive_sha256"][str(year)]
        require_hash(archive, expected)
        observed = sample_archive(year, archive, points, quotas, manifest["seed"], pools, counts)
        archives[str(year)] = {"sha256": expected, **observed}
    if counts != expected_counts or {k: len(v) for k, v in pools.items()} != quotas:
        raise ValueError("At least one eligible stratum or selected count differs from its frozen value")
    inputs = model_bytes(pools)
    digest = hashlib.sha256(inputs).hexdigest()
    if digest != manifest["model_input_sha256"]:
        raise ValueError(f"Recovered model input does not match the prescoring freeze: {digest}")
    if args.private_inputs:
        with args.private_inputs.open("xb") as handle:
            handle.write(inputs)
    report = {
        "slot": manifest["slot"], "status": "verified_model_inputs", "tzdb": tz_version(),
        "archives": archives, "iter_2020_sha256": ITER_SHA256, "seat_catalog_sha256": catalog_hashes,
        "eligible_records": sum(counts.values()), "matching_strata": len(counts),
        "selected_records": sum(map(len, pools.values())), "model_input_sha256": digest,
        "scope": "This replay verifies the model inputs and all stratum counts. It does not reconstruct the separate historical metadata serialization or calculate target scores.",
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
