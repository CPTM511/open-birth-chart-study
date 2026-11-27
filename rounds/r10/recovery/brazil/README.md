# Reproducing the four Brazilian R10 birth samples

The 2007, 2010, 2020 and 2024 SINASC samples were rebuilt from a fresh copy of each Ministry of Health archive. All four birth-field audits, sample manifests, model inputs and metadata files matched their pre-scoring SHA-256 values. A second parser checked the selected birth fields and UTC offsets for all 8,000 records. Its aggregate output matched the earlier review in every field except the time of the rerun. The public replay receipt gives the source URLs, file hashes, sample sizes and scope. [Replay receipt](replay_receipt.json) · [Earlier independent check](../../verification/brazil_source_inputs_independent.json)

## Acquire the inputs

Run these commands from the repository root with Python 3.11 or later, `curl`, `tar`, `make` and `zic`. Use a fresh private directory. The frozen acquisition script reads the official catalogue and writes a download receipt beside each archive.

```sh
work=private/r10-brazil
mkdir -p "$work/raw" "$work/iana" "$work/zoneinfo"
curl -fsSL 'https://dadosabertos.saude.gov.br/dataset/sistema-de-informacao-sobre-nascidos-vivos-sinasc' -o "$work/raw/catalogue.html"
for year in 2007 2010 2020 2024; do
  python3 rounds/r9/data/brazil_acquire.py --year "$year" --out "$work/raw" --catalogue-file "$work/raw/catalogue.html" || exit 1
done
curl -fsSL 'https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/Localidades_Brasil_gpkg.zip' -o "$work/raw/ibge_localities_2022.zip"
curl -fsSL 'https://data.iana.org/time-zones/releases/tzdata2026c.tar.gz' -o "$work/raw/tzdata2026c.tar.gz"
python3 - "$work/raw" <<'PY'
import hashlib, json, sys
from pathlib import Path

raw = Path(sys.argv[1])
receipt = json.loads(Path("rounds/r10/recovery/brazil/replay_receipt.json").read_text())
expected = {f"brazil{c['birth_year']}.zip": c["archive_sha256"] for c in receipt["cohorts"]}
expected["ibge_localities_2022.zip"] = receipt["sources"]["ibge_archive_sha256"]
expected["tzdata2026c.tar.gz"] = receipt["environment"]["tzdata_archive_sha256"]
for name, digest in expected.items():
    with (raw / name).open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise SystemExit(f"Source archive changed: {name}")
PY
```

Continue after all six archives match. The R8 municipality builder recreates the IBGE municipal-seat reference. The IANA source archive supplies the frozen 2026c rules used by Python's time-zone reader.

```sh
tar -xzf "$work/raw/tzdata2026c.tar.gz" -C "$work/iana"
make -C "$work/iana" -o version tzdata.zi
zic -d "$work/zoneinfo" "$work/iana/main.zi"
cp "$work/iana/tzdata.zi" "$work/zoneinfo/tzdata.zi"
export PYTHONTZPATH="$(cd "$work/zoneinfo" && pwd)"
python3 - "$work" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "data_expansion")
from build_birth_inputs import municipality_references

work = Path(sys.argv[1])
municipality_references(work / "raw", work)
PY
```

## Rebuild and verify

The frozen R10 builder audits each restricted source-year frame before selecting 2,000 records. Each recreated sample manifest must match the public file byte for byte. The manifest binds the source archive, municipality reference, birth-field audit, model inputs and metadata.

```sh
reference="$work/reference/ibge_municipality_reference.json"
for year in 2007 2010 2020 2024; do
  slot="brazil$year"
  if [ "$year" = 2007 ]; then slot=brazil_2000s; fi
  audit="$work/audits/brazil$year.json"
  sample="$work/samples/brazil$year"
  python3 rounds/r10/brazil/build_inputs.py --mode audit --year "$year" --archive "$work/raw/brazil$year.zip" --references "$reference" --audit "$audit" || exit 1
  python3 rounds/r10/brazil/build_inputs.py --mode sample --year "$year" --archive "$work/raw/brazil$year.zip" --references "$reference" --audit "$audit" --slot "$slot" --out "$sample" || exit 1
  cmp "$sample/sampling_manifest.json" "rounds/r10/brazil/audits/brazil${year}_sampling_manifest.json" || exit 1
done
python3 rounds/r10/verification/verify_brazil_source_inputs.py \
  --raw-dir "$work/raw" --samples-dir "$work/samples" --reference "$reference" \
  --tzdata-archive "$work/raw/tzdata2026c.tar.gz" --work-dir "$work/independent" \
  --output "$work/independent/replay.json"
```

The second parser rereads the selected source rows, verifies the local clock, municipality, sex, source-row identity, sample rank and weights, and derives UTC offsets using separately compiled IANA rules. Keep all raw and individual-level files in the private directory. Public releases contain aggregates and checksums. [Source decisions](../../source_decisions.json) · [Verifier](../../verification/verify_brazil_source_inputs.py)
