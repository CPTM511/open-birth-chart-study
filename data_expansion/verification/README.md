# Public-script integration verification

The public copies of all four data-preparation scripts were run using the
already downloaded, hash-pinned source cache. No archive was downloaded again.
OGDB and ADB were reconstructed into a newly created directory outside the
repository. Their complete model-input files matched the frozen research
inputs byte for byte:

| Source | Rebuilt records | SHA-256 of rebuilt and frozen input |
|---|---:|---|
| OGDB | 1,388 | `76b78ec7e494c2bccc13922e782631071147519894c64cf691d09b0005e1c2cf` |
| ADB | 341 | `b2db70b22414ad12d8d6d4a7dee6d2bcd79cc5d2fbeb88b713bcf954cd029061` |

The verification also checked record and source-ID uniqueness, stratum counts,
sample-weight totals, input/metadata agreement, valid coordinates, recorded
M/F and local/UTC/offset consistency. The machine-readable result and the exact
public script hashes are in `fresh_rebuild_validation.json`.

The national Brazil file was not rescanned during this integration step. The
earlier validation independently reread all 2,000 selected Brazil records from
the pinned original ZIP and matched dates, clocks, sex, municipality codes,
source counters and physical row ordinals. That evidence remains in
`../audits/sample_integrity_validation.json`. The frozen Brazil input hash is
`3d9a2dc48a26a083a20abbd372310310d13b6e93d880a4f8d1fafa02f8914f6d`.
All three original frozen input files remained unchanged.

## Portable command interface

From the repository root, the normal complete preparation is:

```bash
python data_expansion/download_sources.py
python data_expansion/build_birth_inputs.py --max-n 2000
python data_expansion/build_adb_reference.py
python data_expansion/audit_birth_inputs.py --verify-brazil-source
```

For an existing cache, use `--raw-dir CACHE_DIRECTORY`. For a fresh reconstruction,
add `--output-dir NEW_OUTPUT_DIRECTORY` to the builders and point the auditor's
`--input-dir` to the same directory. `build_birth_inputs.py --source ogdb`
reconstructs only OGDB; the ADB builder is separate. The auditor can write its
report to a separate directory with `--output-dir REPORT_DIRECTORY`.

The scripts contain no user-specific scratch or temporary directory. The
default cache and generated output locations are derived from the module
directory and ignored by Git. See `../REQUIREMENTS.md` for Python and IANA
time-zone requirements.

## Public-data boundary check

The only row-level JSONL files in this public module are
`ogdb_birth_inputs.jsonl` and `ogdb_source_index.jsonl`, attributed under
CC BY-SA 4.0. No original ZIP, GeoPackage, XML, SINASC/ADB individual birth input
or individual prediction/outcome file was copied into the repository module.
