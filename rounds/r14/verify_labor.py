"""Re-read ACS classifications and independently verify aggregate estimates."""
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import file_digest
from io import TextIOWrapper
import json
from math import fsum, sqrt
from pathlib import Path
from zipfile import ZipFile


def check(condition, description):
    if not condition:
        raise ValueError(description)


def recalculate_counts(path, sectors):
    sector_map = {str(i): str(i) for i in range(10, 100)}
    sector_map.update({"32": "31", "33": "31", "45": "44", "49": "48"})
    totals, level, occupations = Counter(), Counter(), Counter()
    raw = 0
    with ZipFile(path) as archive:
        for member in ("psam_pusb.csv", "psam_pusa.csv"):
            with TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                header = next(reader)
                indices = [header.index(key) for key in ("AGEP", "ESR", "COW", "NAICSP", "OCCP", "PWGTP")]
                for row in reader:
                    raw += 1
                    age = int(row[indices[0]])
                    if age < 20 or age >= 55:
                        continue
                    if row[indices[1]] not in {"1", "2"} or row[indices[2]] not in {"1", "2"}:
                        continue
                    band = "20–29" if age < 30 else "30–39" if age < 40 else "40–54"
                    pw = int(row[indices[-1]])
                    totals[band] += pw
                    sector = sector_map.get(row[indices[3]].strip()[:2])
                    if sector not in sectors:
                        continue
                    level[band, sector, "n"] += 1
                    level[band, sector, "w"] += pw
                    occupation = row[indices[4]].strip()
                    if occupation and occupation != "N.A.":
                        occupations[band, occupation.zfill(4), "n"] += 1
                        occupations[band, occupation.zfill(4), "w"] += pw
    return totals, level, occupations, raw


def run(args):
    out = args.results
    release = json.loads((out / "results.json").read_bytes())
    with (out / "acs_age_sector_weights.csv").open(encoding="utf-8") as f:
        source = list(csv.DictReader(f))
    with (out / "acs_age_occupation_counts.csv").open(encoding="utf-8") as f:
        occupations = list(csv.DictReader(f))
    with (out / "btos_2024_sector_waves.csv").open(encoding="utf-8") as f:
        waves = list(csv.DictReader(f))
    rates = defaultdict(list)
    for entry in waves:
        rates[entry["sector"]].append(float(entry["employer_yes_percent"]))
    included = set(release["included_sectors"])
    rate_mean = {s: fsum(rates[s]) / len(rates[s]) for s in included}
    numeric_comparisons = 0
    for y in ("2023", "2024"):
        year = release["acs_age_industry_context"][y]
        totals, counts, occ, raw = recalculate_counts(args.sources / f"acs-{y}-person.zip", included)
        check(raw == year["records"]["archive_person_rows"], "Raw archive counts differed")
        independently_published = {(band, code): (n, occ[band, code, "w"])
                                   for (band, code, key), n in occ.items() if key == "n" and n >= 100}
        from_release = {(r["age"], r["census_occp"]): (int(r["sample_records"]), int(r["weighted_workers"]))
                        for r in occupations if r["acs_year"] == y}
        check(independently_published == from_release, "Detailed employment estimates differ")
        numeric_comparisons += len(from_release) * 2
        results = {}
        for band, expected in year["age_context_percent"].items():
            matched = [r for r in source if r["acs_year"] == y and r["age"] == band]
            check({r["sector"] for r in matched} == included and len(matched) == len(included), "Sector support differs")
            for cell in matched:
                sector = cell["sector"]
                check(int(cell["PWGTP"]) == counts[band, sector, "w"]
                      and int(cell["sample_records"]) == counts[band, sector, "n"],
                      "Independently re-read sector denominator differs")
                numeric_comparisons += 2
            check(totals[band] == expected["acs_private_workers_before_sector_join"], "Unmatched denominator differs")
            weights = ["PWGTP"] + [f"PWGTP{i}" for i in range(1, 81)]
            values = [fsum(int(c[w]) * rate_mean[c["sector"]] for c in matched) /
                      sum(int(c[w]) for c in matched) for w in weights]
            check(abs(values[0] - expected["estimate"]) < 1e-12, "Weighted context differs")
            se = sqrt(sum((v - values[0]) ** 2 for v in values[1:]) / 20)
            check(abs(se - expected["conditional_acs_se"]) < 1e-12, "SDR variance differs")
            results[band] = values
            numeric_comparisons += 3
        difference = [a - b for a, b in zip(results["20–29"], results["40–54"], strict=True)]
        contrast = year["age_20_29_minus_age_40_54_pp"]
        check(abs(difference[0] - contrast["estimate"]) < 1e-12, "Context contrast differs")
        se = sqrt(sum((v - difference[0]) ** 2 for v in difference[1:]) / 20)
        check(abs(se - contrast["conditional_acs_se"]) < 1e-12, "Joint replicate contrast differs")
        numeric_comparisons += 2
    with (out / "results.json").open("rb") as stream:
        result_hash = file_digest(stream, "sha256").hexdigest()
    receipt = {
        "status": "passed", "result_sha256": result_hash, "numeric_comparisons": numeric_comparisons,
        "independent_acs_counts": "Both entire publisher archives re-read in reverse member order.",
        "acs_replicate_variance": "Verified all age and contrast SDR calculations from exact sector aggregate weights.",
        "scope_limit": "Replicate source weights and the BTOS published estimate extraction were shared.",
    }
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("sources", "results", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    run(p.parse_args())
