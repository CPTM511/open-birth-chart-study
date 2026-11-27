"""Alternate arithmetic for the R12 threshold, bootstrap and matching results."""
import argparse
from collections import defaultdict
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from statistics import quantiles
import sys

import numpy as np

from analyze import add_analysis_arguments, checked_data
from study import R10, digest, read_json, read_registration, require, write_json
from review import deterministic_rates, form_groups, replay_draws  # R11 independent arithmetic

sys.path.insert(0, str(R10 / "verification"))
from verify_aggregates import RawSortedReference


def replay_bootstrap(whole_record_counts, sample, seed, draws):
    strata = defaultdict(list)
    for row, count in zip(sample.rows, whole_record_counts, strict=True):
        strata[row["stratum_id"]].append(int(count))
    population = sum(sample.frame.values())
    total_point, total_variance = Fraction(0), Fraction(0)
    simulated = np.zeros(draws)
    for index, h in enumerate(sorted(strata)):
        counts = np.array(strata[h], dtype=np.int64)
        n, size = len(counts), sample.frame[h]
        mass = Fraction(size, population)
        mean = Fraction(int(counts.sum()), n * 40)
        total_point += mass * mean
        simulated += float(mass * mean)
        if n == size:
            continue
        correction = Fraction(size - n, size)
        sum_square = (sum(int(x)**2 for x in counts) * n - int(counts.sum())**2)
        total_variance += (mass**2 * correction * Fraction(sum_square, n**2 * (n - 1) * 1600))
        factor = sqrt(float(correction * Fraction(n, n - 1)))
        stream = np.random.PCG64(np.random.SeedSequence([seed, index]))
        rng = np.random.Generator(stream)
        indices = rng.integers(n, size=(draws, n), dtype=np.int32)
        frequencies = np.asarray([np.bincount(draw, minlength=n) for draw in indices])
        delta = frequencies @ counts - int(counts.sum())
        simulated += (float(mass) * factor / (n * 40)) * delta
    return total_point, simulated, total_variance


