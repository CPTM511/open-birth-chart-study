# R9 data coverage ledger

R9 prepares **4,000 additional source-record inputs** from two restricted
eligible frames totaling **3,991,280 records**. These are record counts, not
verified counts of unique people. This ledger concerns acquisition and input
quality; it makes no claim about scoring results or predictive validity.

## Acquisition and usable coverage

| Source | Actual acquisition | Eligible frame | Selected records | Coverage boundary |
|---|---|---:|---:|---|
| Brazil SINASC 1996 | Official ZIP obtained; schema inspected | Not constructed | 0 | Required `HORANASC` birth-clock field absent |
| Brazil SINASC 2001 | Official ZIP obtained as the single prespecified field-availability fallback; schema inspected | Not constructed | 0 | Required `HORANASC` also absent; no further substitution or clock imputation |
| Brazil SINASC 2016 | 2,857,800 source rows audited | **2,736,944** | **2,000** | 27 UFs, 54 UF × sex strata; partial coverage within split-time-zone states |
| Mexico INEGI 2015 | 2,353,596 registration-year source rows audited; 1,616,998 births dated 2015 | **1,254,336** | **2,000** | Birth and registration both in 2015; 27 federal entities, 54 entity × sex strata |

“Unavailable” for the early Brazil arm means **unusable for the required
four-system birth inputs**, not that its public archive was unavailable.
Archive URLs, actual HTTP receipts, full hashes and observed headers are in
[1996](audits/brazil1996.download.json), [2001](audits/brazil2001.download.json),
[2016](audits/brazil2016.download.json), and the
[early-arm decision](audits/early_brazil_unavailable.json).
Mexico's [acquisition manifest](mexico/acquisition_manifest.json) records the
actual official DBF ZIP; it was resolved through INEGI's download catalogue.

## Complete exclusion accounting

The following rows are sequential and mutually exclusive within each source.

| Brazil 2016 gate | Excluded records |
|---|---:|
| Missing/invalid required fields | 5,762 |
| Unmatched historical municipality code | 1 |
| Unresolved historical timezone | 114,822 |
| Ambiguous DST fold | 267 |
| Nonexistent DST gap | 4 |
| **Total excluded** | **120,856** |
| **Remaining from 2,857,800 source rows** | **2,736,944** |

Among the 5,762 field failures, invalid/missing clocks occur in 5,221 rows and
invalid/other sex codes in 546; these field categories overlap. Coordinates
reuse official **2022 IBGE municipal-seat reference points**, not observed birth
sites. The inherited conservative mapping resolves only explicitly supported
municipalities in Amazonas and Pará. Historical offsets use tzdb 2026c.
Evidence: [birth audit](audits/brazil2016_audit.json),
[sampling manifest](audits/brazil2016_sampling_manifest.json), and
[reference-source policy](../../../data_expansion/audits/municipality_reference_audit.json).

| Mexico 2015 gate | Excluded records |
|---|---:|
| Birth year not recorded as 2015 in the registration-year file | 736,598 |
| Required date, clock, explicit sex or domestic municipality fields fail | 33,754 |
| Complete fields but no exact 2015 locality-catalog match | 93,960 |
| No approved coordinate/code/name join | 11,352 |
| Unresolved historical timezone | 223,408 |
| Ambiguous DST fold | 135 |
| Nonexistent DST gap | 53 |
| **Total excluded** | **1,099,260** |
| **Remaining from 2,353,596 source rows** | **1,254,336** |

Mexico joins official 2015 locality codes/names to **2020 INEGI locality
reference points**; unchanged geometry and precise birth-site location are not
established. Coahuila, Colima, Chihuahua, Nuevo León and Tamaulipas are excluded
conservatively pending border/island timezone resolution. Historical rules,
including Quintana Roo's 2015 change, are applied to the actual clock labels.
The eligible frame has 131,144 January births but only 20,423 December births:
same-year registration truncation materially limits interpretation.
Evidence: [birth-field audit](mexico/birth_field_audit.json),
[final-frame audit](mexico/frame_audit.json),
[sampling manifest](mexico/sampling_manifest.json), and
[geography/timezone provenance](mexico/geo/README.md).

## What expanded, and what did not

R9 adds a new Brazil birth year and a second national administrative source
country, Mexico. **The overall country-label union remains 32.** This was
recalculated from R8's
[ADB country-stratum audit](../../../data_expansion/audits/adb_z2026_final_audit.json),
[OGDB country audit](../../../data_expansion/audits/ogdb_final_audit.json), and
Brazil: R8 already included 12 Mexican ADB records. Adding the new `BR` and `MX`
frames adds no previously absent country label. A national registry frame is a
substantial improvement in source diversity; a country label alone does not
measure representative coverage.

R8's 3,729 inputs plus R9's 4,000 prepared inputs equal **7,729 source-record
projections across five source frames**. No cross-source identity verification
was added. R8's four possible ADB–OGDB overlaps remain unresolved, and equal
birth tuples are not removed because twins or coincident births may share them.
The earlier Brazil birth-year arm remains unfilled. Global representative
sampling, Chinese 1990s/2000s population coverage and independent death testing
are not established by this expansion.

## Weight and provenance interpretation

Both new samples use the frozen seed `OBS-R9-2026-11-27`, state/entity × explicit
sex strata, the exact allocation in [common.py](common.py), and ascending hashes
of stable source-row IDs. Weights `N_h/n_h` apply only to each eligible source
frame. They do not repair missing clocks, geographic exclusions, registration
truncation, selection into the administrative source, or global population
coverage. Minute fields indicate recorded resolution; their measurement error
remains unknown.

Read-only consistency checks confirmed all three Brazil archive hashes/byte
lengths against download manifests, absence/presence of the required clock
header, agreement between the 2016 archive/audit/sample manifests, selected
input/metadata hashes, row-conservation arithmetic and stratum totals. Mexico's
source-reread and interface checks are recorded
[here](mexico/independent_source_reread.json) and
[here](mexico/input_interface_validation.json). No source inputs, frozen files,
outcome labels or scores were changed while preparing this ledger.
