# Requirements and portable paths

These four acquisition/projection/audit scripts require **Python 3.10 or later**
with its standard-library `sqlite3`, `zipfile`, `csv`, `xml.etree.ElementTree`
and `zoneinfo` modules. No astrological engine, database server, pandas, NumPy,
external shell executable or paid service is required for birth-data preparation.
`requirements.txt` intentionally has no mandatory PyPI dependency.

## Time-zone database

The frozen Brazil cohort was reconstructed using **IANA tzdb 2026c**. Python
`zoneinfo` searches the system time-zone paths, then the optional `tzdata` Python
package. The builder detects the version from those paths or from
`tzdata.IANA_VERSION`; it does not assume a Linux installation directory.

On a host without system time-zone files, install the optional `tzdata` package.
For exact reference reproduction, choose a release whose
`tzdata.IANA_VERSION` is `2026c`. A different IANA version is recorded as such;
do not call a different-version run an exact environment reproduction merely
because its birth-input hashes happen to agree. A custom IANA installation can
be selected using Python's documented `PYTHONTZPATH` environment variable.

From the repository root, inspect the detected version with:

```bash
python -c "import sys; sys.path.insert(0, 'data_expansion'); from build_birth_inputs import timezone_database_version; print(timezone_database_version())"
```

The OGDB and ADB projections preserve/check source offsets and do not calculate
their birth UTC instants from IANA zones. Their input hashes can be reproduced
without using Brazil's historical-zone conversion.

## Storage and command-line directories

All defaults are derived from the script location, not a user's home, scratch
folder or a fixed temporary path:

- Downloaded archives: `data_expansion/data/cache/`
- Locally reconstructed records: `data_expansion/data/reconstructed/`
- Download manifests: `<selected cache>/download_manifests/`
- Audit output: `<selected reconstruction directory>/audits/`

The module's `.gitignore` excludes the entire local `data/` directory. Raw
archives and the private SINASC/ADB individual projections must stay out of a
public commit. The provided minimal OGDB derivative has its own CC BY-SA 4.0
attribution in `DATA_LICENSES.md`.

Every script accepts directory overrides. `build_birth_inputs.py` and
`build_adb_reference.py` take `--raw-dir`/`--input-dir` and
`--output`/`--output-dir`. The downloader takes `--raw-dir`/`--output-dir` and
`--manifests`. The auditor takes `--input-dir`, `--output-dir` and `--raw-dir`;
its old `--output` option remains an alias for the input reconstruction root.

The four required compressed source archives total approximately 88.8 MB. The
IBGE GeoPackage adds approximately 23.4 MB when extracted. The 491 MB national
Brazil CSV is streamed inside its ZIP rather than written out. Allow additional
space for generated metadata and local model outputs.
