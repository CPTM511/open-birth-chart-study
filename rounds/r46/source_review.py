"""Reread every selected physical birth row, including the original 2017 layout."""

import argparse
from collections import defaultdict
import csv
from datetime import date, datetime
from fractions import Fraction
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from rounds.r45.prepare import mexico
from rounds.r13.sources.audit_mexico_1990s import reference_points
from rounds.r9.data.mexico.audit_mexico2015 import dbf_header
from rounds.r15.review_inputs import independent_instant

from .common import GROUPS, HERE, REGISTRATION, digest, private, protocol, read_json, require, write_json
from .score import inputs


def same_birth(row, moment, sex, lat, lon, zone):
    utc = independent_instant(moment,ZoneInfo(zone))
    require(utc is not None and row["birth_local"]==moment.isoformat()
            and row["birth_utc"]==utc.isoformat().replace("+00:00","Z")
            and row["sex"]==sex and row["latitude"]==lat and row["longitude"]==lon
            and row["timezone_id"]==zone,"Input differs from the official physical record")


def verify_brazil(path, rows, references, year):
    expected = {int(row["source_row_id"]):row for row in rows}
    seen = set()
    filename = "SINASC_1999.csv" if year==1999 else "DNBR2009.csv"
    with ZipFile(path) as z, TextIOWrapper(z.open(filename),encoding="utf-8-sig",newline="") as stream:
        for ordinal, raw in enumerate(csv.DictReader(stream,delimiter=";"),1):
            if ordinal not in expected:
                continue
            clock = raw["HORANASC"]
            local = datetime.strptime(raw["DTNASC"]+clock,"%d%m%Y%H%M")
            sex = {"1":"M","2":"F"}[raw["SEXO"]]
            place = raw["CODMUNNASC"]
            point = references[place[:6]]
            require(local.year==year and (len(place)==6 or point["municipality_ibge7"]==place),
                    "Brazil year or full location key changed")
            saved = expected[ordinal]
            require(saved["source_id"]==f"SINASC{year}:row:{ordinal:07d}","Brazil physical-key mismatch")
            same_birth(saved,local,sex,point["latitude"],point["longitude"],point["timezone_id"])
            seen.add(ordinal)
    require(seen==set(expected),"Incomplete official Brazil reread")
    return {"physical_rows_scanned":ordinal,"selected_rows_verified":len(seen)}


def verify_mexico(paths,rows,geography,modern):
    groups = defaultdict(dict)
    for row in rows:
        label,key = row["source_id"].rsplit("-",1)
        year,ordinal = int(label.removeprefix("INEGI-NACIM")),int(key)
        require(ordinal not in groups[year],"Duplicate selected Mexico ordinal")
        groups[year][ordinal] = row
    counts = {}
    for year, selected in sorted(groups.items()):
        with ZipFile(paths[year]) as z:
            members = {Path(k).name.lower():k for k in z.namelist()}
            with z.open(members[f"nacim{year%100:02}.dbf"]) as stream:
                length,width,schema,encoding = dbf_header(stream)
                head = stream.tell()
                month = "MES_NACIM" if year==2017 else "MES_NAC"
                birth_fields = ("ANO_NAC",month,"DIA_NAC","HORA_NAC","MINUTO_NAC")
                common = (*birth_fields,"SEXO","ANO_REG","MES_REG","DIA_REG","ENT_OCURR","MUN_OCURR")
                columns = common+("LOC_OCURR",) if modern else common
                offsets = {k:slice(schema[k][0],schema[k][0]+schema[k][1]) for k in columns}
                for ordinal, row in sorted(selected.items()):
                    require(1<=ordinal<=length,"Mexico row offset outside table")
                    stream.seek(head+(ordinal-1)*width)
                    record = stream.read(width)
                    require(len(record)==width and record[:1]==b" ","Missing or deleted physical Mexico row")
                    raw = {k:record[span].decode(encoding).strip() for k,span in offsets.items()}
                    local = datetime(*(int(raw[k]) for k in birth_fields))
                    registration = date(*(int(raw[k]) for k in ("ANO_REG","MES_REG","DIA_REG")))
                    require(registration.year==year and local.date()<=registration,"Mexico registration date differs")
                    place = raw["ENT_OCURR"].zfill(2)+raw["MUN_OCURR"].zfill(3)
                    if modern:
                        place += raw["LOC_OCURR"].zfill(4)
                    _,lat,lon,zone = geography[place]
                    same_birth(row,local,{"1":"M","2":"F"}[raw["SEXO"]],lat,lon,zone)
                counts[str(year)] = len(selected)
    require(sum(counts.values())==len(rows),"Incomplete official Mexico reread")
    return {"selected_rows_verified":len(rows),"selected_per_registration_year":counts,
            "original_2017_month_read_directly":modern and "2017" in counts}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("job","replay-job","br1999","br2009","references","mex-modern","mex-old","iter","seats","output"):
        p.add_argument("--"+name,type=Path,required=True)
    a = p.parse_args()
    protocol()
    results = {}
    refs = read_json(a.references)
    for group in GROUPS:
        rows,_,seal = inputs(private(a.job),group)
        replay_rows,_,fresh = inputs(private(a.replay_job),group)
        require(seal==fresh and rows==replay_rows,"Source re-selection differs")
        registered = read_json(HERE/"seals"/f"{group}.json")
        if group.startswith("br"):
            path = getattr(a,group)
            require(digest(path)==registered["source_archive_sha256"]
                    and digest(a.references)==registered["municipality_reference_sha256"],"Wrong Brazil source")
            evidence = verify_brazil(path,rows,refs,int(group[2:]))
        else:
            is_modern = group=="mx1999"
            if is_modern:
                archives = {s["year"]:s["sha256"] for s in registered["archives"] if s["included"]}
                paths = {year:a.mex_modern/f"natalidad_base_datos_{year}_dbf.zip" for year in archives}
                points = reference_points(a.iter)
            else:
                archives = {int(y):h for y,h in registered["source_archive_sha256"].items()}
                paths = {year:a.mex_old/f"{year}/natalidad_base_datos_{year}_dbf.zip" for year in archives}
                points,_ = mexico.municipal_points(a.seats,a.iter)
            require(all(digest(paths[y])==sha for y,sha in archives.items()),"Wrong Mexico archive")
            evidence = verify_mexico(paths,rows,points,is_modern)
        require(sum(Fraction(r["N_h"],r["n_h"]) for r in rows)==registered["eligible_frame_N"],
                "Sampling weights differ from the sealed frame")
        results[group] = dict(evidence,independent_source_replay_matches=True,input_seal_sha256=seal)
    write_json(a.output,{"registration":REGISTRATION,"groups":results,"physical_source_rows_verified":sum(
        row["selected_rows_verified"] for row in results.values()),"shared_geographic_references":True})


if __name__=="__main__":
    main()
