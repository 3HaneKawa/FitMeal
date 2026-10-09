# 数据录入指南（快速补数据）

> 状态：v1
> 更新时间：2026-10-06
> 适用范围：本地数据服务 `server/` 的 `/data/*` 接口、命令行批量导入 `scripts/add_data.py`

## 1. 这份文档解决什么

项目目前最大的瓶颈**不是营养库准不准，而是菜谱太少**：142 种食材里有 53 种（37.3%）只出现在 1–2 道菜里，最高频的组合也只有 14 道。用户一说冷门食材，候选池就空了。

> 进展（2026-10-06）：`data/target_ingredients.csv` 的 48 项优先目标已 **48/48 达标**，食谱 121 → 199 → 208（2026-10-07 权威化扩充）；下面的接口继续用于补「全量食材密度」和后续新增数据。

所以这里提供一套**快速补数据的入口**，让你能持续往库里加：

- 菜谱（recipes）
- 食材营养成分（nutrition，每 100g）
- 外出饮食（eat_out）
- 食材别名（aliases）
- 单位换算（units）

两种用法，按场景选：

| 场景 | 用哪种 |
| --- | --- |
| 一次加几条、想马上看到结果 | HTTP 接口（`POST /data/*`），返回 JSON，可配表单或脚本 |
| 批量导入（几十上百条）、先试跑再落库 | 命令行 `scripts/add_data.py` |

### 三条铁律

1. **营养不接受传入**。加菜谱时你只写「用了什么、多少克」，热量 / 蛋白 / 脂肪 / 碳水 / 纤维全部由 `scripts/nutrition_calc.py` 按 `data/nutrition.csv` 现算，杜绝手填错数。
2. **只走专用写入层**。所有落库都经过 `scripts/data_store.py`，它保证不破坏原有的 BOM、行尾、列顺序。**任何时候都不要用记事本或 Excel 直接改 `data/*.csv`**。
3. **改完要重算**。新增或修改菜谱后，跑一次重算（`POST /data/regen` 或 `add_data.py --regen`），把 `recipes.csv` 里的营养缓存对齐。

## 2. 接口一览

