#!/usr/bin/env python3
"""Build an R9 birth-only sample after official geography/zone review.

Inputs:
  --geo JSON mapping 9-digit 2015 cvegeo to latitude, longitude and provenance.
  --zones JSON with by_municipality and by_state mappings to IANA identifiers.
No charts or outcome labels are read. Incomplete joins and ambiguous local
times are excluded; a reference point must be explicitly sourced.
"""
from __future__ import annotations
import argparse
import collections
import csv
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import heapq
import importlib.util
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo, TZPATH

MODEL_KEYS = ("study_id", "birth_local", "birth_utc", "source_offset_seconds",
              "sex_resolved", "latitude", "longitude", "calendar",
              "time_precision_seconds", "time_uncertainty_seconds",
              "coordinate_precision_degrees", "timezone_id", "instant_scale")


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def tz_version():
    for base in TZPATH:
        p = Path(base) / "tzdata.zi"
        if p.exists():
            first = p.open().readline().strip()
            if first.startswith("# version "):
                return first.split()[-1]
    try:
        import tzdata
        return tzdata.IANA_VERSION
    except ImportError:
        return "unverified"


@lru_cache(maxsize=32)
def zone(name):
    return ZoneInfo(name)


@lru_cache(maxsize=200000)
def valid_offsets(local_iso, name):
    local = datetime.fromisoformat(local_iso)
    z = zone(name)
    offsets = set()
    for fold in (0, 1):
        aware = local.replace(tzinfo=z, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(z).replace(tzinfo=None) == local:
            offsets.add(int(aware.utcoffset().total_seconds()))
    return tuple(sorted(offsets))


def eligible(args, refs, zones, audit=None):
    with args.candidates.open(newline="", encoding="utf8") as handle:
        for row in csv.DictReader(handle):
            if audit is not None:
                audit["counts"]["candidate_rows"] += 1
            ref = refs.get(row["cvegeo"])
            if not ref:
                if audit is not None:
                    audit["excluded"]["no_approved_geographic_reference"] += 1
                continue
            lat, lon = ref.get("latitude"), ref.get("longitude")
            if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f"Invalid approved reference {row['cvegeo']}")
            if not ref.get("source_url") or not ref.get("reference_role"):
                raise ValueError("Reference must state its source URL and role")
            zone_id = zones.get("by_municipality", {}).get(row["cvegeo"][:5], zones.get("by_state", {}).get(row["state_code"]))
            if not zone_id:
                if audit is not None:
                    audit["excluded"]["unresolved_historical_timezone"] += 1
                    audit["unresolved_zone_by_state"][row["state_code"]] += 1
                continue
            offsets = valid_offsets(row["birth_local"], zone_id)
            if len(offsets) != 1:
                if audit is not None:
                    reason = "nonexistent_DST_gap" if not offsets else "ambiguous_DST_fold"
                    audit["excluded"][reason] += 1
                    audit["DST_exclusions_zone_date"][zone_id + "|" + row["birth_local"][:10] + "|" + reason] += 1
                continue
            stratum = row["state_code"] + "|" + row["sex"]
            if audit is not None:
                audit["counts"]["eligible_rows"] += 1
                audit["eligible_strata"][stratum] += 1
                audit["eligible_months"][row["birth_local"][5:7]] += 1
                audit["eligible_zone_counts"][zone_id] += 1
            yield row, ref, zone_id, offsets[0], stratum


