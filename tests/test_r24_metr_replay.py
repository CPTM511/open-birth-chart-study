"""Regression checks for the explicit METR treatment and status denominators."""
from pathlib import Path
import math
import runpy
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "rounds" / "r24" / "replay.py"))
Task = MODULE["Task"]


class R24METRTests(unittest.TestCase):
    def test_early_csv_uses_numeric_treatment_codes(self):
        header = ("issue_id,dev_id,ai_treatment,predicted_time_no_ai,initial_implementation_time,"
                  "post_review_implementation_time\n")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "early.csv"
            path.write_text(header + "1,4,1.0,60,50,\n2,4,0.0,55,62,0\n", encoding="utf-8")
            actual = MODULE["read_tasks"](path, early=True)
            self.assertEqual([x.ai for x in actual], [1, 0])
            self.assertIsNone(actual[0].review)
            self.assertEqual(actual[1].review, 0.0)
            path.write_text(header + "1,4,1.1,60,50,\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE["read_tasks"](path, early=True)

    def test_all_five_statuses_stay_in_completion_denominator(self):
        records = [(0, "complete"), (0, "incomplete"), (0, "cheating"),
                   (1, "complete"), (1, "complete"), (1, "corrupted"), (1, "ditched")]
        tasks = [Task(str(i), str(i % 3), arm, status, False, None, None, None)
                 for i, (arm, status) in enumerate(records)]
        actual = MODULE["completed_share"](tasks)
        self.assertEqual(actual["by_assignment"]["no_ai"]["n_released"], 3)
        self.assertEqual(actual["by_assignment"]["ai"]["n_released"], 4)
        self.assertEqual(actual["by_assignment"]["ai"]["counts"]["corrupted"], 1)
        self.assertEqual(actual["by_assignment"]["no_ai"]["counts"]["cheating"], 1)
        self.assertAlmostEqual(actual["share_diff_ai_minus_no_ai"], 1 / 2 - 1 / 3, places=9)

    def test_effect_sign_and_scale_for_known_time_ratio(self):
        tasks = [Task(str(i), str(i % 3), i % 2, "complete", None, 15.0 + i, 10.0, 0.0)
                 for i in range(12)]
        outcome = [x.predicted ** 0.7 * 2 * (0.8 if x.ai else 1.0) for x in tasks]
        actual = MODULE["time_estimate"](tasks, outcome)
        self.assertAlmostEqual(actual["time_change_ratio"], -0.2, places=10)
        self.assertAlmostEqual(actual["log_coefficient"], math.log(0.8), places=9)
        self.assertEqual(actual["n_developers"], 3)
