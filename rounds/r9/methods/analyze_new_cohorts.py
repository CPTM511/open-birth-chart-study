"""Apply the frozen R9 structural estimator to completed profile JSONL files.

This script does not calculate charts, read death outcomes, choose sample sizes,
or estimate an AI/civilization-event probability. See PROTOCOL_SUPPLEMENT.md.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import sys
import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
from open_birth_chart.io import load_source, jsonlines, sha256
from fixed_reference import FixedReference, conditional_frame_interval, joint_record_rates

REFERENCE_INPUT_SHA256 = "3d9a2dc48a26a083a20abbd372310310d13b6e93d880a4f8d1fafa02f8914f6d"
SLOT_SEEDS = {"mexico2015":2026112711, "earlier_brazil":2026112712, "brazil2016":2026112713}


def load_profiles(sample_directory, profile_files):
    rows, manifest = load_source(sample_directory)
    by_id = {row["study_id"]:row for row in rows}
    profiles = {}
    seen_selected = 0
    for file in profile_files:
        for profile in jsonlines(file):
            if profile.get("variant") != "base" or profile.get("study_id") not in by_id:
                continue
            key = profile["study_id"]
            seen_selected += 1
            if key in profiles:
                raise ValueError("Duplicate base profile for a sampled study record")
            if profile.get("status") != "computed":
                raise ValueError("Sample contains uncomputed profiles; handle exclusions explicitly before analysis")
            expected = by_id[key]
            for field in ["source", "chart_input_key", "calendar_years"]:
                if profile.get(field) != expected[field]:
                    raise ValueError("Profile-input mismatch in " + field)
            profiles[key] = profile
    if set(profiles) != set(by_id):
        raise ValueError(f"Incomplete selected-profile coverage: {len(profiles)} of {len(by_id)}")
    scores = np.asarray([profiles[row["study_id"]]["primary_scores"] for row in rows], dtype=float)
    if scores.shape != (len(rows),40,4) or not np.isfinite(scores).all():
        raise ValueError("Selected profiles must be complete finite (n,40,4) arrays")
    weights = np.asarray([row["sample_weight"] for row in rows], float)
    strata = np.asarray([row["stratum_id"] for row in rows], str)
    frame_counts = {s["stratum_id"]:s["N_h"] for s in manifest["strata"]}
    observed_counts = Counter(strata)
    for row in rows:
        if observed_counts[row["stratum_id"]] != row["n_h"]:
            raise ValueError("Actual sampled stratum size differs from declared n_h")
    provenance = {
        "input_sha256":manifest["model_input_sha256"],
        "metadata_sha256":manifest["metadata_sha256"],
        "sampling_manifest_sha256":sha256(Path(sample_directory)/"sampling_manifest.json"),
        "profile_files":[{"name":Path(p).name,"sha256":sha256(p)} for p in profile_files],
        "source_labels":sorted(set(row["source"] for row in rows)),
        "sample_n":len(rows),"eligible_frame_N":manifest["eligible_frame_N"],
        "complete_profiles":seen_selected,
    }
    return rows, manifest, scores, weights, strata, frame_counts, provenance


def r8_relative_continuity(scores, weights):
    from scipy.stats import rankdata
    q = (rankdata(scores, axis=1, method="average")-0.5)/40
    flags = q >= 0.8
    joint = flags.sum(axis=2) >= 3
    probabilities = flags.reshape(len(scores),4,10,4).mean(axis=2)
    exact = np.zeros((len(scores),4))
    for triple in itertools.combinations(range(4),3):
        exact += np.prod(probabilities[:,:,triple],axis=2)
    exact -= 3*np.prod(probabilities,axis=2)
    return {
        "kind":"R8 within-person relative alignment; descriptive continuity, no new p values",
        "age20_59_joint_rate":float(np.average(joint.mean(axis=1),weights=weights)),
        "age20_49_joint_rate":float(np.average(joint[:,:30].mean(axis=1),weights=weights)),
        "age20_59_exact_independent_phase_mean":float(np.average(exact.mean(axis=1),weights=weights)),
        "age20_49_exact_independent_phase_mean":float(np.average(exact[:,:3].mean(axis=1),weights=weights)),
    }


def calendar_view(rows, q, weights):
    joint = np.sum(q>=0.8,axis=2)>=3
    calendar = np.asarray([r["calendar_years"] for r in rows], int)
    result = []
    for year in range(2026,2071):
        present = calendar == year
        who, age = np.nonzero(present)
        count = len(who)
        result.append({"year":year,"eligible_source_records":count,
            "joint_rate":None if count==0 else float(np.average(joint[who,age],weights=weights[who])),
            "descriptive_only":True,"peak_listing_eligible":count>=30})
    return result


def analyze(config):
    ref_config = config["reference"]
    rr, rm, rs, rw, rstr, rcounts, rprov = load_profiles(ref_config["sample_dir"],ref_config["profile_files"])
    if rm["model_input_sha256"] != REFERENCE_INPUT_SHA256 or len(rr)!=2000:
        raise ValueError("Reference must be the frozen 2,000-record R8 Brazil 2006 sample")
    if set(r["source"] for r in rr)!={"SINASC-2006"}:
        raise ValueError("Reference source label mismatch")
    ref = FixedReference(rs,rw)
    reference_summary = ref.summarize(rs,rw)
    reference_summary.update({"provenance":rprov,"relative_alignment":r8_relative_continuity(rs,rw),
        "fixed_reference_cdf_support_sizes":{f"band{b}_system{s}":len(cdf.values) for (b,s),cdf in ref.cdfs.items()},
        "calendar_2026_2070":calendar_view(rr,ref.transform(rs),rw)})
    out = {
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "analysis":"R9 frozen-reference structural contrasts",
        "reference":reference_summary,
        "primary_family_size":3,
        "unavailable_slots":[{"slot":"earlier_brazil","reason":"Brazil 1996 and the single permitted fallback 2001 lack birth-clock field HORANASC"}],
        "targets":[],
        "primary_age_window":"40 completed ages 20–59; calendar view alone is clipped to 2026–2070",
        "no_real_world_null_pvalues":True,
        "interpretation":"Structural contrasts conditional on the specified models and source frames. No mortality, AI-event, civilization-event or global-population inference.",
    }
    seen=set()
    for target in config["targets"]:
        slot=target["slot"]
        if slot not in SLOT_SEEDS or slot=="earlier_brazil" or slot in seen:
            raise ValueError("Unavailable, duplicate or unregistered target slot")
        seen.add(slot)
        rows, manifest, scores, weights, strata, counts, prov = load_profiles(target["sample_dir"],target["profile_files"])
        if len(rows)>2000:
            raise ValueError("Precommitted target sample cap exceeded")
        result=ref.summarize(scores,weights)
        q=ref.transform(scores)
        interval=conditional_frame_interval(joint_record_rates(q),strata,counts,seed=SLOT_SEEDS[slot],draws=1999,family_size=3)
        if abs(interval["point"]-result["joint_rate"])>2e-13:
            raise ArithmeticError("Stratum and direct source-weight estimators differ")
        if interval["status"]!="unavailable":
            interval["delta_joint_interval95"]=[v-ref.joint_rate for v in interval["interval95"]]
            interval["delta_joint_family_adjusted_interval"]=[v-ref.joint_rate for v in interval["family_adjusted_interval"]]
        result.update({"slot":slot,"provenance":prov,"sampling_interval":interval,
            "relative_alignment":r8_relative_continuity(scores,weights),
            "calendar_2026_2070":calendar_view(rows,q,weights)})
        out["targets"].append(result)
    for slot in ["mexico2015","brazil2016"]:
        if slot not in seen:
            out["unavailable_slots"].append({"slot":slot,"reason":"Not supplied to this analysis invocation; not estimated"})
    directory=Path(__file__).parent
    out["code_sha256"]={f:sha256(directory/f) for f in ["fixed_reference.py","analyze_new_cohorts.py","PROTOCOL_SUPPLEMENT.md"]}
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--config",required=True,help="JSON containing reference{sample_dir,profile_files} and targets[{slot,sample_dir,profile_files}]")
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_text())
    result=analyze(config)
    result["analysis_config_sha256"]=sha256(args.config)
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"output":str(output),"reference_records":result["reference"]["n_source_records"],
        "target_records":[t["n_source_records"] for t in result["targets"]],
        "unavailable_slots":result["unavailable_slots"]}))


if __name__=="__main__":
    main()
