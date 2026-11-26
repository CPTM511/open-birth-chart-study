# 七政四余与西方占星：R8 的明确版本与核验 / Versioned methods and checks

## 结论与范围

R8 已实现两个可运行、可复算的指定流程：`OBS-R8-QZ-1.0` 与 `OBS-R8-WEST-1.0`。本命配置、年度时序、评分组成及未实现项目均由接口输出。**这证明的是计算流程完成程度，不是占星能预测现实事件，更不是死亡预测获得验证。**

七政版本采用清代宫宿表、紫炁公式与罗计命名，配合现代天文星历。月孛用现代月球平远地点，是明确的近似约定；清代「太阴最高实行」全部修正没有实现。运限选择《星学大成》古法固定年数版本；没有冒充已实现依命度调整童限的量天尺法。

西方版本包含十星本命、整宫制、主要相位、逐月行运、日年次限及 Naibod 推进的轴。没有把它称为所有西方流派的完整解释体系。

冻结参数见 [`qizheng_western_protocol.json`](../protocol/qizheng_western_protocol.json)，代码摘要见 [`qizheng_western_freeze.json`](../protocol/qizheng_western_freeze.json)。冻结前仅使用人工合成出生与历史天文表，没有打开真实队列出生文件或观察其信号分布。

## 1. 输入和共同天文层

必需字段为 `birth_local`、明确的 `birth_utc` 或 `source_offset_seconds`、`latitude`、`longitude`，历法为 Gregorian。输入不能只有日期。由城市或国家猜时区、把未知钟点填成正午、在两种时间标签矛盾时任选一种，均不接受。源时间差大于一秒时报错。

计算固定为 `pyswisseph==2.10.3.2`（内部 Swiss Ephemeris `2.10.03`），显式请求 Moshier 星历并检查实际返回标志。没有把读取到的官网最新版本当成本地运行版本。采用地心视位置、当日黄道及春分点、回归黄道；未采用日心或 J2000 坐标冒充上述坐标。技术定义依据 Swiss Ephemeris 官方手册。[1]

历史时间和未来时间按源提供的名义 UT 输入。UTC 与 UT1 的精确差值、无法恢复的历史钟表误差没有被伪造；星历内部使用各自的 ΔT 模型。月球对时间模型尤其敏感，独立核验同时报告名义 UT 和统一 TT 两种比较。

每个年度在 12 个月的 15 日 12:00 UT 取样并作等权平均。这是明确的 12 点年度指数，不是全年所有瞬间的积分，也不保证捕获每一次短暂相位。出生纬度须严格位于两极之间；整宫制可计算高纬地区，但不能消除出生地点近似与出生钟点误差。

## 2. 七政四余的具体版本

### 2.1 十一曜与紫炁历元

| 对象 | 实现 | 边界 |
|---|---|---|
| 日、月、水、金、火、木、土 | 现代地心天文星历 | 与历史表格天文理论存在差别 |
| 罗睺 | 现代真升交点加 180° | 采用清代罗降、计升命名 |
| 计都 | 现代真升交点 | 现代真交点也不是清代全部交点修正算法 |
| 月孛 | 现代平远地点 | 明确不是「最高实行」原法的同义替换 |
| 紫炁 | 清代原典匀速虚点 | 不把紫炁当作实际天体 |

《清史稿·时宪志六》给出紫炁的历元、初相、日行量，并载四余取法。[2] 历元文字对应 **1743 年冬至次日子正**；甲子年天正冬至落在前一个公历年，不能误写成 1744 年 12 月。

另据《天文算学纂要》冬至星纪为初宫的坐标定义，原典 `7宫17°50′14″53微` 需要转换成现代春分点起算的黄经：[3]

\[
\lambda_0=(270^\circ+227.8374675925926^\circ)\bmod360^\circ
=137.8374675925926^\circ.
\]

以北京参考经度 116.4°E 的地方平时午夜明确重建，历元为 `JDUT 2358033.176666667`，即地方平时 `1743-12-23 00:00`。这项经度是声明的数值约定，不是声称古书提供了现代测地精度。日行量为 `126.720777` 角秒。绝对相位由上述原典导出，没有对 1833 年历书拟合。

### 2.2 宫、宿、躔度与运限

二十八宿使用《皇朝通志》卷十九「乾隆九年甲子测二十八宿宫度」的**完整不等宽表**，卷二十给出每年 51 角秒的岁差规则。[4][5] 表只指定年份，因此数值历元声明为 `1744-01-01 00 UT`；这项年内歧义对应不超过 51 角秒。该实现没有用 360/28 等分代替距星宿界。

