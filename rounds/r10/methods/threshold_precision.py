"""Exact >=4/5 classification at weighted-CDF floating-point boundaries.

The proximity window chooses when to use exact arithmetic; it never widens the
statistical threshold. Outside it, the ordinary finite float comparison is used.
"""
from fractions import Fraction
import math
import numpy as np

BOUNDARY_WINDOW=2e-10


class ExactWeights:
    def __init__(self, fractions):
        fractions=[x if isinstance(x,Fraction) else Fraction(x) for x in fractions]
        if not fractions or any(x<0 for x in fractions) or sum(fractions)<=0:
            raise ValueError('Exact reference weights must be nonnegative with positive total')
        denominator=math.lcm(*(x.denominator for x in fractions))
        self.integers=[x.numerator*(denominator//x.denominator) for x in fractions]
        self.total=sum(self.integers)

    @classmethod
    def from_floats(cls, values):
        return cls([Fraction(*float(x).as_integer_ratio()) for x in values])

    def elevated(self, inverse, left, right):
        if inverse.ndim!=2 or len(inverse)!=len(self.integers):
            raise ValueError('Reference observations do not match exact weights')
        coefficients=2*(inverse<left).sum(axis=1)+((inverse>=left)&(inverse<right)).sum(axis=1)
        doubled_mass=sum(w*int(c) for w,c in zip(self.integers,coefficients))
        total_mass=inverse.shape[1]*self.total
        return 5*doubled_mass>=8*total_mass


def classify(q,left,right,inverse,exact_weights,*,cache=None,diagnostics=None):
    flags=np.asarray(q)>=.8
    near=np.abs(np.asarray(q)-.8)<=BOUNDARY_WINDOW
    if not np.any(near):return flags
    exact=exact_weights() if callable(exact_weights) else exact_weights
    cache={} if cache is None else cache
    pairs=np.unique(np.stack([left[near],right[near]],axis=1),axis=0)
    for l,r in pairs:
        key=(int(l),int(r))
        if key not in cache:cache[key]=exact.elevated(inverse,*key)
        selected=near&(left==l)&(right==r)
        if diagnostics is not None:
            diagnostics['boundary_cells_checked']=diagnostics.get('boundary_cells_checked',0)+int(selected.sum())
            diagnostics['float_classification_corrections']=diagnostics.get('float_classification_corrections',0)+int(np.count_nonzero(flags[selected]!=cache[key]))
        flags[selected]=cache[key]
    return flags
