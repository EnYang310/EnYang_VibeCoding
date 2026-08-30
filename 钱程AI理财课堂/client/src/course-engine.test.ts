import { describe, expect, it } from 'vitest'
import { advanceCourse, createLearningState, openReviewUnit, restartCourse, skipCourseUnit } from './course-engine'

describe('course progress', () => {
  it('keeps independent checkpoints for all six courses', () => {
    let state = createLearningState()
    state = advanceCourse(state, 'money-jobs', { answer: '先写日期' })
    state = advanceCourse(state, 'safety-net', { answer: '先守住房租' })
    expect(state.courses['money-jobs'].unitIndex).toBe(1)
    expect(state.courses['safety-net'].unitIndex).toBe(1)
    expect(state.courses['product-map'].unitIndex).toBe(0)
  })

  it('remembers the last course after returning to the course map', async () => {
    const { leaveCourse, selectCourse } = await import('./course-engine')
    let state = selectCourse(createLearningState(), 'steady-mind')
    state = leaveCourse(state)
    expect(state.activeCourseId).toBe('')
    expect(state.lastCourseId).toBe('steady-mind')
  })

  it('marks skipped units for review and advances exactly once', () => {
    const state = skipCourseUnit(createLearningState(), 'tradeoffs')
    expect(state.courses.tradeoffs.unitIndex).toBe(1)
    expect(state.courses.tradeoffs.reviewUnits).toEqual([0])
  })

  it('restarts only the selected course', () => {
    let state = advanceCourse(createLearningState(), 'money-jobs', { answer: '日期' })
    state = advanceCourse(state, 'safety-net', { answer: '缓冲' })
    state = restartCourse(state, 'money-jobs')
    expect(state.courses['money-jobs'].unitIndex).toBe(0)
    expect(state.courses['safety-net'].unitIndex).toBe(1)
  })

  it('does not advance after the final action card until it contains text', () => {
    let state = createLearningState()
    state.courses['future-date'].unitIndex = 7
    const unchanged = advanceCourse(state, 'future-date', { answer: '' })
    expect(unchanged.courses['future-date'].completed).toBe(false)
    const completed = advanceCourse(state, 'future-date', { answer: '周日写下目标日期' })
    expect(completed.courses['future-date'].completed).toBe(true)
  })

  it('can reopen a skipped unit and removes it after a reviewed answer', () => {
    let state = skipCourseUnit(createLearningState(), 'product-map')
    state = openReviewUnit(state, 'product-map', 0)
    expect(state.courses['product-map'].unitIndex).toBe(0)
    state = advanceCourse(state, 'product-map', { answer: '补上这一回合' })
    expect(state.courses['product-map'].reviewUnits).toEqual([])
  })
})
