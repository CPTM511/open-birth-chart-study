"""Compute the R46 age-gap tests on independent, fixed-size holdouts."""

import argparse
from fractions import Fraction
from pathlib import Path
from statistics import NormalDist

import numpy as np

from rounds.r45.analyze import alternate_flags, clock_changes
from rounds.r45.common import fractions
from rounds.r45.estimate import (Layout, describe, design_vectors, intervals, weight_means, windows)
from precision_reference import PrecisionReference

from .common import GROUPS, REGISTRATION, ROOT, private, protocol, read_json, require, write_json
from .read_profiles import load_inputs

FAMILIES = {
    "p75_recorded": GROUPS,
    "p80_recorded": ("br2009","mx2009"),
    "p80_hour": ("br2009","mx2009"),
}


def layout(cfg):
    return Layout(range(cfg["window_starts"][0],cfg["window_starts"][1]+1),range(0),cfg["window_width"])


def decide(lower,upper,interest):
    if lower > interest:
        return "supported"
    if upper < interest:
        return "excluded"
    return "unresolved"


def prior_selection(cfg, ages):
    prior = read_json(ROOT/"rounds/r45/results.json")
    coverage = prior["input_coverage"]
    z = NormalDist().inv_cdf(1-cfg["one_sided_alpha"])
    out = {}
    for label, rule in cfg["primary"].items():
        stage = prior[rule["upper_witness_prior"]]
        eligibles = rule["upper_witness_groups"]
        estimates = {g:np.array(stage["groups"][g]["effect_curve"][:len(ages)]) for g in eligibles}
        errors = {g:np.array(stage["groups"][g]["conditional_standard_error"][:len(ages)])
                  * np.sqrt(coverage[g]["sample_n"]/cfg["sampling"]["sample_n"]) for g in eligibles}
        selections = [min(eligibles,key=lambda g:(estimates[g][i]+z*errors[g][i],g)) for i in range(len(ages))]
        lower = stage["peaks"]["age_gap"][rule["prior_subset"]]["start"]
        require(lower in ages,"The fixed lower-bound window is unavailable")
        out[label] = {"groups_by_age":selections,"lower_bound_start_age":lower,"z":z}
    return out


def directional(curves,errors,witness,ages,interest):
    z = witness["z"]
    chosen = witness["groups_by_age"]
    require(len(chosen)==len(ages),"Invalid registered age witnesses")
    upper_curve = [curves[g][i]+z*errors[g][i] for i,g in enumerate(chosen)]
    lower_idx = ages.index(witness["lower_bound_start_age"])
    lower = float(min(curves[g][lower_idx]-z*errors[g][lower_idx] for g in curves))
    upper = float(max(upper_curve))
    common = np.array(list(curves.values())).min(axis=0)
    p = int(np.flatnonzero(common >= common.max()-1e-14)[0])
    require(lower<=float(common[p])+1e-14 and upper>=float(common[p])-1e-14, "Invalid test interval")
    return {"start_age":ages[p],"point":float(common[p]),"interval":[lower,upper],"threshold":interest,
            "decision":decide(lower,upper,interest),"upper_attaining_age":ages[upper_curve.index(upper)],
            "preselected_witnesses":witness}


def family_band(curves,margins,ages,interest):
    values = np.asarray(list(curves.values()))
    margins = np.asarray([margins[g] for g in curves])
    joint = values.min(axis=0)
    p = int(np.flatnonzero(joint>=max(joint)-1e-14)[0])
    lo = float(np.max(np.min(values-margins,axis=0)))
    hi = float(np.max(np.min(values+margins,axis=0)))
    return {"start_age":ages[p],"point":float(joint[p]),"simultaneous_interval":[lo,hi],
            "threshold":interest,"decision":decide(lo,hi,interest)}


