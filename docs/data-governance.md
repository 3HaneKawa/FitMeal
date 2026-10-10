# 数据治理与版本规范

> 阶段：E2 配套文档
> 日期：2026-10-06（2026-10-07 更新 §2.2 / §2.3 / §3）
> 上位文档：`docs/PRD.md` §4.2 F4 / F12、`docs/data-dictionary.md`、`docs/evaluation-plan.md`
> 相关工具：`scripts/data_version.py`、`scripts/validate_data.py`、`scripts/data_entry.py`、`scripts/data_store.py`、`scripts/add_data.py`、`scripts/refresh_target_ingredients.py`、`scripts/coverage_report.py`

## 1. 目的与适用范围

本文件回答三个问题：

1. 当前数据**从哪来、可信度多高**（来源分级）。
2. 数据**怎么改、改完怎么验、怎么留痕**（扩充与替换流程）。
3. 重新填写或替换数据后，**评测结果会不会失效、怎么处理**（版本与断言隔离）。

适用范围：`data/` 下的全部 CSV（营养、食谱、外食、替换规则、目标规则、别名、单位换算、目标食材清单）及其对评测、推荐、解释链路的影响。

核心原则：

- **营养事实必须来自可引用来源**；食谱可以由 LLM 起草，但必须过规则校验。
- **数据只增不改口径**：换来源是「重新标注 + 版本升级」，不是「悄悄改数字」。
- **一次运行对应一个版本**：任何评测结果都必须能追到当时的 `data_version`。

## 2. 数据来源分级

### 2.1 分级定义

| 等级 | 名称 | 判定标准 | 可否作为营养事实 | 典型处置 |
| --- | --- | --- | --- | --- |
| L0 | 无来源 | 记录里没有 `source` 字段或字段为空 | ❌ 不能对外声称权威 | 补来源标注；优先级最高的治理债 |
| L1 | 内部整理 | 由项目内人工按经验整理 / 从公开食谱改写 | ⚠️ 仅可内部自测 | 逐步替换为 L2/L3 |
| L2 | 参考估算 | 参考公开资料估算，有来源类型但未逐条引用 | ⚠️ 可作 dev 基线 | 标注依据，向 L3 迁移 |
| L3 | 权威可引用 | 来自可查证的标准数据源（见 §5） | ✅ 可作为事实来源 | 作为最终验收基线 |

### 2.2 各表现状映射（2026-10-07 快照）

| 数据表 | 行数 | 是否带 `source` | 当前等级 | 现状说明 |
| --- | ---: | --- | --- | --- |
| `data/nutrition.csv` | 159 | ✅ | **L3 为主** | `usda_fdc` 120（USDA FoodData Central）、`cn_food_composition` 21（《中国食物成分表 标准版 第6版》，带 `CFCT6:<编码>`）、`local` 18；按 `confidence` 计 L3 138 / L2 20 / L1 1（仅「温水」全 0，无需外部来源） |
| `data/recipes.csv` | 208 | ✅ | L1 | `curated` 120、`coverage_gap_2026_10` 78、`expansion_2026_10` 9、`api_entry` 1；列内营养为**缓存**，非事实源 |
| `data/eat_out_foods.csv` | 50 | ✅ | **L2** | `reference_estimate`/L2：按「标准份量模型」（主料 + 主食 + 蔬菜 + 烹调油，份量取《中国居民膳食指南 2022》，营养值取 `nutrition.csv` 的 L3 值）重算 `calorie_range`；品牌级 L3 列为后续项 |
| `data/substitutions.csv` | 30 | ✅ | L2 | 已补 5 个来源列，`rule_derived`/L2，依据「营养库差异推导」 |
| `data/goal_rules.csv` | 3 | ➖ | L3（指南锚定） | 区间改由公开营养指南锚定（中国居民膳食指南 2022 能量占比 / ISSN 每餐蛋白下限 / 脂肪供能比≤35%），不再单靠食谱分布校准 |
| `data/ingredient_aliases.csv` | 24 | ❌ | L0/L1 | 别名映射，靠语言习惯整理，无权威性要求 |
| `data/unit_conversions.csv` | 19 | ❌ | L0/L1 | 单位换算，靠常识与包装标注重量 |
| `data/target_ingredients.csv` | 48 | ➖ | — | 施工单，不是营养事实来源；`current_recipes` 为按食谱实时统计的派生列，改食谱后需用 `scripts/refresh_target_ingredients.py` 刷新 |

