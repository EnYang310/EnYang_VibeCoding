import { useMemo } from 'react'
import { Text, View } from '@tarojs/components'
import type { CourseUnit } from '../../course-content'
import { decodeInteractionAnswer, encodeInteractionAnswer } from '../../interaction-answer'

type Props = { unit: CourseUnit; value: string; accent: string; onChange: (value: string) => void }

export function InteractionPanel({ unit, value, accent, onChange }: Props) {
  const selected = useMemo(() => {
    const data = decodeInteractionAnswer(value, unit.interaction)
    return typeof data.choice === 'string' ? data.choice : ''
  }, [unit.interaction, value])
  if (unit.interaction === 'narrative') return null
  return <View className='single-choice-panel'>
    <Text className='choice-label'>互动暂停点 · 单选题</Text>
    <Text className='choice-context'>{unit.questionContext}</Text>
    <Text className='choice-question'>{unit.prompt}</Text>
    <View className='single-choice-options'>
      {unit.options?.map((option, index) => <View
        key={option}
        className={`single-choice-option ${selected === option ? 'selected' : ''}`}
        style={{ '--course-accent': accent } as React.CSSProperties}
        onClick={() => onChange(encodeInteractionAnswer('single-choice', { choice: option }))}
      >
        <Text className='choice-index'>{String.fromCharCode(65 + index)}</Text>
        <Text className='choice-copy'>{option}</Text>
      </View>)}
    </View>
  </View>
}
