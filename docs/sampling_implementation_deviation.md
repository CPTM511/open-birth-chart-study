# Sampling implementation deviation

Recorded UTC: `2026-11-26T08:13:58.656699+00:00`. Audit ID: `OBS-R8-SAMPLING-IMPLEMENTATION-DEVIATION-v1`.

## Finding

The Brazil allocation differs from the frozen protocol's rule to reserve one record per nonempty stratum and apportion the remaining quota by remaining capacity. **35 of 54 strata differ; the total absolute quota difference is 44, equivalent to at least 22 reassigned slots (1.1% of the 2,000-record sample).** OGDB and ADB match the full-frame rule. The existing data-code function exactly reproduces every recorded quota in all three sources.

This deviation was discovered **after source profile computation had started but before the team reviewed actual statistical effects**. That timing was supplied by the root coordinating agent; this audit did not inspect profiles, statistical results or outcomes. This is a retrospective implementation-deviation disclosure, not an amendment made before execution. The protocol seal is a local freeze, not external registration.

## Quantitative comparison

Delta means actual minus planned quota. Both allocations use the same frozen `N_h` values, sample-size cap and nonempty strata. No rows were resampled or inspected.

| Source | Eligible N | Strata | Actual n | Different strata | Sum delta | Max absolute delta | L1 | Minimum reassigned slots |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| brazil2006 | 2,805,207 | 54 | 2,000 | 35 | 0 | 5 | 44 | 22 |
| ogdb2023 | 1,388 | 41 | 1,388 | 0 | 0 | 0 | 0 | 0 |
| adb_z2026 | 341 | 176 | 341 | 0 | 0 | 0 | 0 | 0 |

`L1 = sum(abs(actual_n_h - planned_n_h))`; minimum reassigned slots is `L1/2` because the totals agree. This is a distance between quota vectors, not an executed change or a bound on statistical effects. The largest Brazil difference is `BR|35|M|2000|official_clock_municipality_reference_iana`: planned 215, actual 220 (delta +5).

The [machine-readable audit](../protocol/sampling_implementation_deviation.json) contains the complete planned-versus-actual table for all 271 strata, including zero differences.

## Declared and implemented allocation

The [frozen protocol](../protocol/study_protocol.json) declares:

> At least one per nonempty stratum; remaining quota proportional to remaining stratum capacity with largest-remainder allocation; cap at N_h. Take the entire eligible frame if <=2000.

For `N > 2000`, let `H` be the number of nonempty strata, `R = 2000 - H`, and `C_h = N_h - 1`. The declared allocation starts with one per stratum, adds `floor(R*C_h / sum(C_h))`, then distributes the unfilled slots by largest fractional remainder. Exact ties use ascending lexical `stratum_id`; quotas cannot exceed `N_h`. For `N <= 2000`, all eligible records are included.

In contrast, [`proportional_quotas`](../data_expansion/build_birth_inputs.py) computes `ideal_h = 2000*N_h/N`, starts from `min(N_h, max(1, floor(ideal_h)))`, and adjusts to the target using deviations from that ideal. The initial minimum is imposed on the full proportional allocation; it is not reserved before allocating the remaining capacity. In Brazil, the declared reconstruction allocates 54 guaranteed slots and then apportions 1,946 slots over remaining capacity 2,805,153, with 27 final largest-remainder awards. OGDB and ADB return their entire eligible frames before this difference can arise.

The declared reconstruction used integer division and exact remainders, independently cross-checked with rational arithmetic. The unmodified implemented function was extracted from its syntax tree and executed only on the frozen counts; no data builder was run.

## Frozen identities and provenance

The [original protocol seal](../protocol/study_protocol_seal.json), dated `2026-11-26T07:45:45.733710+00:00`, records SHA-256 `f06f3dcaa72c5c7b02e839ad1edfdc966c7130be373bd7bd55c5534cbb6253fe`. The protocol file still matches it. The [cohort execution seal](../protocol/cohort_execution_seal.json) is dated `2026-11-26T07:58:27.811456+00:00`.

Current data-code hashes match both the [release manifest](../data_expansion/release_manifest.json) and [fresh-rebuild validation manifest](../data_expansion/verification/fresh_rebuild_validation.json):

| File | Observed SHA-256 |
| --- | --- |
| `data_expansion/audit_birth_inputs.py` | `78707c884cd519e8d28b16e436b6b35e973e68b9cfa3bdcd04747432e16e967a` |
| `data_expansion/build_adb_reference.py` | `f0c59249c8d59fa2eb6171104959f797df89c928a600f42fc5488b7da9e9abc2` |
| `data_expansion/build_birth_inputs.py` | `5d3b886d691b98e0f33f1d18e604e6c16ac57bcb2e1fed9b3960642c181ad203` |
| `data_expansion/download_sources.py` | `5cfa0e53cf117ccaaea83bbc0cc24fcd5907d138e0ffbd9cf30460659be00e65` |

All three sampling-design JSON hashes match the release manifest. Their model-input and metadata hashes agree with the cohort execution seal. Exact code, sampling-design, model-input, metadata and source-archive hashes are included in the machine-readable audit. Raw archive hashes were copied from [source provenance](../data_expansion/source_provenance.json); the raw archives and row-level samples were not reopened or rehashed for this audit.

## Interpretation and handling

Conditional weights `N_h / actual_n_h` describe the actual eligible-source sampling allocation under the stated within-stratum selection mechanism. They **do not erase the frozen-protocol discrepancy or make the samples globally representative**. The deterministic hash order also does not create an externally randomized sampling design. The weight target remains each source's eligible frame, not all registered national births, all births, or humanity.

This audit evaluates quota implementation only. It makes no claim about the direction or magnitude of changes to profiles, statistics, p-values or conclusions. The discrepancy must remain visible alongside subsequent source-specific analysis.

**No frozen files were changed.** This audit added only this document and `protocol/sampling_implementation_deviation.json`. It did not alter the frozen protocol, samples, models or existing data code. Hash checks before and after writing confirm that every audited existing input remained unchanged; no resampling was performed.