十二宫采用中气黄道分宫：现代黄经 0–30° 为戌宫，黄经每增加 30°，地支逆行一位。命宫取「太阳宫加生时、卯上见命」的离散宫位规则，生时采用地方平时，不额外加均时差；命宫没有因此生成一个虚构的精确度数。太阴作为选定版本的身；宫主、宿主、行星宫度与宿度、五行生克关系、原守星所属十二宫、昼夜及顺逆行均保留。有关宫主与太阳立命的原典讨论也记录了流派分歧。[6]

大限采用明确的古法固定序列：命、相貌、福德、官禄、迁移、疾厄、妻妾、奴仆、男女、田宅、兄弟、财帛，年数依次为 `15,10,11,15,8,7,11,4.5,4.5,4.5,5,5`，合计 **100.5 年**。[7] 年龄用实际经过的回归年。此处的「百六」指百年零六月，不是任意延长到 106 周岁。超出所选周期范围返回缺失，不能解释成寿限。

小限从命宫起，每过一个公历生日逆一宫；二月二十九日的非闰年周年约定为二月二十八日。上述固定年数、生日交限、地方平时、宫主取法均是选定版本的组成部分。依命度调整童限、连续逐度行限及其他流派变体未混入。

### 2.3 年度研究指数

原典记录同宫、对照、三合的 10/7/4 分量，同时大量说明其解释受恩难、昼夜、季节和救应影响。[8] R8 只把其中可固定的结构转成研究量：同宫 `1`、对宫 `0.7`、三合 `0.4`、其他 `0`。

主指标对象集固定为火、土、罗、计、孛。每个月计算五个归一化组成项：原守对象对大限宫、原守对象对小限宫、流对象对大限宫、流对象对小限宫，以及流对象与本命日/月/命宫主星同宿的比例。年度 `primary_score` 为这五项各自 12 个月均值的等权平均。

金、木、气使用相同结构另报 `support_score`。它没有被任意转换为可抵消伤害的概率。若命主与日或月重合，相同位置保留其预先定义的角色权重，不称为独立证据。

这个主指标**没有实现原典所有条件化吉凶判断**。本命结构与运限流程齐备，不能推导出该简化指数就是完整古典命断，更不能推导出它具有现实预测效力。

## 3. 西方占星的具体版本

本命含日、月、水、金、火、木、土、天王、海王、冥王。宫制固定整宫制，另保留上升、天顶与 ARMC。五种主要黄经相位为合、六合、刑、拱、冲；本命容许度分别 `6°,4°,6°,6°,6°`。本命输出十星位置、宫位、顺逆行、七政传统守护/失势标记及相位表。

次限按 Astrodienst 官方说明的一日对应一年；Naibod 轴以每年 `0.98564733°` 加到本命 ARMC，再以出生纬度及次限日期的真黄赤交角重算。[9] 这清楚区分次限行星与轴的推进约定。数值实现为：

\[
t_p=t_b+\frac{t-t_b}{365.2422},\qquad
ARMC_p=ARMC_b+0.98564733^\circ\frac{t-t_b}{365.2422}.
\]

对行星 A 和目标 B，取黄经最小角距离 `d`。硬相位接触核为：

\[
K_\delta(A,B)=\max\left(0,1-\frac{\min_{\theta\in\{0,90,180\}}|d(A,B)-\theta|}{\delta}\right).
\]

目标固定本命日、月、上升、天顶。行运对象固定火、土、天王、海王、冥王，容许度 3°；次限对象固定日、月、水、金、火，容许度 1°；次限轴为上升和天顶，容许度 1°。分别平均各对象与各目标的接触核，再平均 12 个月。

\[
W=0.5\,T+0.25\,P+0.25\,A.
\]

其中 T 是行运接触，P 是次限行星接触，A 是次限轴接触。金、木行运与相同目标的合/六合/拱、3°容许度另报支持指标。**硬相位名称不表示已经观测到伤害，合相也不是普遍的凶象。**这个量是固定的几何接触定义。

完整年度导出 `include_details=True` 提供每月十星行运、十星次限及轴、宫位和相位详单。批量主运算只计算评分用的次限五颗行星，省略未用于评分的详单；测试确认二者的全部评分组成及主分数相同。

## 4. 实际核验结果与限制

