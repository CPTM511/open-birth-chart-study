"""Aggregate R34 model runs with the three registered date and hour weights."""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import gzip
import io
from pathlib import Path
import platform

import numpy as np

from rounds.r27.analyze import PrecisionReference, load_reference
from rounds.r27.archive_source import read_json, require, write_json
from rounds.r27.study import R10
from rounds.r27.verify import weighted_rank_tables
from rounds.r29.compare import integer_flags
from .profiles import SEXES, VARIANTS, keys_for, load_scores, scores_file, sensitivity_dates
from .source import HERE, YEARS, dates_for, digest, read_counts


SYSTEMS = ("bazi", "ziwei_doushu", "qizheng_siyu", "western_astrology")
RATE_NAMES = ("A_observed", "B_independent_margins", "C_uniform_hours")
MINIMUM_PP = Fraction(3, 10)


def mixed_rates(counts, hits):
    """Both synthetic sex parameters enter hits; each contributes 40 model years."""
    n = int(counts.sum())
    require(n > 0 and counts.shape == hits.shape and counts.shape[1] == 24, "Invalid date and hour cell weights")
    by_day = counts.sum(axis=1)
    by_hour = counts.sum(axis=0)
    return {
        RATE_NAMES[0]: Fraction(int(np.sum(counts * hits)), 80 * n),
        RATE_NAMES[1]: Fraction(int(np.sum(by_day[:, None] * by_hour[None, :] * hits)), 80 * n**2),
        RATE_NAMES[2]: Fraction(int(np.sum(by_day * hits.sum(axis=1))), 80 * 24 * n),
    }


def exact_rate_replay(counts, hits):
    """Rebuild the same three rates as nested exact weighted day means."""
    rows, modeled = counts.tolist(), hits.tolist()
    daily = [sum(row) for row in rows]
    n = sum(daily)
    h = [sum(column) for column in zip(*rows, strict=True)]
    a, b, c = Fraction(), Fraction(), Fraction()
    for daily_births, observed, high in zip(daily, rows, modeled, strict=True):
        if not daily_births:
            continue
        observed_day = Fraction(sum(k * k_hit for k, k_hit in zip(observed, high, strict=True)), daily_births)
        marginal_day = Fraction(sum(k * k_hit for k, k_hit in zip(h, high, strict=True)), n)
        equal_hours = Fraction(sum(high), 24)
        share = Fraction(daily_births, 80 * n)
        a += share * observed_day
        b += share * marginal_day
        c += share * equal_hours
    return dict(zip(RATE_NAMES, (a, b, c), strict=True))


def contrast_values(rates):
    a, b, c = rates.values()
    return {
        "date_hour_linkage_A_minus_B_pp": 100 * (a - b),
        "hour_concentration_B_minus_C_pp": 100 * (b - c),
        "all_hour_composition_A_minus_C_pp": 100 * (a - c),
    }


def to_report(rates, reference):
    return {
        "rates": {key: float(value) for key, value in rates.items()},
        "rates_exact": {key: str(value) for key, value in rates.items()},
        **{key: float(value) for key, value in contrast_values(rates).items()},
        "A_minus_frozen_brazil2006_pp": 100 * (float(rates[RATE_NAMES[0]]) - reference),
    }


def weighted_sex_bounds(counts, sex_hits, male_total):
    n = int(counts.sum())
    require(0 <= male_total <= n, "Incompatible national sex count")
    female_hits = int(np.sum(counts * sex_hits[..., 0]))
    differences = (sex_hits[..., 1] - sex_hits[..., 0]).ravel()
    candidates = list(zip(differences.tolist(), counts.ravel().tolist(), strict=True))
    range_results = []
    for descending in (False, True):
        remaining, hits = male_total, female_hits
        for gain, count in sorted(candidates, reverse=descending):
            allocated = min(remaining, count)
            remaining -= allocated
            hits += allocated * gain
            if remaining == 0:
                break
        require(remaining == 0, "Could not distribute all registered sex counts")
        range_results.append(Fraction(hits, 40 * n))
    return range_results


