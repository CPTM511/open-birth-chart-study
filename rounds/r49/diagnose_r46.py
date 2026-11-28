"""Replay both R46 P75 upper bounds using the sealed public group curves."""

import argparse
from pathlib import Path

import numpy as np

from rounds.r45.review import check_equal
from rounds.r46.analyze import directional, family_band, prior_selection
from rounds.r46.common import protocol as r46_protocol

from .common import REGISTRATION, ROOT, protocol, read_json, require, write_json


def replay(settings):
    old = read_json(ROOT / "rounds/r46/results.json")
    ages = old["age_starts"]
    rule = prior_selection(r46_protocol(), ages)["four_p75"]
    issued = old["primary"]["four_p75"]
    require(issued["preselected_witnesses"] == rule, "R46's prior selection did not replay")
    family = old["families"]["p75_recorded"]
    curves = {name: np.asarray(group["effect_curve"]) for name, group in family["groups"].items()}
    errors = {name: np.asarray(group["conditional_standard_error"]) for name, group in family["groups"].items()}
    margins = {name: np.asarray(group["simultaneous_margin"]) for name, group in family["groups"].items()}
    interest = settings["gap_threshold"]
    main = directional(curves, errors, rule, ages, interest)
    simultaneous = family_band(curves, margins, ages, interest)
    compare = family["peaks"]["all_groups"]
    check_equal([main["point"], *main["interval"]], [issued["point"], *issued["interval"]], "R46 main replay")
    check_equal([simultaneous["point"], *simultaneous["simultaneous_interval"]],
                [compare["point"], *compare["simultaneous_interval"]], "R46 simultaneous replay")
    require(main["decision"] == issued["decision"] and simultaneous["decision"] == compare["decision"],
            "R46's upper-bound decision changed")

    per_age = []
    for i, age in enumerate(ages):
        fixed = rule["groups_by_age"][i]
        fixed_upper = curves[fixed][i] + rule["z"] * errors[fixed][i]
        available = {g: curves[g][i] + margins[g][i] for g in curves}
        projected = min(available, key=lambda name: (available[name], name))
        per_age.append(dict(age=age, r46_fixed_group=fixed, fixed_upper=float(fixed_upper),
                            r46_simultaneous_group=projected, simultaneous_upper=float(available[projected]),
                            same_group_with_simultaneous_margin=float(available[fixed])))
    peak_main = max(per_age, key=lambda row: row["fixed_upper"])
    peak_simultaneous = max(per_age, key=lambda row: row["simultaneous_upper"])
    bottleneck = ages.index(peak_main["age"])
    at_bottleneck = {
        g: dict(effect=float(curves[g][bottleneck]), standard_error=float(errors[g][bottleneck]),
                old_pointwise_upper=float(curves[g][bottleneck] + rule["z"] * errors[g][bottleneck]),
                simultaneous_upper=float(curves[g][bottleneck] + margins[g][bottleneck]))
        for g in curves
    }
    explanation = dict(registration=REGISTRATION, old_aggregate_sha256=settings["r46_aggregate_sha256"],
                       age_start=peak_main["age"], group_values_at_old_upper_max=at_bottleneck,
                       fixed_witness=main, simultaneous=simultaneous, simultaneous_critical=old["critical"],
                       fixed_upper_peak=peak_main, simultaneous_upper_peak=peak_simultaneous, per_age=per_age)
    return explanation, rule


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    explanation, _ = replay(protocol())
    write_json(args.output, explanation)


if __name__ == "__main__":
    main()
