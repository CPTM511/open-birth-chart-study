"""Regression checks for the preregistered 偏官 examples and their counterexamples."""

import json
from pathlib import Path
import unittest

from rounds.r28.killing_cases import inspect


ROUND = Path(__file__).resolve().parents[1] / "rounds/r28"
CASE_ROWS = json.loads((ROUND / "cases.json").read_text(encoding="utf-8"))
PILLARS = {row["id"]: row["pillars"] for row in CASE_ROWS}
STEMS = "甲乙丙丁戊己庚辛壬癸"
ROLE_BY_ELEMENT_DISTANCE = (
    ("比肩", "劫财"), ("食神", "伤官"), ("偏财", "正财"), ("七杀", "正官"), ("偏印", "正印"),
)
MONTH_STEMS = {"酉": "辛", "辰": "戊乙癸", "戌": "戊辛丁", "子": "癸",
               "亥": "壬甲", "巳": "丙庚戊", "午": "丁己", "寅": "甲丙戊"}


def independent_role(day, stem):
    reference, acted = STEMS.index(day), STEMS.index(stem)
    distance = (acted // 2 - reference // 2) % 5
    return ROLE_BY_ELEMENT_DISTANCE[distance][(acted - reference) % 2]


class KillingSourceCaseTests(unittest.TestCase):
    def test_every_registered_premise_and_ten_god_has_a_source_anchor(self):
        for row in CASE_ROWS:
            with self.subTest(case=row["id"]):
                year, month, day, hour = row["pillars"]
                out = inspect(row["pillars"])
                self.assertTrue(out["conditions"][row["target"]])
                self.assertFalse(out["strength_or_transformation_adjudicated"])
                expected_visible = {
                    position: {"stem": pillar[0], "role": independent_role(day[0], pillar[0])}
                    for position, pillar in (("year", year), ("month", month), ("hour", hour))
                }
                self.assertEqual(out["visible_stems"], expected_visible)
                self.assertEqual(out["month_hidden_stems"], {
                    stem: independent_role(day[0], stem) for stem in MONTH_STEMS[month[1]]
                })

    def test_lunar_month_hides_gui_without_hiding_ren_in_case_two(self):
        actual = inspect(PILLARS[2])
        self.assertFalse(actual["visible_wealth_precedes_food"])
        self.assertEqual(actual["visible_killings_exact_in_month"], [])
        self.assertEqual(actual["visible_killings_same_element_roots_in_month"], {"壬": ["癸"]})
        self.assertEqual(actual["food_root_positions"], {"戊": ["year", "month", "day", "hour"]})

    def test_wealth_rescue_uses_hurting_officer_and_can_fail_under_literal_food(self):
        actual = inspect(PILLARS[4])
        self.assertEqual(actual["finances_resource_output_killing_links"], [
            ("hour", "month", "year", "癸", "伤官"),
        ])
        self.assertFalse(actual["strict_food_chain"])

    def test_case_eight_carries_both_source_readings_in_the_same_pillars(self):
        actual = inspect(PILLARS[8])
        self.assertEqual(actual["blade_positions"], ["hour"])
        self.assertIn("丁", actual["hidden_resource"]["hour"])
        self.assertTrue(actual["no_visible_or_hidden_output"])

    def test_remove_each_registered_structural_ingredient(self):
        counterexamples = (
            (1, ("乙亥", "甲申", "乙卯", "丁丑")),
            (3, ("丙寅", "戊戌", "壬戌", "庚子")),
            (4, ("戊戌", "甲子", "丁未", "壬寅")),
            (5, ("甲申", "乙亥", "丙戌", "辛卯")),
            (6, ("戊辰", "丁巳", "庚寅", "庚辰")),
            (7, ("丙寅", "甲午", "辛亥", "辛卯")),
            (8, ("戊辰", "甲寅", "戊寅", "丙辰")),
            (8, ("戊辰", "甲寅", "戊午", "庚申")),
        )
        for case_id, changed in counterexamples:
            with self.subTest(case=case_id, pillars=changed):
                target = CASE_ROWS[case_id - 1]["target"]
                self.assertFalse(inspect(changed)["conditions"][target])

    def test_illegal_traditional_pillar_cannot_enter_the_comparison(self):
        with self.assertRaises(ValueError):
            inspect(("癸卯", "丁卯", "庚寅", "庚辰"))
