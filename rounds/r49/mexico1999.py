"""Screen INEGI 2011–2016 schemas and reconstruct the admissible 1999-born census."""

from collections import Counter, defaultdict
from hashlib import file_digest, sha256
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from rounds.r9.data.mexico.audit_mexico2015 import dbf_header
from rounds.r13.sources.audit_mexico_1990s import BIRTH_FIELDS, CATALOG_FIELDS, inspect_archive, reference_points
from rounds.r45.prepare import make_sample, model_row, r8
from rounds.r46.prepare import prior_sample

from .common import ROOT, R10, digest, read_json, require


def archive_name(year):
    return f"natalidad_base_datos_{year}_dbf.zip"


def rows_born_in_1999(stream, length, width, schema):
    offset, size = schema["ANO_NAC"][:2]
    count = 0
    for start in range(0, length, 8192):
        records = min(length - start, 8192)
        block = stream.read(records * width)
        require(len(block) == records * width, "Short DBF in the recorded year field audit")
        for row in range(0, len(block), width):
            count += block[row:row + 1] == b" " and block[row + offset:row + offset + size].strip() == b"1999"
    return count


def check_schema(path, year):
    birth_name = f"nacim{year % 100:02d}.dbf"
    catalog_name = f"catemlna{year % 100:02d}.dbf"
    url = f"https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/{year}/{archive_name(year)}"
    row = dict(year=year, url=url)
    if not path.is_file():
        return dict(row, included=False, reason="official archive not retrieved")

    row.update(sha256=digest(path), archive_bytes=path.stat().st_size)
    with ZipFile(path) as archive:
        members = {Path(name).name.lower(): name for name in archive.namelist() if not name.endswith("/")}
        missing = []
        source_catalog = "catemln14.dbf" if year == 2014 and catalog_name not in members else catalog_name
        if source_catalog not in members:
            missing.append(catalog_name)
        else:
            row["occurrence_catalog_table"] = source_catalog
            with archive.open(members[source_catalog]) as stream:
                _, _, fields, _ = dbf_header(stream)
                missing.extend(f"{source_catalog}:{name}" for name in CATALOG_FIELDS if name not in fields)
        documents = sorted(name for name in members if name.endswith(".pdf") and "descripcion" in name)
        if documents:
            with archive.open(members[documents[0]]) as stream:
                row.update(embedded_dictionary_pdf=documents[0], embedded_dictionary_sha256=file_digest(stream, "sha256").hexdigest())
        if birth_name not in members:
            return dict(row, included=False, reason="required DBF table missing", missing_fields_or_tables=missing+[birth_name])
        with archive.open(members[birth_name]) as stream:
            length, width, fields, _ = dbf_header(stream)
            row.update(source_rows=length, birth_table=birth_name,
                       has_occurrence_locality="LOC_OCURR" in fields,
                       has_recorded_hour_and_minute={"HORA_NAC", "MINUTO_NAC"} <= fields.keys(),
                       birth_month_descriptor=next((m for m in ("MES_NAC", "MES_NACIM") if m in fields), None))
            columns = set(fields)
            if year == 2015 and "MES_NACIM" in fields and "MES_NAC" not in fields:
                columns.add("MES_NAC")
                row["month_descriptor_normalized_from"] = "MES_NACIM"
                row["month_descriptor_documentation"] = "https://www.inegi.org.mx/rnm/index.php/catalog/246/data-dictionary/F10"
            missing.extend(f"{birth_name}:{name}" for name in BIRTH_FIELDS if name not in columns)
            if missing:
                if "ANO_NAC" in fields:
                    row["observed_birth_year"] = rows_born_in_1999(stream, length, width, fields)
                return dict(row, included=False, reason="registered locality or source fields missing",
                            missing_fields_or_tables=missing)
    return dict(row, included=True)


