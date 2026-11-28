"""Load and audit complete sets of frozen and paired score trajectories."""

from dataclasses import dataclass
from functools import cached_property

import numpy as np

from .common import REGISTRATION, R10, digest, read_json, require, source_seal
from .datasets import datasets, verify_profile
from .score import audit_sample, hour_offset
from analyze_cohorts import load_profiles
from r10_io import jsonlines


@dataclass(frozen=True)
class Cohort:
    rows: list
    scores: np.ndarray
    publication: dict

    @cached_property
    def weights(self):
        return np.asarray([r["sample_weight"] for r in self.rows])

    @cached_property
    def anchors(self):
        return np.asarray([r["calendar_years"][0] for r in self.rows])

    def subset(self, noted):
        return Cohort([r for r, use in zip(self.rows, noted, strict=True) if use], self.scores[noted], self.publication)


def load_all(args, cfg):
    entries = datasets(args, cfg)
    cohorts, loaded = {}, {}
    expected_count = {"reference": cfg["reference_n"]}
    expected_count.update({name: info["n"] for name, info in (cfg["groups"] | cfg["holdout"]).items()})
    for group, item in entries.items():
        same_input = item.sample, item.profile
        if same_input not in loaded:
            verify_profile(item, args.job, group)
            rows, manifest, scores, _, _, _, raw = load_profiles(item.sample, [item.profile])
            require(np.all((0 <= scores) & (scores <= 1)), "Out-of-domain score")
            loaded[same_input] = rows, manifest, scores, raw
        rows, manifest, scores, raw = loaded[same_input]
        mask = np.array([item.includes(row) for row in rows])
        selected = [row for row, take in zip(rows, mask, strict=True) if take]
        require(len(selected) == expected_count[group], f"Missing or unexpected records in {group}")
        require(all(row["birth_country"] == item.country for row in selected), "Wrong birth country")
        if not mask.all():
            require(all(r["N_h"] == r["n_h"] for r in rows),
                    "Birth-year subset would alter the design of a non-censused stratum")
        metadata = {k: raw[k] for k in ("input_sha256", "metadata_sha256", "sampling_manifest_sha256",
                                       "profile_files", "source_labels")}
        metadata.update(sample_n=len(selected), parent_sample_n=manifest["sample_n"],
                        eligible_frame_N=manifest["eligible_frame_N"] if mask.all() else len(selected),
                        birth_years=sorted({int(r["birth_local"][:4]) for r in selected}),
                        full_record_years=40*len(selected), full_system_year_scores=160*len(selected))
        cohorts[group] = Cohort(selected, scores[mask], metadata)
    legacy = {r["source_id"] for r in cohorts["mx2009_r10"].rows}
    new = {r["source_id"] for r in cohorts["mx2009"].rows}
    require(not legacy & new, "2009 Mexico samples share physical rows")
    main_ids = {r["study_id"] for group in cfg["groups"] for r in cohorts[group].rows}
    require(len(main_ids) == sum(cfg["groups"][group]["n"] for group in cfg["groups"]), "Duplicate main study ID")
    return cohorts


def paired_scores(cohort, item, job, group, cfg):
    archive = job / group / "scores"
    rows = {row["study_id"]: row for row in cohort.rows}
    indices = {row["study_id"]: i for i, row in enumerate(cohort.rows)}
    shifts = {sid: hour_offset(row) for sid, row in rows.items()}
    probes = {row["study_id"] for row in audit_sample(cohort.rows, cfg)}
    hour = cohort.scores.copy()
    receipts = {}
    for mode in ("hour", "audit"):
        sample = rows.keys() if mode == "hour" else probes
        expect = {("hour", sid) for sid in sample if shifts[sid]}
        if mode == "audit":
            expect |= {("base", sid) for sid in sample}
        receipt = read_json(archive / f"{mode}_receipt.json")
        path = archive / f"{mode}.jsonl"
        require(receipt["score_sha256"] == digest(path) and receipt["registration"] == REGISTRATION
                and receipt["group"] == group and receipt["mode"] == mode
                and receipt["source"] == source_seal(item.sample)
                and receipt["engine_runner_sha256"] == digest(R10 / "methods/run_profiles.py")
                and receipt["n"] == len(sample), "Paired scoring receipt failed")
        require(receipt["source_clocks_already_on_hour"] == sum(shifts[sid] == 0 for sid in sample)
                and receipt["rounded_offset_not_resolved"] == sum(shifts[sid] is None for sid in sample),
                "Paired clock eligibility differs")
        observed = set()
        for profile in jsonlines(path):
            variant, sid = profile["variant"], profile["study_id"]
            key = variant, sid
            require(key in expect and key not in observed and profile["status"] == "computed", "Unexpected paired score")
            index, row = indices[sid], rows[sid]
            require(all(profile[name] == row[name] for name in ("calendar_years", "source", "chart_input_key")),
                    "Unpaired score record")
            scores = np.asarray(profile["primary_scores"], dtype=float)
            require(scores.shape == (40, 4) and np.all((0 <= scores) & (scores <= 1)), "Invalid paired scores")
            if mode == "hour":
                hour[index] = scores
            else:
                expected = cohort.scores[index] if variant == "base" else hour[index]
                require(np.array_equal(scores, expected), f"{group} scoring replay differs from complete run")
            observed.add(key)
        require(observed == expect, "Incomplete paired or probe trajectory set")
        require(sum(receipt["completed"].values()) == len(expect), "Paired receipt trajectory count")
        receipts[mode] = receipt
    receipts["paired_records"] = len(rows)
    receipts["replay_exact_scores"] = 160*sum(receipts["audit"]["completed"].values())
    return hour, receipts
