#!/usr/bin/env python3
"""Birth-only projection of the official free Astro-Databank Z sample.

This is an alphabetically selected, reused reference source, not a new holdout.
Biographies, source prose, events, relationships and outcome fields are ignored.
Raw and derived individual records are not included in the public repository.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from build_birth_inputs import write_json, sha256, study_id, sampling_hash, proportional_quotas, weight_metadata, write_rows, DEFAULT_CACHE, DEFAULT_OUTPUT

SOURCE_URL = "https://www.astro.com/adbexport/z_sample.zip"
SOURCE_SHA256 = "f3b9a93eae4bf27588d2e4c0f81cfd47f1b8aad009f7c469843e2974fa371edc"
COUNTRIES = {"ALG": ("DZ", "Algeria"), "ARG": ("AR", "Argentina"),
    "AUS": ("AT", "Austria"), "AZE": ("AZ", "Azerbaijan"),
    "BANG": ("BD", "Bangladesh"), "BEL": ("BE", "Belgium"),
    "BRAS": ("BR", "Brazil"), "BRU": ("BN", "Brunei"), "BY": ("BY", "Belarus"),
    "CHILE": ("CL", "Chile"), "CHINA": ("CN", "China"),
    "CR": ("CR", "Costa Rica"), "CUBA": ("CU", "Cuba"),
    "CZ": ("CZ", "Czech Republic"), "EGYPT": ("EG", "Egypt"),
    "FR": ("FR", "France"), "GER": ("DE", "Germany"),
    "HRV": ("HR", "Croatia"), "INDIA": ("IN", "India"),
    "ISRL": ("IL", "Israel"), "ITALY": ("IT", "Italy"),
    "JOR": ("JO", "Jordan"), "KZ": ("KZ", "Kazakhstan"),
    "MEX": ("MX", "Mexico"), "NETH": ("NL", "Netherlands"),
    "NOR": ("NO", "Norway"), "PAK": ("PK", "Pakistan"),
    "PERU": ("PE", "Peru"), "POL": ("PL", "Poland"),
    "ROM": ("RO", "Romania"), "RU": ("RU", "Russian Federation"),
    "SPAIN": ("ES", "Spain"), "SWTZ": ("CH", "Switzerland"),
    "TUN": ("TN", "Tunisia"), "TUR": ("TR", "Turkey"),
    "UA": ("UA", "Ukraine"), "UR": ("UY", "Uruguay"), "VEN": ("VE", "Venezuela")}


def country_iso(code, label):
    if code.endswith(" (US)"):
        return "US"
    if code.endswith(" (CAN)"):
        return "CA"
    if code.endswith(" (UK)"):
        return "GB"
    if code not in COUNTRIES:
        raise ValueError("unmapped_source_country")
    iso, expected = COUNTRIES[code]
    if label != expected:
        raise ValueError("source_country_code_name_conflict")
    return iso


def coord(text, axis):
    m = re.fullmatch(r"(\d+)([nsew])(\d{1,2})(?::?(\d\d(?:\.\d+)?))?", text or "")
    if not m:
        raise ValueError("unparsed_coordinate")
    major, direction, minute, second = m.groups()
    if direction not in ("ns" if axis == "lat" else "ew"):
        raise ValueError("coordinate_axis_conflict")
    if int(minute) >= 60 or float(second or 0) >= 60:
        raise ValueError("coordinate_minute_second_range")
    value = int(major) + int(minute) / 60 + float(second or 0) / 3600
    if direction in "sw":
        value = -value
    if abs(value) > (90 if axis == "lat" else 180):
        raise ValueError("coordinate_range")
    return value


def offset(text):
    m = re.fullmatch(r"([hm])(\d+)([ew])(?:(\d{1,2})(?::?(\d\d(?:\.\d+)?))?)?", text or "")
    if not m:
        raise ValueError("unparsed_offset")
    kind, major, direction, minute, second = m.groups()
    if int(minute or 0) >= 60 or float(second or 0) >= 60:
        raise ValueError("offset_minute_second_range")
    units = int(major) + int(minute or 0) / 60 + float(second or 0) / 3600
    seconds = units * 3600 / (15 if kind == "m" else 1)
    return (1 if direction == "e" else -1) * seconds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", "--input-dir", type=Path, default=DEFAULT_CACHE,
                        help="Directory holding adb_z_sample.zip")
    parser.add_argument("--output", "--output-dir", type=Path, default=DEFAULT_OUTPUT,
                        help="Directory for locally generated cohorts and audits")
    args = parser.parse_args()
    raw = args.raw_dir / "adb_z_sample.zip"
    assert sha256(raw) == SOURCE_SHA256, "Source differs from frozen snapshot"
    with zipfile.ZipFile(raw) as z:
        members = z.namelist()
        assert len(members) == 1 and members[0].endswith(".xml")
        tree = ET.fromstring(z.read(members[0]))
    audit = {k: Counter() for k in ["counts", "excluded", "all_exclusion_reasons", "raw_ratings",
        "eligible_countries", "eligible_decades", "eligible_rating", "eligible_sex",
        "eligible_strata", "time_accuracy_codes", "country_decade_sex_quality"]}
    rows = []
    seen = set()
    for entry in tree.findall("adb_entry"):
        audit["counts"]["raw_entries"] += 1
        p = entry.find("public_data")
        b = p.find("bdata")
        d, t = b.find("sbdate"), b.find("sbtime")
        aid = entry.get("adb_id")
        rating = p.findtext("roddenrating")
        sex = p.findtext("gender")
        audit["raw_ratings"][rating] += 1
        reasons = []
        if aid in seen:
            reasons.append("duplicate_adb_id")
        seen.add(aid)
        if rating not in {"AA", "A"}:
            reasons.append("not_AA_or_A")
        if p.find("datatype").get("dtc") not in {"1", "4"} or sex not in {"M", "F"}:
            reasons.append("not_single_human_explicit_MF")
        if d.get("ccalendar") != "g":
            reasons.append("not_explicit_Gregorian")
        try:
            dob = date(int(d.get("iyear")), int(d.get("imonth")), int(d.get("iday")))
            if not 1880 <= dob.year <= 2019:
                reasons.append("outside_1880_2019_birth_window")
        except (TypeError, ValueError):
            dob = None
            reasons.append("invalid_birth_date")
        if t is None or t.get("time_unknown") or t.get("itimeacc") in {"11", "12", "13", "14", "15", "16", "17"}:
            reasons.append("clock_unknown_or_insufficient")
        if reasons:
            audit["excluded"][reasons[0]] += 1
            audit["all_exclusion_reasons"].update(reasons)
            continue
        try:
            if not re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", t.text or ""):
                raise ValueError("clock_not_explicit_HHMM")
            clock = datetime.strptime(t.text, "%H:%M:%S" if t.text.count(":") == 2 else "%H:%M").time()
            local = datetime.combine(dob, clock)
            place = b.find("place")
            lat, lon = coord(place.get("slati"), "lat"), coord(place.get("slong"), "lon")
            if (lat, lon) == (0.0, 0.0):
                raise ValueError("Null_Island_coordinate_placeholder")
            off = offset(t.get("stmerid"))
            jd = float(t.get("jd_ut"))
            if not math.isfinite(jd):
                raise ValueError("nonfinite_JD_UT")
            utc_jd = datetime(1970, 1, 1) + timedelta(days=jd - 2440587.5)
            utc = local - timedelta(seconds=off)
            residual = (utc_jd - utc).total_seconds()
            audit["counts"]["complete_birth_fields_before_JD_consistency"] += 1
            if abs(residual) > 1:
                raise ValueError("local_offset_JD_UT_disagree_gt_1_second")
            country_raw = b.find("country").get("sctr")
            country_name = b.findtext("country")
            country = country_iso(country_raw, country_name)
        except (ValueError, TypeError, OverflowError) as exc:
            audit["excluded"][str(exc)] += 1
            audit["all_exclusion_reasons"][str(exc)] += 1
            continue
        decade = (dob.year // 10) * 10
        source_id = "ADB_Z2026:" + aid
        quality = "ADB_" + rating
        stratum = f"{country}|{sex}|{decade}|{quality}"
        audit["counts"]["four_system_birth_input_eligible"] += 1
        audit["eligible_countries"][country] += 1
        audit["eligible_decades"][decade] += 1
        audit["eligible_rating"][rating] += 1
        audit["eligible_sex"][sex] += 1
        audit["eligible_strata"][stratum] += 1
        audit["country_decade_sex_quality"][stratum] += 1
        audit["time_accuracy_codes"][t.get("itimeacc") or "not_supplied"] += 1
        rows.append(dict(study_id=study_id(source_id), source_id=source_id,
            source="ADB-official-free-Z-2026-11-10", source_row_id=aid,
            birth_local=local.isoformat(), birth_utc=utc.isoformat() + "Z",
            source_offset_seconds=off, utc_offset_seconds=off, utc_offset_hours=off / 3600,
            sex_resolved=sex, sex=sex, birth_country=country, birth_year=dob.year,
            birth_decade=decade, calendar="gregorian", instant_scale="UT",
            latitude=lat, longitude=lon, timezone_id=None,
            time_precision_seconds=1 if t.text.count(":") == 2 else 60,
            time_uncertainty_seconds=None, coordinate_precision_degrees=None,
            geo_precision="source_locality_reference",
            quality=quality, rodden_rating=rating, source_jd_ut=jd,
            jd_ut_minus_local_offset_seconds=residual,
            source_time_meridian=t.get("stmerid"), source_time_type=t.get("ctimetype"),
            source_timezone_origin=t.get("ctzauto"), source_time_accuracy_code=t.get("itimeacc"),
            source_time_accuracy_description=t.get("stimeacc"),
            source_country_code=country_raw, source_country_name=country_name,
            birth_source_type=p.find("datatype").get("sdatasource"),
            birth_source_type_code=p.find("datatype").get("dsc"),
            birth_precision_independently_verified=False,
            eligibility_role="reused_reference_not_independent_holdout",
            stratum_id=stratum, sampling_sha256=sampling_hash(source_id),
            uncertainty_flags=["alphabetical_Z_reference_selection",
                "source_used_in_prior_round_not_independent", "possible_overlap_with_OGDB",
                "provider_Rodden_grade_not_independent_certificate_verification",
                "clock_measurement_accuracy_not_estimated", "source_locality_coordinate_not_exact_birthpoint"]))
    counts = audit["eligible_strata"]
    quotas = proportional_quotas(counts, 2000)
    assert len(rows) <= 2000, "Unexpected sample growth; apply deterministic selection before proceeding"
    for row in rows:
        row.update(weight_metadata(row["stratum_id"], counts, quotas))
    result = write_rows(args.output, "adb_z2026", rows, counts, quotas)
    audit["source"] = dict(url=SOURCE_URL, sha256=SOURCE_SHA256, xml_member=members[0])
    audit["selection"] = "Official alphabetical Z sample; reused reference source, not a newly independent cohort or a probability sample of humanity. All eligible records included."
    audit["outcomes_parsed"] = False
    audit["biographies_or_event_text_parsed"] = False
    audit["cross_source_identity_deduplication"] = "Not performed; do not sum source sizes as independent people."
    write_json(args.output / "audits/adb_z2026_final_audit.json", audit)
    write_json(args.output / "adb_z2026_build_manifest.json", dict(
        built_utc=datetime.now(timezone.utc).isoformat(), source_sha256=SOURCE_SHA256,
        source_url=SOURCE_URL, outputs=[result], raw_redistribution=False,
        individual_derived_redistribution=False, analysis_results_seen=False))
    print(json.dumps({"result": result, "counts": audit["counts"], "countries": audit["eligible_countries"],
                      "decades": audit["eligible_decades"], "ratings": audit["eligible_rating"], "excluded": audit["excluded"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
