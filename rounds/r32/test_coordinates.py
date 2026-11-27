from datetime import datetime
from fractions import Fraction as F
import unittest

from rounds.r32.coordinates import CHOU_READINGS, TURN, ShoushiCoordinates, calculate, label_at, palace_width, time_branches, transfer


class CoordinateTests(unittest.TestCase):
    def test_cardinal_points_and_first_tabulated_interval(self):
        table = ShoushiCoordinates("wikisource_san").table
        for quarter in range(5):
            endpoint = TURN * quarter / 4
            self.assertEqual(table.from_ecliptic(endpoint), endpoint % TURN)
            self.assertEqual(table.from_equator(endpoint), endpoint % TURN)
        self.assertEqual(table.from_ecliptic(F(1)), F("1.0865"))
        self.assertEqual(table.from_ecliptic(TURN - 1), TURN - F("1.0865"))

    def test_same_palace_heads_at_epoch_and_separate_readings(self):
        charts = {}
        for reading in CHOU_READINGS:
            calculator = ShoushiCoordinates(reading)
            printed, reprojected = calculator.sun_frames(270, 0).values()
            self.assertEqual(printed.palace_starts, reprojected.palace_starts)
            self.assertEqual(printed.sun_old_degrees, reprojected.sun_old_degrees)
            self.assertEqual(sum(palace_width(name, reprojected.palace_starts) for name in reprojected.palace_starts), TURN)
            self.assertEqual(calculator.equatorial_widths["觜"], F(".05"))
            charts[reading] = printed.palace_starts["丑"]
        self.assertEqual(charts[CHOU_READINGS[0]] - charts[CHOU_READINGS[1]], 1)

    def test_half_open_arc_including_the_turn_boundary(self):
        starts = {"甲段": F(0), "乙段": F(".05"), "丙段": TURN - F(".002")}
        self.assertEqual(label_at(TURN, starts), ("甲段", 0))
        self.assertEqual(label_at(F(".05"), starts), ("乙段", 0))
        self.assertEqual(label_at(TURN - F(".001"), starts), ("丙段", F(".001")))

    def test_unequal_palace_transfer_can_abstain(self):
        calculator = ShoushiCoordinates("wikisource_san")
        scale = calculator.printed
        solar = max(scale.heads, key=scale.palace_width)
        width = scale.palace_width(solar)
        position = scale.heads[solar] + width - F(".0001")
        longitude = 270 + (position - calculator.winter_ecliptic) * 360 / TURN
        frames = calculator.sun_frames(longitude, 0)
        frame = frames["rotated_printed_table"]
        same = transfer(frame, "卯", "head")
        self.assertEqual(same["ming_palace"], solar)
        self.assertGreater(same["palace_offset_old_units"], 30)
        self.assertEqual(same["status"], "outside_first_change_lookup")
        self.assertTrue(any(transfer(frame, hour, "head")["status"] == "outside_target_palace"
                            for hour in "子丑寅卯辰巳午未申酉戌亥"))

    def test_local_mean_solar_date_and_midnight(self):
        civil = datetime.fromisoformat("2000-01-01T00:02:00+08:00")
        self.assertEqual(time_branches(civil, 120), {"civil": "子", "local_mean_solar": "子"})
        self.assertEqual(time_branches(civil, 100), {"civil": "子", "local_mean_solar": "亥"})
        civil = datetime.fromisoformat("2000-01-01T22:59:00+08:00")
        self.assertEqual(time_branches(civil, 121), {"civil": "亥", "local_mean_solar": "子"})

    def test_both_clocks_observe_the_same_astronomical_instant(self):
        first = calculate(datetime.fromisoformat("2000-01-01T00:02:00+08:00"), 110)
        second = calculate(datetime.fromisoformat("1999-12-31T16:02:00+00:00"), 110)
        self.assertEqual(first["solar_tropical_longitude_deg"], second["solar_tropical_longitude_deg"])
        self.assertEqual(first["time_branch"]["local_mean_solar"], second["time_branch"]["local_mean_solar"])
        self.assertNotEqual(first["time_branch"]["civil"], second["time_branch"]["civil"])

    def test_invalid_coordinates_and_birth_label(self):
        with self.assertRaises(ValueError):
            calculate(datetime.fromisoformat("2000-01-01T01:00"), 110)
        with self.assertRaises(ValueError):
            calculate(datetime.fromisoformat("2000-01-01T01:00+00:00"), 181)


if __name__ == "__main__":
    unittest.main()
