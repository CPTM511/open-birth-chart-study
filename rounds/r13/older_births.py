"""Prepare, score and audit the registered population of late-registered 1990s births."""
import argparse
from collections import Counter
from datetime import timedelta, timezone
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
sys.path[:0] = [str(HERE / "sources"), str(R10 / "methods"), str(R10 / "verification")]
from audit_mexico_1990s import audit, digest
from analyze_cohorts import load_profiles
from precision_reference import PrecisionReference
from r10_io import jsonlines, load_source
from verify_aggregates import RawSortedReference


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def save(path, data):
    with path.open("x", encoding="utf-8") as out:
        json.dump(data, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write("\n")


def registration(reg_digest):
    path = HERE / "protocol.json"
    require(digest(path) == reg_digest, "Use the actual GitHub registration SHA-256")
    cfg = read(path)
    for name, expected in cfg["files_sha256"].items():
        require(digest(ROOT / name) == expected, "Frozen file differs: " + name)
    return cfg


def prepare(args, cfg):
    records = []

    def capture(year, ordinal, civil, registered, code, state_sex, point, offset):
        key = f"INEGI-NACIM{year}-{ordinal:08d}"
        _, lat, lon, zone = point
        birth = {
            "study_id": "R13-" + sha256(key.encode()).hexdigest()[:24],
            "birth_local": civil.isoformat(),
            "birth_utc": (civil - timedelta(seconds=offset)).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "latitude": lat, "longitude": lon, "source_offset_seconds": offset,
            "sex_resolved": state_sex[-1], "calendar": "gregorian", "timezone_id": zone,
            "time_precision_seconds": 60, "time_uncertainty_seconds": None, "coordinate_precision_degrees": None,
            "instant_scale": "UT",
        }
        records.append((key, birth, f"{civil.year}|{state_sex}", registered, code))

    reread = audit(args.archives, args.census, older_birth=capture)
    expected = read(HERE / "sources/mexico_1990s_audit.json")
    for key in ("archives", "birth_year_counts"):
        require(reread[key] == expected[key], "Raw source count differs from prescoring audit")
    require(len(records) == cfg["eligible_1990s_records"] == len({row[0] for row in records}),
            "Invalid physical row coverage")
    counts = Counter(item[2] for item in records)
    sample = args.job / "sample"
    sample.mkdir(mode=0o700)
    with (sample / "birth_inputs.jsonl").open("x") as f, (sample / "birth_metadata.jsonl").open("x") as m:
        for key, birth, stratum, registered, location in sorted(records, key=lambda row: row[0]):
            denominator = counts[stratum]
            meta = {
                **birth, "source": cfg["source_label"], "source_id": key, "source_row_id": key,
                "sex": birth["sex_resolved"], "stratum_id": stratum, "birth_country": "MX",
                "geo_precision": "census_locality_reference", "quality": "administrative_minute_late_registration",
                "N_h": denominator, "n_h": denominator, "sample_weight": 1, "inclusion_probability": 1,
                "sampling_sha256": sha256((cfg["rank_seed"] + "|" + key).encode()).hexdigest(),
                "registration_date": registered.isoformat(), "occurrence_code": location,
            }
            f.write(json.dumps(birth, separators=(",", ":")) + "\n")
            m.write(json.dumps(meta, separators=(",", ":")) + "\n")
    files = {name: digest(sample / name) for name in ("birth_inputs.jsonl", "birth_metadata.jsonl")}
    manifest = {
        "sample_n": len(records), "eligible_frame_N": len(records), "seed": cfg["rank_seed"],
        "model_input_sha256": files["birth_inputs.jsonl"], "metadata_sha256": files["birth_metadata.jsonl"],
        "strata": [{"stratum_id": h, "N_h": counts[h], "n_h": counts[h]} for h in sorted(counts)],
    }
    save(sample / "sampling_manifest.json", manifest)
    files["sampling_manifest.json"] = digest(sample / "sampling_manifest.json")
    rows, _ = load_source(sample)
    save(args.job / "input_seal.json", {
        "registration_sha256": args.registration_sha256, "records": len(rows),
        "physical_source_rows_distinct": len(records),
        "complete_census_of_eligible_rows": True,
        "additional_rows_with_duplicate_input_tuple": len(rows) - len({r["chart_input_key"] for r in rows}),
        "private_input_sha256": files,
    })


def checked_input(args, cfg):
    seal_path = args.job / "input_seal.json"
    require(digest(seal_path) == args.input_sha256, "Supply the GitHub-verified input seal")
    seal = read(seal_path)
    require(seal["records"] == cfg["eligible_1990s_records"]
            and seal["registration_sha256"] == args.registration_sha256, "Unregistered census")
    sample = args.job / "sample"
    for file, expected in seal["private_input_sha256"].items():
        require(digest(sample / file) == expected, "Private input differs from sealed release")
    return sample


def score(args, cfg):
    sample = checked_input(args, cfg)
    require(platform.system() == "Linux" and platform.machine() == "x86_64"
            and platform.python_version() == "3.12.14", "Use the frozen Linux scoring environment")
    require(subprocess.check_output(["node", "--version"], text=True).strip() == "v24.22.3", "Wrong Node runtime")
    count = cfg["eligible_1990s_records"]
    output = args.job / "profiles"
    require(not output.exists(), "Choose a new private job")
    for mode, expected in (("baseline", count), ("sensitivity", 800)):
        subprocess.run([sys.executable, str(R10 / "methods/run_profiles.py"), "--samples", str(sample),
                        "--output", str(output), "--jobs", "4", "--mode", mode], check=True)
        receipt = read(output / f"{mode}_summary.json")
        require(receipt["tasks"] == expected and receipt["status_counts"] == {"computed": expected},
                "R13 profiles incomplete")
    save(args.job / "completed.json", {
        "registration_sha256": args.registration_sha256, "input_sha256": args.input_sha256,
        "baseline_records": count, "base_record_years": count * 40, "base_system_year_scores": count * 160,
        "clock_stress_profiles": 800,
        "baseline_sha256": digest(output / "baseline_profiles.jsonl"),
        "clock_stress_sha256": digest(output / "sensitivity_profiles.jsonl"),
    })


def summarize(flags):
    n = len(flags)
    hits = int(np.count_nonzero(flags.sum(axis=2) >= 3))
    return {"source_records": n, "modeled_record_years": n * 40, "joint_high_record_years": hits,
            "joint_rate": hits / (n * 40)}


def analyze(args, cfg):
    sample = checked_input(args, cfg)
    completed = read(args.job / "completed.json")
    require(completed["registration_sha256"] == args.registration_sha256 and completed["input_sha256"] == args.input_sha256,
            "Completed run and sealed inputs differ")
    folder = args.job / "profiles"
    base_file, stress_file = folder / "baseline_profiles.jsonl", folder / "sensitivity_profiles.jsonl"
    require(digest(base_file) == completed["baseline_sha256"] and
            digest(stress_file) == completed["clock_stress_sha256"], "A scored file changed")
    pinned = read(R10 / "independent_replay/registration.json")["reference_files_sha256"]
    for name, expected in pinned.items():
        require(digest(args.r10_job / name) == expected, "Frozen Brazil 2006 reference differs: " + name)
    r_dir = args.r10_job / "reference/brazil2006"
    r_file = args.r10_job / "reference/full-frozen-r8-baseline_profiles.jsonl"
    ref_rows, _, r_scores, r_w, *_ = load_profiles(r_dir, [r_file])
    rows, _, values, _, _, _, _ = load_profiles(sample, [base_file])
    fractions = [Fraction(row["N_h"], row["n_h"]) for row in ref_rows]
    fixed = PrecisionReference(r_scores, r_w, fractions)
    separate = RawSortedReference([{"weight": w} for w in fractions], r_scores)
    def flags(array):
        main = fixed.flags(array)
        _, check, _ = separate.apply(array)
        require(np.array_equal(main, check), "Independent fixed-reference threshold differs")
        return main
    high = flags(values)
    ref_high = flags(r_scores)
    anchor = float(np.average((ref_high.sum(axis=2) >= 3).mean(axis=1), weights=r_w))
    require(abs(anchor - fixed.joint_rate) < 2e-13, "Independent reference rate differed")
    minute = np.array([int(row["birth_local"][14:16]) for row in rows])
    lines = np.array([row["birth_local"][11:16] for row in rows])
    birth = np.array([int(row["birth_local"][:4]) for row in rows])
    groups = {"all_eligible": summarize(high), "nonmidnight": summarize(high[lines != "00:00"]),
              "nonround_minute": summarize(high[minute != 0]), "on_the_hour": summarize(high[minute == 0])}
    cohorts = {str(year): summarize(high[birth == year]) for year in range(1990, 2000)}
    for row in (*groups.values(), *cohorts.values()):
        row["difference_from_fixed_brazil_2006"] = row["joint_rate"] - anchor
    chosen = sorted(range(len(rows)), key=lambda i: (rows[i]["sampling_sha256"], rows[i]["study_id"]))[:200]
    ids = [rows[i]["study_id"] for i in chosen]
    want = set(ids)
    expected_rows = {rows[i]["study_id"]: rows[i] for i in chosen}
    variants = {}
    for item in jsonlines(stress_file):
        key, label = item["study_id"], item["variant"]
        row = expected_rows[key]
        require(item["status"] == "computed" and item["calendar_years"] == row["calendar_years"]
                and item["source"] == row["source"] and item["chart_input_key"] == row["chart_input_key"],
                "Unmatched clock perturbation record")
        group = variants.setdefault(label, {})
        require(key not in group, "Repeating perturbation")
        group[key] = item["primary_scores"]
    stress = {}
    base = high[chosen]
    base_joint = base.sum(axis=2) >= 3
    require(set(variants) == {"clock_-120", "clock_-30", "clock_+30", "clock_+120"},
            "Missing declared variants")
    for label, mapping in sorted(variants.items()):
        require(set(mapping) == want, "Perturbation sample coverage differs")
        perturbed = flags(np.array([mapping[key] for key in ids], dtype=float))
        joint = perturbed.sum(axis=2) >= 3
        stress[label] = {
            "records": len(ids), "base_joint_rate": float(base_joint.mean()), "stress_joint_rate": float(joint.mean()),
            "joint_flag_changed_share": float(np.mean(base_joint != joint)),
            "system_flags_changed_share": (base != perturbed).mean(axis=(0, 1)).tolist(),
        }
    require(sum(r["joint_high_record_years"] for r in cohorts.values()) == groups["all_eligible"]["joint_high_record_years"],
            "Year-level counts fail conservation")
    save(args.job / "results.json", {
        "reference": {"source_records": len(ref_rows), "joint_rate": anchor},
        "scope": "Eligible births in the four late-registration archives, census within this restricted frame.",
        "clock_quality_subsets": groups, "birth_year_breakdown": cohorts, "paired_clock_stress": stress,
        "complete_run": completed, "independent_threshold_checks": int(high.size + ref_high.size + 800 * 160),
        "independent_reference_arithmetic": "Raw sorted prefix CDF and exact rational boundary resolution",
    })
    print("Census, three clock-quality subsets, all ten birth years and four clock stress paths verified.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="stage", required=True)
    for stage in ("prepare", "score", "analyze"):
        sub = subs.add_parser(stage)
        sub.add_argument("--job", required=True, type=Path)
        sub.add_argument("--registration-sha256", required=True)
        if stage == "prepare":
            sub.add_argument("--archives", required=True, type=Path)
            sub.add_argument("--census", required=True, type=Path)
        else:
            sub.add_argument("--input-sha256", required=True)
        if stage == "analyze":
            sub.add_argument("--r10-job", required=True, type=Path)
    args = parser.parse_args()
    globals()[args.stage](args, registration(args.registration_sha256))
