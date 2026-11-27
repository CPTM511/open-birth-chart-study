# Open Birth Chart Study

**A reproducible study of four explicitly defined birth-chart models.**

R8 computes Bazi, Ziwei, Qizheng and Western structural indices for **3,729 source birth records**, with forty annual points at completed ages 20–59. All four workflows completed: **149,160 record-years and 596,640 system-year scores**, plus **2,800 sensitivity profiles**.

**Result:** none of the six planned source/age-window alignment tests rejected the specified independent-phase reference after Holm correction; the smallest adjusted p value was **0.183**. This result concerns the chosen structural indices. **R8 does not test death outcomes, estimate prediction accuracy, or provide a globally representative individual sample.**

[中文](README.zh.md) · [English article](articles/substack.en.md) · [中文文章](articles/substack.zh.md) · [Reproduce](docs/REPRODUCING.md) · [Methods](docs/statistical_design.md) · [Contribute](CONTRIBUTING.md) · [Research charter](CONSTITUTION.md) · [Research status 中文](RESEARCH_STATUS.zh.md)

## Question

The motivating rumor suggests that many younger people's charts lack future life/luck periods, sometimes interpreted as generational mass death. Its exact source and canonical decision rule have not been established. This project makes a narrower question explicit: do four versioned structural indices become elevated together unusually often under a declared phase reference?

Computable future chart entries do not establish survival. Missing entries outside a program's age range do not establish death. The [research questions and completion gates](docs/RESEARCH_QUESTIONS.md) define what the project can assess.

## Actual data

| Source | Source records inspected | Eligible frame | Four-system sample | Selected birth years |
|---|---:|---:|---:|---|
| Brazil SINASC 2006 | 2,944,928 | 2,805,207 | 2,000 | 2006 |
| Open Gauquelin Database, 2023 export | 25,869 | 1,388 | 1,388 | 1880–1962 |
| Astro-Databank free Z sample, November 2026 | 483 | 341 | 341 | 1880–2014 |

The union contains 32 country labels. The modern cohort is dominated by Brazil 2006; ADB adds only 42 births in 1980–2019, including 14 in the 1990s. There is only one China birth in the eligible ADB sample. Four possible ADB/OGDB overlaps were identified from birth inputs but not identity-confirmed. These are **source records, not 3,729 verified independent people**, and the sample cannot support estimates for China's 1990s/2000s cohorts or humanity as a whole.

Weights refer only to the eligible source frame. Brazil coordinates are municipal-seat reference points from IBGE, not precise birth sites. Time-zone ambiguity, source clock consistency, sex availability, duplicate counters and rounding are documented in the [data audit](data_expansion/README.md). Millions of source rows inspected must not be described as millions of charts scored.

![Sample coverage](figures/01_sample_coverage.png)

## Prespecified results

An elevated signal means within-record midrank percentile ≥0.8 over the forty annual values. With ties, this is not exactly the top 20% of years. A joint year has at least three elevated systems. The reference independently rotates each system within each ten-age band, preserving marginal frequencies and record weights. There are 1,999 draws and six Holm-corrected tests.

| Source | Completed ages | Observed joint rate | Exact phase-reference mean | Raw p | Holm p |
|---|---|---:|---:|---:|---:|
| OGDB | 20–59 | 2.275% | 2.236% | 0.4725 | 0.945 |
| OGDB | 20–49 | 1.707% | 1.723% | 0.7665 | 0.945 |
| Brazil 2006 | 20–59 | 2.287% | 2.225% | 0.1360 | 0.680 |
| Brazil 2006 | 20–49 | 1.864% | 1.798% | 0.1590 | 0.680 |
| ADB Z | 20–59 | 1.928% | 2.051% | 0.2255 | 0.680 |
| ADB Z | 20–49 | 1.388% | 1.618% | 0.0305 | 0.183 |

The nominal ADB 20–49 difference is a **deficit** of alignment and does not pass the six-test correction. Neither that deficit nor the other results describes real mortality. Failure to reject the phase reference is not proof of equivalence or a rejection of every possible traditional rule.

The calendar curves include descriptive peaks; this study does not assign year-specific event probabilities or test every annual peak for significance. Shared calendars and astronomical inputs mean four systems are not four independent empirical votes.

![Observed structural alignment](figures/02_phase_reference.png)

