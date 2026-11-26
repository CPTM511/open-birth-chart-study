# Frozen Bazi and Ziwei methods (R8)

## What is ready

The selected natal, decadal and yearly calculation pipelines run reproducibly. The implementation also evaluates **14 Bazi conditional clauses and 5 Ziwei conditional clauses**, preserving ambiguity, adverse conditions and possible rescue conditions together. It does **not** implement a complete traditional adjudication of strength, pattern priority, useful elements, transformations, rescue effectiveness or lifespan. No output is a death forecast or a probability of an event.

The distinction matters: implementing every chart field does not validate an interpretation. The two primary scores below are deliberately narrow, frozen structural observables. Agreement between systems would show agreement between these declared observables; it would not establish that the original rumor is true.

## Input and clock contract

The engines accept a Gregorian `birth_local` including a clock, birth years 1880–2019, and recorded `sex` or `sex_resolved` equal to `M` or `F`. Sex is required solely by the selected traditional cycle-direction rules. Missing values cause abstention; no sex or clock is guessed.

Bazi additionally requires a source absolute instant or a source offset. Accepted offset fields are `source_offset_seconds`, `utc_offset_seconds`, and `timezone_offset_minutes`. When local time, an instant and an offset are all supplied, their disagreement must not exceed one second. Original labels are preserved. Geography is not used to invent a timezone.

- **Bazi year/month and starting luck period:** the same supplied instant expressed in UTC+08:00, because the pinned calendar's solar-term tables use that reference.
- **Bazi day/hour:** the supplied civil clock. The declared day boundary is 23:00 (`EightChar` sect 1).
- **Ziwei:** the supplied local Gregorian date and civil two-hour bin are mapped through the pinned Chinese-calendar implementation. This is an explicitly selected convention for foreign births, not a claim of universal traditional agreement. A late-Zi hour advances the effective date (`dayDivide: forward`).
- **Clock perturbations:** a supplied shift changes both civil and absolute labels by the same amount in Bazi, and the civil label in Ziwei. Perturbation size is a study sensitivity setting, not an asserted measurement error.
- **Annual snapshot:** July 1 at 12:00. Bazi uses the birth source offset as the snapshot reference offset; this does not model the person's subsequent location or future daylight-saving rules. The engines accept a year list; the analysis chooses completed ages 20–59. A snapshot is not continuous coverage of its calendar year.

Nominal historical UT labels are accepted as supplied. The code does not manufacture second-level historical accuracy or correct an uncertain clock. Municipality coordinates and geocoding precision do not affect these two primary scores under the civil-clock convention.

## Bazi implementation

`lunar-python==1.4.9` supplies the sexagenary calendar and starting-period calculation. The engine exports all four pillars; hidden stems; visible and hidden ten-god relations; na-yin; twelve growth phases; xun and empty branches; natal pair relations; starting luck direction and full timestamp; and 24 explicit ten-year intervals. The starting-period calculation uses `Yun` sect 2: minute intervals to the relevant solar term are converted under the three-days-to-one-year convention. Ten-year boundaries are exact calendar anniversaries of that returned timestamp, rather than integer birth-year bins.

The annual and active decadal pillars are compared with each of four natal pillars. The **primary score** is:

\[
S_{BZ}(y)=\frac{1}{8}\sum_{p\in\{\text{annual, decadal}\}}\sum_{n\in\{\text{year, month, day, hour}\}} I\{p\text{ and }n\text{ have opposite branches}\}.
\]

The denominator stays eight; repeated natal branches count as separate pillar comparisons. Before birth or outside the supported decadal interval, the result is missing, not zero. Stem control/combination, six harmonies/harms, complete trines, specified punishments, repeated pillars and simultaneous stem-control/branch-clash are exported separately. A trine is not automatically declared transformed.

### Conditional interpretation

