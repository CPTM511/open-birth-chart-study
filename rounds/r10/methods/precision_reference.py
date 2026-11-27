"""R9 weighted CDF with exact design-weight threshold classification for R10."""
from fractions import Fraction
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'rounds/r9/methods'))
from fixed_reference import FixedReference
from threshold_precision import ExactWeights,classify


class PrecisionReference:
    def __init__(self,scores,weights,design_fractions):
        self.base=FixedReference(scores,weights)
        self.reference_scores=np.asarray(scores,float)
        self.reference_weights=np.asarray(weights,float)
        self.exact=ExactWeights(design_fractions)
        if len(self.exact.integers)!=len(self.reference_scores):raise ValueError('Reference weight count differs')
        self.tables={};self.diagnostics={'boundary_cells_checked':0,'float_classification_corrections':0}
        for (band,system),cdf in self.base.cdfs.items():
            values=self.reference_scores[:,band*10:band*10+10,system]
            self.tables[band,system]={'inverse':np.searchsorted(cdf.values,values),'cache':{}}
        flags=self.flags(self.reference_scores)
        self.joint_rate=float(np.average((flags.sum(axis=2)>=3).mean(axis=1),weights=weights))

    def transform(self,scores):return self.base.transform(scores)

    def flags(self,scores):
        scores=np.asarray(scores,float);q=self.transform(scores);flags=np.empty(q.shape,dtype=bool)
        for (band,system),cdf in self.base.cdfs.items():
            values=scores[:,band*10:band*10+10,system];table=self.tables[band,system]
            left=np.searchsorted(cdf.values,values,'left');right=np.searchsorted(cdf.values,values,'right')
            flags[:,band*10:band*10+10,system]=classify(q[:,band*10:band*10+10,system],left,right,table['inverse'],self.exact,cache=table['cache'],diagnostics=self.diagnostics)
        return flags

    def summarize(self,scores,weights):
        # Descriptive floating CDF/raw means are deliberately left unchanged.
        result=self.base.summarize(scores,weights);flags=self.flags(scores);joint=flags.sum(axis=2)>=3
        value=float(np.average(joint.mean(axis=1),weights=weights))
        result.update(reference_joint_rate=self.joint_rate,joint_rate=value,delta_joint_rate=value-self.joint_rate,
            age_band_joint_rates=[float(np.average(joint[:,b*10:b*10+10].mean(axis=1),weights=weights)) for b in range(4)])
        return result
