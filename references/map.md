# 资料地图

| 要找的内容 | 文件或命令 |
|---|---|
| 书目、版本、页码和缺页 | reading.md → 三本 *-coverage.md；三本 *-source.json |
| 已核查外部资料（日期、地区、出版者、网址及小节） | external-sources.json |
| 主张与限定 | cn-claims.jsonl、ada-claims.jsonl、harvard-claims.jsonl、external-claims.jsonl |
| 中英同义词、重要差别 | glossary.jsonl；检索概念可用其中英文或别名 |
| 实体与图 | entities.jsonl 与 graph.jsonl（生成索引）；relations.jsonl（人工维护的冲突、支持、补充或时间替代） |
| 来源不同或依据不足的情况 | evidence.md、relations.jsonl 与 gaps.md；查单条也会反查关联讨论 |
| 按情境选餐 | planning.md、recipes.jsonl、foods.json、substitutions.jsonl；tests/field-cases.md 有虚构验收菜单 |
| 更新与验收 | changes.jsonl、../tests/verify.py 及 validation.md |
| EPUB 食谱出处 | harvard-recipes.jsonl；有原文件时可用 ../scripts/read_harvard.py --help 查看按段取回方式 |

命令从技能目录运行。例：`python3 scripts/graph.py search 'whole grains'`；`python3 scripts/graph.py search 进餐 --population 老年`；`python3 scripts/graph.py conflicts 酒`；`python3 scripts/graph.py show EXT-031`。多条件可先分别查 `备孕` 和 `过敏`，然后逐成员交叉核实。无匹配时扩大用词或移除筛选，转查地区机构。

菜谱可用 `python3 scripts/kitchen.py card R04`，净用量合并用 `python3 scripts/kitchen.py shop R01 R04 R07`。计算器使用见 `../assets/nutrition-input.json` 和 `python3 scripts/kitchen.py nutrients 文件路径`。它处理输入的已知成分数值；没有收录通用食物成分数据库。

来源、主张、菜谱和关系各有独立 ID。实体 ID 由规范名称生成；同义词归并、重大身份变化须保留旧名称及变更记录。claim 的 subject / object 保留原可读表述。图中的 subject、object、来源、人口、场景、食谱依据与原料对应到实体或记录；限定数量、风险、日期及证据类型随主张读取。术语表中标记为“相关但不同”的词仅扩展理解，不能自动换算。示例和用户反馈独立于科学主张。

按食材查替换用 `python3 scripts/graph.py swap 牛奶`，查原书和自拟食谱用 `python3 scripts/graph.py recipes 虾`，查原食谱定位用 `python3 scripts/graph.py show HAR-R001`。应用设计主张见 application-claims.jsonl，其中每条的 links 均指向组成证据。方案检索加 --for-plan；原书历史争议可用 conflicts 和 show 回看。中国指南的图表位置另见 cn-visual-index.jsonl。
