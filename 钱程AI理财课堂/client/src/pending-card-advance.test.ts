import { describe, expect, it } from 'vitest'
import { clearPendingCardAdvance, pendingCardAdvanceForCourse, savePendingCardAdvance } from './pending-card-advance'

describe('pending card advance', () => {
  it('keeps a confirmed answer and reply count available after leaving and reopening a course', () => {
    const saved = savePendingCardAdvance({}, 'money-jobs', {
      unitId: 'initial-judgment',
      nextUnitId: 'money-calendar',
      answer: '{"v":1,"kind":"single-choice","data":{"choice":"先留房租"}}'
    })

    expect(pendingCardAdvanceForCourse(saved, 'money-jobs')).toEqual({
      unitId: 'initial-judgment',
      nextUnitId: 'money-calendar',
      answer: '{"v":1,"kind":"single-choice","data":{"choice":"先留房租"}}'
    })
    expect(pendingCardAdvanceForCourse(clearPendingCardAdvance(saved, 'money-jobs'), 'money-jobs')).toBeUndefined()
  })
})
