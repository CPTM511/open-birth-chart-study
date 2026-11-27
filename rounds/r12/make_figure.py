"""Plot early and expanded cohort contrasts with their conditional intervals."""
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


def plot(result, output):
    rows = []
    for year in (2020, 2023):
        early = result["sample_results"][f"mexico{year}_early"]
        full = result["late_registration_sensitivities"][str(year)]
        rows.extend([
            (f"Mexico {year} • early window", early["delta_joint_rate"], early["fixed_reference_conditional_95_interval"]),
            (f"Mexico {year} • with late records", full["expanded_minus_reference"],
             full["expanded_minus_reference_conditional_95_interval"]),
        ])
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "text.color": "#17283C"})
    fig, ax = plt.subplots(figsize=(10.2, 4.6), dpi=160)
    fig.subplots_adjust(left=0.26, right=0.96, top=0.75, bottom=0.22)
    fig.text(0.055, 0.92, "Mexico 2023 stays near the fixed reference", fontsize=16, fontweight="bold")
    fig.text(0.055, 0.852, "Joint high-score years at ages 20–59 compared with Brazil 2006", color="#41546A")
    positions = (3.25, 2.45, 0.95, 0.15)
    navy, clay = "#173B58", "#B14F34"
    ax.set_axisbelow(True)
    ax.set_xlim(-0.23, 0.73)
    ax.set_ylim(-0.48, 3.9)
    ax.xaxis.set_major_locator(MultipleLocator(0.1))
    ax.grid(axis="x", linewidth=0.65, color="#D8E0E8")
    ax.axvline(0, linewidth=1.0, color="#647487")
    ax.axhline(1.7, linewidth=0.7, color="#E1E8EE")
    ax.spines[["left", "right", "top"]].set_visible(False)
    ax.spines["bottom"].set_color("#B9C6D1")
    ax.tick_params(axis="both", length=0)
    for i, (y, (_, point, bounds)) in enumerate(zip(positions, rows, strict=True)):
        lo, hi = (100 * x for x in bounds)
        value = 100 * point
        color = navy if i % 2 == 0 else clay
        ax.hlines(y, lo, hi, color=color, linewidth=2)
        ax.vlines([lo, hi], y - 0.11, y + 0.11, color=color, linewidth=1.25)
        ax.scatter(value, y, s=52, color=color, marker="o" if i % 2 == 0 else "D", zorder=4)
        label = f"{value:+.5f}" if abs(value) < 0.001 else f"{value:+.3f}"
        ax.annotate(label, (hi, y), textcoords="offset points", xytext=(8, 0), va="center", color=color)
    ax.set_yticks(positions, [r[0] for r in rows])
    ax.set_xlabel("Difference from Brazil 2006 (percentage points)", labelpad=9, color="#41546A")
    fig.text(0.055, 0.055, "Bars show 95% sampling intervals conditional on the fixed reference and covered source frames.",
             fontsize=9, color="#41546A")
    fig.savefig(output, facecolor="white")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    plot(json.loads(arguments.result.read_bytes()), arguments.output)
