"""Independent R10 aggregate review; no imports from primary analysis methods.

Prepared before access to R10 target scores. The numerical CDF/Fraction path is
adapted from the separate R9 verification path, with direct exact threshold
flags and protocol-driven slot rules. Internal second-agent review, not external
peer review. Require explicit coordinator AGGREGATION_READY before reading scores.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
REFERENCE_INPUT = "3d9a2dc48a26a083a20abbd372310310d13b6e93d880a4f8d1fafa02f8914f6d"
REFERENCE_PROFILES = "5bdc0d2e5c53cb15928a4a0781e5c7785085d3d039cfbf7dcc9b44f2a3f1c401"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def jsonl(path):
    with Path(path).open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def source_data(spec, slot, protocol, rule=None):
    directory = Path(spec["sample_dir"])
    manifest = json.loads((directory / "sampling_manifest.json").read_text())
    input_hash, metadata_hash = [digest(directory / name) for name in ["birth_inputs.jsonl", "birth_metadata.jsonl"]]
    assert input_hash == manifest["model_input_sha256"]
    assert metadata_hash == manifest["metadata_sha256"]
    seal_hash = None
    if slot == "reference":
        assert input_hash == REFERENCE_INPUT and manifest["sample_n"] == protocol["reference"]["records"] == 2000
        assert len(spec["profile_files"]) == 1
        assert digest(spec["profile_files"][0]) == REFERENCE_PROFILES == protocol["reference"]["profile_sha256"]
    else:
        seal_path = Path(spec.get("input_seal", ROOT / "rounds/r10/execution" / (slot + "_input_seal.json")))
        seal = json.loads(seal_path.read_text())
        assert manifest == seal["input_manifest"], "Sample manifest differs from pre-execution seal: " + slot
        seal_hash = digest(seal_path)
        assert manifest["seed"] == protocol["sampling"]["seed"]
        assert manifest["sample_n"] == min(protocol["sampling"]["n_per_slot"], manifest["eligible_frame_N"])
    births, metadata = [list(jsonl(directory / name)) for name in ["birth_inputs.jsonl", "birth_metadata.jsonl"]]
    birth_by_id, meta_by_id = [{r["study_id"]: r for r in data} for data in [births, metadata]]
    assert len(birth_by_id) == len(births) == len(meta_by_id) == len(metadata) == manifest["sample_n"]
    assert set(birth_by_id) == set(meta_by_id)
    rows = []
    for study_id in sorted(birth_by_id):
        birth, meta = birth_by_id[study_id], meta_by_id[study_id]
        for field in ["birth_local", "birth_utc", "latitude", "longitude", "source_offset_seconds"]:
            assert birth[field] == meta[field]
        sex = birth.get("sex_resolved", birth.get("sex"))
        assert sex in ["M", "F"] and sex == meta["sex"]
        assert birth.get("calendar", "").lower() == "gregorian"
        civil = datetime.fromisoformat(birth["birth_local"])
        utc = datetime.fromisoformat(birth["birth_utc"].replace("Z", "+00:00"))
        assert civil.tzinfo is None and utc.tzinfo is not None and utc.utcoffset().total_seconds() == 0
        assert abs((civil - utc.replace(tzinfo=None)).total_seconds() - birth["source_offset_seconds"]) <= 1
        assert 1880 <= civil.year <= 2025
        assert -90 < float(birth["latitude"]) < 90 and -180 <= float(birth["longitude"]) <= 180
        if rule is not None:
            assert civil.year in rule["allowed_birth_years"] and meta["birth_country"] == rule["expected_country"]
            if rule.get("source_label"):
                assert meta["source"] == rule["source_label"]
        after_july = int((civil.month, civil.day) > (7, 1))
        years = [civil.year + age + after_july for age in range(20, 60)]
        fields = {k: birth[k] for k in ["birth_local", "birth_utc", "source_offset_seconds", "latitude", "longitude"]}
        fields["sex"] = sex
        chart_hash = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        N, n = meta["N_h"], meta["n_h"]
        assert isinstance(N, int) and isinstance(n, int) and 0 < n <= N
        assert abs(float(meta["sample_weight"]) - N/n) < 1e-10
        assert abs(float(meta["inclusion_probability"]) - n/N) < 1e-12
        rows.append({"id": study_id, "source": meta["source"], "stratum": str(meta["stratum_id"]), "N": N, "n": n,
            "weight": Fraction(N, n), "years": years, "birth_year": civil.year, "chart_hash": chart_hash})
    frame = {str(s["stratum_id"]): (s["N_h"], s["n_h"]) for s in manifest["strata"]}
    assert len(frame) == len(manifest["strata"])
    counts = Counter(r["stratum"] for r in rows)
    assert set(counts) == set(frame)
    for key, (N, n) in frame.items():
        assert counts[key] == n
        assert all((r["N"], r["n"]) == (N, n) for r in rows if r["stratum"] == key)
    assert sum(N for N, n in frame.values()) == manifest["eligible_frame_N"]
    assert sum(r["weight"] for r in rows) == manifest["eligible_frame_N"]
    expected = {r["id"]: r for r in rows}
    selected, statuses = {}, Counter()
    for file in spec["profile_files"]:
        for profile in jsonl(file):
            key = profile.get("study_id")
            if key not in expected or profile.get("variant") != "base":
                continue
            assert key not in selected, "Duplicate selected profile"
            statuses[profile.get("status")] += 1
            assert profile.get("status") == "computed", "Incomplete selected trajectory"
            row = expected[key]
            assert profile["source"] == row["source"]
            assert profile["chart_input_key"] == row["chart_hash"]
            assert profile["calendar_years"] == row["years"]
            selected[key] = profile["primary_scores"]
    assert set(selected) == set(expected)
    scores = np.asarray([selected[row["id"]] for row in rows], float)
    assert scores.shape == (len(rows), 40, 4) and np.isfinite(scores).all()
    assert np.all((scores >= 0) & (scores <= 1))
    provenance = {"input_sha256": input_hash, "metadata_sha256": metadata_hash,
        "sampling_manifest_sha256": digest(directory / "sampling_manifest.json"), "input_seal_sha256": seal_hash,
        "sample_n": len(rows), "eligible_frame_N": manifest["eligible_frame_N"], "profile_status_counts": dict(statuses),
        "profile_sha256": [digest(p) for p in spec["profile_files"]], "strata": len(frame),
        "all_clock_offsets_and_40_completed_ages_checked": True}
    return rows, scores, np.array([float(r["weight"]) for r in rows]), frame, provenance


class RawSortedReference:
    """Sort every raw reference observation; do not collapse ties into bincounts."""
    def __init__(self,rows,scores):
        self.rows,self.scores=rows,scores
        self.total_frame=sum(r["weight"] for r in rows)
        self.tables={}
        weights=np.asarray([float(r["weight"]) for r in rows])
        for band in range(4):
            for system in range(4):
                raw=scores[:,band*10:band*10+10,system].ravel()
                order=np.argsort(raw,kind="stable")
                ordered_weights=np.repeat(weights,10)[order]
                self.tables[band,system]=(raw[order],np.r_[0,np.cumsum(ordered_weights)])

    def exact_value(self,band,system,x):
        numerator=Fraction(0)
        raw=self.scores[:,band*10:band*10+10,system]
        for row,values in zip(self.rows,raw):
            lower=int(np.count_nonzero(values<x))
            equal=int(np.count_nonzero(values==x))
            numerator+=row["weight"]*Fraction(2*lower+equal,2)
        return numerator/(10*self.total_frame)

    def apply(self,scores):
        q=np.empty_like(scores)
        flags=np.empty(scores.shape,dtype=bool)
        rational_threshold_checks=0
        rational_flag_corrections=0
        brute_checks=0
        max_brute_error=0.0
        for (band,system),(values,prefix) in self.tables.items():
            x=scores[:,band*10:band*10+10,system]
            left=np.searchsorted(values,x,"left")
            right=np.searchsorted(values,x,"right")
            transformed=(prefix[left]+prefix[right])/(2*prefix[-1])
            band_flags=transformed>=0.8
            near=np.unique(x[np.abs(transformed-0.8)<2e-10])
            for query in near:
                exact=self.exact_value(band,system,query)
                affected=x==query
                rational_flag_corrections+=int(np.count_nonzero((transformed[affected]>=0.8)!=(exact>=Fraction(4,5))))
                transformed[affected]=float(exact)
                band_flags[affected]=exact>=Fraction(4,5)
                rational_threshold_checks+=1
            raw_reference=self.scores[:,band*10:band*10+10,system].ravel()
            reference_weights=np.repeat([float(r["weight"]) for r in self.rows],10)
            # Fixed positions, chosen before target results: first/middle/last record and age.
            for record_index,age_index in [(0,0),(0,9),(len(scores)//2,4),(len(scores)-1,0),(len(scores)-1,9)]:
                query=x[record_index,age_index]
                brute=np.sum(reference_weights*(np.less(raw_reference,query)+0.5*np.equal(raw_reference,query)))/np.sum(reference_weights)
                difference=abs(float(transformed[record_index,age_index])-float(brute))
                max_brute_error=max(max_brute_error,difference)
                assert difference<1e-11,"Sorted-prefix CDF disagrees with selected direct sums"
                brute_checks+=1
            q[:,band*10:band*10+10,system]=transformed
            flags[:,band*10:band*10+10,system]=band_flags
        return q,flags,{"selected_direct_CDF_checks":brute_checks,"max_direct_CDF_error":max_brute_error,
            "near_threshold_exact_rational_queries":rational_threshold_checks,
            "floating_threshold_flags_corrected_by_exact_rational_comparison":rational_flag_corrections}


def stratum_weighted_mean(per_record,rows,frame):
    total=sum(N for N,n in frame.values())
    result=np.zeros(np.asarray(per_record).shape[1:])
    keys=np.asarray([r["stratum"] for r in rows])
    for key,(N,n) in sorted(frame.items()):
        result=result+(N/total)*np.mean(per_record[keys==key],axis=0)
    return result


def exact_joint_and_variance(joint_counts,rows,frame):
    total=sum(N for N,n in frame.values())
    point,variance=Fraction(0),Fraction(0)
    unavailable=[]
    for key,(N,n) in sorted(frame.items()):
        k=[int(joint_counts[i]) for i,r in enumerate(rows) if r["stratum"]==key]
        assert len(k)==n
        point+=Fraction(N,total)*Fraction(sum(k),40*n)
        if n==N:
            continue
        if n<2:
            unavailable.append(key)
            continue
        sum_squared=sum(v*v for v in k)
        unbiased=Fraction(sum_squared,1600)-Fraction(sum(k)**2,1600*n)
        unbiased/=n-1
        variance+=Fraction(N,total)**2*Fraction(N-n,N)*unbiased/n
    return float(point),None if unavailable else float(variance),unavailable


def relative_check(scores,rows,frame):
    flags=np.empty(scores.shape,bool)
    for system in range(4):
        x=scores[:,:,system]
        less=np.sum(x[:,:,None]>x[:,None,:],axis=2)
        equal=np.sum(x[:,:,None]==x[:,None,:],axis=2)
        flags[:,:,system]=(less+0.5*equal)/40>=0.8
    joint=flags.sum(axis=2)>=3
    marginal=flags.reshape(len(scores),4,10,4).mean(axis=2)
    exact=np.prod(marginal,axis=2)
    # Enumerate the four states with exactly three flags plus the all-four state.
    for absent in range(4):
        keep=[s for s in range(4) if s!=absent]
        exact+=np.prod(marginal[:,:,keep],axis=2)*(1-marginal[:,:,absent])
    return {
        "age20_59_joint_rate":float(stratum_weighted_mean(joint.mean(axis=1),rows,frame)),
        "age20_49_joint_rate":float(stratum_weighted_mean(joint[:,:30].mean(axis=1),rows,frame)),
        "age20_59_exact_independent_phase_mean":float(stratum_weighted_mean(exact.mean(axis=1),rows,frame)),
        "age20_49_exact_independent_phase_mean":float(stratum_weighted_mean(exact[:,:3].mean(axis=1),rows,frame)),
    }


def bootstrap_replay(joint_counts, rows, frame, *, seed, draws, family):
    """Independent whole-record compressed multinomial replay, using integer counts."""
    rng = np.random.default_rng(seed)
    total = sum(N for N, n in frame.values())
    replicates = np.zeros(draws)
    for key, (N, n) in sorted(frame.items()):
        values = [int(joint_counts[i]) for i, r in enumerate(rows) if r["stratum"] == key]
        center = sum(values)/(40*n)
        if N == n:
            replicates += (N/total)*center
            continue
        assert n > 1
        histogram = Counter(values)
        support = sorted(histogram)
        counts = rng.multinomial(n, [histogram[k]/n for k in support], size=draws)
        sampled_means = (counts @ (np.array(support, float)/40))/n
        adjusted = center + math.sqrt((1-n/N)*n/(n-1))*(sampled_means-center)
        replicates += (N/total)*adjusted
    alpha = .05/family
    return {"interval95": np.quantile(replicates, [.025, .975]),
        "family_adjusted_interval": np.quantile(replicates, [alpha/2, 1-alpha/2]),
        "bootstrap_variance": float(replicates.var(ddof=1))}


def calendar_and_ages(rows, flags, weights):
    joint = flags.sum(axis=2) >= 3
    years = np.array([r["years"] for r in rows])
    calendar = []
    for year in range(2026, 2071):
        who, age = np.nonzero(years == year)
        record_count = len(who)
        numerator = sum((rows[i]["weight"]*int(joint[i, a]) for i, a in zip(who, age)), Fraction(0))
        denominator = sum((rows[i]["weight"] for i in who), Fraction(0))
        calendar.append({"year": year, "eligible_source_records": record_count,
            "joint_rate": float(numerator/denominator) if denominator else None,
            "descriptive_only": True, "peak_listing_eligible": record_count >= 30})
    return {"birth_years": sorted(set(r["birth_year"] for r in rows)),
        "age20_39_joint_rate_descriptive": float(np.average(joint[:, :20].mean(axis=1), weights=weights)),
        "age20_39_calendar_range": [int(years[:, :20].min()), int(years[:, :20].max())],
        "primary_calendar_range": [int(years.min()), int(years.max())],
        "modeled_record_years_total": int(years.size),
        "modeled_record_years_within_2026_2070": int(((years >= 2026) & (years <= 2070)).sum()),
        "calendar_2026_2070": calendar}


def review(config, primary):
    protocol_path, decisions_path = Path(config["protocol"]), Path(config["source_decisions"])
    protocol = json.loads(protocol_path.read_text())
    decisions = json.loads(decisions_path.read_text())["source_slots"]
    slots = {s["id"]: s for s in protocol["source_slots"]}
    decision_map = {s["id"]: s for s in decisions}
    family = protocol["inference"]["family_size"]
    draws = protocol["inference"]["primary_draws"]
    assert len(slots) == len(protocol["source_slots"]) == family
    assert len(decision_map) == len(decisions) == family and set(decision_map) == set(slots)
    assert all(s["status"] in ["available", "unavailable"] for s in decisions)
    available = {k for k, v in decision_map.items() if v["status"] == "available"}
    unavailable = set(slots)-available
    assert not any(slots[k]["status"] == "unavailable" for k in available)
    assert all(decision_map[k].get("reason") for k in unavailable)
    assert len(config["targets"]) == len({s["slot"] for s in config["targets"]})
    assert {s["slot"] for s in config["targets"]} == available
    assert len(primary["targets"]) == len({t["slot"] for t in primary["targets"]})
    assert {t["slot"] for t in primary["targets"]} == available
    assert {s["slot"] for s in primary["unavailable_slots"]} == unavailable
    assert primary["protocol_sha256"] == digest(protocol_path)
    assert primary["source_decisions_sha256"] == digest(decisions_path)
    assert primary["primary_family_size"] == family and primary["primary_draws"] == draws
    assert primary["no_real_world_null_pvalues"] is True
    for path, expected in primary["code_sha256"].items():
        assert digest(ROOT/path) == expected, "Reported analysis code changed: " + path
    comparisons = []
    def compare(label, actual, reported, tolerance=1e-11):
        a, b = np.asarray(actual, float), np.asarray(reported, float)
        assert a.shape == b.shape, "Comparison shape mismatch: " + label
        assert np.isfinite(a).all() and np.isfinite(b).all()
        error = float(np.max(np.abs(a-b))) if a.size else 0.
        comparisons.append({"label": label, "max_abs_error": error, "tolerance": tolerance, "pass": error <= tolerance})
    rr, rs, rw, rf, rp = source_data(config["reference"], "reference", protocol)
    cdf = RawSortedReference(rr, rs)
    rq, rflags, rdiag = cdf.apply(rs)
    rJ, _, _ = exact_joint_and_variance((rflags.sum(axis=2) >= 3).sum(axis=1), rr, rf)
    reference_raw = stratum_weighted_mean(rs.mean(axis=1), rr, rf)
    compare("reference.J", rJ, primary["reference"]["joint_rate"])
    compare("reference.raw_means", reference_raw, primary["reference"]["raw_system_means"])
    compare("reference.mid_CDF_mean_half", stratum_weighted_mean(rq.mean(axis=1), rr, rf), [.5]*4)

    def check_description(label, rows, scores, q, flags, weights, frame, reported):
        relative = relative_check(scores, rows, frame)
        for key, value in relative.items():
            compare(label+".relative."+key, value, reported["relative_alignment"][key])
        description = calendar_and_ages(rows, flags, weights)
        for key, value in description.items():
            if key == "calendar_2026_2070":
                assert len(reported[key]) == len(value)
                for a, b in zip(value, reported[key]):
                    for field in ["year", "eligible_source_records", "descriptive_only", "peak_listing_eligible"]:
                        assert a[field] == b[field], label+".calendar."+field
                    if a["joint_rate"] is None:
                        assert b["joint_rate"] is None
                    else:
                        compare(label+".calendar_"+str(a["year"]), a["joint_rate"], b["joint_rate"])
            elif key == "age20_39_joint_rate_descriptive":
                compare(label+"."+key, value, reported[key])
            else:
                assert value == reported[key], label+"."+key
    check_description("reference", rr, rs, rq, rflags, rw, rf, primary["reference"])
    reviewed = []
    reported_by_slot = {t["slot"]: t for t in primary["targets"]}
    for spec in config["targets"]:
        slot = spec["slot"]
        rule = dict(slots[slot])
        if not rule.get("source_label") and decision_map[slot].get("source_label"):
            rule["source_label"] = decision_map[slot]["source_label"]
        rows, scores, weights, frame, prov = source_data(spec, slot, protocol, rule)
        target = reported_by_slot[slot]
        assert target["n_source_records"] == len(rows)
        for key in ["input_sha256", "metadata_sha256", "sampling_manifest_sha256", "sample_n", "eligible_frame_N"]:
            assert target["provenance"][key] == prov[key]
        assert target["provenance"]["complete_profiles"] == len(rows)
        assert [p["sha256"] for p in target["provenance"]["profile_files"]] == prov["profile_sha256"]
        q, flags, diag = cdf.apply(scores)
        joint = flags.sum(axis=2) >= 3
        counts = joint.sum(axis=1)
        j, variance, singleton = exact_joint_and_variance(counts, rows, frame)
        raw = stratum_weighted_mean(scores.mean(axis=1), rows, frame)
        level = stratum_weighted_mean(q.mean(axis=1), rows, frame)
        metrics = {"joint_rate": j, "delta_joint_rate": j-rJ, "reference_joint_rate": rJ,
            "raw_system_means": raw, "delta_raw_system_means": raw-reference_raw,
            "fixed_reference_system_means": level, "delta_fixed_reference_system_means": level-.5,
            "delta_L": level.mean()-.5,
            "age_band_joint_rates": [stratum_weighted_mean(joint[:, i*10:i*10+10].mean(axis=1), rows, frame) for i in range(4)]}
        for key, value in metrics.items():
            compare(slot+"."+key, value, target[key])
        interval = target["sampling_interval"]
        assert interval["seed"] == rule["primary_bootstrap_seed"] and interval["draws"] == draws
        assert interval["family_size_including_unavailable_slots"] == family
        compare(slot+".interval_point", j, interval["point"])
        if singleton:
            assert interval["status"] == "unavailable"
        else:
            assert interval["status"] == "computed_assumption_conditional"
            compare(slot+".exact_Fraction_design_variance", variance, interval["analytic_design_variance"], 1e-14)
            replay = bootstrap_replay(counts, rows, frame, seed=rule["primary_bootstrap_seed"], draws=draws, family=family)
            for key, value in replay.items():
                compare(slot+".bootstrap_replay."+key, value, interval[key], 1e-12 if "interval" in key else 1e-14)
            compare(slot+".delta_interval95", replay["interval95"]-rJ, interval["delta_joint_interval95"])
            compare(slot+".delta_family_interval", replay["family_adjusted_interval"]-rJ, interval["delta_joint_family_adjusted_interval"])
            compare(slot+".Bonferroni_marginal_coverage", 1-.05/family, interval["family_adjusted_marginal_coverage"])
        check_description(slot, rows, scores, q, flags, weights, frame, target)
        reviewed.append({"slot": slot, "provenance": prov, "CDF_diagnostics": diag, "independent_joint_rate": j,
            "independent_delta_joint_rate": j-rJ, "independent_analytic_design_variance": variance,
            "unweighted_joint_record_years": int(joint.sum()), "all_40_age_points_verified": True,
            "all_45_calendar_entries_checked": True, "primary_bootstrap_replayed": not bool(singleton)})
    sensitivity = primary["reference_refit_sensitivity"]
    if sensitivity["status"] == "computed_exploratory_sensitivity":
        spec = protocol["reference_stability_sensitivity"]
        assert sensitivity["draws"] == spec["draws"] and sensitivity["reference_seed"] == spec["seed"]
        order = {s["id"]: i for i, s in enumerate(protocol["source_slots"])}
        assert sensitivity["reference_draw_shared_across_targets"] and sensitivity["reference_CDF_refitted_each_draw"]
        for result in sensitivity["targets"]:
            slot = result["slot"]
            assert sensitivity["target_seeds"][slot] == spec["seed"]+1+order[slot]
            compare(slot+".refit_fixed_point", result["point_delta_joint_rate"], reported_by_slot[slot]["delta_joint_rate"])
    failed = [c for c in comparisons if not c["pass"]]
    return {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "passed" if not failed else "mismatch",
        "review_scope": "Internal second-agent review; sorted raw-value CDF, direct selected sums, exact Fraction(N_h,n_h) threshold/variance arithmetic and independent primary bootstrap replay. No imports from primary methods; not external peer review.",
        "not_reviewed": ["full reference-refit Monte Carlo distribution not replayed", "birth-record truth beyond sealed inputs", "traditional-rule predictive validity", "mortality or AI outcomes"],
        "reference": {"provenance": rp, "CDF_diagnostics": rdiag, "independent_joint_rate": rJ},
        "targets": reviewed, "unavailable_slots": sorted(unavailable), "family_size_retained": family,
        "comparisons": comparisons, "comparison_count": len(comparisons), "failure_count": len(failed),
        "max_aggregate_absolute_error": max((x["max_abs_error"] for x in comparisons), default=0.)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--primary-result", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--aggregation-ready", action="store_true")
    args = p.parse_args()
    if not args.aggregation_ready:
        raise SystemExit("Do not read target scores before coordinator AGGREGATION_READY")
    output = Path(args.output)
    if output.exists():
        raise FileExistsError("Preserve prior review; choose a new output path")
    config, primary = [json.loads(Path(x).read_text()) for x in [args.config, args.primary_result]]
    assert primary["analysis_config_sha256"] == digest(args.config)
    result = review(config, primary)
    result["input_hashes"] = {"config": digest(args.config), "primary_result": digest(args.primary_result), "verification_code": digest(__file__)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k: result[k] for k in ["status", "comparison_count", "failure_count", "max_aggregate_absolute_error"]}))
    if result["failure_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
