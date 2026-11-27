"""Verify the explicit 2020s input extension without modifying R8 code."""
import ast,hashlib,importlib.util,json,os
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).parent


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def checks():
    old=(ROOT/'src/open_birth_chart/io.py').read_text();new=(HERE/'r10_io.py').read_text()
    assert old.replace('1880<=civil.year<=2019','1880<=civil.year<=2025')==new
    oldrunner=(ROOT/'scripts/run_profiles.py').read_text();newrunner=(HERE/'run_profiles.py').read_text()
    expected=oldrunner.replace('ROOT=Path(__file__).resolve().parents[1]','ROOT=Path(__file__).resolve().parents[3]').replace('from open_birth_chart.io import load_source,sha256,chart_key','from r10_io import load_source,sha256,chart_key').replace('from open_birth_chart import bazi_engine as bz,ziwei_engine as zw,qizheng_engine as qz,western_engine as west','from open_birth_chart_r10 import bazi_engine as bz,ziwei_engine as zw,qizheng_engine as qz,western_engine as west').replace("'protocol_sha256':sha256(ROOT/'protocol/study_protocol.json'),'outcome_inputs':False}","'protocol_sha256':sha256(ROOT/'rounds/r10/protocol.json'),'input_loader_sha256':sha256(Path(__file__).with_name('r10_io.py')),'runner_sha256':sha256(Path(__file__)),'date_scope':'R10 1880–2025; R8 scoring rules','date_scope_engine_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in sorted((Path(__file__).parent/'open_birth_chart_r10').glob('*')) if p.is_file()},'outcome_inputs':False}")
    assert expected==newrunner
    functions={}
    for name in ['init_worker','score_record']:
        originals=[n for n in ast.parse(oldrunner).body if isinstance(n,ast.FunctionDef) and n.name==name]
        additions=[n for n in ast.parse(newrunner).body if isinstance(n,ast.FunctionDef) and n.name==name]
        assert len(originals)==len(additions)==1
        a=ast.dump(originals[0],include_attributes=False);b=ast.dump(additions[0],include_attributes=False).replace("module='open_birth_chart_r10'","module='open_birth_chart'")
        assert a==b
        functions[name]=hashlib.sha256(a.encode()).hexdigest()
    oldio=module('old_r8_io',ROOT/'src/open_birth_chart/io.py');newio=module('new_r10_io',HERE/'r10_io.py')
    tests=[];synthetic_row=None
    with tempfile.TemporaryDirectory(prefix='obs_r10_gate_',dir='/tmp') as directory:
        p=Path(directory)
        for year in [1879,1880,2019,2020,2024,2025,2026]:
            birth={'study_id':'synthetic-gate-example','birth_local':f'{year}-06-01T12:00:00','birth_utc':f'{year}-06-01T12:00:00Z','latitude':0.,'longitude':0.,'source_offset_seconds':0,'sex':'M','calendar':'gregorian'}
            meta={**birth,'source':'SYNTHETIC-GATE','source_id':'synthetic-gate-example','birth_country':'ZZ','quality':'synthetic','geo_precision':'synthetic','stratum_id':'S','N_h':1,'n_h':1,'inclusion_probability':1.,'sample_weight':1.,'sampling_sha256':'synthetic'}
            for name,obj in [('birth_inputs.jsonl',birth),('birth_metadata.jsonl',meta)]:
                (p/name).write_text(json.dumps(obj)+'\n')
            manifest={'model_input_sha256':newio.sha256(p/'birth_inputs.jsonl'),'metadata_sha256':newio.sha256(p/'birth_metadata.jsonl'),'sample_n':1,'eligible_frame_N':1,'strata':[{'stratum_id':'S','n_h':1,'N_h':1}]}
            (p/'sampling_manifest.json').write_text(json.dumps(manifest))
            outcomes=[]
            for reader in [oldio,newio]:
                try:rows,_=reader.load_source(p);outcomes.append(True)
                except ValueError:outcomes.append(False)
            assert outcomes==[1880<=year<=2019,1880<=year<=2025]
            tests.append({'year':year,'R8_accepted':outcomes[0],'R10_accepted':outcomes[1]})
            if year==2024:synthetic_row=rows[0]
    engine_diffs=[]
    for filename in ['__init__.py','astronomy.py','bazi_engine.py','ziwei_engine.py','qizheng_engine.py','western_engine.py','ziwei_bridge.cjs']:
        original=(ROOT/'src/open_birth_chart'/filename).read_text();changed=(HERE/'open_birth_chart_r10'/filename).read_text()
        expected=original
        if filename in ['astronomy.py','bazi_engine.py']:
            expected=expected.replace('1880 <= civil.year <= 2019','1880 <= civil.year <= 2025').replace('1880–2019','1880–2025')
        elif filename=='ziwei_bridge.cjs':expected=expected.replace('y>2019','y>2025')
        assert expected==changed,filename
        engine_diffs.append({'file':filename,'only_declared_date_scope_changes':True})
    runner=module('r10_run_profiles_check',HERE/'run_profiles.py');runner.init_worker()
    profile=runner.score_record((synthetic_row,'base',0,None))
    assert profile['status']=='computed',profile.get('reason')
    assert len(profile['primary_scores'])==40
    oldrun=module('r8_run_profiles_check',ROOT/'scripts/run_profiles.py');oldrun.init_worker();legacy=[]
    for year in [1880,2006,2019]:
        row=dict(synthetic_row);row['birth_local']=f'{year}-06-01T12:00:00';row['birth_utc']=f'{year}-06-01T12:00:00Z'
        row['calendar_years']=list(range(year+20,year+60));row['chart_input_key']=newio.chart_key(row)
        before=oldrun.score_record((row,'base',0,None));after=runner.score_record((row,'base',0,None))
        assert before['status']==after['status']=='computed'
        assert before==after,year
        legacy.append({'synthetic_birth_year':year,'whole_profile_exact_match':True,'system_year_scores':160})
    oldrun.zw_engine.close();runner.zw_engine.close()
    return {'status':'passed','real_R10_targets_inspected':False,'date_gate_cases':tests,
        'loader_change':'Only maximum birth year2019→2025 in an additive copy; R8 unchanged',
        'runner_changes':'Only root locator, loader/engine-package routing, protocol/provenance metadata; scoring function identical',
        'unchanged_function_ast_sha256':functions,
        'engine_package_diff_checks':engine_diffs,'legacy_synthetic_equivalence':legacy,
        'synthetic_future_trajectory':{'birth_year':2024,'calendar_first':profile['calendar_years'][0],'calendar_last':profile['calendar_years'][-1],'systems':4,'age_points':40,'status':profile['status']},
        'R10_engine_package_sha256':{p.name:newio.sha256(p) for p in (HERE/'open_birth_chart_r10').glob('*') if p.is_file()}}


if __name__=='__main__':
    result=checks();(HERE/'scope_extension_checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
