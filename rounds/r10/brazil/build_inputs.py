"""R10 birth-only SINASC audit and deterministic sample, using frozen R9 parsers.

Audit and sample are separate operations. No chart scores or outcomes are read.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import timedelta
import hashlib
import heapq
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'rounds/r9/data'))
spec = importlib.util.spec_from_file_location('frozen_r9_brazil_builder', ROOT/'rounds/r9/data/build_brazil.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
r8 = prior.r8
SEED = 'OBS-R10-2026-11-27'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2)+'\n')


def audit(args, refs):
    report = {k:Counter() for k in ['counts','invalid_fields_nonexclusive','excluded','minute_mod5','eligible_strata']}
    for _ in prior.eligible(args.archive, args.year, refs, report):
        pass
    report.update(year=args.year, archive_sha256=r8.sha256(args.archive),
        reference_sha256=r8.sha256(args.references), timezone_database=r8.timezone_database_version(),
        timezone_source=r8.IANA_URL, coordinate_reference_year=2022,
        coordinate_limitation='Official municipal-seat reference, not precise birthplace; unresolved historical codes/zones excluded',
        birth_fields_only=True, outcome_fields_used=False,
        parsing_implementation_sha256=r8.sha256(ROOT/'rounds/r9/data/build_brazil.py'))
    assert report['counts']['raw_rows'] == report['counts']['eligible'] + sum(report['excluded'].values())
    write(args.audit, report)
    print(json.dumps({'stage':'audit_complete','year':args.year,'counts':report['counts'],'excluded':report['excluded']}), flush=True)


def sample(args, refs):
    protocol = json.loads((ROOT/'rounds/r10/protocol.json').read_text())
    receipt = json.loads((ROOT/'rounds/r10/public_freeze_receipt.json').read_text())
    for item in receipt['files']:
        assert r8.sha256(ROOT/item['path']) == item['sha256'], 'Changed public freeze file'
    slots = {s['id']:s for s in protocol['source_slots']}
    slot = slots[args.slot]
    assert slot['expected_country']=='BR' and args.year in slot['allowed_birth_years']
    assert protocol['sampling']['seed']==SEED and protocol['sampling']['n_per_slot']==2000
    report = json.loads(args.audit.read_text())
    assert report['year']==args.year
    assert report['archive_sha256']==r8.sha256(args.archive)
    assert report['reference_sha256']==r8.sha256(args.references)
    assert report['timezone_database']==r8.timezone_database_version()
    assert report['timezone_database'].removeprefix('# version ')=='2026c', 'Exact version required for this release'
    counts = report['eligible_strata']
    quota = prior.quotas(counts, 2000)
    heaps = defaultdict(list)
    for row in prior.eligible(args.archive, args.year, refs):
        ordinal, local, sex, municipality, offset, stratum = row
        source_id = f'SINASC{args.year}:row:{ordinal:07d}'
        ranking = int(hashlib.sha256((SEED+'|'+source_id).encode()).hexdigest(), 16)
        item = (-ranking, source_id, row)
        bucket = heaps[stratum]
        if len(bucket)<quota[stratum]:
            heapq.heappush(bucket,item)
        elif ranking < -bucket[0][0]:
            heapq.heapreplace(bucket,item)
    output=[]
    for stratum, bucket in heaps.items():
        for negative, source_id, (ordinal, local, sex, municipality, offset, _) in bucket:
            ref=refs[municipality]
            assert r8.valid_offsets(local,ref['timezone_id'])==(offset,)
            row=dict(study_id='R10-'+hashlib.sha256(source_id.encode()).hexdigest()[:24],
                source_id=source_id,source=f'SINASC-{args.year}',source_row_id=str(ordinal),
                birth_local=local.isoformat(),birth_utc=(local-timedelta(seconds=offset)).isoformat()+'Z',
                source_offset_seconds=offset,utc_offset_seconds=offset,sex_resolved=sex,sex=sex,
                birth_country='BR',birth_year=args.year,birth_decade=(args.year//10)*10,
                calendar='gregorian',instant_scale='UT',time_precision_seconds=60,
                time_uncertainty_seconds=None,coordinate_precision_degrees=None,
                clock_precision='source_display_minutes; measurement_error_unknown',quality=r8.BRAZIL_QUALITY,
                sampling_sha256=f'{-negative:064x}',timezone_source=r8.IANA_URL,
                uncertainty_flags=['municipal_seat_not_actual_birthplace_point',
                    f'2022_coordinate_reference_for_{args.year}_birth','clock_accuracy_not_independently_verified'],
                **ref,**r8.weight_metadata(stratum,counts,quota))
            output.append(row)
    output.sort(key=lambda row:row['study_id'])
    args.out.mkdir(parents=True,exist_ok=False)
    for name,rows in [('birth_metadata.jsonl',output),('birth_inputs.jsonl',[{k:r.get(k) for k in r8.MODEL_KEYS} for r in output])]:
        with (args.out/name).open('x') as stream:
            for row in rows:
                stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    allocations=[dict(stratum_id=h,N_h=counts[h],n_h=quota[h],inclusion_probability=quota[h]/counts[h],sample_weight=counts[h]/quota[h]) for h in sorted(counts)]
    manifest=dict(source=f'brazil{args.year}',slot=args.slot,seed=SEED,
        eligible_frame_N=sum(counts.values()),sample_n=len(output),strata=allocations,
        algorithm='Frozen R9 exact residual-capacity allocation; SHA256(R10 seed|stable source row ID) ascending',
        model_input_sha256=r8.sha256(args.out/'birth_inputs.jsonl'),metadata_sha256=r8.sha256(args.out/'birth_metadata.jsonl'),
        archive_sha256=report['archive_sha256'],reference_sha256=report['reference_sha256'],
        audit_sha256=r8.sha256(args.audit),sampling_code_sha256=r8.sha256(Path(__file__)),
        timezone_database=report['timezone_database'],public_protocol_commit=receipt['public_protocol_commit'],
        weight_interpretation='Restricted eligible source-year frame only; not an entire decade or humanity',
        outcome_fields=[],selection_uses_model_outputs=False)
    write(args.out/'sampling_manifest.json',manifest)
    print(json.dumps({'stage':'sample_complete','slot':args.slot,'year':args.year,'records':len(output),'input_sha256':manifest['model_input_sha256']}),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['audit','sample'],required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--year',type=int,required=True)
    parser.add_argument('--references',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--slot')
    args=parser.parse_args()
    refs=json.loads(args.references.read_text())
    if args.mode=='audit':
        audit(args,refs)
    else:
        if args.out is None or args.slot is None:parser.error('sample requires --out and --slot')
        sample(args,refs)


if __name__=='__main__':
    main()
