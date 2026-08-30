import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from app.schemas import ChatResponse, TeachingScene


PROHIBITED_REPLY_PATTERNS = (
    re.compile(r"(?:建议|应该|可以|需要|适合|直接|立即|今天|现在).{0,10}(?:买入|购买|买|卖出|卖|加仓|减仓|持有)"),
    re.compile(r"(?:买入|购买|买|卖出|卖|加仓|减仓).{0,18}(?:基金|股票|债券|ETF|指数|茅台|沪深|代码|\d{6})", re.IGNORECASE),
    re.compile(r"(?:仓位|配置).{0,10}(?:\d{1,3}\s*%|[一二三四五六七八九十]+成)"),
    re.compile(r"(?:\d{1,3}\s*%).{0,10}(?:仓位|配置)"),
    re.compile(r"(?<!\d)\d{6}(?!\d)"),
    re.compile(r"(?:保证能赚|肯定赚钱|稳赚不赔|保本高收益)"),
)


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
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _safe_chat_generated(payload: dict[str, Any], *, allowed_evidence_ids: set[str]) -> ChatResponse | None:
    try:
        evidence_ids = [str(item).strip() for item in payload["evidence_ids"]]
        # Some otherwise valid Kimi JSON responses return null for this optional
        # teaching signal.  It must not discard a safe, cited classroom answer.
        advance_recommendation = str(payload.get("advance_recommendation") or "stay").strip()
        if advance_recommendation not in {"stay", "continue"}:
            advance_recommendation = "stay"
        decision = str(payload.get("teaching_decision") or "probe").strip()
        if decision not in {"advance", "probe", "repair"}:
            decision = "probe"
        candidate = ChatResponse(
            reply=str(payload["reply"]).strip(),
            evidence_ids=evidence_ids,
            learning_signals=[str(item).strip()[:60] for item in payload.get("learning_signals", [])][:4],
            suggested_optional_card=(str(payload["suggested_optional_card"]).strip()[:120] if payload.get("suggested_optional_card") else None),
            advance_recommendation="continue" if decision == "advance" else "stay",
            teaching_decision=decision,
            observed_criteria=[str(item).strip()[:120] for item in payload.get("observed_criteria", []) if str(item).strip()][:4],
            missing_criterion=(str(payload["missing_criterion"]).strip()[:160] if payload.get("missing_criterion") else None),
            next_step_invitation=(str(payload["next_step_invitation"]).strip()[:160] if payload.get("next_step_invitation") else None),
            teaching_scene=TeachingScene(**payload["teaching_scene"]) if payload.get("teaching_scene") else None,
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
        offer_transition: bool,
        compliance_redirect: bool,
    ) -> ChatResponse | None:
        key = self._key()
        if len(key) < 10:
            return None
        prompt = {
            "role": "钱程的理财启蒙老师",
            "teaching_style": [
                "像给第一次接触理财的人讲：短句、生活例子、一次只讲一个因果",
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
            "current_card_completed": offer_transition,
            "latest_message": message,
            "compliance_redirect": compliance_redirect,
            "rules": [
                "只能使用 allowed_courseware 中的知识；不知道就明确说本课课件没有覆盖。",
                "reply 用一句自然回应即可；完整授课放入 teaching_scene。teaching_scene 的 screen_title 不超过 16 字，screen_summary 是一句白话结论，full_caption 必须是 3 到 5 段完整讲解、每段 45 到 110 个中文字符。讲解要先解释题目中的因果，再举生活例子，最后自然收束；不要堆术语。teaching_artifacts 是 0 到 4 个随讲解出现的视觉教学组件：只在确实能让当前知识更好懂时才生成，绝不能为凑数重复内容。kind 只能是 one_liner（一句话看懂）、steps（因果或判断步骤）、timeline（先后顺序）、contrast（两个容易混淆的概念对照）、scenario（生活情境拆解）、checklist（核验清单）、quote（值得记住的结论）、warning（容易踩坑的提醒）。每个组件有 appear_after_paragraph（0 代表第一段朗读结束后出现，依此类推）、title、lead、items（0 到 4 条）、note。根据知识选择不同 kind，不要每次都用同一个模板；没有合适组件就返回空数组。",
                "如果 current_card_completed 为 true：不要逐字复述选项，不要做泛泛表扬；围绕用户答案解释当前知识点，并根据 advancement_criteria 决定是否已具备进入下一道生活情境题的基础。够了就 teaching_decision=advance，系统会自然呈现下一道题；不够就 teaching_decision=probe 或 repair，用一个有针对性的追问或生活例子继续带向缺口。绝不能让用户通过说“继续、下一步”来触发题目，也绝不能对用户说“卡片、下一张卡、发卡”等内部实现词。",
                "不推荐真实金融产品，不给买卖指令、仓位、配置比例、收益预测或承诺。",
                "若 compliance_redirect 为 true，明确说明不能替用户做真实投资决定，然后提供通用核验框架。",
                "先判断 advancement_criteria：满足才 teaching_decision=advance；缺一个点 teaching_decision=probe；存在关键误解 teaching_decision=repair。不能因为用户填了卡就 advance。",
                "一旦所有 advancement_criteria 已满足，必须 teaching_decision=advance，不能临时增加题目、隐含标准或为了延长聊天继续追问。",
                "observed_criteria 必须逐字使用已满足的 advancement_criteria；missing_criterion 只能填写当前最小缺口。",
                "只输出 JSON：reply、evidence_ids、learning_signals、suggested_optional_card、teaching_decision、observed_criteria、missing_criterion、next_step_invitation、teaching_scene。",
                "next_step_invitation 只在仍需用户补充理解时使用；已达到 advance 时应为 null，不要要求用户说任何触发词。",
                "如果 course_finished 为 true，先用自然语言说明本课知识点已讲完，邀请用户继续问任何概念或生活情境；此后是自由聊天，不再邀请下一张卡。",
                "evidence_ids 至少一个且只能从 allowed_courseware 的 evidence_id 选择。",
            ],
        }
        body = self.request_body(prompt)
        body["messages"][0]["content"] = "你是有温度但守边界的理财启蒙老师。只能依据提供的课件教学。"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        allowed_ids = {item["evidence_id"] for item in evidence}
        parsed: ChatResponse | None = None
        # A malformed JSON turn or a transient gateway response must not turn a
        # normal classroom exchange into a canned local reply immediately.
        for _attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=40.0) as client:
                    response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
                continue
            parsed = _safe_chat_generated(_parse_json(str(content)) or {}, allowed_evidence_ids=allowed_ids)
            if parsed is not None:
                break
        if parsed is None:
            return None
        return parsed
