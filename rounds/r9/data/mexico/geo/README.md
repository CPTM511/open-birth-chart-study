# Mexico 2015 geography support

The national INEGI **ITER2020** ZIP was downloaded from the official source and its geographic schema checked against the official dictionary. The retained fields are ENTIDAD (2), MUN (3), LOC (4), NOM_LOC, LATITUD and LONGITUD. Coordinates are DMS with N/W suffixes, converted to decimal degrees. Both original strings are retained.

The matching rule requires the same nine-digit code and exact locality-name agreement after case/accent/punctuation normalization against the official 2015 birth-data locality catalogue. It retains 7,442 of 8,697 candidate locality codes, covering 1,477,932 candidate birth rows. Another 1,217 codes are absent from ITER2020; 38 codes have different names and are conservatively excluded. No missing coordinate is imputed. No duplicate target locality key or invalid retained coordinate was found.

The 2020 locality point is an explicitly later geographic reference. It is not the exact hospital or residence where a 2015 birth occurred. Matching code/name supports administrative continuity but does not prove unchanged geometry or pinpoint birth location. The source names, reference role, reference year and URL travel with every point.

File `locality2020_refs_for_birth2015.json` provides the public coordinate mapping. The builder also generates an optional CSV copy. `timezone2015_conservative.json` provides the `by_state`/`by_municipality` contract used by the sampler. It resolves 27 states, with a verified 2015 municipality-code exception for Nayarit's Bahía de Banderas (18020). Five states are excluded conservatively pending more detailed historical boundary work: Coahuila, Colima, Chihuahua, Nuevo León and Tamaulipas. This is a study exclusion, not a claim that those states lack legal time zones.

Timezone rules were read from the official **IANA tzdb 2026c** source, preserving the study's software pin. Historical rules must be applied to each local birth timestamp, rejecting folds and gaps. In particular, Quintana Roo changed zone on 1 February 2015. The raw northamerica source and zone table are retained locally with source/archive hashes. The eight used zone identifiers agree with this environment's runtime offsets on 730 midnight/noon checks per zone (5,840 comparisons), and five transition-specific fold/gap cases passed. These validate offsets, not birth-clock truth or administrative assignment.

Before the sampler's DST validation, 1,254,524 candidate rows have both an admitted geographic point and a conservative timezone mapping. Final eligible count and weights are the sampler's responsibility.

## Primary sources

- [INEGI national ITER2020 ZIP](https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_00_cpv2020_csv.zip)
- [INEGI ITER2020 dictionary](https://www.inegi.org.mx/contenidos/programas/ccpv/2020/doc/fd_iter_cpv2020.pdf)
- [IANA 2026c release](https://www.iana.org/time-zones/releases/2026c)
- [IANA source archive](https://data.iana.org/time-zones/releases/tzdata2026c.tar.gz)

## Reproduce reference acquisition and mapping

Run after the birth-only audit in the parent directory's instructions. Python
uses only its standard library; the timezone validation additionally uses an
existing `zic` executable.

```bash
python rounds/r9/data/mexico/geo/acquire_geo_sources.py --out-dir /tmp/r9-mexico/geo-raw
python rounds/r9/data/mexico/geo/build_locality_references.py \
  --candidates /tmp/r9-mexico/private_birth2015_candidates.csv \
  --catalog2015 /tmp/r9-mexico/locality_catalog_2015.json \
  --iter2020-zip /tmp/r9-mexico/geo-raw/iter2020_national.zip \
  --out-dir /tmp/r9-mexico/geo-rebuilt
python rounds/r9/data/mexico/geo/validate_timezone2015.py \
  --raw-dir /tmp/r9-mexico/geo-raw \
  --output /tmp/r9-mexico/geo-rebuilt/timezone2015_validation.json
```

The reference mapping must reproduce SHA-256
`aab6c23c703a9b6146b2ac4612924a8afcaf6f8d163b316bd63acfa534136595`.
The reviewed conservative state/municipality assignment is the versioned
`timezone2015_conservative.json` file, not an automatically inferred polygon map.
The original coordinates/metadata retain INEGI's source terms.
