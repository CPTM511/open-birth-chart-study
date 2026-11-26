# R9 calculation and conditional-calibration gate

The arithmetic and implementation checks passed. The declared synthetic calibration was completed before this methods task read any new R9 real-cohort scores. This supports running the frozen structural calculation; it does not validate an astrological forecast or a real-world AI/disaster null.

## Checks actually performed

- Eight checks passed, including direct rational-arithmetic mid-CDF comparisons, unequal weights and ties, reference identity, and complete enumeration of all 27 ordered bootstrap samples in a three-record example.
- The compressed multinomial bootstrap matches whole-record resampling for the primary statistic. Its finite-population rescaling has the expected exact variance in the enumerated example.
- Census strata produce zero finite-sampling variance. Non-census singleton strata produce an unavailable interval, not invented certainty.
- A monotone shift leaves within-record ranks unchanged while changing fixed-reference levels. A deliberately incorrect record-year calculation understates variance by exactly 40 in the perfectly repeated-record counterexample.
- The old, frozen 2,000-record Brazil 2006 reference passed the actual input/profile validation. Its fixed-reference joint rate is **3.21494285%**, while its R8 within-record relative joint rate is **2.28672573%**. These are different estimands. The self-reference contrast is zero up to floating-point error.

These are separate arithmetic implementations written within this project, not independent external human review.

## Synthetic results

Each synthetic family used a fixed 2,000-record reference, three virtual finite populations of 20,000 records, stratified samples of 2,000, 200 repeated samples and 1,999 whole-record bootstrap draws per interval. The synthetic earlier-Brazil slot is a statistical placeholder; the corresponding real slot remains unavailable.

| Synthetic family | Any of three adjusted intervals missed its known truth | Wilson 95% interval for that frequency | Detection of an injected +1 percentage-point joint contrast |
|---|---:|---:|---:|
| Predominantly individual variation | 11/200 = 5.5% | 3.10%–9.58% | 200/200 in each virtual slot |
| Shared calendar variation | 10/200 = 5.0% | 2.74%–8.96% | 200/200 in each virtual slot |

Each 200/200 detection count has a Wilson 95% interval of approximately 98.12%–100%. It is not proof of 100% power, and it applies only to this artificial injection and generator. The +0.05 fixed-reference level injection also matched its exact intended size. The bootstrap/design variance ratios averaged 1.00020 and 1.00037, respectively. The measured calibration runtime was 23.009 seconds in the recorded execution environment.

The observed family interval miss frequencies are compatible with a 5% target, but 200 repetitions cannot establish exact calibration or exclude modest miscalibration. A shared calendar path was retained for all records and held fixed during source-frame resampling. This checks uncertainty conditional on that path; it does not remove calendar confounding or model uncertainty. The finite-frame truth can be nonzero even before an injection. No synthetic draw is counted as a real human birth record.

## Decision and remaining limits

Proceed with the frozen structural point estimates and clearly labeled assumption-conditional sampling intervals. Do not convert the gate into a statement that the models predict harm, that sources represent humanity, or that the absence/presence of a structural contrast changes the probability of an AI-driven civilizational event.

The actual analysis keeps the three-slot interval family although only Mexico 2015 and Brazil 2016 are eligible. It holds the reference fixed; uncertainty in the reference sample, geographic/source selection, recorded clocks, engine rules and real-world interpretation is excluded. No real-cohort p values are introduced. The two new cohorts are holdouts for this frozen structural specification, not death-outcome validation sets.

Evidence: [`math_verification.json`](math_verification.json), [`synthetic_calibration.json`](synthetic_calibration.json), [`reference_validation.json`](reference_validation.json). Reproduce the arithmetic and synthetic checks with:

```bash
python rounds/r9/methods/verify_math.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python rounds/r9/methods/calibrate_synthetic.py
```
