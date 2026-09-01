import { describe, expect, it } from 'vitest'
import { COURSE_CONTENT, COURSE_SECTIONS } from './course-content'

describe('eight lesson content contract', () => {
  it('contains eight courses with eight distinct teaching units', () => {
    expect(Object.keys(COURSE_CONTENT)).toHaveLength(8)
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

  it('keeps the advanced courses grounded in product mechanics and volatility literacy', () => {
    expect(COURSE_CONTENT['fund-stock-basics'].title).toContain('基金和股票')
    expect(COURSE_CONTENT['volatility-time'].title).toContain('涨跌不是信号')
    expect(COURSE_CONTENT['fund-stock-basics'].units[1].correctOption).toContain('所有权')
    expect(COURSE_CONTENT['volatility-time'].units[1].correctOption).toContain('不预测')
  })

  it('groups six foundation courses before two advanced courses', () => {
    expect(COURSE_SECTIONS.map(section => section.title)).toEqual(['从生活开始学理财', '理财进阶课'])
    expect(COURSE_SECTIONS[0].courses).toHaveLength(6)
    expect(COURSE_SECTIONS[1].courses.map(course => course.id)).toEqual(['fund-stock-basics', 'volatility-time'])
  })

  it('keeps the course guide separate from seven interactive questions', () => {
    for (const course of Object.values(COURSE_CONTENT)) {
      expect(course.units[0].interaction).toBe('narrative')
      expect(course.units.slice(1)).toHaveLength(7)
    }
  })
})
