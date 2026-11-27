"""Bounded source-clause conformance in Ziping Zhenquan's officer chapter."""
from itertools import pairwise

from lunar_python.util import LunarUtil
from open_birth_chart import bazi_engine as bazi

POSITIONS = ("year", "month", "day", "hour")
WEALTH = {"正财", "偏财"}
RESOURCE = {"正印", "偏印"}
PEER = {"比肩", "劫财"}


def read_pillars(pillars):
    if len(pillars) != 4 or any(pillar not in bazi.JIAZI for pillar in pillars):
        raise ValueError("Four sexagenary pillars in year–month–day–hour order are required")
    year, month, day, hour = pillars
    month_from_tiger = (bazi.ZHI.index(month[1]) - 2) % 12
    month_stem = (2 * (bazi.GAN.index(year[0]) % 5 + 1) + month_from_tiger) % 10
    hour_stem = (2 * (bazi.GAN.index(day[0]) % 5) + bazi.ZHI.index(hour[1])) % 10
    if month[0] != bazi.GAN[month_stem] or hour[0] != bazi.GAN[hour_stem]:
        raise ValueError("The stem of the month or hour disagrees with the stated year/day")
    return dict(zip(POSITIONS, pillars, strict=True))


def officer_premises(pillars):
    """Return the source's limited structural candidates and their position evidence."""
    natal = read_pillars(pillars)
    day_stem = natal["day"][0]
    month = natal["month"][1]
    stem_roles = {stem: LunarUtil.SHI_SHEN[day_stem + stem] for stem in bazi.GAN}
    visible = {position: value[0] for position, value in natal.items() if position != "day"}
    visible_roles = {position: stem_roles[stem] for position, stem in visible.items()}
    month_hidden = LunarUtil.ZHI_HIDE_GAN[month]
    officers = [stem for stem in month_hidden if stem_roles[stem] == "正官"]
    officer_context = any(stem == month_hidden[0] or stem in visible.values() for stem in officers)
    wealth = {position for position, role in visible_roles.items() if role in WEALTH}
    resource = {position for position, role in visible_roles.items() if role in RESOURCE}
    wealth_and_resource = wealth | resource
    adjacent_pairs = [
        frozenset((left, right)) for left, right in pairwise(POSITIONS)
        if left in visible and right in visible and bazi.stem_combines(visible[left], visible[right])
    ]
    pairs_with_wealth_and_resource = [
        pair for pair in adjacent_pairs if pair & wealth and pair & resource
    ]
    pairs_with_peer_and_killing = [
        pair for pair in adjacent_pairs
        if {visible_roles[position] for position in pair} & PEER
        and "七杀" in {visible_roles[position] for position in pair}
    ]
    branches = {value[1] for value in natal.values()}
    full_wood_in_month = month in "亥卯未" and set("亥卯未") <= branches
    wood_resource_visible = any(bazi.element(visible[pos]) == "木" for pos in resource)
    two_metal_resources = sum(bazi.element(visible[pos]) == "金" for pos in resource) == 2
    separate_finance_resource_pair = len(wealth) == len(resource) == 1
    remaining_fire_resource = any(
        bazi.element(visible[pos]) == "火" for pair in pairs_with_wealth_and_resource
        for pos in resource - pair
    )
    candidates = {
        "财印隔位": separate_finance_resource_pair and wealth_and_resource == {"month", "hour"},
        "财印相合": separate_finance_resource_pair and bool(pairs_with_wealth_and_resource),
        "化官为印的前提": full_wood_in_month and wood_resource_visible and bool(wealth),
        "木伤官与双金印": full_wood_in_month and stem_roles["乙"] == "伤官" and two_metal_resources,
        "比劫合杀候选": "正官" not in visible_roles.values() and bool(pairs_with_peer_and_killing),
        "巳丑伤官与财印分工": set("巳丑") <= branches and stem_roles["庚"] == "伤官"
        and remaining_fire_resource,
    }
    return {
        "monthly_officer_stems": officers,
        "officer_context": officer_context,
        "visible_roles": visible_roles,
        "adjacent_nonday_stem_pairs": [sorted(pair) for pair in adjacent_pairs],
        "source_conditions": [name for name, matches in candidates.items() if officer_context and matches],
        "unique_yongshen": None,
        "transformation_effectiveness": None,
    }
