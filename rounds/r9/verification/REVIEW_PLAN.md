# R9 independent aggregate implementation check

This plan and separate verification implementation are prepared before the reviewer is released to inspect R9 target score distributions. The coordinator must explicitly send `AGGREGATION_READY`. No sealed methods file will be changed during this review.

The same project methods author is performing this alternative implementation, so the result is an **internal independent code-path check**, not independent external peer review. The verifier imports none of the primary analysis functions.

## Checks

1. Recompute source input, metadata and profile hashes. Compare actual source manifests with their pre-execution seals. Enforce the exact frozen R8 reference input/profile hashes.
2. Reconstruct chart-input keys, source identities, absolute/local clock consistency and all 40 completed-age calendar years independently. Verify all selected profiles are computed, complete and unique.
3. Compute reference CDFs by sorting every raw reference observation and accumulating its weight; do not reuse the primary distinct-support/bincount path. Cross-check fixed selected points with direct weighted comparisons. For values within 2e-10 of the threshold, use exact rational source-frame weights to check which side of 0.8 the CDF lies on, and report any floating-point classification disagreement.
4. Recompute primary joint rates and contrasts from integer joint-year counts and rational stratum weights. Verify raw means, fixed-reference levels, age-band summaries and the separate R8 relative-alignment quantities.
5. Independently derive the conditional finite-population variance using exact rational sums and sums of squares of each record's integer joint-year count. Check interval seeds, draws, three-slot adjustment, quantile nesting and subtraction of the fixed reference. **Do not claim a replay of bootstrap tail quantiles.**
6. Check all 45 descriptive calendar-year entries for actual eligibility, source-weighted values and missing versus zero distinctions.

Numeric comparison tolerance is 1e-11 for floating aggregate values and 1e-14 for analytic design variances; counts, hashes, statuses and source metadata must match exactly. Any substantive mismatch is reported rather than repaired silently. Verification output contains aggregate diagnostics, not individual record IDs or profiles.

## Known identifier alias

The unified protocol names the unavailable cohort `early_brazil`; the sealed methods output names it `earlier_brazil`. Both describe the same unavailable Brazil 1996/2001 slot. The verifier records this metadata alias and enforces the unchanged three-slot family; it does not treat it as an extra comparison or a zero-valued result.
