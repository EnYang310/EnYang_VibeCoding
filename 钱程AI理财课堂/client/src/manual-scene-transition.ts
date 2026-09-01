export type ManualSceneTransitionInput = {
  unitIndex: number
  unitCount: number
  confirmedAnswer: string
}

export type ManualSceneTransition = {
  nextUnitIndex: number
  saveAnswer: string
  markForReview: boolean
  clearsPendingAdvance: true
}

export function manualSceneTransition(input: ManualSceneTransitionInput): ManualSceneTransition | null {
  if (input.unitIndex < 0 || input.unitIndex >= input.unitCount - 1) return null
  const saveAnswer = input.confirmedAnswer.trim()
  return {
    nextUnitIndex: input.unitIndex + 1,
    saveAnswer,
    markForReview: !saveAnswer,
    clearsPendingAdvance: true,
  }
}
