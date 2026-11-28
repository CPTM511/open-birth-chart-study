"""Recheck the Nanyang folios against the frozen R8 Ziwei chart and clauses."""

from __future__ import annotations

import argparse
from pathlib import Path

from lunar_python import Lunar

from open_birth_chart.ziwei_engine import ZiweiEngine
from rounds.r23.classical import BRANCHES, CYCLE, STEMS, calculate
from rounds.r27.archive_source import ROOT, digest, read_json, require, write_json


HERE = Path(__file__).resolve().parent
RESCUE = ("紫微", "天相", "禄存")
LU_POSITIONS = dict(zip(STEMS, "寅卯巳午巳午申酉亥子", strict=True))
MINOR_STARTS = {branch: start for members, start in (("寅午戌", "辰"), ("申子辰", "戌"),
               ("巳酉丑", "未"), ("亥卯未", "丑")) for branch in members}
THREE_HARMONIES = ("申子辰", "巳酉丑", "寅午戌", "亥卯未")
OPPOSITIONS = ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥")
SAME, TRINE, OPPOSITE, OUTSIDE = "same_palace", "trine_wing", "opposition", "outside"


def shift(branch, number):
    return BRANCHES[(BRANCHES.index(branch) + number) % 12]


def relationship(anchor, position):
    offset = (BRANCHES.index(position) - BRANCHES.index(anchor)) % 12
    return {0: SAME, 4: TRINE, 6: OPPOSITE, 8: TRINE}.get(offset, OUTSIDE)


def check_geometry():
    for anchor in BRANCHES:
        group = next(set(g) for g in THREE_HARMONIES if anchor in g)
        opposite = next(set(g) - {anchor} for g in OPPOSITIONS if anchor in g)
        for position in BRANCHES:
            relation = relationship(anchor, position)
            require((relation == SAME) == (position == anchor)
                    and (relation == TRINE) == (position in group - {anchor})
                    and (relation == OPPOSITE) == (position in opposite),
                    "Modular geometry differs from the fixed branch groups")
    return 12 * 12


def flow_stars(stem):
    lu = LU_POSITIONS[stem]
    return {"流禄": lu, "流羊": shift(lu, 1), "流陀": shift(lu, -1)}


def duplicates(life, natal, annual):
    return {
        yearly: annual[yearly] for native, yearly in (("擎羊", "流羊"), ("陀罗", "流陀"))
        if natal[native] == annual[yearly] and relationship(life, annual[yearly]) != OUTSIDE
    }


def rescue_context(anchor, natal):
    kinds = {star: relationship(anchor, natal[star]) for star in RESCUE}
    variants = {
        "trine_wings_only": {TRINE},
        "same_or_trine_wings": {SAME, TRINE},
        "same_trine_wings_or_opposition": {SAME, TRINE, OPPOSITE},
    }
    return {"relationships": kinds, "rules": {
        variant: {"stars": [star for star, kind in kinds.items() if kind in allowed],
                  "any": any(kind in allowed for kind in kinds.values()),
                  "all_three": all(kind in allowed for kind in kinds.values())}
        for variant, allowed in variants.items()
    }}


def qisha_context(life, natal, flowing):
    qisha = natal["七杀"]
    triggers = {}
    for name, excluded in (("same_or_trine_wings", {OPPOSITE, OUTSIDE}),
                           ("same_trine_wings_or_opposition", {OUTSIDE})):
        contains_qisha = relationship(life, qisha) not in excluded
        yang_tuo = [star for star in ("流羊", "流陀") if relationship(life, flowing[star]) not in excluded]
        triggers[name] = {"natal_qisha": contains_qisha, "transit_stars": yang_tuo,
                          "with_any": contains_qisha and bool(yang_tuo),
                          "with_both": contains_qisha and len(yang_tuo) == 2}
    return {"qisha_relative_to_life": relationship(life, qisha), "triggers": triggers,
            "rescue_relative_to_life": rescue_context(life, natal),
            "rescue_relative_to_qisha": rescue_context(qisha, natal)}


def year_placement(birth_gz, age):
    return CYCLE[(CYCLE.index(birth_gz) + age - 1) % len(CYCLE)]


