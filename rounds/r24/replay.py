"""R24 replication of the METR time regressions and late-trial completion diagnostic."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import fmean

import numpy as np
from scipy.stats import norm, t

HERE = Path(__file__).resolve().parent
ARMS = (0, 1)
STATUS = ("complete", "incomplete", "ditched", "cheating", "corrupted")
REGISTRATION_SHA = "8f8498dc71fe1fb74eb73ac3316b16b82abfa2930c1c4a6d1a660a17fb7171c5"
PROTOCOL_SHA = "c7192ec4fb860e11a16bda609edef820eed5917861af6811ef2237af1c5fc6a9"


@dataclass(frozen=True)
class Task:
    issue: str
    developer: str
    ai: int
    status: str
    is_panel: bool | None
    predicted: float | None
    initial: float | None
    review: float | None


def number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def read_tasks(path: Path, early: bool) -> list[Task]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    tasks = []
    for row in rows:
        if early:
            arm = number(row["ai_treatment"])
            if arm not in ARMS:
                raise ValueError("Unexpected early assignment")
            task = Task(row["issue_id"], row["dev_id"], int(arm),
                        "complete", None, number(row["predicted_time_no_ai"]),
                        number(row["initial_implementation_time"]), number(row["post_review_implementation_time"]))
        else:
            assignment = {"AI-disallowed": 0, "AI-allowed": 1}[row["treatmentAssignment"]]
            panel = {"true": True, "false": False}[row["isPanelDeveloper"].lower()]
            task = Task(row["id"], row["developerId"], assignment, row["status"], panel,
                        number(row["estimatedTimeWithoutAI"]), number(row["initialImplementationTime"]),
                        number(row["postReviewImplementationTime"]))
        if not task.issue or not task.developer or task.status not in STATUS:
            raise ValueError("Missing issue/developer or unknown status")
        tasks.append(task)

    if not tasks or len({task.issue for task in tasks}) != len(tasks):
        raise ValueError("Source rows must be nonempty with unique issue IDs")
    if not early:
        by_developer = defaultdict(set)
        for task in tasks:
            by_developer[task.developer].add(task.is_panel)
        if any(len(labels) != 1 for labels in by_developer.values()):
            raise ValueError("A late developer appears in both recruitment groups")
    return tasks


def fit(tasks: list[Task], outcome: list[float], *, adjust: bool) -> tuple[float, dict[str, float]]:
    if len(tasks) != len(outcome):
        raise ValueError("Outcome length must match task count")
    controls = [np.ones(len(tasks)), np.array([task.ai for task in tasks], dtype=float)]
    if adjust:
        controls.append(np.log([task.predicted for task in tasks]))
    x = np.column_stack(controls)
    y = np.asarray(outcome, dtype=float)
    beta, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    n, p = x.shape
    devs = sorted({task.developer for task in tasks})
    g = len(devs)
    if rank != p or n <= p or g < 2:
        raise ValueError("The estimation sample has insufficient support")
    inverse = np.linalg.inv(x.T @ x)
    residual = y - x @ beta
    influence = x @ inverse[:, 1]
    leverage = np.einsum("ij,ij->i", x @ inverse, x)
    scores = residual * influence
    cluster_scores = defaultdict(float)
    for task, score in zip(tasks, scores, strict=True):
        cluster_scores[task.developer] += float(score)
    correction = (g / (g - 1)) * ((n - 1) / (n - p))
    cluster_var = correction * math.fsum(cluster_scores[d] ** 2 for d in devs)
    hc3 = np.linalg.norm(scores / (1 - leverage))
    classical = math.sqrt(float((residual @ residual) / (n - p) * inverse[1, 1]))
    return float(beta[1]), {
        "classical": classical, "hc3": float(hc3), "cluster_dev": math.sqrt(cluster_var), "clusters": g,
    }


def time_estimate(tasks: list[Task], minutes: list[float]) -> dict:
    beta, se = fit(tasks, [math.log(m) for m in minutes], adjust=True)
    z95 = norm.ppf(0.975)
    t95 = t.ppf(0.975, se["clusters"] - 1)
    return {
        "n_tasks": len(tasks),
        "n_developers": se["clusters"],
        "n_by_assignment": {"no_ai" if arm == 0 else "ai": sum(x.ai == arm for x in tasks) for arm in ARMS},
        "log_coefficient": round(beta, 10),
        "time_change_ratio": round(math.expm1(beta), 10),
        "ci95_time_change_ratio": {
            "classical_normal": _interval(beta, se["classical"], z95, math.expm1),
            "hc3_normal": _interval(beta, se["hc3"], z95, math.expm1),
            "developer_cluster_normal": _interval(beta, se["cluster_dev"], z95, math.expm1),
            "developer_cluster_t": _interval(beta, se["cluster_dev"], t95, math.expm1),
        },
    }


def _interval(beta, scale, critical, transform) -> list[float]:
    return [round(transform(beta + sign * critical * scale), 10) for sign in (-1, 1)]


def time_report(eligible: list[Task], minutes: list[float]) -> dict:
    primary = time_estimate(eligible, minutes)
    initial_only = [task for task in eligible if task.initial is not None and task.initial > 0]
    leave_one = []
    for developer in sorted({task.developer for task in eligible}):
        pairs = [(task, math.log(value)) for task, value in zip(eligible, minutes, strict=True)
                 if task.developer != developer]
        tasks, outcome = zip(*pairs, strict=True)
        beta, _ = fit(list(tasks), list(outcome), adjust=True)
        leave_one.append(round(math.expm1(beta), 10))
    return {
        "primary_total_time": primary,
        "initial_only_same_primary_sample": time_estimate(initial_only, [x.initial for x in initial_only]),
        "one_developer_omitted_primary_range": [min(leave_one), max(leave_one)],
        "one_developer_omitted_count": len(leave_one),
    }


def completed_share(tasks: list[Task]) -> dict:
    by_arm = {}
    for arm in ARMS:
        statuses = Counter(task.status for task in tasks if task.ai == arm)
        n = sum(statuses.values())
        by_arm["no_ai" if arm == 0 else "ai"] = {
            "n_released": n,
            "counts": {name: statuses[name] for name in STATUS},
            "completion_share": round(statuses["complete"] / n, 10),
        }

    beta, se = fit(tasks, [float(task.status == "complete") for task in tasks], adjust=False)
    critical = t.ppf(0.975, se["clusters"] - 1)
    return {"n_developers": se["clusters"], "by_assignment": by_arm, "share_diff_ai_minus_no_ai": round(beta, 10),
            "ci95_share_diff_developer_cluster_t": _interval(beta, se["cluster_dev"], critical, float)}


def early_2025(tasks: list[Task]) -> dict:
    fill = {arm: fmean(x.review for x in tasks if x.ai == arm and x.review is not None) for arm in ARMS}
    minutes = []
    for task in tasks:
        if task.initial is None or task.predicted is None or task.predicted <= 0:
            raise ValueError("Early data has missing initial time or invalid baseline forecast")
        total = task.initial + (fill[task.ai] if task.review is None else task.review)
        if total <= 0:
            raise ValueError("Early data has nonpositive total time")
        minutes.append(total)
    return {
        "released_records": len(tasks),
        "completion_unavailable_reason": "Only valid completed tasks are released.",
        "missing_post_review_counts": {
            "no_ai" if arm == 0 else "ai": sum(x.ai == arm and x.review is None for x in tasks) for arm in ARMS
        },
        "mean_imputed_review_minutes": {"no_ai" if arm == 0 else "ai": round(fill[arm], 10) for arm in ARMS},
        **time_report(tasks, minutes),
    }


def late_2025(tasks: list[Task]) -> dict:
    out = {}
    groups = {"all": tasks, "panel": [x for x in tasks if x.is_panel], "new": [x for x in tasks if not x.is_panel]}
    for label, group in groups.items():
        pairs = []
        for task in group:
            if task.status != "complete" or task.initial is None or task.predicted is None or task.predicted <= 0:
                continue
            total = task.initial + (task.review if task.review is not None else 0)
            if total > 0:
                pairs.append((task, total))
        eligible, minutes = zip(*pairs, strict=True)
        out[label] = {
            "completion_among_all_released": completed_share(group),
            "excluded_before_time_model": len(group) - len(eligible),
            "released_complete_excluded_by_time_or_forecast": sum(x.status == "complete" for x in group) - len(eligible),
            "primary_records_zero_filled_review": sum(x.review is None for x in eligible),
            **time_report(list(eligible), list(minutes)),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path, help="Root containing early and late source folders")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    for name, digest in {"protocol.json": PROTOCOL_SHA, "REGISTRATION.zh.md": REGISTRATION_SHA}.items():
        if sha256((HERE / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"The registered source was modified: {name}")
    snapshot = json.loads((HERE / "source-snapshot.json").read_text(encoding="utf-8"))
    for relative_path, expected in snapshot["sha256"].items():
        if sha256((args.source_dir / relative_path).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Source checksum mismatch: {relative_path}")
    data = {
        "protocol_version": "OBS-R24-METR-TASKS-1.0",
        "source_sha256": snapshot["sha256"],
        "early_2025": early_2025(read_tasks(args.source_dir / "early/data_complete.csv", early=True)),
        "late_2025": late_2025(read_tasks(args.source_dir / "late/data.csv", early=False)),
    }
    output = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
