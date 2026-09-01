export type InteractionTurnPayload = {
  assistant_reply?: { reply?: string }
  tool_call?: { tool_name?: string, unit_id?: string } | null
}

export function hasTeacherFeedback(payload: InteractionTurnPayload): boolean {
  return Boolean(payload.assistant_reply?.reply?.trim())
}

export function matchingNextInteractionCard(payload: InteractionTurnPayload, nextUnitId: string): boolean {
  return payload.tool_call?.tool_name === 'present_interaction_card' && payload.tool_call.unit_id === nextUnitId
}
