#!/usr/bin/env python3
"""Fetch the exact public archives used for R8, with pinned SHA-256 checks.

No accounts, application, payment, scraping bypass, or outcome queries are used.
Do not commit downloaded archives or SINASC/ADB row-level records. See DATA_LICENSES
for the separately attributed CC BY-SA 4.0 minimal OGDB derivative.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

MODULE_ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE = MODULE_ROOT / "data" / "cache"

SOURCES = [
    {
        "name": "adb_z_sample.zip", "role": "reused_alphabetical_reference_birth_frame",
        "url": "https://www.astro.com/adbexport/z_sample.zip",
        "bytes": 232904,
        "sha256": "f3b9a93eae4bf27588d2e4c0f81cfd47f1b8aad009f7c469843e2974fa371edc",
        "publication_page": "https://www.astro.com/adbexport/",
    },
    {
        "name": "brazil2006.zip", "role": "birth_record_frame",
        "url": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINASC/csv/DNBR2006_csv.zip",
        "bytes": 54305352,
        "sha256": "4089f12103eb7af2840b39f0d5a6c4ac5aafcd46bf3cf9cd77964865ceffdd65",
        "publication_page": "https://dadosabertos.saude.gov.br/dataset/sistema-de-informacao-sobre-nascidos-vivos-sinasc",
    },
    {
        "name": "ogdb_pg_dump.zip", "role": "birth_record_frame",
        "url": "https://opengauquelin.org/download/ogdb-pg-dump.zip",
        "bytes": 27780946,
        "sha256": "b9a90c6bfc5856a05305360e8faa7d67ca71f001a9ae5ab4efd79df81dc0d01c",
        "publication_page": "https://opengauquelin.org/downloads2",
    },
    {
        "name": "ibge_localities_2022.zip", "role": "municipal_seat_reference_coordinates",
        "url": "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/Localidades_Brasil_gpkg.zip",
        "bytes": 6477540,
        "sha256": "1d96d5f0b379972a506d4b18c3696af974fbe59f8f6680557cb3a6dd38a0eb57",
        "publication_page": "https://www.ibge.gov.br/estatisticas/sociais/saude/22827-censo-demografico-2022.html?edicao=45203",
    },
]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", "--output-dir", type=Path, default=DEFAULT_CACHE,
                        help="Archive download/cache directory (default: data_expansion/data/cache)")
    parser.add_argument("--manifests", type=Path,
                        help="Download manifest directory (default: <raw-dir>/download_manifests)")
    args = parser.parse_args()
    if args.manifests is None:
        args.manifests = args.raw_dir / "download_manifests"
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    args.manifests.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        dest = args.raw_dir / source["name"]
        if dest.exists():
            if dest.stat().st_size != source["bytes"] or digest(dest) != source["sha256"]:
                raise RuntimeError(f"Existing file differs from frozen snapshot: {dest}")
            print(json.dumps({"file": str(dest), "status": "verified_existing_snapshot"}), flush=True)
            continue
        temp = dest.with_suffix(dest.suffix + ".part")
        request = urllib.request.Request(source["url"], headers={"User-Agent": "OBS-R8-public-research/1.0"})
        size = 0
        h = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=60) as response, temp.open("wb") as f:
            if response.status != 200:
                raise RuntimeError(f"Unexpected status {response.status}")
            headers = dict(response.headers)
            while block := response.read(1 << 20):
                size += len(block)
                if size > source["bytes"] + (1 << 20):
                    raise RuntimeError("Source grew beyond frozen snapshot; refusing unbounded download")
                h.update(block)
                f.write(block)
        observed = h.hexdigest()
        manifest = dict(source, retrieved_utc=datetime.now(timezone.utc).isoformat(),
                        observed_bytes=size, observed_sha256=observed, headers=headers)
        (args.manifests / (source["name"] + ".json")).write_text(json.dumps(manifest, indent=2) + "\n")
        if size != source["bytes"] or observed != source["sha256"]:
            raise RuntimeError("Public file has changed since R8. Preserve the new hash, do not silently overwrite the frozen cohort.")
        temp.replace(dest)
        print(json.dumps({"file": str(dest), "status": "downloaded_verified", "bytes": size}), flush=True)


if __name__ == "__main__":
    main()
