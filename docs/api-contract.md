# 接口契约

> 状态：v0.11
> 更新时间：2026-10-10
> 适用范围：Dify Chatflow、本地数据服务与独立营养计算页的统一输入输出约定

## 1. 约定

1. 所有接口使用 JSON 传输，UTF-8 编码。
2. 聊天入口只有 `POST /chat`。浏览器不得直接调用 `/recommend`，也不得持有 Dify API Key；营养计算页是独立的确定性工具，不进入聊天链路。
3. LLM 节点的输出必须是可直接解析的 JSON，不允许夹带解释文字。
4. 缺失字段一律填 `null`，不编造用户未提及的信息。
5. 营养数值只能由 `scripts/nutrition_calc.py` 现算得出，事实来源是 `data/nutrition.csv`（每 100g）；LLM 与编排层都不得改写。

## 2. 客户端聊天接口（唯一前端入口）

### 2.1 `GET /chat/status`

用于前端和演示前检查 Dify 代理是否已配置，不返回 Token。

```json
{
  "ok": true,
  "configured": true,
  "provider": "Dify Chatflow",
  "timeout_seconds": 180.0
}
```

### 2.2 `POST /chat`

请求：

```json
{
  "query": "我有鸡胸肉、西兰花和鸡蛋，减脂，20 分钟内做完",
  "conversation_id": "",
  "user": "fitmeal-anonymous-user",
  "inputs": {}
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| query | string | 是 | 用户自然语言输入，最长 4000 字 |
| conversation_id | string | 否 | Dify 多轮会话 ID；首次请求为空，后续沿用返回值 |
| user | string | 否 | 匿名用户标识；当前存于浏览器 localStorage，不使用真实身份 |
| inputs | object | 否 | 预留给 Dify 应用变量的固定输入；当前前端传空对象 |

成功响应：

```json
{
  "ok": true,
  "answer": "Dify 返回的自然语言回答",
  "conversation_id": "dify-conversation-id",
  "message_id": "dify-message-id",
  "request_id": "本地生成的请求编号",
  "elapsed_ms": 26437.6,
  "metadata": {}
}
```

| 字段 | 说明 |
| --- | --- |
| answer | Dify Chatflow 最终回答；前端只展示该文本，不重新拼本地推荐 |
| conversation_id | 下一次请求继续多轮对话时回传 |
| message_id | Dify 消息编号，用于问题排查 |
| request_id | FitMeal 为本次端到端请求生成的编号，用于关联 `/feedback` |
| elapsed_ms | 浏览器到 Dify 再返回的真实端到端耗时，不是 `/recommend` 的毫秒级数据节点耗时 |
| metadata | Dify 返回的 token、模型耗时等元数据；缺少时不补造 |

错误：

| HTTP | error.code | 触发条件 |
| ---: | --- | --- |
| 400 | `empty_query` / `query_too_long` | 输入为空或超过 4000 字 |
| 502 | `dify_error` | Dify 未配置、不可连接、超时或返回异常 |
| 502 | `empty_answer` | Dify 返回成功但没有可展示回答 |

> 前端不会在 `/chat` 失败后调用 `/recommend` 生成替代答案。若要演示本地规则回归，必须单独明确标注，不能冒充 Dify 结果。

### 2.3 Dify 内部数据 payload

> 以下结构是 Dify 通过 HTTP 请求节点调用 `POST /recommend` 时使用的内部 payload，不是浏览器聊天请求。

```json
{
  "user_input": "我有鸡胸肉、西兰花、鸡蛋，练完背，想吃低脂但有点味道的，20 分钟内搞定",
  "goal": "fat_loss",
  "region": "generic"
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| user_input | string | 是 | 用户自然语言输入；`cook` / `eat_out` / `substitute` / `nutrition_analysis` / `provenance` 五类意图与安全风险标志均由 LLM 从这句话推断，请求体不再单列场景字段 |
| goal | string | 否 | `fat_loss` / `muscle_gain` / `maintain` |
| region | string | 否 | 地域偏好，见第 5 节词表 |

> v1 的 Dify 实现里 `user_input` 就是聊天输入（`sys.query`），`goal` / `region` 暂不单独传入、由 LLM 从自然语言抽取；这两个字段留给后续前端选择器与自建 API。

> Dify 的 LLM 节点会先抽取食材、目标、时间、地域和忌口，再与安全、意图字段合并成 `payload` 交给 `/recommend`；前端不负责拼这些字段。

## 3. 节点输出结构

> **本节是这套字段的唯一事实来源。** `prompts/parameter_extractor.md`、`prompts/intent_classifier.md` 与 `scripts/handler.py` 都必须和本节一致；编排画布配置属于本地内部资料，不随公开仓库提供。
> v1 使用**三个 LLM 节点**：参数抽取、安全判断、意图分类。安全判断与意图分类并行，之后由「参数合并」代码节点合成一个 `payload`，再交给 `handler.handle()` 消费。
> 注意：LLM 节点在 Dify 里**读不到任何本地文件**，提示词必须自带全部判据与字段规则，不能写“请参考某文档”。

### 3.1 参数抽取节点输出

```json
{
  "ingredients": ["鸡胸肉", "西兰花", "鸡蛋"],
  "goal": "fat_loss",
  "time_limit": 20,
  "flavor_preference": ["低脂", "有味道"],
  "region": "generic",
  "allergies": [],
  "avoid_items": [],
  "original_ingredient": null,
  "nutrition_ingredient": null,
  "amount_g": null
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| ingredients | array | 否 | 现有食材，仅 `cook` 场景；参数抽取 LLM 必须先按提示词内的别名表归一化成数据标准名 |
| goal | string / null | 否 | `fat_loss` / `muscle_gain` / `maintain` |
| time_limit | int / null | 否 | 时间上限，单位分钟 |
| flavor_preference | array | 否 | **仅采集，不参与 v1 评分**：口味目前只散落在 `recipes.csv` 的 `notes` 自由文本里（如「适合北方口味」），未结构化、无法稳定打分；后续新增 `taste_tags` 列后再接入 |
| region | string / null | 否 | 见第 5 节词表 |
| allergies | array | 否 | 过敏原，仅来自用户显式说明 |
| avoid_items | array | 否 | **预留字段：v1 仅采集，不参与过滤** |
| original_ingredient | string / null | 否 | 想替换掉的食材，仅 `substitute` 场景 |
| nutrition_ingredient | string / null | 否 | 想查询营养的食材，仅 `nutrition_analysis` 场景 |
| amount_g | number / null | 否 | 查询重量（克），仅 `nutrition_analysis` 场景 |

### 3.2 安全判断节点输出

```json
{
  "risk_flag": false,
  "risk_type": null
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| risk_flag | bool | 是 | 是否命中 S2–S5 安全风险；命中后由代码节点短路返回 `answer_type=safety` |
| risk_type | string / null | 否 | 命中风险类型：`extreme_low_calorie` / `extreme_single_food` / `medical_condition` / `unsafe_advice` |

> 安全节点只判断 S2–S5，且不读取任何文件；过敏属于 S1 系统不变量，不拦截用户请求，由 Python 在下游过滤过敏原。
> `scripts/handler.py` 依据合并后的 `risk_flag` 短路；缺失该字段会导致安全分支失效。

### 3.3 意图分类节点输出

```json
{
  "intent": "cook"
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| intent | string | 是 | `cook` / `eat_out` / `substitute` / `nutrition_analysis` / `provenance` |

> 意图节点不判断风险，也不输出 `unsafe`；风险请求由 §3.2 的 `risk_flag=true` 表示。
> 安全判断与意图分类都从参数抽取节点并行引出，之后汇入「参数合并」代码节点。

### 3.4 合并后 payload

> `payload` 是 §3.1、§3.2、§3.3 三个对象的并集；合并顺序为参数 → 安全 → 意图。下游只消费合并后的 `payload`。

## 4. 响应结构

> 本节描述 Dify 内部数据节点 `POST /recommend` 的响应。完整响应是外层包络 `{ "result": { … }, "elapsed_ms": 123.4, "request_id": "…" }`；下面先展示 `result` 的内容，再把 `request_id` 交给 `POST /feedback`。

```json
{
  "answer_type": "recipe",
  "recommendations": [
    {
      "id": "R001",
      "name": "黑椒鸡胸炒西兰花",
      "score": 0.86,
      "region": "通用",
      "servings": 1,
      "serving_weight_g": 400,
      "nutrition_basis": "每份",
      "cooking_time": 15,
      "nutrition": {
        "calories": 343.5,
        "protein_g": 50.0,
        "fat_g": 10.7,
        "carbs_g": 14.4,
        "fiber_g": 5.2
      },
      "ingredient_breakdown": [
        {
          "name": "鸡胸肉",
          "raw_name": "鸡胸肉",
          "amount_text": "150g",
          "amount_g": 150.0,
          "calories": 199.5,
          "protein_g": 36.0,
          "fat_g": 4.5,
          "carbs_g": 0.0,
          "fiber_g": 0.0,
          "calorie_share": 0.581
        },
        {
          "name": "西兰花",
          "raw_name": "西兰花",
          "amount_text": "200g",
          "amount_g": 200.0,
          "calories": 72.0,
          "protein_g": 8.0,
          "fat_g": 1.2,
          "carbs_g": 14.0,
          "fiber_g": 5.2,
          "calorie_share": 0.21
        },
        {
          "name": "鸡蛋",
          "raw_name": "鸡蛋",
          "amount_text": "1个",
          "amount_g": 50.0,
          "calories": 72.0,
          "protein_g": 6.0,
          "fat_g": 5.0,
          "carbs_g": 0.4,
          "fiber_g": 0.0,
          "calorie_share": 0.21
        }
      ],
      "ingredients": ["鸡胸肉", "西兰花", "鸡蛋"],
      "matched_ingredients": ["鸡胸肉", "西兰花", "鸡蛋"],
      "steps": ["鸡胸肉切块", "用生抽和黑胡椒腌制"],
      "reasons": [],
      "missing_ingredients": [],
      "substitutions": [],
      "risk_notes": []
    }
  ],
  "missing_information": [],
  "risk_notes": [],
  "next_actions": []
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| result | object | 下方第 4.1 至 4.3 节描述的业务响应 |
| elapsed_ms | float | 本地服务处理耗时，单位毫秒；仅用于本地 Demo 排查，不代表 Dify 全链路延迟 |
| request_id | string | 本次推荐请求编号；仅用于关联同一次结果上的反馈事件，不包含用户身份信息 |
| answer_type | string | `recipe` / `eat_out` / `substitution` / `nutrition` / `provenance` / `safety` |
| recommendations | array | 推荐列表，安全拦截时为空 |
| missing_information | array | 需要追问的字段 |
| risk_notes | array | 风险提示 |
| next_actions | array | 建议的后续操作 |
| sources | array | 仅 `answer_type=provenance` 时返回：查询到的食材来源清单（见 §4.3） |

### 4.1 推荐项（`recommendations[]`）字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id / name | string | 食谱 ID 与菜名 |
| score | float | 综合得分（0–1） |
| region | string | 地域标签 |
| servings | int | 份数（这份食谱做出来够几人吃） |
| serving_weight_g | int | 每份可食部分估算重量（克） |
| nutrition_basis | string | 营养数值的基准，如「每份」 |
| cooking_time | int | 制作时间（分钟） |
| nutrition | object | 每份营养，`scripts/nutrition_calc.py` 现算：`calories` / `protein_g` / `fat_g` / `carbs_g` / `fiber_g` |
| ingredient_breakdown | array | **食材级营养拆解**（见 §4.2），说明每份里各食材贡献了多少克、多少热量，用于解释「营养是由什么构成的」 |
| ingredients | array | 食材名列表 |
| matched_ingredients | array | 本食谱实际使用到的用户食材（仅在 cook 且用户提供食材时非空） |
| steps | array | 制作步骤 |
| notes | string | 注意事项 |

### 4.2 食材级营养拆解（`ingredient_breakdown[]`）

推荐项的 `nutrition` 只回答「每份一共多少」，`ingredient_breakdown` 回答「这些营养分别是谁贡献的」。全部数值**按每份**折算，单位与 `nutrition` 一致。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| name | string | 标准食材名（已过别名归一化） |
| raw_name | string | 食谱里原始写法（便于对照） |
| amount_text | string | 原始用量文本，如 `150g` / `1个` / `半个` |
| amount_g | float | 折算后的每份克重 |
| calories | float | 该食材对每份热量的贡献（kcal） |
| protein_g / fat_g / carbs_g / fiber_g | float | 该食材对每份各大营养素的贡献 |
| calorie_share | float | 该食材占总热量的比例（0–1，如 `0.581` = 58.1%） |
| source | string | 数据来源标识，如 `usda_fdc` / `cn_food_composition` |
| source_ref | string | 来源引用，如 `FDC:171077` / `CFCT6:<编码>` |
| source_name | string | 来源原始描述（英文原名或成分表条目名），用于说明口径 |
| confidence | string | 可信度分级 `L1` / `L2` / `L3` |
| verified_at | string | 核验日期 `YYYY-MM-DD` |

> 用法：解释节点应把它写成「鸡胸肉 150g 贡献 199.5 千卡（58%）、蛋白质 36g」这类用户能直接看懂的话，而不是只报一个「每份 400 克」。
> 无法解析的食材（库里没有、或没有单位换算）不会进入本数组，会落到同一响应的 `unresolved` 字段里供排查；正常数据下应为空。

### 4.3 来源清单（`sources[]`，仅 `answer_type=provenance`）

回答「这个数字哪来的 / 怎么算的」时返回。每一项对应一个被查询的食材，**只透传数据表里已存在的来源字段，不推断、不编造**；库里查不到的食材 `found=false`，不带任何来源字段。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| name | string | 标准食材名（已过别名归一化） |
| found | bool | 是否在 `data/nutrition.csv` 中查到；`false` 时下列字段不出现 |
| source | string | 数据来源标识，如 `usda_fdc` / `cn_food_composition` |
| source_ref | string | 来源引用，如 `FDC:171077` / `CFCT6:<编码>` |
| source_name | string | 来源原始描述（英文原名或成分表条目名），用于说明口径（生/熟、部位、每 100g 等） |
| confidence | string | 可信度分级 `L1` / `L2` / `L3` |
| verified_at | string | 核验日期 `YYYY-MM-DD` |

> 来源事实由 `scripts/recommend.py` 的 `lookup_sources()` 提供，字段来自 `scripts/nutrition_calc.py` 的 `row_provenance()`；解释节点据此说明「来源 + 口径 + 算法（每 100g × 克重 ÷ 份数）」，不得改写数值或补造来源。

## 5. 枚举词表

### 意图（intent / answer_type）

| 值 | 含义 |
| --- | --- |
| cook / recipe | 自烹饪食谱推荐 |
| eat_out | 外食类型与点餐策略 |
| substitute / substitution | 食材替换建议 |
| nutrition_analysis / nutrition | 营养数据解释 |
| provenance | 数据来源与算法口径解释（回答「这个数字哪来的 / 怎么算的」）；由 `answer_type=provenance` + `sources` 承载 |
| safety | 安全拦截输出；`unsafe` 仅为 `handler` 的兼容别名，不是意图分类节点的合法输出 |

### 目标（goal）

`fat_loss` 减脂 · `muscle_gain` 增肌 · `maintain` 维持

### 地域（region）

| 规范值（接口） | 数据表值（`data/*.csv`） |
| --- | --- |
| `generic` | 通用 |
| `Sichuan` | 川渝 |
| `Cantonese` | 粤式 |
| `Jiangsu` | 江浙 |
| `Northern` | 北方 |

> 注意：Prompt / 接口使用英文枚举，数据表使用中文。映射已收敛到 `scripts/recommend.py` 的 `normalize_region()`，同时接受英文枚举、中文标签与城市名（如 `成都`→`川渝`）；编排层直接调用该函数即可，无需重复维护映射表。

### 食材（ingredients）

食材归一化分两层，两层共用同一张词表：

1. **LLM 层**：参数抽取提示词内必须自带词表（不能写“参考某文档”），把用户口语转成标准名后再写入 `ingredients`。
2. **计算层**：`data/ingredient_aliases.csv` 是词表的事实来源，`scripts/nutrition_calc.py` 在解析任何食材前都会再过一遍；`data/unit_conversions.csv` 负责「个 / 瓣 / 张 / 半根」等非重量单位折算。

当前别名覆盖 24 组（姜丝→姜、蒜蓉→蒜、生抽→酱油、牛腱肉/牛肉→瘦牛肉、猪肉/瘦肉→猪瘦肉、蛋白→鸡蛋白、青豆→豌豆、玉米粒→玉米、排骨→猪小排、宽粉→红薯粉、荞麦面→荞麦面条、花生碎→花生、笋丁→笋、红油→辣椒油、西红柿→番茄 等），完整列表见 `data/ingredient_aliases.csv` 与 `docs/data-dictionary.md`。

最低匹配门槛由 Python 执行：当 `intent = cook` 且用户提供了食材时，候选食谱必须至少命中 1 个标准食材；如果没有任何候选命中，返回空 `recommendations`，并通过 `missing_information` 要求用户确认食材或放宽条件。

## 6. 错误与兜底

| 场景 | 处理 |
| --- | --- |
| 参数缺失 | 返回 `missing_information`，向用户追问 |
| 无有效候选 | 放宽限制或给出替换 / 外食建议 |
| JSON 解析失败 | 重试一次，仍失败则返回错误对象 |
| 触发安全规则 | `answer_type = safety`，`recommendations` 为空 |

## 7. 版本策略

1. 字段只增不删；删除字段需升级主版本号。
   - v0.3（2026-10-05）：删除 `meal_type`（早餐/午餐/晚餐/练后）；推荐项新增 `servings` / `serving_weight_g` / `nutrition_basis`。
   - v0.4（2026-10-06）：`ingredients` 明确由参数抽取 LLM 先归一化；推荐项新增 `matched_ingredients`；Python 增加最低食材匹配门槛。
   - v0.5（2026-10-06）：营养改为**计算值**（事实来源 `data/nutrition.csv`，`recipes.csv` 营养列降级为缓存并由校验强制对齐）；新增 `data/ingredient_aliases.csv`（24 组别名）与 `data/unit_conversions.csv`（当前 19 条单位换算）；推荐项新增 `ingredient_breakdown`（食材级营养拆解）与每份 `fiber_g`。
   - v0.6（2026-10-06）：新增第 8 节「数据录入接口」（`/data/*` + `scripts/add_data.py`）；确认营养写入规则为「只收食材与克重、一律现算」，写入统一走 `scripts/data_store.py`。
   - v0.7（2026-10-07）：意图新增 `provenance`（数据来源与算法口径溯源）；响应新增 `answer_type=provenance` 与 `sources`；`ingredient_breakdown[]` 与 `analyze_nutrition` 新增 `source` / `source_ref` / `source_name` / `confidence` / `verified_at` 来源字段。
   - v0.8（2026-10-10）：`/recommend` 外层新增 `request_id`；新增 `/feedback` 最小事件记录接口。反馈当前不读取、不重排、不持久化为个性化偏好。
   - v0.9（2026-10-10）：新增浏览器唯一聊天入口 `/chat` 及探活接口 `/chat/status`；明确 `/recommend` 只作为 Dify 内部数据节点，前端不持有 API Key、不回退本地规则。
   - v0.10（2026-10-10）：新增只读数据查询接口 `/data/rows`，供数据总览页执行表切换、关键词检索与分页。
   - v0.11（2026-10-10）：新增独立营养计算接口 `POST /nutrition/calculate`，输入标准食材名或已登记别名与克重，返回整份、每份、食材拆解、来源和未识别项；接口不调用 LLM，也不经过 Dify。
2. 本契约变更需同步更新 `prompts/*.md`、`scripts/*.py` 与 `evals/eval_set.csv`。

## 8. 数据录入与查询接口

数据录入不走 Chatflow，直接面向本地数据服务 `server/`（`POST /data/*`）与命令行 `scripts/add_data.py`。字段级说明与完整示例见 `docs/data-entry-guide.md`。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/data/schema` | 返回各表的文件名、列名、行数与 ID 前缀 |
| GET | `/data/rows` | 按表只读查询已有数据，支持关键词、分页 |
| POST | `/data/nutrition` | 新增食材营养（每 100g） |
| POST | `/data/recipes/preview` | 试算每份营养与 `ingredient_breakdown`，**不落库** |
| POST | `/data/recipes` | 新增菜谱，营养现算 |
| POST | `/data/eat_out` | 新增外出饮食 |
| POST | `/data/aliases` | 新增食材别名 |
| POST | `/data/units` | 新增单位换算 |
| POST | `/data/import` | 批量导入（数组，每条带 `table`） |
| POST | `/data/regen` | 重算全部菜谱的营养缓存 |

查询示例：

```http
GET /data/rows?table=nutrition&q=鸡胸&limit=50&offset=0
```

`q` 会匹配该表全部字段，英文不区分大小写；`limit` 范围为 1–200，`offset` 用于分页。该接口只读，不写入 CSV。

约定：

1. 写库统一经过 `scripts/data_store.py`，保持 BOM / 行尾 / 列序不变，原子写入，自动生成主键。
2. **营养不接受传入**：`POST /data/recipes` 只接受 `ingredients`（写法 `食材名:用量;…`），营养由 `scripts/nutrition_calc.py` 按 `data/nutrition.csv` 现算，写了营养字段也不采信。
3. 成功返回 `{ "ok": true, "result": { … } }`；入参不合法返回 HTTP 400 且 `error.code = "invalid_payload"`；服务内部错误返回 500。
4. `preview` 与 `add` 的请求体完全一致，便于「先看后写」：`preview` 额外返回 `goal_fit`（`{ passed, reasons }`），只提示不拦。
5. 新增或修改菜谱后必须重算营养缓存（`POST /data/regen`，或 `add_data.py --regen` 导入时自动做）。

## 9. 反馈接口

`POST /feedback` 只记录用户对某次 Dify 回答或推荐结果的明确操作，用于本地 Demo 复盘。它不自动改变下一次推荐，也不把反馈写进用户画像。

当前前端只发送回答级 `accept` / `reject`，并把 `request_id` 或 Dify `message_id` 填入兼容字段 `recipe_id`；`recipe_id` 暂不代表某道具体食谱。

请求：

```json
{
  "request_id": "b4c2e0f7a9d14c91b9576a04e0a54db7",
  "recipe_id": "dify-message-id",
  "action": "accept",
  "reason": "有帮助",
  "note": ""
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| request_id | string | 是 | `/chat` 或 `/recommend` 返回的请求编号 |
| recipe_id | string | 是 | 兼容字段；当前回答级反馈填入 Dify `message_id` 或 `request_id`，后续单道食谱反馈再填食谱 ID |
| action | string | 是 | `accept` 有帮助 / `reject` 没帮助；接口同时预留 `too_much` 太麻烦 / `regenerate` 换一批，供后续卡片反馈使用 |
| reason | string | 否 | 当前只接受与 `action` 一致的中文按钮文案 |
| note | string | 否 | 自由文本，最长 500 字；当前前端不采集 |

成功响应：

```json
{
  "ok": true,
  "event": {
    "event_id": "1f5c9f5d5d8a4cd5a85b9f547db2f4e0",
    "request_id": "b4c2e0f7a9d14c91b9576a04e0a54db7",
    "recipe_id": "dify-message-id",
    "action": "accept",
    "reason": "有帮助",
    "note": "",
    "created_at": "2026-10-10T14:30:00+08:00"
  }
}
```

错误：

| HTTP | error.code | 触发条件 |
| ---: | --- | --- |
| 400 | `invalid_feedback` | `request_id` 或 `recipe_id` 为空；action 不在枚举内；reason 与 action 不匹配 |
| 500 | `internal_error` | 本地事件文件无法写入 |

边界：

1. 当前是回答级反馈，不能区分推荐、外食、替换、营养和安全分支。
2. “换一批”当前只记录用户意图，不会重新生成或排除上一批推荐。
3. 事件写入 `runtime/feedback_events.csv`；该运行文件被 `.gitignore` 排除，不进入公开仓库。
4. 反馈事件持久化不等于偏好持久化；对话式反馈理解、偏好记忆和排序闭环仍未实现。

## 10. 独立营养计算接口

`POST /nutrition/calculate` 面向“食材和克重已经确定，只需要算这一餐营养”的场景。它直连本地 FastAPI，不经过 Dify，不调用 LLM，也不写入任何 CSV。

请求：

```json
{
  "items": [
    {"name": "鸡胸肉", "amount_g": 150},
    {"name": "西兰花", "amount_g": 200}
  ],
  "servings": 2
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| items | array | 是 | 至少一条；每一项包含食材名和克重 |
| items[].name | string | 是 | 标准食材名或 `data/ingredient_aliases.csv` 中已有的别名 |
| items[].amount_g | number | 是 | 克重，必须大于 0；这里不接收“个 / 碗 / 把”等单位 |
| servings | int | 否 | 份数，默认 1，范围 1–100；只影响每份结果，不改变输入总重量 |

成功响应：

```json
{
  "ok": true,
  "result": {
    "action": "calculate",
    "servings": 2,
    "total_weight_g": 350.0,
    "serving_weight_g": 175.0,
    "total_nutrition": {
      "calories": 248.0,
      "protein_g": 39.4,
      "fat_g": 4.7,
      "carbs_g": 13.2,
      "fiber_g": 5.2
    },
    "per_serving_nutrition": {
      "calories": 124.0,
      "protein_g": 19.7,
      "fat_g": 2.4,
      "carbs_g": 6.6,
      "fiber_g": 2.6
    },
    "ingredient_breakdown": [
      {
        "name": "鸡胸肉",
        "raw_name": "鸡胸肉",
        "amount_text": "150g",
        "amount_g": 150.0,
        "calories": 180.0,
        "protein_g": 33.8,
        "fat_g": 3.9,
        "carbs_g": 0.0,
        "fiber_g": 0.0,
        "per_serving_amount_g": 75.0,
        "per_serving_calories": 90.0,
        "per_serving_protein_g": 16.9,
        "per_serving_fat_g": 1.9,
        "per_serving_carbs_g": 0.0,
        "per_serving_fiber_g": 0.0,
        "calorie_share": 0.726,
        "source": "usda_fdc",
        "source_ref": "FDC:171077",
        "source_name": "Chicken, broiler or fryers, breast, skinless, boneless, meat only, raw",
        "confidence": "L3",
        "verified_at": "2026-10-07"
      },
      {
        "name": "西兰花",
        "raw_name": "西兰花",
        "amount_text": "200g",
        "amount_g": 200.0,
        "calories": 68.0,
        "protein_g": 5.6,
        "fat_g": 0.8,
        "carbs_g": 13.2,
        "fiber_g": 5.2,
        "per_serving_amount_g": 100.0,
        "per_serving_calories": 34.0,
        "per_serving_protein_g": 2.8,
        "per_serving_fat_g": 0.4,
        "per_serving_carbs_g": 6.6,
        "per_serving_fiber_g": 2.6,
        "calorie_share": 0.274,
        "source": "usda_fdc",
        "source_ref": "FDC:170379",
        "source_name": "Broccoli, raw",
        "confidence": "L3",
        "verified_at": "2026-10-07"
      }
    ],
    "unresolved": [],
    "complete": true,
    "nutrition_source": "data/nutrition.csv",
    "note": "营养值按 data/nutrition.csv 的每 100g 数据计算；未识别食材未计入合计。"
  },
  "elapsed_ms": 1.2,
  "request_id": "4d5e6f..."
}
```

响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| total_weight_g | float | 已识别食材的输入总重量；未识别项不计入 |
| serving_weight_g | float | 输入总重量按份数折算后的每份重量 |
| total_nutrition | object | 输入总量对应的热量、蛋白质、脂肪、碳水、膳食纤维 |
| per_serving_nutrition | object | 按份数折算后的每份营养 |
| ingredient_breakdown | array | 已识别食材的整份营养、每份营养、热量占比和数据来源 |
| unresolved | array | 未识别的食材及原因；不会按 0 静默计入合计 |
| complete | bool | 是否全部食材均已识别且存在可计算明细 |
| nutrition_source | string | 当前固定为 `data/nutrition.csv` |

错误：

| HTTP | error.code | 触发条件 |
| ---: | --- | --- |
| 400 | `invalid_data` | `items` 为空或格式错误、食材名缺失、克重不大于 0、份数不是 1–100 的整数 |
| 500 | `internal_error` | 本地数据表读取或计算过程异常 |

边界：

1. 已识别食材会正常计算，未识别食材只在 `unresolved` 中列出并在页面明确提示，不伪造近似值。
2. 别名归一化使用 `data/ingredient_aliases.csv`；该接口只接收克重，因此不依赖单位换算表。
3. `ingredient_breakdown` 中 `amount_g`、`calories` 等字段表示整份输入量；`per_serving_*` 字段才表示每份。
4. 当前通过接口、页面和 `scripts/check_nutrition_calculator.py` 离线回归验证了正常计算、别名、份数、未识别项和非法输入；尚无真实用户使用验证。
