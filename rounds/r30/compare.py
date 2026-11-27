"""Compare both fixed releases with the frozen Brazil reference and verify the counts."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, time, timedelta
from fractions import Fraction
from importlib.metadata import PackageNotFoundError, version
from math import fsum, isclose
from pathlib import Path
import platform
import subprocess
from zoneinfo import TZPATH

import numpy as np

from rounds.r27.analyze import PrecisionReference, load_reference
from rounds.r27.archive_source import ROOT, write_json
from rounds.r27.verify import weighted_rank_tables, year_hits
from rounds.r29.clock_pairs import read_pairs, rounding_shift
from rounds.r29.compare import check_transitions, integer_flags, paired_metrics
from .study import CONFIG, HERE, digest, in_window, inputs, private_job, read_json, require


SYSTEMS = ("bazi", "ziwei_doushu", "qizheng_siyu", "western_astrology")
EFFECT_PP = 0.30


def timezone_release():
    for directory in map(Path, TZPATH):
        if (directory / CONFIG["timezone"]).is_file():
            manifest = directory / "tzdata.zi"
            if manifest.is_file():
                with manifest.open(encoding="ascii") as stream:
                    header = stream.readline().split()
                if len(header) >= 3 and header[:2] == ["#", "version"]:
                    return header[2]
            return None
    try:
        return version("tzdata")
    except PackageNotFoundError:
        return None


def estimate(joint, reference):
    records = len(joint)
    require(records > 0, "No records in the registered comparison window")
    hits = int(joint.sum())
    rate = hits / (40 * records)
    return {"records": records, "joint_years": hits, "joint_rate": rate, "delta_pp": 100 * (rate - reference)}


def summarize(rows, arrays, flags, reference, shifted):
    civil = [datetime.fromisoformat(row["birth_local"]) for row in rows]
    months = np.asarray([value.date().isoformat()[:7] for value in civil])
    first_for_clock_and_sex = {}
    for index, row in enumerate(rows):
        first_for_clock_and_sex.setdefault((row["birth_local"], row["sex"]), index)
    joint = flags[0].sum(axis=2) >= 3
    omitted = [estimate(joint[months != month], reference)["delta_pp"] for month in np.unique(months)]
    result = {
        **estimate(joint, reference),
        "record_years": len(rows) * 40,
        "age_band_joint_rates": np.reshape(joint, (len(rows), 4, 10)).mean(axis=(0, 2)).tolist(),
        "system_high_rates": flags[0].mean(axis=(0, 1)).tolist(),
        "system_raw_means": arrays[0].mean(axis=(0, 1)).tolist(),
        "common_2022_window": estimate(joint[[in_window(v.date(), CONFIG["common_window"]) for v in civil]], reference),
        "born_through_2025": estimate(joint[[v.year <= 2025 for v in civil]], reference),
        "leave_one_month_out_delta_pp": [min(omitted), max(omitted)],
        "exclude_midnight": estimate(joint[[v.time() != time(0) for v in civil]], reference),
        "one_per_clock_and_sex": estimate(joint[list(first_for_clock_and_sex.values())], reference),
        "clock_rounding": {
            **paired_metrics(flags, np.ones(len(rows))),
            "changed_clocks": shifted,
            "rounded_across_midnight": sum((v + timedelta(minutes=rounding_shift(v))).date() != v.date() for v in civil),
        },
    }
    return result


def verify_counts(rows, scores, flags, result, reference):
    joint = [[sum(year) >= 3 for year in person] for person in flags[0]]
    counts = [sum(1 for hit in person if hit) for person in joint]
    total_hits = sum(counts)
    count_by_month, hits_by_month = Counter(), Counter()
    common, through_2025, non_midnight, collapsed = [], [], [], []
    seen = set()
    start, end = CONFIG["common_window"]
    for row, hits in zip(rows, counts, strict=True):
        date, time = row["birth_local"].split("T")
        month = date[:7]
        count_by_month[month] += 1
        hits_by_month[month] += hits
        if start <= date <= end:
            common.append(hits)
        if date[:4] <= "2025":
            through_2025.append(hits)
        if time != "00:00:00":
            non_midnight.append(hits)
        key = (row["birth_local"], row["sex"])
        if key not in seen:
            seen.add(key)
            collapsed.append(hits)

    groups = {"full_archive": counts, "common_2022_window": common, "born_through_2025": through_2025,
              "exclude_midnight": non_midnight, "one_per_clock_and_sex": collapsed}
    exact_rates = {}
    for name, group in groups.items():
        observed = result if name == "full_archive" else result[name]
        rate = Fraction(sum(group), 40 * len(group))
        exact_rates[name] = str(rate)
        require(observed["records"] == len(group) and observed["joint_years"] == sum(group)
                and isclose(observed["joint_rate"], float(rate), rel_tol=0, abs_tol=1e-13)
                and isclose(observed["delta_pp"], float(100 * (rate - reference)), rel_tol=0, abs_tol=1e-12),
                f"Independent rate or denominator differs for {name}")
    remaining = [100 * (Fraction(total_hits - hits_by_month[key], 40 * (len(rows) - n)) - reference)
                 for key, n in count_by_month.items()]
    require(np.allclose([float(min(remaining)), float(max(remaining))], result["leave_one_month_out_delta_pp"],
                        rtol=0, atol=1e-12), "Independent month omission disagrees")

    band_hits = [sum(sum(person[i:i + 10]) for person in joint) / (len(rows) * 10) for i in range(0, 40, 10)]
    system_hits = [sum(1 for person in flags[0] for year in person if year[i]) / (len(rows) * 40) for i in range(4)]
    raw_means = [fsum(year[i] for person in scores[0] for year in person) / (len(rows) * 40) for i in range(4)]
    for expected, field in ((band_hits, "age_band_joint_rates"), (system_hits, "system_high_rates"),
                            (raw_means, "system_raw_means")):
        require(np.allclose(expected, result[field], rtol=0, atol=1e-13), f"Independent {field} differs")
    return {
        "exact_joint_rates": exact_rates,
        "month_omission_delta_pp_exact": [str(min(remaining)), str(max(remaining))],
        "exact_clock_transition_rates": check_transitions(flags, [Fraction(1)] * len(rows), result["clock_rounding"]),
    }


def compute(primary, replay, r10_job, output):
    require(primary != replay, "Supply separate acquisition and scoring directories")
    source, source_replay = (read_json(run / "source_receipt.json") for run in (primary, replay))
    require({source["format"], source_replay["format"]} == {"csv", "json"}, "The two formats must be retrieved separately")
    groups, coverage = inputs(primary)
    replay_groups, replay_coverage = inputs(replay)
    require(groups == replay_groups and coverage == replay_coverage, "Separate source formats produce different model inputs")
    require(all(source["sites"][site]["private_projection_sha256"] == source_replay["sites"][site]["private_projection_sha256"]
                for site in groups), "The two independently retrieved record projections differ")
    profile_path = primary / "profiles.jsonl"
    profiles_sha256 = digest(profile_path)
    require(profiles_sha256 == digest(replay / profile_path.name), "Two scoring runs differ")
    date_receipt, date_replay = (read_json(run / "date_extension_receipt.json") for run in (primary, replay))
    require(date_receipt == date_replay
            and date_receipt["amendment_sha256"] == digest(HERE / "DATE_RANGE_AMENDMENT.zh.md")
            and date_receipt["birth_year_2026_trajectories"] > 0, "The two amended date-range receipts differ")

    reference, float_weights, exact_weights = load_reference(r10_job)
    calibration = PrecisionReference(reference, float_weights, exact_weights)
    rank_tables = weighted_rank_tables(reference, exact_weights)
    exact_reference = sum(weight * hits for weight, hits in zip(exact_weights, year_hits(reference, rank_tables), strict=True))
    exact_reference /= 40 * sum(exact_weights)
    published = read_json(ROOT / "rounds/r10/independent_replay/results/structural_comparison.json")["reference"]["joint_rate"]
    require(isclose(calibration.joint_rate, published, rel_tol=0, abs_tol=1e-13)
            and isclose(float(exact_reference), published, rel_tol=0, abs_tol=1e-13), "Frozen reference rate differs")

    estimates, independent, case_trajectories = {}, {}, 0
    for name, (scores, shifted) in read_pairs(groups, profile_path).items():
        rows, _ = groups[name]
        case_trajectories += len(rows) + shifted
        flags = np.asarray([calibration.flags(branch) for branch in scores])
        exact_flags = np.asarray([integer_flags(branch, rank_tables) for branch in scores])
        require(np.array_equal(flags, exact_flags), "Independent threshold classifications differ")
        estimates[name] = summarize(rows, scores, flags, calibration.joint_rate, shifted)
        independent[name] = verify_counts(rows, scores, exact_flags, estimates[name], exact_reference)

    thresholds = []
    for site in estimates.values():
        thresholds.extend((site["delta_pp"], site["common_2022_window"]["delta_pp"], *site["leave_one_month_out_delta_pp"]))
    stable_direction = next((label for label, sign in (("higher", 1), ("lower", -1))
                             if all(sign * delta >= EFFECT_PP for delta in thresholds)), None)
    common_difference = (estimates["colon"]["common_2022_window"]["joint_rate"]
                         - estimates["duitama"]["common_2022_window"]["joint_rate"]) * 100
    exact_common_difference = (Fraction(independent["colon"]["exact_joint_rates"]["common_2022_window"])
                               - Fraction(independent["duitama"]["exact_joint_rates"]["common_2022_window"])) * 100
    require(isclose(common_difference, float(exact_common_difference), rel_tol=0, abs_tol=1e-12),
            "Independent common-period site contrast differs")

    code = [*HERE.glob("*.py"), *sorted((ROOT / "src/open_birth_chart").glob("*.py")),
            ROOT / "src/open_birth_chart/ziwei_bridge.cjs",
            *(ROOT / f"rounds/{f}" for f in ("r27/archive_source.py", "r27/study.py", "r27/analyze.py", "r27/verify.py",
                                             "r29/clock_pairs.py", "r29/compare.py", "r10/methods/r10_io.py",
                                             "r10/methods/run_profiles.py", "r10/methods/analyze_cohorts.py")),
            *(p for p in (ROOT / "rounds/r10/methods/open_birth_chart_r10").glob("*") if p.is_file())]
    write_json(output, {
        "round": "R30",
        "registration_sha256": digest(HERE / "REGISTRATION.zh.md"),
        "fixed_reference": {"cohort": "brazil2006", "records": 2000, "joint_rate": calibration.joint_rate,
                            "exact_joint_rate": str(exact_reference)},
        "system_order": list(SYSTEMS),
        "common_2022_window": CONFIG["common_window"],
        "source_retrievals": {receipt["format"]: receipt for receipt in (source, source_replay)},
        "coverage": coverage,
        "estimates": estimates,
        "common_window_colon_minus_duitama_pp": common_difference,
        "same_direction_gate_pp": EFFECT_PP,
        "same_direction_at_registered_scale": stable_direction,
        "verification": {
            "different_formats_projected_bytes_match": True,
            "score_runs": 2,
            "score_trajectories_per_run": case_trajectories,
            "two_score_file_hashes_match_sha256": profiles_sha256,
            "independent_integer_threshold_flags_and_summary_match": True,
            "date_extension": date_receipt,
            "exact_counts_and_rates": independent,
            "software": {"platform": platform.platform(), "python": platform.python_version(),
                         "numpy": version("numpy"), "swiss_ephemeris": version("pyswisseph"),
                         "lunar_python": version("lunar-python"), "timezone_release": timezone_release(),
                         "zone_and_source_offset_seconds": [CONFIG["timezone"], CONFIG["source_offset_seconds"]],
                         "node": subprocess.check_output(["node", "--version"], text=True).strip()},
            "code_sha256": {str(path.relative_to(ROOT)): digest(path) for path in sorted(code)},
        },
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--replay-job", required=True, type=Path)
    parser.add_argument("--r10-job", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    compute(private_job(args.job), private_job(args.replay_job), args.r10_job, args.output)
