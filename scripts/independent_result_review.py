#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent aggregate replication using only the Python standard library.

No project analysis, I/O, model or aggregation implementation is imported.
Private birth/profile records are consumed locally; outputs contain aggregates.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from itertools import product
from pathlib import Path
import argparse
import hashlib
import json
import math

SYSTEMS = ('bazi', 'ziwei', 'qizheng', 'western')
WINDOWS = (('age20_59', 40), ('age20_49', 30))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def records(path):
    with Path(path).open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def midrank_flags(scores):
    """Compute mid-distribution values via frequency tables, without rankdata."""
    assert len(scores) == 40 and all(len(row) == 4 for row in scores)
    percentile = [[None] * 4 for _ in range(40)]
    for system in range(4):
        counts = Counter(float(row[system]) for row in scores)
        assert all(math.isfinite(x) and 0 <= x <= 1 for x in counts)
        lower = 0
        lookup = {}
        for value, count in sorted(counts.items()):
            lookup[value] = (lower + count / 2) / 40
            lower += count
        for age, row in enumerate(scores):
            percentile[age][system] = lookup[float(row[system])]
    flags = [[value >= .8 for value in row] for row in percentile]
    joint = [sum(row) >= 3 for row in flags]
    return percentile, flags, joint


def reference_probability(frequencies):
    """Sum the five Bernoulli states with 3 or 4 positives, not triple-minus-quad."""
    return math.fsum(
        math.prod(p if bit else 1 - p for p, bit in zip(frequencies, bits))
        for bits in product((False, True), repeat=4) if sum(bits) >= 3
    )


def expected_person(flags, length):
    probabilities = []
    for beginning in range(0, length, 10):
        frequencies = [sum(flags[age][s] for age in range(beginning, beginning+10))/10 for s in range(4)]
        probabilities.append(reference_probability(frequencies))
    return math.fsum(probabilities) / len(probabilities)


def load_samples(directories):
    sources, metadata, inputs = {}, {}, {}
    for directory in directories:
        directory = Path(directory)
        manifest = json.loads((directory/'sampling_manifest.json').read_text())
        source = manifest['source']
        assert source not in sources
        assert digest(directory/'birth_inputs.jsonl') == manifest['model_input_sha256']
        assert digest(directory/'birth_metadata.jsonl') == manifest['metadata_sha256']
        source_metadata = list(records(directory/'birth_metadata.jsonl'))
        source_inputs = list(records(directory/'birth_inputs.jsonl'))
        assert len(source_metadata) == len(source_inputs) == manifest['sample_n']
        assert {r['study_id'] for r in source_metadata} == {r['study_id'] for r in source_inputs}
        ids = []
        for r in source_metadata:
            key = r['study_id']
            assert key not in metadata
            r = dict(r, canonical_source=source)
            assert math.isclose(float(r['sample_weight']), r['N_h']/r['n_h'], rel_tol=0, abs_tol=1e-10)
            metadata[key] = r
            ids.append(key)
        for r in source_inputs:
            key = r['study_id']
            assert key not in inputs
            inputs[key] = r
        sources[source] = {'manifest': manifest, 'ids': ids}
    return sources, metadata, inputs


