# SPDX-License-Identifier: AGPL-3.0-or-later
"""Western reference workflow: tropical, whole sign, transits and secondary progressions.

The frozen primary is a geometric contact index. It has no event probability or
diagnostic meaning. Computing a selected workflow is not empirical validation of
astrology or completion of every Western interpretive tradition.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
from statistics import fmean as mean
import swisseph as swe
from . import astronomy as astro

VERSION = "OBS-R8-WEST-1.0"
SIGNS = ("Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces")
ASPECTS = {"conjunction": 0.0, "sextile": 60.0, "square": 90.0,
           "trine": 120.0, "opposition": 180.0}
NATAL_ORBS = {"conjunction": 6.0, "sextile": 4.0, "square": 6.0,
              "trine": 6.0, "opposition": 6.0}
TRANSIT_ACTORS = ("Mars", "Saturn", "Uranus", "Neptune", "Pluto")
PROGRESSED_ACTORS = ("Sun", "Moon", "Mercury", "Venus", "Mars")
TARGETS = ("Sun", "Moon", "Ascendant", "Midheaven")
HARD_ANGLES = (0.0, 90.0, 180.0)
SOFT_ANGLES = (0.0, 60.0, 120.0)
NAIBOD_DEG_PER_YEAR = 0.98564733
DOMICILES = {"Sun": (4,), "Moon": (3,), "Mercury": (2, 5),
             "Venus": (1, 6), "Mars": (0, 7), "Jupiter": (8, 11),
             "Saturn": (9, 10)}


def aspects(positions, other=None, orb=None):
    """Longitude aspects only; no declination parallels or inferred meanings."""
    pairs = combinations(positions, 2) if other is None else (
        (a, b) for a in positions for b in other)
    other = positions if other is None else other
    result = []
    for a, b in pairs:
        separation = astro.circular_distance(positions[a], other[b])
        for name, angle in ASPECTS.items():
            tolerance = NATAL_ORBS[name] if orb is None else orb
            distance = abs(separation - angle)
            if distance <= tolerance:
                result.append({"actor": a, "target": b, "aspect": name,
                               "orb_deg": distance})
    return result


def _annotate_planets(planets, ascendant):
    output = {}
    for name, p in planets.items():
        p = dict(p)
        sign = int(p["longitude"] // 30)
        p.update(sign_index=sign, sign=SIGNS[sign],
                 degree_in_sign=p["longitude"] % 30,
                 house=astro.house_number(p["longitude"], ascendant))
        if name in DOMICILES:
            p["domicile"] = sign in DOMICILES[name]
            p["detriment"] = (sign + 6) % 12 in DOMICILES[name]
        else:
            p["domicile"] = p["detriment"] = None
        output[name] = p
    return output


def build_natal(birth, shift_minutes=0):
    b = astro.normalize_birth(birth, shift_minutes)
    h = astro.houses(b["jd_ut"], b["latitude"], b["longitude"])
    planets = _annotate_planets(astro.sky(b["jd_ut"]), h["Ascendant"])
    angles = {name: h[name] for name in ("Ascendant", "Midheaven")}
    longitudes = {name: p["longitude"] for name, p in planets.items()}
    return {
        "system": "Western", "version": VERSION, "birth": b,
        "planets": planets, "houses": h, "angles": angles,
        "sect": astro.sun_above_horizon(b["jd_ut"], b["latitude"], b["longitude"]),
        "natal_aspects": aspects(longitudes | angles),
        "method": {"zodiac": "tropical", "houses": "whole sign",
                   "planets": list(astro.TEN), "aspect_orbs_deg": NATAL_ORBS,
                   "progression": "secondary day/year; Naibod in right ascension for axes",
                   "year_days": astro.TROPICAL_YEAR_DAYS,
                   "naibod_deg_per_year": NAIBOD_DEG_PER_YEAR},
        "module_completeness": {"ten_planets": True, "twelve_houses": True,
                                "major_aspects": True, "monthly_transits": True,
                                "secondary_progressions": True,
                                "naibod_progressed_axes": True,
                                "all_western_schools": False,
                                "empirically_validated_prediction": False},
        "astronomy": astro.metadata(),
    }


def progressed_chart(natal, jd_target, bodies=astro.TEN):
    """One ephemeris day per elapsed tropical year; explicit ARMC-based axes."""
    b = natal["birth"]
    age = astro.age_years(b["jd_ut"], jd_target)
    if age < 0:
        raise astro.InputError("Target precedes birth")
    progressed_jd = b["jd_ut"] + age
    armc = (natal["houses"]["ARMC"] + NAIBOD_DEG_PER_YEAR * age) % 360
    cusps, axes = swe.houses_armc(armc, b["latitude"],
                                astro.obliquity(progressed_jd), b"W")
    h = {"system": "whole-sign", "cusps": list(cusps),
         "Ascendant": axes[0], "Midheaven": axes[1], "ARMC": axes[2]}
    return {"age_years": age, "progressed_jd_ut": progressed_jd,
            "planets": _annotate_planets(astro.sky(progressed_jd, bodies), h["Ascendant"]),
            "houses": h, "angles": {"Ascendant": axes[0], "Midheaven": axes[1]}}


def contact_index(actors, targets, angles, orb):
    """Mean triangular contact, bounded 0..1; nearest allowed angle per pair."""
    if not actors or not targets or orb <= 0:
        raise ValueError("Nonempty actors/targets and positive orb required")
    return mean(max(0.0, 1.0 - min(abs(astro.circular_distance(a, b) - theta)
                                  for theta in angles) / orb)
                for a in actors.values() for b in targets.values())


def annual_signals(natal, year, include_details=False):
    if natal.get("version") != VERSION:
        raise ValueError("Natal version mismatch")
    birth_jd = natal["birth"]["jd_ut"]
    if astro.annual_instants(year)[0] < birth_jd:
        return {"system": "Western", "version": VERSION, "year": year,
                "primary_score": None, "components": {}, "status": "prebirth"}
    target = {name: (natal["planets"][name]["longitude"] if name in natal["planets"]
                     else natal["angles"][name]) for name in TARGETS}
    all_native = {name: p["longitude"] for name, p in natal["planets"].items()} | natal["angles"]
    channels = {key: [] for key in ("transit_hard", "progressed_planet_hard",
                                    "progressed_axis_hard", "transit_support")}
    transit_counts, progressed_counts = Counter(), Counter()
    details = []
    for month, (jd, transits) in enumerate(zip(astro.annual_instants(year), astro.annual_sky(year)), 1):
        progressed = progressed_chart(natal, jd, astro.TEN if include_details else PROGRESSED_ACTORS)
        tl = {name: p["longitude"] for name, p in transits.items() if name in astro.TEN}
        pl = {name: p["longitude"] for name, p in progressed["planets"].items()}
        vals = {
            "transit_hard": contact_index({n: tl[n] for n in TRANSIT_ACTORS}, target, HARD_ANGLES, 3.0),
            "progressed_planet_hard": contact_index({n: pl[n] for n in PROGRESSED_ACTORS}, target, HARD_ANGLES, 1.0),
            "progressed_axis_hard": contact_index(progressed["angles"], target, HARD_ANGLES, 1.0),
            "transit_support": contact_index({n: tl[n] for n in ("Venus", "Jupiter")}, target, SOFT_ANGLES, 3.0),
        }
        for k, v in vals.items():
            channels[k].append(v)
        if include_details:
            ta = aspects(tl, all_native, orb=3.0)
            pa = aspects(pl | progressed["angles"], all_native, orb=1.0)
            transit_counts.update(a["aspect"] for a in ta)
            progressed_counts.update(a["aspect"] for a in pa)
            details.append({"month": month, "jd_ut": jd, "components": vals,
                            "transit_planets": _annotate_planets(
                                {n: dict(transits[n]) for n in astro.TEN}, natal["angles"]["Ascendant"]),
                            "progressed_chart": progressed,
                            "transit_to_natal_aspects": ta,
                            "progressed_to_natal_aspects": pa})
    components = {key: mean(values) for key, values in channels.items()}
    secondary = mean([components["progressed_planet_hard"], components["progressed_axis_hard"]])
    score = mean([components["transit_hard"], secondary])
    output = {"system": "Western", "version": VERSION, "year": year,
              "primary_score": score, "components": components,
              "support_score": components["transit_support"], "status": "ok",
              "monthly_snapshots": 12,
              "transit_major_aspect_counts": dict(transit_counts) if include_details else None,
              "progressed_major_aspect_counts": dict(progressed_counts) if include_details else None,
              "full_aspect_details_computed": include_details,
              "interpretation": "registered geometric contact index; no event/death probability"}
    if include_details:
        output["details"] = details
    return output
