"""Run the R52 on-site calculation on fictional inputs and emit aggregate checks."""

import argparse
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory
from zoneinfo import TZPATH, ZoneInfo

import numpy as np

from rounds.r45.common import load_source
from rounds.r45.score import init_worker
from rounds.r46.score import worker
from rounds.r50.compare import (
    AGE_STARTS,
    MAIN_AGE,
    SYSTEMS,
    WINDOW_COUNT,
    WINDOW_WIDTH,
    centered_gap_integers,
    classify_scores,
    fixed_age_contrast,
)


REFERENCE = Path(__file__).resolve().parents[1] / "r50" / "reference.json"
FICTIONAL_INPUTS = {
    "census": (
        ("2009-01-24T00:01", "F"),
        ("2009-04-12T13:57", "M"),
        ("2009-07-01T07:29", "M"),
        ("2009-10-19T23:58", "F"),
    ),
    "sample": (
        ("2009-02-03T23:12", "M"),
        ("2009-02-04T03:42", "F"),
        ("2009-03-18T16:07", "M"),
        ("2009-05-27T22:53", "F"),
        ("2009-07-02T11:11", "F"),
        ("2009-08-15T06:18", "M"),
        ("2009-11-06T10:04", "F"),
        ("2009-12-24T17:27", "M"),
    ),
}


def load_fictional_population():
    local_zone = ZoneInfo("Asia/Hong_Kong")
    births, metadata, strata = [], [], []
    for name, fixtures in FICTIONAL_INPUTS.items():
        size = len(fixtures)
        strata.append({"stratum_id": name, "N_h": size, "n_h": size})
        for stamp, sex in fixtures:
            local = datetime.fromisoformat(stamp)
            aware = local.replace(tzinfo=local_zone)
            record_id = f"r52-fictional-{len(births) + 1:02d}"
            birth = {
                "study_id": record_id,
                "birth_local": local.isoformat(timespec="seconds"),
                "birth_utc": aware.astimezone(timezone.utc).isoformat(timespec="seconds"),
                "source_offset_seconds": int(aware.utcoffset().total_seconds()),
                "timezone_id": local_zone.key,
                "latitude": 22.3,
                "longitude": 114.2,
                "sex": sex,
                "calendar": "gregorian",
            }
            births.append(birth)
            metadata.append({
                **birth,
                "source": "R52 fictional fixture",
                "source_id": "r52-fictional",
                "birth_country": "HK",
                "quality": "fictional",
                "geo_precision": "fictional",
                "stratum_id": name,
                "N_h": size,
                "n_h": size,
                "inclusion_probability": 1.0,
                "sample_weight": 1.0,
                "sampling_sha256": sha256(record_id.encode()).hexdigest(),
            })
    manifest = {"sample_n": len(births), "eligible_frame_N": len(births), "strata": strata}
    with TemporaryDirectory(prefix="r52-fictional-") as directory:
        root = Path(directory)
        for filename, rows, key in (
            ("birth_inputs.jsonl", births, "model_input_sha256"),
            ("birth_metadata.jsonl", metadata, "metadata_sha256"),
        ):
            payload = "".join(json.dumps(row) + "\n" for row in rows).encode()
            (root / filename).write_bytes(payload)
            manifest[key] = sha256(payload).hexdigest()
        (root / "sampling_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        rows, _ = load_source(root)
    return rows


def check_windows(scores, flags, centered, rules):
    by_key = {(rule["age_from"], rule["system"]): rule for rule in rules}
    for trajectory, actual_flags, actual_windows in zip(scores, flags, centered, strict=True):
        simultaneous = []
        for age, (values, classified) in enumerate(zip(trajectory, actual_flags, strict=True), 20):
            band = age // 10 * 10
            matches = []
            for system, score, flag in zip(SYSTEMS, values, classified, strict=True):
                rule = by_key[band, system]
                cutoff = rule["score"]
                matches_rule = score > cutoff or (score == cutoff and rule["operator"] == ">=")
                if matches_rule != flag:
                    raise ValueError("Independent cutoff check differs")
                matches.append(matches_rule)
            simultaneous.append(sum(matches) >= 3)
        gaps = [not any(simultaneous[i:i + WINDOW_WIDTH]) for i in range(WINDOW_COUNT)]
        expected = [WINDOW_COUNT * gap - sum(gaps) for gap in gaps]
        if actual_windows.tolist() != expected:
            raise ValueError("Independent ten-year window check differs")


def check_sampling(rows, values, center):
    census, population = [], []
    for row, value in zip(rows, values, strict=True):
        target = census if row["stratum_id"] == "census" else population
        target.append(int(value))
    all_values = census + population
    truth = Fraction(sum(all_values), WINDOW_COUNT * len(all_values)) - center
    census_tuple = (len(census), len(census), sum(census), sum(x * x for x in census))
    effects, variances = [], []
    for draw in combinations(population, 4):
        sample_tuple = (len(population), len(draw), sum(draw), sum(x * x for x in draw))
        effect, variance = fixed_age_contrast((census_tuple, sample_tuple), center)
        effects.append(effect)
        variances.append(variance)
    n_draws = len(effects)
    variance_over_draws = sum((effect - truth) ** 2 for effect in effects) / n_draws
    if (sum(effects) / n_draws != truth or variance_over_draws <= 0
            or sum(variances) / n_draws != variance_over_draws):
        raise ValueError("Independent finite-population sampling check differs or is degenerate")
    return n_draws


def run():
    rows = load_fictional_population()
    init_worker()
    scores = np.array([worker((row, 0))["scores"]["base"] for row in rows], dtype=np.float64)
    reference_bytes = REFERENCE.read_bytes()
    reference = json.loads(reference_bytes)
    rules = reference["score_cutoffs"]
    flags = classify_scores(scores, rules)
    windows = centered_gap_integers(flags)
    index = AGE_STARTS.index(MAIN_AGE)
    check_windows(scores, flags, windows, rules)
    draws = check_sampling(rows, windows[:, index], Fraction(reference["fixed_reference_center_proportions"][index]))
    tzdb = next((Path(folder, "tzdata.zi") for folder in TZPATH if Path(folder, "tzdata.zi").is_file()), None)
    return {
        "scope": "Fictional inputs only. No external data were read or scored.",
        "synthetic_records_scored": len(rows),
        "score_flags_compared": flags.size,
        "centered_windows_compared": windows.size,
        "finite_population_draws_checked": draws,
        "distinct_age_34_centered_integers": len(set(windows[:, index])),
        "reference_sha256": sha256(reference_bytes).hexdigest(),
        "score_buffer_sha256": sha256(scores.astype("<f8").tobytes()).hexdigest(),
        "runtime": {
            "os": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
            "tzdb": tzdb.read_text(encoding="utf-8").splitlines()[0] if tzdb else None,
        },
    }


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(run(), indent=2))
