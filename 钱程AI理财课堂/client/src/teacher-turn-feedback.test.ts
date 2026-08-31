import { describe, expect, it } from 'vitest'
import { answerReceivedMessage, answerRequestFailedMessage } from './teacher-turn-feedback'

describe('teacher turn feedback', () => {
  it('confirms a submitted answer immediately while the full explanation is prepared', () => {
    expect(answerReceivedMessage()).toContain('已经收到你的答案')
    expect(answerReceivedMessage()).toContain('讲解')
  })

  it('never falsely claims that a failed response means the answer was not received', () => {
    expect(answerRequestFailedMessage()).toContain('答案已经保留')
    expect(answerRequestFailedMessage()).not.toContain('没有收到答案')
  })
})
