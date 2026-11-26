"""Independent R9 aggregate code path; never imports the primary methods.

Use only after the coordinator explicitly authorizes AGGREGATION_READY. This
checks deterministic arithmetic and sampling-variance formulas, not predictive
validity. The methods author also authored this alternative code path: it is
an internal algorithmic cross-check, not independent external peer review.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
REFERENCE_INPUT = "3d9a2dc48a26a083a20abbd372310310d13b6e93d880a4f8d1fafa02f8914f6d"
REFERENCE_PROFILES = "5bdc0d2e5c53cb15928a4a0781e5c7785085d3d039cfbf7dcc9b44f2a3f1c401"
SEEDS = {"mexico2015":2026112711,"brazil2016":2026112713}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()


def jsonl(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def source_data(spec,slot):
    directory=Path(spec["sample_dir"])
    manifest=json.loads((directory/"sampling_manifest.json").read_text())
    input_hash=digest(directory/"birth_inputs.jsonl")
    metadata_hash=digest(directory/"birth_metadata.jsonl")
    assert input_hash==manifest["model_input_sha256"], "Source input hash differs from manifest"
    assert metadata_hash==manifest["metadata_sha256"], "Metadata hash differs from manifest"
    if slot=="reference":
        assert input_hash==REFERENCE_INPUT and manifest["sample_n"]==2000
        assert len(spec["profile_files"])==1 and digest(spec["profile_files"][0])==REFERENCE_PROFILES
    else:
        seal=json.loads((ROOT/"rounds"/"r9"/"execution"/(slot+"_input_seal.json")).read_text())
        assert manifest==seal["input_manifest"], "Sample manifest differs from pre-execution seal"
        assert input_hash==seal["input_manifest"]["model_input_sha256"]
    births=list(jsonl(directory/"birth_inputs.jsonl"))
    metadata=list(jsonl(directory/"birth_metadata.jsonl"))
    birth_by_id={r["study_id"]:r for r in births}
    meta_by_id={r["study_id"]:r for r in metadata}
    assert len(birth_by_id)==len(births)==len(meta_by_id)==len(metadata)==manifest["sample_n"]
    assert set(birth_by_id)==set(meta_by_id)
    ids=sorted(birth_by_id)
    rows=[]
    for study_id in ids:
        birth,meta=birth_by_id[study_id],meta_by_id[study_id]
        for field in ["birth_local","birth_utc","latitude","longitude","source_offset_seconds"]:
            assert birth[field]==meta[field], "Input-metadata mismatch"
        sex=birth.get("sex_resolved",birth.get("sex"))
        assert sex in ["M","F"] and sex==meta["sex"]
        assert birth.get("calendar","").lower()=="gregorian"
        civil=datetime.fromisoformat(birth["birth_local"])
        utc=datetime.fromisoformat(birth["birth_utc"].replace("Z","+00:00"))
        assert civil.tzinfo is None and utc.tzinfo is not None
        assert abs((civil-utc.replace(tzinfo=None)).total_seconds()-birth["source_offset_seconds"])<=1
        if slot=="mexico2015":
            assert civil.year==2015 and meta["birth_country"]=="MX"
        elif slot=="brazil2016":
            assert civil.year==2016 and meta["birth_country"]=="BR"
        after_july=(civil.month,civil.day)>(7,1)
        years=[civil.year+age+int(after_july) for age in range(20,60)]
        chart_fields={k:birth[k] for k in ["birth_local","birth_utc","source_offset_seconds","latitude","longitude"]}
        chart_fields["sex"]=sex
        chart_hash=hashlib.sha256(json.dumps(chart_fields,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        N,n=meta["N_h"],meta["n_h"]
        assert isinstance(N,int) and isinstance(n,int) and 0<n<=N
        assert abs(float(meta["sample_weight"])-N/n)<1e-10
        assert abs(float(meta["inclusion_probability"])-n/N)<1e-12
        rows.append({"id":study_id,"source":meta["source"],"stratum":meta["stratum_id"],"N":N,"n":n,
            "weight":Fraction(N,n),"years":years,"chart_hash":chart_hash})
    frame={s["stratum_id"]:(s["N_h"],s["n_h"]) for s in manifest["strata"]}
    counts=Counter(r["stratum"] for r in rows)
    assert set(counts)==set(frame)
    for key,(N,n) in frame.items():
        assert counts[key]==n
        assert all((r["N"],r["n"])==(N,n) for r in rows if r["stratum"]==key)
    assert sum(N for N,n in frame.values())==manifest["eligible_frame_N"]
    assert sum(r["weight"] for r in rows)==manifest["eligible_frame_N"]
    expected={r["id"]:r for r in rows}
    selected={}
    statuses=Counter()
    for file in spec["profile_files"]:
        for profile in jsonl(file):
            key=profile.get("study_id")
            if key not in expected or profile.get("variant")!="base":
                continue
            assert key not in selected,"Duplicate selected profile"
            statuses[profile.get("status")]+=1
            assert profile.get("status")=="computed","Incomplete selected profile"
            row=expected[key]
            assert profile["source"]==row["source"]
            assert profile["chart_input_key"]==row["chart_hash"]
            assert profile["calendar_years"]==row["years"]
            selected[key]=profile["primary_scores"]
    assert set(selected)==set(ids),"Incomplete source profile coverage"
    scores=np.asarray([selected[k] for k in ids],float)
    assert scores.shape==(len(ids),40,4) and np.isfinite(scores).all()
    assert np.all((scores>=0)&(scores<=1))
    weights=np.asarray([float(r["weight"]) for r in rows])
    provenance={"input_sha256":input_hash,"metadata_sha256":metadata_hash,"sample_n":len(rows),
        "eligible_frame_N":manifest["eligible_frame_N"],"profile_status_counts":dict(statuses),
        "profile_sha256":[digest(p) for p in spec["profile_files"]],
        "strata":len(frame),"all_clock_offsets_and_40_completed_ages_checked":True}
    return rows,scores,weights,frame,provenance


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
        rational_threshold_checks=0
        rational_flag_corrections=0
        brute_checks=0
        max_brute_error=0.0
        for (band,system),(values,prefix) in self.tables.items():
            x=scores[:,band*10:band*10+10,system]
            left=np.searchsorted(values,x,"left")
            right=np.searchsorted(values,x,"right")
            transformed=(prefix[left]+prefix[right])/(2*prefix[-1])
            near=np.unique(x[np.abs(transformed-0.8)<2e-10])
            for query in near:
                exact=self.exact_value(band,system,query)
                affected=x==query
                rational_flag_corrections+=int(np.count_nonzero((transformed[affected]>=0.8)!=(exact>=Fraction(4,5))))
                transformed[affected]=float(exact)
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
        return q,{"selected_direct_CDF_checks":brute_checks,"max_direct_CDF_error":max_brute_error,
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


def review(config,primary):
    comparisons=[]
    warnings=[]
    def compare(label,actual,reported,tolerance=1e-11):
        delta=np.asarray(actual,float)-np.asarray(reported,float)
        error=float(np.max(np.abs(delta))) if delta.size else 0.0
        comparisons.append({"label":label,"max_abs_error":error,"tolerance":tolerance,"pass":error<=tolerance})
    seal=json.loads((ROOT/"rounds/r9/methods/methods_implementation_seal.json").read_text())
    for name,expected_hash in seal["files"].items():
        assert digest(ROOT/"rounds/r9/methods"/name)==expected_hash,"Sealed methods artifact changed: "+name
    for name,expected_hash in primary["code_sha256"].items():
        assert digest(ROOT/"rounds/r9/methods"/name)==expected_hash
    rr,rs,rw,rf,rp=source_data(config["reference"],"reference")
    reference=RawSortedReference(rr,rs)
    rq,reference_diagnostics=reference.apply(rs)
    reference_joint=(np.sum(rq>=0.8,axis=2)>=3)
    rJ,rV,rUnavailable=exact_joint_and_variance(reference_joint.sum(axis=1),rr,rf)
    reference_raw=stratum_weighted_mean(rs.mean(axis=1),rr,rf)
    compare("reference.J",rJ,primary["reference"]["joint_rate"])
    compare("reference.mid_CDF_mean_half",stratum_weighted_mean(rq.mean(axis=1),rr,rf),[0.5]*4)
    compare("reference.raw_means",reference_raw,primary["reference"]["raw_system_means"])
    rrelative=relative_check(rs,rr,rf)
    for key,value in rrelative.items():
        compare("reference.relative."+key,value,primary["reference"]["relative_alignment"][key])
    targets=[]
    by_slot={r["slot"]:r for r in primary["targets"]}
    assert len(by_slot)==len(primary["targets"])==len(config["targets"])
    assert primary["primary_family_size"]==3 and primary["no_real_world_null_pvalues"] is True
    unavailable={r["slot"] for r in primary["unavailable_slots"]}
    assert "earlier_brazil" in unavailable or "early_brazil" in unavailable
    if "earlier_brazil" in unavailable:
        warnings.append("Unavailable-slot alias: unified protocol uses early_brazil; methods output uses earlier_brazil. Both denote the same unavailable 1996/2001 slot; family size remains three.")
    for specification in config["targets"]:
        slot=specification["slot"]
        reported=by_slot[slot]
        rows,scores,weights,frame,prov=source_data(specification,slot)
        assert len(rows)==reported["n_source_records"]==2000
        for key in ["input_sha256","metadata_sha256","sample_n","eligible_frame_N"]:
            assert reported["provenance"][key]==prov[key]
        assert reported["provenance"]["complete_profiles"]==2000
        q,diagnostics=reference.apply(scores)
        joint=np.sum(q>=0.8,axis=2)>=3
        j,variance,unavailable_variance=exact_joint_and_variance(joint.sum(axis=1),rows,frame)
        raw=stratum_weighted_mean(scores.mean(axis=1),rows,frame)
        level=stratum_weighted_mean(q.mean(axis=1),rows,frame)
        compare(slot+".J",j,reported["joint_rate"])
        compare(slot+".DeltaJ",j-rJ,reported["delta_joint_rate"])
        compare(slot+".raw_means",raw,reported["raw_system_means"])
        compare(slot+".delta_raw_means",raw-reference_raw,reported["delta_raw_system_means"])
        compare(slot+".fixed_levels",level,reported["fixed_reference_system_means"])
        compare(slot+".delta_levels",level-0.5,reported["delta_fixed_reference_system_means"])
        compare(slot+".DeltaL",np.mean(level)-0.5,reported["delta_L"])
        for band in range(4):
            actual=stratum_weighted_mean(joint[:,band*10:band*10+10].mean(axis=1),rows,frame)
            compare(slot+".age_band_"+str(band),actual,reported["age_band_joint_rates"][band])
        relative=relative_check(scores,rows,frame)
        for key,value in relative.items():
            compare(slot+".relative."+key,value,reported["relative_alignment"][key])
        interval=reported["sampling_interval"]
        assert interval["seed"]==SEEDS[slot] and interval["draws"]==1999
        assert interval["family_size_including_unavailable_slots"]==3
        compare(slot+".interval_point",j,interval["point"])
        if unavailable_variance:
            assert interval["status"]=="unavailable"
        else:
            assert interval["status"]=="computed_assumption_conditional"
            compare(slot+".exact_Fraction_design_variance",variance,interval["analytic_design_variance"],tolerance=1e-14)
            lo,hi=interval["family_adjusted_interval"]
            l95,h95=interval["interval95"]
            assert lo<=l95<=h95<=hi
            compare(slot+".adjusted_delta_endpoints",np.array([lo,hi])-rJ,interval["delta_joint_family_adjusted_interval"])
            compare(slot+".ordinary_delta_endpoints",np.array([l95,h95])-rJ,interval["delta_joint_interval95"])
            compare(slot+".Bonferroni_marginal_coverage",1-0.05/3,interval["family_adjusted_marginal_coverage"])
        years=np.asarray([r["years"] for r in rows])
        annual=reported["calendar_2026_2070"]
        assert [a["year"] for a in annual]==list(range(2026,2071))
        for entry in annual:
            selected=(years==entry["year"])
            who,age=np.nonzero(selected)
            assert entry["eligible_source_records"]==len(who)
            assert entry["descriptive_only"] is True and entry["peak_listing_eligible"]==(len(who)>=30)
            if len(who)==0:
                assert entry["joint_rate"] is None
            else:
                point=float(sum(weights[i]*int(joint[i,a]) for i,a in zip(who,age))/sum(weights[who]))
                compare(slot+".calendar_"+str(entry["year"]),point,entry["joint_rate"])
        targets.append({"slot":slot,"provenance":prov,"CDF_diagnostics":diagnostics,
            "independent_joint_rate":j,"independent_delta_joint_rate":j-rJ,
            "independent_analytic_design_variance":variance,"unweighted_joint_record_years":int(joint.sum()),
            "all_40_age_points_verified":True,"all_45_calendar_display_entries_checked":True})
    failures=[r for r in comparisons if not r["pass"]]
    return {
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "status":"passed" if not failures else "mismatch",
        "review_scope":"Independent code path using raw-observation sorting, direct selected sums and exact Fraction stratum arithmetic. Same project methods author; not external peer review.",
        "not_reviewed":["bootstrap random-quantile tails were not replayed","birth source truth beyond frozen input/hash/interface checks","traditional rule validity","mortality or AI outcomes"],
        "reference":{"provenance":rp,"CDF_diagnostics":reference_diagnostics,"independent_joint_rate":rJ},
        "targets":targets,"comparisons":comparisons,"comparison_count":len(comparisons),
        "failure_count":len(failures),"max_aggregate_absolute_error":max((r["max_abs_error"] for r in comparisons),default=0),
        "warnings":warnings,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--config",required=True)
    parser.add_argument("--primary-result",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--aggregation-ready",action="store_true",help="Coordinator explicitly released the aggregate-review gate")
    args=parser.parse_args()
    if not args.aggregation_ready:
        raise SystemExit("Do not read target scores before coordinator AGGREGATION_READY")
    config=json.loads(Path(args.config).read_text())
    primary=json.loads(Path(args.primary_result).read_text())
    assert primary["analysis_config_sha256"]==digest(args.config)
    result=review(config,primary)
    result["input_hashes"]={"config":digest(args.config),"primary_result":digest(args.primary_result),"verification_code":digest(__file__)}
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"comparisons":result["comparison_count"],"failures":result["failure_count"],"max_error":result["max_aggregate_absolute_error"],"warnings":result["warnings"]}))
    if result["failure_count"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
