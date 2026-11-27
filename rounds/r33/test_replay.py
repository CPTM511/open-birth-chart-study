import unittest

from rounds.r22.degrees import MANSIONS
from rounds.r32.coordinates import ShoushiCoordinates
from rounds.r33.astrometry import Epoch, signed_degrees
from rounds.r33.replay import (
    date_noon, independent_ra_label, label_at, model_boundaries, signed_widths, solar_frames,
)
from rounds.r33.source import designation_matches


class DeterminativeStarChecks(unittest.TestCase):
    def test_crosswalk_disambiguates_numbers_and_components(self):
        self.assertTrue(designation_matches("17 Tau", "17    Tau"))
        self.assertFalse(designation_matches("17 Tau", "117    Tau"))
        self.assertTrue(designation_matches("Phi1 Ori", "37Phi1Ori"))
        self.assertFalse(designation_matches("Phi1 Ori", "Phi2Ori"))
        self.assertTrue(designation_matches("Alp Lib", "9Alp2Lib"))
        self.assertFalse(designation_matches("Alp Lib", "Alp1Lup"))

    def test_projection_round_trips_through_all_quadrants(self):
        epoch = Epoch.from_ut(date_noon(2026))
        for ra in (0, 12, 89.5, 90, 123, 180, 240, 270, 359.99):
            longitude = epoch.meridian_longitude(ra)
            self.assertAlmostEqual(0, signed_degrees(epoch.ecliptic_right_ascension(longitude) - ra), places=10)

    def test_reversed_meridians_keep_labels_without_a_false_full_turn_width(self):
        ras = {name: (200 + 10 * i) % 360 for i, name in enumerate(MANSIONS)}
        ras["觜"], ras["参"] = ras["参"], ras["觜"]
        self.assertEqual(signed_widths(ras)["觜"], -10)
        epoch = Epoch.from_ut(date_noon(2026))
        boundaries = {name: epoch.meridian_longitude(ra) for name, ra in ras.items()}
        test_lon = epoch.meridian_longitude((ras["参"] + 5) % 360)
        self.assertEqual("参", label_at(test_lon, boundaries))
        self.assertEqual("参", independent_ra_label(test_lon, ras, epoch))

    def test_r32_inverted_boundaries_select_the_same_labels_as_the_adapter(self):
        jd = date_noon(2026)
        calculator = ShoushiCoordinates("wikisource_san")
        boundaries = model_boundaries(calculator, jd)
        for longitude in (0.0, 0.01, 28.35, 89.99, 90.0, 123.41, 180.0, 197.23, 270.0, 342.98, 359.999):
            for scheme, frame in solar_frames(calculator, longitude, jd).items():
                self.assertEqual(frame.solar_mansion[0], label_at(longitude, boundaries[scheme]))


if __name__ == "__main__":
    unittest.main()
