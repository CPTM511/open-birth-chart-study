# R9 structural comparison protocol supplement

Status: prepared before any R9 real-cohort chart scoring, for public freezing by the coordinator. R8 files, engines and results remain unchanged. Death-outcome testing remains paused. All effects below are properties of specified chart indices, not probabilities of harm, mortality, AI replacement or civilizational disruption.

## 1. Fixed source slots and sample size

The frozen reference is the 2,000 R8 Brazil 2006 records, their original source-frame weights, and their frozen four-system scores at completed ages 20–59. Each new eligible source-year has a fixed maximum of **2,000 records**, decided before new score calculation; if its eligible frame is smaller, take the census without replacement or invented records. Sample allocation and field audits belong to the coordinator's source protocol.

Three intended comparison slots are retained: (1) Mexico actual births in 2015 with domestic birthplaces, rather than all registrations in 2015; (2) an earlier Brazil cohort; (3) Brazil 2016. Brazil 1996 lacks the required birth-clock field. Its single permitted field-only fallback, Brazil 2001, also lacks that field. The earlier-Brazil slot is therefore **unavailable**, without further substitution. The inferential/interval family remains three slots. Sample size will not be increased in response to observed effects or synthetic power estimates.

## 2. Fixed reference transformation

Let r[i,a,s] be a frozen reference raw score, w[i] its source-frame weight, s one of four systems and a a completed age. For each system s and ten-age band b, define the weighted mid-distribution function:

`F_R,s,b(x) = sum_i sum_a_in_b w[i] * (1(r[i,a,s] < x) + 0.5 * 1(r[i,a,s] = x)) / (10 * sum_i w[i])`.

Apply this **same fixed function** to every reference and new-cohort raw score at the corresponding age band. Denote the result q[i,a,s]. Do not rank each target trajectory against itself, recompute a threshold on a target cohort, pool target data into the reference, or choose a reference after seeing target scores. Exact raw-score ties remain ties; missing values cause an explicit exclusion, not zero replacement. The weighted mean q in each reference system/band is exactly 0.5 up to numerical tolerance.

This supplies a common structural scale relative to Brazil 2006. It does not turn Brazil 2006 into a globally representative or biologically normal baseline. Geographic, cohort, registration and calendar differences remain possible explanations of contrasts.

## 3. Primary estimand and secondary outputs

A record-year is jointly elevated when at least three of its four q values are `>= 0.8`. Let j[i] be its proportion of jointly elevated years across all 40 ages. For a source C, define `J_C = sum_i w[i]*j[i] / sum_i w[i]`.

The **primary contrast** for each available slot is `Delta_J = J_C - J_R`, with J_R calculated using the same fixed-reference transformation. Report J_C, J_R and Delta_J in percentage points. This differs deliberately from R8's within-person ranking and its independent-phase reference. Both versions remain separately named; their numbers must not be silently pooled.

The prespecified structural resolution target is **Delta_J = +0.010** (one percentage point). It is an engineering sensitivity target, not an empirically validated danger threshold. Negative contrasts are also reported without adverse/protective interpretations.

Secondary descriptive outputs are: each system's source-weighted raw-score mean difference; each system's mean fixed-reference percentile difference; `Delta_L`, the mean of all four systems' weighted fixed-reference percentiles minus 0.5; age-band summaries; and the original R8 relative-alignment quantities for continuity. The secondary synthetic sensitivity target is **Delta_L = +0.050**. No significance search across these secondary summaries or calendar peaks is authorized by this supplement.

## 4. Real-cohort uncertainty and multiplicity

No real-cohort p value is to be interpreted as testing absence of AI or absence of a physical disaster. Without a justified exchangeable sampling/null model, report structural contrasts rather than a statistical rejection of a real-world hypothesis.

Where a source has an auditable eligible finite frame and fixed stratified sampling, report a **conditional source-frame sampling interval**. The frozen reference transformation and J_R are held fixed. Resample whole records within each declared stratum; all 40 years and four systems of a record stay together. Do not resample record-years independently. For stratum h with sample n_h, frame N_h and sample statistic mean m_h, ordinary bootstrap means are centered on m_h and their deviations multiplied by `sqrt((1 - n_h/N_h) * n_h/(n_h-1))`. Combine strata with weights `N_h / sum_h N_h`. Census strata contribute no sampling variance. A non-census stratum with fewer than two records makes this interval unavailable; do not silently assign zero variance.

