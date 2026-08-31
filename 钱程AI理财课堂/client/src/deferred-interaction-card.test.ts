import { describe, expect, it } from 'vitest'
import { shouldRevealDeferredInteractionCard } from './deferred-interaction-card'

describe('deferred interaction cards', () => {
  it('keeps the next question hidden until its preceding lecture audio has settled', () => {
    const deferred = { sceneId: 'scene-money-jobs-why-buffer', card: { unit_id: 'buffer' }, answer: 'A' }

    expect(shouldRevealDeferredInteractionCard(deferred, null)).toBe(false)
    expect(shouldRevealDeferredInteractionCard(deferred, 'scene-another-lesson')).toBe(false)
    expect(shouldRevealDeferredInteractionCard(deferred, 'scene-money-jobs-why-buffer')).toBe(true)
  })
})
