"""Compare the historical model and its unadjusted mean with the 1833 almanac."""
import argparse
from hashlib import sha256
import json
from math import remainder
from pathlib import Path
from statistics import fmean

from open_birth_chart import astronomy, qizheng_engine as qizheng
import qing_apogee as qing

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def main(args):
    protocol=HERE/"protocol.json"
    def digest(p): return sha256(p.read_bytes()).hexdigest()
    if digest(protocol)!=args.registration_sha256:
        raise ValueError("Use the GitHub-verified protocol hash")
    cfg=json.loads(protocol.read_bytes())
    for name,h in cfg["files_sha256"].items():
        if digest(ROOT/name)!=h:
            raise ValueError("Frozen inputs changed: "+name)
    original=json.loads((ROOT/"docs/engine_validation/1833_reference.json").read_bytes())
    results=[]
    keys=("modern_mean","qing_mean","qing_with_annual_correction","qing_full_6973","qing_full_6913")
    for day,observations in original["transcription_rows"]:
        jd=original["jd_ut"]+day
        mansion,degree,minute=observations[0]
        target=(qizheng.mansion_boundaries(jd)[qizheng.MANSION_NAMES.index(mansion)]+degree+minute/60)%360
        model=qing.source_angles(jd)
        main=qing.calculate(*model)
        alternate=qing.calculate(*model,solar_maximum_arcsec=6913)
        ds=(astronomy.position(jd,"MeanApogee")["longitude"],
            main["historical_mean_deg"],main["highest_in_use_deg"],main["highest_true_deg"],
            alternate["highest_true_deg"])
        errors={k:60*remainder(v-target,360) for k,v in zip(keys,ds,strict=True)}
        results.append({"days_after_almanac_epoch":day,"target_deg":target,
                        "signed_error_arcmin":errors,
                        "traditional_steps_main":main,
                        "absolute_6913_vs_6973_arcmin":abs(remainder(ds[-1]-ds[-2],360))*60})
    summary={}
    for k in keys:
        errors=[abs(r["signed_error_arcmin"][k]) for r in results]
        summary[k]={"mean_absolute_error_arcmin":fmean(errors),
                    "maximum_absolute_error_arcmin":max(errors),
                    "passes_registered_60_arcmin_max_gate":max(errors)<=60}
    report={"registration_sha256":args.registration_sha256,"version":qing.VERSION,
            "registered_historical_gate_arcmin":60,"free_parameters_fit":0,"observations":results,
            "solar_maximum_reading_difference_max_arcmin":max(r["absolute_6913_vs_6973_arcmin"] for r in results),
            "scope":"Comparison under the registered modern time and mansion conversion from 1833, no cohort inputs.",
            "summaries":summary}
    with args.output.open("x",encoding="utf8") as out:
        json.dump(report,out,ensure_ascii=False,indent=2,allow_nan=False)
        out.write("\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registration-sha256",required=True)
    p.add_argument("--output",required=True,type=Path)
    main(p.parse_args())
