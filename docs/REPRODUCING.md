# Reproducing the R8 structural-signal study

This guide describes the actual command interfaces and reference environment.
It separates the calculations that have been checked during release preparation
from a clean, complete rerun of the study. It does not claim that a new machine
has reproduced the entire cohort analysis merely because the commands are
documented.

All commands below run from the repository root. Downloaded sources, reconstructed
individual records and individual model profiles stay in ignored local directories.
Published results are aggregate structural statistics, not mortality estimates.

## 1. Reference environment

The observed release environment is recorded in
[`reproduction_environment.json`](reproduction_environment.json).

| Component | Observed version | Role |
|---|---|---|
| CPython | 3.12.14 | Data preparation, models and analysis |
| NumPy | 2.3.5 | Arrays and phase-reference randomization |
| SciPy | 1.17.0 | Ranks and descriptive correlations |
| lunar-python | 1.4.9 | Bazi calendar/cycle implementation |
| pyswisseph | 2.10.3.2 | Swiss Ephemeris calculations using the declared Moshier backend |
| astronomy-engine | 2.1.19 | Independent astronomical comparison checks |
| Node.js / npm | 24.22.3 / 11.19.1 | Persistent Ziwei bridge |
| iztro | 2.6.5 | Ziwei calculations |
| IANA time-zone database | 2026c | Historical Brazil civil-time conversion |
| Matplotlib, optional | 3.10.8 | Aggregate PNG/SVG figure rendering |
| markdown2, optional | 2.5.3 | Article HTML rendering |

The direct Python dependencies are pinned in `requirements.txt`. Node's exact
dependency tree is in `package-lock.json`, copied from the installed reference
resolution with the root iztro requirement narrowed to exact `2.6.5`. This is
not a claim of a fully hermetic operating-system or compiler image. Figure
rendering can also depend on the platform's graphics libraries.

