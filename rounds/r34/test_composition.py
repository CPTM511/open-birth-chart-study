import itertools
import unittest
from datetime import date
from fractions import Fraction

import numpy as np

from rounds.r34.analyze import exact_rate_replay, mixed_rates, weighted_sex_bounds
from rounds.r34.profiles import keys_for, row_for, sensitivity_dates


class CompositionChecks(unittest.TestCase):
    def test_identical_daily_hour_mix_preserves_both_margins(self):
        hours = np.array([2, 4] * 12)
        counts = np.array([2, 3, 8])[:, None] * hours
        hits = np.tile(np.array([10, 20] * 12), (3, 1))
        reported = mixed_rates(counts, hits)
        self.assertEqual(reported, exact_rate_replay(counts, hits))
        measured, independent, uniform = reported.values()
        self.assertEqual(measured, independent)
        self.assertEqual(measured, Fraction(5, 24))
        self.assertEqual(uniform, Fraction(3, 16))

    def test_population_bounds_with_known_sex_totals_match_enumeration(self):
        counts = np.array([[2, 1], [0, 2]])
        rates = np.array([[[7, 8], [4, 2]], [[0, 4], [5, 4]]])
        for males in range(6):
            candidates = []
            for allocations in itertools.product(*(range(int(n) + 1) for n in counts.ravel())):
                if sum(allocations) == males:
                    m = np.array(allocations).reshape(counts.shape)
                    candidates.append(Fraction(int(np.sum((counts - m) * rates[..., 0] + m * rates[..., 1])), 200))
            self.assertEqual(weighted_sex_bounds(counts, rates, males), [min(candidates), max(candidates)])

    def test_calendar_supported_as_registered(self):
        year = 1999
        scheduled = sensitivity_dates(year)
        self.assertEqual({month: sum(d.month == month for d in scheduled) for month in range(1, 13)},
                         dict.fromkeys(range(1, 13), 2))
        keys = [key for month in range(1, 13) for key in keys_for(year, month)]
        self.assertEqual(len(set(keys)), (365 + 24 * 3) * 24 * 2)
        self.assertEqual(len(keys_for(year, 0)), 48)

    def test_preserves_civil_birth_day_when_ut_is_previous_day(self):
        row = row_for(date(1999, 1, 1), 0, 0, 0)
        self.assertEqual(row["birth_local"], "1999-01-01T00:30:00")
        self.assertEqual(row["birth_utc"], "1998-12-31T15:30:00Z")
        self.assertEqual(row["calendar_years"], list(range(2019, 2059)))


if __name__ == "__main__":
    unittest.main()
