"""R10 registered-slot adapter: same fixed-reference score rules; 2020s scope.

No real-world mortality or AI-event outcome enters this structural calculation.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
import argparse, hashlib, json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'rounds/r9/methods'))
from fixed_reference import conditional_frame_interval
from analyze_new_cohorts import r8_relative_continuity
from r10_io import load_source, jsonlines, sha256
from reference_sensitivity import run_sensitivity, RecordDesign
from precision_reference import PrecisionReference

REFERENCE_INPUT_SHA256='3d9a2dc48a26a083a20abbd372310310d13b6e93d880a4f8d1fafa02f8914f6d'
REFERENCE_PROFILE_SHA256='5bdc0d2e5c53cb15928a4a0781e5c7785085d3d039cfbf7dcc9b44f2a3f1c401'
FAMILY_SIZE=7
PRIMARY_DRAWS=9999
SAMPLE_SEED='OBS-R10-2026-11-27'

def load_profiles(sample_directory, profile_files):
    rows, manifest = load_source(sample_directory)
    by_id = {row["study_id"]:row for row in rows}
    profiles = {}
    seen_selected = 0
    for file in profile_files:
        for profile in jsonlines(file):
            if profile.get("variant") != "base" or profile.get("study_id") not in by_id:
                continue
            key = profile["study_id"]
            seen_selected += 1
            if key in profiles:
                raise ValueError("Duplicate base profile for a sampled study record")
            if profile.get("status") != "computed":
                raise ValueError("Sample contains uncomputed profiles; handle exclusions explicitly before analysis")
            expected = by_id[key]
            for field in ["source", "chart_input_key", "calendar_years"]:
                if profile.get(field) != expected[field]:
                    raise ValueError("Profile-input mismatch in " + field)
            profiles[key] = profile
    if set(profiles) != set(by_id):
        raise ValueError(f"Incomplete selected-profile coverage: {len(profiles)} of {len(by_id)}")
    scores = np.asarray([profiles[row["study_id"]]["primary_scores"] for row in rows], dtype=float)
    if scores.shape != (len(rows),40,4) or not np.isfinite(scores).all():
        raise ValueError("Selected profiles must be complete finite (n,40,4) arrays")
    weights = np.asarray([row["sample_weight"] for row in rows], float)
    strata = np.asarray([row["stratum_id"] for row in rows], str)
    frame_counts = {s["stratum_id"]:s["N_h"] for s in manifest["strata"]}
    observed_counts = Counter(strata)
    for row in rows:
        if observed_counts[row["stratum_id"]] != row["n_h"]:
            raise ValueError("Actual sampled stratum size differs from declared n_h")
    provenance = {
        "input_sha256":manifest["model_input_sha256"],
        "metadata_sha256":manifest["metadata_sha256"],
        "sampling_manifest_sha256":sha256(Path(sample_directory)/"sampling_manifest.json"),
        "profile_files":[{"name":Path(p).name,"sha256":sha256(p)} for p in profile_files],
        "source_labels":sorted(set(row["source"] for row in rows)),
        "sample_n":len(rows),"eligible_frame_N":manifest["eligible_frame_N"],
        "complete_profiles":seen_selected,
    }
    return rows, manifest, scores, weights, strata, frame_counts, provenance


def describe(rows, flags, weights):
    joint=np.sum(flags,axis=2)>=3
    calendar=np.asarray([r['calendar_years'] for r in rows],int)
    mask=(calendar>=2026)&(calendar<=2070)
    birth_years=sorted(set(int(r['birth_local'][:4]) for r in rows))
    view=[]
    for year in range(2026,2071):
        who,age=np.nonzero(calendar==year);count=len(who)
        view.append({'year':year,'eligible_source_records':count,'joint_rate':None if not count else float(np.average(joint[who,age],weights=weights[who])),
            'descriptive_only':True,'peak_listing_eligible':count>=30})
    return {'birth_years':birth_years,
        'age20_39_joint_rate_descriptive':float(np.average(joint[:,:20].mean(axis=1),weights=weights)),
        'age20_39_calendar_range':[int(calendar[:,:20].min()),int(calendar[:,:20].max())],
        'primary_calendar_range':[int(calendar.min()),int(calendar.max())],
        'modeled_record_years_total':int(calendar.size),
        'modeled_record_years_within_2026_2070':int(mask.sum()),
        'calendar_2026_2070':view}


def analyze(config):
    protocol_path=Path(config['protocol'])
    protocol=json.loads(protocol_path.read_text())
    slots=protocol['source_slots']
    if len(slots)!=FAMILY_SIZE or len(set(s['id'] for s in slots))!=FAMILY_SIZE:
        raise ValueError('R10 must retain exactly seven unique comparison slots')
    registry={s['id']:s for s in slots}
    order={s['id']:i for i,s in enumerate(slots)}
    if protocol['inference']['family_size']!=FAMILY_SIZE or protocol['inference']['primary_draws']!=PRIMARY_DRAWS:
        raise ValueError('Primary draw count or family differs from frozen R10 implementation')
    decision_path=Path(config['source_decisions'])
    decisions=json.loads(decision_path.read_text())['source_slots']
    if len(decisions)!=FAMILY_SIZE or {s['id'] for s in decisions}!=set(registry):
        raise ValueError('Final birth-field availability decisions must cover all seven registered slots')
    decision_by_id={s['id']:s for s in decisions}
    if any(s.get('status') not in ['available','unavailable'] for s in decisions):
        raise ValueError('Final availability decisions must precede target analysis')
    if any(s['status']=='unavailable' and not s.get('reason') for s in decisions):
        raise ValueError('Every unavailable slot requires an explicit reason')
    registered={s['id'] for s in decisions if s['status']=='available'}
    for slot in registered:
        if str(registry[slot].get('status','')).startswith('unavailable'):
            raise ValueError('Cannot reopen a slot declared unavailable at protocol freeze')
    targets={s['slot']:s for s in config['targets']}
    if len(targets)!=len(config['targets']) or set(targets)-set(registry):
        raise ValueError('Duplicate or unregistered target slot')
    if set(targets)!=registered:
        raise ValueError('Final analysis must include every and only available registered slot')
    reference=config['reference']
    rr,rm,rs,rw,rstr,rcounts,rprov=load_profiles(reference['sample_dir'],reference['profile_files'])
    if rm['model_input_sha256']!=REFERENCE_INPUT_SHA256 or len(rr)!=2000:
        raise ValueError('Reference is not frozen R8 Brazil2006')
    if len(reference['profile_files'])!=1 or sha256(reference['profile_files'][0])!=REFERENCE_PROFILE_SHA256:
        raise ValueError('Frozen reference profile-file hash differs')
    if set(r['source'] for r in rr)!={'SINASC-2006'}:
        raise ValueError('Wrong reference source')
    ref=PrecisionReference(rs,rw,[Fraction(r['N_h'],r['n_h']) for r in rr])
    reference_summary=ref.summarize(rs,rw)
    reference_summary.update({'provenance':rprov,'relative_alignment':r8_relative_continuity(rs,rw),
        **describe(rr,ref.flags(rs),rw)})
    out={'created_utc':datetime.now(timezone.utc).isoformat(),
        'analysis':'R10 registered country-by-birth-year structural comparisons',
        'protocol_sha256':sha256(protocol_path),'source_decisions_sha256':sha256(decision_path),'reference':reference_summary,
        'primary_family_size':FAMILY_SIZE,'primary_draws':PRIMARY_DRAWS,
        'primary_age_window':'Complete ages20–59; calendar2026–2070 and ages20–39 are descriptive only',
        'all_available_registered_slots_estimated':True,'no_real_world_null_pvalues':True,
        'unavailable_slots':[{'slot':s['id'],'reason':s['reason']} for s in decisions if s['status']=='unavailable'],
        'targets':[],'interpretation':'Structural source-frame contrasts; no decade-wide, global, mortality or AI-risk inference.'}
    sensitivity_inputs={};sensitivity_unavailable=[]
    for slot in sorted(targets,key=order.get):
        spec=targets[slot];rule=registry[slot]
        rows,manifest,scores,weights,strata,counts,prov=load_profiles(spec['sample_dir'],spec['profile_files'])
        years=set(int(r['birth_local'][:4]) for r in rows)
        if len(years)!=1 or not years.issubset(set(rule['allowed_birth_years'])):
            raise ValueError('Target must contain one registered actual birth year, not registration years')
        if not rule.get('expected_country') or set(r['birth_country'] for r in rows)!={rule['expected_country']}:
            raise ValueError('Country differs from registered slot')
        expected_source=rule.get('source_label',rule.get('expected_source',decision_by_id[slot].get('source_label')))
        if expected_source and set(r['source'] for r in rows)!={expected_source}:
            raise ValueError('Source label differs from frozen slot')
        if len(rows)!=min(2000,manifest['eligible_frame_N']) or manifest['seed']!=SAMPLE_SEED:
            raise ValueError('Prespecified sample size or selection seed differs')
        result=ref.summarize(scores,weights);flags=ref.flags(scores)
        interval=conditional_frame_interval((flags.sum(axis=2)>=3).mean(axis=1),strata,counts,
            seed=rule['primary_bootstrap_seed'],draws=PRIMARY_DRAWS,family_size=FAMILY_SIZE)
        if abs(interval['point']-result['joint_rate'])>2e-13:
            raise ArithmeticError('Stratum and direct source-weight means differ')
        if interval['status']!='unavailable':
            interval['delta_joint_interval95']=[v-ref.joint_rate for v in interval['interval95']]
            interval['delta_joint_family_adjusted_interval']=[v-ref.joint_rate for v in interval['family_adjusted_interval']]
        result.update({'slot':slot,'provenance':prov,'sampling_interval':interval,
            'relative_alignment':r8_relative_continuity(scores,weights),**describe(rows,flags,weights)})
        out['targets'].append(result)
        try:
            RecordDesign.from_frame(weights,strata,counts)
        except ValueError as exc:
            sensitivity_unavailable.append({'slot':slot,'reason':str(exc)})
        else:
            sensitivity_inputs[slot]={'scores':scores,'weights':weights,'strata':strata,'frame_counts':counts}
    benchmark=json.loads((HERE/'refit_benchmark.json').read_text())
    if benchmark['real_R10_targets_inspected'] is not False or benchmark['selected_refit_draws'] not in [199,999]:
        raise ValueError('Pre-target refit budget decision missing')
    for name,digest in benchmark['code_sha256'].items():
        if sha256(HERE/name)!=digest:raise ValueError('Benchmarked code changed: '+name)
    refit_spec=protocol['reference_stability_sensitivity']
    if refit_spec['draws']!=benchmark['selected_refit_draws']:
        raise ValueError('Refit draw count differs from pre-target benchmark decision')
    if sensitivity_inputs:
        sensitivity=run_sensitivity({'scores':rs,'weights':rw,'strata':rstr,'frame_counts':rcounts},sensitivity_inputs,
            draws=benchmark['selected_refit_draws'],reference_seed=refit_spec['seed'],
            target_seeds={slot:refit_spec['seed']+1+order[slot] for slot in sensitivity_inputs})
    else:
        sensitivity={'status':'unavailable','reason':'No eligible target for reference sensitivity'}
    primary_points={t['slot']:t['delta_joint_rate'] for t in out['targets']}
    for result in sensitivity.get('targets',[]):
        if abs(result['point_delta_joint_rate']-primary_points[result['slot']])>2e-13:
            raise ArithmeticError('Reference sensitivity baseline differs from the primary design-weight contrast')
    sensitivity['unavailable_targets']=sensitivity_unavailable
    out['reference_refit_sensitivity']=sensitivity
    out['primary_threshold_precision']={'comparison':'Exact rational design-weight >=4/5 oracle within2e-10 of the threshold; no widened threshold','diagnostics':ref.diagnostics}
    out['code_sha256']={str(p.relative_to(ROOT)):sha256(p) for p in [Path(__file__),HERE/'r10_io.py',HERE/'reference_sensitivity.py',HERE/'threshold_precision.py',HERE/'precision_reference.py',ROOT/'rounds/r9/methods/fixed_reference.py',ROOT/'rounds/r9/methods/analyze_new_cohorts.py']}
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    output=Path(a.output)
    if output.exists():raise FileExistsError('Preserve prior R10 result; choose another output path')
    result=analyze(json.loads(Path(a.config).read_text()));result['analysis_config_sha256']=sha256(a.config)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(output),'target_samples':[{k:t[k] for k in ['slot','n_source_records']} for t in result['targets']],
        'unavailable_slots':result['unavailable_slots'],'reference_refit_draws':result['reference_refit_sensitivity'].get('draws')}))


if __name__=='__main__':main()
