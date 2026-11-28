"""Audit literal period coverage separately from the R45 high-score endpoint."""

import argparse
from calendar import isleap
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import multiprocessing
import subprocess

from lunar_python import Solar

from rounds.r45.common import ROOT, digest, read_json, require, write_json
from rounds.r45.datasets import datasets
from open_birth_chart_r10 import bazi_engine, ziwei_engine, qizheng_engine, astronomy

HERE = Path(__file__).resolve().parent
REGISTRATION = "286d37385fbbbd420da6c3f6568f5bcaa112ee08"
GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
JIAZI = [GAN[i%10]+ZHI[i%12] for i in range(60)]
CLASSES = {"水二局":2,"木三局":3,"金四局":4,"土五局":5,"火六局":6}
CST = timezone(timedelta(hours=8))


def registered():
    for name in ("protocol.json","REGISTRATION.zh.md"):
        old = subprocess.check_output(["git","show",f"{REGISTRATION}:rounds/r48/{name}"],cwd=ROOT)
        require((HERE/name).read_bytes() == old,"Literal period registration was altered")
    return read_json(HERE/"protocol.json")


def anniversary(moment, years):
    target = moment.year+years
    day = 28 if moment.month==2 and moment.day==29 and not isleap(target) else moment.day
    return moment.replace(year=target,day=day)


def extent(intervals, first, end):
    """Half-open sweep returning the uncovered and multiply covered segments."""
    require(first<end,"Invalid interval of interest")
    events = Counter({first:0,end:0})
    for start,stop in intervals:
        require(start<stop,"Malformed period")
        lo,hi = max(start,first),min(stop,end)
        if lo<hi:
            events[lo] += 1
            events[hi] -= 1
    order = sorted(events)
    gaps, overlaps = [], []
    active = 0
    for left,right in zip(order,order[1:]):
        active += events[left]
        if active==0:
            gaps.append((left,right))
        if active>1:
            overlaps.append((left,right))
    return gaps,overlaps


def one_only(intervals, value):
    hit = [j for j,(lo,hi) in enumerate(intervals) if lo<=value<hi]
    require(len(hit)==1,"No unique period at a registered age or instant")
    return hit[0]


def bazi_cover(row, cfg):
    chart = bazi_engine.build_chart(row)
    periods = chart["decades"]
    birth = datetime.fromisoformat(row["birth_local"]).replace(
        tzinfo=timezone(timedelta(seconds=row["source_offset_seconds"])))
    first = datetime.fromisoformat(chart["qiyun"]["start_utc"]).astimezone(CST)
    intervals = [(datetime.fromisoformat(p["start_utc"]),datetime.fromisoformat(p["end_utc_exclusive"])) for p in periods]
    require(len(periods)==cfg["bazi_expected_decades"],"Wrong number of BaZi periods")
    expected_forward = (GAN.index(chart["pillars"]["year"]["stem"])%2==0)==(row["sex"]=="M")
    direction = 1 if expected_forward else -1
    require(chart["qiyun"]["direction"]==("forward" if expected_forward else "backward"),"BaZi direction mismatch")
    month = JIAZI.index(chart["pillars"]["month"]["ganzhi"])
    for n, label in enumerate(periods):
        require(intervals[n]==(anniversary(first,10*n),anniversary(first,10*(n+1)))
                and label["ganzhi"]==JIAZI[(month+direction*(n+1))%60] and label["index"]==n+1,
                "BaZi anniversary or ganzhi fails independent reconstruction")
    domain = tuple(anniversary(birth,y) for y in cfg["completed_age_interval"])
    require(extent(intervals,*domain)==([],[]),"A BaZi adult period is missing or overlaps")
    snapshots = [datetime(y,7,1,12,tzinfo=birth.tzinfo) for y in row["calendar_years"]]
    for snap in snapshots:
        one_only(intervals,snap)
    return {"bazi_periods":len(periods),"bazi_scores_with_unique_period":len(snapshots),
            "bazi_forward":int(expected_forward),"bazi_activation_delay_seconds":int((first-birth).total_seconds())}


def ziwei_cover(row, cfg, replay):
    years = row["calendar_years"] if replay else ()
    reply = ZW.compute(row,years,include_chart=True,detailed=replay)
    require(reply["status"]=="computed_for_registered_conventions","Ziwei natal chart did not compute")
    chart = reply["chart"]
    pals = sorted(chart["palaces"],key=lambda p:p["decadal"]["range"][0])
    require(len(pals)==cfg["ziwei_expected_decades"] and len({p["earthly_branch"] for p in pals})==len(pals),
            "Wrong Ziwei palace count")
    seed = CLASSES[chart["five_elements_class"]]
    direction = 1 if (GAN.index(chart["chinese_date"][0])%2==0)==(row["sex"]=="M") else -1
    life = ZHI.index(chart["soul_branch"])
    intervals = []
    for j,p in enumerate(pals):
        start,stop = p["decadal"]["range"]
        require((start,stop)==(seed+10*j,seed+10*j+9)
                and ZHI.index(p["earthly_branch"])==(life+j*direction)%12,"Ziwei boundary or palace order differs")
        intervals.append((start,stop+1))
    start,stop = cfg["ziwei_nominal_age_inclusive"]
    require(extent(intervals,start,stop+1)==([],[]),"A Ziwei adult nominal age has no unique limit")
    changed = 0
    for age in range(start,stop+1):
        j = one_only(intervals,age)
        pivot = (life+direction*(j+1))%12
        changed += int(pivot!=ZHI.index(pals[j]["earthly_branch"]))
    replay_n = 0
    born = chart["raw_lunar_date"]["lunarYear"]
    for expected, item in zip(years,reply["annual"],strict=True):
        age = Solar.fromYmd(expected,7,1).getLunar().getYear()-born+1
        j = one_only(intervals,age)
        require(item["status"]=="computed_for_registered_conventions" and item["year"]==expected
                and item["other_cycles"]["age"]["nominalAge"]==age and item["decadal_index"]==pals[j]["index"],
                "Ziwei annual snapshot fails independent nominal-age check")
        replay_n += 1
    return {"ziwei_periods":len(pals),"ziwei_nominal_ages_with_unique_palace":stop-start+1,
            "neighbor_start_palace_changes":changed,"ziwei_annual_replay_matches":replay_n,
            "ziwei_first_admitted_nominal_age":seed}


