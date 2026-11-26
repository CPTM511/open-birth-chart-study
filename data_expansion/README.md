# R8 public birth-data expansion

This directory contains the actual acquisition, birth-only cleaning, historical
time-zone conversion, deterministic sampling and data-quality work for R8.
It does not contain death predictions, outcome labels or a mortality validation.
It prepares three separately analyzed source frames for the frozen four-system
research models. All downloads were public, free and required no registration.

## What was obtained and made usable

| Source snapshot | Actual source records | Eligible birth input frame | Selected inputs | Birth years selected | Geographic coverage |
|---|---:|---:|---:|---|---|
| Brazil SINASC 2006 national CSV | 2,944,928 birth-record rows | 2,805,207 | 2,000 | 2006 | Brazil, all 27 UFs; selected areas of the two split-time-zone states |
| Open Gauquelin Database, public PG export last modified 2023-08-20 | 25,869 source-person records | 1,388 | 1,388 | 1880–1962 | France 833, United States 360, Italy 178, Germany 15, Belgium 1, Luxembourg 1 |
| Astro-Databank free Z sample, 2026-11-10 | 483 source entries | 341 | 341 | 1880–2014 | 31 source country labels; alphabetically selected reference data |

The model input files contain **3,729 source-record projections**, not 3,729
verified independent people. A birth-only overlap check finds four candidate
ADB–OGDB pairs with the same date/sex and locality points within 25 km. Those
pairs were not identity-verified or silently merged. The source-country label
union is 32 countries, but this is **not a representative sample of humanity**.

The 341 ADB records include 42 births in 1980–2019 from 15 countries: 22 in the
1980s, 14 in the 1990s, three in the 2000s and three in the 2010s. The eligible
ADB sample contains only one China birth. The modern population-style frame is
Brazil in a single year; the historical and multi-country supplements are
selected collections. These data do not support estimates for China's 1990s or
2000s birth populations, the full global 1980–2019 population, or the world's
future mortality.

