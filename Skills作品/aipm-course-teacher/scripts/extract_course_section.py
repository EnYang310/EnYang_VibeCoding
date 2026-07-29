#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def course_file(course: str) -> Path:
    return ROOT / "references" / "courses" / course / "course.md"


def heading_level(line: str) -> int | None:
    m = re.match(r"^(#{1,6})\s+", line)
    return len(m.group(1)) if m else None


def section_by_heading(lines: list[str], heading: str) -> tuple[int, int] | None:
    start = None
    level = None
    for i, line in enumerate(lines):
        if line.strip() == heading.strip():
            start = i
            level = heading_level(line) or 2
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        lv = heading_level(lines[j])
        if lv is not None and lv <= level:
            end = j
            break
    return start, end


def section_around_query(lines: list[str], query: str) -> tuple[int, int] | None:
    q = query.lower()
    hit = None
    for i, line in enumerate(lines):
        if q in line.lower():
            hit = i
            break
    if hit is None:
        return None
    start = 0
    level = 2
    for i in range(hit, -1, -1):
        lv = heading_level(lines[i])
        if lv is not None and lv <= 3:
            start = i
            level = lv
            break
    end = len(lines)
    for j in range(start + 1, len(lines)):
        lv = heading_level(lines[j])
        if lv is not None and lv <= level:
            end = j
            break
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--heading")
    group.add_argument("--query")
    parser.add_argument("--max-lines", type=int, default=180)
    args = parser.parse_args()

    path = course_file(args.course)
    if not path.exists():
        print(f"Course not found: {args.course}")
        return 1
    lines = path.read_text(encoding="utf-8").splitlines()
    span = section_by_heading(lines, args.heading) if args.heading else section_around_query(lines, args.query)
    if span is None:
        print("No matching section found.")
        return 1
    start, end = span
    end = min(end, start + args.max_lines)
    print(f"<!-- course={args.course} lines={start + 1}-{end} -->")
    print("\n".join(lines[start:end]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

