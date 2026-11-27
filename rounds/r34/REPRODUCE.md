# Reproduce the Japanese date and hour composition comparison

Run from the repository root using the [pinned project setup](../../docs/REPRODUCING.md). Use separate writable directories for `R34_SOURCE_A`, `R34_SOURCE_B`, `R34_MAC_1999`, `R34_MAC_2006`, `R34_LINUX` and `R34_RESULTS`. The scoring directories must be outside the repository and readable only by their custodian. The standard inputs contain calendar, city, clock and F/M parameters. The original sources contain aggregate counts.

## Check the released comparison

```sh
export PYTHONPATH="$PWD/src"
python -m rounds.r34.source "$R34_SOURCE_A"
python -m rounds.r34.source "$R34_SOURCE_B"
python -m rounds.r34.check_release "$R34_SOURCE_A"
python -m unittest discover -s rounds/r34 -v
```

The two acquisitions check each table against its [recorded publisher hash](sources.json). An auditor can recompute the report's weighted rates and conditional bounds from the government tables and the [released grid](model_year_grid.csv.gz). Each grid row gives one date, hour, reference city and minute scenario, and the F/M parameter. The first four numbers count joint-high model years within the four ten-year age bands. The last four count high model years by system over ages 20–59. The paired alternate scenario rows cover the registered 24 dates per year.

## Rerun the profiles and reference

The complete computation uses the original [R10 pinned engines and reference recovery](../r10/recovery/reference/README.md). Point `R10_JOB` to the private reference directory containing `reference/brazil2006/` and `reference/full-frozen-r8-baseline_profiles.jsonl`. The analyzer verifies the locked files before reading the reference rates.

```sh
umask 077
export PYTHONPATH="$PWD/src"
export OBS_NODE_MODULES="$PWD/node_modules"

python -m rounds.r34.profiles "$R34_MAC_1999" --year 1999 --workers 4
python -m rounds.r34.profiles "$R34_MAC_2006" --year 2006 --workers 4
```

The main run uses macOS arm64 with CPython 3.12.14, the frozen Python dependencies and Node 24.22.3. Each completed month can be verified on restart. A month file contains all 40 model years and four scores for every required standard input. The mid-CDF classifications are checked against a second calculation using exact integer weights for every score.

On the pinned Linux x86_64 runtime, run the monthly verification fixtures using the same Git revision and scoring dependencies. Move the two resulting month-00 files to `R34_LINUX` on the analysis host if necessary.

```sh
python -m rounds.r34.profiles "$R34_LINUX" --year 1999 --workers 2 --probe
python -m rounds.r34.profiles "$R34_LINUX" --year 2006 --workers 2 --probe
```

Back on the analysis host, run the final cross-check and aggregation. Use fresh output paths.

```sh
python -m rounds.r34.analyze \
  --sources "$R34_SOURCE_A" --source-replay "$R34_SOURCE_B" \
  --scores-1999 "$R34_MAC_1999" --scores-2006 "$R34_MAC_2006" \
  --alternate "$R34_LINUX" --reference-job "$R10_JOB" \
  --output "$R34_RESULTS/results.json" --grid "$R34_RESULTS/model_year_grid.csv.gz"
python -m rounds.r34.check_release "$R34_SOURCE_B" \
  --result "$R34_RESULTS/results.json" --grid "$R34_RESULTS/model_year_grid.csv.gz"
```

The number of births in each published cell is the weight. The three comparisons combine the same modeled results with the observed distribution, the product of the observed date and hour marginals, and the observed daily counts split evenly across hours. The release checks those weighted means with a separate exact-ratio implementation. For the sex allocation bounds, available births are filled in increasing or decreasing order of the F-to-M score increment while respecting the actual national sex counts. The national totals and their original publications are listed in [the denominator reconciliation](SOURCE_CORRECTION.zh.md).


## Historical data extension

The 1996–1998 digital tables use the same numeric schema with earlier section headings. Verify their separate publisher receipts and all venue, month, day and hour sums. Add `--include-scans` to acquire the eight earlier PDF files and check their byte hashes. The annual aggregate rows for 1993–1995 were transcribed from the first published page pair in each all-venues file. Their 24 hours reconcile to the printed totals. See the [historical data report](HISTORICAL_SOURCES.zh.md).

```sh
python -m rounds.r34.historical "$R34_HISTORICAL" --output "$R34_RESULTS/historical.json"
```
