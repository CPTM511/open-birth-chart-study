"""Read Japanese vital-statistics birth tables grouped by date, hour and venue."""
import argparse
from calendar import monthrange
import csv
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
from unicodedata import normalize

HERE = Path(__file__).resolve().parent
VENUES = ("総数", "病院", "診療所", "助産所", "自宅", "その他")
YEARS = (2024, 2025)
DAY_HOURS = slice(10,19)  # column zero is total, 09--17 inclusive


def clean(value):
    return normalize("NFKC",value).replace(" ","")


def require(ok,msg):
    if not ok:
        raise ValueError(msg)


def digest(p):
    return sha256(p.read_bytes()).hexdigest()


def labels(value,unit,lo,hi):
    if value=="総数":
        return 0
    require(re.fullmatch(r"[0-9]+"+unit,value) is not None,"Unexpected label: "+value)
    n=int(value.removesuffix(unit))
    require(lo<=n<=hi,"Unexpected numeric label")
    return n


def value(raw):
    if raw=="-":
        return 0
    require(re.fullmatch(r"[0-9]+",raw) is not None,"Unrecognized count cells")
    return int(raw)


def source_blocks(p):
    with p.open(encoding="cp932",newline="") as src:
        rows=csv.reader(src)
        blocks={}
        block=None
        columns=False
        for row in rows:
            if row and row[0]=="" and len(row)==26:
                require([clean(s) for s in row[1:]]==["総数",*(str(i)+"時" for i in range(24))],
                        "Source hour order changed")
                columns=True
            elif len(row)==1 and "*" in row[0]:
                venue, month=map(clean,row[0].split("*",1))
                require(venue in VENUES and columns,"Unexpected venue or row ordering")
                block=(venue,labels(month,"月",1,12))
            elif block is not None and len(row)==26:
                day=labels(clean(row[0]),"日",1,31)
                k=(*block,day)
                require(k not in blocks,"Duplicate source cell")
                blocks[k]=tuple(value(x) for x in row[1:])
        require(set(blocks)=={(v,m,d) for v in VENUES for m in range(13) for d in range(32)},
               "The full published venue/month/day support is incomplete")
        return blocks


def add_vectors(values):
    return tuple(map(sum,zip(*values,strict=True)))


def year_summary(p,year,official_total):
    data=source_blocks(p)
    valid={"weekday":[],"weekend":[]}
    checked=0
    for venue in VENUES:
        yearly=data[venue,0,0]
        require(add_vectors(data[venue,m,0] for m in range(1,13))==yearly,"Monthly totals disagree with annual")
        checked+=25
        for m in range(1,13):
            require(add_vectors(data[venue,m,d] for d in range(1,32))==data[venue,m,0],"Daily totals disagree with monthly")
            checked+=25
            last=monthrange(year,m)[1]
            require(not any(any(data[venue,m,d]) for d in range(last+1,32)),"Birth on an invalid date")
            for d in range(1,last+1):
                components=data[venue,m,d]
                require(components[0]>=sum(components[1:]),"Known births exceed the date total")
                if venue==VENUES[0]:
                    k="weekend" if date(year,m,d).weekday()>=5 else "weekday"
                    valid[k].append(components)
    total=data[VENUES[0],0,0]
    require(total[0]==official_total,"Published all-birth annual total differs")
    for m in range(13):
        for d in range(32):
            require(add_vectors(data[v,m,d] for v in VENUES[1:])==data[VENUES[0],m,d],"Venue rows do not reconcile")
            checked+=25
    out={"births_publisher_total":total[0],"hour_known":sum(total[1:]),
         "hour_unknown":total[0]-sum(total[1:]),"hour_counts_0_through_23":total[1:],
         "counts_by_venue":{v:data[v,0,0][0] for v in VENUES[1:]},"checks_of_source_aggregates":checked}
    proportions={}
    for k,items in valid.items():
        collapsed=add_vectors(items)
        known=sum(collapsed[1:])
        daytime=sum(collapsed[DAY_HOURS])
        proportions[k]=Fraction(daytime,known)
        out[k]={"days":len(items),"births_all":collapsed[0],"births_hour_known":known,
                "births_0900_1759":daytime,"share_known_clocks_0900_1759":float(proportions[k])}
    require(add_vectors(v for items in valid.values() for v in items)==total,
            "Cross-check of weekday and weekend dates failed")
    out["weekday_minus_weekend_pp"]=float(100*(proportions["weekday"]-proportions["weekend"]))
    return out


def analyze(args):
    spec=HERE/"protocol.json"
    require(digest(spec)==args.registration_sha256,"Use published R18 protocol hash")
    config=json.loads(spec.read_bytes())
    for filename,expected in config["method_sha256"].items():
        require(digest(HERE/filename)==expected,"Method changed since registration")
    result={}
    for y in YEARS:
        name=f"jp{y}.csv"
        source=args.sources/name
        require(digest(source)==config["source_sha256"][name],"Publisher source hash differs")
        result[y]=year_summary(source,y,config["official_birth_totals"][str(y)])
    out={"registration_sha256":args.registration_sha256,"years":result,
         "practical_threshold_pp":config["practical_threshold_pp"],
         "aggregate_only":True,"individual_charts_computed":0}
    with args.output.open("x",encoding="utf-8") as f:
        json.dump(out,f,ensure_ascii=False,allow_nan=False,indent=2)
        f.write("\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources",required=True,type=Path)
    p.add_argument("--registration-sha256",required=True)
    p.add_argument("--output",required=True,type=Path)
    analyze(p.parse_args())
