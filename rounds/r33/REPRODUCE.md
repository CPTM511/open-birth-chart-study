# Reproduce R33

Use the project’s pinned [Python and astronomical dependencies](../../docs/REPRODUCING.md), plus [the round's pinned PyERFA version](requirements.txt). Run commands from the project root. Set `R33_SOURCE_A` and `R33_SOURCE_B` to separate writable directories and `R33_RUN` to an existing output directory. The scripts refuse to overwrite a completed JSON result.

```sh
export PYTHONPATH="$PWD/src"
python -m pip install -r rounds/r33/requirements.txt
python -m rounds.r33.source --job "$R33_SOURCE_A" --fetch --output "$R33_RUN/source_a.json"
python -m rounds.r33.source --job "$R33_SOURCE_B" --fetch --output "$R33_RUN/source_b.json"
python -m rounds.r33.replay --output "$R33_RUN/results.json"
cmp rounds/r33/results.json "$R33_RUN/results.json"
python -m unittest discover -s rounds/r33 -v
```

The acquisition reads the Stellarium versioned JSON and the two NASA ASCII archives before querying the exact Hipparcos identifiers at the CDS VizieR Harvard mirror. It compares 35 HIP identifiers across NASA and CDS on four astrometric fields, using the published decimal digits. The three fixed archive SHA-256 values matched on the two acquisitions. The generated VizieR response includes acquisition metadata. Compare the star identifiers, named decisions, coordinates, proper motions and source URLs if its byte hash changes. The numerical input released with this round has the receipts for the first acquisition. The official sources remain the reference for raw files and terms.

```sh
python - "$R33_RUN/source_a.json" "$R33_RUN/source_b.json" <<'PY'
import json
from pathlib import Path
import sys

def canonical(path):
    data = json.loads(Path(path).read_bytes())
    for receipt in data["sources"].values():
        receipt.pop("sha256")
    return data

reference = canonical("rounds/r33/source_numeric.json")
assert all(canonical(path) == reference for path in sys.argv[1:])
PY
```

**Source map.** The historical star-name transcription uses table 13.1 on printed page 517. Bayer and Flamsteed aliases come from the HEASARC distribution of the Yale Bright Star Catalog. Its HD identifiers join to Hipparcos. Stellarium names and HIP identifiers use the corresponding array positions. The repository holds the numerical subset and its provenance. The source links identify the publishers and catalogues. [Stephenson chapter](https://press.uchicago.edu/books/HOC/HOC_V2_B2/HOC_VOLUME2_Book2_chapter13.pdf) · [Yale catalogue at HEASARC](https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/bsc5p.html) · [Stellarium configuration](https://github.com/Stellarium/stellarium/blob/61b5f160cc1ada854e094717fa4c8189db92bc09/skycultures/chinese/index.json) · [ESA documentation](https://hipparcos-tools.cosmos.esa.int/pstex/sect2_01.pdf) · [Hipparcos at HEASARC](https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/hipparcos.html) · [CDS record and terms](https://vizier.cfa.harvard.edu/viz-bin/VizieR?-source=I/239/hip_main)

**Angular conventions.** Swiss Ephemeris converts the nominal UT instants to TT and provides the Sun. PyERFA applies the IAU 2006 frame-bias and precession rotation to ICRS positions after transport by catalogue proper motion. The star direction is taken in the mean equator and equinox of date. To project the meridian of right ascension `a` onto the ecliptic, the code uses `atan2(sin(a), cos(a) * cos(obliquity))`. R32 uses its original ancient-degree scale and winter origin. Its computed edge offsets are converted back to the absolute tropical ecliptic of date by inverting its solar-label mapping. The independent numerical comparison uses an ERFA spherical position/velocity conversion, direct IAU 1976 precession angles and a vector cross product of the two plane normals. Its proper motion and target instants share the catalogue values and date conventions. Day labels are also recomputed by locating the Sun in sorted right ascensions, including the reversed sections. [ERFA IAU 2006 precession](https://github.com/liberfa/erfa/blob/v2.0.1/src/pmat06.c) · [ERFA IAU 1976 coefficients](https://github.com/liberfa/erfa/blob/v2.0.1/src/prec76.c) · [R32 coordinate bridge](../r32/REPRODUCE.md)

**Reference software and scope.** CPython 3.12.14, PyERFA 2.0.1.5, NumPy 2.3.5 and PySwissEph 2.10.3.2 (Swiss Ephemeris 2.10.03). The release reports numerical agreement and dated input recovery. It uses public star measurements and fixed astronomical sample dates. The R10 reference scores are outside this round’s input.