def review(samples, result, registration):
    checks, errors = 0, []

    def compare(values, expected):
        nonlocal checks
        err = np.abs(np.asarray(values, dtype=float) - np.asarray(expected, dtype=float))
        max_error = float(err.max())
        require(max_error <= 2e-12, f"Independent computation differs by {max_error}")
        errors.append(max_error)
        checks += int(err.size)

    def compare_bounds(draws, published):
        q = quantiles(draws.tolist(), n=40, method="inclusive")
        compare([q[0], q[-1]], published)

    def row_view(sample):
        return [{"id": row["study_id"], "stratum": row["stratum_id"], "years": row["calendar_years"],
                 "weight": Fraction(row["N_h"], row["n_h"])} for row in sample.rows]

    def month_view(sample):
        return {row["study_id"]: date.fromisoformat(row["birth_local"][:10]).month for row in sample.rows}

    settings = registration["analysis"]
    reference = samples["brazil2006"]
    anchor = RawSortedReference(row_view(reference), reference.scores)
    _, flags_ref, _ = anchor.apply(reference.scores)
    reference_count = np.count_nonzero(flags_ref.sum(axis=2) >= 3, axis=1)
    j_ref = sum(Fraction(int(count) * row["N_h"], 40 * row["n_h"])
                for row, count in zip(reference.rows, reference_count, strict=True)) / sum(reference.frame.values())
    compare(j_ref, result["reference"]["joint_rate"])
    observed, replicates = {}, {}
    flag_cells = int(flags_ref.size)
    primary_flags = None
    for slot, seed in settings["bootstrap_seeds"].items():
        sample = samples[slot]
        transformed, flags, _ = anchor.apply(sample.scores)
        flag_cells += int(flags.size)
        hits = np.count_nonzero(flags.sum(axis=2) >= 3, axis=1)
        pub = result["sample_results"][slot]
        require(sha256(flags.tobytes()).hexdigest() == pub["threshold_flag_sha256"], "Threshold markings differ")
        j, draws, var = replay_bootstrap(hits, sample, seed, settings["bootstrap_draws"])
        compare([j, j - j_ref, var, draws.var(ddof=1)],
                [pub["joint_rate"], pub["delta_joint_rate"], pub["analytic_design_variance"], pub["bootstrap_variance"]])
        compare(np.average(transformed.mean(axis=1), weights=sample.weights, axis=0), pub["fixed_reference_system_means"])
        compare(np.average(sample.scores.mean(axis=1), weights=sample.weights, axis=0), pub["raw_system_means"])
        compare_bounds(draws - float(j_ref), pub["fixed_reference_conditional_95_interval"])
        observed[slot], replicates[slot] = j, draws
        if slot == "mexico2023_early":
            primary_flags = flags
    require(primary_flags is not None, "Primary sample was not reviewed")

    primary = samples["mexico2023_early"]
    comparison = result["held_out_calendar_decomposition"]
    for label, months in (("quarter", 3), ("calendar_only", 0), ("month", 1)):
        ref_groups = form_groups(row_view(reference), month_view(reference), flags_ref, months)
        groups = form_groups(row_view(primary), month_view(primary), primary_flags, months)
        ref, expected_ref = deterministic_rates(ref_groups)
        obs, expected = deterministic_rates(groups)
        pub = comparison[label]
        compare([obs, expected, obs - expected, expected_ref, obs - ref, expected - expected_ref,
                 (obs - ref) - (expected - expected_ref)],
                [pub["observed"], pub["expected"], pub["observed_minus_expected"], pub["fixed_reference_expected"],
                 pub["observed_difference"], pub["expected_difference"], pub["remaining_difference"]])
        if label == "quarter":
            nums, denom = replay_draws(groups, settings["permutation_draws"], settings["permutation_seed"])
            encoded = json.dumps(nums, separators=(",", ":")).encode()
            perm = pub["permutation"]
            require(sha256(encoded).hexdigest() == perm["full_draw_numerators_sha256"], "Permutations differ")
            threshold = abs(obs - expected)
            tail = sum(abs(Fraction(num, denom) - expected) >= threshold for num in nums)
            require(tail == perm["two_sided_tail_including_ties"], "Permutation tail differs")
            compare((tail + 1) / (len(nums) + 1), perm["p"])
            compare_bounds(np.array(nums, dtype=object) / denom, perm["conditional_range95"])

    for year in (2020, 2023):
        first, second = f"mexico{year}_early", f"mexico{year}_late"
        n, m = sum(samples[first].frame.values()), sum(samples[second].frame.values())
        share = Fraction(m, n + m)
        average = (n * observed[first] + m * observed[second]) / (n + m)
        pub = result["late_registration_sensitivities"][str(year)]
        compare([share, average, average - j_ref, average - observed[first]],
                [pub["late_share"], pub["expanded_joint_rate"], pub["expanded_minus_reference"],
                 pub["expanded_minus_early"]])
        delta = float(share) * (replicates[second] - replicates[first])
        compare_bounds(replicates[first] + delta - float(j_ref), pub["expanded_minus_reference_conditional_95_interval"])
        compare_bounds(delta, pub["expanded_minus_early_conditional_95_interval"])

    return {
        "status": "passed", "finite_score_threshold_cells_checked": flag_cells,
        "matching_draws_replayed": settings["permutation_draws"],
        "individual_sampling_bootstraps_replayed": len(settings["bootstrap_seeds"]) * settings["bootstrap_draws"],
        "aggregate_fields_checked": checks, "largest_absolute_field_difference": max(errors),
        "scope": "Shared immutable profile reader and seeds. Alternate sorted-prefix CDF with exact boundary checks, "
                 "integer multinomial-frequency arithmetic using uniform sampled indices, and byte-based permutation replay.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    add_analysis_arguments(parser)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), "Choose a new review path")
    reg = read_registration(args.registration_sha256)
    samples, marker = checked_data(args.job, args.r10_job, reg, args.registration_sha256, args.input_sha256)
    result = read_json(args.result)
    require(result["registration_sha256"] == args.registration_sha256 and result["input_sha256"] == args.input_sha256
            and result["new_profiles_sha256"] == marker["profiles_sha256"], "Review uses the wrong result")
    evidence = review(samples, result, reg)
    evidence.update(result_sha256=digest(args.result), registration_sha256=args.registration_sha256,
                    input_sha256=args.input_sha256)
    write_json(args.output, evidence)
    print(f"Independent review passed {evidence['aggregate_fields_checked']} aggregate checks.")
