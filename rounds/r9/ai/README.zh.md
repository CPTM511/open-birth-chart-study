# R9：AI现实指标研究线

本轮已开始实际数据工作，将**任务自动化、就业替代、人类失去控制**分别研究。命盘信号不进入AI风险概率计算；本轮没有估计失业因果效应、灭绝概率或死亡结局。

## 已完成

- 抓取17个公开来源端点，均返回HTTP 200；16份快照完整。ILOSTAT大目录因8 MB上限仅保存前缀，已明确标注；实际数据文件、指标目录及必要字典均完整下载。日期、URL和哈希见[抓取清单](source_fetch_manifest.json)。
- 下载[METR 2026年11月20日更新](https://metr.org/blog/2026-11-20-q4-2026-capability-update/)的图10数据，保留15个模型估计及置信区间。其发布的能力时长倍增拟合为3.61275个月（95%区间2.08267–4.93514）；这是原机构在特定任务集上的估计，我们没有重估，也没有推算人类被取代的日期。
- 下载[ILOSTAT年度职业就业指标](https://rplumber.ilo.org/data/indicator?id=EMP_TEMP_SEX_OCU_NB_A&format=.csv.gz)：原始227,083行；2020–2025年47,965行、245个参考地区代码。这些是汇总统计行，包含调查、模型估计和地区汇总，不能称为个人样本或245个独立国家。
- 建立[证据账本](evidence_ledger.json)，记录[ILO职业暴露方法](https://www.ilo.org/publications/generative-ai-and-jobs-refined-global-index-occupational-exposure)、[2026年2月AI安全报告](https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026)的失控框架，以及[OECD事故监测](https://oecd.ai/en/incidents-methodology)的报道偏差。未下载事故个案数据库。

## 数据审计发现

[公开的窄子集](metrics/labor_lfs_isco08_major_total_sex_2020plus.csv)包含5,211行、121个参考地区、122个地区/来源组合，限定劳动调查、男女合计、ISCO-08职业大类0–9、2020年以后。保留原值与注释，补充官方字典标签。

其中有**340行序列断点、24行不可靠标记、9行数值缺失**。该表没有年龄字段，不能判断90/00后或年轻入职者；职业大类也不足以直接匹配精细任务暴露。尚未合并AI采用数据，未做趋势因果解释。完整结果见[劳动数据审计](labor_audit.json)。

## 下一步门槛

先处理口径、缺失、断序和职业映射，再取得实际AI采用强度，最后才考虑可检验的对照设计。基准能力、就业变化和不可恢复的失控不能互相替代。详见[执行协议](operational_protocol.md)；复现命令与来源授权见[英文说明](README.md)。

数据归属ILO及各原来源，本项目进行了筛选与标注，不代表原机构认可。R8的全部研究文件保持不变。
