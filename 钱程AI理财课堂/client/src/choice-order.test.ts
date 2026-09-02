import { describe, expect, it } from 'vitest'
import { COURSE_LIST } from './course-content'
import { orderedChoiceOptions } from './choice-order'

describe('choice option order', () => {
  it('keeps every authored option exactly once while moving the correct option across A, B and C', () => {
    const correctPositions = new Set<number>()

    COURSE_LIST.flatMap(course => course.units).filter(unit => unit.interaction === 'single-choice').forEach(unit => {
      const ordered = orderedChoiceOptions(unit)
      expect(ordered).toHaveLength(3)
      expect([...ordered].sort()).toEqual([...(unit.options || [])].sort())
      correctPositions.add(ordered.indexOf(unit.correctOption || ''))
    })

    expect(correctPositions).toEqual(new Set([0, 1, 2]))
  })

  it('keeps one question in the same order after a rerender or return visit', () => {
    const unit = COURSE_LIST[0].units[1]
    expect(orderedChoiceOptions(unit)).toEqual(orderedChoiceOptions(unit))
  })
})
