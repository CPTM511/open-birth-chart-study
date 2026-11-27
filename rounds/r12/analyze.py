"""Analyze the prespecified held-out comparison and the two registration sensitivities."""
import argparse
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import math
from pathlib import Path

import numpy as np

from study import REPLAY, R11, checked_historical, checked_samples, digest, read_json, read_registration, require, write_json
from analyze_cohorts import load_profiles
from calendar_controls import assemble_cells, permutation_summary, summarize_cells
from precision_reference import PrecisionReference


@dataclass
class Sample:
    rows: list
    scores: np.ndarray
    weights: np.ndarray
    strata: np.ndarray
    frame: dict


def load_sample(directory, profiles):
    rows, _, scores, weights, strata, frame, _ = load_profiles(directory, [profiles])
    return Sample(rows, scores, weights, strata, frame)


def checked_data(job, r10_job, registration, reg_sha, input_sha):
    require(np.__version__ == registration["analysis"]["numpy"], "Use the registered NumPy version")
    directories = checked_samples(job, registration, reg_sha, input_sha)
    marker = read_json(job / "aggregation_ready.json")
    require(marker["stage"] == "AGGREGATION_READY" and marker["registration_sha256"] == reg_sha
            and marker["prepared_receipt_sha256"] == input_sha, "Unexpected scoring receipt")
    expected = {k: s["sample_n"] for k, s in registration["samples"].items()}
    require(marker["counts_by_sample"] == expected, "The required samples are incomplete")
    profiles = job / "profiles/baseline_profiles.jsonl"
    require(digest(profiles) == marker["profiles_sha256"], "New profiles differ from scored receipt")
    historical = checked_historical(r10_job)
    samples = {slot: load_sample(*pair) for slot, pair in historical.items()}
    for slot, path in directories.items():
        samples[slot] = load_sample(path, profiles)
    return samples, marker


def frame_bootstrap(hits, strata, frame, *, seed, draws):
    """Resample n_h whole rows by integer index then rescale each stratum."""
    total = sum(frame.values())
    result = np.zeros(draws)
    mean_terms, variance_terms = [], []
    for i, (stratum, size) in enumerate(sorted(frame.items())):
        counts = hits[strata == stratum]
        n = len(counts)
        require(1 <= n <= size, "Invalid eligible/sample stratum size")
        center = int(counts.sum()) / (n * 40)
        mass = size / total
        mean_terms.append(mass * center)
        if n == size:
            result += mass * center
            continue
        require(n >= 2, "Sampling variance of non-census singleton is undefined")
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, i])))
        selected = rng.integers(0, n, size=(draws, n), dtype=np.int32)
        # Integer arithmetic on the resampled record-year counts.
        average = counts[selected].sum(axis=1) / (n * 40)
        factor = math.sqrt((1 - n / size) * n / (n - 1))
        result += mass * (center + factor * (average - center))
        variance_terms.append(mass**2 * (1 - n / size) * (counts / 40).var(ddof=1) / n)
    return math.fsum(mean_terms), result, math.fsum(variance_terms)


def interval(draws):
    return np.quantile(draws, [0.025, 0.975]).tolist()


def summarize(sample, reference, flags, boot_seed, draws):
    counts = (flags.sum(axis=2) >= 3).sum(axis=1)
    point, reps, variance = frame_bootstrap(counts, sample.strata, sample.frame, seed=boot_seed, draws=draws)
    result = reference.summarize(sample.scores, sample.weights)
    require(abs(result["joint_rate"] - point) < 2e-13, "Score average and stratum estimates disagree")
    result.update(eligible_frame_records=sum(sample.frame.values()),
                  fixed_reference_conditional_95_interval=interval(reps - reference.joint_rate),
                  analytic_design_variance=variance, bootstrap_variance=float(reps.var(ddof=1)),
                  threshold_flag_sha256=sha256(flags.tobytes()).hexdigest())
    return result, reps


