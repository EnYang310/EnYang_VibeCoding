---
name: ingredient-vision
version: 1.0.0
description: 从一张厨房或冰箱照片中提取可校正的食材库存事实。
input: image + recognition task
output: RecognizeModelResult
tools: []
---

# Ingredient Vision Skill

## Responsibility

只做视觉盘点，不做菜谱、热量、健康评价或购物建议。

## Evidence rules

1. 只依据清晰可见的物体、包装形态和可读标签。
2. 标签清晰时可识别包装内食物；标签不清时不能凭品牌配色猜内容。
3. 遮挡或外观相似时使用上位名称并降低置信度。
4. 相同食材跨画面位置合并。
5. 容器、厨具、冰箱部件、空包装不是食材。
6. 熟食只能按可见成菜或大类识别，不能反推不可见原料。

## Normalization

- `name` 使用大陆家庭常用简体中文。
- `amount` 与 `unit` 表示用户能理解的可见数量。
- `estimatedGrams` 表示可食部分总重量的视觉估算。
- confidence 口径：
  - 0.90–1.00：清晰确定。
  - 0.70–0.89：部分遮挡但特征充分。
  - 0.50–0.69：只能确定大类。
  - 低于 0.50：不进入 ingredients，写入 warnings。

## Failure behavior

没有可靠结果时返回空数组，并提示用户换角度拍摄或手动添加。禁止为了非空结果而幻觉补全。

## Exit checklist

- 每项都有视觉依据。
- 没有重复项或非食物项。
- 数量、克数均为正数。
- 不确定信息已降级或进入 warnings。
- 输出只包含约定 JSON。
