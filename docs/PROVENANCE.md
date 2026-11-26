# Provenance and licensing boundaries

This record separates original research code, executable dependencies, historical definitions, and reference evidence. It does not change the repository's `LICENSE`. It was compiled from frozen method/source records, installed dependency metadata and licence files, and the cited primary or official sources; no real-person profiles, live signal distributions or outcomes were read for this document.

## 1. Original project code and dependency use

Original project engine adapters, explicit structural scores, bounded interpretive clauses, tests and audit scripts are distributed under **AGPL-3.0-or-later** through the repository licence; many source files also carry SPDX notices. Their parameters are research definitions, not quotations of a universally accepted traditional scoring system. The repository licence does not relicense upstream packages, third-party records, scans or modern editorial material.

| Dependency | Installed version / role | Licence observed in installed distribution | Primary record |
|---|---|---|---|
| `lunar-python` | **1.4.9**; Bazi calendar, hidden-stem/ten-god tables and selected `Yun` computation | **MIT**, copyright 6tail | [Repository](https://github.com/6tail/lunar-python); [Yun source](https://github.com/6tail/lunar-python/blob/master/lunar_python/eightchar/Yun.py) |
| `iztro` | **2.6.5**; Ziwei chart, transformation/brightness tables and cycle objects | **MIT**, copyright All Contributors | [Repository](https://github.com/SylarLong/iztro); [versioned package](https://www.npmjs.com/package/iztro/v/2.6.5); [official documentation](https://docs.iztro.com/en_US/quick-start) |
| `pyswisseph` | **2.10.3.2**; Python wrapper and bundled Swiss Ephemeris **2.10.03** used by Qizheng/Western | Distribution includes **GNU AGPL version 3** | [Wrapper project](https://astrorigin.com/pyswisseph); [Swiss official manual](https://www.astro.com/swisseph/swephprg.htm) |
| Swiss Ephemeris | Explicit **Moshier** backend, geocentric apparent tropical positions, houses and axes | Upstream documents **AGPL or a separate professional licence**; this project uses the open-source route | [Official technical/licensing description](https://www.astro.com/swisseph/swisseph.htm) |
| `astronomy-engine` | **2.1.19**; independent astronomical comparison only, not the primary scoring ephemeris | **MIT**, copyright Don Cross | [Official Python reference](https://github.com/cosinekitty/astronomy/blob/master/source/python/README.md) |

Observed Node runtime dependencies were `dayjs 1.11.23`, `i18next 23.16.8`, `lunar-lite 0.2.9`, `lunar-typescript 1.8.7`, and `@babel/runtime 7.29.15`; their installed package metadata declares **MIT**. The resolved installation and lockfile, where supplied, govern reproducibility; upstream semver ranges alone do not pin these versions. These are runtime observations, not claims that those versions are the latest.

Preserve upstream licence/copyright notices when redistributing dependency code. Original project code being AGPL does not remove those notices or imply that a proprietary Swiss Ephemeris licence was purchased. No commercial ephemeris service, private account or paid reference database is needed by these engines. External Swiss/JPL planetary ephemeris files and downloaded fixed-star catalogues are not used by the frozen primary calculation.

### Shared ancestry affects independence

`lunar-python` and `lunar-typescript` share the 6tail calendar family; the latter is part of the Ziwei dependency chain. Qizheng and Western share Swiss Ephemeris and several physical luminaries. These are real provenance dependencies: agreement between systems is not four independent replications of either calendars, astronomy or event prediction.

## 2. Historical definitions and extraction boundaries

| System | Definition sources | What was incorporated |
|---|---|---|
| Bazi | [*Gengcunji* month-command text](https://www.shidianguji.com/book/NCL06599A/chapter/1lystjkljywij); [*Sanming Tonghui* luck-period context](https://www.shidianguji.com/book/SK1610/chapter/1kf5v6ol1vhnp) | Bounded, attributed operational clauses and context. Transmitted attribution is not treated as settled; the primary clash fraction is a project definition. |
| Ziwei | [*Ziwei Doushu Quanshu*, volume 3](https://zh.wikisource.org/wiki/紫微斗數全書/卷三) | Five conditional clause groups, retaining brightness, cross-cycle and rescue qualifications. Library placement rules remain the pinned iztro version. |
| Qizheng | [*Qing Shi Gao*, Shixian Zhi 6](https://www.shidianguji.com/zh/book/LS0025/chapter/1kt95er1advsv); [*Tianwen Suanxue Zuanyao*, volume 5](https://www.shidianguji.com/book/CADAL02032854/chapter/1l6xxrk89hica) | Four-point definitions, Zi Qi epoch/rate, and winter-solstice numerical origin. Modern lunar-node and apogee choices are explicitly distinguished from the historical algorithms. |
| Qizheng | [*Huangchao Tongzhi* full 1744 mansion table](https://www.shidianguji.com/zh/book/SK1154/chapter/1l9l7p13m8oiq); [parallel transcription](https://zh.wikisource.org/wiki/皇朝通志_(四庫全書本)/卷019); [precession rule](https://www.shidianguji.com/zh/book/SK1154/chapter/1l9l7p300kgf7) | All 28 numerical boundaries and 51 arcsec/year rule. Shen/Wing discrepancies with another primary source remain recorded. |
| Qizheng | [*Xingxue Dacheng*, volume 4](https://zh.wikisource.org/zh-hans/星學大成_(四庫全書本)/卷04); [full text with fixed-period verse](https://zh.wikisource.org/zh-hant/星學大成_(四庫全書本)/全覽); [*Shendao Dabian Xiangzong Huatian Wuxing*, volume 8](https://www.shidianguji.com/book/CADAL02093863/chapter/1lazcaitic9be) | Selected palace/ruler and fixed-period conventions, and 10/7/4 contact weights. No exhaustive classical adjudication is claimed. |
| Western | [Astrodienst chart description](https://www.astro.com/faq/fq_fh_owtype_i.htm); [secondary directions](https://www.astro.com/astrowiki/en/Secondary_Directions) | Day/year progression and explicit Naibod-axis convention. The primary actor sets, orbs and weights are disclosed project choices. |

The underlying historical works and their modern hosts are different provenance layers. The project records source URLs and attributable numerical facts/rule interpretations; it does not claim ownership of source texts or a blanket licence over the hosts' modern editions, annotations or translations. Modern site terms and source-specific attribution remain distinct from the project code licence. No full modern commentary or commercial book was imported into the engines.

## 3. Verification material

**Bazi golden examples.** Eight examples derive from the author's [EightChar tests](https://github.com/6tail/lunar-python/blob/master/test/EightCharTest.py). The fetched fixture's SHA-256 is recorded in [`bazi_ziwei_dependencies.json`](bazi_ziwei_dependencies.json). This is MIT-licensed upstream implementation evidence, not an independent almanac or empirical prediction test.

**Independent formulas and synthetic fixtures.** Day-cycle arithmetic, Ziwei life/body formulas, house geometry, boundaries and ambiguous/rescue cases are explicitly constructed checks. Synthetic fixtures are marked as such and must not be counted as sampled people or observed outcomes.

**1833 primary almanac.** The National Library of China item [*Da Qing Daoguang 13 Qizheng Jingwei Chandu Shixianshu*](https://commons.wikimedia.org/wiki/File:NLC892-411999011532-17590_大清道光十三年七政經緯躔度時憲書.pdf), shelfmark 05525, is available as a faithful scan with the Commons public-domain scan designation. Only the used reference pages **40 and 41**, their factual transcription, source URLs and numerical comparisons are included. The whole downloaded PDF is not republished in this repository. Its SHA-1 matches Commons' published `5e73b15f44961340f2813e2b6fddc939615453ac`; SHA-256 and the exact download URL are in [`1833_reference.json`](engine_validation/1833_reference.json).

Discovery credit goes to the [lhttjdr/calendar Qizheng research notes](https://lhttjdr.github.io/calendar/docs/folk/qizheng), which identified the useful 1833 pages. The original pages were subsequently downloaded and visually checked directly. Its code was not incorporated, and Zi Qi's phase was not fitted to its published comparison. Source discovery does not convert that project into an independently validated forecasting authority.

**Astronomy checks.** [`astronomy_comparison.json`](engine_validation/astronomy_comparison.json) records 50 comparisons with Astronomy Engine and both nominal-UT and matched-TT differences. This is numerical astronomy verification; it does not establish the interpretive meaning of a chart.

## 4. Freeze, changes and reproducibility

The controlling records are [`bazi_ziwei_protocol.json`](../protocol/bazi_ziwei_protocol.json), [`bazi_ziwei_interpretive_clauses.json`](../protocol/bazi_ziwei_interpretive_clauses.json), [`bazi_ziwei_implementation_seal.json`](../protocol/bazi_ziwei_implementation_seal.json), [`qizheng_western_protocol.json`](../protocol/qizheng_western_protocol.json), and [`qizheng_western_freeze.json`](../protocol/qizheng_western_freeze.json). They distinguish frozen scoring definitions from implementations and record that engine construction did not inspect real-cohort signals.

Upstream documentation and `master` links may change. The recorded installed versions, resolved dependency records and archived hashes identify the actual research implementation; a live link alone does not freeze it.

Recorded pre-cohort corrections include retaining an incorrectly assumed unique Bazi pattern as an ambiguity fixture and correcting Ziwei ZWC05's dynamic-life-palace scope. They did not change primary scores. Qizheng/Western compact-mode optimization omits unused detailed enumeration while preserving all primary components; equality with detailed mode is tested. No additional scoring edits were made for this provenance/readiness compilation.

Source cohort records and derived person-level files have their own provenance, privacy and redistribution boundaries. **Public accessibility does not make all data AGPL or public domain.** This document grants no additional data rights and does not establish global sampling representativeness; consult the cohort acquisition and release manifests for those matters.

## 中文摘要

原创引擎与审计代码采用项目既有 AGPL 声明；lunar-python、iztro 及其所列 Node 依赖为 MIT，pyswisseph/Swiss 使用开源 AGPL 路线。原典事实、现代转录、历史扫描、测试样例和真实队列数据分别保留来源与许可边界，不能由项目代码许可一并覆盖。

八字与紫微共享部分历法来源，七政与西方共享天文引擎，因此不属于四次独立预测复现。原页核验和星历误差检查支持计算溯源，不支持寿命或现实事件预测有效。本说明未读取真实个人信号，未更改评分或 `LICENSE`。
