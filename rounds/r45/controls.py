"""Calendar-preserving pairing permutations and predeclared injection checks."""

from collections import defaultdict
from datetime import date

import numpy as np

from .common import require
from .estimate import curve_summary, reference_curves, residuals, weight_means, windows


def cells(rows):
    by_cell = defaultdict(list)
    for index, row in enumerate(rows):
        born = date.fromisoformat(row["birth_local"][:10])
        key = row["stratum_id"], (born.month-1)//3+1, row["calendar_years"][0]
        by_cell[key].append(index)
    return [np.array(by_cell[key]) for key in sorted(by_cell)]


def shuffle_flags(flags, blocks, rng):
    paired = flags.copy()
    for indices in blocks:
        if len(indices) <= 1:
            continue
        for system in (1, 2, 3):
            paired[indices, :, system] = flags[rng.permutation(indices), :, system]
    return paired


def check_shuffle(before, after, blocks):
    require(np.array_equal(before[:, :, 0], after[:, :, 0]), "Fixed Bazi trajectories were permuted")
    for group in blocks:
        for i in (1, 2, 3):
            a, b = [sorted(row.tobytes() for row in flags[group, :, i]) for flags in (before, after)]
            require(a == b, "Pairing changed the multiset of complete trajectories within a block")


def pairing_control(cohorts, all_flags, layout, cfg, measured):
    settings = cfg["inference"]
    rng = np.random.default_rng(settings["pairing_permutation_seed"])
    all_cells, movable, years = {}, {}, {}
    for name, cohort in cohorts.items():
        blocks = cells(cohort.rows)
        all_cells[name] = blocks
        movable_ids = [i for group in blocks if len(group) > 1 for i in group]
        movable[name] = {
            "blocks": len(blocks),
            "singleton_blocks": sum(len(c) == 1 for c in blocks),
            "exchangeable_records": len(movable_ids),
            "exchangeable_weight_share": float(cohort.weights[movable_ids].sum() / cohort.weights.sum()),
        }
        years[name] = cohort.anchors
    targets = [name for name in cohorts if name != "reference"]
    trials = {metric: {subset: [] for subset in views} for metric, views in measured.items()}
    for draw in range(settings["pairing_permutation_draws"]):
        permuted = {}
        for name, flags in all_flags.items():
            paired = shuffle_flags(flags, all_cells[name], rng)
            if draw == 0:
                check_shuffle(flags, paired, all_cells[name])
            joint = paired.sum(axis=2) >= cfg["recorded_rule"]["minimum_high_systems"]
            permuted[name] = windows(joint, layout)
        reference = reference_curves(permuted["reference"], cohorts["reference"].weights)
        curves = {k: weight_means(residuals(permuted[k], years[k], reference, layout), cohorts[k].weights)
                  for k in targets}
        simulated = curve_summary(curves, layout, cfg["thresholds"])
        for metric, views in simulated.items():
            for subset, value in views.items():
                trials[metric][subset].append(value["estimate"])
    comparison = {}
    for metric, views in trials.items():
        comparison[metric] = {}
        for subset, values in views.items():
            observed = measured[metric][subset]["estimate"]
            expected = np.asarray(values)
            comparison[metric][subset] = {
                "observed": observed,
                "permuted_interval_2_5_50_97_5_percentiles": np.percentile(expected, [2.5, 50, 97.5]).tolist(),
                "permuted_at_or_above_observed_fraction":
                    (1+int(np.count_nonzero(expected >= observed-1e-14)))/(len(expected)+1),
            }
    return {"draws": settings["pairing_permutation_draws"], "exchangeable": movable, "peaks": comparison,
            "first_draw_full_flag_marginals_verified": True, "conditional_diagnostic_includes_fixed_reference": True}


def calibration(layout, cfg):
    spec = cfg["calibration"]
    n, floor = spec["records_per_group"], layout.ages.start
    shape = n//2, len(layout.ages)+layout.width-1
    rng = np.random.default_rng(spec["seed"])
    half = rng.random(shape) < spec["base_joint_bernoulli_rate"]
    base = np.tile(half, (2, 1))
    weights = np.ones(n)
    anchors = {k: x["birth_year"]+floor+np.repeat([0, 1], n//2) for k, x in cfg["groups"].items()}
    ref = reference_curves(windows(base, layout), weights)
    outcomes = {}
    for trial in ("negative", "age_injection", "calendar_injection"):
        curves = {}
        for k, first in anchors.items():
            data = base.copy()
            ids = rng.choice(n, size=int(spec["injected_record_fraction"]*n), replace=False)
            if trial == "age_injection":
                begin = spec["age_start"]-floor
                data[ids, begin:begin+layout.width] = False
            if trial == "calendar_injection":
                offset = spec["calendar_start"]-first[ids]
                data[ids[:, None], offset[:, None]+np.arange(layout.width)] = False
            curves[k] = weight_means(residuals(windows(data, layout), first, ref, layout), weights)
        outcomes[trial] = {metric: views["all_four"] for metric, views
                           in curve_summary(curves, layout, cfg["thresholds"]).items()}
    require(all(abs(item["estimate"]) < 1e-12 for item in outcomes["negative"].values()),
            "The balanced negative control gave a signal")
    scenarios = [("age_injection", "age_gap", "age_start"), ("calendar_injection", "calendar_gap", "calendar_start"),
                 ("calendar_injection", "calendar_density_down", "calendar_start")]
    for trial, metric, target in scenarios:
        row = outcomes[trial][metric]
        require(abs(row["start"]-spec[target]) <= spec["peak_tolerance_years"]
                and row["estimate"] > row["threshold"], "Injection recovery failed for " + metric)
    return outcomes
