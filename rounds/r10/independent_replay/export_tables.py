"""Export cohort contrasts and per-system means from the verified aggregate output."""
import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYSTEMS = ("Bazi", "Ziwei Doushu", "Qizheng Siyu", "Western astrology")


def write_table(path, rows):
    with path.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export(primary, output):
    release = json.loads((HERE / "prepared_receipt.json").read_bytes())
    groups = {s["slot"]: s for s in release["groups"]}
    targets = {t["slot"]: t for t in primary["targets"]}
    sensitivity = primary["reference_refit_sensitivity"]
    if set(groups) != set(targets) or primary["primary_family_size"] != 7 or sensitivity["draws"] != 999:
        raise ValueError("Incomplete independent replay")
    refits = {s["slot"]: s["full_reference_refit_percentile_range95"] for s in sensitivity["targets"]}
    contrasts = []
    sources = [("brazil2006_reference", primary["reference"])]
    for slot, group in groups.items():
        row = targets[slot]
        interval = row["sampling_interval"]
        raw95 = interval["delta_joint_interval95"]
        adjusted = interval["delta_joint_family_adjusted_interval"]
        refit = refits[slot]
        if row["n_source_records"] != 2000 or interval["draws"] != 9999:
            raise ValueError("Incorrect sample or draw count")
        contrasts.append({
            "slot": slot, "country": "BR" if slot.startswith("brazil") else "MX",
            "birth_year": group["target_birth_year"], "sample_records": row["n_source_records"],
            "eligible_source_records": group["eligible_population"], "modeled_record_years": row["modeled_record_years_total"],
            "joint_rate_percent": f'{100 * row["joint_rate"]:.9f}', "difference_from_brazil2006_pp": f'{100 * row["delta_joint_rate"]:.9f}',
            "conditional_95_low_pp": f"{100*raw95[0]:.9f}", "conditional_95_high_pp": f"{100*raw95[1]:.9f}",
            "seven_slot_adjusted_low_pp": f"{100*adjusted[0]:.9f}", "seven_slot_adjusted_high_pp": f"{100*adjusted[1]:.9f}",
            "shared_reference_refit_p025_pp": f"{100*refit[0]:.9f}", "shared_reference_refit_p975_pp": f"{100*refit[1]:.9f}",
            "historical_sampling_metadata_bytes_recovered": str(group["historical_metadata_recovered"]).lower(),
        })
        sources.append((slot, row))
    systems = []
    for slot, row in sources:
        for i, system in enumerate(SYSTEMS):
            systems.append({
                "slot": slot, "system": system, "mean_raw_score": f'{row["raw_system_means"][i]:.9f}',
                "difference_from_reference_raw": f'{row["delta_raw_system_means"][i]:.9f}',
                "mean_brazil2006_midcdf": f'{row["fixed_reference_system_means"][i]:.9f}',
                "difference_from_reference_midcdf": f'{row["delta_fixed_reference_system_means"][i]:.9f}',
            })
    output.mkdir(parents=True, exist_ok=True)
    write_table(output / "cohort_contrasts.csv", contrasts)
    write_table(output / "four_system_means.csv", systems)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("primary", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    export(json.loads(args.primary.read_bytes()), args.output)
