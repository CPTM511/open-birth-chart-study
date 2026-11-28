import unittest

import numpy as np

from rounds.r46.analyze import calibration, directional, family_band, prior_selection
from rounds.r46.common import HERE, read_json


class AgeGapHoldoutTests(unittest.TestCase):
    def test_directional_upper_uses_fixed_witnesses(self):
        curves = {"a":[.02,.06],"b":[.04,.02]}
        errors = {"a":[.01,.01],"b":[.01,.01]}
        rule = {"groups_by_age":["a","b"],"lower_bound_start_age":20,"z":2.}
        result = directional(curves,errors,rule,range(20,22),.05)
        np.testing.assert_allclose(result["interval"],[0.,.04])
        self.assertEqual(result["decision"],"excluded")
        # Only the preassigned curve contributes to the upper bound at each age.
        changed = directional(curves,errors,dict(rule,groups_by_age=["b","a"]),range(20,22),.05)
        self.assertEqual(changed["decision"],"unresolved")

    def test_no_claim_at_the_exact_effect_boundary(self):
        effects = {"a":[.05,0.],"b":[.05,.01]}
        errors = {"a":[0.,0.],"b":[0.,0.]}
        self.assertEqual(family_band(effects,errors,[20,21],.05)["decision"],"unresolved")

    def test_registered_injections_recover_strength_and_age(self):
        cfg = read_json(HERE/"protocol.json")
        by_test = prior_selection(cfg,range(20,51))
        for name,items in calibration(cfg).items():
            self.assertEqual(items["injected"]["start_age"],by_test[name]["lower_bound_start_age"])
            self.assertEqual(items["injected"]["decision"],"supported")
            self.assertEqual(items["matched_negative"]["decision"],"excluded")


if __name__ == "__main__":
    unittest.main()
