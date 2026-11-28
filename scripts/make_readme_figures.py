"""Render the current README evidence figures from released aggregate JSON."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter


ROOT = Path(__file__).resolve().parents[1]
INK = "#132D42"
MUTED = "#516478"
TEAL = "#087D73"
BLUE = "#325B99"
ACCENT = "#9A481A"
GRID = "#DBE4EB"
GROUPS = ("br1999", "mx1999", "br2009", "mx2009")
COPY = {
    "en": {
        "interval_title": "R49 · Four-cohort gap at the 75th percentile",
        "interval_subtitle": "Independent holdout · {count:,} scored records · fixed Brazil 2006 reference",
        "interval_rows": ("Registered primary", "Preset-group replay", "Full simultaneous band"),
        "threshold": "+5 threshold",
        "interval_scale": "Common peak above the fixed reference (percentage points)",
        "interval_note": "Dot marks the {point:+.3f} point estimate. The three intervals use the same holdout.",
        "sample_title": "R49 · Which birth records were scored?",
        "sample_subtitle": "Four new cohorts and one fixed comparison sample",
        "sample_rows": ("Brazil 1999", "Mexico 1999", "Brazil 2009", "Mexico 2009", "Brazil 2006 reference"),
        "sample_scale": "Scored birth records",
        "sample_note": "The reference predates R49 and sits outside the {count:,} holdout records.",
    },
    "zh": {
        "interval_title": "R49 · 四个出生组的第 75 百分位共同缺段",
        "interval_subtitle": "独立留出样本 · {count:,} 条评分记录 · 巴西 2006 固定参照",
        "interval_rows": ("预登记主检验", "原预选组回放", "全曲线同时带"),
        "threshold": "+5 门槛",
        "interval_scale": "共同峰相对于固定参照的差值（百分点）",
        "interval_note": "圆点标出 {point:+.3f} 个百分点的点估计。三个区间使用同一批留出记录。",
        "sample_title": "R49 · 哪些出生记录进入评分？",
        "sample_subtitle": "四个新出生组及一个固定参照样本",
        "sample_rows": ("巴西 1999", "墨西哥 1999", "巴西 2009", "墨西哥 2009", "巴西 2006 参照"),
        "sample_scale": "完成评分的出生记录数",
        "sample_note": "固定参照来自早期研究，未计入本轮 {count:,} 条留出记录。",
    },
}


def canvas(title, subtitle, note, rows):
    fig = plt.figure(figsize=(8.6, 2.3 + 0.43 * rows), facecolor="white")
    fig.text(0.04, 0.92, title, color=INK, fontsize=18, fontweight="bold")
    fig.text(0.04, 0.837, subtitle, color=MUTED, fontsize=11)
    fig.text(0.04, 0.047, note, color=MUTED, fontsize=10.5)
    ax = fig.add_axes((0.278, 0.235, 0.675, 0.52))
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="both", length=0, labelcolor=INK, labelsize=11)
    ax.tick_params(axis="y", pad=9)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    return fig, ax


def intervals(result, counts, copy, target):
    primary = result["primary"]
    limits = [(primary["lower"], primary["upper"]),
              result["auxiliary"]["r46_fixed_witness"]["interval"],
              result["auxiliary"]["r49_full_simultaneous"]["simultaneous_interval"]]
    fig, ax = canvas(copy["interval_title"], copy["interval_subtitle"].format(count=sum(counts)),
                     copy["interval_note"].format(point=100 * primary["point"]), len(limits))
    threshold = 100 * primary["threshold"]
    ax.axvspan(threshold, 6.2, color="#F8F0E9", zorder=0)
    ax.axvline(threshold, ls=(0, (4, 3)), lw=1.5, color=ACCENT)
    ax.text(threshold, 1.045, copy["threshold"], transform=ax.get_xaxis_transform(),
            ha="center", va="bottom", color=ACCENT, fontweight="bold", fontsize=11)
    for row, ((lo, hi), color) in enumerate(zip(limits, (TEAL, BLUE, BLUE), strict=True)):
        lo, hi = 100 * lo, 100 * hi
        ax.hlines(row, lo, hi, color=color, lw=3.2, zorder=3)
        ax.vlines([lo, hi], row - 0.08, row + 0.08, color=color, lw=1.5, zorder=3)
        ax.text((lo + hi) / 2, row - 0.11, f"{lo:+.3f} – {hi:+.3f}",
                ha="center", va="bottom", color=INK, fontsize=10.3)
    ax.scatter(100 * primary["point"], 0, color=TEAL, s=49, zorder=4, edgecolor="white", linewidth=0.85)
    ax.set(yticks=range(len(limits)), yticklabels=copy["interval_rows"],
           ylim=(len(limits) - 0.58, -0.53), xlim=(0, 6.2), xticks=range(7))
    ax.set_xlabel(copy["interval_scale"], fontsize=11, color=MUTED, labelpad=8)
    fig.savefig(target, dpi=175)
    plt.close(fig)


def sample_coverage(counts, reference_count, copy, target):
    displayed_counts = [*counts, reference_count]
    fig, ax = canvas(copy["sample_title"], copy["sample_subtitle"],
                     copy["sample_note"].format(count=sum(counts)), len(displayed_counts))
    ax.barh(range(len(displayed_counts)), displayed_counts, height=0.55, color=(BLUE, BLUE, TEAL, TEAL, "#8797AA"))
    for row, count in enumerate(displayed_counts):
        ax.text(count + 125, row, f"{count:,}", va="center", color=INK, fontsize=11, fontweight="bold")
    ax.set(yticks=range(len(displayed_counts)), yticklabels=copy["sample_rows"],
           ylim=(len(displayed_counts) - 0.46, -0.55), xlim=(0, 7000), xticks=(0, 2000, 4000, 6000))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    ax.set_xlabel(copy["sample_scale"], fontsize=11, color=MUTED, labelpad=7)
    fig.savefig(target, dpi=175)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cjk-font", type=Path, required=True, help="Path to a Simplified Chinese font")
    parser.add_argument("--output", type=Path, default=ROOT / "figures/readme")
    args = parser.parse_args()
    result = json.loads((ROOT / "rounds/r49/results.json").read_text())
    reference = json.loads((ROOT / "rounds/r50/review.json").read_text())
    counts = [result["coverage"][group]["sample_n"] for group in GROUPS]
    args.output.mkdir(parents=True, exist_ok=True)
    font_manager.fontManager.addfont(args.cjk_font)
    cjk = font_manager.FontProperties(fname=args.cjk_font).get_name()
    for language, copy in COPY.items():
        family = [cjk, "DejaVu Sans"] if language == "zh" else ["DejaVu Sans"]
        with plt.rc_context({"font.family": family, "axes.unicode_minus": False}):
            intervals(result, counts, copy, args.output / f"r49-intervals.{language}.png")
            sample_coverage(counts, reference["reference_records"], copy, args.output / f"r49-coverage.{language}.png")


if __name__ == "__main__":
    main()
