"""Exact window bounds using Japanese date-hour counts and R41 synthetic masks."""

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
import gzip
from pathlib import Path
import subprocess

import numpy as np

from rounds.r34.source import read_counts
from rounds.r41.profiles import study_dates
from rounds.r45.common import R10, ROOT, digest, fractions, read_json, require, write_json
from rounds.r45.review import centered, classify_exact, exact_mean_columns, integral_weights, points
from analyze_cohorts import load_profiles
from precision_reference import PrecisionReference
from rounds.r27.verify import weighted_rank_tables

HERE = Path(__file__).resolve().parent
REGISTRATION = "1db5d645d00f7f1f6760b9c9982369fd98c0ffed"


@dataclass(frozen=True)
class Cell:
    day: date
    hour: int
    count: int
    masks: tuple


def protocol():
    for name in ("protocol.json","REGISTRATION.zh.md"):
        first = subprocess.check_output(["git","show",f"{REGISTRATION}:rounds/r47/{name}"],cwd=ROOT)
        require(first == (HERE/name).read_bytes(), "Changed Japan registration")
    cfg = read_json(HERE/"protocol.json")
    require(digest(ROOT/cfg["grid_path"]) == cfg["grid_sha256"]
            and digest(ROOT/"rounds/r45/results.json") == cfg["r45_aggregate_sha256"], "Frozen R41/R45 files differ")
    return cfg


def calibrate(r10, cfg):
    commitments = read_json(R10/"independent_replay/registration.json")["reference_files_sha256"]
    require(all(digest(r10/name) == sha for name,sha in commitments.items()), "Brazil reference is not the R10 freeze")
    rr, _, scores, weights, *_ = load_profiles(
        r10/"reference/brazil2006", [r10/"reference/full-frozen-r8-baseline_profiles.jsonl"])
    fixed = PrecisionReference(scores,weights,fractions(rr))
    exact = classify_exact(scores,weighted_rank_tables(scores,fractions(rr)),Fraction(4,5))
    require(np.array_equal(fixed.flags(scores),exact), "Brazil fixed border flags disagree")
    _, _, zeros = points(exact,3,cfg["window_years"])
    starts = cfg["age_starts"][1]-cfg["age_starts"][0]+1
    b = exact_mean_columns(centered(zeros),integral_weights(rr),starts)
    prior = read_json(ROOT/"rounds/r45/results.json")["primary"]["reference_centers"][0]
    require(sum(b) == 0 and np.allclose(np.asarray(b,dtype=float),prior,atol=1e-14,rtol=0), "R45 gap centers differ")
    return b


def load_panel(source, cfg):
    years = cfg["birth_years"]
    counts, receipts = {}, {}
    panels = {year: [] for year in years}
    for year in years:
        counts[year], receipts[year] = read_counts(source,year)
    with gzip.open(ROOT/cfg["grid_path"],"rt",encoding="ascii",newline="") as stream:
        rows = csv.reader(stream)
        header = ["date","hour","official_birth_count"]
        header.extend(f"minute_{m:02d}_{s}" for m in range(cfg["minutes_per_hour"]) for s in cfg["sex_parameters"])
        require(next(rows) == header,"Wrong synthetic mask header")
        for year in years:
            for day in study_dates(year):
                offset = (day-date(year,1,1)).days
                for hour,count in enumerate(counts[year][offset]):
                    raw = next(rows)
                    require(raw[:3] == [day.isoformat(),str(hour),str(count)]
                            and len(raw) == len(header) and all(len(m)==10 for m in raw[3:]), "Wrong date-hour cell")
                    values = tuple(int(m,16) for m in raw[3:])
                    require(all(0 <= m < 1 << 40 for m in values), "Invalid 40-age mask")
                    panels[year].append(Cell(day,hour,int(count),values))
        require(next(rows,None) is None, "Unexpected records in R41 grid")
    return panels, receipts


def age_maps(cell, axes):
    default = np.arange(len(axes["age"]))
    first = cell.day.year+20+int((cell.day.month,cell.day.day)>(7,1))
    assigned = np.asarray(axes["calendar"]) - first
    require(np.all((0<=assigned)&(assigned<len(default))), "Registered calendar range is not covered")
    return {"age":default,"calendar":assigned}


def numerators(masks, width, length):
    years = np.asarray(masks,dtype=np.uint64)[:,None]
    windows = (years >> np.arange(length,dtype=np.uint64)) & ((1 << width)-1)
    zero = windows == 0
    return length*zero - zero.sum(axis=1,keepdims=True)


