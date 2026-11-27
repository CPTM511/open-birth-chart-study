"""Verify R26 point estimates with integer record-year counts and rational weights."""
import argparse
from collections import defaultdict
from datetime import date
from fractions import Fraction
import json
from pathlib import Path

from rounds.r26.clock_balance import load_cohorts, read_registered_config

HERE = Path(__file__).resolve().parent


def check(condition: bool, explanation: str) -> None:
    if not condition:
        raise ValueError(explanation)


def exact_rates(cohort, config, *, by_month: bool) -> tuple[Fraction, Fraction]:
    strata = defaultdict(list)
    for row, hits in zip(cohort.rows, cohort.joint_years, strict=True):
        birthday = date.fromisoformat(row["birth_local"][:10])
        quarter = 1 + (birthday.month - 1) // 3
        weekday = birthday.isoweekday() < 6
        hour = int(row["birth_local"][11:13])
        lo, hi = config["daytime_hours_inclusive"]
        strata[birthday.month if by_month else quarter, row["sex"]].append(
            ((weekday, lo <= hour <= hi), Fraction(row["N_h"], row["n_h"]), int(hits))
        )
    numerator = Fraction(0)
    adjusted = Fraction(0)
    frame = Fraction(0)
    for rows in strata.values():
        masses = defaultdict(Fraction)
        day_masses = defaultdict(Fraction)
        hour_masses = defaultdict(Fraction)
        for (weekday, dayhour), weight, hit_count in rows:
            masses[weekday, dayhour] += weight
            day_masses[weekday] += weight
            hour_masses[dayhour] += weight
            numerator += weight * hit_count
        check(len(masses) == 4, "The exact verification needs all four observed cells")
        group_mass = sum(masses.values(), Fraction(0))
        actual_margins = defaultdict(Fraction)
        for (weekday, dayhour), weight, hit_count in rows:
            new = weight * day_masses[weekday] * hour_masses[dayhour] / (group_mass * masses[weekday, dayhour])
            adjusted += new * hit_count
            actual_margins["weekday", weekday] += new
            actual_margins["daytime", dayhour] += new
        check(all(actual_margins["weekday", key] == value for key, value in day_masses.items()),
              "Reweighted weekdays differ from their original marginal")
        check(all(actual_margins["daytime", key] == value for key, value in hour_masses.items()),
              "Reweighted clock categories differ from their original marginal")
        frame += group_mass
    check(frame == sum(cohort.frame_sizes.values()), "Weights do not sum to the eligible frame")
    years = frame * config["aging_years"]
    return numerator / years, adjusted / years


def verify(r10_job: Path, r12_job: Path) -> dict:
    cfg = read_registered_config()
    report = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    data = load_cohorts(r10_job, r12_job, cfg)
    quarterly = {}
    monthly = {}
    for co in data:
        published = report["cohorts"][co.slot]
        quarterly[co.slot] = exact_rates(co, cfg, by_month=False)
        monthly[co.slot] = exact_rates(co, cfg, by_month=True)
        raw, q = quarterly[co.slot]
        raw_m, m = monthly[co.slot]
        check(raw == raw_m, "Original rate changes by calendar resolution")
        check(abs(float(raw) - published["observed_rate"]) < 1e-11, "Original weighted rate differs")
        check(abs(float(q) - published[cfg["primary_level"]]["adjusted_rate"]) < 1e-11, "Quarterly rate differs")
        check(abs(float(m) - published[cfg["sensitivity_level"]]["adjusted_rate"]) < 1e-11, "Monthly rate differs")
    for level, exact in ((cfg["primary_level"], quarterly), (cfg["sensitivity_level"], monthly)):
        raw_ref, adjusted_ref = exact[cfg["reference"]]
        for slot, compared in report["contrasts"].items():
            raw, adjusted = exact[slot]
            move = 100 * ((adjusted - adjusted_ref) - (raw - raw_ref))
            check(abs(float(move) - compared[level]["contrast_movement_pp"]) < 1e-10,
                  "Reweighted comparison does not match exact arithmetic")
    return {
        "cohorts": len(data),
        "weighted_rates_recomputed": len(data) * 3,
        "reweighted_cross_cohort_contrasts_verified": (len(data) - 1) * 2,
        "both_calendar_and_clock_margins_match_exactly": True,
        "frozen_model_record_years": sum(len(co.rows) * cfg["aging_years"] for co in data),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r10-job", type=Path, required=True)
    parser.add_argument("--r12-job", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.r10_job, args.r12_job), indent=2))
