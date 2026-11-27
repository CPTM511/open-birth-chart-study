# R17 研究登记 · 工作者自报生成式 AI 使用与实际就业指数

本轮接续 R14，使用两个观察单位不同的公开资料。RPS 问受雇者是否曾在工作中使用、上周使用和每个工作日使用生成式 AI。Stanford Digital Economy Lab 的 Canaries 公布 ADP 工资单样本中的分年龄、职业暴露五分位就业指数。这一轮复算公开合计。研究者已见两来源的公开描述和部分原文结果，包括 RPS 2026 年三季度全体受雇者的采用概览和原 Canaries 文稿的早期职业组方向。以下具体算式、月份和分组根据发布字段固定，没有查看下载档中的目标数值。[RPS 原研究](https://doi.org/10.1287/mnsc.2025.02523) · [Stanford 数据及说明](https://digitaleconomy.stanford.edu/project/indicators/canaries-dashboard/) · [R14 行业环境](../../R14.md)

## 工作者实际使用

用 FRED 发布的三条 RPS 序列，统一到 2024 年第三季度至 2026 年第三季度的 9 期。目标总体是 18–64 岁有工作受访者。主量为**上周至少一次工作使用率**首末差，报告百分点。另报告曾为工作使用和上周每工作日使用，核查 `每日 ≤ 上周 ≥1 次 ≤ 曾使用`。季度标签来自发布机构；同年三季度重比较，三条序列均未季节调整。合计序列没有用于本复算的微观调查权重及方差，报告只给公开点估计。[曾使用](https://fred.stlouisfed.org/series/RPSGENAIUSAGESHAREWORK) · [上周使用](https://fred.stlouisfed.org/series/RPSGENAIUSAGESHARELWWORK) · [每工作日使用](https://fred.stlouisfed.org/series/RPSGENAIUSAGESHAREEDLWWOR)

## 工资单实际就业

先验证 Stanford 按职业暴露五分位和六个年龄段公布的 60×5 月度表。每条序列在 2022 年 11 月归一为 100。主比较为 2026 年 10 月就业指数中，职业暴露第 5 组／第 1 组所反映的相对变化 `100×(I5/I1−1)`。分别报告 22–25 岁与 41–49 岁，并给其百分点差。另报告 6 个年龄段首个年度基线前的相对变化，从 2021 年 11 月到 2022 年 11 月，展示生成式 AI 公布前的已有分化。预设月度核对包括 2026 年 6 月重现旧报告时点、2026 年 8、9、10 月。统计单位为发布者所用的工资单就业指数。无原始工资单或方差信息，保留年龄与职业异质性、固定企业样本和前趋势的限制。[主研究 2026 年 8 月稿](https://digitaleconomy.stanford.edu/app/uploads/2026/08/Canaries_August2026.pdf)

在 GitHub 核验注册及输入 SHA-256 后计算，独立用同一公开发布数列交叉复算。就业端核对各月同比发布表与原指数计算，采用端用十进制定点和有理数复算差值。若发现缺失保留，其样本替代、权重和因果识别列为后续独立问题。两来源不作个体、行业或出生资料关联。

```sh
python rounds/r17/observed.py --sources "$SOURCE_FOLDER" --registration-sha256 "$REG_SHA" --output "$PUBLIC_RESULT"
```
