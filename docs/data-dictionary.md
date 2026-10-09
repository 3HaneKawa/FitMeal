# 数据字典

> **写入规则：任何新增 / 修改都走 `scripts/data_store.py`（HTTP 侧是 `POST /data/*`，命令行是 `scripts/add_data.py`），不要手工编辑 `data/*.csv`。**
> 写库层会保持 BOM / 行尾 / 列序 / 列名不变并原子写入；字段级录入说明见 `docs/data-entry-guide.md`。

## recipes.csv

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 食谱唯一 ID |
| name | string | 菜名 |
| region | string | 地域标签 |
| goal | string | 适合目标 |
| servings | int | 份数（这份食谱做出来够几人吃） |
| serving_weight_g | float | 每份可食部分重量（克），**现算缓存**（见文末「营养缓存」） |
| nutrition_basis | string | 营养数值基准（如「每份」） |
| cooking_time | int | 制作时间，单位分钟 |
| difficulty | string | 难度 |
| ingredients | string | 食材和克数，分号分隔；食材使用**标准名**（见文末「食材标准名与别名」） |
| steps | string | 制作步骤，分号分隔 |
| calories | float | 热量 kcal，**现算缓存** |
| protein_g | float | 蛋白质，**现算缓存** |
| fat_g | float | 脂肪，**现算缓存** |
| carbs_g | float | 碳水，**现算缓存** |
| fiber_g | float | 纤维，**现算缓存** |
| tags | string | 标签 |
| allergens | string | 过敏原 |
| missing_tolerance | string | 可缺失食材 |
| substitutes | string | 替换建议 |
| source | string | 数据来源 |
| notes | string | 注意事项 |

## nutrition.csv

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 食材 ID |
| name | string | 食材名 |
| category | string | 类别 |
| unit | string | 基准单位，**统一为 `100g`**；本表所有营养值均按每 100g 计 |
| calories | float | 每 100g 热量（kcal） |
| protein_g | float | 蛋白质 |
| fat_g | float | 脂肪 |
| carbs_g | float | 碳水 |
| fiber_g | float | 纤维 |
| allergens | string | 过敏原 |
| substitutes | string | 可替代食材 |
| source | string | 数据来源枚举：`usda_fdc` / `cn_food_composition` / `local` |
| source_ref | string | 来源编号：USDA 为 `FDC:<fdc_id>`，中国食物成分表为 `CFCT6:<编码>` |
| source_name | string | 来源可读名称（USDA 为英文条目名，成分表为对应条目名） |
| confidence | string | 可信度分级 `L1` / `L2` / `L3`，定义见 `docs/data-governance.md` §2.1 |
| verified_at | string | 最近一次核对日期（YYYY-MM-DD） |

> 来源字段口径：`source` 表示数据从哪来，`source_ref` 表示可回查的编号，`confidence` 表示可信度等级（L3 权威可引用 / L2 参考估算 / L1 内部整理 / L0 无来源）。LLM 与知识库都**不得改写或补造**这些字段；溯源分支直接透传本表的值。

## eat_out_foods.csv

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 外食 ID |
| name | string | 菜品类型 |
| region | string | 地域 |
| suitable_goals | string | 适合目标 |
| order_strategy | string | 点餐策略 |
| risk_notes | string | 风险提示 |
| calorie_range | string | 热量区间 |
| tags | string | 标签 |
| source | string | 数据来源枚举：`reference_estimate`（标准份量模型估算，当前 50 条全为该项）/ `brand_official`（品牌官方，后续） |
| source_ref | string | 来源编号；当前为 `CFCT6+DG2022`（成分表 + 膳食指南口径） |
| source_name | string | 估算方法与口径说明 |
| confidence | string | 可信度分级，当前全为 `L2` |
| verified_at | string | 最近一次核对日期（YYYY-MM-DD） |

> 50 条均为品类级菜品（潮汕牛肉锅、冒菜…），无官方 SKU 可对，因此采用「标准份量模型」估算并标 L2；品牌级 L3 需联网核对官方营养表，列为后续项。

