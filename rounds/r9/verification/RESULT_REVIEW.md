# R9 aggregate numerical review

**Verdict: the reviewed aggregate arithmetic matches.** There were **118 numerical comparisons, zero failures**, with maximum aggregate absolute difference **3.08642 × 10⁻¹⁴**. The verifier additionally checked 240 fixed selected CDF points against direct weighted sums; the largest difference was **5.69544 × 10⁻¹⁴**. No near-threshold rational check changed a 0.8 classification on the actual data.

The alternative code path was prepared and publicly frozen before this review received permission to inspect target results. It does not import primary numerical methods. It sorts all raw reference observations, uses direct selected-point comparisons, computes joint-year counts with rational stratum weights, and derives the conditional variance from exact sums and sums of squares. **The methods author also wrote this alternative implementation: it is an internal code-path review, not independent external human peer review.**

## Values checked

The fixed Brazil 2006 reference joint rate is **3.21494285%**.

| Target source | Complete profiles | Joint rate | Difference from fixed reference | Three-slot-adjusted conditional sampling interval for difference |
|---|---:|---:|---:|---:|
| Brazil 2016 | 2,000 | 3.18712268% | −0.02782017 percentage points | −0.19962471 to +0.14990821 percentage points |
| Mexico 2015 eligible registration frame | 2,000 | 3.32480010% | +0.10985725 percentage points | −0.07744735 to +0.29824541 percentage points |

Both intervals contain zero. Their upper endpoints are below the prespecified +1 percentage-point structural resolution target, conditional on the fixed reference and sampling assumptions. This is not a formal global equivalence result, an adverse-event estimate, or evidence about the probability of AI-driven civilizational disruption. Reference-estimation uncertainty and source, clock and model uncertainty remain outside these intervals.

## Verified scope

- All 2,000 reference profiles and both sets of 2,000 target profiles are present, unique and marked computed.
- Source inputs and metadata match their manifests; both target manifests match pre-execution input seals. The reference input and profile hashes match the original frozen R8 values.
- Local/absolute clock offsets, chart-input keys and all 40 completed-age calendar positions agree with independently reconstructed inputs.
- Fixed-reference joint rates and contrasts, raw-score means, fixed-reference mean levels, age-band summaries and the separate R8 relative-alignment quantities agree.
- Exact rational finite-population variances agree with the primary analysis: approximately **5.31862260 × 10⁻⁷** for Brazil and **6.12235657 × 10⁻⁷** for Mexico in squared proportion units.
- Interval seeds, 1,999 draws, three-slot adjustment, quantile nesting and subtraction of the fixed reference are consistent.
- All 45 descriptive calendar entries per target were checked for actual eligibility and weighted values. Missing calendar entries remain missing.

The verifier **did not replay bootstrap tail quantiles**, repeat chart-engine calculations, or independently verify the truth of underlying birth certificates. It checks the sealed inputs and aggregate implementation; it does not validate the traditional models or any mortality/AI forecast.

## Metadata note

The unified protocol uses `early_brazil`; the methods output uses `earlier_brazil`. Both labels identify the same unavailable Brazil 1996/2001 slot. The unchanged family has three slots. This alias has no numerical effect and has not been silently changed in sealed files.

Machine-readable evidence: [`result_review.json`](result_review.json). Verification code: [`verify_aggregates.py`](verify_aggregates.py). Pre-result plan: [`REVIEW_PLAN.md`](REVIEW_PLAN.md).
