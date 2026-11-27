# R10 design review and analysis specification

Prepared before inspection of any R10 human-record score distributions. This is an internal project methods review, not external peer review. The original R8 and R9 files remain unchanged.

## What the expansion can answer

R10 compares additional **country × actual birth-year source frames** with the existing, frozen Brazil 2006 reference. The registered slots are Brazil 2007 (the sole field-only fallback after 2005), Brazil 2010, Brazil 2020, Brazil 2024, Mexico 2009, Mexico 2020, and a bounded new-country search slot. Availability is closed in a public `source_decisions.json` before real chart scoring. A slot can fail its declared birth-field or geography gate; it cannot be replaced after observing a score distribution.

These selected years extend coverage of the 2000s, 2010s and observed 2020s. They do **not** form a representative sample of every birth year in a decade. No missing years are interpolated into personal birth records, and future 2027–2029 births are not invented. Public demographic estimates or projections, if used elsewhere, remain aggregate benchmarks and are never counted as individual four-system inputs.

Each available source frame has a fixed maximum n=2,000, or its census if smaller. Source-frame weights are N_h/n_h within recorded state × explicit M/F strata, and only within the eligible frame. A country label or a large administrative archive does not make the resulting sample representative of humanity. Registration delays, field completeness, timezone exclusions and locality approximations remain selection mechanisms.

The Mexico union of birth-year registrations and the following registration year improves on the R9 same-year restriction but does not remove all delayed-registration undercoverage. Stable archive-year/row identities identify **source records**, not independently confirmed unique people. Equal birth tuples cannot safely be discarded as duplicates because twins can share them.

## Explicit date-domain extension

R8 validators were registered only through 2019. The restriction occurred in four places: the source-input loader, Bazi input normalization, shared astronomy input normalization, and the Ziwei JavaScript bridge. Extending the study to the 2020s therefore requires a declared new executable version; claiming byte-identical executables would be inaccurate.

R10 has an additive package at `open_birth_chart_r10/`. Only the three engine date-scope predicates/error descriptions extend from 2019 through 2025. The separate `r10_io.py` changes the corresponding input bound. All scoring equations, traditional rules, annual snapshot conventions, dependency versions and astronomy settings are preserved. The new runner routes to this package and records its hashes and the R10 protocol. Original R8 files are never patched or monkey-patched at runtime. Inherited engine version labels identify the unchanged R8 score rules; the `OBS-R10-DATE-SCOPE-2025-v1` source audit identifies the extended date domain.

The exact changes are in [date_scope_diff.json](date_scope_diff.json). [Scope checks](scope_extension_checks.json) compare the complete copied files against their permitted transformations, verify exact full-profile agreement on three synthetic legacy fixtures (1880, 2006 and 2019), and calculate a complete synthetic 2024 trajectory. These examples are not human records or external forecasts. They verify the extension and selected calculation paths, not all possible traditional interpretations.

## Age and calendar estimands

The primary statistic retains **40 completed ages, 20–59**, using the R8 July 1 age convention. This supports like-age comparison across the chosen birth years. It necessarily extends beyond 2070 for recent cohorts: 2024 births span 2044/2045 through 2083/2084, depending on birthday.

Two descriptive views are prespecified: ages 20–39 and calendar years 2026–2070. The adapter reports the first/last modeled years, included record-year counts, and every annual denominator. Years before a cohort enters the chosen age window are missing coverage, not zero scores, death or missing life. The 2026–2070 curve must not be substituted for the complete-age primary statistic. No calendar peak is selected for a new hypothesis test.

Age, cohort and calendar remain linked. Comparing the same age uses different calendar years; comparing the same calendar year uses different ages. This structural study does not identify an AI effect or disentangle these causes. Four models using shared calendars and birth inputs are also not four independent empirical witnesses.

## Primary estimator and intervals

The R9 weighted mid-CDF calculation and conditional-bootstrap functions are imported unchanged. R10 adds exact near-boundary threshold classification, as documented in [PRECISION_NOTE.md](PRECISION_NOTE.md); it does not widen or alter the mathematical threshold. The reference is the original 2,000 Brazil 2006 records with frozen inputs, source weights and profile-file hash. The transformation is fitted separately by system and ten-age band. A joint high-score year has at least three of four fixed-reference values at or above 0.8. J is the source-weighted mean of each record's joint-year proportion; the primary contrast is ΔJ=J_target−J_reference.

The 0.8 threshold and the +1 percentage-point resolution target are structural design choices, not validated danger thresholds. Positive or negative contrasts cannot be called harmful or protective.