def deterministic_mix(count, options):
    return np.diff(np.arange(options+1)*count//options)


def axis_data(cells, reference, axes, width):
    n = sum(cell.count for cell in cells)
    length = len(axes["age"])
    structures = {axis:{name:np.zeros(len(starts),dtype=np.int64) for name in ("lower","upper","balanced")}
                  for axis,starts in axes.items()}
    offsets = {axis:[Fraction(0)]*len(starts) for axis,starts in axes.items()}
    for cell in cells:
        raw = numerators(cell.masks,width,length)
        mix = deterministic_mix(cell.count,len(cell.masks))
        for axis, locations in age_maps(cell,axes).items():
            local = raw[:,locations]
            values = structures[axis]
            values["lower"] += cell.count*local.min(axis=0)
            values["upper"] += cell.count*local.max(axis=0)
            values["balanced"] += mix @ local
            for i,a in enumerate(locations):
                offsets[axis][i] += reference[a]*cell.count
    return {axis:{kind:[100*(Fraction(int(num),length*n)-b/n)
                        for num,b in zip(raw,offsets[axis],strict=True)] for kind,raw in values.items()}
            for axis,values in structures.items()}


def assignment(cells, axes, axis, start_index, width):
    size = len(axes["age"])
    return [int(numerators(cell.masks,width,size)[:,age_maps(cell,axes)[axis][start_index]].argmax()) for cell in cells]


def number(rational):
    return {"exact":str(rational),"value":float(rational)}


def artificial_split(source, centers, axes, width):
    frames = {}
    for year, cells in source.items():
        split = [Cell(c.day,c.hour,(c.count+(s==0))//2,c.masks[s::2])
                 for c in cells for s in (0,1)]
        frames[year] = axis_data(split,centers,axes,width)
    result = {axis:{kind:number(max(min(f[axis][kind][i] for f in frames.values()) for i in range(len(starts))))
                    for kind in ("lower","upper","balanced")} for axis,starts in axes.items()}
    return {"assumption":"Artificial per-cell split with F receiving an extra record when count is odd",
            "primary_registration_unchanged":True,"common":result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "r10-job", "output"):
        parser.add_argument("--"+key,type=Path,required=True)
    parser.add_argument("--sex-split-output",type=Path)
    args = parser.parse_args()
    cfg = protocol()
    centers = calibrate(args.r10_job,cfg)
    source, receipts = load_panel(args.source,cfg)
    width = cfg["window_years"]
    axes = {k:list(range(cfg[k+"_starts"][0],cfg[k+"_starts"][1]+1)) for k in ("age","calendar")}
    frames = {y:axis_data(cells,centers,axes,width) for y,cells in source.items()}
    out = {"registration":REGISTRATION,"grid_sha256":cfg["grid_sha256"],
           "reference_age_centers":[str(value) for value in centers],"window_starts":axes,
           "virtual_scores":sum(len(cell.masks) for cells in source.values() for cell in cells),
           "years":{},"common":{}}
    for y, cells in source.items():
        N = sum(cell.count for cell in cells)
        require(N == cfg["cohort_counts"][str(y)], "Japanese birth count differs from registration")
        out["years"][str(y)] = {"official_panel_birth_count":N,"date_hour_cells":len(cells),
                                 "source_sha256":receipts[y]["source_sha256"],
                                 "window_effect_curves_pp":{axis:{key:[number(v) for v in row] for key,row in cols.items()}
                                                            for axis,cols in frames[y].items()}}
    for axis, domain in axes.items():
        joint = {k:[min(frame[axis][k][i] for frame in frames.values()) for i in range(len(domain))]
                 for k in ("lower","upper","balanced")}
        peaks = {k:max(v) for k,v in joint.items()}
        start_index = joint["upper"].index(peaks["upper"])
        at = cfg["minimum_percentage_points"]
        decision = ("excluded" if peaks["upper"] < at else "supported" if peaks["lower"] >= at else
                    "not_identified_two_feasible_assignments" if peaks["balanced"] < at else "not_identified")
        out["common"][axis] = {"sharp_upper_pp":number(peaks["upper"]),"safe_lower_pp":number(peaks["lower"]),
                               "balanced_feasible_pp":number(peaks["balanced"]),"upper_axis_start":domain[start_index],
                               "upper_assignment":{str(y):assignment(cells,axes,axis,start_index,width)
                                                   for y,cells in source.items()},
                               "decision":decision}
    write_json(args.output,out)
    if args.sex_split_output is not None:
        write_json(args.sex_split_output,artificial_split(source,centers,axes,width))


if __name__ == "__main__":
    main()