def sex_ranges(counts, sex_hits, sex_margin):
    n = int(counts.sum())
    f_and_m = [Fraction(int(np.sum(counts * sex_hits[..., i])), 40 * n) for i in range(2)]
    lower_upper = [Fraction(int(np.sum(counts * bound(sex_hits, axis=-1))), 40 * n)
                   for bound in (np.min, np.max)]
    require(all(lower_upper[0] <= rate <= lower_upper[1] for rate in f_and_m), "Invalid sex uncertainty bounds")
    result = {
        "constant_parameter_A_rates": dict(zip(SEXES, map(float, f_and_m), strict=True)),
        "unrestricted_cell_assignment_A_bounds": list(map(float, lower_upper)),
    }
    if sex_margin is not None:
        require(sex_margin["male"] + sex_margin["female"] == n, "External totals cannot constrain this table")
        constrained = weighted_sex_bounds(counts, sex_hits, sex_margin["male"])
        require(lower_upper[0] <= constrained[0] <= constrained[1] <= lower_upper[1], "Invalid restricted margins")
        result["national_margins"] = sex_margin
        result["fixed_national_margins_A_bounds"] = list(map(float, constrained))
    return result


def classify(scores, calibration, tables):
    flags = calibration.flags(scores)
    exact = integer_flags(scores, tables)
    require(np.array_equal(flags, exact), "Float and independent integer R10 high flags differ")
    joint = flags.sum(axis=2) >= 3
    bands = joint.reshape(len(scores), 4, 10).sum(axis=2)
    return np.hstack((bands, flags.sum(axis=1)))


def load_grid(directory, year, calibration, tables):
    dimensions = len(VARIANTS), len(dates_for(year)), 24, len(SEXES), 8
    grid = np.full(dimensions, -1, dtype=np.int16)
    receipts = {}
    for month in range(1, 13):
        keys = keys_for(year, month)
        path = scores_file(directory, year, month)
        scores = load_scores(path, keys, same_environment=False)
        for (day, variant, hour, sex), rows in zip(keys, classify(scores, calibration, tables), strict=True):
            grid[variant, day, hour, sex] = rows
        receipts[path.name] = {"model_runs": len(keys), "sha256": digest(path)}
    selected_dates = sensitivity_dates(year)
    mask = np.array([day in selected_dates for day in dates_for(year)])
    require(np.all(grid[0] >= 0) and np.all(grid[1:, mask] >= 0) and np.all(grid[1:, ~mask] == -1),
            f"Scoring grid is missing or has unexpected cells for {year}")
    return grid, mask, receipts


def verify_probe(directory, alternate, year, grid, calibration, tables):
    keys = keys_for(year, 0)
    linux_path = scores_file(alternate, year, 0)
    linux = load_scores(linux_path, keys, same_environment=False)
    derived, host = {}, {}
    for month in range(1, 13):
        month_keys = keys_for(year, month)
        scores = load_scores(scores_file(directory, year, month), month_keys, same_environment=False)
        indexes = {key: i for i, key in enumerate(month_keys)}
        for key in keys:
            if key in indexes:
                host[key] = scores[indexes[key]]
                day, variant, hour, sex = key
                derived[key] = grid[variant, day, hour, sex]
    host = np.stack([host[key] for key in keys])
    host_counts, linux_counts = np.stack([derived[key] for key in keys]), classify(linux, calibration, tables)
    flags_host, flags_linux = calibration.flags(host), calibration.flags(linux)
    require(np.array_equal(host_counts, linux_counts) and np.array_equal(flags_host, flags_linux),
            f"Cross-runtime high flags differ in the independent {year} checks")
    return {"profiles": len(keys), "system_year_flags_agree": flags_host.size,
            "maximum_raw_score_difference": float(np.abs(host - linux).max()),
            "alternate_runtime_profile_sha256": digest(linux_path)}


def analyze_rates(counts, grid, dates, selected, reference, sex_margin):
    base = grid[0]
    sex_hits = base[..., :4].sum(axis=-1)
    total_hits = sex_hits.sum(axis=2)
    rates = mixed_rates(counts, total_hits)
    require(rates == exact_rate_replay(counts, total_hits), "Independent yearly rate or denominator differs")
    n = int(counts.sum())
    metrics = {
        **to_report(rates, reference),
        "age_band_A_rates": [float(Fraction(int(value), 20 * n)) for value in
                             (counts[..., None] * base[..., :4].sum(axis=2)).sum(axis=(0, 1))],
        "system_A_high_rates": dict(zip(SYSTEMS, (
            float(Fraction(int(value), 80 * n)) for value in
            (counts[..., None] * base[..., 4:].sum(axis=2)).sum(axis=(0, 1))), strict=True)),
        "missing_sex_linkage": sex_ranges(counts, sex_hits, sex_margin),
    }
    month_reports = {}
    for month in range(1, 13):
        keep = np.array([day.month != month for day in dates])
        omitted = mixed_rates(counts[keep], total_hits[keep])
        require(omitted == exact_rate_replay(counts[keep], total_hits[keep]), "Independent monthly check differs")
        month_reports[f"{month:02d}"] = to_report(omitted, reference)
    variants = {}
    for variant, mode in enumerate(VARIANTS):
        sample_hits = grid[variant, selected, ..., :4].sum(axis=(2, 3))
        changed = mixed_rates(counts[selected], sample_hits)
        require(changed == exact_rate_replay(counts[selected], sample_hits), "Independent sensitivity rates differ")
        variants[mode] = to_report(changed, reference)
    return dict(metrics, month_omission=month_reports, paired_clock_and_location={
        "days": [day.isoformat() for day, include in zip(dates, selected, strict=True) if include],
        "observed_births_in_these_dates": int(counts[selected].sum()),
        "variants": variants,
    })


