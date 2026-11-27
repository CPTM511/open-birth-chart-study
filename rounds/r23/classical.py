"""Natal Ziwei arithmetic for R23's Nanyang exemplars, independent of Iztro."""
from __future__ import annotations

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
CYCLE = tuple(STEMS[i % 10] + BRANCHES[i % 12] for i in range(60))
NAYIN = "金火木土金火水土金木水土火木水金火木土金火水土金木水土火木水"
BUREAUS = {"水": 2, "木": 3, "金": 4, "土": 5, "火": 6}
ZIWEI_STEPS = {"紫微": 0, "天机": -1, "太阳": -3, "武曲": -4, "天同": -5, "廉贞": -8}
TIANFU_STEPS = {"天府": 0, "太阴": 1, "贪狼": 2, "巨门": 3, "天相": 4, "天梁": 5, "七杀": 6, "破军": 10}
STARS = (*ZIWEI_STEPS, *TIANFU_STEPS)


def star_palaces(ziwei: str) -> dict[str, list[str]]:
    origin = BRANCHES.index(ziwei)
    tianfu = (2 * BRANCHES.index("寅") - origin) % 12
    return {
        **{s: [BRANCHES[(origin + step) % 12]] for s, step in ZIWEI_STEPS.items()},
        **{s: [BRANCHES[(tianfu + step) % 12]] for s, step in TIANFU_STEPS.items()},
    }


def ziwei_branch(bureau: int, day: int) -> str:
    if type(bureau) is not int or bureau not in BUREAUS.values() or type(day) is not int or not 1 <= day <= 30:
        raise ValueError("A five-element bureau and a lunar day from 1 to 30 are required")
    quotient = (day + bureau - 1) // bureau
    padding = bureau * quotient - day
    adjustment = -padding if padding % 2 else padding
    return BRANCHES[(BRANCHES.index("寅") + quotient - 1 + adjustment) % 12]


def calculate(birth: dict) -> dict:
    year, month, day, hour, leap = (
        birth[k] for k in ("ganzhi", "lunar_month", "lunar_day", "hour_branch", "is_leap")
    )
    if year not in CYCLE or type(month) is not int or not 1 <= month <= 12 or hour not in tuple(BRANCHES):
        raise ValueError("A sexagenary year, lunar month and single traditional hour branch are required")
    if type(leap) is not bool:
        raise ValueError("An explicit leap-month flag is required")
    year_stem = STEMS.index(year[0])
    month_position = BRANCHES.index("寅") + month - 1 + int(leap)
    hour_position = BRANCHES.index(hour)
    life = BRANCHES[(month_position - hour_position) % 12]
    body = BRANCHES[(month_position + hour_position) % 12]
    tiger_stem = STEMS.index("丙戊庚壬甲"[year_stem % 5])
    stems_from_tiger = (BRANCHES.index(life) - BRANCHES.index("寅")) % 12
    life_stem = STEMS[(tiger_stem + stems_from_tiger) % 10]
    life_pair = life_stem + life
    bureau = BUREAUS[NAYIN[CYCLE.index(life_pair) // 2]]
    return {"life": life, "body": body, "bureau": bureau, "life_pair": life_pair,
            "stars": star_palaces(ziwei_branch(bureau, day))}
