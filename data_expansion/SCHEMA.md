# R8 birth-only input schema

Three source frames are retained separately. The public release
contains code, source links, hashes, aggregate audits and reconstruction
instructions. It also includes the minimal OGDB birth derivative under its own
CC BY-SA 4.0 attribution; SINASC row-level inputs are reconstructed locally.
Third-party source records do not have the same license as the project's own
code. See `DATA_LICENSES.md`.

## Model input: `samples/<source>/birth_inputs.jsonl`

One JSON object per selected source record. No name, occupation, death date,
health information, parent information or outcome label is included.

| Field | Meaning |
|---|---|
| `study_id` | `R8-` plus first 24 hex digits of SHA-256 of the stable source record ID. Pseudonym, not a guarantee of anonymity. |
| `birth_local` | ISO Gregorian local civil datetime. A clock must be explicitly present in the original source. |
| `birth_utc` | Source UT datetime (OGDB) or the unique valid UTC conversion using IANA 2026c historical rules (SINASC). Ends in `Z`. |
| `source_offset_seconds` | Signed seconds east of UTC; historical second-level offsets are retained. |
| `sex_resolved` | `M` or `F`, mapped only from explicit source codes. Unknown sex is excluded, never guessed from names or occupations. |
| `latitude`, `longitude` | Decimal degrees, north/east positive. Brazil: official municipal-seat reference point, not hospital/birth coordinates. OGDB: original source locality coordinates, not independently certified. |
| `calendar` | `gregorian`. Selected source birth years are 1880–1962 in six Western countries and 2006 in Brazil. |
| `time_precision_seconds` | **Display resolution only:** 60 for HH:MM, 1 for HH:MM:SS. It is not an estimated error bound or claim of clock accuracy. |
| `time_uncertainty_seconds` | `null`; actual measurement error is not known. Sensitivity scenarios are assumptions, not measured uncertainty. |
| `coordinate_precision_degrees` | `null`; error relative to actual birthplace is unknown. Decimal places do not imply physical accuracy. |
| `timezone_id` | IANA identifier for Brazil. `null` for OGDB because the source supplies a historical offset without a certified zone identifier. |
| `instant_scale` | `UT`, retained for compatibility with the research engine. Civil time versus UT1 differences are not resolved by the source. |

## Metadata: `samples/<source>/birth_metadata.jsonl`

Contains all model fields plus provenance, quality and design fields. Join only
by `study_id`. Metadata is not passed into prediction functions.

- `source`, `source_id`, `source_row_id`: exact snapshot and stable record locator.
  Brazil uses **one-based physical data row ordinal inside the pinned CSV ZIP**.
  Its `contador` field is stored as `source_record_counter` and must not be used
  as a national unique key: it repeats 2,341,560 times in this snapshot.
- `birth_country`, `birth_year`, `birth_decade`, `sex`: source demographics.
- `geo_precision`: `municipality_reference` (Brazil) or
  `source_locality_reference` (OGDB and ADB).
- `quality`, `uncertainty_flags`, source coordinate/clock/zone method details.
- `stratum_id`, `N_h`, `n_h`, `inclusion_probability=n_h/N_h`,
  `sample_weight=N_h/n_h`, `weight_scope=eligible_source_frame_only`.
- `sampling_sha256`: SHA-256 of `OBS-R8-2026-11-26|<source_id>`.

Every nonempty stratum receives at least one sample where feasible. Proportional
integer quotas use largest remainders, with lexical stratum IDs breaking ties.
Within each stratum the lowest hashes are selected. Sampling decisions use no
prediction outputs or death outcomes.

The Brazil strata are UF × explicit sex × decade (2000) × quality; there are
54. OGDB strata are country × sex × birth decade × quality; there are 41. ADB
uses the same country/sex/decade dimensions with AA/A source quality separated,
giving 176 strata. The complete eligible OGDB and ADB reference frames are each
smaller than 2,000 and are retained, so their weights are all 1. These weights do
**not** repair source selection, missing clock or sex data, unresolved time zones,
unregistered births or geographic coverage gaps.

## Exclusions and deduplication

Brazil: exclude invalid/missing date, recorded HHMM clock, M/F or municipality;
unmatched municipal code; unresolved historical zone in split states; and local
times with zero or multiple valid UTC instants. Do not silently fill a clock,
zone, sex or coordinate. Physical rows are the record unit. Equal birth tuples
are not deleted because twins and other genuine coincidences can share them.

OGDB: decode PostgreSQL COPY escaping once; read only ID, sex and birth JSON.
Require explicit clocks, offset, finite nonzero coordinates, M/F, year
1880–1979, source country and local minus UTC minus offset residual ≤1 second.
Keep the source UTC and offset even when they differ by one rounding second.
Duplicate numeric source primary IDs would be excluded, but none were observed.
Source-locality coordinates and offset consistency are not independent
birth-certificate or historical-timezone validation.

ADB: retain explicit Gregorian dates in 1880–2019, source rating AA or A, single
human M/F records, explicit clock/coordinates/time meridian/Julian UT, and local
clock-minus-meridian agreement with source Julian UT within one second. Source
clock-unknown flags and insufficient time-accuracy codes are excluded. Country
codes are mapped explicitly to ISO country labels; contradictory code/name pairs
are excluded. This is the **same 483-record ZIP snapshot used in R7**, projected
over a wider birth window. No earlier identity exclusions are applied because
R8 treats it as a reused reference source, not an independent blind holdout.
Individual ADB records and derived person-level inputs are not redistributed.

## Reproduction

```bash
python download_sources.py
python build_birth_inputs.py --max-n 2000
python build_adb_reference.py
python audit_birth_inputs.py --verify-brazil-source
```

These commands run from `data_expansion/`. Portable defaults use the ignored
`data/cache/` and `data/reconstructed/` subdirectories next to the scripts.
Override the input cache with `--raw-dir PATH` and generated output with
`--output-dir PATH`; the auditor takes `--input-dir PATH` for reconstructed data.

The build requires Python's standard library, an IANA zoneinfo database and
approximately 110 MB of raw/locality storage. Pin IANA **2026c** to reproduce the
published input hashes exactly. The script records the installed tzdb version.
If a public archive's hash has changed, the downloader stops instead of quietly
treating a different release as this frozen cohort.
