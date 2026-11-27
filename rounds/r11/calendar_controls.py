"""Compute fixed-reference contrasts under calendar-matched trajectory pairing."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from hashlib import file_digest, sha256
from itertools import combinations
import json
from math import lcm, sqrt
from pathlib import Path
from statistics import stdev
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
R10 = ROOT / "rounds/r10"
REPLAY = R10 / "independent_replay"
sys.path.insert(0, str(R10 / "methods"))

from analyze_cohorts import load_profiles
from precision_reference import PrecisionReference


def digest(path):
    with Path(path).open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_bytes())


def write_json(path, document):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def match_key(row, resolution):
    birthday = date.fromisoformat(row["birth_local"][:10])
    period = {
        "quarter": (birthday.month - 1) // 3 + 1,
        "month": birthday.month,
        "calendar_only": 0,
    }[resolution]
    return row["stratum_id"], row["calendar_years"][0], period


@dataclass
class Cell:
    flags: np.ndarray
    weight: Fraction


def assemble_cells(rows, flags, resolution):
    grouped = defaultdict(list)
    for i, row in enumerate(rows):
        grouped[match_key(row, resolution)].append(i)
    cells = []
    for key in sorted(grouped):
        indices = grouped[key]
        weights = {Fraction(rows[i]["N_h"], rows[i]["n_h"]) for i in indices}
        require(len(weights) == 1, "A pairing cell crosses sampling weights")
        cells.append(Cell(flags[indices], weights.pop()))
    return cells


def weighted_numerators(cells):
    denominator = lcm(*(cell.weight.denominator for cell in cells))
    terms = [int(cell.weight * denominator) for cell in cells]
    return terms, sum(term * len(cell.flags) for term, cell in zip(terms, cells, strict=True))


def summarize_cells(cells):
    """Evaluate an exact age-by-age product of empirical system marginals."""
    units, population = weighted_numerators(cells)
    age_count = cells[0].flags.shape[1]
    observed, expected, supported = 0, Fraction(0), [0, 0, 0]
    for unit, cell in zip(units, cells, strict=True):
        size = len(cell.flags)
        n_high = cell.flags.sum(axis=0, dtype=np.int64)
        four = n_high.prod(axis=1, dtype=np.int64)
        triples = sum(n_high[:, list(indices)].prod(axis=1, dtype=np.int64)
                      for indices in combinations(range(4), 3))
        # At least three includes the four-success event once.
        expected += Fraction(unit * int((size * triples - 3 * four).sum()), size ** 3)
        observed += unit * int((cell.flags.sum(axis=2) >= 3).sum())
        for i, minimum in enumerate((2, 5, 10)):
            if size >= minimum:
                supported[i] += unit * size
    denominator = population * age_count
    return Fraction(observed, denominator), expected / denominator, {
        "cells": len(cells),
        "singleton_records": sum(len(cell.flags) == 1 for cell in cells),
        "weight_share_by_minimum_donors": {
            str(n): float(Fraction(part, population)) for n, part in zip((2, 5, 10), supported, strict=True)
        },
    }


def donor_indices(size, draws, seed, cell_index, system):
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, cell_index, system])))
    labels = np.arange(size, dtype=np.int32)
    return rng.permuted(np.broadcast_to(labels, (draws, size)), axis=1)


def permuted_counts(flags, draws, seed, cell_index):
    size, ages, systems = flags.shape
    require(1 <= ages <= 64 and systems == 4, "Wrong trajectory shape for bit counting")
    if size == 1:
        return np.full(draws, np.count_nonzero(flags.sum(axis=2) >= 3), dtype=np.int64)
    age_bit = np.left_shift(np.uint64(1), np.arange(ages, dtype=np.uint64))
    words = (flags * age_bit[None, :, None]).sum(axis=1, dtype=np.uint64)
    a = words[:, 0]
    b, c, d = [words[donor_indices(size, draws, seed, cell_index, s), s] for s in (1, 2, 3)]
    at_least_three = (a & b & (c | d)) | (c & d & (a | b))
    return np.bitwise_count(at_least_three).sum(axis=1, dtype=np.int64)


def quantile(numerators, denominator, q):
    """Return the linear order-statistic quantile as an exact fraction."""
    i, remainder = divmod((len(numerators) - 1) * q.numerator, q.denominator)
    a = numerators[i]
    if not remainder:
        return Fraction(a, denominator)
    b = numerators[i + 1]
    return Fraction(a * (q.denominator - remainder) + b * remainder, denominator * q.denominator)


def permutation_summary(cells, observed, expected, draws, seed, audit_draws):
    units, population = weighted_numerators(cells)
    denominator = population * cells[0].flags.shape[1]
    numerators = [0] * draws
    for i, (cell, unit) in enumerate(zip(cells, units, strict=True)):
        counts = permuted_counts(cell.flags, draws, seed, i)
        numerators = [n + unit * int(k) for n, k in zip(numerators, counts, strict=True)]
    observed_numerator = observed * denominator
    require(observed_numerator.denominator == 1, "Observed rate does not use the registered weights")
    center = expected * denominator
    threshold = abs(int(observed_numerator) * center.denominator - center.numerator)
    tail = sum(abs(n * center.denominator - center.numerator) >= threshold for n in numerators)
    audit = sha256(json.dumps(numerators[:audit_draws], separators=(",", ":")).encode()).hexdigest()
    ordered = sorted(numerators)
    simulated_mean = Fraction(sum(numerators), draws * denominator)
    sampled_rates = [n / denominator for n in numerators]
    mean_se = stdev(sampled_rates) / sqrt(draws)
    return {
        "draws": draws,
        "two_sided_tail_including_ties": tail,
        "p": float(Fraction(tail + 1, draws + 1)),
        "conditional_range95": [float(quantile(ordered, denominator, q)) for q in (Fraction(1, 40), Fraction(39, 40))],
        "simulated_mean": float(simulated_mean),
        "mean_standard_error": mean_se,
        "mean_exact_error": float(abs(simulated_mean - expected)),
        "first_draw_numerators_sha256": audit,
        "draw_numerator_denominator": str(denominator),
        "full_draw_numerators_sha256": sha256(json.dumps(numerators, separators=(",", ":")).encode()).hexdigest(),
    }


def holm(tails, draws):
    in_order = sorted(range(len(tails)), key=lambda i: tails[i])
    result = [0.0] * len(tails)
    running = Fraction(0)
    for j, i in enumerate(in_order):
        running = min(Fraction(1), max(running, Fraction((len(tails) - j) * (tails[i] + 1), draws + 1)))
        result[i] = float(running)
    return result


def check_registration(registered_sha):
    protocol_file = HERE / "protocol.json"
    require(digest(protocol_file) == registered_sha, "Use the protocol digest verified on GitHub")
    protocol = read_json(protocol_file)
    for path, expected in protocol["files_sha256"].items():
        require(digest(ROOT / path) == expected, "Registered file differs: " + path)
    require(np.__version__ == protocol["numpy"], "Use the frozen NumPy version")
    return protocol


def checked_input(job, protocol):
    """Bind the reproduction paths to the released R10 profile and design files."""
    source = protocol["input_commits"]
    replay = read_json(REPLAY / "analysis_config.json")
    receipt = read_json(REPLAY / "prepared_receipt.json")
    release = read_json(REPLAY / "results/release.json")
    reference_registration = read_json(REPLAY / "registration.json")
    marker = job / "aggregation_ready.json"
    require(digest(marker) == release["artifact_sha256"]["aggregation_ready.json"], "Wrong R10 completion marker")
    marker_data = read_json(marker)
    require(marker_data["stage"] == "AGGREGATION_READY" and marker_data["distinct_records"] == 12000,
            "R10 replay is not complete")

    specs = {"brazil2006": replay["reference"], **{s["slot"]: s for s in replay["targets"]}}
    require(set(specs) == {s["slot"] for s in protocol["cohorts"]}, "Missing or unregistered cohort")
    for path, expected in reference_registration["reference_files_sha256"].items():
        require(digest(job / path) == expected, "R8 reference input integrity mismatch: " + path)
    require(digest(job / source["combined_target_profile_path"]) == marker_data["profile_file_sha256"],
            "R10 target profiles changed")
    prepared = {group["slot"]: group for group in receipt["groups"]}
    for slot, spec in specs.items():
        if slot != "brazil2006":
            group = prepared[slot]
            require(digest(job / spec["input_seal"]) == group["seal_sha256"], "Prepared seal changed for " + slot)
            require(spec["profile_files"] == [source["combined_target_profile_path"]], "Wrong target profile path")
            for name, key in (
                ("birth_inputs.jsonl", "input_sha256"),
                ("birth_metadata.jsonl", "metadata_used_sha256"),
                ("sampling_manifest.json", "manifest_used_sha256"),
            ):
                require(digest(job / spec["sample_dir"] / name) == group[key], "Prepared input changed for " + slot)
    return specs


def rows_and_profiles(job, spec, cohort):
    rows, manifest, values, weights, _, _, provenance = load_profiles(
        job / spec["sample_dir"], [job / path for path in spec["profile_files"]])
    require(len(rows) == 2000 and values.min() >= 0 and values.max() <= 1, "Incomplete cohort")
    require(all(r["birth_country"] == cohort["country"] and int(r["birth_local"][:4]) == cohort["birth_year"]
                for r in rows), "Cohort identity mismatch")
    require(len({r["stratum_id"] for r in rows}) == len(manifest["strata"]), "Unmatched sampling strata")
    return rows, values, weights, provenance


def analyze(job, protocol, registration_sha):
    specs = checked_input(job, protocol)
    previous = read_json(REPLAY / "results/structural_comparison.json")
    original = {"brazil2006": previous["reference"], **{row["slot"]: row for row in previous["targets"]}}
    output, exact_values = [], {}
    frozen_ref = None
    for cohort in protocol["cohorts"]:
        slot = cohort["slot"]
        rows, scores, weights, provenance = rows_and_profiles(job, specs[slot], cohort)
        if slot == "brazil2006":
            frozen_ref = PrecisionReference(scores, weights, [Fraction(row["N_h"], row["n_h"]) for row in rows])
        require(frozen_ref is not None, "The fixed Brazil 2006 reference must appear first")
        flags = frozen_ref.flags(scores)
        cells = assemble_cells(rows, flags, "quarter")
        observed, expected, support = summarize_cells(cells)
        require(abs(float(observed) - original[slot]["joint_rate"]) <= 2e-13, "R10 joint rate differs for " + slot)
        require(support["weight_share_by_minimum_donors"]["2"] >= protocol["minimum_quarter_support"],
                "Primary pairing has too many singleton records")
        permutation = permutation_summary(
            cells, observed, expected, protocol["draws"], cohort["seed"], protocol["audit_draws"])
        require(permutation["mean_exact_error"] <= max(5 * permutation["mean_standard_error"], 2e-13),
                "Random-pairing mean failed its analytic expectation check")
        secondary, sensitivity = {}, {}
        for resolution in ("calendar_only", "month"):
            check_observed, mean, checked_support = summarize_cells(assemble_cells(rows, flags, resolution))
            require(check_observed == observed, "Regrouping changed the observed sample")
            sensitivity[resolution] = {"expected": float(mean), "excess": float(observed - mean), **checked_support}
            secondary[resolution] = mean
        output.append({
            **cohort, "source_records": len(rows), "eligible_frame_records": provenance["eligible_frame_N"],
            "observed": float(observed), "quarter_expected": float(expected), "quarter_excess": float(observed - expected),
            "quarter_support": support, "quarter_permutations": permutation,
            "marginal_sensitivities": sensitivity,
            "flag_array_sha256": sha256(flags.tobytes()).hexdigest(),
        })
        exact_values[slot] = (observed, expected, secondary)
    adjusted = holm([r["quarter_permutations"]["two_sided_tail_including_ties"] for r in output], protocol["draws"])
    reference_observed, reference_expected, ref_secondary = exact_values["brazil2006"]
    for row, p in zip(output, adjusted, strict=True):
        slot = row["slot"]
        row["quarter_permutations"]["holm_p_for_seven_cohorts"] = p
        if slot == "brazil2006":
            continue
        observed, expected, secondary = exact_values[slot]
        raw, background = observed - reference_observed, expected - reference_expected
        row["contrast_with_brazil2006"] = {
            "observed_difference": float(raw),
            "quarter_expected_difference": float(background),
            "quarter_excess_difference": float(raw - background),
            "observed_R10_seven_slot_adjusted_interval": original[slot]["sampling_interval"]["delta_joint_family_adjusted_interval"],
            "sensitivity": {
                res: {"expected_difference": float(value - ref_secondary[res]),
                      "excess_difference": float(raw - (value - ref_secondary[res]))}
                for res, value in secondary.items()
            },
        }
    return {
        "id": protocol["id"], "registration_sha256": registration_sha, "numpy": np.__version__,
        "reference_profile_sha256": previous["reference"]["provenance"]["profile_files"][0]["sha256"],
        "target_profile_sha256": previous["targets"][0]["provenance"]["profile_files"][0]["sha256"],
        "retrospective": True, "observed_event_outcomes": False, "cohorts": output,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True, help="Private R10 job with prepared profiles and reference")
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = check_registration(args.registration_sha256)
    calibration = read_json(args.calibration)
    require(calibration["id"] == protocol["id"] and calibration["status"] == "passed"
            and calibration["registration_sha256"] == args.registration_sha256, "Synthetic gate has not passed")
    require(not args.output.exists(), "Choose a new output filename")
    result = analyze(args.job, protocol, args.registration_sha256)
    result["calibration_sha256"] = digest(args.calibration)
    write_json(args.output, result)
    print(f"Computed all {len(result['cohorts'])} registered cohorts.")


if __name__ == "__main__":
    main()
