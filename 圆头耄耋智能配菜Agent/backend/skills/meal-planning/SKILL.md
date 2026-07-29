---
name: meal-planning
version: 1.6.0
description: 用用户现有库存设计可直接下厨的低热量家庭菜品。
input: GeneratePlanRequest
output: MealPlanDraft
tools: []
---

# Meal Planning

## Priority

忌口 > 厨具 > 库存与克数 > 可执行成菜 > 相对低热量 > 口味。发生冲突时少做菜或留下食材，不得突破更高优先级。

## Dish count

- 1 人通常每餐 1–2 道；2–3 人 2–3 道；4–5 人 3–4 道；6–8 人 4–5 道。
- 这是参考，不是凑数指标；`meals` 数量必须等于 `mealCount`。

## Real dish

每道菜有明确成菜、主要食材与调料克数、3–5 个顺序步骤、火候/状态观察点、对应厨具和总时长。不能只列“A+B”。

## Inventory and low calorie

- 全计划主要食材总量不超过库存约 110%；不得新增库存外主要食材。
- 盐、水、葱姜蒜、生抽、酱油、醋和少量食用油可作基础调料。
- 优先蒸、煮、焯、炖、烤和少油炒；避免油炸、厚芡和高糖酱汁。
- 未使用的主要食材写入 `unusedIngredients`；不做医疗或减重承诺。

## Nutrition query

每条食材与调料必须给出两个不同的英文 USDA 描述：主词精确、备用词更宽，并给出 `estimatedKcalPer100g` 作为权威库未命中时的明确估值。最终热量由服务端重算。

## Output

文字短但能下厨；不写背景、审计说明、Markdown 或契约外字段。
