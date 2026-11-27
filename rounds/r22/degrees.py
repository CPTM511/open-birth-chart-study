"""Separate historical palace-grid and Shoushi coordinate workflows."""
from fractions import Fraction
from math import ceil
from pathlib import Path
import json

from open_birth_chart import qizheng_engine as original

SOURCE = json.loads(Path(__file__).with_name("sources.json").read_bytes())
BRANCHES = original.BRANCHES
MANSIONS = original.MANSION_NAMES
F = Fraction
GRID = {palace: tuple((mansion, degree - step)
                      for mansion, degree, count in segments for step in range(count))
        for palace, segments in SOURCE["grid_segments"].items()}
DURATIONS = {name: F(item["duration"]) for name, item in SOURCE["printed_rates"].items()}
PRINTED_RATES = {name: F(item["rate"]) for name, item in SOURCE["printed_rates"].items()}


def branch_index(branch):
    if len(branch) != 1 or branch not in BRANCHES:
        raise ValueError(f"Unknown earthly branch: {branch!r}")
    return BRANCHES.index(branch)


def ming_palace(solar_palace, birth_hour_branch):
    return BRANCHES[(branch_index(solar_palace) + 3 - branch_index(birth_hour_branch)) % 12]


def column_for(palace, mansion, whole_degree):
    if type(whole_degree) is not int or whole_degree < 0:
        raise ValueError("Grid input requires a nonnegative whole degree")
    try:
        return GRID[palace].index((mansion, whole_degree)) + 1
    except ValueError:
        return None


def grid_value(palace, column):
    if type(column) is not int or not 1 <= column <= 30:
        raise ValueError("Grid column must be 1 through 30")
    return GRID[palace][column - 1]


def age_for_column(column):
    if type(column) is not int or not 1 <= column <= 30:
        raise ValueError("Grid column must be 1 through 30")
    return 11 + (30 - column) // 3


def grid_transfer(solar_palace, solar_mansion, whole_degree, birth_hour_branch):
    ming = ming_palace(solar_palace, birth_hour_branch)
    column = column_for(solar_palace, solar_mansion, whole_degree)
    if column is None:
        return None
    m, degree = grid_value(ming, column)
    return {"ming_palace": ming, "solar_column": column,
            "ming_mansion": m, "ming_whole_degree": degree,
            "first_change_nominal_age": age_for_column(column)}


def spans(first, last, low, high):
    start, end = max(first, low), min(last, high)
    return (start, end) if start < end else None


class ShoushiScale:
    def __init__(self, chou_reference):
        boundaries = dict(SOURCE["yuanshi_palace_heads"])
        if chou_reference == "shidian_er":
            boundaries["丑"] = SOURCE["alternate_chou_head"]
        elif chou_reference != "wikisource_san":
            raise ValueError("Provide one of the two source readings for the Chou palace")
        self.widths = {m: F(SOURCE["yuanshi_mansion_widths"][m]) for m in MANSIONS}
        self.starts = {}
        self.cycle = F(0)
        for mansion, width in self.widths.items():
            self.starts[mansion] = self.cycle
            self.cycle += width
        self.heads = {palace: self.starts[m] + F(degree)
                      for palace, (m, degree) in boundaries.items()}

    def palace_width(self, palace):
        next_in_longitude = BRANCHES[(branch_index(palace)-1) % 12]
        return (self.heads[next_in_longitude] - self.heads[palace]) % self.cycle

    def relative_solar_bin(self, palace, mansion, whole_degree):
        first = self.starts[mansion] + whole_degree
        end = self.starts[mansion] + min(F(whole_degree+1), self.widths[mansion])
        if first >= end:
            raise ValueError("The supplied degree is outside the source mansion")
        relative = first - self.heads[palace]
        candidate_length = end-first
        for shift in (0, self.cycle, -self.cycle):
            match = spans(relative+shift, relative+shift+candidate_length,
                          F(0), self.palace_width(palace))
            if match:
                return match, candidate_length
        return None, candidate_length

    def available_labels(self, palace, interval):
        first, end = interval
        head = self.heads[palace]
        labels = []
        for shift in (0, self.cycle):
            for mansion in self.widths:
                begin = self.starts[mansion] + shift
                match = spans(first+head, end+head, begin, begin+self.widths[mansion])
                if match:
                    lower, upper = match
                    for value in range(int(lower-begin), ceil(upper-begin)):
                        labels.append([mansion, value])
        return labels

    def project_bin(self, solar_palace, mansion, whole_degree, ming, anchor):
        """Return the complete half-open image of a printed degree bin."""
        if type(whole_degree) is not int or whole_degree < 0:
            raise ValueError("The recorded bin must be a nonnegative integer")
        solar, source_width = self.relative_solar_bin(solar_palace, mansion, whole_degree)
        if anchor not in ("head", "tail"):
            raise ValueError("Declare the corresponding head or tail offset")
        if not solar:
            return {"status": "solar_bin_outside_reported_palace"}
        width = self.palace_width(ming)
        projected = solar
        if anchor == "tail":
            shift = width - self.palace_width(solar_palace)
            projected = solar[0]+shift, solar[1]+shift
        kept = spans(*projected, F(0), width)
        out = {"source_arc_units": str(source_width),
               "source_in_solar_palace_arc_units": str(solar[1]-solar[0]),
               "target_palace_width_arc_units": str(width)}
        if not kept:
            return {**out, "status": "projected_bin_outside_ming_palace"}
        a, b = kept
        ages = [11+i for i in range(10) if spans(a,b,3*i,3*(i+1))]
        return {**out, "status": "computed", "target_offset_interval_arc_units": [str(a),str(b)],
                "target_lost_arc_units": str(solar[1]-solar[0] - (b-a)),
                "possible_mansion_labels": self.available_labels(ming, kept),
                "possible_first_change_nominal_ages": ages, "interval_extends_beyond_age_rule": b > 30}


def period_trace(ming, ming_column, elapsed_years):
    """Read a period and degree under the registered interpolation of the grid."""
    index = branch_index(ming)
    if ming_column is None:
        return {"status":"missing_ming_degree"}
    first_change = age_for_column(ming_column)
    years = F(str(elapsed_years))
    if years < 0:
        raise ValueError("Elapsed years must be nonnegative")
    start = F(first_change-1)
    if years < start:
        remaining = (start-years)/start
        low = 31-ceil((31-ming_column)*remaining)
        high = 30-int((30-ming_column)*remaining)
        return {"status":"computed", "period":"命", "palace":ming,
                "start_elapsed_year":"0", "end_elapsed_year_exclusive":str(start),
                "possible_columns":list(range(low,high+1))}
    for advance, (name, duration) in enumerate(DURATIONS.items(), start=1):
        end = start + duration
        if years < end:
            progress = years-start
            normalized = 30*progress/duration
            literal = PRINTED_RATES[name]*progress
            palace = BRANCHES[(index+advance) % 12]
            column = 1 + int(normalized)
            printed_distance_column = 1 + int(literal)
            return {"status":"computed", "period":name, "palace":palace, "column":column,
                    "mansion_degree":list(grid_value(palace,column)),
                    "start_elapsed_year":str(start), "end_elapsed_year_exclusive":str(end),
                    "normalized_distance_from_tail":str(normalized),
                    "printed_rate_distance_from_tail":str(literal),
                    "printed_rate_column":printed_distance_column}
        start = end
    return {"status":"outside_this_cycle", "end_elapsed_year_exclusive":str(start)}
