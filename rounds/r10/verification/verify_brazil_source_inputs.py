"""Independent R10 Brazil selected-input verification; no chart/profile imports.

Uses positional standard-library CSV decoding and explicit source date/clock
parsing, rather than the sample builder or the R8/R9 eligibility/birth parsers.
Recompiles official IANA southamerica rules for a separate historical offset path.
Public output contains aggregate checks/hashes only, never individual identifiers.
"""
import argparse, collections, concurrent.futures, csv, datetime as dt, hashlib
import io, json, re, subprocess, tarfile, zipfile
from pathlib import Path
from zoneinfo import ZoneInfo


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def numeric_token(value):
    value=value.strip()
    if re.fullmatch(r'[0-9]+\.0',value):value=value[:-2]
    if not value.isdigit():raise ValueError('Selected numeric birth field is missing or malformed')
    return value


def birth_datetime(date_text,time_text):
    date_text=date_text.strip()
    if re.fullmatch(r'[0-9]{8}',date_text):
        day,month,year=int(date_text[:2]),int(date_text[2:4]),int(date_text[4:])
    elif re.fullmatch(r'[0-9]{2}/[0-9]{2}/[0-9]{4}',date_text):
        day,month,year=map(int,date_text.split('/'))
    elif re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',date_text):
        year,month,day=map(int,date_text.split('-'))
    else:raise ValueError('Unrecognized selected source birth-date format')
    token=numeric_token(time_text)
    if len(token)>4:raise ValueError('Invalid source HHMM width')
    token=token.zfill(4);hour,minute=int(token[:2]),int(token[2:])
    return dt.datetime(year,month,day,hour,minute)


def verify_year(args):
    year,raw_dir,sample_root,reference_path,tzif_dir=args
    directory=Path(sample_root)/f'brazil{year}'
    manifest=json.loads((directory/'sampling_manifest.json').read_text())
    assert manifest['sample_n']==2000
    assert sha(directory/'birth_inputs.jsonl')==manifest['model_input_sha256']
    assert sha(directory/'birth_metadata.jsonl')==manifest['metadata_sha256']
    assert sha(reference_path)==manifest['reference_sha256']
    records=[json.loads(line) for line in (directory/'birth_metadata.jsonl').read_text().splitlines() if line]
    models=[json.loads(line) for line in (directory/'birth_inputs.jsonl').read_text().splitlines() if line]
    by_id={r['study_id']:r for r in models};wanted={int(r['source_row_id']):r for r in records}
    assert len(records)==len(models)==len(by_id)==len(wanted)==2000
    references=json.loads(Path(reference_path).read_text());zones={};checked=0
    by_zone=collections.Counter();minute_counts=collections.Counter();coordinates=set();source_date_formats=collections.Counter()
    archive=Path(raw_dir)/f'brazil{year}.zip';assert sha(archive)==manifest['archive_sha256']
    receipt=json.loads((Path(raw_dir)/f'brazil{year}.download.json').read_text())
    assert receipt['sha256']==manifest['archive_sha256'] and receipt['bytes']==archive.stat().st_size
    last=max(wanted);strata=collections.Counter()
    with zipfile.ZipFile(archive) as z:
        members=[n for n in z.namelist() if n.lower().endswith('.csv')]
        assert len(members)==1
        with io.TextIOWrapper(z.open(members[0]),encoding='latin1',newline='') as stream:
            reader=csv.reader(stream,delimiter=';',quotechar='"',strict=True)
            columns=[c.strip().lstrip('\ufeff') for c in next(reader)]
            # Only these four birth-field columns are projected or interpreted.
            names=['DTNASC','HORANASC','SEXO','CODMUNNASC']
            indices={name:columns.index(name) for name in names}
            for ordinal,values in enumerate(reader,1):
                if ordinal not in wanted:
                    if ordinal>=last:break
                    continue
                raw={name:values[index] for name,index in indices.items()};meta=wanted[ordinal]
                civil=birth_datetime(raw['DTNASC'],raw['HORANASC'])
                sex_value=numeric_token(raw['SEXO']);assert sex_value in ['1','2']
                sex={'1':'M','2':'F'}[sex_value];municipality=numeric_token(raw['CODMUNNASC']).zfill(6)
                assert len(municipality)==6 and municipality in references
                assert civil.year==year and civil.isoformat()==meta['birth_local']
                assert sex==meta['sex']==meta['sex_resolved']
                assert municipality==str(meta['municipality_code'])
                assert meta['source_id']==f'SINASC{year}:row:{ordinal:07d}'
                assert meta['source']==f'SINASC-{year}' and meta['birth_country']=='BR' and meta['calendar']=='gregorian'
                expected_rank=hashlib.sha256((manifest['seed']+'|'+meta['source_id']).encode()).hexdigest()
                assert expected_rank==meta['sampling_sha256']
                ref=references[municipality]
                for key in ['latitude','longitude','municipality_code','municipality_ibge7','municipality_name',
                            'state_code','timezone_id','coordinate_reference_year','coordinate_reference_kind',
                            'coordinate_reference_subkind','geo_precision']:
                    assert meta[key]==ref[key]
                assert str(meta['municipality_ibge7'])[:6]==municipality
                assert str(meta['state_code'])==municipality[:2]
                assert meta['stratum_id']==f'BR|{municipality[:2]}|{sex}|{year}'
                zone_name=meta['timezone_id']
                if zone_name not in zones:
                    with (Path(tzif_dir)/zone_name).open('rb') as f:zones[zone_name]=ZoneInfo.from_file(f,key=zone_name)
                zone=zones[zone_name];offsets=set()
                for fold in [0,1]:
                    aware=civil.replace(tzinfo=zone,fold=fold);absolute=aware.astimezone(dt.timezone.utc)
                    if absolute.astimezone(zone).replace(tzinfo=None)==civil:offsets.add(int(aware.utcoffset().total_seconds()))
                assert offsets=={meta['source_offset_seconds']}
                assert meta['utc_offset_seconds']==meta['source_offset_seconds']
                expected_utc=(civil-dt.timedelta(seconds=meta['source_offset_seconds'])).isoformat()+'Z'
                assert expected_utc==meta['birth_utc']
                model=by_id[meta['study_id']]
                for key in ['birth_local','birth_utc','source_offset_seconds','sex_resolved','latitude','longitude',
                            'calendar','time_precision_seconds','time_uncertainty_seconds','coordinate_precision_degrees']:
                    assert model[key]==meta[key]
                assert meta['time_precision_seconds']==60 and meta['time_uncertainty_seconds'] is None
                assert abs(meta['sample_weight']-meta['N_h']/meta['n_h'])<1e-10
                assert abs(meta['inclusion_probability']-meta['n_h']/meta['N_h'])<1e-15
                strata[meta['stratum_id']]+=1;by_zone[zone_name]+=1
                minute_counts['minute_zero']+=int(civil.minute==0);minute_counts['multiple_of_five']+=int(civil.minute%5==0)
                coordinates.add(municipality);checked+=1
                if ordinal>=last:break
    assert checked==2000 and set(by_id)=={r['study_id'] for r in records}
    for row in manifest['strata']:assert strata[row['stratum_id']]==row['n_h']
    assert len(strata)==len(manifest['strata'])
    assert abs(sum(r['sample_weight'] for r in records)-manifest['eligible_frame_N'])<1e-5
    assert sha(directory/'birth_inputs.jsonl')==manifest['model_input_sha256']
    assert sha(directory/'birth_metadata.jsonl')==manifest['metadata_sha256']
    return {'year':year,'sample_n':checked,'pass':True,'source_fields_projected':names,
        'independent_source_birth_date_clock_sex_municipality_checks':checked,
        'source_ordinal_and_rank_checks':checked,'approved_IBGE_reference_json_checks':checked,
        'distinct_selected_reference_municipalities':len(coordinates),'independently_compiled_historical_offset_checks':checked,
        'model_to_metadata_checks':checked,'source_records_traversed_through_last_selected':last,
        'strata':len(strata),'compiled_zones':dict(sorted(by_zone.items())),
        'sample_clock_minute_counts_descriptive_only':dict(minute_counts),
        'model_input_sha256':manifest['model_input_sha256'],'metadata_sha256':manifest['metadata_sha256'],
        'archive_sha256':manifest['archive_sha256'],'approved_IBGE_reference_sha256':manifest['reference_sha256'],
        'birth_inputs_unchanged':True,'charts_or_profiles_read':False,'outcome_fields_projected_or_used':False,
        'scope':'Checks selected source records against archived birth CSV fields, approved2022municipal reference JSON and independently compiled IANA rules; not exact birth-site validation or unique-person linkage'}


