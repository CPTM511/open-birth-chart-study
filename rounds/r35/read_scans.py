"""Render and OCR the eight frozen Japanese historical birth tables on macOS."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

from rounds.r27.archive_source import digest, read_json, require


HERE = Path(__file__).resolve().parent
CATALOGUE = read_json(HERE.parent / "r34" / "historical_sources.json")["scanned_publisher_files"]
# Keep the body and headings for page geometry verification.
CROP = (0.13, 0.18, 0.90, 0.80)


def published_pages(directory, include_places):
    import pymupdf

    for filename, record in CATALOGUE.items():
        if not include_places and filename not in {"jp1993-000031896462.pdf", "jp1994-000031897479.pdf",
                                                    "jp1995-000023616728.pdf"}:
            continue
        source = directory / filename
        require(digest(source) == record["sha256"], f"Source hash differs for {filename}")
        with pymupdf.open(source) as document:
            require(document.page_count == record["pages"], "Unexpected scanned page count")
            pages = document.page_count if include_places else 26
            for number in range(pages):
                yield source.stem, number + 1, document[number]


def render(directory, output, include_places):
    import pymupdf

    for stub, page_number, page in published_pages(directory, include_places):
        name = output / f"{stub}-{page_number:03}.png"
        if name.is_file():
            continue
        page_width, page_height = page.rect.width, page.rect.height
        x0, y0, x1, y1 = CROP
        box = pymupdf.Rect(x0 * page_width, y0 * page_height, x1 * page_width, y1 * page_height)
        scale = 2420 / box.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=box, colorspace=pymupdf.csGRAY)
        pix.save(name)


def invoke(executable, groups, languages, workers):
    def read(paths):
        subprocess.run([str(executable), languages, *map(str, paths)], check=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(read, groups):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-places", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "vision_read"
    subprocess.run(["swiftc", str(HERE / "vision_read.swift"), "-framework", "Vision", "-o", str(target)], check=True)
    render(args.sources, args.output, args.include_places)
    todo = [p.resolve() for p in sorted(args.output.glob("jp*.png")) if not p.with_suffix(".json").is_file()]
    invoke(target.resolve(), [todo[i:i + 8] for i in range(0, len(todo), 8)], "en-US", args.workers)
    print(f"Completed {len(todo)} OCR pages", flush=True)


if __name__ == "__main__":
    main()
