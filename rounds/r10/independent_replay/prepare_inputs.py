"""Prepare a separate input release for the independent R10 replay, before scoring."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
R10 = HERE.parent
ROOT = R10.parents[1]
sys.path.insert(0, str(R10 / "methods"))
from r10_io import load_source, sha256, jsonlines

REPLAY_ID = "OBS-R10-INDEPENDENT-2026-11-27"
RECOVERY = R10 / "recovery/input_and_design_receipt.json"
OCCURRENCE = {"mexico_2000s": ("occurrence_municipality_code", "physical_record_ordinal_1based",
                                "recovered_2020_municipal_seat"),
              "mexico2020": ("occurrence_code", "physical_record_ordinal", "recovered_2020_locality")}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def verify_files(file_list):
    for item in file_list:
        check(sha256(ROOT / item["path"]) == item["sha256"], "Published file changed: " + item["path"])


def historical_records():
    for name in ["public_freeze_receipt.json", "public_source_decisions_receipt.json", "public_methods_receipt.json",
                 "verification/prior_release_manifest.json"]:
        verify_files(json.loads((R10 / name).read_bytes())["files"])
    decisions = json.loads((R10 / "source_decisions.json").read_bytes())
    check(sha256(R10 / "protocol.json") == decisions["protocol_sha256"], "Protocol mismatch")
    slots = decisions["source_slots"]
    available = {s["id"]: s for s in slots if s["status"] == "available"}
    earlier = {r["slot"]: r for r in json.loads(RECOVERY.read_bytes())["groups"]}
    check(len(slots) == 7 and len(available) == 6 and set(available) == set(earlier), "Source decision mismatch")
    return available, earlier


def project_mexico(source, target, manifest, decision, recovered):
    slot = decision["id"]
    design = source / "reconstructed_design.jsonl"
    check(sha256(design) == recovered["verified_design_file_sha256"], "Reconstructed design digest: " + slot)
    by_id = {r["study_id"]: r for r in jsonlines(design)}
    check(len(by_id) == 2000, "Design identifier count: " + slot)
    code_key, ordinal_key, geo_tier = OCCURRENCE[slot]
    with (target / "birth_metadata.jsonl").open("x", encoding="utf-8", newline="\n") as dest:
        for birth in jsonlines(source / "birth_inputs.jsonl"):
            ident = birth["study_id"]
            row = by_id.pop(ident)
            sid = row["source_id"]
            ordinal = row[ordinal_key]
            check(sid == f"INEGI-NACIM{row['registration_archive_year']}-{ordinal:08d}", "Source row identity")
            check(row["registration_archive_year"] in decision["registration_archive_years"], "Registration year")
            check(ident == "R10-" + hashlib.sha256(sid.encode()).hexdigest()[:24], "Model/registry join")
            rank = hashlib.sha256((manifest["seed"] + "|" + sid).encode()).hexdigest()
            check(row["sampling_sha256"] == rank, "Sampling rank")
            sex = birth["sex_resolved"]
            check(row["stratum_id"] == row[code_key][:2] + "|" + sex, "Occurrence/sex stratum")
            check(row["source"] == decision["source_label"] and row["birth_country"] == decision["country"],
                  "Source label or country")
            if "birth_input" in row:
                check(row["birth_input"] == birth, "Design contains a different birth input")
            # The two recovery labels describe provenance. Baseline engines and the reference refit use neither.
            fields = {k: birth[k] for k in ("study_id", "birth_local", "birth_utc", "source_offset_seconds", "latitude", "longitude")}
            fields.update({k: row[k] for k in ("source_id", "source", "birth_country", "stratum_id", "N_h", "n_h",
                                                 "inclusion_probability", "sample_weight", "sampling_sha256")})
            fields.update(source_row_id=ordinal, sex=sex, quality="reconstructed_official_inegi_design", geo_precision=geo_tier)
            dest.write(json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    check(not by_id, "Leftover design identifiers")
    adjusted = dict(manifest, metadata_sha256=sha256(target / "birth_metadata.jsonl"),
                    independent_replay={"id": REPLAY_ID, "metadata_origin": "explicit recovery projection",
                                        "historical_metadata_recovered": False,
                                        "historical_metadata_sha256": decision["metadata_sha256"],
                                        "historical_manifest_sha256": decision["sampling_manifest_sha256"],
                                        "reconstructed_design_sha256": sha256(design)})
    write_json(target / "sampling_manifest.json", adjusted)


def prepare(source_root, destination):
    available, earlier = historical_records()
    destination = destination.resolve()
    check(not destination.exists(), "Use a new private output directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ids = set()
    groups = []
    with TemporaryDirectory(dir=destination.parent, prefix=".r10-input-") as temp:
        stage = Path(temp) / "prepared"
        (stage / "seals").mkdir(parents=True)
        for slot, decision in available.items():
            source, target = source_root / slot, stage / "samples" / slot
            target.mkdir(parents=True)
            manifest_path = source / "sampling_manifest.json"
            check(sha256(manifest_path) == decision["sampling_manifest_sha256"], "Original manifest: " + slot)
            manifest = json.loads(manifest_path.read_bytes())
            check(sha256(source / "birth_inputs.jsonl") == manifest["model_input_sha256"] == decision["input_sha256"],
                  "Original model input: " + slot)
            check(manifest["metadata_sha256"] == decision["metadata_sha256"], "Original metadata commitment")
            shutil.copyfile(source / "birth_inputs.jsonl", target / "birth_inputs.jsonl")
            if slot in OCCURRENCE:
                project_mexico(source, target, manifest, decision, earlier[slot])
            else:
                check(sha256(source / "birth_metadata.jsonl") == decision["metadata_sha256"], "Original metadata: " + slot)
                shutil.copyfile(source / "birth_metadata.jsonl", target / "birth_metadata.jsonl")
                shutil.copyfile(manifest_path, target / "sampling_manifest.json")
            rows, used_manifest = load_source(target)
            check(len(rows) == decision["sample_n"] == 2000 and used_manifest["seed"] == "OBS-R10-2026-11-27",
                  "Sample size or seed")
            counts = Counter(r["stratum_id"] for r in rows)
            frame = {s["stratum_id"]: s for s in manifest["strata"]}
            check(counts == {k: s["n_h"] for k, s in frame.items()}, "Stratum quotas")
            check(sum((Fraction(r["N_h"], r["n_h"]) for r in rows), Fraction()) ==
                  manifest["eligible_frame_N"] == decision["eligible_frame_N"], "Eligible weight total")
            for r in rows:
                s = frame[r["stratum_id"]]
                check(r["study_id"] not in ids and int(r["birth_local"][:4]) == decision["birth_year"], "Identity or birth year")
                ids.add(r["study_id"])
                check(r["source"] == decision["source_label"] and r["birth_country"] == decision["country"], "Provenance")
                check(all(r[k] == s[k] for k in ("N_h", "n_h", "inclusion_probability", "sample_weight")),
                      "Record weight or inclusion probability")
                check(s["sample_weight"] == s["N_h"]/s["n_h"] and s["inclusion_probability"] == s["n_h"]/s["N_h"],
                      "Incorrect recorded design fraction")
            seal = {"id": REPLAY_ID, "slot": slot, "input_manifest": used_manifest, "historical_metadata_recovered": slot not in OCCURRENCE,
                    "historical_manifest_sha256": decision["sampling_manifest_sha256"],
                    "historical_metadata_sha256": decision["metadata_sha256"], "design_evidence_sha256": earlier[slot]["verified_design_file_sha256"]}
            seal_path = stage / "seals" / (slot + ".json")
            write_json(seal_path, seal)
            groups.append({"slot": slot, "records": len(rows), "strata": len(counts), "target_birth_year": decision["birth_year"],
                           "eligible_population": decision["eligible_frame_N"], "historical_metadata_recovered": slot not in OCCURRENCE,
                           "input_sha256": sha256(target/"birth_inputs.jsonl"), "metadata_used_sha256": sha256(target/"birth_metadata.jsonl"),
                           "manifest_used_sha256": sha256(target/"sampling_manifest.json"), "seal_sha256": sha256(seal_path)})
        check(len(ids) == 12000, "Twelve thousand unique source-record identifiers required")
        write_json(stage / "receipt.json", {"id": REPLAY_ID, "distinct_record_ids": len(ids), "groups": groups})
        stage.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    prepare(args.source_root, args.output)
