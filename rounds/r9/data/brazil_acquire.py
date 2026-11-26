#!/usr/bin/env python3
"""Download a bounded, official SINASC CSV archive discovered in the catalogue.

Only public birth archives are fetched. The archive is kept outside the repo.
No authentication, outcome linking, or paid endpoints are used.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request
import zipfile

CATALOGUE = 'https://dadosabertos.saude.gov.br/dataset/sistema-de-informacao-sobre-nascidos-vivos-sinasc'
AGENT = 'OpenBirthChartStudy-R9/1.0 public research'

def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--year',type=int,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--catalogue-file',type=Path)
    p.add_argument('--max-bytes',type=int,default=160_000_000)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if a.catalogue_file:
        raw=a.catalogue_file.read_bytes()
    else:
        with urllib.request.urlopen(urllib.request.Request(CATALOGUE,headers={'User-Agent':AGENT}),timeout=30) as r:
            raw=r.read(10_000_001)
        if len(raw)>10_000_000:raise ValueError('Catalogue exceeds size cap')
    matches=re.findall(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',raw.decode('utf8'),re.S)
    if len(matches)!=1:raise ValueError('Expected one explicit catalogue JSON block')
    entries={o['url']:o for o in walk(json.loads(matches[0])) if o.get('format')=='CSV' and str(o.get('name','')).strip().endswith(str(a.year)) and o.get('url')}
    if len(entries)!=1:raise ValueError('Year does not identify exactly one CSV resource')
    url,resource=next(iter(entries.items()))
    if not url.startswith('https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINASC/csv/') or not url.endswith('.zip'):
        raise ValueError('Unexpected official archive location')
    dest=a.out/f'brazil{a.year}.zip';manifest=a.out/f'brazil{a.year}.download.json'
    if dest.exists():raise FileExistsError('Preserve existing archive; inspect its manifest instead')
    temp=dest.with_suffix('.part');h=hashlib.sha256();size=0
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':AGENT}),timeout=45) as r,temp.open('xb') as f:
        if r.status!=200:raise ValueError(f'HTTP {r.status}')
        length=r.headers.get('Content-Length')
        if length and int(length)>a.max_bytes:raise ValueError('Declared size exceeds cap')
        headers={k:r.headers.get(k) for k in ['Content-Type','Content-Length','Last-Modified','ETag']}
        while block:=r.read(1<<20):
            size+=len(block)
            if size>a.max_bytes:raise ValueError('Download exceeds size cap')
            h.update(block);f.write(block)
    if length and size!=int(length):raise ValueError('Incomplete download')
    if not zipfile.is_zipfile(temp):raise ValueError('Not a ZIP archive')
    temp.replace(dest)
    with zipfile.ZipFile(dest) as z:
        members=[{'name':x.filename,'bytes':x.file_size,'compressed_bytes':x.compress_size} for x in z.infolist()]
        csvs=[x for x in z.namelist() if x.lower().endswith('.csv')]
        headers_csv={name:z.open(name).readline().decode('utf-8-sig').strip() for name in csvs}
    out={'catalogue_url':CATALOGUE,'catalogue_sha256':hashlib.sha256(raw).hexdigest(),'year':a.year,'resource_id':resource['id'],'download_url':url,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'http_status':200,'bytes':size,'sha256':h.hexdigest(),'headers':headers,'members':members,'csv_headers':headers_csv,'outcome_fields_used':False}
    manifest.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out),flush=True)

if __name__=='__main__':main()