Counts in this README are produced by the scripts and recorded in `audits/`.
The [official SINASC dataset](https://dadosabertos.saude.gov.br/dataset/sistema-de-informacao-sobre-nascidos-vivos-sinasc)
defines the national registration source. The [OGDB project](https://opengauquelin.org/)
describes its selected historical collections and warns about remaining data
errors. The [official ADB export page](https://www.astro.com/adbexport/) describes
its Z-name sample and provider ratings.

## What the quality audit found

**Brazil.** All 2,944,928 source dates are in 2006. Of these, 2,934,762 contain a
valid date, explicit HHMM clock, explicit M/F code and six-digit birth
municipality code. Missing or invalid clocks occur in 9,275 records; unknown or
other sex codes occur in 923. These field-failure categories overlap; the total
number of rows failing the required field checks is 10,166. The source
dictionary identifies `DTNASC` as birth date, `HORANASC` as birth time,
`CODMUNNASC` as birth municipality and sex 1/2 as male/female.

Every field-complete municipality code joins exactly to the first six digits of
an official 2022 IBGE municipality code. The script selects the **municipal-seat
locality reference point**, not a hospital point, household point, polygon
centroid or independently observed birthplace. The 2022 reference year is
explicitly retained when approximating a 2006 location. The official coordinate
source is [IBGE Localidades do Brasil](https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/).

Historical offsets use IANA 2026c rules for the actual 2006 local date. In
Amazonas and Pará, only municipalities explicitly placed by the
[IANA Brazil definitions](https://data.iana.org/time-zones/tzdb/southamerica)
are assigned a zone; 129,280 otherwise complete records are excluded rather
than assigned a guessed offset. Another 265 local times have two valid UTC
instants at a daylight-saving fold, and ten have none at a daylight-saving gap.
They are also excluded. Thus 2,805,207 records form the explicitly eligible
frame. Weights refer to this restricted frame, not all Brazilian births.

A critical identifier check found that `contador` repeats 2,341,560 times in the
national export. It is not a unique national person ID. Every physical birth
record is retained, with a stable source ID based on the one-based CSV row
ordinal in the pinned ZIP. Equal date/time/sex/place combinations are not
deleted: legitimate twins and coincident births can share them. After selection,
all 2,000 sampled records were independently reread from the original ZIP and
matched exactly on date, time, sex, municipality, counter and row ordinal.

Among field-complete Brazil records, 1,906,943 of 2,934,762 clocks have a minute
divisible by five, approximately 65.0%. Clock text is not a measured accuracy
guarantee; `time_uncertainty_seconds` remains null.

**OGDB.** All 25,869 birth JSON objects were parsed after correctly decoding
PostgreSQL COPY escapes. Only ID, recorded sex and birth JSON were projected;
other columns were ignored. The snapshot has 20,304 records without explicit
sex. A total of 12,593 have complete clock/UT/offset and finite non-placeholder
coordinates, 1,769 also have explicit M/F, and 1,621 fall in 1880–1979. The
source local-clock minus UTC minus offset difference exceeds one second for
233 of those records, leaving 1,388 usable inputs. Of these, 1,301 are male and
87 female. The strong source and completeness selection remains visible.

The retained source clocks and UT values are preserved. In 162 records the
offset consistency residual is minus one second, within the predeclared
rounding tolerance; this is not silently corrected. A coordinate equal to zero
on one axis remains valid. Only a `(0,0)` placeholder, absent/nonfinite values
or out-of-range coordinates are rejected. A source-locality coordinate is not
certified hospital precision. Passing these checks does not convert OGDB
records into independently verified birth certificates.

**ADB.** The downloaded ZIP is byte-identical to the R7 snapshot. R8 widens the
date window to 1880–2019 and uses it as a reused reference source. The original
483 entries contain 304 AA and 89 A records. The final subset has 255 AA and 86 A
records, all with explicit Gregorian birth information and source Julian UT
consistent with local clock minus source time meridian within one second.
Provider AA/A grades are retained as separate quality strata and are not
described as independent certificate verification. There are 258 male and 83
female records. Surname-based selection and possible cross-source overlap are
not corrected by source-inclusion weights.

## Sampling and reproducibility

The frozen seed is `OBS-R8-2026-11-26`. Each independent source frame is capped
at 2,000 eligible records. Strata are country (Brazil UF within country) × sex ×
birth decade × quality. Proportional quotas use largest remainders and give
each nonempty stratum at least one record. Within stratum, the smallest
SHA-256 hashes of `seed|source_id` are selected. ADB and OGDB are below the cap,
so all eligible records are retained. The model builder did not read
prediction distributions or outcome labels before selection.

`sampling_manifest.json` records each stratum's frame count `N_h`, sample count
`n_h`, inclusion probability `n_h/N_h` and weight `N_h/n_h`. All individual
record IDs are unique within a source. Sample weights sum exactly, within
floating-point tolerance, to each eligible frame count. These are conditional
source-frame probabilities, not global survey weights.

Run the scripts from the repository root. Defaults keep downloaded and locally
reconstructed records in the ignored `data_expansion/data/` directory:

```bash
python data_expansion/download_sources.py
python data_expansion/build_birth_inputs.py --max-n 2000
python data_expansion/build_adb_reference.py
python data_expansion/audit_birth_inputs.py --verify-brazil-source
```

For a pre-existing cache and a separate reconstruction directory, provide
`--raw-dir PATH` and `--output-dir PATH` to either builder. The auditor accepts
`--input-dir PATH` and an optional separate `--output-dir PATH` for reports.
The downloader verifies an existing pinned archive instead of downloading it
again. See `REQUIREMENTS.md` for all defaults and portable time-zone setup.

Python's standard library plus IANA zoneinfo is sufficient. The reference build
uses IANA **2026c**. Downloads use pinned byte lengths and SHA-256 hashes and stop
if a source has changed. Large archives and temporary GeoPackage files should
stay outside the repository. The national CSV is streamed from its ZIP.

| Input | SHA-256 |
|---|---|
| Brazil model input | `3d9a2dc48a26a083a20abbd372310310d13b6e93d880a4f8d1fafa02f8914f6d` |
| OGDB model input | `76b78ec7e494c2bccc13922e782631071147519894c64cf691d09b0005e1c2cf` |
| ADB model input | `b2db70b22414ad12d8d6d4a7dee6d2bcd79cc5d2fbeb88b713bcf954cd029061` |

See `SCHEMA.md` for field definitions and `DATA_LICENSES.md` for source-specific
attribution. Only the minimal OGDB derivative and its reconstruction index are
redistributed under CC BY-SA 4.0. SINASC and ADB individual inputs are recreated
locally from their publishers. No original archive or person-year prediction
table is included in the public data bundle.

`verification/README.md` records a fresh-output rebuild of OGDB and ADB with the
public scripts and the frozen cache. Both model-input hashes match the original
research inputs. The earlier 2,000-row Brazil source verification is retained;
the national table was not needlessly rescanned during repository integration.

## What remains outside this data result

This work provides real expanded birth records, documented approximations and
reproducible model inputs. It does not complete a global representative
individual sample, establish that four metaphysical systems are valid predictors,
test the mortality rumor, or estimate an individual's lifespan. Death blind
testing is paused in this round. Reproducible signal patterns, if produced by
the separate models, require an independent outcome study before they can be
interpreted as real-world predictive performance.

Mexico 2000/2008/2010 direct archive probes returned HTML soft-404 responses,
not valid ZIPs; they were not counted as acquired birth records. OGDB's new
download endpoint returned an empty body; the published older downloadable
snapshot was used instead. These failures are retained in the acquisition
audit rather than converted into coverage claims.
