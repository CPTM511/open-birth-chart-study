"""Link ACS occupational employment to observed, fixed BTOS industry context."""
import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import file_digest
from io import TextIOWrapper
import json
import math
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import numpy as np

HERE = Path(__file__).resolve().parent
AGE_BANDS = ("20–29", "30–39", "40–54")
SECTORS = ("21", "22", "23", "31", "42", "44", "51", "53", "54", "55", "56", "61", "62", "71", "72")
WEIGHTS = ("PWGTP",) + tuple(f"PWGTP{i}" for i in range(1, 81))
NS = "{*}"


def digest(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sheet_rows(archive, name):
    # Verify the semantic sheet name before using the publisher's internal ID.
    w = ET.fromstring(archive.read("xl/workbook.xml"))
    matches = [e for e in w.iterfind(".//" + NS + "sheet") if e.get("name") == name]
    require(len(matches) == 1, "Required BTOS worksheet missing: " + name)
    sheet_id = matches[0].get("sheetId")
    strings = []
    if "xl/sharedStrings.xml" in archive.namelist():
        table = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = ["".join(v.text or "" for v in e.iterfind(".//" + NS + "t")) for e in table]
    page = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet_id}.xml"))
    for row in page.iterfind(".//" + NS + "row"):
        values = {}
        for cell in row:
            col = re.match(r"[A-Z]+", cell.get("r")).group()
            raw = cell.findtext(NS + "v", default="")
            kind = cell.get("t")
            if kind == "s":
                raw = strings[int(raw)]
            elif kind == "inlineStr":
                raw = "".join(t.text or "" for t in cell.iterfind(".//" + NS + "t"))
            values[col] = raw.strip()
        yield values


def spreadsheet_date(text):
    if text.isdecimal():
        return date(1899, 12, 30) + timedelta(days=int(text))
    for form in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, form).date()
        except ValueError:
            pass
    raise ValueError("Unrecognized BTOS date label: " + text)


def decimal_if_published(text):
    try:
        v = Decimal(text.rstrip("%"))
    except InvalidOperation:
        return None
    return v if v.is_finite() and v >= 0 else None


def business_rates(path):
    with ZipFile(path) as archive:
        dates = list(sheet_rows(archive, "Collection and Reference Dates"))
        require([dates[0].get(k) for k in "AE"] == ["Smpdt", "Ref End"], "BTOS reference-date scheme changed")
        waves = {r["A"]: spreadsheet_date(r["E"]).isoformat()
                 for r in dates[1:] if r.get("A", "").isdigit() and r.get("E") and spreadsheet_date(r["E"]).year == 2024}
        estimates = list(sheet_rows(archive, "Sector Estimates"))
    columns = {label: col for col, label in estimates[0].items() if label in waves}
    require(set(columns) == set(waves) and 24 <= len(waves) <= 27, "Unexpected number of 2024 waves")
    rows = {}
    for row in estimates[1:]:
        if row.get("B") != "7" or row.get("A") not in SECTORS:
            continue
        require("in producing goods or services" in row.get("C", "")
                and "last two weeks" in row.get("C", "").lower(), "BTOS wording mismatch")
        key = row["A"], row.get("E", "").lower()
        require(key not in rows, "Repeated question answer row")
        rows[key] = row
    stats, wave_rows = {}, []
    for sector in SECTORS:
        series, missing = [], []
        for wave, ref_end in sorted(waves.items(), key=lambda x: x[1]):
            col = columns[wave]
            choices = [decimal_if_published(rows[sector, a].get(col, "")) for a in ("yes", "no", "do not know")]
            if any(x is None for x in choices):
                missing.append(wave)
                continue
            total = sum(choices)
            if abs(total - 1) <= Decimal("0.004"):
                rate = choices[0] * 100
            elif abs(total - 100) <= Decimal("0.4"):
                rate = choices[0]
            else:
                raise ValueError("BTOS answer shares use unsupported scale or denominator")
            require(0 <= rate <= 100, "Invalid employer rate")
            series.append(rate)
            wave_rows.append((sector, wave, ref_end, float(rate)))
        stats[sector] = {
            "waves_used": len(series), "missing_waves": missing, "included": len(series) >= 12,
            "mean_employer_yes_percent": float(sum(series) / len(series)) if len(series) >= 12 else None,
            "minimum_wave_percent": float(min(series)) if series else None,
            "maximum_wave_percent": float(max(series)) if series else None,
        }
    return stats, wave_rows


