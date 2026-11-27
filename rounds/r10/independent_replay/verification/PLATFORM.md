# Platform dependence of the primary bootstrap

The Linux x86-64 replay used for the primary analysis passed all 399 primary comparisons. On macOS arm64, 20 comparisons across four cohorts exceeded the same tolerances. All 20 concerned the 9,999-draw fixed-reference bootstrap, including four interval fields and one variance field per affected cohort. The largest endpoint difference was 0.01167 percentage points. All six cohorts’ individual and seven-slot family-adjusted intervals for ΔJ had the same positions relative to zero and +1 percentage point on both machines. The published intervals come from the original Linux run. [Linux primary review](../results/independent_primary_review.json) · [macOS primary review](../results/macos_primary_replay.json)

## Where the computations first differed

All six cohort point estimates and analytic design variances agreed across platforms within the registered tolerances. Across all 322 target strata, the ordered categories, counts and binary64 probability values matched. Each affected cohort began its first differing stratum with identical PCG64 state on both machines. In Brazil 2007, the third category of the first draw in stratum 40 differed. The first differing strata for Brazil 2010, Brazil 2020 and Mexico 2020 were 33, 40 and 23, respectively, counting from one in the registered stratum order. Every draw matrix matched for Brazil 2024 and Mexico 2009.

NumPy makes a multinomial draw by drawing conditional binomial counts. In the first differing Brazil 2007 draw, the two machines generated different counts at the same conditional binomial step. Fused multiply-add and separate multiplication and addition rounded the initialization to opposite sides of an integer boundary. With the same two random uniforms, NumPy’s central proposal reproduced the observed one-count difference. [NumPy 2.3.5 multinomial implementation](https://github.com/numpy/numpy/blob/v2.3.5/numpy/random/src/distributions/distributions.c#L1619-L1636) · [Binomial initialization and central proposal](https://github.com/numpy/numpy/blob/v2.3.5/numpy/random/src/distributions/distributions.c#L580-L631)

## Reproduce with two synthetic categories

Run `python bootstrap_platform_probe.py` from this directory with NumPy 2.3.5. The example uses 92 trials, probabilities of 1/3 and 2/3, and seed 2. Each execution emits its PCG64 initial state, the two uniform draws and the results obtained with both rounding conventions. The following results were observed with CPython 3.12.14.

| Numerical operation in the installed NumPy binary | Integer used by the sampler | Observed multinomial draw |
| --- | ---: | --- |
| macOS arm64, fused multiply-add | 31 | [34, 58] |
| Linux x86-64, separate multiply and add | 30 | [33, 59] |

The probability bits, initial state and uniform draws matched exactly. Disassembly of the installed `random_binomial_btpe` function showed an ARM64 `fmadd` before rounding down, and x86-64 `mulsd` then `addsd` before rounding down. The synthetic example isolates this arithmetic effect in the two tested builds. The full study also passed the separate 999-common-reference-refit and descriptive checks on macOS. [Synthetic program](bootstrap_platform_probe.py) · [macOS output](bootstrap_probe_darwin.json) · [Linux output](bootstrap_probe_linux.json) · [Reference-refit review](../results/independent_refit_review.json) · [Descriptive review](../results/independent_descriptive_review.json)
