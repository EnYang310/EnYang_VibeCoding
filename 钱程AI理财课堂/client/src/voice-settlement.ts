export type VoiceSceneOutcome = 'ended' | 'learner_skipped' | 'autoplay_blocked' | 'playback_error'

export function shouldSettleVoiceScene(outcome: VoiceSceneOutcome): boolean {
  return outcome === 'ended' || outcome === 'learner_skipped'
}