服务地址：`http://127.0.0.1:8765`（本机）/ `http://host.docker.internal:8765`（Dify 容器内）。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/data/schema` | 查看各表的文件名、列名、当前行数、ID 前缀 |
| POST | `/data/nutrition` | 新增一条食材营养（每 100g） |
| POST | `/data/recipes/preview` | **只试算不落库**：算出每份营养与食材拆解给你看 |
| POST | `/data/recipes` | 新增一条菜谱（营养现算） |
| POST | `/data/eat_out` | 新增一条外出饮食 |
| POST | `/data/aliases` | 新增一条食材别名（口语 → 标准名） |
| POST | `/data/units` | 新增一条单位换算（个 / 瓣 / 根 → 克） |
| POST | `/data/import` | 批量导入（数组，每条的 `table` 决定写哪张表） |
| POST | `/data/regen` | 重算全部菜谱的营养缓存 |

统一返回格式：

```json
{ "ok": true, "result": { } }
```

失败时返回：

```json
{ "ok": false, "error": { "code": "invalid_payload", "message": "……" } }
```

**录入类接口只有在 `ok: true` 且带 `created` / `id` 字段时，才算真的写进去了。**

## 3. 字段说明

### 3.1 食材营养 nutrition（每 100g）

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| name | 是 | 食材标准名，要和菜谱 `ingredients` 里的写法一致 |
| category | 否 | 分类，如 `vegetable` / `meat` / `staple` |
| unit | 否 | 默认 `100g` |
| calories | 是 | 每 100g 热量（kcal） |
| protein_g / fat_g / carbs_g / fiber_g | 否 | 每 100g 三大营养素与膳食纤维（g），缺省按 0 |
| allergens | 否 | 过敏原，多个用分号分隔，无则写「无」 |
| substitutes | 否 | 可替换食材，多个用分号分隔 |
| source | 否 | 数据来源，建议写 `manual_entry` / `USDA` / `中国食物成分表` |

> 注：表中只有 `source` 可经本接口录入；`source_ref` / `source_name` / `confidence` / `verified_at` 不由本接口写入，由来源替换与校验脚本（`scripts/source_authority.py`、`scripts/cn_food_composition.py`）维护，具体口径见 `docs/data-dictionary.md`。

### 3.2 菜谱 recipes

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| name | 是 | 菜名，默认不允许重名（重名会报错） |
| goal | 是 | `fat_loss` / `muscle_gain` / `maintain` |
| region | 否 | 通用 / 川渝 / 粤式 / 江浙 / 北方，也接受城市名（如「成都」→ 川渝） |
| servings | 否 | 份数，默认 1 |
| cooking_time | 否 | 制作时间（分钟） |
| difficulty | 否 | 难度，如「简单」/「中等」 |
| ingredients | 是 | 配方，写法见下 |
| steps | 否 | 步骤，数组或分号分隔字符串 |
| tags | 否 | 标签，如「高蛋白;快手菜」 |
| allergens | 否 | 过敏原，多个用分号分隔 |
| notes | 否 | 备注 |
| allow_duplicate | 否 | 传 `true` 才允许同名新增，默认 `false` |

**配方 ingredients 写法**：`食材名:用量`，多条用分号分隔。

```
"鸡胸肉:150g;秋葵:200g"
"鸡蛋:1个;牛奶:200ml"
```

- 食材名必须是 `data/nutrition.csv` 里的标准名（或能被别名表解析）。
- 用量支持克 / ml / 个 / 瓣 / 张 / 根 / 半根等；克与 ml 直接换算，其余靠 `data/unit_conversions.csv`。
- **不要写营养数值**——系统会算，写了也不采信。

### 3.3 外出饮食 eat_out

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| name | 是 | 菜品或品类名 |
| region | 否 | 同菜谱 |
| suitable_goals | 否 | 适用的目标，如「fat_loss;maintain」 |
| order_strategy | 否 | 点餐策略，如「少酱，多加鸡胸」 |
| risk_notes | 否 | 风险提示 |
| calorie_range | 否 | 热量区间，如 `300-500 kcal` |
| tags | 否 | 标签 |

### 3.4 食材别名 aliases

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| alias | 是 | 口语说法，如「大虾」 |
| standard | 是 | 必须已存在于 `nutrition.csv` 的标准名，如「虾仁」 |
| note | 否 | 备注 |

### 3.5 单位换算 units

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| unit | 是 | 单位，如「个」/「瓣」/「根」 |
| ingredient | 是 | 限定食材，如「黄瓜」（可不填，表示通用） |
| grams | 是 | 1 个该单位 = 多少克 |
| note | 否 | 备注 |

## 4. 完整示例

### 示例一：先加食材营养，再加用到它的菜谱

**第一步**，加一条食材（秋葵，每 100g）：

```powershell
$body = @'
{
  "name": "秋葵",
  "category": "vegetable",
  "calories": 33,
  "protein_g": 2,
  "fat_g": 0.2,
  "carbs_g": 7.5,
  "fiber_g": 3.9,
  "allergens": "无",
  "source": "中国食物成分表"
}
'@
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/data/nutrition `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

返回：

```json
{ "ok": true, "result": { "created": "I138", "name": "秋葵" } }
```

**第二步**，先试算这道菜（不落库），确认营养与食材拆解合理：

```powershell
$body = @'
{
  "name": "秋葵炒鸡胸",
  "goal": "fat_loss",
  "region": "上海",
  "servings": 1,
  "cooking_time": 15,
  "ingredients": "鸡胸肉:150g;秋葵:200g",
  "steps": ["鸡胸肉切块腌制", "秋葵焯水", "少油翻炒"],
  "tags": ["高蛋白", "快手菜"]
}
'@
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/data/recipes/preview `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

返回里会带：

- `nutrition`：每份热量 / 蛋白 / 脂肪 / 碳水 / 纤维
- `serving_weight_g`：每份克重
- `ingredient_breakdown`：每个食材贡献了多少克、多少热量、占比多少
- `goal_fit`：`{ passed, reasons }`，说明这道菜是否落在该目标的营养区间内

**第三步**，确认没问题再正式落库（把路径从 `/data/recipes/preview` 换成 `/data/recipes`）：

```json
{ "ok": true, "result": { "created": "R121", "name": "秋葵炒鸡胸" } }
```

### 示例二：批量导入 + 先试跑（推荐）

批量走命令行，**先试跑再落库**：

```powershell
# 1. 生成一份带注释的模板
uv run --python 3.12 python scripts/add_data.py --template batch.json

