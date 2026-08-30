# 课程 Skill 01｜钱有任务

**读课件：** `courseware/01-money-jobs-courseware.md`　**目标：** 用用途和日期给钱分工。

| 回合 | 用户动作 | 工具 | AI 只做什么 |
|---|---|---|---|
| 1–2 | 看“工资、房租、报名费”情境，预测不分工的后果 | `narrative`、`forecast` | 不调用模型 |
| 3 | 将模拟钱卡分到近期、缓冲、长期任务 | `budget-board` | 不调用 |
| 4 | 手机维修事件后重新安排并比较 | `consequence` | 不调用模型 |
| 5 | 自由问答 | `personalized_lesson_chat` + 课件证据 | 只解释一个要点 |
| 6 | 判断房租与旅行谁更要先写日期 | `transfer-choice` | 不调用模型 |
| 7 | 检查“一笔钱同时承担两个刚性任务”的冲突 | `personalized_lesson_chat` + 课件证据 | 引用 `money-jobs.core-3` |
| 8 | 填满用途、最早使用日期、任务标签 | `action-card` | 不调用模型 |

**检查点：** 用户提交任务卡或点“先继续”；后者标待回看。不得询问真实金额或推荐去处。
