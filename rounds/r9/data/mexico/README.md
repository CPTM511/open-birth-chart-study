# R9 Mexico 2015: actual public acquisition and birth-only audit

## Verified acquisition

The official INEGI national natality ZIP was downloaded successfully without an
account or payment. It is a **registration-year 2015** file, not the complete
cohort of all births occurring in 2015.

- Publication: <https://www.inegi.org.mx/programas/natalidad/>
- Metadata: <https://www.inegi.org.mx/rnm/index.php/catalog/246>
- Official birth-variable dictionary: <https://www.inegi.org.mx/rnm/index.php/catalog/246/data-dictionary/F10>
- Archive: <https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/2015/natalidad_base_datos_2015_dbf.zip>
- Bytes: `39143088`.
- SHA-256: `995c451db513f19641c1e28032d0164e3e5a2c5a0b210b49e0754fde15f4f6c7`.
- Server last-modified: `Thu, 25 Sep 2025 12:00:51 GMT`.
- Contents: `NACIM15.dbf` (2,353,596 physical records), `CATEMLNA15.dbf`
  (46,089 locality/state/municipality catalog records), and the official PDF dictionary.

The file URL was resolved from the official program HTML, its
`data/pestana/pestanadata.js`, the declared `descargaMasivaV2.min.js`, and the
official catalogue API with `idBiinegi=2066`, `tipodocto=4`. The website's own
link rule is `/contenidos` + `pathLogico` + the format suffix. The API returned
all years despite `anio=2015`; the 2015 entry was selected by exact title.
Its current open-CSV catalogue starts at 2017; older years are offered as DBF.
R8's failed older CSV URL probes therefore did not establish absence of data.

`acquisition_manifest.json` preserves the exact official catalogue item,
response metadata, ZIP members, byte count and hash. The catalogue and webpage
snapshots are retained locally for provenance.

## Completed whole-file audit

| Quantity | Records |
|---|---:|
| Physical/active source records | 2,353,596 |
| Actual birth year 2015 | 1,616,998 |
| Actual 2015 with valid date | 1,616,988 |
| Actual 2015 with valid hour and minute | 1,584,929 |
| Actual 2015 with explicit male/female source sex | 1,616,989 |
| Actual 2015 with domestic occurrence state | 1,615,499 |
| Actual 2015 complete date/time/sex/domestic municipality | 1,583,244 |
| Above, also exact match to the 2015 locality catalogue | 1,489,284 |

The last row is a **candidate frame before coordinates and historical time-zone
validation**. It contains 8,697 distinct source locality codes. The completed
geography/time-zone gate below reduces this to the final eligible frame.

The 2015 target records contain 32,069 invalid/unspecified clocks. The source
dictionary uses `99` for unspecified hour/minute and `9` for unspecified sex.
Among 1,584,929 valid target clocks, 777,304 (49.0435%) have a minute divisible
by five and 137,306 have minute zero. A recorded minute is display precision,
not a certified uncertainty interval. Actual source fields include `MES_NACIM`
and `LOCAL_RESI`, so metadata names were not blindly assumed to match the DBF.
The locality catalogue declares DBF codepage 0x02 (CP850); the birth file declares
0x03 (CP1252). Birth numeric codes are projected explicitly.

## Material selection boundary

All source registration years are 2015, but only 68.7033% of records have birth
year 2015. Restricting to births occurring and registered in 2015 creates strong
within-year registration truncation: the current candidate frame contains
154,209 January births and 27,423 December births. Registry delays among valid
target dates range from 0 to 362 days. This is an incomplete same-year registered
birth frame, **not a complete Mexican 2015 birth cohort**. Its sampling weights
cannot recover unregistered, later-registered, missing-clock or excluded-location
births. The R9 protocol fixes this frame; no later registration file is silently
added after the freeze.

`audit_mexico2015.py` projects only birth date, birth time, recorded sex,
occurrence geography, and registration date. It does not project or inspect
death/survival, medical, parental, occupation or other outcome fields. Physical
DBF ordinals define stable source IDs; equal birth tuples are not silently
deduplicated because twins and coincident births can share them.

## Completed geography, historical-time and sampling gates

The official national INEGI ITER2020 archive supplies locality reference points.
The join requires both the same 9-digit locality code and the same normalized
locality name as the official 2015 catalogue. This gives 7,442 reference points
covering 1,477,932 candidate rows. A 2020 locality point is an approximation to
the 2015 locality, not a hospital coordinate or an observed birthplace point.
Its numeric decimal precision does not establish geographic accuracy.

