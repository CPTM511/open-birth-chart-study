"""Pre-target synthetic and exact-enumeration checks for R10 additions."""
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'rounds/r9/methods'))
from fixed_reference import FixedReference
from reference_sensitivity import ReferenceCache, RecordDesign, run_sensitivity
from precision_reference import PrecisionReference


def exact_toy_flags(raw,weights,queries):
    result=np.empty(queries.shape,dtype=bool)
    weights=[Fraction(x) for x in weights]
    for band in range(4):
        for system in range(4):
            observations=[(float(x),w) for record,w in zip(raw,weights) for x in record[band*10:band*10+10,system]]
            total=sum(w for _,w in observations)
            for i in range(len(queries)):
                for age in range(band*10,band*10+10):
                    x=float(queries[i,age,system])
                    low=sum(w for v,w in observations if v<x)
                    equal=sum(w for v,w in observations if v==x)
                    result[i,age,system]=5*(2*low+equal)>=8*total
    return result


def checks():
    passed=[]
    n,N=3,12
    v=np.array([0.,.25,.75]);fpc=np.sqrt(1-n/N);means=[]
    for draw in product(range(n),repeat=n-1):
        m=np.bincount(draw,minlength=n);g=1-fpc+fpc*n/(n-1)*m
        assert np.all(g>=0) and abs(g.sum()-n)<1e-13
        means.append(np.average(v,weights=g))
    expected=(1-Fraction(n,N))*sum((Fraction(float(x))-Fraction(1,3))**2 for x in v)/(n-1)/n
    assert abs(np.var(means,ddof=0)-float(expected))<1e-14
    passed.append('all nine n-1 resamples preserve total, nonnegative weights and exact finite-frame mean variance')
    design=RecordDesign.from_frame([4,4,4],['A']*3,{'A':12});rng=np.random.default_rng(202611271001)
    for _ in range(100):
        w=design.draw(rng);assert np.all(w>0) and abs(w.sum()-12)<1e-12
    passed.append('100 replicate draws preserve finite-frame stratum totals')
    census=RecordDesign.from_frame([1,1,1],['A']*3,{'A':3})
    assert np.array_equal(census.draw(rng),[1,1,1])
    passed.append('census replicate weights are unchanged')
    try:RecordDesign.from_frame([12],['A'],{'A':12})
    except ValueError:passed.append('non-census singleton produces unavailable sensitivity')
    else:raise AssertionError('Singleton variance invented')
    r=rng.uniform(size=(12,40,4));t=rng.uniform(size=(15,40,4))
    r[:,:,0]=np.round(r[:,:,0]*8)/8;r[:,:,1]=np.round(r[:,:,1]*2)/2
    t[:,:,0]=np.round(t[:,:,0]*8)/8;t[:,:,1]=np.round(t[:,:,1]*2)/2
    cache=ReferenceCache(r,{'target':t})
    for _ in range(10):
        w=rng.uniform(.01,5,size=len(r));full=cache.transform(w,full=True);primary=FixedReference(r,w)
        assert np.max(abs(full['target']-primary.transform(t)))<1e-13
        assert np.max(abs(full['reference']-primary.transform(r)))<1e-13
        rates=cache.transform(w)
        assert np.array_equal(rates['target'],(np.sum(full['target']>=.8,axis=2)>=3).mean(axis=1))
        assert abs(np.average(full['reference'].mean(axis=(1,2)),weights=w)-.5)<1e-13
    passed.append('cached refit CDF equals original implementation for 10 reweightings with ties')
    passed.append('refitted reference percentile mean remains one half with unequal weights')
    identical=ReferenceCache(r,{'identical':r}).transform(np.ones(len(r)))
    assert np.array_equal(identical['reference'],identical['identical'])
    passed.append('identical score arrays have identical joint flags under a shared reference')
    boundary=np.zeros((5,40,4));boundary[3:]=1
    cases=[('exact equality',[Fraction(7,5)]*5,True),
        ('strictly below',[Fraction(10**11)]*4+[Fraction(10**11+1)],False),
        ('strictly above',[Fraction(10**11+1)]+[Fraction(10**11)]*4,True)]
    for label,exact,expect_one in cases:
        w=np.asarray(exact,float);primary=PrecisionReference(boundary,w,exact)
        oracle=exact_toy_flags(boundary,exact,boundary)
        assert np.all(oracle[3:]==expect_one)
        assert not np.any(oracle[:3])
        assert np.array_equal(primary.flags(boundary),oracle)
        rates=ReferenceCache(boundary,{}).transform(w)['reference']
        assert np.array_equal(rates,(oracle.sum(axis=2)>=3).mean(axis=1))
        expected_rate=float(np.average((oracle.sum(axis=2)>=3).mean(axis=1),weights=w))
        assert abs(primary.joint_rate-expected_rate)<1e-15
        assert abs(primary.summarize(boundary,w)['joint_rate']-expected_rate)<1e-15
    equal=PrecisionReference(boundary,np.full(5,7/5),[Fraction(7,5)]*5)
    assert abs(equal.joint_rate-.4)<1e-15 and equal.base.joint_rate==0
    passed.append('exact 4/5 equality is included and both sides about 1e-13 away match an independent Fraction oracle without tolerance widening')
    src={'scores':boundary,'weights':np.full(5,7/5),'strata':['A']*5,'frame_counts':{'A':7}}
    sensitivity=run_sensitivity(src,{'identical':src},draws=10,reference_seed=111,target_seeds={'identical':112})
    assert sensitivity['targets'][0]['point_delta_joint_rate']==0
    assert np.array_equal(ReferenceCache(boundary,{}).transform(src['weights'],exact_design_weights=RecordDesign.from_frame(src['weights'],src['strata'],src['frame_counts']).exact_weights())['reference'],[0,0,0,1,1])
    passed.append('sensitivity baseline and primary use the same exact design-weight boundary rule')
    return {'status':'passed','count':len(passed),'checks':passed,'real_R10_targets_inspected':False,
        'scope':'Arithmetic and implementation checks; not confidence-coverage validation or real-world prediction'}


if __name__=='__main__':
    result=checks();Path(__file__).with_name('method_checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
