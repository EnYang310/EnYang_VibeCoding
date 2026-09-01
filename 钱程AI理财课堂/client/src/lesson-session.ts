type Abortable = PromiseLike<unknown> & { abort?: () => void }

/**
 * Owns work started inside one visible classroom. Closing it immediately
 * aborts cancellable transport tasks and makes every late completion stale.
 */
export function createLessonSession() {
  let generation = 0
  const pending = new Set<Abortable>()

  return {
    token: () => generation,
    isCurrent: (token: number) => token === generation,
    track: <T extends Abortable>(request: T): T => {
      pending.add(request)
      Promise.resolve(request).then(
        () => pending.delete(request),
        () => pending.delete(request)
      )
      return request
    },
    cancel: (request: Abortable | null | undefined) => {
      if (!request || !pending.delete(request)) return
      request.abort?.()
    },
    close: () => {
      generation += 1
      pending.forEach(request => request.abort?.())
      pending.clear()
    }
  }
}

export type LessonSession = ReturnType<typeof createLessonSession>
