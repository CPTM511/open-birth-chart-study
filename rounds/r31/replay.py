"""Check the specified relationship paths and sexagenary constraints of R31."""

from __future__ import annotations

import argparse
from itertools import pairwise, product
from pathlib import Path

from lunar_python.util import LunarUtil
from open_birth_chart import bazi_engine as bazi

from rounds.r21.officer_cases import POSITIONS, read_pillars
from rounds.r27.archive_source import digest, read_json, require, write_json


HERE = Path(__file__).resolve().parent
VISIBLE_POSITIONS = ("year", "month", "hour")
MEETING_NAMES = {"木": "wood", "水": "water"}
FIVE_TIGER_START = dict(zip(bazi.GAN, "丙戊庚壬甲丙戊庚壬甲", strict=True))
FIVE_RAT_START = dict(zip(bazi.GAN, "甲丙戊庚壬甲丙戊庚壬", strict=True))
SOURCE_FILES = {"world_library": "world-library.pdf", "collected": "second-edition.pdf"}


def compatible(pillars, case):
    stems = {position: pillar[0] for position, pillar in zip(POSITIONS, pillars, strict=True)}
    visible = {stems[position] for position in VISIBLE_POSITIONS}
    return (
        set(case["visible"]) <= visible
        and all(stems[position] == stem for position, stem in case.get("fixed_visible_positions", {}).items())
        and set(case.get("required_branches", "")) <= {pillar[1] for pillar in pillars}
        and ("visible_element" not in case or any(bazi.element(stem) == case["visible_element"] for stem in visible))
    )


def derived_completions(case):
    if case["month"] not in bazi.ZHI:
        return set()
    month_index = "寅卯辰巳午未申酉戌亥子丑".index(case["month"])
    generated = set()
    for year in bazi.JIAZI:
        month_start = bazi.GAN.index(FIVE_TIGER_START[year[0]])
        month = bazi.GAN[(month_start + month_index) % 10] + case["month"]
        hour_start = bazi.GAN.index(FIVE_RAT_START[case["day"]])
        for day in (value for value in bazi.JIAZI if value[0] == case["day"]):
            for index, branch in enumerate(bazi.ZHI):
                hour = bazi.GAN[(hour_start + index) % 10] + branch
                pillars = (year, month, day, hour)
                if compatible(pillars, case):
                    generated.add(pillars)
    return generated


def enumerate_sexagenary(case):
    month_values = [value for value in bazi.JIAZI if value[1] == case["month"]]
    day_values = [value for value in bazi.JIAZI if value[0] == case["day"]]
    found = set()
    for pillars in product(bazi.JIAZI, month_values, day_values, bazi.JIAZI):
        if not compatible(pillars, case):
            continue
        try:
            read_pillars(pillars)
        except ValueError:
            continue
        found.add(pillars)
    return found


def ordered_controls(edges, binding=None):
    inactive = set()
    if binding is not None:
        require(bazi.stem_combines(*binding), "The stated stems do not form a five-combination pair")
        inactive.add(binding[1])
    states = []
    for source, target in edges:
        require(bazi.control(source, target), "The stated directed control fails")
        enabled = source not in inactive
        states.append(enabled)
        if enabled:
            inactive.add(target)
    return states


def generation(stems):
    return all((bazi.ELEMENTS.index(bazi.element(a)) + 1) % 5 == bazi.ELEMENTS.index(bazi.element(b))
               for a, b in pairwise(stems))


