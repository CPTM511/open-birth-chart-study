"""Check the public R9 release, frozen files, and aggregate execution claims.

This does not reconstruct private birth records or validate real-world outcomes.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
R9 = ROOT / 'rounds/r9'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline = read(R9 / 'verification/r8_baseline_manifest.json')
    assert baseline['file_count'] == len(baseline['files']) == 130
    for item in baseline['files']:
        assert digest(ROOT/item['path']) == item['sha256'], item['path']

    release = read(R9 / 'release_manifest.json')
    paths = [x['path'] for x in release['files']]
    assert len(set(paths)) == len(paths)
    for item in release['files']:
        path = ROOT/item['path']
        assert path.stat().st_size == item['bytes'], item['path']
        assert digest(path) == item['sha256'], item['path']
    for item in read(R9/'public_freeze_receipt.json')['files']:
        assert digest(ROOT/item['path']) == item['sha256'], item['path']
    for name, sha in read(R9/'methods/methods_implementation_seal.json')['files'].items():
        assert digest(R9/'methods'/name) == sha, name

    syntax_files = list(R9.rglob('*.py'))
    for path in syntax_files:
        ast.parse(path.read_text(), filename=str(path))
    assert read(R9/'methods/math_verification.json')['status'] == 'passed'
    calibration = read(R9/'methods/synthetic_calibration.json')
    assert calibration['real_R9_chart_results_inspected'] is False
    assert len(calibration['scenarios']) == 2
    for name, sha in calibration['code_sha256'].items():
        assert digest(R9/'methods'/name) == sha

    result = read(R9/'results/structural_comparison.json')
    assert result['primary_family_size'] == 3
    assert result['no_real_world_null_pvalues'] is True
    assert result['reference']['n_source_records'] == 2000
    assert {x['slot'] for x in result['targets']} == {'brazil2016', 'mexico2015'}
    for target in result['targets']:
        slot = target['slot']
        seal = read(R9/'execution'/f'{slot}_input_seal.json')
        completion = read(R9/'execution'/f'{slot}_completion.json')
        assert completion['input_records'] == completion['tasks'] == 2000
        assert completion['status_counts'] == {'computed': 2000}
        assert completion['outcome_inputs'] is False
        assert target['n_source_records'] == target['provenance']['complete_profiles'] == 2000
        assert target['provenance']['input_sha256'] == seal['input_manifest']['model_input_sha256']
        assert target['provenance']['profile_files'][0]['sha256'] == completion['result_sha256']
        assert abs(target['joint_rate'] - result['reference']['joint_rate'] - target['delta_joint_rate']) < 1e-13
        interval = target['sampling_interval']
        assert interval['family_size_including_unavailable_slots'] == 3
        assert interval['draws'] == 1999
        assert len(target['calendar_2026_2070']) == 45
        assert all((r['joint_rate'] is None) == (r['eligible_source_records'] == 0) for r in target['calendar_2026_2070'])
    print(json.dumps({'status':'passed', 'unchanged_R8_files':130,
        'R9_manifest_files':len(paths), 'Python_syntax_files':len(syntax_files),
        'new_complete_profiles':4000, 'scope':'Public file integrity and aggregate consistency; no private-input rerun or outcome validation'}))


if __name__ == '__main__':
    main()
