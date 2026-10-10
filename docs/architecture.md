# 系统架构

> 状态：v0.6（单输入前端 + FastAPI Dify 代理 + HTTP 数据节点 + 来源溯源 + 多轮记忆 + 独立营养计算器）
> 更新时间：2026-10-10

## 1. 设计目标

1. LLM 只负责理解、解释和表达，不负责计算和编造数据。
2. 营养计算、筛选、评分由 Python 和数据表完成，结果可追溯。
3. 所有推荐必须可评测、可追溯、可回滚。
4. 过敏、忌口和极端饮食请求必须被拦截。

## 2. 组件划分

```text
┌────────────────────────────────────────────────────────────┐
│                    浏览器单输入前端                         │
│        一句话描述、Dify 回答、真实耗时、回答级反馈            │
└───────────────────────────┬────────────────────────────────┘
                            │ POST /chat：query + conversation_id + user
┌───────────────────────────▼────────────────────────────────┐
│                FastAPI 服务（server/app.py）                │
│   持有 Dify API Key · 代理请求 · 统一错误 · 记录端到端耗时     │
└───────────────────────────┬────────────────────────────────┘
                            │ Dify Chat API
┌───────────────────────────▼────────────────────────────────┐
│                    Dify Chatflow                           │
│  参数抽取 → 安全判断 ∥ 意图分类 → 参数合并 → 数据节点 → 回答生成 │
└───────────────────────────┬────────────────────────────────┘
                            │ HTTP 请求
┌───────────────────────────▼────────────────────────────────┐
│              POST /recommend（内部数据节点）                  │
│   过敏过滤 · 候选筛选 · 评分排序 · 营养计算 · 来源透传          │
└───────────────────────────┬────────────────────────────────┘
                            │
                     ┌──────▼──────┐
                     │ data/*.csv  │
                     └─────────────┘
```

独立营养计算页不进入这条 Dify 链路：

```text
营养计算页（web/nutrition.html）
  → POST /nutrition/calculate
  → scripts/data_entry.calculate_nutrition()
  → data/nutrition.csv + data/ingredient_aliases.csv
  → 整份 / 每份营养、食材明细、热量占比、来源和未识别项
```

## 3. 职责边界

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| LLM | 参数抽取（含食材别名归一化）、安全判断、意图分类（v1 为三个独立节点，安全与意图并行）、来源与口径解释、推荐理由、风险话术 | 计算营养、决定最低匹配门槛、发明食谱、修改数值、补造来源 |
| Python | 过敏过滤、最低食材匹配门槛、目标匹配、评分排序、营养计算 | 生成自然语言、编造数据 |
| 数据集 | 提供食谱、营养、外食、目标规则、替换规则 | 实时联网数据 |
| 知识库 | **后置**补充背景与替代建议 | 作为事实来源、决定推荐结果 |
| API 代理（FastAPI `/chat`） | 持有 Dify API Key、透传多轮会话、统一错误、记录真实端到端耗时 | 判断意图、筛选食谱、计算营养、静默回退到本地规则 |
| 编排层（Dify） | 流程串联、节点路由、结构化输出 | 业务规则本身、绕过数据节点自行计算 |

## 4. 目录与组件映射

| 目录 | 作用 | 对应组件 |
| --- | --- | --- |
| `server/` | `/chat` Dify 代理、`/recommend` 数据接口、独立营养计算、反馈和数据录入 | API 与数据服务 |
| `web/` | 单输入聊天页、营养计算页、数据录入与总览 | 浏览器前端 |
| `docs/` | PRD、架构、接口、安全、评测文档 | 产品与规范 |
| `data/` | 食谱、营养、外食、目标、替换、别名和单位数据 | `/recommend` 数据节点 |
| `prompts/` | LLM 提示词模板 | Dify LLM 节点 |
| `scripts/` | 数据校验、推荐、营养计算、评测和反馈存储 | `/recommend` 后端逻辑 |
| `evals/` | 评测集、评分规则、运行记录 | 质量保障 |
| `prototypes/` | 页面结构与交互说明 | 前端 |

