# Reproduce the Colombian hospital birth archive comparison

Run from the repository root. Use the [pinned R10 scoring environment](../../docs/REPRODUCING.md) and two distinct access-restricted directories outside the checkout. The released output was generated with the [Linux x86-64 runtime](../r10/recovery/reference/README.md) that matches the R10 calibration. The registered archive versions are defined in [sources.json](sources.json). The reference contains the same 2,000 frozen Brazil 2006 trajectories, original record weights and age-band calibration used by R10.

Set `R30_CSV` and `R30_JSON` to fresh directories. Set `R10_JOB` to the private R10 directory containing `reference/brazil2006/` and `reference/full-frozen-r8-baseline_profiles.jsonl`. For a fresh reference, follow the [frozen R10 source recovery and byte checks](../r10/recovery/README.md). Ensure the pipeline uses the local Python source and installed Node dependencies.

```sh
umask 077
export PYTHONPATH="$PWD/src"
export OBS_NODE_MODULES="$PWD/node_modules"
python -m rounds.r30.source --format csv --job "$R30_CSV"
python -m rounds.r30.source --format json --job "$R30_JSON"
python -m rounds.r30.study --job "$R30_CSV" --jobs 2 --frozen-only
python -m rounds.r30.study --job "$R30_JSON" --jobs 2 --frozen-only
python -m rounds.r30.study --job "$R30_CSV" --jobs 2 --finish-year-expansion
python -m rounds.r30.study --job "$R30_JSON" --jobs 2 --finish-year-expansion
python -m rounds.r30.compare --job "$R30_CSV" --replay-job "$R30_JSON" \
  --r10-job "$R10_JOB" --output "$R30_CSV/results.json"
```

Both downloads use the official portal with a server-side field list and sort by its internal row order. Only the listed values reach the research directory. The two transport formats are reconciled as UTF-8 JSON Lines with empty fields and fixed field order. The program checks the publisher's revision and license before and after acquisition. Compare the projected hashes with [the release receipt](results.json). The recorded retrieval time will vary. An authorised custodian can use the sealed, access-restricted projections when an exact original portal version is unavailable.

The scorer uses the calendar date as the birth date and the time component of the separate clock field. It rejects clocks whose legacy day marker has rolled to a different day. It verifies the registered UTC−05:00 offset for all records. For the paired branch it applies nearest-hour rounding to the civil time, shifts the corresponding UTC instant, and retains the original R10 July 1 age-year convention. A source time already at an hour is evaluated once and contributes to both branches.

The first two runs with the frozen engine in this release stopped at the first unsupported 2026 birth. The completed earlier trajectories were preserved and validated before reuse. The amended second phase creates a separate, hash-verified engine directory for each run and admits 2026 births by changing three date validation rules only. It also checks a designated earlier birth per site-year against the original engine. Full fresh runs can use the commands above with an explicitly in-range first phase. The separate integer-weight calculation reconstructs threshold decisions, exact rates, joint transitions and the month-removal range using the same scoring outputs. [Date range amendment](DATE_RANGE_AMENDMENT.zh.md)

Source attribution is to E.S.E. Hospital Regional de Duitama, Boyacá for `cv8g-j7c4`, and E.S.E. Hospital Pío XII de Colón, Putumayo for `qa7n-i2xc`, via Colombia's Ministry of ICT open data portal. Both source metadata records specify CC BY-SA 4.0. The reports publish aggregate calculations and source receipts. The projected birth inputs and individual score trajectories stay in restricted local custody. [Duitama metadata](https://www.datos.gov.co/api/views/cv8g-j7c4.json) · [Colón metadata](https://www.datos.gov.co/api/views/qa7n-i2xc.json) · [License](https://creativecommons.org/licenses/by-sa/4.0/)
