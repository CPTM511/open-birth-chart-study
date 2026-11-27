"""Independently check the frozen R25 report using raw all-venue CSV cells."""
import argparse
import csv
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANNUAL_SHA = "21221dd463005c5d7c52bb04337a0db184196f8960f88ec70b11dfa5ed52a746"
TRANSLATION = str.maketrans("０１２３４５６７８９", "0123456789", "\u3000 \t")


def ensure(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError(detail)


def read_annual_totals(path: Path) -> dict[int, int]:
    ensure(sha256(path.read_bytes()).hexdigest() == ANNUAL_SHA, "Annual Table 4-1 differs from its review copy")
    with path.open(encoding="cp932", newline="") as stream:
        totals = {int(row[0]): int(row[1]) for row in csv.reader(stream)
                  if row and row[0].strip().isdigit() and 2000 <= int(row[0]) <= 2025}
    ensure(set(totals) == set(range(2000, 2026)), "Annual Table 4-1 coverage does not match R25")
    return totals


def read_all_venue_dates(path: Path, year: int) -> dict[date, tuple[int, int, int]]:
    group = ""
    month = ""
    daily = {}
    with path.open(encoding="cp932", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) == 1 and "*" in row[0]:
                group, month = row[0].translate(TRANSLATION).split("*", maxsplit=1)
                continue
            elif len(row) != 26 or group != "総数" or not month.endswith("月"):
                continue
            day = row[0].translate(TRANSLATION)
            if not day.endswith("日"):
                continue
            vals = [0 if x == "-" else int(x) for x in row[1:]]
            try:
                d = date(year, int(month[:-1]), int(day[:-1]))
            except ValueError:
                ensure(not any(vals), "Invalid date has nonzero row")
                continue
            ensure(d not in daily, "Duplicate source date")
            daily[d] = (vals[0], sum(vals[1:]), sum(vals[10:19]))
    ensure(len(daily) == (date(year + 1, 1, 1) - date(year, 1, 1)).days, "The input year has missing dates")
    return daily


def mean(values) -> Fraction:
    values = list(values)
    return sum(values, Fraction(0)) / len(values)


def verified_contrast(points: dict, holidays: set, day: date, report: dict) -> Fraction:
    # Comparing ordinals makes the date-offset calculation independent of the analysis routine.
    d = day.toordinal()
    refs = [date.fromordinal(index) for index in range(d - 14, d + 15, 7)
            if index != d and date.fromordinal(index) not in holidays]
    ensure([v.isoformat() for v in refs] == report["matched_control_days"], f"Controls differ for {day}")
    for reference in refs:
        total, known, daytime = points[reference]
        raw = report["control_counts_all_venues"][reference.isoformat()]
        ensure((raw["births"], raw["known"], raw["daytime"]) == (total, known, daytime),
               f"Control counts differ on {reference}")
    total, known, daytime = points[day]
    target_raw = report["all_venues"]["target_counts"]
    ensure((target_raw["births"], target_raw["known"], target_raw["daytime"]) == (total, known, daytime),
           f"Target counts differ on {day}")
    contrast = 100 * (Fraction(daytime, known) - mean(Fraction(points[x][2], points[x][1]) for x in refs))
    ensure(abs(float(contrast) - report["all_venues"]["daytime_share_difference_pp"]) < 1e-9,
           f"Primary share difference differs on {day}")
    daytime_control = mean(points[x][2] for x in refs)
    other_control = mean(points[x][1] - points[x][2] for x in refs)
    for field, exact in [
        ("daytime_count_change_pct", 100 * (Fraction(daytime) / daytime_control - 1)),
        ("other_hours_count_change_pct", 100 * (Fraction(known - daytime) / other_control - 1)),
    ]:
        ensure(abs(float(exact) - report["all_venues"][field]) < 1e-9, f"Count comparison differs on {day}")
    return contrast


def verify(sources: Path, annual_table: Path) -> dict:
    result = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    published = read_annual_totals(annual_table)
    points = {}
    for year, total in published.items():
        raw = read_all_venue_dates(sources / f"jp{year}.csv", year)
        points.update(raw)
        report = result["annual_published_counts"][str(year)]
        ensure(sum(x[0] for x in raw.values()) == report["births"] == total, f"Annual total mismatch in {year}")
        ensure(sum(x[1] for x in raw.values()) == report["known"], f"Known-hour total mismatch in {year}")
        ensure(sum(x[2] for x in raw.values()) == report["daytime"], f"Daytime-hour total mismatch in {year}")

    with (sources / "holidays.csv").open(encoding="cp932", newline="") as stream:
        calendar = {date(*map(int, stamp.split("/"))): name for stamp, name in filter(None, list(csv.reader(stream))[1:])}
    names = {"海の日", "敬老の日", "体育の日", "スポーツの日", "体育の日（スポーツの日）"}
    holidays = set(calendar)
    matched = {d.isoformat() for d in calendar if d in points and calendar[d] in names and d.toordinal() % 7 == 1}
    records = result["primary_holidays"]
    ensure(matched == {row["date"] for row in records}, "One or more registered Monday holidays were missed")
    days = {row["date"]: verified_contrast(points, holidays, date.fromisoformat(row["date"]), row["main"])
            for row in records}
    groups = {"overall": days.values()}
    for tag, bound in {"2000s": (2000, 2009), "2010s": (2010, 2019), "2020s": (2020, 2025)}.items():
        groups[tag] = [value for stamp, value in days.items() if bound[0] <= int(stamp[:4]) <= bound[1]]
    observed = {tag: mean(data) for tag, data in groups.items()}
    for tag, pp in observed.items():
        report = result["overall"] if tag == "overall" else result["periods"][tag]
        ensure(abs(float(pp) - report["all_venues"]["daytime_share_difference_pp"]) < 1e-9,
               f"Average estimate differs: {tag}")
    for item in result["relocations"]:
        actual, usual = [date.fromisoformat(item[key]) for key in ("actual_date", "usual_date")]
        ensure(actual in holidays and usual not in holidays and calendar[actual] == item["holiday"],
               "Calendar labels disagree with relocation")
        a = verified_contrast(points, holidays, actual, item["actual_holiday"])
        b = verified_contrast(points, holidays, usual, item["usual_non_holiday"])
        ensure(abs(float(a - b) - item["actual_minus_usual_share_difference_pp"]) < 1e-9,
               "Relocation effect disagrees")
    return {
        "verified_annual_totals_against_table_4_1": len(published),
        "verified_daily_rows": len(points),
        "checked_main_date_comparisons": len(days),
        "checked_relocation_pairs": len(result["relocations"]),
        "checked_aggregate_primary_estimates": len(observed),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", required=True, type=Path)
    p.add_argument("--annual-table", required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(verify(args.sources, args.annual_table), indent=2))
