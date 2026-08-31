import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Input, ScrollView, Text, View } from '@tarojs/components'
import { COURSE_CONTENT, COURSE_LIST, type CourseUnit } from '../../course-content'
import { UNIT_IDS, advanceCourse, createLearningState, leaveCourse, openReviewUnit, restartCourse, selectCourse, skipCourseUnit, type CourseId, type LearningState } from '../../course-engine'
import { readLearningHomeState } from '../../learning-storage'
import { createLessonSession, type LessonSession } from '../../lesson-session'
import { shouldRevealDeferredInteractionCard, type DeferredInteractionCard } from '../../deferred-interaction-card'
import { answerReceivedMessage, answerRequestFailedMessage } from '../../teacher-turn-feedback'
import { shouldSettleVoiceScene } from '../../voice-settlement'
import { InteractionPanel } from './interaction-panel'
import { completionHint, humanizeInteractionAnswer, isInteractionComplete } from '../../interaction-answer'
import './index.scss'

const STORAGE_KEY = 'qiancheng-learning-v1'
const CLASSROOM_STORAGE_KEY = 'qiancheng-classroom-v1'

type EvidenceNote = { evidence_id: string, text: string }
type TeachingArtifactKind = 'one_liner' | 'steps' | 'timeline' | 'contrast' | 'scenario' | 'checklist' | 'quote' | 'warning'
type TeachingArtifact = { kind: TeachingArtifactKind, appear_after_paragraph: number, title: string, lead: string, items: string[], note: string }
type TeachingScene = { screen_title: string, screen_summary: string, key_points: string[], common_misconception: string, right_reframe: string, subtitle_excerpt: string, full_caption: string[], teaching_artifacts?: TeachingArtifact[] }
type ChatMessage = {
  role: 'user' | 'assistant'
  text: string
  // A real turn placeholder, not a fake answer. It is replaced atomically
  // when this exact request returns, so late requests cannot overwrite a
  // newer classroom state.
  pending?: boolean
  turnId?: number
  // One course owns one continuous transcript.  Keeping the originating card
  // lets us place each exchange next to the card that prompted it.
  unitId: string
  evidenceIds?: string[]
  evidenceNotes?: EvidenceNote[]
  source?: 'kimi' | 'local_fallback' | 'connection_error'
  teachingScene?: TeachingScene
}
type ChatMap = Record<string, ChatMessage[]>
type PresentedCard = { tool_name: 'present_interaction_card', status: 'presented', course_id: string, unit_id: string, teacher_intro: string, unit_title: string }
type AwaitingNext = { unitId: string, nextUnitId: string, answer: string }

const sceneVoiceId = (unitId: string, scene: TeachingScene) => `scene-${unitId}-${scene.screen_title}-${scene.full_caption.join('').slice(0, 24)}`

type VoiceSubtitle = { text: string, begin_time: number, end_time: number, begin_index: number, end_index: number }
type VoiceSegment = { audio_url: string, audio_base64?: string, subtitles: VoiceSubtitle[] }
type SpeechStatus = { sceneId: string | null, paused: boolean, subtitles: VoiceSubtitle[], activeIndex: number, paragraphIndex: number }

type ApiResult<T> = { data: T, statusCode: number }
const isWeapp = process.env.TARO_ENV === 'weapp'

// H5 keeps same-origin HTTP requests. The mini program uses CloudBase's
// private WeChat-to-container channel, which is why no request-domain entry
// is needed in the WeChat public platform console.
function apiRequest<T>(path: string, method: 'GET' | 'POST', data?: unknown, session?: LessonSession): Promise<ApiResult<T>> {
  if (isWeapp) {
    const cloud = (globalThis as typeof globalThis & { wx?: { cloud?: { callContainer: (options: Record<string, unknown>) => Promise<{ data: T }> } } }).wx?.cloud
    if (!cloud) throw new Error('请在微信开发者工具中启用云开发环境')
    const request = cloud.callContainer({
      config: { env: CLOUDBASE_ENV_ID },
      path,
      method,
      data,
      header: { 'X-WX-SERVICE': CLOUDBASE_SERVICE, 'content-type': 'application/json' }
    })
    session?.track(request)
    return request.then(result => ({ data: result.data, statusCode: 200 }))
  }
  const request = Taro.request<T>({ url: `${API_BASE}${path}`, method, data })
  session?.track(request)
  return request
}

function materializeMiniAudio(segment: VoiceSegment, index: number): string {
  if (!segment.audio_base64) return segment.audio_url
  const fs = Taro.getFileSystemManager()
  const path = `${Taro.env.USER_DATA_PATH}/qiancheng-voice-${Date.now()}-${index}.mp3`
  fs.writeFileSync(path, segment.audio_base64, 'base64')
  return path
}

