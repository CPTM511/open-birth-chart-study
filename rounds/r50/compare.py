"""Apply the fixed R49 reference and combine approved age-34 sampling summaries."""

from bisect import bisect_left
from fractions import Fraction

import numpy as np


SYSTEMS = ("bazi", "ziwei", "qizheng", "western")
AGE_STARTS = tuple(range(20, 51))
MAIN_AGE = 34
WINDOW_WIDTH = 10
WINDOW_COUNT = len(AGE_STARTS)


def cutoff_rule(values, prefix):
    """Convert an exact weighted midrank table to a single P75 comparison."""
    total = prefix[-1]
    boundary = bisect_left(prefix, (3 * total + 3) // 4)
    inclusive = 2 * (prefix[boundary - 1] + prefix[boundary]) >= 3 * total
    return values[boundary - 1], ">=" if inclusive else ">"


def classify_scores(scores, cutoff_rules):
    """Return flags in the original record, completed age, and system order."""
    scores = np.asarray(scores, dtype=np.float64)
    if (scores.ndim != 3 or scores.shape[1:] != (40, 4)
            or not np.isfinite(scores).all() or (scores < 0).any() or (scores > 1).any()):
        raise ValueError("Expected complete finite four-system scores in [0, 1] at ages 20–59")
    expected = [(age, system) for age in range(20, 60, 10) for system in SYSTEMS]
    by_key = {(rule["age_from"], rule["system"]): rule for rule in cutoff_rules}
    if len(cutoff_rules) != len(expected) or set(by_key) != set(expected):
        raise ValueError("Expected one fixed cutoff for every age band and system")

    elevated = np.empty(scores.shape, dtype=bool)
    for age, system in expected:
        rule = by_key[age, system]
        score = rule["score"]
        operation = rule["operator"]
        if not 0 <= score <= 1 or operation not in (">", ">="):
            raise ValueError("Invalid fixed reference rule")
        band = slice(age - 20, age - 20 + 10)
        system_index = SYSTEMS.index(system)
        values = scores[:, band, system_index]
        elevated[:, band, system_index] = values >= score if operation == ">=" else values > score
    return elevated


def centered_gap_integers(flags):
    """Return 31 times each ten-year gap indicator minus the record's gap count."""
    joint = flags.sum(axis=2) >= 3
    totals = np.pad(np.cumsum(joint, axis=1, dtype=np.int64), ((0, 0), (1, 0)))
    absent = totals[:, WINDOW_WIDTH:] == totals[:, :-WINDOW_WIDTH]
    return WINDOW_COUNT * absent - absent.sum(axis=1, keepdims=True)


def fixed_age_contrast(strata, reference_center):
    """Return exact effect and design variance from (N, n, sum(x), sum(x²)) tuples.

    Each row represents a complete eligible stratum with a simple random sample
    without replacement. The Brazil 2006 comparator is treated as fixed.
    """
    frame = 0
    weighted_sum = Fraction(0)
    variance_sum = Fraction(0)
    for population, n, total, squares in strata:
        if (not all(type(item) is int for item in (population, n, total, squares))
                or not 1 <= n <= population or abs(total) > (WINDOW_COUNT - 1) * n
                or not 0 <= squares <= (WINDOW_COUNT - 1) ** 2 * n or total ** 2 > n * squares):
            raise ValueError("Invalid stratum counts or unrounded integer moments")
        frame += population
        weighted_sum += Fraction(population * total, n)
        if population == n:
            continue
        if n < 2:
            raise ValueError("Variance is unidentified for a noncensus singleton stratum")
        sample_variance = Fraction(n * squares - total ** 2, n * (n - 1))
        variance_sum += Fraction(population * (population - n), n) * sample_variance
    if frame == 0:
        raise ValueError("At least one eligible stratum is required")
    scale = WINDOW_COUNT * frame
    return weighted_sum / scale - reference_center, variance_sum / scale ** 2
