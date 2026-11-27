# R10 independent replay registration · R10 独立复算登记

**OBS-R10-INDEPENDENT-2026-11-27** · Registered on GitHub before this replay calculated or inspected target scores.

本次用原定的 12,000 条出生记录、原样本权重及四体系算法，与巴西 2006 年参照作比较。六组评分输入都已逐字节验真。**墨西哥 2009 和 2020 年两份原始抽样说明未找回。** 两组入选记录、原档行号、抽样排名、分层人数和权重已从官方资料独立复原，分别封存。原轮曾启动评分，具体完成数和可复用结果未知。本次从零计算并标记为独立复算。先核实本登记已在 GitHub 可读，再启动目标计算。历史轮次保留其原始文件要求。[恢复证据](../recovery/README.md) · [计算登记](registration.json)

## Study and prior exposure

The estimand is the difference in four-model alignment between each of six registered country–birth-year source frames and the fixed Brazil 2006 source frame. An earlier execution started on these same records. We have no authenticated completion count or effect estimates from it. The recovery team knows R8/R9 results, the fixed R8 reference rate, and the R10 source counts, ranks and input digests. It has not inspected target effects or used earlier target trajectories. This is a replay on the same records. It provides internal reproducibility evidence and carries no independent population or observed-event validation. [Original R10 protocol](../protocol.json) · [Source decisions](../source_decisions.json)

## Inputs fixed before this run

| Source | Birth year(s), each a separate group | Records per group | Restricted frame |
|---|---|---:|---|
| Brazil SINASC | 2007, 2010, 2020, 2024 | 2,000 | Birth records with resolved source fields and historical clocks |
| Mexico INEGI | 2009, registrations 2009–10 | 2,000 | 26 states; occurrence municipality with verified seat as a location proxy |
| Mexico INEGI | 2020, registrations 2020–21 | 2,000 | 27 states; exact locality code and normalized name matched to the census |
| Fixed reference, Brazil SINASC | 2006 | 2,000 | Original R8 records and weights, extracted by ID from the exact 3,729-record R8 profile file |

All six model-input digests and all six original sampling manifests are frozen. For Brazil the historical metadata files also match. For Mexico, use the recovered design files publicly committed by digest at `943addc967bec492221faeb0df84980af3e51c68`. The literal historical metadata bytes, including free text, are unavailable. The private replay adapter binds each study ID and source rank to the physical official record, its occurrence-state-by-sex stratum, its inclusion probability, and its weight. It projects the numerical birth fields verbatim from the frozen model file. Each stratum uses the original integer population and sample counts, with exact design weight `N_h/n_h`. The location and quality labels are disclosed recovery labels. These labels have no role in baseline scoring, the primary contrast or the reference refit. The separate clock/coordinate perturbation mode of the general runner is outside the registered R10 endpoints. Each public seal has a distinct identity for this replay. [Six-group input evidence](../recovery/input_and_design_receipt.json) · [Mexico 2009 design reconstruction](source_design_2009/README.md) · [Mexico 2020 design reconstruction](../recovery/mexico2020/README.md) · [Prepared input commitments](prepared_receipt.json)

## Scoring, comparison and decision rules

1. Use the frozen Bazi, Ziwei Doushu, Qizheng Siyu and Western astrology engines at each of 40 completed ages, 20–59, with the historical 1 July age convention. Require exactly 12,000 distinct study IDs, 480,000 complete record-years and 1,920,000 finite scores in the registered ranges. A failure stops aggregation. Repair an execution failure against these same inputs and preserve the failed run. Disclose any methodological change before interpreting effects.
2. Within the four fixed age bands, transform scores by the frozen Brazil 2006 weighted mid-CDF. A year qualifies when at least three of four systems reach 0.8. The joint rate `J` is the source-weighted proportion of such years. Report each target's rate and `100 × (J_target − J_reference)` in percentage points. Preserve the exact 4/5 rule at ties. Report all six comparisons in source order, irrespective of sign or magnitude.
3. For each target use the original seed and 9,999 within-stratum whole-record bootstrap draws with finite-population rescaling. Report the original individual and seven-slot family-adjusted intervals. The unavailable seventh source remains in the multiplicity family. The primary intervals condition on the empirical reference. Use the prespecified 1-percentage-point resolution target only when interpreting how much the intervals exclude.
4. Run all 999 exploratory draws that refit the common reference with the frozen per-slot seeds and preserve the complete age trajectories. Report sensitivity ranges separately. Retain the original secondary outputs, including raw and transformed four-system means, age-band summaries, ages 20–39, relative alignment and the 2026–2070 calendar series with denominators. The resulting calendar coverage describes modeled years.
5. After the completed-file audit releases `AGGREGATION_READY`, run the frozen separate primary verifier on the same registered analysis configuration. Cross-check the sample and reference identities, exact boundary decisions, point estimates, design variance, all main bootstrap intervals and calendar denominators. Independently replay the common-reference sensitivity, state the extent and shared dependencies of that check, and publish discrepancies with their implications. The numerical tolerances for primary cross-checks are those in the original [verifier](../verification/verify_aggregates.py). Release aggregate results, review receipts and limitations. Individual birth records and trajectories remain private.

This research compares model outputs for specific source frames and birth years. Births are observed records; adult-age scores are calculations. These data contain no independently observed mortality, personal life outcomes or AI exposures. The study cannot estimate a worldwide generational break, deaths or an AI effect.

## Reproduction

Use the registered GitHub snapshot and pinned dependencies. In a private job directory have `repository/` point to that checkout. Under `reference/` place the R8 Brazil 2006 sample and the full frozen R8 profile file at the paths in the [portable analysis configuration](analysis_config.json). Under a private source root, provide one folder per target, containing its original model input and manifest, plus original Brazilian metadata or the appropriate Mexican `reconstructed_design.jsonl`. The source reconstruction instructions and publication restrictions are linked above.

```sh
python repository/rounds/r10/independent_replay/prepare_inputs.py --source-root /private/targets --output prepared
python repository/rounds/r10/independent_replay/run_scoring.py --registration-sha256 VERIFIED_GITHUB_FILE_SHA256 --jobs 4
python repository/rounds/r10/methods/analyze_cohorts.py --config repository/rounds/r10/independent_replay/analysis_config.json --output results/structural_comparison.json
python repository/rounds/r10/verification/verify_aggregates.py --config repository/rounds/r10/independent_replay/analysis_config.json --primary-result results/structural_comparison.json --output results/independent_primary_review.json --aggregation-ready
python repository/rounds/r10/independent_replay/verification/review_refits.py --config repository/rounds/r10/independent_replay/analysis_config.json --primary-result results/structural_comparison.json --output results/independent_refit_review.json --aggregation-ready
```

The registration digest refers to the SHA-256 of the actual bytes of `registration.json` at the published commit. Independently verify those bytes against GitHub before starting `run_scoring.py`. The validator also checks the frozen historical method and earlier release files. Use a new private job directory for each run.

The supplementary verifier will replay all 999 common-reference draws for all six targets using a separately derived integer threshold. Its prespecified tolerances are 2 × 10⁻¹⁴ for variances and 2 × 10⁻¹² for other sensitivity quantities. It shares the private input files, a reader from the other independent verifier and NumPy's random stream. [Independent algorithm](verification/review_refits.py) · [Synthetic checks](verification/test_refit_replay.py)
