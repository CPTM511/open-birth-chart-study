"""Plot upper-bound curves from the R46 diagnostic and public R49 results."""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .common import read_json


def plot(previous, result, destination):
    ages = result["age_starts"]
    groups = result["groups"]
    fixed = result["auxiliary"]["r46_fixed_witness"]["preselected_witnesses"]
    selected = [groups[g]["effect_curve"][i] + fixed["z"] * groups[g]["conditional_standard_error"][i]
                for i, g in enumerate(fixed["groups_by_age"])]
    projected = np.min([np.array(g["effect_curve"]) + g["simultaneous_margin"] for g in groups.values()], axis=0)
    historical = previous["per_age"]
    assert ages == [row["age"] for row in historical]

    fig, axes = plt.subplots(2, 1, figsize=(9.2, 6.6), sharex=True, sharey=True, layout="constrained")
    fig.suptitle("Upper bounds for the four-group 75th-percentile gap", ha="left", x=.03, fontweight="bold", fontsize=15)
    threshold = 100 * result["primary"]["threshold"]
    primary_label = "Group-adjusted primary"
    preset_label = "Preset group"
    simultaneous_label = "Projected simultaneous band"
    for ax, title, preset, simultaneous in (
        (axes[0], "R46   Different upper bounds on the same data", [row["fixed_upper"] for row in historical],
         [row["simultaneous_upper"] for row in historical]),
        (axes[1], "R49   Independent birth-record holdout", selected, projected),
    ):
        ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
        ax.plot(ages, 100 * np.asarray(preset), color="#A04A19", lw=1.8, linestyle="-.", label=preset_label)
        ax.plot(ages, 100 * np.asarray(simultaneous), color="#18756F", lw=1.8, linestyle="--", label=simultaneous_label)
        ax.axhline(threshold, color="#333C45", lw=1.0, linestyle=":", label="Registered threshold")
        ax.set_ylabel("Percentage points")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.24)
        ax.set_xlim(20, 50)
    axes[1].plot(ages, 100 * np.asarray(result["primary"]["upper_curve"]), color="#294C9C", lw=2.2, label=primary_label)
    for key, color in (("fixed_upper_peak", "#A04A19"), ("simultaneous_upper_peak", "#18756F")):
        peak = previous[key]
        value = peak["fixed_upper" if key == "fixed_upper_peak" else "simultaneous_upper"] * 100
        offset = 8 if key == "fixed_upper_peak" else -14
        axes[0].scatter(peak["age"], value, color=color, s=20, zorder=4)
        axes[0].annotate(f"{value:+.3f}", (peak["age"], value), xytext=(8, offset),
                         textcoords="offset points", color=color, fontweight="bold", fontsize=9)
    axes[1].set_xlabel("Starting age of the ten-year window")
    axes[1].set_xticks([20, 25, 30, 34, 40, 45, 50])
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=4, frameon=False, fontsize=9)
    fig.savefig(destination, dpi=175, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("diagnostic", type=Path)
    cli.add_argument("results", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    plot(read_json(args.diagnostic), read_json(args.results), args.output)
