"""Audit the counts in the scanned annual, monthly, venue and hourly margins."""

from __future__ import annotations

import argparse
from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from rounds.r27.archive_source import read_json, require, write_json
from .grid_reads import isolated_values, page_identity, read_page
from .isolated_cells import read_cell


HERE = Path(__file__).resolve().parent
YEARS = (1993, 1994, 1995)
FIELDS = range(25)


@dataclass(frozen=True)
class Equation:
    family: str
    total: tuple[int, int, int, int]
    parts: tuple[tuple[int, int, int, int], ...]

    def terms(self):
        yield self.total, 1
        for key in self.parts:
            yield key, -1


def source_anchors(year):
    receipt = read_json(HERE.parent / "r34" / "historical_annual_hours.json")[str(year)]
    return {(0, 0, 0, field): value for field, value in enumerate(
        [receipt["publisher_total"], *receipt["hours_00_through_23"]])}


def layout(page):
    year, place, month, half = page_identity(page)
    last = monthrange(year, month)[1] if month else 31
    offset = 13 * half
    return year, place, month, last, offset


def source_slots(year, places):
    return {(v, m, d, k) for v in places for m in range(13)
            for d in range((monthrange(year, m)[1] if m else 31) + 1) for k in FIELDS}


def load_votes(year, places, pages, contacts, crops, frozen_tesseract=None):
    votes, provenance = {}, {}
    for path in sorted(pages.glob(f"jp{year}*.json")):
        _, place, month, last, offset = layout(path.stem)
        if place not in places:
            continue
        first, _, _ = read_page(path)
        second = isolated_values(contacts / path.name, len(first[0]))
        for day in range(last + 1):
            for j in range(len(first[0])):
                key = (place, month, day, j + offset)
                require(key not in votes, f"The same source slot appears more than once: {path.stem}")
                alternatives = Counter(first[day][j] + second[day][j])
                alternatives.update(read_cell(crops, path.stem, day, j, frozen_tesseract))
                votes[key] = alternatives
                provenance[key] = path.stem, day, j
    require(set(votes) == source_slots(year, places), f"The page cells omit expected dates or hours for {year}")
    return votes, provenance


def accounting(year, places):
    last = {month: monthrange(year, month)[1] for month in range(1, 13)}
    for place in places:
        for month in range(13):
            days = last.get(month, 31)
            for day in range(days + 1):
                yield Equation("hours", (place, month, day, 0),
                               tuple((place, month, day, h) for h in range(1, 25)))
        for field in FIELDS:
            yield Equation("months", (place, 0, 0, field),
                           tuple((place, m, 0, field) for m in last))
            for month, days in last.items():
                yield Equation("dates", (place, month, 0, field),
                               tuple((place, month, d, field) for d in range(1, days + 1)))
            for day in range(1, 32):
                yield Equation("days_of_month", (place, 0, day, field),
                               tuple((place, m, day, field) for m in last if day <= last[m]))
    if set(places) == set(range(6)):
        for month in range(13):
            for day in range(last.get(month, 31) + 1):
                for field in FIELDS:
                    yield Equation("venues", (0, month, day, field),
                                   tuple((place, month, day, field) for place in range(1, 6)))


def read_manual(path, year, locations):
    if not path or not path.is_file():
        return {}
    manual = {}
    for item in read_json(path):
        if item["year"] == year:
            location = tuple(item["cell"])
            if location not in locations:
                continue
            require(location not in manual and type(item["printed_value"]) is int and
                    0 <= item["printed_value"] and tuple(item["source"]) == locations[location],
                    "The visual review must identify a unique printed value and source page, row and column")
            manual[location] = item["printed_value"]
    return manual


def simple_choice(votes, fixed):
    numbers = {}
    for key, alternatives in votes.items():
        ranked = alternatives.most_common()
        numbers[key] = ranked[0][0] if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]) else None
    numbers.update(fixed)
    return numbers


