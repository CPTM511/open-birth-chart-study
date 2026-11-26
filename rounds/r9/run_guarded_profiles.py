#!/usr/bin/env python3
"""Seal R9 source inputs and verify frozen gates before unchanged R8 scoring."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[2]
R9=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from open_birth_chart.io import load_source

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--sample',type=Path,required=True);p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--slot',choices=['brazil2016','mexico2015'],required=True);p.add_argument('--jobs',type=int,default=4);a=p.parse_args()
    if a.run_dir.exists():raise FileExistsError('Never overwrite a prior R9 run directory')
    receipt=json.loads((R9/'public_freeze_receipt.json').read_text())
    for item in receipt['files']:
        if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('Public freeze file changed: '+item['path'])
    protocol=json.loads((R9/'protocol.json').read_text())
    for path,digest in protocol['engines']['hashes'].items():
        if sha(ROOT/path)!=digest:raise ValueError('Frozen score/input engine changed')
    math=json.loads((R9/'methods/math_verification.json').read_text());cal=json.loads((R9/'methods/synthetic_calibration.json').read_text())
    if math['status']!='passed' or cal['real_R9_chart_results_inspected'] is not False:raise ValueError('Pre-score controls missing')
    if len(cal['scenarios'])!=2 or cal['design']['repetitions']!=200:raise ValueError('Calibration incomplete')
    for file,digest in cal['code_sha256'].items():
        if sha(R9/'methods'/file)!=digest:raise ValueError('Calibration implementation changed')
    rows,manifest=load_source(a.sample)
    expected_year=2016 if a.slot=='brazil2016' else 2015
    if any(int(r['birth_local'][:4])!=expected_year for r in rows):raise ValueError('Birth cohort mismatch')
    if len(rows)!=min(2000,manifest['eligible_frame_N']):raise ValueError('Fixed sample-size rule changed')
    if manifest['seed']!='OBS-R9-2026-11-27':raise ValueError('Selection seed changed')
    command=[sys.executable,str(ROOT/'scripts/run_profiles.py'),'--samples',str(a.sample),'--output',str(a.run_dir),'--jobs',str(a.jobs),'--mode','baseline']
    seal={'created_utc':datetime.now(timezone.utc).isoformat(),'slot':a.slot,'public_protocol_commit':receipt['public_protocol_commit'],'protocol_sha256':sha(R9/'protocol.json'),'supplement_sha256':sha(R9/'methods/PROTOCOL_SUPPLEMENT.md'),'calibration_sha256':sha(R9/'methods/synthetic_calibration.json'),'math_verification_sha256':sha(R9/'methods/math_verification.json'),'reference_profile_sha256':protocol['reference']['profile_sha256'],'input_manifest':manifest,'scoring_engine_hashes':protocol['engines']['hashes'],'scoring_command_uses_unchanged_R8_runner':True,'new_scores_seen_before_this_seal':False,'outcome_inputs':False}
    d=R9/'execution';d.mkdir(exist_ok=True)
    path=d/(a.slot+'_input_seal.json')
    if path.exists():raise FileExistsError('Preserve existing execution seal')
    path.write_text(json.dumps(seal,indent=2)+'\n')
    print(json.dumps({'stage':'R9_input_sealed','slot':a.slot,'records':len(rows),'input_sha256':manifest['model_input_sha256']}),flush=True)
    subprocess.run(command,check=True)
    summary=json.loads((a.run_dir/'baseline_summary.json').read_text())
    if summary['input_records']!=len(rows) or summary['tasks']!=len(rows):raise ValueError('Incomplete run')
    (d/(a.slot+'_completion.json')).write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':main()
