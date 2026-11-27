# R10 recovery verification, 27 November 2026

R10 已恢复巴西四组 8,000 条原样本、墨西哥四份官方登记档案，以及与原件逐字节一致的 R8 参照评分文件。两种计算方法得到的巴西 2006 年联合高分年度比例均为 **3.214943%**。这项数值只描述参照组。这个恢复节点尚无经验证的六组比较结果。

| Material | What was verified at this checkpoint |
|---|---|
| Four Brazilian target samples | All 8,000 inputs, metadata and sampling manifests match the prescoring freeze. A second parser reread the selected birth fields and clock offsets from the official sources. [Reconstruction and checks](brazil/README.md) |
| Four Mexican registration archives | The 2009, 2010, 2020 and 2021 ZIPs match the frozen digests. They contain 5,221,122 rows in the earlier pair and 3,541,389 in the later pair. Reading the recorded birth year reproduces 2,172,917 births from 2009 and 1,674,248 from 2020 in the respective unions, before eligibility and selection. [Archive audit](mexico_archives.json) |
| Brazil 2006 reference | All three R8 input/metadata pairs were reconstructed. Replaying the full 3,729-record file under Linux reproduced the registered file hash. The R10 analysis takes only the 2,000 Brazil 2006 records with their original weights. [Runtime and replay evidence](reference/README.md) |
| Reference statistic | The primary and separately implemented reference calculations agreed on all 320,000 threshold flags over 80,000 record-years and on the weighted joint rate of 0.03214942848730289. The statistic counts years in which at least three of four models reach their registered threshold. [Numerical receipt](reference_anchor.json) |

The frozen [source decisions](../source_decisions.json) declare six available groups of 2,000. The original [scoring coordinator](../run_guarded_profiles.py) validates every input before launching the shared 12,000-record run. Reusing earlier target output also requires verifiable profiles, inputs and provenance. At this checkpoint the count of recoverable earlier target profiles was unknown. Both private Mexican samples still required matching input and metadata digests. The source-row counts and reference rate do not estimate any target contrast.

## Repeating the two aggregate checks

Use the project's pinned Python dependencies. Store original ZIPs under a private directory, one subdirectory per registration year with the publisher's original file name. The archive audit reads only the deletion flag and registered birth-year field after verifying the whole-file hash.

```sh
python rounds/r10/recovery/audit_mexico_archives.py /path/to/private/inegi-archives
python rounds/r10/recovery/check_reference.py \
  --sample-dir /path/to/private/reconstructed/samples/brazil2006 \
  --profiles /path/to/private/r8-baseline/baseline_profiles.jsonl
```

The reference check uses the entire frozen profile file as required by the [R10 protocol](../protocol.json). Keep individual inputs, profiles and private storage locations outside public commits. The [methods receipt](../public_methods_receipt.json) links the code used here to the original public freeze.
