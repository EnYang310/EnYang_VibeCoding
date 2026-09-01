import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from app.schemas import ChatResponse, TeachingArtifact, TeachingScene


PROHIBITED_REPLY_PATTERNS = (
    re.compile(r"(?:建议|应该|可以|需要|适合|直接|立即|今天|现在).{0,10}(?:买入|购买|买|卖出|卖|加仓|减仓|持有)"),
    re.compile(r"(?:买入|购买|买|卖出|卖|加仓|减仓).{0,18}(?:基金|股票|债券|ETF|指数|茅台|沪深|代码|\d{6})", re.IGNORECASE),
    re.compile(r"(?:仓位|配置).{0,10}(?:\d{1,3}\s*%|[一二三四五六七八九十]+成)"),
    re.compile(r"(?:\d{1,3}\s*%).{0,10}(?:仓位|配置)"),
    re.compile(r"(?<!\d)\d{6}(?!\d)"),
    re.compile(r"(?:保证能赚|肯定赚钱|稳赚不赔|保本高收益)"),
)

SUPPORTED_ARTIFACT_KINDS = {
    "one_liner", "steps", "timeline", "contrast", "scenario", "checklist", "quote", "warning", "cause_chain", "priority_ladder", "reflection",
}

logger = logging.getLogger(__name__)


