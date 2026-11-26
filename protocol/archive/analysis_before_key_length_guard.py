"""Frozen structural-signal analysis. No mortality outcomes are accepted.

The randomization reference is a mathematical independent-phase reference,
not a generative model of deaths, accidents, illness or human futures.
"""
from __future__ import annotations

from itertools import combinations
import math
import warnings
import numpy as np
from scipy.stats import rankdata, spearmanr

SYSTEMS = ("bazi", "ziwei", "qizheng", "western")
WINDOWS = {"age20_59": 40, "age20_49": 30}


def percentiles(scores):
    values = np.asarray(scores, dtype=float)
    if values.ndim != 3 or values.shape[1:] != (40, 4):
        raise ValueError("Require people x 40 completed ages x 4 systems")
    if not np.isfinite(values).all():
        raise ValueError("Missing/nonfinite scores cannot be replaced by zero")
    return (rankdata(values, axis=1, method="average") - 0.5) / 40


def weighted_rate(flags, weights, length=40):
    joint = (np.asarray(flags)[:, :length].sum(axis=2) >= 3)
    return float(np.sum(np.asarray(weights) * joint.mean(axis=1)) / np.sum(weights))


def exact_phase_expectation(flags, weights, length=40):
    """Exact mean under independent uniform shifts in each 10-age block.

    For four marginal flag probabilities, P(at least 3) = sum of triple
    products - 3*product(all four). No Monte Carlo estimated centering.
    """
    f = np.asarray(flags, dtype=float).reshape(-1, 4, 10, 4)
    prob = f.mean(axis=2)
    triples = sum(np.prod(prob[:, :, list(c)], axis=2)
                  for c in combinations(range(4), 3))
    p_joint = triples - 3 * np.prod(prob, axis=2)
    per_person = p_joint[:, :length // 10].mean(axis=1)
    return float(np.dot(weights, per_person) / np.sum(weights))


def group_identical_inputs(flags, weights, input_keys):
    """Keep real-person weights but share null shifts for identical charts."""
    groups = {}
    for index, key in enumerate(input_keys):
        if key in groups:
            first, weight = groups[key]
            if not np.array_equal(flags[first], flags[index]):
                raise ValueError("Identical chart inputs produced different profiles")
            groups[key] = (first, weight + float(weights[index]))
        else:
            groups[key] = (index, float(weights[index]))
    ordered = [groups[k] for k in sorted(groups)]
    return (np.asarray([flags[i] for i, _ in ordered], dtype=bool),
            np.asarray([w for _, w in ordered], dtype=float))


def phase_reference(scores, weights, input_keys, draws=1999, seed=2026112608):
    pct = percentiles(scores)
    flags = pct >= .8
    w = np.asarray(weights, dtype=float)
    if len(w) != len(flags) or not np.isfinite(w).all() or np.any(w <= 0):
        raise ValueError("Invalid source-frame sampling weights")
    grouped, group_weights = group_identical_inputs(flags, w, input_keys)
    # group x system x age decade x age within decade
    reference = grouped.reshape(-1, 4, 10, 4).transpose(0, 3, 1, 2)
    rng = np.random.default_rng(seed)
    simulations = np.empty((draws, 2), dtype=float)
    positions = np.arange(10)[None, None, None, :]
    for draw in range(draws):
        shifts = rng.integers(0, 10, size=reference.shape[:3] + (1,))
        rotated = np.take_along_axis(reference, (positions + shifts) % 10, axis=3)
        joint = rotated.sum(axis=1) >= 3
        for j, length in enumerate(WINDOWS.values()):
            per_group = joint[:, :length // 10].mean(axis=(1, 2))
            simulations[draw, j] = np.dot(group_weights, per_group) / group_weights.sum()
    output = {}
    for j, (name, length) in enumerate(WINDOWS.items()):
        observed = weighted_rate(flags, w, length)
        expected = exact_phase_expectation(grouped, group_weights, length)
        delta = abs(observed - expected)
        extreme = np.count_nonzero(np.abs(simulations[:, j] - expected) >= delta - 1e-14)
        output[name] = {
            "people": len(flags), "unique_chart_input_blocks": len(grouped),
            "person_years": int(len(flags) * length), "weighted_concordance": observed,
            "exact_independent_phase_mean": expected,
            "difference_percentage_points": 100 * (observed - expected),
            "p_raw_two_sided": float((extreme + 1) / (draws + 1)),
            "draws": draws, "seed": seed, "p_resolution": 1 / (draws + 1),
            "phase_reference_interval95": np.quantile(simulations[:, j], [.025, .975]).tolist(),
            "interval_is_not_a_population_or_mortality_confidence_interval": True,
            "phase_null_monte_carlo_mean": float(simulations[:, j].mean()),
            "phase_null_monte_carlo_se_of_mean": float(simulations[:, j].std(ddof=1) / math.sqrt(draws)),
            "is_prediction_validity_test": False,
        }
    return output


def holm(values):
    """Include unavailable tests in family size but keep their display null."""
    work = [1.0 if x is None else float(x) for x in values]
    if any(not (0 <= x <= 1) for x in work):
        raise ValueError("Invalid probability")
    order = sorted(range(len(work)), key=lambda i: (work[i], i))
    answer = [None] * len(work)
    running = 0.0
    for position, index in enumerate(order):
        running = max(running, (len(work) - position) * work[index])
        if values[index] is not None:
            answer[index] = min(1., running)
    return answer


def descriptive_correlations(scores):
    values = np.asarray(scores).reshape(-1, 4)
    out = {}
    for i, j in combinations(range(4), 2):
        if np.ptp(values[:, i]) == 0 or np.ptp(values[:, j]) == 0:
            rho = None
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                rho = float(spearmanr(values[:, i], values[:, j]).statistic)
        out[f"{SYSTEMS[i]}__{SYSTEMS[j]}"] = {
            "spearman_rho_unweighted_sample_descriptive": rho,
            "p_value": None, "person_years_not_independent": True,
        }
    return out


def annual_summary(scores, years, weights, start=2026, end=2070):
    values = np.asarray(scores, dtype=float)
    pct = percentiles(values)
    joint = (pct >= .8).sum(axis=2) >= 3
    y = np.asarray(years, dtype=int)
    w = np.asarray(weights, dtype=float)
    if y.shape != values.shape[:2]:
        raise ValueError("One calendar year is required for each age point")
    out = []
    for year in range(start, end + 1):
        person, age = np.where(y == year)
        if len(set(person)) != len(person):
            raise ValueError("Repeated person within a calendar year")
        if len(person) == 0:
            out.append({"year": year, "people": 0, "concordance": None,
                        "mean_primary_scores": None, "mean_within_person_percentiles": None})
            continue
        weights_here = w[person]
        out.append({
            "year": year, "people": len(person), "source_frame_weight_sum": float(weights_here.sum()),
            "concordance": float(np.average(joint[person, age], weights=weights_here)),
            "mean_primary_scores": dict(zip(SYSTEMS, np.average(values[person, age], axis=0, weights=weights_here).tolist())),
            "mean_within_person_percentiles": dict(zip(SYSTEMS, np.average(pct[person, age], axis=0, weights=weights_here).tolist())),
            "eligible_for_descriptive_peak_listing": len(person) >= 30,
        })
    return out


def age_summary(scores, weights):
    values = np.asarray(scores, dtype=float)
    pct = percentiles(values)
    joint = (pct >= .8).sum(axis=2) >= 3
    return [{"completed_age": a + 20,
             "concordance": float(np.average(joint[:, a], weights=weights)),
             "mean_within_person_percentiles": dict(zip(SYSTEMS, np.average(pct[:, a], axis=0, weights=weights).tolist()))}
            for a in range(40)]
