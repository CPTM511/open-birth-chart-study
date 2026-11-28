# Reproduce the R49 P75 holdout and R46 comparison

Use a full checkout so that the public preregistration commits are available. The test holds the R10 engines, Brazil 2006 reference, R45 centering, recorded-minute inputs and the 75th percentile fixed. The repository contains group aggregates and content digests. Use a restricted directory outside the checkout for birth inputs and scores.

## Sources and input regeneration

Use the [R46 reproduction guide](../r46/REPRODUCE.md) to recover prior runs, the official Brazilian ZIPs, the INEGI 2009–2010 archives, national ITER 2020 archive, INEGI municipal-seat catalog and pinned IBGE reference. The earlier R10, R13, R15, R45 and R46 inputs provide exclusion keys and the fixed reference. Acquire the 2011–2016 INEGI archives at the publisher URLs in [the Mexico 1999 seal](seals/mx1999.json). Put the archives in `INEGI_2011_16` with their publisher filenames.

The 2011 and 2012 actual DBFs lack the occurrence locality field and archive-specific locality catalog. The workflow reads their birth year for the source coverage check. For 2014 it maps the publisher's `CATEMLN14.DBF` member name to the reproduction parser's canonical member name. For 2015 it reads the month column described as `Mes_nac` in the INEGI dictionary and named `MES_NACIM` in the DBF. The temporary adapter renames just that descriptor. The source review reads the untouched records and catalog members directly. [INEGI 2015 dictionary](https://www.inegi.org.mx/rnm/index.php/catalog/246/data-dictionary/F10)

~~~sh
umask 077
mkdir "$R49_RUN" "$R49_SECOND"
export PYTHONPATH="$PWD/src" PYTHONTZPATH="$IANA_2026C" OBS_NODE_MODULES="$PWD/node_modules"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
for instance in "$R49_RUN" "$R49_SECOND"; do
  python -m rounds.r49.prepare br1999 --job "$instance" --r15-job "$R15_RUN" --r46-job "$R46_RUN" \
    --brazil-archive "$SINASC_1999" --references "$IBGE_2022"
  python -m rounds.r49.prepare br2009 --job "$instance" --r45-job "$R45_RUN" --r46-job "$R46_RUN" \
    --brazil-archive "$SINASC_2009" --references "$IBGE_2022"
  python -m rounds.r49.prepare mx2009 --job "$instance" --r10-job "$R10_RUN" --r45-job "$R45_RUN" \
    --r46-job "$R46_RUN" --mex-old "$INEGI_ORIGINAL_DBF" --seats "$INEGI_SEATS" --iter "$INEGI_ITER"
  python -m rounds.r49.prepare mx1999 --job "$instance" --r13-job "$R13_RUN" --r46-job "$R46_RUN" \
    --mex-modern "$INEGI_2011_16" --iter "$INEGI_ITER"
done
python -m rounds.r49.source_review --job "$R49_RUN" --replay-job "$R49_SECOND" \
  --r10-job "$R10_RUN" --r13-job "$R13_RUN" --r15-job "$R15_RUN" --r45-job "$R45_RUN" --r46-job "$R46_RUN" \
  --br1999 "$SINASC_1999" --br2009 "$SINASC_2009" --references "$IBGE_2022" \
  --mex-modern "$INEGI_2011_16" --mex-old "$INEGI_ORIGINAL_DBF" --seats "$INEGI_SEATS" --iter "$INEGI_ITER" \
  --output "$R49_RUN/source_review.json"
~~~

## Score and recompute

Run the recorded-minute scoring batches and the registered restart subset in the [R10 frozen Linux and Node environment](../r10/recovery/reference/README.md). A complete batch is checked and skipped on restart. Rebuild in a fresh run directory to force the full computation again.

~~~sh
python -m rounds.r49.score --job "$R49_RUN" --mode full --groups br1999 mx1999 br2009 mx2009
python -m rounds.r49.score --job "$R49_RUN" --mode audit --groups br1999 mx1999 br2009 mx2009
python -m rounds.r49.diagnose_r46 --output "$R49_RUN/r46_diagnostic.json"
python -m rounds.r49.analyze --job "$R49_RUN" --r10-job "$R10_RUN" --output "$R49_RUN/results.json"
python -m rounds.r49.review --job "$R49_RUN" --r10-job "$R10_RUN" --results "$R49_RUN/results.json" \
  --diagnostic "$R49_RUN/r46_diagnostic.json" --output "$R49_RUN/review.json"
~~~

The aggregate arrays follow the 31 age starts 20–50. The numeric scale in JSON is proportion. Multiply by 100 for percentage points. The independent review uses direct integer reference ranks, bit windows, rational group means and a separate stratum covariance calculation. Run aggregation again with the same sealed score batches and reference in a second environment to compare every discrete value and every floating-point field at an absolute tolerance of 5 × 10⁻¹² on the proportion scale.

With Matplotlib 3.10.8, regenerate the published figure from the public aggregates.

~~~sh
python -m rounds.r49.figure rounds/r49/r46_diagnostic.json rounds/r49/results.json "$R49_RUN/upper_bounds.png"
~~~
