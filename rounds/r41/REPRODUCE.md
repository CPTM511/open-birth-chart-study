# Reproduce R41

The [registration](REGISTRATION.zh.md) fixes the two historical date panels, all 60 integer minutes, the fixed location and sex parameters, the fixed comparison cohort, and the weighting rules. [The execution note](EXECUTION_CHANGE.zh.md) records the exact reuse of annual Ziwei calls with identical effective inputs. The other three workflows always run for each specified input.

## Acquire weights and verify the public result

Run from the repository root after installing the [pinned dependencies](../../docs/REPRODUCING.md). Use separate directories for the two government downloads.

```sh
export PYTHONPATH="$PWD/src"
python -m rounds.r34.source "$R41_SOURCES_A"
python -m rounds.r34.source "$R41_SOURCES_B"
python -m unittest discover -s rounds/r41 -v
python -m rounds.r41.check_release "$R41_SOURCES_A"
```

The compressed CSV has one row for every registered date and hour. Its first columns give the date, hour and official birth count. Each succeeding column is the joint-high age mask for one integer minute and F/M parameter. Every unsigned mask is a ten-character hexadecimal integer. Bit 0 is age 20, increasing to bit 39 for age 59, and a set bit means at least three systems reached their corresponding frozen threshold. The separately implemented verifier uses these masks and public official counts to recompute the results with rational weights.

## Recompute model scores and the fixed calibration

Use the [frozen R10 Linux x86-64 setup](../r10/recovery/reference/README.md), including Node 24.22.3 and `iztro==2.6.5`. Set `OBS_NODE_MODULES` to the installed Node modules and `R10_JOB` to the private R10 replay root. The scorer requires directories outside the checkout with user-only permissions. Daily files are checked and resumed independently.

First compare a full day per year with and without reuse. These direct calculations become the first days of the complete score arrays. Then complete the two years and score all verification probes through the direct entry point.

```sh
umask 077
export PYTHONPATH="$PWD/src"
for year in 1999 2006; do
  first_day=$(python -c "from rounds.r41.profiles import study_dates; print(study_dates($year)[0])")
  python -m rounds.r41.profiles "$R41_SCORES/main-$year" --year "$year" --last-date "$first_day"
  python -m rounds.r41.run_cached "$R41_SCORES/cache-validation-$year" --year "$year" --last-date "$first_day"
  python -m rounds.r41.run_cached "$R41_SCORES/main-$year" --year "$year"
  python -m rounds.r41.profiles "$R41_SCORES/probe-$year" --year "$year" --probe
done
```

Aggregate after all four verification steps have produced their registered coverage. The analyzer checks the frozen reference files and weights, every system-year threshold decision with two ranking implementations, the complete first-date comparisons, all probe scores, source totals and the earlier R34 band counts.

```sh
python -m rounds.r41.analyze \
  --source-first "$R41_SOURCES_A" --source-second "$R41_SOURCES_B" \
  --scoring-root "$R41_SCORES" --reference-job "$R10_JOB" \
  --output "$R41_OUTPUT/results.json" --grid "$R41_OUTPUT/minute_grid.csv.gz"
python -m rounds.r41.check_release "$R41_SOURCES_B" \
  --result "$R41_OUTPUT/results.json" --grid "$R41_OUTPUT/minute_grid.csv.gz"
```
