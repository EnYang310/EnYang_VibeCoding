# Teaching Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chat-first classroom with a responsive teaching stage, 42 fully-authored single-choice cards, and Kimi-generated long-form captions.

**Architecture:** Fixed lesson data owns questions and correct answers. Python turns Kimi output into a validated `teaching_scene`; React renders the concise scene and an expandable transcript while retaining the existing intent-gated card tool flow.

**Tech Stack:** Taro/React/TypeScript, Sass, FastAPI/Pydantic, Kimi API, pytest, Vitest.

---

### Task 1: Make every course interaction a fixed single-choice card

**Files:**
- Modify: `client/src/course-content.ts`
- Modify: `client/src/interaction-answer.ts`
- Modify: `client/src/interaction-answer.test.ts`

- [ ] Replace the interaction union with `narrative | single-choice`, add `questionContext`, `correctOption`, and `teachingGoal`, and author seven explicit three-option questions for each of six courses.
- [ ] Add a failing test that a `single-choice` answer is incomplete until one exact option is selected.
- [ ] Simplify answer encoding and panel completion to the selected option only; preserve previously stored data as readable text.
- [ ] Run `npm test -- --run src/interaction-answer.test.ts`.

### Task 2: Generate and validate the teaching-scene object

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/kimi.py`
- Modify: `backend/app/lesson_chat.py`
- Modify: `backend/tests/test_lesson_chat_service.py`
- Modify: `backend/tests/test_kimi.py`

- [ ] Add a failing backend assertion that a successful teaching turn returns a title, summary, 1–3 key points, caption excerpt and 3–5 caption paragraphs.
- [ ] Add `TeachingScene` to the API response and prompt Kimi to output it from fixed courseware. Require 3–5 short paragraphs and keep the current compliance boundary.
- [ ] Create a deterministic courseware fallback scene so an API failure cannot produce a short chat-only lesson.
- [ ] Run focused pytest files.

### Task 3: Replace the visual panel with an accessible single-choice panel

**Files:**
- Modify: `client/src/pages/index/interaction-panel.tsx`
- Modify: `client/src/pages/index/index.scss`
- Modify: `client/src/interaction-answer.test.ts`

- [ ] Add a failing interaction-completeness case for a non-empty option selection.
- [ ] Remove drag, slider, multi-select and input controls; render question context, prompt, three selectable option buttons and one confirm button supplied by the parent.
- [ ] Add responsive choice-grid styles: 2 columns only when room exists, otherwise one full-width target with 44px minimum touch height.
- [ ] Run the focused frontend tests.

### Task 4: Build the stage, subtitle dock and expanded transcript

**Files:**
- Modify: `client/src/pages/index/index.tsx`
- Modify: `client/src/pages/index/index.scss`
- Modify: `client/src/pages/index/index.test.tsx` (create)

- [ ] Add a failing test for collapsed stage content and an expanded caption sheet.
- [ ] Store `teaching_scene` alongside each assistant turn. Render its title/summary/key points on the stage and only the excerpt in the dock.
- [ ] Add an expandable full-caption sheet with close control, and put history behind a secondary “课堂记录” control rather than the default stage.
- [ ] Make the stage width `min(1180px, 100%)`; at mobile breakpoints remove desktop margins, use `100svh`, single column, and bottom safe-area padding.
- [ ] Run frontend tests, typecheck and H5 build.

### Task 5: Preserve intent-gated progression and final free chat

**Files:**
- Modify: `backend/app/main.py`
- Modify: `client/src/pages/index/index.tsx`
- Modify: `backend/tests/test_chat_api.py`

- [ ] Add a failing API test proving a completed card plus “好啊，往下看看” returns the next `present_interaction_card` tool result, while ordinary free chat does not.
- [ ] Preserve the existing server-side successor check and change only user-facing terms to “学习环节”.
- [ ] After the final card, return a long teaching scene and leave the composer in normal chat mode without issuing a tool result.
- [ ] Run backend API tests and full build.
