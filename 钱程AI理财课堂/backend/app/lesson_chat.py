from __future__ import annotations

import re

from app.course_data import get_course
from app.courseware import evidence_for_unit
from app.kimi import KimiClient
from app.lesson_runtime import COURSE_FOCUS, UNIT_IDS, UNIT_TITLES
from app.learning_gates import criteria_for
from app.schemas import ChatRequest, ChatResponse, EvidenceNote, TeachingArtifact, TeachingScene
from app.teaching_flow import COURSE_FINISHED_CLOSING, append_course_finished_closing


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


class TeacherModelUnavailable(RuntimeError):
    """The personalised teacher turn could not be generated safely."""


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
        final_scene = response.teaching_scene
        if final_scene and final_scene.full_caption:
            last_caption = final_scene.full_caption[-1]
            if COURSE_FINISHED_CLOSING not in last_caption:
                caption_room = 180 - len(COURSE_FINISHED_CLOSING) - 1
                last_caption = append_course_finished_closing(last_caption[:caption_room])
            final_scene = final_scene.model_copy(update={
                "full_caption": [*final_scene.full_caption[:-1], last_caption],
            })
        return response.model_copy(update={
            "reply": append_course_finished_closing(response.reply[:room_for_reply]),
            "teaching_scene": final_scene,
        })
    hook = response.next_step_invitation or "想把它放进自己的生活里，再追问一个最想弄明白的地方吗？"
    reply = response.reply.strip()
    if reply.endswith(hook):
        reply = reply[:-len(hook)].rstrip("。！？!? ") or response.reply.strip()
    scene = response.teaching_scene or TeachingScene(
        screen_title="再想一步",
        screen_summary=reply[:100],
        full_caption=[reply],
    )
    hook_card = TeachingArtifact(
        kind="quote",
        appear_after_paragraph=max(len(scene.full_caption) - 1, 0),
        title="想一想，再告诉老师",
        lead=hook,
    )
    return response.model_copy(update={
        "reply": reply[:400],
        "teaching_scene": scene.model_copy(update={"teaching_artifacts": [*scene.teaching_artifacts, hook_card]}),
    })


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
    elif request.context.current_card_completed:
        submitted_answer = sanitize_user_text(request.context.current_card_answer)[:180]
        reply = (
            f"你刚才的选择是“{submitted_answer or '先把眼前这笔钱的用途说清楚'}”。"
            f"老师先不急着判对错，带你用这一课的规则把它讲透：{primary.text}"
            "把这个判断放回自己的生活里再看一次，才知道它能不能站得住。"
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
                f"这一段课，我们不急着背概念，先把眼前的事看清楚。{primary.text}",
                "老师先给你一个判断顺序：用途在前，日期在后，最后才看数字。顺序一乱，很多看似合理的安排都会出问题。",
                f"把它放回生活里想一想。{COURSE_FOCUS[request.course_id]}，不是为了把钱分得漂亮，而是为了临时变化发生时还有选择。",
                "比如同样一笔钱，今天看着都够用；可一笔明天要交，另一笔三个月后才要用，处理方式就完全不同。日期越近，越不能拿它去承担不确定。",
                "容易混淆的地方是：总额没少，不等于安排没有风险。真正会让人慌的，往往是该用的钱被别的事情占住了。",
                "所以这不是一道算术题，而是一道先后顺序题。你先把用途、最早日期和可能变化分开，后面的选择才站得住。",
            ],
            teaching_artifacts=[
                TeachingArtifact(kind="one_liner", appear_after_paragraph=0, title="先记这一句", lead=primary.text[:100]),
                TeachingArtifact(kind="steps", appear_after_paragraph=1, title="老师带你按顺序看", items=["先问用途", "再看最早日期", "最后才看金额"], note="顺序比总额更能决定这笔钱能不能用。"),
                TeachingArtifact(kind="scenario", appear_after_paragraph=2, title="放进生活里", lead="同样的钱，日期不同，处理方式就不同。", items=["今天必须用：先保住可用", "之后才用：可以再安排"], note="先后不同，选择就不同。"),
                TeachingArtifact(kind="contrast", appear_after_paragraph=3, title="总额够，不等于随时可用", items=["只看总额：容易误判", "先看日期：知道哪里不能动"], note="真正的风险，是该用时拿不出来。"),
                TeachingArtifact(kind="checklist", appear_after_paragraph=4, title="轮到你自己核验", items=["这笔钱准备做什么", "最早什么时候必须用", "临时变化会影响哪里"], note="先把三件事说清楚，再讨论下一步。"),
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
    # Both the regular interaction endpoint and the final action-card endpoint
    # submit a confirmed answer.  The latter has a different user-facing
    # message, so matching copy here silently dropped its teacher feedback.
    offer_transition = request.context.current_card_completed
    answer_feedback = None
    if offer_transition:
        answer_feedback = {
            "student_answer": sanitize_user_text(request.context.current_card_answer)[:180],
            "correct_answer": sanitize_user_text(request.context.correct_answer)[:180],
            "is_correct": request.context.answer_is_correct,
        }
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
        answer_feedback=answer_feedback,
        compliance_redirect=False,
    )
    if generated is None:
        # A generic courseware scene is fine for a deterministic safety
        # boundary above, but it must never impersonate a teacher who is
        # responding to this learner's answer. Preserve the answer and let the
        # learner retry instead of repeating the same stock lecture.
        raise TeacherModelUnavailable("老师正在生成针对这份答案的讲解，请稍后重试。")
    by_id = {item.evidence_id: item for item in evidence}
    response = generated.model_copy(
        update={
            "reply": generated.reply[:400],
            "evidence_notes": [
                EvidenceNote(evidence_id=evidence_id, text=by_id[evidence_id].text)
                for evidence_id in generated.evidence_ids
                if evidence_id in by_id
            ]
        }
    )
    return finish_free_question_mode(response, course_finished=request.context.course_finished)