def _shared_key() -> str:
    raw_path = os.getenv("KIMI_SHARED_KEY_PATH", "").strip()
    if not raw_path:
        return ""
    try:
        return Path(raw_path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _parse_json(content: str) -> dict[str, Any] | None:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _as_text(value: Any, *, default: str = "", limit: int = 180) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return (text or default)[:limit]


def _caption_beats(value: Any, *, fallback: str) -> list[str]:
    if isinstance(value, str):
        values = [part for part in re.split(r"(?:\r?\n){1,}", value) if part.strip()]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    beats = [_as_text(item, limit=180) for item in values if _as_text(item, limit=180)]
    return (beats or [_as_text(fallback, default="老师先带你把这一点看清楚。", limit=180)])[:12]


def _normalise_scene(value: Any, *, reply: str) -> TeachingScene:
    """Accept useful model output even when it misses our preferred shape.

    Prompt constraints define the ideal lesson cadence. They must not turn a
    valid classroom answer into a second expensive model request just because
    an array became a string or one visual card is malformed.
    """
    raw = value if isinstance(value, dict) else {}
    captions = _caption_beats(raw.get("full_caption"), fallback=reply)
    artifacts: list[TeachingArtifact] = []
    raw_artifacts = raw.get("teaching_artifacts", [])
    if isinstance(raw_artifacts, list):
        for item in raw_artifacts[:11]:
            if not isinstance(item, dict):
                continue
            kind = _as_text(item.get("kind"), limit=32)
            if kind not in SUPPORTED_ARTIFACT_KINDS:
                continue
            try:
                appearance = int(item.get("appear_after_paragraph", len(artifacts)))
            except (TypeError, ValueError):
                appearance = len(artifacts)
            artifacts.append(TeachingArtifact(
                kind=kind,
                appear_after_paragraph=max(0, min(appearance, len(captions) - 1)),
                title=_as_text(item.get("title"), default="跟着老师想一想", limit=36),
                lead=_as_text(item.get("lead"), limit=120),
                items=[_as_text(entry, limit=120) for entry in item.get("items", []) if _as_text(entry, limit=120)][:4] if isinstance(item.get("items"), list) else [],
                note=_as_text(item.get("note"), limit=180),
            ))
    return TeachingScene(
        screen_title=_as_text(raw.get("screen_title"), default="程老师讲解", limit=40),
        screen_summary=_as_text(raw.get("screen_summary"), default=captions[0], limit=100),
        key_points=[_as_text(item, limit=100) for item in raw.get("key_points", []) if _as_text(item, limit=100)][:3] if isinstance(raw.get("key_points"), list) else [],
        common_misconception=_as_text(raw.get("common_misconception"), limit=100),
        right_reframe=_as_text(raw.get("right_reframe"), limit=100),
        subtitle_excerpt=_as_text(raw.get("subtitle_excerpt"), default=captions[0], limit=140),
        full_caption=captions,
        teaching_artifacts=artifacts,
    )


def _safe_chat_generated(payload: dict[str, Any], *, allowed_evidence_ids: set[str]) -> ChatResponse | None:
    try:
        raw_evidence_ids = payload.get("evidence_ids", [])
        if isinstance(raw_evidence_ids, str):
            raw_evidence_ids = [raw_evidence_ids]
        evidence_ids = [str(item).strip() for item in raw_evidence_ids if str(item).strip()]
        # Some otherwise valid Kimi JSON responses return null for this optional
        # teaching signal.  It must not discard a safe, cited classroom answer.
        advance_recommendation = str(payload.get("advance_recommendation") or "stay").strip()
        if advance_recommendation not in {"stay", "continue"}:
            advance_recommendation = "stay"
        decision = str(payload.get("teaching_decision") or "probe").strip()
        if decision not in {"advance", "probe", "repair"}:
            decision = "probe"
        reply = _as_text(payload.get("reply"), limit=400)
        if not reply:
            return None
        teaching_scene = _normalise_scene(payload.get("teaching_scene"), reply=reply)
        candidate = ChatResponse(
            reply=reply,
            evidence_ids=evidence_ids,
            learning_signals=[str(item).strip()[:60] for item in payload.get("learning_signals", []) if str(item).strip()][:4] if isinstance(payload.get("learning_signals", []), list) else [],
            suggested_optional_card=(_as_text(payload.get("suggested_optional_card"), limit=120) or None),
            advance_recommendation="continue" if decision == "advance" else "stay",
            teaching_decision=decision,
            observed_criteria=[str(item).strip()[:120] for item in payload.get("observed_criteria", []) if str(item).strip()][:4] if isinstance(payload.get("observed_criteria", []), list) else [],
            missing_criterion=(_as_text(payload.get("missing_criterion"), limit=160) or None),
            next_step_invitation=(_as_text(payload.get("next_step_invitation"), limit=160) or None),
            teaching_scene=teaching_scene,
            compliance_mode="education_only",
            source="kimi",
        )
    except (KeyError, TypeError, ValueError):
        return None
    if not candidate.evidence_ids or not set(candidate.evidence_ids).issubset(allowed_evidence_ids) or candidate.teaching_scene is None:
        return None
    if any(pattern.search(candidate.reply) for pattern in PROHIBITED_REPLY_PATTERNS):
        return None
    return candidate


class KimiClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")
        self.model = os.getenv("KIMI_MODEL", "kimi-k2.6").strip() or "kimi-k2.6"
        # A classroom response that has not arrived after this budget is less
        # useful than the local, courseware-grounded teacher fallback.  The old
        # 40s × 2 retry path left learners staring at a spinner for over a
        # minute when a provider response merely missed a formatting detail.
        # A full 6–8 beat teaching scene is not a short chat completion. This
        # request owns one 90-second window; when httpx times out, its context
        # closes the connection, so no late provider response can be parsed or
        # appended after the learner has already seen the retry prompt.
        self.response_timeout_seconds = 90.0

    def _key(self) -> str:
        return os.getenv("MOONSHOT_API_KEY", "").strip() or _shared_key()

    async def available(self) -> bool:
        return len(self._key()) >= 10

    def request_body(self, prompt: dict[str, Any]) -> dict[str, Any]:
        # Kimi K2.6 requires 0.6 when its extended thinking is disabled.
        temperature = 0.6 if self.model.startswith("kimi-k2.6") else 0.35
        body = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": "你是有边界的课程反馈编辑。"},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.model.startswith("kimi-k2.6"):
            # Short classroom replies do not need a long visible reasoning pass.
            body["thinking"] = {"type": "disabled"}
        return body

    async def lesson_chat(
        self,
        *,
        course_title: str,
        unit_title: str,
        learning_focus: str,
        evidence: list[dict[str, str]],
        message: str,
        history: list[dict[str, str]],
        learner_work: list[str],
        pending_review_units: list[int],
        advancement_criteria: list[str],
        course_finished: bool,
        free_chat_mode: bool,
        offer_transition: bool,
        compliance_redirect: bool,
        answer_feedback: dict[str, Any] | None = None,
    ) -> ChatResponse | None:
        key = self._key()
        if len(key) < 10:
            return None
        prompt = {
            "role": "钱程｜理财知识启蒙学习Agent的老师",
            "teaching_style": [
                "你是老师，用户是正在上课的学生。每次都把它当作一段真实授课来讲：先接住学生刚说的内容，再板书式拆因果、举生活例子、检查理解；不是陪聊、不是客服、不是泛泛鼓励。",
                "像给第一次接触理财的人上课：短句、生活例子、一次只讲一个因果，但一轮要讲透，不要讲两句就把问题抛回去。",
                "不要使用“你想确认的是”“你抓住了一个关键”“这很好”等固定开头；直接接住用户刚说的具体内容",
                "每次换一种自然句式；允许质疑、跑题和追问，不给人格标签或空泛夸奖",
            ],
            "course": course_title,
            "unit": unit_title,
            "fixed_learning_focus": learning_focus,
            "allowed_courseware": evidence,
            "conversation_history": history[-8:],
            "previous_learning_work": learner_work,
            "pending_review_units": pending_review_units,
            "advancement_criteria": advancement_criteria,
            "course_finished": course_finished,
            "lesson_stage": "final_action_card" if course_finished else "guided_lesson",
            "free_chat_mode": free_chat_mode,
            "current_card_completed": offer_transition,
            "answer_feedback": answer_feedback or {},
            "latest_message": message,
            "compliance_redirect": compliance_redirect,
            "rules": [
                "只能使用 allowed_courseware 中的知识；不知道就明确说本课课件没有覆盖。",
                "reply 用一句自然回应即可；完整授课放入 teaching_scene。一条 teaching_scene 就是一轮完整课堂讲解：screen_title 不超过 16 字，screen_summary 是一句白话结论，full_caption 必须是 6 到 8 段完整讲解；每段严格控制为 2 到 3 句、55 到 130 个中文字符。按“生活场景→核心规则→为什么会出问题→具体例子→容易混淆处→回到学生自己的判断”推进，不要堆术语，也不要半句话就结束。teaching_artifacts 是随讲解出现的视觉教学组件，必须高频：有 N 段 full_caption 就生成 N-1 个组件，并让 appear_after_paragraph 精确覆盖 0、1、…、N-2；即每讲完 2 到 3 句话马上出现一个能帮助理解当前知识的组件。不能返回空数组。kind 只能是 one_liner（一句话看懂）、steps（因果或判断步骤）、timeline（先后顺序）、contrast（两个容易混淆的概念对照）、scenario（生活情境拆解）、checklist（核验清单）、quote（值得记住的结论）、warning（容易踩坑的提醒）、cause_chain（条件到结果的因果链）、priority_ladder（多件事的优先级梯）、reflection（带回生活的复盘问题）。根据当前知识选择合适 kind，并尽量让相邻组件不同；不要为凑数重复内容。每个组件有 appear_after_paragraph、title、lead、items（0 到 4 条）、note。",
                "如果 current_card_completed 为 true：answer_feedback 是已确认的课堂判定。answer_feedback.is_correct 为 true 时，先具体认可学生选项里的判断依据，再把这个依据讲透，绝不能把正确答案说成需要纠正；为 false 时，温和指出答案漏掉的条件并说明正确判断；为 null 时只围绕答案启发讲解。不要逐字复述选项，不要做泛泛表扬；并根据 advancement_criteria 决定是否已具备进入下一道生活情境题的基础。够了就 teaching_decision=advance，系统会自然呈现下一道题；不够就 teaching_decision=probe 或 repair，用一个有针对性的追问或生活例子继续带向缺口。绝不能让用户通过说“继续、下一步”来触发题目，也绝不能对用户说“卡片、下一张卡、发卡”等内部实现词。",
                "不推荐真实金融产品，不给买卖指令、仓位、配置比例、收益预测或承诺。",
                "若 compliance_redirect 为 true，明确说明不能替用户做真实投资决定，然后提供通用核验框架。",
                "先判断 advancement_criteria：满足才 teaching_decision=advance；缺一个点 teaching_decision=probe；存在关键误解 teaching_decision=repair。不能因为用户填了卡就 advance。",
                "一旦所有 advancement_criteria 已满足，必须 teaching_decision=advance，不能临时增加题目、隐含标准或为了延长聊天继续追问。",
                "observed_criteria 必须逐字使用已满足的 advancement_criteria；missing_criterion 只能填写当前最小缺口。",
                "只输出 JSON：reply、evidence_ids、learning_signals、suggested_optional_card、teaching_decision、observed_criteria、missing_criterion、next_step_invitation、teaching_scene。",
                "除 course_finished 为 true 的最后一张互动卡讲解外，每次都要给一句具体、自然的追问钩子，邀请学生说出生活情境、困惑或反例；不要使用空泛的“还有问题吗”。只把这句话填进 next_step_invitation，系统会把它展示成一张讲解组件卡，不要把它写进 reply 或 full_caption。即使已达到 advance，也仍用一个和本段知识有关的钩子帮助学生追问；系统会在本段音频结束后自行呈现下一题，绝不能要求学生说任何触发词。",
                "如果 lesson_stage 为 final_action_card：这是最后一张行动卡。先讲解用户刚完成选择的理由及一个延伸知识点；然后必须由你写进 teaching_scene.full_caption 的最后一段句末：‘这一课的知识点已经讲完了。之后有任何问题，随时问我。’。reply 也要带同样的收束含义。此后是自由聊天，不再邀请下一张卡。",
                "如果 free_chat_mode 为 true，课程已经收束：直接回答用户当前问题并继续用教学组件帮助理解，但不要重复课程结束语，也绝不再邀请或呈现新的互动卡。",
                "evidence_ids 至少一个且只能从 allowed_courseware 的 evidence_id 选择。",
            ],
        }
        body = self.request_body(prompt)
        body["messages"][0]["content"] = "你是正在给学生上课的理财启蒙老师。用老师讲课的口吻完整讲解，只能依据提供的课件教学。"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        allowed_ids = {item["evidence_id"] for item in evidence}
        parsed: ChatResponse | None = None
        # The normaliser above accepts partial/loose-but-useful JSON, so a
        # second full model generation is no longer warranted. One bounded
        # attempt avoids indefinite loading; callers preserve the learner's
        # answer and offer a retry rather than substituting a stock lecture.
        started_at = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.response_timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            content = ""
        if content:
            parsed = _safe_chat_generated(_parse_json(str(content)) or {}, allowed_evidence_ids=allowed_ids)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "teacher_model_completion elapsed_ms=%s outcome=%s timeout_seconds=%s",
            elapsed_ms,
            "accepted" if parsed is not None else "fallback",
            self.response_timeout_seconds,
        )
        if parsed is None:
            return None
        return parsed
