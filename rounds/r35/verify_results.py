"""Independently verify the released dates, denominators and contrasts with decimal arithmetic."""

from __future__ import annotations

import argparse
from csv import DictReader, reader
from datetime import date
from decimal import Decimal, localcontext
import gzip
from pathlib import Path

from rounds.r25.verify_results import ANNUAL_SHA
from rounds.r27.archive_source import digest, read_json, require, write_json


PERIOD = (date(1993, 1, 1), date(1999, 12, 31))
NAMES = {"海の日", "敬老の日", "体育の日", "スポーツの日"}
MARGINS = ("births", "known", "daytime", "other_known_hours", "unknown")
FIELDS = ("daytime_share_difference_pp", "daytime_count_change_pct", "other_hours_count_change_pct")
NATIONAL, CLINICAL = "all_venues", "hospital_and_clinic"
ANNUAL_TABLE_URL = "https://www.e-stat.go.jp/stat-search/file-download?fileKind=1&statInfId=000040503640"


def event_calendar(path):
    with path.open(encoding="cp932", newline="") as stream:
        importer = reader(stream)
        next(importer)
        return {date(*map(int, year_month_day.split("/"))): named for year_month_day, named in importer
                if year_month_day}


def event_counts(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        events = {}
        annual = {}
        for row in DictReader(stream):
            year, month, day = (int(row[unit]) for unit in ("year", "month", "day"))
            if row["venue"] == "総数" and month == day == 0:
                require(year not in annual, "Annual source count is repeated")
                annual[year] = int(row["total"])
            if not (month and day):
                continue
            daypart = 0
            known = 0
            for i in range(24):
                births = int(row[f"h{i:02d}"])
                known += births
                if 9 <= i <= 17:
                    daypart += births
            total = int(row["total"])
            events.setdefault(date(year, month, day), {})[row["venue"]] = (
                total, known, daypart, known - daypart, total - known)
    return events, annual


def publisher_totals(path):
    require(digest(path) == ANNUAL_SHA, "Official annual Table 4-1 differs from its independent review copy")
    with path.open(encoding="cp932", newline="") as stream:
        return {int(row[0]): int(row[1]) for row in reader(stream) if row and row[0].isdigit() and
                PERIOD[0].year <= int(row[0]) <= PERIOD[1].year}


def ratio_contrasts(target, references):
    n = len(references)
    target_ratio = Decimal(target[2]) / Decimal(target[1])
    control_ratio = sum(Decimal(d[2]) / Decimal(d[1]) for d in references) / n
    return (
        100 * (target_ratio - control_ratio),
        100 * (Decimal(target[2] * n) / sum(d[2] for d in references) - 1),
        100 * (Decimal(target[3] * n) / sum(d[3] for d in references) - 1),
    )


def event_pairing(events, calendar, d, adjacent_only):
    # Date ordinals provide an independent calendar cross-check.
    delta = 7 if adjacent_only else 14
    window = range(d.toordinal() - delta, d.toordinal() + delta + 1, 7)
    dates = [date.fromordinal(n) for n in window if n != d.toordinal()]
    references = [day for day in dates if day not in calendar and day in events]
    if not references or references[0] >= d or references[-1] <= d:
        return None
    in_scope = [events[day] for day in (d, *references)]
    scopes = {NATIONAL: [x["総数"] for x in in_scope]}
    if all("病院" in x and "診療所" in x for x in in_scope):
        scopes[CLINICAL] = [tuple(a + b for a, b in zip(x["病院"], x["診療所"], strict=True)) for x in in_scope]
    return references, scopes


def compare(actual, expected):
    delta = abs(Decimal(str(actual)) - expected)
    require(delta <= Decimal("0.000000000051"), f"Published comparison differs from independent arithmetic by {delta}")
    return delta


def check_summary(published, verified):
    require(published["matched_holidays"] == len(verified), "Holiday count disagrees")
    occurrences = sum(len(rows[1]) for rows in verified)
    require(published["control_date_occurrences"] == occurrences, "Control date count disagrees")
    for i, margin in enumerate(MARGINS):
        targets_sum = sum(row[0][i] for row in verified)
        controls_sum = sum(control[i] for _, controls, _ in verified for control in controls)
        require(published["target_counts"][margin] == targets_sum and
                published["control_counts_by_occurrence"][margin] == controls_sum, "Summary birth totals disagree")
    if not verified:
        require(all(published[field] is None for field in FIELDS), "A period without support has a result")
        return []
    return [compare(published[field], sum(metrics[i] for _, _, metrics in verified) / len(verified))
            for i, field in enumerate(FIELDS)]


def verify(directory, holidays, results, annual_table):
    receipt = read_json(directory / "source_receipt.json")
    result = read_json(results)
    counts_file = directory / "historical_counts.csv.gz"
    require(receipt["public_counts_sha256"] == digest(counts_file) and
            receipt["official_holiday_csv"]["sha256"] == digest(holidays) and
            result["source_receipt_sha256"] == digest(directory / "source_receipt.json"),
            "Verifier inputs have inconsistent digests")
    calendar = event_calendar(holidays)
    events, annual = event_counts(counts_file)
    require(len(events) == PERIOD[1].toordinal() - PERIOD[0].toordinal() + 1 and
            (min(events), max(events)) == PERIOD, "Historical data has missing dates")
    official = publisher_totals(annual_table)
    require(annual == official, "The historical table and separate official annual publication differ")
    for year, total in official.items():
        require(sum(scopes["総数"][0] for d, scopes in events.items() if d.year == year) == total,
                f"{year}: daily births do not match the annual publication")
    require(sum(official.values()) == result["source_births"], "Reported national source totals do not balance")
    require(sum(scopes["総数"][4] for scopes in events.values()) == result["source_births_unknown_hour"],
            "Independent known-hour count does not balance")
    candidates = {}
    for d, name in calendar.items():
        label = name.split("（", 1)[0]
        if PERIOD[0] <= d <= PERIOD[1] and d.isoweekday() < 6 and label in NAMES:
            candidates[d] = label
    indexed = {date.fromisoformat(row["date"]): row for row in result["weekday_holiday_cases"]}
    require(sorted(candidates) == sorted(indexed) and len(indexed) == len(result["weekday_holiday_cases"]),
            "The weekday candidate calendars disagree")
    series = {"main": {}, "adjacent_week": {}}
    discrepancies = []
    for d, label in sorted(candidates.items()):
        item = indexed[d]
        require(item["holiday"] == label and item["publisher_holiday_label"] == calendar[d]
                and item["is_monday"] == (d.isoweekday() == 1), "Holiday label or weekday disagrees")
        for design in series:
            fresh = event_pairing(events, calendar, d, design == "adjacent_week")
            paired = item[design]
            if fresh is None:
                require(paired is None, "Published result includes an unmatched holiday")
                continue
            references, scopes = fresh
            require(paired and paired["controls"] == [str(r) for r in references] and
                    set(paired) == {"controls", *scopes}, "Published matching dates or venue support disagrees")
            for scope, (target, *controls) in scopes.items():
                output = paired[scope]
                require(output["target_counts"] == dict(zip(MARGINS, target, strict=True)), "Target counts disagree")
                require(output["control_counts"] == {
                    str(day): dict(zip(MARGINS, counts, strict=True))
                    for day, counts in zip(references, controls, strict=True)
                }, "Control day counts disagree")
                metrics = ratio_contrasts(target, controls)
                discrepancies.extend(compare(output[field], number) for field, number in zip(FIELDS, metrics, strict=True))
                series[design].setdefault(d, {})[scope] = target, controls, metrics

    def select(dates, design, scope):
        return [series[design][d][scope] for d in dates if scope in series[design].get(d, {})]

    mondays = [d for d in candidates if d.isoweekday() == 1]
    for block, days in (("primary_mondays", mondays), ("secondary_all_weekdays", list(candidates))):
        aggregate = result[block]
        require(aggregate["candidate_holidays"] == len(days), "The published candidate count differs")
        main = select(days, "main", NATIONAL)
        supported_clinical = [d for d in days if CLINICAL in series["main"].get(d, {})]
        comparisons = [
            (aggregate["national"], main),
            (aggregate["national_adjacent_week"], select(days, "adjacent_week", NATIONAL)),
            (aggregate["clinic_and_hospital"], select(supported_clinical, "main", CLINICAL)),
            (aggregate["national_same_pairs_as_clinic_and_hospital"], select(supported_clinical, "main", NATIONAL)),
        ]
        by_year = {str(d.year) for d in days}
        by_holiday = {candidates[d] for d in days}
        require(set(aggregate["national_by_year"]) == by_year and set(aggregate["national_by_holiday"]) == by_holiday,
                "The published by-year or by-holiday groups differ")
        comparisons.extend((aggregate["national_by_year"][year],
                            select([d for d in days if str(d.year) == year], "main", NATIONAL)) for year in by_year)
        comparisons.extend((aggregate["national_by_holiday"][label],
                            select([d for d in days if candidates[d] == label], "main", NATIONAL)) for label in by_holiday)
        for published, verified in comparisons:
            discrepancies.extend(check_summary(published, verified))
        if block == "primary_mondays":
            require(aggregate["practical_threshold_pp"] == -5, "The practical threshold differs from preregistration")
            threshold = "incomplete_calendar_support"
            if len(main) == len(mondays):
                threshold = "met" if sum(m[0] for _, _, m in main) / len(main) <= -5 else "not_met"
            require(aggregate["threshold_status"] == threshold, "The registered threshold judgment differs")
    return {
        "independent_numeric_implementation": "decimal arithmetic from the released hourly counts",
        "calendar_days": len(events),
        "official_births": sum(official.values()),
        "official_annual_reference": {"url": ANNUAL_TABLE_URL, "sha256": ANNUAL_SHA,
                                      "verified_totals": official},
        "independently_checked_numeric_results": len(discrepancies),
        "max_absolute_rounding_difference": float(max(discrepancies)),
        "results_sha256": digest(results),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "holidays", "results", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--annual-table", type=Path, required=True)
    args = parser.parse_args()
    with localcontext() as ctx:
        ctx.prec = 50
        receipt = verify(args.directory, args.holidays, args.results, args.annual_table)
    write_json(args.output, receipt)
    print(receipt)


if __name__ == "__main__":
    main()
