"""Compare Japanese live-birth hours on holidays and matched calendar dates."""
from __future__ import annotations

import argparse
from calendar import monthrange
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
import json
import math
from pathlib import Path
import re
from statistics import stdev

from scipy.stats import t

from rounds.r18.japanese_birth_hours import VENUES, add_vectors, clean, digest, source_blocks

HERE = Path(__file__).resolve().parent
SEALED = {
    "REGISTRATION.zh.md": "61dc300c13f09354812b3cd8eb0d57b6d2192cd9e47d95ef86ab5ff1c3d505a6",
    "protocol.json": "ed37f02bd2052cb410601cce64fe4a1b67f80c35ef01ebebda4ccbb7c34dcdb2",
    "source-snapshot.json": "162cbaf47c1d54d6616be084b8a4cfe6bbe8b1983fe3bfc36ac93f1c0af999f7",
}
SEASONAL_RULE = {"海の日": (7, 3), "スポーツの日": (10, 2)}
NAME_ALIASES = {"体育の日（スポーツの日）": "体育の日"}
PUBLISHER_YEARS = {"平成": 1988, "令和": 2018}


def mean_exact(values) -> Fraction:
    values = list(values)
    return sum(values, Fraction()) / len(values)


def numeric(value: Fraction | float) -> float:
    return round(float(value), 10)


def parse_holidays(path: Path) -> dict[date, str]:
    with path.open(encoding="cp932", newline="") as f:
        rows = csv.reader(f)
        if next(rows) != ["国民の祝日・休日月日", "国民の祝日・休日名称"]:
            raise ValueError("The published holiday CSV fields have changed")
        holidays = {}
        for row in rows:
            if not row:
                continue
            key, label = row
            d = date(*map(int, key.split("/")))
            if d in holidays or not label.strip():
                raise ValueError("Duplicate date or blank in official holiday calendar")
            holidays[d] = label.strip()
    return holidays


def verify_source_year(path: Path, year: int) -> None:
    with path.open(encoding="cp932", newline="") as f:
        header = clean(next(csv.reader(f))[0])
    match = re.fullmatch(r"(平成|令和)(元|\d+)年", header)
    if not match:
        raise ValueError("Unrecognized birth source year")
    era, era_year = match.groups()
    if PUBLISHER_YEARS[era] + (1 if era_year == "元" else int(era_year)) != year:
        raise ValueError(f"Source year disagrees with the registered year {year}")


@dataclass(frozen=True)
class ClockCounts:
    total: int
    known: int
    daytime: int

    @property
    def other_hours(self) -> int:
        return self.known - self.daytime

    def as_dict(self) -> dict[str, int]:
        return {"births": self.total, "known": self.known, "daytime": self.daytime,
                "other_known_hours": self.other_hours, "unknown": self.total - self.known}


def as_counts(vector: tuple[int, ...], hours: list[int]) -> ClockCounts:
    return ClockCounts(vector[0], sum(vector[1:]), sum(vector[h + 1] for h in hours))


def load_year(path: Path, year: int, hours: list[int]) -> tuple[dict, dict]:
    verify_source_year(path, year)
    blocks = source_blocks(path)
    checks = 0
    for v in VENUES:
        if add_vectors(blocks[v, month, 0] for month in range(1, 13)) != blocks[v, 0, 0]:
            raise ValueError(f"{year} {v}: yearly and monthly counts disagree")
        checks += 25
        for month in range(1, 13):
            if add_vectors(blocks[v, month, d] for d in range(1, 32)) != blocks[v, month, 0]:
                raise ValueError(f"{year} {v} {month}: monthly and daily counts disagree")
            checks += 25
            last = monthrange(year, month)[1]
            if any(any(blocks[v, month, d]) for d in range(last + 1, 32)):
                raise ValueError(f"{year} {v} {month}: counts occur on an invalid date")
            for d in range(1, last + 1):
                vector = blocks[v, month, d]
                if sum(vector[1:]) > vector[0]:
                    raise ValueError(f"{year} {v} {month} {d}: known hours exceed the daily total")
    for month in range(13):
        for d in range(32):
            if add_vectors(blocks[v, month, d] for v in VENUES[1:]) != blocks[VENUES[0], month, d]:
                raise ValueError(f"{year} {month} {d}: birth venue counts disagree")
            checks += 25

    rows = {}
    for month in range(1, 13):
        for d in range(1, monthrange(year, month)[1] + 1):
            calendar_date = date(year, month, d)
            rows[calendar_date] = {
                "all_venues": as_counts(blocks["総数", month, d], hours),
                "hospital_and_clinic": as_counts(add_vectors([
                    blocks["病院", month, d], blocks["診療所", month, d],
                ]), hours),
            }
    summary = as_counts(blocks["総数", 0, 0], hours).as_dict()
    summary.update(days=len(rows), reconciled_published_cells=checks,
                   venue_birth_counts={v: blocks[v, 0, 0][0] for v in VENUES[1:]})
    return rows, summary


