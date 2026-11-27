"""Replay the preregistered historic widths, tropical boundaries and daily labels."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import date, timedelta
from fractions import Fraction
from itertools import combinations
from math import degrees, sqrt
from pathlib import Path
from statistics import mean

import erfa
import swisseph as swe

from open_birth_chart import astronomy
from rounds.r22.degrees import MANSIONS
from rounds.r27.archive_source import digest, read_json, require, write_json
from rounds.r32.coordinates import ShoushiCoordinates, YEAR_DAYS, winter_epoch_jd
from rounds.r32.input_data import TURN
from .astrometry import Epoch, Star, independent_longitude, signed_degrees
from .source import BRANCHES as STAR_BRANCHES, HERE, POSITION_FIELDS


WINTER_SOLSTICE_LONGITUDE = 270
HISTORICAL_TOLERANCE_ARCMIN = 5
BOUNDARY_TOLERANCE_ARCMIN = 15
SECOND_METHOD_TOLERANCE_ARCSEC = 5
SCHEMES = ("rotated_printed_table", "reprojected_equatorial_table")
METHODS = (*STAR_BRANCHES, *SCHEMES)
NEXT_MANSION = dict(zip(MANSIONS, MANSIONS[1:] + MANSIONS[0], strict=True))


def signed_widths(boundaries):
    return {name: signed_degrees(boundaries[following] - boundaries[name])
            for name, following in NEXT_MANSION.items()}


def measure(errors, tolerance):
    largest = max(errors, key=lambda name: abs(errors[name]))
    return {
        "mean_absolute": round(mean(map(abs, errors.values())), 8),
        "root_mean_square": round(sqrt(mean(value * value for value in errors.values())), 8),
        "largest_absolute": round(abs(errors[largest]), 8),
        "largest_at": largest,
        "within_tolerance": sum(abs(value) <= tolerance for value in errors.values()),
        "denominator": len(errors),
        "tolerance": tolerance,
    }


def solar_frames(calculator, longitude, jd_ut):
    years = Fraction(str(jd_ut - winter_epoch_jd())) / YEAR_DAYS
    return calculator.sun_frames(longitude, years)


def model_boundaries(calculator, jd_ut):
    return {
        scheme: {name: float((WINTER_SOLSTICE_LONGITUDE + (edges - frame.sun_old_degrees) % TURN * 360 / TURN) % 360)
                 for name, edges in frame.mansion_starts.items()}
        for scheme, frame in solar_frames(calculator, WINTER_SOLSTICE_LONGITUDE, jd_ut).items()
    }


def model_errors(reference, predicted):
    errors = {name: 60 * signed_degrees(predicted[name] - reference[name]) for name in MANSIONS}
    anchor_shift = signed_degrees(predicted["角"] - reference["角"])
    aligned = {name: 60 * signed_degrees(predicted[name] - anchor_shift - reference[name]) for name in MANSIONS}
    return {
        "signed_model_minus_star_arcmin": {name: round(err, 8) for name, err in errors.items()},
        "absolute_summary_arcmin": measure(errors, BOUNDARY_TOLERANCE_ARCMIN),
        "jiao_aligned_summary_arcmin": measure(aligned, BOUNDARY_TOLERANCE_ARCMIN),
    }


def angles_at(epoch, star_list, *, proper_motion=True):
    ras = {mansion: epoch.right_ascension(star, proper_motion=proper_motion)
           for mansion, star in star_list.items()}
    return ras, {mansion: epoch.meridian_longitude(ra) for mansion, ra in ras.items()}


def label_at(angle, boundaries):
    return min(boundaries, key=lambda mansion: (angle - boundaries[mansion]) % 360.0)


def independent_ra_label(longitude, ras, epoch):
    ascension = epoch.ecliptic_right_ascension(longitude)
    ordered = sorted((angle, mansion) for mansion, angle in ras.items())
    return ordered[bisect_right([angle for angle, _ in ordered], ascension) - 1][1]


def date_noon(year, month=1, day=1):
    return swe.julday(year, month, day, 12.0, swe.GREG_CAL)


def astro_date(jd):
    year, month, day, _hour = swe.revjul(jd, swe.GREG_CAL)
    return date(year, month, day).isoformat()


def crossing(lo, hi, star_list):
    def separation(jd):
        epoch = Epoch.from_ut(jd)
        return signed_degrees(epoch.right_ascension(star_list["参"]) - epoch.right_ascension(star_list["觜"]))

    lower, upper = separation(lo), separation(hi)
    result = {"start_width_deg": round(lower, 9), "end_width_deg": round(upper, 9)}
    if lower * upper > 0:
        return dict(result, status="not_bracketed")
    for _ in range(40):
        middle = (lo + hi) / 2
        if separation(middle) * lower > 0:
            lo = middle
        else:
            hi = middle
    root = (lo + hi) / 2
    require(abs(separation(root)) < 1e-7, "The alleged crossing is not a zero of the arc")
    return dict(result, status="bracketed", nominal_ut_jd=round(root, 8), gregorian_day=astro_date(root))


def epoch_report(jd_ut, star_lists, calculator):
    epoch = Epoch.from_ut(jd_ut)
    predicted = model_boundaries(calculator, jd_ut)
    groups = {}
    old_widths = calculator.equatorial_widths
    for branch, star_list in star_lists.items():
        ras, longitudes = angles_at(epoch, star_list)
        _, fixed = angles_at(epoch, star_list, proper_motion=False)
        widths = signed_widths(ras)
        errors = {name: (width - float(old_widths[name] * 360 / TURN)) * 60
                  for name, width in widths.items()}
        numeric_gaps = {name: signed_degrees(longitudes[name] - independent_longitude(star, epoch)) * 3600
                        for name, star in star_list.items()}
        groups[branch] = {
            "right_ascension_deg": {name: round(ra, 9) for name, ra in ras.items()},
            "projected_ecliptic_longitude_deg": {name: round(lon, 9) for name, lon in longitudes.items()},
            "signed_equatorial_width_deg": {name: round(width, 9) for name, width in widths.items()},
            "reversed_in_traditional_order": [name for name in MANSIONS if widths[name] < 0],
            "historical_width_signed_observed_minus_printed_arcmin": {
                name: round(width, 8) for name, width in errors.items()
            },
            "historical_width_summary_arcmin": measure(errors, HISTORICAL_TOLERANCE_ARCMIN),
            "proper_motion_signed_boundary_shift_arcsec": {
                name: round(3600 * signed_degrees(longitudes[name] - fixed[name]), 8) for name in MANSIONS
            },
            "independent_projection_differences_arcsec": measure(numeric_gaps, SECOND_METHOD_TOLERANCE_ARCSEC),
            "model_errors": {scheme: model_errors(longitudes, boundaries) for scheme, boundaries in predicted.items()},
        }
    return {
        "nominal_ut_jd": round(jd_ut, 9), "tt_jd": round(epoch.jd_tt, 9),
        "mean_obliquity_deg": round(degrees(epoch.obliquity), 9),
        "model_boundary_lon_deg": {method: {key: round(value, 9) for key, value in values.items()}
                                   for method, values in predicted.items()},
        "star_branches": groups,
    }


def daily_report(year, star_lists, calculator):
    first_day = date(year, 1, 1)
    length = (date(year + 1, 1, 1) - first_day).days
    daily_labels = {method: [] for method in METHODS}
    legacy_model_disagreements, ra_projection_disagreements, second_model_label_disagreements = 0, 0, 0
    first_jd = date_noon(year)
    for offset in range(length):
        jd = first_jd + offset
        epoch = Epoch.from_ut(jd)
        mean_longitude = swe.calc_ut(jd, swe.SUN, astronomy.FLAGS | swe.FLG_NONUT)[0][0]
        for branch, star_list in star_lists.items():
            ras, projected = angles_at(epoch, star_list)
            label = label_at(mean_longitude, projected)
            daily_labels[branch].append(label)
            ra_projection_disagreements += label != independent_ra_label(mean_longitude, ras, epoch)
            independent = {name: independent_longitude(star, epoch) for name, star in star_list.items()}
            second_model_label_disagreements += label != label_at(mean_longitude, independent)
        mean_frames = solar_frames(calculator, mean_longitude, jd)
        for method, frame in mean_frames.items():
            daily_labels[method].append(frame.solar_mansion[0])
        apparent_longitude = astronomy.position(jd, "Sun")["longitude"]
        first, second = solar_frames(calculator, apparent_longitude, jd).values()
        legacy_model_disagreements += first.solar_mansion[0] != second.solar_mansion[0]
    return {
        "origin_utc": f"{first_day.isoformat()}T12:00:00Z",
        "daily_samples": length,
        "labels_by_day": {method: "".join(values) for method, values in daily_labels.items()},
        "comparisons": [
            {"left": left, "right": right,
             "disagreeing_dates": [(first_day + timedelta(days=i)).isoformat()
                                   for i, (a, b) in enumerate(zip(daily_labels[left], daily_labels[right], strict=True))
                                   if a != b]}
            for left, right in combinations(METHODS, 2)
        ],
        "r32_apparent_sun_model_label_disagreements": legacy_model_disagreements,
        "equatorial_label_replay_differences": ra_projection_disagreements,
        "alternative_astrometry_label_differences": second_model_label_disagreements,
    }


def component_sensitivity(source, catalogue, historical, anchor_jds):
    branches = []
    for label, group in source[STAR_BRANCHES[0]].items():
        previous = MANSIONS[MANSIONS.index(label) - 1]
        for alternate in group["alternates"]:
            alternate_hip = alternate["hip"]
            if alternate_hip is None:
                branches.append({"mansion": label, "hr": alternate["hr"], "status": "no_complete_hipparcos_match"})
                continue
            changed = historical.copy()
            changed[label] = catalogue[alternate_hip]
            deltas = {}
            for name, jd in anchor_jds.items():
                epoch = Epoch.from_ut(jd)
                original_ra, original_long = angles_at(epoch, historical)
                alternate_ra, alternate_long = angles_at(epoch, changed)
                original_widths, alternate_widths = signed_widths(original_ra), signed_widths(alternate_ra)
                deltas[name] = {
                    "boundary_shift_arcmin": round(60 * signed_degrees(alternate_long[label] - original_long[label]), 8),
                    "independent_projection_difference_arcsec": round(3600 * signed_degrees(
                        alternate_long[label] - independent_longitude(changed[label], epoch)), 8),
                    "affected_width_shift_arcmin": {
                        lodge: round(60 * (alternate_widths[lodge] - original_widths[lodge]), 8)
                        for lodge in (previous, label)
                    },
                }
            branches.append({"mansion": label, "hr": alternate["hr"], "hip": alternate_hip,
                             "status": "compared", "deltas": deltas})
    return branches


def run(source_path=HERE / "source_numeric.json"):
    source = read_json(source_path)
    catalogue = {int(hip): Star(*(float(row[field]) for field in POSITION_FIELDS))
                 for hip, row in source["astrometry"].items()}
    identities = {
        STAR_BRANCHES[0]: {name: group["primary"]["hip"] for name, group in source[STAR_BRANCHES[0]].items()},
        STAR_BRANCHES[1]: source[STAR_BRANCHES[1]],
    }
    for mapping in identities.values():
        require("".join(mapping) == MANSIONS and len(set(mapping.values())) == len(MANSIONS),
                "Each stellar mapping must cover 28 distinct stars in source order")
    star_lists = {branch: {name: catalogue[hip] for name, hip in mapping.items()}
                  for branch, mapping in identities.items()}
    calculator = ShoushiCoordinates("wikisource_san")
    anchor_jds = {
        "1280_winter_solstice": winter_epoch_jd(),
        **{f"{year}_jan_1_noon": date_noon(year) for year in (1600, 2000, 2026)},
    }
    return {
        "source_numeric_sha256": digest(source_path),
        "r32_source_numeric_sha256": digest(HERE.parent / "r32" / "source_numeric.json"),
        "versions": {"pyerfa": erfa.__version__, "swiss_ephemeris": swe.version},
        "stars_by_scheme": identities,
        "epochs": {label: epoch_report(jd, star_lists, calculator) for label, jd in anchor_jds.items()},
        "zui_shen_meridian_crossing": {
            branch: crossing(winter_epoch_jd(), date_noon(2026), stars) for branch, stars in star_lists.items()
        },
        "historical_component_sensitivity": component_sensitivity(source, catalogue, star_lists[STAR_BRANCHES[0]],
                                                                  anchor_jds),
        "daily": {str(year): daily_report(year, star_lists, calculator) for year in (2000, 2026)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE / "source_numeric.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_json(args.output, run(args.source))


if __name__ == "__main__":
    main()
