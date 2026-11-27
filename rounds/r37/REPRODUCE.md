# R37 复算

在仓库根目录运行。采用 [R10 同款 Linux x86-64 数值环境](../r10/recovery/reference/README.md)和[锁定的依赖](../../docs/reproduction_environment.json)。将 `R10_JOB` 指向含 `reference/brazil2006/` 和 `reference/full-frozen-r8-baseline_profiles.jsonl` 的限权目录。每次评分前验证 [R10 预留散列](../r10/independent_replay/registration.json)。若需重建参照，按 [R10 恢复记录](../r10/recovery/README.md)取档。

在仓库外指定四个互相独立且只有保管者可访问的路径 `R37_SOURCE`、`R37_SOURCE_RECHECK`、`R37_FIRST` 和 `R37_REPLAY`。两个原图目录分别重取。新获取时间会变化，卷序、样本位置和图像字节必须等同于[冻结凭据](source_receipt.json)。

```sh
umask 077
export PYTHONPATH="$PWD/src"
export OBS_NODE_MODULES="$PWD/node_modules"
export OPENBLAS_NUM_THREADS=1
python -m rounds.r37.archive_source "$R37_SOURCE" "$R37_SOURCE/source_receipt.json"
python -m rounds.r37.archive_source "$R37_SOURCE_RECHECK" "$R37_SOURCE_RECHECK/source_receipt.json"
```

在 `R37_SOURCE` 中保存以下三份本地记录。当前发布所用的三个文件散列见[结果凭据](results.json)。已有的限权副本也可由保管者按散列校核后用于复算。

- `pass_a.tsv`。按图像代号升序，在每幅中按左页、右页，各自自上而下清点。每行先写源照片文件名去掉后缀，之后用空格分隔各项，两页用 `|` 分隔。
- `pass_b.tsv`。用第二份档案按图像代号降序，在每幅中从右页底部读至顶部，再从左页底部读至顶部。优先遮住后来添加的旁注。遇到正文的当时批准改写，可展开所指的改写文字复核。
- `adjudications.json`。对两遍字段或已读文书号之间的分歧，按 `图像:L1` 或 `图像:R1` 等位置记裁决。每项包含最终的 `final` 字段及文字说明 `basis`。第一遍略去的号码以 `?` 暂记，由第二遍读取确认。卷内档号区分数字主号、事后认领独立的 `R` 号和正式 `bis` 后缀。

纳入项格式是 `文书号/登记月日/出生月日/钟点/性别/所记精度/发生地依据`，月份日期用 MMDD，钟点为 24 小时制 HHMM。性别采用原文 M/F，精度采用 `h`、`half`、`quarter` 或 `minute`。地点依据为文书明确的当地住所 `d`、当地医院 `c` 或可定位当地地址 `a`。排除项只记文书号和原因。认领用 `ACK`，裁判抄件 `COURT`，出生钟点无法判定用 `U_CLOCK` 或 `U_MIDNIGHT`。索引页用 `INDEX`，封卷签文用 `CLOSE`。姓名、通讯地址、父母字段、后来发生的事项及非必要旁注不进入转录。

```sh
python -m rounds.r37.study --source "$R37_SOURCE" --source-recheck "$R37_SOURCE_RECHECK" \
  --r10-job "$R10_JOB" --job "$R37_FIRST"
python -m rounds.r37.study --source "$R37_SOURCE" --source-recheck "$R37_SOURCE_RECHECK" \
  --r10-job "$R10_JOB" --job "$R37_REPLAY"
python -m rounds.r37.compare --source "$R37_SOURCE" --source-recheck "$R37_SOURCE_RECHECK" \
  --r10-job "$R10_JOB" --job "$R37_FIRST" --replay-job "$R37_REPLAY" --output "$R37_SOURCE/results.json"
```

原钟点与取整钟点共享当地巴黎平均时 UTC+00:09:21，使用同一里昂参考点及原出生日期对应的 R10 完成年龄轴。取整规则使用 R29，原记录是整点时复用同一轨迹。比较程序核对卷序、图像和校准参照，要求两遍评分文件散列一致，验证全部阈值判定，并用精确权重和另一套卷内图像差分公式复核点估计及方差。[R29 规则](../r29/REGISTRATION.zh.md) · [输出和计算凭据](results.json)

原图权属标示 Ville de Lyon, Archives municipales。源档由里昂市档案馆发布，公开材料提供原始入口和聚合结果。逐条转录和评分文件保存在仓库外的限权档案。[档案馆民事登记入口](https://recherches.archives-lyon.fr/page/registres-d-etat-civil) · [馆方开放使用条件](https://www.archives-lyon.fr/pages/donnees-ouvertes)