def write_grid(path, grids):
    """Retain aggregate model-year counts so readers can recheck weighting without scoring again."""
    with path.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as archive:
        with io.TextIOWrapper(archive, newline="", encoding="ascii") as stream:
            data = csv.writer(stream, lineterminator="\n")
            data.writerow(("date", "hour", "variant", "parameter", "joint_20_29", "joint_30_39", "joint_40_49",
                           "joint_50_59", *SYSTEMS))
            for year, grid in grids.items():
                for index, day in enumerate(dates_for(year)):
                    for variant, mode in enumerate(VARIANTS):
                        if grid[variant, index, 0, 0, 0] < 0:
                            continue
                        for hour in range(24):
                            for sex, parameter in enumerate(SEXES):
                                data.writerow((day.isoformat(), hour, mode, parameter,
                                               *grid[variant, index, hour, sex].tolist()))


def run(sources, source_replay, scores, alternate, reference_job, output, grid_path):
    reference, weights, exact_weights = load_reference(reference_job)
    calibration = PrecisionReference(reference, weights, exact_weights)
    published = read_json(R10 / "independent_replay/results/structural_comparison.json")["reference"]["joint_rate"]
    require(abs(calibration.joint_rate - published) < 2e-13, "Brazil fixed-reference rate differs from R10")
    tables = weighted_rank_tables(reference, exact_weights)
    sex_margins = read_json(HERE / "sex_margins.json")
    grids, results = {}, {}
    for year in YEARS:
        counts, quality = read_counts(sources, year)
        replay_counts, replay_quality = read_counts(source_replay, year)
        require(sources.resolve() != source_replay.resolve() and quality == replay_quality
                and np.array_equal(counts, replay_counts), "Independently retrieved counts differ")
        grid, selected, receipts = load_grid(scores[year], year, calibration, tables)
        grids[year] = grid
        results[str(year)] = {
            "source": quality,
            "scoring_batches": receipts,
            "model_runs": sum(batch["model_runs"] for batch in receipts.values()),
            "cross_runtime": verify_probe(scores[year], alternate, year, grid, calibration, tables),
            **analyze_rates(counts, grid, dates_for(year), selected, calibration.joint_rate, sex_margins.get(str(year))),
        }
        print(f"{year}: all {results[str(year)]['model_runs']} profiles checked", flush=True)
    write_grid(grid_path, grids)
    linkage = [entry["date_hour_linkage_A_minus_B_pp"] for entry in results.values()]
    stable = all(delta >= float(MINIMUM_PP) for delta in linkage) or all(delta <= -float(MINIMUM_PP) for delta in linkage)
    write_json(output, {
        "round": "R34",
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "source_definition_sha256": digest(HERE / "sources.json"),
        "sex_margins_sha256": digest(HERE / "sex_margins.json"),
        "main_runtime": {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version()},
        "reference": {"name": "Frozen R10 Brazil 2006, 2000 weighted profiles", "joint_rate": calibration.joint_rate},
        "minimum_difference_pp": float(MINIMUM_PP),
        "linked_date_hour_difference_reaches_threshold_in_same_direction": stable,
        "profile_grid_sha256": digest(grid_path),
        "years": results,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("sources", "source-replay", "scores-1999", "scores-2006", "alternate", "reference-job", "output",
                     "grid"):
        parser.add_argument(f"--{argument}", required=True, type=Path)
    args = parser.parse_args()
    run(args.sources, args.source_replay, {1999: args.scores_1999, 2006: args.scores_2006},
        args.alternate, args.reference_job, args.output, args.grid)


if __name__ == "__main__":
    main()
