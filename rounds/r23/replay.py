"""Replay the R23 sealed chart transcriptions against two separate calculations."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from classical import BRANCHES, STARS, calculate, star_palaces

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORE_FIELDS = ("life", "bureau", *STARS)
FIELDS = ("life", "body", "bureau", *STARS)
SEALED_DIGESTS = {
    "rounds/r23/protocol.json": "2c243bb80edf59ca43f37f4f247171d4113330b8b4f5c0d52c033d6152686159",
    "rounds/r23/transcription.json": "24d4f88ea2a061444a3b8d61e14d2ddcf0430cc6ac5db1decbcf2401d13d9f10",
    "rounds/r23/rules-scan-receipts.json": "f48f3ea2921b430e60a0273e61e0a41beccdab86d279c700cfd51a83957c5645",
}
SLOTS = ("193L", *(f"{page}{side}" for page in range(194, 201) for side in "RL"))


def read_inputs() -> tuple[list[dict], dict[str, str]]:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    fingerprints = {**protocol["files_sha256"], **SEALED_DIGESTS}
    for relative_path, expected in fingerprints.items():
        if sha256((ROOT / relative_path).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Sealed input has changed: {relative_path}")
    transcribed = json.loads((HERE / "transcription.json").read_text(encoding="utf-8"))
    charts = transcribed["charts"]
    if tuple(row["slot"] for row in charts) != SLOTS or len(charts) != protocol["planned_slots"]:
        raise ValueError("The consecutive chart slots do not match registration")
    if "".join(transcribed["cell_order"]) != BRANCHES[5:] + BRANCHES[:5]:
        raise ValueError("Historical plate orientation is incomplete")
    return charts, fingerprints


def printed_fields(printed: dict) -> dict:
    cells = printed["star_cells"]
    if set(cells) != set(BRANCHES):
        raise ValueError("The chart must contain all twelve graphic cells")
    for stars in cells.values():
        if len(stars) != len(set(stars)) or not set(stars) <= set(STARS):
            raise ValueError("Unknown or repeated major star in a single cell")
    placements = {star: [b for b in BRANCHES if star in cells[b]] or None for star in STARS}
    return {**{key: printed[key] for key in ("life", "body", "bureau")}, **placements}


def calculated_fields(calculated: dict) -> dict:
    if set(calculated["stars"]) != set(STARS):
        raise ValueError("A calculated chart has an incomplete major star catalogue")
    return {**{key: calculated[key] for key in ("life", "body", "bureau")}, **calculated["stars"]}


def compare(expected, predictions: list) -> str:
    if expected is None:
        return "source_unread"
    if not predictions:
        return "unavailable"
    if any(x != predictions[0] for x in predictions[1:]):
        return "variant_dependent"
    return "equal" if predictions[0] == expected else "different"


def comparisons(printed: dict, classical: dict, candidates: list[dict]) -> dict:
    print_to_classical = {field: compare(printed[field], [classical[field]]) for field in FIELDS}
    print_to_modern = {
        field: compare(printed[field], [x[field] for x in candidates]) for field in FIELDS
    }
    classical_to_modern = {
        field: compare(classical[field], [x[field] for x in candidates]) for field in FIELDS
    }
    projected = {}
    if printed["紫微"] and len(printed["紫微"]) == 1:
        offsets = star_palaces(printed["紫微"][0])
        projected = {star: compare(printed[star], [offsets[star]]) for star in STARS if star != "紫微"}
    return {
        "printed_classical": print_to_classical,
        "printed_modern": print_to_modern,
        "classical_modern": classical_to_modern,
        "printed_ziwei_origin_other_stars": projected,
    }


def modern_placements(charts: list[dict]) -> list[dict]:
    inputs = [{"slot": row["slot"], "birth": row["birth"]} for row in charts]
    done = subprocess.run(
        ["node", str(HERE / "modern.cjs")],
        input=json.dumps(inputs, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if done.returncode:
        raise RuntimeError(f"Iztro replay failed: {done.stderr.strip()}")
    returned = json.loads(done.stdout)
    if [r["slot"] for r in returned] != [r["slot"] for r in charts]:
        raise ValueError("The modern replay returned different chart slots")
    return returned


def replay() -> dict:
    charts, fingerprints = read_inputs()
    modern = modern_placements(charts)
    rows = []
    attempts = Counter()
    bridge = Counter()
    modern_candidate_fields = {}
    for chart, engine in zip(charts, modern, strict=True):
        expected = printed_fields(chart["printed"])
        old_chart = calculate(chart["birth"])
        old_fields = calculated_fields(old_chart)
        variants = []
        for attempt in engine["attempts"]:
            attempts[attempt["status"]] += 1
            for variant in attempt.get("variants", []):
                placements = calculated_fields(variant)
                bridge[variant["r8_bridge"]] += 1
                variants.append(placements)
                fields = modern_candidate_fields.setdefault(variant["branch"], Counter())
                fields.update(compare(expected[field], [placements[field]]) for field in FIELDS)
                variant["vs_printed"] = {
                    field: compare(expected[field], [placements[field]]) for field in FIELDS
                }

        rows.append({
            "slot": chart["slot"],
            "printed": expected,
            "classical": old_chart,
            "modern_by_carrier": engine["attempts"],
            "comparison": comparisons(expected, old_fields, variants),
        })

    comparable = ("printed_classical", "printed_modern", "classical_modern",
                  "printed_ziwei_origin_other_stars")
    counts = {}
    for layer in comparable:
        keys = list(rows[0]["comparison"][layer])
        passing_by_field = {
            key: dict(Counter(row["comparison"][layer].get(key, "unavailable") for row in rows))
            for key in keys
        }
        all_fields = dict(Counter(value for row in rows for value in row["comparison"][layer].values()))
        counts[layer] = {"all_fields": all_fields, "by_field": passing_by_field}
        if layer == "printed_ziwei_origin_other_stars":
            continue
        counts[layer]["complete_core_equal"] = sum(
            all(row["comparison"][layer][k] == "equal" for k in CORE_FIELDS) for row in rows
        )
        counts[layer]["complete_with_body_equal"] = sum(
            all(row["comparison"][layer][k] == "equal" for k in FIELDS) for row in rows
        )
        counts[layer]["all_available_fields_equal"] = sum(
            all(x in {"equal", "source_unread"} for x in row["comparison"][layer].values())
            for row in rows
        )
    return {
        "registration_version": "OBS-R23-ZW-MING-CHARTS-1.0",
        "sha256_sealed_inputs": fingerprints,
        "slots": len(rows),
        "modern_carrier_status": dict(attempts),
        "r8_bridge_status": dict(bridge),
        "source_core_complete_slots": sum(all(r["printed"][k] is not None for k in CORE_FIELDS) for r in rows),
        "source_complete_with_body_slots": sum(all(r["printed"][k] is not None for k in FIELDS) for r in rows),
        "field_counts": counts,
        "modern_candidate_field_counts": {k: dict(v) for k, v in modern_candidate_fields.items()},
        "charts": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    args = parser.parse_args()
    data = json.dumps(replay(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(data, encoding="utf-8")
    else:
        print(data, end="")


if __name__ == "__main__":
    main()