def age_band(age):
    return int(age >= 30) + int(age >= 40)


def naics_sector(code):
    lead = code.strip()[:2]
    return {"32": "31", "33": "31", "45": "44", "49": "48"}.get(lead, lead)


def acs_data(path, sectors):
    by_age_sector = np.zeros((3, len(sectors), len(WEIGHTS)), dtype=np.int64)
    person_counts = np.zeros((3, len(sectors)), dtype=np.int64)
    all_workers = np.zeros((3, 2), dtype=np.int64)
    occupation = Counter()
    audit = Counter()
    indexes = {v: i for i, v in enumerate(sectors)}
    with ZipFile(path) as archive:
        require([n for n in sorted(archive.namelist()) if n.endswith(".csv")] == ["psam_pusa.csv", "psam_pusb.csv"],
                "Verify the national one-year ACS person archives")
        for member in ("psam_pusa.csv", "psam_pusb.csv"):
            with TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="") as file:
                reader = csv.reader(file)
                header = {name: i for i, name in enumerate(next(reader))}
                age_c, esr_c, cow_c, naics_c, occ_c, weight_c = [
                    header[k] for k in ("AGEP", "ESR", "COW", "NAICSP", "OCCP", "PWGTP")]
                weight_cols = [header[k] for k in WEIGHTS]
                for row in reader:
                    audit["archive_person_rows"] += 1
                    age = int(row[age_c])
                    if not (20 <= age <= 54 and row[esr_c] in ("1", "2") and row[cow_c] in ("1", "2")):
                        continue
                    i = age_band(age)
                    w = int(row[weight_c])
                    require(w > 0, "Invalid full sample person weight")
                    all_workers[i] += (1, w)
                    sector = naics_sector(row[naics_c])
                    if sector not in indexes:
                        audit["unmatched_sector_rows"] += 1
                        if not sector.isdigit() or sector == "00":
                            audit["unknown_sector"] += 1
                        elif sector in SECTORS:
                            audit["insufficient_btos_waves"] += 1
                        else:
                            audit["excluded_sector_scope"] += 1
                        continue
                    j = indexes[sector]
                    by_age_sector[i, j] += np.fromiter((int(row[k]) for k in weight_cols), dtype="int64", count=81)
                    person_counts[i, j] += 1
                    code = row[occ_c].strip()
                    if code and code != "N.A.":
                        occupation[i, code.zfill(4), "sample"] += 1
                        occupation[i, code.zfill(4), "weighted"] += w
                    else:
                        audit["matched_sector_rows_missing_occupation"] += 1
    audit["eligible_private_worker_sample_rows"] = int(all_workers[:, 0].sum())
    audit["matched_sector_rows"] = int(person_counts.sum())
    require(audit["eligible_private_worker_sample_rows"] == audit["matched_sector_rows"] + audit["unmatched_sector_rows"],
            "ACS classifications failed conservation")
    return by_age_sector, person_counts, all_workers, occupation, dict(audit)


def summarize_context(sector_counts, rates):
    exposure = np.einsum("asr,s->ar", sector_counts, rates) / sector_counts.sum(axis=1)
    def estimate(a):
        se = math.sqrt(4 / 80 * float(np.square(a[1:] - a[0]).sum()))
        return {"estimate": float(a[0]), "conditional_acs_se": se,
                "conditional_acs_95": [float(a[0] - 1.96 * se), float(a[0] + 1.96 * se)]}
    return {b: estimate(exp) for b, exp in zip(AGE_BANDS, exposure, strict=True)}, estimate(exposure[0] - exposure[2])


