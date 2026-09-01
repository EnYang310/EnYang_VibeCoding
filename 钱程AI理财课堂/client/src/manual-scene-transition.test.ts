import { describe, expect, it } from 'vitest'
import { manualSceneTransition } from './manual-scene-transition'

describe('manual next-scene transition', () => {
  it('keeps a confirmed answer while moving to the next scene', () => {
    expect(manualSceneTransition({ unitIndex: 2, unitCount: 8, confirmedAnswer: '选项 A' })).toEqual({
      nextUnitIndex: 3,
      saveAnswer: '选项 A',
      markForReview: false,
      clearsPendingAdvance: true,
    })
  })

  it('marks an unanswered scene for review instead of inventing an answer', () => {
    expect(manualSceneTransition({ unitIndex: 2, unitCount: 8, confirmedAnswer: '' })).toEqual({
      nextUnitIndex: 3,
      saveAnswer: '',
      markForReview: true,
      clearsPendingAdvance: true,
    })
  })

  it('does not offer a next scene after the final action card', () => {
    expect(manualSceneTransition({ unitIndex: 7, unitCount: 8, confirmedAnswer: '' })).toBeNull()
  })
})
