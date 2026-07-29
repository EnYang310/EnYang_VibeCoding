---
name: nutrition-grounding
version: 1.1.0
description: 使用 USDA FoodData Central 为菜品食材匹配可追溯的每 100g 热量数据。
input: batch USDA queries
output: nutrition matches
tools:
  - lookup_usda_nutrition
---

# Nutrition Grounding Skill

## Source policy

权威数据源为 USDA FoodData Central：

1. 先查随应用部署的 USDA Foundation Foods + SR Legacy 本地知识库。
2. 主查询词未命中时，使用备用查询词再次查本地库。
3. 两次本地检索均未命中时，只允许联网查询 USDA 一次。
4. 只读取单位为 kcal 的 Energy（nutrient 208）。
5. 记录 FDC ID、英文描述、数据类型和来源链接。
6. 在线查询结果写入 SQLite 缓存，避免重复调用。

## Query rules

- 每项提供主、备用两个英文标准食物描述；备用词应更宽，偶尔相同也不影响菜单合格。
- 指明必要状态，例如 raw、cooked、boiled。
- 不使用品牌词或整句自然语言。
- 主词尽量精确，备用词去掉次要限定但保留食物本体与状态。
- 同一主查询词在一轮中去重。

## Fallback

USDA 无匹配或不可用时可以使用 Kimi 估值维持可用性，但必须：

- `estimated=true`
- `nutritionSource="耄耋估算"`
- 不生成 FDC ID 或 USDA 链接
- 在计划 warnings 中告知用户

## Calculation boundary

模型不负责最终加总。Python 以 `grams × kcalPer100g / 100` 计算单项热量，再汇总菜品、餐次和人均值。
