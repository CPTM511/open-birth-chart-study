"""Rebuild the two prospective 2009 birth-only draws and seal them before scoring."""

import argparse
from collections import Counter, defaultdict
from datetime import timedelta
from hashlib import sha256
import heapq
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .common import R10, ROOT, FILES, REGISTRATION, digest, read_json, registered, require, source_seal, write_json
from rounds.r10.brazil import build_inputs as brazil

sys.path.insert(0, str(ROOT / "rounds/r12"))
from prepare_samples import allocate
from rounds.r10.recovery.mexico2009 import rebuild_inputs as mexico

r8 = brazil.r8


def source_id(key):
    return "R45-" + sha256(key.encode()).hexdigest()[:24]


def model_row(key, civil, offset, sex, reference):
    return dict(study_id=source_id(key), birth_local=civil.isoformat(),
                birth_utc=(civil-timedelta(seconds=offset)).isoformat()+"Z",
                source_offset_seconds=offset, sex_resolved=sex, calendar="gregorian", instant_scale="UT",
                time_precision_seconds=60, time_uncertainty_seconds=None, coordinate_precision_degrees=None,
                **reference)


def make_sample(folder, rows, counts, quotas, metadata):
    folder.mkdir()
    rows.sort(key=lambda row: row["study_id"])
    modeled = ({key: row[key] for key in r8.MODEL_KEYS} for row in rows)
    for name, data in zip(FILES, (modeled, rows)):
        with (folder / name).open("x", encoding="utf-8") as out:
            for row in data:
                out.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
    write_json(folder / FILES[2], dict(metadata, sample_n=len(rows), eligible_frame_N=sum(counts.values()),
               model_input_sha256=digest(folder / FILES[0]), metadata_sha256=digest(folder / FILES[1]),
               strata=[r8.weight_metadata(h, counts, quotas) for h in sorted(counts)]))
    return source_seal(folder)


def brazil_draw(folder, archive, references, count, scheme):
    require(digest(archive) == scheme["archive_sha256"], "SINASC archive hash differs")
    require(digest(references) == scheme["municipality_reference_sha256"], "IBGE reference hash differs")
    ref = read_json(references)
    audit = {key: Counter() for key in ("counts", "invalid_fields_nonexclusive", "excluded", "minute_mod5",
                                        "eligible_strata")}
    for _ in brazil.prior.eligible(archive, 2009, ref, audit):
        pass
    counts = audit["eligible_strata"]
    require(sum(counts.values()) == audit["counts"]["eligible"], "Invalid Brazil eligibility totals")
    require(audit["counts"]["raw_rows"] == sum(audit["excluded"].values()) + sum(counts.values()),
            "Brazil exclusions do not reconcile")
    quotas = allocate(counts, count)
    pools = defaultdict(list)
    eligible_state = Counter()
    zero_minute = Counter()
    for item in brazil.prior.eligible(archive, 2009, ref):
        ordinal, civil, _, _, _, h = item
        eligible_state[h] += 1
        zero_minute["on_the_hour"] += int(civil.minute == 0)
        zero_minute["midnight"] += int(civil.hour == civil.minute == 0)
        key = f"SINASC2009:row:{ordinal:07d}"
        rank = int(sha256((scheme["seed"] + "|" + key).encode()).hexdigest(), 16)
        pool = pools[h]
        candidate = (-rank, key, item)
        if len(pool) < quotas[h]:
            heapq.heappush(pool, candidate)
        elif rank < -pool[0][0]:
            heapq.heapreplace(pool, candidate)
    require(eligible_state == counts, "SINASC source scans disagree")
    rows = []
    for h, pool in pools.items():
        for negative, key, (ordinal, civil, sex, place, offset, _) in pool:
            geo = ref[place]
            require(r8.valid_offsets(civil, geo["timezone_id"]) == (offset,), "Brazil selected offset differs")
            rows.append(dict(model_row(key, civil, offset, sex, geo),
                             source="SINASC-2009-R45", source_id=key, source_row_id=str(ordinal),
                             sex=sex, birth_country="BR", quality=r8.BRAZIL_QUALITY,
                             sampling_sha256=f"{-negative:064x}", **r8.weight_metadata(h, counts, quotas)))
    receipt = make_sample(folder, rows, counts, quotas, dict(
        source="SINASC-2009-R45", seed=scheme["seed"], birth_fields_only=True,
        archive_sha256=scheme["archive_sha256"], reference_sha256=scheme["municipality_reference_sha256"]))
    receipt.update(audit=dict(audit, eligible_clock=zero_minute), archive_sha256=scheme["archive_sha256"],
                   municipality_reference_sha256=scheme["municipality_reference_sha256"])
    return receipt


