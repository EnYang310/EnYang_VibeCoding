# Chat Classroom Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the fixed-page lesson into a continuous teacher-led chat classroom where every exercise can be completed and submitted visibly.

**Architecture:** The existing six-course/eight-unit state machine remains the source of truth. The active unit becomes an assistant message in a conversation feed; its exercise card is rendered inside that message and the learner sends a structured response through an explicit chat action. H5 budget cards gain native drag-and-drop while touch/click remains a usable fallback.

**Tech Stack:** Taro React, TypeScript, Sass, Vitest, existing FastAPI/Kimi endpoint.

---

### Task 1: Make completion state explainable

**Files:**
- Modify: `client/src/interaction-answer.ts`
- Modify: `client/src/interaction-answer.test.ts`

- [ ] Add `completionHint(unit, value)` returning a human instruction such as `还差 2 个字说明理由` or `请先安排完 3 张钱卡`.
- [ ] Add a failing test for a selected forecast answer with a four-character reason, expecting the exact missing-character hint.
- [ ] Implement the helper and run `npm test -- --run src/interaction-answer.test.ts`.

### Task 2: Make the budget board genuinely draggable in H5

**Files:**
- Modify: `client/src/pages/index/interaction-panel.tsx`
- Modify: `client/src/pages/index/index.scss`

- [ ] Render each money card as a draggable H5 element carrying its task name.
- [ ] Render three task zones as drop targets; dropping assigns the card and updates the existing structured answer.
- [ ] Retain the existing tap-to-cycle action as a mobile fallback and label it clearly.

### Task 3: Render the lesson as a teacher-led chat feed

**Files:**
- Modify: `client/src/pages/index/index.tsx`
- Modify: `client/src/pages/index/index.scss`

- [ ] Replace the standalone prompt card/lesson action layout with a scrollable `课堂对话` feed.
- [ ] Show the current unit as an assistant bubble containing its title, prompt and interaction card.
- [ ] Put a visible completion hint directly above an enabled/disabled `发送给程老师并继续` action.
- [ ] On submit, append the learner’s readable answer to local classroom history, advance exactly one unit, and show the next teacher unit.
- [ ] Keep teacher-chat units connected to `/api/v1/lessons/chat`; normal exercise units never call the model.

### Task 4: Verify the user path

**Files:**
- Test: `client/src/interaction-answer.test.ts`

- [ ] Run typecheck and all Vitest tests.
- [ ] Build H5.
- [ ] Start the desktop backend, verify a Kimi response, then manually inspect the browser: select + reason + send; drag a money card; continue into the Kimi round.
