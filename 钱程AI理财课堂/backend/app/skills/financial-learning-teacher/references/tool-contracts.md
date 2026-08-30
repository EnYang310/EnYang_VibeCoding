# 课程工具合同

这些工具已经落在产品代码里。前端确定性状态机控制进度，大模型没有跳关权限。

| 工具 / 组件 | 精确调用回合 | 输入 | 输出 | 失败或边界 |
|---|---|---|---|---|
| `InteractionPanel:narrative` | 1 | 固定情境题干 | 已进入情境标记 | 模型不能改写题干。 |
| `InteractionPanel:forecast` | 2 | 选项、用户理由 | 一条可读回答 | 未选择或理由不足 6 字不能提交；可以“先继续”。 |
| 六个专属实验组件 | 3 | 当前课配置与用户操作 | 版本化结构化回答 | 只有满足下表完成条件才能提交；只处理模拟卡片。 |
| `InteractionPanel:consequence` | 4 | 固定事件、选择、理由 | 变化后的判断 | 不计算真实收益，不生成新市场事实。 |
| `personalized_lesson_chat` | 5、7，每次发送 | 课程、回合、消息、最近 8 轮对话 | `ChatResponse` | 对话轮数不限；接口不改变 `unitIndex`。 |
| `evidence_for_unit` | 每次 AI 对话前 | 课程 ID、回合 ID | 允许引用的课件片段 | evidence_id 不在白名单时拒绝模型输出。 |
| `courseware_fallback` | Key 缺失、超时、坏 JSON、越界引用、敏感信息或真实交易问题 | 同上 | 有课件依据的安全回答 | 敏感信息与真实交易问题在调用模型前拦截；`source=local_fallback`。 |
| `InteractionPanel:transfer-choice` | 6 | 新情境选择、理由 | 迁移回答 | 不调用模型，不自动判断对错。 |
| `InteractionPanel:action-card` | 8 | 当前课程声明的 3–4 个字段 | 版本化结构化行动卡 | 每个声明字段都非空才能结课；不得要求账号、收入或真实金额。 |
| `advanceCourse` | 用户主动点继续 | 当前课程状态、回答 | 下一回合或完成状态 | 一次只推进一回合；AI 不能直接调用。 |
| `skipCourseUnit` | 回合 1–7 的“先继续” | 当前课程状态 | 下一回合 + `reviewUnits` | 行动卡不可跳过。 |
| `openReviewUnit` | 结课页补答 | 课程 ID、待回看回合 | 回到指定回合 | 补完后删除该待回看项并返回结课页。 |
| `hydrateLearningState` | 应用启动 | 本地存储未知数据 | 完整六课状态 | 旧 Demo 或损坏数据回退为空状态；索引被限制在 0–7。 |

## 六个第 3 回合专属实验

| 课程 | 组件 | 用户操作 |
|---|---|---|
| 01 钱有任务 | `budget-board` | 三张钱卡全部进入有效任务区，并写至少一句理由。 |
| 02 生活保护伞 | `safety-umbrella` | 选满三块不重复保护片，并解释第一顺位。 |
| 03 产品任务地图 | `product-map` | 三个目标分别完成期限、变化、取用三问（共九项）并说明理由。 |
| 04 取舍跷跷板 | `tradeoff-sliders` | 三项共用 100 点，任何调整仍保持合计 100，并说明牺牲。 |
| 05 未来时间轴 | `future-timeline` | 三个模拟目标都放到有效时间点，补回看节点并说明理由。 |
| 06 情绪暂停站 | `pause-station` | 五张卡全部进入不重复核验顺序，并说明暂停信号。 |

## 状态机

```text
opening → initial-judgment → hands-on → consequence
        → ai-feedback-1 ⇄ unlimited chat
        → transfer
        → ai-feedback-2 ⇄ unlimited chat
        → action-card → completed
```

任何 1–7 回合都可通过 `skipCourseUnit` 前进并进入 `reviewUnits`；结课后用 `openReviewUnit` 补答。每门课的 `CourseProgress` 独立保存，`restartCourse` 只清除当前课程。
