"""Compare the sealed classical examples with the R8 and R21 scopes."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from open_birth_chart import bazi_engine as bazi
from officer_cases import officer_premises, read_pillars

HERE = Path(__file__).resolve().parent


def main(args):
    spec = (HERE / "protocol.json").read_bytes()
    if sha256(spec).hexdigest() != args.registration_sha256:
        raise ValueError("Use the GitHub-verified registration SHA-256")
    cfg = json.loads(spec)
    for file, expected in cfg["files_sha256"].items():
        if sha256((HERE.parents[1] / file).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Sealed input changed: {file}")
    cases = json.loads((HERE / "cases.json").read_bytes())
    if len(cases) != cfg["source_case_count"]:
        raise ValueError("Run every registered example")
    results = []
    for case in cases:
        old = bazi.interpret_pillars(read_pillars(case["pillars"]))
        command = old["month_command"]
        new = officer_premises(case["pillars"])
        results.append({
            **case,
            "r8_month_command": command,
            "r8_active_officer_clauses": [
                x["rule"] for x in old["clause_matches"]
                if x["rule"] in ("BZC01", "BZC02a", "BZC02b") and x["structural_match"]
            ],
            "r21": new,
            "source_condition_matched": case["expected"] in new["source_conditions"],
        })
    output = {
        "registration_sha256": args.registration_sha256,
        "r8_officer_as_month_candidate": sum(
            r["r8_month_command"]["pattern_candidate"] == "正官" for r in results
        ),
        "r8_officer_as_unique_registration_candidate": sum(
            r["r8_month_command"]["pattern_candidate"] == "正官"
            and r["r8_month_command"]["unique_month_candidate_under_registered_selector"]
            for r in results
        ),
        "r21_known_case_condition_matches": sum(r["source_condition_matched"] for r in results),
        "known_classical_examples": len(results),
        "cases": results,
    }
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    main(parser.parse_args())
