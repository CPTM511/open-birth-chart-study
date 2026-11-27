# Replaying the Brazil 2006 reference

The R10 protocol pins the SHA-256 of the **entire R8 baseline file**. Its 3,729 profiles cover 1,388 OGDB records, 2,000 Brazil 2006 records and 341 Astro-Databank Z records, in that order. The cross-cohort comparison uses the 2,000 Brazil records from that file. [R10 protocol](../../protocol.json) · [Original R8 release instructions](../../../../docs/REPRODUCING.md)

The replay downloaded the four publisher archives, checked their frozen digests and reconstructed the three samples with tzdb 2026c. All six input and metadata digests matched their original values. Both platforms completed all 3,729 profiles using the unchanged R8 runner with four workers. The Linux result reproduced the original bytes. [Aggregate replay receipt](replay_receipt.json) · [Frozen R8 digest](../../../../results/run_integrity.json)

| Runtime | Complete baseline SHA-256 | Published Swiss longitude values matched exactly |
|---|---|---:|
| macOS arm64, Clang | `a487230ccce5d3e31a633b2a6227fc78b07e524b5ab3702b14ab6c81c769a949` | 0 of 50 |
| Linux x86_64, glibc 2.36, GCC | `5bdc0d2e5c53cb15928a4a0781e5c7785085d3d039cfbf7dcc9b44f2a3f1c401` | 50 of 50 |

The largest longitude difference on macOS was 9.43 × 10⁻¹⁰ degrees. That run illustrates why the release checks the full serialized file. The Linux check also reproduced all 4,334 numeric fields, the other values and the structure of the two published synthetic examples, including their detailed monthly outputs. [Public longitude cases](../../../../docs/engine_validation/astronomy_comparison.json) · [Synthetic chart examples](../../../../docs/engine_validation/synthetic_full_chart_examples.json)

## Reproduce the numeric environment

Use the official `linux/amd64` Python 3.12.14 Bookworm image selected by the immutable multi-platform index below. Inside it, use pip 26.2.2, setuptools 84.2.1 and wheel 0.48.0, then install the repository's pinned `requirements.txt`. The `pyswisseph==2.10.3.2` source release compiled with the image's default GCC settings. Use the official Node 24.22.3 Linux x64 archive and run `npm ci --ignore-scripts` with the frozen lockfile. The tested host was Apple arm64 running this Linux x86_64 userspace locally through Rosetta. [Pinned versions](../../../../docs/reproduction_environment.json)

```text
docker.io/library/python@sha256:dbbe4ceb97851e2e5fa83798b239811f871cb743b259ba3563737349f6bcfaa0
node-v24.22.3-linux-x64.tar.xz  SHA-256  4f2b175a6d53a5c617a80dba2676238a0688cef28c6da4eba35c7d844e66fcfb
```

Follow sections 3–5 of the R8 instructions to reconstruct the inputs and keep the source order. After the baseline completes, hash `baseline_profiles.jsonl` and compare it with the value in the R10 protocol. The recorded replay additionally checked each study ID, source, input key, forty completed-age years and all 596,640 four-system scores against the expected structure and range. Individual inputs and profiles remain private. [R8 reconstruction and scoring](../../../../docs/REPRODUCING.md)
