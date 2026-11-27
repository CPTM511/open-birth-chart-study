"""Independently replay R15 source counts, quotas, selected ranks and instants."""
import argparse
from bisect import insort
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import file_digest, sha256
from io import TextIOWrapper
import json
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

UTC = timezone.utc


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def check(condition, msg):
    if not condition:
        raise ValueError(msg)


def independent_instant(local, tz):
    candidates = {local.replace(tzinfo=tz, fold=fold).astimezone(UTC) for fold in (0, 1)}
    valid = [t for t in candidates if t.astimezone(tz).replace(tzinfo=None) == local]
    return valid[0] if len(valid) == 1 else None


def run(args):
    seal = json.loads((args.job/"input_seal.json").read_bytes())
    sample = args.job/"sample"
    for filename, expected in seal["private_input_sha256"].items():
        check(sha(sample/filename) == expected, "Sealed sample differs")
    metadata = [json.loads(line) for line in (sample/"birth_metadata.jsonl").read_text().splitlines()]
    manifest = json.loads((sample/"sampling_manifest.json").read_bytes())
    registered = {cell["stratum_id"]:cell for cell in manifest["strata"]}
    expected = {row["source_id"]:row for row in metadata}
    check(len(expected) == manifest["sample_n"], "Repeated physical source row")
    ref_table = {r["municipality_ibge7"]:r for r in json.loads(args.references.read_bytes()).values()}
    zones = {z:ZoneInfo(z) for z in {r["timezone_id"] for r in ref_table.values()} if z}
    source_counts, rankings = Counter(), defaultdict(list)
    total = 0
    with ZipFile(args.archive) as archive, TextIOWrapper(archive.open("SINASC_1999.csv"), encoding="utf-8-sig", newline="") as stream:
        for index, r in enumerate(csv.DictReader(stream, delimiter=";"),1):
            total += 1
            d, clock, place = r["DTNASC"], r["HORANASC"], r["CODMUNNASC"]
            sex = {"1":"M","2":"F"}.get(r["SEXO"])
            point = ref_table.get(place)
            if len(d) != 8 or not d.endswith("1999") or len(clock) != 4 or not clock.isascii() or not clock.isdecimal():
                continue
            if not sex or not point or point["timezone_id"] is None:
                continue
            try:
                local = datetime.strptime(d + clock, "%d%m%Y%H%M")
            except ValueError:
                continue
            instant = independent_instant(local,zones[point["timezone_id"]])
            if instant is None:
                continue
            h = f"BR|{place[:2]}|{sex}|1999"
            source_counts[h] += 1
            key = f"SINASC1999:row:{index:07d}"
            rank = sha256((manifest["seed"]+"|"+key).encode()).hexdigest()
            bucket = rankings[h]
            insort(bucket,(rank,key))
            if len(bucket)>registered[h]["n_h"]:
                bucket.pop()
            if key in expected:
                row = expected[key]
                check(row["sampling_sha256"] == rank and row["stratum_id"] == h and row["sex"] == sex
                      and row["birth_local"] == local.isoformat() and row["birth_utc"] == instant.isoformat().replace("+00:00","Z")
                      and row["source_offset_seconds"] == (local-instant.replace(tzinfo=None)).total_seconds()
                      and (row["latitude"],row["longitude"]) == (point["latitude"],point["longitude"]),
                      "Replayed physical row differs from model input metadata")
    check(source_counts == {h:r["N_h"] for h,r in registered.items()}, "Eligible counts by stratum differ")
    minima = Counter({h:min(n,2) for h,n in source_counts.items()})
    capacity = sum(source_counts.values()) - sum(minima.values())
    to_allocate = manifest["sample_n"] - sum(minima.values())
    remainders = []
    for h,n in source_counts.items():
        floor, remainder = divmod(to_allocate*(n-minima[h]), capacity)
        minima[h] += floor
        remainders.append((-remainder,h))
    for _,h in sorted(remainders)[:manifest["sample_n"]-sum(minima.values())]:
        minima[h] += 1
    check(minima == {h:r["n_h"] for h,r in registered.items()}, "Replayed quotas differ")
    recovered = {key for group in rankings.values() for _,key in group}
    check(recovered == set(expected), "Replayed ranked source IDs differ")
    weight_total = sum((Fraction(row["N_h"],row["n_h"]) for row in metadata), Fraction())
    check(weight_total == sum(source_counts.values()), "Layered weights do not agree with source frame")
    return {"scanned_source_rows":total,"eligible_source_rows":sum(source_counts.values()),
        "matched_physical_rows":len(recovered),"distinct_strata":len(rankings),
        "exact_weight_sum":int(weight_total),
        "method":"Independent CSV DictReader, full IBGE lookup, round trip of both folds, ordered ranks and integer quotas.",
        "same_primary_sources_and_tzdb":True}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("archive","references","job","output"):
        p.add_argument("--"+name,type=Path,required=True)
    args=p.parse_args()
    with args.output.open("x",encoding="utf-8") as out:
        json.dump(run(args),out,indent=2)
        out.write("\n")