## goal_rules.csv

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| goal | string | 健身目标（每个目标一条通用规则） |
| calorie_min | int | 最低热量 |
| calorie_max | int | 最高热量 |
| protein_min | float | 最低蛋白 |
| fat_max | float | 最高脂肪 |
| carbs_min | float | 最低碳水 |
| carbs_max | float | 最高碳水 |
| description | string | 规则说明 |

## substitutions.csv

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 替换规则 ID |
| original | string | 原食材 |
| substitute | string | 替代食材 |
| reason | string | 替换理由 |
| nutrition_change | string | 营养变化（当前为定性描述） |
| applies_to | string | 适用目标 |
| source | string | 数据来源；当前全为 `rule_derived`（由 `nutrition.csv` 每 100g 差异推导） |
| source_ref | string | 来源编号；定性规则暂无外部编号，留空 |
| source_name | string | 推导口径说明 |
| confidence | string | 可信度分级，当前全为 `L2` |
| verified_at | string | 最近一次核对日期（YYYY-MM-DD） |

## ingredient_aliases.csv

把食谱 / 用户口语里的写法归一到 `nutrition.csv` 的标准名，供计算层解析食材。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| alias | string | 别名（食谱或用户可能写出的叫法，如「蒜蓉」「剩饭」） |
| standard | string | 标准名，**必须能在 `nutrition.csv` 里查到** |
| note | string | 备注（为什么归到这个标准名） |

## unit_conversions.csv

把「个 / 瓣 / 张 / 半根」这类非重量单位换算成克。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| unit | string | 单位（个 / 张 / 瓣 / 半根 / 根 / ml …） |
| ingredient | string | 限定到具体食材；留空表示通用默认值 |
| grams | float | 1 个该单位对应的克重 |
| note | string | 备注 |

查找顺序：①「原始写法 + 食材」（如 `半个柠檬`）→ ②「单位 + 食材」（如 `个 + 鸡蛋`）→ ③ 通用默认（如 `个 = 50g`）。`ml` 按 1ml ≈ 1g 处理。

## target_ingredients.csv

补数据的**施工单**：列出必须优先覆盖的食材、目标道数与当前道数，达标后仍保留；供 `scripts/coverage_report.py` 输出各优先级的达标进度与剩余缺口。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| ingredient | string | 食材标准名，**必须能在 `nutrition.csv` 查到** |
| category | string | 主料 / 辅料（由 `nutrition.csv` 的类别映射而来） |
| priority | string | P0 / P1 / P2。P0 = 评测集出现过且覆盖不足；P1 = 健身高频或营养库有但 0 道菜用；P2 = 点缀与风味辅料，不设硬目标 |
| target_recipes | int | 目标覆盖道数：主料 5 道，辅料 3 道 |
| current_recipes | int | 当前覆盖道数的**快照**，由 `scripts/check_target_ingredients.py` 与实际数据比对 |
| reason | string | 为什么进清单 |
| note | string | 备注（同名易混、过敏原、是否低优先等） |

清单**保留全部目标项**作为稳定的目标覆盖台账：`current_recipes < target_recipes` 时列入缺口，达标后仍留在表中用于追踪达标进度。校验与缺口报告：

```powershell
uv run --python 3.12 python scripts/check_target_ingredients.py   # 校验清单本身
uv run --python 3.12 python scripts/coverage_report.py            # 第 5 节输出达标进度
```

> `current_recipes` 是缓存快照，改完食谱要重跑校验脚本对齐；本文件无 BOM、LF 行尾。

## eval_cases.csv

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| case_id | string | 评测 ID |
| user_input | string | 用户输入 |
| expected_intent | string | 预期意图 |
| expected_goal | string | 预期目标 |
| expected_ingredients | string | 应识别食材 |
| expected_time | int | 预期时间 |
| expected_region | string | 预期地域 |
| expected_recommendations | string | 可接受推荐 ID |
| expected_behavior | string | 预期行为 |
| severity | string | 严重度 |
| forbidden_items | string | 禁止内容 |
| pass_rule | string | 通过规则 |
| grader | string | 评分方式 |
| notes | string | 备注 |

