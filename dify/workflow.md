# Dify Workflow 设计

## 总体流程

```text
用户输入
  ↓
参数抽取节点
  ├─ ingredients
  ├─ goal
  ├─ meal_type
  ├─ time_limit
  ├─ flavor_preference
  ├─ region
  ├─ allergies
  └─ intent
  ↓
意图分类节点
  ├─ cook
  ├─ eat_out
  ├─ substitute
  ├─ nutrition_analysis
  └─ unsafe
  ↓
知识库检索节点
  ├─ recipes
  ├─ nutrition
  ├─ eat_out_foods
  ├─ goal_rules
  └─ substitutions
  ↓
Python 工具节点
  ├─ 过滤过敏原
  ├─ 匹配目标规则
  ├─ 计算推荐分
  └─ 输出 Top3
  ↓
LLM 生成节点
  ├─ 推荐理由
  ├─ 风险提示
  └─ 不改变营养数据
  ↓
结构化输出节点
```

## 节点配置

### 1. 输入节点

输入字段：

1. `user_input`
2. `scene`
3. `goal`

### 2. 参数抽取节点

Prompt 使用 `prompts/parameter_extractor.md`。

### 3. 意图分类节点

Prompt 使用 `prompts/intent_classifier.md`。

### 4. 知识库检索节点

建议建立 5 个知识库：

1. `fitmeal_recipes`
2. `fitmeal_nutrition`
3. `fitmeal_eat_out`
4. `fitmeal_goal_rules`
5. `fitmeal_substitutions`

### 5. Python 工具节点

核心输入：

```json
{
  "intent": "cook",
  "ingredients": ["鸡胸肉", "西兰花", "鸡蛋"],
  "goal": "fat_loss",
  "meal_type": "dinner",
  "time_limit": 20,
  "region": "generic",
  "allergies": []
}
```

核心输出：

```json
{
  "candidates": [
    {
      "id": "R001",
      "name": "黑椒鸡胸炒西兰花",
      "score": 0.86,
      "reasons": []
    }
  ]
}
```

### 6. LLM 生成节点

Prompt 使用 `prompts/response_generator.md`。

## 失败路径

1. 参数缺失：追问用户
2. 无有效食谱：推荐替换或放宽限制
3. 检索失败：拒答
4. 触发安全规则：安全提示
5. JSON 解析失败：重试一次或返回错误

