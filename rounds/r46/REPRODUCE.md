# Reproduce the R46 independent holdout

Use a full checkout containing the preregistration commit and [input commitments](seals). Use the R10 frozen [Linux and Node environment](../r10/recovery/reference/README.md) to score. Archive and reference hashes are in the group receipts. Run on birth-only inputs inside a restricted directory outside the checkout.

## Sources

1. Resolve R10, R15, and R45 private input roots from their reconstruction instructions. The prior samples are used to identify excluded physical source rows. Use the pinned IBGE municipal coordinates and IANA 2026c. [R10](../r10/independent_replay/REGISTRATION.md) · [R15](../r15/REGISTRATION.zh.md) · [R45](../r45/REPRODUCE.md)
2. Obtain the two SINASC CSV ZIPs and the 2009–2010 INEGI DBF archives, 2020 national locality archive and 32 municipal-seat snapshots. Their respective [R15](../r15/source_audit.json), [R45](../r45/SOURCE_SEALS.json) and [R10](../r10/recovery/mexico2009/README.md) receipts give the exact sources.
3. Download all five INEGI 2017–2021 archives using the URLs in [the Mexico 1999 receipt](seals/mx1999.json) into one directory, by the publisher filenames. Keep the original bytes. The 2017 download's embedded field dictionary on PDF page 15 lists the birth month as Mes_nac. The actual DBF uses MES_NACIM. The adapter renames just that one descriptor in a temporary copy, leaving physical offsets and values intact.

~~~sh
umask 077
mkdir "$R46_RUN"
export PYTHONPATH="$PWD/src" PYTHONTZPATH="$IANA_2026C"
export OBS_NODE_MODULES="$PWD/node_modules"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python - "$R46_RUN/mex_index.json" <<'PY'
import json
from pathlib import Path
import sys
rows = json.loads(Path("rounds/r46/seals/mx1999.json").read_bytes())["archives"]
fields = ("year", "url", "sha256", "archive_bytes", "included", "missing_fields_or_tables",
          "normalized_publisher_alias", "official_birth_month_description_page",
          "official_dictionary_embedded_pdf_sha256")
with Path(sys.argv[1]).open("x", encoding="utf-8") as f:
    json.dump([{k:r[k] for k in fields if k in r} for r in rows], f, ensure_ascii=False, indent=2)
    f.write("\n")
PY

python -m rounds.r46.prepare br1999 --job "$R46_RUN" --r15-job "$R15_RUN" \
  --brazil-archive "$SINASC_1999" --references "$IBGE_2022"
python -m rounds.r46.prepare br2009 --job "$R46_RUN" --r45-job "$R45_RUN" \
  --brazil-archive "$SINASC_2009" --references "$IBGE_2022"
python -m rounds.r46.prepare mx1999 --job "$R46_RUN" --mex-modern "$INEGI_2017_21" \
  --mex-index "$R46_RUN/mex_index.json" --iter "$INEGI_ITER"
python -m rounds.r46.prepare mx2009 --job "$R46_RUN" --r45-job "$R45_RUN" --r10-job "$R10_RUN" \
  --mex-old "$INEGI_ORIGINAL_DBF" --seats "$INEGI_SEATS" --iter "$INEGI_ITER"
~~~

An additional source-index record confirms that the 2002 and 2003 DBF releases contain many 1999 births while both omit the hour and minute columns. Those downloads were screened for birth year and documented fields only. [Source check](early_mexico_schema.json)

## Score, check, and aggregate

~~~sh
python -m rounds.r46.score --mode full --job "$R46_RUN" --groups br1999 mx1999 br2009 mx2009
python -m rounds.r46.score --mode audit --job "$R46_RUN" --groups br1999 mx1999 br2009 mx2009
python -m rounds.r46.analyze --job "$R46_RUN" --r10-job "$R10_RUN" --output "$R46_RUN/results.json"
python -m rounds.r46.review --job "$R46_RUN" --r10-job "$R10_RUN" \
  --results "$R46_RUN/results.json" --output "$R46_RUN/review.json"
~~~

Re-running the score command verifies and skips complete batches. Use a fresh score directory or duplicated run folder to force full re-execution. Audit mode selects the registered records by digest and creates separate batches in fresh worker processes. The analysis checks every scored record, score range, year index and input identifier against its sealed batch receipts. The review uses separate prefix-rank arithmetic, rational window means, covariance and replayed multipliers. Fields in results are proportions, with conversion to percentage points by multiplying by 100.
