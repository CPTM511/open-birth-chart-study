"""Compare the presealed sources with the five registered R19 calculations."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from math import atan2, cos, degrees, radians, remainder, sin
from pathlib import Path
from statistics import fmean, median
import sys

from open_birth_chart import astronomy, qizheng_engine as qizheng

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "r19"))
import qing_apogee as qing


def verified_json(path, expected):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f"Unexpected digest for {path.name}")
    return json.loads(raw)


def signed_error(candidate, target):
    direct = 60 * remainder(candidate - target, 360)
    angle = radians(candidate - target)
    independent = 60 * degrees(atan2(sin(angle), cos(angle)))
    if abs(direct - independent) > 1e-8:
        raise ArithmeticError("Independent angular difference disagrees")
    return direct


def compare(day, printed):
    location, degree, minute = printed
    if len(location) != 1 or location not in qizheng.MANSION_NAMES or not 0 <= degree <= 29:
        raise ValueError(f"Invalid mansion or degree on {day}")
    if minute is not None and not 0 <= minute < 60:
        raise ValueError(f"Invalid arcminute on {day}")
    utc = datetime.combine(day, time(0), tzinfo=timezone.utc) - timedelta(
        hours=qing.BEIJING_EAST_DEG / 15
    )
    jd = astronomy.julian_day(utc)
    ordinal_jd = day.toordinal() + 1721424.5 - qing.BEIJING_EAST_DEG / 360
    if abs(jd - ordinal_jd) > 1e-8:
        raise ArithmeticError("Independent Gregorian-to-Julian date disagrees")
    start = qizheng.mansion_boundaries(jd)[qizheng.MANSION_NAMES.index(location)]
    target = (start + degree + (minute or 0) / 60) % 360
    source_inputs = qing.source_angles(jd)
    main = qing.calculate(*source_inputs)
    alternate = qing.calculate(*source_inputs, solar_maximum_arcsec=6913)
    candidate_angles = {
        "modern_mean": astronomy.position(jd, "MeanApogee")["longitude"],
        "qing_mean": main["historical_mean_deg"],
        "qing_highest_in_use": main["highest_in_use_deg"],
        "qing_full_6973": main["highest_true_deg"],
        "qing_full_6913": alternate["highest_true_deg"],
    }
    return {k: signed_error(v, target) for k, v in candidate_angles.items()}


def summarize(rows, protocol, planned):
    methods = next(row["signed_error_arcmin"].keys() for row in rows if row["signed_error_arcmin"])
    summary = {}
    for name in methods:
        signed = [row["signed_error_arcmin"][name] for row in rows if row["signed_error_arcmin"]]
        errors = [abs(x) for x in signed]
        within = sum(error <= protocol["precision_threshold_arcminute"] for error in errors)
        summary[name] = {
            "reported_dates": len(errors),
            "within_precision": within,
            "strict_gate": within >= planned - protocol["allowed_missing_or_outside_precision"],
            "wide_gate_on_observed_dates": max(errors) <= protocol["maximum_threshold_arcminute"],
            "mean_absolute_error_arcmin": fmean(errors),
            "median_signed_error_arcmin": median(signed),
            "maximum_absolute_error_arcmin": max(errors),
        }
    return summary


def edition(year, sources, protocol):
    spec = protocol["source_editions"][year]
    if sources["source_sha256"] != spec["pdf_sha256"]:
        raise ValueError(f"Unexpected scan for {year}")
    rows = []
    month_starts = []
    start = date.fromisoformat(spec["first_date"])
    days = protocol["day_of_lunar_month"]
    for month in sources["monthly"]:
        page = month["pdf_page_one_based"]
        count = month["printed_days"]
        if page not in spec["pdf_pages"] or count not in (29, 30):
            raise ValueError(f"Unexpected page or month size for {year}/{month['month']}")
        month_starts.append(start.isoformat())
        for day, entry in zip(days, month["printed_mansion_degree_minute"], strict=True):
            gregorian = start + timedelta(days=day - 1)
            rows.append({
                "lunar_month": month["month"],
                "lunar_day": day,
                "pdf_page": page,
                "gregorian_local_date": gregorian.isoformat(),
                "printed_mansion_degree_minute": entry,
                "signed_error_arcmin": compare(gregorian, entry) if entry is not None else None,
            })
        start += timedelta(days=count)
    month_starts.append(start.isoformat())
    external = sources["external_month_starts_and_next_year"]
    calendar_disagreements = [
        [a, b] for a, b in zip(month_starts, external, strict=True) if a != b
    ]
    planned = spec["planned_dates"]
    unique_dates = {(row["lunar_month"], row["lunar_day"]) for row in rows}
    if len(unique_dates) != len(rows) or len(rows) > planned:
        raise ValueError(f"Duplicate or unexpected days for {year}")
    fully_inked = [
        row for row in rows
        if row["printed_mansion_degree_minute"] and row["printed_mansion_degree_minute"][2] is not None
    ]
    return {
        "planned_dates": planned,
        "observed_days_with_printed_month": len(rows),
        "reconciled_month_starts_including_next_year": len(external) - len(calendar_disagreements),
        "all_external_date_disagreements": calendar_disagreements,
        "summary": summarize(rows, protocol, planned),
        "summary_excluding_bare_degrees": summarize(fully_inked, protocol, planned),
        "observations": rows,
    }


def main(args):
    protocol = verified_json(HERE / "protocol.json", args.registration_sha256)
    for name, expected in protocol["files_sha256"].items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Registered source or method differs: {name}")
    transcription = verified_json(HERE / "transcription.json", args.transcription_sha256)
    report = {
        "registration_sha256": args.registration_sha256,
        "transcription_sha256": args.transcription_sha256,
        "formula_version": qing.VERSION,
        "fitted_parameters": 0,
        "comparison_by_edition": {year: edition(year, sources, protocol)
                                  for year, sources in transcription["editions"].items()},
    }
    with args.output.open("x", encoding="utf8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--registration-sha256", required=True)
    cli.add_argument("--transcription-sha256", required=True)
    cli.add_argument("--output", required=True, type=Path)
    main(cli.parse_args())
