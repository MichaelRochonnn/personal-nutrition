# 个人健康饮食助手 · personal-nutrition

一个用简体中文工作的 Codex Skill。告诉它这顿饭给谁吃、有哪些忌口、能做多久，它可以安排菜单、列出每人份量和购物清单。想知道某条建议为何适用，也可以追问它来自哪本书、哪一页，或哪份指南。

## 安装与调用

1. 在 [v1.0.0 发布页](https://github.com/MichaelRochonnn/personal-nutrition/releases/tag/v1.0.0)下载附件 `personal-nutrition-1.0.0.zip`。
2. 解压，把整个 `personal-nutrition` 文件夹放入 Codex 用户技能目录。安装后的入口通常是 `~/.codex/skills/personal-nutrition/SKILL.md`。
3. 新开一个 Codex 聊天，输入 `$personal-nutrition`，接着描述你的需求。

例如，可以直接输入：

```text
$personal-nutrition 请安排两个人下周七天的晚餐。从洗切到上桌最多20分钟，
两个人的过敏和忌口请分别跟我确认。尽量复用食材，并列出购物清单。
```

也可以问“出差五天，酒店含早餐但没有冰箱，途中和晚餐怎么吃？”或“这两本书对喝奶有什么不同看法，各自说的是哪些人？”。[查看八个完整场景示例](tests/field-cases.md)

## 知识从哪里来

v1.0.0 收录 185 条有编号的主张。其中 148 条取自《中国居民膳食指南（2022）》、《食物保健书》和 *Eat, Drink, and Be Healthy*，31 条来自对外部资料的核对，6 条把多个来源的原则用于实际安排。每条记录都能查到适用人群、前提、限制和来源位置。书中观点有分歧时，可查双方的原意及选用理由。[逐书阅读记录](references/reading.md) · [资料地图](references/map.md) · [证据与更新方法](references/evidence.md)

## 适合怎样使用

- **做饭和买菜**　按人数、预算、厨具和可用时间安排一餐或一周，区分生重、熟重和可食部。换食材时再核对每个人的过敏及忌口。
- **家庭与生活阶段**　可为备孕伴侣设计共享菜谱，并分别核对与本人相关的事项。孕哺期、围绝经期和中老年阶段可调整一般饮食安排。
- **外食与记录**　可组合酒店早餐、便利店和餐馆餐食，用文字或照片复盘执行情况。照片看不出的油盐、配料和重量保留为未知。
- **查原方和依据**　仓库提供 13 套自拟餐食组合，以及 61 个英文原书食谱的位置索引。阅读完整原方需要对应版本的原书。

## 在本地查一条建议

在技能目录中使用 Python 3.9 或更新版本运行以下命令：

```sh
python3 scripts/graph.py search 无厨房 --for-plan --limit 3
python3 scripts/graph.py show APP-001
python3 scripts/graph.py conflicts 奶
```

第一条找适合纳入方案的候选主张，第二条展开来源和限定条件，第三条列出有关奶类的分歧。要检查自己的修改，可运行 `python3 scripts/graph.py validate` 和 `python3 -B tests/verify.py`。[验收记录](references/validation.md)

本项目用于日常健康饮食教育与规划。疾病治疗、药物调整和个体化高剂量补充方案由诊疗团队评估。仓库中的成员模板为空，示例人物为虚构。填写后的健康档案应保存在本人授权的私有位置。知识按调用需要复核；当前资料的覆盖与待核问题见[资料缺口记录](references/gaps.md)。
