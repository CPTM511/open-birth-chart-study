"""Independently reread the physical 2009 birth records from official archives."""

import argparse
from bisect import insort
from collections import Counter, defaultdict
import csv
from datetime import datetime
from hashlib import sha256
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from .common import ROOT, REGISTRATION, digest, load_source, read_json, registered, require, write_json
from rounds.r10.independent_replay.source_design_2009.rebuild_design import attach_geography, design_rows
from rounds.r15.review_inputs import independent_instant


def brazil(args, folder, cfg):
    sample, manifest = load_source(folder / "sample")
    require(digest(args.brazil_archive) == cfg["brazil2009"]["archive_sha256"]
            and digest(args.references) == cfg["brazil2009"]["municipality_reference_sha256"], "Wrong Brazil replay sources")
    rows = {r["source_id"]: r for r in sample}
    expected_counts = {x["stratum_id"]: x["N_h"] for x in manifest["strata"]}
    quota = {x["stratum_id"]: x["n_h"] for x in manifest["strata"]}
    refs = read_json(args.references)
    zones = {z: ZoneInfo(z) for z in {r["timezone_id"] for r in refs.values()} if z}
    matched, ranks, actual = set(), defaultdict(list), Counter()
    with ZipFile(args.brazil_archive) as archive, TextIOWrapper(
            archive.open("DNBR2009.csv"), encoding="utf-8-sig", newline="") as stream:
        for ordinal, record in enumerate(csv.DictReader(stream, delimiter=";"), 1):
            day, clock, place = [record[key] for key in ("DTNASC", "HORANASC", "CODMUNNASC")]
            sex = {"1": "M", "2": "F"}.get(record["SEXO"])
            point = refs.get(place)
            if len(day) != 8 or not day.endswith("2009") or len(clock) != 4 or not clock.isascii() or not clock.isdecimal():
                continue
            if not sex or not point or not point["timezone_id"]:
                continue
            try:
                local = datetime(int(day[4:]), int(day[2:4]), int(day[:2]), int(clock[:2]), int(clock[2:]))
            except ValueError:
                continue
            instant = independent_instant(local, zones[point["timezone_id"]])
            if instant is None:
                continue
            h = f"BR|{place[:2]}|{sex}|2009"
            actual[h] += 1
            key = f"SINASC2009:row:{ordinal:07d}"
            rank = sha256((manifest["seed"]+"|"+key).encode()).hexdigest()
            bucket = ranks[h]
            insort(bucket, (rank, key))
            if len(bucket) > quota[h]:
                bucket.pop()
            if key in rows:
                saved = rows[key]
                require(saved["sampling_sha256"] == rank and saved["stratum_id"] == h and saved["sex"] == sex
                        and saved["birth_local"] == local.isoformat()
                        and saved["birth_utc"] == instant.isoformat().replace("+00:00", "Z")
                        and saved["source_offset_seconds"] == (local-instant.replace(tzinfo=None)).total_seconds()
                        and (saved["latitude"], saved["longitude"]) == (point["latitude"], point["longitude"]),
                        "Physical SINASC row does not reconstruct the sealed model input")
                matched.add(key)
    require(actual == expected_counts, "Brazil frame recount differs")
    minima = {h: min(actual[h],2) for h in actual}
    extra, pool_size = len(rows)-sum(minima.values()), sum(actual.values())-sum(minima.values())
    remainder = []
    for h, n in actual.items():
        extra_count, fraction = divmod(extra*(n-minima[h]),pool_size)
        minima[h] += extra_count
        remainder.append((-fraction,h))
    for _, h in sorted(remainder)[:len(rows)-sum(minima.values())]:
        minima[h] += 1
    require(quota == minima, "Brazil sample allocation differs")
    require(set(rows) == matched == {key for bucket in ranks.values() for _, key in bucket},
            "Brazil sample selection differs on independent reread")
    return {"physical_rows_read": ordinal, "eligible_rows": sum(actual.values()), "physical_sample_matches": len(matched),
            "method": "Independent CSV reread, UTC round trips, ordered insertion and integer quotas"}


def mexico(args, folder, cfg):
    old = read_json(ROOT / cfg["mexico2009"]["source_manifest"])
    rows, manifest = load_source(folder / "sample")
    frame = {row["stratum_id"]: row["N_h"] for row in manifest["strata"]}
    quota = {row["stratum_id"]: row["n_h"] for row in manifest["strata"]}
    old_quota = {row["stratum_id"]: row["n_h"] for row in old["strata"]}
    ranks, selected = defaultdict(list), defaultdict(dict)
    for row in rows:
        ranks[row["stratum_id"]].append(row)
    for cell, bucket in ranks.items():
        for place, row in enumerate(sorted(bucket, key=lambda b: b["sampling_sha256"]), 1+old_quota[cell]):
            prefix, ordinal = row["source_id"].rsplit("-", 1)
            y = int(prefix.removeprefix("INEGI-NACIM"))
            number = int(ordinal)
            require(number not in selected[y], "Duplicate Mexican physical DBF row")
            selected[y][number] = (row["source_id"], row, cell, place, row["sampling_sha256"])
    replay = []
    for y, sample in sorted(selected.items()):
        path = args.mexico_archives / str(y) / f"natalidad_base_datos_{y}_dbf.zip"
        require(digest(path) == old["archive_sha256"][str(y)], "Wrong Mexico replay source")
        replay.extend(design_rows(y, path, sample, old, frame, quota))
    require(len(rows) == len(replay), "Missing verified Mexican physical DBF row")
    places = attach_geography(replay, args.seats, args.iter)
    return {"physical_sample_matches": len(replay), "matched_municipalities": places,
            "method": "Separate physical DBF record seek and birth/registration/municipal coordinates recheck"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("job", "replay-job", "brazil-archive", "references", "mexico-archives", "iter", "seats", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    cfg = registered()
    require(args.job.resolve() != args.replay_job.resolve(), "Use a distinct path for the second source draw")
    for label in ("br2009", "mx2009"):
        a, b = [job / label / "input_seal.json" for job in (args.job, args.replay_job)]
        require(digest(a) == digest(b), "The second prepared source seal differs")
    write_json(args.output, dict(registration=REGISTRATION, repeated_draw_seals_identical=True,
                                 br2009=brazil(args, args.job / "br2009", cfg),
                                 mx2009=mexico(args, args.job / "mx2009", cfg)))


if __name__ == "__main__":
    main()
