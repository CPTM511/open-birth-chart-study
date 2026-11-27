"""Read the unresolved table cells at a larger scale directly from each scan."""

from __future__ import annotations

import argparse
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from rounds.r27.archive_source import read_json
from .grid_reads import cell_centres, count_value, isolated_values, page_identity, read_page
from .read_scans import invoke


def cell_file(directory, stem, row, column):
    return directory / f"{stem}-d{row:02}-c{column:02}.png"


def explicit_dash(source):
    gray = np.asarray(source)
    used = gray < 115
    # Take the prominent printed marks, allowing isolated paper speckles.
    levels = np.flatnonzero((used.sum(axis=1) >= 4))
    if not 2 <= len(levels) <= 5 or levels[-1] - levels[0] > 5:
        return False
    support = used[levels[0]:levels[-1] + 1].sum(axis=0)
    cols = np.flatnonzero(support >= 2)
    return 5 <= len(cols) <= 15 and cols[-1] - cols[0] <= 16


def collect_cells(page, output, keys, x_terms, y_terms, columns):
    xs, ys = cell_centres(x_terms, y_terms, columns)
    with Image.open(page) as scanned:
        width, height = scanned.size
        for day, column in keys:
            name = cell_file(output, page.stem, day, column)
            if name.is_file() or name.with_suffix(".dash").is_file():
                continue
            x, y = xs[day, column], ys[day, column]
            crop = scanned.crop((round((x - .034) * width), round((y - .0079) * height),
                                 round((x + .005) * width), round((y + .0079) * height))).convert("L")
            if explicit_dash(crop):
                name.with_suffix(".dash").write_text("0\n", encoding="ascii")
                continue
            crop = ImageOps.autocontrast(crop, cutoff=0)
            crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.BICUBIC)
            canvas = Image.new("L", (crop.width + 60, crop.height + 44), 255)
            canvas.paste(crop, (30, 22))
            canvas.save(name)


def all_cells(directory, pages, contacts, workers, places, years):
    directory.mkdir(parents=True, exist_ok=True)
    paths = [path for path in sorted(pages.glob("jp*.json"))
             if page_identity(path.stem)[0] in years and page_identity(path.stem)[1] in places]

    def prepare(path):
        year, _, month, _ = page_identity(path.stem)
        first, x_terms, y_terms = read_page(path)
        columns = len(first[0])
        second = isolated_values(contacts / path.name, columns)
        last = monthrange(year, month)[1] if month else 31
        keys = [(day, j) for day in range(last + 1) for j in range(columns)
                if not first[day][j] and not second[day][j] or
                first[day][j] and second[day][j] and not set(first[day][j]) & set(second[day][j])]
        collect_cells(path.with_suffix(".png"), directory, keys, x_terms, y_terms, columns)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(prepare, paths):
            pass
    return read_pending(directory, pages / "vision_read", workers)


def read_pending(directory, executable, workers):
    todo = [path.resolve() for path in sorted(directory.glob("*.png")) if not path.with_suffix(".json").is_file()]
    invoke(executable.resolve(), [todo[start:start + 60] for start in range(0, len(todo), 60)], "en-US", workers)
    return len(todo)


def read_cell(directory, stem, row, column, frozen_tesseract=None):
    image = cell_file(directory, stem, row, column)
    if image.with_suffix(".dash").is_file():
        return [0]
    vision = image.with_suffix(".json")
    alternative = image.with_suffix(".tesseract")
    vision_values = set()
    if vision.is_file():
        vision_values.update(count_value(result["text"]) for result in read_json(vision))
    values = sorted(vision_values - {None})
    if frozen_tesseract is not None:
        raw = frozen_tesseract.get(image.stem)
    else:
        raw = alternative.read_text(encoding="ascii") if alternative.is_file() else None
    if raw is not None:
        number = count_value(raw)
        if number is not None:
            values.append(number)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages", type=Path)
    parser.add_argument("contacts", type=Path)
    parser.add_argument("cells", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--places", type=int, nargs="+", choices=range(6), default=[0])
    parser.add_argument("--years", type=int, nargs="+", choices=(1993, 1994, 1995), default=[1993, 1994, 1995])
    a = parser.parse_args()
    count = all_cells(a.cells, a.pages, a.contacts, a.workers, a.places, a.years)
    print(f"Completed {count} targeted OCR crops", flush=True)


if __name__ == "__main__":
    main()