function useLectureVoice(session: LessonSession) {
  const [status, setStatus] = useState<SpeechStatus>({ sceneId: null, paused: false, subtitles: [], activeIndex: -1, paragraphIndex: -1 })
  const [settledSceneId, setSettledSceneId] = useState<string | null>(null)
  const miniAudioRef = useRef<ReturnType<typeof Taro.createInnerAudioContext> | null>(null)
  // H5 uses the browser's real Audio element.  It is substantially more
  // reliable than the Taro shim for an mp3 served by the same classroom
  // domain, while the mini-program continues to use InnerAudioContext.
  const webAudioRef = useRef<HTMLAudioElement | null>(null)
  const playbackTokenRef = useRef(0)
  const isWebAudio = () => typeof window !== 'undefined' && typeof Audio !== 'undefined'

  const stop = useCallback(() => {
    playbackTokenRef.current += 1
    if (isWebAudio()) {
      const audio = webAudioRef.current
      if (audio) { audio.pause(); audio.currentTime = 0 }
    } else {
      miniAudioRef.current?.stop()
    }
    setSettledSceneId(null)
    setStatus({ sceneId: null, paused: false, subtitles: [], activeIndex: -1, paragraphIndex: -1 })
  }, [])

  const toggle = useCallback(async (sceneId: string, paragraphs: string[]) => {
    if (status.sceneId === sceneId) {
      if (status.paused) {
        if (isWebAudio()) {
          try {
            await webAudioRef.current?.play()
          } catch {
            Taro.showToast({ title: '浏览器仍未允许播放，请再点一次', icon: 'none' })
            return
          }
        } else miniAudioRef.current?.play()
        setStatus(current => ({ ...current, paused: false }))
      } else {
        if (isWebAudio()) webAudioRef.current?.pause()
        else miniAudioRef.current?.pause()
        setStatus(current => ({ ...current, paused: true }))
      }
      return
    }
    const sessionToken = session.token()
    try {
      const playbackToken = ++playbackTokenRef.current
      setSettledSceneId(null)
      setStatus({ sceneId, paused: false, subtitles: [], activeIndex: -1, paragraphIndex: -1 })
      // Critical path: synthesize the first spoken paragraph only. The rest
      // starts at the same time and is queued before paragraph one finishes.
      // This removes the former "wait for five paragraphs" dead time.
      const getSegments = async (part: string[]) => {
        if (!part.length) return [] as VoiceSegment[]
        const response = await apiRequest<{ segments?: VoiceSegment[], detail?: string }>('/api/v1/voice/synthesize', 'POST', { paragraphs: part }, session)
        const data = response.data as { segments?: VoiceSegment[], detail?: string }
        if (response.statusCode >= 400 || !data.segments?.length) throw new Error(data.detail || '朗读音频暂时不可用')
        return data.segments
      }
      const firstPromise = getSegments(paragraphs.slice(0, 1))
      const restPromise = getSegments(paragraphs.slice(1))
      const segments = await firstPromise
      if (playbackToken !== playbackTokenRef.current || !session.isCurrent(sessionToken)) return
      let remainingLoaded = false
      const remaining = restPromise.then(
        items => { remainingLoaded = true; segments.push(...items); return items },
        () => { remainingLoaded = true; return [] as VoiceSegment[] }
      )
      let currentIndex = 0
      const playNext = async () => {
        if (playbackToken !== playbackTokenRef.current || !session.isCurrent(sessionToken)) return
        const nextSegment = segments[currentIndex]
        if (!nextSegment) {
          // The teacher should never race ahead of queued audio. At most this
          // waits for the already-running background request; no subtitle is
          // advanced while there is no corresponding sound.
          if (!remainingLoaded && currentIndex > 0) {
            try { await remaining } catch { /* handled by the normal end state below */ }
            if (playbackToken !== playbackTokenRef.current) return
            return playNext()
          }
          setStatus(current => current.sceneId === sceneId ? { sceneId: null, paused: false, subtitles: [], activeIndex: -1, paragraphIndex: -1 } : current)
          if (shouldSettleVoiceScene('ended')) setSettledSceneId(sceneId)
          return
        }
        const src = isWeapp
          ? materializeMiniAudio(nextSegment, currentIndex)
          : (/^https?:\/\//.test(nextSegment.audio_url) ? nextSegment.audio_url : `${API_BASE}${nextSegment.audio_url}`)
        setStatus({ sceneId, paused: false, subtitles: nextSegment.subtitles, activeIndex: 0, paragraphIndex: currentIndex })
        if (isWebAudio()) {
          const audio = webAudioRef.current || new Audio()
          webAudioRef.current = audio
          audio.onended = () => { currentIndex += 1; void playNext() }
          audio.ontimeupdate = () => {
            if (!session.isCurrent(sessionToken) || playbackToken !== playbackTokenRef.current) return
            const subtitles = segments[currentIndex]?.subtitles || []
            const now = Math.round(audio.currentTime * 1000)
            const activeIndex = subtitles.findIndex(item => now >= item.begin_time && now < item.end_time)
            if (activeIndex >= 0) setStatus(current => current.sceneId === sceneId && current.activeIndex !== activeIndex ? { ...current, subtitles, activeIndex } : current)
          }
          audio.onerror = () => {
            if (!session.isCurrent(sessionToken) || playbackToken !== playbackTokenRef.current) return
            setStatus(current => current.sceneId === sceneId ? { sceneId: null, paused: false, subtitles: [], activeIndex: -1, paragraphIndex: -1 } : current)
            if (shouldSettleVoiceScene('playback_error')) setSettledSceneId(sceneId)
            Taro.showToast({ title: '朗读没有开始，点“朗读本段”重试', icon: 'none' })
          }
          audio.src = src
          audio.play().catch(() => {
            if (!session.isCurrent(sessionToken) || playbackToken !== playbackTokenRef.current) return
            // Autoplay permission is a browser policy, not the end of this
            // lecture. Keep the scene active so its deferred question remains
            // locked until the learner deliberately starts playback.
            setStatus(current => current.sceneId === sceneId ? { ...current, paused: true } : current)
            if (shouldSettleVoiceScene('autoplay_blocked')) setSettledSceneId(sceneId)
            Taro.showToast({ title: '浏览器需要你点一下“继续朗读”才可播放', icon: 'none' })
          })
          return
        }
        const audio = miniAudioRef.current || Taro.createInnerAudioContext()
        miniAudioRef.current = audio
        audio.offEnded(); audio.offError(); audio.offTimeUpdate()
        audio.onEnded(() => { currentIndex += 1; void playNext() })
        audio.onTimeUpdate(() => {
          if (!session.isCurrent(sessionToken) || playbackToken !== playbackTokenRef.current) return
          const subtitles = segments[currentIndex]?.subtitles || []
          const now = Math.round(audio.currentTime * 1000)
          const activeIndex = subtitles.findIndex(item => now >= item.begin_time && now < item.end_time)
          if (activeIndex >= 0) setStatus(current => current.sceneId === sceneId && current.activeIndex !== activeIndex ? { ...current, subtitles, activeIndex } : current)
        })
        audio.onError(() => {
          if (!session.isCurrent(sessionToken) || playbackToken !== playbackTokenRef.current) return
          setStatus(current => current.sceneId === sceneId ? { sceneId: null, paused: false, subtitles: [], activeIndex: -1, paragraphIndex: -1 } : current)
          if (shouldSettleVoiceScene('playback_error')) setSettledSceneId(sceneId)
          Taro.showToast({ title: '朗读没有开始，点“朗读本段”重试', icon: 'none' })
        })
        audio.src = src
        audio.play()
      }
      void playNext()
    } catch (error) {
      if (!session.isCurrent(sessionToken)) return
      setStatus(current => current.sceneId === sceneId ? { sceneId: null, paused: false, subtitles: [], activeIndex: -1, paragraphIndex: -1 } : current)
      if (shouldSettleVoiceScene('playback_error')) setSettledSceneId(sceneId)
      Taro.showToast({ title: error instanceof Error ? error.message : '朗读暂时不可用', icon: 'none' })
      return
    }
  }, [session, status.sceneId, status.paused])

  useEffect(() => () => {
    miniAudioRef.current?.destroy()
    webAudioRef.current?.pause()
  }, [])

  return { status, settledSceneId, toggle, stop }
}

const readState = (): LearningState => {
  try { return readLearningHomeState(Taro.getStorageSync(STORAGE_KEY)) } catch { return createLearningState() }
}

const readClassroom = (): { chatByUnit: ChatMap, cardTimeline: Record<string, PresentedCard[]> } => {
  try {
    const stored = Taro.getStorageSync(CLASSROOM_STORAGE_KEY) as Partial<{ chatByUnit: ChatMap, cardTimeline: Record<string, PresentedCard[]> }>
    return { chatByUnit: stored?.chatByUnit || {}, cardTimeline: stored?.cardTimeline || {} }
  } catch { return { chatByUnit: {}, cardTimeline: {} } }
}

const hasStarted = (state: LearningState, courseId: CourseId) => {
  const progress = state.courses[courseId]
  return progress.unitIndex > 0 || Object.keys(progress.answers).length > 0 || progress.reviewUnits.length > 0 || progress.completed
}

export default function Index() {
  const [learning, setLearning] = useState<LearningState>(readState)
  const initialClassroom = useMemo(readClassroom, [])
  const [answer, setAnswer] = useState('')
  const [chatByUnit, setChatByUnit] = useState<ChatMap>(initialClassroom.chatByUnit)
  const [chatDraft, setChatDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [submittingInteraction, setSubmittingInteraction] = useState(false)
  const [presentedCard, setPresentedCard] = useState<PresentedCard | null>(null)
  const [deferredCard, setDeferredCard] = useState<DeferredInteractionCard<PresentedCard> | null>(null)
  const [cardLoading, setCardLoading] = useState(false)
  const [awaitingNext, setAwaitingNext] = useState<AwaitingNext | null>(null)
  const [courseChatCompleted, setCourseChatCompleted] = useState(false)
  const [captionExpanded, setCaptionExpanded] = useState(false)
  const [cardTimeline, setCardTimeline] = useState<Record<string, PresentedCard[]>>(initialClassroom.cardTimeline)
  const openingRequestRef = useRef('')
  const autoReadNextSceneRef = useRef(false)
  const turnSequenceRef = useRef(0)
  const lessonSessionRef = useRef<LessonSession>(createLessonSession())
  const lectureVoice = useLectureVoice(lessonSessionRef.current)
  const course = learning.activeCourseId ? COURSE_CONTENT[learning.activeCourseId] : null
  const progress = course ? learning.courses[course.id] : null
  const unit = course && progress ? course.units[progress.unitIndex] : null
  const freeQuestionMode = Boolean(progress?.completed && progress.reviewingUnit === null) || courseChatCompleted
  // The classroom conversation belongs to the course, not to one page. The
  // current unit only tells the teacher which piece of courseware to use.
  const chatKey = course ? course.id : ''
  const chat = chatKey ? (chatByUnit[chatKey] || []) : []
  const activeCardId = course && progress && presentedCard?.unit_id === unit?.id ? `active-card-${course.id}-${progress.unitIndex}` : ''
  const waitingForNextCard = Boolean(deferredCard)

  useEffect(() => {
    if (!course || !presentedCard || presentedCard.course_id !== course.id) return
    setCardTimeline(current => {
      const cards = current[course.id] || []
      if (cards.some(card => card.unit_id === presentedCard.unit_id)) return current
      return { ...current, [course.id]: [...cards, presentedCard] }
    })
  }, [course?.id, presentedCard?.course_id, presentedCard?.unit_id])

  useEffect(() => {
    try { Taro.setStorageSync(CLASSROOM_STORAGE_KEY, { chatByUnit, cardTimeline }) } catch { /* optional classroom history */ }
  }, [chatByUnit, cardTimeline])

  const persist = (next: LearningState) => {
    setLearning(next)
    try { Taro.setStorageSync(STORAGE_KEY, next) } catch { /* storage can be unavailable in privacy mode */ }
  }

  const closeVisibleLesson = useCallback(() => {
    lessonSessionRef.current.close()
    turnSequenceRef.current += 1
    openingRequestRef.current = ''
    autoReadNextSceneRef.current = false
    lectureVoice.stop()
    setSending(false)
    setSubmittingInteraction(false)
    setCardLoading(false)
    setAwaitingNext(null)
    setPresentedCard(null)
    setDeferredCard(null)
    setCaptionExpanded(false)
    setChatDraft('')
    setCourseChatCompleted(false)
  }, [lectureVoice.stop])

  useEffect(() => {
    if (course && progress) setAnswer(progress.answers[progress.unitIndex] || (progress.unitIndex === 7 ? progress.actionCard : ''))
  }, [course?.id, progress?.unitIndex, progress?.reviewingUnit])

  useEffect(() => {
    if (!course || !unit) return
    // The action card has already closed the learning path. Returning to a
    // completed course reopens its transcript as free Q&A, never as a fresh
    // duplicate of the final choice card.
    if (progress?.completed && progress.reviewingUnit === null) {
      setPresentedCard(null)
      setCardLoading(false)
      return
    }
    if (unit.id === 'opening') {
      const requestKey = `${course.id}:${progress?.unitIndex}`
      if (openingRequestRef.current === requestKey) return
      openingRequestRef.current = requestKey
      let cancelled = false
      const session = lessonSessionRef.current
      const sessionToken = session.token()
      setCardLoading(true)
      // A course opens on a concrete choice, not an AI monologue.  The first
      // voice, captions and teaching artifacts begin only after the learner
      // has submitted this choice.
      autoReadNextSceneRef.current = false
      lectureVoice.stop()
      const nextUnit = course.units[1]
      apiRequest<Partial<PresentedCard>>('/api/v1/lessons/interaction-card', 'POST', {
        course_id: course.id, unit_id: nextUnit?.id
      }, session).then(result => {
        const card = result.data as Partial<PresentedCard>
        if (result.statusCode >= 400 || card.tool_name !== 'present_interaction_card' || card.unit_id !== nextUnit?.id) throw new Error('first card failed')
        if (cancelled || !session.isCurrent(sessionToken)) return
        setPresentedCard(card as PresentedCard)
        persist(advanceCourse(learning, course.id, { answer: '第一题已呈现' }))
      }).catch(() => {
        if (!cancelled && session.isCurrent(sessionToken)) Taro.showToast({ title: '第一道题暂时未送达，请重新进入课程', icon: 'none' })
      }).finally(() => { if (!cancelled && session.isCurrent(sessionToken)) setCardLoading(false) })
      return () => { cancelled = true }
    }
    if (presentedCard?.course_id === course.id && presentedCard.unit_id === unit.id) {
      setCardLoading(false)
      return
    }
    let cancelled = false
    const session = lessonSessionRef.current
    const sessionToken = session.token()
    setPresentedCard(null)
    setCardLoading(true)
    apiRequest<Partial<PresentedCard>>('/api/v1/lessons/interaction-card', 'POST', {
      course_id: course.id, unit_id: unit.id
    }, session).then(result => {
      const data = result.data as Partial<PresentedCard>
      if (!cancelled && session.isCurrent(sessionToken) && result.statusCode < 400 && data.tool_name === 'present_interaction_card' && data.unit_id === unit.id) setPresentedCard(data as PresentedCard)
    }).catch(() => undefined).finally(() => { if (!cancelled && session.isCurrent(sessionToken)) setCardLoading(false) })
    return () => { cancelled = true }
  }, [course?.id, unit?.id, progress?.unitIndex, progress?.completed, progress?.reviewingUnit, presentedCard?.course_id, presentedCard?.unit_id])

  useEffect(() => {
    if (!course || !shouldRevealDeferredInteractionCard(deferredCard, lectureVoice.settledSceneId)) return
    const nextCard = deferredCard.card
    const submittedAnswer = deferredCard.answer
    setDeferredCard(null)
    setPresentedCard(nextCard)
    persist(advanceCourse(learning, course.id, { answer: submittedAnswer }))
    setAnswer('')
    setAwaitingNext(null)
  }, [course?.id, deferredCard, lectureVoice.settledSceneId, learning])

  const startCourse = (courseId: CourseId) => {
    closeVisibleLesson()
    const target = learning.courses[courseId]
    setAnswer(target.answers[target.unitIndex] || (target.unitIndex === 7 ? target.actionCard : ''))
    persist(selectCourse(learning, courseId))
  }
  const goHome = () => { closeVisibleLesson(); setAnswer(''); persist(leaveCourse(learning)) }

  const restart = () => {
    if (!course) return
    Taro.showModal({
      title: '从头学习这一课？',
      content: '只清除本课的回答、待回看和行动卡；另外五课不会受影响。',
      confirmText: '重新开始',
      success: result => {
        if (result.confirm) {
          closeVisibleLesson()
          persist(restartCourse(learning, course.id))
          setChatByUnit(current => ({ ...current, [course.id]: [] }))
          setCardTimeline(current => ({ ...current, [course.id]: [] }))
          setAnswer('')
        }
      }
    })
  }

  const sendChat = async () => {
    const message = chatDraft.trim()
    if (!message || !course || !unit || !progress || sending || waitingForNextCard) return
    const session = lessonSessionRef.current
    const sessionToken = session.token()
    const turnId = ++turnSequenceRef.current
    const userMessage: ChatMessage = { role: 'user', text: message, unitId: unit.id, turnId }
    const pendingMessage: ChatMessage = { role: 'assistant', text: '程老师正在整理这一段讲解…', unitId: unit.id, pending: true, turnId }
    const previous = chat
    autoReadNextSceneRef.current = true
    lectureVoice.stop()
    setChatDraft('')
    setChatByUnit(current => ({ ...current, [chatKey]: [...(current[chatKey] || []), userMessage, pendingMessage] }))
    setSending(true)
    try {
      const result = await apiRequest<{ reply?: string, evidence_ids?: string[], evidence_notes?: EvidenceNote[], source?: 'kimi' | 'local_fallback', teaching_scene?: TeachingScene, tool_call?: PresentedCard | null }>('/api/v1/lessons/chat', 'POST', {
          course_id: course.id,
          unit_id: unit.id,
          message,
          history: previous.slice(-6).map(item => ({ role: item.role, content: item.text })),
          context: {
            answer_summaries: Object.entries(progress.answers).map(([index, text]) => `回合 ${Number(index) + 1}：${humanizeInteractionAnswer(text).slice(0, 300)}`),
            pending_review_units: progress.reviewUnits,
            // The card becomes eligible for advancement only after its
            // confirm button has been pressed. Merely selecting an option is
            // never enough to let ordinary chat skip the exercise.
            current_card_completed: awaitingNext?.unitId === unit.id,
            current_card_answer: awaitingNext?.unitId === unit.id ? humanizeInteractionAnswer(awaitingNext.answer) : '',
            awaiting_next: awaitingNext?.unitId === unit.id,
            next_unit_id: awaitingNext?.unitId === unit.id ? awaitingNext.nextUnitId : '',
            assistant_replies_since_card: awaitingNext?.unitId === unit.id ? messagesFor(unit.id).filter(item => item.role === 'assistant' && !item.pending).length : 0,
            course_finished: false,
            free_chat_mode: freeQuestionMode
          }
      }, session)
      const data = result.data as { reply?: string, evidence_ids?: string[], evidence_notes?: EvidenceNote[], source?: 'kimi' | 'local_fallback', teaching_scene?: TeachingScene, tool_call?: PresentedCard | null }
      if (result.statusCode >= 400 || !data.reply) throw new Error('chat request failed')
      if (turnId !== turnSequenceRef.current || !session.isCurrent(sessionToken)) return
      setChatByUnit(current => ({ ...current, [chatKey]: [...(current[chatKey] || []).filter(item => item.turnId !== turnId || !item.pending), { role: 'assistant', text: data.reply!, unitId: unit.id, turnId, evidenceIds: data.evidence_ids || [], evidenceNotes: data.evidence_notes || [], source: data.source, teachingScene: data.teaching_scene }] }))
      if (data.tool_call?.tool_name === 'present_interaction_card' && data.tool_call.unit_id === course.units[progress.unitIndex + 1]?.id) {
        const submittedAnswer = awaitingNext?.unitId === unit.id ? awaitingNext.answer : answer
        if (data.teaching_scene) {
          setDeferredCard({ sceneId: sceneVoiceId(unit.id, data.teaching_scene), card: data.tool_call, answer: submittedAnswer })
        } else {
          setPresentedCard(data.tool_call)
          persist(advanceCourse(learning, course.id, { answer: submittedAnswer }))
          setAnswer('')
          setAwaitingNext(null)
        }
      }
    } catch {
      if (turnId !== turnSequenceRef.current || !session.isCurrent(sessionToken)) return
      setChatByUnit(current => ({ ...current, [chatKey]: [...(current[chatKey] || []).filter(item => item.turnId !== turnId || !item.pending), { role: 'assistant', text: `这次没连上老师，但主线先别丢：${course.focus}。你可以稍后再问，或者先回到刚才的生活情境想一想。`, unitId: unit.id, turnId, evidenceIds: [], source: 'connection_error' }] }))
    } finally {
      if (session.isCurrent(sessionToken)) setSending(false)
    }
  }

  const messagesFor = (unitId: string) => chat.filter(item => item.unitId === unitId)
  const isTeacherUnit = false
  const canContinue = Boolean(unit && presentedCard?.unit_id === unit.id) && isInteractionComplete(unit!, answer)

  const continueLesson = async () => {
    if (!course || !unit || !canContinue || submittingInteraction || freeQuestionMode) return
    const session = lessonSessionRef.current
    const sessionToken = session.token()
    const submitted = answer
    const nextUnit = course.units[progress!.unitIndex + 1]
    const turnId = ++turnSequenceRef.current
    autoReadNextSceneRef.current = true
    lectureVoice.stop()
    // Do not make a learner stare at a button while a long teacher turn is
    // being generated.  This is an acknowledgement of the submitted answer,
    // not a completed AI turn, so it never affects the card cadence.
    setChatByUnit(current => ({ ...current, [chatKey]: [...(current[chatKey] || []), {
      role: 'assistant', unitId: unit.id, text: answerReceivedMessage(), pending: true, turnId
    }] }))
    setSubmittingInteraction(true)
    if (!nextUnit) {
      try {
        const result = await apiRequest<{ reply?: string, evidence_ids?: string[], evidence_notes?: EvidenceNote[], source?: 'kimi' | 'local_fallback', teaching_scene?: TeachingScene }>('/api/v1/lessons/chat', 'POST', {
          course_id: course.id,
          unit_id: unit.id,
          message: `【课程完成】我完成了行动卡：${humanizeInteractionAnswer(submitted)}`,
          history: chat.slice(-6).map(item => ({ role: item.role, content: item.text })),
          context: {
            answer_summaries: Object.entries(progress!.answers).map(([index, text]) => `回合 ${Number(index) + 1}：${humanizeInteractionAnswer(text).slice(0, 300)}`),
            pending_review_units: progress!.reviewUnits,
            current_card_completed: true,
            current_card_answer: humanizeInteractionAnswer(submitted),
            assistant_replies_since_card: messagesFor(unit.id).filter(item => item.role === 'assistant' && !item.pending).length,
            course_finished: true,
            free_chat_mode: false
          }
        }, session)
        const data = result.data as { reply?: string, evidence_ids?: string[], evidence_notes?: EvidenceNote[], source?: 'kimi' | 'local_fallback', teaching_scene?: TeachingScene }
        if (result.statusCode >= 400 || !data.reply) throw new Error('action card feedback failed')
        if (turnId !== turnSequenceRef.current || !session.isCurrent(sessionToken)) return
        setChatByUnit(current => ({ ...current, [chatKey]: [...(current[chatKey] || []).filter(item => item.turnId !== turnId || !item.pending), { role: 'assistant', unitId: unit.id, text: data.reply!, evidenceIds: data.evidence_ids || [], evidenceNotes: data.evidence_notes || [], source: data.source || 'local_fallback', teachingScene: data.teaching_scene, turnId }] }))
        persist(advanceCourse(learning, course.id, { answer: submitted }))
        setAnswer('')
        setPresentedCard(null)
        setCourseChatCompleted(true)
      } catch {
        if (turnId === turnSequenceRef.current && session.isCurrent(sessionToken)) {
          setChatByUnit(current => ({ ...current, [chatKey]: [...(current[chatKey] || []).filter(item => item.turnId !== turnId || !item.pending), { role: 'assistant', unitId: unit.id, text: answerRequestFailedMessage(), source: 'connection_error', turnId }] }))
          Taro.showToast({ title: '讲解没有返回，答案已保留', icon: 'none' })
        }
      } finally {
        if (session.isCurrent(sessionToken)) setSubmittingInteraction(false)
      }
      return
    }
    try {
      const result = await apiRequest<{ assistant_reply?: { reply?: string, evidence_ids?: string[], evidence_notes?: EvidenceNote[], source?: 'kimi' | 'local_fallback', teaching_scene?: TeachingScene }, tool_call?: PresentedCard | null }>('/api/v1/lessons/interaction-turn', 'POST', {
          course_id: course.id,
          unit_id: unit.id,
          next_unit_id: nextUnit.id,
          submitted_answer: humanizeInteractionAnswer(submitted),
          message: '提交互动卡',
          history: chat.slice(-6).map(item => ({ role: item.role, content: item.text })),
          context: {
            answer_summaries: Object.entries(progress!.answers).map(([index, text]) => `回合 ${Number(index) + 1}：${humanizeInteractionAnswer(text).slice(0, 300)}`),
            pending_review_units: progress!.reviewUnits,
            current_card_completed: true,
            current_card_answer: humanizeInteractionAnswer(submitted),
            assistant_replies_since_card: messagesFor(unit.id).filter(item => item.role === 'assistant' && !item.pending).length,
            course_finished: false,
            free_chat_mode: false
          }
      }, session)
      const data = result.data as { assistant_reply?: { reply?: string, evidence_ids?: string[], evidence_notes?: EvidenceNote[], source?: 'kimi' | 'local_fallback', teaching_scene?: TeachingScene }, tool_call?: PresentedCard | null }
      if (result.statusCode >= 400 || !data.assistant_reply?.reply || (data.tool_call && (data.tool_call.tool_name !== 'present_interaction_card' || data.tool_call.unit_id !== nextUnit.id))) throw new Error('interaction turn failed')
      if (turnId !== turnSequenceRef.current || !session.isCurrent(sessionToken)) return
      setChatByUnit(current => ({ ...current, [chatKey]: [...(current[chatKey] || []).filter(item => item.turnId !== turnId || !item.pending), { role: 'assistant', unitId: unit.id, text: data.assistant_reply!.reply!, evidenceIds: data.assistant_reply!.evidence_ids || [], evidenceNotes: data.assistant_reply!.evidence_notes || [], source: data.assistant_reply!.source || 'local_fallback', teachingScene: data.assistant_reply!.teaching_scene, turnId }] }))
      if (data.tool_call?.tool_name === 'present_interaction_card' && data.tool_call.unit_id === nextUnit.id) {
        const feedbackScene = data.assistant_reply.teaching_scene
        if (feedbackScene) {
          setDeferredCard({ sceneId: sceneVoiceId(unit.id, feedbackScene), card: data.tool_call, answer: submitted })
        } else {
          setPresentedCard(data.tool_call)
          persist(advanceCourse(learning, course.id, { answer: submitted }))
          setAnswer('')
          setAwaitingNext(null)
        }
      } else {
        // The learner can freely chat here. The next question will appear only
        // after the teaching gate judges the current idea to be solid enough.
        setAwaitingNext({ unitId: unit.id, nextUnitId: nextUnit.id, answer: submitted })
      }
    } catch {
      if (turnId === turnSequenceRef.current && session.isCurrent(sessionToken)) {
        setChatByUnit(current => ({ ...current, [chatKey]: [...(current[chatKey] || []).filter(item => item.turnId !== turnId || !item.pending), { role: 'assistant', unitId: unit.id, text: answerRequestFailedMessage(), source: 'connection_error', turnId }] }))
        Taro.showToast({ title: '讲解没有返回，答案已保留', icon: 'none' })
      }
    } finally {
      if (session.isCurrent(sessionToken)) setSubmittingInteraction(false)
    }
  }

  const skip = () => {
    if (!course || !unit) return
    persist(skipCourseUnit(learning, course.id))
    setAnswer('')
  }

  const lectureMessages = chat.filter(item => item.role === 'assistant' && item.teachingScene)
  const lectureScenes = lectureMessages.map(item => item.teachingScene as TeachingScene)
  const lectureSceneSignature = lectureScenes.map(sceneItem => sceneItem.full_caption.join('|')).join('||')
  const latestTeacher = [...chat].reverse().find(item => item.role === 'assistant' && item.teachingScene)
  const scene = latestTeacher?.teachingScene || {
    screen_title: unit?.screenTitle || unit?.title || '钱程课堂',
    screen_summary: unit?.interaction === 'narrative' ? unit.prompt : unit?.teachingGoal || course?.focus || '从生活情境开始，建立自己的判断。',
    key_points: unit?.screenKeyPoints || [course?.focus || '先把问题看清楚。'],
    common_misconception: '只记住一个亮眼词，就以为已经完成判断。',
    right_reframe: '回到题目里的用途、日期和规则，一步一步看。',
    subtitle_excerpt: cardLoading ? '程老师正在准备这段讲解…' : '跟着题目一步一步判断，不需要急着答对。',
    full_caption: [unit?.prompt || '从生活情境开始。', unit?.teachingGoal || course?.focus || '先把问题看清楚。', '如果哪里不明白，随时在下方问程老师。']
  }
  useEffect(() => { lectureVoice.stop() }, [course?.id])
  useEffect(() => () => {
    lessonSessionRef.current.close()
    lectureVoice.stop()
  }, [lectureVoice.stop])
  useEffect(() => {
    if (!autoReadNextSceneRef.current || lectureMessages.length === 0) return
    autoReadNextSceneRef.current = false
    const newestMessage = lectureMessages[lectureMessages.length - 1]
    const newestScene = newestMessage.teachingScene as TeachingScene
    lectureVoice.toggle(sceneVoiceId(newestMessage.unitId, newestScene), newestScene.full_caption)
  }, [lectureSceneSignature])
  const cards = course ? (cardTimeline[course.id] || []) : []

  if (!course || !progress || !unit) return <Home learning={learning} onStart={startCourse} />
  return <View className='page lesson-page' style={{ '--course-accent': course.color } as React.CSSProperties}>
    <View className='topbar'>
      <Text className='wordmark' onClick={goHome}>钱程</Text>
      <Text className='lesson-position'>{course.number} / 06</Text>
      <Text className='text-button' onClick={goHome}>课程地图</Text>
    </View>

    <View className='unit-progress'>
      {course.units.map((item, index) => <View key={item.id} className={`unit-track ${index < progress.unitIndex || progress.completed ? 'done' : ''} ${index === progress.unitIndex ? 'current' : ''}`} />)}
    </View>
    <View className='classroom-title'><Text className='eyebrow'>第 {progress.unitIndex + 1} / 8 环节 · {progress.reviewingUnit !== null ? '补上这一环节' : unit.title}</Text><Text className='lesson-title'>{course.title}</Text></View>

    <View className='teaching-stage transcript-stage'>
      <ScrollView scrollY className='classroom-transcript'>
        <CourseStartCard course={course} />
        <LessonMessages messages={messagesFor('opening')} voice={lectureVoice} />
        {cards.map(card => {
        const cardUnit = course.units.find(item => item.id === card.unit_id)
        if (!cardUnit) return null
        const active = card.unit_id === unit.id && presentedCard?.unit_id === card.unit_id
        return <View key={card.unit_id} className='timeline-turn'>
          {active ? <View id={activeCardId} className='stage-question-card timeline-card'>
            <Text className='teacher-line'>程老师 · 轮到你想一想</Text><Text className='card-teacher-intro'>{card.teacher_intro}</Text>
            <InteractionPanel key={`${course.id}-${progress.unitIndex}-${progress.reviewingUnit ?? 'main'}`} unit={cardUnit} value={answer} accent={course.color} onChange={setAnswer} />
            <Text className={`submission-hint ${canContinue ? 'ready' : ''}`}>{completionHint(cardUnit, answer)}</Text>
            <Button className='primary-action stage-confirm' disabled={!canContinue || submittingInteraction || freeQuestionMode} onClick={continueLesson}>{submittingInteraction ? '程老师正在准备讲解…' : '确认作答，听程老师讲解'}</Button>
          </View> : <HistoricChoiceCard unit={cardUnit} answer={progress.answers[course.units.indexOf(cardUnit)]} />}
          <LessonMessages messages={messagesFor(card.unit_id)} voice={lectureVoice} />
        </View>
        })}
        {(cardLoading || waitingForNextCard) && <View className='stage-loading'><Text>{waitingForNextCard ? '本段讲解结束后，下一道题会出现。' : '程老师正在准备下一个学习环节…'}</Text></View>}
      </ScrollView>
      <View className='caption-dock'>
        {lectureVoice.status.sceneId && <View className='caption-pause' onClick={() => lectureVoice.toggle(lectureVoice.status.sceneId!, [])}><Text>{lectureVoice.status.paused ? '▶' : 'Ⅱ'}</Text></View>}
        {lectureVoice.status.sceneId && lectureVoice.status.subtitles.length > 0 ? <SyncedCaption subtitles={lectureVoice.status.subtitles} activeIndex={lectureVoice.status.activeIndex} /> : <Text className='caption-short'>点击“朗读本段”后，字幕将跟随语音逐字同步。</Text>}
        <Text className='caption-expand' onClick={() => setCaptionExpanded(true)}>展开字幕全文</Text>
      </View>
      <View className='classroom-composer'>
        <View className='chat-compose'><Input value={chatDraft} disabled={waitingForNextCard || submittingInteraction} maxlength={500} onInput={event => setChatDraft(event.detail.value)} onConfirm={sendChat} placeholder={waitingForNextCard ? '请先听完这一段讲解…' : submittingInteraction ? '程老师正在结合你的答案讲解…' : '随时问程老师：解释、反驳、举例都可以…'} /><Button disabled={sending || submittingInteraction || waitingForNextCard || !chatDraft.trim()} onClick={sendChat}>{sending ? '…' : '发送'}</Button></View>
        <Text className='chat-tip'>{waitingForNextCard ? '程老师讲完后会进入下一道题。' : freeQuestionMode ? '这一课已经讲完。接下来可以自由问任何概念或生活情境。' : '自由提问不会跳过学习环节；程老师会在合适的学习节点自然带你进入下一题。'}</Text>
      </View>
    </View>
    {captionExpanded && <View className='caption-sheet'><View className='caption-sheet-inner'><Text className='caption-sheet-label'>本课讲解全文 · 已累计 {lectureScenes.length} 段</Text>{(lectureScenes.length > 0 ? lectureScenes : [scene]).map((lecture, sceneIndex) => <View key={`${lecture.screen_title}-${sceneIndex}`} className='caption-lesson'><Text className='caption-sheet-title'>{lecture.screen_title}</Text>{lecture.full_caption.map((paragraph, index) => <Text className='caption-paragraph' key={`${paragraph}-${index}`}>{paragraph}</Text>)}</View>)}<Button className='secondary-action caption-close' onClick={() => setCaptionExpanded(false)}>返回继续听</Button></View></View>}
    <Text className='restart-link' onClick={restart}>从头学习本课</Text>
    <View className='compliance-note'>本产品仅用于理财启蒙学习，不提供真实标的推荐、买卖指令或个性化资产配置。</View>
  </View>
}

function SyncedCaption({ subtitles, activeIndex }: { subtitles: VoiceSubtitle[], activeIndex: number }) {
  return <View className='caption-synced'>{subtitles.map((item, index) => <Text key={`${item.begin_index}-${index}`} className={`caption-token ${index < activeIndex ? 'passed' : ''} ${index === activeIndex ? 'active' : ''}`}>{item.text}</Text>)}</View>
}

function CourseStartCard({ course }: { course: typeof COURSE_CONTENT[CourseId] }) {
  return <View className='course-start-card'>
    <Text className='teacher-line'>程老师 · 本课导览</Text>
    <Text className='course-start-title'>{course.number} · {course.title}</Text>
    <Text className='course-start-copy'>{course.subtitle}</Text>
    <Text className='course-start-focus'>这一课会带你练习：{course.focus}</Text>
  </View>
}

function HistoricChoiceCard({ unit, answer }: { unit: CourseUnit, answer?: string }) {
  return <View className='stage-question-card timeline-card completed-card'>
    <Text className='teacher-line'>程老师 · 互动练习</Text>
    <Text className='historic-question-title'>{unit.title}</Text>
    <Text className='historic-question'>{unit.prompt}</Text>
    <View className='historic-choice'><Text>{answer ? humanizeInteractionAnswer(answer) : '本题暂时跳过'}</Text></View>
  </View>
}

function TeachingSceneMessage({ message, voice }: { message: ChatMessage, voice: ReturnType<typeof useLectureVoice> }) {
  const scene = message.teachingScene
  if (!scene) return null
  const sceneId = sceneVoiceId(message.unitId, scene)
  const isSpeaking = voice.status.sceneId === sceneId
  const artifacts = scene.teaching_artifacts || []
  const [played, setPlayed] = useState(false)
  const [visibleArtifactCount, setVisibleArtifactCount] = useState(0)
  useEffect(() => {
    if (isSpeaking) {
      setPlayed(true)
      setVisibleArtifactCount(artifacts.filter(item => item.appear_after_paragraph <= voice.status.paragraphIndex).length)
    } else if (played) {
      // Pausing, skipping, or finishing never leaves the lesson half-hidden.
      setVisibleArtifactCount(artifacts.length)
    }
  }, [isSpeaking, voice.status.paragraphIndex, played, artifacts.length])
  return <View className='teaching-scene-message'>
    <View className='scene-heading'><Text className='teacher-line'>程老师 · 本段讲解</Text><View className={`voice-toggle ${isSpeaking ? 'speaking' : ''}`} onClick={() => voice.toggle(sceneId, scene.full_caption)}><Text>{isSpeaking ? (voice.status.paused ? '▶ 继续朗读' : 'Ⅱ 暂停朗读') : '🔊 朗读本段'}</Text></View></View>
    <Text className='scene-title'>{scene.screen_title}</Text>
    <Text className='scene-summary'>{scene.screen_summary}</Text>
    <View className='artifact-stream'>{artifacts.slice(0, visibleArtifactCount).map((artifact, index) => <TeachingArtifactCard key={`${sceneId}-${artifact.kind}-${index}`} artifact={artifact} index={index} />)}</View>
  </View>
}

function TeachingArtifactCard({ artifact, index }: { artifact: TeachingArtifact, index: number }) {
  const label: Record<TeachingArtifactKind, string> = { one_liner: '一句话看懂', steps: '顺着想', timeline: '时间线', contrast: '别混在一起', scenario: '放进生活里', checklist: '自己核验', quote: '值得记住', warning: '容易踩坑' }
  if (artifact.kind === 'timeline') return <View className='artifact-card artifact-timeline'><Text className='artifact-label'>{label[artifact.kind]}</Text><Text className='artifact-title'>{artifact.title}</Text>{artifact.lead && <Text className='artifact-lead'>{artifact.lead}</Text>}<View className='timeline-artifact-list'>{artifact.items.map((item, itemIndex) => <View className='timeline-artifact-row' key={`${item}-${itemIndex}`}><Text className='timeline-artifact-dot' /><Text>{item}</Text></View>)}</View>{artifact.note && <Text className='artifact-note'>{artifact.note}</Text>}</View>
  if (artifact.kind === 'steps' || artifact.kind === 'checklist') return <View className={`artifact-card artifact-${artifact.kind}`}><Text className='artifact-label'>{label[artifact.kind]}</Text><Text className='artifact-title'>{artifact.title}</Text>{artifact.lead && <Text className='artifact-lead'>{artifact.lead}</Text>}<View className='artifact-step-list'>{artifact.items.map((item, itemIndex) => <View className='artifact-step' key={`${item}-${itemIndex}`}><Text className='artifact-step-mark'>{artifact.kind === 'checklist' ? '✓' : String(itemIndex + 1).padStart(2, '0')}</Text><Text>{item}</Text></View>)}</View>{artifact.note && <Text className='artifact-note'>{artifact.note}</Text>}</View>
  if (artifact.kind === 'contrast') return <View className='artifact-card artifact-contrast'><Text className='artifact-label'>{label[artifact.kind]}</Text><Text className='artifact-title'>{artifact.title}</Text><View className='contrast-columns'>{artifact.items.slice(0, 2).map((item, itemIndex) => <View className={`contrast-column ${itemIndex === 0 ? 'left' : 'right'}`} key={`${item}-${itemIndex}`}><Text>{item}</Text></View>)}</View>{artifact.lead && <Text className='artifact-note'>{artifact.lead}</Text>}{artifact.note && <Text className='artifact-note'>{artifact.note}</Text>}</View>
  return <View className={`artifact-card artifact-${artifact.kind}`}><Text className='artifact-label'>{label[artifact.kind]} · {String(index + 1).padStart(2, '0')}</Text><Text className='artifact-title'>{artifact.title}</Text>{artifact.lead && <Text className='artifact-lead'>{artifact.lead}</Text>}{artifact.items.length > 0 && <View className='artifact-plain-items'>{artifact.items.map((item, itemIndex) => <Text key={`${item}-${itemIndex}`}>• {item}</Text>)}</View>}{artifact.note && <Text className='artifact-note'>{artifact.note}</Text>}</View>
}

function LessonMessages({ messages, voice }: { messages: ChatMessage[], voice: ReturnType<typeof useLectureVoice> }) {
  return <>{messages.map((message, index) => <View key={`${message.unitId}-${message.role}-${index}`}>
    {message.pending && <View className='chat-bubble assistant thinking'><Text>{message.text}</Text><Text className='thinking-dots'>···</Text></View>}
    {!message.pending && message.role === 'assistant' && message.teachingScene && <TeachingSceneMessage message={message} voice={voice} />}
    {!message.pending && !message.teachingScene && <View className={`chat-bubble ${message.role}`}>
      {message.role === 'assistant' && <Text className={`source-badge ${message.source || 'connection_error'}`}>{message.source === 'kimi' ? 'Kimi 个性讲解' : message.source === 'local_fallback' ? '课件安全模式' : '连接提示'}</Text>}
      <Text>{message.text}</Text>
      {message.role === 'assistant' && message.evidenceNotes && message.evidenceNotes.length > 0 && <View className='evidence-box'><Text className='evidence-title'>本课依据</Text>{message.evidenceNotes.map(note => <View key={note.evidence_id} className='evidence-item'><Text className='evidence-id'>{note.evidence_id}</Text><Text>{note.text}</Text></View>)}</View>}
    </View>}
  </View>)}</>
}

function Home({ learning, onStart }: { learning: LearningState, onStart: (id: CourseId) => void }) {
  const completed = COURSE_LIST.filter(course => learning.courses[course.id].completed).length
  const started = COURSE_LIST.filter(course => hasStarted(learning, course.id)).length
  const active = learning.lastCourseId ? COURSE_CONTENT[learning.lastCourseId] : null
  return <View className='page home-page'>
    <View className='home-nav'><Text className='wordmark'>钱程</Text><Text className='nav-tag'>AI 理财启蒙课</Text></View>
    <View className='hero-block'>
      <Text className='hero-kicker'>不是背术语，是练判断</Text>
      <Text className='hero-title'>先看清你的钱，{`\n`}再决定它去哪里。</Text>
      <Text className='hero-copy'>六门 10–20 分钟互动课。每课有固定教学主线，也给你自由追问、反驳和改答案的空间。</Text>
      <View className='learning-stats'><View><Text className='stat-number'>{completed}</Text><Text className='stat-label'>已完成</Text></View><View><Text className='stat-number'>{started}</Text><Text className='stat-label'>已开始</Text></View><View><Text className='stat-number'>6</Text><Text className='stat-label'>全部课程</Text></View></View>
    </View>

    {active && <View className='resume-card' onClick={() => onStart(active.id)}><View><Text className='resume-kicker'>继续上次学习</Text><Text className='resume-title'>{active.number} · {active.title}</Text><Text className='resume-meta'>第 {learning.courses[active.id].unitIndex + 1} / 8 回合</Text></View><Text className='resume-arrow'>→</Text></View>}

    <View className='section-heading'><View><Text className='section-eyebrow'>COURSE MAP</Text><Text className='section-title'>从生活开始学理财</Text></View><Text className='section-count'>6 门</Text></View>
    <View className='course-grid'>{COURSE_LIST.map(course => {
      const progress = learning.courses[course.id]
      const status = progress.completed ? '已完成' : hasStarted(learning, course.id) ? `第 ${progress.unitIndex + 1}/8 回合` : '未开始'
      return <View className='course-card' key={course.id} style={{ '--course-accent': course.color } as React.CSSProperties} onClick={() => onStart(course.id)}>
        <View className='course-card-top'><Text className='course-number'>{course.number}</Text><Text className={`course-status ${progress.completed ? 'completed' : ''}`}>{status}</Text></View>
        <Text className='course-title'>{course.title}</Text><Text className='course-subtitle'>{course.subtitle}</Text>
        <View className='course-footer'><View className='mini-progress'>{course.units.map((_, index) => <View key={index} className={`mini-segment ${index < progress.unitIndex || progress.completed ? 'done' : ''}`} />)}</View>{progress.reviewUnits.length > 0 && <Text className='review-badge'>{progress.reviewUnits.length} 待回看</Text>}</View>
      </View>
    })}</View>
    <View className='home-principle'><Text className='principle-title'>固定主线，自由课堂</Text><Text>课程不会因聊天跑偏；你可以随时追问，AI 只用当前课件里的知识回应。涉及真实投资决策时，统一回到教育解释与风险提示。</Text></View>
    <View className='compliance-note'>钱程是理财启蒙学习工具，不构成投资建议。</View>
  </View>
}

function Completion({ courseId, learning, onHome, onReview, onRestart }: { courseId: CourseId, learning: LearningState, onHome: () => void, onReview: (index: number) => void, onRestart: () => void }) {
  const course = COURSE_CONTENT[courseId]
  const progress = learning.courses[courseId]
  return <View className='page completion-page' style={{ '--course-accent': course.color } as React.CSSProperties}>
    <View className='completion-mark'>✓</View><Text className='completion-eyebrow'>第 {course.number} 课完成</Text><Text className='completion-title'>你带走的不是答案，{`\n`}是一条自己的判断。</Text>
    <View className='takeaway-card'><Text className='takeaway-label'>本课行动卡</Text><Text className='takeaway-text'>{humanizeInteractionAnswer(progress.actionCard)}</Text><Text className='takeaway-focus'>{course.focus}</Text></View>
    {progress.reviewUnits.length > 0 ? <View className='review-panel'><Text className='review-title'>还有 {progress.reviewUnits.length} 个回合等你补上</Text><Text className='review-copy'>不补也不会抹掉完成记录；补上后，这张行动卡会更扎实。</Text>{progress.reviewUnits.map(index => <View className='review-row' key={index} onClick={() => onReview(index)}><View><Text className='review-index'>回合 {index + 1}</Text><Text className='review-unit-title'>{course.units[index].title}</Text></View><Text>去补上 →</Text></View>)}</View> : <View className='all-clear'>8 个回合都已完成，没有待回看的内容。</View>}
    <Button className='primary-action' onClick={onHome}>回到课程地图</Button><Text className='restart-link' onClick={onRestart}>重新学习本课</Text>
    <View className='compliance-note'>行动卡仅用于自我学习与记录，不构成投资建议。</View>
  </View>
}
