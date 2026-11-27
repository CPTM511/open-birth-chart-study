"""Convert modern solar coordinates under two declared Shoushi continuations."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from functools import lru_cache
from itertools import accumulate
import json
from math import isfinite

import swisseph as swe

from open_birth_chart import astronomy
from rounds.r22.degrees import BRANCHES, MANSIONS, ShoushiScale, branch_index, ming_palace
from rounds.r27.archive_source import read_json, require
from .input_data import HERE, QUARTER, TURN


PRECESSION_OLD_DEGREES_PER_YEAR = Fraction("0.015")
YEAR_DAYS = Fraction("365.2425")
YUAN_HISTORICAL_ORIGIN = Fraction("315.1075")
CHOU_READINGS = ("wikisource_san", "shidian_er")


@dataclass(frozen=True)
class QuarterTable:
    ecliptic: tuple[Fraction, ...]
    equatorial: tuple[Fraction, ...]

    def from_ecliptic(self, angle):
        return self._around_turn(angle, self.ecliptic, self.equatorial)

    def from_equator(self, angle):
        return self._around_turn(angle, self.equatorial, self.ecliptic)

    @staticmethod
    def _around_turn(angle, source, target):
        quadrant, within = divmod(angle % TURN, QUARTER)
        coordinate = QUARTER - within if quadrant % 2 else within
        index = min(bisect_right(source, coordinate) - 1, len(source) - 2)
        mapped = target[index] + (coordinate - source[index]) * (
            (target[index + 1] - target[index]) / (source[index + 1] - source[index])
        )
        return quadrant * QUARTER + (QUARTER - mapped if quadrant % 2 else mapped)


def accumulated_starts(widths):
    values = tuple(accumulate(widths.values(), initial=Fraction(0)))
    return dict(zip(widths, values[:-1], strict=True))


@lru_cache(maxsize=1)
def winter_epoch_jd():
    start = swe.julday(1280, 12, 15, 0.0, swe.GREG_CAL)
    jd = swe.solcross_ut(270.0, start, swe.FLG_MOSEPH)
    require(start < jd < start + 10, "The specified 1280 solstice is outside its registered window")
    return jd


@dataclass(frozen=True)
class SolarFrame:
    sun_old_degrees: Fraction
    mansion_starts: dict[str, Fraction]
    palace_starts: dict[str, Fraction]

    @property
    def solar_mansion(self):
        return label_at(self.sun_old_degrees, self.mansion_starts)

    @property
    def solar_palace(self):
        return label_at(self.sun_old_degrees, self.palace_starts)


def label_at(coordinate, starts):
    candidate = min(starts, key=lambda label: (coordinate - starts[label]) % TURN)
    return candidate, (coordinate - starts[candidate]) % TURN


def palace_width(palace, starts):
    following = BRANCHES[(branch_index(palace) - 1) % 12]
    return (starts[following] - starts[palace]) % TURN


class ShoushiCoordinates:
    def __init__(self, chou_reference, *, corrected=True):
        source = read_json(HERE / "source_numeric.json")
        equatorial = "equatorial_quarter_knots_old_degrees" if corrected else "uncorrected_equatorial_quarter_knots_old_degrees"
        self.table = QuarterTable(tuple(map(Fraction, source["ecliptic_quarter_knots_old_degrees"])),
                                  tuple(map(Fraction, source[equatorial])))
        self.equatorial_widths = {name: Fraction(source["equatorial_widths_old_degrees"][name]) for name in MANSIONS}
        self.equatorial_starts = accumulated_starts(self.equatorial_widths)
        self.winter_equator = (self.equatorial_starts["虚"] + 6 + YUAN_HISTORICAL_ORIGIN) % TURN
        require(self.winter_equator == self.equatorial_starts["箕"] + 10, "The two source epoch anchors differ")
        self.printed = ShoushiScale(chou_reference)
        require(self.printed.cycle == TURN, "The R22 palace scale differs")
        self.winter_ecliptic = self.ecliptic_zero_offset(self.winter_equator)
        self.palace_equatorial_anchors = {
            palace: (self.table.from_ecliptic((ecliptic - self.winter_ecliptic) % TURN) + self.winter_equator) % TURN
            for palace, ecliptic in self.printed.heads.items()
        }

    def ecliptic_zero_offset(self, winter_equator):
        return (-self.table.from_equator((-winter_equator) % TURN)) % TURN

    def project_right_ascension(self, equatorial, winter_equator):
        return (self.table.from_equator((equatorial - winter_equator) % TURN)
                + self.ecliptic_zero_offset(winter_equator)) % TURN

    def sun_frames(self, tropical_longitude, elapsed_years):
        standardized_sun = ((Fraction(str(tropical_longitude)) - 270) % 360) * TURN / 360
        drift = PRECESSION_OLD_DEGREES_PER_YEAR * elapsed_years
        equator = (self.winter_equator - drift) % TURN
        return {
            "rotated_printed_table": SolarFrame((standardized_sun + self.winter_ecliptic - drift) % TURN,
                                                self.printed.starts, self.printed.heads),
            "reprojected_equatorial_table": SolarFrame(
                (standardized_sun + self.ecliptic_zero_offset(equator)) % TURN,
                {name: self.project_right_ascension(start, equator) for name, start in self.equatorial_starts.items()},
                {palace: self.project_right_ascension(start, equator)
                 for palace, start in self.palace_equatorial_anchors.items()},
            ),
        }


def transfer(frame, hour_branch, anchor):
    if anchor not in ("head", "tail"):
        raise ValueError("Use head or tail for the transfer anchor")
    solar, distance = frame.solar_palace
    ming = ming_palace(solar, hour_branch)
    target_width = palace_width(ming, frame.palace_starts)
    if anchor == "tail":
        distance += target_width - palace_width(solar, frame.palace_starts)
    result = {"ming_palace": ming, "nominal_first_change_age": None}
    if not 0 <= distance < target_width:
        return {**result, "status": "outside_target_palace"}
    ming_angle = (frame.palace_starts[ming] + distance) % TURN
    mansion, within = label_at(ming_angle, frame.mansion_starts)
    result.update(ming_mansion=mansion, ming_degree_old_units=float(within), palace_offset_old_units=float(distance))
    if distance >= 30:
        return {**result, "status": "outside_first_change_lookup"}
    return {**result, "status": "computed", "nominal_first_change_age": 11 + int(distance // 3)}


def time_branches(timestamp, longitude):
    if timestamp.utcoffset() is None:
        raise ValueError("Supply a civil timestamp with an explicit UTC offset")
    if not isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Supply east-positive longitude in degrees between −180 and 180")
    utc = timestamp.astimezone(timezone.utc)
    solar = utc + timedelta(seconds=longitude * 240)
    clocks = {"civil": timestamp, "local_mean_solar": solar}
    return {key: BRANCHES[((clock.hour + 1) // 2) % 12] for key, clock in clocks.items()}


def calculate(timestamp, longitude):
    branches = time_branches(timestamp, longitude)
    jd = astronomy.julian_day(timestamp)
    elapsed_years = Fraction(str(jd - winter_epoch_jd())) / YEAR_DAYS
    solar_longitude = astronomy.position(jd, "Sun")["longitude"]
    projections = {}
    for chou in CHOU_READINGS:
        calculator = ShoushiCoordinates(chou)
        frames = calculator.sun_frames(solar_longitude, elapsed_years)
        projections[chou] = {}
        for method, frame in frames.items():
            mansion, degree = frame.solar_mansion
            projections[chou][method] = {
                "solar_palace": frame.solar_palace[0],
                "solar_mansion": mansion,
                "solar_degree_old_units": float(degree),
                "time_branches": {clock: {anchor: transfer(frame, branch, anchor) for anchor in ("head", "tail")}
                                  for clock, branch in branches.items()},
            }
    return {"birth_utc": timestamp.astimezone(timezone.utc).isoformat(), "solar_tropical_longitude_deg": solar_longitude,
            "time_branch": branches, "historical_model_versions": projections}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--birth", required=True, help="Gregorian ISO 8601 timestamp with offset")
    parser.add_argument("--longitude", type=float, required=True, help="Longitude in degrees, east positive")
    args = parser.parse_args()
    print(json.dumps(calculate(datetime.fromisoformat(args.birth), args.longitude), ensure_ascii=False, indent=2))
