# Independent numerical result review

**Verdict: PASS.**

A separate standard-library implementation recomputed aggregate results from the private birth-only profiles and source metadata. It imports none of the project analysis, I/O, scoring or aggregation implementations. Personal records stay private.

Checked 6 source-by-window tests and 16 sensitivity groups; baseline 3729 records, 3729 complete, sensitivity 2800 records.

| Quantity | Maximum absolute difference | Comparisons |
|---|---:|---:|
| counts | 0 | 68 |
| weight_sum | 0 | 3 |
| observed_rate | 6.94e-18 | 6 |
| exact_mean | 6.94e-18 | 6 |
| difference_pp | 6.94e-16 | 6 |
| holm | 0 | 6 |
| sensitivity | 5.55e-17 | 400 |

Midranks were recomputed from frequency tables. Exact reference means were recomputed by summing the five independent Bernoulli states with at least three positive systems, then averaging age bands and source-frame weights. This is separate from the production triple-product formula.

All complete counts, person-year counts, same-input group counts, source weights, observed concurrence rates, exact means, percentage-point differences and six-slot Holm values were checked. Every sensitivity group was checked for raw/percentile changes, elevated-flag changes, concurrence flips and paired counts.

The production script corrected canonical source grouping and added frozen metadata/frame-size verification before producing results. No model definition or statistical hypothesis changed.

The 1,999-draw Monte Carlo tail counts were not rerun. This review verifies deterministic aggregates and Holm arithmetic, not mortality prediction or independent evidential status of the four systems.

Review code: `scripts/independent_result_review.py`, SHA256 `f605f5ad6b8d57c17500edd3ad4f2c34702d40f265837c57a5ac5055bf44117c`.
The JSON companion records result hashes, aggregate comparisons and exact limitations.
