from fractions import Fraction
import unittest

import numpy as np

from rounds.r50.compare import SYSTEMS, classify_scores, cutoff_rule, fixed_age_contrast


class R50ExternalReferenceTests(unittest.TestCase):
    def test_tied_boundary_differs_from_a_value_one_float_above_it(self):
        exclusive = cutoff_rule((0.2, 0.5, 0.9), (0, 1, 3, 4))
        inclusive = cutoff_rule((0.2, 0.5), (0, 2, 4))
        self.assertEqual(exclusive, (0.5, ">"))
        self.assertEqual(inclusive, (0.5, ">="))
        rules = [{"age_from": age, "system": system, "score": 0.5,
                  "operator": inclusive[1] if age == 20 else exclusive[1]}
                 for age in range(20, 60, 10) for system in SYSTEMS]
        scores = np.empty((3, 40, 4))
        scores[0] = np.nextafter(0.5, 0)
        scores[1] = 0.5
        scores[2] = np.nextafter(0.5, 1)
        flags = classify_scores(scores, rules)
        self.assertFalse(flags[0].any())
        self.assertTrue(flags[1, :10].all())
        self.assertFalse(flags[1, 10:].any())
        self.assertTrue(flags[2].all())

    def test_finite_population_variance_and_singleton_census(self):
        self.assertEqual(fixed_age_contrast([(5, 2, 6, 116)], Fraction(1, 31)),
                         (Fraction(2, 31), Fraction(147, 4805)))
        self.assertEqual(fixed_age_contrast([(1, 1, -4, 16)], Fraction(1, 31)),
                         (Fraction(-5, 31), Fraction(0)))
        with self.assertRaisesRegex(ValueError, "noncensus singleton"):
            fixed_age_contrast([(5, 1, -4, 16)], Fraction(1, 31))
