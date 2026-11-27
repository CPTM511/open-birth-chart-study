# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent replay of the complete R10 common-reference sensitivity distribution.

The primary implementation transforms each query through a weighted CDF. This
implementation finds one exact inclusive or exclusive cutoff for each of the
16 age-band/system combinations, and compares the raw scores to that cutoff.
Input parsing is shared with the independent R10 fixed-reference verifier.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

R10 = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R10 / "verification"))
from verify_aggregates import digest, source_data


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer_weights(values):
    """Use an exact common denominator, including for binary floating draws."""
    ratios = [value.as_integer_ratio() for value in values]
    denominator = math.lcm(*(den for _, den in ratios))
    return np.array([num * (denominator // den) for num, den in ratios], dtype=object)


class Cutoff:
    def __init__(self, values):
        self.raw = np.ascontiguousarray(values)
        order = np.argsort(values, axis=None, kind="stable")
        self.record = order // values.shape[1]
        self.ordered = values.ravel()[order]
        self.support = np.unique(self.ordered)
        self.multiplicities = {}

    def find(self, design_float, design_int, total):
        """Floating lookup locates a candidate; exact masses decide all flags."""
        prefix = np.cumsum(design_float[self.record])
        ix = min(np.searchsorted(prefix, 0.8 * prefix[-1]), len(prefix) - 1)
        index = np.searchsorted(self.support, self.ordered[ix])
        while 0 <= index < len(self.support):
            value = self.support[index]
            if index not in self.multiplicities:
                self.multiplicities[index] = (
                    np.count_nonzero(self.raw < value, axis=1).astype(np.uint8),
                    np.count_nonzero(self.raw == value, axis=1).astype(np.uint8),
                )
            lower_counts, equal_counts = self.multiplicities[index]
            lower = lower_counts @ design_int
            equal = equal_counts @ design_int
            # Choose the first actual reference value whose upper CDF reaches 4/5.
            if 5 * lower >= 4 * total:
                index -= 1
            elif 5 * (lower + equal) < 4 * total:
                index += 1
            else:
                return value, 5 * (2 * lower + equal) >= 8 * total
        raise ArithmeticError("No reference cutoff brackets 4/5")


class Cohort:
    def __init__(self, rows, scores, frame):
        self.scores = scores
        self.exact = [row["weight"] for row in rows]
        self.weights = np.array([float(w) for w in self.exact])
        labels = np.array([row["stratum"] for row in rows])
        self.groups = []
        for key, (population, n) in sorted(frame.items()):
            ids = np.flatnonzero(labels == key)
            require(len(ids) == n and 0 < n <= population, "Invalid sampling stratum")
            if n == population:
                continue
            require(n > 1, "Noncensus singleton cannot supply a reference-refit draw")
            root = math.sqrt(1 - n / population)
            self.groups.append((ids, n, np.repeat(1.0 / n, n), root))

    def draw(self, rng):
        weights = self.weights.copy()
        for ids, n, probabilities, root in self.groups:
            multiplicity = rng.multinomial(n - 1, probabilities)
            scale = root * n / (n - 1)
            weights[ids] = self.weights[ids] * ((1 - root) + scale * multiplicity)
        return weights


class Rates:
    def __init__(self, reference, target_scores):
        scores = np.concatenate([reference, *target_scores])
        self.values = np.ascontiguousarray(scores.reshape(-1, 4, 10, 4).transpose(1, 3, 0, 2))
        self.cutoffs = [
            [Cutoff(reference[:, band * 10:band * 10 + 10, system]) for system in range(4)]
            for band in range(4)
        ]
        self.boundaries = np.cumsum([len(reference), *map(len, target_scores)])[:-1]

    def counts(self, reference_weights, exact_weights):
        integers = integer_weights(exact_weights)
        total = 10 * sum(integers)
        counts = np.zeros(self.values.shape[2], dtype=np.uint8)
        for band, tables in enumerate(self.cutoffs):
            flags = np.zeros(self.values.shape[2:], dtype=np.uint8)
            for system, cutoff in enumerate(tables):
                value, inclusive = cutoff.find(reference_weights, integers, total)
                x = self.values[band, system]
                flags += (x >= value) if inclusive else (x > value)
            counts += np.count_nonzero(flags >= 3, axis=1).astype(np.uint8)
        return np.split(counts, self.boundaries)


def rate(counts, weights):
    return float(np.dot(weights, counts) / (40 * weights.sum()))


def percentiles(observations):
    """The registered linear quantile interpolation, applied to sorted draws."""
    ordered = sorted(observations)
    result = []
    for fraction in (0.025, 0.975):
        index = (len(ordered) - 1) * fraction
        low, high = math.floor(index), math.ceil(index)
        result.append(float(ordered[low] + (index - low) * (ordered[high] - ordered[low])))
    return result


def variance(values):
    mean = math.fsum(values) / len(values)
    return math.fsum((x - mean) ** 2 for x in values) / (len(values) - 1)


def replay(reference, targets, draws, reference_seed, target_seeds):
    names = sorted(targets)
    calculator = Rates(reference.scores, [targets[name].scores for name in names])
    fixed = calculator.counts(reference.weights, reference.exact)
    baseline = rate(fixed[0], reference.weights)
    ref_rng = np.random.default_rng(reference_seed)
    target_rng = {name: np.random.default_rng(target_seeds[name]) for name in names}
    reference_draws = []
    full, static = ({name: [] for name in names} for _ in range(2))
    for _ in range(draws):
        weights = reference.draw(ref_rng)
        counts = calculator.counts(weights, weights)
        refitted = rate(counts[0], weights)
        reference_draws.append(refitted)
        fixed_sampled = rate(fixed[0], weights)
        for i, name in enumerate(names, start=1):
            weight = targets[name].draw(target_rng[name])
            full[name].append(rate(counts[i], weight) - refitted)
            static[name].append(rate(fixed[i], weight) - fixed_sampled)
    result = {}
    for i, name in enumerate(names, start=1):
        result[name] = {
            "point_delta_joint_rate": rate(fixed[i], targets[name].weights) - baseline,
            "full_reference_refit_percentile_range95": percentiles(full[name]),
            "full_reference_refit_mean": math.fsum(full[name]) / draws,
            "full_reference_refit_variance": variance(full[name]),
            "fixed_CDF_two_sample_percentile_range95": percentiles(static[name]),
            "fixed_CDF_two_sample_variance": variance(static[name]),
        }
    return percentiles(reference_draws), result


def load_cohort(spec, slot, protocol, rule=None):
    rows, scores, _, frame, provenance = source_data(spec, slot, protocol, rule)
    if slot != "reference":
        decision = next(x for x in json.loads((R10 / "source_decisions.json").read_text())["source_slots"] if x["id"] == slot)
        orig_manifest = (R10 / "brazil/audits" / f"brazil{decision['birth_year']}_sampling_manifest.json"
                         if decision["country"] == "BR" else R10 / "mexico/samples" / slot / "sampling_manifest.json")
        require(digest(orig_manifest) == decision["sampling_manifest_sha256"], "Original design manifest has changed")
        orig = json.loads(orig_manifest.read_text())
        original_frame = {s["stratum_id"]: (s["N_h"], s["n_h"]) for s in orig["strata"]}
        require(frame == original_frame, f"Stratum population/sample sizes differ for {slot}")
        require(provenance["input_sha256"] == decision["input_sha256"], f"Frozen scored inputs differ for {slot}")
        provenance["original_frame_and_model_inputs_match"] = True
    return Cohort(rows, scores, frame), provenance


def review(config, primary):
    frozen = json.loads((R10 / "protocol.json").read_text())
    protocol = json.loads(Path(config["protocol"]).read_text())
    decisions = json.loads((R10 / "source_decisions.json").read_text())["source_slots"]
    available = {d["id"] for d in decisions if d["status"] == "available"}
    require(len(decisions) == 7 and len(available) == 6, "Expected six eligible slots in a seven-slot family")
    require(primary["primary_draws"] == protocol["inference"]["primary_draws"] == 9999 and
            primary["primary_family_size"] == protocol["inference"]["family_size"] == 7, "Primary family or draws changed")
    spec = frozen["reference_stability_sensitivity"]
    require(spec["draws"] == protocol["reference_stability_sensitivity"]["draws"] == 999, "Unexpected refit draw count")
    require(spec["seed"] == protocol["reference_stability_sensitivity"]["seed"], "Unexpected refit seed")
    seeds = {slot["id"]: spec["seed"] + 1 + i for i, slot in enumerate(frozen["source_slots"]) if slot["id"] in available}
    rule = {s["id"]: s for s in frozen["source_slots"]}
    declared = primary["reference_refit_sensitivity"]
    require(declared["status"] == "computed_exploratory_sensitivity" and declared["draws"] == spec["draws"] and
            declared["reference_seed"] == spec["seed"] and declared["target_seeds"] == seeds and
            not declared["unavailable_targets"] and declared["reference_draw_shared_across_targets"] is True and
            declared["reference_CDF_refitted_each_draw"] is True, "Unexpected sensitivity specification or unavailable slot")
    offered = {s["slot"]: s for s in declared["targets"]}
    require(len(offered) == len(declared["targets"]) == 6 and set(offered) == available, "Sensitivity results incomplete")
    require(len(config["targets"]) == 6 and {s["slot"] for s in config["targets"]} == available, "Incomplete design")
    ref, ref_provenance = load_cohort(config["reference"], "reference", protocol)
    targets, provenance = {}, {"reference": ref_provenance}
    for s in config["targets"]:
        slot = s["slot"]
        rule_for_slot = dict(rule[slot])
        if not rule_for_slot.get("source_label"):
            rule_for_slot["source_label"] = next(d["source_label"] for d in decisions if d["id"] == slot)
        targets[slot], provenance[slot] = load_cohort(s, slot, protocol, rule_for_slot)
    ref_range, summaries = replay(ref, targets, spec["draws"], spec["seed"], seeds)
    checks = []

    def check(label, actual, expected):
        a, b = np.asarray(actual), np.asarray(expected)
        require(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), "Invalid fields: " + label)
        tolerance = 2e-14 if "variance" in label else 2e-12
        difference = float(np.max(np.abs(a - b)))
        checks.append({"field": label, "absolute_difference": difference, "tolerance": tolerance,
                       "pass": difference <= tolerance})

    check("reference.refit_range95", ref_range, declared["full_refit_reference_joint_percentile_range95"])
    for slot, stats in summaries.items():
        for key, actual in stats.items():
            check(slot + "." + key, actual, offered[slot][key])
    return {"created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "passed" if all(c["pass"] for c in checks) else "mismatch",
            "draws_per_target": spec["draws"], "common_reference_draws": spec["draws"], "target_draws_total": 6 * spec["draws"],
            "reference_j_range95": ref_range, "independently_recomputed": summaries,
            "checks": checks, "failure_count": sum(not c["pass"] for c in checks), "scope": {
                "independent": "Exact integer 4/5 crossing from sorted observations; single inclusive/exclusive boundary per age band/system; whole-record joint counts; separate stratum sampler, percentile interpolation and variance.",
                "shared": "Frozen score files, design manifests, NumPy PCG64/multinomial stream, and input reader from the other independent R10 verifier. The score engines were not reimplemented.",
                "interpretation": "Internal computational replication. The empirical refit range has no calibrated probability interpretation for any real-world event."},
            "sample_provenance": provenance, "numpy": np.__version__}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--aggregation-ready", action="store_true")
    cli.add_argument("--config", type=Path, required=True)
    cli.add_argument("--primary-result", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    if not args.aggregation_ready or not __debug__:
        cli.error("Require AGGREGATION_READY and a Python runtime with assertions enabled")
    if args.output.exists():
        raise FileExistsError(args.output)
    config, primary = [json.loads(p.read_text()) for p in (args.config, args.primary_result)]
    require(primary["analysis_config_sha256"] == digest(args.config), "Result/config mismatch")
    out = review(config, primary)
    out["hashes"] = {key: digest(path) for key, path in {
        "analysis_config": args.config, "primary_result": args.primary_result, "verifier": __file__,
        "shared_input_reader": R10 / "verification/verify_aggregates.py"}.items()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as f:
        json.dump(out, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({key: out[key] for key in ("status", "draws_per_target", "failure_count")}))
    if out["failure_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
