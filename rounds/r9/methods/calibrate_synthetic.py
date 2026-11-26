"""Conditional finite-frame calibration; synthetic profiles are not human data."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np

from fixed_reference import FixedReference, conditional_frame_interval, joint_record_rates
from verify_math import run_checks

BASE_SEED = 2026112710
SAMPLING_SEED = 2026112720
N_REFERENCE = 2000
N_FRAME = 20000
N_SAMPLE = 2000
REPETITIONS = 200
DRAWS = 1999
FAMILY_SIZE = 3
COHORTS = [2001, 2015, 2016]  # first is a synthetic placeholder, not an available real cohort


def wilson(count, n):
    z = 1.959963984540054
    p = count / n
    denominator = 1 + z*z/n
    center = (p + z*z/(2*n)) / denominator
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return [center-half, center+half]


def calendar_path(rng):
    years = np.arange(2020, 2077)
    innovations = rng.normal(0, 0.2, len(years))
    correlated = np.zeros(len(years))
    for i in range(1, len(years)):
        correlated[i] = 0.8 * correlated[i-1] + innovations[i]
    factor = np.sin(2*np.pi*years/12) + 0.4*np.sin(2*np.pi*years/20) + correlated
    return dict(zip(years.tolist(), factor.tolist()))


def generate_scores(rng, n, birth_year, calendar, loading):
    ages = np.arange(20, 60)
    common_calendar = np.array([calendar[int(birth_year+a)] for a in ages])
    strata = np.repeat([-1.0, 1.0], n//2)
    person_common = rng.normal(0, 0.35, (n,1,1))
    person_system = rng.normal(0, 0.25, (n,1,4))
    age_common = rng.normal(0, 0.35, (n,40,1))
    for a in range(1,40):
        age_common[:,a] = 0.65*age_common[:,a-1] + age_common[:,a]
    noise = rng.normal(0, 0.8, (n,40,4))
    linear = (person_common + person_system + age_common + noise
              + loading*common_calendar[None,:,None]*np.array([1.0,0.8,1.2,0.9])[None,None,:]
              + strata[:,None,None]*0.12 + np.array([-0.25,-0.05,0.1,0.25])[None,None,:])
    scores = 1/(1+np.exp(-linear))
    # Coarse channels deliberately exercise the ties present in two R8 indices.
    scores[:,:,0] = np.round(scores[:,:,0]*8)/8
    scores[:,:,1] = np.round(scores[:,:,1]*2)/2
    return scores


def positive_joint_control(q, rng):
    before = np.sum(q >= 0.8, axis=2) >= 3
    after = before.copy()
    total_to_change = int(round(before.size*0.01))
    remaining = total_to_change
    changed_by_age = {}
    for age_index in list(range(20,40)) + list(range(20)):
        candidates = np.flatnonzero(~after[:,age_index])
        take = min(remaining, len(candidates))
        if take:
            chosen = rng.choice(candidates, take, replace=False)
            # Identical to setting all four q values to .99 in these cells.
            after[chosen,age_index] = True
            changed_by_age[str(age_index+20)] = int(take)
            remaining -= take
        if not remaining:
            break
    if remaining:
        raise ArithmeticError("Synthetic frame has insufficient nonjoint cells for fixed injection")
    delta = float(after.mean()-before.mean())
    if abs(delta-0.01)>1e-13:
        raise ArithmeticError("Joint positive-control magnitude differs from frozen 0.01")
    return after.mean(axis=1), {"delta_joint_truth":delta,"changed_record_years":total_to_change,"completed_age_counts":changed_by_age}


def sample_indices(rng):
    half_frame, half_sample = N_FRAME//2, N_SAMPLE//2
    return np.r_[rng.choice(half_frame,half_sample,replace=False),
                 half_frame+rng.choice(half_frame,half_sample,replace=False)]


def calibrate_family(name, loading, scenario_index):
    generator = np.random.default_rng(BASE_SEED+scenario_index)
    calendar = calendar_path(generator)
    reference_scores = generate_scores(generator,N_REFERENCE,2006,calendar,loading)
    reference = FixedReference(reference_scores,np.ones(N_REFERENCE))
    frame_values, positive_values, truths, positives, control_records = [], [], [], [], []
    for birth_year in COHORTS:
        raw = generate_scores(generator,N_FRAME,birth_year,calendar,loading)
        q = reference.transform(raw)
        j = joint_record_rates(q)
        j_positive, injection = positive_joint_control(q,generator)
        old_level = float(q.mean())
        lam = 0.05/(1-old_level)
        if lam>1:
            raise ArithmeticError("Fixed level injection cannot remain bounded")
        raised = q + lam*(1-q)
        level_change = float(raised.mean()-old_level)
        if abs(level_change-0.05)>1e-13 or np.any((raised<0)|(raised>1)):
            raise ArithmeticError("Fixed level injection failed")
        frame_values.append(j)
        positive_values.append(j_positive)
        truths.append(float(j.mean()))
        positives.append(float(j_positive.mean()))
        control_records.append({"synthetic_birth_year":birth_year, "baseline_joint_truth":float(j.mean()),
            "baseline_contrast_truth":float(j.mean()-reference.joint_rate),
            "positive_joint_truth":float(j_positive.mean()),"level_injection_delta":level_change,
            "level_injection_lambda":lam, **injection})
        del raw,q,raised

    null_misses = np.zeros((REPETITIONS,FAMILY_SIZE),bool)
    positive_detections = np.zeros((REPETITIONS,FAMILY_SIZE),bool)
    widths, variance_ratios = [], []
    labels = np.repeat(["A","B"],N_SAMPLE//2)
    counts = {"A":N_FRAME//2,"B":N_FRAME//2}
    sample_rng = np.random.default_rng(SAMPLING_SEED+scenario_index)
    for repetition in range(REPETITIONS):
        for slot in range(FAMILY_SIZE):
            indices = sample_indices(sample_rng)
            bseed = SAMPLING_SEED+scenario_index*100000+repetition*10+slot
            null = conditional_frame_interval(frame_values[slot][indices],labels,counts,seed=bseed,draws=DRAWS,family_size=FAMILY_SIZE)
            lo,hi = null["family_adjusted_interval"]
            null_misses[repetition,slot] = not (lo<=truths[slot]<=hi)
            widths.append(hi-lo)
            if null["analytic_design_variance"]>0:
                variance_ratios.append(null["bootstrap_variance"]/null["analytic_design_variance"])
            positive = conditional_frame_interval(positive_values[slot][indices],labels,counts,
                seed=bseed+5000000,draws=DRAWS,family_size=FAMILY_SIZE)
            positive_detections[repetition,slot] = positive["family_adjusted_interval"][0]>truths[slot]
        if (repetition+1)%50==0:
            print(json.dumps({"scenario":name,"repetitions_completed":repetition+1}),flush=True)
    family_count = int(null_misses.any(axis=1).sum())
    return {
        "name":name,"calendar_loading":loading,"reference_joint_rate":reference.joint_rate,
        "finite_frame_controls":control_records,
        "null_family_misses":family_count,"null_family_error_estimate":family_count/REPETITIONS,
        "null_family_error_wilson95":wilson(family_count,REPETITIONS),
        "null_slot_misses":null_misses.sum(axis=0).tolist(),
        "positive_detection_counts":positive_detections.sum(axis=0).tolist(),
        "positive_power_estimates":positive_detections.mean(axis=0).tolist(),
        "positive_power_wilson95":[wilson(int(c),REPETITIONS) for c in positive_detections.sum(axis=0)],
        "mean_adjusted_interval_width":float(np.mean(widths)),
        "mean_bootstrap_to_analytic_variance_ratio":float(np.mean(variance_ratios)),
        "calendar_path_sha256":hashlib.sha256(json.dumps(calendar,sort_keys=True).encode()).hexdigest(),
    }


def main():
    started=time.monotonic()
    math_checks=run_checks()
    scenarios=[]
    for i,(name,loading) in enumerate([("predominantly_individual",0.15),("shared_calendar",0.8)]):
        scenarios.append(calibrate_family(name,loading,i))
    # This is a diagnostic report, not a forced power or guaranteed-coverage gate.
    out={
        "analysis":"synthetic finite-frame whole-record bootstrap calibration",
        "real_R9_chart_results_inspected":False,
        "math_checks":math_checks,
        "design":{"reference_n":N_REFERENCE,"target_frame_n":N_FRAME,"target_sample_n":N_SAMPLE,
            "strata":2,"repetitions":REPETITIONS,"bootstrap_draws":DRAWS,"family_size":FAMILY_SIZE,
            "synthetic_cohorts":COHORTS,"generator_seed":BASE_SEED,"sampling_seed":SAMPLING_SEED,
            "positive_joint_effect":0.01,"positive_level_effect":0.05},
        "scenarios":scenarios,
        "runtime_seconds":round(time.monotonic()-started,3),
        "interpretation":"Conditional calibration for stated synthetic finite populations, fixed reference and correct stratified sampling. Shared calendar paths are held fixed; no world, mortality or AI null is tested. Actual R9 has two eligible slots and one unavailable slot; synthetic calibration exercises all three slots conservatively.",
        "limitations":["Monte Carlo uncertainty with 200 repetitions","synthetic generator is not empirically validated","reference-estimation uncertainty excluded","no guarantee of coverage under source selection or clock/model error"],
    }
    directory=Path(__file__).parent
    out["code_sha256"]={f:hashlib.sha256((directory/f).read_bytes()).hexdigest() for f in ["fixed_reference.py","verify_math.py","calibrate_synthetic.py","PROTOCOL_SUPPLEMENT.md"]}
    (directory/"synthetic_calibration.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({"done":True,"runtime_seconds":out["runtime_seconds"],"summary":[{"name":s["name"],"family_error":s["null_family_error_estimate"],"power":s["positive_power_estimates"]} for s in scenarios]}),flush=True)


if __name__=="__main__":
    main()
