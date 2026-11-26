# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reproduce outcome-free numerical checks without changing frozen artifacts."""
from pathlib import Path
import hashlib
import io
import json
import unittest
import astronomy as independent
import swisseph as swe
from open_birth_chart import astronomy as a, qizheng_engine as q


def main():
    here=Path(__file__).resolve().parent
    repo=here.parents[1]
    freeze=json.loads((repo/'protocol'/'qizheng_western_freeze.json').read_text())
    hash_checks={name:hashlib.sha256((repo/name).read_bytes()).hexdigest()==expected
                 for name,expected in freeze['sha256'].items()}
    if not all(hash_checks.values()):
        raise RuntimeError(f'Frozen source files changed: {hash_checks}')
    source=json.loads((here/'1833_reference.json').read_text())
    book=[]
    for day,rows in source['transcription_rows']:
        jd=source['jd_ut']+day
        for variant in ('mean','osculating'):
            positions=q.qizheng_sky(jd,variant)
            for name,(mansion,degree,minute) in zip(('Yuebo','Luohou','Jidu','Ziqi'),rows):
                target=(q.mansion_boundaries(jd)[q.MANSION_NAMES.index(mansion)]+degree+minute/60)%360
                error=((positions[name]['longitude']-target+180)%360-180)*60
                book.append((name,variant,error))
    nominal,matched=[],[]
    for year in (1880,1950,2000,2026,2070):
        jd=swe.julday(year,6,15,12)
        times=(independent.Time(jd-2451545),independent.Time(jd-2451545,jd+swe.deltat(jd)-2451545))
        for name in a.TEN:
            lon=a.position(jd,name)['longitude']
            for t,out in zip(times,(nominal,matched)):
                other=independent.Ecliptic(independent.GeoVector(getattr(independent.Body,name),t,True)).elon
                out.append(a.circular_distance(lon,other)*3600)
    suite=unittest.defaultTestLoader.discover(str(repo/'tests'),pattern='test_qizheng_western.py')
    log=io.StringIO()
    result=unittest.TextTestRunner(stream=log,verbosity=1).run(suite)
    summary={'frozen_hashes_match':all(hash_checks.values()),'tests_run':result.testsRun,
             'tests_pass':result.wasSuccessful(),'astronomy_cases':len(nominal),
             'max_nominal_ut_arcsec':max(nominal),'max_matched_tt_arcsec':max(matched),
             'historical_max_error_arcmin':{
                 f'{name}_{variant}':max(abs(e) for n,v,e in book if n==name and v==variant)
                 for name in ('Yuebo','Luohou','Jidu','Ziqi') for variant in ('mean','osculating')},
             'outcomes_read':False,'forecast_validity_tested':False}
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print(log.getvalue())
    if not result.wasSuccessful(): raise SystemExit(1)


if __name__=='__main__': main()
