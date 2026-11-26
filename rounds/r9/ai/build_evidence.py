"""Rebuild the R9 AI-track data extracts and coverage audit from public snapshots.

No causal estimation, death outcomes, astrology-to-AI inference, or benchmark
execution occurs here. Row counts describe published aggregate observations.
"""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).parent)
    args = ap.parse_args()
    raw, out = args.raw_dir, args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    metrics = out / "metrics"
    metrics.mkdir(exist_ok=True)
    manifest = json.loads((out / "source_fetch_manifest.json").read_text())
    by_id = {row["source_id"]: row for row in manifest}
    required = ["metr_figure_10", "ilostat_employment_annual", "ilostat_dic_source",
                "ilostat_dic_ref_area", "ilostat_dic_classif1", "ilostat_dic_obs_status"]
    for source_id in required:
        record = by_id[source_id]
        payload = (raw / record["private_snapshot_filename"]).read_bytes()
        if not record.get("snapshot_complete") or hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise ValueError("Incomplete or changed frozen source: " + source_id)

    chart = json.loads((raw / "metr_figure_10.json").read_text())
    tables = {table["name"]: table["rows"] for table in chart["panels"][0]["tables"]}
    models = tables["models"]
    write_csv(metrics / "metr_model_horizons.csv", models, list(models[0]))
    dump(metrics / "metr_reported_trend.json", {
        "status": "provider_reported_fit_not_independently_reestimated",
        "publication_date": "2026-11-20", "source_id": "metr_figure_10",
        "trend": tables["frontier trends"], "task_limits": tables["task limits"],
        "definition": "Human-expert task duration at a fitted 50 percent success level; not AI wall-clock autonomy duration.",
        "caveats": ["Software and AI-R&D task distribution, not all work.",
                    "Combined TH1.1 and TH2; human baselining and task designs differ.",
                    "Large confidence intervals for frontier model horizons are retained.",
                    "No extrapolation to human displacement, loss of control, or extinction."]})

    with gzip.open(raw / "ilostat_employment_annual.csv.gz", "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        all_rows = list(reader)
    recent = [row for row in all_rows if int(row["time"]) >= 2020]
    sources = {(r["ref_area"], r["source"]): r["source.label"] for r in read_csv(raw / "ilostat_dic_source.csv")}
    areas = {r["ref_area"]: r["ref_area.label"] for r in read_csv(raw / "ilostat_dic_ref_area.csv")}
    occupations = {r["classif1"]: r["classif1.label"] for r in read_csv(raw / "ilostat_dic_classif1.csv")}
    statuses = {r["obs_status"]: r["obs_status.label"] for r in read_csv(raw / "ilostat_dic_obs_status.csv")}
    selected_codes = {"OCU_ISCO08_" + str(i) for i in range(10)}
    subset = [r for r in recent if r["source"].startswith("BA:") and r["sex"] == "SEX_T" and r["classif1"] in selected_codes]
    subset.sort(key=lambda r: (r["ref_area"], r["source"], r["time"], r["classif1"]))
    extract = []
    for row in subset:
        value = dict(row)
        value.update(ref_area_label=areas.get(row["ref_area"], ""),
                     source_label=sources.get((row["ref_area"], row["source"]), ""),
                     occupation_label=occupations.get(row["classif1"], ""),
                     status_label=statuses.get(row["obs_status"], ""))
        extract.append(value)
    write_csv(metrics / "labor_lfs_isco08_major_total_sex_2020plus.csv", extract,
              fields + ["ref_area_label", "source_label", "occupation_label", "status_label"])
    key_fields = ["ref_area", "source", "indicator", "sex", "classif1", "time"]
    duplicate_keys = sum(n - 1 for n in Counter(tuple(r[k] for k in key_fields) for r in recent).values() if n > 1)
    year_rows = []
    for year in sorted({r["time"] for r in recent}):
        group = [r for r in recent if r["time"] == year]
        chosen = [r for r in subset if r["time"] == year]
        year_rows.append({"year": year, "all_source_rows": len(group), "all_reference_areas": len({r["ref_area"] for r in group}),
                          "selected_lfs_rows": len(chosen), "selected_lfs_reference_areas": len({r["ref_area"] for r in chosen}),
                          "selected_break_flag_rows": sum(r["obs_status"] == "B" for r in chosen),
                          "selected_unreliable_flag_rows": sum(r["obs_status"] == "U" for r in chosen)})
    write_csv(metrics / "labor_coverage_by_year.csv", year_rows, list(year_rows[0]))
    area_rows = []
    for area in sorted({r["ref_area"] for r in subset}):
        group = [r for r in subset if r["ref_area"] == area]
        area_rows.append({"ref_area": area, "label": areas.get(area, ""), "rows": len(group),
                          "years": ";".join(sorted({r["time"] for r in group})),
                          "source_codes": ";".join(sorted({r["source"] for r in group})),
                          "break_flag_rows": sum(r["obs_status"] == "B" for r in group),
                          "unreliable_flag_rows": sum(r["obs_status"] == "U" for r in group)})
    write_csv(metrics / "labor_coverage_by_area.csv", area_rows, list(area_rows[0]))
    source_counts = Counter(sources.get((r["ref_area"], r["source"]), "UNMAPPED") for r in recent)
    audit = {
        "source_id": "ilostat_employment_annual", "indicator": "EMP_TEMP_SEX_OCU_NB_A",
        "source_update_date_from_directory": "2026-11-24", "unit": "thousands of employed persons, as published",
        "original_rows": len(all_rows), "original_reference_area_codes": len({r["ref_area"] for r in all_rows}),
        "original_year_min": min(int(r["time"]) for r in all_rows), "original_year_max": max(int(r["time"]) for r in all_rows),
        "original_columns": fields, "age_field_present": False,
        "filter_2020_onward": {"rows": len(recent), "reference_area_codes": len({r["ref_area"] for r in recent}),
            "years": sorted({int(r["time"]) for r in recent}), "observation_status_counts": dict(Counter(r["obs_status"] for r in recent)),
            "source_label_counts": dict(sorted(source_counts.items())), "classification_codes": sorted({r["classif1"] for r in recent}),
            "duplicate_rows_on_full_series_key": duplicate_keys},
        "published_narrow_extract": {"definition": "2020 onward; BA source prefix (labour-force survey family); total sex; ISCO-08 one-digit groups 0 through 9; no totals, unknown group, ISCO-88 or skill aggregate.",
            "rows": len(subset), "reference_area_codes": len({r["ref_area"] for r in subset}),
            "reference_area_source_pairs": len({(r["ref_area"], r["source"]) for r in subset}),
            "observation_status_counts": dict(Counter(r["obs_status"] for r in subset)),
            "source_labels": sorted({sources.get((r["ref_area"], r["source"]), "UNMAPPED") for r in subset}),
            "missing_numeric_values": sum(r["obs_value"] == "" for r in subset),
            "unmapped_source_rows": sum((r["ref_area"], r["source"]) not in sources for r in subset)},
        "warning": "Reference areas include countries, territories and aggregates in the source. Counts are published aggregate rows, not people or nationally representative individual samples.",
        "causal_estimation_performed": False, "ai_exposure_merge_performed": False,
        "limitations": ["No age field: cannot identify the 1990s/2000s birth cohorts or youth entrants.",
            "One-digit occupation groups are too broad for a direct match to detailed task exposure without a separately justified crosswalk.",
            "Recent source rows contain modelled estimates as well as surveys; never pool source families or regional aggregates as independent countries.",
            "The narrow extract still contains series breaks and unreliable observations, preserved with flags.",
            "Multiple sources per reference area and missing groups require adjudication before constructing a comparable panel.",
            "No adoption date/intensity or counterfactual is supplied; post-2022 employment changes cannot be attributed to AI here."]}
    dump(out / "labor_audit.json", audit)
    print(json.dumps({"metr_models": len(models), "labor_original_rows": len(all_rows), "labor_2020plus_rows": len(recent),
                      "labor_selected_rows": len(subset), "labor_selected_areas": len(area_rows), "duplicate_series_keys": duplicate_keys,
                      "source_mapping_missing": audit["published_narrow_extract"]["unmapped_source_rows"]}, indent=2))


if __name__ == "__main__":
    main()
