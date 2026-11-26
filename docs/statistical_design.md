# Statistical design and interpretation

The frozen [study protocol](../protocol/study_protocol.json) and [cohort execution seal](../protocol/cohort_execution_seal.json) precede real profile calculation. They are local timestamped records, not independently timestamped public preregistration. Input-validation fixes and the sampling-prose deviation are preserved separately under `protocol/`; none replaces the original frozen file.

## Unit, sample and age

The unit is a source birth record, not a confirmed independent person. The three sources are analyzed separately. Four candidate cross-source overlaps are retained and disclosed; their uncertain identities are not silently resolved. Equal chart inputs within a source share a phase-reference block while retaining their record weights. Non-identical related people can still be dependent.

The age index has forty points: completed civil ages 20–59 on July 1. For a birthday after July 1, the first index year is birth year + 21; otherwise it is birth year + 20. The secondary window contains the first thirty points, ages 20–49. The 2026–2070 output is a separate calendar view restricted to these age-eligible points. Historical observations are not artificially projected into future calendar years after age 59.

The source-frame weight is `N_h/n_h` for each selected record in stratum h. Source membership and eligibility filters remain part of the estimand. Deterministic SHA-256 ordering is used as a reproducible pseudorandom sample within strata. Its nominal inclusion weights describe the selected source-frame design, not the selection of the original database or representation of the world's population. The actual allocation differs slightly from the protocol's prose; [the full deviation record](sampling_implementation_deviation.md) is part of the result.

## Relative signal and joint alignment

The four bounded primary structural scores have different units and resolutions. They are not added together as a risk score. Each record/system trajectory is transformed to a midrank percentile:

`percentile = (average rank among that record's 40 values − 0.5) / 40`.

Tied values receive the same average rank. A constant trajectory becomes 0.5 throughout. A signal is elevated at `percentile >= 0.8`; with ties this does **not** imply exactly 20% of years. The joint indicator is one when at least three of the four elevated flags are one in the same record-year.

The primary statistic for a source and age window is the weighted average of each record's proportion of joint years. One record contributes 40 or 30 points but is not treated as 40 or 30 independent people. A record with an incomplete four-system trajectory is excluded from this complete-case primary statistic, with the exclusion and its cause reported. Missing scores are never replaced by zero.

## Independent-phase reference

For every record, system and ten-age band, independently draw a circular shift from 0 through 9. Rotate the ten-year flag pattern by that amount. This keeps its marginal flag frequency and cyclic within-band pattern while breaking the relative phase between systems. Source weights and coarse age bands are retained. Identical chart input hashes receive the same shifts.

For a band with marginal flag probabilities p1 through p4, the exact probability of at least three flags under independent phases is:

`p1*p2*p3 + p1*p2*p4 + p1*p3*p4 + p2*p3*p4 − 3*p1*p2*p3*p4`.

The exact source/window reference mean is the weighted band average of that expression. It is not estimated from the simulations. There are 1,999 reproducible draws using NumPy's fixed seed 2026112608. The two-sided statistic is absolute deviation of observed joint frequency from that exact mean. The plus-one p value is `(1 + number of simulated absolute deviations >= observed deviation) / 2000`. Numerical comparison includes a 1e-14 tolerance; resolution is 0.0005. Both age windows use the same simulated trajectories.

Holm correction covers all six planned source/window tests. An unavailable slot counts as p=1 for multiplicity but is displayed as unavailable, not as a calculated test. The 2.5th/97.5th percentiles of simulated rates form a **phase-reference interval**, not a confidence interval for population incidence, death risk or forecast accuracy.

This reference deliberately assumes independent phases. Real calendars, shared astronomical inputs, cohort selection and shared chart conventions can violate that reference. A rejection can therefore identify model alignment; it does not identify a mortality mechanism or show that the four systems are independent. Failure to reject does not establish equivalence, absence of every possible structure, or the truth/falsity of all astrological claims.

## Descriptive and sensitivity outputs

All six pairwise Spearman correlations are descriptive sample correlations. They do not have record-year independence p values. Age and calendar curves are descriptive; birth cohort, age and calendar year are not separately identifiable from a single-age/single-year comparison. An apparent calendar peak is not a forecast of an external event. Years with no eligible records are missing, not zero. Fewer than thirty records disqualifies a year from peak listings.

Clock shifts −120, −30, +30 and +120 minutes are applied to 200 fixed-hash-selected records per source. Four coordinate shifts (±0.25° latitude or longitude) are applied to 100 municipality-reference records in Brazil. The same baseline calendar years are retained. These are one-at-a-time stress points, not measured uncertainty intervals or an exhaustive search of possible clocks/locations. Sensitivity summaries use unweighted paired subsets and report score changes and relative-flag changes; they do not estimate population error rates or add confirmatory p values.

## Numerical review

The project includes synthetic counterexamples, exact enumeration of non-symmetric phase patterns, and a separate aggregate calculation review by another AI agent. The independent reviewer did not import the primary analysis implementation for its arithmetic check. This is internal computational review, not external human peer review. See [analysis review](analysis_independent_review.md) and the published numerical result review for the precise checks and limits.
