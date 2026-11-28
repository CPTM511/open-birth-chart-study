"""Independently recompute R46 fractional effects and shared-record errors."""

import argparse
from fractions import Fraction
from math import ceil, sqrt
from pathlib import Path

import numpy as np
from scipy.special import ndtri

from rounds.r27.verify import weighted_rank_tables
from rounds.r45.common import fractions
from rounds.r45.review import (centered, check_equal, classify_exact, demographics,
                               exact_mean_columns, integral_weights, points, spread)

from .common import GROUPS, REGISTRATION, ROOT, digest, private, protocol, read_json, require, write_json
from .read_profiles import load_inputs


def decisions(lo,hi,threshold):
    if hi<threshold:
        return "excluded"
    if lo>threshold:
        return "supported"
    return "unresolved"


def selection_from_published_prior(cfg, settings, ages):
    z = float(ndtri(1-cfg["one_sided_alpha"]))
    j = read_json(ROOT/"rounds/r45/results.json")
    prior = j[settings["upper_witness_prior"]]
    choices = []
    for i in range(len(ages)):
        candidates = []
        for group in settings["upper_witness_groups"]:
            estimates = prior["groups"][group]
            prior_sample = j["input_coverage"][group]["sample_n"]
            expected_width = estimates["conditional_standard_error"][i]*sqrt(prior_sample/cfg["sampling"]["sample_n"])
            candidates.append((estimates["effect_curve"][i]+z*expected_width,group))
        choices.append(sorted(candidates)[0][1])
    lower = prior["peaks"]["age_gap"][settings["prior_subset"]]["start"]
    return choices,lower,z


