"""Render the published decomposition on a common percentage-point scale."""
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


def draw(results, destination):
    targets = [c for c in results["cohorts"] if c["slot"] != "brazil2006"]
    yearly = [c["contrast_with_brazil2006"] for c in targets]
    observed = [100 * c["observed_difference"] for c in yearly]
    paired = [100 * c["quarter_expected_difference"] for c in yearly]
    residual = [100 * c["quarter_excess_difference"] for c in yearly]
    names = {"BR": "Brazil", "MX": "Mexico"}
    labels = [f'{names[c["country"]]} {c["birth_year"]}' for c in targets]
    indices = list(range(len(labels)))

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": "#17283C"})
    fig, (left, right) = plt.subplots(1, 2, sharey=True, figsize=(11, 5.7), dpi=160)
    fig.subplots_adjust(left=0.16, right=0.97, top=0.77, bottom=0.21, wspace=0.27)
    fig.text(0.05, 0.94, "Calendar-matched pairing reproduces most of the three increases",
             fontsize=16, fontweight="bold")
    fig.text(0.05, 0.885, "Joint high-score years at ages 20–59 compared with Brazil 2006",
             fontsize=11, color="#41546A")

    contrast = "#173B58"
    matching = "#B14F34"
    for ax in (left, right):
        ax.set_axisbelow(True)
        ax.set_xlim(-0.26, 0.72)
        ax.xaxis.set_major_locator(MultipleLocator(0.2))
        ax.grid(axis="x", linewidth=0.65, color="#D8E0E8")
        ax.axvline(0, color="#6C7B8C", linewidth=1.0)
        ax.spines[["left", "right", "top"]].set_visible(False)
        ax.spines["bottom"].set_color("#BDC9D4")
        ax.tick_params(axis="both", length=0, labelcolor="#26384B")
        ax.set_xlabel("Difference (percentage points)", color="#41546A", labelpad=8)
    left.set_title("Observed and matched pairing", loc="left", fontweight="bold", pad=12)
    right.set_title("Remaining difference", loc="left", fontweight="bold", pad=12)
    left.set_yticks(indices, labels, ha="right")
    left.invert_yaxis()
    for y, a, b in zip(indices, observed, paired, strict=True):
        left.plot([a, b], [y - 0.13, y + 0.13], color="#9AABBB", linewidth=1)
    left.scatter(observed, [i - 0.13 for i in indices], color=contrast, s=41, label="Observed R10 contrast")
    left.scatter(paired, [i + 0.13 for i in indices], facecolors="white", edgecolors=matching,
                 marker="D", linewidths=1.5, s=42, label="Matched pairing expectation")
    right.scatter(residual, indices, color=contrast, s=38)
    for i, value in enumerate(residual):
        label = f"{value:+.3f}".replace("-", "−")
        direction = 1 if value >= 0 else -1
        right.annotate(label, (value, i), xytext=(direction * 7, 0), textcoords="offset points",
                       ha="left" if direction > 0 else "right", va="center", fontsize=9, color=contrast)

    handles, labels = left.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower left", bbox_to_anchor=(0.05, 0.06), ncol=2, frameon=False)
    fig.text(0.055, 0.047, "Both panels use the same scale. Pairings preserve modeled calendar year, birth quarter, state and sex.",
             fontsize=9, color="#41546A")
    fig.savefig(destination, facecolor="white", dpi=fig.dpi)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    draw(json.loads(args.results.read_bytes()), args.output)
