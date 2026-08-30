# 课程 Skill 05｜给未来日期

**读课件：** `courseware/05-future-date-courseware.md`　**目标：** 把愿望变成日期、范围与一周内的第一步。

| 回合 | 用户动作 | 工具 | AI 只做什么 |
|---|---|---|---|
| 1–2 | 看“以后旅行”情境，选优先补的信息 | `narrative`、`forecast` | 不调用模型 |
| 3 | 将三个模拟目标分别放入时间轴，并写回看节点 | `future-timeline` | 不调用 |
| 4 | 日期提前，决定先重看什么 | `consequence` | 不调用模型 |
| 5 | 自由问答 | `personalized_lesson_chat` + 课件证据 | 降低焦虑，不承诺金额 |
| 6 | 为大目标选阶段点或信息收集动作 | `transfer-choice` | 不调用模型 |
| 7 | 把动作缩小到一周能开始 | `personalized_lesson_chat` + 课件证据 | 引用 `future-date.core-3`，不设金额 KPI |
| 8 | 填满用途、月份、下周动作、回看日期 | `action-card` | 不调用模型 |

**检查点：** 用户可写月份/区间，禁止要求真实收入或目标金额。
