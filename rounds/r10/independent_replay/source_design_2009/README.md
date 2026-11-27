# Mexico 2009 design-file reconstruction

This command recreates the private record-level sampling evidence used by the R10 independent replay. It takes the two dated INEGI registration archives, the national 2020 census locality file, the 32 municipal-seat catalogue responses and IANA time-zone data from the [documented source replay](../../recovery/mexico2009/README.md). The [source receipt](../../recovery/mexico2009/replay_receipt.json) pins the geographic catalogue responses, which the publisher may update.

```sh
PYTHONTZPATH=/private/zoneinfo-2026c python rounds/r10/independent_replay/source_design_2009/rebuild_design.py \
  --archives /private/inegi \
  --iter /private/iter_00_cpv2020_csv.zip \
  --seats /private/inegi-seats \
  --private-design /private/mexico_2000s/reconstructed_design.jsonl
```

The script recounts the eligible frame and its 52 strata, reranks records using the registered seed, and checks the entire 2,000-row model file against the historical input digest. It then rereads the selected physical DBF rows and joins them to the historical municipality names, census coordinates and designated seats. The exact weights sum to 1,645,435. The reconstructed design file must match the recovery digest `e2a126d75ed4526e3403f014d135572fc215889d4e4911942622cb91aa5abed1` before any record-level output is written. Omit `--private-design` to print only the aggregate receipt. [Six-group input and design receipt](../../recovery/input_and_design_receipt.json)

墨西哥 2009 年的原始抽样说明仍然缺失。上述校验值指向依据官方登记重新构建的逐条抽样证据。个体记录仅在本地私有目录生成。
