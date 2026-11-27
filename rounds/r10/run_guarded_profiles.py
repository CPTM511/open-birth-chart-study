"""Bind R10 inputs to public freezes and source decisions before scoring."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import argparse,hashlib,json,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
R10=Path(__file__).resolve().parent
sys.path.insert(0,str(R10/'methods'))
from r10_io import load_source


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    args=parser.parse_args();config=read(args.config)
    receipts={}
    for name in ['public_freeze_receipt.json','public_source_decisions_receipt.json','public_methods_receipt.json']:
        receipt=read(R10/name)
        for file in receipt['files']:
            assert sha(ROOT/file['path'])==file['sha256'], 'Publicly sealed file changed: '+file['path']
        receipts[name]=receipt
    for file in read(R10/'verification/prior_release_manifest.json')['files']:
        assert sha(ROOT/file['path'])==file['sha256'], 'Prior release changed: '+file['path']
    protocol=read(config['protocol']);decisions=read(config['source_decisions'])
    assert decisions['protocol_sha256']==sha(config['protocol'])
    rules={r['id']:r for r in protocol['source_slots']}
    available={r['id']:r for r in decisions['source_slots'] if r['status']=='available'}
    assert len(rules)==7 and len(available)==6
    assert {s['slot'] for s in config['targets']}==set(available)
    assert read(R10/'methods/scope_extension_checks.json')['status']=='passed'
    assert read(R10/'methods/method_checks.json')['status']=='passed'
    run_dir=Path(config['run_dir'])
    if run_dir.exists():raise FileExistsError('Preserve previous run directory')
    seals=[];samples=[];expected_sources={};total=0
    for target in config['targets']:
        slot=target['slot'];rows,manifest=load_source(target['sample_dir']);decision=available[slot]
        assert len(rows)==min(2000,manifest['eligible_frame_N'])
        assert manifest['seed']==protocol['sampling']['seed']
        assert manifest['eligible_frame_N']==decision['eligible_frame_N']
        assert manifest['model_input_sha256']==decision['input_sha256']
        assert manifest['metadata_sha256']==decision['metadata_sha256']
        assert sha(Path(target['sample_dir'])/'sampling_manifest.json')==decision['sampling_manifest_sha256']
        assert {int(r['birth_local'][:4]) for r in rows}=={decision['birth_year']}
        assert decision['birth_year'] in rules[slot]['allowed_birth_years']
        assert {r['birth_country'] for r in rows}=={rules[slot]['expected_country']}
        assert {r['source'] for r in rows}=={decision['source_label']}
        samples.append(target['sample_dir']);expected_sources[decision['source_label']]=slot;total+=len(rows)
        seals.append((slot,{'created_utc':datetime.now(timezone.utc).isoformat(),'slot':slot,
            'input_manifest':manifest,'protocol_sha256':sha(config['protocol']),
            'source_decisions_sha256':sha(config['source_decisions']),
            'public_protocol_commit':receipts['public_freeze_receipt.json']['public_protocol_commit'],
            'public_source_decisions_commit':receipts['public_source_decisions_receipt.json']['public_source_decisions_commit'],
            'public_methods_commit':receipts['public_methods_receipt.json']['public_methods_commit'],
            'outcome_inputs':False,'new_real_scores_seen_before_seal':False}))
    assert total==12000
    execution=R10/'execution';execution.mkdir(exist_ok=True)
    for slot,seal in seals:
        with (execution/f'{slot}_input_seal.json').open('x') as stream:stream.write(json.dumps(seal,indent=2)+'\n')
    print(json.dumps({'stage':'all_R10_inputs_sealed','records':total,'source_slots':len(samples)}),flush=True)
    command=[sys.executable,str(R10/'methods/run_profiles.py'),'--samples',*samples,'--output',str(run_dir),'--jobs',str(config['jobs']),'--mode','baseline']
    subprocess.run(command,check=True)
    summary=read(run_dir/'baseline_summary.json')
    assert summary['input_records']==summary['tasks']==total
    assert summary['status_counts']=={'computed':total}
    assert summary['result_sha256']==sha(run_dir/'baseline_profiles.jsonl')
    counts=Counter()
    with (run_dir/'baseline_profiles.jsonl').open() as stream:
        for line in stream:
            profile=json.loads(line)
            assert profile['status']=='computed' and profile['variant']=='base'
            counts[profile['source']]+=1
    assert set(counts)==set(expected_sources)
    for source,n in counts.items():
        slot=expected_sources[source];assert n==available[slot]['sample_n']
        completion={'slot':slot,'input_records':n,'tasks':n,'status_counts':{'computed':n},
            'shared_run_records':total,'shared_profile_file':'baseline_profiles.jsonl',
            'result_sha256':summary['result_sha256'],'completed_utc':summary['completed_utc'],
            'outcome_inputs':False,'derived_from_completed_shared_run_and_actual_profile_source_counts':True}
        (execution/f'{slot}_completion.json').write_text(json.dumps(completion,indent=2)+'\n')
    (execution/'combined_completion.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
