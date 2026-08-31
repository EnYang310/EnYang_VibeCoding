from __future__ import annotations

import re

from app.course_data import get_course
from app.courseware import evidence_for_unit
from app.kimi import KimiClient
from app.lesson_runtime import COURSE_FOCUS, UNIT_IDS, UNIT_TITLES
from app.learning_gates import criteria_for
from app.schemas import ChatRequest, ChatResponse, EvidenceNote, TeachingArtifact, TeachingScene
from app.teaching_flow import append_course_finished_closing, append_follow_up_hook


REAL_DECISION_TERMS = (
    "买哪个", "买哪只", "卖哪只", "具体买", "具体卖", "卖不卖", "要不要买", "要不要卖", "买入", "卖出", "标的", "基金代码", "股票代码",
    "仓位", "配置多少", "投入多少", "收益率预测", "保本吗", "稳赚",
)

SENSITIVE_LABEL_PATTERN = re.compile(
    r"(?P<label>姓名|身份证号?|银行卡号?|卡号|账号|手机号|验证码|支付密码|登录密码|密码|口令)"
    r"(?P<separator>\s*[：:]?\s*)"
    r"(?P<value>[^\s，。；,;]{2,})",
    re.IGNORECASE,
)
LONG_NUMBER_PATTERN = re.compile(r"(?<!\d)(?:\d[\s-]?){6,}(?!\d)")


def sanitize_user_text(text: str) -> str:
    compact = " ".join(text.split())[:500]
    compact = SENSITIVE_LABEL_PATTERN.sub(lambda match: f"{match.group('label')}：[已隐藏敏感信息]", compact)
    return LONG_NUMBER_PATTERN.sub("[已隐藏数字]", compact)


def contains_sensitive_data(text: str) -> bool:
    return sanitize_user_text(text) != " ".join(text.split())[:500]


def sanitize_learner_work(items: list[str]) -> list[str]:
    return [sanitize_user_text(item)[:320] for item in items[:8]]


def needs_compliance_redirect(message: str) -> bool:
    compact = "".join(message.split())
    return any(term in compact for term in REAL_DECISION_TERMS)


def finish_free_question_mode(response: ChatResponse, *, course_finished: bool) -> ChatResponse:
    if course_finished:
        room_for_reply = 400 - len(append_course_finished_closing("")) - 1
        return response.model_copy(update={"reply": append_course_finished_closing(response.reply[:room_for_reply])})
    hook = response.next_step_invitation or "想把它放进自己的生活里，再追问一个最想弄明白的地方吗？"
    room_for_reply = 400 - len(hook) - 1
    return response.model_copy(update={"reply": append_follow_up_hook(response.reply[:room_for_reply], hook)})


