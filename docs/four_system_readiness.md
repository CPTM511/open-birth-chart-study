# Four-system implementation readiness

**Ready for the locally frozen structural-signal study; not a validated four-system prediction model.** This inventory concerns the frozen engines and synthetic/historical astronomical checks. It does not inspect real-person profiles, live cohort distributions or outcomes. Mortality blind testing remains paused.

## Implemented workflows and primary scalars

| Engine | Implemented calculation modules | Frozen annual primary |
|---|---|---|
| Bazi `OBS-R8-BZ-1.0` | Four pillars; hidden stems; ten gods; na-yin; twelve growth phases; xun/empty branches; specified stem/branch interactions; starting-period timestamp and direction; 24 contiguous ten-year intervals; annual pillar; bounded month-command and rescue clauses. | Annual and active-decadal branches versus each of four natal branches: number of six-clash pairs divided by **8**. |
| Ziwei `OBS-R8-ZW-1.0` | Twelve palaces; life/body placements; fourteen major stars; subsidiary/adjective stars; brightness; natal transformations and auxiliary cycles; decadal/annual palace maps, transformations and transit stars. Detailed output retains available minor/month/day/hour cycle objects. | Mean of **two indicators**: annual Hua Ji's natal-star position lies in annual life/health palaces; decadal Hua Ji's natal-star position lies in decadal life/health palaces. Values: **0, 0.5, 1**. |
| Qizheng `OBS-R8-QZ-1.0` | Seven luminaries; four explicitly defined additional points; twelve palaces; all 28 unequal mansion boundaries; planetary palace/mansion degrees; rulers and element relations; sect/retrograde fields; selected fixed major periods; birthday minor periods; monthly transits. | Equal mean of **five normalized channels**: natal adverse-set contacts with major/minor palaces, transit adverse-set contacts with major/minor palaces, and transit co-mansion contacts with natal Sun/Moon/Ming-palace ruler. Same/opposite/trine weights: **1/0.7/0.4**. |
| Western `OBS-R8-WEST-1.0` | Ten natal planets; whole-sign houses; Ascendant/Midheaven; five major aspects; monthly transits; day/year secondary progressions; Naibod progression of axes. Detailed output includes full monthly charts and aspect tables. | **0.5 × transit + 0.25 × progressed-planet + 0.25 × progressed-axis** hard-contact indices. Triangular proximity to 0°/90°/180°; transit orb 3°, progressed orb 1°. Targets: natal Sun, Moon, Ascendant, Midheaven. |

Bazi and Ziwei use a July 1, 12:00 source-reference civil-clock snapshot. Qizheng and Western average twelve snapshots, each month 15 at 12:00 UT. Neither scheme constitutes continuous annual coverage. Supportive configurations remain separately reported; they do not become calibrated numerical cancellation of adverse configurations.

Qizheng's primary actor set is Mars/Saturn/Luohou/Jidu/Yuebo; Venus/Jupiter/Ziqi are separately reported support. Western's transit actors are Mars/Saturn/Uranus/Neptune/Pluto; its progressed-planet actors are Sun/Moon/Mercury/Venus/Mars, and progressed axes are Ascendant/Midheaven. These are declared research selections, not universal classifications of harm.

All four require an explicit birth clock. Bazi/Qizheng/Western require a supplied instant or offset; Qizheng/Western also require coordinates. The chosen Bazi/Ziwei cycle rules require a recorded M/F source field. Missing or contradictory prerequisites cause an error or missing result with a reason, not an invented clock, sex, location or zero-risk score.

## Conditional interpretation and material gaps

