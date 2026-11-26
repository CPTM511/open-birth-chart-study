#!/usr/bin/env python3
"""Audit one SINASC birth-year frame and build R9 birth-only sample.

R8 parsing/coordinate/time-zone helpers are reused unchanged, with a new
explicit year and exact R9 allocation. Full source rows and selected inputs
stay outside the repository. No outcomes are parsed.
"""
import argparse
from collections import Counter,defaultdict
import csv
from datetime import datetime,timedelta
import heapq
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile
from common import SEED,quotas,rank_hash,study_id

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('r8_birth_builder',ROOT/'data_expansion/build_birth_inputs.py')
r8=importlib.util.module_from_spec(spec);spec.loader.exec_module(r8)

def raw_rows(path):
    with zipfile.ZipFile(path) as z:
        names=[x for x in z.namelist() if x.lower().endswith('.csv')]
        if len(names)!=1:raise ValueError('Expected one CSV')
        with z.open(names[0]) as f:
            reader=csv.reader(io.TextIOWrapper(f,encoding='utf-8-sig'),delimiter=';')
            headers=[x.upper() for x in next(reader)]
            fields=['DTNASC','HORANASC','SEXO','CODMUNNASC']
            absent=[x for x in fields if x not in headers]
            if absent:raise ValueError('Missing required fields: '+str(absent))
            ix=[headers.index(x) for x in fields]
            for ordinal,row in enumerate(reader,1):
                yield ordinal,tuple(row[i] if i<len(row) else '' for i in ix)

def eligible(path,year,refs,audit=None):
    for ordinal,(ds,ts,sc,mun) in raw_rows(path):
        if audit is not None:audit['counts']['raw_rows']+=1
        d=r8.brazil_date(ds)
        flags={'birth_year':d is not None and d.year==year,'clock':len(ts)==4 and ts.isascii() and ts.isdigit() and int(ts[:2])<24 and int(ts[2:])<60,'sex':sc in ('1','2'),'municipality_code':len(mun)==6 and mun.isascii() and mun.isdigit()}
        if audit is not None:
            for k,v in flags.items():
                if not v:audit['invalid_fields_nonexclusive'][k]+=1
        if not all(flags.values()):
            if audit is not None:audit['excluded']['invalid_or_missing_fields']+=1
            continue
        sex='M' if sc=='1' else 'F'
        if audit is not None:
            audit['counts']['complete_birth_fields']+=1
            audit['minute_mod5'][str(int(ts[2:])%5)]+=1
        ref=refs.get(mun)
        reason='unmatched_municipality' if ref is None else ('unresolved_timezone' if not ref['timezone_id'] else None)
        if reason:
            if audit is not None:audit['excluded'][reason]+=1
            continue
        local=datetime(d.year,d.month,d.day,int(ts[:2]),int(ts[2:]))
        offsets=r8.row_offset(local,ref['timezone_id'])
        if len(offsets)!=1:
            if audit is not None:audit['excluded']['DST_gap' if not offsets else 'DST_fold']+=1
            continue
        stratum=f'BR|{mun[:2]}|{sex}|{year}'
        if audit is not None:
            audit['counts']['eligible']+=1;audit['eligible_strata'][stratum]+=1
        yield ordinal,local,sex,mun,offsets[0],stratum