# 2. 只试跑：在数据副本上真实执行一遍（含批内先后依赖），原始数据零改动
uv run --python 3.12 python scripts/add_data.py --check batch.json

# 3. 正式导入，并顺手重算菜谱营养缓存
uv run --python 3.12 python scripts/add_data.py --regen batch.json
```

批量文件是一个 JSON 数组（或 `{ "items": [] }`），每条的 `table` 决定写哪张表：

```json
[
  { "table": "nutrition", "name": "秋葵", "category": "vegetable",
    "calories": 33, "protein_g": 2, "fat_g": 0.2, "carbs_g": 7.5, "fiber_g": 3.9 },

  { "table": "aliases", "alias": "牛油果", "standard": "鳄梨" },

  { "table": "units", "unit": "根", "ingredient": "黄瓜", "grams": 200 },

  { "table": "recipes", "name": "秋葵炒鸡胸", "goal": "fat_loss", "region": "上海",
    "cooking_time": 15, "ingredients": "鸡胸肉:150g;秋葵:200g",
    "steps": ["鸡胸切块腌制", "秋葵焯水", "少油翻炒"],
    "tags": ["高蛋白", "快手菜"] },

  { "table": "eat_out", "name": "轻食沙拉碗", "region": "上海",
    "suitable_goals": ["fat_loss", "maintain"], "order_strategy": "少酱，多加鸡胸",
    "calorie_range": "300-500 kcal", "tags": ["低脂"] }
]
```

退出码：`0` = 全部成功；`1` = 有失败条目；`2` = 文件或参数错误。脚本会逐条打印 OK / FAIL 与原因。

### 示例三：改完菜谱后重算营养缓存

不管用接口还是脚本加了菜谱，最后都跑一次重算：

```powershell
# 通过服务
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/data/regen `
  -ContentType "application/json" -Body "{}"

# 或直接命令行
uv run --python 3.12 python scripts/regen_recipe_nutrition.py
```

### 示例四：加别名（让口语能被认出来）

```powershell
$body = @'
{ "alias": "秋葵荚", "standard": "秋葵" }
'@
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/data/aliases `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

> `standard` 必须已经是营养库里的标准名，否则会返回 400。

## 5. 加完数据后必做的三件事

1. **重算营养缓存**：`POST /data/regen`（或 `add_data.py --regen`，导入时已自动做）。
2. **跑数据校验**：`uv run --python 3.12 python scripts/validate_data.py`，应全 PASS。
3. **看重算结果是否合理**：如果某道菜营养超出目标区间，`goal_fit.passed` 会是 `false` 并给出原因——这时应调整配方比例或改 `goal`，而不是放宽规则。

## 6. 常见错误

| 返回 | 原因 | 怎么办 |
| --- | --- | --- |
| 400 缺少必填字段 | 漏填必填项 | 对照第 3 节补上 |
| 400 必须是数字 | 营养或克重填了文字 | 检查是否填了文字或空值 |
| 400 未知食材 | 菜谱里写了库里没有的名字 | 先加 `nutrition`，或加 `aliases` 把它指到已有标准名 |
| 400 同名已存在 | 菜名重复 | 改名；确需再加时传 `allow_duplicate: true` |
| 400 standard 不存在 | 别名的目标标准名不在营养库 | 先加对应食材，或改指已有标准名 |
| 500 | 服务内部错误 | 看服务窗口日志；多为数据文件被外部占用或格式被破坏 |

## 7. 相关文档

| 文档 | 说明 |
| --- | --- |
| `docs/data-dictionary.md` | 各表的完整列定义 |
| `docs/api-contract.md` 第 8 节 | 数据录入接口的契约 |
| `docs/project-plan.md` 阶段二·补 | 数据扩充的目标与来源 |
| `scripts/coverage_report.py` | 补数据前后看覆盖度指标 |
