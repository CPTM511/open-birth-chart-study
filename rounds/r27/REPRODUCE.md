# Reproducing the Amsterdam 1901 comparison

Use the repository root, Python 3.12, the [pinned Python and Node dependencies](../../docs/REPRODUCING.md), and a fresh, access-restricted directory outside this checkout. The [registered source](REGISTRATION.zh.md) is Stadsarchief Amsterdam fonds 5009, volumes 4686–4699. The archive provides images through IIIF. All four systems use the frozen R10 scoring files. Raw scans, transcription and individual trajectories stay in the custodian's local private research storage. Aggregate results, source locations and file hashes are public. [Archive catalogue](https://id.archief.amsterdam/80ae8641-6dbd-40ae-e053-b784100ad8d3) · [Archive reuse conditions](https://beta.archief.amsterdam/gebruik/application-programming-interface)

## Obtain and check the sources

Set `R27_JOB` and `R27_RECHECK` to two new directories outside the checkout. Set `R10_JOB` to the preserved private R10 directory. Its `reference/brazil2006/` contains the frozen sample and its `reference/full-frozen-r8-baseline_profiles.jsonl` contains the complete frozen R8 baseline profile file. The scorer takes the same 2,000 Brazil 2006 profiles through the registered weighted reference. The analyzer checks the reference folders against the [R10 registration hashes](../r10/independent_replay/registration.json). If those files need recovery, use the [R8 source and baseline instructions](../../docs/REPRODUCING.md) and the [R10 reference check](../r10/recovery/README.md).

```sh
umask 077
export OBS_NODE_MODULES="$PWD/node_modules"
python -m rounds.r27.archive_source --job "$R27_JOB" --output "$R27_JOB/source_receipt.json"
python -m rounds.r27.archive_source --job "$R27_RECHECK" --output "$R27_RECHECK/source_receipt.json"
python - "$R27_JOB/source_receipt.json" "$R27_RECHECK/source_receipt.json" rounds/r27/source_receipt.json <<'PY'
import json
import sys
from pathlib import Path

receipts = [json.loads(Path(path).read_text()) for path in sys.argv[1:]]
for receipt in receipts:
    receipt.pop("receipt_created_utc")
if not (receipts[0] == receipts[1] == receipts[2]):
    raise SystemExit("Archive frame or selected image bytes differ from the R27 release.")
PY
```

A matching receipt verifies the selected full image byte hashes and the ordered canvas metadata for every volume. The public [source receipt](source_receipt.json) also gives the direct archive image URI for each selected scan. After matching, use the published source receipt in the private scoring directory when reproducing the exact source receipt hash.

## Transcribe, score and check

Make `read-a.txt`, `read-b.txt` and `adjudicated.txt` in the private job directory. A line begins with the sampled image stem, such as `4686-003`, followed by space-separated entries. Leave just the stem on a blank scan. In A and the adjudicated file, list all document starts from top to bottom on the left and then top to bottom on the right. In B, read the same image in reverse document order. Enter each qualifying act as `ACT:MMDD:HHMM:M` or `ACT:MMDD:HHMM:F`. Excluded acts use a single reason after the number (`ack`, `year`, `place`, `unreadable` or `repeat`). Take the birth date and the AM, PM, or noon marker from the statement of actual birth. Use the filing date only to interpret date expressions such as `heden` and `dezer`. A marginal acknowledgement attached to an original ordinary birth act is distinct from an acknowledgement-only act. Adjudicate differences against the handwritten scan before scoring, retaining the two original readings. Compare counts and aggregates from a new independent transcription even when its text serialization differs from the private file hashes.

```sh
python -m rounds.r27.study --job "$R27_JOB" --jobs 4
python -m rounds.r27.analyze --job "$R27_JOB" --r10-job "$R10_JOB" --output "$R27_JOB/results.json"
python -m rounds.r27.verify --job "$R27_JOB" --r10-job "$R10_JOB" --results "$R27_JOB/results.json" --output "$R27_JOB/review.json"
```

Use new output paths for reruns. To check the scoring files byte for byte, use the published receipt and the same three transcription files in the second private directory, with the images obtained separately. Run the scorer there with the same environment. Add `--replay-job "$R27_RECHECK"` to the verifier to compare both scoring outputs.

The [study adapter](study.py) computes the historical local-to-UTC conversion to the second. It treats the recorded civil time as an input on an hourly grid, keeps location at the city reference point, and passes original and ±30-minute times through all four engines. By the R10 convention each year's age is the completed age on July 1. The [estimator](analyze.py) divides the expansion-weighted total of qualifying years by the expansion-weighted total of modeled years. The first-order variance is derived from the within-volume sample variance of each scan's hit total minus the estimated rate times its year total, with the finite-population correction. The [separate verifier](verify.py) classifies scores against integer-weight reference tables and reconstructs the primary interval through scan-pair squared differences. The same transcriptions and engine outputs are shared in that check.