def main():
    ap=argparse.ArgumentParser()
    for name in ['raw-dir','samples-dir','reference','tzdata-archive','work-dir','output']:
        ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();a.work_dir.mkdir(parents=True,exist_ok=True)
    with tarfile.open(a.tzdata_archive) as t:
        version=t.extractfile('version').read().decode().strip();assert version=='2026c'
        source=t.extractfile('southamerica').read()
    southamerica=a.work_dir/'southamerica';southamerica.write_bytes(source)
    tzif=a.work_dir/'compiled_tzif'
    subprocess.run(['zic','-d',str(tzif),str(southamerica)],check=True)
    jobs=[(year,str(a.raw_dir),str(a.samples_dir),str(a.reference),str(tzif)) for year in [2007,2010,2020,2024]]
    results=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        for result in pool.map(verify_year,jobs):
            results.append(result);print(json.dumps({'year':result['year'],'checked':result['sample_n'],'pass':True}),flush=True)
    report={'verified_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'PASS','total_selected_records_checked':sum(r['sample_n'] for r in results),
        'cohorts':results,'tzdb_version':version,'tzdata_archive_sha256':sha(a.tzdata_archive),
        'southamerica_source_sha256':hashlib.sha256(source).hexdigest(),'verification_code_sha256':sha(Path(__file__)),
        'independent_of_birth_parser_and_eligibility_imports':True,'input_mutations':False,'public_output_contains_individual_ids':False,
        'timezone_source_url':'https://data.iana.org/time-zones/releases/tzdata2026c.tar.gz'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'total':report['total_selected_records_checked'],'receipt_sha256':sha(a.output)}),flush=True)


if __name__=='__main__':main()
