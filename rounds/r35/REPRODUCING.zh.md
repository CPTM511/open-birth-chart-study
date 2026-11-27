# R35 数据和复算

研究登记提交为 `3f2d52940bf0dd39784e19a7279dad357ebfce8f`。在计算节日结果前，原表通过的场所范围、数据和识读凭据于 `68e4dbd0e847eb8ace0a310dc5fc8f03b814be2a` 冻结并推送。

## 由固定计数复算

[historical_counts.csv.gz](historical_counts.csv.gz) 含 13,503 行原表日期或边际向量，字段依次为 `year,venue,month,day,total,h00,…,h23`。日期为日本本地民用日。年月日中 `day=0` 表示该月或该年的小计，而 `month=0,day>0` 表示全年按月内日序重聚合。全国总表及各场所分表有各自的行，使用时以所需范围筛选。`h00` 至 `h23` 为 24 个小时组。源表的无效历日经核对后省略。

以下命令从仓库根目录运行，使用仓库固定的 Python 依赖，另需 Pillow。输出路径须为新文件。第二套程序独立读取发布计数和节日原表，使用不同的历日枚举和十进制小数计算比例，并对照单独发布的年度原表。

```sh
r35_tmp=$(mktemp -d)
gzip -dc rounds/r35/cabinet_holidays.csv.gz > "$r35_tmp/holidays.csv"
python -m rounds.r35.holdout rounds/r35 "$r35_tmp/holidays.csv" "$r35_tmp/results.json"
cmp rounds/r35/results.json "$r35_tmp/results.json"
curl -fsSL 'https://www.e-stat.go.jp/stat-search/file-download?fileKind=1&statInfId=000040503640' -o "$r35_tmp/annual.csv"
python -m rounds.r35.verify_results rounds/r35 "$r35_tmp/holidays.csv" "$r35_tmp/results.json" \
  "$r35_tmp/review.json" --annual-table "$r35_tmp/annual.csv"
cmp rounds/r35/independent_review.json "$r35_tmp/review.json"
```

## 由发布者原表重新生成计数

扫描输入为 R34 记录的八份 e-Stat 原始 PDF。全部 468 页均做原页识别与拆格识别。1993–1995 年过关的 234 页包括全国、医院和诊疗所。原表两个半页分别为总数及 00–11 时、12–23 时。源文件缩写、PDF 页号、行序、半页列序保留在 [原图校订](visual_review.json) 和 [调和记录](reconciliation.json) 中。PDF 页号从 1 开始，行列序从 0 开始，行 0 为段落小计。1995 年部分扫描的行距由像素投影重新拟合。OCR 冲突修订需要实际读数，阅读渠道包括原页、拆格、Tesseract 和直接查看原图。

原表至计数的入口使用 macOS 的 Apple Vision、PyMuPDF 1.26.7、Pillow 13.0.0 和仓库锁定依赖。已冻结的第二 OCR 读数来自 Tesseract 5.3.4，留有源页位置。[R34 扫描索引](../r34/historical_sources.json) · [原件与版本](source_receipt.json) · [第二 OCR 读数](tesseract_reads.json)

```sh
r35_tmp=$(mktemp -d)
mkdir -p "$r35_tmp/archive" "$r35_tmp/rebuilt"
R35_TMP="$r35_tmp" python - <<'PY'
from pathlib import Path
import json
import os
from rounds.r34.source import fetch_verified

root = Path(os.environ["R35_TMP"])
receipt = json.loads(Path("rounds/r35/source_receipt.json").read_bytes())
for name, record in receipt["official_scans"].items():
    fetch_verified(root / "archive" / name, record)
for year, record in receipt["official_digital_tables"].items():
    fetch_verified(root / "archive" / f"jp{year}.csv", record)
PY
gzip -dc rounds/r35/cabinet_holidays.csv.gz > "$r35_tmp/holidays.csv"
python -m rounds.r35.read_scans "$r35_tmp/archive" "$r35_tmp/pages" --include-places
python -m rounds.r35.grid_reads "$r35_tmp/pages" "$r35_tmp/contacts" --places 0 1 2
python -m rounds.r35.isolated_cells "$r35_tmp/pages" "$r35_tmp/contacts" "$r35_tmp/crops" --places 0 1 2
python -m rounds.r35.freeze_counts "$r35_tmp/archive" "$r35_tmp/archive/jp1999.csv" \
  "$r35_tmp/pages" "$r35_tmp/contacts" "$r35_tmp/crops" "$r35_tmp/holidays.csv" \
  rounds/r35/released_scan_scope.json "$r35_tmp/rebuilt"
cmp rounds/r35/historical_counts.csv.gz "$r35_tmp/rebuilt/historical_counts.csv.gz"
```

第一及第二组 Vision 识别在不同系统版本上可能产生不同的候选文本。发布计数和复算所用的节日快照附有 SHA-256。研究使用 e-Stat 发布的日本厚生劳动省《人口動態統計》保管统计表，项目做了转录、规范化、算术核对与配对分析。节日快照为日本内阁府《国民の祝日・休日》原 CSV 的无损压缩。[e-Stat 使用条款](https://www.e-stat.go.jp/en/terms-of-use) · [日本内阁府原始 CSV](https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv)
