"""Cross-identify the registered names and seal matching publisher astrometry."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from decimal import Decimal
import gzip
from pathlib import Path
import re
import subprocess
from urllib.parse import urlencode

from rounds.r22.degrees import MANSIONS
from rounds.r27.archive_source import digest, read_json, require, write_json


HERE = Path(__file__).resolve().parent
STELLARIUM_REVISION = "61b5f160cc1ada854e094717fa4c8189db92bc09"
HISTORICAL_SOURCE = "https://press.uchicago.edu/books/HOC/HOC_V2_B2/HOC_VOLUME2_Book2_chapter13.pdf"
BASE_VIZIER = "https://vizier.cfa.harvard.edu/viz-bin/asu-tsv"
NASA_ARCHIVE = "https://heasarc.gsfc.nasa.gov/FTP/heasarc/dbase/tdat_files"
URLS = {
    "stellarium.json": f"https://raw.githubusercontent.com/Stellarium/stellarium/{STELLARIUM_REVISION}/skycultures/chinese/index.json",
    "bright-stars.tdat.gz": f"{NASA_ARCHIVE}/heasarc_bsc5p.tdat.gz",
    "hipparcos.tdat.gz": f"{NASA_ARCHIVE}/heasarc_hipparcos.tdat.gz",
}
# Stephenson's Table 13.1 uses Bayer or Flamsteed designations, in the order of MANSIONS.
HISTORICAL_NAMES = dict(zip(MANSIONS, (
    "Alp Vir", "Kap Vir", "Alp Lib", "Pi Sco", "Sig Sco", "Mu Sco", "Gam Sgr",
    "Phi Sgr", "Bet Cap", "Eps Aqr", "Bet Aqr", "Alp Aqr", "Alp Peg", "Gam Peg",
    "Zet And", "Bet Ari", "35 Ari", "17 Tau", "Eps Tau", "Phi1 Ori", "Del Ori",
    "Mu Gem", "The Cnc", "Del Hya", "Alp Hya", "Ups Hya", "Alp Crt", "Gam Crv",
), strict=True))
POSITION_FIELDS = ("ra_deg", "dec_deg", "pm_ra", "pm_dec")
VIZIER_FIELDS = ("HIP", "RAICRS", "DEICRS", "pmRA", "pmDE")
BRANCHES = ("stephenson_maeyama", "stellarium_chinese")


def tdat_rows(path):
    """Read a documented HEASARC ASCII table and verify that it ended cleanly."""
    with gzip.open(path, "rt", encoding="ascii") as stream:
        fields = next(line for line in stream if line.startswith("line[1] =")).split("=", 1)[1].split()
        next(line for line in stream if line.strip() == "<DATA>")
        for line in stream:
            if line.strip() == "<END>":
                break
            values = line.rstrip("\n").split("|")
            require(values[-1] == "", f"Missing row delimiter in {path.name}")
            yield dict(zip(fields, values[:-1], strict=True))
        else:
            raise ValueError(f"Missing table terminator in {path.name}")
        # Reading to EOF also verifies the compressed checksum.
        stream.read()


def designation_matches(target, listed):
    value, constellation = target.split()
    listed = listed.replace(" ", "")
    if not listed.endswith(constellation):
        return False
    match = re.fullmatch(r"(\d*)([A-Za-z]+)?(\d?)", listed[:-3])
    if not match:
        return False
    flamsteed, bayer, component = match.groups()
    if value.isdigit():
        return flamsteed == value
    return bayer == value if value.isalpha() else (bayer or "") + component == value


def stellarium_bindings(path):
    scheme = read_json(path)["lunar_system"]
    labels = "".join(item["native"] for item in scheme["names"])
    require(labels == MANSIONS and scheme["coordsys"] == "equatorial", "Unexpected Stellarium mansion definition")
    stars = scheme["defining_stars"]
    require(len(set(stars)) == 28, "Stellarium lacks 28 distinct HIP identifiers")
    return dict(zip(labels, stars, strict=True))


def bright_star_bindings(path):
    targets = defaultdict(list)
    for row in tdat_rows(path):
        for label, target in HISTORICAL_NAMES.items():
            if designation_matches(target, row["alt_name"]):
                require(row["hd"] and row["vmag"], f"Missing HD or magnitude for {row['alt_name']}")
                targets[label].append({
                    "name": " ".join(row["alt_name"].split()), "hd": int(row["hd"]),
                    "hr": int(row["hr"]), "visual_magnitude": row["vmag"],
                })
    return targets


def nasa_positions(path, requested_hip, requested_hd):
    by_hd, astrometry = defaultdict(list), {}
    for row in tdat_rows(path):
        hip = int(row["hip_number"])
        hd = int(row["hd_id"]) if row["hd_id"] else None
        if hip in requested_hip or hd in requested_hd:
            require(hip not in astrometry, f"Duplicate HIP {hip}")
            if all(row[field] for field in POSITION_FIELDS):
                astrometry[hip] = tuple(Decimal(row[field]) for field in POSITION_FIELDS)
                by_hd[hd].append(hip)
    return by_hd, astrometry


def cross_identify(bsc, by_hd):
    historical = {}
    for label in MANSIONS:
        candidates = sorted(bsc[label], key=lambda row: Decimal(row["visual_magnitude"]))
        require(bool(candidates), f"No Bright Star Catalog entry for {label}")
        require(len(candidates) == 1 or Decimal(candidates[0]["visual_magnitude"])
                < Decimal(candidates[1]["visual_magnitude"]), f"Indeterminate primary member for {label}")
        candidates_with_hip = []
        for row in candidates:
            matches = by_hd[row["hd"]]
            require(len(matches) <= 1, f"HD {row['hd']} has ambiguous Hipparcos matches")
            candidates_with_hip.append(dict(row, hip=matches[0] if matches else None))
        require(candidates_with_hip[0]["hip"] is not None, f"Primary member lacks Hipparcos astrometry for {label}")
        historical[label] = {
            "table_designation": HISTORICAL_NAMES[label],
            "primary": candidates_with_hip[0],
            "alternates": candidates_with_hip[1:],
        }
    return historical


def vizier_url(hip_ids):
    query = urlencode({"-source": "I/239/hip_main", "-out": ",".join(VIZIER_FIELDS),
                       "-out.max": 100, "HIP": ",".join(map(str, sorted(hip_ids)))})
    return f"{BASE_VIZIER}?{query}"


def vizier_positions(path):
    with path.open(encoding="utf-8", newline="") as stream:
        active_rows = (line for line in stream if line.strip() and not line.startswith("#"))
        rows = csv.reader(active_rows, delimiter="\t")
        require(tuple(next(rows)) == VIZIER_FIELDS, "Unexpected VizieR fields")
        require([field.strip() for field in next(rows)] == ["", "deg", "deg", "mas/yr", "mas/yr"],
                "Unexpected VizieR units")
        next(rows)  # ASCII field separator.
        result = {}
        for identifier, *values in rows:
            hip = int(identifier)
            require(hip not in result and len(values) == len(POSITION_FIELDS),
                    f"VizieR has missing fields or duplicate HIP {hip}")
            result[hip] = tuple(Decimal(value.strip()) for value in values)
        return result


def download(url, output):
    temporary = output.with_suffix(output.suffix + ".partial")
    subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "110",
                    "--output", str(temporary), url], check=True)
    temporary.replace(output)


def extract(job, *, fetch):
    if fetch:
        job.mkdir(parents=True, exist_ok=True)
        for name, url in URLS.items():
            download(url, job / name)
    stellarium = stellarium_bindings(job / "stellarium.json")
    bsc = bright_star_bindings(job / "bright-stars.tdat.gz")
    by_hd, nasa = nasa_positions(job / "hipparcos.tdat.gz", set(stellarium.values()),
                                {row["hd"] for group in bsc.values() for row in group})
    historical = cross_identify(bsc, by_hd)
    hips = set(stellarium.values()) | {
        row["hip"] for group in historical.values() for row in [group["primary"], *group["alternates"]]
        if row["hip"] is not None
    }
    url = vizier_url(hips)
    if fetch:
        download(url, job / "vizier.tsv")
    vizier = vizier_positions(job / "vizier.tsv")
    require(set(vizier) == hips, f"Unexpected VizieR HIP IDs: {sorted(hips ^ set(vizier))}")
    for hip, coordinates in vizier.items():
        require(nasa.get(hip) == coordinates, f"NASA and CDS differ in astrometry for HIP {hip}")
    return {
        "historical_table": {"url": HISTORICAL_SOURCE, "locator": "Table 13.1, printed page 517"},
        "stellarium_revision": STELLARIUM_REVISION,
        "catalogue": "Hipparcos Main Catalogue, ESA 1997 (CDS I/239), ICRS at J1991.25",
        "sources": {name: {"url": address, "sha256": digest(job / name)}
                    for name, address in {**URLS, "vizier.tsv": url}.items()},
        "published_numeric_fields_compared": list(POSITION_FIELDS),
        "stephenson_maeyama": historical,
        "stellarium_chinese": stellarium,
        "astrometry": {str(hip): dict(zip(POSITION_FIELDS, map(str, vizier[hip]), strict=True))
                       for hip in sorted(hips)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True, help="directory for the four original files")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true", help="reacquire all four downloads before extraction")
    args = parser.parse_args()
    write_json(args.output, extract(args.job, fetch=args.fetch))


if __name__ == "__main__":
    main()
