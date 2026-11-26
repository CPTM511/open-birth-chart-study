"""R9 source-frame allocation, fixed before chart scoring."""
from fractions import Fraction
import hashlib

SEED = 'OBS-R9-2026-11-27'

def quotas(counts, target=2000):
    """One per nonempty stratum, then residual-capacity largest remainders.

    q_h = 1 + floor((n-H)*(N_h-1)/(N-H)); allocate remaining slots by
    descending fractional remainder, ascending stratum string on ties.
    Fractions avoid platform-dependent rounding. If N<=target, take census.
    """
    counts={str(h):int(n) for h,n in counts.items() if n>0}
    if not counts:return {}
    N=sum(counts.values());n=min(target,N);H=len(counts)
    if n==N:return dict(counts)
    if n<H:raise ValueError('Target smaller than number of strata')
    ideal={h:Fraction((n-H)*(v-1),N-H) for h,v in counts.items()}
    out={h:1+int(x) for h,x in ideal.items()}
    for h in sorted(counts,key=lambda h:(-(ideal[h]-int(ideal[h])),h))[:n-sum(out.values())]:
        out[h]+=1
    assert sum(out.values())==n and all(1<=out[h]<=counts[h] for h in out)
    return out

def rank_hash(source_id):
    return hashlib.sha256((SEED+'|'+source_id).encode()).hexdigest()

def study_id(source_id):
    return 'R9-'+hashlib.sha256(source_id.encode()).hexdigest()[:24]
