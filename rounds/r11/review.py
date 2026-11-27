"""Independently recompute the calendar-control aggregates and every draw."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
from math import lcm
from pathlib import Path
from statistics import mean
import sys

import numpy as np

from calendar_controls import R10, check_registration, checked_input, digest, read_json, require, write_json

sys.path.insert(0, str(R10 / "verification"))
from verify_aggregates import RawSortedReference, jsonl, source_data

BYTE_COUNTS = np.array([i.bit_count() for i in range(256)], dtype=np.int64)


def form_groups(rows, months, flags, divisor):
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        season = (months[row["id"]] - 1) // divisor if divisor else 0
        groups[(row["stratum"], row["years"][0], season)].append(i)
    return [(flags[ix], rows[ix[0]]["weight"]) for key, ix in sorted(groups.items())]


def deterministic_rates(groups):
    people = sum(len(flags) * weight for flags, weight in groups)
    ages = groups[0][0].shape[1]
    observed = sum(int((matrix.sum(axis=2) >= 3).sum()) * weight for matrix, weight in groups)
    expectation = Fraction(0)
    for matrix, weight in groups:
        n = len(matrix)
        for marginals in matrix.sum(axis=0).tolist():
            all_positive = 1
            for value in marginals:
                all_positive *= value
            ways = all_positive
            for signs in product((False, True), repeat=4):
                if sum(signs) != 3:
                    continue
                favorable = 1
                for k, high in zip(marginals, signs, strict=True):
                    favorable *= k if high else n - k
                ways += favorable
            expectation += weight * Fraction(ways, n**3)
    return observed / (people * ages), expectation / (people * ages)


def replay_draws(groups, draws, seed):
    denominator_weights = lcm(*(w.denominator for _, w in groups))
    all_draws = [0] * draws
    denominator = 0
    for index, (flags, weight) in enumerate(groups):
        n, ages, _ = flags.shape
        w = int(weight * denominator_weights)
        denominator += w * n * ages
        packed = np.packbits(flags, axis=1)
        systems = [packed[None, :, :, 0]]
        for s in range(1, 4):
            generator = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, index, s])))
            ordering = np.tile(np.arange(n, dtype=np.int32), (draws, 1))
            generator.permuted(ordering, axis=1, out=ordering)
            systems.append(packed[ordering, :, s])
        a, b, c, d = systems
        joint = (a & b & c) | (a & b & d) | (a & c & d) | (b & c & d)
        counts = BYTE_COUNTS[joint].sum(axis=(1, 2)).tolist()
        all_draws = [old + w * now for old, now in zip(all_draws, counts, strict=True)]
    return all_draws, denominator


def review(job, protocol, result):
    specs = checked_input(job, protocol)
    r10_protocol = read_json(R10 / "protocol.json")
    anchor = None
    reviewed, raw_p, exact = [], [], {}

    def near(a, b, key):
        require(abs(float(a) - b) <= 2e-13, "Numeric mismatch: " + key)

    require([r["slot"] for r in result["cohorts"]] == [r["slot"] for r in protocol["cohorts"]],
            "Cohort ordering changed")
    for registered, published in zip(protocol["cohorts"], result["cohorts"], strict=True):
        slot, seed = registered["slot"], registered["seed"]
        spec = dict(specs[slot])
        spec["sample_dir"] = job / spec["sample_dir"]
        spec["profile_files"] = [job / p for p in spec["profile_files"]]
        if "input_seal" in spec:
            spec["input_seal"] = job / spec["input_seal"]
        rows, scores, _, _, _ = source_data(
            spec, "reference" if slot == "brazil2006" else slot, r10_protocol,
            {"allowed_birth_years": [registered["birth_year"]], "expected_country": registered["country"]})
        if slot == "brazil2006":
            anchor = RawSortedReference(rows, scores)
        _, flags, cdf_checks = anchor.apply(scores)
        require(sha256(flags.tobytes()).hexdigest() == published["flag_array_sha256"], "Threshold flags differ: " + slot)
        months = {r["study_id"]: date.fromisoformat(r["birth_local"][:10]).month
                  for r in jsonl(spec["sample_dir"] / "birth_inputs.jsonl")}
        means = {}
        for key, divisor in (("quarter", 3), ("calendar_only", 0), ("month", 1)):
            cells = form_groups(rows, months, flags, divisor)
            obs, exp = deterministic_rates(cells)
            means[key] = exp
            near(obs, published["observed"], slot)
            bucket = published["marginal_sensitivities"].get(key, {})
            near(exp, bucket["expected"] if bucket else published["quarter_expected"], slot)
            near(obs - exp, bucket["excess"] if bucket else published["quarter_excess"], slot)
            if key != "quarter":
                continue
            nums, denom = replay_draws(cells, protocol["draws"], seed)
            perm = published["quarter_permutations"]
            require(str(denom) == perm["draw_numerator_denominator"], "Permutation weights differ: " + slot)
            for values, label in ((nums, "full_draw_numerators_sha256"),
                                  (nums[:protocol["audit_draws"]], "first_draw_numerators_sha256")):
                require(sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest() == perm[label],
                        "Permuted draw digest differs: " + slot)
            centered = [abs(Fraction(n, denom) - exp) for n in nums]
            tail = sum(value >= abs(obs - exp) for value in centered)
            require(tail == perm["two_sided_tail_including_ties"], "Permutation tail differs: " + slot)
            independence_p = Fraction(tail + 1, len(nums) + 1)
            near(independence_p, perm["p"], slot)
            raw_p.append(independence_p)
            near(Fraction(sum(nums), denom * len(nums)), perm["simulated_mean"], slot)
            for a, b in zip(np.quantile([n / denom for n in nums], [0.025, 0.975]), perm["conditional_range95"], strict=True):
                near(a, b, slot)
        exact[slot] = obs, means
        reviewed.append({"slot": slot, "threshold_cells": int(flags.size), "replayed_draws": protocol["draws"],
                         "all_draws_match": True, "independent_threshold_path": cdf_checks})
    ordered = sorted(raw_p)
    ref, ref_means = exact["brazil2006"]
    for row, p in zip(result["cohorts"], raw_p, strict=True):
        adjusted = min(Fraction(1), max((len(ordered) - n) * v for n, v in enumerate(ordered) if v <= p))
        near(adjusted, row["quarter_permutations"]["holm_p_for_seven_cohorts"], row["slot"])
        if row["slot"] == "brazil2006":
            continue
        obs, means = exact[row["slot"]]
        comparison = row["contrast_with_brazil2006"]
        near(obs - ref, comparison["observed_difference"], row["slot"])
        for key in ("quarter", "calendar_only", "month"):
            delta = means[key] - ref_means[key]
            if key == "quarter":
                b, residual = comparison["quarter_expected_difference"], comparison["quarter_excess_difference"]
            else:
                branch = comparison["sensitivity"][key]
                b, residual = branch["expected_difference"], branch["excess_difference"]
            near(delta, b, row["slot"])
            near((obs - ref) - delta, residual, row["slot"])
    return {"status": "passed", "cohorts": reviewed,
            "scope": "Separate R10 input and threshold implementation, exact pattern probabilities and byte counting. "
                     "Shares input files, registered pairing strata, NumPy and seeds. Internal computational verification."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = check_registration(args.registration_sha256)
    require(not args.output.exists(), "Choose a new output filename")
    result = read_json(args.result)
    require(result["registration_sha256"] == args.registration_sha256, "Wrong review input")
    receipt = review(args.job, protocol, result)
    receipt["registration_sha256"] = args.registration_sha256
    receipt["result_sha256"] = digest(args.result)
    write_json(args.output, receipt)
    print(f"Verified the flags and all draws for {len(receipt['cohorts'])} cohorts.")


if __name__ == "__main__":
    main()
