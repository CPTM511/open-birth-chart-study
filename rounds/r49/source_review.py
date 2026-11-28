"""Compare a fresh sample rebuild and reread its selected physical source records."""

import argparse
from collections import defaultdict
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path
from zipfile import ZipFile

from rounds.r9.data.mexico.audit_mexico2015 import dbf_header
from rounds.r13.sources.audit_mexico_1990s import CATALOG_FIELDS, dbf_rows, normalize, reference_points
from rounds.r45.prepare import mexico
from rounds.r46.prepare import prior_sample
from rounds.r46.source_review import same_birth, verify_brazil, verify_mexico

from .common import GROUPS, REGISTRATION, ROOT, R10, digest, input_receipt, inputs, private, protocol, read_json, require, write_json
from .mexico1999 import archive_name


def verify_early_mexico(directory, rows, captures, points):
    selected = defaultdict(dict)
    for row in rows:
        citation, position = row["source_id"].rsplit("-", 1)
        year, index = int(citation.removeprefix("INEGI-NACIM")), int(position)
        require(index not in selected[year], "Duplicate archive row in the reconstructed census")
        selected[year][index] = row
    counts = {}
    for receipt in captures:
        year = receipt["year"]
        path = directory / archive_name(year)
        if "sha256" not in receipt:
            require(not path.exists() and not selected[year], "Unexpected unavailable official archive")
            continue
        require(digest(path) == receipt["sha256"], "INEGI 2011–2016 file differs from the input seal")
        if not receipt["included"]:
            require(not selected[year], "An incompatible archive entered the scored sample")
            continue
        indexes = selected[year]
        require(len(indexes) == receipt.get("eligible", 0), "INEGI census by file differs")
        with ZipFile(path) as archive:
            members = {Path(path).name.lower(): path for path in archive.namelist()}
            catalog = members[receipt["occurrence_catalog_table"]]
            names = {entry["CVE_ENT"] + entry["CVE_MUN"] + entry["CVE_LOC"]: normalize(entry["NOM_LOC"])
                     for _, deleted, entry in dbf_rows(archive, catalog, CATALOG_FIELDS) if not deleted}
            with archive.open(members[receipt["birth_table"]]) as stream:
                length, width, fields, encoding = dbf_header(stream)
                header = stream.tell()
                month = receipt["birth_month_descriptor"]
                born = ("ANO_NAC", month, "DIA_NAC", "HORA_NAC", "MINUTO_NAC")
                registered = ("ANO_REG", "MES_REG", "DIA_REG")
                places = ("ENT_OCURR", "MUN_OCURR", "LOC_OCURR")
                columns = (*born, *registered, *places, "SEXO")
                slices = {name: slice(fields[name][0], fields[name][0] + fields[name][1]) for name in columns}
                require(length == receipt["source_rows"], "Original INEGI row count changed")
                for index, row in sorted(indexes.items()):
                    require(1 <= index <= length, "Source row ordinal out of range")
                    stream.seek(header + (index - 1) * width)
                    raw = stream.read(width)
                    require(len(raw) == width and raw[:1] == b" ", "Original INEGI row is missing or deleted")
                    value = {name: raw[span].decode(encoding).strip() for name, span in slices.items()}
                    birth = datetime(*(int(value[name]) for name in born))
                    registration = date(*(int(value[name]) for name in registered))
                    code = "".join(value[name].zfill(places_n) for name, places_n in zip(places, (2, 3, 4), strict=True))
                    expected_name, lat, lon, zone = points[code]
                    require(registration.year == year and birth.date() <= registration and birth.year == 1999
                            and names[code] == expected_name, "Original historical locality record or date inconsistent")
                    same_birth(row, birth, {"1": "M", "2": "F"}[value["SEXO"]], lat, lon, zone)
        counts[str(year)] = len(indexes)
    require(sum(counts.values()) == len(rows), "The independently reread source is incomplete")
    return {"selected_rows_verified": len(rows), "selected_per_registration_year": counts,
            "aliases_reread_from_original": sorted(item["year"] for item in captures if "month_descriptor_normalized_from" in item)}