def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--year',type=int,required=True);p.add_argument('--references',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--n',type=int,default=2000)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    destination=a.out/'samples'/f'brazil{a.year}'
    if destination.exists():raise FileExistsError('Do not overwrite a sealed sample')
    refs=json.loads(a.references.read_text());audit={k:Counter() for k in ['counts','invalid_fields_nonexclusive','excluded','minute_mod5','eligible_strata']}
    for _ in eligible(a.archive,a.year,refs,audit):pass
    counts=dict(audit['eligible_strata']);q=quotas(counts,a.n)
    audit.update(year=a.year,archive_sha256=r8.sha256(a.archive),reference_sha256=r8.sha256(a.references),timezone_database=r8.timezone_database_version(),timezone_source=r8.IANA_URL,coordinate_reference_year=2022,coordinate_limitation='Municipal-seat reference, not actual birthplace; historical unmatched codes excluded',outcome_fields_used=False)
    r8.write_json(a.out/'audits'/f'brazil{a.year}_audit.json',audit)
    print(json.dumps({'stage':'audit_complete','year':a.year,'counts':audit['counts'],'excluded':audit['excluded']}),flush=True)
    heaps=defaultdict(list)
    for row in eligible(a.archive,a.year,refs):
        ordinal,local,sex,mun,offset,stratum=row;sid=f'SINASC{a.year}:row:{ordinal:07d}';rank=int(rank_hash(sid),16)
        item=(-rank,sid,row);h=heaps[stratum]
        if len(h)<q[stratum]:heapq.heappush(h,item)
        elif rank< -h[0][0]:heapq.heapreplace(h,item)
    output=[]
    for stratum,items in heaps.items():
        for neg,sid,(ordinal,local,sex,mun,offset,_) in items:
            ref=refs[mun]
            # Recheck each selected instant without the hour-level cache.
            if r8.valid_offsets(local,ref['timezone_id'])!=(offset,):raise ValueError('Selected timezone recheck failed')
            row=dict(study_id=study_id(sid),source_id=sid,source=f'SINASC-{a.year}',source_row_id=str(ordinal),birth_local=local.isoformat(),birth_utc=(local-timedelta(seconds=offset)).isoformat()+'Z',source_offset_seconds=offset,utc_offset_seconds=offset,sex_resolved=sex,sex=sex,birth_country='BR',birth_year=a.year,birth_decade=(a.year//10)*10,calendar='gregorian',instant_scale='UT',time_precision_seconds=60,time_uncertainty_seconds=None,coordinate_precision_degrees=None,clock_precision='source_display_minutes; measurement_error_unknown',quality=r8.BRAZIL_QUALITY,sampling_sha256=f'{-neg:064x}',uncertainty_flags=['municipal_seat_not_actual_birthplace_point',f'2022_coordinate_reference_for_{a.year}_birth','clock_accuracy_not_independently_verified'],timezone_source=r8.IANA_URL,**ref,**r8.weight_metadata(stratum,counts,q))
            output.append(row)
    output.sort(key=lambda x:x['study_id']);destination.mkdir(parents=True)
    for name,rows in [('birth_metadata.jsonl',output),('birth_inputs.jsonl',[{k:r.get(k) for k in r8.MODEL_KEYS} for r in output])]:
        with (destination/name).open('x') as f:
            for row in rows:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    alloc=[dict(stratum_id=h,N_h=counts[h],n_h=q[h],inclusion_probability=q[h]/counts[h],sample_weight=counts[h]/q[h]) for h in sorted(counts)]
    manifest={'source':f'brazil{a.year}','seed':SEED,'eligible_frame_N':sum(counts.values()),'sample_n':len(output),'algorithm':'1 per nonempty stratum then proportional residual capacity floor; descending exact fractional remainder, ascending stratum tie; SHA256(seed|source_id) ascending','strata':alloc,'model_input_sha256':r8.sha256(destination/'birth_inputs.jsonl'),'metadata_sha256':r8.sha256(destination/'birth_metadata.jsonl'),'archive_sha256':r8.sha256(a.archive),'reference_sha256':r8.sha256(a.references),'weight_interpretation':'Eligible source birth-year frame only; not all national births or global population','outcome_fields':[],'selection_uses_model_outputs':False}
    r8.write_json(destination/'sampling_manifest.json',manifest)
    print(json.dumps({'stage':'sample_complete','year':a.year,'n':len(output),'input_sha256':manifest['model_input_sha256']}),flush=True)

if __name__=='__main__':main()