> 说明：**唯一营养事实源是 `data/nutrition.csv`（每 100g）**。`recipes.csv` 的 `serving_weight_g` 与 5 个营养列是缓存，由 `scripts/nutrition_calc.py` 现算、`scripts/validate_data.py` 强制对齐（容差 0.05），禁止手改。

### 2.3 已知治理债（按优先级）

1. `nutrition.csv` 仍有 20 条 L2（`local`，已由 41 条降到 20 条）：河粉 / 魔芋 / 魔芋丝 / 紫薯（干湿基或品种口径不符）、全麦饺子皮 / 全麦饼 / 杂粮米 / 杂粮馒头 / 凉粉（复合加工品无条目）、黄酒 / 沙茶酱 / 豆瓣酱 / 豆豉 / 甜面酱 / 麻辣酱 / 黄酱 / 叉烧酱 / 龙井茶叶 / 醋 / 辣椒油（该书数字版未收录调味品 / 酒 / 茶）；需另找权威源逐条转正。
2. `eat_out_foods.csv` 50 条为品类级菜品，已按「标准份量模型」升到 L2（`reference_estimate`）；若要 L3，需在能联网核验时对到连锁品牌官方营养表。
3. `substitutions.csv` 的 `nutrition_change` 为定性描述，L2；若要对用户强承诺，应绑定 `nutrition.csv` 的定量差异。
4. 目标区间已改为指南锚定（见 §5），但「指南数值 → 每餐区间」的换算仍是项目自定口径，需在文档中持续标注为「工程换算」而非临床标准。

## 3. 版本机制

运行 `uv run --python 3.12 python scripts/data_version.py` 得到三个哈希版本号：

| 版本号 | 覆盖文件 | 含义 |
| --- | --- | --- |
| `data_version`（`dv-…`） | recipes / nutrition / eat_out_foods / ingredient_aliases / unit_conversions / target_ingredients | 数据内容指纹 |
| `rules_version`（`rv-…`） | goal_rules / substitutions | 规则内容指纹 |
| `bundle_version`（`bv-…`） | 以上两组 | 数据 + 规则整体指纹 |

当前（2026-10-09）：

- `data_version = dv-a3345d800862`
- `rules_version = rv-ecedb1a359c3`
- `bundle_version = bv-a3e6abe13870`

规则：

- 任何 `data/*.csv` 变更都会改变对应版本号；**不手动维护版本号**，一切以哈希为准。
- 每次评测运行必须记录当次的 `bundle_version`（或 `data_version` + `rules_version`）。
- 版本号相同 = 结果可复现；版本号不同 = 差异必须能归因到具体变更。

## 4. 数据扩充流程

**单类型变更的标准流程**（顺序不可省）：

1. **准备**：把新增内容写成批次文件（`scripts/add_data.py --template` 生成带注释模板），不要直接编辑 CSV。
2. **试跑**：`uv run --python 3.12 python scripts/add_data.py --check batch.json` —— 在数据副本上真实试跑，原始数据零改动，可处理批内先后依赖。
3. **落库**：`uv run --python 3.12 python scripts/add_data.py --regen batch.json` —— 走 `scripts/data_store.py` 原子写入，保持 BOM / 行尾 / 列序 / 列名不变，自动生成主键。
4. **重算缓存 / 派生列**：改食谱后执行 `uv run --python 3.12 python scripts/regen_recipe_nutrition.py`（或 `--regen` 已包含）；再执行 `uv run --python 3.12 python scripts/refresh_target_ingredients.py` 同步 `data/target_ingredients.csv` 的 `current_recipes` 派生列。
5. **全量校验**：`uv run --python 3.12 python scripts/validate_data.py` 必须全 PASS。
6. **回归**：跑 `scripts/run_eval_set.py --cases evals/eval_set.csv`，确认没有新增回归；同时关注 `coverage_report.py` 的覆盖变化。
7. **记录版本**：在提交说明和评测摘要中写明新的 `bundle_version`，并说明改了什么、为什么。

> 铁律：**所有写入必须走 `scripts/data_store.py`**，不要手工编辑 `data/*.csv`。手改会破坏行尾 / 列序，且绕过校验。

## 5. 营养来源替换流程

把 `human_estimated` / `reference_estimate` 逐步替换为 L3 权威数据时：

