import { describe, expect, it } from 'vitest'
import { COURSE_CONTENT } from './course-content'

describe('six lesson content contract', () => {
  it('contains six courses with eight distinct teaching units', () => {
    expect(Object.keys(COURSE_CONTENT)).toHaveLength(6)
    for (const course of Object.values(COURSE_CONTENT)) {
      expect(course.units).toHaveLength(8)
      expect(new Set(course.units.map(unit => unit.id)).size).toBe(8)
      expect(course.units.slice(1).every(unit => unit.interaction === 'single-choice')).toBe(true)
      expect(course.units.slice(1).every(unit => unit.questionContext && unit.options?.length === 3 && unit.correctOption)).toBe(true)
      course.units.slice(1).forEach(unit => {
        expect(unit.options?.filter(option => option === unit.correctOption)).toHaveLength(1)
      })
    }
  })

  it('keeps the course guide separate from seven interactive questions', () => {
    for (const course of Object.values(COURSE_CONTENT)) {
      expect(course.units[0].interaction).toBe('narrative')
      expect(course.units.slice(1)).toHaveLength(7)
    }
  })
})
