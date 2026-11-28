import json
from pathlib import Path
import unittest

from rounds.r49.analyze import calibrate, primary_bounds
from rounds.r49.common import GROUPS


SETTINGS = json.loads((Path(__file__).parents[1] / "rounds/r49/protocol.json").read_text())
AGES = [33, 34, 35]


class P75BoundsTests(unittest.TestCase):
    def test_upper_uses_different_limiting_groups_and_group_adjustment(self):
        effects = dict(zip(GROUPS, ([.04, .08, .09], [.09, .035, .09], [.09, .09, .03], [.10, .10, .10])))
        errors = {name: [.001] * 3 for name in effects}
        bound = primary_bounds(effects, errors, AGES, SETTINGS)
        self.assertAlmostEqual(bound["upper_z"], 2.4977054744123737)
        self.assertAlmostEqual(bound["upper"], .04 + bound["upper_z"] * .001)
        self.assertEqual((bound["upper_attaining_age"], bound["upper_attaining_group"]), (33, "br1999"))
        self.assertEqual(bound["decision"], "excluded")

    def test_lower_is_preselected_and_threshold_equality_is_unresolved(self):
        effects = {name: [.12, .05, .01] for name in GROUPS}
        errors = {name: [0] * 3 for name in GROUPS}
        bound = primary_bounds(effects, errors, AGES, SETTINGS)
        self.assertEqual((bound["start_age"], bound["lower_start_age"]), (33, 34))
        self.assertEqual((bound["lower"], bound["decision"]), (.05, "unresolved"))
        effects["br1999"] = [.05] * 3
        self.assertEqual(primary_bounds(effects, errors, AGES, SETTINGS)["decision"], "unresolved")

    def test_missing_1999_arm_only_reports_a_subgroup_upper_bound(self):
        curves = {name: [.005] * 3 for name in GROUPS if name != "mx1999"}
        report = primary_bounds(curves, {g: [0] * 3 for g in curves}, AGES, SETTINGS)
        self.assertEqual(report["decision"], "incomplete_four_group")
        self.assertEqual(report["upper"], .005)
        self.assertNotIn("lower", report)
        self.assertNotIn("point", report)

    def test_synthetic_controls_recover_the_planted_positive_and_boundary_rate(self):
        checks = calibrate(SETTINGS)
        self.assertEqual(checks["matched_negative"]["decision"], "excluded")
        self.assertEqual(checks["common_gap_injected"]["decision"], "supported")
        self.assertEqual(checks["common_gap_injected"]["start_age"], 34)
        rates = checks["fixed_age_four_independent_boundary_groups"]
        self.assertGreater(rates["without_group_adjustment"], .09)
        self.assertLess(rates["with_registered_group_adjustment"], .025)


if __name__ == "__main__":
    unittest.main()
