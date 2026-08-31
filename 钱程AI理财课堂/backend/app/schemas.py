from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=500)


class LearningContext(BaseModel):
    answer_summaries: list[Annotated[str, Field(max_length=320)]] = Field(default_factory=list, max_length=8)
    pending_review_units: list[Annotated[int, Field(ge=0, le=7)]] = Field(default_factory=list, max_length=8)
    current_card_completed: bool = False
    current_card_answer: str = Field(default="", max_length=2400)
    awaiting_next: bool = False
    next_unit_id: str = Field(default="", max_length=48)
    # Replies already delivered after the learner answered the current card.
    # The server adds the reply for this request before enforcing the cap.
    assistant_replies_since_card: int = Field(default=0, ge=0, le=3)
    course_finished: bool = False
    free_chat_mode: bool = False


class ChatRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=48)
    unit_id: str = Field(min_length=1, max_length=48)
    message: str = Field(min_length=1, max_length=500)
    history: list[ChatTurn] = Field(default_factory=list, max_length=8)
    context: LearningContext = Field(default_factory=LearningContext)


class EvidenceNote(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=240)


class InteractionCardRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=48)
    unit_id: str = Field(min_length=1, max_length=48)


class InteractionCardResponse(BaseModel):
    tool_name: Literal["present_interaction_card"]
    status: Literal["presented"]
    course_id: str
    unit_id: str
    teacher_intro: str
    unit_title: str


class TeachingArtifact(BaseModel):
    """A visual teaching beat chosen for this particular explanation.

    The model may emit no artifact at all; this keeps visual teaching useful
    rather than forcing every lesson through the same card layout.
    """

    kind: Literal["one_liner", "steps", "timeline", "contrast", "scenario", "checklist", "quote", "warning"]
    appear_after_paragraph: int = Field(ge=0, le=11)
    title: str = Field(min_length=2, max_length=36)
    lead: str = Field(default="", max_length=120)
    items: list[str] = Field(default_factory=list, max_length=4)
    note: str = Field(default="", max_length=180)


class TeachingScene(BaseModel):
    screen_title: str = Field(min_length=2, max_length=40)
    screen_summary: str = Field(default="", max_length=100)
    # Kept optional so old stored conversations still render, but new lesson
    # turns use teaching_artifacts instead of this fixed-board shape.
    key_points: list[str] = Field(default_factory=list, max_length=3)
    common_misconception: str = Field(default="", max_length=100)
    right_reframe: str = Field(default="", max_length=100)
    subtitle_excerpt: str = Field(default="", max_length=140)
    # The model is asked for a complete 6–8 beat explanation, but a usable
    # shorter or longer answer must never be thrown away and regenerated just
    # because its presentation rhythm is imperfect.
    full_caption: list[str] = Field(min_length=1, max_length=12)
    teaching_artifacts: list[TeachingArtifact] = Field(default_factory=list, max_length=11)


class VoiceSynthesisRequest(BaseModel):
    # Only teacher-authored caption paragraphs are accepted.  User chat is
    # deliberately excluded so the service does not turn private input into a
    # retained audio artifact.
    paragraphs: list[Annotated[str, Field(min_length=1, max_length=180)]] = Field(min_length=1, max_length=12)


class VoiceSubtitle(BaseModel):
    text: str = Field(min_length=1, max_length=16)
    begin_time: int = Field(ge=0)
    end_time: int = Field(gt=0)
    begin_index: int = Field(ge=0)
    end_index: int = Field(gt=0)


class VoiceSegment(BaseModel):
    audio_url: str
    # The mini program receives audio through callContainer rather than a
    # public URL. It writes this payload to its sandbox and plays that local
    # file, so no media-domain whitelist is required.
    audio_base64: str | None = None
    subtitles: list[VoiceSubtitle] = Field(default_factory=list)


class VoiceSynthesisResponse(BaseModel):
    segments: list[VoiceSegment] = Field(min_length=1, max_length=12)


class ChatResponse(BaseModel):
    reply: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    evidence_notes: list[EvidenceNote] = Field(default_factory=list, max_length=4)
    learning_signals: list[str] = Field(default_factory=list, max_length=4)
    suggested_optional_card: str | None = None
    advance_recommendation: Literal["stay", "continue"]
    teaching_decision: Literal["advance", "probe", "repair"] = "probe"
    observed_criteria: list[str] = Field(default_factory=list, max_length=4)
    missing_criterion: str | None = None
    next_step_invitation: str | None = Field(default=None, max_length=160)
    teaching_scene: TeachingScene | None = None
    tool_call: InteractionCardResponse | None = None
    compliance_mode: Literal["education_only"]
    source: Literal["local_fallback", "kimi"]


class InteractionTurnRequest(ChatRequest):
    submitted_answer: str = Field(min_length=1, max_length=2400)
    next_unit_id: str = Field(min_length=1, max_length=48)


class InteractionTurnResponse(BaseModel):
    assistant_reply: ChatResponse
    tool_call: InteractionCardResponse | None = None
