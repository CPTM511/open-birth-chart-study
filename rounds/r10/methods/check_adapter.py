"""Synthetic integration fixture for R10 adapter; not additional human records."""
from pathlib import Path
import copy,hashlib,json,tempfile,time
import numpy as np
from analyze_cohorts import analyze, ROOT
from r10_io import age_years,chart_key,sha256


def main():
    started=time.monotonic();checks=[]
    with tempfile.TemporaryDirectory(prefix='obs_r10_adapter_',dir='/tmp') as directory:
        p=Path(directory);sample=p/'sample';sample.mkdir()
        protocol=json.loads((ROOT/'rounds/r10/protocol.json').read_text())
        protocol['id']='SYNTHETIC-ADAPTER-FIXTURE-NOT-REAL-DATA'
        selected='brazil2024'
        for s in protocol['source_slots']:
            if s['id']==selected:s['status']='available';s['source_label']='SYNTHETIC-2024'
            else:s['status']='unavailable'
        protocol_path=p/'protocol.json';protocol_path.write_text(json.dumps(protocol))
        decisions={'source_slots':[{'id':s['id'],'status':s['status'],'reason':'Synthetic interface fixture, not a source availability assessment'} for s in protocol['source_slots']]}
        decision_path=p/'decisions.json';decision_path.write_text(json.dumps(decisions))
        births=[];metadata=[];profiles=[];rng=np.random.default_rng(20261127999)
        for i,sex in enumerate(['M','F']):
            birth={'study_id':f'synthetic-adapter-{sex}','birth_local':f'2024-06-0{i+1}T12:00:00','birth_utc':f'2024-06-0{i+1}T15:00:00Z','latitude':-23.,'longitude':-46.,'source_offset_seconds':-10800,'sex':sex,'calendar':'gregorian'}
            meta={**birth,'source':'SYNTHETIC-2024','source_id':f'synthetic-{i}','birth_country':'BR','quality':'synthetic','geo_precision':'synthetic','stratum_id':sex,'N_h':1,'n_h':1,'inclusion_probability':1.,'sample_weight':1.,'sampling_sha256':hashlib.sha256(f'synthetic-{i}'.encode()).hexdigest()}
            births.append(birth);metadata.append(meta)
            profiles.append({'study_id':birth['study_id'],'variant':'base','status':'computed','source':meta['source'],'calendar_years':age_years(birth['birth_local']),'chart_input_key':chart_key(birth),'primary_scores':rng.uniform(size=(40,4)).tolist()})
        for name,rows in [('birth_inputs.jsonl',births),('birth_metadata.jsonl',metadata)]:
            (sample/name).write_text(''.join(json.dumps(r)+'\n' for r in rows))
        manifest={'sample_n':2,'eligible_frame_N':2,'seed':'OBS-R10-2026-11-27','model_input_sha256':sha256(sample/'birth_inputs.jsonl'),'metadata_sha256':sha256(sample/'birth_metadata.jsonl'),'strata':[{'stratum_id':s,'n_h':1,'N_h':1} for s in ['M','F']]}
        (sample/'sampling_manifest.json').write_text(json.dumps(manifest))
        profile_path=p/'profiles.jsonl';profile_path.write_text(''.join(json.dumps(r)+'\n' for r in profiles))
        config={'protocol':str(protocol_path),'source_decisions':str(decision_path),
            'reference':{'sample_dir':str(ROOT.parent/'research_work/r8_data_expansion/samples/brazil2006'),'profile_files':['/tmp/obs_r8_runs/frozen_v1/baseline_profiles.jsonl']},
            'targets':[{'slot':selected,'sample_dir':str(sample),'profile_files':[str(profile_path)]}]}
        result=analyze(config)
        target=result['targets'][0]
        assert target['n_source_records']==2 and target['birth_years']==[2024]
        assert target['sampling_interval']['analytic_design_variance']==0
        assert result['primary_family_size']==7 and result['primary_draws']==9999
        assert result['reference_refit_sensitivity']['draws']==999
        assert target['primary_calendar_range']==[2044,2083]
        assert target['age20_39_calendar_range']==[2044,2063]
        assert target['modeled_record_years_within_2026_2070']==54
        assert all(x['joint_rate'] is None for x in target['calendar_2026_2070'] if x['year']<2044)
        checks.append('synthetic2024 complete fixture reaches all layers, retains age/calendar coverage and census variance')
        checks.append('exact protocol seeds, seven-slot family,9999 primary draws and999 refit draws are used')
        bad=copy.deepcopy(config);bad['targets']=[]
        try:analyze(bad)
        except ValueError:checks.append('missing available target is rejected before analysis')
        else:raise AssertionError('Missing slot accepted')
        bad=copy.deepcopy(config);bad['targets'].append(bad['targets'][0])
        try:analyze(bad)
        except ValueError:checks.append('duplicate target slot is rejected')
        else:raise AssertionError('Duplicate slot accepted')
        profile_path.write_text(json.dumps(profiles[0])+'\n')
        try:analyze(config)
        except ValueError:checks.append('incomplete computed-profile coverage is rejected')
        else:raise AssertionError('Partial output accepted')
    out={'status':'passed','real_R10_targets_inspected':False,'count':len(checks),'checks':checks,
        'fixture_records':2,'fixture_kind':'synthetic inputs and synthetic raw-score arrays; not actual human births',
        'reference':'existing frozen R8 Brazil2006 only','runtime_seconds':round(time.monotonic()-started,3)}
    Path(__file__).with_name('adapter_checks.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))


if __name__=='__main__':main()