def main():
    ap = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--geo", type=Path, required=True)
    ap.add_argument("--zones", type=Path, required=True)
    ap.add_argument("--common", type=Path, default=here.parent / "common.py")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--target", type=int, default=2000)
    args = ap.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError("Refusing to overwrite an existing sample; choose an empty output directory")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("r9_sampling_common", args.common)
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    refs = json.loads(args.geo.read_text())
    zones = json.loads(args.zones.read_text())
    if "points" in refs:
        refs = refs["points"]
    audit = {key: collections.Counter() for key in ("counts", "excluded", "unresolved_zone_by_state", "DST_exclusions_zone_date", "eligible_strata", "eligible_months", "eligible_zone_counts")}
    for _ in eligible(args, refs, zones, audit):
        pass
    N = audit["eligible_strata"]
    q = common.quotas(N, args.target)
    if not q:
        raise ValueError("No eligible source frame; no sample written")
    print(json.dumps({"stage": "eligible_frame", "counts": dict(audit["counts"]), "exclusions": dict(audit["excluded"])}), flush=True)
    heaps = collections.defaultdict(list)
    for row, ref, zone_id, offset, stratum in eligible(args, refs, zones):
        rank = int(common.rank_hash(row["source_id"]), 16)
        entry = (-rank, row["source_id"], row, ref, zone_id, offset, stratum)
        heap = heaps[stratum]
        if len(heap) < q[stratum]:
            heapq.heappush(heap, entry)
        elif rank < -heap[0][0]:
            heapq.heapreplace(heap, entry)
    selected = []
    for heap in heaps.values():
        for neg_rank, source_id, row, ref, zone_id, offset, stratum in heap:
            local = datetime.fromisoformat(row["birth_local"])
            selected.append({
                "study_id": common.study_id(source_id), "source_id": source_id,
                "source": "INEGI-NACIM15-birth2015-registered2015", "source_row_id": row["source_ordinal"],
                "birth_local": row["birth_local"], "birth_utc": (local - timedelta(seconds=offset)).isoformat() + "Z",
                "source_offset_seconds": offset, "sex_resolved": row["sex"], "sex": row["sex"],
                "birth_country": "MX", "birth_year": 2015, "birth_decade": 2010,
                "calendar": "gregorian", "instant_scale": "UT", "time_precision_seconds": 60,
                "time_uncertainty_seconds": None, "coordinate_precision_degrees": None,
                "latitude": ref["latitude"], "longitude": ref["longitude"], "timezone_id": zone_id,
                "source_cvegeo_2015": row["cvegeo"], "locality_name_2015": row["locality_name_2015"],
                "reference_provenance": ref,
                "geo_precision": ref["reference_role"],
                "quality": "official_clock_approved_inegi_reference_iana",
                "uncertainty_flags": ["reference_point_not_hospital_or_observed_birthplace", "recorded_clock_accuracy_unknown", "same_year_registration_frame_underrepresents_late_year_births"],
                "stratum_id": stratum, "N_h": N[stratum], "n_h": q[stratum],
                "inclusion_probability": q[stratum] / N[stratum], "sample_weight": N[stratum] / q[stratum],
                "weight_scope": "eligible_source_frame_only", "sampling_sha256": f"{-neg_rank:064x}",
                "registration_date": row["registration_date"], "registration_delay_days": row["registration_delay_days"],
            })
    selected.sort(key=lambda row: row["study_id"])
    model = args.output_dir / "birth_inputs.jsonl"
    metadata = args.output_dir / "birth_metadata.jsonl"
    with model.open("w") as mh, metadata.open("w", encoding="utf8") as ph:
        for row in selected:
            mh.write(json.dumps({key: row[key] for key in MODEL_KEYS}, separators=(",", ":")) + "\n")
            ph.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    manifest = {
        "source": "INEGI-NACIM15-birth2015-registered2015", "seed": common.SEED,
        "eligible_frame_N": sum(N.values()), "sample_n": len(selected),
        "stratum_fields": "2015 occurrence state × explicit sex",
        "algorithm": common.quotas.__doc__.strip(),
        "rank_method": "SHA256(seed+'|'+source_id) ascending; stable one-based DBF physical ordinal",
        "strata": [{"stratum_id": h, "N_h": N[h], "n_h": q[h], "inclusion_probability": q[h]/N[h], "sample_weight": N[h]/q[h]} for h in sorted(N)],
        "model_input_sha256": sha(model), "metadata_sha256": sha(metadata),
        "source_candidate_sha256": sha(args.candidates), "geographic_reference_sha256": sha(args.geo),
        "timezone_rules_sha256": sha(args.zones), "common_sampling_code_sha256": sha(args.common),
        "sampling_code_sha256": sha(Path(__file__)),
        "tzdb": tz_version(), "outcome_fields": [], "selection_uses_model_outputs": False,
        "weight_interpretation": "Only the registered2015/born2015 complete-field geographically resolved eligible source frame, not all Mexican births or humanity.",
    }
    assert len(selected) == min(args.target, sum(N.values()))
    assert len({row["study_id"] for row in selected}) == len(selected)
    assert abs(sum(row["sample_weight"] for row in selected) - sum(N.values())) < 1e-5
    save(args.output_dir / "sampling_manifest.json", manifest)
    save(args.output_dir / "frame_audit.json", audit)
    print(json.dumps({"sample_n": len(selected), "eligible_frame_N": sum(N.values()), "model_sha256": manifest["model_input_sha256"], "metadata_sha256": manifest["metadata_sha256"], "tzdb": manifest["tzdb"]}, indent=2))


if __name__ == "__main__":
    main()
