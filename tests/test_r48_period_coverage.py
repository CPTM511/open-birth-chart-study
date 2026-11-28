from datetime import datetime, timezone
import unittest

from rounds.r48.coverage import anniversary, check_controls, extent, one_only


class PeriodCoverageTests(unittest.TestCase):
    def test_handover_uses_next_period_without_one_day_gap(self):
        self.assertEqual(one_only([(1,11),(11,21)],11),1)
        self.assertEqual(extent([(1,11),(11,21)],1,21),([],[]))
        with self.assertRaisesRegex(ValueError,"No unique period"):
            one_only([(1,11),(11,21)],21)

    def test_leap_day_and_injected_discontinuities(self):
        d=datetime(2000,2,29,23,tzinfo=timezone.utc)
        self.assertEqual(anniversary(d,10),datetime(2010,2,28,23,tzinfo=timezone.utc))
        self.assertTrue(check_controls()["deleted_decade_detected"])
        self.assertTrue(check_controls()["overlap_detected"])


if __name__=="__main__":
    unittest.main()
