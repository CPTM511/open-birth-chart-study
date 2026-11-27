import json
from pathlib import Path
import unittest

from officer_cases import officer_premises, read_pillars

CASES = json.loads(Path(__file__).with_name("cases.json").read_bytes())


class OfficerCasesTest(unittest.TestCase):
    def test_all_classical_cases_and_expected_premises(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                result = officer_premises(case["pillars"])
                self.assertEqual(result["source_conditions"], [case["expected"]])
                self.assertIsNone(result["unique_yongshen"])
                self.assertIsNone(result["transformation_effectiveness"])

    def test_opposing_fixtures_require_their_own_conditions(self):
        changed = (
            (0, 3, "辛巳"),
            (1, 0, "丁卯"),
            (2, 0, "乙亥"),
            (3, 3, "庚戌"),
            (4, 3, "辛未"),
            (5, 2, "己卯"),
            (5, 3, "甲子"),
        )
        for i, column, replacement in changed:
            case = CASES[i]
            pillars = case["pillars"].copy()
            pillars[column] = replacement
            with self.subTest(case=case["id"], replacement=replacement):
                self.assertNotIn(case["expected"], officer_premises(pillars)["source_conditions"])

    def test_officer_must_be_month_main_or_exposed(self):
        chart = officer_premises(["壬戌", "丁未", "戊申", "甲寅"])
        self.assertEqual(chart["monthly_officer_stems"], ["乙"])
        self.assertFalse(chart["officer_context"])
        self.assertEqual(chart["source_conditions"], [])

    def test_invalid_branch_and_incompatible_stems(self):
        for case in (("壬戌","丁未","戊甲","乙卯"),
                     ("壬戌","乙未","戊申","乙卯"),
                     ("壬戌","丁未","戊申","丁卯")):
            with self.subTest(pillars=case):
                with self.assertRaises(ValueError):
                    read_pillars(case)


if __name__ == "__main__":
    unittest.main()
