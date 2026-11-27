# R13 · 可用于独立复现的出生资料筛查

筛查目标是找到巴西、墨西哥之外的近代实际出生资料，同时具备逐行的公历年月日、出生钟点、出生发生地和记录性别。发生地要足以匹配地点与历史时区。来源还须允许本地研究及汇总发布。登记表曾经采集的字段与公开文件提供的字段分别核对。以下判断针对所列版本或目录。

| 候选来源 | 查到的可用内容 | 对四体系研究的处理 |
| --- | --- | --- |
| 哥伦比亚 DANE 2023、2024 出生微数据 | 当胎的出生年月、发生地和性别。完整公开变量表没有当胎出生的日或钟点。`FECHA_NACM` 指上一胎。 | 不把上一胎日期拼接到当胎资料。[2023 字典](https://microdatos.dane.gov.co/index.php/catalog/876/data-dictionary/F35?file_name=nac2023) · [2024 字典](https://microdatos.dane.gov.co/index.php/catalog/878/data-dictionary/F46) |
| 危地马拉 INE 公开出生簿 | 公开档案有出生日期、地点、性别及其他变量。2023 官方发布变量清单未列出生钟点。 | 无法按现有逐行时钟输入评分。[数据入口](https://datos.ine.gob.gt/es/dataset/estadisticas-vitales-nacimientos) · [2023 变量清单](https://sen.ine.gob.gt/wp-content/uploads/2024/01/Caracteristicas-Generales-de-las-Estadisticas-que-produce-el-INE-2023-1.pdf) |
| 哥斯达黎加 INEC 2023 | 公开出生文件列有 50,205 条记录和 52 个变量。字典有年月日；未见独立的出生钟点字段。 | 可用于核对登记日期范围。完整评分缺时钟。[NACI2023 字典](https://sistemas.inec.cr/pad5/index.php/catalog/379/data-dictionary/F2?file_name=NACI2023) |
| 智利 DEIS | 公开出生数据字典列有出生年月日和性别。地理字段及分娩地点类型有定义，字典没有出生钟点。 | 不以出生当日其他时间字段补钟。[公开出生库字段](https://repositoriodeis.minsal.cl/BDPublica/EsquemaRegistroNacimientos.pdf) |
| 美国 CDC/NCHS 2024 | 公用文件列 `DOB_TT`、年月和星期几，缺精确日及州县发生地。含精确日和更细地理的文件分别受限。 | 公开版无法唯一还原个体时空。受限出生资料路径需正式申请。[2024 布局](https://ftp.cdc.gov/pub/health_statistics/nchs/dataset_documentation/DVS/natality/UserGuide2024.pdf) · [访问说明](https://www.cdc.gov/nchs/nvss/nvss-restricted-data.htm) |
| 台湾地区出生通报及公开数据平台 | 卫生主管部门提供公开聚合表。受控 `Health09` 的公布字典列新生儿性别、出生年月和发生地县市乡镇。 | 已核公开资源没有所需逐行字段。已查的受控通报档也缺新生儿生日和钟点。[通报说明](https://www.hpa.gov.tw/EngPages/Detail.aspx?nodeid=1059&pid=6056) · [公开聚合表](https://data.gov.tw/dataset/101883) · [受控通报档说明及字典](https://dep.mohw.gov.tw/dos/fp-2503-9547-113.html) · [去识别字段清单](https://ghd.tw/Home/Datasets_card?result=Key_9) |
| 日本人口动态统计 | 原统计与基于 1995–2013 年的实证论文给出按小时、日期和分娩场所类别归组的出生数。 | 可独立研究日内分布。该聚合资料没有逐行分钟和发生地坐标，无法按当前口径重建四体系命盘。[e-Stat 出生月日及小时表](https://www.e-stat.go.jp/stat-search/database?statdisp_id=0003411915) · [观察研究](https://pmc.ncbi.nlm.nih.gov/articles/PMC5112194/) |
| 韩国 MDIS | 出生申报示范表含时分。微数据门户列出 1997–2024 年出生调查，并公布 2025 年微数据再提供消息。 | 目录和采集表不足以确认可用发布版保留个体时分与精确发生地，暂列候选。[出生申报官方示例](https://www.bokjiro.go.kr/ssis-tbu/cms/pc/news/promotion/__icsFiles/afieldfile/2021/08/12/160583920385278.pdf) · [MDIS 数据目录](https://mdis.mods.go.kr/ofrData/selectOrgOfrData.do) |
| 巴拉圭 DIGIES | 生命事件登记手册要求在出生证明填时刻。公开目录中尚未核实有同时提供所需字段的出生记录档案。 | 保留候选，等可访问的字段清单或实际档案。[官方手册](https://digies.mspbs.gov.py/wp-content/uploads/2024/05/Resolucion-2024-0046-Manual-de-normas-y-procedimientos-de-los-hechos-vitales.pdf) · [公开目录](https://digies.mspbs.gov.py/datos-abiertos/) |

R8 已使用更早的 Open Gauquelin 欧洲和美国记录，以及 Astro-Databank 按姓氏抽取的目录样本。它们可用于检查计算适用范围。其年代、选择方式和既往使用情况限制了作为近代独立出生登记队列的用途。上述筛查尚未取得合格的第三地新队列。[R8 来源覆盖](../../../data_expansion/README.md)