def adapt_archive(path, destination, evidence):
    """Give the unmodified catalog and birth rows their registered parser names."""
    canonical_catalog = f"catemlna{evidence['year'] % 100:02d}.dbf"
    birth_name = evidence["birth_table"]
    with ZipFile(path) as original, ZipFile(destination, "x") as adapted:
        members = {Path(name).name.lower(): name for name in original.namelist()}
        with original.open(members[evidence["occurrence_catalog_table"]]) as source, adapted.open(canonical_catalog, "w") as out:
            copyfileobj(source, out)
        with original.open(members[birth_name]) as source, adapted.open(birth_name, "w") as out:
            if "month_descriptor_normalized_from" in evidence:
                prefix = source.read(32)
                size = int.from_bytes(prefix[8:10], "little")
                descriptors = bytearray(source.read(size - 32))
                names = {bytes(descriptors[i:i + 11]).rstrip(b"\0").upper(): i for i in range(0, len(descriptors) - 1, 32)}
                require(descriptors[-1] == 13 and b"MES_NAC" not in names and b"MES_NACIM" in names,
                        "Published birth month alias changed")
                index = names[b"MES_NACIM"]
                descriptors[index:index + 11] = b"MES_NAC".ljust(11, b"\0")
                out.write(prefix)
                out.write(descriptors)
            copyfileobj(source, out)


def census(args, settings, folder):
    receipt = read_json(R10 / "recovery/mexico2009/replay_receipt.json")
    require(digest(args.iter) == receipt["iter_2020_sha256"], "The fixed national INEGI 2020 locality reference changed")
    r13 = read_json(ROOT / "rounds/r13/INPUT_SEAL.json")["private_input_sha256"]
    older_r13, _ = prior_sample(args.r13_job / "sample", r13)
    claim = read_json(ROOT / "rounds/r46/seals/mx1999.json")
    require(digest(args.r46_job / "mx1999/input_seal.json") == claim["input_seal_sha256"], "R46 Mexico 1999 seal changed")
    older_r46, _ = prior_sample(args.r46_job / "mx1999/sample", claim["sha256"])
    require(not (older_r13.keys() & older_r46.keys()), "Prior Mexico physical records overlap")
    historical = read_json(R10 / "mexico/samples/mexico2020/sampling_manifest.json")
    allowed = {item["stratum_id"] for item in historical["strata"]}
    points = reference_points(args.iter)
    strata, selected = defaultdict(Counter), []

    def retain(year, index, civil, _, code, stratum, point, offset):
        if civil.year == 1999:
            selected.append((year, index, civil, stratum, point, offset))

    sources = []
    for year in settings["sampling"]["mx1999_registration_years"]:
        path = args.mex_modern / archive_name(year)
        evidence = check_schema(path, year)
        if evidence["included"]:
            canonical = f"catemlna{year % 100:02d}.dbf"
            if evidence["occurrence_catalog_table"] != canonical or "month_descriptor_normalized_from" in evidence:
                with TemporaryDirectory(dir=args.job) as temporary:
                    adapted = Path(temporary) / "parsed.zip"
                    adapt_archive(path, adapted, evidence)
                    n_rows, counts = inspect_archive(adapted, year, points, allowed, strata, older_birth=retain)
            else:
                n_rows, counts = inspect_archive(path, year, points, allowed, strata, older_birth=retain)
            require(n_rows == evidence["source_rows"], "INEGI archive row count differs from its header")
            evidence.update(counts[1999])
        sources.append(evidence)

    counts = strata[1999]
    require(len(selected) == sum(counts.values()), "Invalid Mexico census denominator")
    common = dict(archives=sources, iter_2020_sha256=receipt["iter_2020_sha256"], legacy_physical_overlap=0,
                  predecessor_physical_records_checked={"r13": len(older_r13), "r46": len(older_r46)},
                  physical_keys_not_identified_people=True)
    if not selected:
        return dict(common, records=0, eligible_frame_N=0, strata=0)
    source = "INEGI-birth1999-registered2011_2016-R49"
    rows = []
    for year, index, civil, stratum, (_, lat, lon, zone), offset in selected:
        key = f"INEGI-NACIM{year}-{index:08d}"
        require(key not in older_r13 and key not in older_r46, "R49 Mexico 1999 repeats an earlier physical record")
        row = model_row(key, civil, offset, stratum[-1], dict(latitude=lat, longitude=lon, timezone_id=zone))
        rows.append(dict(row, source=source, source_id=key, source_row_id=str(index), birth_country="MX",
                         sex=stratum[-1], geo_precision="official_occurrence_locality_reference",
                         quality="recorded_late_registry_clock", sampling_sha256=sha256(key.encode()).hexdigest(),
                         **r8.weight_metadata(stratum, counts, counts)))
    require(len(rows) == len({row["source_id"] for row in rows}), "Duplicate INEGI physical row")
    sample = make_sample(folder, rows, counts, counts, {"source": source, "full_eligible_census": True})
    return dict(sample, **common)
