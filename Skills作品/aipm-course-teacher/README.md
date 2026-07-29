# AI 产品经理课程老师 Skill

这是一个用于 AI 产品经理学习的课程老师 Skill。它可以帮助用户管理多门 AI PM 课程、生成企业级课件、按对话式节奏上课、做面试训练、推进项目练习，并把每天的学习状态归档下来。

当前内置课程是：

- `harness`：LLM Harness 与 AI 产品经理系统课

## 适合谁用

- AI 产品经理实习生
- 想进入 DeepSeek 或同类大模型公司的产品候选人
- 想系统学习 Agent、Tool Calling、MCP、Skill、Context、Eval、Governance 等 AI 产品知识的人
- 想把学习内容沉淀成项目、PRD、面试表达的人

## 这个 Skill 能做什么

1. 展示当前已有课程，让用户选择继续学习或新增课程。
2. 新增课程时，强制走课程生成 SOP。
3. 生成课程时，要求接近 Harness 课程质量：大量官方来源、GitHub 项目、技术资料、来源精读和来源审计。
4. 正式上课前，强制复习前天、昨天、今天的学习记录。
5. 上课时采用短轮对话，不一次性甩大段内容。
6. 下课后归档学习状态、困惑点、小测、作业和下一节建议。
7. 支持面试训练、项目路径设计、课程质量检查和多日学习总结。

## 文件结构

```text
aipm-course-teacher/
├── SKILL.md
├── README.md
├── references/
│   ├── course_authoring_sop.md
│   ├── course_catalog.md
│   ├── interview_rubric.md
│   ├── project_path.md
│   ├── teaching_sop.md
│   └── courses/
│       └── harness/
│           ├── course.md
│           └── manifest.md
├── scripts/
│   ├── add_course.py
│   ├── archive_lesson.py
│   ├── check_course_quality.py
│   ├── export_daily_summary.py
│   ├── extract_course_section.py
│   ├── generate_quiz.py
│   ├── list_courses.py
│   ├── resolve_course.py
│   └── state_manager.py
└── state/
    ├── daily/
    │   └── .gitkeep
    └── summaries/
        └── .gitkeep
```

## 重要文件说明

| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 主入口，定义什么时候触发、如何选课、如何上课、如何归档 |
| `references/course_catalog.md` | 当前课程目录 |
| `references/course_authoring_sop.md` | 新课程生成 SOP |
| `references/teaching_sop.md` | 上课 SOP |
| `references/interview_rubric.md` | AI PM 面试评分标准 |
| `references/project_path.md` | 项目路径模板 |
| `references/courses/harness/course.md` | Harness 主课件 |
| `state/daily/` | 每日学习记录 |
| `state/summaries/` | 多日学习总结 |

## 工具脚本

| 脚本 | 用途 |
|---|---|
| `list_courses.py` | 展示当前课程列表 |
| `resolve_course.py` | 判断用户是在选课、确认课程，还是要新建课程 |
| `add_course.py` | 注册新课程 |
| `check_course_quality.py` | 检查课程是否足够完整、权威、接近标准课 |
| `extract_course_section.py` | 从课程中检索相关章节 |
| `generate_quiz.py` | 根据课程主题生成小测 |
| `state_manager.py` | 创建、读取、追加学习状态 |
| `archive_lesson.py` | 下课后结构化归档 |
| `export_daily_summary.py` | 导出多日学习总结 |

## 安装方式

Codex 常见安装路径：

```text
~/.codex/skills/aipm-course-teacher/
```

Claude Code 常见安装路径：

```text
~/.claude/skills/aipm-course-teacher/
```

把整个 `aipm-course-teacher` 文件夹复制到对应 skills 目录即可。

## 推荐使用方式

开始学习时可以说：

```text
我要学习 AI PM 课程。
```

新开课程时可以说：

```text
我要学习一门新课程：XXXX课，我想学习XXXX均可。
```
**注意：** 如果新开一门课程，会花掉较长时间进行课件的准备，也会花费掉很多的token，需要注意自己的额度，由于需要保证课程质量，所以课件的内容会很多。

继续已有课程时可以说：

```text
继续 harness 课程。
```

做面试训练时可以说：

```text
用 harness 课程考我一道 DeepSeek AI PM 面试题。
```

## 新课程生成规则

这个 Skill 对新课程要求很高。标准课必须接近内置 Harness 课程的质量，不允许只生成一个薄目录。

标准课最低要求：

- 至少 `80,000` 字符
- 至少 `120` 个章节标题
- 至少 `80` 个来源链接
- 至少 `40` 个权威来源链接
- 至少 `30` 个 GitHub 项目链接
- 必须有来源精读
- 必须有来源审计和观点分级
- 必须有练习、面试问答、项目路径和 PM 判断框架

如果缺少官方资料、GitHub 项目或可靠来源，Skill 应该先生成资料获取清单，而不是编造课程。

## 学习状态

学习记录会写入：

```text
state/daily/YYYY-MM-DD.md
```

每次正式上课前，Skill 会读取：

- 前天
- 昨天
- 今天

然后先复习，再进入新课。

## 注意事项

- 发布或分享前，不要带上个人学习记录。
- `state/daily/` 和 `state/summaries/` 里只保留 `.gitkeep` 即可。
- 新课程必须写入本 Skill 的 `references/courses/` 目录，不能只放到临时 `outputs/`。
- 如果没有写入权限，Skill 应该向用户申请权限，而不是假装已经注册或归档。