def courseware_fallback(request: ChatRequest, *, privacy_redirect: bool = False) -> ChatResponse:
    if request.course_id not in COURSE_FOCUS or request.unit_id not in UNIT_IDS:
        raise ValueError("unknown course or unit")
    evidence = evidence_for_unit(request.course_id, request.unit_id)
    primary = evidence[0]
    message = " ".join(request.message.split())[:180]
    if privacy_redirect:
        reply = (
            "先停一下：这段话里可能有姓名、账号、卡号、密码或验证码。请删除这些信息后再问，"
            f"我也不会把它发给外部模型。本课仍可继续讨论通用判断：{primary.text}"
        )
    elif needs_compliance_redirect(message):
        reply = (
            "这已经碰到真实投资决定了，我不能替你决定具体产品、交易动作或比例。"
            f"我们可以把它改成一个通用学习题：{COURSE_FOCUS[request.course_id]}{primary.text}"
            "先说说这笔钱最早什么时候要用，好吗？"
        )
    else:
        opening = f"你问的是“{message or '这一点怎么理解'}”。"
        reply = f"{opening}先用一句人话抓住它：{primary.text}你可以用自己的生活情境举一个反例吗？"
    return ChatResponse(
        reply=reply[:400],
        evidence_ids=[item.evidence_id for item in evidence],
        evidence_notes=[{"evidence_id": item.evidence_id, "text": item.text} for item in evidence],
        learning_signals=[],
        suggested_optional_card=None,
        advance_recommendation="stay",
        teaching_decision="probe",
        observed_criteria=[],
        missing_criterion=criteria_for(request.unit_id)[0],
        teaching_scene=TeachingScene(
            screen_title="先抓住这一点",
            screen_summary=primary.text[:100],
            key_points=[primary.text[:70], "先回到自己的生活情境，再做判断。"],
            common_misconception="把眼前的热闹当成已经完成的判断。",
            right_reframe="先看用途、日期和规则，再决定下一步。",
            subtitle_excerpt=primary.text[:140],
            full_caption=[
                f"我们先不急着得出结论。{primary.text}",
                f"把它放回生活里理解。{COURSE_FOCUS[request.course_id]}",
                "先用这个原则看清任务、日期和可能的变化。再决定还想继续追问什么。",
            ],
            teaching_artifacts=[
                TeachingArtifact(kind="one_liner", appear_after_paragraph=0, title="先记这一句", lead=primary.text[:100]),
                TeachingArtifact(kind="checklist", appear_after_paragraph=1, title="回到生活里怎么判断", items=["这笔钱准备做什么", "最早什么时候必须用", "如果临时变化，哪里会受影响"], note="先把这三个问题想清楚，再谈下一步。"),
            ],
        ),
        compliance_mode="education_only",
        source="local_fallback",
    )


async def personalized_lesson_chat(request: ChatRequest) -> ChatResponse:
    course = get_course(request.course_id)
    if course is None or request.unit_id not in UNIT_IDS:
        raise ValueError("unknown course or unit")
    evidence = evidence_for_unit(request.course_id, request.unit_id)
    unit_title = UNIT_TITLES[UNIT_IDS.index(request.unit_id)]
    all_user_text = [request.message, *[turn.content for turn in request.history], *request.context.answer_summaries]
    if any(contains_sensitive_data(item) for item in all_user_text):
        return finish_free_question_mode(courseware_fallback(request, privacy_redirect=True), course_finished=request.context.course_finished)
    if needs_compliance_redirect(request.message):
        # Real purchase, sale, allocation and product-selection questions never
        # reach the external model. The boundary is deterministic, not prompt-only.
        return finish_free_question_mode(courseware_fallback(request), course_finished=request.context.course_finished)
    offer_transition = request.message.startswith("我完成了这张互动卡")
    generated = await KimiClient().lesson_chat(
        course_title=course["title"],
        unit_title=unit_title,
        learning_focus=COURSE_FOCUS[request.course_id],
        evidence=[
            {"evidence_id": item.evidence_id, "text": item.text, "boundary": item.boundary}
            for item in evidence
        ],
        message=sanitize_user_text(request.message),
        history=[{"role": turn.role, "content": sanitize_user_text(turn.content)} for turn in request.history],
        learner_work=sanitize_learner_work(request.context.answer_summaries),
        pending_review_units=request.context.pending_review_units,
        advancement_criteria=list(criteria_for(request.unit_id)),
        course_finished=request.context.course_finished,
        free_chat_mode=request.context.free_chat_mode,
        offer_transition=offer_transition,
        compliance_redirect=False,
    )
    if generated is None:
        return finish_free_question_mode(courseware_fallback(request), course_finished=request.context.course_finished)
    by_id = {item.evidence_id: item for item in evidence}
    reply = generated.reply
    if generated.next_step_invitation and generated.next_step_invitation.strip() not in reply:
        reply = f"{reply.rstrip('。！？!?')}。{generated.next_step_invitation}"
    response = generated.model_copy(
        update={
            "reply": reply[:400],
            "evidence_notes": [
                EvidenceNote(evidence_id=evidence_id, text=by_id[evidence_id].text)
                for evidence_id in generated.evidence_ids
                if evidence_id in by_id
            ]
        }
    )
    return finish_free_question_mode(response, course_finished=request.context.course_finished)
