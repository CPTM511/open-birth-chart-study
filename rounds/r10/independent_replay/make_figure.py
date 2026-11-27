"""Draw the six registered contrasts using only the published aggregate output."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

LABELS = {"brazil_2000s": "Brazil 2007", "brazil2010": "Brazil 2010", "brazil2020": "Brazil 2020",
          "brazil2024": "Brazil 2024", "mexico_2000s": "Mexico 2009", "mexico2020": "Mexico 2020"}


def draw(result_path, output):
    data = json.loads(result_path.read_bytes())
    targets = {t["slot"]: t for t in data["targets"]}
    if set(targets) != set(LABELS) or data["primary_family_size"] != 7:
        raise ValueError("Expected the six registered targets and seven-slot family")
    fig, ax = plt.subplots(figsize=(8.7, 4.6))
    fig.subplots_adjust(left=.19, right=.95, top=.78, bottom=.22)
    ax.axvline(0, color="#59636b", lw=1.25, ls="--", zorder=1)
    farthest = .05
    heights = [5.5, 4.5, 3.5, 2.5, 1, 0]
    for y, (slot, label) in zip(heights, LABELS.items(), strict=True):
        t = targets[slot]
        estimate = 100 * t["delta_joint_rate"]
        lo, hi = [100*v for v in t["sampling_interval"]["delta_joint_family_adjusted_interval"]]
        if not lo <= estimate <= hi:
            raise ValueError("Estimate lies outside plotted interval")
        farthest = max(farthest, abs(lo), abs(hi))
        color = "#126e71" if slot.startswith("brazil") else "#a34a29"
        ax.hlines(y, lo, hi, color=color, linewidth=2.2, zorder=3)
        ax.vlines([lo, hi], y-.10, y+.10, color=color, linewidth=1.5, zorder=3)
        ax.scatter(estimate, y, color=color, s=60, edgecolor="white", linewidth=.75, zorder=4)
    ax.set_xlim(-1.12*farthest, 1.12*farthest)
    ax.set_ylim(-.55, 6.05)
    ax.set_yticks(heights, list(LABELS.values()))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=8, symmetric=True))
    ax.grid(axis="x", linewidth=.6, color="#d8dce0", zorder=0)
    ax.tick_params(axis="both", length=0, labelsize=10, pad=7, colors="#303a40")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlabel("Difference from the fixed Brazil 2006 reference (percentage points)", labelpad=10)
    fig.text(.045,.94,"Joint high-score years across six birth cohorts",fontsize=16,weight="bold",color="#172a35")
    fig.text(.045,.87,"Ages 20–59  ·  2,000 records per cohort  ·  at least 3 of 4 systems at or above the registered cutoff",
             fontsize=9.2,color="#40515b")
    fig.text(.045,.055,"Dots show estimated differences. Bars show conditional intervals adjusted for the seven planned comparisons.",
             fontsize=9,color="#40515b")
    fig.savefig(output, dpi=170, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("result", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    draw(args.result, args.output)
