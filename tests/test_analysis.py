import unittest
import numpy as np
from open_birth_chart.analysis import (percentiles, weighted_rate,
    exact_phase_expectation, group_identical_inputs, phase_reference, holm,
    annual_summary)


class ReferenceTests(unittest.TestCase):
    def test_constant_profiles_have_no_elevated_signal(self):
        scores = np.ones((3, 40, 4))
        np.testing.assert_array_equal(percentiles(scores), .5 * np.ones_like(scores))
        result = phase_reference(scores, [1, 2, 1], ["a", "b", "c"], draws=99)
        self.assertEqual(result["age20_59"]["weighted_concordance"], 0)
        self.assertEqual(result["age20_59"]["p_raw_two_sided"], 1)

    def test_independent_phase_mean_matches_enumeration(self):
        flags = np.zeros((1, 40, 4), bool)
        for band in range(4):
            flags[0, band*10:band*10+2, :] = True
        expected = 4 * (.2**3) * .8 + .2**4
        self.assertAlmostEqual(exact_phase_expectation(flags, [1]), expected)
        count = 0
        total = 0
        for a in range(10):
            for b in range(10):
                for c in range(10):
                    for d in range(10):
                        count += sum(v < 2 for v in [a, b, c, d]) >= 3
                        total += 1
        self.assertAlmostEqual(expected, count / total)

    def test_identical_inputs_share_null_block_and_preserve_weight(self):
        flags = np.zeros((2, 40, 4), bool)
        f, w = group_identical_inputs(flags, [2, 5], ["same", "same"])
        self.assertEqual(f.shape, (1, 40, 4))
        self.assertEqual(w.tolist(), [7])

    def test_short_key_list_cannot_drop_null_participants(self):
        flags = np.zeros((2, 40, 4), bool)
        with self.assertRaises(ValueError):
            group_identical_inputs(flags, [1, 1], ["only_one"])
        with self.assertRaises(ValueError):
            group_identical_inputs(flags, [1], ["a", "b"])

    def test_identical_inputs_different_results_fail(self):
        flags = np.zeros((2, 40, 4), bool)
        flags[1, 0, 0] = True
        with self.assertRaises(ValueError):
            group_identical_inputs(flags, [1, 1], ["same", "same"])

    def test_missing_is_not_zero(self):
        scores = np.zeros((1, 40, 4))
        scores[0, 0, 0] = np.nan
        with self.assertRaises(ValueError): percentiles(scores)

    def test_holm_preserves_nonestimable_slot(self):
        self.assertEqual(holm([.01, .04, None, .03]), [.04, .09, None, .09])

    def test_unoccupied_calendar_year_not_zero(self):
        rows = annual_summary(np.zeros((1, 40, 4)), np.arange(2000,2040)[None,:], [1], 2039,2040)
        self.assertEqual(rows[0]["concordance"], 0)
        self.assertIsNone(rows[1]["concordance"])

    def test_column_vector_weights_rejected(self):
        flags = np.zeros((3, 40, 4), bool)
        with self.assertRaises(ValueError): weighted_rate(flags, [[1],[1],[1]])
        with self.assertRaises(ValueError): exact_phase_expectation(flags, [[1],[1],[1]])
        with self.assertRaises(ValueError): phase_reference(flags.astype(float), [[1],[1],[1]], ["a","b","c"], draws=9)

    def test_weights_change_rate_not_person_count(self):
        flags = np.zeros((2, 40, 4), bool)
        flags[0] = True
        self.assertAlmostEqual(weighted_rate(flags, [9, 1]), .9)


if __name__ == "__main__": unittest.main()
