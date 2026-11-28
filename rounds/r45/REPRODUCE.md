# Reproduce the cross-source cohort-break study

Use a full checkout containing the [preregistration](REGISTRATION.zh.md) and [new input commitments](SOURCE_SEALS.json). The code checks the registered text and JSON against the published commit. Every computation uses birth records and scores, with no life outcome data. Use private directories for downloads, birth inputs and scores. The public results contain source totals, digests, parameters, and group aggregates.

## Birth input and scoring prerequisites

1. Follow [R10 fixed reference replay](../r10/recovery/reference/README.md) and [R10 independent replay](../r10/independent_replay/REGISTRATION.md) to reconstruct the reference and R10 Mexico 2009 inputs and baseline profiles. The older Mexico 2009 sample is only used for the separate archived-sample check. Its original private sampling metadata were unavailable. The R10 receipts identify the re-created files.
2. Rebuild R13 and R15 using the [R13](../r13/REGISTRATION.zh.md) and [R15](../r15/REGISTRATION.zh.md) instructions. For R13 retain the complete late-registration sample and profiles. The analyzer partitions it into 1999 and 1990–1998 actual birth years. Keep the original sample and profile directories within each earlier run root.
3. Obtain the Brazil 2009 CSV ZIP directly from [SINASC](https://dadosabertos.saude.gov.br/dataset/sistema-de-informacao-sobre-nascidos-vivos-sinasc/resource/eaec50d8-8155-4148-90bb-db361b686bd0). Obtain the two dated DBF archives, 2020 national ITER census ZIP and 32 municipal-seat catalogue responses via the [R10 Mexico reconstruction](../r10/recovery/mexico2009/README.md). Follow the [IBGE reference instructions](../../docs/REPRODUCING.md) for the pinned municipal reference table. Use IANA 2026c and the pinned [Linux scoring runtime](../r10/recovery/reference/README.md). Snapshot source responses identified in the R10 receipt may change at their official endpoint.

Set `R45_RUN`, `R10_RUN`, `R13_RUN`, `R15_RUN` and the source paths below to absolute locations on the scoring machine. The prepared source seals must match the pre-scoring commitments on GitHub. Use a new work directory for each repetition.

```sh
umask 077
mkdir "$R45_RUN"
export PYTHONPATH="$PWD/src"
export PYTHONTZPATH="$IANA_2026C"
export OBS_NODE_MODULES="$PWD/node_modules"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1

python -m rounds.r45.prepare br2009 --job "$R45_RUN" \
  --brazil-archive "$SINASC_2009" --references "$IBGE_2022"
python -m rounds.r45.prepare mx2009 --job "$R45_RUN" \
  --mexico-archives "$INEGI_DBF" --iter "$INEGI_ITER" --seats "$INEGI_SEATS"

set -- --job "$R45_RUN" --r10-job "$R10_RUN" --r13-job "$R13_RUN" --r15-job "$R15_RUN"
python -m rounds.r45.score "$@" --mode base --groups br2009 mx2009
python -m rounds.r45.score "$@" --mode hour --groups br1999 mx1999 br2009 mx2009
python -m rounds.r45.score "$@" --mode audit --groups br1999 mx1999 br2009 mx2009
```

The minute-compression run retains recorded scores for clocks already at the start of an hour or without an unambiguous offset at the compressed time. The latter condition is reported. The audit command selects 64 records per main group by the registered hash and independently restarts the same frozen engines. Its output is compared to the full execution before publication.

To reproduce the source review, repeat the two draw commands under a second private run root. Fetch the Brazil archive again and pass the second copy to the review. The review checks both seals, recounts and reranks the Brazilian frame through another parser, and checks the selected Mexican rows by physical DBF position.

~~~sh
python -m rounds.r45.source_recheck --job "$R45_RUN" --replay-job "$R45_SECOND_DRAW" \
  --brazil-archive "$SINASC_2009_SECOND" --references "$IBGE_2022" \
  --mexico-archives "$INEGI_DBF" --iter "$INEGI_ITER" --seats "$INEGI_SEATS" \
  --output "$R45_RUN/source_review.json"
~~~

## Quantitative checks and release

```sh
python -m rounds.r45.analyze "$@" --output "$R45_RUN/results.json"
python -m rounds.r45.review "$@" --aggregate "$R45_RUN/results.json" --output "$R45_RUN/review.json"
python -m unittest discover -s tests -p 'test_r45_cohort_breaks.py' -v
```

The exact review uses sorted integer-weight prefix ranks and chronological bitmasks. It directly recomputes age and calendar means, census and stratified errors, the normal-multiplier critical value, the projected intervals, and the thresholds for the three analysis variants. Scoring replay uses the same versioned engines. The aggregate review uses the same sealed inputs and separate arithmetic. The scripts also record one complete match of within-cell trajectory multisets for the first calendar-preserving permutation.

The effect curve arrays run in this order.

- 31 age starts for ten-year windows without a joint high year.
- 20 calendar starts for the same ten-year absence.
- 20 calendar starts for ten-year joint-high density. The downward test takes the negative of these values.

All effect arrays and thresholds are proportions. Multiplying by 100 converts them to percentage points. The scale removes each record's average across its complete window grid and the age-specific reference means. Use the separately reported raw age and calendar fractions for absolute prevalence. Because centering reallocates deviations, a relative high elsewhere can accompany an injected suppression.

With Matplotlib 3.10.8, use the public aggregates to render the published figure.

~~~sh
python -m rounds.r45.figure "$R45_RUN/results.json" "$R45_RUN/curves.png"
~~~
