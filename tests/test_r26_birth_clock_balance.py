"""Regression tests for balancing weights and design linearization."""
import unittest

import numpy as np

from rounds.r26.clock_balance import design_variance, factorize


class CalendarBalanceTests(unittest.TestCase):
    def setUp(self):
        self.group = np.repeat([0, 1], 4)
        self.weekend = np.tile([0, 0, 1, 1], 2)
        self.daytime = np.tile([0, 1, 0, 1], 2)
        self.weight = np.array([5, 10, 12, 2, 6, 2, 3, 9], dtype=float)
        self.y = np.array([0.0, 0.1, 0.3, 0.9, 0.4, 0.3, 0.6, 0.9])

    def estimate(self, w):
        return factorize(w, self.y, self.group, self.weekend, self.daytime)

    def test_balancing_preserves_groupwise_clock_and_weekend_margins(self):
        actual = self.estimate(self.weight)
        for g in (0, 1):
            mask = self.group == g
            w = actual.weight[mask].reshape(2, 2)
            old = self.weight[mask].reshape(2, 2)
            for axis in (0, 1):
                np.testing.assert_allclose(w.sum(axis=axis), old.sum(axis=axis), atol=1e-12)
            self.assertAlmostEqual(w[0, 0] * w[1, 1], w[0, 1] * w[1, 0], places=12)

    def test_linearity_derivative_matches_every_component_of_finite_difference(self):
        seen = self.estimate(self.weight)
        for i in range(len(self.weight)):
            perturbation = np.zeros(len(self.weight))
            perturbation[i] = 1e-4
            plus = self.estimate(self.weight + perturbation).factorized_rate
            minus = self.estimate(self.weight - perturbation).factorized_rate
            self.assertAlmostEqual((plus - minus) / 2e-4, seen.influence[i] / self.weight.sum(), places=9)
        self.assertAlmostEqual(float(self.weight @ seen.influence), 0.0, places=12)

    def test_empty_joint_cell_is_not_imputed(self):
        keep = np.arange(len(self.y)) != 1
        self.assertIsNone(factorize(self.weight[keep], self.y[keep], self.group[keep],
                                    self.weekend[keep], self.daytime[keep]))

    def test_census_strata_contribute_no_finite_population_variance(self):
        x = np.array([0.0, 1.0, 2.0, 4.0])
        strata = np.array(["full", "full", "sample", "sample"])
        expected = (4 / 6) ** 2 * (1 - 2 / 4) * 2.0 / 2
        self.assertAlmostEqual(design_variance(x, strata, {"full": 2, "sample": 4}), expected, places=14)
