import { COURSE_IDS, UNIT_IDS, createLearningState, type CourseId, type CourseProgress, type LearningState } from './course-engine'

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const isCourseId = (value: unknown): value is CourseId => typeof value === 'string' && COURSE_IDS.includes(value as CourseId)

function hydrateCourse(raw: unknown): CourseProgress {
  const empty = createLearningState().courses['money-jobs']
  if (!isRecord(raw)) return empty
  const rawIndex = typeof raw.unitIndex === 'number' && Number.isFinite(raw.unitIndex) ? Math.trunc(raw.unitIndex) : 0
  const unitIndex = Math.max(0, Math.min(UNIT_IDS.length - 1, rawIndex))
  const reviewUnits = Array.isArray(raw.reviewUnits)
    ? [...new Set(raw.reviewUnits.filter(value => Number.isInteger(value) && value >= 0 && value < UNIT_IDS.length - 1) as number[])]
    : []
  const answers: Record<number, string> = {}
  if (isRecord(raw.answers)) {
    Object.entries(raw.answers).forEach(([key, value]) => {
      const index = Number(key)
      if (Number.isInteger(index) && index >= 0 && index < UNIT_IDS.length && typeof value === 'string') answers[index] = value
    })
  }
  const reviewingUnit = typeof raw.reviewingUnit === 'number' && reviewUnits.includes(raw.reviewingUnit)
    ? raw.reviewingUnit
    : null
  return {
    unitIndex,
    completed: raw.completed === true,
    reviewUnits,
    reviewingUnit,
    answers,
    actionCard: typeof raw.actionCard === 'string' ? raw.actionCard : ''
  }
}

export function hydrateLearningState(raw: unknown): LearningState {
  const fresh = createLearningState()
  if (!isRecord(raw) || raw.version !== 1 || !isRecord(raw.courses)) return fresh
  const rawCourses = raw.courses
  const courses = Object.fromEntries(COURSE_IDS.map(id => [id, hydrateCourse(rawCourses[id])])) as LearningState['courses']
  return {
    version: 1,
    activeCourseId: isCourseId(raw.activeCourseId) ? raw.activeCourseId : '',
    lastCourseId: isCourseId(raw.lastCourseId) ? raw.lastCourseId : (isCourseId(raw.activeCourseId) ? raw.activeCourseId : ''),
    courses
  }
}
