"""Audit Mexico 2020 late registration and a Mexico 2023 source candidate."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from calendar_controls import REPLAY, R10, digest, require, write_json

sys.path.insert(0, str(R10 / "recovery/mexico2020"))
from rebuild_inputs import BIRTH_FIELDS, CATALOG_FIELDS, ITER_SHA256, dbf_rows
from rebuild_inputs import normalize, reference_points, tz_version, valid_offsets

YEARS = tuple(range(2022, 2026))


def audit(path, registration_year, points, allowed_strata, *, birth_year):
    counts = Counter()
    target = f"birth_year_{birth_year}"
    birth_label, registration_label = str(birth_year), str(registration_year)
    with ZipFile(path) as archive:
        members = {Path(n).name.lower(): n for n in archive.namelist() if not n.endswith("/")}
        yy = registration_year % 100
        names = {}
        for _, deleted, row in dbf_rows(archive, members[f"catemlna{yy:02}.dbf"], CATALOG_FIELDS):
            if not deleted:
                key = row["CVE_ENT"] + row["CVE_MUN"] + row["CVE_LOC"]
                label = normalize(row["NOM_LOC"])
                require(key not in names or names[key] == label, "Ambiguous occurrence locality code")
                names[key] = label
        joined = {k: points[k][3] for k, name in names.items() if k in points and points[k][0] == name}
        for _, deleted, row in dbf_rows(archive, members[f"nacim{yy:02}.dbf"], BIRTH_FIELDS):
            counts["physical_rows"] += 1
            if deleted or row["ANO_NAC"] != birth_label:
                continue
            counts[target] += 1
            sex = {"1": "M", "2": "F"}.get(row["SEXO"])
            state = row["ENT_OCURR"].zfill(2)
            if sex is None or row["ANO_REG"] != registration_label:
                counts["exclude_sex_or_registration_year"] += 1
                continue
            try:
                moment = datetime(birth_year, int(row["MES_NAC"]), int(row["DIA_NAC"]),
                                  int(row["HORA_NAC"]), int(row["MINUTO_NAC"]))
                registration = date(registration_year, int(row["MES_REG"]), int(row["DIA_REG"]))
            except ValueError:
                counts["exclude_invalid_birth_clock_or_date"] += 1
                continue
            if registration < moment.date():
                counts["exclude_chronology"] += 1
                continue
            key = state + row["MUN_OCURR"].zfill(3) + row["LOC_OCURR"].zfill(4)
            zone = joined.get(key)
            if zone is None or state + "|" + sex not in allowed_strata:
                counts["exclude_locality_or_geography"] += 1
                continue
            if len(valid_offsets(moment.isoformat(), zone)) != 1:
                counts["exclude_ambiguous_historical_clock"] += 1
                continue
            counts["eligible"] += 1
    c = {name: counts[name] for name in ("physical_rows", target, "exclude_sex_or_registration_year",
          "exclude_invalid_birth_clock_or_date", "exclude_chronology", "exclude_locality_or_geography",
          "exclude_ambiguous_historical_clock", "eligible")}
    require(sum(v for k, v in c.items() if k.startswith("exclude_")) + c["eligible"] == c[target],
            "Count conservation failed")
    return {
        "registration_year": registration_year, "sha256": digest(path), "archive_bytes": path.stat().st_size,
        "url": f"https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/{registration_year}/"
               f"natalidad_base_datos_{registration_year}_dbf.zip",
        **c,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-archives", type=Path, nargs=2, metavar=("ZIP_2020", "ZIP_2021"), required=True)
    parser.add_argument("--late-archives", type=Path, required=True)
    parser.add_argument("--iter-2020", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((R10 / "mexico/samples/mexico2020/sampling_manifest.json").read_bytes())
    require(tz_version() == manifest["tzdb"], "Use the original R10 timezone edition")
    points = reference_points(args.iter_2020)
    strata = {s["stratum_id"] for s in manifest["strata"]}
    late_files = {y: args.late_archives / f"natalidad_base_datos_{y}_dbf.zip" for y in YEARS}
    earlier = []
    for year, path in zip((2020, 2021), args.baseline_archives, strict=True):
        require(digest(path) == manifest["archive_sha256"][str(year)], "Wrong original archive")
        earlier.append(audit(path, year, points, strata, birth_year=2020))
    require([r["eligible"] for r in earlier] == [952075, 417831],
            "Early-frame counts do not reproduce the R10 release")
    later = [audit(late_files[y], y, points, strata, birth_year=2020) for y in YEARS]
    candidate = [audit(late_files[y], y, points, strata, birth_year=2023) for y in (2023, 2024, 2025)]
    n_early, n_late = sum(r["eligible"] for r in earlier), sum(r["eligible"] for r in later)
    primary = json.loads((REPLAY / "results/structural_comparison.json").read_bytes())
    mexico = next(r for r in primary["targets"] if r["slot"] == "mexico2020")
    reference = primary["reference"]["joint_rate"]
    kept = mexico["joint_rate"]
    early_lower = reference + mexico["sampling_interval"]["delta_joint_family_adjusted_interval"][0]
    share = n_late / (n_early + n_late)
    lower = (1 - share) * kept
    upper = lower + share
    receipt = {
        "scope": "R12 source eligibility check and arithmetic bounds, with no additional chart development or scoring.",
        "source_rows_are_not_verified_unique_people": True,
        "birth_year": 2020, "iter_2020_sha256": ITER_SHA256, "tzdb": tz_version(),
        "early_records": n_early, "late_records": n_late, "late_eligible_share": share,
        "source_archives": earlier + later,
        "held_out_source_candidate": {
            "birth_year": 2023, "source_archives": candidate,
            "eligible_2023_2024_registration_records": sum(r["eligible"] for r in candidate[:2]),
            "additional_2025_eligible_registration_records": candidate[2]["eligible"],
            "selected_or_scored": False,
        },
        "score_bound": {
            "r10_early_point_estimate": kept, "reference": reference,
            "expanded_frame_rate_lower_at_r10_point": lower,
            "expanded_frame_rate_upper_at_r10_point": upper,
            "expanded_frame_difference_pp_bounds_at_r10_point": [100 * (lower - reference), 100 * (upper - reference)],
            "late_joint_rate_that_would_equal_reference": (reference - lower) / share if share else None,
            "expanded_frame_difference_pp_at_r10_lower_and_zero_late": 100 * ((1 - share) * early_lower - reference),
            "scope": "Sharp arithmetic bounds with the earlier R10 point held fixed and the unscored late cohort's "
                     "joint rate anywhere in [0,1]. These are not sampling intervals.",
        },
    }
    write_json(args.output, receipt)
    print(n_early, n_late, receipt["score_bound"]["expanded_frame_difference_pp_bounds_at_r10_point"])
    print("Mexico 2023 candidate eligible counts:", [r["eligible"] for r in candidate])


if __name__ == "__main__":
    main()
