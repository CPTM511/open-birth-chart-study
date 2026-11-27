# R12 reproduction

Use the frozen R12 registration and source hashes. Download INEGI registration archives 2022–2025 under their publisher filenames in a private directory. Obtain the national 2020 census ZIP and tzdb 2026c. The R11 source receipt gives the four archive URLs and checksums. It also records separate counts for 2020 and 2023 births in the same registration archives. [Source receipt](../r11/results/mexico_registration_sources.json) · [Census archive](https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_00_cpv2020_csv.zip)

Provide the authorized R10 job or a reconstruction of its private directory. It contains `reference/brazil2006`, `reference/full-frozen-r8-baseline_profiles.jsonl`, `prepared/samples/mexico2020`, `profiles/baseline_profiles.jsonl`, and `aggregation_ready.json`. The project custodian holds the verified R10 archive. Its scripts rebuild the prepared metadata from the source recovery package. The complete original score file is hashed even when only the required reference and Mexico 2020 rows are read for analysis. [R10 reproduction and sealed inputs](../r10/independent_replay/REGISTRATION.md)

Use CPython 3.12.14, Node 24.22.3, the pinned Python/Node environments, and Linux x86-64 for the score stage. Supply the SHA-256 of `protocol.json` verified from the published registration as `REG_SHA`. Use `PYTHONTZPATH` pointing to the observed IANA 2026c database when preparing the samples. Individually identifiable inputs and per-record results stay in private directories.

```sh
python rounds/r12/check_methods.py --output "$PRIVATE_R12/toy.json"
python rounds/r12/prepare_samples.py --archives "$PRIVATE_INEGI" --iter-2020 "$ITER_2020" \
  --r10-job "$PRIVATE_R10" --output "$PRIVATE_R12/prepared" --registration-sha256 "$REG_SHA"
```

The published input receipt's registration SHA and the private sample file hashes bind the approved run to these selected records. Its actual bytes include the preparation timestamp. For new authorized reproductions the two reads and private sample files must yield the same hashes, while the new receipt retains its own date. Commit and verify that receipt, or verify that the date and all nondated fields match the release and use the published receipt bytes in the replay directory. Set `INPUT_SHA` to the SHA-256 of the verified receipt.

```sh
python rounds/r12/score.py --job "$PRIVATE_R12" --registration-sha256 "$REG_SHA" --input-sha256 "$INPUT_SHA"
python rounds/r12/analyze.py --job "$PRIVATE_R12" --r10-job "$PRIVATE_R10" \
  --registration-sha256 "$REG_SHA" --input-sha256 "$INPUT_SHA" --output "$PRIVATE_R12/results.json"
python rounds/r12/verify_results.py --job "$PRIVATE_R12" --r10-job "$PRIVATE_R10" \
  --registration-sha256 "$REG_SHA" --input-sha256 "$INPUT_SHA" --result "$PRIVATE_R12/results.json" \
  --output "$PRIVATE_R12/review.json"
```

Keep each run in a new directory. Archive the complete private samples and profiles only with the project custodian. The repository records hashes, source methods and population and model aggregates. [Chinese registration](REGISTRATION.md)