| Engine | Interpretation actually implemented | Material work still absent |
|---|---|---|
| Bazi | **14 executable clauses in eight source groups**: officer formation/damage/resource rescue; wealth/robbery mediation; eating-god/indirect-resource interference; killings/control/counterconditions; hurting-officer exceptions; blade containment; peer-command formation. Ambiguous month selection, transformation dependence and competing rescue candidates remain explicit. | A complete classical strength verdict, pattern hierarchy, unique effective yongshen, transformation validity, placement effectiveness, climate adjustment and net outcome adjudication. Weighted-element annotations do not decide these questions. |
| Ziwei | **Five conditional clauses**: favorable decadal-life premises; adverse conditions across cycles; repeated Qisha with annual Yang/Tuo; natal/transit Yang/Tuo duplication; mixed support/adversity in each dynamic life palace. Brightness and specified rescue stars remain visible. | Exhaustive pattern priorities, all rescue interactions, a numerical meaning for qualitative phrases such as “many beneficial stars,” and event/lifespan adjudication. Every auxiliary-star table has not received independent expert review. |
| Qizheng | An explicit Qing-informed modern reference workflow and bounded contact statistic. Palace/mansion rulers and element relations are exported as context. | **Modern mean-apogee Yuebo approximates, rather than reproduces, the Qing “highest true longitude” algorithm.** Nodes use modern true-node astronomy with Qing names. Ming is a discrete palace rule, without a fabricated precise degree. The chosen fixed Dongwei major periods do not implement degree-adjusted childhood limits or continuous degree-based limits. Conditional seasonal/sect/rescue judgments are not exhaustively adjudicated. |
| Western | A specified geometry-based chart/transit/progression workflow. Traditional seven-planet domicile/detriment flags and sect are exported. | Comprehensive traditional or modern interpretive doctrines, primary-direction alternatives, exhaustive dignity/sect/rescue prioritization, and any event or lifespan model. A hard aspect or conjunction is not automatically an observed harmful event. |

The Qizheng table consistently uses *Huangchao Tongzhi*'s 1744 boundaries and 51 arcsec/year rule. Its Shen boundary differs from a *Qing Shi Gao* anchor by **2′15″**, and Wing by **9′17″**. Both discrepancies are retained. The alternative osculating-apogee model is a separately labelled sensitivity, not a replacement selected after seeing cohort results.

The selected Qizheng major-period sequence totals **100.5 years**. This is a calculation-domain boundary, not a lifespan cutoff; unsupported ages return missing.

## Readiness evidence

| Evidence | Observed result | What it establishes |
|---|---|---|
| Bazi/Ziwei implementation tests | **18 unittest methods passed** before cohort-signal inspection: eight author golden charts, day-cycle arithmetic, solar-term representation across four offsets, minute-based starting-period reconstruction, interval continuity, missing inputs, conditional ambiguity/rescue examples, 26 life/body formula cases, three Node timezones and 40 annual snapshots. | Specified calendar/interface/formula behavior. Author golden charts are not independent historical almanac validation. |
| Qizheng/Western implementation tests | **11 unittest methods passed**: input/offset rejection, analytical house geometry, poles, mansion coverage, four-point definitions, period boundaries, secondary-progression identities, and identical compact/full scores. | Selected workflow and numerical-boundary behavior. |
| Independent astronomy | Ten bodies at five dates: maximum discrepancy **27.973″** under nominal UT, **11.832″** with matched TT. | Agreement at those 50 test cases, not a guarantee over all dates or predictive validity. |
| Direct 1833 almanac check | Pages 40–41 visually checked; 12 dates per additional point. Zi Qi maximum error **0.573′**; mean-apogee Yuebo **34.851′**; osculating-apogee Yuebo **27.311°**; Luo/Ji **22.037′/23.037′**. | Correctly reconstructed Zi Qi absolute origin/epoch and quantified limitations of the chosen modern lunar points. |

Audit records: [Bazi/Ziwei readiness](bazi_ziwei_readiness.json), [validation](bazi_ziwei_validation_results.json), [Qizheng/Western validation](engine_validation/validation.json), [historical reference](engine_validation/1833_reference.json). Frozen specifications and source/code seals are in [`protocol/`](../protocol/). Detailed methods: [Bazi/Ziwei](bazi_ziwei_methods.md), [Qizheng/Western](qizheng_western_methods.md).

