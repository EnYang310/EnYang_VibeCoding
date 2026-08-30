# 课程 Skill 03｜看懂差异

**读课件：** `courseware/03-product-map-courseware.md`　**目标：** 用期限、变化、可用性比较信息。

| 回合 | 用户动作 | 工具 | AI 只做什么 |
|---|---|---|---|
| 1–2 | 看两个规则不同的模拟盒子，排序三问 | `narrative`、`forecast` | 不调用模型 |
| 3 | 为三个目标分别填写期限、变化、取用要求（3×3） | `product-map` | 不调用 |
| 4 | 搬家日期提前，重看可用性 | `consequence` | 不调用模型 |
| 5 | 自由问答 | `personalized_lesson_chat` + 课件证据 | 用人话解释风险/流动性 |
| 6 | 面对陌生宣传，选择下一步核验动作 | `transfer-choice` | 不调用模型 |
| 7 | 解释看不懂的术语并把判断权拿回来 | `personalized_lesson_chat` + 课件证据 | 引用 `product-map.core-3` |
| 8 | 分别写下“多久要用、可能怎么变、何时能取” | `action-card` | 不调用模型 |

**检查点：** 真实产品追问仅返回通用三问与正规渠道提示。
