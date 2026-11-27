# Independent pre-target methods review

**Decision: passed after an explicit numerical boundary correction.** This review inspected source code, the frozen protocol, and synthetic fixtures only. No actual R10 target score, effect or death outcome was read. It is an internal second-agent review, not external peer review or predictive validation.

Machine-readable evidence: [method_review.json](method_review.json). Reproduction: [review_predata.py](review_predata.py). The independent post-run verifier is [verify_aggregates.py](verify_aggregates.py).

## Date extension and scoring formulas

All nine source/copy hashes and complete diffs in `date_scope_diff.json` were independently reproduced. The copied engines change only the allowed birth-year maximum from 2019 to 2025. Other engine files are byte-identical. The runner changes its root, package/loader routing and run provenance. Its scoring function and task construction are unchanged. Original engine hashes match the frozen protocol.

Actual engine execution, using synthetic births, independently established:

| Fixture | Check |
|---|---|
| Birth years 1880, 2006 and 2019 | Original and R10 runners return exactly identical whole profiles: 160 system/age scores per fixture, including all profile components. |
| 2024-02-29, female, UTC−3 | Four systems return complete bounded 40-age trajectories covering 2044–2083. |
| 2024-12-31, male, UTC+8 | Four systems return complete bounded 40-age trajectories covering 2045–2084. |
| 2025-07-02, female, UTC | Four systems return complete bounded 40-age trajectories covering 2046–2085. |
| 1879 and 2026 | R10 runner rejects out-of-domain births. |

Thus the gate is more than a header/schema test: all four calculation paths execute beyond the old birth-year domain, and July-1 completed-age indexing is preserved.

## Concrete issue found and resolved before target access

The inherited floating-point CDF path can misclassify exact equality at the registered `>= 0.8` threshold. A synthetic reference of five records, each weighted `7/5`, with three all-zero and two all-one trajectories gives an exact mid-CDF at score 1 of `4/5`. The ordinary float implementation returned `0.7999999999999999`, excluding equality. In this deliberately constructed fixture, the resulting joint frequency was zero instead of 0.4.

The additive R10 correction preserves the mathematical rule. Close to the boundary it compares exact integer-scaled masses using `5 × (2L + E) >= 8T`; it does not widen the threshold. Primary calculations use exact design fractions `N_h/n_h`. Boolean classifications are separate from descriptive floating CDF values and are passed through summaries, age bands, intervals and calendar descriptions. Refit replicates use the exact binary ratios of their supplied floating replicate weights, as explicitly documented by the methods author.

The independent verifier uses a different implementation: sort every raw reference observation, find the lower/equal observations, and sum their `Fraction(N_h,n_h)` masses directly. It agrees with the corrected primary and baseline-refit paths for:

- Exact equality at `4/5`, which must be included.
- A value strictly below: `266666666667/333333333334`, which remains excluded.
- A value strictly above: `400000000001/500000000001`, which remains included.
- Refit binary-weight cases with tied values, gaps in score support and zero-mass records.

The two close-side controls differ from 0.8 by less than `10^-12`; they would expose an indiscriminate tolerance rule. The `2e-10` proximity window triggers exact computation only. It is not an acceptance margin.

This synthetic issue does **not** establish that actual R8/R9 results were misclassified. Those earlier releases were not modified by this review or the additive correction.

## Reference-refit replicate weights

For a stratum with sample size `n`, eligible frame size `N`, `r = sqrt(1−n/N)` and multinomial counts from `n−1` draws, the implemented factor is:

`g_i = 1 − r + r × n/(n−1) × m_i`.

It has nonnegative factors, preserves the stratum total and has expected factor one. For any fixed record statistic, the replicate mean equals the sample mean plus `r` times the deviation of the `n−1` resample mean. Therefore its conditional variance is exactly `(1−n/N) × s²/n`.

An independent exact enumeration covered **700 resamples** across `(n,N) = (2,7), (3,12), (4,17), (5,8)`. Every mean/variance identity and weight-total condition passed. The largest observed floating discrepancy in a stratum total or replicate mean was approximately `3.6e-15`.

A separate two-stratum synthetic case checked the independent primary bootstrap replay: **9,999 draws**, seven-slot multiplicity family, exact point **15/38**. Both interval families and the analytic/bootstrap variances matched the production path.

These arithmetic checks establish the stated linear replicate-weight properties. They do not calibrate coverage for the nonlinear reference-refitted threshold statistic. The registered exploratory sensitivity label is appropriate; it must not be promoted to an exact confidence or prediction claim.

## Post-run verification boundary

The prepared verifier reads target scores only after an explicit `--aggregation-ready` gate. It checks input seals, protocol-driven source slots, complete profile coverage, exact-threshold classifications, aggregate contrasts, exact analytic design variance, full primary bootstrap replay, all 45 calendar entries and registered refit seeds/point estimates. It does not replay the full reference-refit Monte Carlo distribution, and says so in its output.

No unresolved issue in the reviewed domain/routing changes, corrected boundary classification, or nonnegative replicate-weight arithmetic blocks R10 execution. Whether real outputs pass remains a separate post-run question.
