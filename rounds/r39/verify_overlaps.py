"""Verify R39's four headline overlaps using standalone integer and SQL checks."""

import argparse
import json
from pathlib import Path
import sqlite3


STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
CHECKS = (
    ("辛寅", "xin_yin_officer/xin_yin_retain", "instr(v,'丙')", "instr(v,'丙') AND instr(v,'甲')", None),
    ("癸寅", "gui_yin_wealth/gui_yin_retain", "instr(v,'丙') AND instr(b,'午') AND instr(b,'戌')",
     "instr(v,'甲') AND instr(v,'丙')", "甲"),
    ("丙寅", "bing_yin_adverse/bing_yin_retain", "instr(b,'午') AND instr(b,'戌') AND NOT instr(v,'甲')",
     "instr(b,'午') AND instr(b,'戌') AND instr(v,'壬')", None),
    ("丙申", "bing_shen_adverse/bing_shen_retain", "instr(v,'壬') AND instr(b,'子') AND instr(b,'辰')",
     "instr(v,'壬') AND instr(v,'戊')", "庚"),
)


def chart_features(domain):
    day, month = domain
    month_from_yin = (BRANCHES.index(month) + 10) % 12
    day_stem = STEMS.index(day)
    for year_cycle in range(60):
        month_stem = (2 * (year_cycle + 1) + month_from_yin) % 10
        for day_cycle in range(day_stem, 60, 10):
            for hour_branch in range(12):
                hour_stem = (2 * day_stem + hour_branch) % 10
                visible = STEMS[year_cycle % 10] + STEMS[month_stem] + STEMS[hour_stem]
                branches = BRANCHES[year_cycle % 12] + month + BRANCHES[day_cycle % 12] + BRANCHES[hour_branch]
                yield domain, visible, branches


def verify(record):
    compared = 0
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE charts (day_month TEXT, v TEXT, b TEXT)")
        for domain, *_ in CHECKS:
            db.executemany("INSERT INTO charts VALUES (?, ?, ?)", chart_features(domain))
        for name, edition in record["edition_results"].items():
            for domain, key, first, shared_second, concealed in CHECKS:
                pair = edition["paired_predicate_overlaps"][key]
                if domain == "癸寅" and name == "world_library":
                    if pair != {"status": "clause_absent_or_trigger_unspecified"}:
                        raise ValueError("The World Library edition omits the favorable 癸寅 clause")
                    continue
                second = shared_second
                if domain == "丙寅" and name == "collected":
                    second = second.replace("instr(v,'壬')", "(instr(v,'壬') OR instr(v,'甲'))")
                for reading in ("literal", "concealed_stem_not_exposed"):
                    clause = first
                    if reading == "concealed_stem_not_exposed" and concealed:
                        clause += f" AND NOT instr(v,'{concealed}')"
                    counts = db.execute(f"""
                        SELECT sum(a AND c), sum(a AND NOT c), sum(NOT a AND c), sum(a AND c AND wu)
                        FROM (
                            SELECT ({clause}) AS a, ({second}) AS c, instr(v,'戊') AS wu
                            FROM charts WHERE day_month=?
                        )
                    """, (domain,)).fetchone()
                    row = pair[reading]
                    if counts[:3] != tuple(row[field] for field in ("both", "first_only", "second_only")):
                        raise ValueError(f"Overlap count differs for {name}, {key}, {reading}")
                    if domain == "癸寅" and counts[3] != row["both_with_additional_visible_stem"]["戊"]:
                        raise ValueError(f"The 癸寅 戊-exposed subset differs under {reading}")
                    compared += 1
    if compared != 14:
        raise ValueError(f"Expected 14 edition and reading combinations, checked {compared}")
    return compared


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, nargs="?", default=Path(__file__).with_name("results.json"))
    args = parser.parse_args()
    print(f"Checked {verify(json.loads(args.results.read_bytes()))} overlap results and the 癸寅 戊-exposed subset")
