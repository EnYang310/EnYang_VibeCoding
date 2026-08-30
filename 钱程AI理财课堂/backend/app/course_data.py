from __future__ import annotations

from copy import deepcopy
from typing import Any


COURSE_IDS = (
    "money-jobs",
    "safety-net",
    "product-map",
    "tradeoffs",
    "future-date",
    "steady-mind",
)

COURSES: dict[str, dict[str, Any]] = {
    "money-jobs": {
        "id": "money-jobs", "number": "01", "title": "我的钱有任务",
        "subtitle": "工资到账后，先给每一笔钱安排未来。",
        "learning_goal": "能用用途和最早使用日期区分一笔钱的任务。",
    },
    "safety-net": {
        "id": "safety-net", "number": "02", "title": "先给生活装一把伞",
        "subtitle": "意外来时，不必仓促做决定。",
        "learning_goal": "理解生活缓冲保护的是连续性与选择权。",
    },
    "product-map": {
        "id": "product-map", "number": "03", "title": "产品不是名字，是任务",
        "subtitle": "不背名词，先问三个问题。",
        "learning_goal": "能用期限、变化和取用规则比较陌生金融信息。",
    },
    "tradeoffs": {
        "id": "tradeoffs", "number": "04", "title": "收益、风险和时间的跷跷板",
        "subtitle": "没有一把钥匙能开所有门。",
        "learning_goal": "理解稳定、灵活和增长可能性之间存在取舍。",
    },
    "future-date": {
        "id": "future-date", "number": "05", "title": "把未来日期放到今天",
        "subtitle": "愿望有日期，今天才有第一步。",
        "learning_goal": "把模糊愿望拆成日期、阶段点和一周行动。",
    },
    "steady-mind": {
        "id": "steady-mind", "number": "06", "title": "市场热闹时，先按暂停",
        "subtitle": "别让情绪替你开车。",
        "learning_goal": "在催促、从众和高收益话术中练习暂停与核验。",
    },
}

for course in COURSES.values():
    course["disclaimer"] = "仅作学习模拟，不构成投资建议。"


def list_courses() -> list[dict[str, Any]]:
    return [deepcopy(COURSES[course_id]) for course_id in COURSE_IDS]


def get_course(course_id: str) -> dict[str, Any] | None:
    course = COURSES.get(course_id)
    return deepcopy(course) if course else None
