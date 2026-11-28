"""Reconstruct the registered R49 birth-only frames and seal their physical holdouts."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from rounds.r45.prepare import allocate, brazil, make_sample, mexico, model_row, r8
from rounds.r46.prepare import prior_sample, residual_counts, shortlist
from rounds.r15.brazil_1999 import audit_source

from .common import GROUPS, REGISTRATION, ROOT, R10, digest, private, protocol, read_json, require, write_json


def r46_predecessor(args, group):
    public = read_json(ROOT / "rounds/r46/seals" / f"{group}.json")
    require(digest(args.r46_job / group / "input_seal.json") == public["input_seal_sha256"],
            "R46 predecessor seal changed")
    return prior_sample(args.r46_job / group / "sample", public["sha256"])


def add_exclusion(previous, population, predecessor):
    new_rows, new_frame = predecessor
    require(not (previous.keys() & new_rows.keys()) and new_frame == residual_counts(population, previous),
            "Predecessor physical keys or residual strata disagree")
    return previous | new_rows


def brazil_holdout(args, settings, folder, year):
    group = f"br{year}"
    if year == 1999:
        old_hashes = read_json(ROOT / "rounds/r15/INPUT_SEAL.json")["private_input_sha256"]
        original = args.r15_job / "sample"
        source_receipt = read_json(ROOT / "rounds/r15/source_audit.json")
        archive_sha = source_receipt["archive"]["sha256"]
        prior_round = "r15"
    else:
        source_receipt = read_json(ROOT / "rounds/r45/SOURCE_SEALS.json")["draws"][group]
        old_hashes = source_receipt["sha256"]
        original = args.r45_job / group / "sample"
        archive_sha = source_receipt["archive_sha256"]
        prior_round = "r45"
    reference_sha = source_receipt["municipality_reference_sha256"]
    require(digest(args.brazil_archive) == archive_sha and digest(args.references) == reference_sha,
            "SINASC archive or municipal reference changed")
    first, population = prior_sample(original, old_hashes)
    excluded = add_exclusion(first, population, r46_predecessor(args, group))
    require(len(first) == 2000 and len(excluded) == 6000, "Wrong Brazil predecessor totals")
    references = read_json(args.references)
    if year == 1999:
        archive_rows = audit_source(args.brazil_archive, references, {}, retain=True)
        eligible = (row for bucket in archive_rows.values() for _, _, row in bucket)
    else:
        eligible = brazil.prior.eligible(args.brazil_archive, year, references)

    frame = residual_counts(population, excluded)
    quotas = allocate(frame, settings["sampling"]["sample_n"])
    seed = settings["sampling"]["brazil_seed"]
    counts, seen, pools = Counter(), set(), defaultdict(list)
    for ordinal, civil, sex, municipality, offset, stratum in eligible:
        key = f"SINASC{year}:row:{ordinal:07d}"
        counts[stratum] += 1
        if key in excluded:
            require(excluded[key] == stratum, "Excluded Brazil row changed strata")
            seen.add(key)
            continue
        rank = sha256((seed + "|" + key).encode()).hexdigest()
        shortlist(pools[stratum], quotas[stratum], rank, (key, ordinal, civil, sex, municipality, offset))
    require(counts == population and seen == excluded.keys(), "Brazil frame or excluded rows differ")
    require({h: len(bucket) for h, bucket in pools.items()} == quotas, "Brazil quotas were not met")

    source = f"SINASC-{year}-R49"
    rows = []
    for stratum, bucket in pools.items():
        for _, rank, (key, ordinal, civil, sex, municipality, offset) in bucket:
            point = references[municipality]
            require(r8.valid_offsets(civil, point["timezone_id"]) == (offset,), "Brazil historical hour mismatch")
            row = model_row(key, civil, offset, sex, point)
            rows.append(dict(row, source=source, source_id=key, source_row_id=str(ordinal), sex=sex,
                             birth_country="BR", quality=r8.BRAZIL_QUALITY, sampling_sha256=rank,
                             **r8.weight_metadata(stratum, frame, quotas)))
    seal = make_sample(folder, rows, frame, quotas, {"source": source, "seed": seed})
    return dict(seal, source_archive_sha256=archive_sha, municipality_reference_sha256=reference_sha,
                eligibility_before_exclusions=sum(population.values()), excluded_by_round={prior_round: 2000, "r46": 4000},
                legacy_physical_overlap=0)


def mexico2009_holdout(args, settings, folder):
    legacy = read_json(R10 / "mexico/samples/mexico_2000s/sampling_manifest.json")
    reconstruction = read_json(R10 / "recovery/mexico2009/replay_receipt.json")
    r10 = next(row for row in read_json(R10 / "independent_replay/prepared_receipt.json")["groups"]
               if row["slot"] == "mexico_2000s")
    first, population = prior_sample(args.r10_job / "prepared/samples/mexico_2000s", {
        "birth_inputs.jsonl": r10["input_sha256"], "birth_metadata.jsonl": r10["metadata_used_sha256"],
        "sampling_manifest.json": r10["manifest_used_sha256"],
    })
    r45_hashes = read_json(ROOT / "rounds/r45/SOURCE_SEALS.json")["draws"]["mx2009"]["sha256"]
    r45_rows, r45_frame = prior_sample(args.r45_job / "mx2009/sample", r45_hashes)
    prior_two = add_exclusion(first, population, (r45_rows, r45_frame))
    r46_rows, r46_frame = r46_predecessor(args, "mx2009")
    excluded = add_exclusion(prior_two, population, (r46_rows, r46_frame))
    batches = (first, r45_rows, r46_rows)
    require([len(batch) for batch in batches] == [2000, 2000, 4000], "Wrong INEGI predecessor totals")
    frame = residual_counts(population, excluded)
    quota = allocate(frame, settings["sampling"]["sample_n"])
    prior_sizes = [Counter(batch.values()) for batch in batches]
    capacities = {h: sum(size[h] for size in prior_sizes) + quota.get(h, 0) for h in population}

    points, geo_digests = mexico.municipal_points(args.seats, args.iter)
    require(geo_digests == reconstruction["seat_catalog_sha256"], "INEGI municipal-seat references changed")
    pools, observed = defaultdict(list), Counter()
    for year in legacy["registration_archive_years"]:
        archive = args.mex_old / f"{year}/natalidad_base_datos_{year}_dbf.zip"
        archive_sha = legacy["archive_sha256"][str(year)]
        mexico.require_hash(archive, archive_sha)
        audit = mexico.sample_archive(year, archive, points, capacities, legacy["seed"], pools, observed)
        require({"sha256": archive_sha, **audit} == reconstruction["archives"][str(year)],
                "An original INEGI archive count changed")
    require(observed == population, "The INEGI 2009 birth frame changed")

    source = "INEGI-birth2009-R49"
    verified = [{}, {}, {}]
    rows = []
    for stratum in sorted(capacities):
        ranked = sorted(pools[stratum], key=lambda row: -row[0])
        require(len(ranked) == capacities[stratum], "INEGI ranked draw is incomplete")
        offset_index = 0
        for size, found in zip(prior_sizes, verified, strict=True):
            stop = offset_index + size[stratum]
            found.update({entry[1]: stratum for entry in ranked[offset_index:stop]})
            offset_index = stop
        for negative, key, civil, sex, (_, lat, lon, zone), offset in ranked[offset_index:]:
            require(mexico.valid_offsets(civil.isoformat(), zone) == (offset,), "Mexican historical offset mismatch")
            point = dict(latitude=lat, longitude=lon, timezone_id=zone)
            row = model_row(key, civil, offset, sex, point)
            rows.append(dict(row, source=source, source_id=key, source_row_id=key.rsplit("-", 1)[1],
                             birth_country="MX", sex=sex, geo_precision="recovered_2020_municipal_seat",
                             quality="verified_official_inegi_design", sampling_sha256=f"{-negative:064x}",
                             **r8.weight_metadata(stratum, frame, quota)))
    require(all(found == original for found, original in zip(verified, batches, strict=True)),
            "A predecessor INEGI draw fails exact physical-key verification")
    seal = make_sample(folder, rows, frame, quota, {"source": source, "seed": legacy["seed"]})
    return dict(seal, source_archive_sha256=legacy["archive_sha256"], eligibility_before_exclusions=sum(population.values()),
                excluded_by_round={"r10": 2000, "r45": 2000, "r46": 4000}, legacy_physical_overlap=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=GROUPS)
    parser.add_argument("--job", type=Path, required=True)
    for key in ("brazil-archive", "references", "r10-job", "r13-job", "r15-job", "r45-job", "r46-job",
                "mex-old", "mex-modern", "seats", "iter"):
        parser.add_argument("--" + key, type=Path)
    args = parser.parse_args()
    settings = protocol()
    require(mexico.tz_version() == settings["sampling"]["timezone_database"], "Use the registered IANA tzdb")
    destination = private(args.job) / args.group
    require(not destination.exists(), "Use a fresh R49 sample directory")
    with TemporaryDirectory(dir=args.job) as temporary:
        stage = Path(temporary) / args.group
        stage.mkdir()
        sample_folder = stage / "sample"
        if args.group.startswith("br"):
            receipt = brazil_holdout(args, settings, sample_folder, int(args.group[2:]))
        elif args.group == "mx2009":
            receipt = mexico2009_holdout(args, settings, sample_folder)
        else:
            from .mexico1999 import census
            receipt = census(args, settings, sample_folder)
        write_json(stage / "input_seal.json", dict(receipt, registration=REGISTRATION, group=args.group))
        stage.rename(destination)
    print(args.group, receipt["records"], receipt["eligible_frame_N"], digest(destination / "input_seal.json"), flush=True)


if __name__ == "__main__":
    main()