## 5. 数据流（当前 Dify 端到端链路）

```text
用户输入
  → [浏览器] POST /chat（只提交自然语言、会话 ID 和匿名用户 ID）
  → [FastAPI /chat 代理] 读取服务端 Dify API Key，调用 Dify Chat API
  → [Dify LLM-A] 参数抽取（含食材别名归一化）
        → {ingredients（标准名）, goal, time_limit, flavor_preference, region, allergies,
           avoid_items, original_ingredient, nutrition_ingredient, amount_g}
  → [Dify LLM-B] 安全判断（与 LLM-C 并行）
        → {risk_flag, risk_type}
  → [Dify LLM-C] 意图分类（与 LLM-B 并行）
        → {intent}
  → [Dify 参数合并] 把三段 JSON 合成 payload
  → [Dify HTTP 请求节点] POST http://host.docker.internal:8765/recommend
        → [Python] 过敏过滤 → 最低食材匹配门槛 → 目标规则匹配 → 评分排序 → Top3 + 营养计算
        → provenance：按食材名返回来源清单（source / source_ref / source_name / confidence）
  → [Dify LLM] 解释 Python 结果：推荐理由、缺失食材、替换、风险和来源
  → [Dify 多轮记忆] 参数抽取 / 意图分类 / 解释节点使用会话记忆，用于理解追问指代
  → [Dify 知识库·后置] 仅补充背景/替代检索，不改变推荐结果
  → [Dify 回答] 返回最终自然语言回答
  → [FastAPI /chat 代理] 返回 answer、conversation_id、message_id、request_id、elapsed_ms
  → [浏览器] 展示 Dify 回答、真实端到端耗时和回答级反馈入口
```
关键约束：

1. **Python 是唯一的计算与筛选来源**，LLM 拿到的是已算好的结构化结果。
2. **知识库后置**：不作为推荐依据，只在解释阶段补充背景信息。
3. **安全判断前置**：由独立的 LLM-B「安全判断」节点判定（与 LLM-C 意图分类并行）；命中风险时由 `handler` 短路，返回 `answer_type = safety`，不进入推荐计算。
4. **食材别名归一化前移、门槛后置**：参数抽取 LLM 把“大虾 / 剩饭”等常见说法转成数据标准名；Python 再做确定性的最低匹配门槛，不依赖 LLM 判断候选菜是否命中。
5. **LLM 节点一律绑 `text`、不绑 `structured_output`**：模型会先输出 `<think>…</think>`，Dify 的结构化输出会解析失败并回退成占位值；合并节点与 `handler` 都会从原始文本里剥离 `<think>` 与 json 代码块后再解析。
6. **判断节点设上限**：两个判断节点温度 0~0.2、`max_tokens` 512~1024，避免出现上万 token 的长篇推理（实测最高 7773 token / 155 秒）。
7. **来源只来自数据表**：`provenance` 分支与营养拆解里的来源字段一律由 `scripts/nutrition_calc.row_provenance()` / `scripts/recommend.lookup_sources()` 透传，LLM 与知识库都不得补造或改写来源。
8. **多轮记忆只管指代**：三个 LLM 节点启用记忆窗口（size 10）以承接「它 / 这个 / 上面那道」等追问；参数抽取规则明确「参数以当前问题为准，历史只用于理解指代」，避免历史条件污染新问题。追问数字时不得否认上一轮已给出的结果。

## 6. 集成方案

### 6.1 浏览器到 Dify：FastAPI `/chat` 代理

