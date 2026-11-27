"""R16 source-linked premises. Callable alongside, and independent of, the R8 scores."""
from itertools import combinations
from math import isfinite

from open_birth_chart import bazi_engine as bazi, qizheng_engine as qizheng, western_engine as western

POSITIONS = ("year", "month", "day", "hour")
ZIWEI_STEMS = "甲乙丙丁戊己庚辛壬癸"
ZIWEI_TRANSFORMS = ("禄", "权", "科", "忌")
# Ziwei Doushu Quanshu, volume 2, entry "安禄权科忌四星变化诀".
ZIWEI_TEXT_ROWS = (
    ("廉贞", "破军", "武曲", "太阳"),
    ("天机", "天梁", "紫微", "太阴"),
    ("天同", "天机", "文昌", "廉贞"),
    ("太阴", "天同", "天机", "巨门"),
    ("贪狼", "太阴", "右弼", "天机"),
    ("武曲", "贪狼", "天梁", "文曲"),
    ("太阳", "武曲", "太阴", "天同"),
    ("巨门", "太阳", "文曲", "文昌"),
    ("天梁", "紫微", "天府", "武曲"),
    ("破军", "巨门", "太阴", "贪狼"),
)
EXALTATIONS = {"Sun": 0, "Moon": 1, "Mercury": 5, "Venus": 11, "Mars": 9, "Jupiter": 3, "Saturn": 6}


def bazi_pairing(stems, month_branch=None):
    """Classify exposed pairs before transformation, using the stated positions."""
    if len(stems) != 4 or any(len(x) != 1 or x not in bazi.GAN for x in stems):
        raise ValueError("Exactly four recognized stems in year–month–day–hour order are required")
    if month_branch is not None and (len(month_branch) != 1 or month_branch not in bazi.ZHI):
        raise ValueError("Unknown month branch")
    pairs = []
    for left, right in combinations(range(4), 2):
        a, b = stems[left], stems[right]
        if not bazi.stem_combines(a, b):
            continue
        blockers = [POSITIONS[i] for i in range(left + 1, right)
                    if bazi.control(stems[i], a) or bazi.control(stems[i], b)]
        if blockers:
            status = "intervening_control"
        elif right - left == 3:
            status = "remote_partial"
        elif right - left == 2:
            status = "nonadjacent_unresolved"
        elif 2 in (left, right):
            status = "day_master_own_pair"
        else:
            status = "adjacent_other_stems"
        pairs.append({"positions": [POSITIONS[left], POSITIONS[right]], "stems": [a, b],
                      "status": status, "intervening_controls": blockers})
    viable = [p for p in pairs if p["status"] in {
        "adjacent_other_stems", "day_master_own_pair", "nonadjacent_unresolved"}]
    competition = [pos for pos in POSITIONS if sum(pos in p["positions"] for p in viable) > 1]

    # Bounded instances of the passages, with no inferred effective transformation.
    source_matches = []
    if month_branch in ("寅", "卯") and tuple(stems) == ("丙", "辛", "甲", "辛"):
        source_matches.append({"premise": "combine_one_visible_officer_retain_the_other",
                               "paired_officer": "month", "retained_officer": "hour"})
    if tuple(stems[:3]) == ("庚", "乙", "乙") and stems[3] not in ("乙", "庚"):
        source_matches.append({"premise": "year_officer_combines_with_another_yi_before_day",
                               "paired_officer": "year", "eclipsed_day_pair": ["year", "day"]})
    return {"pairs": pairs, "competition_positions": competition, "source_case_matches": source_matches,
            "effective_transformation": None, "net_pattern": None}


def ziwei_text_transformations(stem):
    if len(stem) != 1 or stem not in ZIWEI_STEMS:
        raise ValueError("One of the ten recognized natal stems is required")
    return dict(zip(ZIWEI_TRANSFORMS, ZIWEI_TEXT_ROWS[ZIWEI_STEMS.index(stem)], strict=True))


def western_premises(natal):
    """Tetrabiblos I.7/19 using the tropical chart's geometric solar altitude."""
    if natal.get("version") != western.VERSION:
        raise ValueError("Expected the named tropical chart version")
    altitude = natal["sect"]["geometric_solar_altitude_deg"]
    if not isfinite(altitude) or not -90 <= altitude <= 90:
        raise ValueError("Solar altitude must be finite and between the poles")
    sect = "day" if altitude > .25 else "night" if altitude < -.25 else None
    dignities = {}
    for name, sign in EXALTATIONS.items():
        longitude = natal["planets"][name]["longitude"]
        if not isfinite(longitude) or not 0 <= longitude < 360:
            raise ValueError("Expected a normalized tropical longitude")
        number = int(longitude // 30)
        dignities[name] = {"exaltation": number == sign, "fall": number == (sign + 6) % 12,
                           "domicile": number in western.DOMICILES[name],
                           "detriment": (number + 6) % 12 in western.DOMICILES[name]}
    return {"sect": sect, "solar_geometric_altitude_deg": altitude, "horizon_uncertainty_band_deg": .25,
            "malefic_moderation_by_sect_only": {
                "Mars": sect == "night" if sect else None,
                "Saturn": sect == "day" if sect else None,
            },
            "mercury_sect": None, "essential_dignities_by_sign": dignities}


def qizheng_adjust_first_limit(natal, elapsed_years, first_limit_ordinal_age=None):
    """Propagate an externally sourced first limit ordinal age (11–20) to later intervals."""
    if natal.get("version") != qizheng.VERSION:
        raise ValueError("Expected the named Qizheng chart version")
    if not isfinite(elapsed_years) or elapsed_years < 0:
        raise ValueError("Expected nonnegative elapsed tropical years")
    if first_limit_ordinal_age is None:
        return {"status": "unknown_first_limit_age", "period": None}
    if type(first_limit_ordinal_age) is not int or not 11 <= first_limit_ordinal_age <= 20:
        raise ValueError("The declared text permits ordinal ages 11–20")
    durations = (first_limit_ordinal_age - 1, *qizheng.MAJOR_YEARS[1:])
    age_start = 0
    for i, duration in enumerate(durations):
        age_end = age_start + duration
        if age_start <= elapsed_years < age_end:
            branch = (natal["ming"]["branch_index"] + i) % 12
            return {"status": "computed_for_supplied_first_limit", "period": qizheng.MAJOR_NAMES[i],
                    "branch": qizheng.BRANCHES[branch], "start_elapsed_year": age_start,
                    "end_elapsed_year_exclusive": age_end}
        age_start = age_end
    return {"status": "outside_this_cycle", "period": None}
