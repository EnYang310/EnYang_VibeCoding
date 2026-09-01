# Advanced Financial Literacy Courses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two survey-informed advanced financial-literacy courses, keep the existing six-course learning state valid, and visually separate the foundational and advanced tracks on the H5 home page.

**Architecture:** Add `fund-stock-basics` and `volatility-time` to the shared client and backend course registries. Each course has the same eight-unit interaction contract as the existing courses, separate courseware, evidence allowlists, and a course-specific teacher workflow. Export ordered course sections from the client content module, then render each section independently so course 07 and 08 sit below a visible “理财进阶课” heading.

**Tech Stack:** TypeScript, React/Taro H5, Vitest, Python 3, FastAPI, pytest, Markdown courseware, CloudBase Docker deployment.

---

## Course specification and source boundary

The survey has 272 valid responses. The two new courses address the 44.85% of respondents who have only used money-market funds, the 16.91% who have used funds/stocks/gold but do not understand movement and operation, and the top requested topic: risk and return (35.66%).

### Course 07: 《基金和股票，到底买到了什么》

**Learning goal:** distinguish stock ownership from fund shares; explain that a fund pools money into underlying assets; compare product categories by holdings, risk features, use date, and liquidity without recommending a real product.

| Unit | Interaction | Student task | Correct teaching conclusion |
| --- | --- | --- | --- |
| `opening` | narrative | See a “fund” and a “stock” label beside three future money tasks | Labels do not answer what is owned or whether the money can bear change. |
| `initial-judgment` | choice | Decide what a stock purchase represents | A stock represents an ownership claim in a company, not a guaranteed interest payment. |
| `hands-on` | choice | Identify what a fund share represents | A fund pools holders’ money and invests according to disclosed objectives; it is not a guaranteed deposit. |
| `consequence` | choice | React when a six-month rent reserve is proposed for a volatile equity-type fund | First recheck use date and ability to bear loss/volatility, not product popularity. |
| `ai-feedback-1` | choice | Correct “a fund automatically cannot lose because it is diversified” | Diversification can reduce single-security concentration, not remove all loss or liquidity risk. |
| `transfer` | choice | Compare stock, bond, money-market and mixed fund descriptions | Compare underlying assets, expected volatility, rules and availability rather than names. |
| `ai-feedback-2` | choice | Choose the first document to read after seeing a specific fund | Read disclosed legal/risk documents; no recommendation or purchase decision is supplied. |
| `action-card` | choice | Pick the first question before researching any investment product | “What does it mainly hold, and when might I need this money?” |

### Course 08: 《涨跌不是信号：用时间看收益与波动》

**Learning goal:** distinguish expected return from guarantee; explain net asset value, volatility, drawdown and liquidity in teaching language; form a pause-and-check sequence before reacting to market movement.

| Unit | Interaction | Student task | Correct teaching conclusion |
| --- | --- | --- | --- |
| `opening` | narrative | See a simulated fund value move down after a purchase | A short-term price change is information, not an instruction to trade. |
| `initial-judgment` | choice | Identify “net value falls” accurately | It means the value of underlying assets changed; it does not by itself predict the next movement. |
| `hands-on` | choice | Compare a one-month need and a three-year goal | Use date changes the capacity to wait through volatility. |
| `consequence` | choice | Handle an 8% simulated drawdown | Check purpose, deadline, rule understanding and loss capacity before any real-world decision. |
| `ai-feedback-1` | choice | Correct “high expected return means the result will definitely be high” | Return expectation is not a promise; higher expected return commonly accompanies higher uncertainty. |
| `transfer` | choice | Identify what diversification can and cannot do | It may reduce single-asset concentration, but cannot eliminate market or liquidity risk. |
| `ai-feedback-2` | choice | Respond to a hot-news-driven urge | Pause, verify source, and revisit the original task instead of following a single movement. |
| `action-card` | choice | Choose the reusable market-movement checklist | “Is this money needed soon, do I understand the rule, and can I bear this change?” |

