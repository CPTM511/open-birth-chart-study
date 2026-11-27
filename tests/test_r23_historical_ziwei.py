"""Regression checks for the fixed R23 scans and late-zi branch handling."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUND = ROOT / "rounds" / "r23"
spec = importlib.util.spec_from_file_location("r23_classical", ROUND / "classical.py")
classical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(classical)


class R23HistoricalZiweiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.published = (ROUND / "results.json").read_bytes()
        cls.result = json.loads(cls.published)
        cls.rows = {row["slot"]: row for row in cls.result["charts"]}

    def test_classical_named_chart_and_invalid_day(self):
        birth = dict(ganzhi="庚戌", lunar_month=3, lunar_day=18, hour_branch="辰", is_leap=False)
        actual = classical.calculate(birth)
        self.assertEqual((actual["life"], actual["body"], actual["life_pair"], actual["bureau"]),
                         ("子", "申", "戊子", 6))
        self.assertEqual(actual["stars"]["紫微"], ["辰"])
        self.assertEqual(actual["stars"]["天府"], ["子"])
        with self.assertRaises(ValueError):
            classical.calculate({**birth, "lunar_day": 31})
        with self.assertRaises(ValueError):
            classical.calculate({**birth, "ganzhi": "甲丑"})
        with self.assertRaises(ValueError):
            classical.calculate({**birth, "hour_branch": ""})

    def test_sealed_chart_replay_is_byte_exact(self):
        result = subprocess.run([sys.executable, str(ROUND / "replay.py")], capture_output=True, check=True)
        self.assertEqual(sha256(result.stdout).hexdigest(), sha256(self.published).hexdigest())

    def test_early_zi_and_late_zi_are_retained_in_two_carriers(self):
        row = self.rows["195R"]
        for carrier in row["modern_by_carrier"]:
            self.assertEqual(carrier["status"], "valid")
            early, late = carrier["variants"]
            self.assertEqual((early["branch"], late["branch"]), ("early_zi", "late_zi"))
            self.assertEqual((early["processed_lunar_date"]["day"], late["processed_lunar_date"]["day"]), (1, 2))
            self.assertEqual(early["vs_printed"]["紫微"], "equal")
            self.assertEqual(late["vs_printed"]["紫微"], "different")
        self.assertEqual(row["comparison"]["printed_modern"]["紫微"], "variant_dependent")
        self.assertEqual(row["comparison"]["printed_modern"]["life"], "equal")

    def test_unread_and_duplicated_printed_stars_are_treated_differently(self):
        self.assertIsNone(self.rows["197R"]["printed"]["天梁"])
        self.assertEqual(self.rows["197R"]["comparison"]["printed_classical"]["天梁"], "source_unread")
        duplicate = self.rows["199L"]
        self.assertEqual(duplicate["printed"]["武曲"], ["午", "申"])
        self.assertEqual(duplicate["printed"]["天相"], ["申", "戌"])
        self.assertEqual(duplicate["comparison"]["printed_classical"]["武曲"], "different")
        self.assertEqual(duplicate["comparison"]["printed_ziwei_origin_other_stars"]["天相"], "different")

    def test_disputed_start_is_distinct_from_star_steps(self):
        row = self.rows["194L"]
        self.assertEqual(row["printed"]["紫微"], ["亥"])
        self.assertEqual(row["classical"]["stars"]["紫微"], ["未"])
        star_mismatches = sum(row["comparison"]["printed_classical"][s] == "different" for s in classical.STARS)
        self.assertEqual(star_mismatches, 14)
        self.assertEqual(set(row["comparison"]["printed_ziwei_origin_other_stars"].values()), {"equal"})
