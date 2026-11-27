"""Compare the registered Linux estimator to a row-index resampling replay."""
import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from brazil_1999 import checked_sample, load_profiles, PrecisionReference, read, registered, require
from analyze import frame_bootstrap
from fixed_reference import rescaled_stratum_bootstrap


def replay(args):
    protocol = registered(args)
    sample = checked_sample(args, protocol)
    _, _, scores, weights, strata, frame, _ = load_profiles(
        sample,[args.job/"profiles/baseline_profiles.jsonl"])
    rr, _, ref, ref_w, *_ = load_profiles(args.r10_job/"reference/brazil2006",
        [args.r10_job/"reference/full-frozen-r8-baseline_profiles.jsonl"])
    reference = PrecisionReference(ref,ref_w,[Fraction(r["N_h"],r["n_h"]) for r in rr])
    flags=reference.flags(scores)
    hit_counts=(flags.sum(axis=2)>=3).sum(axis=1)
    point, draws, variance = frame_bootstrap(hit_counts,strata,frame,
        seed=protocol["bootstrap_seed"],draws=protocol["bootstrap_draws"])
    r = read(args.job/"results.json")
    require(abs(point-r["joint_rate"])<2e-13 and abs(variance-r["analytic_design_variance"])<2e-13,
            "Whole-record repeat calculation differs from the original point/variance")
    generator=np.random.default_rng(protocol["bootstrap_seed"])
    frequency_fingerprint=sha256()
    for group,n in sorted(frame.items()):
        replicate,_=rescaled_stratum_bootstrap(hit_counts[strata==group]/40,n,9999,generator)
        frequency_fingerprint.update(replicate.astype("<f8").tobytes())
    result={"threshold_flags_sha256":sha256(flags.tobytes()).hexdigest(),
            "whole_record_counts_sha256":sha256(hit_counts.astype("<i8").tobytes()).hexdigest(),
            "independent_index_replay_95_diff":np.quantile(draws-reference.joint_rate,[.025,.975]).tolist(),
            "registered_frequency_resampling_fingerprint":frequency_fingerprint.hexdigest()}
    with args.output.open("x",encoding="utf-8") as out:
        json.dump(result,out,indent=2,allow_nan=False)
        out.write("\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("job","r10-job","output"):
        p.add_argument("--"+name,type=Path,required=True)
    for name in ("registration-sha256","input-sha256"):
        p.add_argument("--"+name,required=True)
    replay(p.parse_args())
