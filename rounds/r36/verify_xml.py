"""Verify the reported metadata fields directly in the workbooks' native XML."""

from __future__ import annotations

import argparse
from pathlib import Path
from posixpath import join
from unicodedata import normalize
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from rounds.r27.archive_source import digest, read_json, require, write_json


HERE = Path(__file__).resolve().parent
XLSX = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def sheet_map(archive):
    relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {}
    for entry in relations:
        target = entry.get("Target")
        targets[entry.get("Id")] = target[1:] if target.startswith("/") else join("xl", target)
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    return {sheet.get("name"): targets[sheet.get(RID)] for sheet in workbook.iter(XLSX + "sheet")}


def written_text(item):
    # Ruby annotations give the reading of the label, not another part of its text.
    return "".join(t.text or "" for child in item if child.tag != XLSX + "rPh"
                   for t in child.iter(XLSX + "t"))


def strings(archive):
    try:
        values = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [written_text(item) for item in values]


def cells(archive, file, shared):
    sheet = ET.fromstring(archive.read(file))
    out = {}
    for cell in sheet.iter(XLSX + "c"):
        value = cell.findtext(XLSX + "v", "")
        style = cell.get("t")
        if style == "s":
            value = shared[int(value)]
        if style == "inlineStr":
            value = written_text(cell.find(XLSX + "is"))
        out[cell.get("r")] = value
    return out


def canonical(raw):
    return normalize("NFKC", raw).strip()


def verify(downloads, result_path):
    result = read_json(result_path)
    catalog = read_json(HERE / "source_catalog.json")["onsite_index"]
    expected_codes = {}
    for year, entry in catalog.items():
        expected_codes.setdefault(entry["code"], []).append(int(year))
        require(result["layouts"][entry["code"]]["sha256"] == entry["sha256"], "Catalogue digest differs")
    require(set(expected_codes) == set(result["layouts"]), "Audited inventory has unexpected editions")
    checked_fields = 0
    for code, item in result["layouts"].items():
        require(sorted(expected_codes[code]) == item["years"], f"The years for {code} differ")
        source = downloads / f"{code}.xlsx"
        require(digest(source) == item["sha256"], f"Unexpected archive digest for {code}")
        with ZipFile(source) as z:
            shared = strings(z)
            tabs = sheet_map(z)
            original = cells(z, tabs[result["layout_worksheet"]], shared)
            source_rows = [int(k[1:]) for k, value in original.items()
                           if k.startswith("A") and k[1:].isdigit() and value.isdigit()]
            require(len(source_rows) == item["fields_checked"], f"Field count differs for {code}")
            for field in [*item["birth_calendar_fields"], item["birth_hour"], item["sex"],
                          item["birth_country_group"], item["delivery_venue_type"]]:
                r = field["worksheet_row"]
                view = (str(field["field_number"]), field["category"], field["label"], field["name"],
                        str(field["one_based_byte_position"]), str(field["bytes"]))
                require(r in source_rows and tuple(original[f"{c}{r}"] for c in "ABCDEF") == view,
                        f"Published field locator differs for {code} row {r}")
                if field["code_sheet"]:
                    require(original[f"G{r}"] == field["code_sheet"], f"Code sheet differs for {code} row {r}")
                if "codes" in field:
                    codes = cells(z, tabs[field["code_sheet"]], shared)
                    first, = (int(k[1:]) + 1 for k, value in codes.items()
                              if k.startswith("A") and k[1:].isdigit() and value.strip() == "符号")
                    recoded = {canonical(value): canonical(codes[f"B{k[1:]}"])
                               for k, value in codes.items()
                               if k.startswith("A") and k[1:].isdigit() and int(k[1:]) >= first and value.strip()}
                    require(field["codes"] == recoded, f"Published values differ for {code} row {r}")
                checked_fields += 1
    return {"method": "native Office Open XML cells, independent of the main workbook reader",
            "distinct_layouts": len(result["layouts"]), "rechecked_fields": checked_fields,
            "metadata_only": True, "results_sha256": digest(result_path)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("downloads", type=Path)
    p.add_argument("results", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    write_json(args.output, verify(args.downloads, args.results))


if __name__ == "__main__":
    main()
