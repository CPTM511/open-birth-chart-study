"""Reread scan cells implicated by the table checks with a second OCR engine."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from pathlib import Path
from shutil import copyfile
import subprocess
from tempfile import TemporaryDirectory

from rounds.r27.archive_source import read_json, require

from .grid_reads import read_page
from .isolated_cells import cell_file, collect_cells


def selected_slots(diagnostics):
    slots = defaultdict(set)
    for path in diagnostics:
        report = read_json(path)
        for entry in report["missing_slots"] + report["suggestions"]:
            page, day, column = entry["location"]
            slots[page].add((day, column))
    return slots


def prepare_crops(pages, crops, diagnostics):
    for name, slots in sorted(selected_slots(diagnostics).items()):
        page = pages / f"{name}.json"
        first, x, y = read_page(page)
        collect_cells(page.with_suffix(".png"), crops, sorted(slots), x, y, len(first[0]))
        for day, column in sorted(slots):
            crop = cell_file(crops, name, day, column)
            if crop.is_file() and not crop.with_suffix(".tesseract").is_file():
                yield crop


def read_edition_result(path, page_count):
    words = defaultdict(list)
    pages = set()
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            page = int(row["page_num"])
            if row["level"] == "1":
                require(page not in pages, "Tesseract reported a duplicate crop page")
                pages.add(page)
            elif row["level"] == "5":
                words[page].append(row["text"])
    require(pages == set(range(1, page_count + 1)), "Tesseract page indices do not match the crop list")
    return {page: value[0] for page, value in words.items()
            if len(value) == 1 and value[0].isascii() and value[0].isdigit()}


def reread(pages, crops, diagnostics, tesseract, scratch):
    sources = list(prepare_crops(pages, crops, diagnostics))
    if not sources:
        return 0, 0
    with TemporaryDirectory(dir=scratch) as temporary:
        work = Path(temporary).resolve()
        inputs = [work / source.name for source in sources]
        for original, copy in zip(sources, inputs, strict=True):
            copyfile(original, copy)
        filelist = work / "cropped_pages.txt"
        filelist.write_text("".join(f"{path}\n" for path in inputs), encoding="utf-8")
        result = work / "ocr"
        completed = subprocess.run([tesseract, str(filelist), str(result), "--psm", "7",
                                    "-c", "tessedit_char_whitelist=0123456789", "tsv"],
                                   stderr=subprocess.PIPE, check=False, text=True)
        require(completed.returncode == 0, f"Tesseract failed: {completed.stderr[-1000:]}")
        recognized = read_edition_result(result.with_suffix(".tsv"), len(sources))
    for page, raw in recognized.items():
        sources[page - 1].with_suffix(".tesseract").write_text(raw + "\n", encoding="ascii")
    return len(sources), len(recognized)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages", type=Path)
    parser.add_argument("crops", type=Path)
    parser.add_argument("diagnostics", type=Path, nargs="+")
    parser.add_argument("--tesseract", default="tesseract")
    parser.add_argument("--scratch", type=Path)
    count, recognized = reread(**vars(parser.parse_args()))
    print(f"Read {recognized} of {count} scan crops with Tesseract")


if __name__ == "__main__":
    main()
