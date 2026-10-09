# 评测集维护计划（E2 建设与后续路线）

> 状态：E2.2-2 已完成，正式结构化集 154 / 270
> 更新日期：2026-10-07
> 维护方：评测集维护聊天（本聊天）
> 上位文档：`docs/evaluation-plan.md`（E1 能力冻结）、`docs/data-governance.md`
> 运行记录：`evals/runs/20261007T102115Z_code_bv-fcec5cdd225e.csv`

## 1. 资产与版本

| 资产 | 当前规模 | 状态 |
| --- | ---: | --- |
| `evals/capability_matrix.csv` | 31 项能力 | ✅ E1 已冻结 |
| `evals/e2_pilot_cases.csv` | 60 条（49 dev / 11 holdout） | ✅ 试点集稳定 |
| `evals/eval_batch2_cases.csv` | 57 条（47 dev / 10 holdout） | ✅ E2.2-2 已入库 |
| `evals/eval_set.csv` | 154 条（126 dev / 28 holdout） | ✅ 正式结构化集 |
| `evals/eval_cases.csv` | 32 条旧口径 | ⚠️ 独立迁移，暂不混入 270 计数 |
| `evals/rubric.md` | 3 类目标规则 | ✅ 已与 `data/goal_rules.csv` 对齐 |

当前版本指纹：`data_version=dv-3bc959a3d8ad` / `rules_version=rv-9124f01c88ba` / `bundle_version=bv-fcec5cdd225e`。

正式集划分：dev 126 / holdout 28 ≈ 4.5 : 1，符合 4 : 1 目标。新增的第二批 57 条全部通过代码层评测，没有引入新的失败或未判定项。

## 2. 当前健康检查

以下校验均在 2026-10-07 通过：

| 检查 | 结果 |
| --- | --- |
| 能力矩阵 | ✅ PASS：31 项，能力分组完整 |
| 试点集严格校验 | ✅ PASS：60 条，版本统一 |
| 正式集严格校验 | ✅ PASS：154 条，schema / 枚举 / 能力引用 / 版本一致 |
| 营养口径一致性 | ✅ PASS：3 类目标与 `goal_rules.csv` 一致 |
| 正式集评测 | 总 154：pass 132 / fail 7 / blocked 14 / not_ready 1 |

结果拆分：

| 划分 | pass | fail | 未判定 | 合计 |
| --- | ---: | ---: | ---: | ---: |
| dev | 108 | 6 | 12 | 126 |
| holdout | 24 | 1 | 3 | 28 |

## 3. 剩余失败归因

失败用例共 7 条，保持原期望，不放宽规则、不删用例：

| 用例 | 失败阶段 | 当前归因 | 后续动作 |
| --- | --- | --- | --- |
| P004 | scoring / nutrition | R009 脂肪 26g，高于该用例 `fat_max=20g` | 调整候选排序或营养软门槛，不改用例 |
| P047、P061–P064 | extraction / clarification | `handler.py` 缺少真正的信息缺失追问分支 | 实现追问分支后原用例复测 |
| P091 | filter / data | 三文鱼 + 芦笋 + 维持目标无匹配食谱 | 判断为数据覆盖问题还是产品行为问题，不改期望 |

另有 14 条需要 LLM / 人工评分：`P048, P050, P051, P065–P068, P073–P079`。1 条 F10 为已承诺未实现占位。下一步应先把 blocked 的评分路径补齐，再统一看端到端结果。

## 4. 当前覆盖缺口

以下均为 in-scope 能力，缺口 = 目标数 - 当前数：

| 能力 | 当前 dev / holdout | 目标 dev / holdout | 缺口 |
| --- | --- | --- | ---: |
| F09 安全拦截 | 16 / 3 | 40 / 8 | 29 |
| F08 食材替换 | 18 / 3 | 40 / 8 | 27 |
| F06 外食推荐 | 20 / 3 | 40 / 8 | 25 |
| X01 组合难题 | 3 / 0 | 20 / 4 | 21 |
| F05 推荐理由 | 28 / 6 | 40 / 8 | 14 |
| F04 营养估算 | 31 / 9 | 40 / 8 | 9 |
| F12 份数与营养基准 | 31 / 10 | 40 / 8 | 9 |
| S05 不安全建议 | 2 / 1 | 8 / 2 | 7 |
| S04 医疗条件 | 3 / 0 | 8 / 2 | 7 |
| S03 极端单一食物 | 2 / 1 | 8 / 2 | 7 |
| S02 极低热量 | 3 / 1 | 8 / 2 | 6 |
| S01 过敏冲突 | 6 / 0 | 8 / 2 | 4 |
| F10 用户反馈 | 1 / 0 | 10 / 2 | 11（暂缓） |

