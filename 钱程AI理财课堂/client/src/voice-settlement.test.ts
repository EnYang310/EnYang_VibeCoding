import { describe, expect, it } from 'vitest'
import { shouldSettleVoiceScene } from './voice-settlement'

describe('voice scene settlement', () => {
  it('does not unlock the next interaction card when browser autoplay is blocked', () => {
    expect(shouldSettleVoiceScene('autoplay_blocked')).toBe(false)
    expect(shouldSettleVoiceScene('playback_error')).toBe(false)
  })

  it('unlocks the next card only after narration ends or the learner explicitly skips it', () => {
    expect(shouldSettleVoiceScene('ended')).toBe(true)
    expect(shouldSettleVoiceScene('learner_skipped')).toBe(true)
  })
})
