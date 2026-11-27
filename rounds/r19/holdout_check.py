"""Replay the pre-sealed R19 months 5–12 almanac transcription."""
import argparse
from hashlib import sha256
import json
from math import remainder
from pathlib import Path
from statistics import fmean

from open_birth_chart import astronomy, qizheng_engine as qizheng
import qing_apogee as qing

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def digest(p):
    return sha256(p.read_bytes()).hexdigest()


def run(args):
    spec=HERE/"holdout_protocol.json"
    if digest(spec)!=args.registration_sha256:
        raise ValueError("The study requires the GitHub-verified holdout registration")
    cfg=json.loads(spec.read_bytes())
    for name,h in cfg["files_sha256"].items():
        if digest(ROOT/name)!=h:
            raise ValueError("R19 holdout source or method differs: "+name)
    holdout=json.loads((HERE/"p41_transcription.json").read_bytes())
    basis=json.loads((ROOT/"docs/engine_validation/1833_reference.json").read_bytes())
    days_lengths=holdout["lunar_month_lengths"]
    if len(days_lengths)!=12 or sum(days_lengths)!=354:
        raise ValueError("Invalid table's twelve months")
    rows=[]
    for month, day, mansion, degree, minute in holdout["observations"]:
        day_number=sum(days_lengths[:month-1])+day-1
        jd=basis["jd_ut"]+day_number
        first=qing.calculate(*qing.source_angles(jd))
        other=qing.calculate(*qing.source_angles(jd), solar_maximum_arcsec=6913)
        points={"qing_average_corrected":first["highest_in_use_deg"],
                "qing_historical_mean":first["historical_mean_deg"],
                "qing_full_6973":first["highest_true_deg"],
                "qing_full_6913":other["highest_true_deg"],
                "modern_mean":astronomy.position(jd,"MeanApogee")["longitude"]}
        target=(qizheng.mansion_boundaries(jd)[qizheng.MANSION_NAMES.index(mansion)]+degree+minute/60)%360
        errors={}
        for key,candidate in points.items():
            diff=abs(candidate-target)%360
            dev=60*remainder(candidate-target,360)
            if abs(abs(dev)-60*min(diff,360-diff))>1e-10:
                raise ValueError("Independent angular distance check failed")
            errors[key]=dev
        rows.append({"lunar_month":month,"lunar_day":day,"epoch_days":day_number,
                     "printed_mansion":mansion,"printed_degree":degree,"printed_arcminute":minute,
                     "interpolated_target_deg":target,"signed_error_arcmin":errors})
    if len(rows)!=24 or set((r["lunar_month"],r["lunar_day"]) for r in rows)!={(m,d) for m in range(5,13) for d in (1,11,21)}:
        raise ValueError("The complete presealed period is required")
    summary={}
    for name in rows[0]["signed_error_arcmin"]:
        values=[abs(r["signed_error_arcmin"][name]) for r in rows]
        summary[name]={"mean_absolute_error_arcmin":fmean(values),
                       "maximum_absolute_error_arcmin":max(values),
                       "within_one_arcmin":sum(v<=1 for v in values)}
    with args.output.open("x",encoding="utf8") as out:
        json.dump({"registration_sha256":args.registration_sha256,"new_dates":24,
                   "threshold_passed":summary["qing_average_corrected"]["within_one_arcmin"]>=23,
                   "source":"Same 1833 printed edition, unused months 5 to 12",
                   "rows":rows,"summary":summary},out,ensure_ascii=False,indent=2,allow_nan=False)
        out.write("\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registration-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    run(p.parse_args())
