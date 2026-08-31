export type PendingCardAdvance = { unitId: string, nextUnitId: string, answer: string }
export type PendingCardAdvances = Record<string, PendingCardAdvance>

const isPendingCardAdvance = (value: unknown): value is PendingCardAdvance => Boolean(value)
  && typeof value === 'object'
  && typeof (value as PendingCardAdvance).unitId === 'string'
  && typeof (value as PendingCardAdvance).nextUnitId === 'string'
  && typeof (value as PendingCardAdvance).answer === 'string'

export function hydratePendingCardAdvances(raw: unknown): PendingCardAdvances {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  return Object.fromEntries(Object.entries(raw).filter(([, value]) => isPendingCardAdvance(value))) as PendingCardAdvances
}

export function pendingCardAdvanceForCourse(advances: PendingCardAdvances, courseId: string): PendingCardAdvance | undefined {
  return advances[courseId]
}

export function savePendingCardAdvance(advances: PendingCardAdvances, courseId: string, advance: PendingCardAdvance): PendingCardAdvances {
  return { ...advances, [courseId]: advance }
}

export function clearPendingCardAdvance(advances: PendingCardAdvances, courseId: string): PendingCardAdvances {
  const { [courseId]: _removed, ...remaining } = advances
  return remaining
}
