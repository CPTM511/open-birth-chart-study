from datetime import date
from fractions import Fraction
from itertools import product
import unittest

import numpy as np

from rounds.r47.bounds import Cell, axis_data, numerators
from rounds.r47.verify import window_numerators


class JapanIdentificationTests(unittest.TestCase):
    def test_vector_windows_equal_independent_bits(self):
        masks = (0, 0x0200000001, 0xffffffffff, 0xaaffbbaa12)
        expected = [window_numerators(m, 10, 31) for m in masks]
        np.testing.assert_array_equal(numerators(masks, 10, 31), expected)

    def test_exact_upper_has_joint_integer_witness(self):
        axes = {"age": [20,21,22], "calendar": [2019,2020,2021]}
        day = date(1999,4,1)
        layers = [(Cell(day,0,1,(0,2)),Cell(day,1,1,(0,8))),
                  (Cell(day,0,1,(2,8)),Cell(day,1,1,(0,2)))]
        reference = [Fraction(0)]*3
        possible = [[axis_data([Cell(c.day,c.hour,1,(mask,)) for c,mask in zip(L, path, strict=True)],
                               reference,axes,2)["age"]["balanced"]
                     for path in product(*(c.masks for c in L))] for L in layers]
        observed = max(max(min(u,v) for u,v in zip(a,b,strict=True))
                       for a,b in product(*possible))
        x,y = [axis_data(L,reference,axes,2)["age"]["upper"] for L in layers]
        self.assertEqual(observed,max(min(u,v) for u,v in zip(x,y,strict=True)))


if __name__ == "__main__":
    unittest.main()
