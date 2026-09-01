import { describe, expect, it, vi } from 'vitest'
import { createLessonSession } from './lesson-session'

describe('lesson session', () => {
  it('aborts every in-flight request and invalidates its token when a learner leaves', () => {
    const session = createLessonSession()
    const abortFirst = vi.fn()
    const abortSecond = vi.fn()
    const first = new Promise<void>(() => undefined)
    const second = new Promise<void>(() => undefined)
    const token = session.token()

    session.track(Object.assign(first, { abort: abortFirst }))
    session.track(Object.assign(second, { abort: abortSecond }))
    session.close()

    expect(abortFirst).toHaveBeenCalledOnce()
    expect(abortSecond).toHaveBeenCalledOnce()
    expect(session.isCurrent(token)).toBe(false)
  })

  it('does not abort a request that already completed', async () => {
    const session = createLessonSession()
    const abort = vi.fn()
    let resolve!: () => void
    const pending = new Promise<void>(done => { resolve = done })

    session.track(Object.assign(pending, { abort }))
    resolve()
    await pending
    await Promise.resolve()
    session.close()

    expect(abort).not.toHaveBeenCalled()
  })

  it('cancels one specific in-flight request without invalidating the whole lesson', () => {
    const session = createLessonSession()
    const abort = vi.fn()
    const pending = new Promise<void>(() => undefined)
    const token = session.token()
    const request = Object.assign(pending, { abort })

    session.track(request)
    session.cancel(request)

    expect(abort).toHaveBeenCalledOnce()
    expect(session.isCurrent(token)).toBe(true)
  })
})
