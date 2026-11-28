"""Count birth-only source frames and draw records disjoint from R10 and R45."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import heapq
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from rounds.r45.common import load_source, source_seal
from rounds.r45.prepare import allocate, brazil, make_sample, mexico, model_row, r8
from rounds.r13.sources.audit_mexico_1990s import inspect_archive, reference_points
from rounds.r15.brazil_1999 import audit_source

from .common import GROUPS, REGISTRATION, ROOT, R10, digest, private, protocol, read_json, require, verify_files, write_json


def prior_sample(folder, sha):
    verify_files(folder, sha)
    rows, manifest = load_source(folder)
    excluded = {r["source_id"]: r["stratum_id"] for r in rows}
    require(len(excluded) == len(rows), "Legacy physical IDs are not unique")
    return excluded, {x["stratum_id"]: x["N_h"] for x in manifest["strata"]}


def residual_counts(population, remove):
    exclusions = Counter(remove.values())
    require(set(exclusions) <= set(population) and all(population[h] >= n for h, n in exclusions.items()),
            "Removed rows exceed the source frame")
    return {h: N-exclusions[h] for h, N in population.items() if N > exclusions[h]}


def shortlist(pool, count, key, fields):
    ranked = (-int(key, 16), key, fields)
    if len(pool) < count:
        heapq.heappush(pool, ranked)
    elif ranked[0] > pool[0][0]:
        heapq.heapreplace(pool, ranked)


def brazil_holdout(args, spec, folder, year):
    if year == 1999:
        predecessor = read_json(ROOT / "rounds/r15/INPUT_SEAL.json")["private_input_sha256"]
        previous = args.r15_job / "sample"
        published = read_json(ROOT / "rounds/r15/source_audit.json")
        archive_sha = published["archive"]["sha256"]
        reference_sha = published["municipality_reference_sha256"]
    else:
        published = read_json(ROOT / "rounds/r45/SOURCE_SEALS.json")["draws"]["br2009"]
        predecessor, previous = published["sha256"], args.r45_job / "br2009/sample"
        archive_sha, reference_sha = published["archive_sha256"], published["municipality_reference_sha256"]
    excluded, population = prior_sample(previous, predecessor)
    require(digest(args.brazil_archive) == archive_sha and digest(args.references) == reference_sha,
            "Brazil archive or official geography differs")
    refs = read_json(args.references)
    if year == 1999:
        old_audit = {}
        prior = audit_source(args.brazil_archive, refs, old_audit, retain=True)
        entered = (data for bucket in prior.values() for _, _, data in bucket)
    else:
        entered = brazil.prior.eligible(args.brazil_archive, year, refs)
    counts = residual_counts(population, excluded)
    quotas = allocate(counts, spec["sampling"]["sample_n"])
    seed = spec["sampling"]["brazil_seed"]
    totals, hits, pools = Counter(), set(), defaultdict(list)
    for ordinal, civil, sex, muni, offset, h in entered:
        totals[h] += 1
        key = f"SINASC{year}:row:{ordinal:07d}"
        if key in excluded:
            require(h == excluded[key], "Legacy Brazil source ID moved across strata")
            hits.add(key)
            continue
        rank = sha256((seed+"|"+key).encode()).hexdigest()
        shortlist(pools[h], quotas[h], rank, (key, ordinal, civil, sex, muni, offset))
    require(totals == population and hits == set(excluded), "Brazil source frame or exclusions differ")
    source = f"SINASC-{year}-R46"
    rows = []
    for h, pool in pools.items():
        require(len(pool) == quotas[h], "Brazil stratum sample is incomplete")
        for _, rank, (key, ordinal, civil, sex, muni, offset) in pool:
            point = refs[muni]
            require(r8.valid_offsets(civil, point["timezone_id"]) == (offset,), "Wrong Brazil historical offset")
            row = model_row(key, civil, offset, sex, point)
            rows.append(dict(row, source=source, source_id=key, source_row_id=str(ordinal), sex=sex,
                             birth_country="BR", quality=r8.BRAZIL_QUALITY, sampling_sha256=rank,
                             **r8.weight_metadata(h, counts, quotas)))
    seal = make_sample(folder, rows, counts, quotas, {"source": source, "seed": seed})
    return dict(seal, source_archive_sha256=archive_sha, municipality_reference_sha256=reference_sha,
                eligibility_before_exclusions=sum(population.values()), old_rows_excluded=len(hits),
                legacy_physical_overlap=0)


def mexico2009_holdout(args, spec, folder):
    legacy = read_json(R10 / "mexico/samples/mexico_2000s/sampling_manifest.json")
    released = read_json(R10 / "recovery/mexico2009/replay_receipt.json")
    r10 = next(item for item in read_json(R10 / "independent_replay/prepared_receipt.json")["groups"]
               if item["slot"] == "mexico_2000s")
    old, population = prior_sample(args.r10_job / "prepared/samples/mexico_2000s",
        {"birth_inputs.jsonl": r10["input_sha256"], "birth_metadata.jsonl": r10["metadata_used_sha256"],
         "sampling_manifest.json": r10["manifest_used_sha256"]})
    r45 = read_json(ROOT / "rounds/r45/SOURCE_SEALS.json")["draws"]["mx2009"]["sha256"]
    r45_keys, prior_frame = prior_sample(args.r45_job / "mx2009/sample", r45)
    require(not old.keys() & r45_keys.keys() and prior_frame == residual_counts(population, old),
            "Mismatched previous Mexico ranked draws")
    counts = residual_counts(population, old | r45_keys)
    quotas = allocate(counts, spec["sampling"]["sample_n"])
    n_old, n_r45 = Counter(old.values()), Counter(r45_keys.values())
    totals = {h: n_old[h]+n_r45[h]+quotas.get(h, 0) for h in population}
    points, geo_digests = mexico.municipal_points(args.seats, args.iter)
    require(geo_digests == released["seat_catalog_sha256"], "INEGI municipal-seat snapshots changed")
    pools, observed = defaultdict(list), Counter()
    for year in legacy["registration_archive_years"]:
        archive = args.mex_old / f"{year}/natalidad_base_datos_{year}_dbf.zip"
        archive_sha = legacy["archive_sha256"][str(year)]
        mexico.require_hash(archive, archive_sha)
        audit = mexico.sample_archive(year, archive, points, totals, legacy["seed"], pools, observed)
        require({"sha256": archive_sha, **audit} == released["archives"][str(year)], "INEGI archive count changed")
    require(observed == population, "The original INEGI frame cannot be reproduced")
    rows, prior_old, prior_r45 = [], {}, {}
    for h in sorted(totals):
        ranked = sorted(pools[h], key=lambda item: -item[0])
        require(len(ranked) == totals[h], "Insufficient ordered Mexico rows")
        prior_old.update({entry[1]: h for entry in ranked[:n_old[h]]})
        start = n_old[h]+n_r45[h]
        prior_r45.update({entry[1]: h for entry in ranked[n_old[h]:start]})
        for negative, key, civil, sex, (_, lat, lon, zone), offset in ranked[start:]:
            row = model_row(key, civil, offset, sex, dict(latitude=lat, longitude=lon, timezone_id=zone))
            require(mexico.valid_offsets(civil.isoformat(), zone) == (offset,), "Wrong Mexican historical offset")
            rows.append(dict(row, source="INEGI-birth2009-R46", source_id=key, source_row_id=key.rsplit("-",1)[1],
                             birth_country="MX", sex=sex, geo_precision="recovered_2020_municipal_seat",
                             quality="verified_official_inegi_design", sampling_sha256=f"{-negative:064x}",
                             **r8.weight_metadata(h, counts, quotas)))
    require(prior_old == old and prior_r45 == r45_keys, "Either earlier Mexico sample fails exact physical-key replay")
    seal = make_sample(folder, rows, counts, quotas, {"source": "INEGI-birth2009-R46", "seed": legacy["seed"]})
    return dict(seal, source_archive_sha256=legacy["archive_sha256"], eligibility_before_exclusions=sum(population.values()),
                old_r10_rows_excluded=len(old), old_r45_rows_excluded=len(r45_keys), legacy_physical_overlap=0)


def normalize_2017_month(archive, destination):
    """Rename only the documented month descriptor for the unchanged R13 parser."""
    with ZipFile(archive) as source, ZipFile(destination, "x") as derived:
        members = {Path(member).name.lower(): member for member in source.namelist()}
        with source.open(members["catemlna17.dbf"]) as f, derived.open("catemlna17.dbf", "w") as out:
            copyfileobj(f, out)
        with source.open(members["nacim17.dbf"]) as f, derived.open("nacim17.dbf", "w") as out:
            lead = f.read(32)
            size = int.from_bytes(lead[8:10], "little")
            descriptors = bytearray(f.read(size-32))
            end = range(0, len(descriptors)-1, 32)
            names = {bytes(descriptors[i:i+11]).rstrip(b"\0").upper(): i for i in end}
            require(descriptors[-1] == 13 and b"MES_NAC" not in names and b"MES_NACIM" in names,
                    "The 2017 month header differs from the documented alias")
            index = names[b"MES_NACIM"]
            descriptors[index:index+11] = b"MES_NAC".ljust(11,b"\0")
            out.write(lead)
            out.write(descriptors)
            copyfileobj(f, out)


def mexico1999_census(args, spec, folder):
    availability = read_json(args.mex_index)
    require([x["year"] for x in availability] == spec["sampling"]["mx1999_registration_years"], "Wrong Mexico census years")
    historical = read_json(R10 / "mexico/samples/mexico2020/sampling_manifest.json")
    allowed = {item["stratum_id"] for item in historical["strata"]}
    points = reference_points(args.iter)
    selected, source_audits = [], []

    def capture(year, ordinal, civil, _, code, h, point, offset):
        if civil.year == 1999:
            selected.append((year, ordinal, civil, code, h, point, offset))

    strata = defaultdict(Counter)
    for source in availability:
        year = source["year"]
        if not source["included"]:
            source_audits.append(source)
            continue
        archive = args.mex_modern / f"natalidad_base_datos_{year}_dbf.zip"
        require(digest(archive) == source["sha256"], "Late INEGI archive differs")
        if str(year) in historical["archive_sha256"]:
            require(source["sha256"] == historical["archive_sha256"][str(year)], "R10 INEGI archive changed")
        if year == 2017:
            with TemporaryDirectory(dir=args.job) as temporary:
                canonical = Path(temporary) / "nacimientos-canonical.zip"
                normalize_2017_month(archive, canonical)
                n, counts = inspect_archive(canonical, year, points, allowed, strata, older_birth=capture)
        else:
            n, counts = inspect_archive(archive, year, points, allowed, strata, older_birth=capture)
        source_audits.append(dict(source, source_rows=n, **counts[1999]))
    require(len(selected) == sum(strata[1999].values()) > 0, "No qualifying Mexico 1999 births")
    rows, source = [], "INEGI-birth1999-registered2017_2021-R46"
    for year, ordinal, civil, _, h, (_, lat, lon, zone), offset in selected:
        key = f"INEGI-NACIM{year}-{ordinal:08d}"
        sex = h[-1]
        row = model_row(key, civil, offset, sex, dict(latitude=lat, longitude=lon, timezone_id=zone))
        rows.append(dict(row, source=source, source_id=key, source_row_id=str(ordinal), birth_country="MX", sex=sex,
                         geo_precision="official_occurrence_locality_reference", quality="recorded_late_registry_clock",
                         sampling_sha256=sha256(key.encode()).hexdigest(),
                         **r8.weight_metadata(h, strata[1999], strata[1999])))
    seal = make_sample(folder, rows, strata[1999], strata[1999], {"source": source, "full_eligible_census": True})
    return dict(seal, archives=source_audits, legacy_physical_overlap=0, physical_keys_not_identified_people=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=GROUPS)
    parser.add_argument("--job", type=Path, required=True)
    for key in ("brazil-archive", "references", "r15-job", "r45-job", "r10-job", "mex-old", "seats",
                "iter", "mex-index", "mex-modern"):
        parser.add_argument("--"+key, type=Path)
    args = parser.parse_args()
    spec = protocol()
    require(mexico.tz_version() == spec["sampling"]["timezone_database"], "Use the registered IANA edition")
    destination = private(args.job) / args.group
    require(not destination.exists(), "Use a new holdout folder")
    with TemporaryDirectory(dir=args.job) as temporary:
        stage = Path(temporary) / args.group
        stage.mkdir()
        if args.group.startswith("br"):
            seal = brazil_holdout(args, spec, stage / "sample", int(args.group[2:]))
        elif args.group == "mx2009":
            seal = mexico2009_holdout(args, spec, stage / "sample")
        else:
            seal = mexico1999_census(args, spec, stage / "sample")
        require(seal["records"] == source_seal(stage / "sample")["records"], "Seal sample count differs")
        write_json(stage / "input_seal.json", dict(seal, registration=REGISTRATION, group=args.group))
        stage.rename(destination)
    print(args.group, seal["records"], seal["eligible_frame_N"], digest(destination / "input_seal.json"))


if __name__ == "__main__":
    main()