已达标的核心能力包括 F01、F02、F03、F07，以及全部 B01–B05、L01–L04。F10 仍是 `v1_promised_not_ready`，不删除、不改范围，但实现前不作为门禁失败。

## 5. 分批建设计划

### E2.2-3：外食推荐补齐（26 条）

- 目标：F06 +20 dev / +5 holdout，另留 1 条边界回归位。
- 规模：21 dev / 5 holdout；完成后总量 180。
- 重点：不同地域、预算、点餐策略、品牌营养禁止编造、无明确菜品时的降级。
- 退出标准：F06 达到 41 / 40 dev、8 / 8 holdout；新增用例无未归因失败。

### E2.2-4：食材替换补齐（27 条）

- 目标：F08 +22 dev / +5 holdout。
- 规模：22 dev / 5 holdout；完成后总量 207。
- 重点：常见主食、蛋白、酱料、饮品替换；说明替换关系和营养变化；禁止编造营养数值。
- 退出标准：F08 达到 40 / 40 dev、8 / 8 holdout。

### E2.2-5：安全风险补齐（31 条）

- 目标：一次性关闭 F09 与 S01–S05 缺口。
- 分配：S01 +2 dev / +2 holdout；S02 +5 / +1；S03 +6 / +1；S04 +5 / +2；S05 +6 / +1。
- 规模：24 dev / 7 holdout；完成后总量 238。
- 重点：S1 过敏原零泄漏；S2–S5 100% 拦截；审核“拦截后继续推荐”和“整体安全提示”的行为边界。
- 退出标准：F09 达到 40 / 40 dev、8 / 8 holdout；S01–S05 全部达标。

### E2.2-6：交叉难题补齐（21 条）

- 目标：关闭 X01，并在同一批交叉覆盖 F05、F04、F12。
- 规模：17 dev / 4 holdout；完成后总量 259。
- 交叉覆盖：F05 +12 dev / +2 holdout；F04 +9 dev；F12 +9 dev。
- 重点：风险 + 边界 + 语言变体组合，确保一条用例可验证多个能力但只按一个主行为判定。
- 退出标准：X01、F04、F05、F12 全部达标；holdout 不缺能力。

### E2.2-7：用户反馈转正（11 条）

- 前置条件：F10 反馈交互已实现并可运行。
- 规模：9 dev / 2 holdout；完成后正式集达到 270。
- 重点：是否收集反馈、反馈如何影响下一轮、反馈缺失时是否可降级。
- 退出标准：全部 in-scope 能力达标；`eval_status.py --strict` 返回 0。

## 6. 旧 32 条与评分执行

- 旧 32 条独立迁移到结构化 schema，单独审计 ID、能力引用和重复输入；不直接混入 270 计数，避免虚增规模。
- 迁移后作为回归集保留，不删除旧文件。
- `auto` 用例继续机检；`rubric` / `human` 用例补 LLM 辅助评分和人工抽检路径。
- 每批构建后必须依次执行：结构校验 → 口径校验 → 正式集评测 → 记录 `bundle_version` → 更新维护文档。
- holdout 达到目标后冻结，只用于验收，不参与调参。

## 7. 维护规则

1. **只增不删**：行为变化时旧用例转回归，不因改实现而删除。
2. **不迁就实现**：期望从 PRD 和能力矩阵反推，不从当前代码反推。
3. **先归因再改**：先判断是实现、数据还是 PRD 问题，再决定修复方向。
4. **版本绑定**：数据变化后重算 `data_sensitive` 基线，invariant 用例跨版本必须保持。
5. **不做假通过**：不放宽规则、不修改期望值、不删除用例来制造通过。
6. **冻结 holdout**：只读验收集不进入调参闭环。

## 8. 常用命令

```powershell
uv run --python 3.12 python scripts/check_capability_matrix.py
uv run --python 3.12 python scripts/check_e2_pilot_cases.py --strict
uv run --python 3.12 python scripts/check_eval_set.py --strict
uv run --python 3.12 python scripts/check_eval_consistency.py
uv run --python 3.12 python scripts/run_eval_set.py --cases evals/eval_set.csv
uv run --python 3.12 python scripts/eval_status.py
uv run --python 3.12 python scripts/eval_status.py --strict
```

## 9. 当前决策

- 270 条按五批补齐，不等待所有用例写完后再统一评测。
- F06 / F08 优先，因为它们是当前最大的可直接补齐功能缺口。
- 安全缺口单独成批，避免和普通推荐用例混在一起后难以判断拦截行为。
- F10 保持在正式集中占位；实现后再转正，不提前删除专属位置。