def matched_dates(d: date, holidays: dict[date, str], available: dict, offsets: list[int]) -> tuple[date, ...]:
    refs = tuple(d + timedelta(days=x) for x in offsets)
    kept = tuple(r for r in refs if r in available and r not in holidays and r.weekday() == d.weekday())
    if any(r < d for r in kept) and any(r > d for r in kept):
        return kept
    return ()


def contrast(target: ClockCounts, references: list[ClockCounts]) -> dict:
    avg_share = mean_exact(Fraction(r.daytime, r.known) for r in references)
    target_share = Fraction(target.daytime, target.known)
    avg_day = mean_exact(r.daytime for r in references)
    avg_other = mean_exact(r.other_hours for r in references)
    return {
        "target_counts": target.as_dict(),
        "daytime_share_difference_pp": 100 * (target_share - avg_share),
        "daytime_count_change_pct": 100 * (Fraction(target.daytime) / avg_day - 1),
        "other_hours_count_change_pct": 100 * (Fraction(target.other_hours) / avg_other - 1),
    }


def day_comparison(d: date, dates: dict, holidays: dict[date, str], offsets: list[int]) -> dict | None:
    matched = matched_dates(d, holidays, dates, offsets)
    if not matched:
        return None
    return {
        "matched_control_days": [r.isoformat() for r in matched],
        "control_counts_all_venues": {r.isoformat(): dates[r]["all_venues"].as_dict() for r in matched},
        **{venue: contrast(dates[d][venue], [dates[r][venue] for r in matched])
           for venue in ("all_venues", "hospital_and_clinic")},
    }


def nth_monday(year: int, month: int, ordinal: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(-first.weekday()) % 7 + 7 * (ordinal - 1))


def compare_holidays(dates: dict, holidays: dict[date, str], config: dict) -> tuple[list[dict], list[dict], list[dict]]:
    main = []
    skipped = []
    for d, label in holidays.items():
        if NAME_ALIASES.get(label, label) not in config["primary_holidays"] or str(d.year) not in config["source_years"]:
            continue
        if d.weekday() != 0 or d not in dates:
            skipped.append({"date": d.isoformat(), "holiday": label,
                            "reason": "not_a_monday" if d.weekday() != 0 else "target_year_unavailable"})
            continue
        regular = day_comparison(d, dates, holidays, config["control_day_offsets"])
        if regular is None:
            skipped.append({"date": d.isoformat(), "holiday": label, "reason": "no_controls_on_both_sides"})
            continue
        main.append({
            "date": d.isoformat(), "holiday": label, "main": regular,
            "adjacent_week_sensitivity": day_comparison(d, dates, holidays, config["sensitivity_day_offsets"]),
        })
    relocations = []
    for year in config["relocation_years"]:
        for label, (month, ordinal) in SEASONAL_RULE.items():
            hits = [d for d in holidays if d.year == year and holidays[d] == label]
            if len(hits) != 1:
                raise ValueError(f"Expected one {label} holiday on the official {year} calendar")
            actual, = hits
            nominal = nth_monday(year, month, ordinal)
            if actual == nominal or nominal in holidays:
                raise ValueError(f"Invalid relocation design for {year} {label}")
            if actual not in dates or nominal not in dates:
                relocations.append({"year": year, "holiday": label, "status": "source_year_unavailable"})
                continue
            first = day_comparison(actual, dates, holidays, config["control_day_offsets"])
            second = day_comparison(nominal, dates, holidays, config["control_day_offsets"])
            if first is None or second is None:
                raise ValueError(f"Missing matched relocation dates for {year} {label}")
            relocations.append({"year": year, "holiday": label, "actual_date": actual.isoformat(),
                                "usual_date": nominal.isoformat(), "actual_holiday": first,
                                "usual_non_holiday": second,
                                "actual_minus_usual_share_difference_pp":
                                    first["all_venues"]["daytime_share_difference_pp"]
                                    - second["all_venues"]["daytime_share_difference_pp"]})
    return main, skipped, relocations


