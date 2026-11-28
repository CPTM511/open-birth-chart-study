"""Verify R43 primal and dual certificates and recompute all public estimates."""

from __future__ import annotations

import argparse
from fractions import Fraction
import gzip
import json
from pathlib import Path

from rounds.r27.archive_source import digest, read_json, require

from .inputs import AGE_PARAMETER_COUNT, DESIGN, HERE, HOURS, THRESHOLD, load_donors, load_target, provenance


def certified_objective(certificate, dates, minutes, hits, sense):
    donor_total, target_total = sum(minutes), sum(dates)
    row_weights = [n * donor_total for n in dates]
    col_weights = [n * target_total for n in minutes]
    actual_rows, actual_columns = [0] * len(dates), [0] * len(minutes)
    used = set()
    primal = 0
    for day, minute, weight in certificate["allocation"]:
        require(type(day) is int and type(minute) is int and type(weight) is int
                and 0 <= day < len(dates) and 0 <= minute < len(minutes) and weight > 0,
                "Invalid sparse allocation entry")
        require((day, minute) not in used, "Duplicate sparse allocation entry")
        used.add((day, minute))
        actual_rows[day] += weight
        actual_columns[minute] += weight
        primal += sense * hits[day][minute] * weight
    require(actual_rows == row_weights and actual_columns == col_weights, "Primal margins do not match")
    u, v = certificate["row_potentials"], certificate["column_potentials"]
    require(len(u) == len(dates) and len(v) == len(minutes) and all(type(item) is int for item in u + v),
            "Invalid integer dual dimensions or types")
    require(all(row_dual + column_dual <= sense * hits[day][minute]
                for day, row_dual in enumerate(u) for minute, column_dual in enumerate(v)), "Infeasible dual")
    dual = sum(w * value for w, value in zip(row_weights + col_weights, u + v, strict=True))
    require(type(certificate["signed_objective"]) is int and primal == dual == certificate["signed_objective"],
            "Integer primal and dual objectives do not agree")
    return sense * primal


def check_result(published, value):
    if isinstance(value, Fraction):
        require(Fraction(published["exact"]) == value and published["value"] == float(value),
                "Published exact or decimal result differs")
    elif isinstance(value, dict):
        require(published.keys() == value.keys(), "Published result keys differ")
        for key in value:
            check_result(published[key], value[key])
    elif isinstance(value, list):
        require(len(published) == len(value), "Published list length differs")
        for old, new in zip(published, value, strict=True):
            check_result(old, new)
    else:
        require(type(published) is type(value) and published == value, "Published counts or threshold checks differ")


def check_release(donors_path, certificates_path, results_path):
    donors = load_donors(donors_path)
    baseline, targets = load_target()
    with gzip.open(certificates_path, "rt", encoding="utf-8") as handle:
        certificates = json.load(handle)
    results = read_json(results_path)
    expected_receipts = provenance(donors_path)
    require(certificates["round"] == results["round"] == "R43"
            and certificates["inputs"] == results["inputs"] == expected_receipts,
            "R43 release artifacts use different inputs")
    require(results["certificates_sha256"] == digest(certificates_path), "Published certificate digest differs")
    require(results["r41_registration_commit"] == DESIGN["target_registration_sha"], "Wrong R41 registration")
    check_result(results["reference_joint_rate"], baseline)
    check_result(results["attention_threshold_pp"], THRESHOLD)
    require(set(certificates["years"]) == set(results["years"]) == set(targets), "Unexpected target panels")
    verified = 0
    for year, panel in targets.items():
        totals, values, n = panel["counts"], panel["hits"], panel["total"]
        unrestricted = [
            100 * (sum(weight * bound(values[h][d]) for h in HOURS for d, weight in enumerate(totals[h]))
                   / Fraction(AGE_PARAMETER_COUNT * n) - baseline)
            for bound in (min, max)
        ]
        require(unrestricted == panel["unrestricted"], f"Unrestricted R41 bound differs for {year}")
        released = results["years"][year]
        check_result(released["official_birth_count"], n)
        check_result(released["unrestricted_delta_to_brazil_pp"], unrestricted)
        require(set(certificates["years"][year]) == set(released["donors"]) == set(donors), "Unexpected donors")
        for donor, time_counts in donors.items():
            details = certificates["years"][year][donor]
            require(details["date_order"] == panel["dates"] and len(details["hours"]) == len(HOURS),
                    "Certificates use an unexpected date or hour order")
            lo = hi = point = Fraction()
            for h in HOURS:
                proof = details["hours"][h]
                clock, rows, hits = time_counts[h], totals[h], values[h]
                require(proof["hour"] == h, "Certificate hour index differs")
                denominator = sum(clock) * n * AGE_PARAMETER_COUNT
                lo += Fraction(certified_objective(proof["minimum"], rows, clock, hits, 1), denominator)
                hi += Fraction(certified_objective(proof["maximum"], rows, clock, hits, -1), denominator)
                for count, day in zip(rows, hits, strict=True):
                    point += Fraction(count * sum(value * c for value, c in zip(day, clock, strict=True)),
                                      denominator)
                verified += 2
            low, middle, high = [100 * (value - baseline) for value in (lo, point, hi)]
            require(unrestricted[0] <= low <= middle <= high <= unrestricted[1],
                    "Certified estimates fall outside the admissible intervals")
            check_result(released["donors"][donor], {
                "joint_rate_bounds": [lo, hi],
                "common_daily_minute_profile_joint_rate": point,
                "delta_to_brazil_pp_bounds": [low, high],
                "common_daily_minute_profile_delta_to_brazil_pp": middle,
                "narrowing_at_lower_and_upper_pp": [low - unrestricted[0], unrestricted[1] - high],
                "thresholds": {
                    "can_include_zero": low <= 0 <= high,
                    "strictly_straddles_zero": low < 0 < high,
                    "can_reach_negative_attention_threshold": low <= -THRESHOLD,
                    "can_reach_positive_attention_threshold": high >= THRESHOLD,
                },
            })
    require(verified == results["verified_endpoint_certificates"], "Incomplete certificate coverage")
    print(f"{verified} exact certificates verified; all endpoint, point and threshold results reproduced")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donors", type=Path, default=HERE / "donor_counts.json")
    parser.add_argument("--certificates", type=Path, default=HERE / "certificates.json.gz")
    parser.add_argument("--results", type=Path, default=HERE / "results.json")
    arguments = parser.parse_args()
    check_release(arguments.donors, arguments.certificates, arguments.results)
