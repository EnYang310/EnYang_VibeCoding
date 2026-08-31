import { describe, expect, it } from 'vitest'
import { COURSE_CONTENT } from './course-content'
import { completionHint, encodeInteractionAnswer, isInteractionComplete, reviewedChoice } from './interaction-answer'

describe('interaction completion contracts', () => {
  it('uses single-choice cards for every interactive lesson turn', () => {
    Object.values(COURSE_CONTENT).forEach(course => {
      course.units.slice(1).forEach(unit => expect(unit.interaction).toBe('single-choice'))
    })
  })

  it('accepts a selected option without requiring a second text input', () => {
    const unit = COURSE_CONTENT['money-jobs'].units[1]
    expect(isInteractionComplete(unit, encodeInteractionAnswer('single-choice', { choice: '' }))).toBe(false)
    expect(isInteractionComplete(unit, encodeInteractionAnswer('single-choice', { choice: unit.options?.[0] }))).toBe(true)
  })

  it('lets a learner send a selected short answer so the teacher can follow up in chat', () => {
    const unit = COURSE_CONTENT['money-jobs'].units[1]
    const answer = encodeInteractionAnswer('single-choice', { choice: unit.options?.[1] })
    expect(isInteractionComplete(unit, answer)).toBe(true)
    expect(completionHint(unit, answer)).toBe('已选好答案。确认后，程老师会继续讲解。')
  })

  it('rejects a choice outside the authored options', () => {
    const unit = COURSE_CONTENT['future-date'].units[7]
    expect(isInteractionComplete(unit, encodeInteractionAnswer('single-choice', { choice: '随便选一个' }))).toBe(false)
  })

  it('labels the learner choice separately from the authored correct answer', () => {
    const unit = COURSE_CONTENT['money-jobs'].units[1]
    const review = reviewedChoice(unit, encodeInteractionAnswer('single-choice', { choice: unit.options?.[1] }))

    expect(review.yourChoice).toBe(`你的选择：${unit.options?.[1]}`)
    expect(review.correctAnswer).toBe(`正确答案：${unit.correctOption}`)
  })
})