All prompts, teacher explanations, local fallbacks and courseware must preserve the existing `education_only` contract: no real security/fund names, no buy/sell/hold instruction, no allocation percentage, no price forecast and no return promise. Source courseware will cite official CSRC/AMAC investment-education material: [CSRC: securities investment funds](https://www.csrc.gov.cn/csrc/c100211/c1452112/content.shtml), [CSRC: fund classification](https://www.csrc.gov.cn/guangdong/c105589/c31725464ec11439cadd8e6496673031f/content.shtml), [AMAC: funds vs. stocks and bonds](https://investor.amac.org.cn/investread/tzbdjczs/202006/t20200603_9657.html), and [CSRC: fund investment risks](https://www.csrc.gov.cn/tianjin/c105377/c05f4e3a5604e4c7cac5fd6ddd85c231c/content.shtml).

### Task 1: Extend the shared course registries and prove old progress still hydrates

**Files:**
- Modify: `client/src/course-engine.test.ts`
- Modify: `client/src/learning-storage.test.ts`
- Modify: `client/src/course-engine.ts`
- Modify: `client/src/learning-storage.ts`
- Modify: `backend/tests/test_catalog.py`
- Modify: `backend/app/course_data.py`
- Modify: `backend/app/lesson_runtime.py`

- [ ] **Step 1: Write the failing registry and migration tests**

```ts
// client/src/learning-storage.test.ts
it('adds untouched advanced-course progress to a saved six-course state', () => {
  const legacy = createLearningState()
  delete (legacy.courses as Record<string, unknown>)['fund-stock-basics']
  delete (legacy.courses as Record<string, unknown>)['volatility-time']
  const hydrated = hydrateLearningState(legacy)
  expect(hydrated.courses['fund-stock-basics'].unitIndex).toBe(0)
  expect(hydrated.courses['volatility-time'].completed).toBe(false)
})
```

```py
# backend/tests/test_catalog.py
assert COURSE_IDS[-2:] == ("fund-stock-basics", "volatility-time")
assert len(list_courses()) == 8
```

- [ ] **Step 2: Run the new focused tests and verify they fail because the IDs are absent**

Run: `npm test -- --run src/learning-storage.test.ts` from `client/`; `python3 -m pytest backend/tests/test_catalog.py -q` from the project root.

Expected: TypeScript test cannot index the two new course IDs; Python catalog assertion reports six courses.

- [ ] **Step 3: Add the two IDs and their server metadata**

```ts
// client/src/course-engine.ts
export const COURSE_IDS = [
  'money-jobs', 'safety-net', 'product-map', 'tradeoffs',
  'future-date', 'steady-mind', 'fund-stock-basics', 'volatility-time'
] as const
```

```py
# backend/app/course_data.py
"fund-stock-basics": {
    "id": "fund-stock-basics", "number": "07", "title": "基金和股票，到底买到了什么",
    "subtitle": "先看钱买到了什么，再看它可能怎么变。",
    "learning_goal": "能区分股票、基金份额及基金底层资产，并先看期限与规则。",
},
"volatility-time": {
    "id": "volatility-time", "number": "08", "title": "涨跌不是信号：用时间看收益与波动",
    "subtitle": "价格在变，判断先回到用途和时间。",
    "learning_goal": "能用用途、期限、波动与可承受性解释一次市场变化。",
},
```

Add matching `COURSE_FOCUS` entries in `backend/app/lesson_runtime.py`; do not change `LearningState.version`, because `hydrateLearningState()` already creates defaults for every ID in the current registry.

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `npm test -- --run src/learning-storage.test.ts src/course-engine.test.ts` from `client/`; `python3 -m pytest backend/tests/test_catalog.py backend/tests/test_lesson_runtime.py -q` from the project root.

Expected: all selected tests pass and a six-course saved object acquires blank state for 07 and 08.

- [ ] **Step 5: Commit the registry change**

```bash
git add client/src/course-engine.ts client/src/course-engine.test.ts client/src/learning-storage.test.ts backend/app/course_data.py backend/app/lesson_runtime.py backend/tests/test_catalog.py
git commit -m "Add advanced course registries"
```

### Task 2: Add complete course content and grounded teacher courseware

**Files:**
- Modify: `client/src/course-content.ts`
- Modify: `client/src/course-content.test.ts`
- Modify: `backend/app/courseware.py`
- Modify: `backend/app/skills/financial-learning-teacher/SKILL.md`
- Create: `backend/app/skills/financial-learning-teacher/references/07-fund-stock-basics.md`
- Create: `backend/app/skills/financial-learning-teacher/references/08-volatility-time.md`
- Create: `backend/app/skills/financial-learning-teacher/references/courseware/07-fund-stock-basics-courseware.md`
- Create: `backend/app/skills/financial-learning-teacher/references/courseware/08-volatility-time-courseware.md`
- Modify: `backend/tests/test_courseware_registry.py`

- [ ] **Step 1: Write failing content and courseware tests**

```ts
// client/src/course-content.test.ts
it('contains eight courses with eight distinct teaching units', () => {
  expect(Object.keys(COURSE_CONTENT)).toHaveLength(8)
  expect(COURSE_CONTENT['fund-stock-basics'].units).toHaveLength(8)
  expect(COURSE_CONTENT['volatility-time'].units).toHaveLength(8)
})
```

```py
# backend/tests/test_courseware_registry.py
for course_id in ("fund-stock-basics", "volatility-time"):
    courseware = load_courseware(course_id)
    assert len(courseware.evidence) >= 4
    assert courseware.sources
```

- [ ] **Step 2: Run the focused tests and verify they fail because the content/courseware files do not exist**

Run: `npm test -- --run src/course-content.test.ts` from `client/`; `python3 -m pytest backend/tests/test_courseware_registry.py -q` from the project root.

Expected: content count is six and `load_courseware()` raises for each unknown new course.

- [ ] **Step 3: Implement the two eight-unit client courses and four evidence points per course**

Append the exact eight-unit outlines above to `COURSE_CONTENT`, using the existing `choice()` helper, three options per choice, and exactly one `correctOption`. Give 07 a distinct teal accent and 08 a distinct blue accent. Add the two courseware filenames to `COURSE_FILES`, then allow `ai-feedback-1` to cite core 1–2 and `ai-feedback-2` to cite core 3–4 for both courses.

Courseware 07 must include four facts: stock = ownership relationship; fund = pooled/indirect investment with disclosed holdings; fund types differ by underlying assets; fund investing can lose and diversification does not erase every risk. Courseware 08 must include four facts: net asset value equals assets minus liabilities; market price changes can create volatility; expected return is not guaranteed; liquidity/market/management risk remain and use date matters. Every fact must carry a source URL and a boundary sentence forbidding real-product advice.

- [ ] **Step 4: Add the two Skill route pages**

Each route page must map the eight fixed units to the new courseware and state that any request for a real fund, stock, trading action, percentage, forecast or target return remains `education_only`. Add rows 07 and 08 to the Skill route table.

- [ ] **Step 5: Run focused tests and verify they pass**

Run: `npm test -- --run src/course-content.test.ts src/interaction-answer.test.ts` from `client/`; `python3 -m pytest backend/tests/test_courseware_registry.py backend/tests/test_lesson_runtime.py -q` from the project root.

Expected: both courses have a narrative opener, seven unique three-option choices, valid correct answers, four or more evidence rows, and parseable HTTPS sources.

- [ ] **Step 6: Commit the course content and courseware**

```bash
git add client/src/course-content.ts client/src/course-content.test.ts backend/app/courseware.py backend/app/skills/financial-learning-teacher backend/tests/test_courseware_registry.py
git commit -m "Add fund and volatility courseware"
```

### Task 3: Render foundation and advanced tracks as separate course-map sections

**Files:**
- Modify: `client/src/course-content.ts`
- Modify: `client/src/course-content.test.ts`
- Modify: `client/src/pages/index/index.tsx`
- Modify: `client/src/pages/index/index.scss`

- [ ] **Step 1: Write the failing course-section contract test**

```ts
import { COURSE_SECTIONS } from './course-content'

it('groups six foundation courses before two advanced courses', () => {
  expect(COURSE_SECTIONS.map(section => section.title)).toEqual(['从生活开始学理财', '理财进阶课'])
  expect(COURSE_SECTIONS[0].courses).toHaveLength(6)
  expect(COURSE_SECTIONS[1].courses.map(course => course.id)).toEqual(['fund-stock-basics', 'volatility-time'])
})
```

- [ ] **Step 2: Run the test and verify it fails because `COURSE_SECTIONS` is not exported**

Run: `npm test -- --run src/course-content.test.ts` from `client/`.

Expected: module export failure.

- [ ] **Step 3: Export two ordered course sections and render them independently**

```ts
// client/src/course-content.ts
export const COURSE_LIST = Object.values(COURSE_CONTENT)
export const COURSE_SECTIONS = [
  { eyebrow: 'COURSE MAP', title: '从生活开始学理财', courses: COURSE_LIST.slice(0, 6) },
  { eyebrow: 'ADVANCED TRACK', title: '理财进阶课', courses: COURSE_LIST.slice(6) },
] as const
```

Replace the single `COURSE_LIST.map()` block in `Home()` with `COURSE_SECTIONS.map()` and put a separate heading and grid inside each section. Replace hard-coded `6` / `6 门` in the hero stat and map count with `COURSE_LIST.length` / `${COURSE_LIST.length} 门`. Preserve every existing course-card click handler, status label and progress segment.

Add `.course-section + .course-section` spacing and a restrained advanced-track heading treatment in `index.scss`; do not shrink type or cards.

- [ ] **Step 4: Run focused tests and build**

Run: `npm test -- --run src/course-content.test.ts src/course-engine.test.ts src/learning-storage.test.ts && npm run typecheck && npm run build:h5` from `client/`.

Expected: all commands exit 0; the course map has two headings, six cards in the first group and two cards in the second group.

- [ ] **Step 5: Commit the course-map UI**

```bash
git add client/src/course-content.ts client/src/course-content.test.ts client/src/pages/index/index.tsx client/src/pages/index/index.scss
git commit -m "Group advanced financial courses on home"
```

### Task 4: Document the eight-course curriculum and run the full regression suite

**Files:**
- Modify: `README.md`
- Modify: `../README.md`
- Modify: `backend/app/skills/financial-learning-teacher/README.md` only if it states six courses

- [ ] **Step 1: Update public curriculum copy**

Change every current-course count from six to eight. Keep courses 01–06 under “基础课”, add the “理财进阶课” label before 07–08, and describe their boundaries as fund/stock mechanism and volatility/time literacy, not investment recommendations.

- [ ] **Step 2: Run the full verification commands**

Run:

```bash
python3 -m pytest backend/tests -q
cd client && npm test -- --run && npm run typecheck && npm run build:h5
git diff --check
```

Expected: all test suites pass, H5 build completes, and no whitespace errors are reported.

- [ ] **Step 3: Commit and publish**

```bash
git add README.md ../README.md backend/app/skills/financial-learning-teacher/README.md
git commit -m "Document advanced financial literacy track"
git push origin HEAD:main
```

## Plan self-review

- Coverage: Tasks 1–2 create the two lessons, shared IDs, progress migration, backend catalogue, courseware and compliance routes. Task 3 creates the requested visual dividing title between 06 and 07. Task 4 documents and verifies the complete feature.
- No placeholders: course titles, IDs, all eight teaching moments, evidence requirements, UI sections, exact test commands and commit scopes are specified.
- Type consistency: `fund-stock-basics` and `volatility-time` are used consistently across client registry, backend catalogue, courseware and sections; `COURSE_SECTIONS` is the sole grouping export consumed by the home page.