Create an environment using Python 3.12; the following POSIX-shell commands
assume the reference interpreter and Node are available:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip==26.2.2
python -m pip install -r requirements.txt
python -m pip install -e .
npm ci --ignore-scripts
export OBS_NODE_MODULES="$PWD/node_modules"
```

`pyproject.toml` makes `src/open_birth_chart` installable and includes the
`ziwei_bridge.cjs` file. Alternatively, after installing the requirements, use
`PYTHONPATH=src` for direct Python imports; the supplied command-line scripts
already add the local `src` directory. `OBS_NODE_MODULES` points the bridge to
the repository's installed Node dependencies, including when Python imports an
installed package outside the source tree.

If `pyswisseph` must be built from source, a working C/C++ toolchain is needed.
The reference installation used `CC=gcc CXX=g++` because its default clang was
unavailable. No external ephemeris-file download is required by the declared
Moshier-backend implementation. For Brazil's time-zone database, follow
[`data_expansion/REQUIREMENTS.md`](../data_expansion/REQUIREMENTS.md); unknown
or different tzdb versions must remain visible in the build manifest.

For optional figures and article rendering:

```bash
python -m pip install -r requirements-publication.txt
```

## 2. Smoke checks without source or private data

```bash
python scripts/smoke_check.py
```

The wrapper runs eight existing synthetic/fixed-fixture tests across Bazi,
Ziwei, astronomy and the phase-reference calculations. It does not download
birth data or read cohort records, individual profiles or mortality labels.
An optional report can be written to an ignored local directory:

```bash
python scripts/smoke_check.py --output private/checks/smoke.json
python scripts/smoke_check.py --full
```

The second command runs all existing test suites. These checks assess declared
implementation behavior; they do not establish predictive validity of astrology.

## 3. Fetch the pinned public source snapshots

Primary download locations are:

| Source | Publisher URL | Use in this release |
|---|---|---|
| SINASC 2006 | <https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINASC/csv/DNBR2006_csv.zip> | Brazil birth-record frame |
| SINASC dictionary | <https://diaad.s3.sa-east-1.amazonaws.com/sinasc/SINASC+-+Estrutura.pdf> | Official birth-field definitions |
| OGDB PostgreSQL snapshot | <https://opengauquelin.org/download/ogdb-pg-dump.zip> | Birth-only projection of the historical collection |
| ADB free Z sample | <https://www.astro.com/adbexport/z_sample.zip> | Reused alphabetical reference source |
| IBGE Localidades 2022 | <https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/Localidades_Brasil_gpkg.zip> | Municipal-seat reference coordinates |
| IANA Brazil definitions | <https://data.iana.org/time-zones/tzdb/southamerica> | Historical time-zone mapping |

Publisher descriptions and licensing are linked in
[`DATA_LICENSES.md`](../data_expansion/DATA_LICENSES.md). The original SINASC,
ADB and IBGE archives and the SINASC/ADB individual derivatives are **not
redistributed in this repository**. Readers fetch them locally from the
publishers. The small OGDB birth-only derivative and its source index are
public here under their separate CC BY-SA 4.0 attribution; that data license
must not be confused with the project's code license.

```bash
python data_expansion/download_sources.py
```

The default cache is `data_expansion/data/cache/`. The four required source ZIPs
total about 88.8 MB. Existing cached files are hash-verified and reused. SHA-256
hashes and byte lengths are pinned in `download_sources.py` and
`source_provenance.json`. If a publisher changes an archive, the downloader
stops; a different snapshot must not silently replace the frozen source.

## 4. Reconstruct and audit the three input frames

```bash
python data_expansion/build_birth_inputs.py --max-n 2000
python data_expansion/build_adb_reference.py
python data_expansion/audit_birth_inputs.py --verify-brazil-source
```

The default generated root is `data_expansion/data/reconstructed/`, containing
`samples/ogdb2023/`, `samples/brazil2006/` and `samples/adb_z2026/`. Each source
directory contains `birth_inputs.jsonl`, `birth_metadata.jsonl` and
`sampling_manifest.json`; the model runner requires all three. The publicly
provided minimal OGDB JSONL alone is not a substitute for that full input
interface.

The national CSV is streamed from its ZIP. The official `contador` repeats,
so stable Brazil source IDs use physical ZIP-row ordinals. No birth clock, sex,
time zone or exact birthplace is silently invented. See
[`SCHEMA.md`](../data_expansion/SCHEMA.md) for the exclusions and approximations.

The expected model-input hashes are:

| Source directory | Records | SHA-256 |
|---|---:|---|
| `ogdb2023` | 1,388 | `76b78ec7e494c2bccc13922e782631071147519894c64cf691d09b0005e1c2cf` |
| `brazil2006` | 2,000 | `3d9a2dc48a26a083a20abbd372310310d13b6e93d880a4f8d1fafa02f8914f6d` |
| `adb_z2026` | 341 | `b2db70b22414ad12d8d6d4a7dee6d2bcd79cc5d2fbeb88b713bcf954cd029061` |

The Brazil proportional-quota implementation differs from the frozen protocol
prose. The actual sample and weights are preserved and the discrepancy is
quantified in [`sampling_implementation_deviation.md`](sampling_implementation_deviation.md).
Reproduction means reconstructing the **as-executed** inputs; do not fix that
disclosure by replacing the sample or editing the original freeze.

All directory paths can be overridden: builders accept `--raw-dir` and
`--output-dir`, while the auditor accepts `--input-dir` for the reconstructed
root and `--output-dir` for audit reports. No user-specific environment path is
required.

## 5. Compute baseline and sensitivity profiles

Preserve the sealed source order: **OGDB, Brazil, ADB**. Use a new private run
directory for a new execution. The runner accepts one to four local workers;
two is its default. It refuses to overwrite an existing profile file.

```bash
python scripts/run_profiles.py \
  --samples data_expansion/data/reconstructed/samples/ogdb2023 \
            data_expansion/data/reconstructed/samples/brazil2006 \
            data_expansion/data/reconstructed/samples/adb_z2026 \
  --output private/runs/reproduction_01 --jobs 2 --mode baseline

