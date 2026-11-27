"""Replay the registered comparisons against the unchanged R8 Bazi selector."""

import argparse
import hashlib
import json
from pathlib import Path

from open_birth_chart import bazi_engine as bazi

from rounds.r21.officer_cases import read_pillars
from .killing_cases import inspect


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
R8_CLAUSES = ("BZC05a", "BZC05b", "BZC05c")


def run(output):
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, expected in protocol["files_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Sealed input changed: {name}")
    cases = json.loads((HERE / "cases.json").read_text())
    if [case["id"] for case in cases] != list(range(1, 9)):
        raise ValueError("Run all eight registered cases in source order")

    comparisons = []
    for case in cases:
        old = bazi.interpret_pillars(read_pillars(case["pillars"]))
        command = old["month_command"]
        found = inspect(case["pillars"])
        matched = found["conditions"][case["target"]]
        partial = case["target"] == "食重透印的可核部分" and not (
            found["visible_wealth_precedes_food"] and found["visible_killings_exact_in_month"]
        )
        comparisons.append({
            "id": case["id"],
            "target": case["target"],
            "r8_month_pattern": command["pattern_candidate"],
            "r8_month_pattern_status": command["selection_status"],
            "r8_unique_month_candidate": command["unique_month_candidate_under_registered_selector"],
            "r8_clauses": [clause["rule"] for clause in old["clause_matches"]
                           if clause["rule"] in R8_CLAUSES and clause["structural_match"]],
            "premise_status": ("partial" if partial else "present") if matched else "not_found",
            "chapter_evidence": found,
        })

    with output.open("x", encoding="utf-8") as stream:
        json.dump({
            "registration_commit": protocol["registration_commit"],
            "cases": comparisons,
            "counts": {
                "known_classical_cases": len(comparisons),
                "r8_killing_as_month_pattern": sum(c["r8_month_pattern"] == "七杀" for c in comparisons),
                "r8_killing_as_unique_month_pattern": sum(c["r8_month_pattern"] == "七杀" and
                                                        c["r8_unique_month_candidate"] for c in comparisons),
                "r8_clause_matches_by_case": {
                    rule: sum(rule in c["r8_clauses"] for c in comparisons) for rule in R8_CLAUSES
                },
                "bounded_source_premises_present": sum(c["premise_status"] == "present" for c in comparisons),
                "bounded_source_premises_partial": sum(c["premise_status"] == "partial" for c in comparisons),
            },
            "outcomes_scored": False,
        }, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
