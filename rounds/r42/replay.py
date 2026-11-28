"""Reproduce the R42 generation, control, and context comparisons."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from lunar_python.util import LunarUtil
from open_birth_chart import bazi_engine as bazi

from rounds.r21.officer_cases import read_pillars
from rounds.r27.archive_source import digest, read_json, require, write_json
from rounds.r31.replay import generation
from rounds.r39.replay import ELEMENTS, STEMS, calendar_round_trip, pool, ten_god


HERE = Path(__file__).resolve().parent
R39 = HERE.parent / "r39"


def directed_relation(first, second):
    difference = (STEMS.index(second) // 2 - STEMS.index(first) // 2) % len(ELEMENTS)
    return {1: "generation", 2: "control"}.get(difference)


def compare_case(case):
    key, day, month = (case[field] for field in ("id", "day", "month"))
    pair = case["pair"]
    hidden = LunarUtil.ZHI_HIDE_GAN[month]
    require(hidden[0] == case["month_main"], f"Unexpected monthly main stem for {key}")
    roles = [ten_god(day, stem) for stem in pair]
    require(roles == case["roles"] == [LunarUtil.SHI_SHEN[day + stem] for stem in pair],
            f"An explicit ten-god relation differs for {key}")
    relation = directed_relation(*pair)
    require(relation == case["direction"] and
            (generation(pair) if relation == "generation" else bazi.control(*pair)),
            f"Five-element direction differs for {key}")

    exposure = dict.fromkeys(("both", "first_only", "second_only", "neither"), 0)
    extra = dict.fromkeys(("present", "extra_controls_named_stem", "named_stem_controls_extra"), 0)
    extras_by_stem = Counter()
    r8_status = Counter()
    r8_unique_month = 0
    r8_specific_clause = 0
    matched = []
    for pillars, (visible, _) in pool(day, month).items():
        first, second = (stem in visible for stem in pair)
        label = ("both" if second else "first_only") if first else ("second_only" if second else "neither")
        exposure[label] += 1
        if label != "both":
            continue
        matched.append(pillars)
        remaining = visible - set(pair)
        require(len(remaining) <= 1, f"Unexpected number of additional visible stems for {key}")
        for stem in remaining:
            extras_by_stem[stem] += 1
            extra["present"] += 1
            extra["extra_controls_named_stem"] += any(directed_relation(stem, named) == "control" for named in pair)
            extra["named_stem_controls_extra"] += any(directed_relation(named, stem) == "control" for named in pair)
        model = bazi.interpret_pillars(read_pillars(pillars))
        command = model["month_command"]
        require(command["unique_yongshen_adjudicated"] is False, f"Unexpected final R8 judgment for {key}")
        r8_status[command["selection_status"]] += 1
        r8_unique_month += command["unique_month_candidate_under_registered_selector"]
        if "r8_clause" in case:
            relevant, = [clause for clause in model["clause_matches"] if clause["rule"] == case["r8_clause"]]
            r8_specific_clause += relevant["structural_match"]

    return {
        "stated_purity": case["source_result"],
        "two_stem_roles": dict(zip(pair, roles, strict=True)),
        "monthly_main_stem": hidden[0],
        "named_stems_hidden_in_month": [stem for stem in pair if stem in hidden],
        "direction": {"source": pair[0], "target": pair[1], "relation": relation},
        "simplified_generation_pure_control_mixed_agrees": (relation == "generation") == (case["source_result"] == "纯"),
        "exposure_counts": exposure,
        "additional_visible_stem_counts": extra | {"by_stem": dict(sorted(extras_by_stem.items()))},
        "r8_month_command_status_counts": dict(sorted(r8_status.items())),
        "r8_unique_month_candidate_count": r8_unique_month,
        "r8_named_clause": {"rule": case["r8_clause"], "matches": r8_specific_clause} if "r8_clause" in case else None,
    }, matched


def matched_roles_pair(left, right, config, limit):
    def groups(charts):
        grouped = defaultdict(list)
        for year, month, day, hour in charts:
            grouped[year, month, hour[0]].append((year, month, day, hour))
        return grouped

    left_groups, right_groups = groups(left), groups(right)
    shared = sorted(left_groups.keys() & right_groups.keys())
    report = {
        "shared_year_month_and_non_day_stem_keys": len(shared),
        "legal_candidates_with_counterpart": [
            sum(len(grouped[key]) for key in shared) for grouped in (left_groups, right_groups)
        ],
        "inverse_attempt_count": [0, 0],
        "status": "no_calendar_pair_within_budget",
    }
    attempts = report["inverse_attempt_count"]
    for key in shared:
        witnesses = []
        for index, grouped in enumerate((left_groups, right_groups)):
            for chart in grouped[key]:
                if attempts[index] >= limit:
                    break
                attempts[index] += 1
                clock = calendar_round_trip(chart, config)
                if clock is not None:
                    witnesses.append({"pillars": list(chart), "synthetic_local_clock": clock})
                    break
        if len(witnesses) == 2:
            report.update(status="calendar_pair_found", witnesses=witnesses)
            break
        if limit in attempts:
            break
    return report


def compare_previous(case_record, specification):
    older = {case["id"]: case for case in specification["cases"]}
    previous = read_json(R39 / "results.json")["edition_results"]["collected"]["cases"]
    xin, shen = older["xin_yin_retain"], older["bing_shen_retain"]
    require(set(xin["visible"]) == set(case_record["xin_yin"]["two_stem_roles"]), "The two Xin clauses differ")
    require(previous["xin_yin_retain"]["literal"]["count"] == case_record["xin_yin"]["exposure_counts"]["both"],
            "Cross-chapter co-exposure counts differ")
    require(shen["control"] == ["戊壬"] and shen["roles"]["戊"] == "食神" and shen["roles"]["壬"] == "七杀"
            and shen["generation"] == ["戊庚"] and shen["roles"]["庚"] == "偏财",
            "Prior retention clause has different directions or roles")
    return {
        "xin_yin": {"same_visible_stems": "甲丙", "coexposed_count_in_both_chapters": previous["xin_yin_retain"]["literal"]["count"],
                    "r39_role_order": xin["target"], "r42_label": case_record["xin_yin"]["stated_purity"]},
        "gui_wei_and_bing_shen": {
            "shared_directed_role_relation": ["食神", "control", "七杀"],
            "r39_additional_generation": ["食神", "generation", "偏财"],
            "r39_target": shen["target"],
        },
    }


def run(source, output):
    prior = read_json(R39 / "cases.json")
    hashes = {name: digest(source / entry["file"]) for name, entry in prior["sources"].items()}
    require(hashes == {name: entry["file_sha256"] for name, entry in prior["sources"].items()}, "Source PDF hashes differ")
    spec = read_json(HERE / "cases.json")
    cases = {}
    candidates = {}
    for case in spec["cases"]:
        key = case["id"]
        cases[key], candidates[key] = compare_case(case)
    editions = {}
    for edition, item in spec["sources"].items():
        covered = [case["id"] for case in spec["cases"] if edition not in case.get("omitted_in", [])]
        editions[edition] = item | {
            "covered_case_ids": covered,
            "pure": sum(cases[key]["stated_purity"] == "纯" for key in covered),
            "mixed": sum(cases[key]["stated_purity"] == "杂" for key in covered),
            "counterexamples_to_generation_pure_control_mixed": [
                key for key in covered if not cases[key]["simplified_generation_pure_control_mixed_agrees"]
            ],
        }
    left, right = spec["matched_calendar_pair"]
    result = {
        "round": "R42",
        "source_pdf_sha256": hashes,
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "case_spec_sha256": digest(HERE / "cases.json"),
        "edition_scope": editions,
        "cases": cases,
        "role_reversal_pair": {"case_ids": [left, right], **matched_roles_pair(
            candidates[left], candidates[right], prior["calendar_controls"], spec["calendar_attempt_limit_per_side"]
        )},
        "paired_previous_chapter": compare_previous(cases, prior),
    }
    write_json(output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source_dir, args.output)
