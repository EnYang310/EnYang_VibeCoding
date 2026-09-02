import type { CourseUnit } from './course-content'

function stableHash(value: string): number {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

/**
 * A question must not reshuffle after a learner has picked an option.  This
 * deterministic shuffle varies the correct answer across A/B/C while keeping
 * the authored option text (and therefore answer checking) unchanged.
 */
export function orderedChoiceOptions(unit: CourseUnit): string[] {
  const options = unit.options || []
  if (options.length !== 3 || !unit.correctOption || !options.includes(unit.correctOption)) return options

  const hash = stableHash(`${unit.id}|${unit.title}|${unit.prompt}`)
  const correctIndex = hash % 3
  const distractors = options.filter(option => option !== unit.correctOption)
  if ((hash >>> 2) % 2 === 1) distractors.reverse()

  const ordered = [...distractors]
  ordered.splice(correctIndex, 0, unit.correctOption)
  return ordered
}