Historical offsets use IANA tzdb 2026c. The conservative mapping excludes entire
states 05 (Coahuila), 06 (Colima), 08 (Chihuahua), 19 (Nuevo León), and 28
(Tamaulipas) where this round did not resolve all border or island exceptions.
Nayarit's municipality 18020 uses `America/Bahia_Banderas`; the remainder uses
`America/Mazatlan`. Quintana Roo uses `America/Cancun`, including its February
2015 change. The final sample covers 27 states; it is not nationally complete.

| Sequential gate | Excluded rows |
|---|---:|
| No approved coordinate/code/name join | 11,352 |
| Unresolved historical zone in the approved geographic frame | 223,408 |
| Nonexistent local civil time at a clock-change gap | 53 |
| Ambiguous local civil time at a clock-change fold | 135 |
| **Remaining eligible rows** | **1,254,336** |

The frozen `OBS-R9-2026-11-27` procedure selects **2,000 records in 54 state ×
sex strata**, using the shared `../common.py` exact-fraction allocation and
ascending SHA-256 ranks of the stable source ID. Weights sum to 1,254,336 and
apply only to this restricted eligible source frame. They do not adjust for
registration timing, excluded states, missing source fields, or global coverage.

The existing R8 `load_source` interface accepted all 2,000 inputs, checked
metadata parity, unique IDs, hashes, sex, clocks, coordinates, weights and strata.
A separate reread of the pinned original DBF checked eight properties for each
selected record: **16,000 comparisons, zero mismatches**. All 2,000 chart input
keys are distinct, which does not establish identity-level independence.

- Model input SHA-256: `47289b74bf639325bffb5e355f1493a698a8bb91cc95e7c5d3a643a7ce596794`.
- Metadata SHA-256: `86a50efdd6db66fd4445be8903c2e19b77a32c1577df7e024db1f202c4999705`.
- Sample clock heaping: 993/2,000 minutes divisible by five; 192/2,000 at minute zero.
- All coordinate references are dated 2020; all birth inputs are dated 2015.
- This data-preparation stage performed no chart scoring or outcome testing.

`sampling_manifest.json`, `frame_audit.json`, `independent_source_reread.json`,
and `input_interface_validation.json` are public aggregate evidence. The birth
inputs and metadata remain local. See `geo/` for official coordinate source
links, source hashes, the deterministic crosswalk, and the historical-zone
mapping/validation.

## Reproduce

Run from the repository root with Python 3.11 or newer. Choose a private work
directory outside the repository, represented below as `/tmp/r9-mexico`.

```bash
python rounds/r9/data/mexico/download_mexico2015.py --output-dir /tmp/r9-mexico
python rounds/r9/data/mexico/audit_mexico2015.py \
  --archive /tmp/r9-mexico/natalidad_base_datos_2015_dbf.zip \
  --output-dir /tmp/r9-mexico
python rounds/r9/data/mexico/sample_mexico2015.py \
  --candidates /tmp/r9-mexico/private_birth2015_candidates.csv \
  --geo rounds/r9/data/mexico/geo/locality2020_refs_for_birth2015.json \
  --zones rounds/r9/data/mexico/geo/timezone2015_conservative.json \
  --output-dir /tmp/r9-mexico/sample
python rounds/r9/data/mexico/verify_selected.py \
  --archive /tmp/r9-mexico/natalidad_base_datos_2015_dbf.zip \
  --sample-dir /tmp/r9-mexico/sample
PYTHONPATH=src python -c 'from open_birth_chart.io import load_source; rows, manifest = load_source("/tmp/r9-mexico/sample"); print(len(rows), manifest["model_input_sha256"])'
```

The downloader verifies the pinned cache before reusing it. A changed upstream
file stops reconstruction instead of silently replacing the scientific inputs.
The audit streams the compressed DBF and writes a private birth-only candidate
CSV plus aggregate audit JSON. No astronomical or astrological calculation is
performed by these scripts.

Use IANA tzdb 2026c for an exact runtime-version match. The sampler records the
runtime timezone database and all input/code hashes. It refuses to overwrite an
existing nonempty sample directory. The pinned coordinate map is public because
it contains only locality reference points and official geographic labels; the
private birth candidate file is never needed as a public repository attachment.

## Publication boundary

Publish source links, scripts, aggregate audits, sampling metadata without
individual entries, and the resulting model limitations. Keep the ZIP, private
candidate CSV, selected individual inputs/metadata and full per-record output
local. This stage does not provide global representative sampling, death
validation, or evidence about AI-caused civilizational change.
