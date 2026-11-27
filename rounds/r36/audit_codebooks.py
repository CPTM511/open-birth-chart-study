"""Reacquire the public dictionaries for restricted Japanese live-birth files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from unicodedata import normalize

from openpyxl import load_workbook

from rounds.r27.archive_source import digest, read_json, require, write_json


HERE = Path(__file__).resolve().parent
PUBLIC_PORTAL = "https://www.e-stat.go.jp/microdata/available-data/onsite"
METADATA_DOWNLOAD = "https://www.e-stat.go.jp/microdata/available-data/file/download/meta"
SHEET = "個票データの項目（事項名）"
YEARS = (1974, *range(1990, 2010), 2023, 2025)
CLOCK_LABELS = {"時", "時間", "出生年月日時"}
REVIEWED_PLACE_LABELS = {
    "届出地", "住所地", "都道府県", "都道府県1", "都道府県2", "都道府県3", "保健所", "保健所1", "保健所2",
    "市区町村", "市区町村1", "市区町村2", "市区町村(種類)", "市区町村(順位)",
    "都道府県における順位", "県別一連番号", "地方公共団体コード", "場所の種別",
    "国内外(生まれたところ)",
}
CLOCK_TERMS = re.compile(r"[時分]|娩出")
PLACE_TERMS = re.compile(r"都道府県|保健所|届出地|住所地|市区町村|施設|場所|ところ|管轄|県別|地方公共団体|発生地|出生地")


def clean(value):
    return "" if value is None else normalize("NFKC", str(value)).strip()


@dataclass(frozen=True)
class Field:
    row: int
    number: int
    category: str
    label: str
    name: str
    position: int
    width: int
    code_sheet: str

    def labels(self):
        return {clean(x) for x in (self.category, self.label, self.name)}

    def locator(self):
        return {
            "worksheet_row": self.row,
            "field_number": self.number,
            "category": self.category,
            "label": self.label,
            "name": self.name,
            "one_based_byte_position": self.position,
            "bytes": self.width,
            "code_sheet": self.code_sheet or None,
        }


def fields(sheet):
    out = []
    next_position = 1
    for row_index, row in enumerate(sheet.values, 1):
        if type(row[0]) is not int:
            continue
        i, category, label, name, position, width, code_sheet = row[:7]
        field = Field(row_index, i, category, label, name, int(position), int(width), clean(code_sheet))
        require(field.number == len(out) + 1, f"Field-number sequence changes at Excel row {row_index}")
        require(field.position == next_position and field.width > 0,
                f"Fixed-width positions do not reconcile at Excel row {row_index}")
        require(bool(clean(name)), f"Field name is missing at Excel row {row_index}")
        next_position += field.width
        out.append(field)
    require(bool(out), "The publisher workbook has no fixed-width field list")
    return out


def code_table(workbook, field):
    require(field.code_sheet in workbook.sheetnames, f"Missing code table for {field.name}")
    entries = {}
    listed = False
    for raw_code, raw_label, *_ in workbook[field.code_sheet].values:
        code, label = clean(raw_code), clean(raw_label)
        if not listed:
            listed = (code, label) == ("符号", "符号内容")
            continue
        if not code and not label:
            continue
        require(code and label and code not in entries, f"Ambiguous code in the table for {field.name}")
        entries[code] = label
    require(bool(entries), f"Code table is empty for {field.name}")
    return entries


def audit_book(path):
    wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        inventory = fields(wb[SHEET])
        clock = sorted({label for field in inventory for label in field.labels() if CLOCK_TERMS.search(label)})
        place = sorted({label for field in inventory for label in field.labels() if PLACE_TERMS.search(label)})
        require(set(clock) <= CLOCK_LABELS, f"Unexpected time-related label in {path.name}: {clock}")
        require(set(place) <= REVIEWED_PLACE_LABELS, f"Unexpected place-related label in {path.name}: {place}")
        hour, = (field for field in inventory if clean(field.name) in {"時", "時間"})
        year, month, day = inventory[hour.number - 4:hour.number - 1]
        require([clean(field.label) for field in (year, month, day)] == ["年", "月", "日"] and
                all(field.width == 2 for field in (year, month, day, hour)),
                "Unexpected format for the full birth date and hour")
        sex, = (field for field in inventory if clean(field.name) == "性別")
        occurrence, = (field for field in inventory if clean(field.name) == "国内外(生まれたところ)")
        venue, = (field for field in inventory if clean(field.name) == "場所の種別")
        hour_codes = code_table(wb, hour)
        require(hour_codes.get("00-23") == "午前0時~午後11時" and len(hour_codes) in (2, 3),
                "The published time codes are not the reviewed hour-only convention")
        sex_codes = code_table(wb, sex)
        require(sex_codes == {"1": "男", "2": "女"}, "Unexpected birth-sex coding")
        occurrence_codes = code_table(wb, occurrence)
        require(occurrence_codes == {"1": "日本", "2": "日本外"}, "Unexpected occurrence-country coding")
        venue_codes = code_table(wb, venue)
        require(venue_codes == dict(zip("12345", ("病院", "診療所", "助産所", "自宅", "その他"), strict=True)),
                "Unexpected delivery venue group coding")
        return {
            "fields_checked": len(inventory),
            "time_related_labels": clock,
            "geography_related_labels": place,
            "birth_calendar_fields": [field.locator() for field in (year, month, day)],
            "birth_hour": {**hour.locator(), "codes": hour_codes},
            "sex": {**sex.locator(), "codes": sex_codes},
            "birth_country_group": {**occurrence.locator(), "codes": occurrence_codes},
            "delivery_venue_type": {**venue.locator(), "codes": venue_codes},
        }
    finally:
        wb.close()


def acquire(download_dir, entry):
    path = download_dir / f"{entry['code']}.xlsx"
    if not path.exists():
        part = path.with_suffix(".part.xlsx")
        subprocess.run([
            "curl", "-fsSL", "--retry", "1", "--max-time", "40", "-o", str(part),
            "-H", f"Referer: {PUBLIC_PORTAL}?governmentStatisticsCode=00450011",
            "--form-string", f"code={entry['code']}",
            "--form-string", f"version={entry['version']}",
            METADATA_DOWNLOAD,
        ], check=True)
        require(digest(part) == entry["sha256"], f"Publisher bytes changed for {entry['code']}")
        part.replace(path)
    require(digest(path) == entry["sha256"], f"Cached dictionary digest differs for {entry['code']}")
    return path


def study(download_dir, catalogue):
    require(tuple(sorted(map(int, catalogue["onsite_index"]))) == YEARS,
            "The release must include both target decades and all context snapshots")
    download_dir.mkdir(parents=True, exist_ok=True)
    datasets = {}
    for year in YEARS:
        entry = catalogue["onsite_index"][str(year)]
        require(entry["type"] == "出生票" and entry["format"] == "固定長",
                f"{year} is not the reviewed regular live-birth file")
        if entry["code"] not in datasets:
            path = acquire(download_dir, entry)
            datasets[entry["code"]] = {"years": [], "sha256": entry["sha256"], **audit_book(path)}
        item = datasets[entry["code"]]
        require(entry["sha256"] == item["sha256"], "Inconsistent codebook identity across years")
        item["years"].append(year)
    return {
        "public_metadata_only": True,
        "layout_worksheet": SHEET,
        "target_years": list(range(1990, 2010)),
        "comparison_years": [1974, 2023, 2025],
        "annual_catalogue_entries_checked": len(YEARS),
        "distinct_fixed_width_dictionaries": len(datasets),
        "birth_clock_resolution_in_reviewed_layouts": "hour",
        "minutes_in_reviewed_layouts": False,
        "birth_municipality_or_named_facility_in_reviewed_layouts": False,
        "layouts": datasets,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("downloads", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    write_json(args.output, study(args.downloads, read_json(HERE / "source_catalog.json")))


if __name__ == "__main__":
    main()
