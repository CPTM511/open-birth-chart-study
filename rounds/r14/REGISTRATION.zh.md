# R14 研究登记 · 就业年龄、职业与实际企业 AI 采用

本轮沿 R9 独立现实指标研究线，建立可核验的美国就业年龄×职业及行业环境估计。使用美国人口普查局 ACS 2023、2024 两份一年期全国个人样本，以及 BTOS 原口径的 2024 年 26 个调查参考期。研究者已查数据字典、调查问卷、档案校验值和出版物。登记时未计算跨年龄结果，也未检查本轮选定时期的企业采用率数值。[ACS 2023](https://www.census.gov/programs-surveys/acs/microdata/access.2023.html) · [ACS 2024](https://www.census.gov/programs-surveys/acs/microdata/access.2024.html) · [BTOS 发布入口](https://www.census.gov/hfp/btos/data_downloads?so=1) · [R9 现实指标线](../r9/ai/README.zh.md)

## 样本与行业对齐

按 ACS 观察年龄分为 20–29、30–39、40–54。纳入平民受雇人员，劳动状态为在岗或有工作但不在岗（ESR 1、2），且私人营利或私人非营利组织的工资薪金就业（COW 1、2）。保留人员权重 PWGTP 与全部 80 个复制权重。行业取 NAICSP 前两位，31–33、44–45、48–49 按公布合并口径处理。候选为 21、22、23、31–33、42、44–45、51、53、54、55、56、61、62、71、72。农业、交通运输、金融、其他服务和公共行政因调查框有排除子行业或定义相差而整类排除。未知行业和无最低期数的行业单列。报告原私人受雇样本与成功连接行业的数量和加权覆盖。另导出每年、年龄段、原始 Census 职业代码的人数估计和未加权样本数，至少 100 条原始记录才公开。缺少职业编码单独计入核查。[BTOS 方法及框](https://www2.census.gov/data/experimental-data-products/business-trends-and-outlook-survey/methodology.pdf) · [ACS 复制权重公式](https://www2.census.gov/programs-surveys/acs/tech_docs/pums/2024ACS_PUMS_User_Guide.pdf)

## 观察到的 AI 采用环境

使用 BTOS 原问卷问题 7 的“是”占比，即企业称过去两周使用 AI 生产商品或服务。依据 `Ref End` 选择 2024 年的 26 期。三种答案“是／否／不知道”均有数值且总占比可核对的期次可用。每个行业至少 12 期可用，取可用期数的算术平均并保留缺期期号。2025 年末问卷改为涵盖任何业务职能，此后系列保留其独立口径。2024 年原问卷行业均值固定用于两年就业构成。将各年龄段成功连接行业中的就业加权构成乘以这个固定采用率，得到年龄段的行业采用环境。其单位是企业“是”的行业百分比加权均值。BTOS 行业来源含波多黎各，ACS 美国全国文件按其本身范围使用。[原始 BTOS 表](https://www.census.gov/hfp/btos/downloads/AI%20Core%20Questions.xlsx) · [题目改版及序列断点](https://www.census.gov/hfp/btos/downloads/AI%20Question%20Wording%20Updates.pdf)

## 主要比较与复核

唯一主比较为 2024 年 20–29 岁减 40–54 岁的行业采用环境，单位百分点。按 ACS 方法对同一重复权重所得两组估计之差计算方差，乘 1.96 给出 95% 区间。该区间仅对 ACS 抽样且固定行业调查点估计。报告 2023 的同口径数值与行业就业构成的描述性变化。该指标可区别行业就业构成，个人使用、年龄影响和就业替代需要各自的观测与比较设计。本轮结果脱离命盘计算。

在 GitHub 核验登记后执行。复读全量 ACS 样本、核对各年龄段×行业分母及细职业表，独立按发布的 80 个行业合计权重复算区间。记录档案校验值、所有输出分母和未通过的配对。若少于 12 个候选行业有足够的调查期，结果记作覆盖不足。

```sh
python rounds/r14/analyze_labor.py --sources "$SOURCE_FILES" --output "$NEW_RESULTS" \
  --registration-sha256 "$PUBLIC_REG_SHA"
python rounds/r14/verify_labor.py --sources "$SOURCE_FILES" --results "$NEW_RESULTS" --output "$REVIEW_JSON"
```

源文件命名与校验值见 [机器可读登记](protocol.json)。
