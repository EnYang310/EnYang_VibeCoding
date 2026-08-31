import { describe, expect, it } from 'vitest'
import { answerReceivedMessage, answerRequestFailedMessage } from './teacher-turn-feedback'

describe('teacher turn feedback', () => {
  it('confirms a submitted answer immediately while the full explanation is prepared', () => {
    expect(answerReceivedMessage()).toContain('已经收到你的答案')
    expect(answerReceivedMessage()).toContain('讲解')
  })

  it('uses a short retry prompt when the teacher has not responded in time', () => {
    expect(answerRequestFailedMessage()).not.toContain('没有收到答案')
    expect(answerRequestFailedMessage()).toBe('LLM思考超时，请重试。')
  })
})
