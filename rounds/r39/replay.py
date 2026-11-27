"""Reproduce the registered R39 month-command clause checks."""

from __future__ import annotations

import argparse
from collections import Counter
from functools import cache
from importlib.metadata import version
from itertools import product
from pathlib import Path

from lunar_python import Solar
from lunar_python.util import LunarUtil
from open_birth_chart import bazi_engine as bazi

from rounds.r21.officer_cases import POSITIONS, read_pillars
from rounds.r27.archive_source import digest, read_json, require, write_json
from rounds.r31.replay import VISIBLE_POSITIONS, derived_completions, enumerate_sexagenary, generation


HERE = Path(__file__).resolve().parent
STEMS = "甲乙丙丁戊己庚辛壬癸"
ELEMENTS = "木火土金水"
SAME_POLARITY = ("比肩", "食神", "偏财", "七杀", "偏印")
OTHER_POLARITY = ("劫财", "伤官", "正财", "正官", "正印")
ROLE_FAMILIES = ("比劫", "食伤", "财", "官杀", "印")
TRINE_ELEMENTS = dict(zip("水金火木", (frozenset(bazi.ZHI[i::4]) for i in range(4)), strict=True))
READINGS = ("literal", "concealed_stem_not_exposed")


def ten_god(day, stem):
    day_index = STEMS.index(day)
    stem_index = STEMS.index(stem)
    cycle_distance = (stem_index // 2 - day_index // 2) % 5
    roles = OTHER_POLARITY if (stem_index - day_index) % 2 else SAME_POLARITY
    return roles[cycle_distance]


def inspect_structure(spec):
    for day, stem in product(STEMS, repeat=2):
        require(ten_god(day, stem) == LunarUtil.SHI_SHEN[day + stem], f"Ten-god mismatch {day}{stem}")
    require(set(TRINE_ELEMENTS.values()) == {frozenset(group) for group in bazi.TRINES.values()},
            "Independent branch trine groups differ from R8")
    opening = spec["opening"]
    hidden = LunarUtil.ZHI_HIDE_GAN[opening["month"]]
    require(hidden[0] == opening["month_main"] and set(hidden) == set(opening["discussed_hidden"]),
            "Opening illustration disagrees with the month hidden stems")
    require(opening["day"] is None, "Opening illustration does not fix a day stem")
    for case in spec["cases"]:
        day, month = case["day"], case["month"]
        hidden = LunarUtil.ZHI_HIDE_GAN[month]
        require(hidden[0] == case["month_main"], f"Month main stem differs in {case['id']}")
        if "concealed_contrast" in case:
            require(case["concealed_contrast"] in hidden, f"Contrasted stem is not hidden in {case['id']}")
        for stem, role in case["roles"].items():
            require(ten_god(day, stem) == role, f"Named ten-god relation differs in {case['id']}")
        if "trine" in case:
            element = case["trine_element"]
            require(month in case["trine"] and TRINE_ELEMENTS[element] == frozenset(case["trine"]),
                    f"Wrong branches for the registered trine in {case['id']}")
            family = ROLE_FAMILIES[(ELEMENTS.index(element) - STEMS.index(day) // 2) % 5]
            require(family == case["trine_role_family"], f"Wrong trine role family in {case['id']}")
        for edge in case.get("generation", []):
            require(generation(edge), f"Generation relation differs in {case['id']}")
        for edge in case.get("control", []):
            require(bazi.control(*edge), f"Control relation differs in {case['id']}")


@cache
def pool(day, month):
    template = {"day": day, "month": month, "visible": ""}
    pillars = derived_completions(template)
    require(pillars == enumerate_sexagenary(template), f"Four-pillar enumerations differ for {day}{month}")
    require(len(pillars) == 4320, f"Expected 4320 combinations for {day}{month}, got {len(pillars)}")
    return {
        chart: (frozenset(chart[POSITIONS.index(position)][0] for position in VISIBLE_POSITIONS),
                frozenset(pillar[1] for pillar in chart))
        for chart in sorted(pillars)
    }


def matches(case, stems, branches, reading="literal"):
    absent = set(case.get("absent", ""))
    if reading == "concealed_stem_not_exposed":
        absent.update(case.get("concealed_contrast", ""))
    one_of = case.get("visible_any", "")
    return (
        set(case.get("visible", "")) <= stems
        and not absent & stems
        and (not one_of or bool(set(one_of) & stems))
        and set(case.get("trine", case.get("branches", ""))) <= branches
    )


@cache
def month_command(pillars):
    result = bazi.interpret_pillars(read_pillars(pillars))["month_command"]
    month = pillars[1][1]
    branches = {pillar[1] for pillar in pillars}
    trines = {group for group in TRINE_ELEMENTS.values() if month in group and group <= branches}
    require(trines == {frozenset(group) for group in result["month_in_complete_trines"]},
            f"R8 disagrees with the independent month-trine test for {pillars}")
    require(result["unique_yongshen_adjudicated"] is False,
            f"R8 now adjudicates a unique use-god for {pillars}")
    return result


def summarize_matches(case, selected):
    commands = [month_command(pillars) for pillars in selected]
    counts = {
        "count": len(selected),
        "r8_selection_status_counts": dict(sorted(Counter(command["selection_status"] for command in commands).items())),
        "r8_candidate_ten_god_counts": dict(sorted(
            Counter(command["candidate_ten_god"] or "none" for command in commands).items()
        )),
        "r8_unique_month_candidate_count": sum(command["unique_month_candidate_under_registered_selector"]
                                               for command in commands),
        "r8_unique_yongshen_count": sum(command["unique_yongshen_adjudicated"] for command in commands),
    }
    features = pool(case["day"], case["month"])
    if "stratify_visible" in case:
        stem = case["stratify_visible"]
        counts["with_additional_visible_stem"] = {stem: sum(stem in features[pillars][0] for pillars in selected)}
    if "visible_any" in case:
        stems = set(case["visible_any"])
        alternatives = Counter("".join(sorted(stems & features[pillars][0])) for pillars in selected)
        counts["visible_alternatives"] = dict(sorted(alternatives.items()))
    return counts


def edition_results(spec, edition):
    cases = {}
    selection = {}
    predicates = {}
    for original in spec["cases"]:
        case = original | original.get("edition_overrides", {}).get(edition, {})
        key, day, month = case["id"], case["day"], case["month"]
        status = case.get("status", "testable")
        item = {"status": status, "pdf_pages": case["pdf_pages"][edition], "textual_target": case["target"]}
        cases[key] = item
        if status == "omitted":
            continue
        if status == "trigger_unspecified":
            hidden = {stem: ten_god(day, stem) for stem in LunarUtil.ZHI_HIDE_GAN[month]}
            item["month_hidden_roles"] = hidden
            item["named_input_role_is_month_hidden"] = case["stated_from_role"] in hidden.values()
            continue
        candidates = pool(day, month)
        for reading in READINGS:
            selected = {pillars for pillars, (stems, branches) in candidates.items()
                        if matches(case, stems, branches, reading)}
            selection[key, reading] = selected
            item[reading] = summarize_matches(case, selected)
        predicates[key] = case

    overlaps = {}
    for first, second in spec["overlaps"]:
        key = f"{first}/{second}"
        if first not in predicates or second not in predicates:
            overlaps[key] = {"status": "clause_absent_or_trigger_unspecified"}
            continue
        case = predicates[first]
        features = pool(case["day"], case["month"])
        results = {}
        for reading in READINGS:
            left, right = selection[first, reading], selection[second, reading]
            both = left & right
            counts = {"both": len(both), "first_only": len(left - right), "second_only": len(right - left)}
            if "stratify_visible" in case:
                stem = case["stratify_visible"]
                counts["both_with_additional_visible_stem"] = {
                    stem: sum(stem in features[pillars][0] for pillars in both)
                }
            results[reading] = counts
        overlaps[key] = results
    return {"cases": cases, "paired_predicate_overlaps": overlaps}, predicates


def calendar_round_trip(pillars, config):
    candidates = Solar.fromBaZi(*pillars, sect=config["sect"], base_year=config["start_year"])
    clocks = sorted(solar.toYmdHms().replace(" ", "T") for solar in candidates
                    if config["start_year"] <= solar.getYear() <= config["end_year"])
    for clock in clocks:
        row = {"study_id": "r39-synthetic", "birth_local": clock, "sex": "M",
               "source_offset_seconds": config["offset_seconds"]}
        calculated = bazi.build_natal(row)["pillars"]
        require(tuple(calculated[position]["ganzhi"] for position in POSITIONS) == pillars,
                f"Forward R8 natal calculation did not reproduce the inverse calendar candidate {clock}")
        return clock
    return None


def sample_calendar(pillars, config):
    results = {}
    attempts = 0
    for chart in pillars[:config["inverse_attempt_limit_per_side"]]:
        attempts += 1
        clock = calendar_round_trip(chart, config)
        if clock is not None:
            results[chart] = clock
        if len(results) == config["valid_limit_per_side"]:
            break
    return results, attempts


def compare_control(control, config, editions):
    day, month = control["day"], control["month"]
    features = pool(day, month)
    toggle_stem = set(control.get("toggle_visible", ""))
    substitute = set(control.get("substitute_visible", ""))
    toggle_branches = set(control.get("toggle_branches", ""))
    with_condition = {}
    without_condition = {}
    for pillars, (stems, branches) in features.items():
        if not matches(control, stems, branches):
            continue
        matching_key = stems - toggle_stem - substitute if control.get("match_visible") else None
        condition = toggle_stem <= stems if toggle_stem else toggle_branches <= branches
        if condition and not substitute & stems:
            with_condition[pillars] = matching_key
        elif not condition and substitute <= stems:
            without_condition[pillars] = matching_key

    shared = set(with_condition.values()) & set(without_condition.values())
    positive = [pillars for pillars, key in with_condition.items() if key in shared]
    negative = [pillars for pillars, key in without_condition.items() if key in shared]
    left, left_attempts = sample_calendar(positive, config)
    right, right_attempts = sample_calendar(negative, config)
    comparable = [(a, b) for a in left for b in right if with_condition[a] == without_condition[b]]
    report = {
        "legal_candidates_with_counterpart": {"with": len(positive), "without": len(negative)},
        "inverse_attempts": {"with": left_attempts, "without": right_attempts},
        "successful_calendar_round_trips": {"with": len(left), "without": len(right)},
        "status": "calendar_pair_found" if comparable else "no_calendar_pair_within_budget",
    }
    if not comparable:
        return report

    a, b = min(comparable, key=lambda pair: (sum(x != y for x, y in zip(*pair, strict=True)), *pair))
    report["changed_pillar_positions"] = [position for position, x, y in zip(POSITIONS, a, b, strict=True) if x != y]
    for label, pillars, clocks in (("with", a, left), ("without", b, right)):
        stems, branches = features[pillars]
        report[label] = {
            "pillars": list(pillars),
            "synthetic_birth_local": clocks[pillars],
            "matching_clause_ids": {
                edition: {
                    reading: [
                        key for key, clause in cases.items()
                        if (clause["day"], clause["month"]) == (day, month)
                        and matches(clause, stems, branches, reading)
                    ]
                    for reading in READINGS
                }
                for edition, cases in editions.items()
            },
            "r8_selection_status": month_command(pillars)["selection_status"],
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    spec = read_json(HERE / "cases.json")
    source_hashes = {name: digest(args.source_dir / source["file"]) for name, source in spec["sources"].items()}
    require(source_hashes == {name: source["file_sha256"] for name, source in spec["sources"].items()},
            "One or both source PDFs differ from the preregistered files")
    require(version("lunar-python") == "1.4.9", "The registered lunar-python dependency is missing")
    inspect_structure(spec)
    parts = {edition: edition_results(spec, edition) for edition in spec["sources"]}
    editions = {edition: result for edition, (result, _) in parts.items()}
    predicates = {edition: values for edition, (_, values) in parts.items()}
    calendar = spec["calendar_controls"]
    controls = {control["id"]: compare_control(control, calendar, predicates) for control in spec["controls"]}
    domains = sorted({(case["day"], case["month"]) for case in spec["cases"]})
    result = {
        "round": "R39",
        "source_pdf_sha256": source_hashes,
        "case_spec_sha256": digest(HERE / "cases.json"),
        "lunar_python": version("lunar-python"),
        "r8_engine": bazi.VERSION,
        "opening_month_stem_roles": "not_applicable_day_stem_unspecified",
        "independent_ten_god_relations_checked": len(STEMS) ** 2,
        "independent_trine_groups_checked": len(TRINE_ELEMENTS),
        "sexagenary_combinations_by_day_month": {day + month: len(pool(day, month)) for day, month in domains},
        "edition_results": editions,
        "synthetic_calendar_controls": controls,
    }
    write_json(args.output, result)


if __name__ == "__main__":
    main()