### Primary and official sources

- Bazi month-command clauses: [*Gengcunji*, transmitted Ziping-related text](https://www.shidianguji.com/book/NCL06599A/chapter/1lystjkljywij). The study does not settle attribution of every transmitted passage.
- Bazi luck-period context: [*Sanming Tonghui*](https://www.shidianguji.com/book/SK1610/chapter/1kf5v6ol1vhnp); exact selected implementation: [lunar-python Yun](https://github.com/6tail/lunar-python/blob/master/lunar_python/eightchar/Yun.py).
- Ziwei clauses: [*Ziwei Doushu Quanshu*, volume 3](https://zh.wikisource.org/wiki/紫微斗數全書/卷三); placement/cycle implementation: [iztro](https://github.com/SylarLong/iztro), [official horoscope API](https://docs.iztro.com/en_US/posts/horoscope).
- Qizheng four-point definitions: [*Qing Shi Gao*, Shixian Zhi 6](https://www.shidianguji.com/zh/book/LS0025/chapter/1kt95er1advsv); numerical palace origin: [*Tianwen Suanxue Zuanyao*, volume 5](https://www.shidianguji.com/book/CADAL02032854/chapter/1l6xxrk89hica).
- Full mansion table: [*Huangchao Tongzhi*, volume 19](https://www.shidianguji.com/zh/book/SK1154/chapter/1l9l7p13m8oiq), [parallel transcription](https://zh.wikisource.org/wiki/皇朝通志_(四庫全書本)/卷019); [volume 20 precession rule](https://www.shidianguji.com/zh/book/SK1154/chapter/1l9l7p300kgf7).
- Qizheng palace and limit traditions: [*Xingxue Dacheng*, volume 4](https://zh.wikisource.org/zh-hans/星學大成_(四庫全書本)/卷04), [fixed-period verse in full text](https://zh.wikisource.org/zh-hant/星學大成_(四庫全書本)/全覽); [contact weights and conditional judgments](https://www.shidianguji.com/book/CADAL02093863/chapter/1lazcaitic9be).
- Historical sky reference: [1833 National Library of China almanac scan](https://commons.wikimedia.org/wiki/File:NLC892-411999011532-17590_大清道光十三年七政經緯躔度時憲書.pdf).
- Modern astronomy/progressions: [Swiss Ephemeris manual](https://www.astro.com/swisseph/swephprg.htm), [Astrodienst progression description](https://www.astro.com/faq/fq_fh_owtype_i.htm), [secondary directions](https://www.astro.com/astrowiki/en/Secondary_Directions), [Astronomy Engine reference](https://github.com/cosinekitty/astronomy/blob/master/source/python/README.md).

## Permitted research claim

The four declared calculation workflows and their frozen structural indices can be reproduced; selected conditional clauses and implementation checks are available. **No complete classical mortality judgment, event-risk calibration or independent outcome validation has been completed.** Shared birth inputs, calendar families and astronomy also prevent interpreting cross-system concurrence as independent votes. Astronomical accuracy establishes where a defined object is placed, not whether that placement forecasts a life event.

## 中文摘要

四个指定版本已具备排盘、选定动态周期和冻结结构指标，另实现 **14 条八字、5 条紫微条件规则**。29 项引擎测试及历史天文对照支持计算可复核，不支持现实预测有效。

关键缺口仍在：八字旺衰、格局、用神与合化救应未作完整裁决；紫微未实现全部格局和救应优先级；七政月孛是现代平远地点近似，命宫为离散宫位，未完成依命度行限；西方实现选定行运/次限流程。四者均没有完整古典寿命判断或死亡概率验证。应称“指定版本的结构研究”，不能称“完整四体系寿命预测已验证”。