- 浏览器只调用 `POST /chat`，请求体包含 `query`、`conversation_id` 和匿名 `user`。
- `server/app.py` 从项目根目录 `.env` 读取 `DIFY_API_KEY`，再调用 Dify Chat API；密钥不下发到浏览器。
- `/chat` 返回 Dify 回答、会话 ID、消息 ID、请求 ID、真实端到端耗时和必要的元数据。
- Dify 不可用时返回明确错误，前端不回退到本地规则，也不把 `/recommend` 结果伪装成完整 Dify 回答。
- `GET /chat/status` 只返回是否已配置、提供方和超时时间，不输出 Token。

### 6.2 Dify 到数据层：`POST /recommend`

- Dify 通过 HTTP 请求节点调用 `http://host.docker.internal:8765/recommend`。
- `/recommend` 包装 `scripts/handler.py`，负责候选筛选、评分、过敏过滤、营养计算和来源透传。
- 该接口仍可被本地测试直接调用，但在产品链路中只作为 Dify 内部数据节点，不由浏览器直接调用。
- 优点：数据和评分逻辑常驻服务，改 `data/*.csv` 只需重启服务，逻辑可单测、可追溯。
- 依赖：FastAPI 服务、Dify 容器和本地向量服务必须在线；缺失时请求直接失败，并提示检查依赖。

### 6.3 独立营养计算器：`POST /nutrition/calculate`

- `web/nutrition.html` 收集食材标准名或已登记别名、克重和份数。
- FastAPI 调用 `scripts/data_entry.calculate_nutrition()`，复用营养表和别名表。
- 该接口不调用 LLM、不经过 Dify、不写入数据表，也不受 Dify 或向量服务状态影响。
- 未识别食材不会被静默按 0 计入合计，而是进入 `unresolved`，页面提示先补营养或别名数据。
- 该页面归入 PRD 的 F4 营养估算和 F12 份数基准，不新增能力编号。

### 6.4 公开仓库边界

公开仓库保留可运行的 FastAPI、前端、提示词和数据；Dify 画布配置、节点 ID、API Key 和内部运行记录不提交。这样既能复现链路，也不会公开内部配置或密钥。

## 7. 接口与规范

- 输入输出契约见 `docs/api-contract.md`。
- 安全规则见 `docs/safety-spec.md`。
- 评测方法见 `evals/rubric.md`、`docs/evaluation-plan.md` 与 `docs/evaluation-summary.md`。

## 8. 可观测性与回滚

1. 每次请求记录：输入、抽取参数、意图、候选、最终输出、延迟、成本。
2. 本地评测运行记录写入 `evals/runs/`（CSV）；该目录不进入公开仓库，只提交汇总和复现命令。
3. 回滚条件见 `docs/PRD.md` 第 6.2 节：营养严重错误、安全未拦截、JSON 失败率超 5%、P95 延迟超 15 秒、成本超预算 3 倍。

## 9. 已知问题

1. Dify Chatflow 主体链路、FastAPI 数据节点和六个业务分支已经搭好并做过冒烟验证，但首轮真实 API 验收仍有明显缺口：安全 LLM 判定 88.9%、过敏自动口径 14.3%、食材抽取 52.5%、P95 26.08 秒，均未达到目标。Dify 通过 HTTP 请求节点调用本地数据服务，画布上不再保留内联代码节点；因此**数据服务必须先启动**，服务不可用时请求会直接失败，这是刻意的，避免静默降级到可能过期的内联数据。
2. 食材别名表目前放在参数抽取 LLM 提示词中，模型漏归一化时 Python 会返回“无匹配”而不会硬推无关菜；阶段三评测继续补充常见别名。
3. 食谱营养值与目标规则区间的一致率为 188/208；R054 / R056 / R061 / R076 / R096 已完成减脂化修订，剩余 20 道轻度偏差继续校准。规则目前作为评分信号而非硬门槛。
4. 营养数据来源为 USDA FoodData Central 与《中国食物成分表 标准版（第6版）》（159 条：`confidence` L3 138 / L2 20 / L1 1；`source` usda_fdc 120 + cn_food_composition 21 + local 18），剩余 L2 待继续换用权威来源。
