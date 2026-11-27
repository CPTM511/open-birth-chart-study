"""Locate printed count rows and read them again as isolated cells."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from pathlib import Path
import re
from unicodedata import normalize

import numpy as np
from PIL import Image

from rounds.r27.archive_source import read_json, require
from .read_scans import invoke


ROW_SLOTS = np.array([0] + [day + 1 + min((day - 1) // 5, 5) for day in range(1, 32)])
SLOT_TO_ROW = {int(slot): day for day, slot in enumerate(ROW_SLOTS)}
SLOT_LOOKUP = np.full(38, -1)
SLOT_LOOKUP[ROW_SLOTS] = np.arange(32)
CELL_WIDTH = 170
CELL_HEIGHT = 55


@dataclass(frozen=True)
class Mark:
    number: int
    right: float
    ordinate: float
    confidence: float


def count_value(raw):
    text = normalize("NFKC", raw).strip()
    if text in {"-", "−", "–", "—", "ー", "―", "-.", "-,"}:
        return 0
    token = re.fullmatch(r"([0-9]{1,7})[.·,:;'`]*", text)
    return int(token[1]) if token else None


def source_marks(path):
    readings = read_json(path)
    numbers = []
    for row in readings:
        value = count_value(row["text"])
        x = row["left"] + row["width"]
        y = row["top"] + row["height"] / 2
        if value is not None and 0.155 < x < 0.87 and 0.155 < y < 0.86:
            numbers.append(Mark(value, x, y, row["confidence"]))
    return numbers


def fit_columns(marks, columns, year, regular_layout=False):
    """Fit the right edge of the printed monospaced columns."""
    target = 0.247 if year == 1995 and regular_layout else (0.246 if year == 1995 else 0.208)
    pitch = 0.0446 if year == 1995 else 0.049
    xs = np.array([point.right for point in marks])
    ys = np.array([point.ordinate for point in marks])
    weights = np.array([1 if point.number else 0.25 for point in marks])
    if len(xs) < 18:
        return np.array([target, pitch, 0.0])
    if regular_layout:
        starts = np.arange(target - .009, target + .013, .002)
        steps = np.arange(pitch - .0006, pitch + .00061, .0002)
    else:
        starts = np.arange(target - .030, target + .031, .003)
        steps = np.arange(pitch - .004, pitch + .0041, .0009)
    trials = np.stack(np.meshgrid(starts, steps), axis=-1).reshape(-1, 2)
    positions = (xs[None, :] - trials[:, 0, None]) / trials[:, 1, None]
    column = np.rint(positions)
    offset = np.abs(positions - column) * trials[:, 1, None]
    evidence = np.exp(-(offset / .004) ** 2) * ((column >= 0) & (column < columns)) * weights
    best = np.argmax(evidence.sum(axis=1))
    terms = np.array([*trials[best], 0.0])
    for _ in range(3):
        j = np.rint((xs - terms[0] - terms[2] * (ys - .45)) / terms[1])
        gap = xs - (terms[0] + terms[1] * j + terms[2] * (ys - .45))
        valid = (0 <= j) & (j < columns) & (np.abs(gap) < .008)
        if len(set(j[valid])) < 3:
            break
        form = np.stack([np.ones(valid.sum()), j[valid], (ys - .45)[valid]], axis=1)
        improved = np.linalg.lstsq(form, xs[valid], rcond=None)[0]
        if regular_layout and (abs(improved[0] - target) > .014 or
                               abs(improved[1] - pitch) > .001 or abs(improved[2]) > .018):
            break
        terms = improved
    return terms


def columns_and_marks(marks, terms, columns):
    start, pitch, tilt = terms
    accepted = []
    for mark in marks:
        position = (mark.right - start - tilt * (mark.ordinate - .45)) / pitch
        column = round(position)
        if 0 <= column < columns and abs(position - column) * pitch < .013:
            accepted.append((column, mark))
    return accepted


def fit_rows(marks):
    """Fit the body rows including the five extra intergroup spacers."""
    if len(marks) < 18:
        return np.array([.216, .0157, 0.0])
    starts = np.arange(.169, .273, .004)
    steps = np.arange(.0144, .01715, .00027)
    tilts = np.arange(-.021, .026, .009)
    y = np.array([mark.ordinate for _, mark in marks])
    x = np.array([mark.right - .25 for _, mark in marks])
    weights = np.array([1 if mark.number else 0.4 for _, mark in marks])
    choices = np.stack(np.meshgrid(starts, steps, tilts), axis=-1).reshape(-1, 3)
    values = (y[None, :] - choices[:, 0, None] - choices[:, 2, None] * x) / choices[:, 1, None]
    nearest = np.rint(values).astype(int)
    correct = (nearest >= 0) & (nearest < len(SLOT_LOOKUP))
    correct &= SLOT_LOOKUP[np.clip(nearest, 0, len(SLOT_LOOKUP) - 1)] >= 0
    offsets = (values - nearest) * choices[:, 1, None]
    strength = np.exp(-(offsets / .0038) ** 2) * correct * weights
    # The published totals sit above the first numbered day with one extra line.
    strength *= np.where(nearest == 0, 1.06, 1.0)
    terms = choices[np.argmax(strength.sum(axis=1))]
    for _ in range(3):
        slots = np.rint((y - terms[0] - terms[2] * x) / terms[1]).astype(int)
        valid = (slots >= 0) & (slots < len(SLOT_LOOKUP))
        valid &= SLOT_LOOKUP[np.clip(slots, 0, len(SLOT_LOOKUP) - 1)] >= 0
        valid &= np.abs(y - (terms[0] + terms[1] * slots + terms[2] * x)) <= .007
        if len(set(slots[valid])) < 7:
            break
        form = np.stack([np.ones(valid.sum()), slots[valid], x[valid]], axis=1)
        terms = np.linalg.lstsq(form, y[valid], rcond=None)[0]
    return terms


def projected_rows(path, year):
    """Align sparse or faded editions to the printed rows using ink density."""
    with Image.open(path) as image:
        scan = np.asarray(image)
    height, width = scan.shape
    columns = np.arange(int(.157 * width), int(.834 * width), 8)
    ink = scan[:, columns] < 135
    center, pitch, nominal_tilt = {1993: (.214, .0157, .012),
                                  1994: (.205, .0157, .017),
                                  1995: (.220, .0156, .001)}[year]
    starts = np.linspace(center - .008, center + .008, 49)
    steps = np.linspace(pitch - .00024, pitch + .00024, 49)
    y_forms = np.stack(np.meshgrid(starts, steps), axis=-1).reshape(-1, 2)
    ordinates = y_forms[:, 0, None] + y_forms[:, 1, None] * ROW_SLOTS[None, :]
    pixels = np.rint(ordinates * height).astype(int)
    best_score = -1
    for tilt in np.linspace(nominal_tilt - .012, nominal_tilt + .012, 25):
        shifts = np.rint(tilt * (columns / width - .25) * height).astype(int)
        projection = sum(np.roll(strip, -shift).astype(int) for strip, shift in zip(ink.T, shifts, strict=True))
        smoothed = np.convolve(projection, [1, 2, 3, 4, 5, 4, 3, 2, 1], mode="same")
        scores = smoothed[pixels].sum(axis=1)
        winner = np.argmax(scores)
        if scores[winner] > best_score:
            best_score = scores[winner]
            terms = np.array([*y_forms[winner], tilt])
    return terms


def projected_columns(path, count):
    """Recover right-justified columns when sparse OCR marks imply a large false tilt."""
    with Image.open(path) as image:
        scan = np.asarray(image)
    height, width = scan.shape
    rows = np.arange(int(.208 * height), int(.813 * height), 7)
    ink = scan[rows, :] < 128
    starts = np.linspace(.24, .265, 51)
    steps = np.linspace(.04434, .04486, 27)
    x_forms = np.stack(np.meshgrid(starts, steps), axis=-1).reshape(-1, 2)
    centers = x_forms[:, 0, None] + x_forms[:, 1, None] * np.arange(count)[None, :] - .007
    pixels = np.rint(centers * width).astype(int)
    best_score = -1
    for tilt in np.linspace(-.016, .016, 33):
        shifts = np.rint(tilt * (rows / height - .45) * width).astype(int)
        projection = sum(np.roll(strip, -shift).astype(int) for strip, shift in zip(ink, shifts, strict=True))
        smoothed = np.convolve(projection, [1, 2, 3, 4, 5, 4, 3, 2, 1], mode="same")
        scores = smoothed[pixels].sum(axis=1)
        winner = np.argmax(scores)
        if scores[winner] > best_score:
            best_score = scores[winner]
            terms = np.array([*x_forms[winner], tilt])
    return terms


def page_identity(name):
    match = re.fullmatch(r"jp(199[345])-([0-9]{12})-([0-9]{3})", name)
    require(match is not None, f"Unexpected page name {name}")
    year, table, page = match.groups()
    year, page = int(year), int(page)
    half = (page - 1) % 2
    place = (page - 1) // 26 if year < 1995 else int(table) - 23616728
    month = ((page - 1) % 26) // 2
    require(place in range(6), f"Unexpected place index in {name}")
    return year, place, month, half


def read_page(path):
    year, place, _, half = page_identity(path.stem)
    columns = 13 - half
    regular_layout = (year == 1995 and place != 0) or place >= 3
    marks = source_marks(path)
    x_terms = fit_columns(marks, columns, year, regular_layout)
    if year == 1995 and place in (1, 2) and abs(x_terms[2]) > .012:
        x_terms = projected_columns(path.with_suffix(".png"), columns)
    selected = columns_and_marks(marks, x_terms, columns)
    y_terms = projected_rows(path.with_suffix(".png"), year) if regular_layout else fit_rows(selected)
    values = [[[] for _ in range(columns)] for _ in range(32)]
    for column, mark in selected:
        fractional = (mark.ordinate - y_terms[0] - y_terms[2] * (mark.right - .25)) / y_terms[1]
        slot = round(fractional)
        if slot not in SLOT_TO_ROW or abs(fractional - slot) > .40:
            continue
        cell = values[SLOT_TO_ROW[slot]][column]
        if mark.number not in cell:
            cell.append(mark.number)
    return values, x_terms, y_terms


def cell_centres(x_terms, y_terms, columns):
    y0, dy, rise = y_terms
    x0, dx, run = x_terms
    j = np.arange(columns)[None, :]
    y = y0 + dy * ROW_SLOTS[:, None] + rise * (x0 + dx * j - .25)
    x = x0 + dx * j + run * (y - .45)
    return x, y


def isolated_page(path, output, x_terms, y_terms, columns):
    """Lay out the scanned cells with sufficient white space for a second reading."""
    with Image.open(path) as source:
        source = source.convert("L")
        width, height = source.size
        canvas = Image.new("L", (columns * CELL_WIDTH, 32 * CELL_HEIGHT), 255)
        xs, ys = cell_centres(x_terms, y_terms, columns)
        for day in range(32):
            for column in range(columns):
                x, y = xs[day, column], ys[day, column]
                crop = source.crop((round((x - .035) * width), round((y - .008) * height),
                                    round((x + .005) * width), round((y + .008) * height)))
                crop = crop.resize((int(crop.width * 1.4), int(crop.height * 1.4)), Image.Resampling.BICUBIC)
                canvas.paste(crop, (column * CELL_WIDTH + CELL_WIDTH - crop.width - 12,
                                   day * CELL_HEIGHT + (CELL_HEIGHT - crop.height) // 2))
        canvas.save(output)


def isolated_values(path, columns):
    values = [[[] for _ in range(columns)] for _ in range(32)]
    for reading in read_json(path):
        number = count_value(reading["text"])
        if number is None:
            continue
        column = int((reading["left"] + reading["width"] / 2) * columns)
        day = int((reading["top"] + reading["height"] / 2) * 32)
        if 0 <= column < columns and 0 <= day < 32 and number not in values[day][column]:
            values[day][column].append(number)
    return values


def prepare(pages, contacts, workers, years, places):
    contacts.mkdir(parents=True, exist_ok=True)
    sources = [item for item in sorted(pages.glob("jp*.json"))
               if page_identity(item.stem)[0] in years and page_identity(item.stem)[1] in places]

    def make(path):
        image = contacts / f"{path.stem}.png"
        if image.is_file():
            return
        values, xs, ys = read_page(path)
        isolated_page(path.with_suffix(".png"), image, xs, ys, len(values[0]))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(make, sources):
            pass
    todo = [(contacts / f"{path.stem}.png").resolve() for path in sources
            if not (contacts / f"{path.stem}.json").is_file()]
    invoke((pages / "vision_read").resolve(), [todo[start:start + 10] for start in range(0, len(todo), 10)],
           "en-US", workers)
    print(f"Read {len(sources)} second-pass contact sheets", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages", type=Path)
    parser.add_argument("contacts", type=Path)
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--places", nargs="+", type=int, choices=range(6), default=[0])
    parser.add_argument("--years", nargs="+", type=int, choices=(1993, 1994, 1995), default=[1993, 1994, 1995])
    args = parser.parse_args()
    prepare(**vars(args))


if __name__ == "__main__":
    main()
