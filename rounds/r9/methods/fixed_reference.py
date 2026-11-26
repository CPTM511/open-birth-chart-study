"""R9 fixed-reference structural estimators; no mortality or AI-risk model.

Raw score shape is (source records, 40 completed ages, 4 systems). The
bootstrap treats each record's complete trajectory as one sampling unit.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


def _scores(value):
    value = np.asarray(value, dtype=float)
    if value.ndim != 3 or value.shape[1:] != (40, 4) or len(value) == 0:
        raise ValueError("Scores must have nonempty shape (records,40,4)")
    if not np.isfinite(value).all():
        raise ValueError("Nonfinite or missing scores are not imputed")
    if np.any((value < 0) | (value > 1)):
        raise ValueError("Frozen R8 primary scores must be in [0,1]")
    return value


def _weights(value, n):
    value = np.asarray(value, dtype=float)
    if value.shape != (n,) or not np.isfinite(value).all() or np.any(value <= 0):
        raise ValueError("One finite positive source-frame weight per record is required")
    return value


@dataclass
class WeightedMidCDF:
    values: np.ndarray
    cumulative_weights: np.ndarray

    @classmethod
    def fit(cls, values, weights):
        values, weights = np.asarray(values, float), np.asarray(weights, float)
        if values.ndim != 1 or weights.shape != values.shape or not len(values):
            raise ValueError("CDF inputs must be nonempty equal-length vectors")
        if not np.isfinite(values).all():
            raise ValueError("CDF values must be finite")
        _weights(weights, len(values))
        support, inverse = np.unique(values, return_inverse=True)
        masses = np.bincount(inverse, weights=weights, minlength=len(support))
        return cls(support, np.r_[0.0, np.cumsum(masses)])

    def __call__(self, values):
        values = np.asarray(values, float)
        if not np.isfinite(values).all():
            raise ValueError("Cannot transform missing scores")
        left = np.searchsorted(self.values, values, side="left")
        right = np.searchsorted(self.values, values, side="right")
        return (self.cumulative_weights[left] + self.cumulative_weights[right]) / (
            2.0 * self.cumulative_weights[-1]
        )


class FixedReference:
    """Weighted mid-CDF fitted only to the frozen R8 Brazil 2006 reference."""

    def __init__(self, scores, weights):
        scores = _scores(scores)
        weights = _weights(weights, len(scores))
        self.cdfs = {}
        for band in range(4):
            for system in range(4):
                self.cdfs[band, system] = WeightedMidCDF.fit(
                    scores[:, band * 10 : band * 10 + 10, system].reshape(-1),
                    np.repeat(weights, 10),
                )
        q = self.transform(scores)
        self.raw_means = np.average(scores.mean(axis=1), axis=0, weights=weights)
        self.percentile_means = np.average(q.mean(axis=1), axis=0, weights=weights)
        self.joint_rate = float(np.average(joint_record_rates(q), weights=weights))
        if not np.allclose(self.percentile_means, 0.5, atol=2e-13, rtol=0):
            raise ArithmeticError("Reference mid-CDF means must equal 0.5")

    def transform(self, scores):
        scores = _scores(scores)
        q = np.empty_like(scores)
        for (band, system), cdf in self.cdfs.items():
            q[:, band * 10 : band * 10 + 10, system] = cdf(
                scores[:, band * 10 : band * 10 + 10, system]
            )
        return q

    def summarize(self, scores, weights):
        scores = _scores(scores)
        weights = _weights(weights, len(scores))
        q = self.transform(scores)
        joint = joint_record_rates(q)
        j = float(np.average(joint, weights=weights))
        raw = np.average(scores.mean(axis=1), axis=0, weights=weights)
        levels = np.average(q.mean(axis=1), axis=0, weights=weights)
        return {
            "n_source_records": len(scores),
            "reference_joint_rate": self.joint_rate,
            "joint_rate": j,
            "delta_joint_rate": j - self.joint_rate,
            "raw_system_means": raw.tolist(),
            "delta_raw_system_means": (raw - self.raw_means).tolist(),
            "fixed_reference_system_means": levels.tolist(),
            "delta_fixed_reference_system_means": (levels - 0.5).tolist(),
            "delta_L": float(levels.mean() - 0.5),
            "age_band_joint_rates": [
                float(np.average((np.sum(q[:, b * 10 : b * 10 + 10] >= 0.8, axis=2) >= 3).mean(axis=1), weights=weights))
                for b in range(4)
            ],
        }


def joint_record_rates(q):
    q = _scores(q)
    return (np.sum(q >= 0.8, axis=2) >= 3).mean(axis=1)


def rescaled_stratum_bootstrap(values, frame_n, draws, rng):
    """Multinomial compression exactly resamples the empirical whole-record statistic."""
    values = np.asarray(values, float)
    n = len(values)
    if values.ndim != 1 or n == 0 or not np.isfinite(values).all():
        raise ValueError("Stratum values must be a nonempty finite vector")
    if frame_n < n:
        raise ValueError("Sample cannot exceed eligible frame")
    center = values.mean()
    if frame_n == n:
        return np.full(draws, center), 0.0
    if n < 2:
        raise ValueError("Non-census singleton stratum has unidentifiable sampling variance")
    support, counts = np.unique(values, return_counts=True)
    bootstrap_counts = rng.multinomial(n, counts / n, size=draws)
    bootstrap_means = np.sum(bootstrap_counts * support[None, :], axis=1) / n
    factor = math.sqrt((1.0 - n / frame_n) * n / (n - 1))
    replicates = center + factor * (bootstrap_means - center)
    variance = (1.0 - n / frame_n) * values.var(ddof=1) / n
    return replicates, float(variance)


def conditional_frame_interval(values, strata, frame_counts, *, seed, draws=1999, family_size=3):
    """Approximate finite-frame interval conditional on fixed reference and assumptions.

    `values` contains each sampled record's 40-year joint proportion, not annual
    rows. All eligible strata must be included in frame_counts. Source-frame
    weights are N_h/n_h; nonprobability source selection is not repaired here.
    """
    values, strata = np.asarray(values, float), np.asarray(strata, str)
    if values.ndim != 1 or strata.shape != values.shape or len(values) == 0:
        raise ValueError("One stratum per nonempty vector of whole-record values")
    if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
        raise ValueError("Joint proportions must be finite and in [0,1]")
    if not isinstance(draws, int) or draws < 2 or not isinstance(family_size, int) or family_size < 1:
        raise ValueError("Invalid bootstrap draws or interval family size")
    keys = sorted(set(strata.tolist()))
    normalized_frame = {str(k): int(v) for k, v in frame_counts.items()}
    if set(keys) != set(normalized_frame) or any(n <= 0 for n in normalized_frame.values()):
        raise ValueError("Every eligible stratum must be sampled and have a positive frame count")
    total = sum(normalized_frame.values())
    rng = np.random.default_rng(seed)
    replicates = np.zeros(draws)
    point = variance = 0.0
    unavailable = []
    detail = []
    for key in keys:
        v = values[strata == key]
        n, population_n = len(v), normalized_frame[key]
        if n > population_n:
            raise ValueError("Sample exceeds frame in " + key)
        weight = population_n / total
        point += weight * float(v.mean())
        detail.append({"stratum": key, "sample_n": n, "frame_n": population_n})
        if n == 1 and population_n > 1:
            unavailable.append(key)
            continue
        b, var = rescaled_stratum_bootstrap(v, population_n, draws, rng)
        replicates += weight * b
        variance += weight * weight * var
    out = {
        "status": "unavailable" if unavailable else "computed_assumption_conditional",
        "point": point,
        "strata": detail,
        "draws": draws,
        "seed": int(seed),
        "family_size_including_unavailable_slots": family_size,
        "conditioning": "fixed reference; fixed scores; stated finite frame and stratified sampling approximation",
        "not_included": ["reference estimation", "source selection", "clock/location error", "model validity", "global generalization"],
    }
    if unavailable:
        out["unavailable_reason"] = "non-census singleton strata: " + ", ".join(unavailable)
        return out
    alpha = 0.05 / family_size
    out.update({
        "interval95": np.quantile(replicates, [0.025, 0.975]).tolist(),
        "family_adjusted_interval": np.quantile(replicates, [alpha / 2, 1 - alpha / 2]).tolist(),
        "family_adjusted_marginal_coverage": 1 - alpha,
        "analytic_design_variance": variance,
        "bootstrap_variance": float(replicates.var(ddof=1)),
    })
    return out
