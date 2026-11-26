# Contributing

This project examines explicit computational versions of four birth-chart traditions. It welcomes corrections from traditional practitioners, historians of astronomy, demographers, statisticians and software contributors. A useful contribution specifies what would change the result and how another person could check it.

## Suitable contributions

- **Data:** a publicly accessible source with a real birth date, recorded clock, explicit historical offset or absolute instant, location and provenance. Report the sampling frame, missingness, geographical/cohort coverage and reuse terms. Date-only lists do not meet the current four-system interface.
- **Textual rules:** name the work, edition and passage; provide the complete applicable conditions, exceptions and rescue conditions; explain contradictory cases. A quoted adverse phrase alone is not an executable prediction rule.
- **Calendar or astronomy corrections:** provide a minimal synthetic example, expected result and an independent reference. Distinguish numerical error, convention choice and textual disagreement.
- **Statistics:** identify the estimand, dependence structure, missing-data assumptions and a falsifiable alternative. The current phase-reference test is not an outcome test.
- **Replication:** report the release/commit, input hashes, dependency and timezone versions, exact command and resulting aggregate hashes. Describe any mismatch before interpreting it.

## Changes and versions

Open an issue describing the evidence, then propose a focused pull request. Preserve the published R8 protocol, data-input seals and results. A new rule or source is a new version, not a silent replacement of the frozen analysis. Corrections should explain the old behavior, the new behavior, affected outputs and whether outcomes or previous effects were visible when the choice was made.

Run the existing relevant tests. Do not tune a rule until a historical outcome becomes significant and then describe the exercise as a new prediction. Synthetic fixtures must be labeled as synthetic and must never be added to real-person sample counts.

## Data and interpretation

The public release contains a minimal licensed OGDB derivative, source acquisition/reconstruction scripts and aggregate outputs. It does not redistribute individual SINASC/ADB inputs or person-year scores. Do not include credentials, private data or identifiable personal lifespan assessments in an issue or pull request. Use a synthetic example for a software defect whenever possible.

No current score is a death probability. Shared calendars, birth inputs and astronomical inputs make the four outputs statistically dependent. Null results, failed implementations and unresolved textual cases are legitimate research results.

## A next study that could change the evidence

A future outcome study would need a separately frozen rule set, genuinely withheld or prospective outcomes, an explicit risk set and follow-up period, outcome ascertainment independent of chart scores, appropriate age/cohort/place baselines and correction for all attempted endpoints. These are future research requirements. Death-outcome validation is paused in R8.

Contributions retain their source licenses. New project code uses AGPL-3.0-or-later; see [LICENSE](LICENSE), [provenance](docs/PROVENANCE.md) and [data terms](data_expansion/DATA_LICENSES.md).
