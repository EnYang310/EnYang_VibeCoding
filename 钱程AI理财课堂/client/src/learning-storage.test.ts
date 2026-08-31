import { describe, expect, it } from 'vitest'
import { createLearningState } from './course-engine'
import { hydrateLearningState, readLearningHomeState } from './learning-storage'

describe('learning state storage', () => {
  it('returns a complete six-course state for invalid or legacy data', () => {
    expect(hydrateLearningState(null)).toEqual(createLearningState())
    expect(hydrateLearningState({ courseId: 'money-jobs', unit: 2 })).toEqual(createLearningState())
  })

  it('keeps valid progress while filling newly introduced fields', () => {
    const state = createLearningState()
    const raw = JSON.parse(JSON.stringify(state))
    raw.activeCourseId = 'money-jobs'
    raw.courses['money-jobs'] = {
      unitIndex: 3,
      completed: false,
      reviewUnits: [1],
      answers: { 0: '日期明确' },
      actionCard: ''
    }
    const hydrated = hydrateLearningState(raw)
    expect(hydrated.courses['money-jobs'].unitIndex).toBe(3)
    expect(hydrated.courses['money-jobs'].reviewingUnit).toBe(null)
    expect(hydrated.courses['money-jobs'].answers[0]).toBe('日期明确')
  })

  it('clamps corrupt indices and ignores unknown course ids', () => {
    const state = createLearningState() as any
    state.activeCourseId = 'unknown'
    state.courses.tradeoffs.unitIndex = 999
    state.courses.tradeoffs.reviewUnits = [-1, 2, 99, 2]
    const hydrated = hydrateLearningState(state)
    expect(hydrated.activeCourseId).toBe('')
    expect(hydrated.courses.tradeoffs.unitIndex).toBe(7)
    expect(hydrated.courses.tradeoffs.reviewUnits).toEqual([2])
  })

  it('opens the application at the course home while keeping saved progress', () => {
    const saved = createLearningState()
    saved.activeCourseId = 'money-jobs'
    saved.courses['money-jobs'].unitIndex = 3

    const opened = readLearningHomeState(saved)

    expect(opened.activeCourseId).toBe('')
    expect(opened.courses['money-jobs'].unitIndex).toBe(3)
  })
})