def mexico_draw(folder, archives, iter_archive, seats, count, scheme):
    manifest = read_json(ROOT / scheme["source_manifest"])
    old_receipt = read_json(ROOT / scheme["source_replay_receipt"])
    original_frame = {r["stratum_id"]: r["N_h"] for r in manifest["strata"]}
    original_quota = {r["stratum_id"]: r["n_h"] for r in manifest["strata"]}
    counts = {h: original_frame[h]-original_quota[h] for h in original_frame}
    require(min(counts.values()) > 0, "A Mexico stratum is fully consumed by the legacy sample")
    quotas = allocate(counts, count)
    combined = {h: original_quota[h]+quotas[h] for h in original_frame}
    points, geo_hashes = mexico.municipal_points(seats, iter_archive)
    require(geo_hashes == old_receipt["seat_catalog_sha256"], "Mexico geography hashes differ")
    pools, seen, audits = defaultdict(list), Counter(), {}
    for year in manifest["registration_archive_years"]:
        path = archives / str(year) / f"natalidad_base_datos_{year}_dbf.zip"
        archive_hash = manifest["archive_sha256"][str(year)]
        mexico.require_hash(path, archive_hash)
        audit = mexico.sample_archive(year, path, points, combined, manifest["seed"], pools, seen)
        audits[str(year)] = {"sha256": archive_hash, **audit}
        require(audits[str(year)] == old_receipt["archives"][str(year)], "Mexico archive counts differ")
    require(seen == original_frame, "Mexico source strata differ")
    old, rows = {}, []
    for h in sorted(combined):
        ordered = sorted(pools[h], key=lambda entry: -entry[0])
        require(len(ordered) == combined[h] == len({entry[0] for entry in ordered}), "Invalid Mexico ranks")
        old[h] = ordered[:original_quota[h]]
        for negative, key, civil, sex, (_, lat, lon, zone), offset in ordered[original_quota[h]:]:
            require(mexico.valid_offsets(civil.isoformat(), zone) == (offset,), "Mexico selected offset differs")
            row = model_row(key, civil, offset, sex, dict(latitude=lat, longitude=lon, timezone_id=zone))
            rows.append(dict(row, source="INEGI-birth2009-R45", source_id=key, birth_country="MX", sex=sex,
                             geo_precision="recovered_2020_municipal_seat", quality="verified_official_inegi_design",
                             source_row_id=key.rsplit("-", 1)[1], sampling_sha256=f"{-negative:064x}",
                             **r8.weight_metadata(h, counts, quotas)))
    old_digest = sha256(mexico.model_bytes(old)).hexdigest()
    require(old_digest == manifest["model_input_sha256"], "Original R10 draw does not reproduce")
    old_keys = {entry[1] for pool in old.values() for entry in pool}
    new_keys = {row["source_id"] for row in rows}
    require(len(old_keys) == manifest["sample_n"] and len(new_keys) == count and not old_keys & new_keys,
            "Legacy and confirmatory physical rows overlap")
    receipt = make_sample(folder, rows, counts, quotas, dict(
        source="INEGI-birth2009-R45", seed=manifest["seed"], birth_fields_only=True,
        old_physical_rows_excluded=len(old_keys), archives=manifest["archive_sha256"]))
    receipt.update(archives=audits, original_frame_N=sum(seen.values()), excluded_r10_records=len(old_keys),
                   physical_overlap=0, reproduced_r10_model_sha256=old_digest, original_metadata_found=False)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("country", choices=["br2009", "mx2009"])
    parser.add_argument("--job", required=True, type=Path)
    for name in ("brazil-archive", "references", "mexico-archives", "iter", "seats"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    cfg = registered()
    require(mexico.tz_version() == cfg["brazil2009"]["tzdb"], "Use IANA 2026c")
    destination = args.job / args.country
    require(args.job.is_dir() and args.job.stat().st_mode & 0o077 == 0, "Use a private work directory")
    require(not destination.exists(), "Use a new cohort directory")
    with TemporaryDirectory(dir=args.job) as temporary:
        stage = Path(temporary) / args.country
        stage.mkdir()
        if args.country == "br2009":
            result = brazil_draw(stage / "sample", args.brazil_archive, args.references,
                                 cfg["new_sample_n"], cfg["brazil2009"])
        else:
            result = mexico_draw(stage / "sample", args.mexico_archives, args.iter, args.seats,
                                 cfg["new_sample_n"], cfg["mexico2009"])
        write_json(stage / "input_seal.json", dict(result, registration=REGISTRATION, profile_inputs_sealed=True))
        stage.rename(destination)
    print(args.country, result["records"], result["eligible_frame_N"], digest(destination / "input_seal.json"))


if __name__ == "__main__":
    main()
