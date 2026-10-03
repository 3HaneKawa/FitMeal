# FitMeal 轻食令

面向健身人群的“今晚吃什么”助手。

## 产品定位

根据用户的：

1. 现有食材
2. 健身目标
3. 时间限制
4. 口味和地域偏好
5. 自烹饪或外食场景

输出可执行的自烹饪食谱或外食建议。

## 核心原则

1. LLM 负责理解、解释和表达。
2. 营养计算与筛选由 Python 和数据集完成。
3. 所有推荐必须可评测、可追溯、可回滚。
4. 过敏、忌口和极端饮食请求必须被拦截。

## MVP 范围

1. 自然语言食材输入
2. 意图识别与参数抽取
3. 减脂和增肌两类目标
4. 自烹饪食谱推荐
5. 外食菜品类型推荐
6. 成都、广州、上海、北京四类地域偏好
7. 营养估算、缺失食材、替换建议和风险提示

## 项目结构

```text
docs/        产品文档、PRD、访谈与项目计划
data/        食谱、营养、外食、目标和替换规则数据
evals/       评测集、评分规则、运行记录
prompts/     Prompt 模板
scripts/     数据校验、推荐、评测脚本
dify/        Dify Workflow 设计说明
prototypes/  页面结构和原型说明
```

## 快速开始

```bash
python scripts/validate_data.py
python scripts/recommend.py
python scripts/run_eval.py --dry-run
```

Windows 环境下如果你的 `python` 命令指向 Microsoft Store 占位程序，可以使用：

```powershell
py scripts/validate_data.py
py scripts/recommend.py
py scripts/run_eval.py --dry-run
```

## 当前状态

- [x] 产品定位
- [x] PRD 粗略版
- [x] 数据字典和种子数据
- [x] 100 条食谱数据
- [x] 100 条营养数据
- [x] 30 条评测集
- [x] 数据校验脚本
- [x] 规则推荐器
- [x] 外食推荐、安全拦截、替换与营养分析分支
- [ ] Dify Workflow 搭建
- [ ] API 联调
- [ ] 前端原型
- [ ] 真实用户测试

