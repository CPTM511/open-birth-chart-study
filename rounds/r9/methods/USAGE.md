# R9 structural analysis interface

R9 retains the frozen R8 engines. This interface analyzes completed base-profile JSONL files and verified sample directories. It never calculates new charts or reads outcomes. The primary index uses four raw scores in their existing order: Bazi, Ziwei, Qizheng, Western.

```python
from fixed_reference import FixedReference, joint_record_rates, conditional_frame_interval

reference = FixedReference(reference_scores, reference_weights)  # shape (2000,40,4)
summary = reference.summarize(target_scores, target_weights)
q = reference.transform(target_scores)
interval = conditional_frame_interval(
    joint_record_rates(q), stratum_labels, eligible_frame_counts,
    seed=2026112713, draws=1999, family_size=3,
)
```

`eligible_frame_counts` maps every sampled stratum ID to its eligible population count. The source estimator uses weights N_h/n_h. The sampling interval is for the target's joint rate conditional on the frozen reference; subtract `reference.joint_rate` from its endpoints for the primary contrast. Missing, malformed, incomplete and nonfinite inputs fail rather than being zero-filled. Non-census singleton strata make the interval unavailable.

## Validated JSONL adapter

The adapter uses the unchanged R8 sample loader to validate source-input and metadata hashes, unique study IDs, strata and weights. Profile files may contain multiple sources, or each source may have a separate file. Every selected base profile must have a matching source, chart-input key and full calendar-year array. Duplicate or incomplete selected profiles are rejected. The reference's original input hash and 2,000-record size are enforced.

Create a private configuration JSON with this structure, supplying actual accessible paths:

```json
{
  "reference": {
    "sample_dir": "/path/to/frozen/brazil2006/sample",
    "profile_files": ["/path/to/frozen/R8/baseline_profiles.jsonl"]
  },
  "targets": [
    {
      "slot": "brazil2016",
      "sample_dir": "/path/to/brazil2016/sample",
      "profile_files": ["/path/to/brazil2016/baseline_profiles.jsonl"]
    },
    {
      "slot": "mexico2015",
      "sample_dir": "/path/to/mexico2015/sample",
      "profile_files": ["/path/to/mexico2015/baseline_profiles.jsonl"]
    }
  ]
}
```

Then run:

```bash
python rounds/r9/methods/analyze_new_cohorts.py --config private/r9-analysis.json --output rounds/r9/results/structural_comparison.json
```

The output includes fixed-reference contrasts and source-frame intervals, descriptive raw and fixed-reference levels, separately labeled R8 relative-alignment summaries, hashes and a descriptive 2026–2070 calendar view. The primary age window remains all 40 completed ages 20–59; years beyond 2070 can therefore contribute to the primary statistic. A missing calendar year is not a death. No calendar peak significance tests or new real-cohort p values are produced.

Mexico uses seed 2026112711; Brazil 2016 uses 2026112713. The unavailable earlier-Brazil slot and reserved seed 2026112712 remain documented. The adapter can analyze either available cohort first, or both together, without changing the reference or interval family. Output from a partial invocation must not be described as complete two-cohort analysis.
