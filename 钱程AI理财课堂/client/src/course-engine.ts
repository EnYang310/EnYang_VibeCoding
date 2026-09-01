export const COURSE_IDS = [
  'money-jobs',
  'safety-net',
  'product-map',
  'tradeoffs',
  'future-date',
  'steady-mind',
  'fund-stock-basics',
  'volatility-time'
] as const

export const UNIT_IDS = [
  'opening',
  'initial-judgment',
  'hands-on',
  'consequence',
  'ai-feedback-1',
  'transfer',
  'ai-feedback-2',
  'action-card'
] as const

export type CourseId = (typeof COURSE_IDS)[number]

export type CourseProgress = {
  unitIndex: number
  completed: boolean
  reviewUnits: number[]
  reviewingUnit: number | null
  answers: Record<number, string>
  actionCard: string
}

export type LearningState = {
  version: 1
  activeCourseId: CourseId | ''
  lastCourseId: CourseId | ''
  courses: Record<CourseId, CourseProgress>
}

const emptyCourseProgress = (): CourseProgress => ({
  unitIndex: 0,
  completed: false,
  reviewUnits: [],
  reviewingUnit: null,
  answers: {},
  actionCard: ''
})

export function createLearningState(): LearningState {
  return {
    version: 1,
    activeCourseId: '',
    lastCourseId: '',
    courses: Object.fromEntries(COURSE_IDS.map(id => [id, emptyCourseProgress()])) as Record<CourseId, CourseProgress>
  }
}

function updateCourse(state: LearningState, courseId: CourseId, next: CourseProgress): LearningState {
  return { ...state, activeCourseId: courseId, lastCourseId: courseId, courses: { ...state.courses, [courseId]: next } }
}

export function advanceCourse(state: LearningState, courseId: CourseId, payload: { answer?: string } = {}): LearningState {
  const current = state.courses[courseId]
  const answer = (payload.answer || '').trim()
  if (current.reviewingUnit === current.unitIndex) {
    if (!answer) return state
    const reviewUnits = current.reviewUnits.filter(index => index !== current.unitIndex)
    return updateCourse(state, courseId, {
      ...current,
      unitIndex: current.completed ? UNIT_IDS.length - 1 : Math.min(current.unitIndex + 1, UNIT_IDS.length - 1),
      reviewUnits,
      reviewingUnit: null,
      answers: { ...current.answers, [current.unitIndex]: answer }
    })
  }
  if (current.unitIndex === UNIT_IDS.length - 1) {
    if (!answer) return state
    return updateCourse(state, courseId, {
      ...current,
      completed: true,
      actionCard: answer,
      answers: { ...current.answers, [current.unitIndex]: answer }
    })
  }
  return updateCourse(state, courseId, {
    ...current,
    unitIndex: current.unitIndex + 1,
    answers: answer ? { ...current.answers, [current.unitIndex]: answer } : current.answers
  })
}

export function skipCourseUnit(state: LearningState, courseId: CourseId): LearningState {
  const current = state.courses[courseId]
  if (current.unitIndex === UNIT_IDS.length - 1) return state
  const reviewUnits = current.reviewUnits.includes(current.unitIndex)
    ? current.reviewUnits
    : [...current.reviewUnits, current.unitIndex]
  return updateCourse(state, courseId, { ...current, unitIndex: current.unitIndex + 1, reviewUnits })
}

export function restartCourse(state: LearningState, courseId: CourseId): LearningState {
  return updateCourse(state, courseId, emptyCourseProgress())
}

export function openReviewUnit(state: LearningState, courseId: CourseId, unitIndex: number): LearningState {
  const current = state.courses[courseId]
  if (!current.reviewUnits.includes(unitIndex) || unitIndex < 0 || unitIndex >= UNIT_IDS.length - 1) return state
  return updateCourse(state, courseId, { ...current, unitIndex, reviewingUnit: unitIndex })
}

export function selectCourse(state: LearningState, courseId: CourseId): LearningState {
  return { ...state, activeCourseId: courseId, lastCourseId: courseId }
}

export function leaveCourse(state: LearningState): LearningState {
  return { ...state, activeCourseId: '' }
}
