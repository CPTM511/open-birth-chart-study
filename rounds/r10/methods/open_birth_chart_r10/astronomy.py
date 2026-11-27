# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared deterministic astronomy for the registered R8 reference models.

Uses the explicitly requested Moshier backend in Swiss Ephemeris 2.10.03.
Positions are geocentric apparent tropical ecliptic-of-date, degrees. Input
clock labels use nominal UT; missing historical UT1 corrections are disclosed,
not inferred from a location or an outcome. No network or outcome inputs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math
import swisseph as swe

VERSION = "OBS-R8-ASTRO-1.0"
FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED
TROPICAL_YEAR_DAYS = 365.2422
UTC = timezone.utc
BODY_IDS = {
    "Sun": swe.SUN, "Moon": swe.MOON, "Mercury": swe.MERCURY,
    "Venus": swe.VENUS, "Mars": swe.MARS, "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN, "Uranus": swe.URANUS, "Neptune": swe.NEPTUNE,
    "Pluto": swe.PLUTO, "TrueNode": swe.TRUE_NODE,
    "MeanNode": swe.MEAN_NODE, "MeanApogee": swe.MEAN_APOG,
    "OsculatingApogee": swe.OSCU_APOG,
}
SEVEN = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn")
TEN = SEVEN + ("Uranus", "Neptune", "Pluto")


class InputError(ValueError):
    """An unresolved input, never a low or high astrological score."""


def circular_distance(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def julian_day(dt):
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    hour = dt.hour + dt.minute / 60 + (dt.second + dt.microsecond / 1e6) / 3600
    return swe.julday(dt.year, dt.month, dt.day, hour, swe.GREG_CAL)


def normalize_birth(row, shift_minutes=0):
    if not isinstance(row, dict):
        raise InputError("Birth must be a mapping")
    if str(row.get("calendar", "gregorian")).lower() != "gregorian":
        raise InputError("Explicit Gregorian calendar required")
    try:
        label = row["birth_local"]
        if "T" not in label and " " not in label:
            raise ValueError("date only")
        civil = datetime.fromisoformat(label)
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError("Complete birth_local clock label required") from exc
    if civil.tzinfo is not None:
        raise InputError("birth_local must be a local label without zone suffix")
    if not 1880 <= civil.year <= 2025:
        raise InputError("Birth outside registered 1880–2025 range")
    offset = row.get("source_offset_seconds")
    if offset is None and row.get("timezone_offset_minutes") is not None:
        offset = float(row["timezone_offset_minutes"]) * 60
    if offset is not None:
        if isinstance(offset, bool) or not math.isfinite(float(offset)) or abs(float(offset)) >= 86400:
            raise InputError("Invalid source time offset")
        offset = float(offset)
    absolute = None
    if row.get("birth_utc") is not None:
        try:
            absolute = datetime.fromisoformat(row["birth_utc"].replace("Z", "+00:00"))
            if absolute.tzinfo is None:
                absolute = absolute.replace(tzinfo=UTC)
            if absolute.utcoffset() != timedelta(0):
                raise ValueError("nonzero UTC offset")
        except (TypeError, ValueError) as exc:
            raise InputError("birth_utc must be a zero-offset instant label") from exc
        implied = (civil - absolute.replace(tzinfo=None)).total_seconds()
        if offset is not None and abs(implied - offset) > 1:
            raise InputError("Civil and absolute labels disagree by more than 1 second")
        offset = implied
    elif offset is not None:
        absolute = (civil - timedelta(seconds=offset)).replace(tzinfo=UTC)
    else:
        raise InputError("Source instant or source offset required")
    if abs(offset) >= 86400:
        raise InputError("Invalid inferred offset between supplied labels")
    try:
        lat = float(row.get("latitude", row.get("lat")))
        lon = float(row.get("longitude", row.get("lon")))
    except (TypeError, ValueError) as exc:
        raise InputError("Explicit birth latitude and longitude required") from exc
    if not math.isfinite(lat) or not -90 < lat < 90:
        raise InputError("Latitude must be finite and strictly between the poles")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise InputError("Invalid longitude")
    if not isinstance(shift_minutes, (int, float)) or not math.isfinite(shift_minutes):
        raise InputError("Invalid clock perturbation")
    delta = timedelta(minutes=shift_minutes)
    civil += delta
    absolute += delta
    return {
        "study_id": str(row.get("study_id", "")),
        "birth_local": civil.isoformat(), "birth_utc": absolute.isoformat(),
        "jd_ut": julian_day(absolute), "latitude": lat, "longitude": lon,
        "source_offset_seconds": offset, "shift_minutes": shift_minutes,
        "time_scale": "nominal UT; UTC label treated as UT1, no inferred DUT1",
    }


@lru_cache(maxsize=150000)
def position(jd_ut, body):
    values, returned = swe.calc_ut(float(jd_ut), BODY_IDS[body], FLAGS)
    # Nodes/apogee are analytical lunar points and can omit an ephemeris flag.
    if body in TEN and not (returned & swe.FLG_MOSEPH):
        raise RuntimeError("Unexpected ephemeris backend; never accept silent fallback")
    return {"longitude": values[0] % 360, "latitude": values[1],
            "distance_au": values[2], "speed_longitude": values[3],
            "retrograde": values[3] < 0, "returned_flags": returned}


def sky(jd_ut, bodies=TEN):
    # Copy each cached result so downstream annotations cannot contaminate cache.
    return {body: dict(position(float(jd_ut), body)) for body in bodies}


def obliquity(jd_ut):
    # ECL_NUT[0] = true obliquity, [1] = mean obliquity.
    return swe.calc_ut(jd_ut, swe.ECL_NUT, FLAGS)[0][0]


def houses(jd_ut, latitude, longitude):
    if not -90 < latitude < 90:
        raise InputError("House angles undefined at a geographic pole")
    cusps, axes = swe.houses_ex(jd_ut, latitude, longitude, b"W", 0)
    return {"system": "whole-sign", "cusps": list(cusps),
            "Ascendant": axes[0], "Midheaven": axes[1], "ARMC": axes[2],
            "Vertex": axes[3]}


def house_number(longitude, ascendant):
    return (int(longitude % 360 // 30) - int(ascendant % 360 // 30)) % 12 + 1


def sun_above_horizon(jd_ut, latitude, longitude):
    p = position(jd_ut, "Sun")
    _, true_alt, _ = swe.azalt(jd_ut, swe.ECL2HOR, (longitude, latitude, 0),
                             0, 0, (p["longitude"], p["latitude"], p["distance_au"]))
    return {"day_chart": true_alt >= 0, "geometric_solar_altitude_deg": true_alt}


def annual_instants(year):
    if not isinstance(year, int) or not 1880 <= year <= 2100:
        raise InputError("Annual year outside supported reference range")
    return tuple(julian_day(datetime(year, month, 15, 12, tzinfo=UTC)) for month in range(1, 13))


@lru_cache(maxsize=221)
def annual_sky(year):
    return tuple(sky(jd, TEN + ("TrueNode", "MeanApogee")) for jd in annual_instants(year))


def age_years(jd_birth, jd_target):
    return (jd_target - jd_birth) / TROPICAL_YEAR_DAYS


def metadata():
    return {"version": VERSION, "swiss_ephemeris_version": swe.version,
            "pyswisseph_pin": "2.10.3.2", "backend": "Moshier, explicitly requested",
            "requested_flags": FLAGS, "frame": "geocentric apparent tropical ecliptic-of-date",
            "calendar": "proleptic Gregorian", "leap_seconds": "nominal UT approximation",
            "months": "15th, 12:00 UT, January–December; arithmetic mean"}
