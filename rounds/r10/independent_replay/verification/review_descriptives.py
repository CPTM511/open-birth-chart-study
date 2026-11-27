# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify the descriptive fields in the reported reference and six target rows.

The mean fixed-reference percentile is an ordering probability. This executable
sorts the *target* scores and evaluates the fraction above each reference
score, giving half weight to ties. It shares the separate refit verifier's
input parser and exact cutoff routine only.
"""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path

import numpy as np

from review_refits import Cohort, Cutoff, R10, digest, integer_weights, load_cohort, require


def probability_target_above_reference(ref, sample, ref_weight, sample_weight):
    values = sample.ravel()
    order = np.argsort(values, kind="stable")
    ordered = values[order]
    prefix = np.r_[0, np.cumsum(np.repeat(sample_weight, sample.shape[1])[order])]
    low = np.searchsorted(ordered, ref, side="left")
    high = np.searchsorted(ordered, ref, side="right")
    # All target values above r count fully; ties with r receive one half.
    target_fraction = 1 - (prefix[low] + prefix[high]) / (2 * prefix[-1])
    return float(np.dot(ref_weight, target_fraction.mean(axis=1)) / ref_weight.sum())


def describe(reference, sample):
    ref, scores = reference.scores, sample.scores
    rw, weights = reference.weights, sample.weights
    rational = integer_weights(reference.exact)
    total = 10 * sum(rational)
    raw = np.array([math.fsum(np.mean(scores[:, :, s], axis=1) * weights) /
                    math.fsum(weights) for s in range(4)])
    means_by_band = np.zeros((4, 4))
    band_joint = np.zeros(4)
    for band in range(4):
        age = slice(10 * band, 10 * (band + 1))
        flags = np.zeros((len(scores), 10), dtype=np.uint8)
        for system in range(4):
            r = ref[:, age, system]
            x = scores[:, age, system]
            means_by_band[band, system] = probability_target_above_reference(r, x, rw, weights)
            value, inclusive = Cutoff(r).find(rw, rational, total)
            flags += (x >= value) if inclusive else (x > value)
        band_joint[band] = math.fsum(weights * np.mean(flags >= 3, axis=1)) / math.fsum(weights)
    return raw, means_by_band.mean(axis=0), band_joint


def inspect(config, primary):
    frozen = json.loads((R10 / "protocol.json").read_text())
    reference, _ = load_cohort(config["reference"], "reference", frozen)
    ref_raw, ref_levels, ref_by_age = describe(reference, reference)
    ref_joint = float(ref_by_age.mean())
    rows = {x["slot"]: x for x in primary["targets"]}
    checks = []

    def verify(slot, reported, raw, levels, bands):
        joint = float(bands.mean())
        independently_computed = {
            "raw_system_means": raw, "delta_raw_system_means": raw-ref_raw,
            "fixed_reference_system_means": levels, "delta_fixed_reference_system_means": levels-.5,
            "delta_L": float(levels.mean()-.5), "age_band_joint_rates": bands,
            "joint_rate": joint, "reference_joint_rate": ref_joint, "delta_joint_rate": joint-ref_joint,
        }
        for key, actual in independently_computed.items():
            a, b = np.asarray(actual), np.asarray(reported[key])
            require(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), slot + "." + key)
            difference = float(np.max(np.abs(a-b)))
            checks.append({"slot": slot, "field": key, "cells": int(a.size), "absolute_difference": difference,
                           "pass": difference <= 2e-12})

    verify("reference", primary["reference"], ref_raw, ref_levels, ref_by_age)
    require(len(rows) == len(primary["targets"]) == len(config["targets"]) == 6, "Six target cohorts required")
    for source in config["targets"]:
        name = source["slot"]
        rule = next(s for s in frozen["source_slots"] if s["id"] == name)
        sample, _ = load_cohort(source, name, frozen, rule)
        verify(name, rows[name], *describe(reference, sample))
    failed = sum(not c["pass"] for c in checks)
    return {"status": "mismatch" if failed else "passed",
            "scope": "Top-level joint and band rates, raw and transformed system means and differences. Reverse pairwise ordering calculation for transformed means; shares input parser and exact cutoff with independent refit review.",
            "tolerance": 2e-12, "field_groups": len(checks), "scalar_values": sum(c["cells"] for c in checks),
            "failure_count": failed, "max_abs_difference": max(c["absolute_difference"] for c in checks), "checks": checks}


def self_test():
    r = np.array([[0., .5, 1.], [.3, .5, .5]])
    x = np.array([[.2, .5, 1.], [0., .1, 1.], [.25, .7, .99]])
    rw, tw = np.array([1., 2.]), np.array([2., 3., 1.])
    oracle = sum(Fraction(int(rw[i] * tw[j]), 2) * (2 * int(a < b) + int(a == b))
                 for i, rr in enumerate(r) for a in rr for j, xx in enumerate(x) for b in xx)
    oracle /= int(r.shape[1] * x.shape[1] * rw.sum() * tw.sum())
    require(abs(probability_target_above_reference(r,x,rw,tw)-float(oracle)) < 1e-15, "Pair-count oracle")
    rows = [{"stratum": "S", "weight": Fraction(1)} for _ in range(5)]
    synthetic = Cohort(rows, np.repeat(np.array([0., 0., 0., 1., 1.])[:,None,None], 160,
                                       axis=1).reshape(-1,40,4), {"S": (5,5)})
    raw, levels, bands = describe(synthetic, synthetic)
    np.testing.assert_allclose(raw, [.4]*4)
    np.testing.assert_allclose(levels, [.5]*4)
    np.testing.assert_allclose(bands, [.4]*4)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--self-test", action="store_true")
    cli.add_argument("--aggregation-ready", action="store_true")
    cli.add_argument("--config", type=Path)
    cli.add_argument("--primary-result", type=Path)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if args.self_test:
        self_test()
        print("Synthetic direct pair-count and exact threshold checks passed.")
        return
    if not args.aggregation_ready or not __debug__ or not all((args.config,args.primary_result,args.output)):
        cli.error("Require AGGREGATION_READY, the config, primary result, output path and enabled assertions")
    require(not args.output.exists(), "Preserve previous review output")
    config, primary = [json.loads(p.read_text()) for p in (args.config, args.primary_result)]
    require(primary["analysis_config_sha256"] == digest(args.config), "Wrong result/config pairing")
    report = inspect(config, primary)
    report["input_hashes"] = {"config": digest(args.config), "primary": digest(args.primary_result),
                              "reviewer": digest(__file__), "cutoff_and_input_interface": digest(Path(__file__).with_name("review_refits.py"))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as f:
        json.dump(report, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({k:report[k] for k in ["status","field_groups","scalar_values","failure_count"]}))
    if report["failure_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
