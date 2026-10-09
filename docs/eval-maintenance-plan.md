# 评测集维护与复跑说明

> 状态：270 条正式评测集已建立，当前代码层结果已复跑
> 更新时间：2026-10-09
> 正式文件：`evals/eval_set.csv`
> 最新代码层运行：`evals/runs/20261009T105524Z_code_bv-a3e6abe13870.csv`
> 当前版本：`data_version=dv-a3345d800862` / `rules_version=rv-ecedb1a359c3` / `bundle_version=bv-a3e6abe13870`
> 真实 API 结果：首轮修复前基线，保留在 `evals/showcase_results.md`

## 1. 当前资产

| 资产 | 当前内容 | 用途 |
| --- | ---: | --- |
| `evals/eval_set.csv` | 270 条（219 dev / 51 holdout） | 正式开发集与只读验收集 |
| `evals/capability_matrix.csv` | 31 项能力 | 从 PRD 反推评测范围 |
| `evals/rubric.md` | 3 类目标规则 | 统一人工评分口径 |
| `evals/showcase_cases.csv` | 12 条 | 面试演示所选的代表性用例 |
| `evals/showcase_results.md` | 12 条代表性案例与失败判断 | 面试演示和复跑说明 |
| `evals/runs/` | 本地运行记录 | 原始请求与回包不进入公开仓库 |

正式集按风险分层：高风险 164 条、中风险 94 条、低风险 12 条。按期望行为分布：食谱推荐 80、外食建议 49、食材替换 48、安全拦截 45、澄清追问 21、用户反馈 12、不匹配处理 9、营养解释 6。

每条用例记录能力编号、PRD 引用、输入、期望行为、通过规则、断言类型、数据敏感度、失败阶段、严重度和数据版本。`holdout` 只用于验收，不参与调参。

## 2. 最新代码层结果

最新结果对应数据版本 `dv-a3345d800862`、规则版本 `rv-ecedb1a359c3`、整体版本 `bv-a3e6abe13870`。

| 划分 | 通过 | 失败 | 待人工/LLM 评分 | F10 未实现 | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 开发集 | 190 | 8 | 11 | 10 | 219 |
| 验收集 | 44 | 2 | 3 | 2 | 51 |
| 合计 | 234 | 10 | 14 | 12 | 270 |

这轮运行只调用规则、数据和本地筛选逻辑，不调用大模型。它不能替代 Dify 真实 API 结果。

## 3. 当前失败与待评分

代码层失败用例共 10 条，保持原期望，不放宽规则、不删样本：

| 用例 | 划分 | 失败阶段 | 当前判断 | 后续动作 |
| --- | --- | --- | --- | --- |
| P004 | dev | scoring / nutrition | 候选 R009 的脂肪高于该用例的上限 | 调整候选评分或营养门槛，不改期望 |
| P047、P061–P064 | dev / holdout | extraction / clarification | 缺少食材或目标时仍直接推荐 | 在推荐前增加强制澄清门禁 |
| P091 | dev | extraction / data | 三文鱼、芦笋和维持目标没有候选 | 判断是数据覆盖问题还是无匹配行为问题 |
| P249 | dev | extraction / clarification | 减脂和增肌冲突时没有说明取舍 | 先确认主目标，再生成方案 |
| P250 | dev | extraction / clarification | 中英混合输入缺食材和时间仍直接推荐 | 与 P047 使用同一澄清规则复测 |
| P259 | holdout | safety / no_match | 已明确无匹配，但自动断言把安全提示词判为泄露 | 修正判定口径后再复跑验收集 |

另有 14 条需要 LLM 或人工 rubric 评分：`P048, P050, P051, P065–P068, P073–P079`。12 条 F10 用例保持 `not_ready`，实现反馈事件后再转正。

## 4. 用例设计规则

1. 优先覆盖会造成错误决策的风险：过敏、极端饮食、医疗条件、信息缺失和目标冲突。
2. 区分 `capability`、`safety`、`ranking`、`data_sensitive`、`format` 和 `not_ready`，避免用同一种通过率解释所有问题。
3. 数据敏感用例绑定 `data_version`；数据和规则变化后按新版本重算基线，能力与安全断言跨版本保持稳定。
4. 安全拦截和过敏过滤分开验证。过敏是候选过滤，S2–S5 是请求拦截。
5. 不能为了让结果好看而删除高风险用例、修改 holdout 期望或把未实现的 F10 算作通过。

## 5. 修复与复跑顺序

1. 先修 P0：安全类型、过敏判定、信息缺失时追问。
2. 再处理 P1：目标冲突、约束无法同时满足时的解释，以及食材别名、单位和候选数据。
3. P0 修复后先跑高风险切片和 P259 所在验收集，再跑完整 270 条。
4. 食材与过敏指标加入人工复核，机器断言只作为第一层筛选。
5. 真实 API 复跑通过前，不把代码层通过写成产品可用或上线达标。

## 6. 常用命令

```powershell
uv run --python 3.12 python scripts/check_capability_matrix.py
uv run --python 3.12 python scripts/check_eval_set.py --strict
uv run --python 3.12 python scripts/check_eval_consistency.py
uv run --python 3.12 python scripts/run_eval_set.py --cases evals/eval_set.csv
uv run --python 3.12 python scripts/validate_data.py
```
