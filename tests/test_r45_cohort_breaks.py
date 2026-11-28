from fractions import Fraction
import unittest

import numpy as np

from rounds.r45.common import HERE, read_json
from rounds.r45.controls import calibration, check_shuffle, shuffle_flags
from rounds.r45.estimate import Layout, curve_summary, design_vectors, residuals, windows
from rounds.r45.review import classify_exact
from precision_reference import PrecisionReference
from rounds.r27.verify import weighted_rank_tables


class CohortBreaksTest(unittest.TestCase):
    def setUp(self):
        self.cfg = read_json(HERE / "protocol.json")
        self.layout = Layout.from_protocol(self.cfg)

    def test_ten_year_windows_and_birthday_anchor(self):
        flags = np.zeros((2, 40), dtype=bool)
        flags[:, 10] = True
        result = windows(flags, self.layout)
        self.assertTrue(result.absent[0, 0])
        self.assertFalse(result.absent[0, 1])
        self.assertFalse(result.absent[0, 10])
        self.assertTrue(result.absent[0, 11])
        self.assertAlmostEqual(result.gap.sum(), 0)
        adjusted = residuals(result, [2019, 2020], np.zeros((2, 31)), self.layout)
        self.assertAlmostEqual(adjusted[0, 31]-adjusted[1, 31], 1)
        self.assertAlmostEqual(adjusted[1, 51]-adjusted[0, 51], 0.1)
        with self.assertRaisesRegex(ValueError, "Incomplete common calendar support"):
            residuals(result, [2018, 2020], np.zeros((2, 31)), self.layout)

    def test_finite_population_and_unknown_singleton(self):
        sample = [{"stratum_id": label, "N_h": size, "n_h": count}
                  for label, size, count in (("a",4,2),("a",4,2),("b",2,2),("b",2,2),("c",2,1))]
        matrix = np.array([[0], [2], [5], [1], [3]], dtype=float)
        vectors, bounds = design_vectors(matrix, sample, np.array([2.]))
        self.assertAlmostEqual(float((vectors**2).sum()), 0.125)
        self.assertEqual(vectors[2:].tolist(), [[0.], [0.], [0.]])
        self.assertEqual(bounds.tolist(), [0.5])

    def test_joint_peak_projects_whole_band(self):
        a = np.zeros(71)
        b = a.copy()
        a[:2], b[:2] = [.06,.04], [.03,.07]
        curves = {"br1999": a, "mx1999": b, "br2009": a, "mx2009": b}
        peaks = curve_summary(curves, self.layout, self.cfg["thresholds"],
                              {g: np.full(71, .015) for g in curves})
        result = peaks["age_gap"]["all_four"]
        self.assertEqual(result["start"], 21)
        self.assertEqual(result["estimate"], .04)
        np.testing.assert_allclose(result["simultaneous_interval"], [.025,.055])
        self.assertEqual(result["decision"], "unresolved")

    def test_tied_score_reaches_exact_eightieth_percentile(self):
        reference = np.tile([0.]*7 + [0.5]*2 + [1.], (1, 4))
        reference = np.repeat(reference[:, :, None], 4, axis=2)
        weights = [Fraction(1)]
        ranks = weighted_rank_tables(reference, weights)
        expected = classify_exact(reference, ranks, Fraction(4, 5))
        self.assertTrue(expected[0,7,0])
        self.assertFalse(expected[0,6,0])
        np.testing.assert_array_equal(PrecisionReference(reference, [1.], weights).flags(reference), expected)

    def test_pairing_shuffles_complete_vectors_within_blocks(self):
        rng = np.random.default_rng(1009)
        flags = rng.random((5, 40, 4)) > .5
        blocks = [np.array([0,1,2]), np.array([3,4])]
        result = shuffle_flags(flags, blocks, rng)
        check_shuffle(flags, result, blocks)
        self.assertFalse(np.array_equal(result, flags))

    def test_predeclared_injections_distinguish_age_and_calendar_peaks(self):
        controls = calibration(self.layout, self.cfg)
        self.assertLess(abs(controls["negative"]["age_gap"]["estimate"]), 1e-12)
        self.assertEqual(controls["age_injection"]["age_gap"]["start"], 25)
        self.assertLess(controls["age_injection"]["calendar_gap"]["estimate"], .05)
        self.assertEqual(controls["calendar_injection"]["calendar_gap"]["start"], 2037)
        self.assertLess(controls["calendar_injection"]["age_gap"]["estimate"], .05)


if __name__ == "__main__":
    unittest.main()
