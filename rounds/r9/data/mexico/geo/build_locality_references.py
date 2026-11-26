"""Match INEGI birth-locality keys to explicitly dated ITER2020 reference points.

Conservative: exact 9-digit code and exact normalized locality name required.
Coordinates are locality reference points, never exact hospital/birth locations.
"""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re
import unicodedata
import zipfile

SOURCE_URL = "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_00_cpv2020_csv.zip"


def normalize(text):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode())


def dms(text):
    numbers = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", text)]
    if len(numbers) != 3:
        raise ValueError("Unexpected DMS format")
    degrees, minutes, seconds = numbers
    if not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError("Invalid DMS value")
    value = degrees + minutes / 60 + seconds / 3600
    return -value if "W" in text or "S" in text else value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True, type=Path)
    ap.add_argument("--catalog2015", required=True, type=Path)
    ap.add_argument("--iter2020-zip", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(args.catalog2015.read_text())
    with args.candidates.open() as handle:
        counts = Counter(row["cvegeo"] for row in csv.DictReader(handle))
    points, mismatches, bad, seen = {}, [], [], set()
    with zipfile.ZipFile(args.iter2020_zip) as archive:
        member = "iter_00_cpv2020/conjunto_de_datos/conjunto_de_datos_iter_00CSV20.csv"
        with io.TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                code = row["ENTIDAD"].zfill(2) + row["MUN"].zfill(3) + row["LOC"].zfill(4)
                if code not in counts:
                    continue
                if code in seen:
                    raise ValueError("Duplicate target key in ITER2020: " + code)
                seen.add(code)
                if normalize(catalog.get(code, "")) != normalize(row["NOM_LOC"]):
                    mismatches.append({"cvegeo": code, "name_2015": catalog.get(code), "name_2020": row["NOM_LOC"], "candidate_rows": counts[code]})
                    continue
                try:
                    lat, lon = dms(row["LATITUD"]), dms(row["LONGITUD"])
                except ValueError as error:
                    bad.append({"cvegeo": code, "error": str(error)})
                    continue
                if not (14 <= lat <= 33 and -119 <= lon <= -86):
                    bad.append({"cvegeo": code, "error": "outside broad Mexico bound"})
                    continue
                points[code] = {
                    "latitude": lat, "longitude": lon, "reference_year": 2020,
                    "reference_name": row["NOM_LOC"],
                    "reference_role": "INEGI_2020_locality_reference_point_not_exact_birth_site",
                    "source_url": SOURCE_URL, "source_2015_locality_name": catalog[code],
                    "crosswalk": "same_9_digit_cvegeo_and_normalized_exact_locality_name",
                    "latitude_source_DMS": row["LATITUD"], "longitude_source_DMS": row["LONGITUD"],
                    "geographic_uncertainty": "Reference point from 2020 applied to 2015 locality; neither a hospital coordinate nor a measured birthplace uncertainty interval."
                }
    for name, value in [("locality2020_refs_for_birth2015.json", points), ("locality_name_mismatches.json", mismatches), ("locality_reference_bad_coordinates.json", bad)]:
        (args.out_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    with (args.out_dir / "locality2020_refs_for_birth2015.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["cvegeo"] + list(next(iter(points.values()))))
        writer.writeheader()
        writer.writerows({"cvegeo": code, **point} for code, point in points.items())
    print(json.dumps({"candidate_codes": len(counts), "matched_codes": len(points), "matched_candidate_rows": sum(counts[c] for c in points), "name_mismatches": len(mismatches), "missing_codes": len(set(counts) - seen), "invalid_coordinates": len(bad)}))


if __name__ == "__main__":
    main()
