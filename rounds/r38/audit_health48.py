"""Inspect the public Health48 dictionaries without reading any participant rows."""

from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
from unicodedata import normalize
from zipfile import ZipFile

import openpyxl
import xlrd


PACKAGE_SHA256 = "c9c9284f29b106b66d2b8e7c59a299e8e6136ceaa1583cb547f677433035b951"
SURVEY_YEARS = (2005, 2007, 2008, 2010, 2013, 2017, 2022, 2023, 2024)
BASELINE_FIELDS = ("TOWN", "Sampleid", "REGION", "B_SEX", "B_yy", "B_mm", "B_dd", "E10a")
SEARCHES = {
    "birth_clock": re.compile(
        r"出生.{0,5}(?:時刻|鐘點|幾點|時分|時間|小時)|"
        r"生[產産]|分娩", re.IGNORECASE
    ),
    "birth_place": re.compile(
        r"出生(?:地|場所|醫院|院所|縣市)|"
        r"(?:生[產産]|分娩).{0,5}(?:地點|場所|醫院|院所)|"
        r"出生時的居住行政區", re.IGNORECASE
    ),
    "birth_date": re.compile(r"出生(?:日期|日|年|月)|生日|BIRTH_DATE", re.IGNORECASE),
}


def member_path(info):
    name = info.filename
    if not info.flag_bits & 0x800:
        name = name.encode("cp437").decode("big5")
    return PurePosixPath(name)


def read_codebook(content, suffix):
    if suffix == ".xls":
        book = xlrd.open_workbook(file_contents=content)
        return {sheet.name: [sheet.row_values(index) for index in range(sheet.nrows)] for sheet in book.sheets()}
    with BytesIO(content) as stream:
        book = openpyxl.load_workbook(stream, read_only=True, data_only=True)
        try:
            return {sheet.title: list(sheet.values) for sheet in book.worksheets}
        finally:
            book.close()


def compact(cell):
    return " ".join(normalize("NFKC", str(cell) if cell is not None else "").split())


def inspect(package):
    if sha256(package.read_bytes()).hexdigest() != PACKAGE_SHA256:
        raise ValueError("Source ZIP differs from the documented release")
    survey = {}
    linkage = {}
    baseline = {}
    with ZipFile(package) as archive:
        if archive.testzip() is not None:
            raise ValueError("Invalid member checksum in the public documentation package")
        for info in archive.infolist():
            if info.is_dir():
                continue
            path = member_path(info)
            is_survey = "主問卷編碼簿" in path.name
            is_linkage = "健保連結同意檔欄位說明" in path.name
            if not (is_survey or is_linkage):
                continue
            if path.suffix not in {".xls", ".xlsx"}:
                raise ValueError("Unexpected codebook format")
            relative = PurePosixPath(*path.parts[1:])
            year = "base" if len(relative.parts) == 1 else str(1911 + int(relative.parts[0]))
            bucket = survey if is_survey else linkage
            if year in bucket:
                raise ValueError("Unexpected additional codebook for an audited year")
            contents = archive.read(info)
            sheets = read_codebook(contents, path.suffix)
            item = {"member": relative.as_posix(), "sha256": sha256(contents).hexdigest(), "sheets": len(sheets)}
            if is_survey:
                item["semantic_review_row_counts"] = {key: 0 for key in SEARCHES}
            for sheet, rows in sheets.items():
                for index, raw in enumerate(rows, 1):
                    cells = [compact(cell) for cell in raw]
                    if is_survey:
                        for key, pattern in SEARCHES.items():
                            item["semantic_review_row_counts"][key] += any(pattern.search(cell) for cell in cells[1:])
                    if is_survey and year == "2005" and cells and cells[0] in BASELINE_FIELDS:
                        variable, _, _, label, options, note = (cells + [""] * 6)[:6]
                        if variable in baseline:
                            raise ValueError("A baseline field appears more than once")
                        baseline[variable] = {"sheet": sheet, "row": index, "label": label,
                                              "release_note": note, "options": options if variable == "REGION" else ""}
            bucket[year] = item
    if (sorted(map(int, survey)) != list(SURVEY_YEARS) or set(linkage) != {"base", "2022", "2023", "2024"}
            or set(baseline) != set(BASELINE_FIELDS)):
        raise ValueError("Unexpected survey, linkage or baseline field coverage")
    return {"survey": dict(sorted(survey.items())), "linkage": dict(sorted(linkage.items())), "baseline": baseline}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.package), ensure_ascii=False, indent=2))
