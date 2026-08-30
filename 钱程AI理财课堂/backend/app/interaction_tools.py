"""Server-side tools that turn a course state into an assistant interaction card."""

from __future__ import annotations

from app.lesson_runtime import UNIT_IDS, UNIT_TITLES


CARD_INTROS = {
    "opening": "先读这个生活片段。读完后点一下进入情境，再把你的第一反应告诉我。",
    "initial-judgment": "先选一个你认为最可能的结果，再写一句理由；我会顺着你的理由继续讲。",
    "hands-on": "现在轮到你动手。完成这个练习后，我们会进入下一个学习环节。",
    "consequence": "情境变了。请重新做一次判断，再比较你为什么会调整。",
    "ai-feedback-1": "这是一段自由讨论。你可以追问、反驳或举例；聊明白后再继续。",
    "transfer": "换一个新情境，试试看能不能把刚学到的判断迁移过去。",
    "ai-feedback-2": "再做一次自由讨论，把你最不确定的地方说给我听。",
    "action-card": "最后把这一课带回生活：写自己的行动卡，不填写真实金额或账户信息。",
}


def present_interaction_card(course_id: str, unit_id: str) -> dict[str, str]:
    """The classroom agent's UI tool. It never advances learning state."""
    if unit_id not in UNIT_IDS:
        raise ValueError("unknown unit")
    return {
        "tool_name": "present_interaction_card",
        "status": "presented",
        "course_id": course_id,
        "unit_id": unit_id,
        "teacher_intro": CARD_INTROS[unit_id],
        "unit_title": UNIT_TITLES[UNIT_IDS.index(unit_id)],
    }


def next_unit_after(unit_id: str) -> str:
    if unit_id not in UNIT_IDS:
        raise ValueError("unknown unit")
    index = UNIT_IDS.index(unit_id)
    if index >= len(UNIT_IDS) - 1:
        raise ValueError("course already complete")
    return UNIT_IDS[index + 1]
