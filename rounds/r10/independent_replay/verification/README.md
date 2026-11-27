# Verification of the independent R10 replay

The original [primary verifier](../../verification/verify_aggregates.py) independently checks the weighted fixed-reference comparisons and the 9,999 main bootstrap draws in each target. The registered [refit verifier](review_refits.py) uses an independently written threshold computation to replay all 999 common-reference draws and their target contrasts. Both consume the same frozen input profiles, sampling design and random seeds. [Independent registration](../REGISTRATION.md)

Two supplementary checks were specified during scoring, before release of the six target effects. The [descriptive verifier](review_descriptives.py) recomputes model means, transformed means and age summaries, using reverse ordering of reference–target pairs to check the percentile means. The [profile replay](check_profile_replay.py) chooses each cohort's lowest and highest sampling rank, then recomputes each full profile in a new Linux process. It checks for dependence on state retained by a scoring worker. This last check uses the same engines and compares all 160 primary scores and the additional recorded profile fields in each selected record.

Run the supplementary checks from the private job directory after the official completion marker has been written. Both require a new output file.

```sh
python repository/rounds/r10/independent_replay/verification/review_descriptives.py \
  --aggregation-ready --config repository/rounds/r10/independent_replay/analysis_config.json \
  --primary-result results/structural_comparison.json --output results/independent_descriptive_review.json
python repository/rounds/r10/independent_replay/verification/check_profile_replay.py \
  --aggregation-ready aggregation_ready.json --config repository/rounds/r10/independent_replay/analysis_config.json \
  --output results/fresh_worker_review.json
```
