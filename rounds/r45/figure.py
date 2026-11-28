"""Plot the complete preregistered window curves from public R45 aggregates."""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .common import HERE, read_json
from .estimate import Layout


def plot(result, cfg, destination):
    layout = Layout.from_protocol(cfg)
    primary = result["primary"]
    groups = ("br1999", "mx1999", "br2009", "mx2009")
    labels = ["Brazil 1999", "Mexico 1999", "Brazil 2009", "Mexico 2009"]
    colors = ["#1A7D72", "#A63863", "#3163AD", "#AD5A14"]
    headings = ["No joint high year · same age", "No joint high year · same calendar period",
                "Higher joint-high density · same calendar period", "Lower joint-high density · same calendar period"]
    fig, axes = plt.subplots(2, 2, figsize=(12.7, 7.6), layout="constrained")
    for i, (ax, (metric, (domain, ix, sign)), title) in enumerate(
            zip(axes.flat, layout.metrics().items(), headings, strict=True)):
        x = list(domain)
        estimate = 100 * sign * np.array([primary["groups"][g]["effect_curve"][ix] for g in groups])
        error = 100 * np.array([primary["groups"][g]["simultaneous_margin"][ix] for g in groups])
        common = estimate.min(axis=0)
        ax.fill_between(x, (estimate-error).min(axis=0), (estimate+error).min(axis=0), color="#E1E7F0",
                        label="Simultaneous 95% band")
        for y, color, label in zip(estimate, colors, labels, strict=True):
            ax.plot(x, y, color=color, lw=1.3, label=label)
        ax.plot(x, common, lw=2.1, color="#1A2637", label="Smallest of four")
        ax.axhline(0, lw=.8, color="#9EA9B5")
        ax.axhline(100*cfg["thresholds"][metric], linestyle="--", color="#40536D", lw=1, label="Registered threshold")
        ax.set_title(title, fontsize=11, loc="left", fontweight="bold")
        ax.set_xlabel("Starting age" if i == 0 else "Starting calendar year")
        ax.set_ylabel("Adjusted percentage points")
        ax.grid(axis="y", linewidth=.5, alpha=.33)
        ax.spines[["right", "top"]].set_visible(False)
        ax.set_xlim(min(x), max(x))
        ax.set_xticks([20,25,30,35,40,45,50] if i == 0 else [2030,2035,2040,2045,2049])
    handles, names = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, names, loc="outside lower center", ncol=4, frameon=False, fontsize=9)
    fig.suptitle("Ten-year model signals in four birth-record frames", fontweight="bold", fontsize=16)
    fig.savefig(destination, dpi=175, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("result", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    plot(read_json(args.result), read_json(HERE / "protocol.json"), args.output)
