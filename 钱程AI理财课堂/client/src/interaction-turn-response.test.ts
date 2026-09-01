import { describe, expect, it } from 'vitest'
import { hasTeacherFeedback, matchingNextInteractionCard } from './interaction-turn-response'

describe('interaction turn response handling', () => {
  const teacherReply = { assistant_reply: { reply: '老师先把你的判断讲清楚。' } }

  it('keeps a valid teacher reply even when the next-card metadata is absent', () => {
    expect(hasTeacherFeedback(teacherReply)).toBe(true)
    expect(matchingNextInteractionCard(teacherReply, 'hands-on')).toBe(false)
  })

  it('does not discard a valid teacher reply when a stale card points elsewhere', () => {
    const response = { ...teacherReply, tool_call: { tool_name: 'present_interaction_card', unit_id: 'action-card' } }

    expect(hasTeacherFeedback(response)).toBe(true)
    expect(matchingNextInteractionCard(response, 'hands-on')).toBe(false)
  })
})