def read_profiles(path, metadata, inputs):
    output = {}
    for raw in records(path):
        key = raw['study_id'], raw['variant']
        assert key not in output, 'Repeated private profile key'
        meta, birth = metadata[key[0]], inputs[key[0]]
        assert raw['source'] == meta['source'], 'Publisher label mismatch'
        fields = {k: birth[k] for k in ('birth_local', 'birth_utc', 'source_offset_seconds', 'latitude', 'longitude')}
        fields['sex'] = birth.get('sex_resolved', birth.get('sex'))
        chart_key = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        assert raw['chart_input_key'] == chart_key, 'Chart-input key mismatch'
        birthday = date.fromisoformat(birth['birth_local'][:10])
        years = [y for y in range(birthday.year+19, birthday.year+62)
                 if 20 <= y-birthday.year-int((7,1)<(birthday.month,birthday.day)) < 60]
        assert raw['calendar_years'] == years and len(years) == 40, 'Age-calendar mismatch'
        compact = {'source': meta['canonical_source'], 'variant': key[1], 'status': raw['status'],
                   'chart_input_key': chart_key, 'scores': raw.get('primary_scores')}
        if raw['status'] == 'computed':
            compact['percentiles'], compact['flags'], compact['joint'] = midrank_flags(compact['scores'])
        else:
            assert raw['status'] == 'abstain'
        output[key] = compact
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--samples', nargs='+', required=True)
    p.add_argument('--run-dir', required=True)
    p.add_argument('--results', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    result_dir, run_dir = Path(args.results), Path(args.run_dir)
    for name in ('structural_results.json', 'sensitivity_results.json'):
        if not (result_dir/name).is_file():
            raise FileNotFoundError('Both published aggregate files must exist before actual-effect review')
    structural = json.loads((result_dir/'structural_results.json').read_text())
    sensitivity = json.loads((result_dir/'sensitivity_results.json').read_text())
    sources, meta, inputs = load_samples(args.samples)
    base = read_profiles(run_dir/'baseline_profiles.jsonl', meta, inputs)
    stress = read_profiles(run_dir/'sensitivity_profiles.jsonl', meta, inputs)
    assert set(base) == {(key, 'base') for key in meta}
    expected_stress = set()
    for source, spec in sources.items():
        ordered = sorted(spec['ids'], key=lambda key: (meta[key]['sampling_sha256'], key))
        for key in ordered[:200]:
            expected_stress.update((key, f'clock_{shift:+}') for shift in (-120,-30,30,120))
        geo = [key for key in ordered if meta[key]['geo_precision'] == 'municipality_reference'][:100]
        for key in geo:
            expected_stress.update((key, 'geo_'+direction) for direction in ('north','south','east','west'))
    assert set(stress) == expected_stress, 'Sensitivity task-selection mismatch'
    differences = defaultdict(list)
    mismatches = []

    def compare(label, actual, published, category='numeric'):
        if actual is None or published is None:
            okay = actual is published
            difference = 0 if okay else None
        else:
            difference = abs(float(actual)-float(published))
            tolerance = 1e-12
            if category == 'weight_sum':
                tolerance = max(tolerance, 32*math.ulp(max(abs(float(actual)), abs(float(published)))))
            okay = difference <= tolerance
        if difference is not None:
            differences[category].append(difference)
        if not okay:
            mismatches.append({'aggregate': label, 'recomputed': actual, 'published': published})

    complete = sum(r['status']=='computed' for r in base.values())
    compare('input_records', len(meta), structural['input_records'], 'counts')
    compare('complete_record_years', complete*40, structural['complete_record_years'], 'counts')
    compare('complete_system_year_scores', complete*160, structural['complete_system_year_scores'], 'counts')
    compare('country_labels_union', len({r['birth_country'] for r in meta.values()}), structural['country_labels_union'], 'counts')
    for mode, profiles in [('baseline',base),('sensitivity',stress)]:
        assert digest(run_dir/f'{mode}_profiles.jsonl') == structural[f'{mode}_run']['result_sha256']
        assert dict(Counter(r['status'] for r in profiles.values())) == structural[f'{mode}_run']['status_counts']
        compare(mode+'_tasks', len(profiles), structural[f'{mode}_run']['tasks'], 'counts')

    primary_checks, raw_pvalues, slots = [], [], []
    for source, spec in sources.items():
        published = structural['sources'][source]
        kept = [key for key in spec['ids'] if base[(key,'base')]['status']=='computed']
        weights = {key: float(meta[key]['sample_weight']) for key in kept}
        weight_total = math.fsum(weights.values())
        compare(source+'/source_records',len(spec['ids']),published['source_records'],'counts')
        compare(source+'/complete_profiles',len(kept),published['complete_four_system_profiles'],'counts')
        compare(source+'/abstain_profiles',len(spec['ids'])-len(kept),published['abstain_profiles'],'counts')
        compare(source+'/weight_sum',weight_total,published['included_source_frame_weight_sum'],'weight_sum')
        compare(source+'/frame_N',spec['manifest']['eligible_frame_N'],published['eligible_source_frame'],'counts')
        duplicate_flags = {}
        for key in kept:
            r = base[(key,'base')]
            if r['chart_input_key'] in duplicate_flags:
                assert duplicate_flags[r['chart_input_key']] == r['flags'], 'Same input, different flags'
            duplicate_flags[r['chart_input_key']] = r['flags']
        for window, length in WINDOWS:
            test = published['tests'][window]
            slots.append((source,window))
            raw_pvalues.append(None if test is None else test['p_raw_two_sided'])
            if not kept:
                assert test is None
                continue
            observed = math.fsum(weights[key]*sum(base[(key,'base')]['joint'][:length])/length for key in kept)/weight_total
            expected = math.fsum(weights[key]*expected_person(base[(key,'base')]['flags'],length) for key in kept)/weight_total
            compare(source+'/'+window+'/observed',observed,test['weighted_concordance'],'observed_rate')
            compare(source+'/'+window+'/exact_mean',expected,test['exact_independent_phase_mean'],'exact_mean')
            compare(source+'/'+window+'/difference_pp',100*(observed-expected),test['difference_percentage_points'],'difference_pp')
            compare(source+'/'+window+'/people',len(kept),test['people'],'counts')
            compare(source+'/'+window+'/person_years',len(kept)*length,test['person_years'],'counts')
            compare(source+'/'+window+'/input_blocks',len(duplicate_flags),test['unique_chart_input_blocks'],'counts')
            rawp = test['p_raw_two_sided']
            assert 0 < rawp <= 1 and abs(rawp*(test['draws']+1)-round(rawp*(test['draws']+1))) < 1e-10
            primary_checks.append({'source':source,'window':window,'complete_records':len(kept),
                'observed_recomputed':observed,'observed_published':test['weighted_concordance'],
                'exact_mean_recomputed':expected,'exact_mean_published':test['exact_independent_phase_mean'],
                'p_raw_used_for_holm_only':rawp})

    assert len(slots) == structural['multiple_testing_family_size'] == 6
    working = [1 if value is None else value for value in raw_pvalues]
    ordered = sorted(range(6), key=lambda i: (working[i],i))
    adjusted = [None]*6
    for position,index in enumerate(ordered):
        if raw_pvalues[index] is not None:
            adjusted[index] = min(1, max((6-k)*working[ordered[k]] for k in range(position+1)))
    for index,(source,window) in enumerate(slots):
        test = structural['sources'][source]['tests'][window]
        if test is not None:
            compare(source+'/'+window+'/holm',adjusted[index],test['p_holm_six_tests'],'holm')
            assert test['reject_independent_phase_reference_at_0_05'] == (adjusted[index] < .05)

    groups = defaultdict(list)
    for key,r in stress.items():
        groups[(r['source'],r['variant'])].append(key)
    reported = {(g['source'],g['variant']):g for g in sensitivity['groups']}
    assert set(groups) == set(reported)
    stress_checks = []
    for (source,variant),keys in sorted(groups.items()):
        published = reported[(source,variant)]
        pairs = [key for key in keys if stress[key]['status']=='computed' and base[(key[0],'base')]['status']=='computed']
        label = source+'/'+variant
        compare(label+'/planned',len(keys),published['planned_profiles'],'counts')
        compare(label+'/paired',len(pairs),published['paired_complete_profiles'],'counts')
        if not pairs:
            continue
        n_years = len(pairs)*40
        per_system = {}
        for system,name in enumerate(SYSTEMS):
            raw_diffs,percentile_diffs = [],[]
            flag_flips,changed_profiles = 0,0
            for key in pairs:
                a,b = base[(key[0],'base')],stress[key]
                this_raw = [abs(a['scores'][age][system]-b['scores'][age][system]) for age in range(40)]
                raw_diffs.extend(this_raw)
                changed_profiles += any(d>1e-12 for d in this_raw)
                percentile_diffs.extend(abs(a['percentiles'][age][system]-b['percentiles'][age][system]) for age in range(40))
                flag_flips += sum(a['flags'][age][system]!=b['flags'][age][system] for age in range(40))
            values = {'mean_absolute_raw_change':math.fsum(raw_diffs)/n_years,
                'maximum_absolute_raw_change':max(raw_diffs),
                'fraction_profiles_with_any_raw_change_gt_1e_12':changed_profiles/len(pairs),
                'mean_absolute_within_person_percentile_change':math.fsum(percentile_diffs)/n_years,
                'elevated_flag_flip_fraction':flag_flips/n_years}
            for metric,value in values.items():
                compare(label+'/'+name+'/'+metric,value,published['systems'][name][metric],'sensitivity')
            per_system[name] = values
        joint_flips,any_joint,baseline_true,changed_true = 0,0,0,0
        for key in pairs:
            a,b = base[(key[0],'base')],stress[key]
            differing = sum(x!=y for x,y in zip(a['joint'],b['joint']))
            joint_flips += differing
            any_joint += differing>0
            baseline_true += sum(a['joint'])
            changed_true += sum(b['joint'])
        values = {'concordance_flag_flip_fraction':joint_flips/n_years,
            'profiles_with_any_concordance_flip':any_joint,
            'baseline_concordance_fraction':baseline_true/n_years,
            'stress_concordance_fraction':changed_true/n_years,'paired_record_years':n_years}
        for metric,value in values.items():
            compare(label+'/'+metric,value,published[metric],'sensitivity')
        stress_checks.append({'source':source,'variant':variant,'paired_profiles':len(pairs),
                             'systems_recomputed':per_system,**values})

    root = Path(__file__).resolve().parents[1]
    report = {'completed_utc':datetime.now(timezone.utc).isoformat(),
        'verdict':'pass' if not mismatches else 'fail',
        'review_scope':'Independent recomputation of actual birth-only aggregate results; no project analysis/I/O/model/aggregation imports.',
        'review_script':'scripts/independent_result_review.py','review_script_sha256':digest(__file__),
        'aggregator_sha256_reviewed':digest(root/'scripts/analyze_profiles.py'),
        'structural_results_sha256':digest(result_dir/'structural_results.json'),
        'sensitivity_results_sha256':digest(result_dir/'sensitivity_results.json'),
        'tolerance_absolute':1e-12,'large_weight_sum_tolerance':'max(1e-12, 32 ULP of the weight total)',
        'comparison_counts':{k:len(v) for k,v in differences.items()},
        'maximum_absolute_differences':{k:max(v,default=0) for k,v in differences.items()},
        'baseline_records':len(base),'baseline_complete':complete,'stress_records':len(stress),
        'primary_tests_checked':len(primary_checks),'sensitivity_groups_checked':len(stress_checks),
        'primary_checks':primary_checks,'sensitivity_checks':stress_checks,
        'mismatches':mismatches,
        'static_review_corrections':[
            'Canonical manifest source IDs are grouped via the directory-to-row mapping, separately from publisher labels; sensitivity uses study_id-to-canonical-source mapping.',
            'Frozen manifest comparison includes metadata_sha256 and eligible_frame_N; all current metadata hashes also independently matched the earlier cohort seal.'
        ],
        'limits':['Raw Monte Carlo tail counts were not rerun; their reported values were used only to recompute six-slot Holm and validate the plus-one grid.',
                  'No mortality outcomes read, no forecast-validity inference, no independent-humanity sample claim.',
                  'No individual identifiers or personal score trajectories are included in this report.']}
    out = Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    (out/'result_numerical_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines = ['# Independent numerical result review','',f"**Verdict: {report['verdict'].upper()}.**",'',
        'A separate standard-library implementation recomputed aggregate results from the private birth-only profiles and source metadata. It imports none of the project analysis, I/O, scoring or aggregation implementations. Personal records stay private.','',
        f"Checked {len(primary_checks)} source-by-window tests and {len(stress_checks)} sensitivity groups; baseline {len(base)} records, {complete} complete, sensitivity {len(stress)} records.",'',
        '| Quantity | Maximum absolute difference | Comparisons |','|---|---:|---:|']
    lines.extend(f'| {k} | {max(v,default=0):.3g} | {len(v)} |' for k,v in differences.items())
    lines += ['', 'Midranks were recomputed from frequency tables. Exact reference means were recomputed by summing the five independent Bernoulli states with at least three positive systems, then averaging age bands and source-frame weights. This is separate from the production triple-product formula.', '',
        'All complete counts, person-year counts, same-input group counts, source weights, observed concurrence rates, exact means, percentage-point differences and six-slot Holm values were checked. Every sensitivity group was checked for raw/percentile changes, elevated-flag changes, concurrence flips and paired counts.', '',
        'The production script corrected canonical source grouping and added frozen metadata/frame-size verification before producing results. No model definition or statistical hypothesis changed.', '',
        'The 1,999-draw Monte Carlo tail counts were not rerun. This review verifies deterministic aggregates and Holm arithmetic, not mortality prediction or independent evidential status of the four systems.', '',
        f"Review code: `scripts/independent_result_review.py`, SHA256 `{report['review_script_sha256']}`.",
        'The JSON companion records result hashes, aggregate comparisons and exact limitations.']
    (out/'result_numerical_review.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:report[k] for k in ('verdict','baseline_records','baseline_complete','stress_records','primary_tests_checked','sensitivity_groups_checked','maximum_absolute_differences','mismatches')},ensure_ascii=False))
    if mismatches:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