def write_csv(path, header, rows):
    with path.open("x", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def run(args):
    protocol_path = HERE / "protocol.json"
    require(digest(protocol_path) == args.registration_sha256, "Use the GitHub-verified registration")
    protocol = json.loads(protocol_path.read_bytes())
    for name, expected in protocol["files_sha256"].items():
        require(digest(HERE / name) == expected, "Registered method changed")
    files = {name: args.sources / name for name in protocol["archive_sha256"]}
    for name, path in files.items():
        require(digest(path) == protocol["archive_sha256"][name], "Official input hash differs: " + name)
    btos, waves = business_rates(files["btos-ai-original.xlsx"])
    sectors = tuple(s for s in SECTORS if btos[s]["included"])
    require(len(sectors) >= 12, "Insufficient harmonized industry coverage")
    args.output.mkdir(mode=0o700)
    weights_out, occupations_out, people = [], [], {}
    for year in (2023, 2024):
        weights, samples, all_eligible, occupations, audit = acs_data(files[f"acs-{year}-person.zip"], sectors)
        dictionary = json.loads(files[f"occp-{year}.json"].read_bytes())
        require(dictionary["name"] == "OCCP", "Wrong Census occupation dictionary")
        labels = {k.zfill(4): v for k, v in dictionary["values"]["item"].items()}
        rates = [btos[key]["mean_employer_yes_percent"] for key in sectors]
        age_context, younger_minus_older = summarize_context(weights, rates)
        for i, band in enumerate(AGE_BANDS):
            total = int(weights[i, :, 0].sum())
            age_context[band].update(acs_matched_workers=total,
                acs_private_workers_before_sector_join=int(all_eligible[i, 1]),
                age_sector_match_share=total / int(all_eligible[i, 1]), matched_source_records=int(samples[i].sum()))
            for j, sector in enumerate(sectors):
                weights_out.append([year, band, sector, int(samples[i, j]), *weights[i, j].tolist()])
        for (i, code, k), value in sorted(occupations.items()):
            if k == "sample" and value >= 100:
                occupations_out.append([year, AGE_BANDS[i], code, labels.get(code, ""),
                                        value, occupations[i, code, "weighted"]])
        people[str(year)] = {"age_context_percent": age_context,
                             "age_20_29_minus_age_40_54_pp": younger_minus_older, "records": audit}
        print(f"{year}: {audit['archive_person_rows']} rows streamed, {audit['matched_sector_rows']} eligible matched.", flush=True)
    write_csv(args.output / "btos_2024_sector_waves.csv", ["sector", "wave", "reference_end", "employer_yes_percent"], waves)
    write_csv(args.output / "acs_age_sector_weights.csv", ["acs_year", "age", "sector", "sample_records", *WEIGHTS], weights_out)
    write_csv(args.output / "acs_age_occupation_counts.csv",
              ["acs_year", "age", "census_occp", "publisher_label", "sample_records", "weighted_workers"], occupations_out)
    result = {
        "registration_sha256": args.registration_sha256,
        "btos_reference_year": 2024, "btos_question": "7 Yes, used AI in producing goods or services",
        "btos_fixed_sector_context": btos, "included_sectors": list(sectors),
        "acs_age_industry_context": people,
        "detailed_occupation_rows_n_at_least_100": len(occupations_out),
        "scope": "Private wage and salary workers in harmonized industries. ACS conditional uncertainty holds the BTOS "
                 "means fixed. Sector-level share of employers does not measure individual worker usage.",
    }
    with (args.output / "results.json").open("x", encoding="utf8") as f:
        json.dump(result, f, ensure_ascii=False, allow_nan=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--registration-sha256", required=True)
    run(p.parse_args())
