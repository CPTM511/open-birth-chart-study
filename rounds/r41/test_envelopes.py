"""Target the signed linkage bound and the gap left by three times of day."""

from datetime import date
from fractions import Fraction
from itertools import product
import unittest

import numpy as np

from rounds.r41.analyze import envelope, panel_metrics, serialize
from rounds.r41.check_release import evaluate_year


class MinuteBoundsTests(unittest.TestCase):
    def test_signed_bounds_match_joint_assignments(self):
        counts = np.array([[1, 3], [2, 0]])
        total = counts.sum()
        rows, hours = counts.sum(axis=1), counts.sum(axis=0)
        signed = total * counts - rows[:, None] * hours[None, :]
        values = np.array([[[0, 2], [2, 4]], [[0, 1], [0, 6]]])
        brute = []
        for choices in product(range(2), repeat=4):
            num = sum(int(signed[i, j] * values[i, j, choices[2 * i + j]])
                      for i, j in product(range(2), repeat=2))
            brute.append(Fraction(num, int(total**2)))
        self.assertEqual(envelope(values, signed, total**2), [min(brute), max(brute)])
        self.assertLess(min(brute), 0)
        self.assertGreater(max(brute), 0)

    def test_zero_weight_cell_can_affect_linkage_and_internal_minutes_flip(self):
        counts = np.array([[1, 3], [2, 0]])
        masks = np.zeros((2, 2, 60, 2), dtype=np.uint64)
        masks[0, 1, 17, 0] = 1 << 25
        masks[1, 1, 10, :] = (1 << 20) - 1
        baseline = Fraction(1, 1000)
        metrics = panel_metrics(counts, masks, baseline)
        three, full = (metrics["choice_sets"][key] for key in ("r34_three", "all_60"))
        self.assertEqual(three["synthetic_person_years_with_a_minute_flip_rate"], 0)
        self.assertEqual(full["synthetic_person_years_with_a_minute_flip_rate"], Fraction(3, 480))
        self.assertEqual(full["unrestricted_minute_A_rate_bounds"], [Fraction(), Fraction(3, 480)])
        self.assertLess(full["unrestricted_minute_A_minus_B_pp_bounds"][0], 0)
        cells = [(date(1999, 1, i + 1), j, int(counts[i, j]),
                  [tuple(int(x) for x in pair) for pair in masks[i, j]])
                 for i, j in product(range(2), repeat=2)]
        evaluate_year(cells, {"cohort_birth_count": 6, "metrics": serialize(metrics)}, baseline)


if __name__ == "__main__":
    unittest.main()
