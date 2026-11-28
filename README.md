# Open Birth Chart Study

[简体中文](README.zh.md) · [Research program](docs/RESEARCH_PROGRAM.md) · [Constitution](CONSTITUTION.md) · [Research status](RESEARCH_STATUS.md)

Can a claimed break in younger generations’ birth charts be defined, tested and reproduced across populations? This project uses documented birth records and versioned Bazi, Ziwei Doushu, Qizheng Siyu and Western astrology calculations to test that question. The evidence concerns specified model structure and period coverage. Real outcomes and the effects of AI have separate evidence requirements.

## Current findings

| Question | What the evidence supports |
| --- | --- |
| Do four Brazilian and Mexican cohorts share a large gap at the 75th percentile? | **R49 excludes the registered +5 percentage-point effect** for the four studied source frames. With **21,416** new, physically disjoint records and the fixed Brazil 2006 reference, the common peak was **+2.206 percentage points** and its primary interval was **+1.215 to +3.469**. Both secondary intervals also excluded +5. [Result and review](R49.md) |
| Does changing the alignment or rounding change the earlier result? | At the 80th percentile, R45 excluded +5 for the tested same-age and same-calendar gaps. R46 excluded +5 for the 2009 whole-hour comparison. Its two earlier 75th-percentile upper bounds used different groups to constrain the same window starting at age 34. R49 recomputed that discrepancy. [R45](R45.md) · [R46](R46.md) · [Interval analysis](rounds/r49/R46_DIFFERENCE.zh.md) |
| Can the specified methods produce continuous adult periods? | R48 checked **6,766** birth records. The specified Bazi method and both Ziwei starting-palace conventions provided continuous adult coverage. The circulating claim's earliest attributable wording and decision rule remain unverified. [Literal period check](R48.md) |
| Does the finding transfer to East Asia? | This remains unresolved. Japanese date-hour counts for **148,030** births permit minute and sex allocations that put the R47 result on both sides of +5. A contemporaneous, authorized source with jointly observed date, minute, sex and occurrence location is the priority. [R47](R47.md) · [External study acceptance criteria](docs/RESEARCH_PROGRAM.md) |

The gap endpoint refers to a ten-year modeled window with no year where at least three systems reach the defined score threshold. The comparison tests whether these windows concentrate at the same age or calendar period across the specified cohorts, against a fixed reference. The birth years 1999 and 2009 and the admissible source frames define the scope. Brazil 1999 is geographically concentrated and Mexico 1999 comes from late registrations. [Definitions and scope](docs/R45_FOLLOWUP.zh.md)

## Reproduce and cite

- **Current reference release.** R49 publishes its registration, source receipts, group aggregates and independent calculation review. The guide gives the full input and scoring path. [R49 reproduction](rounds/r49/REPRODUCE.md) · [R49 results](rounds/r49/results.json)
- **Original four-system reconstruction.** R10 reproduced scores for **12,000** records across six groups against the fixed Brazil 2006 reference. The original sampling notes for the two Mexico groups remain unavailable. The reconstruction and source checks are public. [R10](R10.md)
- **Historical releases.** The original R8 homepages and R9 workflow are pinned to their release commits. The current release check uses those bytes and verifies every other protected path from the current checkout. Use a full clone to run `python3 scripts/verify_frozen_releases.py`. [R8 English](https://github.com/CPTM511/open-birth-chart-study/blob/210bb7bdab85a9f3672f19241e9ef66eb22021a2/README.md) · [R8 中文](https://github.com/CPTM511/open-birth-chart-study/blob/210bb7bdab85a9f3672f19241e9ef66eb22021a2/README.zh.md) · [R9 release](https://github.com/CPTM511/open-birth-chart-study/blob/8c74a1883404002132dfa82d218a69106c344369/rounds/r9/README.md)

Cite the specific round and commit. The repository publishes aggregate evidence and attributable methods. Individual source rows are handled under their source terms. [Citation](CITATION.cff) · [Data terms](data_expansion/DATA_LICENSES.md) · [Contributing](CONTRIBUTING.md)