---

## 来源底座（`data/sources/`）

存放可复现的**来源原始数据与映射表**，供脚本回查与重建，不直接参与推荐计算。

| 文件 | 内容 | 生成 / 使用脚本 |
| --- | --- | --- |
| `sources/fdc_index.csv` | USDA FoodData Central 条目索引（fdc_id、描述、公开发布日期、营养值） | `scripts/source_authority.py` 等 |
| `sources/ingredient_sources.csv` | 食材标准名 → USDA fdc_id 的映射与匹配质量 | 同上 |
| `sources/cfct/cfct_index.csv` | 《中国食物成分表 标准版（第6版）》条目索引（food_code、食物名、可食部比例、营养值） | `scripts/cn_food_composition.py build` |
| `sources/cfct/raw_json/`、`raw_json_foodwake.json` | 成分表原始 JSON（按类别合并） | 采集产物，随索引一起存档 |
| `sources/cn_food_composition.csv` | 食材标准名 → 成分表条目的映射（`apply_mode=cfct` 覆盖 / `keep` 保留） | `scripts/cn_food_composition.py apply` 读入 |
| `sources/eat_out_portion_model.csv` | 外食「标准份量模型」逐菜组成（主料 / 主食 / 蔬菜 / 烹调油 + 克重） | `scripts/estimate_eat_out.py apply` 读入 |
| `sources/raw/` | USDA 官方 CSV 解压件（SR Legacy / Survey 等），仅本地留档、体积大 | 人工下载，不参与构建 |

> 这些是**执行底稿**，只读；改动 `data/*.csv` 的正式数据一律走 `scripts/data_store.py`。来源分级与替换流程见 `docs/data-governance.md`。

---

## 食材标准名与别名（归一化）

数据表里的食材一律用**标准名**书写（如「虾仁」「米饭」「番茄」）。归一化分两层做，两层共用同一张词表：

| 层 | 位置 | 作用 |
| --- | --- | --- |
| LLM 层 | `prompts/parameter_extractor.md`「食材归一化（重要）」小节 | 在参数抽取节点把用户口语（大虾→虾仁、剩饭→米饭）转成标准名后再写入 `ingredients` |
| 计算层 | `data/ingredient_aliases.csv` + `scripts/nutrition_calc.py` | 兜底：不论来源是食谱还是 LLM，解析食材前都再过一遍同一张别名表 |

配套规则：

- 右列（标准名）必须是 `data/nutrition.csv` 里真实存在的食材名，`scripts/validate_data.py` 会强制校验。
- 只作用于 `ingredients`；`flavor_preference` / `original_ingredient` 等字段保留用户原话。
- 数量、重量、形容词、来源描述（「昨晚的」「半个」）不进食材数组。
- 计算层再加一道**最低食材匹配门槛**：用户给了食材时，一种都没命中的食谱直接跳过；推荐项用 `matched_ingredients` 记录实际命中的食材。

> 两层词表必须同步：新增别名时同时改 `data/ingredient_aliases.csv` 与 `prompts/parameter_extractor.md`，然后跑 `scripts/validate_data.py` 与 `evals/eval_cases.csv` 回归。

## 营养缓存（recipes.csv 的营养列）

`recipes.csv` 里的 `serving_weight_g` 与 5 个营养列（`calories` / `protein_g` / `fat_g` / `carbs_g` / `fiber_g`）**不是事实来源**，只是「`ingredients` × `nutrition.csv`」现算结果的缓存，方便直接读表与人工浏览。

- 唯一事实来源：`data/nutrition.csv`（每 100g 营养）。
- 计算代码：`scripts/nutrition_calc.py` 的 `compute_ingredients()`。
- 刷新缓存：`uv run --python 3.12 python scripts/regen_recipe_nutrition.py`。
- `scripts/validate_data.py` 会强制校验缓存与现算结果一致（容差 0.05），不一致直接 FAIL。

因此：改动 `ingredients` 或 `nutrition.csv` 后必须重跑刷新脚本，**不要手改营养列**。
