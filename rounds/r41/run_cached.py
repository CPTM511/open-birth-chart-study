"""Use identical frozen Ziwei inputs to avoid repeated annual calculation in R41."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from multiprocessing import Pool
from pathlib import Path

from .profiles import YEARS, private_job, require, run_date, runtime_signature, study_dates

import run_profiles as frozen


class ZiweiCalendarCache:
    """Hold one standard calendar day of identical frozen bridge requests."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.day = None
        self.annual = {}

    def compute(self, row, years, shift_minutes=0, include_chart=False, detailed=False):
        if row["source"] != "r41_standard_input" or shift_minutes or include_chart or detailed:
            return self.bridge.compute(row, years, shift_minutes, include_chart, detailed)
        clock = datetime.fromisoformat(row["birth_local"])
        day = clock.date()
        if day != self.day:
            self.annual.clear()
            self.day = day
        # This is the exact selection in the pinned bridge after parseBirth, with shift=0.
        key = (clock.hour + 1) // 2, row["sex"], tuple(years)
        if key not in self.annual:
            result = self.bridge.compute(row, years)
            if result["status"] != "computed_for_registered_conventions":
                return result
            self.annual[key] = result
        return {**self.annual[key], "study_id": row["study_id"], "birth_clock_label": row["birth_local"]}


def init_cached_worker():
    frozen.init_worker()
    frozen.zw_engine = ZiweiCalendarCache(frozen.zw_engine)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--year", required=True, choices=YEARS, type=int)
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--first-date", type=date.fromisoformat)
    parser.add_argument("--last-date", type=date.fromisoformat)
    args = parser.parse_args()
    require(runtime_signature() == ("Linux", "x86_64", "glibc", "2.36", "3.12.14", "v24.22.3"),
            "Use the frozen R10 Linux x86-64 runtime")
    require(args.workers >= 1, "At least one scoring process is required")
    days = [day for day in study_dates(args.year)
            if (args.first_date is None or args.first_date <= day) and (args.last_date is None or day <= args.last_date)]
    require(days, "The requested window contains no registered date")
    directory = private_job(args.directory)
    with Pool(args.workers, initializer=init_cached_worker) as pool:
        for day in days:
            run_date(pool, directory, day, probe=False)


if __name__ == "__main__":
    main()
