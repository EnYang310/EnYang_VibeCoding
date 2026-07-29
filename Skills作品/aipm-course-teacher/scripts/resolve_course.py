#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references" / "course_catalog.md"


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def topic_keywords(topic: str) -> list[str]:
    normalized = normalize(topic)
    stop_words = {
        "ai",
        "pm",
        "aipm",
        "course",
        "lesson",
        "learn",
        "study",
        "about",
        "want",
    }
    keywords: list[str] = []
    for token in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", normalized):
        if token not in stop_words and token not in keywords:
            keywords.append(token)

    zh = re.sub(r"[a-zA-Z0-9_-]+", " ", topic)
    for phrase in ["我想学习", "我想学", "想学习", "想学", "学习", "课程", "上课", "讲讲", "给我讲", "一下", "这个"]:
        zh = zh.replace(phrase, " ")
    for token in re.findall(r"[\u4e00-\u9fff]{2,}", zh):
        if token not in keywords:
            keywords.append(token)
    return keywords


def parse_catalog() -> list[dict[str, str]]:
    if not CATALOG.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "Course ID" in s:
            continue
        cells = [c.strip().strip("`") for c in s.strip("|").split("|")]
        if len(cells) >= 5:
            rows.append({
                "id": cells[0],
                "name": cells[1],
                "audience": cells[2],
                "file": cells[3],
                "status": cells[4],
            })
    return rows


def content_contains(course_id: str, topic: str) -> bool:
    path = ROOT / "references" / "courses" / course_id / "course.md"
    if not path.exists():
        return False
    content = normalize(path.read_text(encoding="utf-8"))
    keywords = topic_keywords(topic)
    if not keywords:
        return False
    return any(keyword in content for keyword in keywords)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve whether a user topic selects a course, needs confirmation, or needs a new course."
    )
    parser.add_argument("--topic", default="")
    args = parser.parse_args()

    topic = normalize(args.topic)
    rows = [row for row in parse_catalog() if row["status"] == "active"]
    if not rows:
        print("STATUS=new_course_needed")
        print("REASON=no active courses registered")
        return 0
    if not topic:
        print("STATUS=needs_selection")
        print("REASON=no topic or course specified")
        return 0

    general_course_requests = [
        "aipm",
        "ai pm",
        "课程列表",
        "其他课程",
        "有哪些课程",
        "所有课程",
        "全部课程",
    ]
    if any(item in topic for item in general_course_requests):
        print("STATUS=needs_selection")
        print("REASON=general course request, not an explicit course selection")
        return 0

    explicit: list[dict[str, str]] = []
    for row in rows:
        course_id = normalize(row["id"])
        course_name = normalize(row["name"])
        if re.search(rf"\b{re.escape(course_id)}\b", topic) or course_name in topic:
            explicit.append(row)

    if len(explicit) == 1:
        print("STATUS=selected")
        print(f"COURSE={explicit[0]['id']}")
        print("REASON=explicit course id or name")
        return 0
    if len(explicit) > 1:
        print("STATUS=needs_selection")
        print("REASON=multiple explicit course matches")
        print("COURSES=" + ",".join(row["id"] for row in explicit))
        return 0

    print("STATUS=new_course_needed")
    print("REASON=topic is not an explicit registered course selection")
    content_matches = [row for row in rows if content_contains(row["id"], topic)]
    if content_matches:
        print("RELATED_COURSES=" + ",".join(row["id"] for row in content_matches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
