"""Record the publisher-library and almanac comparison for the registered premises."""
import argparse
from hashlib import sha256
import json
from math import remainder
import os
from pathlib import Path
from statistics import fmean
import subprocess

import swisseph as swe

from classical import ZIWEI_STEMS, ziwei_text_transformations
from open_birth_chart import astronomy, qizheng_engine as qizheng

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
NODE = """
const path = require("node:path");
const iztro = require(path.join(process.argv[1], "iztro"));
if (iztro.version !== "2.6.5") throw Error("Use the frozen Iztro library");
iztro.astro.setLanguage("zh-CN");
const stems = "甲乙丙丁戊己庚辛壬癸".split("");
console.log(JSON.stringify(stems.map(s => iztro.util.getMutagensByHeavenlyStem(s))));
"""


def apogee_comparison(path):
    source = json.loads(path.read_bytes())
    records = []
    for days, quadruple in source["transcription_rows"]:
        mansion, degree, minute = quadruple[0]
        jd = source["jd_ut"] + days
        target = (qizheng.mansion_boundaries(jd)[qizheng.MANSION_NAMES.index(mansion)] + degree + minute/60) % 360
        interpolated, flags = swe.calc_ut(jd, swe.INTP_APOG, astronomy.FLAGS)
        positions = {"mean": astronomy.position(jd,"MeanApogee")["longitude"],
                     "osculating": astronomy.position(jd,"OsculatingApogee")["longitude"],
                     "interpolated": interpolated[0] % 360}
        records.append({"days_from_almanac_epoch":days,"target_longitude_deg":target,
            "interpolated_returned_flags":flags,
            "signed_error_arcmin":{name:60*remainder(lon-target,360) for name,lon in positions.items()}})
    metrics = {}
    for name in records[0]["signed_error_arcmin"]:
        values = [abs(x["signed_error_arcmin"][name]) for x in records]
        metrics[name] = {"mean_absolute_error_arcmin":fmean(values),"max_absolute_error_arcmin":max(values)}
    return {"edition":source["title"],"observations":records,"summary":metrics,"parameters_fit":0,
            "target_longitude_convention":source["interpretation"],
            "scope":"R8 historical time and mansion conversion used for three defined modern lunar apogees."}


def run(args):
    use = HERE/"protocol.json"
    def digest(path): return sha256(path.read_bytes()).hexdigest()
    if digest(use) != args.registration_sha256:
        raise ValueError("Use the published R16 registration")
    declaration = json.loads(use.read_bytes())
    for name, expected in declaration["files_sha256"].items():
        if digest(ROOT/name) != expected:
            raise ValueError("Registered file differs: "+name)
    value = subprocess.check_output(["node","-e",NODE,os.getenv("OBS_NODE_MODULES",str(ROOT/"node_modules"))],text=True)
    published = json.loads(value)
    differences = []
    for stem, library in zip(ZIWEI_STEMS,published,strict=True):
        for transform, text, engine in zip(("禄","权","科","忌"),
            ziwei_text_transformations(stem).values(),library,strict=True):
            if text != engine:
                differences.append({"natal_stem":stem,"transformation":transform,"classical":text,"pinned_library":engine})
    result={"registration_sha256":args.registration_sha256,"pyswisseph":swe.__version__,
            "ziwei":{"natal_stems":len(published),"cells":sum(map(len,published)),"difference_cells":differences,
                     "hua_ji_identical_by_stem":all(x["transformation"]!="忌" for x in differences)},
            "yuebo":apogee_comparison(ROOT/"docs/engine_validation/1833_reference.json"),
            "cohort_scores_used":False,"observed_outcomes_used":False}
    with args.output.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registration-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    run(p.parse_args())
