"""Reweight observed birth-clock categories without changing any recorded chart."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import norm

from rounds.r11 import calendar_controls as r11
from rounds.r12 import study as r12

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_SHA = "883ed6b911ce526f6ac2a7965f9ad8650480765180f3842aedea585c4885774a"
REGISTRATION_SHA = "8d01831ca8412b91a27030df8734dcbd04ffe9a67c1ba301bd383ae2c877ed87"


@dataclass(frozen=True)
class Cohort:
    slot: str
    country: str
    year: int
    rows: list
    weights: np.ndarray
    design_strata: np.ndarray
    frame_sizes: dict
    joint_years: np.ndarray


@dataclass(frozen=True)
class Balance:
    factorized_rate: float
    weight: np.ndarray
    influence: np.ndarray
    minimum_cell_n: int
    adjustment_factors: np.ndarray


def load_cohorts(r10_job: Path, r12_job: Path, config: dict) -> list[Cohort]:
    r11_config = r11.read_json(ROOT / "rounds/r11/protocol.json")
    r11.require(r11.digest(r10_job / "aggregation_ready.json") == config["r10_receipt"], "Wrong sealed R10 receipt")
    old = r11.checked_input(r10_job, r11_config)
    r12_protocol = r12.read_json(ROOT / "rounds/r12/protocol.json")
    r12_public_marker = ROOT / "rounds/r12/results/aggregation_ready.json"
    marker = r12_job / "aggregation_ready.json"
    r11.require(r11.digest(marker) == r11.digest(r12_public_marker) == config["r12_receipt"],
                "Wrong sealed R12 receipt")
    marker_values = r12.read_json(marker)
    r12_samples = r12.checked_samples(r12_job, r12_protocol, marker_values["registration_sha256"], config["r12_inputs"])
    r12_profiles = r12_job / "profiles/baseline_profiles.jsonl"
    r11.require(r11.digest(r12_profiles) == marker_values["profiles_sha256"], "R12 profiles changed")

    prior = r11.read_json(r11.REPLAY / "results/structural_comparison.json")
    previous = {config["reference"]: prior["reference"], **{x["slot"]: x for x in prior["targets"]}}
    holdout = r12.read_json(ROOT / "rounds/r12/results/holdout.json")
    previous["mexico2023_early"] = holdout["sample_results"]["mexico2023_early"]

    output = []
    reference = None
    for slot, country, year in config["cohorts"]:
        if slot in old:
            name = r10_job / old[slot]["sample_dir"]
            profiles = [r10_job / x for x in old[slot]["profile_files"]]
        else:
            name, profiles = r12_samples[slot], [r12_profiles]
        rows, _, scores, weights, strata, frame, _ = r11.load_profiles(name, profiles)
        r11.require(len(rows) == config["sample_size_each"] and
                    all(x["birth_country"] == country and int(x["birth_local"][:4]) == year for x in rows),
                    "One or more input birth cohorts differ from their registration")
        if slot == config["reference"]:
            reference = r11.PrecisionReference(scores, weights, [Fraction(x["N_h"], x["n_h"]) for x in rows])
        r11.require(reference is not None, "The frozen reference must be loaded before other cohorts")
        flags = reference.flags(scores)
        counts = (flags.sum(axis=2) >= 3).sum(axis=1)
        raw_rate = np.dot(weights, counts) / (weights.sum() * config["aging_years"])
        r11.require(abs(raw_rate - previous[slot]["joint_rate"]) < 2e-13, f"Previously published rate changed: {slot}")
        output.append(Cohort(slot, country, year, rows, weights, strata, frame, counts))
    return output


def calendar_categories(rows: list[dict], level: str, daylight: list[int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    clocks = [datetime.fromisoformat(row["birth_local"]) for row in rows]
    group = []
    for dt, row in zip(clocks, rows, strict=True):
        period = (dt.month - 1) // 3 if level == "quarter_and_sex" else dt.month - 1
        group.append(2 * period + int(row["sex"] == "F"))
    weekend = np.array([dt.weekday() >= 5 for dt in clocks], dtype=np.int64)
    daytime = np.array([daylight[0] <= dt.hour <= daylight[1] for dt in clocks], dtype=np.int64)
    return np.array(group), weekend, daytime


def factorize(weights: np.ndarray, outcome: np.ndarray, group: np.ndarray,
              weekend: np.ndarray, daytime: np.ndarray) -> Balance | None:
    groups = np.unique(group, return_inverse=True)[1]
    shape = (groups.max() + 1, 2, 2)
    cell = 4 * groups + 2 * weekend + daytime
    levels = 4 * shape[0]
    multiplicity = np.bincount(cell, minlength=levels)
    if not multiplicity.min():
        return None
    observed = np.bincount(cell, weights=weights, minlength=levels).reshape(shape)
    weighted_outcome = np.bincount(cell, weights=weights * outcome, minlength=levels).reshape(shape)
    mass = observed.sum(axis=(1, 2), keepdims=True)
    weekend_margin = observed.sum(axis=2, keepdims=True) / mass
    daylight_margin = observed.sum(axis=1, keepdims=True) / mass
    target = mass * weekend_margin * daylight_margin
    r11.require(np.allclose(observed.sum(axis=2), target.sum(axis=2), rtol=1e-12, atol=1e-12)
                and np.allclose(observed.sum(axis=1), target.sum(axis=1), rtol=1e-12, atol=1e-12),
                "The factorized distribution did not preserve its weighted margins")

    mu = weighted_outcome / observed
    multiplier = target[groups, weekend, daytime] / observed[groups, weekend, daytime]
    adjusted_weight = weights * multiplier
    rate = float(np.dot(adjusted_weight, outcome) / weights.sum())
    along_weekday = (mu * daylight_margin).sum(axis=2)
    along_clock = (mu * weekend_margin).sum(axis=1)
    group_mean = (mu * weekend_margin * daylight_margin).sum(axis=(1, 2))
    # Derivative of the weighted numerator, minus the ratio term.
    influence = (along_weekday[groups, weekend] + along_clock[groups, daytime] - group_mean[groups]
                 + multiplier * (outcome - mu[groups, weekend, daytime]) - rate)
    return Balance(rate, adjusted_weight, influence, int(multiplicity.min()), multiplier)


def design_variance(linear_values: np.ndarray, strata: np.ndarray, sizes: dict) -> float:
    total = sum(sizes.values())
    contributions = []
    for k, population in sorted(sizes.items()):
        values = linear_values[strata == k]
        n = len(values)
        r11.require(0 < n <= population, "An original sample stratum has inconsistent size")
        if n < population:
            r11.require(n >= 2, "A non-census singleton cannot estimate finite-population uncertainty")
            contributions.append((population / total) ** 2 * (1 - n / population) * values.var(ddof=1) / n)
    return math.fsum(contributions)


def geo_shift(cohort: Cohort, adjusted_weights: np.ndarray) -> float:
    states = []
    for label in cohort.design_strata:
        parts = label.split("|")
        state = parts[1] if parts[0] == cohort.country else parts[0]
        r11.require(len(state) == 2 and state.isdigit(), "Unrecognized original state design field")
        states.append(state)
    groups = np.unique(states, return_inverse=True)[1]
    raw = np.bincount(groups, weights=cohort.weights)
    adjusted = np.bincount(groups, weights=adjusted_weights)
    return float(np.abs(adjusted - raw).sum() / (2 * cohort.weights.sum()))


def enhance(cohort: Cohort, level: str, config: dict) -> dict:
    w = cohort.weights
    y = cohort.joint_years / config["aging_years"]
    rate = float(np.dot(w, y) / w.sum())
    group, weekend, daytime = calendar_categories(cohort.rows, level, config["daytime_hours_inclusive"])
    point = factorize(w, y, group, weekend, daytime)
    if point is None:
        return {"status": "missing_support"}
    raw_influence = y - rate
    r11.require(abs(float(np.dot(w, point.influence) / w.sum())) < 1e-12,
                "Ratio influence is not centered at the original weights")
    variance = design_variance(point.influence - raw_influence, cohort.design_strata, cohort.frame_sizes)
    return {
        "status": "computed",
        "adjusted_rate": point.factorized_rate,
        "factorization_effect_pp": 100 * (point.factorized_rate - rate),
        "movement_variance": variance,
        "state_mix_total_variation_pp": 100 * geo_shift(cohort, point.weight),
        "minimum_cell_records": point.minimum_cell_n,
        "effective_weight_n": float(point.weight.sum() ** 2 / np.dot(point.weight, point.weight)),
        "multipliers_from_to": [float(point.adjustment_factors.min()), float(point.adjustment_factors.max())],
    }


def finite(v) -> float:
    return round(float(v), 12)


def comparison_changed(item: dict, ref: dict, key: str, threshold: float, critical: float) -> dict:
    left, right = item[key], ref[key]
    if left["status"] != "computed" or right["status"] != "computed":
        return {"status": "not_estimable_for_this_contrast"}
    effect = left["factorization_effect_pp"] - right["factorization_effect_pp"]
    value = 100 * (left["adjusted_rate"] - right["adjusted_rate"])
    bounds = None
    if key == "quarter_and_sex":
        radius = 100 * critical * math.sqrt(left["movement_variance"] + right["movement_variance"])
        bounds = [finite(effect - radius), finite(effect + radius)]
    return {
        "status": "computed",
        "adjusted_contrast_pp": finite(value),
        "contrast_movement_pp": finite(effect),
        "material_point_movement": bool(abs(effect) >= threshold),
        "simultaneous95_interval_for_movement_pp": bounds,
        "excludes_material_change": bool(bounds and bounds[0] >= -threshold and bounds[1] <= threshold),
    }


def round_numbers(record):
    if isinstance(record, float):
        return finite(record)
    if isinstance(record, list):
        return [round_numbers(v) for v in record]
    if isinstance(record, dict):
        return {k: round_numbers(v) for k, v in record.items()}
    return record


def build_output(cohorts: list[Cohort], config: dict) -> dict:
    main, sensitivity = config["primary_level"], config["sensitivity_level"]
    outputs = {}
    for co in cohorts:
        n = len(co.rows)
        rate = float(np.dot(co.weights, co.joint_years) / (config["aging_years"] * co.weights.sum()))
        _, weekend, daytime = calendar_categories(co.rows, main, config["daytime_hours_inclusive"])
        weekday_share = np.average(daytime[weekend == 0], weights=co.weights[weekend == 0])
        weekend_share = np.average(daytime[weekend == 1], weights=co.weights[weekend == 1])
        outputs[co.slot] = {
            "source": co.country,
            "birth_year": co.year,
            "records": n,
            "record_years": n * config["aging_years"],
            "observed_rate": rate,
            "observed_weekday_minus_weekend_daytime_pp": float(100 * (weekday_share - weekend_share)),
            "original_effective_weight_n": float(co.weights.sum() ** 2 / np.dot(co.weights, co.weights)),
            main: enhance(co, main, config),
            sensitivity: enhance(co, sensitivity, config),
        }
    reference = outputs[config["reference"]]
    critical = norm.ppf(1 - config["conditional_alpha"] / (2 * config["simultaneous_family_size"]))
    threshold = config["practical_threshold_pp"]
    contrasts = {
        key: {
            "original_contrast_pp": finite(100 * (row["observed_rate"] - reference["observed_rate"])),
            main: comparison_changed(row, reference, main, threshold, critical),
            sensitivity: comparison_changed(row, reference, sensitivity, threshold, critical),
        }
        for key, row in outputs.items() if key != config["reference"]
    }
    return round_numbers({
        "version": config["version"], "threshold_pp": threshold, "normal_threshold_simultaneous": float(critical),
        "fixed_threshold_reference": config["reference"], "cohorts": outputs, "contrasts": contrasts,
    })


def read_registered_config() -> dict:
    for name, digest in {"REGISTRATION.zh.md": REGISTRATION_SHA, "protocol.json": PROTOCOL_SHA}.items():
        r11.require(r11.digest(HERE / name) == digest, "The registered file differs: " + name)
    return r11.read_json(HERE / "protocol.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r10-job", required=True, type=Path)
    parser.add_argument("--r12-job", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config = read_registered_config()
    data = load_cohorts(args.r10_job, args.r12_job, config)
    with args.output.open("x", encoding="utf-8") as result:
        json.dump(build_output(data, config), result, ensure_ascii=False, indent=2, allow_nan=False)
        result.write("\n")


if __name__ == "__main__":
    main()
