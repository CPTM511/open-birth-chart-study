"""Check every Japan date-hour cell and the two constructive exact bounds."""

import argparse
import csv
from fractions import Fraction
import gzip
from pathlib import Path

from rounds.r27.archive_source import digest, read_json, require, write_json
from rounds.r41.check_release import compressed_panel
from .bounds import REGISTRATION, ROOT, protocol


def window_numerators(mask, width, n):
    trace = bin(mask)[2:].zfill(n+width-1)[::-1]
    zeros = [trace[i:i+width].count("1") == 0 for i in range(n)]
    return [n*value-sum(zeros) for value in zeros]


def check_ratio(expected, actual):
    require(Fraction(expected["exact"]) == actual and expected["value"] == float(actual), "Exact gap curve differs")


def verify(source, path, output):
    cfg = protocol()
    reported = read_json(path)
    require(reported["registration"] == REGISTRATION and reported["grid_sha256"] == cfg["grid_sha256"], "Wrong release")
    baseline = [Fraction(x) for x in reported["reference_age_centers"]]
    axes = reported["window_starts"]
    require(sum(baseline) == 0 and all(axes[axis]==list(range(cfg[f"{axis}_starts"][0],cfg[f"{axis}_starts"][1]+1))
                                       for axis in ("age","calendar")), "Wrong registered window starts")
    n, width = len(baseline), cfg["window_years"]
    r45 = read_json(ROOT/"rounds/r45/results.json")["primary"]["reference_centers"][0]
    require(all(abs(float(x)-y)<1e-14 for x,y in zip(baseline,r45,strict=True)), "Brazil gap centering changed")
    with gzip.open(ROOT/cfg["grid_path"],"rt",encoding="ascii",newline="") as stream:
        rows = csv.reader(stream)
        next(rows)
        panels = {y:list(compressed_panel(rows,y,source)) for y in cfg["birth_years"]}
        require(next(rows,None) is None,"Unaccounted R41 cell")
    all_peaks = {}
    profile_count = 0
    grid_sums = {}
    for year, cells in panels.items():
        counts = sum(c[2] for c in cells)
        require(counts == reported["years"][str(year)]["official_panel_birth_count"] == cfg["cohort_counts"][str(year)],
                "Panel count differs")
        grid_sums[year] = {axis:{kind:[Fraction(0)]*len(periods) for kind in ("lower","upper","balanced")}
                           for axis,periods in axes.items()}
        all_peaks[year] = {}
        for j,(day,_,count,options) in enumerate(cells):
            z = [window_numerators(one,width,n) for pair in options for one in pair]
            profile_count += len(z)
            head = year+20+int(day.strftime("%m-%d") > "07-01")
            for axis, periods in axes.items():
                witness = reported["common"][axis]
                idx = witness["upper_assignment"][str(year)][j]
                require(0<=idx<len(z),"Illegal allocation option")
                summed_for_witness = all_peaks[year].get(axis,Fraction())
                for a,t in enumerate(periods):
                    p = a if axis=="age" else t-head
                    column = [row[p] for row in z]
                    values = grid_sums[year][axis]
                    b = baseline[p]*count
                    values["lower"][a] += Fraction(min(column)*count,n)-b
                    values["upper"][a] += Fraction(max(column)*count,n)-b
                    c = sum(value*((i+1)*count//len(z)-i*count//len(z)) for i,value in enumerate(column))
                    values["balanced"][a] += Fraction(c,n)-b
                    if t == witness["upper_axis_start"]:
                        summed_for_witness += Fraction(count*column[idx],n)-b
                all_peaks[year][axis] = summed_for_witness
        for axis, sums in grid_sums[year].items():
            source_values = reported["years"][str(year)]["window_effect_curves_pp"][axis]
            for k, array in sums.items():
                sums[k] = [x*100/counts for x in array]
                for claim, value in zip(source_values[k],sums[k],strict=True):
                    check_ratio(claim,value)
            all_peaks[year][axis] *= Fraction(100,counts)
    require(profile_count == reported["virtual_scores"],"Synthetic record count differs")
    fields = {"lower":"safe_lower_pp","upper":"sharp_upper_pp","balanced":"balanced_feasible_pp"}
    for axis, periods in axes.items():
        row = reported["common"][axis]
        for kind, field in fields.items():
            sequence = [min(g[axis][kind][i] for g in grid_sums.values()) for i in range(len(periods))]
            check_ratio(row[field],max(sequence))
            if kind=="upper":
                require(row["upper_axis_start"] == periods[sequence.index(max(sequence))],"Wrong attainable peak start")
        check_ratio(row["sharp_upper_pp"],min(r[axis] for r in all_peaks.values()))
        cut = cfg["minimum_percentage_points"]
        lo, hi, feasible = (Fraction(row[fields[k]]["exact"]) for k in ("lower","upper","balanced"))
        expected = ("excluded" if hi < cut else "supported" if lo >= cut else
                    "not_identified_two_feasible_assignments" if feasible < cut else "not_identified")
        require(row["decision"] == expected,"Wrong threshold interpretation")
    write_json(output,{"results_sha256":digest(path),"synthetic_score_inputs_checked":profile_count,
                       "independent_method":"chronological string-bit counts and fractional arithmetic",
                       "both_sharp_upper_assignments_attain_reported_values":True,
                       "both_balanced_integer_assignments_verified":True,"official_dated_counts_verified":True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "results", "output"):
        parser.add_argument("--"+key,type=Path,required=True)
    args = parser.parse_args()
    verify(args.source,args.results,args.output)