def verify_primary(out, exact, se, cfg, ages):
    mapping = {"four_p75":"p75_recorded","born_2009_p80_hour":"p80_hour"}
    for name,definition in cfg["primary"].items():
        family = mapping[name]
        result = out[name]
        choices, lower_age, z = selection_from_published_prior(cfg,definition,ages)
        expected = result["preselected_witnesses"]
        require(expected["groups_by_age"]==choices and expected["lower_bound_start_age"]==lower_age,
                "Published R45 cohorts were not used to pick age witnesses")
        check_equal(z,expected["z"],"Single-tail critical value")
        age_index = ages.index(lower_age)
        upper = [(float(exact[family][g][i])+z*se[family][g][i]) for i,g in enumerate(choices)]
        lower = min(float(exact[family][g][age_index])-z*se[family][g][age_index] for g in definition["groups"])
        check_equal(result["interval"],[lower,max(upper)],"Unresolved/excluded interval")
        require(result["decision"]==decisions(lower,max(upper),cfg["gap_threshold"])
                and result["upper_attaining_age"]==ages[upper.index(max(upper))],"Wrong directional bound decision")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("job","r10-job","results","output"):
        p.add_argument("--"+key,required=True,type=Path)
    args = p.parse_args()
    cfg = protocol()
    actual = read_json(args.results)
    require(actual["registration"]==REGISTRATION,"Wrong registration")
    ages = actual["age_starts"]
    rules = cfg["simultaneous_bands"]
    require(ages==list(range(cfg["window_starts"][0],cfg["window_starts"][1]+1)),"Wrong age starts")
    ref, models = load_inputs(private(args.job),args.r10_job,cfg)
    require(actual["coverage"]=={g:c.evidence for g,c in models.items()},"Released score-seal evidence differs")
    ranked = weighted_rank_tables(ref.scores,fractions(ref.rows))
    w_ref = integral_weights(ref.rows)
    matrices = {g:[] for g in GROUPS}
    flags, exact, reference_centers = {}, {}, {}
    largest_error = 0.
    classifications = 0
    for family in ("p75_recorded","p80_recorded","p80_hour"):
        cutoff = Fraction(3,4) if family=="p75_recorded" else Fraction(4,5)
        ref_flags = classify_exact(ref.scores,ranked,cutoff)
        _,_,basin = points(ref_flags,cfg["minimum_systems"],cfg["window_width"])
        baseline = exact_mean_columns(centered(basin),w_ref,len(ages))
        check_equal(baseline,actual["reference_center"][family],"R46 fixed reference")
        reference_centers[family] = list(baseline)
        classifications += ref_flags.size
        exact[family],flags[family] = {},{}
        members = GROUPS if family=="p75_recorded" else ("br2009","mx2009")
        require(set(members)==set(actual["families"][family]["groups"]),"Unexpected group endpoint")
        for group in members:
            model = models[group]
            arrays = model.hourly if family=="p80_hour" else model.original.scores
            independently_high = classify_exact(arrays,ranked,cutoff)
            classifications += independently_high.size
            report = actual["families"][family]["groups"][group]
            joint,counts,no_hits = points(independently_high,cfg["minimum_systems"],cfg["window_width"])
            weights = integral_weights(model.original.rows)
            demographics(report,joint,counts,no_hits,weights,cfg["window_width"])
            raw = centered(no_hits)
            exact[family][group] = [value-anchor for value,anchor in zip(
                exact_mean_columns(raw,weights,len(ages)),baseline,strict=True)]
            error = check_equal(exact[family][group],report["effect_curve"],"Weighted shape curve")
            largest_error = max(largest_error,error)
            flags[family][group] = joint
            independent_matrix = [[Fraction(x,len(ages))-anchor for x,anchor in zip(row,baseline,strict=True)]
                                  for row in raw]
            matrices[group].append((family,np.asarray(independent_matrix,dtype=float)))
    std = {family:{} for family in exact}
    draws = rules["normal_draws"]
    extreme = np.zeros(draws)
    for g,(group,arrays) in enumerate(matrices.items()):
        values = np.column_stack([matrix for _,matrix in arrays])
        se, maxima, uncovered = spread(values,models[group].original.rows,draws,rules["normal_seed"]+g)
        require(uncovered==0,"Unexpected singleton uncertainty")
        extreme = np.maximum(extreme,maxima)
        for k,(family,_) in enumerate(arrays):
            current = se[k*len(ages):(k+1)*len(ages)]
            std[family][group] = current
            check_equal(current,actual["families"][family]["groups"][group]["conditional_standard_error"],
                        "Finite population correction")
    q = sorted(extreme)[ceil((draws-1)*rules["confidence"])]
    check_equal(q,actual["critical"],"Shared-record simultaneous critical value")
    for family,groups in exact.items():
        margins = {g:std[family][g]*q for g in groups}
        for group,value in margins.items():
            check_equal(value,actual["families"][family]["groups"][group]["simultaneous_margin"],
                        "Simultaneous band margin")
        for name,test in actual["families"][family]["peaks"].items():
            listed = list(groups) if name=="all_groups" else [g for g in groups if g.endswith(name[-4:])]
            curve = [min(groups[g][i] for g in listed) for i in range(len(ages))]
            lows = [min(float(groups[g][i])-margins[g][i] for g in listed) for i in range(len(ages))]
            ups = [min(float(groups[g][i])+margins[g][i] for g in listed) for i in range(len(ages))]
            require(test["start_age"]==ages[curve.index(max(curve))],"Age of common maximum differs")
            check_equal(test["point"],max(curve),"Maximum common effect")
            check_equal(test["simultaneous_interval"],[max(lows),max(ups)],"Projected common effect")
            require(test["decision"]==decisions(max(lows),max(ups),cfg["gap_threshold"]),"Wrong projected band decision")
    verify_primary(actual["primary"],exact,std,cfg,ages)
    for group,report in actual["paired_hour_clock"].items():
        a,b = (flags[k][group] for k in ("p80_recorded","p80_hour"))
        W = integral_weights(models[group].original.rows)
        w_total = sum(W)
        reversals = a!=b
        affected = sum(w*bool(x) for w,x in zip(W,reversals.any(axis=1),strict=True))
        flipped = sum(w*int(x) for w,x in zip(W,reversals.sum(axis=1),strict=True))
        net = sum(w*int(x) for w,x in zip(W,b.sum(axis=1)-a.sum(axis=1),strict=True))
        check_equal([report["record_year_reversal_rate"],report["records_with_at_least_one_reversal"],
                    report["mean_joint_rate_change"]],
                    [Fraction(flipped,40*w_total),Fraction(affected,w_total),Fraction(net,40*w_total)],
                    "Paired clock outcomes")
    write_json(args.output,{"registration":REGISTRATION,"results_sha256":digest(args.results),
                           "direct_integer_threshold_classifications":int(classifications),
                           "maximum_exact_effect_disagreement":largest_error,
                           "joint_multiplier_draws_recomputed":draws,"critical_value":float(q),
                           "methods":"Integer prefix ranks and per-record windows, Fraction weights, separate covariance",
                           "applies_to_both_preregistered_primary_decisions":True})


if __name__=="__main__":
    main()
