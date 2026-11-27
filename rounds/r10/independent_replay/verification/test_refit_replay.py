# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synthetic-only checks for the independent R10 exploratory sensitivity replay."""
from fractions import Fraction
import sys
import unittest

import numpy as np

from review_refits import Cohort, Cutoff, R10, Rates, integer_weights, replay


def literal_flag(reference, weights, query):
    lower_equal = sum(w * (2 * int(np.sum(v < query)) + int(np.sum(v == query)))
                      for w, v in zip(weights, reference))
    return 5 * lower_equal >= 8 * reference.shape[1] * sum(weights)


class RefitChecks(unittest.TestCase):
    def test_cutoff_with_rational_equalities_gaps_and_zero_mass(self):
        reference = np.repeat(np.array([0., 0., 0., 1., 1.])[:, None], 10, axis=1)
        self.check_cutoff(reference, [Fraction(7, 5)] * 5)
        self.check_cutoff(reference, [Fraction(1), Fraction(1), Fraction(2), Fraction(1), Fraction(0)])
        self.check_cutoff(reference, [Fraction(1), Fraction(1), Fraction(2, 10**13),
                                      Fraction(3), Fraction(0)])

    def check_cutoff(self, reference, weights):
        ints = integer_weights(weights)
        value, inc = Cutoff(reference).find(np.array(weights, float), ints, 10 * sum(ints))
        for x in [-.01, 0., np.nextafter(0., 1.), .2, .5, .9, np.nextafter(1., 0.), 1., 2.]:
            self.assertEqual((x >= value) if inc else (x > value), literal_flag(reference, weights, x))

    def test_all_age_system_cells_with_literal_weighted_counts(self):
        rng = np.random.default_rng(819)
        ref = rng.integers(0, 4, (5, 40, 4)) / 3
        target = rng.integers(0, 7, (3, 40, 4)) / 6
        weights = [Fraction(n, 7) for n in (3, 11, 7, 2, 19)]
        actual = Rates(ref, [target]).counts(np.array(weights, float), weights)
        for cohort, counts in zip((ref, target), actual):
            for i, person in enumerate(cohort):
                positives = 0
                for age, values in enumerate(person):
                    start = (age // 10) * 10
                    positives += sum(literal_flag(ref[:, start:start+10, j], weights, x)
                                     for j, x in enumerate(values)) >= 3
                self.assertEqual(counts[i], positives)

    def test_census_and_finite_population_stratum_total(self):
        rows = [{"stratum": key, "weight": Fraction(N, n)}
                for key, N, n in [("census", 2, 2), ("sample", 29, 4)] for _ in range(n)]
        source = Cohort(rows, np.zeros((6, 40, 4)), {"census": (2, 2), "sample": (29, 4)})
        rng = np.random.default_rng(4932)
        for _ in range(20):
            w = source.draw(rng)
            self.assertTrue(np.array_equal(w[:2], [1., 1.]))
            self.assertAlmostEqual(sum(w[2:]), 29)
            self.assertTrue((w >= 0).all())

    def test_independent_replay_agrees_on_synthetic_distribution(self):
        # Comparison only. The reviewer executable does not import the primary path.
        sys.path.insert(0, str(R10 / "methods"))
        from reference_sensitivity import run_sensitivity
        rng = np.random.default_rng(9281)
        frame = {"A": (17, 5), "B": (4, 4), "C": (73, 9)}
        rows = [{"stratum": k, "weight": Fraction(N, n)} for k, (N, n) in frame.items() for _ in range(n)]
        def cohort():
            scores = rng.integers(0, 15, (len(rows), 40, 4)) / 14
            scores[:, :, 3] = rng.random(scores[:, :, 3].shape)
            return Cohort(rows, scores, frame)
        def main_input(c):
            return {"scores": c.scores, "weights": c.weights,
                    "strata": [row["stratum"] for row in rows],
                    "frame_counts": {k: N for k, (N, _) in frame.items()}}
        ref = cohort()
        targets = {s: cohort() for s in ("a", "b", "c")}
        seeds = {"a": 620, "b": 621, "c": 622}
        got_reference, got = replay(ref, targets, 31, 619, seeds)
        previous = run_sensitivity(main_input(ref), {k: main_input(v) for k, v in targets.items()},
                                   draws=31, reference_seed=619, target_seeds=seeds)
        np.testing.assert_allclose(got_reference, previous["full_refit_reference_joint_percentile_range95"], rtol=0, atol=2e-14)
        for item in previous["targets"]:
            for key, actual in got[item["slot"]].items():
                np.testing.assert_allclose(actual, item[key], rtol=0, atol=2e-14)


if __name__ == "__main__":
    unittest.main()
