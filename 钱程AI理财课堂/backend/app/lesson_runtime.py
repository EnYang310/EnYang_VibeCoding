from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.course_data import get_course
from app.courseware import load_courseware


UNIT_IDS = (
    "opening",
    "initial-judgment",
    "hands-on",
    "consequence",
    "ai-feedback-1",
    "transfer",
    "ai-feedback-2",
    "action-card",
)

UNIT_TITLES = (
    "生活开场",
    "先说说你的判断",
    "动手试一试",
    "情况变了",
    "老师和你聊聊",
    "换个场景再试",
    "把道理说透一点",
    "带走你的行动卡",
)

COURSE_FOCUS = {
    "money-jobs": "先写用途和最早使用日期，日期明确的钱先保证可用。",
    "safety-net": "缓冲的价值是在变化来时保留选择，不是追求统一数字。",
    "product-map": "比较前先看期限、可能变化和能否及时取用。",
    "tradeoffs": "稳定、灵活和增长可能性常有取舍，别把不确定当保证。",
    "future-date": "给目标一个日期和一周内能开始的小动作。",
    "steady-mind": "遇到催促和高收益诱导，先暂停、核验、保护信息。",
    "fund-stock-basics": "先看股票或基金份额代表什么、主要投向什么，再看期限、规则与能承受的变化。",
    "volatility-time": "一次涨跌不是指令；先回到用途、最早使用日期、规则理解和可承受的变化。",
}


def get_lesson(course_id: str) -> dict[str, Any] | None:
    course = get_course(course_id)
    if course is None:
        return None
    courseware = load_courseware(course_id)
    return {
        "id": course_id,
        "title": course["title"],
        "subtitle": course["subtitle"],
        "focus": COURSE_FOCUS[course_id],
        "units": [
            {"id": unit_id, "title": title, "position": index + 1}
            for index, (unit_id, title) in enumerate(zip(UNIT_IDS, UNIT_TITLES))
        ],
        "evidence": [
            {"evidence_id": item.evidence_id, "text": item.text, "boundary": item.boundary}
            for item in courseware.evidence
        ],
        "sources": list(courseware.sources),
    }


def advance_state(course_id: str, unit_id: str, *, action: str) -> dict[str, Any]:
    if course_id not in COURSE_FOCUS or unit_id not in UNIT_IDS:
        raise ValueError("unknown course or unit")
    index = UNIT_IDS.index(unit_id)
    next_id = UNIT_IDS[min(index + 1, len(UNIT_IDS) - 1)]
    skipped = [unit_id] if action == "skip" else []
    return {"unit_id": next_id, "skipped": skipped, "completed": unit_id == UNIT_IDS[-1] and action == "submit"}


def local_chat_reply(course_id: str, unit_id: str, message: str) -> dict[str, Any]:
    if course_id not in COURSE_FOCUS or unit_id not in UNIT_IDS:
        raise ValueError("unknown course or unit")
    message = " ".join(message.split())[:300]
    investment_words = ("买", "卖", "标的", "基金", "股票", "仓位", "配置", "收益")
    if any(word in message for word in investment_words):
        reply = "我可以帮你把这件事拆成通用判断：它和你的用途、最早使用日期、能承受的变化有什么关系？但我不能替你决定买卖、比例或真实配置。"
    else:
        reply = f"我听见你在想“{message or '这一步怎么理解'}”。这一课先抓住：{COURSE_FOCUS[course_id]} 你愿意说说这和你当前的情境哪里最像吗？"
    return {
        "reply": reply,
        "evidence_ids": [f"{course_id}.core-1"],
        "learning_signals": [],
        "suggested_optional_card": None,
        "advance_recommendation": "stay",
        "compliance_mode": "education_only",
        "source": "local_fallback",
    }