python scripts/run_profiles.py \
  --samples data_expansion/data/reconstructed/samples/ogdb2023 \
            data_expansion/data/reconstructed/samples/brazil2006 \
            data_expansion/data/reconstructed/samples/adb_z2026 \
  --output private/runs/reproduction_01 --jobs 2 --mode sensitivity
```

The baseline requests 3,729 source-record trajectories, each with 40 completed
age-20-to-59 annual points and four system scores. Source records are not
assumed to be independent people. The frozen stress design selects up to
200 records per source for four clock offsets and up to 100 municipality-point
records for four geographic offsets: 2,800 requested sensitivity profiles for
these frozen frames. These stress points are not measured error intervals.

Each mode writes its profile JSONL, run seal and completion summary. Profile
files contain individual model outputs and stay in the ignored `private/`
directory. A missing or failed calculation is an abstention, not zero signal,
death or an inferred survival endpoint. The run seals record code and protocol
hashes for the later integrity checks.

## 6. Analyze only completed, matching runs

The actual aggregation CLI is:

```bash
python scripts/analyze_profiles.py \
  --samples data_expansion/data/reconstructed/samples/ogdb2023 \
            data_expansion/data/reconstructed/samples/brazil2006 \
            data_expansion/data/reconstructed/samples/adb_z2026 \
  --run-dir private/runs/reproduction_01 \
  --output results/reproduction_01
```

This checks source hashes, the three-source order, profile completeness, input
keys, calendar trajectories, protocol identity and frozen scoring-module
hashes before aggregation. It requires both baseline and sensitivity outputs
and refuses to replace an existing `structural_results.json` release.

Outputs include `structural_results.json`, `sensitivity_results.json`,
`primary_tests.csv`, `annual_2026_2070.csv`, `analysis_execution_seal.json` and
`run_integrity.json`. They are aggregate results; the command does not publish
the individual profile files. The 1,999 phase-reference draws, seed, age windows
and six-test Holm family come from the frozen protocol, not a new user-chosen
configuration. These statistics test the specified structural-alignment
reference and do not validate mortality prediction.

Optional aggregate figures can then be generated without raw birth data:

```bash
python scripts/make_figures.py \
  --results results/reproduction_01 --output figures/reproduction_01
```

The renderer creates PNG and SVG figures from the two aggregate result JSON
files. Article preparation is documented separately; no private input table
needs to be embedded in an article or pushed to GitHub.

## 7. What this release preparation actually verified

- **Data rebuild:** OGDB and ADB were reconstructed into a fresh output directory
  using the existing pinned cache, and both complete input files matched the
  frozen SHA-256 hashes. No repeated archive download was needed. Evidence:
  [`fresh_rebuild_validation.json`](../data_expansion/verification/fresh_rebuild_validation.json).
- **Brazil source transcription:** all 2,000 sampled records were independently
  reread from the original ZIP and matched. The full national cleaning pass was
  not repeated during public-project integration. Evidence:
  [`sample_integrity_validation.json`](../data_expansion/audits/sample_integrity_validation.json).
- **Smoke entry point:** the eight-check wrapper passed using the installed
  reference dependencies and no source cohort. Evidence:
  [`reproduction_smoke_validation.json`](reproduction_smoke_validation.json).
- **Packaging:** the Python wheel was built with existing packaging tools and
  checked for the Node bridge. Evidence:
  [`reproduction_package_validation.json`](reproduction_package_validation.json).

This scaffolding verification did **not** create a clean operating-system image,
perform a fresh dependency installation, or rerun every source profile and
statistical result from scratch. The documented full workflow and the original
study's own run-integrity records are separate from these narrower checks.
