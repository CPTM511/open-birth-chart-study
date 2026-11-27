# R10 pre-data threshold precision correction

This note records an implementation correction identified by a separate project reviewer **before any real R10 chart scoring or target-score inspection**. It changes neither the public mathematical threshold nor any model score rule. R8 and R9 files are preserved.

## Reproduction and consequence

Take five synthetic reference records, all with the same values across 40 ages and four systems. Three have raw score 0; two have raw score 1. Each record has design weight 7/5. The weighted mid-CDF at raw score 1 is exactly 4/5. Both score-1 records should satisfy the inclusive threshold in every system, giving J=2/5.

The inherited floating calculation produces 0.7999999999999999. A direct floating comparison with 0.8 excludes these records and gives J=0. The synthetic case demonstrates a numerical boundary defect in the general implementation; it does **not** establish that any published R9 result encountered that boundary.

## Additive correction

The raw CDF computation remains the frozen R9 function. When a computed value lies within 2×10⁻¹⁰ of 0.8, R10 resolves the threshold comparison with exact arithmetic. This window selects the arithmetic method; it is **not** an acceptance tolerance. Values strictly below 4/5 remain excluded, however close they are.

Let L be reference mass strictly below the query, E equal mass and T total mass within that system and age band. The inclusive rule is evaluated as:

`5 × (2L + E) >= 8 × T`.

For the fixed-reference primary statistic, masses use exact rational source-design weights `N_h/n_h`, converted to common-denominator integers. Raw-score support ordering and ties retain the frozen score-array values. Primary J, reference J, conditional interval inputs, age bands, and calendar descriptions all use the corrected flags. Floating raw/CDF means remain unchanged for descriptive continuity.

The optional diagnostic counters count evaluated cells across function calls, including repeated transformations; they are not counts of unique people, years, or affected source records.

For reference-refit sensitivity, the same exact comparison uses the exact binary ratios of the supplied nonnegative floating replicate weights. This resolves accumulation error relative to those documented inputs. It does not eliminate rounding in the square root or replicate-weight construction, nor claim symbolic exactness of irrational bootstrap factors. The unperturbed sensitivity point and fixed-CDF comparator use the same rational original design weights as the primary analysis; the adapter checks that their point contrasts agree.

The selected window is far larger than the ordinary accumulated rounding scale for the frozen 20,000 reference observations per system/age band. Outside the window, ordinary floating comparison is retained. This is a bounded implementation safeguard for this registered reference size, not a guarantee for arbitrarily large or ill-conditioned datasets.

## Controls and audit trail

`check_methods.py` independently enumerates weighted raw observations using `fractions.Fraction`. It verifies exact equality and two strictly separated controls: with M=10¹¹, weights `[M,M,M,M,M+1]` put the score-1 mid-CDF just below 4/5, while `[M+1,M,M,M,M]` put it just above. The differences are approximately −6×10⁻¹³ and +4×10⁻¹³. Both primary and refit paths agree with the exact oracle. A baseline check confirms the sensitivity uses the same original design-weight classification.

The original local method-seal SHA-256 was `f9ccc7f452f892f9671b6722e74c7402ef075d24927031f7e086dd8f61b439ab`. It was superseded before public method sealing and before real R10 scoring. The replacement seal includes this note, both new precision modules, updated checks and refreshed benchmark evidence. The published protocol and its mathematical estimand remain unchanged. No claim of external peer review or predictive validation follows from these arithmetic checks.
