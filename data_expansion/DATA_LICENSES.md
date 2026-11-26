# Source attribution and release boundaries

The project's own code and reports must be distinguished from third-party data.
Public access alone is not a claim that a source has no attribution or reuse
conditions. The following is the actual release arrangement for R8.

## Open Gauquelin Database birth derivative — CC BY-SA 4.0

**Attribution:** Open Gauquelin Database, maintained by Thierry Graff, drawing on
the historical collections documented by that project: Michel and Françoise
Gauquelin, Arno Müller, Suitbert Ertel, Comité Para, CSICOP and CFEPP. The project
also credits Patrice Guinard/CURA and other contributors for restoring and
making the historical source data available; the complete credits are at
<https://opengauquelin.org/#credits>.

- Project: <https://opengauquelin.org/>
- Source history and contributors: <https://opengauquelin.org/history>
- Source information: <https://opengauquelin.org/sources>
- Data download: <https://opengauquelin.org/download/ogdb-pg-dump.zip>
- Licensing statement: <https://opengauquelin.org/about>
- License: **Creative Commons Attribution-ShareAlike 4.0 International**,
  <https://creativecommons.org/licenses/by-sa/4.0/>

The project home describes data availability under Creative Commons. Its About
page identifies CC BY-SA 4.0 and separately lists GPL and FDL for site content and
related software. R8 distributes only its minimal birth-record derivative and
source index under **CC BY-SA 4.0**, with the above attribution and source links.
No endorsement by Open Gauquelin Database or its contributors is implied.

**Snapshot:** public PostgreSQL ZIP last modified 2023-08-20, retrieved
2026-11-26. SHA-256:
`b9a90c6bfc5856a05305360e8faa7d67ca71f001a9ae5ab4efd79df81dc0d01c`.

**Changes made:** only numeric source ID, recorded sex and birth JSON were parsed;
records were selected by the published birth-field quality rules; names,
occupations, death fields, other outcomes and free-text notes were excluded;
field names and datetimes were normalized; a stable pseudonymous study ID and
source index were generated. Original UTC instants, offsets and locality
coordinates were not corrected. The derivative contains 1,388 selected source
records. It is neither the full original database nor a population probability
sample. The public index permits reconstruction from the pinned original.

Covered files in the release bundle:

- `ogdb_birth_inputs.jsonl`
- `ogdb_source_index.jsonl`

Any downstream distribution of adaptations of those data files must preserve
the applicable attribution and ShareAlike terms. These files must not be relabeled
as MIT, public domain or the project's code license.

## Brazil SINASC 2006 — reconstruction only

**Attribution:** Ministério da Saúde, Sistema de Informações sobre Nascidos Vivos
(SINASC), national 2006 CSV export, snapshot retrieved 2026-11-26.

- Dataset: <https://dadosabertos.saude.gov.br/dataset/sistema-de-informacao-sobre-nascidos-vivos-sinasc>
- Archive: <https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINASC/csv/DNBR2006_csv.zip>
- Official dictionary: <https://diaad.s3.sa-east-1.amazonaws.com/sinasc/SINASC+-+Estrutura.pdf>

The present portal's site-wide notice says Creative Commons Attribution-
NoDerivatives 3.0; the dataset-specific license display is a placeholder. R8
does not infer a broader dataset grant from the word “open.” It distributes the
download/cleaning/sampling code, hashes, design metadata and aggregate audit
tables. **The original ZIP, national CSV, selected SINASC individual birth
records and person-year predictions are not bundled for redistribution.**
Readers obtain the source from the publisher and reconstruct inputs locally.

## IBGE municipal reference coordinates — reconstruction only

**Attribution:** Instituto Brasileiro de Geografia e Estatística (IBGE),
Localidades do Brasil, Censo Demográfico 2022.

- Source directory: <https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/>
- Archive: <https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/Localidades_Brasil_gpkg.zip>

The script extracts the official locality reference point for each municipal
seat, rather than inventing a point or claiming an exact birthplace. The
extracted reference table is rebuilt locally and is not included as a new
standalone redistributed geodataset. The source coordinates refer to 2022;
using them to approximate 2006 birth locations is a documented limitation.

## IANA historical time-zone rules

**Attribution:** IANA Time Zone Database, version 2026c; Brazil definitions in
<https://data.iana.org/time-zones/tzdb/southamerica>.
The scripts call the installed `zoneinfo` data, record its version and use the
historical rules applicable at each birth date. No present-day UTC offset is
substituted for a historical one.

## Astro-Databank official free Z sample — reconstruction only

**Attribution:** Astrodienst AG / Astro-Databank; official free Z-name export,
revision 2026-11-10, retrieved 2026-11-26.

- Export instructions: <https://www.astro.com/adbexport/>
- Free sample: <https://www.astro.com/adbexport/z_sample.zip>
- Source license document: <https://www.astro.com/adbexport/adb_license.pdf>

The official export page makes this 483-record sample available for researchers
to develop tools and techniques and test software. It is not treated as a grant
to redistribute individual data records. R8 distributes the download/projection
scripts, checksums and aggregate quality/coverage tables. The XML, individual
birth projections, source ID mapping and individual prediction outputs are not
included in the public bundle. No paid subscription or login was used.

This is a **reused reference source**: its ZIP hash is identical to the R7 source
snapshot. R8 broadens its date window to 1880–2019 and keeps all 341 eligible
records; it does not claim a fresh independent cohort.
