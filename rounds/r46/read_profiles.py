"""Verify run commitments and recover whole-record R46 arrays."""

from dataclasses import dataclass

import numpy as np

from rounds.r45.trajectories import Cohort
from analyze_cohorts import load_profiles

from .common import GROUPS, R10, digest, read_json, require
from .score import BATCH_SIZE, inputs, selected, signature, tasks, verify_batch


@dataclass(frozen=True)
class CompleteCohort:
    original: Cohort
    hourly: np.ndarray
    evidence: dict


def collect_batches(job, group, source_digest, rows, cfg, mode):
    configs = list(tasks(selected(rows,cfg,mode),group))
    expected = set()
    reports, digests = [], []
    for start in range(0,len(configs),BATCH_SIZE):
        key = f"{start:05d}"
        expected.add(key)
        folder = job/group/mode/key
        current = configs[start:start+BATCH_SIZE]
        commit = signature(source_digest,group,mode,start,current)
        reports.extend(verify_batch(folder,commit,current))
        digests.append(digest(folder/"receipt.json"))
    unit = job/group/mode
    require({p.name for p in unit.iterdir() if p.name.isdecimal()} == expected, "Extra or missing score batches")
    return reports, digests


def load_group(job, group, cfg):
    rows, manifest, commitment = inputs(job,group)
    reports, primary = collect_batches(job,group,commitment,rows,cfg,"full")
    replay, sample = collect_batches(job,group,commitment,rows,cfg,"audit")
    saved = {row["study_id"]:row for row in reports}
    require(len(saved) == len(rows) and all(item == saved[item["study_id"]] for item in replay),
            "Independent engine re-execution differs")
    evidence = {"n":len(rows),"frame_total":manifest["eligible_frame_N"],"batch_receipts_sha256":primary,
                "audit_receipts_sha256":sample,"input_seal_sha256":commitment,
                "scoring_replay_records":len(replay),
                "cohort_40_year_scores":len(rows)*40*4,
                "records_rescored_at_hour":sum("hour" in x["scores"] for x in reports),
                "invalid_hour_offsets":sum(x["clock_shift_minutes"] is None for x in reports),
                "exact_replayed_scores":sum(len(x["scores"])*40*4 for x in replay)}
    arrays = np.asarray([item["scores"]["base"] for item in reports],dtype=float)
    shifted = np.asarray([item["scores"].get("hour",item["scores"]["base"]) for item in reports],dtype=float)
    return CompleteCohort(Cohort(rows,arrays,{}),shifted,evidence)


def load_reference(r10):
    commitments = read_json(R10/"independent_replay/registration.json")["reference_files_sha256"]
    require(all(digest(r10/name)==sha for name,sha in commitments.items()), "R10 calibration inputs changed")
    records, _, scores, _, _, _, _ = load_profiles(r10/"reference/brazil2006",
                                                   [r10/"reference/full-frozen-r8-baseline_profiles.jsonl"])
    require(len(records)==2000, "Reference sample size differs")
    return Cohort(records,scores,{})


def load_inputs(job,r10,cfg):
    models = {group:load_group(job,group,cfg) for group in GROUPS}
    ids = [r["source_id"] for model in models.values() for r in model.original.rows]
    require(len(ids)==len(set(ids)), "R46 group source IDs overlap")
    return load_reference(r10), models
