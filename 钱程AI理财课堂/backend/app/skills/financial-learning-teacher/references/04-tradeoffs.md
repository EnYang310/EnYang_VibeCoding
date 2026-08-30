# 课程 Skill 04｜看见取舍

**读课件：** `courseware/04-tradeoffs-courseware.md`　**目标：** 用任务与期限理解稳定、灵活和增长可能性的取舍。

| 回合 | 用户动作 | 工具 | AI 只做什么 |
|---|---|---|---|
| 1–2 | 看“三个愿望一笔钱”情境，选当前优先点 | `narrative`、`forecast` | 不调用模型 |
| 3 | 在固定 100 点预算内操作三枚取舍滑杆；拉高一项会压低另两项 | `tradeoff-sliders` | 不调用 |
| 4 | 加入一年/五年两张日期卡 | `consequence` | 不调用模型 |
| 5 | 自由问答 | `personalized_lesson_chat` + 课件证据 | 引用 `tradeoffs.core-1` |
| 6 | 将一个愿望拆为两张任务卡 | `transfer-choice` | 不调用模型 |
| 7 | 比较两次选择，强调“这笔钱、这个阶段”的边界 | `personalized_lesson_chat` + 课件证据 | 引用 `tradeoffs.core-2`、`core-3`；不预测收益 |
| 8 | 填满任务、当前优先点、最早使用时间 | `action-card` | 不调用模型 |

**检查点：** 不把滑杆映射为产品或风险等级结论。
