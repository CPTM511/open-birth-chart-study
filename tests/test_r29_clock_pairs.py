"""Check date carryover and preservation of opposite paired transitions."""

from datetime import datetime, timedelta
from fractions import Fraction
import unittest

import numpy as np

from rounds.r29.clock_pairs import rounding_shift
from rounds.r29.compare import check_transitions, paired_metrics


class ClockPairTests(unittest.TestCase):
    def test_nearest_hour_stays_or_carries_the_date(self):
        clocks = [
            ("1997-12-18T12:00", "1997-12-18T12:00"),
            ("1997-12-18T12:29", "1997-12-18T12:00"),
            ("1997-12-18T12:30", "1997-12-18T13:00"),
            ("1997-12-18T23:59", "1997-12-19T00:00"),
        ]
        for unrounded, expected in clocks:
            civil = datetime.fromisoformat(unrounded)
            self.assertEqual(civil + timedelta(minutes=rounding_shift(civil)), datetime.fromisoformat(expected))

    def test_paired_transitions_count_even_when_the_net_difference_is_zero(self):
        flags = np.zeros((2, 2, 40, 4), dtype=bool)
        flags[0, 0, 0, :3] = True
        flags[1, 0, 1, :3] = True
        weights = [Fraction(3), Fraction(1)]
        metrics = paired_metrics(flags, [float(weight) for weight in weights])
        exact = check_transitions(flags, weights, metrics)
        self.assertEqual(exact["rounded_minus_original_pp"], "0")
        self.assertEqual(exact["joint_reversal_rate"], "3/80")
        self.assertEqual(exact["records_with_any_reversal_rate"], "3/4")
        self.assertEqual(exact["joint_lost_rate"], exact["joint_gained_rate"])
        self.assertEqual(exact["system_0"], "3/80")
        self.assertEqual(exact["system_3"], "0")
