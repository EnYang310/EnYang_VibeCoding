"""Auditable advancement criteria shared by the classroom agent and tools."""

from __future__ import annotations


GATE_CRITERIA = {
    "opening": ("能说出情境里至少一个有日期或用途的任务",),
    "initial-judgment": ("能指出不分用途可能造成遗漏、冲突或挤压",),
    "hands-on": ("能用用途或最早使用日期解释至少一张卡的安排",),
    "consequence": ("能说明变化发生后要重新排序任务",),
    "ai-feedback-1": ("能用自己的话复述本课核心因果",),
    "transfer": ("能把本课判断迁移到一个新情境",),
    "ai-feedback-2": ("能指出自己原判断中一个可能遗漏的条件",),
    "action-card": ("行动卡包含用途、时间与一个可执行小动作",),
}

SIGNAL_GROUPS = {
    "opening": (("用途", "日期", "房租", "目标"),),
    "initial-judgment": (("用途", "任务", "分开"), ("遗漏", "冲突", "挤", "忘", "花掉")),
    "hands-on": (("用途", "日期", "近期", "缓冲", "长期"),),
    "consequence": (("重新", "调整", "排序", "延后", "挤"),),
    "ai-feedback-1": (("用途", "日期", "缓冲", "期限", "风险", "核验", "暂停", "目标"),),
    "transfer": (("因为", "所以", "用途", "日期", "期限", "风险", "核验"),),
    "ai-feedback-2": (("遗漏", "条件", "用途", "日期", "风险", "核验", "调整"),),
    "action-card": (("用途", "日期", "动作"),),
}


def criteria_for(unit_id: str) -> tuple[str, ...]:
    if unit_id not in GATE_CRITERIA:
        raise ValueError("unknown unit")
    return GATE_CRITERIA[unit_id]


def passes_gate(unit_id: str, decision: str, observed: list[str]) -> bool:
    """An LLM may recommend advancement, but it cannot waive the rubric."""
    return decision == "advance" and set(criteria_for(unit_id)).issubset(set(observed))


def infer_observed_criteria(unit_id: str, learner_text: str) -> list[str]:
    """Conservative deterministic check when the model under-reports evidence.

    It is deliberately a second lock, not a replacement for the course rubric:
    every required signal group must be present in the learner's own words.
    """
    compact = "".join(learner_text.split())
    groups = SIGNAL_GROUPS[unit_id]
    if len(compact) < 12 or not all(any(word in compact for word in group) for group in groups):
        return []
    return list(criteria_for(unit_id))
