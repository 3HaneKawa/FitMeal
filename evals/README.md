# FitMeal 评测材料说明

这个目录保存 FitMeal 的正式评测集、能力矩阵、评分规则和复现口径。公开仓库只保留结构化用例、汇总结果和运行框架，不提交原始请求、原始回包、模型日志或本地运行记录。

## 1. 文件用途

| 文件 | 用途 |
| --- | --- |
| `eval_set.csv` | 270 条正式评测集，包含 219 条开发集和 51 条验收集 |
| `capability_matrix.csv` | 能力编号、PRD 映射、风险等级和覆盖关系 |
| `rubric.md` | 人工评分和机器断言的统一口径 |
| `runs/.gitkeep` | 运行结果目录占位，原始结果不进入公开仓库 |
| `../docs/evaluation-pipeline.md` | 用例从哪里来、怎么构建、怎么运行、结果怎么解释 |
| `../docs/evaluation-summary.md` | 代码层与真实 API 的汇总结果 |

## 2. 评测目标

评测回答四个问题：

1. 系统是否识别了用户真正想做的事。
2. 安全、过敏和信息不足时，系统有没有停止错误推荐。
3. 推荐、替换和营养结果能不能追溯到数据表。
4. 修复后有没有在同一批用例上复现，而不是只挑成功样本展示。

样本数量不是唯一目标。270 条用例的价值在于固定风险边界、期望行为和验收口径。

## 3. 用例结构

| 维度 | 数量 |
| --- | ---: |
| 正式用例 | 270 |
| 开发集 | 219 |
| 验收集 | 51 |
| 高风险 | 164 |
| 中风险 | 94 |
| 低风险 | 12 |

按期望行为划分：食谱推荐 80、外食建议 49、食材替换 48、安全拦截 45、澄清追问 21、用户反馈 12、不匹配处理 9、营养解释 6。

每条用例记录能力编号、PRD 引用、用户输入、期望行为、风险类型、通过规则、失败阶段、严重度和数据版本。验收集不参与调参。

## 4. 当前结果

当前代码层版本为 `bv-a3e6abe13870`，结果为 234 pass、10 fail、14 条待人工或 LLM 评分、12 条对话式反馈用例未就绪。开发集为 190 / 8 / 11 / 10，验收集为 44 / 2 / 3 / 2。

首轮真实 API 批次是修复前基线：总体为 196 pass、58 fail、3 blocked、12 not_ready、1 error。意图识别和 JSON 解析已经可用，安全判定、食材抽取、过敏自动口径和 P95 延迟尚未达到目标。真实 API 结果不能与代码层结果混写。

## 5. 维护规则

1. 高风险期望不因修复而放宽，holdout 不参与调参。
2. 数据敏感用例绑定 `data_version`；数据或规则变化后按新版本重算基线。
3. 安全拦截和过敏过滤分开验证，机器断言只作为第一层筛选。
4. 失败必须落到实现、数据或产品规则，修复后用同一批用例复跑。
5. 反馈事件记录通过不等于对话式反馈、偏好记忆或排序闭环通过。

## 6. 运行方式

```powershell
uv run --python 3.12 python scripts/check_capability_matrix.py
uv run --python 3.12 python scripts/check_feedback_store.py
uv run --python 3.12 python scripts/check_eval_set.py --strict
uv run --python 3.12 python scripts/check_eval_consistency.py
uv run --python 3.12 python scripts/run_eval_set.py --cases evals/eval_set.csv
```

实时覆盖状态使用 `scripts/eval_status.py` 查看，`--strict` 可作为覆盖率门禁。真实 Dify API 评测需要额外配置 API Key、服务地址和节点 ID；公开仓库中的 `scripts/run_eval_api.py` 只保留运行框架，不包含内部节点配置。
