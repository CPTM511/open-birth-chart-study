# Independent computational-method review

**Scope:** a separate project agent reviewed only `src/open_birth_chart/analysis.py`, `tests/test_analysis.py`, `protocol/study_protocol.json`, and `protocol/analysis_implementation_seal.json`. No real-person profile, real cohort signal or statistical result was opened. The reviewer is part of this project and AI environment; this is not external human peer review.

**Verdict: pass after two required input-validation corrections.** The locally frozen mathematical analysis is coherent. Both defects were identified, corrected and independently retested before real-cohort statistics were run. These corrections changed no model scores, hypotheses, thresholds, randomization rules or endpoint definitions. The machine-readable companion records the final reviewed hashes and exact checks.

## Mathematical checks

| Component | Finding |
|---|---|
| Within-person normalization | Correct: ranking is across the 40 ages, separately for each person and system. The independent check used `(number lower + half number equal)/40`, which equals the implemented midrank formula. |
| Constant and tied scores | Constant trajectories map to 0.5 and never qualify as elevated. Ties mean the elevated share is **not necessarily 20%**. A four-level trajectory with ten equal values at each level marks 25% elevated. The threshold must be described as `midrank percentile >= 0.8`, rather than exactly the “top 20% of years.” |
| Concordance endpoint | Correct: at least three of four elevated flags in the same person's same age/year. This is not an average of raw scores. |
| Ten-year shifts | Correct for the stated reference: each chart-input group, system and age-decade gets an independent uniform shift from 0 to 9. The four age bands and the four systems occupy the intended axes. Rotating the binary flags after ranking is equivalent to ranking after these permutations because the within-person 40-point multiset is unchanged. |
| Exact reference mean | Correct: for marginal probabilities `p1,...,p4`, `P(at least 3) = sum(all four triple products) - 3*product(all four)`. A state with exactly three positives contributes once; a state with four positives contributes `4-3=1`. |
| 30-year secondary endpoint | Correct: flags remain normalized against all 40 ages; the statistic and its reference then use the first three ten-year bands. There is no unplanned re-ranking inside the secondary window. |
| Identical chart inputs | Correct intended dependence treatment: share null rotations and sum their real-person weights. Independent checks confirmed that duplicated records with split weights and the corresponding collapsed weighted group give the same observed/reference quantities, allowing floating-point tolerance. |
| Weights | Correct for positive one-dimensional source-frame weights: the weighted mean of each person's event fraction equals a weighted person-year rate because all included people contribute the same number of years in a window. The code does not supply global-population weights or a complex-survey confidence interval. |
| Monte Carlo tail | Correct for the explicitly defined independent-phase reference: compare absolute deviations from the exact reference mean, with a conservative floating-point tie tolerance and a plus-one Monte Carlo formula. At 1,999 draws, the minimum attainable raw value is 0.0005. |
| Holm family | Correct generic Holm adjustment, including unavailable slots internally as 1 while displaying them as unavailable. A six-slot synthetic example passed. Actual use must pass **all six prespecified source-by-window tests together**; that caller is outside the authorized review scope. Holm does not require those six tests to be independent. |
| Descriptive outputs | Pairwise correlations omit misleading person-year independence p-values. Empty calendar years remain unavailable. The phase-reference interval is explicitly not a population or mortality confidence interval. |

### Exhaustive checks beyond the original tests

The reviewer independently enumerated all **10,000 four-system shift combinations at all ten within-band positions** for each of two asymmetric examples:

| Four systems' elevated counts in a ten-year band | Direct enumeration | Implemented exact mean |
|---|---:|---:|
| 1, 3, 5, 7 | 0.1445 | 0.1445 |
| 0, 10, 3, 9 | 0.2700 | 0.2700 |

Additional synthetic checks covered unequal person weights, different decade marginals, both age windows, duplicate-group equivalence under the same Monte Carlo seed, the same-person/year threshold and six-slot Holm values. None used real birth records or outcomes.

## Defects identified before statistical results

1. **Short input-key lists could remove people only from the null reference.** The original grouping function iterated over keys without checking equal lengths. The observed statistic still used all profiles. Required correction: reject unequal numbers of keys, weights and profiles, and reject an empty group input. The first correction was independently retested and correctly rejected the invalid synthetic request.
2. **Column-vector weights could silently broadcast into a wrong observed rate.** The original rate calculation accepted an `N x 1` array. In a synthetic example with three people, each with 16 elevated concurrent years out of 40, equal column-vector weights produced 1.2 instead of 0.4. The correction enforces one-dimensional weights before multiplication. The reviewer confirmed rejection in `phase_reference`, `weighted_rate`, `exact_phase_expectation` and `group_identical_inputs`, while valid flat equal weights return 0.4.

The project owner reported that the original implementation seal/code and two dated pre-results correction audits were preserved. The reviewer independently verified the final code behavior, not those additional audit files, which were outside the four-file read scope. These corrections must not be described as new model hypotheses. The machine-readable companion records the final reviewed hashes and correction checks. No mandatory mathematical correction remains within the reviewed scope.

## Interpretation conditions for publication

The analysis compares the four **declared structural observables** with a mathematical independent-phase reference. It does not test deaths, illness, accidents, forecast calibration or the truth of a lifespan claim. No endpoint or external outcome appears in this analysis.

The null reference deliberately destroys relative alignment between systems and most nonidentical people. It preserves each person's within-decade marginal frequencies and cyclic arrangement up to rotation, but not arbitrary cross-person dependence, exact calendar-year alignment or relationships across decade boundaries. It is therefore not a complete generative null model of birth cohorts or the physical world. Shared calendrical periods, astronomical computations and birth-registration patterns can produce departures from it.

**Four systems are not four independent pieces of empirical evidence.** They share birth inputs and calendrical/astronomical structure; independence exists in the constructed reference shifts, not as an established property of the original models. A small corrected reference p-value would establish unusual alignment relative to that chosen reference only. A large p-value would not prove that no other traditional interpretation can be constructed.

Weights address the eligible source frame, not all humanity. Calendar-year curves also change cohort and age composition; peaks cannot be read as population death-risk peaks. Same-year concurrence, source-frame weighted rates and an artificial reference interval must retain their stated meanings in every chart and article.

## Review boundary

Within the four-file scope, the reviewer could not verify how actual chart-input keys are constructed, whether every input-affecting convention is included in those keys, whether the caller passes all six Holm slots together, or whether actual exclusions and weights are reported correctly. These are integration requirements, not mathematical claims established by this review. The project must check them separately. No finding here independently validates any chart engine or historical sample frame.
