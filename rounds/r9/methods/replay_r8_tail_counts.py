#!/usr/bin/env python3
"""Independent arithmetic implementation of R8's six frozen phase tests.

Reads sealed existing birth-only scores; does not import R8 analysis or score
engines. Recomputes tied ranks by unique values, independent-phase expectation
by enumerating16 binary states, and all1,999 simulation tail counts. This is
internal numerical replication, not independent outcome validation or a rerun
of source acquisition/astronomical scoring in a new environment.
"""
import argparse
from itertools import product
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import numpy as np

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--samples',type=Path,required=True);p.add_argument('--profiles',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    published=json.loads((a.repo/'results/structural_results.json').read_text())
    expected=published['baseline_run']['result_sha256']
    assert digest(a.profiles)==expected,'Frozen profile bytes differ'
    profiles={r['study_id']:r for r in map(json.loads,a.profiles.open())}
    rows=[];maxerror=0.;checks=[]
    for source in published['sources']:
        d=a.samples/source;manifest=json.loads((d/'sampling_manifest.json').read_text())
        assert digest(d/'birth_inputs.jsonl')==manifest['model_input_sha256']
        assert digest(d/'birth_metadata.jsonl')==manifest['metadata_sha256']
        metadata=sorted(map(json.loads,(d/'birth_metadata.jsonl').open()),key=lambda r:r['study_id'])
        scores=np.asarray([profiles[r['study_id']]['primary_scores'] for r in metadata]);w=np.asarray([r['sample_weight'] for r in metadata],float)
        flags=np.zeros_like(scores,dtype=bool)
        for i in range(len(scores)):
            for s in range(4):
                unique,inverse,counts=np.unique(scores[i,:,s],return_inverse=True,return_counts=True)
                mid=(np.cumsum(counts)-counts/2)/40
                flags[i,:,s]=mid[inverse]>=.8
        groups={}
        for i,r in enumerate(metadata):
            key=profiles[r['study_id']]['chart_input_key']
            if key in groups:
                ix,weight=groups[key];assert np.array_equal(flags[ix],flags[i]);groups[key]=(ix,weight+w[i])
            else:groups[key]=(i,w[i])
        ordered=[groups[k] for k in sorted(groups)];gflags=flags[[i for i,_ in ordered]].reshape(-1,4,10,4);gw=np.array([v for _,v in ordered]);gw=gw/gw.sum()
        marginal=gflags.mean(axis=2);probs=np.zeros(marginal.shape[:2])
        for state in product([False,True],repeat=4):
            if sum(state)>=3:probs+=np.prod(np.where(np.array(state)[None,None,:],marginal,1-marginal),axis=2)
        expectation=[float(gw@probs[:,:b].mean(axis=1)) for b in [4,3]]
        observed=[float(w@((flags[:,:length].sum(axis=2)>=3).mean(axis=1))/w.sum()) for length in [40,30]]
        sims=np.empty((1999,2));rng=np.random.default_rng(2026112608)
        ni=np.arange(len(gflags))[:,None,None];bi=np.arange(4)[None,:,None];pos=np.arange(10)[None,None,:]
        for k in range(1999):
            shifts=rng.integers(0,10,size=(len(gflags),4,4))
            nflags=np.zeros(gflags.shape[:3],dtype=np.int8)
            for s in range(4):nflags+=gflags[ni,bi,(pos+shifts[:,s,:,None])%10,s]
            joint=nflags>=3
            for j,b in enumerate([4,3]):sims[k,j]=gw@joint[:,:b].mean(axis=(1,2))
        for j,name in enumerate(['age20_59','age20_49']):
            tails=int(np.sum(np.abs(sims[:,j]-expectation[j])>=abs(observed[j]-expectation[j])-1e-14));raw=(1+tails)/2000
            old=published['sources'][source]['tests'][name]
            calc={'weighted_concordance':observed[j],'exact_independent_phase_mean':expectation[j],'p_raw_two_sided':raw,'phase_reference_interval95':np.quantile(sims[:,j],[.025,.975]).tolist()}
            for key,value in calc.items():
                err=float(np.max(np.abs(np.asarray(value)-np.asarray(old[key]))));maxerror=max(maxerror,err)
                checks.append({'source':source,'window':name,'quantity':key,'max_abs_error':err,'pass':err<1e-12})
            rows.append({'source':source,'window':name,'extreme_draws':tails,'raw_p':raw,'published_holm':old['p_holm_six_tests']})
        print(json.dumps({'replayed_source':source,'draws':1999}),flush=True)
    order=sorted(range(6),key=lambda i:(rows[i]['raw_p'],i));running=0
    for k,i in enumerate(order):
        running=max(running,(6-k)*rows[i]['raw_p']);adj=min(1.,running)
        rows[i]['replayed_holm']=adj;checks.append({'source':rows[i]['source'],'window':rows[i]['window'],'quantity':'holm','max_abs_error':abs(adj-rows[i]['published_holm']),'pass':abs(adj-rows[i]['published_holm'])<1e-12})
    result={'completed_utc':datetime.now(timezone.utc).isoformat(),'scope':'independent arithmetic replay of existing R8 profile phase tests; not outcome validation or full engine/source rerun','frozen_profile_sha256':expected,'draws_per_source':1999,'seed':2026112608,'r8_analysis_imported':False,'checks':checks,'all_passed':all(c['pass'] for c in checks),'max_abs_error':maxerror,'tests':rows}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'all_passed':result['all_passed'],'checks':len(checks),'max_abs_error':maxerror}),flush=True)
    if not result['all_passed']:raise SystemExit(1)

if __name__=='__main__':main()
