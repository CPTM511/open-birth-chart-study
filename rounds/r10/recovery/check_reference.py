"""Reproduce the fixed Brazil 2006 comparator without reading any R10 target."""

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

ROUND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROUND / "methods"))
sys.path.insert(0, str(ROUND / "verification"))
from analyze_cohorts import PrecisionReference, load_profiles
from verify_aggregates import RawSortedReference, exact_joint_and_variance, source_data


def check(sample_dir, profiles):
    protocol = json.loads((ROUND / "protocol.json").read_text())
    spec = {"sample_dir": sample_dir, "profile_files": [profiles]}

    # This reader enforces the registered input and complete-profile hashes.
    checked_rows, checked_scores, _, frame, provenance = source_data(spec, "reference", protocol)
    independent = RawSortedReference(checked_rows, checked_scores)
    _, checked_flags, diagnostics = independent.apply(checked_scores)
    joint_counts = (checked_flags.sum(axis=2) >= 3).sum(axis=1)
    independent_rate, _, _ = exact_joint_and_variance(joint_counts, checked_rows, frame)

    rows, _, scores, weights, _, _, _ = load_profiles(sample_dir, [profiles])
    if [r["study_id"] for r in rows] != [r["id"] for r in checked_rows]:
        raise ValueError("Reference row order differs between the two readers")
    if not np.array_equal(scores, checked_scores):
        raise ValueError("The two readers returned different reference scores")
    reference = PrecisionReference(scores, weights, [Fraction(r["N_h"], r["n_h"]) for r in rows])
    flag_differences = int(np.count_nonzero(reference.flags(scores) != checked_flags))
    if flag_differences or abs(reference.joint_rate - independent_rate) > 1e-12:
        raise ValueError("Reference classification or weighted rate failed independent review")

    return {
        "scope": "Fixed R8 Brazil 2006 reference under R10 rules. No target effects estimated.",
        "reference_source": protocol["reference"]["source"],
        "reference_records": len(rows),
        "completed_age_range": protocol["age_window"]["primary_completed_ages"],
        "record_years": int(scores.shape[0] * scores.shape[1]),
        "system_age_scores": int(scores.size),
        "model_input_sha256": provenance["input_sha256"],
        "full_frozen_profile_sha256": protocol["reference"]["profile_sha256"],
        "weighted_joint_year_rate": reference.joint_rate,
        "independent_weighted_joint_year_rate": independent_rate,
        "threshold_classification_differences": flag_differences,
        "independent_cdf_checks": diagnostics,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.sample_dir, args.profiles), indent=2, allow_nan=False))
