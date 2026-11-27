# R10 method interfaces

All commands run from the repository root with the pinned requirements. No individual inputs or profiles are committed to the public repository. Exact replay also requires the source-specific timezone database recorded by the acquisition pipeline.

## 1. Source and engine scope

`r10_io.load_source(sample_dir)` follows the R8 interface, extending the birth-year upper bound through2025. A source directory contains `birth_inputs.jsonl`, `birth_metadata.jsonl`, and `sampling_manifest.json`. Input/metadata hashes, identity alignment, source clocks, weights, stratum counts and total frame weight must pass.

The runner uses the additive `open_birth_chart_r10` package. The only engine changes are the declared date gates, not score rules. It preserves complete 40-age trajectories and marks calculation errors as abstentions. The final analysis rejects incomplete or uncomputed selected profiles rather than treating them as zeros.

```bash
python rounds/r10/methods/run_profiles.py \
  --samples /private/source-sample \
  --output /private/new-run-directory \
  --jobs 4 --mode baseline
```

The coordinator must first publish the protocol, final birth-field source decisions, and method/input seals. The runner records the R10 protocol, input loader, runner and extended package hashes. It refuses to overwrite an existing output JSONL.

## 2. Final source decisions

The separately published source-decision file closes all seven slots before any real scoring. It uses this structure:

```json
{
  "source_slots": [
    {"id":"brazil_2000s","status":"available","source_label":"SINASC-2007"},
    {"id":"brazil2010","status":"available","source_label":"SINASC-2010"},
    {"id":"brazil2020","status":"available","source_label":"SINASC-2020"},
    {"id":"brazil2024","status":"available","source_label":"SINASC-2024"},
    {"id":"mexico_2000s","status":"unavailable","reason":"Example only: replace with actual birth-field decision"},
    {"id":"mexico2020","status":"available","source_label":"Use exact actual source label"},
    {"id":"new_country","status":"unavailable","reason":"No verified full-input source within the frozen bounded search"}
  ]
}
```

The example does not decide Mexico2009's actual eligibility. The coordinator supplies the real audited decisions. Country, allowed actual birth year, sample size, selection seed and source labels are checked against the protocol and decisions. Unavailable protocol slots cannot be reopened during analysis. Final analysis requires every and only available slot.

## 3. Analysis configuration

```json
{
  "protocol":"rounds/r10/protocol.json",
  "source_decisions":"rounds/r10/source_decisions.json",
  "reference":{
    "sample_dir":"/private/frozen-r8-brazil2006",
    "profile_files":["/private/frozen-r8/baseline_profiles.jsonl"]
  },
  "targets":[
    {"slot":"brazil2020","sample_dir":"/private/br2020","profile_files":["/private/br2020-run/baseline_profiles.jsonl"]}
  ]
}
```

Add an entry for every available registered slot; the shortened example alone is not a complete final invocation. The reference input and original full profile-file hashes are enforced. All target inputs must use seed `OBS-R10-2026-11-27` and n=min(2,000, eligible frame size).

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python rounds/r10/methods/analyze_cohorts.py \
  --config /private/r10-analysis.json \
  --output rounds/r10/results/structural_comparison.json
```

The output provides the primary fixed-reference J/ΔJ, 9,999-draw conditional intervals with a seven-slot family, raw and fixed-reference means, descriptive ages20–39, all calendar denominators and 999 shared-reference refits. The latter are sensitivity ranges, not calibrated confidence claims. Near-threshold classifications use the additive exact oracle in [PRECISION_NOTE.md](PRECISION_NOTE.md); raw CDF means retain the original floating calculation. The script refuses an existing output path.

## 4. Pre-target checks

```bash
python rounds/r10/methods/check_methods.py
python rounds/r10/methods/check_scope_extension.py
python rounds/r10/methods/check_adapter.py
```

`check_methods.py` uses exact enumeration and synthetic arrays, including exact 4/5 equality and values on each side only about 1e-13 away. The scope check compares all additive source copies, verifies three synthetic legacy full profiles against R8, and computes one synthetic2024 trajectory. The adapter check uses two explicitly synthetic census records and random score arrays plus the already frozen R8 reference; these fixture records are never counted as additional people. It checks the new date scope, strict source-slot completeness, protocol settings, age/calendar coverage, census handling and rejection of incomplete profile files.

The pre-target runtime benchmark selected999 reference-refit draws. Re-running it for timing does not authorize changing the frozen draw count after inspecting targets. See [design review](DESIGN_REVIEW.md), [scope diff](date_scope_diff.json) and [scope checks](scope_extension_checks.json).