def qizheng_cover(row):
    first,last = row["calendar_years"][0],row["calendar_years"][-1]
    earliest = astronomy.annual_instants(first)[0]
    latest = astronomy.annual_instants(last)[-1]
    absolute = datetime.fromisoformat(row["birth_utc"].replace("Z","+00:00"))
    jd = astronomy.julian_day(absolute)
    min_age,max_age = [astronomy.age_years(jd,x) for x in (earliest,latest)]
    require(0<=min_age<=max_age<100.5,"Monthly snapshots leave the selected Dongwei schedule")
    return {"qizheng_minimum_monthly_age":min_age,"qizheng_maximum_monthly_age":max_age,
            "qizheng_monthly_snapshots_in_schedule":len(row["calendar_years"])*12}


def initialize():
    global ZW
    ZW = ziwei_engine.ZiweiEngine()


def score(packet):
    row,cfg,replay = packet
    return bazi_cover(row,cfg)|ziwei_cover(row,cfg,replay)|qizheng_cover(row)


def check_controls():
    original = [(3,13),(13,23),(23,33),(33,43)]
    require(extent(original,20,40)==([],[]),"Continuous fixture failed")
    require(extent([original[0],*original[2:]],10,40)==([(13,23)],[]),"Removed decade not detected")
    require(extent(original+[(24,26)],20,40)==([],[(24,26)]),"Overlap not detected")
    require(extent(original,0,6)==([(0,3)],[]),"Pre-activation interval not detected")
    durations = [15,10,11,15,8,7,11,4.5,4.5,4.5,5,5]
    require(tuple(durations)==qizheng_engine.MAJOR_YEARS and sum(durations)==100.5,"Wrong selected Dongwei lengths")
    year_days = 365.2422
    require(astronomy.TROPICAL_YEAR_DAYS==year_days,"The registered unit of years differs")
    # Probe both sides of every stage boundary without depending on equality of floating-point Julian days.
    toy = {"birth":{"jd_ut":2451545.},"ming":{"branch_index":0}}
    now = 0.
    for index,length in enumerate(durations):
        require(qizheng_engine.major_period(toy,2451545.+(now+1e-5)*year_days)["index"]==index,
                "Dongwei boundary entry differs")
        now += length
        require(qizheng_engine.major_period(toy,2451545.+(now-1e-5)*year_days)["index"]==index,
                "Dongwei boundary exit differs")
    require(qizheng_engine.major_period(toy,2451545.+101*year_days) is None,"Dongwei domain was silently extended")
    return {"continuous":True,"deleted_decade_detected":True,"overlap_detected":True,"pre_activation_distinct":True,
            "dongwei_boundary_probes":24,"dongwei_domain_end_years":now}


def combine(results):
    stats = defaultdict(list)
    for row in results:
        for key,value in row.items():
            stats[key].append(value)
    numeric_spans = {"bazi_activation_delay_seconds","qizheng_minimum_monthly_age","qizheng_maximum_monthly_age"}
    out = {key:sum(values) for key,values in stats.items() if key not in numeric_spans | {"ziwei_first_admitted_nominal_age"}}
    for name in sorted(numeric_spans):
        out[name+"_minmax"] = [min(stats[name]),max(stats[name])]
    out["ziwei_first_admitted_nominal_age_counts"] = dict(sorted(Counter(stats["ziwei_first_admitted_nominal_age"]).items()))
    out["complete_inputs"] = len(results)
    out["observed_gap_or_overlap"] = 0
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("r45-job","r10-job","r13-job","r15-job","original-scan","output"):
        parser.add_argument("--"+key,type=Path,required=True)
    parser.add_argument("--jobs",type=int,default=4,choices=range(1,5))
    args = parser.parse_args()
    cfg = registered()
    require(digest(args.original_scan)==cfg["bazi_source"]["pdf_sha256"],"Classical facsimile differs")
    args.job = args.r45_job
    past = read_json(ROOT/"rounds/r45/protocol.json")
    inputs = datasets(args,past)
    checks = check_controls()
    out = {}
    with multiprocessing.Pool(args.jobs,initializer=initialize) as pool:
        for name,n in cfg["r45_records"].items():
            rows = inputs[name].births()
            require(len(rows)==n,"R45 population changed")
            seed = cfg["ziwei_replay_seed"]+"|"
            order = sorted(rows,key=lambda r:sha256((seed+r["study_id"]).encode()).digest())
            take = {row["study_id"] for row in order[:cfg["ziwei_july_snapshot_replay_per_group"]]}
            units = ((row,cfg,row["study_id"] in take) for row in rows)
            out[name] = combine(list(pool.imap(score,units,chunksize=8)))
            print(name, n, flush=True)
    write_json(args.output,{"registration":REGISTRATION,"groups":out,"controls":checks,
                            "western_decadal_coverage":"inapplicable_to_frozen_western_score",
                            "historical_parity_authority":"BaZi cited text and R44 ZiWei comparison",
                            "outputs_from_real_birth_outcomes":False})


if __name__=="__main__":
    main()
