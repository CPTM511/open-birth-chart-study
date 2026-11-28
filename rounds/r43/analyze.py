"""Compute hour-coupled clock sensitivities under each frozen donor marginal."""

from __future__ import annotations

import argparse
from fractions import Fraction
import gzip
import io
import json
from pathlib import Path

import scipy

from rounds.r27.archive_source import digest, require, write_json

from .check_release import certified_objective
from .inputs import AGE_PARAMETER_COUNT, DESIGN, HOURS, THRESHOLD, load_donors, load_target, provenance
from .transport import extremizers


def comparable(values):
    if isinstance(values, Fraction):
        return {"exact": str(values), "value": float(values)}
    if isinstance(values, dict):
        return {key: comparable(value) for key, value in values.items()}
    if isinstance(values, list):
        return [comparable(value) for value in values]
    return values


def analyze_panel(panel, donor, reference):
    proofs = []
    low, point, high = Fraction(), Fraction(), Fraction()
    for hour, counts, clock, hits in zip(HOURS, panel["counts"], donor, panel["hits"], strict=True):
        pair = extremizers(counts, clock, hits)
        donor_count = sum(clock)
        low += Fraction(certified_objective(pair["minimum"], counts, clock, hits, 1), donor_count)
        high += Fraction(certified_objective(pair["maximum"], counts, clock, hits, -1), donor_count)
        independent = sum(count * minute_count * hit
                          for count, day in zip(counts, hits, strict=True)
                          for minute_count, hit in zip(clock, day, strict=True))
        point += Fraction(independent, donor_count)
        proofs.append({"hour": hour, **pair})
    burden = AGE_PARAMETER_COUNT * panel["total"]
    rate_low, rate_point, rate_high = [value / burden for value in (low, point, high)]
    lpp, ppp, upp = [100 * (rate - reference) for rate in (rate_low, rate_point, rate_high)]
    old_low, old_high = panel["unrestricted"]
    require(old_low <= lpp <= ppp <= upp <= old_high, "Calculated endpoints fall outside the specified domain")
    summary = {
        "joint_rate_bounds": [rate_low, rate_high],
        "common_daily_minute_profile_joint_rate": rate_point,
        "delta_to_brazil_pp_bounds": [lpp, upp],
        "common_daily_minute_profile_delta_to_brazil_pp": ppp,
        "narrowing_at_lower_and_upper_pp": [lpp - old_low, old_high - upp],
        "thresholds": {
            "can_include_zero": lpp <= 0 <= upp,
            "strictly_straddles_zero": lpp < 0 < upp,
            "can_reach_negative_attention_threshold": lpp <= -THRESHOLD,
            "can_reach_positive_attention_threshold": upp >= THRESHOLD,
        },
    }
    return summary, {"date_order": panel["dates"], "hours": proofs}


def analyze(donors_path, certificates_path, results_path):
    donors = load_donors(donors_path)
    reference, panels = load_target()
    receipts = provenance(donors_path)
    report = {
        "round": "R43",
        "inputs": receipts,
        "r41_registration_commit": DESIGN["target_registration_sha"],
        "solver": {"scipy_version": scipy.__version__, "method": "highs-ds"},
        "reference_joint_rate": reference,
        "attention_threshold_pp": THRESHOLD,
        "verified_endpoint_certificates": 0,
        "years": {},
    }
    certificates = {"round": "R43", "inputs": receipts, "years": {}}
    for year, panel in panels.items():
        summary, proofs = {}, {}
        for key, clock in donors.items():
            summary[key], proofs[key] = analyze_panel(panel, clock, reference)
            report["verified_endpoint_certificates"] += 2 * len(proofs[key]["hours"])
        report["years"][year] = {"official_birth_count": panel["total"],
                                 "unrestricted_delta_to_brazil_pp": panel["unrestricted"], "donors": summary}
        certificates["years"][year] = proofs
    with certificates_path.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with io.TextIOWrapper(zipped, encoding="utf-8") as handle:
            json.dump(certificates, handle, separators=(",", ":"), allow_nan=False)
            handle.write("\n")
    report["certificates_sha256"] = digest(certificates_path)
    write_json(results_path, comparable(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donors", type=Path, required=True)
    parser.add_argument("--certificates", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    arguments = parser.parse_args()
    analyze(arguments.donors, arguments.certificates, arguments.results)
