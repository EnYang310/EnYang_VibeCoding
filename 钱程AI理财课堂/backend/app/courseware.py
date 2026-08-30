from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


COURSEWARE_DIR = Path(__file__).resolve().parent / "skills" / "financial-learning-teacher" / "references" / "courseware"
COURSE_FILES = {
    "money-jobs": "01-money-jobs-courseware.md",
    "safety-net": "02-safety-net-courseware.md",
    "product-map": "03-product-map-courseware.md",
    "tradeoffs": "04-tradeoffs-courseware.md",
    "future-date": "05-future-date-courseware.md",
    "steady-mind": "06-steady-mind-courseware.md",
}

UNIT_EVIDENCE = {
    "money-jobs": {"ai-feedback-1": ("money-jobs.core-1", "money-jobs.core-2"), "ai-feedback-2": ("money-jobs.core-3",)},
    "safety-net": {"ai-feedback-1": ("safety-net.core-1", "safety-net.core-2"), "ai-feedback-2": ("safety-net.core-3",)},
    "product-map": {"ai-feedback-1": ("product-map.core-1", "product-map.core-2"), "ai-feedback-2": ("product-map.core-3",)},
    "tradeoffs": {"ai-feedback-1": ("tradeoffs.core-1",), "ai-feedback-2": ("tradeoffs.core-2", "tradeoffs.core-3")},
    "future-date": {"ai-feedback-1": ("future-date.core-1", "future-date.core-2"), "ai-feedback-2": ("future-date.core-3",)},
    "steady-mind": {"ai-feedback-1": ("steady-mind.core-1", "steady-mind.core-2"), "ai-feedback-2": ("steady-mind.core-1", "steady-mind.core-2", "steady-mind.core-3", "steady-mind.core-4")},
}


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    text: str
    boundary: str


@dataclass(frozen=True)
class Courseware:
    course_id: str
    title: str
    evidence: tuple[Evidence, ...]
    sources: tuple[str, ...]
    raw_text: str


@lru_cache(maxsize=6)
def load_courseware(course_id: str) -> Courseware:
    filename = COURSE_FILES.get(course_id)
    if filename is None:
        raise ValueError("unknown course")
    path = COURSEWARE_DIR / filename
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    evidence: list[Evidence] = []
    for line in text.splitlines():
        match = re.match(r"^\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$", line)
        if match:
            evidence.append(Evidence(match.group(1), match.group(2), match.group(3)))
    sources = tuple(dict.fromkeys(re.findall(r"\((https://[^)]+)\)", text)))
    if not evidence or not sources:
        raise ValueError(f"courseware is incomplete: {filename}")
    return Courseware(
        course_id=course_id,
        title=title_match.group(1) if title_match else course_id,
        evidence=tuple(evidence),
        sources=sources,
        raw_text=text,
    )


def evidence_for_unit(course_id: str, unit_id: str) -> tuple[Evidence, ...]:
    courseware = load_courseware(course_id)
    allowed = UNIT_EVIDENCE.get(course_id, {}).get(unit_id)
    if allowed is None:
        allowed = (courseware.evidence[0].evidence_id,)
    by_id = {item.evidence_id: item for item in courseware.evidence}
    return tuple(by_id[evidence_id] for evidence_id in allowed if evidence_id in by_id)