1. **建立映射**：权威源食材名 → 本地标准名（先过 `ingredient_aliases.csv`）。映射不上的食材列入待补清单，不强行凑。
2. **双算对比**：同一食材，旧值 vs 新值并排计算每 100g 差异（热量 / 蛋白 / 脂肪 / 碳水 / 纤维）。
3. **差异报告**：输出差异表，标注相对偏差 >10% 的条目，人工复核。
4. **分批替换**：按食材类目（肉蛋 / 蔬菜 / 主食 / 乳制品…）分批替换，**不一次性全表替换**，便于回滚与归因。
5. **重新校准目标规则**：营养值变更后，`goal_rules.csv` 的区间与新食谱分布可能失配，必须**重新校准**并记录新旧区间。
6. **版本升级**：替换 + 校准完成后，`bundle_version` 自动变化；把旧版本结果归档，新版本重新建立基线。

> 可选权威源（需逐个确认授权与使用条款）：USDA FoodData Central、《中国食物成分表》标准版第 6 版、连锁品牌官网营养表。禁止直接抓取未授权站点。

## 5A. 本轮数据升级方案（2026-10-07）

> 目标：解决 §2.3 的第 1、2 项治理债——外食 50 条 L1 与营养库 41 条 L2。

### 5A.1 中国食物成分表（第6版）接入方案（营养库 L2→L3）

**目标**：把 `data/nutrition.csv` 里 `source=local` / USDA 近似的中式食材，换成
《中国食物成分表 标准版（第6版）》第一册「能量和食物一般营养成分」的每 100g 可食部值，
逐条升到 L3；口径不符或该书未收录的，如实保留 L2，**不强行凑**。

**数据底座**（本地内部资料，不随公开仓库提供）：

- 原始索引和人工映射保存在本地 `internal/` 资料区，不作为公开仓库文件。
- 公开数据表只保留已经核验后的来源字段和版本记录。
- 来源说明：数值转录自开源数字化项目 `Sanotsu/china-food-composition-data`（对原书表格做
  双模型交叉识别 + 恒等式 / 值域校验，并附原始截图）。本项目仅转录数值，著作权归原书作者；
  索引与映射作为可追溯引用一并保留。

**规则**：

1. 只覆盖每 100g 可食部的 5 个营养列 + 5 个来源列；列名 / 列序 / 单位 / 行尾保持原样（`data_store.py` 原子写入）。
2. `apply_mode=cfct`：用食物成分表值覆盖营养列，`source=cn_food_composition`、`source_ref=CFCT6:<编码>`、`confidence=L3`。
3. `apply_mode=keep`：口径不符或未收录，保留本地数值，只更新 `source_name`（写明原因）与 `verified_at`，`confidence` 维持 L2/L1。
4. `report` 标出相对偏差 >10% 的条目，逐条人工复核后才 `apply`。
5. 替换后必须执行 `regen_recipe_nutrition.py` → `refresh_target_ingredients.py`。

**本次口径结论**：

- 该书数字化版只覆盖基础食物，**不含调味品、酒、糖、茶**，也不含复合加工品（全麦饺子皮 / 饼、杂粮米 / 馒头、凉粉）。
- 干基 vs 湿基必须区分：书中「河粉」（79.2g 碳水/100g）为干基，与项目湿河粉不符；书中仅「魔芋精粉」（干基）与项目鲜魔芋不符 → 均 `keep`。
- 品种差异：书中甘薯仅红心 / 白心两档，与「紫薯」差异大 → `keep`。

**本轮执行结果（2026-10-07）**：本地映射底稿共 39 条——21 条替换为 `cn_food_composition`/L3（`source_ref` 形如 `CFCT6:047104`），18 条如实保留 L2/L1（含全 0 的「温水」仍 L1）。`nutrition.csv` 的 `confidence` 由 L3 117 / L2 41 / L1 1 变为 **L3 138 / L2 20 / L1 1**；`source` 变为 `usda_fdc` 120 / `cn_food_composition` 21 / `local` 18。替换后 `regen_recipe_nutrition.py` 重算 208 条营养缓存（最大热量偏差 55.8 kcal），`refresh_target_ingredients.py` 刷新施工单（无变化）。

### 5A.2 外食菜品来源升级方案（L1→L2）

**现实**：50 条是「品类级菜品」（潮汕牛肉锅、冒菜、麻辣拌…），不是某家门店的 SKU，
多数无法对到连锁品牌官方营养表。因此按三档处置：

