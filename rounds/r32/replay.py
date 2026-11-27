"""Reproduce the source-era widths, Ming retrodictions and standardized modern comparisons."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from fractions import Fraction as F
from itertools import pairwise
from math import atan2, cos, degrees, radians, sin
from pathlib import Path
from statistics import mean

import astronomy as independent_astronomy
import swisseph as swe

from open_birth_chart import astronomy
from rounds.r27.archive_source import digest, require, write_json
from .coordinates import (
    BRANCHES, CHOU_READINGS, HERE, QUARTER, TURN, YEAR_DAYS, YUAN_HISTORICAL_ORIGIN,
    ShoushiCoordinates, transfer, winter_epoch_jd,
)


def nearest_hundredth(value):
    return F((value * 100 + F(1, 2)) // 1, 100)


def width_report(geometry, inverse):
    source = geometry.printed.widths
    angles = tuple(inverse((p - geometry.winter_equator) % TURN)
                   for p in geometry.equatorial_starts.values())
    widths = dict(zip(source, ((end - start) % TURN for start, end in pairwise((*angles, angles[0]))), strict=True))
    require(sum(widths.values()) == TURN, "A set of projected widths does not cover one full turn")
    error = {key: widths[key] - source[key] for key in widths}
    return {
        "mean_absolute_error_old_degrees": float(mean(map(abs, error.values()))),
        "max_absolute_error_old_degrees": float(max(map(abs, error.values()))),
        "within_0_005_old_degrees": sum(abs(value) <= F(".005") for value in error.values()),
        "match_rounded_hundredth_excluding_xu": sum(nearest_hundredth(widths[key]) == source[key] for key in widths if key != "虚"),
        "xu_special_fraction_error_old_degrees": float(error["虚"]),
        "group_sums_old_degrees": [float(sum(list(widths.values())[i:i + 7])) for i in range(0, 28, 7)],
        "signed_errors_old_degrees": {key: float(value) for key, value in error.items()},
        "projected_widths_old_degrees": {key: float(value) for key, value in widths.items()},
    }


def spherical_inverse(obliquity_deg, angle):
    ra = radians(270.0 + float(angle * 360 / TURN))
    ecliptic = degrees(atan2(sin(ra) / cos(radians(obliquity_deg)), cos(ra)))
    return F(str((ecliptic - 270.0) % 360)) * TURN / 360


def ming_checks(geometry):
    elapsed_whole_years = 1599 - 1281
    century_increment = F(elapsed_whole_years // 100, 10000)
    seasonal_accumulation = elapsed_whole_years * (YEAR_DAYS - century_increment)
    ji = geometry.equatorial_starts["箕"]
    origin = geometry.equatorial_starts["虚"] + 6
    readings = {"volume_two": F("4.7282"), "volume_fifty_one": F("4.7258")}
    recorded_ra = F("5.1346")
    estimates = {}
    for variant, used_turn in (("fixed_turn", TURN), ("adjusted_turn", TURN + century_increment)):
        predicted_ra = ((origin + (seasonal_accumulation + YUAN_HISTORICAL_ORIGIN) % used_turn) % TURN) - ji
        estimates[variant] = {
            "equatorial_ji_exact": str(predicted_ra),
            "equatorial_difference_old_degrees": float(predicted_ra - recorded_ra),
            "ecliptic_ji": float(geometry.table.from_equator(predicted_ra)),
        }
    mapped = geometry.table.from_equator(recorded_ra)
    return {
        "printed_seasonal_accumulation_exact": str(F("116147.0196")),
        "recomputed_seasonal_accumulation_exact": str(seasonal_accumulation),
        "matches_printed_seasonal_accumulation": seasonal_accumulation == F("116147.0196"),
        "printed_equatorial_ji_old_degrees": float(recorded_ra),
        "epoch_year_label": 1281,
        "ming_worked_example_year_label": 1599,
        "elapsed_years": elapsed_whole_years,
        "reconstructed_from_time_rule": estimates,
        "ecliptic_ji_given_printed_equatorial_ji": float(mapped),
        "printed_ecliptic_ji_old_degrees": {name: float(v) for name, v in readings.items()},
        "ecliptic_differences_given_printed_equatorial_ji": {key: float(mapped - value) for key, value in readings.items()},
        "matches_0_0001_old_degrees_given_printed_equatorial_ji": {
            key: abs(mapped - value) <= F("0.0001") for key, value in readings.items()},
    }


def independent_subarc(angle, inputs, outputs):
    """Accumulate the lengths of the traversed segments instead of locating a single segment."""
    return sum(
        min(max(angle - a, 0), b - a) * (d - c) / (b - a)
        for (a, b), (c, d) in zip(pairwise(inputs), pairwise(outputs), strict=True)
    )


def across_seasons(angle, inputs, outputs):
    reference = angle % TURN
    if reference < QUARTER:
        return independent_subarc(reference, inputs, outputs)
    if reference < 2 * QUARTER:
        return 2 * QUARTER - independent_subarc(2 * QUARTER - reference, inputs, outputs)
    if reference < 3 * QUARTER:
        return 2 * QUARTER + independent_subarc(reference - 2 * QUARTER, inputs, outputs)
    return TURN - independent_subarc(TURN - reference, inputs, outputs)


def verify_angular_geometry(table):
    checked = 0
    for forward, inverse, inputs, outputs in (
        (table.from_ecliptic, table.from_equator, table.ecliptic, table.equatorial),
        (table.from_equator, table.from_ecliptic, table.equatorial, table.ecliptic),
    ):
        probes = [*inputs, *((a + b) / 2 for a, b in pairwise(inputs))]
        for quadrant in range(4):
            for value in probes:
                angle = quadrant * QUARTER + value
                mapped = forward(angle)
                require(inverse(mapped) == angle % TURN and mapped == across_seasons(angle, inputs, outputs),
                        "The integrated and indexed angular transforms disagree")
                checked += 1
    return checked


def compare_modern_days(chou):
    calculator = ShoushiCoordinates(chou)
    calendar, outcomes = Counter(), {anchor: Counter() for anchor in ("head", "tail")}
    alternate_run = {name: Counter() for name in ("rotated_printed_table", "reprojected_equatorial_table")}
    max_longitude_gap_arcsec = 0.0
    first = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    floor_year_jd = winter_epoch_jd()
    for day_index in range(366):
        jd = astronomy.julian_day(first + timedelta(days=day_index))
        longitude = astronomy.position(jd, "Sun")["longitude"]
        comparison_vector = independent_astronomy.GeoVector(independent_astronomy.Body.Sun,
                                                            independent_astronomy.Time(jd - 2451545), True)
        comparison_longitude = independent_astronomy.Ecliptic(comparison_vector).elon
        max_longitude_gap_arcsec = max(max_longitude_gap_arcsec,
                                       3600 * astronomy.circular_distance(longitude, comparison_longitude))
        years = F(str(jd - floor_year_jd)) / YEAR_DAYS
        frames = calculator.sun_frames(longitude, years)
        alternate_frames = calculator.sun_frames(comparison_longitude, years)
        for name, frame in frames.items():
            alternate = alternate_frames[name]
            alternate_run[name]["mansion_days"] += frame.solar_mansion[0] != alternate.solar_mansion[0]
            alternate_run[name]["palace_days"] += frame.solar_palace[0] != alternate.solar_palace[0]
        fixed, dynamic = frames.values()
        calendar["days"] += 1
        calendar["solar_mansion_disagrees"] += fixed.solar_mansion[0] != dynamic.solar_mansion[0]
        calendar["solar_palace_disagrees"] += fixed.solar_palace[0] != dynamic.solar_palace[0]
        native_solar_ra = (calculator.winter_equator - F("0.015") * years + calculator.table.from_ecliptic(
            ((F(str(longitude)) - 270) % 360) * TURN / 360
        )) % TURN
        native_mansion = min(calculator.equatorial_starts,
                             key=lambda k: (native_solar_ra - calculator.equatorial_starts[k]) % TURN)
        native_palace = min(calculator.palace_equatorial_anchors,
                            key=lambda k: (native_solar_ra - calculator.palace_equatorial_anchors[k]) % TURN)
        require((native_mansion, native_palace) == (dynamic.solar_mansion[0], dynamic.solar_palace[0]),
                "Direct equatorial and reprojected ecliptic interval labels differ")
        for branch in BRANCHES:
            for anchor, tally in outcomes.items():
                left, right = transfer(fixed, branch, anchor), transfer(dynamic, branch, anchor)
                tally["date_branch_combinations"] += 1
                tally["ming_palace_disagrees"] += left["ming_palace"] != right["ming_palace"]
                tally["rotated_" + left["status"]] += 1
                tally["reprojected_" + right["status"]] += 1
                sides = (left["nominal_first_change_age"], right["nominal_first_change_age"])
                if None not in sides:
                    tally["both_age_computable"] += 1
                    tally["age_disagrees_when_both_computable"] += sides[0] != sides[1]
                    tally["maximum_absolute_age_difference"] = max(
                        tally["maximum_absolute_age_difference"], abs(sides[0] - sides[1]))
                    if left["ming_palace"] == right["ming_palace"]:
                        tally["largest_age_difference_given_same_ming_palace"] = max(
                            tally["largest_age_difference_given_same_ming_palace"], abs(sides[0] - sides[1]))
                    elif sides[0] != sides[1]:
                        tally["age_disagreements_with_a_change_of_ming_palace"] += 1
                else:
                    tally["neither_age_computable" if sides.count(None) == 2 else "only_one_age_computable"] += 1
                for name, reading in zip(frames, (left, right), strict=True):
                    alternate = transfer(alternate_frames[name], branch, anchor)
                    keys = ("nominal_first_change_age", "status")
                    alternate_run[name][f"{anchor}_age_or_status_combinations"] += any(
                        reading[key] != alternate[key] for key in keys)
    return {
        "solar_dates": dict(calendar),
        "first_change_age": {anchor: dict(counts) for anchor, counts in outcomes.items()},
        "other_solar_ephemeris": {"maximum_solar_longitude_difference_arcsec": max_longitude_gap_arcsec,
                                 "classification_differences": {name: dict(v) for name, v in alternate_run.items()}},
    }


def run(output):
    geometry = ShoushiCoordinates("wikisource_san")
    uncorrected = ShoushiCoordinates("wikisource_san", corrected=False)
    winter_jd = winter_epoch_jd()
    nutation, _ = swe.calc_ut(winter_jd, swe.ECL_NUT, swe.FLG_MOSEPH)
    obliquity = nutation[1]
    require(astronomy.circular_distance(astronomy.position(winter_jd, "Sun")["longitude"], 270) < 1e-6,
            "The astronomy adapter did not obtain the specified winter-longitude anchor")
    width_tables = {
        "native_corrected": width_report(geometry, geometry.table.from_equator),
        "native_as_printed": width_report(uncorrected, uncorrected.table.from_equator),
        "spherical_mean_obliquity": width_report(geometry, lambda angle: spherical_inverse(obliquity, angle)),
        "equator_equals_ecliptic": width_report(geometry, lambda angle: angle),
    }
    write_json(output, {
        "round": "R32",
        "files_sha256": {name: digest(HERE / name) for name in
                         ("REGISTRATION.zh.md", "source_numeric.json", "coordinates.py", "input_data.py", "replay.py")},
        "source_epoch": {"winter_eq_from_jiao": str(geometry.winter_equator), "winter_ji_ra": "10",
                         "winter_ecliptic_from_jiao": float(geometry.winter_ecliptic),
                         "astronomical_epoch_julian_day_ut": winter_jd, "swiss_mean_obliquity_deg": obliquity,
                         "swiss_ephemeris_version": swe.version},
        "reconstructed_widths": width_tables,
        "ming_1599_worked_example": ming_checks(geometry),
        "modern_standardized_examples": {chou: compare_modern_days(chou) for chou in CHOU_READINGS},
        "verification": {"independent_exact_arc_and_roundtrip_probes": verify_angular_geometry(geometry.table),
                         "independent_angular_and_roundtrip_probes_for_uncorrected_reading":
                             verify_angular_geometry(uncorrected.table),
                         "direct_equatorial_sector_labels_verified_for_all_366_dates_and_both_chou_readings": True},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