def natal_and_periods(example):
    birth, annual = example["birth"], example["annual"]
    chart = calculate(birth)
    require((chart["life"], chart["bureau"]) == (example["life"], example["bureau"]),
            "R23 life or bureau does not match the printed plate")
    year = birth["ganzhi"]
    life = chart["life"]
    natal = {star: chart["stars"][star][0] for star in ("七杀", "紫微", "天相")}
    lu = LU_POSITIONS[year[0]]
    forward = (STEMS.index(year[0]) % 2 == 0) == (example["sex"] == "M")
    direction = 1 if forward else -1
    natal.update({"禄存": lu, "擎羊": shift(lu, 1), "陀罗": shift(lu, -1), "飞廉": shift(lu, direction * 6)})
    require(natal == example["natal"], "A reconstructed star differs from the printed plate")
    age = annual["nominal_age"]
    year_gz = year_placement(year, age)
    dasha_from_life = shift(life, direction * ((age - chart["bureau"]) // 10))
    # The Nanyang major-period rule describes the adjacent parent/sibling palace as the start.
    dasha_from_adjacent = shift(dasha_from_life, direction)
    minor = shift(MINOR_STARTS[year[1]], (age - 1) * (1 if example["sex"] == "M" else -1))
    flow = flow_stars(year_gz[0])
    require((dasha_from_adjacent, minor, year_gz, year_gz[1], flow["流羊"], flow["流陀"])
            == tuple(annual[key] for key in ("decadal_branch", "minor_branch", "year_gz", "taisui_branch",
                                             "yearly_yang", "yearly_tuo")), "Cycle positions differ from the plate")
    return {"life": life, "bureau": chart["bureau"], "natal": natal, "nominal_age": age,
            "same_life_start_decadal_branch": dasha_from_life,
            "printed_adjacent_start_decadal_branch": dasha_from_adjacent,
            "minor_branch": minor, "taisui_year_gz": year_gz, "flow": flow,
            "decadal_and_taisui_relation": relationship(dasha_from_adjacent, year_gz[1]),
            **qisha_context(life, natal, flow)}


def solar_clock(year, month, day, branch):
    lunar = Lunar.fromYmd(year, month, day)
    solar = lunar.getSolar()
    require(solar.getLunar().getYear() == year and solar.getLunar().getMonth() == month
            and solar.getLunar().getDay() == day, "Synthetic solar carrier did not round trip")
    hour = BRANCHES.index(branch) * 2
    return f"{solar.toYmd()}T{hour:02d}:30:00"


def placed(star_map, name):
    require(len(star_map[name]) == 1, f"Expected a unique placement of {name}")
    return star_map[name][0]


def replay_modern(engine, birth_clock, sex, years):
    row = {"study_id": "synthetic_calendar_carrier", "birth_local": birth_clock, "sex": sex, "calendar": "gregorian"}
    result = engine.compute(row, years, include_chart=True, detailed=True)
    require(result["status"] == "computed_for_registered_conventions", "Frozen Ziwei chart failed")
    chart = result["chart"]
    life = chart["soul_branch"]
    branches = {palace["index"]: palace["earthly_branch"] for palace in chart["palaces"]}
    by_name = {}
    for palace in chart["palaces"]:
        for star in palace["major_stars"] + palace["minor_stars"] + palace["adjective_stars"]:
            by_name.setdefault(star["name"], []).append(palace["earthly_branch"])
    native_names = ("七杀", "紫微", "天相", "禄存", "擎羊", "陀罗")
    native = {name: placed(by_name, name) for name in native_names}
    fly = [palace["earthly_branch"] for palace in chart["palaces"] if palace["boshi12"] in ("飞廉", "蜚廉")]
    require(len(fly) == 1, "The frozen natal chart has an unexpected 博士 sequence")
    native["飞廉"] = fly[0]
    qisha_palace = next(palace for palace in chart["palaces"] if palace["earthly_branch"] == native["七杀"])
    brightness = next(star.get("brightness") for star in qisha_palace["major_stars"] if star["name"] == "七杀")
    yearly_details = []
    for snapshot in result["annual"]:
        require(snapshot["status"] == "computed_for_registered_conventions", "Frozen Ziwei snapshot failed")
        yearly = snapshot["yearly"]
        generated = flow_stars(yearly["heavenly_stem"])
        found = {star["name"]: branches[index] for index, entries in enumerate(yearly["all_transit_stars"])
                 for star in entries if star["name"] in generated}
        require(found == generated, "R8 transit placements differ from the documented stem sequence")
        period_age = snapshot["other_cycles"]["age"]
        rules = {clause["rule"]: clause for clause in snapshot["interpretive_clauses"]["clauses"]}
        q, d = rules["ZWC03"], rules["ZWC04"]
        context = qisha_context(life, native, found)
        around = context["triggers"]["same_trine_wings_or_opposition"]
        rescue = {item["star"]: branches[item["palace"]] for item in q["rescue_context"]}
        expected_rescue = context["rescue_relative_to_qisha"]["rules"]["same_trine_wings_or_opposition"]["stars"]
        matches = {item["yearly"]: branches[item["palace"]] for item in d["duplicate_locations"]}
        require(q["structural_match"] == around["with_any"]
                and q["qisha_brightness"] == (brightness if around["natal_qisha"] else None)
                and q["temple_mitigation"] == (around["natal_qisha"] and brightness in ("庙", "旺"))
                and rescue == ({name: native[name] for name in expected_rescue} if around["natal_qisha"] else {}),
                "Reconstructed R8 ZWC03 differs from the reported clause")
        require(matches == duplicates(life, native, found) and d["structural_match"] == bool(matches),
                "Reconstructed R8 ZWC04 differs from the reported clause")
        yearly_details.append({
            "year": snapshot["year"], "nominal_age": period_age["nominalAge"],
            "decadal_branch": snapshot["decadal"]["earthly_branch"], "minor_branch": branches[period_age["index"]],
            "taisui_year_gz": yearly["heavenly_stem"] + yearly["earthly_branch"], "flow": found,
            "ZWC03_match": q["structural_match"], "ZWC03_rescue": rescue, "ZWC04_duplicates": matches,
            "strict_temple": brightness == "庙" if brightness else None,
            "R8_temple_or_prosperous": q["temple_mitigation"], "qisha_brightness": brightness,
            "contexts": context,
        })
    return {"synthetic_birth_clock": birth_clock, "life": life, "bureau_name": chart["five_elements_class"],
            "natal": native, "snapshots": yearly_details}


def audit():
    read = read_json(HERE / "transcription.json")
    same, kong = read["same_stem_example"], read["kong_example"]
    life = same["life"]
    same_stem_flow = flow_stars(same["yearly_stem"])
    require((shift(life, 6), same_stem_flow["流羊"], same_stem_flow["流禄"], same_stem_flow["流陀"])
            == tuple(same[k] for k in ("migration", "yearly_yang", "yearly_lu", "yearly_tuo")),
            "The same-stem example differs from its printed placements")
    kong_classical = natal_and_periods(kong)
    with ZiweiEngine() as engine:
        same_modern = replay_modern(engine, solar_clock(2000, 2, 15, "子"), "M", [2020, 2021])
        require(same_modern["life"] == life
                and same_modern["natal"]["擎羊"] == same["natal_yang_explicit"]
                and same_modern["snapshots"][0]["flow"] == same_stem_flow
                and same_modern["snapshots"][0]["ZWC04_duplicates"] == {"流羊": "酉", "流陀": "未"}
                and not same_modern["snapshots"][1]["ZWC04_duplicates"], "The same-stem control does not separate")
        birth, age = kong["birth"], kong["annual"]["nominal_age"]
        offset = CYCLE.index(birth["ganzhi"])
        modern = []
        for start in (1924, 1984):
            year = start + offset
            month = -birth["lunar_month"] if birth["is_leap"] else birth["lunar_month"]
            clock = solar_clock(year, month, birth["lunar_day"], birth["hour_branch"])
            carrier = replay_modern(engine, clock, kong["sex"], [year + age - 1])
            require(carrier["life"] == kong["life"] and carrier["bureau_name"] == "水二局"
                    and carrier["natal"] == kong["natal"], "An R8 calendar carrier differs from the printed natal anchors")
            snapshot = carrier["snapshots"][0]
            require(snapshot["nominal_age"] == age and snapshot["taisui_year_gz"] == kong_classical["taisui_year_gz"]
                    and snapshot["minor_branch"] == kong_classical["minor_branch"]
                    and snapshot["decadal_branch"] == kong_classical["same_life_start_decadal_branch"],
                    "The modern period calculation differs from the independent expectation")
            modern.append(carrier)
    first, second = [item["snapshots"][0] for item in modern]
    require({k: v for k, v in first.items() if k != "year"} == {k: v for k, v in second.items() if k != "year"},
            "The same-cycle carriers disagree")
    receipts = [HERE / name for name in ("REGISTRATION.zh.md", "sources.json", "transcription.json")]
    receipts.extend((ROOT / "rounds/r23/classical.py", ROOT / "src/open_birth_chart/ziwei_bridge.cjs",
                     ROOT / "package-lock.json"))
    return {
        "round": "R44", "verified_branch_pairs": check_geometry(),
        "inputs_sha256": {str(path.relative_to(ROOT)): digest(path) for path in receipts},
        "same_stem_example": {"classical_flow": same_stem_flow, "modern_control": same_modern},
        "kong_example": {"classical": kong_classical, "modern_carriers": modern},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    write_json(parser.parse_args().output, audit())
