# 课程 Skill 06｜不让情绪开车

**读课件：** `courseware/06-steady-mind-courseware.md`　**目标：** 在催促与高回报诱导下暂停、核验、保护信息。

| 回合 | 用户动作 | 工具 | AI 只做什么 |
|---|---|---|---|
| 1–2 | 看群聊催促，选第一反应 | `narrative`、`forecast` | 不调用模型 |
| 3 | 将目标、期限、来源、资质、规则五张卡全部排入核验顺序 | `pause-station` | 不调用 |
| 4 | 出现不明链接/不同目标等新信息 | `consequence` | 不调用模型 |
| 5 | 自由问答 | `personalized_lesson_chat` + 课件证据 | 不给具体项目结论 |
| 6 | 处理代办、保本高收益或验证码情境 | `transfer-choice` | 不调用模型 |
| 7 | 自由追问概念；真实标的、买卖、仓位和配置问题在调用模型前切回课件 | `personalized_lesson_chat` + 课件证据 | 引用 `steady-mind.core-1` 至 `core-4`；保持 `education_only` |
| 8 | 填满四项核验、绝不发送的信息、正规求助渠道 | `action-card` | 不调用模型，不替代报警/鉴定 |

**检查点：** 敏感金融信息一律提醒不发送；真实标的只做教育解释与风险提示。
