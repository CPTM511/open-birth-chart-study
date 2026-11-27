"""Recalculate registered workplace AI usage and payroll-index contrasts."""
import argparse
from csv import DictReader
from datetime import date
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from io import TextIOWrapper
import json
from pathlib import Path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
SERIES = {
    "ever_work": "RPSGENAIUSAGESHAREWORK",
    "last_week_work": "RPSGENAIUSAGESHARELWWORK",
    "every_workday": "RPSGENAIUSAGESHAREEDLWWOR",
}
AGES = ("Early Career 1 (22-25)", "Early Career 2 (26-30)", "Developing (31-34)",
        "Mid-Career 1 (35-40)", "Mid-Career 2 (41-49)", "Senior (50+)")
EXPOSURE = ("Quintile 1 (least exposed)", "Quintile 2", "Quintile 3",
            "Quintile 4", "Quintile 5 (most exposed)")
BASELINE = "2022-11-01"
MONTHS_REPORTED = ("2021-11-01","2022-11-01","2026-06-01","2026-08-01","2026-09-01","2026-10-01")


def require(c, msg):
    if not c:
        raise ValueError(msg)


def digest(file):
    return sha256(file.read_bytes()).hexdigest()


def month_index(label):
    value = date.fromisoformat(label)
    require(value.day == 1, "Expected period start date")
    return 12*value.year+value.month


def rps(sources):
    values = {}
    for key, series in SERIES.items():
        with (sources/f"{series}.csv").open(encoding="utf8") as stream:
            source = list(DictReader(stream))
        values[key] = {x["observation_date"]:Decimal(x[series]) for x in source}
        require(len(source)==len(values[key])==9, "Unexpected RPS quarterly support")
    order = sorted(values["last_week_work"])
    require(order[0]=="2024-07-01" and order[-1]=="2026-07-01" and
            all(month_index(y)-month_index(x)==3 for x,y in zip(order,order[1:])),
            "Wrong quarter range")
    for other in values.values():
        require(sorted(other)==order, "RPS series differ in observed quarters")
    for label in order:
        require(0<=values["every_workday"][label]<=values["last_week_work"][label]<=values["ever_work"][label]<=100,
                "Reported use categories must be nested")
    result = {}
    for key,cells in values.items():
        start,end = cells[order[0]],cells[order[-1]]
        gap = end-start
        require(Fraction(end)-Fraction(start)==Fraction(gap), "Exact RPS difference failed")
        result[key]={"2024_Q3_percent":float(start),"2026_Q3_percent":float(end),"difference_pp":float(gap)}
    return {"quarters":len(order),"nested_series_quarter_checks":len(order),"source_series":SERIES,"rates":result,
            "unit":"Percent of employed respondents aged 18–64, publisher-weighted point estimates."}


def payroll(sources):
    with ZipFile(sources/"canaries_age_exposure.zip") as source:
        loaded=[]
        for name in ("canaries_age_by_exposure.csv","canaries_age_by_exposure_yoy_change.csv"):
            with TextIOWrapper(source.open(name),encoding="utf-8",newline="") as stream:
                loaded.append(list(DictReader(stream)))
    index,yoy = loaded
    months = sorted({r["observation_date"] for r in index})
    keys = {(r["observation_date"],r["exposure_quintile"]) for r in index}
    require(len(months)==60 and months[0]=="2021-11-01" and months[-1]=="2026-10-01" and
            len(keys)==len(index)==300 and keys=={(m,q) for m in months for q in EXPOSURE},
            "Incomplete public payroll panel")
    require(all(month_index(y)-month_index(x)==1 for x,y in zip(months,months[1:])),"Missing monthly period")
    require({r["vintage"] for r in index+yoy}=={"2026-11-15"}, "Unexpected payroll data vintage")
    by_key = {(r["observation_date"],r["exposure_quintile"]):[Decimal(r[a]) for a in AGES] for r in index}
    for q in EXPOSURE:
        require(all(x==100 for x in by_key[BASELINE,q]),"Payroll normalization differs")
    checked, strict_mismatches, maximum_error = 0,0,0.0
    index_radius = Fraction(1,200)
    yoy_radius = Fraction(1,200000)
    require(len(yoy)==(len(months)-12)*5 and
            {(r["observation_date"],r["exposure_quintile"]) for r in yoy}==
            {(m,q) for m in months[12:] for q in EXPOSURE},"Incomplete published year-on-year checks")
    for row in yoy:
        m,q=row["observation_date"],row["exposure_quintile"]
        last_year = f"{int(m[:4])-1}{m[4:]}"
        for age,end,start in zip(AGES,by_key[m,q],by_key[last_year,q],strict=True):
            current, prior = Fraction(end), Fraction(start)
            published = Fraction(row[age])
            expected = current/prior-1
            error = abs(float(expected-published))
            strict_mismatches += int(error>=3e-7)
            lower = (current-index_radius)/(prior+index_radius)-1
            upper = (current+index_radius)/(prior-index_radius)-1
            require(lower-yoy_radius <= published <= upper+yoy_radius,
                    "Published year-on-year rate falls outside the index display precision")
            maximum_error=max(error,maximum_error)
            checked+=1
    gaps={}
    for k,age in enumerate(AGES):
        def gap(month):
            return float(100*(Fraction(by_key[month,EXPOSURE[4]][k])/Fraction(by_key[month,EXPOSURE[0]][k])-1))
        before = gap(months[0])
        gaps[age]={"latest_least_exposed_index":float(by_key[months[-1],EXPOSURE[0]][k]),
                   "latest_most_exposed_index":float(by_key[months[-1],EXPOSURE[4]][k]),
                   "gap_percent_at_prespecified_months":{m:gap(m) for m in MONTHS_REPORTED},
                   "pre_nov_2022_gap_change_pp":gap(BASELINE)-before}
    young,mid = (gaps[AGES[k]]["gap_percent_at_prespecified_months"][months[-1]] for k in (0,4))
    return {"observation_months":len(months),"vintage":"2026-11-15","baseline":BASELINE,"ages":gaps,
            "latest_22_25_minus_41_49_gap_pp":young-mid,"yoy_cells_checked":checked,
            "max_absolute_yoy_point_residual":maximum_error,"original_tolerance_exceedances":strict_mismatches,
            "display_index_rounding_radius_points":float(index_radius),
            "display_yoy_rounding_radius_fraction":float(yoy_radius),
            "unit":"Normalized employment index within publisher's selected ADP employers."}


def run(args):
    protocol=HERE/"protocol.json"
    require(digest(protocol)==args.registration_sha256,"Use public registration hash")
    registered=json.loads(protocol.read_bytes())
    for name,expected in registered["method_sha256"].items():
        require(digest(HERE/name)==expected,"Registered method changed")
    for name,expected in registered["source_sha256"].items():
        require(digest(args.sources/name)==expected,"Official source vintage differs")
    result={"registration_sha256":args.registration_sha256,"rps":rps(args.sources),"payroll":payroll(args.sources),
            "data_linkage":False,"research_design":"Descriptive analysis of two published aggregates."}
    with args.output.open("x",encoding="utf-8") as out:
        json.dump(result,out,indent=2,allow_nan=False)
        out.write("\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--registration-sha256",required=True)
    run(parser.parse_args())
