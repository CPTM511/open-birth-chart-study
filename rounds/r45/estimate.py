"""Estimate age and calendar window effects from forty-year binary trajectories."""

from dataclasses import dataclass

import numpy as np

from .common import require


@dataclass(frozen=True)
class Layout:
    ages: range
    years: range
    width: int

    @classmethod
    def from_protocol(cls, cfg):
        p = cfg["recorded_rule"]
        return cls(range(p["age_starts"][0], p["age_starts"][1]+1),
                   range(p["calendar_starts"][0], p["calendar_starts"][1]+1),
                   p["window_years"])

    @property
    def age_slice(self):
        return slice(len(self.ages))

    @property
    def gap_slice(self):
        return slice(len(self.ages), len(self.ages)+len(self.years))

    @property
    def density_slice(self):
        return slice(len(self.ages)+len(self.years), len(self.ages)+2*len(self.years))

    def metrics(self):
        return {
            "age_gap": (self.ages, self.age_slice, 1),
            "calendar_gap": (self.years, self.gap_slice, 1),
            "calendar_density_up": (self.years, self.density_slice, 1),
            "calendar_density_down": (self.years, self.density_slice, -1),
        }

    def positions(self, anchors):
        indices = np.array(self.years) - np.asarray(anchors)[:, None]
        require(np.all((0 <= indices) & (indices < len(self.ages))), "Incomplete common calendar support")
        return indices


@dataclass(frozen=True)
class Windows:
    totals: np.ndarray
    absent: np.ndarray
    gap: np.ndarray
    density: np.ndarray


def windows(joint, layout):
    require(joint.ndim == 2 and joint.shape[1] == len(layout.ages)+layout.width-1,
            "Wrong number of ages for the registered windows")
    leading = np.zeros((len(joint), 1), dtype=np.int32)
    cumulative = np.cumsum(np.concatenate((leading, joint), axis=1), axis=1, dtype=np.int32)
    totals = cumulative[:, layout.width:] - cumulative[:, :-layout.width]
    absent = totals == 0
    m = len(layout.ages)
    gap = (m * absent - absent.sum(axis=1, keepdims=True)) / m
    density = (m * totals - totals.sum(axis=1, keepdims=True)) / (m * layout.width)
    return Windows(totals, absent, gap, density)


def weight_means(sums, weights):
    return np.average(sums, axis=0, weights=weights)


def reference_curves(win, weights):
    return np.array([weight_means(win.gap, weights), weight_means(win.density, weights)])


def residuals(win, anchors, reference, layout):
    positions = layout.positions(anchors)
    gap = win.gap - reference[0]
    density = win.density - reference[1]
    return np.concatenate((gap, np.take_along_axis(gap, positions, axis=1),
                           np.take_along_axis(density, positions, axis=1)), axis=1)


def ranges(reference, birth_year, layout):
    anchors = [birth_year+20, birth_year+21]
    index = layout.positions(anchors)
    return np.concatenate((np.full(len(layout.ages), 2.), 2+np.ptp(reference[0][index], axis=0),
                           2+np.ptp(reference[1][index], axis=0)))


def design_vectors(values, rows, possible_widths):
    strata = {}
    for i, row in enumerate(rows):
        strata.setdefault(row["stratum_id"], []).append(i)
    total = sum(rows[indices[0]]["N_h"] for indices in strata.values())
    vectors = np.zeros_like(values)
    singleton_weight = 0.
    for indices in strata.values():
        n, N = len(indices), rows[indices[0]]["N_h"]
        require(all((rows[i]["n_h"], rows[i]["N_h"]) == (n, N) for i in indices) and n <= N,
                "Unexpected sampling stratum size")
        if n == N:
            continue
        if n == 1:
            singleton_weight += N/total
            continue
        values_h = values[indices] - values[indices[0]]
        scale = N/total * np.sqrt((1-n/N) / (n*(n-1)))
        vectors[indices] = (values_h - values_h.mean(axis=0)) * scale
    return vectors, singleton_weight * possible_widths


def multipliers(vectors, settings, seed_offset, block=256):
    standard = np.linalg.norm(vectors, axis=0)
    draws = settings["normal_draws"]
    nonzero = standard > 0
    peaks = np.zeros(draws, dtype=float)
    if nonzero.any():
        standardized = vectors[:, nonzero] / standard[nonzero]
        rng = np.random.default_rng(settings["normal_seed"]+seed_offset)
        for start in range(0, draws, block):
            stop = min(start+block, draws)
            errors = rng.standard_normal((stop-start, len(vectors))) @ standardized
            peaks[start:stop] = np.abs(errors).max(axis=1)
    return standard, peaks


def intervals(design, settings):
    largest = np.zeros(settings["normal_draws"])
    standard_errors = {}
    for i, (name, (vectors, _)) in enumerate(design.items()):
        standard, peaks = multipliers(vectors, settings, i)
        standard_errors[name] = standard
        largest = np.maximum(largest, peaks)
    critical = float(np.quantile(largest, settings["confidence"], method="higher"))
    margin = {name: critical * standard_errors[name] + singleton for name, (_, singleton) in design.items()}
    return critical, standard_errors, margin


def curve_summary(curves, layout, thresholds, margins=None):
    names = list(curves)
    subsets = {"all_four": names, "born_1999": [key for key in names if key.endswith("1999")],
               "born_2009": [key for key in names if key.endswith("2009")]}
    result = {}
    for metric, (axis, columns, sign) in layout.metrics().items():
        views = {}
        threshold = thresholds[metric]
        for subgroup, groups in subsets.items():
            individual = np.array([sign*curves[g][columns] for g in groups])
            common = individual.min(axis=0)
            peak = int(np.flatnonzero(common >= common.max()-1e-14)[0])
            row = {"start": axis[peak], "estimate": float(common[peak]), "threshold": threshold,
                   "at_peak_by_group": {g: float(v[peak]) for g, v in zip(groups, individual, strict=True)}}
            if margins is not None:
                error = np.array([margins[g][columns] for g in groups])
                lower = float((individual-error).min(axis=0).max())
                upper = float((individual+error).min(axis=0).max())
                row["simultaneous_interval"] = [lower, upper]
                row["decision"] = ("supported" if lower > threshold else
                                   "excluded" if upper < threshold else "unresolved")
            views[subgroup] = row
        result[metric] = views
    return result


def longest_gap(joint):
    current = np.zeros(len(joint), dtype=int)
    longest = current.copy()
    for high in joint.T:
        current = (current+1) * ~high
        longest = np.maximum(longest, current)
    return longest


def describe(joint, win, weights):
    lengths = longest_gap(joint)
    age_rates = weight_means(joint, weights)
    absent_rates = weight_means(win.absent, weights)
    return {
        "joint_year_rate": float(age_rates.mean()),
        "age_joint_year_rates": age_rates.tolist(),
        "age_ten_year_gap_rates": absent_rates.tolist(),
        "longest_gap_unweighted_histogram": np.bincount(lengths, minlength=41).tolist(),
        "longest_gap_weighted_histogram": (np.bincount(lengths, weights=weights, minlength=41)/weights.sum()).tolist(),
        "at_least_gap_years": {str(x): float(weight_means(lengths >= x, weights)) for x in (10, 20, 40)},
        "mean_ten_year_gap_probability": float(absent_rates.mean()),
    }