The primary interval holds **both the reference CDF and reference J fixed**, matching the conditional estimand used by R9. It uses 9,999 whole-record, within-stratum draws with the unchanged R9 finite-population scalar rescaling. The family remains seven slots, including unavailable slots. The nominal per-slot adjusted coverage is 1−0.05/7 = **99.285714%**; ordinary 95% intervals are also retained. Seeds come directly from the public protocol's per-slot entries.

Increasing draws from 1,999 to 9,999 was decided before new scores: with seven slots, each adjusted tail would otherwise have only about seven Monte Carlo replicates, versus about 36 with 9,999. More draws reduce numerical tail instability; they do not cure source bias or establish exact coverage. Non-census singleton strata make the interval unavailable; census strata have zero sampling variance. Annual points from one record are never treated as independent people.

These intervals exclude reference-estimation uncertainty, source selection, clock/location error, model validity and global generalization. The prior R9 simulation's three-slot miss frequencies are not relabeled as seven-slot R10 calibration results. Bonferroni applies within this R10 comparison family, not across an unlimited sequence of research rounds. No real-world AI, disaster or mortality p value is generated.

## Separate reference-stability sensitivity

Merely resampling reference J while keeping its CDF fixed does not capture uncertainty in how that CDF was fitted. R10 therefore adds an exploratory two-sample procedure that reweights the reference, refits all reference CDFs, and transforms both reference and targets at every draw. The same reference draw is shared across all targets. Target random streams are separate, with seed equal to the protocol's reference-sensitivity seed plus one plus the registered slot index.

The reference-refit procedure needs valid distribution weights. Directly turning R9's scalar n-draw rescaling into individual replicate weights could create negative weights. Instead, for each non-census stratum, draw m_i with total n_h−1 from a uniform multinomial and set:

`g_i = 1 − sqrt(1−n_h/N_h) + sqrt(1−n_h/N_h) × n_h/(n_h−1) × m_i`.

The replicate weight is `w_i × g_i`. Stratum totals are preserved, factors are nonnegative, and for a linear stratum mean the resulting replicate variance equals `(1−n_h/N_h) × s_h²/n_h`. The exact n=3 toy verification enumerates all nine ordered draws. Census weights remain fixed, while non-census singletons remain unavailable.

This follows the nonnegative, rescaled-bootstrap construction discussed in the primary survey-methods literature; see [Preston, Survey Methodology (2009)](https://www150.statcan.gc.ca/n1/pub/12-001-x/2009002/article/11044-eng.pdf) and [Chen, Haziza and Mashreghi, Stats (2022)](https://doi.org/10.3390/stats5020031). The linear-mean variance identity does not establish percentile coverage for this study's discontinuous, tied threshold functional.

Raw-value locations in the original reference support are cached for speed. **Reference masses are recomputed every draw**, so this is a true weighted refit rather than a frozen-CDF approximation. Synthetic checks compare the cached implementation with the original CDF implementation under ten different weight vectors, including ties. Threshold comparisons near 0.8 use an exact oracle: rational N_h/n_h for the original reference and exact binary representations of the supplied floating replicate weights during refits. This does not claim exact arithmetic for the irrational rescaling factors themselves. Separate equality, strictly-below and strictly-above fixtures guard against a tolerance changing the threshold.

Ten synthetic draws with 2,000 reference records and seven 2,000-record targets initially took 0.6873 seconds. The 68.66-second linear projection fixed the draw count at **999** before target inspection. After the pre-data precision correction, the same benchmark took 0.6628 seconds, projecting 66.21 seconds including setup, still below the prespecified 120-second budget. The draw count remains unchanged; see [benchmark](refit_benchmark.json).

Outputs are empirical 2.5th–97.5th percentile **sensitivity ranges**, alongside a fixed-CDF two-sample comparison. They do not replace the primary intervals, carry a calibrated coverage guarantee, or justify multiplicity-adjusted conclusions. Discrete threshold jumps and reference sensitivity are part of what this diagnostic is intended to reveal. No alternate reference is selected because its outcome looks more favorable or dramatic.

## Interpretation and remaining work

Data expansion improves the available evidence base only to the extent that it addresses missing years, countries, registration periods and measurement quality. It does not validate the four traditions, their selected computational rules or a link to human replacement. The R9 [traditional-rule gaps](../../r9/methods/RULE_CONFORMANCE_CHECKLIST.md) remain. Independent death-outcome validation remains paused.

The most useful later work is independent traditional-rule fixtures, time/location sensitivity, more complete registration cohorts, genuinely new source regions and actual AI-adoption/outcome data. Those are separate research versions. Neither increasing sample size nor obtaining a small conditional interval resolves these missing links.
