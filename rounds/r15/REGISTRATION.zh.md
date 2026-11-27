# R15 研究登记 · 巴西 1999 年出生登记留出队列

在巴西官方 SINASC 1999 档查到实际 `HORANASC`。这份 40,239,938 字节的归档已按发布地址重取并通过 ZIP 校验。3,256,433 条物理行中，49,348 条具备完整出生字段且可定位于唯一历史时钟。49,121 条发生在阿拉戈斯州，占合格框的约 99.54%。这与 R9 已核的 1996 和 2001 归档缺时钟的结果同时成立。研究者已看过以上来源质量计数、R8–R14 的公开结果与巴西 2006 固定参照，未查看巴西 1999 的目标评分。[官方资源](https://dadosabertos.saude.gov.br/dataset/sistema-de-informacao-sobre-nascidos-vivos-sinasc/resource/90009ea0-bcf0-4434-b8fe-606194cc2658) · [来源审计](source_audit.json) · [R9 缺字段记录](../r9/data/COVERAGE.md)

## 问题、抽样和参照

预设主比较是巴西 1999 合格登记框对巴西 2006 固定参照的联合高分率差。每条记录计算完整 20–59 岁 40 年轨迹，至少三体系各达到同年龄段参照第 80 百分位的记录年为联合高分。使用 R10 原引擎、年龄、权重和阈值；只重建新样本的分层权重。0.30 个百分点为预设需关注量级。若双侧 95% 条件区间整体在 ±0.30 个百分点以内，可在本观察框排除该幅度的上下偏离。明显超出、与阈值重叠及区间跨零分别按实报告。[R10 方法及参照](../r10/independent_replay/RESULTS.zh.md)

来源钟点须为四位有效时分，出生年月日须确认为 1999 年，使用原登记性别。发生地为七位 IBGE 编码，需与原用 2022 年市镇参考表的完整编码一致。坐标是市镇参考点。使用 IANA 2026c 唯一历史偏移，排除不确定的时钟标记与地点。午夜作为有效记录保留于主分析，并在预设描述性删除分析中复核。1999 源档的七位编码与既往 R9 CSV 的六位不同，完整码匹配避免舍弃所有行或使用未经验证的截断。[SINASC 字典](https://svs.aids.gov.br/daent/cgiae/sistemas-informacao/sinasc/documentacao/dicionario_de_dados_SINASC_tabela_DN.pdf) · [R8 IBGE 复现](../../docs/REPRODUCING.md)

合格行按发生州×记录性别分层，固定抽 **2,000 条**。每层首先保留 `min(2, N_h)`，按剩余容量精确分配剩余名额，按最大余数及字典顺序破同。层内按固定种子与物理行键的 SHA-256 抽取，个体分析权重为 `N_h/n_h`。使用整条 40 年轨迹作 9,999 次分层有限总体校正重抽样，参照和已登记时钟固定。条件区间只涵盖所声明抽样假设下的误差。

另公开去午夜、仅非整点和主要发生州阿拉戈斯的加权描述结果。R13 墨西哥 1999 年晚登记的已发布估计同年并列，两边的覆盖框各自解释，两个结果之间不作显著性检验。年龄相同而时期与队列关系仍须分别报告。

## 复核和停止

核验 GitHub 研究登记与样本封存后才评分。要求 2,000 条完整轨迹、80,000 个建模记录年及 320,000 个分数。核对输入文件、完整样本和权重，用第二条精确阈值路径复算巴西两组全部标记，并以有理数重算新样本率。原始时地与细粒度抽样元数据保留于私有档案。合格时钟绝大部分出自同一州，发布解释限于合格档案框。死亡结局保持暂停。

```sh
python rounds/r15/brazil_1999.py audit --archive "$SINASC_1999" --references "$IBGE_2022" --output "$CHECK_SOURCE"
python rounds/r15/brazil_1999.py prepare --archive "$SINASC_1999" --references "$IBGE_2022" --job "$PRIVATE_RUN" --registration-sha256 "$REG_SHA"
python rounds/r15/brazil_1999.py score --job "$PRIVATE_RUN" --registration-sha256 "$REG_SHA" --input-sha256 "$INPUT_SHA"
python rounds/r15/brazil_1999.py analyze --job "$PRIVATE_RUN" --r10-job "$PRIVATE_R10" --registration-sha256 "$REG_SHA" --input-sha256 "$INPUT_SHA"
```
