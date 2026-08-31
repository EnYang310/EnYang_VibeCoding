import type { CourseUnit } from './course-content'

export type AnswerData = Record<string, unknown>
type AnswerEnvelope = { v: 1, kind: string, data: AnswerData }

export function encodeInteractionAnswer(kind: string, data: AnswerData): string {
  return JSON.stringify({ v: 1, kind, data })
}

export function decodeInteractionAnswer(value: string, kind: string): AnswerData {
  if (!value) return {}
  try {
    const parsed = JSON.parse(value) as Partial<AnswerEnvelope>
    return parsed.v === 1 && parsed.kind === kind && parsed.data && typeof parsed.data === 'object' ? parsed.data : {}
  } catch { return {} }
}

const selectedChoice = (unit: CourseUnit, value: string) => {
  const data = decodeInteractionAnswer(value, unit.interaction)
  return typeof data.choice === 'string' ? data.choice.trim() : ''
}

export function completionHint(unit: CourseUnit, value: string): string {
  if (unit.interaction === 'narrative') return '程老师正在带你进入本课情境。'
  return unit.options?.includes(selectedChoice(unit, value)) ? '已选好答案。确认后，程老师会继续讲解。' : '请选择一个答案，再确认作答。'
}

export function isInteractionComplete(unit: CourseUnit, value: string): boolean {
  return unit.interaction === 'single-choice' && Boolean(unit.options?.includes(selectedChoice(unit, value)))
}

export function shouldRevealChoiceReview(unit: CourseUnit, value: string, confirmed: boolean): boolean {
  return confirmed && isInteractionComplete(unit, value) && Boolean(unit.correctOption)
}

export function humanizeInteractionAnswer(value: string): string {
  try {
    const parsed = JSON.parse(value) as Partial<AnswerEnvelope>
    if (parsed.v !== 1 || !parsed.data || typeof parsed.data !== 'object') return value
    const choice = typeof parsed.data.choice === 'string' ? parsed.data.choice.trim() : ''
    return choice ? `你的选择：${choice}` : value
  } catch { return value }
}

export function reviewedChoice(unit: CourseUnit, value: string): { yourChoice: string; correctAnswer: string } {
  const choice = selectedChoice(unit, value)
  return {
    yourChoice: choice ? `你的选择：${choice}` : '本题暂时跳过',
    correctAnswer: unit.correctOption ? `正确答案：${unit.correctOption}` : '',
  }
}
