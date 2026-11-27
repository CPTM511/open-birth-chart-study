"""Audit, seal and compare the official SINASC 1999 birth-only frame."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
R10 = ROOT / "rounds/r10"
sys.path[:0] = [str(ROOT / name) for name in (
    "rounds/r9/data", "rounds/r10/methods", "rounds/r10/verification", "rounds/r12")]
import build_brazil as legacy
from analyze_cohorts import load_profiles
from fixed_reference import conditional_frame_interval
from prepare_samples import allocate
from precision_reference import PrecisionReference
from r10_io import load_source, sha256 as digest
from verify_aggregates import RawSortedReference

YEAR = 1999
SOURCE = "SINASC-1999"
SEED = "OBS-R15-BR-1999"


def require(predicate, message):
    if not predicate:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open("x", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, allow_nan=False, indent=2)
        out.write("\n")


def audit_source(archive, refs, report, retain=False):
    clock_pattern = Counter()
    per_state = defaultdict(Counter)
    ledger = {name: Counter() for name in ("counts", "invalid_fields_nonexclusive", "excluded",
                                           "minute_mod5", "eligible_strata")}
    counts, exclusions = ledger["counts"], ledger["excluded"]
    eligible_clock = Counter()
    candidates = defaultdict(list)
    for index, (d, t, sex, place) in legacy.raw_rows(archive):
        counts["raw_rows"] += 1
        born = legacy.r8.brazil_date(d)
        place_valid = len(place) == 7 and place.isascii() and place.isdigit()
        state = place[:2] if place_valid else "invalid"
        per_state[state]["source_rows"] += 1
        clock_valid = len(t) == 4 and t.isascii() and t.isdigit() and int(t[:2]) < 24 and int(t[2:]) < 60
        fields = {"birth_year": born is not None and born.year == YEAR, "clock": clock_valid,
                  "sex": sex in ("1", "2"), "municipality_code": place_valid}
        if fields["birth_year"]:
            counts["recorded_1999_birth_year"] += 1
            bucket = "hhmm" if clock_valid else "blank" if not t else "invalid"
            clock_pattern[bucket] += 1
            if clock_valid:
                per_state[state]["recorded_hhmm"] += 1
                clock_pattern["on_the_hour"] += int(t.endswith("00"))
                clock_pattern["midnight"] += int(t == "0000")
        if not all(fields.values()):
            for name, ok in fields.items():
                if not ok:
                    ledger["invalid_fields_nonexclusive"][name] += 1
            exclusions["invalid_or_missing_fields"] += 1
            continue
        counts["complete_birth_fields"] += 1
        # The publisher dictionary specifies seven digits. Match the entire
        # source code, including the final digit, to the official lookup.
        ref = refs.get(place[:6])
        if ref is None or ref["municipality_ibge7"] != place:
            exclusions["unmatched_municipality"] += 1
            continue
        if not ref["timezone_id"]:
            exclusions["unresolved_timezone"] += 1
            continue
        civil = datetime(born.year, born.month, born.day, int(t[:2]), int(t[2:]))
        offsets = legacy.r8.row_offset(civil, ref["timezone_id"])
        if len(offsets) != 1:
            exclusions["dst_fold" if offsets else "dst_gap"] += 1
            continue
        sex = "M" if sex == "1" else "F"
        h = f"BR|{state}|{sex}|{YEAR}"
        ledger["eligible_strata"][h] += 1
        ledger["minute_mod5"][str(civil.minute % 5)] += 1
        eligible_clock["on_the_hour"] += int(civil.minute == 0)
        eligible_clock["midnight"] += int(t == "0000")
        per_state[state]["eligible"] += 1
        counts["eligible"] += 1
        if retain:
            key = f"SINASC1999:row:{index:07d}"
            row = (index, civil, sex, place[:6], offsets[0], h)
            candidates[h].append((sha256((SEED + "|" + key).encode()).digest(), key, row))
    require(counts["raw_rows"] == sum(c["source_rows"] for c in per_state.values())
            == counts["eligible"] + sum(exclusions.values()),
            "Source and eligible row totals do not reconcile")
    report.update(ledger, clock_among_1999_rows=dict(clock_pattern), eligible_clock=dict(eligible_clock),
                  coverage_by_occurrence_state=dict(sorted(per_state.items())))
    return candidates


def audit(args):
    require(legacy.r8.timezone_database_version().removeprefix("# version ") == "2026c",
            "Use the pinned IANA release")
    report = {"archive_sha256": digest(args.archive), "municipality_reference_sha256": digest(args.references),
              "timezone_version": "2026c", "birth_year": YEAR, "outcome_fields_used": False}
    audit_source(args.archive, read(args.references), report)
    write(args.output, report)


def registered(args):
    path = HERE / "protocol.json"
    require(digest(path) == args.registration_sha256, "Use the published research registration")
    protocol = read(path)
    for name, expected in protocol["files_sha256"].items():
        require(digest(ROOT / name) == expected, "Altered frozen file: " + name)
    return protocol


def prepare(args):
    protocol = registered(args)
    source = read(HERE / "source_audit.json")
    require(digest(args.archive) == source["archive"]["sha256"] and
            digest(args.references) == source["municipality_reference_sha256"], "Source bytes differ")
    require(legacy.r8.timezone_database_version().removeprefix("# version ") == "2026c",
            "Use the pinned IANA release")
    refs = read(args.references)
    check = {"archive_sha256": source["archive"]["sha256"],
             "municipality_reference_sha256": source["municipality_reference_sha256"],
             "timezone_version": "2026c", "birth_year": YEAR, "outcome_fields_used": False}
    levels = audit_source(args.archive, refs, check, retain=True)
    serialized = json.dumps(check, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    require(sha256(serialized.encode()).hexdigest() == source["full_private_audit_sha256"],
            "Re-read of archive differs from registered private audit")
    counts = check["eligible_strata"]
    quotas = allocate(counts, protocol["sample_records"])
    sample = args.job / "sample"
    sample.mkdir(mode=0o700)
    rows = []
    for h, ranked in levels.items():
        require(len(ranked) == counts[h], "Stratum candidate count is inconsistent")
        for rank, key, (ordinal, civil, sex, place, offset, _) in sorted(ranked)[:quotas[h]]:
            ref = refs[place]
            require(legacy.r8.valid_offsets(civil, ref["timezone_id"]) == (offset,),
                    "Re-resolved historical clock differs")
            row = dict(study_id="R15-" + sha256(key.encode()).hexdigest()[:24],
                       source_id=key, source=SOURCE, source_row_id=str(ordinal),
                       birth_local=civil.isoformat(), birth_utc=(civil-timedelta(seconds=offset)).isoformat()+"Z",
                       source_offset_seconds=offset, sex=sex, sex_resolved=sex, birth_country="BR",
                       calendar="gregorian", instant_scale="UT", time_precision_seconds=60,
                       time_uncertainty_seconds=None, coordinate_precision_degrees=None,
                       quality=legacy.r8.BRAZIL_QUALITY, sampling_sha256=rank.hex(),
                       **ref, **legacy.r8.weight_metadata(h, counts, quotas))
            rows.append(row)
    rows.sort(key=lambda r: r["study_id"])
    files = {}
    for name, values in (("birth_metadata.jsonl", rows),
                         ("birth_inputs.jsonl", ({key: row.get(key) for key in legacy.r8.MODEL_KEYS} for row in rows))):
        with (sample / name).open("x", encoding="utf-8") as out:
            for row in values:
                out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        files[name] = digest(sample / name)
    manifest = {"sample_n": len(rows), "eligible_frame_N": sum(counts.values()), "seed": SEED,
                "model_input_sha256": files["birth_inputs.jsonl"], "metadata_sha256": files["birth_metadata.jsonl"],
                "strata": [{"stratum_id": h, "N_h": counts[h], "n_h": quotas[h]} for h in sorted(quotas)]}
    write(sample / "sampling_manifest.json", manifest)
    files["sampling_manifest.json"] = digest(sample / "sampling_manifest.json")
    aread, _ = load_source(sample)
    weights = sum((Fraction(r["N_h"], r["n_h"]) for r in aread), Fraction(0))
    require(len(rows) == protocol["sample_records"] and weights == manifest["eligible_frame_N"],
            "Sample design does not reconcile")
    write(args.job / "input_seal.json", {"registration_sha256": args.registration_sha256,
        "private_input_sha256": files, "records": len(rows), "eligible_frame_N": manifest["eligible_frame_N"],
        "additional_matching_chart_inputs": len(aread)-len({r["chart_input_key"] for r in aread})})


def checked_sample(args, cfg):
    seal_path = args.job / "input_seal.json"
    require(digest(seal_path) == args.input_sha256, "Use the published input seal")
    seal = read(seal_path)
    require(seal["registration_sha256"] == args.registration_sha256 and seal["records"] == cfg["sample_records"],
            "Wrong eligible sample")
    sample = args.job / "sample"
    for name, expected in seal["private_input_sha256"].items():
        require(digest(sample / name) == expected, "Altered sealed birth file")
    return sample


def score(args):
    cfg = registered(args)
    sample = checked_sample(args,cfg)
    require(platform.system() == "Linux" and platform.machine() == "x86_64" and
            platform.python_version() == "3.12.14" and np.__version__ == "2.3.5" and
            subprocess.check_output(["node","--version"],text=True).strip()=="v24.22.3",
            "Use the frozen R10 scoring runtime")
    folder = args.job / "profiles"
    require(not folder.exists(), "Do not overwrite a scored job")
    subprocess.run([sys.executable, str(R10 / "methods/run_profiles.py"), "--samples",str(sample),
                    "--output",str(folder),"--jobs","4","--mode","baseline"],check=True)
    receipt = read(folder / "baseline_summary.json")
    require(receipt["tasks"] == cfg["sample_records"] and
            receipt["status_counts"] == {"computed":cfg["sample_records"]}, "Incomplete baseline trajectories")


def analyze(args):
    cfg = registered(args)
    sample = checked_sample(args,cfg)
    score_file = args.job / "profiles/baseline_profiles.jsonl"
    require(digest(score_file)==read(args.job/"profiles/baseline_summary.json")["result_sha256"],
            "Scored output differs from receipt")
    require(np.__version__ == "2.3.5", "Use the frozen reference math runtime")
    receipt = read(R10/"independent_replay/registration.json")
    for name, expected in receipt["reference_files_sha256"].items():
        require(digest(args.r10_job / name)==expected,"Altered Brazil 2006 reference")
    rr, _, reference_scores, rw, *_ = load_profiles(
        args.r10_job/"reference/brazil2006", [args.r10_job/"reference/full-frozen-r8-baseline_profiles.jsonl"])
    rows, manifest, scores, weights, strata, frame, _ = load_profiles(sample,[score_file])
    ref_weights = [Fraction(r["N_h"],r["n_h"]) for r in rr]
    fixed = PrecisionReference(reference_scores,rw,ref_weights)
    alternative = RawSortedReference([{"weight":w} for w in ref_weights],reference_scores)
    flags = fixed.flags(scores)
    _, exact, _ = alternative.apply(scores)
    require(np.array_equal(flags,exact),"Independent threshold decisions disagree")
    ref_flags = fixed.flags(reference_scores)
    _, exact_reference, _ = alternative.apply(reference_scores)
    require(np.array_equal(ref_flags,exact_reference),"Independent reference columns disagree")
    hit_counts = (flags.sum(axis=2)>=3).sum(axis=1)
    weighted = float(np.average(hit_counts/40,weights=weights))
    exact_mean = sum((Fraction(int(hit),40)*Fraction(row["N_h"],row["n_h"])
                      for row,hit in zip(rows,hit_counts,strict=True)),Fraction(0))/manifest["eligible_frame_N"]
    require(abs(float(exact_mean)-weighted)<2e-13,"Exact rational rate differs from float estimate")
    interval = conditional_frame_interval(hit_counts/40,strata,frame,seed=cfg["bootstrap_seed"],
                                          draws=9999,family_size=1)
    require(interval["status"]=="computed_assumption_conditional" and abs(interval["point"]-weighted)<2e-13,
            "Predeclared conditional confidence interval unavailable")
    lower,upper = [float(v-fixed.joint_rate) for v in interval["interval95"]]
    clock = np.array([row["birth_local"][11:16] for row in rows])
    state = np.array([row["stratum_id"].split("|")[1] for row in rows])
    source = read(HERE/"source_audit.json")
    most_covered = source["largest_eligible_state"]["code"]
    def subset(mask):
        count=int(mask.sum())
        return {"sample_records":count, "weighted_eligible_record_share":float(weights[mask].sum()/weights.sum()),
                "weighted_joint_rate":float(np.average(hit_counts[mask]/40,weights=weights[mask])) if count else None}
    mexico = read(ROOT/"rounds/r13/results.json")["birth_year_breakdown"]["1999"]
    write(args.job/"results.json",{"sample_records":len(rows),"eligible_frame_N":manifest["eligible_frame_N"],
        "modeled_record_years":len(rows)*40,"baseline_system_year_scores":len(rows)*160,
        "baseline_sha256":digest(score_file),"reference_joint_rate":fixed.joint_rate,
        "joint_rate":weighted,"difference_from_brazil_2006":weighted-fixed.joint_rate,
        "conditional_95_difference": [lower,upper],"analytic_design_variance":interval["analytic_design_variance"],
        "bootstrap_draws":9999,"weighted_subsets":{"nonround_minute":subset(np.array([v[-2:]!="00" for v in clock])),
            "nonmidnight":subset(clock!="00:00"),"largest_eligible_state":subset(state==most_covered)},
        "largest_eligible_state_code":most_covered,"mx1999_r13_descriptive":mexico,
        "independent_threshold_checks":int(flags.size+ref_flags.size),
        "scope":"Fixed model and reference estimates for the restricted SINASC 1999 eligible record frame."})


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="stage",required=True)
    for stage in ("audit","prepare","score","analyze"):
        cmd=sub.add_parser(stage)
        if stage in ("audit","prepare"):
            for name in ("archive","references"):
                cmd.add_argument("--"+name,type=Path,required=True)
        if stage=="audit":
            cmd.add_argument("--output",type=Path,required=True)
        else:
            cmd.add_argument("--job",type=Path,required=True)
            cmd.add_argument("--registration-sha256",required=True)
        if stage in ("score","analyze"):
            cmd.add_argument("--input-sha256",required=True)
        if stage=="analyze":
            cmd.add_argument("--r10-job",type=Path,required=True)
    args=p.parse_args()
    globals()[args.stage](args)