def earlier_keys(args):
    sources = []
    for run, name in ((args.r13_job, "r13"), (args.r15_job, "r15")):
        seal = read_json(ROOT / "rounds" / name / "INPUT_SEAL.json")["private_input_sha256"]
        sources.append(prior_sample(run / "sample", seal)[0])
    r10 = next(row for row in read_json(R10 / "independent_replay/prepared_receipt.json")["groups"]
               if row["slot"] == "mexico_2000s")
    sources.append(prior_sample(args.r10_job / "prepared/samples/mexico_2000s", {
        "birth_inputs.jsonl": r10["input_sha256"], "birth_metadata.jsonl": r10["metadata_used_sha256"],
        "sampling_manifest.json": r10["manifest_used_sha256"],
    })[0])
    r45 = read_json(ROOT / "rounds/r45/SOURCE_SEALS.json")["draws"]
    for group in ("br2009", "mx2009"):
        sources.append(prior_sample(args.r45_job / group / "sample", r45[group]["sha256"])[0])
    for group in GROUPS:
        r46 = read_json(ROOT / "rounds/r46/seals" / f"{group}.json")
        sources.append(prior_sample(args.r46_job / group / "sample", r46["sha256"])[0])
    return set().union(*sources)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("job", "replay-job", "r10-job", "r13-job", "r15-job", "r45-job", "r46-job",
                "br1999", "br2009", "references", "mex-modern", "mex-old", "iter", "seats", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    protocol()
    job, replay = private(args.job), private(args.replay_job)
    require(job.resolve() != replay.resolve(), "Use a separate source rebuild")
    references = read_json(args.references)
    old = earlier_keys(args)
    used = set()
    report = {}
    for group in GROUPS:
        seal = input_receipt(job, group)
        require(seal == input_receipt(replay, group), "Second reconstruction did not reproduce the seal")
        if not seal["records"]:
            evidence = verify_early_mexico(args.mex_modern, [], seal["archives"], {})
        else:
            rows, _, _ = inputs(job, group)
            again, _, _ = inputs(replay, group)
            require(rows == again, "Second reconstruction selected other birth records")
            keys = {row["source_id"] for row in rows}
            require(len(keys) == len(rows) and not (keys & used) and not (keys & old), "Birth input overlaps another draw")
            used.update(keys)
            require(sum(Fraction(row["N_h"], row["n_h"]) for row in rows) == seal["eligible_frame_N"],
                    "Design weights do not cover the residual frame exactly")
            if group.startswith("br"):
                path = getattr(args, group)
                require(digest(path) == seal["source_archive_sha256"]
                        and digest(args.references) == seal["municipality_reference_sha256"], "Wrong frozen Brazil source")
                evidence = verify_brazil(path, rows, references, int(group[2:]))
            elif group == "mx1999":
                require(digest(args.iter) == seal["iter_2020_sha256"], "Wrong INEGI locality reference")
                evidence = verify_early_mexico(args.mex_modern, rows, seal["archives"], reference_points(args.iter))
            else:
                paths = {int(year): args.mex_old / year / archive_name(year) for year in seal["source_archive_sha256"]}
                require(all(digest(path) == seal["source_archive_sha256"][str(year)] for year, path in paths.items()),
                        "Wrong older Mexico archives")
                points, geography = mexico.municipal_points(args.seats, args.iter)
                receipt = read_json(R10 / "recovery/mexico2009/replay_receipt.json")
                require(geography == receipt["seat_catalog_sha256"], "Wrong older Mexico geography snapshot")
                evidence = verify_mexico(paths, rows, points, modern=False)
        report[group] = dict(evidence, independently_rebuilt_seal_matches=True, input_seal_sha256=seal["input_seal_sha256"])
    require(len(used) == sum(group["selected_rows_verified"] for group in report.values()), "Incomplete source verification")
    write_json(args.output, dict(registration=REGISTRATION, groups=report, physical_rows_verified=len(used),
                                prior_physical_keys_checked=len(old), prior_draw_physical_overlap=0,
                                cross_group_physical_overlap=0, geographic_dictionary_shared=True))


if __name__ == "__main__":
    main()
