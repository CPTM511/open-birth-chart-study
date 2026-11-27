# R10 verification

## Pre-target review

`review_predata.py` reads source code and explicit synthetic fixtures only. Its engine portion requires the same pinned Python and Node dependencies as the R8/R10 runner. It writes only the requested review receipt and refuses to overwrite an existing receipt.

```bash
python rounds/r10/verification/review_predata.py \
  --output /tmp/r10_method_review.json
```

Configure `PYTHONPATH` and `OBS_NODE_MODULES` for the pinned engine installation when it is outside the normal Python/Node search paths. `--skip-engine-runtime` is available only for environments lacking those dependencies; its receipt explicitly records that engine execution was not run.

## Post-run aggregate review

Do not invoke this against R10 target data before the coordinator releases **AGGREGATION_READY**.

```bash
python rounds/r10/verification/verify_aggregates.py \
  --config /private/path/analysis_config.json \
  --primary-result /private/path/analysis_result.json \
  --output /private/path/independent_review.json \
  --aggregation-ready
```

The verifier consumes the same analysis config as `methods/analyze_cohorts.py`, including `protocol`, `source_decisions`, `reference`, and `targets`. Each target's pre-scoring input seal defaults to `rounds/r10/execution/<slot>_input_seal.json`; a target config may specify `input_seal` to override the path. The seal must contain `input_manifest` equal to the source sampling manifest.

The implementation imports no primary analysis methods. It follows the actual protocol registry and final source decisions, retains unavailable slots in the multiplicity family, and verifies the immutable R8 reference hashes. It uses sorted raw reference observations and a direct `Fraction` oracle for threshold equality, exact design-variance arithmetic, and independently replays all registered primary bootstrap draws. It verifies source/year/country rules, all 40 completed ages, and all 45 calendar display entries.

Only aggregate review results and provenance hashes should be published. Individual birth records and individual model trajectories remain private. The verifier explicitly reports that full reference-refit Monte Carlo tails and real-world predictive validity are outside its replay scope.