def period_summary(rows: list[dict], years: list[int], annual: dict, threshold: int) -> dict:
    fields = ("daytime_share_difference_pp", "daytime_count_change_pct", "other_hours_count_change_pct")
    items = [row for row in rows if int(row["date"][:4]) in years]
    sensitivity = [row["adjacent_week_sensitivity"] for row in items if row["adjacent_week_sensitivity"]]
    by_year = {}
    for y in years:
        values = [row["main"]["all_venues"][fields[0]] for row in items if row["date"].startswith(str(y))]
        if values:
            by_year[str(y)] = mean_exact(values)
    annual_values = list(map(float, by_year.values()))
    interval = None
    average = None
    if annual_values:
        average = mean_exact(by_year.values())
    if len(annual_values) > 1:
        deviation = t.ppf(0.975, len(annual_values) - 1) * stdev(annual_values) / math.sqrt(len(annual_values))
        interval = [numeric(float(average) - deviation), numeric(float(average) + deviation)]
    result = {
        "source_years": [y for y in years if str(y) in annual],
        "source_births": sum(annual[str(y)]["births"] for y in years if str(y) in annual),
        "source_births_unknown_hour": sum(annual[str(y)]["unknown"] for y in years if str(y) in annual),
        "matched_holiday_dates": len(items),
        "matched_sensitivity_dates": len(sensitivity),
        "adjacent_week_sensitivity_pp": (
            mean_exact(x["all_venues"][fields[0]] for x in sensitivity) if sensitivity else None
        ),
        "annual_mean_pp": by_year,
        "annual_means_equal_weight_pp": average,
        "across_year_t_interval95_pp": interval,
    }
    for scope in ("all_venues", "hospital_and_clinic"):
        result[scope] = {field: (mean_exact(x["main"][scope][field] for x in items) if items else None)
                         for field in fields}
    result["practical_threshold_met"] = bool(items and result["all_venues"][fields[0]] <= threshold)
    return result


def analyze(source: Path) -> dict:
    for name, expected in SEALED.items():
        if digest(HERE / name) != expected:
            raise ValueError(f"Frozen file differs: {name}")
    config = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    inputs = json.loads((HERE / "source-snapshot.json").read_text(encoding="utf-8"))["files"]
    for name, entry in inputs.items():
        if digest(source / name) != entry["sha256"]:
            raise ValueError(f"Publisher snapshot hash mismatch: {name}")
    holidays = parse_holidays(source / "holidays.csv")
    dates, annual, rejected = {}, {}, {}
    for year in config["source_years"]:
        try:
            rows, summary = load_year(source / f"jp{year}.csv", int(year), config["daytime_hours"])
        except (ValueError, csv.Error) as exc:
            rejected[year] = str(exc)
            continue
        dates.update(rows)
        annual[year] = summary
    primary, skipped, relocations = compare_holidays(dates, holidays, config)
    years = [int(y) for y in config["source_years"]]
    periods = {
        label: period_summary(primary, list(range(start, end + 1)), annual, config["practical_threshold_pp"])
        for label, (start, end) in config["periods"].items()
    }
    overall = period_summary(primary, years, annual, config["practical_threshold_pp"])
    return {
        "protocol_version": config["version"],
        "source_snapshot_sha256": SEALED["source-snapshot.json"],
        "annual_published_counts": annual,
        "source_years_rejected": rejected,
        "primary_holidays": primary,
        "holiday_dates_excluded": skipped,
        "relocations": relocations,
        "periods": periods,
        "overall": overall,
        "every_period_passes": all(row["practical_threshold_met"] for row in periods.values()) and not rejected,
        "individual_charts_computed": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.sources)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False, default=numeric)
        stream.write("\n")


if __name__ == "__main__":
    main()