1. **品牌官方可核** → `source=brand_official`、`source_ref=<品牌>#<页面/产品>`、`confidence=L3`。
2. **标准化中式主食 / 小吃** → 锚定《中国食物成分表 第6版》对应条目，`source=reference_estimate`、`confidence=L2`。
3. **纯品类级菜品** → 按「标准份量模型」估算：主料 + 主食 + 蔬菜 + 烹调油，用量取《中国居民膳食指南 2022》份量口径，营养值取 `data/nutrition.csv`（L3 值），`source=reference_estimate`、`source_name` 写明方法与口径、`confidence=L2`。

**约束**：不得编造品牌或页面；品牌级 L3 只在真能核到官方页面时写。
本次在离线环境下无可核品牌页，50 条统一按第 3 档「标准份量模型」升到 L2（营养值取自已升 L3 的 `nutrition.csv`，`source_ref=CFCT6+DG2022`），并把「品牌级 L3」列为后续项。

## 6. 评测隔离与数据敏感度

### 6.1 断言类型（`assertion_type`）

| 类型 | 含义 | 是否随数据版本变化 |
| --- | --- | --- |
| `capability` | 能力型：意图、参数、推荐是否用到用户食材、是否说明缺失食材 | ❌ 必须跨版本稳定 |
| `safety` | 安全型：S1–S5 是否按规范过滤 / 拦截 | ❌ 必须跨版本稳定 |
| `ranking` | 排序型：Top3 相对顺序 / 多样性 | ⚠️ 可能随候选池变化 |
| `data_sensitive` | 数据敏感型：具体营养数值区间 | ✅ 随版本重算基线 |
| `format` | 格式型：份数 / 每份重量 / 营养基准 / 无 think 无代码块 | ❌ 必须跨版本稳定 |
| `not_ready` | 未完成能力占位；F10 当前仍有 12 条对话式反馈用例未就绪 | ➖ 能力完整实现并重新验收后再转正；最小事件记录不能替代 |

### 6.2 数据敏感度（`data_sensitivity`）

| 取值 | 说明 |
| --- | --- |
| `invariant` | 与数据无关，跨版本必须稳定（如意图、别名归一化、安全拦截） |
| `low` | 弱依赖数据，只验证结构 / 语义 |
| `medium` | 依赖候选池，允许 Top 排序漂移 |
| `high` | 强依赖具体数值，重填数据后必须重算基线 |

### 6.3 隔离规则

1. `dev`（开发调参集）与 `holdout`（只读验收集）分列，holdout 不用于调参。
2. `invariant` 用例**跨数据版本必须保持通过**；若重填数据后失败，先判定是「数据改坏了事实」还是「实现回归」，不能直接改期望值。
3. `data_sensitive` / `high` 用例**按版本重建基线**：记录新 `data_version` 下的实测值作为期望，而不是判为回归。
4. 每条用例都带 `data_version` 列；版本不同即视为**不同基线**，不可直接横向比较通过率。

## 7. 禁止事项

1. 手工直接编辑 `data/*.csv`（绕过 `data_store.py` 与校验）。
2. 静默修改阈值 / 目标区间 / 评分权重而不留版本记录。
3. 用「同一批数据反推规则，再用同一批数据验收」——会造成循环验证。
4. 因为实现做不到，就放宽规则、改期望值或删除用例。
5. 让 LLM 直接生成营养数值并作为事实落库。
6. 在同一份评测摘要里混用不同 `data_version` 的结果而不标注版本。

## 8. 重新填写数据会影响评测吗？

**会有影响，但可控**——关键是把断言分成两类：

- **能力型（`capability` / `safety` / `format` / `invariant`）**：必须跨数据版本稳定。重填数据后如果这些失败了，说明**事实被改坏或实现回归**，要修数据或修实现，**不能改期望值**。
- **数据敏感型（`data_sensitive` / `high`）**：期望值本就绑定当时的数据。重填后**重新测、重新记基线**即可，不算回归。

所以正确的做法不是「怕影响所以不改数据」，而是：

1. 每次改数据都产出一个新的 `bundle_version`。
2. `data_sensitive` 用例按新版本重算基线；`invariant` 用例必须仍然通过。
3. 结果与版本号一起归档，形成「版本 → 指标」趋势，而不是一堆无法比较的数字。

这样重填数据既能持续提升准确性，又不会让历史评测失去意义。
