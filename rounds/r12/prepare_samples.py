"""Reproduce and seal three birth-only INEGI samples before chart scoring."""
import argparse
from bisect import insort
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import heapq
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from study import R10, R11, digest, load_source, read_json, read_registration, require, write_json

sys.path.insert(0, str(R10 / "recovery/mexico2020"))
from rebuild_inputs import BIRTH_FIELDS, CATALOG_FIELDS, MODEL_KEYS
from rebuild_inputs import dbf_rows, normalize, reference_points, tz_version, valid_offsets


@dataclass(frozen=True)
class Candidate:
    source_id: str
    stratum: str
    civil: datetime
    registration: date
    point: tuple
    offset: int
    occurrence: str


def source_rows(path, year, birth_year, points, supported, audit):
    """Use the same restricted frame and exclusive exclusions as the R11 census."""
    target = f"birth_year_{birth_year}"
    with ZipFile(path) as z:
        members = {Path(n).name.lower(): n for n in z.namelist() if not n.endswith("/")}
        suffix = f"{year % 100:02d}"
        names = {}
        for _, deleted, row in dbf_rows(z, members["catemlna" + suffix + ".dbf"], CATALOG_FIELDS):
            if not deleted:
                key = row["CVE_ENT"] + row["CVE_MUN"] + row["CVE_LOC"]
                label = normalize(row["NOM_LOC"])
                require(names.setdefault(key, label) == label, "Conflicting locality catalogue entries")
        joined = {key: points[key] for key, label in names.items() if key in points and points[key][0] == label}
        birth_label, reg_label = str(birth_year), str(year)
        for number, deleted, row in dbf_rows(z, members["nacim" + suffix + ".dbf"], BIRTH_FIELDS):
            audit["physical_rows"] += 1
            if deleted or row["ANO_NAC"] != birth_label:
                continue
            audit[target] += 1
            sex = {"1": "M", "2": "F"}.get(row["SEXO"])
            state = row["ENT_OCURR"].zfill(2)
            if not sex or row["ANO_REG"] != reg_label:
                audit["exclude_sex_or_registration_year"] += 1
                continue
            try:
                civil = datetime(birth_year, int(row["MES_NAC"]), int(row["DIA_NAC"]),
                                 int(row["HORA_NAC"]), int(row["MINUTO_NAC"]))
                registration = date(year, int(row["MES_REG"]), int(row["DIA_REG"]))
            except ValueError:
                audit["exclude_invalid_birth_clock_or_date"] += 1
                continue
            if registration < civil.date():
                audit["exclude_chronology"] += 1
                continue
            occurrence = state + row["MUN_OCURR"].zfill(3) + row["LOC_OCURR"].zfill(4)
            point = joined.get(occurrence)
            stratum = state + "|" + sex
            if point is None or stratum not in supported:
                audit["exclude_locality_or_geography"] += 1
                continue
            offsets = valid_offsets(civil.isoformat(), point[3])
            if len(offsets) != 1:
                audit["exclude_ambiguous_historical_clock"] += 1
                continue
            audit["eligible"] += 1
            yield Candidate(f"INEGI-NACIM{year}-{number:08d}", stratum, civil, registration, point, offsets[0], occurrence)


def allocate(counts, target):
    minimum = {h: min(2, size) for h, size in counts.items()}
    total, base = sum(counts.values()), sum(minimum.values())
    require(base <= target <= total, "Sample cannot support the registered stratum minima")
    if target == total:
        return dict(counts)
    residual = {h: Fraction((target - base) * (size - minimum[h]), total - base)
                for h, size in counts.items()}
    quotas = {h: n + int(residual[h]) for h, n in minimum.items()}
    order = sorted(quotas, key=lambda h: (-(residual[h] % 1), h))
    for h in order[:target - sum(quotas.values())]:
        quotas[h] += 1
    require(sum(quotas.values()) == target and all(minimum[h] <= n <= counts[h] for h, n in quotas.items()),
            "Invalid sample allocation")
    return quotas