| 核验 | 实际结果 | 能支持的结论 |
|---|---|---|
| 11 项风险针对性测试 | 全部通过 | 输入、几何、运限边界、次限映射、详简结果一致 |
| 两套天文引擎，十星 × 五日期 | 名义 UT 最大差 27.973″；统一 TT 后最大 11.832″ | 这些测试点的天文位置相符 |
| 1833 历书四余，每点 12 个日期 | 原页40逐项肉眼核对；页41核对子正起算 | 参考值、日期和时刻约定可审计 |
| 紫炁绝对相位 | 最大误差 0.573′，平均绝对误差 0.267′ | 排除现代黄经原点误置90°等重大错误 |
| 月孛平远地点 | 最大误差 34.851′，平均31.172′ | 这是近似实现，不能声称原法等价 |
| 月孛瞬时远地点敏感性 | 最大差 27.311°，平均9.406° | “平/真远地点”不能互换后仍声称同一模型 |
| 真罗/计与历史表 | 最大差22.037′ /23.037′ | 同样不能称清代交点算法的逐项复刻 |
| 12 个宫界跨原典检查 | 10个在25″以内；参差2′15″，翼差9′17″ | 原典版本冲突保留，未按样本结果修表 |

独立引擎为 Astronomy Engine `2.1.19`，坐标变换使用其官方定义。[10] 测试日期为 1880、1950、2000、2026、2070 年六月十五日；这些不是所有日期的误差上界。

误差数据、参考页、转录、原 PDF 下载地址及摘要均在 [`engine_validation/`](engine_validation/)。原 PDF 的 SHA-1 与 Wikimedia Commons 公布值相符；仓库只提供所用参考页，不整本再发布。复算脚本不会重写原始冻结记录。

跨体系一致性还受共同出生时间、历法、太阳周期和部分相同天文输入影响。多体系同时出现结构信号，不能当作几次独立的预测成功。本轮没有为任何真实死亡结局训练、测试或校准概率。

## English method summary

### Scope

The implemented versions are `OBS-R8-QZ-1.0` and `OBS-R8-WEST-1.0`. They are complete **within the declared calculation workflows**, with explicit exclusions. Neither is a complete collection of traditional interpretive doctrines. Implementation verification and historical astronomy checks do not establish real-world forecast validity. Independent mortality testing is outside this round.

Both require an explicit birth clock, a supplied absolute instant or offset, and coordinates. Date-only records and contradictory clocks are rejected. Swiss Ephemeris 2.10.03, through pyswisseph2.10.3.2, uses an explicitly requested Moshier backend and geocentric apparent tropical positions. Annual indices average twelve fixed snapshots, each month15 at12:00UT. This sampling is not continuous annual event detection.

### Qizheng

The physical seven luminaries use modern astronomy. Qing naming assigns the ascending true node to Jidu and its opposite to Luohou. Yuebo is explicitly approximated by the modern mean lunar apogee; the original Qing “true highest longitude” algorithm is not reproduced. An osculating-apogee variant is available as a separate sensitivity model.

Zi Qi uses primary-source epoch, phase and rate. The Qing numerical palace origin is the winter solstice,270° from modern tropical Aries. Its epoch longitude is consequently137.8374675925926°, not227.8374675925926°. The next Beijing local-mean midnight after the1743December solstice is JDUT2358033.176666667 using the declared116.4°E reference. No phase was fitted to the1833check data.

The entire unequal28-mansion table is transcribed from *Huangchao Tongzhi*, volume19, epoch1744, with its51arcsec/year rule from volume20. January1 of the stated year is a numerical epoch convention. Ten of twelve independently published palace-crossing anchors agree within25arcsec. Shen differs by2′15″ and Wing by9′17″; both source discrepancies remain disclosed, and the selected table is not tuned to cohort results.

Ming is a discrete Sun/hour/Mao palace rule using local mean solar time. A precise Ming degree is not fabricated. The selected major periods use the ancient fixed Dongwei durations totaling100.5years; degree-dependent childhood adjustments are not implemented. Minor periods advance one reverse palace per completed Gregorian birthday. Outside the major-period domain returns missing, never an inferred death or a zero score.

The primary is the equal mean of five normalized contact channels: natal actors with major/minor period palaces, transit actors with major/minor palaces, and transit actors sharing a mansion with natal Sun/Moon/Ming-palace ruler. Actor set: Mars, Saturn, Luohou, Jidu, Yuebo. Palace weights are1/.7/.4 for same/opposite/trine,0otherwise. Venus/Jupiter/Ziqi support is separately reported. This deliberately fixed structural statistic omits many conditional traditional judgments; it is not a canonical adverse-event probability.

### Western