def violations(numbers, equations):
    differences = []
    for eq in equations:
        unresolved = []
        total = 0
        for key, sign in eq.terms():
            value = numbers[key]
            if value is None:
                unresolved.append((key, sign))
            else:
                total += value * sign
        if total or unresolved:
            differences.append((eq, total, unresolved))
    return differences


def equation_connections(equations):
    connections = defaultdict(list)
    for equation in equations:
        for key, sign in equation.terms():
            connections[key].append((equation, sign))
    return connections


def candidates(numbers, equations, fixed, connections):
    suggestions = defaultdict(Counter)
    broken = violations(numbers, equations)
    residuals = {equation: (residual, unknown) for equation, residual, unknown in broken}
    for equation, residual, unknown in broken:
        if len(unknown) > 1:
            continue
        for key, sign in (unknown if unknown else equation.terms()):
            if key in fixed:
                continue
            value = (numbers[key] or 0) - sign * residual
            if value >= 0:
                suggestions[key][value] += 1

    def can_improve(key, value):
        before, after = 0, 0
        for eq, sign in connections[key]:
            residual, unfilled = residuals.get(eq, (0, []))
            others = [k for k, _ in unfilled if k != key]
            if not others:
                before += numbers[key] is not None and residual == 0
                after += residual + sign * (value - (numbers[key] or 0)) == 0
        return after > before

    return broken, {
        key: Counter({value: strength for value, strength in alternatives.items() if can_improve(key, value)})
        for key, alternatives in suggestions.items()
    }


def reconcile(votes, equations, fixed):
    numbers = simple_choice(votes, fixed)
    revised = []
    connections = equation_connections(equations)
    # Each accepted correction must be visible in at least one direct source read.
    # Change one cell at a time when this strictly improves the fully specified sums.
    while True:
        broken, proposal = candidates(numbers, equations, fixed, connections)
        compatible = [(support, votes[key][value], key, value) for key, alternatives in proposal.items()
                      for value, support in alternatives.items() if value in votes[key]]
        if not compatible:
            return numbers, broken, proposal, revised
        _, _, key, value = max(compatible)
        revised.append((key, numbers[key], value))
        numbers[key] = value


def summarize(year, places, pages, contacts, cells, review=None, frozen_tesseract=None):
    votes, locations = load_votes(year, places, pages, contacts, cells, frozen_tesseract)
    fixed = {**read_manual(review, year, locations), **source_anchors(year)}
    numbers, broken, proposal, changes = reconcile(votes, list(accounting(year, places)), fixed)
    missing = [key for key, value in numbers.items() if value is None]
    diagnostics = {
        "year": year,
        "places": places,
        "source_slots": len(numbers),
        "empty": len(missing),
        "unequal_or_incomplete": len(broken),
        "violation_families": dict(Counter(eq.family for eq, _, _ in broken)),
        "corrections_supported_by_source_reads": len(changes),
        "changes": [{"key": key, "location": locations[key], "previous": previous,
                     "printed_value": current, "votes": dict(votes[key])}
                    for key, previous, current in changes],
        "suggestions": [
            {"key": key, "location": locations[key], "current": numbers[key],
             "voted": dict(votes[key]), "possible": dict(guesses)}
            for key, guesses in proposal.items()
            if guesses and (numbers[key] is None or max(guesses.values()) >= 2)
        ],
        "missing_slots": [{"key": key, "location": locations[key]} for key in missing],
        "violations": [{"family": eq.family, "total": eq.total, "residual_without_unknowns": residual,
                        "missing_slots": [key for key, _ in unknown]} for eq, residual, unknown in broken],
    }
    return numbers, diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pages", "contacts", "cells", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--year", type=int, choices=YEARS, required=True)
    parser.add_argument("--places", type=int, nargs="+", choices=range(6), default=[0])
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    _, report = summarize(args.year, args.places, args.pages, args.contacts, args.cells, args.review)
    write_json(args.output, report)
    print({key: value for key, value in report.items() if not isinstance(value, list)})


if __name__ == "__main__":
    main()