def candidates(spec, paths, claims, points, supported, years):
    for year in years:
        audit = Counter()
        yield from source_rows(paths[year], year, spec["birth_year"], points, supported, audit)
        expected = claims[spec["birth_year"], year]
        for name, value in expected.items():
            if name.startswith(("birth_year_", "exclude_")) or name in ("eligible", "physical_rows"):
                require(audit[name] == value, "Official archive count differs from R11: " + str(year) + "/" + name)


def select(spec, paths, claims, points, supported):
    def order(row):
        source_bytes = (spec["seed"] + "|" + row.source_id).encode()
        return int.from_bytes(sha256(source_bytes).digest(), "big"), row.source_id

    args = (spec, paths, claims, points, supported)
    counts, heaps = Counter(), defaultdict(list)
    for row in candidates(*args, spec["registration_years"]):
        counts[row.stratum] += 1
        rank, key = order(row)
        entry = (-rank, key, row)
        heap = heaps[row.stratum]
        if len(heap) < spec["sample_n"]:
            heapq.heappush(heap, entry)
        elif rank < -heap[0][0]:
            heapq.heapreplace(heap, entry)
    require(sum(counts.values()) == spec["frame_N"], "Eligible-frame total differs from preregistration")
    quotas = allocate(counts, spec["sample_n"])
    first = sorted(
        ((-rank, key, row) for h, heap in heaps.items()
         for rank, key, row in heapq.nlargest(quotas[h], heap)),
        key=lambda x: x[1],
    )
    # Reopen the archives in reverse year order. Verify using small sorted lists
    # with the final quotas, independently of the first pass's bounded heaps.
    second_counts, slices = Counter(), defaultdict(list)
    for row in candidates(*args, reversed(spec["registration_years"])):
        h = row.stratum
        second_counts[h] += 1
        rank, key = order(row)
        kept = slices[h]
        if len(kept) < quotas[h] or (rank, key) < kept[-1][:2]:
            insort(kept, (rank, key, row))
            if len(kept) > quotas[h]:
                kept.pop()
    second = sorted((entry for q in slices.values() for entry in q), key=lambda x: x[1])
    require(second_counts == counts and first == second and len(first) == spec["sample_n"],
            "Independent selection order did not reproduce the sample")
    return first, counts, quotas


