# 课程 Skill 07｜基金和股票，到底买到了什么

**读课件：** `courseware/07-fund-stock-basics-courseware.md`　**目标：** 让新手理解股票、基金份额和基金底层资产的关系，并在比较前先看用途、期限与规则。

| 回合 | 用户动作 | 工具 | AI 只做什么 |
|---|---|---|---|
| 1–2 | 看产品名称，判断股票代表什么 | `narrative`、`forecast` | 不调用模型 |
| 3 | 判断基金份额与底层资产的关系 | `single-choice` | 不调用模型 |
| 4 | 发现一笔原本长期的钱半年后要用 | `consequence` | 不调用模型 |
| 5 | 自由问“基金为什么不是存款”或“分散有什么用” | `personalized_lesson_chat` + 课件证据 | 用例子解释，不给真实基金建议 |
| 6 | 比较货币、债券、股票等底层资产描述 | `transfer-choice` | 不调用模型 |
| 7 | 追问净值、公开文件、风险揭示 | `personalized_lesson_chat` + 课件证据 | 只引用 `fund-stock-basics.core-1` 至 `core-4` |
| 8 | 写下看产品前的第一问 | `action-card` | 不调用模型 |

**检查点：** 不推荐具体基金、股票、平台或买卖动作；“分散”必须同时说明其不能消除全部风险；所有真实产品问题均保持 `education_only`。