def bundle_estimates(reference,models,cfg):
    window = layout(cfg)
    cutoff = cfg["minimum_systems"]
    fixed = PrecisionReference(reference.scores,reference.weights,fractions(reference.rows))
    q75 = Fraction(*cfg["primary"]["four_p75"]["threshold_percentile"])
    q80 = Fraction(*cfg["primary"]["born_2009_p80_hour"]["threshold_percentile"])
    require(q80==Fraction(4,5), "R10 precision reference uses the 80th percentile")
    ref_flags = {"p75_recorded":alternate_flags(reference.scores,fixed,reference,q75),
                 "p80_recorded":fixed.flags(reference.scores)}
    ref_flags["p80_hour"] = ref_flags["p80_recorded"]
    family_data, records, centers, all_flags = {}, {}, {}, {}
    for branch, groups in FAMILIES.items():
        ref_joint = ref_flags[branch].sum(axis=2)>=cutoff
        ref_window = windows(ref_joint,window)
        centers[branch] = weight_means(ref_window.gap,reference.weights)
        family_data[branch], all_flags[branch] = {}, {}
        for group in groups:
            model = models[group]
            cohort = model.original
            score = model.hourly if branch=="p80_hour" else cohort.scores
            flags = (alternate_flags(score,fixed,reference,q75) if branch=="p75_recorded" else fixed.flags(score))
            joint = flags.sum(axis=2)>=cutoff
            all_flags[branch][group] = joint
            win = windows(joint,window)
            residual = win.gap-centers[branch]
            records[group] = cohort.rows
            curve = weight_means(residual,cohort.weights)
            summary = dict(describe(joint,win,cohort.weights),effect_curve=curve.tolist())
            family_data[branch][group] = summary,residual
    combined, slices = {}, {}
    for group, rows in records.items():
        matrices = []
        start = 0
        for family, sub in family_data.items():
            if group not in sub:
                continue
            mat = sub[group][1]
            matrices.append(mat)
            slices[family,group] = slice(start,start+mat.shape[1])
            start += mat.shape[1]
        vector, singleton = design_vectors(np.column_stack(matrices),rows,np.full(start,2.))
        require(not singleton.any(),"Unexpected noncensused singleton stratum in R46")
        combined[group] = vector,singleton
    critical, error, margin = intervals(combined,cfg["simultaneous_bands"])
    published, values, uncertainty = {}, {}, {}
    for key, family in family_data.items():
        parts, estimates, se, widths = {}, {}, {}, {}
        for group,(description,_) in family.items():
            pos = slices[key,group]
            estimates[group], se[group], widths[group] = (np.array(description["effect_curve"]),
                                                          error[group][pos],margin[group][pos])
            parts[group] = dict(description,conditional_standard_error=se[group].tolist(),
                                simultaneous_margin=widths[group].tolist())
        sets = {"all_groups":list(parts)}
        if key=="p75_recorded":
            sets.update(born_1999=["br1999","mx1999"],born_2009=["br2009","mx2009"])
        out = {}
        for label, group_set in sets.items():
            out[label] = family_band({g:estimates[g] for g in group_set},{g:widths[g] for g in group_set},
                                     window.ages,cfg["gap_threshold"])
        published[key] = dict(groups=parts,peaks=out)
        values[key], uncertainty[key] = estimates,se
    settings = prior_selection(cfg,window.ages)
    main = {name:directional(values[key],uncertainty[key],settings[name],window.ages,cfg["gap_threshold"])
            for name,key in (("four_p75","p75_recorded"),("born_2009_p80_hour","p80_hour"))}
    clocks = {g:clock_changes(all_flags["p80_recorded"][g],all_flags["p80_hour"][g],models[g].original.weights)
              for g in FAMILIES["p80_hour"]}
    return dict(critical=float(critical),families=published,primary=main,paired_hour_clock=clocks,
                reference_center={k:x.tolist() for k,x in centers.items()})


def calibration(cfg):
    window = layout(cfg)
    reference = np.random.default_rng(46028).random((2000,40))<0.12
    ref_center = windows(reference,window).gap.mean(axis=0)
    result = {}
    for name, witness in prior_selection(cfg,window.ages).items():
        groups = cfg["primary"][name]["groups"]
        launch, width = witness["lower_bound_start_age"]-window.ages.start,window.width
        injected = reference.copy()
        injected[:800,launch:launch+width] = False
        summaries = {}
        for label,data in (("matched_negative",reference),("injected",injected)):
            curve = windows(data,window).gap.mean(axis=0)-ref_center
            fake = {group:curve for group in groups}
            noise = {group:np.zeros(len(curve)) for group in groups}
            summaries[label] = directional(fake,noise,witness,window.ages,cfg["gap_threshold"])
        require(summaries["matched_negative"]["decision"]=="excluded"
                and abs(summaries["matched_negative"]["point"])<1e-13
                and summaries["injected"]["start_age"]==witness["lower_bound_start_age"]
                and summaries["injected"]["decision"]=="supported", "R46 calibration failed")
        result[name] = summaries
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("job","r10-job","output"):
        parser.add_argument("--"+key,type=Path,required=True)
    args = parser.parse_args()
    cfg = protocol()
    checks = calibration(cfg)
    reference, models = load_inputs(private(args.job),args.r10_job,cfg)
    result = bundle_estimates(reference,models,cfg)
    write_json(args.output,dict(registration=REGISTRATION,age_starts=list(layout(cfg).ages),**result,
                                coverage={g:x.evidence for g,x in models.items()},calibration=checks))


if __name__ == "__main__":
    main()