The full chart includes ten planets, whole-sign houses, ascendant, midheaven, five major longitude aspects, monthly transits and secondary progressions. Secondary planets move one ephemeris day per365.2422elapsed days. Naibod axes advance natal ARMC by0.98564733degrees per elapsed tropical year, then recompute angles at the natal latitude.

The primary averages triangular proximity to0/90/180-degree separations. Targets are natal Sun, Moon, Ascendant and Midheaven. Transit actors are Mars, Saturn, Uranus, Neptune, Pluto with3-degree orbs. Progressed actors are Sun, Moon, Mercury, Venus, Mars with1-degree orbs; progressed Ascendant/Midheaven also use1degree. Weights are0.5transits,0.25progressed planets,0.25progressed axes. Supporting Venus/Jupiter contacts at0/60/120degrees are separate. These geometric definitions do not assert that all conjunctions or hard aspects are harmful.

Full monthly charts and aspect tables are available with `include_details=True`. Compact batch computation omits unused outer-planet progressions and detailed aspect enumeration; tests establish identical primary and component values.

### Verification and interpretation

Eleven tests pass. Fifty planet/date comparisons with Astronomy Engine2.1.19 differ by at most27.973arcsec under nominal UT and11.832arcsec with matching TT. The1833primary almanac yields maximum Zi Qi discrepancy0.573arcmin across12dates. Mean-apogee Yuebo differs by up to34.851arcmin; osculating Yuebo by up to27.311degrees. Those disagreements document model limits rather than being hidden by calibration.

The evidence supports reproducibility and bounded numerical checks. It does not establish that these systems predict mortality or other outcomes. Shared birth and astronomy inputs also prevent treating four systems as independent votes.

## API / Reproduction

```python
from open_birth_chart import qizheng_engine, western_engine

natal = qizheng_engine.build_natal(birth, shift_minutes=0, apogee_variant="mean")
annual = qizheng_engine.annual_signals(natal, 2026, include_details=False)

western_natal = western_engine.build_natal(birth)
western_full = western_engine.annual_signals(western_natal, 2026, include_details=True)
```

`annual` exposes `primary_score`, `components`, `support_score`, `version`, `status`. No outcome fields are required or read. Missing inputs raise an explicit error; unsupported period ranges return a missing score with a reason.

```bash
PYTHONPATH=src python -m unittest discover -s tests -p test_qizheng_western.py -v
PYTHONPATH=src python docs/engine_validation/reproduce_checks.py
```

## References

1. [Swiss Ephemeris Programmer's Manual](https://www.astro.com/swisseph/swephprg.htm) and [technical description](https://www.astro.com/swisseph/swisseph.htm).
2. [清史稿·时宪志六](https://www.shidianguji.com/zh/book/LS0025/chapter/1kt95er1advsv).
3. [天文算学纂要卷五](https://www.shidianguji.com/book/CADAL02032854/chapter/1l6xxrk89hica), numerical palace origin and winter-solstice mapping.
4. [皇朝通志卷十九](https://zh.wikisource.org/wiki/皇朝通志_(四庫全書本)/卷019), [parallel transcription](https://www.shidianguji.com/zh/book/SK1154/chapter/1l9l7p13m8oiq).
5. [皇朝通志卷二十](https://www.shidianguji.com/zh/book/SK1154/chapter/1l9l7p300kgf7), mansion-precession rule.
6. [星学大成卷四](https://zh.wikisource.org/zh-hans/星學大成_(四庫全書本)/卷04).
7. [星学大成](https://zh.wikisource.org/zh-hant/星學大成_(四庫全書本)/全覽), fixed-period verse; [volume3 period ordering](https://ctext.org/wiki.pl?chapter=733500&if=en).
8. [神道大编象宗华天五星卷八](https://www.shidianguji.com/book/CADAL02093863/chapter/1lazcaitic9be), contact weights and conditional interpretations.
9. [Astrodienst chart-type explanation](https://www.astro.com/faq/fq_fh_owtype_i.htm), [secondary directions](https://www.astro.com/astrowiki/en/Secondary_Directions).
10. [Astronomy Engine Python reference](https://github.com/cosinekitty/astronomy/blob/master/source/python/README.md).
11. [1833 primary almanac, National Library of China scan](https://commons.wikimedia.org/wiki/File:NLC892-411999011532-17590_大清道光十三年七政經緯躔度時憲書.pdf), pages40–41.

Discovery credit: the open `lhttjdr/calendar` research project's1833comparison identified the relevant almanac pages. The pages were then downloaded and visually checked directly; its implementation code was not incorporated.
