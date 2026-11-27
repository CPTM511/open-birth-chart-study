import math
import unittest

from open_birth_chart import bazi_engine as bazi, qizheng_engine as qizheng, western_engine as western
from classical import bazi_pairing, qizheng_adjust_first_limit, western_premises, ziwei_text_transformations


def birth(hour):
    return dict(study_id="unit_fixture", birth_local=f"2000-03-20T{hour}:00:00",
                source_offset_seconds=0, latitude=0, longitude=0, sex="M", calendar="gregorian")


class BaziCases(unittest.TestCase):
    def test_controlling_intervenor_and_remote_pair_are_distinct(self):
        blocked = bazi_pairing("甲庚己己")["pairs"][0]
        remote = bazi_pairing("甲丁壬己")["pairs"]
        self.assertEqual(blocked["status"], "intervening_control")
        self.assertEqual(blocked["intervening_controls"], ["month"])
        self.assertIn("remote_partial", [pair["status"] for pair in remote])

    def test_own_stem_and_competitor(self):
        self.assertIn("day_master_own_pair", [x["status"] for x in bazi_pairing("丙丁乙庚")["pairs"]])
        contested = bazi_pairing("庚乙乙丙")
        self.assertEqual(contested["competition_positions"], ["year"])
        self.assertEqual(contested["source_case_matches"][0]["eclipsed_day_pair"], ["year", "day"])
        self.assertIsNone(contested["effective_transformation"])
        self.assertIsNone(contested["net_pattern"])

    def test_officer_retention_depends_on_month_and_position(self):
        result = bazi_pairing("丙辛甲辛", "卯")
        self.assertEqual(result["source_case_matches"][0]["retained_officer"], "hour")
        self.assertEqual(bazi_pairing("丙辛甲辛", "辰")["source_case_matches"], [])
        self.assertEqual(bazi_pairing("辛辛甲丙", "卯")["source_case_matches"], [])
        with self.assertRaises(ValueError):
            bazi_pairing("丙辛甲")

    def test_normal_birth_chart_passes_only_recorded_stems(self):
        chart = bazi.build_natal(birth("12"))
        stems = [chart["pillars"][p]["stem"] for p in ("year", "month", "day", "hour")]
        self.assertIsNone(bazi_pairing(stems, chart["pillars"]["month"]["branch"])["net_pattern"])


class ZiweiCases(unittest.TestCase):
    def test_text_example_and_two_candidate_stems(self):
        self.assertEqual(ziwei_text_transformations("甲"), {"禄": "廉贞", "权": "破军", "科": "武曲", "忌": "太阳"})
        self.assertEqual(ziwei_text_transformations("庚")["忌"], "天同")
        self.assertEqual(ziwei_text_transformations("壬")["科"], "天府")
        self.assertEqual(ziwei_text_transformations("壬")["忌"], "武曲")
        with self.assertRaises(ValueError):
            ziwei_text_transformations("戌")


class QizhengCases(unittest.TestCase):
    def test_printed_ages_and_contiguous_boundaries(self):
        chart = qizheng.build_natal(birth("12"))
        for ordinal, elapsed in ((11, 10), (15, 14), (20, 19)):
            with self.subTest(ordinal=ordinal):
                early = qizheng_adjust_first_limit(chart, math.nextafter(elapsed, 0), ordinal)
                on = qizheng_adjust_first_limit(chart, elapsed, ordinal)
                following = qizheng_adjust_first_limit(chart, elapsed + 10, ordinal)
                self.assertEqual((early["period"], on["period"], following["period"]), ("命", "相貌", "福德"))
                self.assertEqual(early["end_elapsed_year_exclusive"], on["start_elapsed_year"])
                self.assertEqual(on["end_elapsed_year_exclusive"], following["start_elapsed_year"])

    def test_missing_age_and_period_end_abstain(self):
        chart = qizheng.build_natal(birth("12"))
        self.assertIsNone(qizheng_adjust_first_limit(chart, 33)["period"])
        self.assertEqual(qizheng_adjust_first_limit(chart, 95.5, 11)["status"], "outside_this_cycle")
        for invalid in (10, 21, 11.5, True):
            with self.assertRaises(ValueError):
                qizheng_adjust_first_limit(chart, 33, invalid)


class WesternCases(unittest.TestCase):
    def test_whole_day_and_night_use_geometric_altitude(self):
        day = western_premises(western.build_natal(birth("12")))
        night = western_premises(western.build_natal(birth("00")))
        self.assertEqual((day["sect"], night["sect"]), ("day", "night"))
        self.assertEqual(day["malefic_moderation_by_sect_only"], {"Mars": False, "Saturn": True})
        self.assertEqual(night["malefic_moderation_by_sect_only"], {"Mars": True, "Saturn": False})

    def test_horizon_and_zodiac_boundaries(self):
        natal = western.build_natal(birth("12"))
        for alt in (-.25, 0, .25):
            natal["sect"]["geometric_solar_altitude_deg"] = alt
            result = western_premises(natal)
            self.assertIsNone(result["sect"])
            self.assertEqual(result["malefic_moderation_by_sect_only"], {"Mars": None, "Saturn": None})
        for longitude, exalted, fall in ((0, True, False), (30, False, False), (180, False, True),
                                        (math.nextafter(360, 0), False, False)):
            natal["planets"]["Sun"]["longitude"] = longitude
            value = western_premises(natal)["essential_dignities_by_sign"]["Sun"]
            self.assertEqual((value["exaltation"], value["fall"]), (exalted, fall))

    def test_active_contact_and_progression_boundaries(self):
        natal = western.build_natal(birth("12"))
        jd = natal["birth"]["jd_ut"]
        at_birth = western.progressed_chart(natal, jd)
        self.assertEqual(at_birth["progressed_jd_ut"], jd)
        with self.assertRaises(ValueError):
            western.progressed_chart(natal, jd - 1)
        for delta, expected in [(0, 1), (1.5, .5), (3, 0), (3.0001, 0)]:
            self.assertAlmostEqual(western.contact_index({"Mars": 90 + delta}, {"Sun": 0}, (90,), 3), expected)


if __name__ == "__main__":
    unittest.main()
