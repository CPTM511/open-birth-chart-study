#!/usr/bin/env python3
"""Compute frozen four-model profiles from birth-only source samples.

Individual outputs stay in the private run directory and are not published as
personal risk assessments. This command never accepts mortality labels.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import argparse,hashlib,json,multiprocessing,os,sys,time
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src'))
from r10_io import load_source,sha256,chart_key


def init_worker():
    global bz,zw,qz,west,zw_engine
    from open_birth_chart_r10 import bazi_engine as bz,ziwei_engine as zw,qizheng_engine as qz,western_engine as west
    zw_engine=zw.ZiweiEngine()


def score_record(task):
    row,variant,shift,geo=task
    row=dict(row)
    if geo:
        row['latitude']+=geo[0];row['longitude']+=geo[1]
    years=row['calendar_years']
    out={'study_id':row['study_id'],'source':row['source'],'variant':variant,
         'calendar_years':years,'chart_input_key':row['chart_input_key']}
    try:
        b=bz.evaluate(row,years,shift_minutes=shift,include_chart=False,detailed=False)
        z=zw_engine.compute(row,years,shift_minutes=shift,include_chart=False,detailed=False)
        qn=qz.build_natal(row,shift_minutes=shift)
        wn=west.build_natal(row,shift_minutes=shift)
        q=[qz.annual_signals(qn,year) for year in years]
        w=[west.annual_signals(wn,year) for year in years]
        by=b['annual'];zy=z['annual']
        if not all(len(x)==40 for x in [by,zy,q,w]):raise ValueError('Incomplete age trajectory')
        scores=[]
        for i in range(40):
            values=[by[i].get('score'),zy[i].get('score'),q[i].get('primary_score'),w[i].get('primary_score')]
            if any(v is None or not isinstance(v,(float,int)) or not np.isfinite(v) for v in values):
                raise ValueError('Unavailable/nonfinite score in complete-trajectory analysis')
            if any(v<0 or v>1 for v in values):raise ValueError('Primary score outside frozen 0..1 range')
            scores.append(values)
        out.update(status='computed',primary_scores=scores,
            bazi_interpretive_rule_counts=dict(Counter(rule for y in by for rule in y.get('matched_interpretive_rules',[]))),
            ziwei_interpretive_rule_counts=dict(Counter(rule for y in zy for rule in y.get('matched_interpretive_rules',[]))),
            qizheng_components=[a['components'] for a in q],western_components=[a['components'] for a in w],
            qizheng_module_completeness=qn.get('module_completeness'),western_module_completeness=wn.get('module_completeness'))
    except Exception as exc:
        out.update(status='abstain',reason=type(exc).__name__+': '+str(exc),primary_scores=None)
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--samples',nargs='+',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--mode',choices=['baseline','sensitivity'],default='baseline')
    args=parser.parse_args()
    if not 1<=args.jobs<=4:raise ValueError('Use one to four bounded local worker processes')
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    result=out/(args.mode+'_profiles.jsonl')
    if result.exists():raise FileExistsError('Never overwrite an existing cohort output; choose a new run directory')
    rows=[];source_manifests=[]
    for directory in args.samples:
        r,m=load_source(directory);rows.extend(r);source_manifests.append(m)
    if len({r['study_id'] for r in rows})!=len(rows):raise ValueError('Cross-source study-ID collision')
    tasks=[]
    if args.mode=='baseline':tasks=[(r,'base',0,None) for r in rows]
    else:
        for source in sorted({r['source'] for r in rows}):
            selected=sorted([r for r in rows if r['source']==source],key=lambda r:(r['sampling_sha256'],r['study_id']))[:200]
            for row in selected:
                for shift in [-120,-30,30,120]:tasks.append((row,f'clock_{shift:+}',shift,None))
            # Only a source explicitly using municipality reference coordinates.
            approx=sorted([r for r in rows if r['source']==source and r['geo_precision']=='municipality_reference'],key=lambda r:(r['sampling_sha256'],r['study_id']))[:100]
            for row in approx:
                for label,geo in [('north',(.25,0)),('south',(-.25,0)),('east',(0,.25)),('west',(0,-.25))]:
                    tasks.append((row,'geo_'+label,0,geo))
    run={'created_utc':datetime.now(timezone.utc).isoformat(),'mode':args.mode,'input_records':len(rows),'tasks':len(tasks),'jobs':args.jobs,
         'source_manifests':source_manifests,'code_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in sorted((ROOT/'src/open_birth_chart').glob('*.py'))},
         'protocol_sha256':sha256(ROOT/'rounds/r10/protocol.json'),'input_loader_sha256':sha256(Path(__file__).with_name('r10_io.py')),'runner_sha256':sha256(Path(__file__)),'date_scope':'R10 1880–2025; R8 scoring rules','date_scope_engine_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in sorted((Path(__file__).parent/'open_birth_chart_r10').glob('*')) if p.is_file()},'outcome_inputs':False}
    (out/(args.mode+'_run_seal.json')).write_text(json.dumps(run,indent=2)+'\n')
    counts=Counter();start=time.monotonic()
    with result.open('x') as f,multiprocessing.Pool(args.jobs,initializer=init_worker) as pool:
        for i,record in enumerate(pool.imap(score_record,tasks,chunksize=4),1):
            f.write(json.dumps(record,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
            counts[record['status']]+=1
            if i%100==0 or i==len(tasks):
                f.flush();print(json.dumps({'done':i,'total':len(tasks),'statuses':dict(counts),'seconds':round(time.monotonic()-start,1)}),flush=True)
    summary={'completed_utc':datetime.now(timezone.utc).isoformat(),'mode':args.mode,'input_records':len(rows),'tasks':len(tasks),'status_counts':dict(counts),
             'elapsed_seconds':time.monotonic()-start,'result_sha256':sha256(result),'outcome_inputs':False}
    (out/(args.mode+'_summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
