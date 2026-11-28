import copy
import unittest

from .check_release import certified_objective
from .transport import extremizers


class TransportationTest(unittest.TestCase):
    def test_coupled_bounds_and_zero_margins(self):
        # Separate date minima cost 6 and cannot satisfy the minute marginal.
        dates = [2, 1, 0]
        minutes = [1, 2, 0]
        hits = [[1, 6, 80], [7, 0, 80], [80, 80, 80]]
        certificates = extremizers(dates, minutes, hits)
        lower = certified_objective(certificates["minimum"], dates, minutes, hits, 1)
        upper = certified_objective(certificates["maximum"], dates, minutes, hits, -1)
        self.assertEqual((lower, upper), (21, 57))

    def test_certificate_rejects_infeasible_inputs(self):
        dates = [2, 1]
        minutes = [1, 2]
        hits = [[1, 6], [7, 0]]
        proof = extremizers(dates, minutes, hits)["minimum"]
        bad_allocation = copy.deepcopy(proof)
        bad_allocation["allocation"][0][2] += 1
        with self.assertRaisesRegex(ValueError, "Primal margins"):
            certified_objective(bad_allocation, dates, minutes, hits, 1)
        bad_dual = copy.deepcopy(proof)
        bad_dual["row_potentials"][0] += 100
        with self.assertRaisesRegex(ValueError, "Infeasible dual"):
            certified_objective(bad_dual, dates, minutes, hits, 1)
        with self.assertRaisesRegex(ValueError, "objectives do not agree"):
            certified_objective({**proof, "signed_objective": -21}, dates, minutes, hits, 1)


if __name__ == "__main__":
    unittest.main()