def check_case(case):
    day, month = case["day"], case["month"]
    require(all(LunarUtil.SHI_SHEN[day + stem] == role for stem, role in case["roles"].items()),
            "An explicit visible-stem role differs from the case")
    candidates = derived_completions(case)
    require(candidates == enumerate_sexagenary(case), "The two legal-pillar enumerations differ")
    result = {
        "month_as_printed": month,
        "month_is_branch": month in bazi.ZHI,
        "visible_stem_roles": case["roles"],
        "fixed_visible_positions": case.get("fixed_visible_positions", {}),
        "compatible_sexagenary_combinations": len(candidates),
        "pdf_pages": case["pdf_pages"],
    }
    if "fixed_visible_positions" in case:
        year_stem = case["fixed_visible_positions"]["year"]
        start = bazi.GAN.index(FIVE_TIGER_START[year_stem])
        result["month_pillar_from_stated_year_stem"] = bazi.GAN[(start + "寅卯辰巳午未申酉戌亥子丑".index(month)) % 10] + month
    if not result["month_is_branch"]:
        require(not candidates, "A non-branch has unsupported completions")
        result["meeting_premise"] = None
        return result
    hidden = LunarUtil.ZHI_HIDE_GAN[month]
    result["month_hidden_stems"] = {stem: LunarUtil.SHI_SHEN[day + stem] for stem in hidden}
    result["month_main_role"] = LunarUtil.SHI_SHEN[day + hidden[0]]
    require(result["month_main_role"] == case["root_role"], "The stated main month role differs")

    if "bind" in case:
        edges = case["ordered_control_edges"]
        baseline = ordered_controls(edges)
        bound = ordered_controls(edges, case["bind"])
        require([baseline[-1], bound[-1]] == case["last_edge_before_after_binding"],
                "The stated actor removal does not produce the registered counterfactual")
        result["five_combination_local_reading"] = {
            "pair": case["bind"],
            "ordered_actor_target_pairs": edges,
            "active_without_binder": baseline,
            "active_with_binder": bound,
        }
    if "meeting_branches" in case:
        branches = month + case["required_branches"]
        meeting = MEETING_NAMES[case["meeting_element"]]
        require(set(case["meeting_branches"]) == set(branches)
                and meeting in bazi.group_patterns(branches)["complete_three_harmonies"],
                "The stated three-branch premise differs")
        removals = {branch: meeting in bazi.group_patterns(branches.replace(branch, ""))["complete_three_harmonies"]
                    for branch in case["required_branches"]}
        require(not any(removals.values()), "A removed branch leaves the complete meeting in place")
        result["meeting_premise"] = {"element": case["meeting_element"], "all_named_branches_present": True,
                                     "complete_after_each_branch_removal": removals}
    if "generation_example" in case:
        require(generation(case["generation_example"]), "Stated generation direction differs")
        result["generation_example"] = case["generation_example"]
    if case["case"] == "shen_water_meeting":
        result["visible_water_month_roots"] = {
            "same_stem": "癸" in hidden,
            "same_element": [stem for stem in hidden if bazi.element(stem) == "水"],
        }
    return result


def run(source_dir, second_source_dir, output):
    require(source_dir.resolve() != second_source_dir.resolve(), "Use distinct source acquisition directories")
    spec = read_json(HERE / "cases.json")
    for edition, file in SOURCE_FILES.items():
        expected = spec["sources"][edition]["file_sha256"]
        require(digest(source_dir / file) == digest(second_source_dir / file) == expected, "A source edition differs")
    results = {}
    for example in spec["cases"]:
        overrides = example.get("edition_overrides", {})
        main = check_case(example)
        results[example["case"]] = {
            edition: check_case({**example, **overrides[edition]}) if edition in overrides else main
            for edition in spec["sources"]
        }
    write_json(output, {
        "round": "R31",
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "case_spec_sha256": digest(HERE / "cases.json"),
        "opening_examples": spec["opening_examples"],
        "edition_and_case_counts": [len(spec["sources"]), len(results)],
        "cases": results,
        "verification": {
            "two_source_copies_for_each_edition_match": True,
            "complete_sexagenary_set_equality_across_two_implementations": True,
            "five_combination_with_and_without_binder_examples": 5,
            "branch_removal_checks": 4,
            "shared_calendar_conventions": ["sexagenary cycle", "five tigers", "five rats"],
            "conditions_held_fixed": ["local binding precedence", "specified stem and branch roles"],
            "actual_birth_calendar_realization_checked": False,
        },
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--second-source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source_dir, args.second_source_dir, args.output)
