export type DeferredInteractionCard<TCard = unknown> = {
  sceneId: string
  card: TCard
  answer: string
}

// A teaching turn can return both the explanation and the next exercise.  The
// exercise belongs after the explanation's audio, never beside its first word.
export function shouldRevealDeferredInteractionCard<TCard>(
  deferred: DeferredInteractionCard<TCard> | null,
  settledSceneId: string | null
): deferred is DeferredInteractionCard<TCard> {
  return Boolean(deferred && settledSceneId && deferred.sceneId === settledSceneId)
}
