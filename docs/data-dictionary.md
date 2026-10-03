# 数据字典

## recipes.csv

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 食谱唯一 ID |
| name | string | 菜名 |
| region | string | 地域标签 |
| goal | string | 适合目标 |
| meal_type | string | 餐段 |
| cooking_time | int | 制作时间，单位分钟 |
| difficulty | string | 难度 |
| ingredients | string | 食材和克数，分号分隔 |
| steps | string | 制作步骤，分号分隔 |
| calories | int | 热量，kcal |
| protein_g | float | 蛋白质 |
| fat_g | float | 脂肪 |
| carbs_g | float | 碳水 |
| fiber_g | float | 纤维 |
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
| unit | string | 基准单位 |
| calories | float | 每 100g 或每个单位热量 |
| protein_g | float | 蛋白质 |
| fat_g | float | 脂肪 |
| carbs_g | float | 碳水 |
| fiber_g | float | 纤维 |
| allergens | string | 过敏原 |
| substitutes | string | 可替代食材 |
| source | string | 数据来源 |

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

## goal_rules.csv

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| goal | string | 健身目标 |
| meal_type | string | 餐段 |
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
| nutrition_change | string | 营养变化 |
| applies_to | string | 适用目标 |

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