def emit_sample(path, slot, spec, selected, counts, quotas):
    path.mkdir(mode=0o700)
    with (path / "birth_inputs.jsonl").open("x", encoding="utf-8") as inputs, \
         (path / "birth_metadata.jsonl").open("x", encoding="utf-8") as metadata:
        for rank, source_id, row in selected:
            _, latitude, longitude, zone = row.point
            sex = row.stratum[-1]
            birth = {
                "study_id": "R12-" + sha256(source_id.encode()).hexdigest()[:24],
                "birth_local": row.civil.isoformat(),
                "birth_utc": (row.civil - timedelta(seconds=row.offset)).isoformat() + "Z",
                "source_offset_seconds": row.offset,
                "sex_resolved": sex, "latitude": latitude, "longitude": longitude, "calendar": "gregorian",
                "time_precision_seconds": 60, "time_uncertainty_seconds": None, "coordinate_precision_degrees": None,
                "timezone_id": zone, "instant_scale": "UT",
            }
            size, n = counts[row.stratum], quotas[row.stratum]
            meta = {
                **birth,
                "sex": sex, "source": spec["source_label"], "source_id": source_id,
                "source_row_id": source_id, "birth_country": "MX", "quality": "administrative_minute",
                "geo_precision": "census_locality_reference", "stratum_id": row.stratum,
                "registration_archive_year": row.registration.year, "registration_date": row.registration.isoformat(),
                "occurrence_code": row.occurrence, "N_h": size, "n_h": n,
                "sample_weight": size / n, "inclusion_probability": n / size, "sampling_sha256": f"{rank:064x}",
            }
            inputs.write(json.dumps({key: birth[key] for key in MODEL_KEYS}, separators=(",", ":")) + "\n")
            metadata.write(json.dumps(meta, separators=(",", ":")) + "\n")
    manifest = {
        "slot": slot, "source": spec["source_label"], "birth_year": spec["birth_year"],
        "registration_archive_years": spec["registration_years"], "seed": spec["seed"], "tzdb": tz_version(),
        "eligible_frame_N": sum(counts.values()), "sample_n": len(selected),
        "model_input_sha256": digest(path / "birth_inputs.jsonl"),
        "metadata_sha256": digest(path / "birth_metadata.jsonl"),
        "strata": [{"stratum_id": h, "N_h": counts[h], "n_h": quotas[h]} for h in sorted(counts)],
    }
    write_json(path / "sampling_manifest.json", manifest)
    rows, _ = load_source(path)
    require(sum(Fraction(r["N_h"], r["n_h"]) for r in rows) == spec["frame_N"], "Exact weights do not sum to frame")
    return rows, {
        "birth_year": spec["birth_year"], "registration_years": spec["registration_years"],
        "eligible_frame_records": spec["frame_N"], "selected_records": len(rows),
        "state_sex_strata": len(counts),
        "noncensus_singletons": sum(n == 1 and counts[h] > 1 for h, n in quotas.items()),
        "extra_rows_with_matching_chart_input_tuples": len(rows) - len({r["chart_input_key"] for r in rows}),
        "private_file_sha256": {name: digest(path / name)
                                for name in ("birth_inputs.jsonl", "birth_metadata.jsonl", "sampling_manifest.json")},
    }


def prepare(args):
    registration = read_registration(args.registration_sha256)
    require(tz_version() == "2026c", "Use the registered IANA timezone database")
    source_evidence = read_json(R11 / "results/mexico_registration_sources.json")
    early20 = read_json(R10 / "mexico/samples/mexico2020/sampling_manifest.json")
    supported = {s["stratum_id"] for s in early20["strata"]}
    claims = {(2020, r["registration_year"]): r for r in source_evidence["source_archives"]}
    claims.update({(2023, r["registration_year"]): r for r in source_evidence["held_out_source_candidate"]["source_archives"]})
    archives = {year: args.archives / f"natalidad_base_datos_{year}_dbf.zip" for year in range(2022, 2026)}
    for year, path in archives.items():
        require(digest(path) == claims[2020, year]["sha256"], "Archive differs from R11 source audit")
    points = reference_points(args.iter_2020)
    frozen, _ = load_source(args.r10_job / "prepared/samples/mexico2020")
    known_source_ids = {r["source_id"] for r in frozen}
    args.output.mkdir(mode=0o700)
    receipt = {}
    for slot, spec in registration["samples"].items():
        print(f"Screening {slot}: {spec['registration_years']}", flush=True)
        kept, counts, quotas = select(spec, archives, claims, points, supported)
        rows, receipt[slot] = emit_sample(args.output / slot, slot, spec, kept, counts, quotas)
        identifiers = {r["source_id"] for r in rows}
        require(len(identifiers) == len(rows) and not known_source_ids.intersection(identifiers), "Source row overlap")
        known_source_ids.update(identifiers)
        print(f"Verified and sealed {slot}: {len(rows)} of {sum(counts.values())}", flush=True)
    result = {
        "id": registration["id"], "status": "two_source_passes_match",
        "registration_sha256": args.registration_sha256,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "samples": receipt,
        "original_records_score_accessed": False,
        "physical_source_row_overlap": 0,
        "replay_scope": "Same eligibility decoder, independent forward heap and reverse ordered-list sampling, "
                        "and matching R11 archive totals and exclusions.",
    }
    write_json(args.output / "receipt.json", result)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archives", "iter-2020", "r10-job", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--registration-sha256", required=True)
    prepare(p.parse_args())
