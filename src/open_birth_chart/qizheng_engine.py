# SPDX-License-Identifier: AGPL-3.0-or-later
"""Qing-table-informed Qizheng reference workflow, versioned and outcome-free.

Seven physical luminaries use modern astronomy. Four additional points are
explicitly specified: Qing-named true nodes, modern mean lunar apogee (an
approximation to historical Yuebo), and a primary-source uniform Zi Qi.
28 unequal mansions use Huangchao Tongzhi 1744 table plus its 51 arcsec/year
rule. A selected ancient fixed-period Dongwei rule is implemented, not every
historical interpretive school. No score is a death prediction.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from statistics import fmean as mean
import math
import swisseph as swe
from . import astronomy as astro

VERSION = "OBS-R8-QZ-1.0"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
MANSION_NAMES = "角亢氐房心尾箕斗牛女虚危室壁奎娄胃昴毕觜参井鬼柳星张翼轸"
# Factual transcription, Huangchao Tongzhi vol.19, Qianlong 9 jiazi (1744).
# (branch palace, degree, arcminute); no fitted or equal-width substitutions.
MANSION_TABLE = (
    (4,20,16),(3,0,56),(3,11,32),(3,29,22),(2,4,14),(2,10,29),(2,27,41),
    (1,6,36),(0,0,29),(0,8,9),(0,19,49),(0,29,47),(11,19,54),(10,5,35),
    (10,18,51),(9,0,23),(9,13,21),(9,25,50),(8,4,53),(8,20,7),(8,21,7),
    (7,1,43),(6,2,10),(6,6,44),(6,23,43),(5,2,9),(5,20,21),(4,7,11),
)
MANSION_RULERS = ("Jupiter", "Venus", "Saturn", "Sun", "Moon", "Mars", "Mercury") * 4
PALACE_RULERS = ("Saturn", "Saturn", "Jupiter", "Mars", "Venus", "Mercury",
                 "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter")
PALACE_NAMES = ("命", "财帛", "兄弟", "田宅", "男女", "奴仆", "妻妾", "疾厄", "迁移", "官禄", "福德", "相貌")
MAJOR_NAMES = ("命", "相貌", "福德", "官禄", "迁移", "疾厄", "妻妾", "奴仆", "男女", "田宅", "兄弟", "财帛")
MAJOR_YEARS = (15.0,10.0,11.0,15.0,8.0,7.0,11.0,4.5,4.5,4.5,5.0,5.0)
ADVERSE = ("Mars", "Saturn", "Luohou", "Jidu", "Yuebo")
SUPPORT = ("Venus", "Jupiter", "Ziqi")
ELEMENTS = ("wood", "fire", "earth", "metal", "water")
ELEMENT = {"Jupiter":"wood", "Ziqi":"wood", "Mars":"fire", "Luohou":"fire",
           "Saturn":"earth", "Jidu":"earth", "Venus":"metal", "Mercury":"water",
           "Yuebo":"water", "Sun":"fire", "Moon":"water"}
POINT_TO_LUMINARY = {"Ziqi":"Jupiter", "Luohou":"Mars", "Jidu":"Saturn", "Yuebo":"Mercury"}
ZIQI_RATE_ARCSEC_DAY = 126.720777
ZIQI_SOURCE_PHASE = 7*30 + 17 + 50/60 + 14/3600 + 53/216000
# Source numerical palace origin is winter-solstice 270 degrees, not Aries zero.
ZIQI_TROPICAL_PHASE = (270.0 + ZIQI_SOURCE_PHASE) % 360
BEIJING_REFERENCE_LONGITUDE = 116.4  # Explicit modern LMT convention, not an invented ancient exact longitude.
MANSION_EPOCH_JD = swe.julday(1744,1,1,0,swe.GREG_CAL)
MANSION_PRECESSION_ARCSEC_YEAR = 51.0


def palace(longitude):
    return (10 - int((longitude % 360) // 30)) % 12


def palace_start(branch):
    return ((10 - branch) % 12) * 30.0


@lru_cache(maxsize=1)
def ziqi_epoch():
    """Next Beijing local mean midnight after the December 1743 solstice."""
    winter = swe.solcross_ut(270, swe.julday(1743,12,10,0), swe.FLG_MOSEPH)
    local_midnight = math.floor(winter + .5 + BEIJING_REFERENCE_LONGITUDE/360) + .5
    epoch = local_midnight - BEIJING_REFERENCE_LONGITUDE/360
    return {"jd_ut": epoch, "solstice_jd_ut": winter,
            "local_date": "1743-12-23T00:00:00", "local_scale": "Beijing LMT at 116.4E",
            "source_epoch": "乾隆九年甲子天正冬至次日子正（癸亥年十一月冬至）",
            "source_phase_deg": ZIQI_SOURCE_PHASE, "tropical_phase_deg": ZIQI_TROPICAL_PHASE,
            "source_origin_deg": 270.0, "rate_arcsec_day": ZIQI_RATE_ARCSEC_DAY}


def ziqi_longitude(jd_ut):
    return (ZIQI_TROPICAL_PHASE + (jd_ut - ziqi_epoch()["jd_ut"]) * ZIQI_RATE_ARCSEC_DAY / 3600) % 360


@lru_cache(maxsize=50000)
def mansion_boundaries(jd_ut):
    # Source identifies an epoch year, not a precise instant. January 1 is a
    # declared numerical convention; its epoch ambiguity is <= 51 arcsec.
    advance = (jd_ut - MANSION_EPOCH_JD) / astro.TROPICAL_YEAR_DAYS * 51 / 3600
    return tuple((palace_start(b) + d + m/60 + advance) % 360 for b,d,m in MANSION_TABLE)


def mansion(longitude, jd_ut):
    starts = mansion_boundaries(float(jd_ut))
    # Full unequal coverage: circular distance forward from each start to body.
    i = min(range(28), key=lambda k: (longitude - starts[k]) % 360)
    width = (starts[(i+1) % 28] - starts[i]) % 360
    return {"index": i, "name": MANSION_NAMES[i], "ruler": MANSION_RULERS[i],
            "degree_in_mansion": (longitude - starts[i]) % 360,
            "mansion_width_deg": width, "start_longitude": starts[i]}


def _point(longitude, speed, source):
    return {"longitude": longitude % 360, "latitude": None, "distance_au": None,
            "speed_longitude": speed, "retrograde": speed < 0, "definition": source}


def qizheng_sky(jd_ut, apogee_variant="mean", underlying_sky=None):
    if apogee_variant not in ("mean", "osculating"):
        raise ValueError("Explicit mean or osculating apogee required")
    sky = underlying_sky if underlying_sky is not None else astro.sky(
        jd_ut, astro.SEVEN + ("TrueNode", "MeanApogee"))
    result = {body: dict(sky[body]) for body in astro.SEVEN}
    node = sky["TrueNode"]
    apogee = sky["MeanApogee"] if apogee_variant == "mean" else astro.position(jd_ut, "OsculatingApogee")
    result["Luohou"] = _point(node["longitude"]+180, node["speed_longitude"], "Qing descending true node")
    result["Jidu"] = _point(node["longitude"], node["speed_longitude"], "Qing ascending true node")
    result["Yuebo"] = _point(apogee["longitude"], apogee["speed_longitude"],
                             "modern " + apogee_variant + " lunar apogee; not identical to Qing highest-true-longitude")
    result["Ziqi"] = _point(ziqi_longitude(jd_ut), ZIQI_RATE_ARCSEC_DAY/3600,
                            "Qing primary-source uniform point; no physical celestial body")
    for name, p in result.items():
        branch = palace(p["longitude"])
        p.update(palace_branch_index=branch, palace_branch=BRANCHES[branch],
                 degree_in_palace=p["longitude"] % 30, palace_ruler=PALACE_RULERS[branch],
                 mansion=mansion(p["longitude"], jd_ut), element=ELEMENT[name])
        owner = POINT_TO_LUMINARY.get(name, name)
        p["in_own_palace"] = owner == PALACE_RULERS[branch]
        p["in_own_mansion"] = owner == p["mansion"]["ruler"]
    return result


def element_relation(actor, target):
    a, b = ELEMENTS.index(ELEMENT[actor]), ELEMENTS.index(ELEMENT[target])
    if a == b: return "same_element"
    if (a+1) % 5 == b: return "actor_generates_target"
    if (b+1) % 5 == a: return "target_generates_actor"
    if (a+2) % 5 == b: return "actor_controls_target"
    return "target_controls_actor"


def palace_contact(branch_a, branch_b):
    """Selected same/opposite/trine weights 10/7/4 from the cited primary text."""
    diff = (branch_a-branch_b) % 12
    return 1.0 if diff == 0 else .7 if diff == 6 else .4 if diff in (4,8) else 0.0


def build_natal(birth, shift_minutes=0, apogee_variant="mean"):
    b = astro.normalize_birth(birth, shift_minutes)
    planets = qizheng_sky(b["jd_ut"], apogee_variant)
    # Local mean solar time, not arbitrary modern civil timezone; no equation-of-time correction.
    local_solar_hours = ((b["jd_ut"] + .5) % 1 * 24 + b["longitude"] / 15) % 24
    hour_branch = int((local_solar_hours + 1) // 2) % 12
    ming = (planets["Sun"]["palace_branch_index"] + 3 - hour_branch) % 12
    ming_ruler = PALACE_RULERS[ming]
    shen = planets["Moon"]["palace_branch_index"]
    for p in planets.values():
        p["natal_palace_number"] = (ming-p["palace_branch_index"]) % 12 + 1
        p["natal_palace_name"] = PALACE_NAMES[p["natal_palace_number"]-1]
    return {
        "system": "Qizheng", "version": VERSION, "birth": b, "planets": planets,
        "ming": {"branch_index": ming, "branch": BRANCHES[ming], "palace_ruler": ming_ruler,
                 "method": "Sun palace placed on LMT birth-hour branch; Mao branch gives Ming",
                 "degree": None, "degree_reason": "discrete palace rule; no fabricated ascendant degree"},
        "shen": {"branch_index": shen, "branch": BRANCHES[shen],
                 "palace_ruler": PALACE_RULERS[shen], "mansion_ruler": planets["Moon"]["mansion"]["ruler"],
                 "method": "Moon as body; selected conventional branch"},
        "palaces": [{"number": i+1, "name": name, "branch_index": (ming-i) % 12,
                     "branch": BRANCHES[(ming-i) % 12], "ruler": PALACE_RULERS[(ming-i) % 12]}
                    for i,name in enumerate(PALACE_NAMES)],
        "relationships_to_ming_ruler": {name: element_relation(name, ming_ruler) for name in planets},
        "sect": astro.sun_above_horizon(b["jd_ut"], b["latitude"], b["longitude"]),
        "hour_branch_index": hour_branch, "local_mean_solar_hours": local_solar_hours,
        "ziqi_epoch": ziqi_epoch(), "apogee_variant": apogee_variant,
        "method": {"mansion_table": "Huangchao Tongzhi vol.19, 1744",
                   "precession": "51 arcsec/tropical year; numerical epoch 1744-01-01 00 UT",
                   "major_periods": "fixed ancient Dongwei verse, 100.5 years total; no degree-adjusted childhood limit",
                   "major_durations_years": MAJOR_YEARS,
                   "minor_periods": "one palace per completed Gregorian birthday, reverse branch order",
                   "ming_ruler": "palace ruler, not a reconstructed degree ruler",
                   "node_names": "Qing: Luohou descending; Jidu ascending"},
        "module_completeness": {"seven_luminaries": True, "four_explicit_points": True,
                                "twelve_palaces": True, "28_unequal_mansions": True,
                                "palace_and_mansion_degrees": True, "rulerships_and_elements": True,
                                "selected_major_and_minor_periods": True, "monthly_transits": True,
                                "historical_qing_lunar_algorithm": False, "degree_adjusted_major_limit": False,
                                "all_traditional_interpretations": False,
                                "empirically_validated_prediction": False},
        "astronomy": astro.metadata(),
    }


def major_period(natal, jd_target):
    age = astro.age_years(natal["birth"]["jd_ut"], jd_target)
    start = 0.0
    for i, length in enumerate(MAJOR_YEARS):
        end = start + length
        if start <= age < end:
            branch = (natal["ming"]["branch_index"]+i) % 12
            return {"name": MAJOR_NAMES[i], "index": i, "branch_index": branch,
                    "branch": BRANCHES[branch], "ruler": PALACE_RULERS[branch],
                    "start_age": start, "end_age": end, "age": age}
        start = end
    return None


def minor_period(natal, jd_target):
    year, month, day, hour = swe.revjul(jd_target, swe.GREG_CAL)
    target = datetime(year,month,day) + timedelta(hours=hour, seconds=natal["birth"]["source_offset_seconds"])
    birth = datetime.fromisoformat(natal["birth"]["birth_local"])
    # February 29 birthday is February 28 in a non-leap year, declared convention.
    try:
        anniversary = birth.replace(year=target.year)
    except ValueError:
        anniversary = birth.replace(year=target.year, day=28)
    age = target.year - birth.year - int(target < anniversary)
    if age < 0: return None
    branch = (natal["ming"]["branch_index"]-age) % 12
    return {"completed_birthdays": age, "branch_index": branch, "branch": BRANCHES[branch],
            "ruler": PALACE_RULERS[branch], "name": PALACE_NAMES[age % 12]}


def _group_contact(planets, names, branch):
    return mean(palace_contact(planets[n]["palace_branch_index"], branch) for n in names)


def _mansion_contact(planets, names, natal):
    # Fixed Sun, Moon and selected Ming-palace-ruler targets; duplicate rulers
    # retain their declared role weight and are not called independent evidence.
    focal = ("Sun", "Moon", natal["ming"]["palace_ruler"])
    return mean(float(planets[n]["mansion"]["index"] == natal["planets"][f]["mansion"]["index"])
                for n in names for f in focal)


@lru_cache(maxsize=442)
def _annual_qizheng_sky(year, apogee_variant):
    return tuple(qizheng_sky(jd, apogee_variant, sky) for jd, sky in
                 zip(astro.annual_instants(year), astro.annual_sky(year)))


def annual_signals(natal, year, include_details=False):
    if natal.get("version") != VERSION:
        raise ValueError("Natal version mismatch")
    channels = {key: [] for key in ("natal_major_contact", "natal_minor_contact",
                                    "transit_major_contact", "transit_minor_contact",
                                    "transit_mansion_contact")}
    supports, details = [], []
    for month, (jd, transits) in enumerate(zip(astro.annual_instants(year),
                                              _annual_qizheng_sky(year, natal["apogee_variant"])), 1):
        major, minor = major_period(natal,jd), minor_period(natal,jd)
        if major is None or minor is None:
            return {"system": "Qizheng", "version": VERSION, "year": year,
                    "primary_score": None, "components": {}, "status": "outside_selected_period_domain"}
        native = natal["planets"]
        vals = {
            "natal_major_contact": _group_contact(native, ADVERSE, major["branch_index"]),
            "natal_minor_contact": _group_contact(native, ADVERSE, minor["branch_index"]),
            "transit_major_contact": _group_contact(transits, ADVERSE, major["branch_index"]),
            "transit_minor_contact": _group_contact(transits, ADVERSE, minor["branch_index"]),
            "transit_mansion_contact": _mansion_contact(transits, ADVERSE, natal),
        }
        support = mean([
            _group_contact(native, SUPPORT, major["branch_index"]),
            _group_contact(native, SUPPORT, minor["branch_index"]),
            _group_contact(transits, SUPPORT, major["branch_index"]),
            _group_contact(transits, SUPPORT, minor["branch_index"]),
            _mansion_contact(transits, SUPPORT, natal),
        ])
        for k,v in vals.items(): channels[k].append(v)
        supports.append(support)
        if include_details:
            details.append({"month": month, "jd_ut": jd, "major_period": major,
                            "minor_period": minor, "components": vals,
                            "support": support, "eleven_transit_positions": transits})
    components = {k: mean(v) for k,v in channels.items()}
    output = {"system": "Qizheng", "version": VERSION, "year": year,
              "primary_score": mean(components.values()), "components": components,
              "support_score": mean(supports), "status": "ok", "monthly_snapshots": 12,
              "apogee_variant": natal["apogee_variant"],
              "interpretation": "registered structural contact index; no event/death probability"}
    if include_details: output["details"] = details
    return output