def calendar_check(reference_sample, target, ref_flags, flags, settings):
    published_reference = read_json(R11 / "results/calendar_controls.json")["cohorts"][0]
    results = {}
    for resolution in ("quarter", "calendar_only", "month"):
        reference_observed, reference_exp, _ = summarize_cells(assemble_cells(reference_sample.rows, ref_flags, resolution))
        cells = assemble_cells(target.rows, flags, resolution)
        observed, expected, support = summarize_cells(cells)
        published_expected = (published_reference["quarter_expected"] if resolution == "quarter"
                              else published_reference["marginal_sensitivities"][resolution]["expected"])
        require(abs(float(reference_exp) - published_expected) <= 2e-13, "R11 reference expectation mismatch")
        observed_difference, expected_difference = observed - reference_observed, expected - reference_exp
        results[resolution] = {
            "observed": float(observed),
            "expected": float(expected),
            "observed_minus_expected": float(observed - expected),
            "fixed_reference_expected": float(reference_exp),
            "observed_difference": float(observed_difference),
            "expected_difference": float(expected_difference),
            "remaining_difference": float(observed_difference - expected_difference),
            "observed_increase_half_recreated": bool(observed_difference > 0 and expected_difference * 2 >= observed_difference),
            "support": support,
        }
        if resolution == "quarter":
            permutation = permutation_summary(cells, observed, expected, settings["permutation_draws"],
                                              settings["permutation_seed"], 0)
            require(permutation["mean_exact_error"] <= max(5 * permutation["mean_standard_error"], 2e-13),
                    "Analytic expectation and permutation mean disagree")
            results[resolution]["permutation"] = permutation
            results[resolution]["registered_pairing_support_passed"] = support["weight_share_by_minimum_donors"]["2"] >= 0.95
    return results


def extended_frame(early, late, early_draws, late_draws, reference):
    n0, n1 = early["eligible_frame_records"], late["eligible_frame_records"]
    share = n1 / (n0 + n1)
    j0, j1 = early["joint_rate"], late["joint_rate"]
    expanded_draws = (1 - share) * early_draws + share * late_draws
    change_draws = share * (late_draws - early_draws)
    expanded = (1 - share) * j0 + share * j1
    return {
        "eligible_records": n0 + n1,
        "late_share": share,
        "early_joint_rate": j0,
        "late_joint_rate": j1,
        "expanded_joint_rate": expanded,
        "expanded_minus_reference": expanded - reference,
        "expanded_minus_reference_conditional_95_interval": interval(expanded_draws - reference),
        "expanded_minus_early": share * (j1 - j0),
        "expanded_minus_early_conditional_95_interval": interval(change_draws),
    }


def analyze(samples, registration):
    settings = registration["analysis"]
    r = samples["brazil2006"]
    reference = PrecisionReference(r.scores, r.weights, [Fraction(row["N_h"], row["n_h"]) for row in r.rows])
    historical = read_json(REPLAY / "results/structural_comparison.json")
    require(abs(reference.joint_rate - historical["reference"]["joint_rate"]) <= 2e-13, "Reference rate changed")
    target, all_reps = {}, {}
    for slot, seed in settings["bootstrap_seeds"].items():
        source = samples[slot]
        target[slot], all_reps[slot] = summarize(source, reference, reference.flags(source.scores), seed,
                                                 settings["bootstrap_draws"])
    early20 = next(r for r in historical["targets"] if r["slot"] == "mexico2020")
    require(abs(target["mexico2020_early"]["joint_rate"] - early20["joint_rate"]) <= 2e-13,
            "Mexico 2020 R10 original point differs")
    holdout = samples["mexico2023_early"]
    calendar = calendar_check(r, holdout, reference.flags(r.scores), reference.flags(holdout.scores), settings)
    lo, hi = target["mexico2023_early"]["fixed_reference_conditional_95_interval"]
    quarter = calendar["quarter"]
    return {
        "id": registration["id"], "numpy": np.__version__,
        "reference": {"source_records": len(r.rows), "joint_rate": reference.joint_rate},
        "sample_results": target,
        "held_out_calendar_decomposition": calendar,
        "registered_decisions": {
            "raw_held_out_increase": bool(lo > 0),
            "raw_held_out_decrease": bool(hi < 0),
            "raw_held_out_upper_below_plus_1pp": bool(hi < 0.01),
            "reproduced_raw_increase_and_majority_in_pairing_point_decomposition":
                bool(lo > 0 and quarter["registered_pairing_support_passed"] and quarter["observed_increase_half_recreated"]),
        },
        "late_registration_sensitivities": {
            str(year): extended_frame(target[a], target[b], all_reps[a], all_reps[b], reference.joint_rate)
            for year in (2020, 2023)
            for a, b in [(f"mexico{year}_early", f"mexico{year}_late")]
        },
        "draws_per_bootstrap": settings["bootstrap_draws"],
        "observed_event_outcomes": False,
    }


def add_analysis_arguments(parser):
    for name in ("job", "r10-job", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--input-sha256", required=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_analysis_arguments(parser)
    args = parser.parse_args()
    require(not args.output.exists(), "Choose a new output filename")
    registration = read_registration(args.registration_sha256)
    samples, marker = checked_data(args.job, args.r10_job, registration, args.registration_sha256, args.input_sha256)
    result = analyze(samples, registration)
    result.update(registration_sha256=args.registration_sha256, input_sha256=args.input_sha256,
                  new_profiles_sha256=marker["profiles_sha256"])
    write_json(args.output, result)
    print("Computed the held-out comparison, three matching definitions and both registration sensitivities.")


if __name__ == "__main__":
    main()