Machine-readable outputs: [all results](results/structural_results.json), [six-test table](results/primary_tests.csv), [calendar series](results/annual_2026_2070.csv), [sensitivity](results/sensitivity_results.json), [run integrity](results/run_integrity.json).

## What the four implementations contain

| System | Implemented workflow | Primary structural quantity | Material boundary |
|---|---|---|---|
| Bazi | Four pillars, solar terms, starting luck, ten-year/annual cycles, 14 conditional interpretation clauses | Annual/decadal branch clashes against natal pillars | Full strength, pattern priority, effective useful element and rescue adjudication remain incomplete |
| Ziwei | Twelve palaces, principal/auxiliary stars, transformations, decadal/annual maps, 5 conditional clauses | Annual/decadal Hua Ji in corresponding life/health palaces | No complete cross-school lifespan judgment |
| Qizheng | Seven luminaries/four points, unequal 28 mansions, selected fixed major/minor periods, monthly transits | Five fixed palace/mansion contact channels | Yuebo is a modern mean-apogee approximation; degree-dependent childhood/period methods are not implemented |
| Western | Ten-planet natal chart, whole-sign houses, monthly transits, secondary progressions, Naibod axes | Weighted geometric hard-contact index | A selected geometric model, not all traditions or validated adverse-event inference |

See the [four-system readiness table](docs/four_system_readiness.md), [Bazi/Ziwei methods](docs/bazi_ziwei_methods.md) and [Qizheng/Western methods](docs/qizheng_western_methods.md). Completing these specified calculation workflows is different from completing all classical interpretation.

## Verification and sensitivity

- 29 engine test methods plus 10 statistical test methods passed. Historical/astronomical checks include 50 planet/date comparisons and the 1833 primary almanac. They verify limited calculations, not divinatory validity.
- A separate AI agent independently recomputed the deterministic aggregate arithmetic: **495 comparisons, no substantive mismatches**. It did not rerun the 1,999 simulation tail counts. This is internal computational review, not external human peer review.
- At ±30 minutes, Western relative-high flags changed in approximately **23.93–24.98%** of paired record-years across the fixed subsets. Joint three-of-four flags changed in **2.35–3.13%**. These are classification changes, not changes in observed risk.
- At ±120 minutes, joint flags changed in **3.74–4.40%**. Brazil's four coordinate stress points changed joint flags in **0.025–0.275%**. Stress points are not measured uncertainty bounds.

The [analysis review](docs/analysis_independent_review.md), [actual result review](docs/result_numerical_review.md), engine validation records and [source/software provenance](docs/PROVENANCE.md) state exactly what was checked.

## Reproduce and extend

```bash
python -m pip install -r requirements.txt
npm ci --ignore-scripts
PYTHONPATH=src python scripts/smoke_check.py
```

The [complete reproduction guide](docs/REPRODUCING.md) covers source downloads, reconstruction, both profile runs, aggregate analysis and figures. Original SINASC and ADB rows are downloaded locally; they are not redistributed in this repository. The minimal licensed OGDB derivative is included. OGDB and ADB reconstruction was actually verified against frozen hashes; the full workflow has not been independently repeated in a newly provisioned environment.

Protocol and code were locally frozen before cohort scoring. A later review found that the sampling prose and actual Brazil allocation algorithm differed: 35 of 54 stratum quotas differed, equivalent to reallocating 22 of 2,000 slots (1.1%). No records were resampled. The [deviation record](docs/sampling_implementation_deviation.md) preserves both definitions and the actual weights. Input-validation and aggregation corrections made before result inspection are also retained in `protocol/`.

The [R7 pilot](baseline/r7/README.md) is a separately labeled prior retrospective experiment with different local rules. Reused ADB data are not a new independent holdout. Independent death-outcome testing is paused in R8.

## Open research

Useful next contributions include public birth-clock data from underrepresented regions/cohorts, source-based corrections to traditional rules, independently checked calendar examples and exact numerical replication. Propose new models before looking at their outcome results. See [CONTRIBUTING.md](CONTRIBUTING.md).

Code is AGPL-3.0-or-later; data retain [source-specific terms](data_expansion/DATA_LICENSES.md). Original project prose, figures and aggregate analysis outputs are CC BY 4.0, excluding reproduced source material. The pinned source manifests and acknowledgments remain part of any reuse. No affiliation with the original data providers or external peer-review endorsement is claimed.