Use **1,999** bootstrap draws. The three-slot family is fixed, including the unavailable earlier-Brazil slot. Show ordinary 95% intervals as descriptive precision and **98.333333% Bonferroni per-slot intervals** as the family-adjusted intervals. These are approximate bootstrap intervals, not guaranteed coverage. Missing slots are unavailable, never zero-valued tests. The rescaled bootstrap can be implemented by multinomial resampling of the empirical distribution of whole-record j values; this is mathematically equivalent for this endpoint to resampling full records.

These intervals condition on the reference sample, fixed engine rules, recorded clocks, eligibility frame and sampling approximation. They exclude uncertainty in reference selection/estimation, source bias, clock/location error, model validity and global generalization. A narrow interval does not remove those limitations. If the sampling assumptions are not defensible, retain the point contrast and label the interval unavailable or assumption-conditional.

## 5. Synthetic controls and conditional calibration

Synthetic inputs are not real births. No real R9 scores may be inspected to tune these controls. The fixed seeds are 2026112710 (synthetic generation), 2026112711 (Mexico bootstrap), 2026112712 (unavailable early-Brazil slot), 2026112713 (Brazil 2016 bootstrap), and 2026112720 (synthetic repeated sampling).

Two synthetic families will be examined: (a) predominantly individual variation with within-record dependence; (b) substantial shared calendar variation common to many records and systems. Both contain four bounded system scores over 40 ages, stratum variation and repeated full-record profiles. Shared calendar paths include a 12-year cycle and a seeded temporally correlated component; that path is retained for all records in a synthetic finite population and throughout its resampling. This is a specified stress model, not a validated generative model of actual human history.

Use a synthetic fixed reference of 2,000 records, target finite frames of 20,000 records, and samples of 2,000 records, with two equal strata. Compute finite-frame truths before repeated sampling. For null coverage, compare intervals with the known finite-frame contrast, which need not be zero when calendar/cohort structure differs. Estimate the probability that any of the three adjusted intervals misses its truth across **200 simulated sampling repetitions**. Report Monte Carlo uncertainty. Do not interpret this exercise as a global-population significance test.

For a positive joint-signal control, increase the finite-frame joint rate by exactly one percentage point, selecting non-joint record-years with the fixed generator and promoting their four q values above 0.8. Start at age-index 20 and move through subsequent age indices cyclically only if there are insufficient non-joint cells; retain each modified record's complete trajectory. Evaluate detection against that same finite frame's pre-injection contrast, using the same 200-repetition sampling design and interval method. This artificial injection validates detectability of the endpoint, not any astrological mechanism. Also verify algebraically/numerically that the transformation `q_new = q + lambda*(1-q)`, with lambda chosen from the finite-frame mean, increases Delta_L by exactly 0.05 without leaving [0,1].

Negative/control checks must include: constant trajectories and ties; exact identity of a reference with itself; invariance of within-person ranks to a positive monotone transformation; sensitivity of fixed-reference levels to a permitted shift; and a deliberately wrong record-year independence calculation whose variance under perfectly repeated within-record outcomes is smaller by a factor of 40. The incorrect calculation is a diagnostic counterexample and must never be used for real inference.

## 6. Gates and interpretation

Required gates before new real-cohort scoring: fixed-CDF and weighted-estimator arithmetic independently checked against direct small-array enumeration; correct finite-population/rescaled-bootstrap variance on explicit examples; full-record resampling; deterministic seeds; transparent synthetic false-positive/coverage and power outputs. Synthetic calibration is conditional on its declared finite frames and reference. No minimum claimed power is forced; an underpowered result is reported, without outcome-driven resampling or model changes. Calibration failure triggers a documented pre-result correction or an unavailable interval, not suppression of the failure.

Traditional rule changes are deferred to separately versioned research. R9 preserves R8 engines for comparability. Every future new rule requires a source passage, executable prerequisites, counterconditions, positive/negative examples, conflict handling and an explicit unknown state. Shared calendars mean four outputs are not four independent witnesses. Any claim relating chart structure to AI-driven civilizational change requires a separately defined observable outcome and validation, which this structural round does not provide.
