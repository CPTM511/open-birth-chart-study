#!/usr/bin/env python3
"""Publish aggregate structural-signal results from completed, sealed runs.

This program accepts birth-only profiles. It neither reads nor estimates
death outcomes. Individual profiles are deliberately excluded from outputs.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import json
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from open_birth_chart.io import load_source, sha256, jsonlines
from open_birth_chart.analysis import (SYSTEMS, WINDOWS, percentiles,
    phase_reference, holm, descriptive_correlations, annual_summary, age_summary)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def checked_profiles(run_dir, mode, rows):
    path = run_dir / f'{mode}_profiles.jsonl'
    summary = json.loads((run_dir / f'{mode}_summary.json').read_text())
    seal = json.loads((run_dir / f'{mode}_run_seal.json').read_text())
    if sha256(path) != summary['result_sha256']:
        raise ValueError(f'{mode} profile hash mismatch')
    if seal['protocol_sha256'] != sha256(ROOT / 'protocol/study_protocol.json'):
        raise ValueError('Study protocol changed')
    # Statistical input-guard amendments do not modify the scoring modules.
    for name in ['astronomy.py', 'bazi_engine.py', 'ziwei_engine.py',
                 'qizheng_engine.py', 'western_engine.py', 'io.py']:
        rel = 'src/open_birth_chart/' + name
        if sha256(ROOT / rel) != seal['code_hashes'][rel]:
            raise ValueError('Scoring/input code changed: ' + rel)
    protocols = json.loads((ROOT / 'protocol/bazi_ziwei_implementation_seal.json').read_text())
    for item in protocols['files']:
        if item['path'].startswith('src/') and sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError('Frozen Bazi/Ziwei module changed: ' + item['path'])
    records = list(jsonlines(path))
    if len(records) != summary['tasks'] or len(records) != seal['tasks']:
        raise ValueError('Run is incomplete')
    if dict(Counter(r['status'] for r in records)) != summary['status_counts']:
        raise ValueError('Status counts mismatch')
    keyed = {}
    by_id = {r['study_id']: r for r in rows}
    for profile in records:
        key = (profile['study_id'], profile['variant'])
        if key in keyed:
            raise ValueError('Repeated profile/variant')
        keyed[key] = profile
        original = by_id[profile['study_id']]
        if profile['source'] != original['source'] or profile['chart_input_key'] != original['chart_input_key']:
            raise ValueError('Profile input key mismatch')
        if profile['calendar_years'] != original['calendar_years']:
            raise ValueError('Age/calendar trajectory mismatch')
        if profile['status'] == 'computed':
            a = np.asarray(profile['primary_scores'], dtype=float)
            if a.shape != (40, 4) or not np.isfinite(a).all() or np.any(a < 0) or np.any(a > 1):
                raise ValueError('Invalid complete score trajectory')
        elif profile['status'] != 'abstain':
            raise ValueError('Unknown result status')
    expected = set()
    if mode == 'baseline':
        expected = {(r['study_id'], 'base') for r in rows}
    else:
        for source in sorted({r['source'] for r in rows}):
            source_rows = [r for r in rows if r['source'] == source]
            order = lambda r: (r['sampling_sha256'], r['study_id'])
            for r in sorted(source_rows, key=order)[:200]:
                expected.update((r['study_id'], f'clock_{v:+}') for v in [-120, -30, 30, 120])
            for r in sorted([r for r in source_rows if r['geo_precision'] == 'municipality_reference'], key=order)[:100]:
                expected.update((r['study_id'], 'geo_' + v) for v in ['north', 'south', 'east', 'west'])
    if set(keyed) != expected:
        raise ValueError('Frozen task selection differs from completed output')
    return keyed, summary, seal


def distribution(scores, weights):
    pct = percentiles(scores)
    return {system: {
        'unweighted_min': float(scores[:, :, i].min()),
        'unweighted_max': float(scores[:, :, i].max()),
        'source_weighted_mean': float(np.average(scores[:, :, i].mean(axis=1), weights=weights)),
        'constant_profiles': int(np.count_nonzero(np.ptp(scores[:, :, i], axis=1) == 0)),
        'source_weighted_elevated_fraction': float(np.average((pct[:, :, i] >= .8).mean(axis=1), weights=weights)),
        'source_weighted_zero_fraction': float(np.average((scores[:, :, i] == 0).mean(axis=1), weights=weights)),
    } for i, system in enumerate(SYSTEMS)}


def sensitivity_summary(base, changed, canonical_source_by_id):
    output = []
    groups = sorted({(canonical_source_by_id[v['study_id']], v['variant']) for v in changed.values()})
    for source, variant in groups:
        records = [v for v in changed.values() if canonical_source_by_id[v['study_id']] == source and v['variant'] == variant]
        complete = [v for v in records if v['status'] == 'computed' and base[(v['study_id'], 'base')]['status'] == 'computed']
        item = {'source': source, 'variant': variant, 'planned_profiles': len(records),
                'paired_complete_profiles': len(complete),
                'weighting': 'unweighted fixed-hash stress subset, not a population estimate',
                'error_interval_claimed': False}
        if complete:
            a = np.asarray([base[(v['study_id'], 'base')]['primary_scores'] for v in complete])
            b = np.asarray([v['primary_scores'] for v in complete])
            pa, pb = percentiles(a), percentiles(b)
            fa, fb = pa >= .8, pb >= .8
            ja, jb = fa.sum(axis=2) >= 3, fb.sum(axis=2) >= 3
            item['systems'] = {s: {
                'mean_absolute_raw_change': float(np.abs(a[:, :, i] - b[:, :, i]).mean()),
                'maximum_absolute_raw_change': float(np.abs(a[:, :, i] - b[:, :, i]).max()),
                'fraction_profiles_with_any_raw_change_gt_1e_12': float(np.any(np.abs(a[:, :, i]-b[:, :, i]) > 1e-12, axis=1).mean()),
                'mean_absolute_within_person_percentile_change': float(np.abs(pa[:, :, i]-pb[:, :, i]).mean()),
                'elevated_flag_flip_fraction': float(np.mean(fa[:, :, i] != fb[:, :, i])),
            } for i, s in enumerate(SYSTEMS)}
            item.update(concordance_flag_flip_fraction=float(np.mean(ja != jb)),
                        profiles_with_any_concordance_flip=int(np.any(ja != jb, axis=1).sum()),
                        baseline_concordance_fraction=float(ja.mean()),
                        stress_concordance_fraction=float(jb.mean()),
                        paired_record_years=int(len(complete)*40))
        output.append(item)
    return {'description': 'Preselected one-at-a-time stress points; all baseline calendar years retained.',
            'no_significance_tests': True, 'groups': output}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--samples', nargs='+', required=True)
    p.add_argument('--run-dir', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    out = Path(args.output)
    if (out / 'structural_results.json').exists():
        raise FileExistsError('Do not replace an existing analysis release')
    out.mkdir(parents=True, exist_ok=True)
    rows, manifests, source_rows_by_id = [], [], {}
    for directory in args.samples:
        rs, manifest = load_source(directory)
        rows.extend(rs); manifests.append(manifest)
        if manifest['source'] in source_rows_by_id:
            raise ValueError('Repeated source frame')
        source_rows_by_id[manifest['source']] = rs
    if len({r['study_id'] for r in rows}) != len(rows):
        raise ValueError('Cross-source study-ID collision')
    frozen_cohorts = json.loads((ROOT / 'protocol/cohort_execution_seal.json').read_text())
    sealed_fields = ['source', 'sample_n', 'eligible_frame_N', 'model_input_sha256', 'metadata_sha256']
    if [tuple(m[k] for k in sealed_fields) for m in manifests] != [
        tuple(m[k] for k in sealed_fields) for m in frozen_cohorts['sources']]:
        raise ValueError('Require the three frozen source frames in their sealed order')
    protocol = json.loads((ROOT / 'protocol/study_protocol.json').read_text())
    run_dir = Path(args.run_dir)
    base, base_summary, base_seal = checked_profiles(run_dir, 'baseline', rows)
    stress, stress_summary, stress_seal = checked_profiles(run_dir, 'sensitivity', rows)
    started = datetime.now(timezone.utc).isoformat()
    write_json(out / 'analysis_execution_seal.json', {
        'started_utc': started, 'protocol_sha256': sha256(ROOT / 'protocol/study_protocol.json'),
        'analysis_code_sha256': sha256(ROOT / 'src/open_birth_chart/analysis.py'),
        'aggregation_code_sha256': sha256(Path(__file__)),
        'base_profile_sha256': base_summary['result_sha256'],
        'stress_profile_sha256': stress_summary['result_sha256'],
        'outcome_inputs': False, 'family_size': 6,
        'source_order': [m['source'] for m in manifests],
        'draws': protocol['primary_statistics']['draws'],
        'seed': protocol['primary_statistics']['seed'],
        'local_freeze_not_external_preregistration': True,
    })
    results = {'study': protocol['id'], 'analysis_started_utc': started,
        'question': 'Alignment of four versioned structural signal trajectories against an independent-phase reference.',
        'is_mortality_prediction_validation': False,
        'global_population_representative': False,
        'sampling_prose_deviation': '../protocol/sampling_implementation_deviation.json',
        'input_records': len(rows), 'country_labels_union': len({r['country'] for r in rows}),
        'records_are_not_confirmed_independent_people': True,
        'baseline_run': base_summary, 'sensitivity_run': stress_summary,
        'complete_record_years': sum(v['status']=='computed' for v in base.values())*40,
        'complete_system_year_scores': sum(v['status']=='computed' for v in base.values())*160,
        'outcome_fields_read': 0, 'sources': {}}
    flat_tests = []
    annual_rows = []
    for manifest in manifests:
        source = manifest['source']
        # Manifest IDs and source publisher labels are intentionally distinct.
        source_rows = source_rows_by_id[source]
        kept = [r for r in source_rows if base[(r['study_id'], 'base')]['status'] == 'computed']
        rejected = [r for r in source_rows if base[(r['study_id'], 'base')]['status'] != 'computed']
        scores = np.asarray([base[(r['study_id'], 'base')]['primary_scores'] for r in kept])
        weights = np.asarray([r['sample_weight'] for r in kept], dtype=float)
        entry = {'source_records': len(source_rows), 'eligible_source_frame': manifest['eligible_frame_N'],
                 'complete_four_system_profiles': len(kept), 'abstain_profiles': len(rejected),
                 'abstain_reasons': dict(Counter(base[(r['study_id'], 'base')].get('reason') for r in rejected)),
                 'included_source_frame_weight_sum': float(weights.sum()),
                 'input_sha256': manifest['model_input_sha256'],
                 'metadata_sha256': manifest['metadata_sha256'],
                 'country_counts': dict(sorted(Counter(r['country'] for r in source_rows).items())),
                 'sex_counts': dict(sorted(Counter(r['sex'] for r in source_rows).items())),
                 'birth_decade_counts': dict(sorted(Counter((int(r['birth_local'][:4])//10)*10 for r in source_rows).items())),
                 'quality_counts': dict(sorted(Counter(r['quality_tier'] for r in source_rows).items())),
                 'birth_year_range': [min(int(r['birth_local'][:4]) for r in source_rows), max(int(r['birth_local'][:4]) for r in source_rows)],
                 'tests': {}}
        if kept:
            entry['tests'] = phase_reference(scores, weights, [r['chart_input_key'] for r in kept],
                    draws=protocol['primary_statistics']['draws'], seed=protocol['primary_statistics']['seed'])
            entry['signal_distribution'] = distribution(scores, weights)
            entry['descriptive_pairwise_correlations'] = descriptive_correlations(scores)
            entry['annual_2026_2070'] = annual_summary(scores, [r['calendar_years'] for r in kept], weights)
            entry['age20_59'] = age_summary(scores, weights)
            entry['interpretive_clause_match_counts'] = {system: dict(Counter({})) for system in ['bazi','ziwei']}
            for system in ['bazi', 'ziwei']:
                c = Counter()
                for row in kept:
                    c.update(base[(row['study_id'],'base')][system+'_interpretive_rule_counts'])
                entry['interpretive_clause_match_counts'][system] = dict(sorted(c.items()))
            for annual in entry['annual_2026_2070']:
                annual_rows.append({'source': source, 'year': annual['year'], 'people': annual['people'],
                    'source_frame_weight_sum': annual.get('source_frame_weight_sum'),
                    'concordance': annual['concordance'],
                    **{s+'_mean_percentile': (annual['mean_within_person_percentiles'] or {}).get(s) for s in SYSTEMS}})
        for window in WINDOWS:
            entry['tests'].setdefault(window, None)
            flat_tests.append((source, window, None if entry['tests'][window] is None else entry['tests'][window]['p_raw_two_sided']))
        results['sources'][source] = entry
        print(json.dumps({'analyzed_source':source,'complete_profiles':len(kept)},ensure_ascii=False),flush=True)
    adjusted = holm([x[2] for x in flat_tests])
    table = []
    for (source, window, _), adj in zip(flat_tests, adjusted):
        test = results['sources'][source]['tests'][window]
        if test is not None:
            test['p_holm_six_tests'] = adj
            test['reject_independent_phase_reference_at_0_05'] = bool(adj < .05)
            table.append({'source':source,'age_window':window,**{k:test[k] for k in [
                'people','person_years','weighted_concordance','exact_independent_phase_mean',
                'difference_percentage_points','p_raw_two_sided','p_holm_six_tests']}})
    results['multiple_testing_family_size'] = len(flat_tests)
    results['analysis_completed_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(out / 'structural_results.json', results)
    canonical = {row['study_id']: source for source, source_rows in source_rows_by_id.items() for row in source_rows}
    write_json(out / 'sensitivity_results.json', sensitivity_summary(base, stress, canonical))
    for filename, records in [('primary_tests.csv',table),('annual_2026_2070.csv',annual_rows)]:
        with (out/filename).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    write_json(out / 'run_integrity.json', {
        'complete': True, 'baseline': base_summary, 'sensitivity': stress_summary,
        'baseline_input_records':len(rows), 'individual_profiles_published':False,
        'profile_ids_and_calendar_years_checked':True,
        'scoring_module_hashes_unchanged':True,
        'outcome_inputs':False,
    })
    print(json.dumps({'analysis_complete':True,'output':str(out),'tests':table},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
