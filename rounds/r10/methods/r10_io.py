# SPDX-License-Identifier: AGPL-3.0-or-later
"""Birth-only interface and immutable source-frame sampling metadata."""
from __future__ import annotations
from datetime import datetime, date
from pathlib import Path
from collections import Counter
import hashlib
import json
import math


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def jsonlines(path):
    with Path(path).open() as f:
        for line in f:
            if line.strip():yield json.loads(line)


def age_years(birth_local):
    birthday=date.fromisoformat(birth_local[:10])
    first=birthday.year+20+int((birthday.month,birthday.day)>(7,1))
    return list(range(first,first+40))


def chart_key(row):
    fields={k:row[k] for k in ['birth_local','birth_utc','source_offset_seconds','latitude','longitude','sex']}
    return hashlib.sha256(json.dumps(fields,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def load_source(sample_directory):
    directory=Path(sample_directory)
    manifest=json.loads((directory/'sampling_manifest.json').read_text())
    if sha256(directory/'birth_inputs.jsonl')!=manifest['model_input_sha256']:
        raise ValueError('Birth input hash mismatch')
    if sha256(directory/'birth_metadata.jsonl')!=manifest['metadata_sha256']:
        raise ValueError('Sampling metadata hash mismatch')
    inputs=list(jsonlines(directory/'birth_inputs.jsonl'))
    metadata=list(jsonlines(directory/'birth_metadata.jsonl'))
    by_id={r['study_id']:r for r in metadata}
    if len(by_id)!=len(metadata) or len(set(r['study_id'] for r in inputs))!=len(inputs):
        raise ValueError('Duplicate study IDs')
    if set(by_id)!={r['study_id'] for r in inputs}:raise ValueError('ID coverage mismatch')
    rows=[]
    for birth in inputs:
        meta=by_id[birth['study_id']]
        for key in ['birth_local','birth_utc','latitude','longitude','source_offset_seconds']:
            if birth[key]!=meta[key]:raise ValueError('Birth and metadata mismatch: '+key)
        sex=birth.get('sex_resolved',birth.get('sex'))
        if sex not in ['M','F'] or sex!=meta['sex']:raise ValueError('Unresolved sex')
        if birth.get('calendar','').lower()!='gregorian':raise ValueError('Unresolved calendar')
        civil=datetime.fromisoformat(birth['birth_local'])
        absolute=datetime.fromisoformat(birth['birth_utc'].replace('Z','+00:00'))
        if civil.tzinfo is not None:raise ValueError('Civil label unexpectedly zoned')
        if abs((civil-absolute.replace(tzinfo=None)).total_seconds()-birth['source_offset_seconds'])>1:
            raise ValueError('Inconsistent absolute instant')
        if not 1880<=civil.year<=2025:raise ValueError('Outside registered cohort')
        if not -90<float(birth['latitude'])<90 or not -180<=float(birth['longitude'])<=180:
            raise ValueError('Invalid coordinates')
        w=float(meta['sample_weight'])
        if not math.isfinite(w) or w<=0 or abs(w-meta['N_h']/meta['n_h'])>1e-10:
            raise ValueError('Invalid conditional source-frame weight')
        row=dict(birth)
        row.update(sex=sex,utc_offset_seconds=birth['source_offset_seconds'],
                   timezone_offset_minutes=birth['source_offset_seconds']/60,
                   source=meta['source'],source_id=meta['source_id'],
                   country=meta['birth_country'],birth_country=meta['birth_country'],
                   quality_tier=meta['quality'],geo_precision=meta['geo_precision'],
                   source_row_id=meta.get('source_row_id'),stratum_id=meta['stratum_id'],
                   N_h=meta['N_h'],n_h=meta['n_h'],inclusion_probability=meta['inclusion_probability'],
                   sample_weight=w,sampling_sha256=meta['sampling_sha256'])
        row['calendar_years']=age_years(row['birth_local'])
        row['chart_input_key']=chart_key(row)
        rows.append(row)
    if len(rows)!=manifest['sample_n']:raise ValueError('Sample count mismatch')
    counts=Counter(r['stratum_id'] for r in rows)
    for s in manifest['strata']:
        if counts[s['stratum_id']]!=s['n_h']:raise ValueError('Stratum sample count mismatch')
    if abs(sum(r['sample_weight'] for r in rows)-manifest['eligible_frame_N'])>1e-6*manifest['eligible_frame_N']:
        raise ValueError('Weights fail eligible-frame total')
    return sorted(rows,key=lambda r:r['study_id']),manifest