The source family is the month-command chapters in the public transcription of [*Gengcunji*](https://www.shidianguji.com/book/NCL06599A/chapter/1lystjkljywij), related to *Ziping Zhenquan*. The source explicitly qualifies seasonal strength with roots and the rest of the chart, distinguishes combinations that do and do not take effect, and presents formation, damage and rescue as conditional. The project does not assert a settled attribution for every transmitted passage.

The declared selector uses the month branch's main hidden stem for 子午卯酉; otherwise it uses a uniquely exposed month-hidden stem, the main hidden stem if none is exposed, or an unresolved result if several are exposed. The day stem itself is excluded from exposed candidates. A full trine involving the month is flagged as transformation-dependent. Peer-command and yang-blade months require further functional selection. This selector is a declared operational subset, not a textual claim that all cases have a unique answer.

The 14 executable clauses cover bounded officer/damage/resource-rescue, wealth/robbery mediation, eating-god/indirect-resource interference, seven-killings/eating-god control and its counterconditions, hurting-officer exceptions, yang-blade containment, and peer-command formation contexts. Each result carries applicability and unresolved prerequisites. Annual and decadal stems add context; they never replace the natal month command.

Two safeguards are deliberate:

1. **Classical strength and a unique effective yongshen remain unadjudicated.** Roots, growth phases, seasonal element and visible support are exposed as evidence. The separate weighted-element tally is labeled a researcher-defined annotation and never decides these classical clauses.
2. **Rescue does not erase damage automatically.** Candidate harmonies, trines and resources remain visible alongside the original condition. Placement, strength and competing combinations can leave the final interpretation unresolved. A clause's structural match must be read with `applicable_pattern_unambiguous` and `unresolved_premises`.

The word `yongshen` here refers to the month-command functional-role vocabulary. It is not silently equated with a modern universally favorable balancing element.

## Ziwei implementation

`iztro@2.6.5` is pinned with `yearDivide=normal`, `horoscopeDivide=normal`, `ageDivide=normal`, `dayDivide=forward`, `algorithm=default`, `fixLeap=true`, and the package's unmodified transformation/brightness tables. The full config is in the frozen protocol.

The engine exports the twelve palaces, life/body placements, fourteen major stars, subsidiary and adjective stars, brightness, natal transformations and auxiliary twelve-star cycles. Dynamic output includes decadal and annual palace maps, four transformations and transit stars. Detailed mode also exposes the library's minor-age, monthly, daily and hourly cycle objects at the snapshot; those are not additional primary endpoints.

For each scope, the transformed natal star is located in the fixed natal chart and assessed against that scope's life and health palace positions. The **primary score** is:

\[
S_{ZW}(y)=\frac{I\{\text{annual Hua Ji in annual life/health}\}+I\{\text{decadal Hua Ji in decadal life/health}\}}{2}.
\]

Its possible values are 0, 0.5 and 1. The reference chart is explicit: this is not a tally of any occurrence of a word such as “death” in a chart. Every transformation target must be uniquely located, and both scope maps must be complete; otherwise the computation abstains.

### Conditional interpretation

[*Ziwei Doushu Quanshu*, volume 3](https://zh.wikisource.org/wiki/紫微斗數全書/卷三) supplies the selected textual contexts. Its decadal, repeated-Yang/Tuo and repeated-Qisha passages also mention brightness, multiple cycles and mitigating stars. Those qualifications are retained instead of interpreting one named star as a sufficient event prediction.

The five executable clauses report favorable decadal-life premises, adverse conditions coinciding across cycles, Qisha with yearly Yang/Tuo in life-palace surroundings, natal/transit Yang/Tuo duplication, and mixed support/adversity within each dynamic life palace. The Qisha clause preserves temple/prosperity status and Ziwei/Tianxiang/Lucun surroundings as mitigation/rescue context. The adverse-cycle clause reports the specified longevity-star context separately. No ungrounded numeric cancellation or exhaustive priority rule is imposed. Unspecified phrases such as “many beneficial stars” remain unresolved.

## Validation and limits

The frozen implementation passed **18 unittest methods** before real-cohort signal inspection. Covered cases include eight author-published Bazi golden charts, independent day-cycle arithmetic and the 23:00 boundary, the same solar-term instant represented in four offsets, minute-based starting-period conversion, contiguous decadal intervals, missing-input abstention, ambiguous-pattern and rescue counterexamples, 26 independent Ziwei life/body formula cases, the 2026 transformation targets, forty annual snapshots, and three Node runtime timezones.

The original seven-killings test fixture exposed two competing month-hidden stems. Its expectation of a unique pattern was wrong. The fixture is retained as an ambiguity test, and a separate unique-month fixture tests the control/rescue clauses. The implementation was not tuned to make the original mistaken expectation pass. Before cohort execution, ZWC05 was also corrected to examine each dynamic life palace separately, matching the already frozen clause rather than pooling life and health contexts. Neither correction changed a primary score.

These are software and convention checks. Author-maintained golden examples are not independent historical almanac validation. Life/body and day-cycle formulas independently check only their own components. No complete expert adjudication of all chart modules, traditional schools, historical calendar practices or actual outcomes has been performed. See `bazi_ziwei_readiness.json`, the validation record and the implementation seal for the exact boundary of completion.

## Reproduction

```python
from open_birth_chart.bazi_engine import build_natal, annual_signals
from open_birth_chart.ziwei_engine import ZiweiEngine

birth = {
    "study_id": "synthetic_example",
    "birth_local": "2000-08-16T12:00:00",
    "source_offset_seconds": 28800,
    "sex": "F",
    "calendar": "gregorian",
}
natal = build_natal(birth)
bazi_2026 = annual_signals(natal, 2026)
with ZiweiEngine() as engine:
    ziwei = engine.compute(birth, range(2021, 2061), include_chart=True, detailed=True)
```

Both modules expose `build_natal(birth)` and `annual_signals(natal, year)`. The latter returns `primary_score`, `status` and `components`. A persistent `ZiweiEngine` avoids creating a Node process per person or per year. With a nonstandard Node installation, set `OBS_NODE_MODULES` to the directory containing `iztro`; otherwise normal Node package resolution applies. Compact mode preserves scores and matched clause IDs; use detailed mode for conditional applicability, ambiguity and rescue context.

### Official implementation sources

- [lunar-python repository](https://github.com/6tail/lunar-python)
- [Yun implementation](https://github.com/6tail/lunar-python/blob/master/lunar_python/eightchar/Yun.py)
- [EightChar author tests](https://github.com/6tail/lunar-python/blob/master/test/EightCharTest.py)
- [iztro quick start](https://docs.iztro.com/en_US/quick-start)
- [iztro horoscope documentation](https://iztro.com/en_US/posts/horoscope)
- [iztro 2.6.5 package](https://www.npmjs.com/package/iztro/v/2.6.5)

## 中文结论与完成边界

本轮完成了指定版本的八字四柱、起运、大运流年及紫微命身宫、主辅星、四化、大限流年计算，并实现 **14 条八字、5 条紫微的有出处条件规则**。18 项软件测试通过，规则及代码在查看真实队列信号前封存。

尚未完成的是全部传统旺衰、格局优先级、用神定夺、合化有效性和救应成败的统一裁决。程序保留“原始条件成立”“同时存在救应候选”“月令选择有歧义”等不同信息，允许结论未定。加权五行计数只是研究者的描述性变量，不冒充古典旺衰结论。

主要指标仍是狭义结构量：八字为流年／大运与本命的六冲配对比例；紫微为流年／大限化忌落入对应命宫或疾厄宫的两个指示量均值。它们不是死亡概率。四体系同时偏高，也只能说明这些预先定义的指标同时偏高，不能据此推断某代人会集中死亡。7 月 1 日是年度快照，不代表全年每个时点均已检验。

因此，可准确报告“指定排盘与动态结构指标已实现，部分原典条件判断已实现”；不能报告“完整四体系寿命预测已经验证”。死亡盲测在本轮暂停。
