"""Screen older birth years in verified INEGI archives without opening model scores."""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from hashlib import file_digest
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[3]
R10 = ROOT / "rounds/r10"
sys.path.insert(0, str(R10 / "recovery/mexico2020"))
from rebuild_inputs import BIRTH_FIELDS, CATALOG_FIELDS
from rebuild_inputs import dbf_rows, normalize, reference_points, tz_version, valid_offsets

OLDER_YEARS = set(range(1990, 2000))
CONTROL_YEARS = {2020, 2023}


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def official_claims():
    path = ROOT / "rounds/r11/results/mexico_registration_sources.json"
    previous = json.loads(path.read_bytes())
    return {a["registration_year"]: a for a in previous["source_archives"]}, previous["held_out_source_candidate"]


def inspect_archive(path, year, points, allowed_strata, strata, *, older_birth=None):
    counts = defaultdict(Counter)
    suffix = f"{year % 100:02d}"
    birth_years = {str(i): i for i in OLDER_YEARS | CONTROL_YEARS}
    n_rows = 0
    with ZipFile(path) as archive:
        members = {Path(name).name.lower(): name for name in archive.namelist() if not name.endswith("/")}
        names = {}
        for _, deleted, row in dbf_rows(archive, members[f"catemlna{suffix}.dbf"], CATALOG_FIELDS):
            if deleted:
                continue
            key = row["CVE_ENT"] + row["CVE_MUN"] + row["CVE_LOC"]
            label = normalize(row["NOM_LOC"])
            if names.setdefault(key, label) != label:
                raise ValueError("Conflicting official locality labels")
        zones = {k: points[k][3] for k, name in names.items() if k in points and points[k][0] == name}
        for ordinal, deleted, row in dbf_rows(archive, members[f"nacim{suffix}.dbf"], BIRTH_FIELDS):
            n_rows += 1
            birth_year = birth_years.get(row["ANO_NAC"])
            if deleted or birth_year is None:
                continue
            coverage = counts[birth_year]
            coverage["observed_birth_year"] += 1
            if row["SEXO"] not in ("1", "2") or row["ANO_REG"] != str(year):
                coverage["excluded_sex_or_registration_year"] += 1
                continue
            try:
                local = datetime(birth_year, int(row["MES_NAC"]), int(row["DIA_NAC"]), int(row["HORA_NAC"]),
                                 int(row["MINUTO_NAC"]))
                registration = date(year, int(row["MES_REG"]), int(row["DIA_REG"]))
            except ValueError:
                coverage["excluded_date_or_clock"] += 1
                continue
            if registration < local.date():
                coverage["excluded_chronology"] += 1
                continue
            code = row["ENT_OCURR"].zfill(2) + row["MUN_OCURR"].zfill(3) + row["LOC_OCURR"].zfill(4)
            stratum = code[:2] + ("|M" if row["SEXO"] == "1" else "|F")
            if code not in zones or stratum not in allowed_strata:
                coverage["excluded_location_or_zone"] += 1
                continue
            offsets = valid_offsets(local.isoformat(), zones[code])
            if len(offsets) != 1:
                coverage["excluded_unresolvable_clock"] += 1
                continue
            coverage["eligible"] += 1
            strata[birth_year][stratum] += 1
            if older_birth is not None and birth_year in OLDER_YEARS:
                older_birth(year, ordinal, local, registration, code, stratum, points[code], offsets[0])
            if local.minute == 0:
                coverage["on_the_hour"] += 1
                if local.hour == 0:
                    coverage["clock_0000"] += 1
                if local.hour == 12:
                    coverage["clock_1200"] += 1
    for counter in counts.values():
        exclusions = sum(v for k, v in counter.items() if k.startswith("excluded_"))
        if counter["observed_birth_year"] != exclusions + counter["eligible"]:
            raise ValueError("Source flow does not conserve rows")
    return n_rows, counts


def audit(directory, census, *, older_birth=None):
    if tz_version() != "2026c":
        raise ValueError("Use R10 IANA 2026c")
    claims, candidate23 = official_claims()
    claims23 = {a["registration_year"]: a for a in candidate23["source_archives"]}
    supported = {s["stratum_id"] for s in json.loads(
        (R10 / "mexico/samples/mexico2020/sampling_manifest.json").read_bytes())["strata"]}
    points = reference_points(census)
    facts, total = [], defaultdict(Counter)
    strata = defaultdict(Counter)
    for year in range(2022, 2026):
        path = directory / f"natalidad_base_datos_{year}_dbf.zip"
        source = claims[year]
        if digest(path) != source["sha256"]:
            raise ValueError("Official archive differs from the validated R11 release")
        rows, cohorts = inspect_archive(path, year, points, supported, strata, older_birth=older_birth)
        if rows != source["physical_rows"] or cohorts[2020]["eligible"] != source["eligible"]:
            raise ValueError("Older release's Mexico 2020 control differs")
        if year in claims23 and cohorts[2023]["eligible"] != claims23[year]["eligible"]:
            raise ValueError("Older release's Mexico 2023 control differs")
        facts.append({"year": year, "physical_rows": rows, "url": source["url"], "sha256": source["sha256"],
                      "older_year_rows": sum(cohorts[y]["observed_birth_year"] for y in OLDER_YEARS),
                      "older_year_eligible": sum(cohorts[y]["eligible"] for y in OLDER_YEARS)})
        for birth_year, summary in cohorts.items():
            total[birth_year].update(summary)
        print(f"{year}: {rows} archive rows screened, R11 control counts match.", flush=True)
    by_birth_year = []
    for year in sorted(OLDER_YEARS | CONTROL_YEARS):
        t = total[year]
        by_birth_year.append({"birth_year": year, **{k: t[k] for k in (
            "observed_birth_year", "excluded_sex_or_registration_year", "excluded_date_or_clock", "excluded_chronology",
            "excluded_location_or_zone", "excluded_unresolvable_clock", "eligible", "on_the_hour", "clock_0000",
            "clock_1200")}, "eligible_state_sex_strata": len(strata[year])})
    return {"status": "screened", "verified_utc": datetime.now(timezone.utc).isoformat(), "archives": facts,
            "birth_year_counts": by_birth_year, "clock_definition": "Clock recorded to minutes; true accuracy unknown.",
            "scope": "Birth-only fields. No sampling, individual exports, model scores or outcome fields read."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", required=True, type=Path)
    parser.add_argument("--census", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Choose a new output")
    summary = audit(args.archives, args.census)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
