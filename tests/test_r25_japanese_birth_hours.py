"""Check critical calendar and denominator behavior of the R25 comparisons."""
from datetime import date, timedelta
from fractions import Fraction
import unittest

from rounds.r25.holiday_hours import (
    ClockCounts, compare_holidays, contrast, matched_dates, nth_monday,
)


class JapaneseHolidayHourTests(unittest.TestCase):
    def test_calendar_controls_exclude_other_holidays_and_require_both_sides(self):
        d = date(2025, 7, 21)
        offsets = [-14, -7, 7, 14]
        potential = {d + timedelta(days=n): True for n in offsets}
        self.assertEqual(
            matched_dates(d, {d - timedelta(days=7): "休日"}, potential, offsets),
            (date(2025, 7, 7), date(2025, 7, 28), date(2025, 8, 4)),
        )
        self.assertEqual(matched_dates(d, {ref: "休日" for ref in potential if ref < d}, potential, offsets), ())

    def test_daily_occupancies_are_weighted_equally_and_unknown_hours_are_excluded(self):
        actual = contrast(ClockCounts(80, 50, 10), [ClockCounts(100, 100, 30), ClockCounts(10, 10, 8)])
        self.assertEqual(actual["daytime_share_difference_pp"], Fraction(-35))
        self.assertEqual(actual["daytime_count_change_pct"], Fraction(-900, 19))
        self.assertEqual(actual["target_counts"]["unknown"], 30)

    def test_2019_official_alias_is_in_the_registered_holiday_family(self):
        day = date(2019, 10, 14)
        label = "体育の日（スポーツの日）"
        days = {day + timedelta(days=d) for d in [-14, -7, 0, 7, 14]}
        counts = {d: {s: ClockCounts(100, 100, 40) for s in ("all_venues", "hospital_and_clinic")} for d in days}
        config = {"source_years": {"2019": ""}, "primary_holidays": ["体育の日"], "relocation_years": [],
                  "control_day_offsets": [-14, -7, 7, 14], "sensitivity_day_offsets": [-7, 7]}
        main, skip, _ = compare_holidays(counts, {day: label}, config)
        self.assertEqual(len(main), 1)
        self.assertEqual(main[0]["holiday"], label)
        self.assertEqual(skip, [])
        self.assertEqual(nth_monday(2021, 10, 2), date(2021, 10, 11))
